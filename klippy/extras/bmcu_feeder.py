"""
bmcu_feeder.py — Klipper extra for BMCU 370C multi-channel feeder control.

Exposes per-channel filament runout/blockage detection and feeder motor
control over USB serial. Drop this file into ~/klipper/klippy/extras/ and
restart Klipper.

Phase 2 plan 01: BmcuSerial, BmcuChannel, BmcuFeeder foundation.
Phase 2 plan 02: GCode commands, polling timer, STATUS response parser.
"""

import serial
import logging
import re

# ---------------------------------------------------------------------------
# Module-level regex for parsing multi-channel STATUS response lines
# ---------------------------------------------------------------------------

_STATUS_FIELD_RE = re.compile(
    r'ch=(\d) fil=(\d) mot=(\d) spd=(\d+) dir=(\w+) mm=(-?[\d.]+) mag=(\w+)')

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BmcuSerial — non-blocking serial I/O via Klipper reactor fd-watching
# ---------------------------------------------------------------------------

class BmcuSerial:
    """Opens a serial port in non-blocking mode (timeout=0) and registers the
    file descriptor with the Klipper reactor so that _handle_rx is called
    whenever bytes are available — no blocking reads, no background threads.
    """

    def __init__(self, port, baud, reactor):
        self._port = port
        self._baud = baud
        self._reactor = reactor
        self._serial = None
        self._fd_handle = None
        self._buf = b""
        self._lines = []   # (kind, content) tuples — drained by get_lines()

    def connect(self):
        """Open serial port and register fd with reactor."""
        self._serial = serial.Serial(self._port, self._baud, timeout=0)
        self._fd_handle = self._reactor.register_fd(
            self._serial.fileno(), self._handle_rx)
        logger.info("BMCU: serial connected on %s" % self._port)

    def disconnect(self):
        """Unregister fd and close serial port."""
        if self._fd_handle is not None:
            self._reactor.unregister_fd(self._fd_handle)
            self._fd_handle = None
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None
        logger.info("BMCU: serial disconnected")

    def send(self, line: str):
        """Write an ASCII line to the serial port."""
        if self._serial is not None and self._serial.is_open:
            self._serial.write(line.encode('ascii'))

    def _handle_rx(self, eventtime):
        """Reactor fd callback — reads available bytes and assembles lines."""
        try:
            data = self._serial.read(256)
        except (OSError, serial.SerialException) as e:
            self._lines.append(('ERROR', str(e)))
            return
        self._buf += data
        while b'\n' in self._buf:
            raw, self._buf = self._buf.split(b'\n', 1)
            self._lines.append(
                ('LINE', raw.decode('ascii', errors='replace').strip()))

    def get_lines(self):
        """Drain and return all complete lines accumulated since last call."""
        out, self._lines = self._lines[:], []
        return out


# ---------------------------------------------------------------------------
# BmcuChannel — per-channel config and state model
# ---------------------------------------------------------------------------

class BmcuChannel:
    """Represents one [bmcu_channel N] config section.

    Created by Klipper's load_config_prefix mechanism; BmcuFeeder discovers
    instances via printer.lookup_object('bmcu_channel N').
    """

    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        # Parse channel_id from section name: "bmcu_channel 0" -> 0
        self.channel_id = int(self.name.split()[-1])
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.extruder = config.get('extruder', None)
        self.event_delay = config.getfloat('event_delay', 3., minval=0.)
        self.pause_on_runout = config.getboolean('pause_on_runout', True)
        self.stall_threshold_mm = config.getfloat('stall_threshold_mm', 0.5,
                                                   minval=0.1)
        self.stall_debounce_count = config.getint('stall_debounce_count', 3,
                                                   minval=1)
        self.stall_startup_ignore_polls = config.getint(
            'stall_startup_ignore_polls', 2, minval=0)
        self._stall_counter = 0
        self._startup_polls_remaining = 0
        self._direction_just_changed = False
        self.sensor_enabled = True
        self.min_event_systime = 0.
        self.runout_gcode = gcode_macro.load_template(config, 'runout_gcode', '')
        self.insert_gcode = gcode_macro.load_template(config, 'insert_gcode', '')
        self.stall_gcode = gcode_macro.load_template(config, 'stall_gcode', '')
        self.state = {
            'filament_present': False,
            'motor_running': False,
            'speed': 0,
            'direction': 'FWD',
            'feed_mm': 0.0,
            'mag_status': 'unknown',
        }

    def cmd_set_sensor(self, gcmd):
        """GCode handler for SET_BMCU_SENSOR CHANNEL=N ENABLE=0|1."""
        enable = gcmd.get_int('ENABLE', minval=0, maxval=1)
        self.sensor_enabled = bool(enable)
        gcmd.respond_info("BMCU channel %d sensor %s" %
                         (self.channel_id,
                          "enabled" if self.sensor_enabled else "disabled"))


# ---------------------------------------------------------------------------
# BmcuFeeder — top-level extra; single instance per [bmcu_feeder] section
# ---------------------------------------------------------------------------

class BmcuFeeder:
    """Top-level Klipper extra.  One [bmcu_feeder] section per BMCU unit.

    Discovers [bmcu_channel N] sections, opens serial in klippy:connect,
    starts poll timer in klippy:ready, tears down in klippy:disconnect.
    """

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.serial_port = config.get('serial')
        # Warn if serial path is bare ttyUSB/ttyACM — unstable across reboots
        if ('ttyUSB' in self.serial_port or 'ttyACM' in self.serial_port) \
                and 'by-path' not in self.serial_port \
                and 'by-id' not in self.serial_port:
            raise config.error(
                "BMCU: serial path must use /dev/serial/by-path/ for stable "
                "device assignment (got: %s)" % self.serial_port)
        self.baud = config.getint('baud', 115200)
        self.poll_interval = config.getfloat('poll_interval', 0.5, minval=0.1)
        self._serial = None
        self._poll_timer_handle = None
        self._prev_mm = {}
        self._channels = {}
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:disconnect",
                                            self._handle_disconnect)
        self.printer.add_object('bmcu_feeder', self)
        self._register_commands()

    def _handle_connect(self):
        """Discover channels and open serial port."""
        # Discover BmcuChannel objects created by load_config_prefix
        for i in range(4):
            try:
                ch = self.printer.lookup_object('bmcu_channel %d' % i)
                self._channels[i] = ch
            except Exception:
                pass
        if not self._channels:
            raise self.printer.config_error(
                "BMCU: no [bmcu_channel N] sections found in config")
        self._register_sensor_commands()
        # Open serial
        try:
            self._serial = BmcuSerial(self.serial_port, self.baud, self.reactor)
            self._serial.connect()
        except Exception as e:
            raise self.printer.config_error(
                "BMCU: cannot open serial port %s: %s" % (self.serial_port, e))

    def _handle_ready(self):
        """Start polling timer.  Must not raise exceptions per Klipper spec."""
        self._poll_timer_handle = self.reactor.register_timer(
            self._poll_status,
            self.reactor.monotonic() + self.poll_interval)

    def _handle_disconnect(self):
        """Tear down timer and serial connection."""
        if self._poll_timer_handle is not None:
            self.reactor.unregister_timer(self._poll_timer_handle)
            self._poll_timer_handle = None
        if self._serial is not None:
            self._serial.disconnect()
            self._serial = None

    def _register_commands(self):
        """Register the five feeder-wide GCode commands.

        SET_BMCU_SENSOR mux commands are registered per-channel after channel
        discovery in _handle_connect, once _channels is populated.
        """
        self.gcode.register_command(
            'BMCU_RUN', self._cmd_run,
            desc="Run BMCU feeder motor: BMCU_RUN CHANNEL=0")
        self.gcode.register_command(
            'BMCU_STOP', self._cmd_stop,
            desc="Stop BMCU feeder motor: BMCU_STOP CHANNEL=0")
        self.gcode.register_command(
            'BMCU_STATUS', self._cmd_status,
            desc="Print per-channel BMCU status table")
        self.gcode.register_command(
            'BMCU_SPEED', self._cmd_speed,
            desc="Set BMCU motor speed: BMCU_SPEED CHANNEL=0 SPEED=75")
        self.gcode.register_command(
            'BMCU_DIR', self._cmd_dir,
            desc="Set BMCU motor direction: BMCU_DIR CHANNEL=0 DIR=FWD")

    def _register_sensor_commands(self):
        """Register per-channel SET_BMCU_SENSOR mux commands.

        Called from _handle_connect after _channels is populated.
        """
        for ch_id, ch in self._channels.items():
            self.gcode.register_mux_command(
                'SET_BMCU_SENSOR', 'CHANNEL', str(ch_id),
                ch.cmd_set_sensor,
                desc="Enable/disable BMCU sensor for channel %d" % ch_id)

    def _cmd_run(self, gcmd):
        ch_id = gcmd.get_int('CHANNEL', minval=0, maxval=3)
        if ch_id not in self._channels:
            gcmd.respond_info("BMCU: channel %d not configured" % ch_id)
            return
        self._serial.send("RUN %d\n" % ch_id)

    def _cmd_stop(self, gcmd):
        ch_id = gcmd.get_int('CHANNEL', minval=0, maxval=3)
        if ch_id not in self._channels:
            gcmd.respond_info("BMCU: channel %d not configured" % ch_id)
            return
        self._serial.send("STOP %d\n" % ch_id)

    def _cmd_speed(self, gcmd):
        ch_id = gcmd.get_int('CHANNEL', minval=0, maxval=3)
        speed = gcmd.get_int('SPEED', minval=0, maxval=100)
        if ch_id not in self._channels:
            gcmd.respond_info("BMCU: channel %d not configured" % ch_id)
            return
        self._serial.send("SPEED %d %d\n" % (ch_id, speed))

    def _cmd_dir(self, gcmd):
        ch_id = gcmd.get_int('CHANNEL', minval=0, maxval=3)
        direction = gcmd.get('DIR')
        if direction not in ('FWD', 'REV'):
            raise gcmd.error("BMCU: DIR must be FWD or REV, got '%s'" % direction)
        if ch_id not in self._channels:
            gcmd.respond_info("BMCU: channel %d not configured" % ch_id)
            return
        self._serial.send("DIR %d %s\n" % (ch_id, direction))

    def _cmd_status(self, gcmd):
        lines = ["BMCU Status:"]
        lines.append("%-4s %-8s %-7s %-6s %-5s %-9s %-8s" %
                     ("CH", "Filament", "Motor", "Speed", "Dir", "Feed(mm)", "Magnet"))
        lines.append("-" * 55)
        for ch_id in sorted(self._channels.keys()):
            s = self._channels[ch_id].state
            lines.append("%-4d %-8s %-7s %-6d %-5s %-9.1f %-8s" % (
                ch_id,
                "present" if s.get('filament_present') else "absent",
                "running" if s.get('motor_running') else "stopped",
                s.get('speed', 0),
                s.get('direction', 'FWD'),
                s.get('feed_mm', 0.0),
                s.get('mag_status', '?'),
            ))
        gcmd.respond_info('\n'.join(lines))

    def _poll_status(self, eventtime):
        """Reactor timer callback — drain queued lines, send STATUS query, reschedule."""
        for kind, content in self._serial.get_lines():
            if kind == 'ERROR':
                self._handle_serial_error(content)
            elif content.startswith('STATUS ok'):
                self._dispatch_status_line(content)
        self._serial.send("STATUS\n")
        return eventtime + self.poll_interval

    def _dispatch_status_line(self, line):
        """Parse a STATUS ok response and update per-channel state dicts."""
        for m in _STATUS_FIELD_RE.finditer(line):
            ch_id = int(m.group(1))
            if ch_id not in self._channels:
                continue
            ch = self._channels[ch_id]
            old_state = dict(ch.state)
            ch.state.update({
                'filament_present': m.group(2) == '1',
                'motor_running':    m.group(3) == '1',
                'speed':            int(m.group(4)),
                'direction':        m.group(5),
                'feed_mm':          float(m.group(6)),
                'mag_status':       m.group(7),
            })
            self._check_events(ch, old_state)

    def _check_events(self, ch, old_state):
        now = self.reactor.monotonic()
        if now < ch.min_event_systime or not ch.sensor_enabled:
            return
        old_fil = old_state.get('filament_present')
        new_fil = ch.state['filament_present']
        # Runout: was present, now absent — only during printing
        if old_fil and not new_fil:
            idle_timeout = self.printer.lookup_object('idle_timeout')
            is_printing = idle_timeout.get_status(now)['state'] == 'Printing'
            if is_printing and ch.runout_gcode is not None:
                ch.min_event_systime = self.reactor.NEVER
                self.reactor.register_callback(
                    lambda et, c=ch: self._runout_handler(et, c))
        # Insert: was absent, now present — fires unconditionally
        # (user always wants to know filament is back, regardless of print state)
        elif not old_fil and new_fil:
            if ch.insert_gcode is not None:
                ch.min_event_systime = self.reactor.NEVER
                self.reactor.register_callback(
                    lambda et, c=ch: self._insert_handler(et, c))
        # --- Motor start detection: reset startup grace and stall counter ---
        old_mot = old_state.get('motor_running', False)
        new_mot = ch.state['motor_running']
        if not old_mot and new_mot:
            ch._startup_polls_remaining = ch.stall_startup_ignore_polls
            ch._stall_counter = 0

        # --- Direction-change detection: reset _prev_mm and set suppression flag ---
        old_dir = old_state.get('direction', 'FWD')
        new_dir = ch.state['direction']
        if old_dir != new_dir:
            self._prev_mm[ch.channel_id] = ch.state['feed_mm']
            ch._stall_counter = 0
            ch._direction_just_changed = True

        # --- Debounced blockage detection ---
        if ch.state['filament_present'] and ch.state['motor_running']:
            if ch.channel_id in self._prev_mm:
                delta = abs(ch.state['feed_mm'] - self._prev_mm[ch.channel_id])
                if ch._direction_just_changed:
                    # Skip stall-counter evaluation on the direction-change poll.
                    ch._direction_just_changed = False
                elif ch._startup_polls_remaining > 0:
                    ch._startup_polls_remaining -= 1
                    ch._stall_counter = 0
                elif delta < ch.stall_threshold_mm:
                    ch._stall_counter += 1
                else:
                    ch._stall_counter = 0
                if (ch._stall_counter >= ch.stall_debounce_count
                        and ch.stall_gcode is not None
                        and now >= ch.min_event_systime
                        and ch.sensor_enabled):
                    ch._stall_counter = 0
                    ch.min_event_systime = self.reactor.NEVER
                    logging.info("BMCU ch%d: blockage detected (delta_mm=%.2f)" %
                                 (ch.channel_id, delta))
                    self.reactor.register_callback(
                        lambda et, c=ch: self._stall_handler(et, c))
        else:
            ch._stall_counter = 0
            ch._startup_polls_remaining = 0
            ch._direction_just_changed = False
        self._prev_mm[ch.channel_id] = ch.state['feed_mm']

    def _runout_handler(self, eventtime, ch):
        if ch.pause_on_runout:
            pause_resume = self.printer.lookup_object('pause_resume')
            pause_resume.send_pause_command()
        self._exec_gcode(ch, ch.runout_gcode)

    def _insert_handler(self, eventtime, ch):
        self._exec_gcode(ch, ch.insert_gcode)

    def _stall_handler(self, eventtime, ch):
        self._exec_gcode(ch, ch.stall_gcode)

    def _exec_gcode(self, ch, template):
        try:
            self.gcode.run_script("" + template.render() + "\nM400")
        except Exception:
            logging.exception("BMCU: script error on channel %d" % ch.channel_id)
        ch.min_event_systime = self.reactor.monotonic() + ch.event_delay

    def _handle_serial_error(self, msg):
        logging.error("BMCU serial error: %s" % msg)
        for ch in self._channels.values():
            if ch.state.get('motor_running') and ch.sensor_enabled:
                self.reactor.register_callback(
                    lambda et, c=ch: self._runout_handler(et, c))

    def get_status(self, eventtime):
        """Return a new dict each call for Moonraker change detection."""
        return {
            'channels': {
                str(ch_id): {
                    'filament_present': bool(
                        ch.state.get('filament_present', False)),
                    'motor_running': bool(ch.state.get('motor_running', False)),
                    'feed_mm': float(ch.state.get('feed_mm', 0.0)),
                    'speed': int(ch.state.get('speed', 0)),
                    'direction': str(ch.state.get('direction', 'FWD')),
                    'mag_status': str(ch.state.get('mag_status', 'unknown')),
                    'sensor_enabled': bool(ch.sensor_enabled),
                }
                for ch_id, ch in self._channels.items()
            }
        }


# ---------------------------------------------------------------------------
# Module entry points (called by Klipper config system)
# ---------------------------------------------------------------------------

def load_config(config):
    return BmcuFeeder(config)

def load_config_prefix(config):
    return BmcuChannel(config)
