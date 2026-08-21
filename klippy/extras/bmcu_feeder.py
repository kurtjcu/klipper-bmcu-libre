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
import time as _time

# ---------------------------------------------------------------------------
# Module-level regex for parsing multi-channel STATUS response lines
# ---------------------------------------------------------------------------

_STATUS_FIELD_RE = re.compile(
    r'ch=(\d) ins=(\d) fil=(\d) mot=(\d) spd=(\d+) dir=(\w+) mm=(-?[\d.]+) mag=(\w+)')

logger = logging.getLogger(__name__)

# Encoder-fault debounce (E77-D): number of consecutive non-ok, non-unknown
# mag_status polls required before a channel is treated as faulted. A
# constant, not a config option -- this module's failures have all come
# from interacting knobs, and 3 polls at the default poll_interval (0.5s)
# is 1.5s of sustained I2C silence.
_MAG_FAULT_DEBOUNCE_POLLS = 3

# Reachability warning threshold (E77-F): implied minimum sustained
# extrusion rate (min_commanded_mm / stall_timeout_s) above which the
# detector may never fire at typical print rates.
_STALL_RATE_WARNING_MMS = 2.0


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
        """Open serial port, wait for BOOT, send ENABLE, and register fd with reactor."""
        MAX_ENABLE_ATTEMPTS = 3
        ENABLE_RETRY_DELAY = 2.0
        s = serial.Serial()
        s.port = self._port
        s.baudrate = self._baud
        s.timeout = 5  # blocking mode for BOOT/ENABLE handshake
        s.dsrdtr = False
        s.rtscts = False
        s.open()
        # CH340 RTS controls NRST — keep deasserted to avoid resetting MCU
        s.dtr = True
        s.rts = False
        # Wait for BOOT message (5-second deadline)
        boot_seen = False
        deadline = _time.monotonic() + 5.0
        while _time.monotonic() < deadline:
            raw = s.readline()
            if not raw:
                break
            text = raw.decode('ascii', errors='replace').strip()
            if text:
                logger.info("BMCU: boot line: %s" % text)
            if text.startswith("BOOT"):
                boot_seen = True
                break
        if not boot_seen:
            logger.warning("BMCU: no BOOT message received within 5s — proceeding to ENABLE")
        # Send ENABLE and retry up to MAX_ENABLE_ATTEMPTS times
        for attempt in range(MAX_ENABLE_ATTEMPTS):
            s.write(b"ENABLE\n")
            resp = s.readline().decode('ascii', errors='replace').strip()
            logger.info("BMCU: ENABLE attempt %d response: %s" % (attempt + 1, resp))
            if resp.startswith("ENABLE ok"):
                break
            logger.warning("BMCU: ENABLE attempt %d failed, retrying..." % (attempt + 1))
            if attempt < MAX_ENABLE_ATTEMPTS - 1:
                _time.sleep(ENABLE_RETRY_DELAY)
        else:
            raise Exception(
                "BMCU: ENABLE handshake failed after %d attempts — "
                "check wiring, firmware, and power" % MAX_ENABLE_ATTEMPTS)
        # Switch to non-blocking for reactor fd-watching
        s.timeout = 0
        self._serial = s
        logger.info("BMCU: serial connected and enabled on %s" % self._port)
        self._fd_handle = self._reactor.register_fd(
            self._serial.fileno(), self._handle_rx)

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
        self.direction_invert = config.getboolean('direction_invert', False)
        # Passive-encoder support: default True preserves the historical
        # gate (stall detection requires the BMCU's own feeder motor to be
        # running). Set False per channel when the BMCU is used as a
        # passive encoder and the toolhead extruder is what pulls the
        # filament, so the feeder motor never runs during a print.
        self.require_motor_running = config.getboolean(
            'require_motor_running', True)
        # Mirrors pause_on_runout: pause the print on a detected blockage
        # independently of whether stall_gcode is configured/succeeds.
        self.pause_on_stall = config.getboolean('pause_on_stall', True)
        # A dead encoder is a loss of observability, not a detected
        # failure -- pausing a healthy print because a sensor went quiet
        # destroys good work to protect against a jam that may not exist.
        # Defaults False; opt in per channel to stop rather than print
        # unwatched.
        self.pause_on_encoder_fault = config.getboolean(
            'pause_on_encoder_fault', False)
        # Activity (liveness) stall detection: fires when the encoder shows
        # no meaningful movement for stall_timeout_s while at least
        # min_commanded_mm of forward extrusion was commanded in that span.
        # No ratio, no correlation, no window list -- one time base.
        self.min_commanded_mm = config.getfloat(
            'min_commanded_mm', 5.0, minval=0.1)
        self.stall_timeout_s = config.getfloat(
            'stall_timeout_s', 15.0, minval=1.0)
        self.min_measured_mm = config.getfloat(
            'min_measured_mm', 1.0, minval=0.1)
        # Deprecated (E77-A): read as documented no-ops so an existing
        # printer.cfg that still sets these does not hard-error at startup
        # -- Klipper rejects a config option no module reads. Compared with
        # `is not None`, never truthiness -- a configured 0 is falsy but
        # present. Values are intentionally not stored or consulted.
        self._deprecated_present = []
        for _dep_name in ('slip_ratio', 'stall_window_polls',
                           'stall_startup_ignore_polls'):
            if config.get(_dep_name, None) is not None:
                self._deprecated_present.append(_dep_name)
        # Activity tracker: encoder reading/time at last confirmed movement,
        # and forward commanded mm accumulated since then.
        self._measured_ref = None
        self._last_movement_time = None
        self._commanded_since_movement = 0.0
        self._prev_commanded_pos = None
        # Stashed values at fire time, read by _stall_handler.
        self._stall_commanded_mm = 0.0
        self._stall_measured_mm = 0.0
        self._stall_stalled_s = 0.0
        # Resolved at ready-time (BmcuFeeder._handle_ready): the extruder
        # object for find_past_position, and whether stall detection is
        # possible at all for this channel (False when extruder is None).
        self._extruder_obj = None
        self._stall_enabled = True
        self._stall_eligible_prev = False
        # Encoder-fault debounce (E77-D): a non-ok, non-unknown mag_status
        # must persist for _MAG_FAULT_DEBOUNCE_POLLS before it is trusted --
        # the BOOT line reports all magnets offline transiently before
        # ENABLE returns ok, so acting on the raw boot value would fault
        # every startup.
        self._mag_faulted = False
        self._mag_fault_streak = 0
        self._feed_mm_at_reset = 0.0
        self._lifetime_stall_count = 0
        self._feed_mm_initialized = False
        self.sensor_enabled = True
        self.min_event_systime = 0.
        self.runout_gcode = gcode_macro.load_template(config, 'runout_gcode', '')
        self.insert_gcode = gcode_macro.load_template(config, 'insert_gcode', '')
        self.stall_gcode = gcode_macro.load_template(config, 'stall_gcode', '')
        self.state = {
            'channel_inserted': False,
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
        self._channels = {}
        self._estimated_print_time = None
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
        """Resolve per-channel extruder objects, cache estimated_print_time,
        and start the polling timer.  Must not raise exceptions per Klipper
        spec — any lookup failure disables stall detection for that channel
        rather than propagating.
        """
        self._estimated_print_time = self.printer.lookup_object(
            'mcu').estimated_print_time
        for ch in self._channels.values():
            if ch.extruder is None:
                ch._extruder_obj = None
                ch._stall_enabled = False
                logging.warning(
                    "BMCU ch%d: no extruder configured — stall detection disabled"
                    % ch.channel_id)
                continue
            try:
                ch._extruder_obj = self.printer.lookup_object(ch.extruder)
                ch._stall_enabled = True
            except Exception:
                ch._extruder_obj = None
                ch._stall_enabled = False
                logging.warning(
                    "BMCU ch%d: extruder '%s' not found — stall detection disabled"
                    % (ch.channel_id, ch.extruder))
        for ch in self._channels.values():
            # Deprecated-option notice (E77-A). Ready-time rather than
            # config-time: a config-time log lands only in klippy.log
            # where nobody looks, whereas respond_info at ready surfaces
            # it once in the console, and _handle_ready is already this
            # module's per-channel validation point.
            if ch._deprecated_present:
                msg = (
                    "BMCU ch%d: config option(s) %s are deprecated and "
                    "ignored — remove them from printer.cfg" %
                    (ch.channel_id, ", ".join(ch._deprecated_present)))
                logging.warning(msg)
                self.gcode.respond_info(msg)
            # Reachability (E77-F). Advisory only — never raise from
            # _handle_ready, Klipper forbids it. Skipped entirely when
            # stall detection is disabled for this channel, so an
            # extruder-less channel still logs exactly one warning.
            if ch._stall_enabled:
                rate = ch.min_commanded_mm / ch.stall_timeout_s
                logging.info(
                    "BMCU ch%d: stall detector implied minimum sustained "
                    "extrusion rate %.3f mm/s (min_commanded_mm=%.2f / "
                    "stall_timeout_s=%.1f)" %
                    (ch.channel_id, rate, ch.min_commanded_mm,
                     ch.stall_timeout_s))
                if rate > _STALL_RATE_WARNING_MMS:
                    msg = (
                        "BMCU ch%d: stall detector may never fire at "
                        "typical print rates — implied minimum sustained "
                        "extrusion rate is %.3f mm/s" %
                        (ch.channel_id, rate))
                    logging.warning(msg)
                    self.gcode.respond_info(msg)
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
        self.gcode.register_command(
            'BMCU_RESET_FEED', self._cmd_reset_feed,
            desc="Reset BMCU feed distance counter: BMCU_RESET_FEED [CHANNEL=0]")
        self.gcode.register_command(
            'BMCU_ENABLE', self._cmd_enable,
            desc="Send ENABLE to BMCU firmware (init hardware)")
        self.gcode.register_command(
            'BMCU_DISCONNECT', self._cmd_disconnect,
            desc="Disconnect BMCU serial port (for flashing)")
        self.gcode.register_command(
            'BMCU_CONNECT', self._cmd_connect,
            desc="Reconnect BMCU serial port after flashing")

    def _cmd_enable(self, gcmd):
        if self._serial is None:
            gcmd.respond_info("BMCU: not connected — run BMCU_CONNECT first")
            return
        self._serial._serial.timeout = 2
        self._serial.send("ENABLE\n")
        resp = self._serial._serial.readline().decode('ascii', errors='replace').strip()
        self._serial._serial.timeout = 0
        gcmd.respond_info("BMCU: ENABLE response: %s" % resp)

    def _cmd_disconnect(self, gcmd):
        """Send DISABLE, stop polling, and release serial port."""
        if self._poll_timer_handle is not None:
            self.reactor.unregister_timer(self._poll_timer_handle)
            self._poll_timer_handle = None
        if self._serial is not None:
            self._serial.send("DISABLE\n")
            _time.sleep(0.2)
            self._serial.disconnect()
            self._serial = None
            gcmd.respond_info("BMCU: disabled and serial port released — safe to flash")
        else:
            gcmd.respond_info("BMCU: already disconnected")

    def _cmd_connect(self, gcmd):
        """Reconnect serial port and resume polling."""
        if self._serial is not None:
            gcmd.respond_info("BMCU: already connected")
            return
        try:
            self._serial = BmcuSerial(self.serial_port, self.baud, self.reactor)
            self._serial.connect()
            self._poll_timer_handle = self.reactor.register_timer(
                self._poll_status,
                self.reactor.monotonic() + self.poll_interval)
            gcmd.respond_info("BMCU: reconnected and polling on %s"
                              % self.serial_port)
        except Exception as e:
            gcmd.respond_info("BMCU: reconnect failed — %s" % str(e))

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
        ch = self._channels[ch_id]
        if ch.direction_invert:
            wire_dir = 'REV' if direction == 'FWD' else 'FWD'
        else:
            wire_dir = direction
        self._serial.send("DIR %d %s\n" % (ch_id, wire_dir))

    def _cmd_reset_feed(self, gcmd):
        ch_id = gcmd.get_int('CHANNEL', default=None, minval=0, maxval=3)
        if ch_id is not None:
            if ch_id not in self._channels:
                gcmd.respond_info("BMCU: channel %d not configured" % ch_id)
                return
            ch = self._channels[ch_id]
            ch._feed_mm_at_reset = ch.state.get('feed_mm', 0.0)
            ch._lifetime_stall_count = 0
            self._reset_activity_tracker(ch)
            gcmd.respond_info("BMCU channel %d feed counter reset" % ch_id)
        else:
            for cid, ch in self._channels.items():
                ch._feed_mm_at_reset = ch.state.get('feed_mm', 0.0)
                ch._lifetime_stall_count = 0
                self._reset_activity_tracker(ch)
            gcmd.respond_info("BMCU all channels feed counter reset")

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
                'channel_inserted': m.group(2) == '1',
                'filament_present': m.group(3) != '0',
                'motor_running':    m.group(4) == '1',
                'speed':            int(m.group(5)),
                'direction':        m.group(6),
                'feed_mm':          float(m.group(7)),
                'mag_status':       m.group(8),
            })
            if not ch._feed_mm_initialized:
                ch._feed_mm_at_reset = ch.state['feed_mm']
                ch._feed_mm_initialized = True
            self._check_events(ch, old_state)

    def _stall_eligible(self, ch):
        """Whether the current poll should accumulate into the stall window:
        filament present, the channel sensor enabled, and either the motor
        is running or require_motor_running has been relaxed for a
        passive-encoder setup.

        Reads ch.state and ch.sensor_enabled directly (no old_state
        argument) — sensor_enabled is a channel attribute, never
        snapshotted into old_state.

        ch.sensor_enabled is deliberately included here, a widening beyond
        the literal passive-encoder proposal: sensor_enabled was previously
        consulted only at fire time, so the window kept accumulating while
        the sensor was administratively disabled and could fire off a stale
        window the instant it was re-enabled. On an active channel the
        toolchanger's BMCU_STOP masked that via motor_running; on a passive
        channel nothing masks it, so sensor_enabled becomes the
        passive-mode equivalent of the motor-stop reset.

        not ch._mag_faulted (E77-D, E77-G) folds the encoder-fault gate
        into this SAME local rather than a second, parallel condition at
        the call site — two gating expressions drifting apart is exactly
        how the trailing else went stale in 260821-akv.
        """
        return (ch.state['filament_present'] and ch.sensor_enabled and
                not ch._mag_faulted and
                (ch.state['motor_running'] or not ch.require_motor_running))

    def _check_events(self, ch, old_state):
        now = self.reactor.monotonic()
        # Encoder health is a sensor-liveness fact, not a print event, so it
        # must keep tracking while runout/stall events are debounced by
        # min_event_systime below; it is edge-triggered itself, so it
        # cannot spam.
        self._update_encoder_fault(ch)
        if now < ch.min_event_systime:
            return
        old_fil = old_state.get('filament_present')
        new_fil = ch.state['filament_present']
        if ch.sensor_enabled:
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

        # --- Stall eligibility transition: re-baseline the activity tracker
        # on a not-eligible -> eligible transition. RETAIN this transition
        # reset rather than relying on the trailing ineligible branch alone:
        # _check_events returns early above while now is below
        # ch.min_event_systime, so a channel that goes ineligible and back
        # inside a suppression window would otherwise resume against a
        # stale _last_movement_time. _stall_eligible_prev exists for
        # exactly that; it is not dead state.
        stall_eligible = self._stall_eligible(ch)
        if stall_eligible and not ch._stall_eligible_prev:
            self._reset_activity_tracker(ch)
        ch._stall_eligible_prev = stall_eligible

        # --- Activity (liveness) stall detection ---
        # Fires when, over the trailing stall_timeout_s, forward commanded
        # extrusion reaches min_commanded_mm while total encoder movement
        # stays under min_measured_mm. Movement is judged as ABSOLUTE
        # displacement from _measured_ref, so a reversal reads as liveness,
        # not as shortfall — no direction-change special-casing is needed.
        # Only FORWARD commanded delta accumulates into
        # _commanded_since_movement, which is the entire retraction
        # tolerance.
        #
        # The elif and the trailing else below both read the SAME
        # stall_eligible local computed above — the else must not fall back
        # to a motor-only condition, or it would wipe the tracker every
        # poll on a passive channel and the require_motor_running
        # relaxation would be inert.
        if not ch._stall_enabled:
            # No extruder configured (no ground truth) — stall detection is
            # disabled entirely for this channel. Runout/insert are unaffected.
            pass
        elif stall_eligible:
            # Hoisted once for the whole arm: ch._stall_enabled is already
            # known true here, so ch._extruder_obj is not None.
            now_print_time = self._estimated_print_time(now)
            commanded_pos = ch._extruder_obj.find_past_position(now_print_time)
            measured_pos = ch.state['feed_mm']
            if ch._measured_ref is None:
                # First sample after a reset — nothing to compare against
                # yet; this poll only establishes the baseline.
                self._take_activity_baseline(ch, now, commanded_pos, measured_pos)
            else:
                commanded_delta = commanded_pos - ch._prev_commanded_pos
                ch._prev_commanded_pos = commanded_pos
                if abs(measured_pos - ch._measured_ref) >= ch.min_measured_mm:
                    # Movement confirmed — the encoder is alive. Re-baseline
                    # from this poll rather than resetting to None, so the
                    # next poll can evaluate immediately.
                    self._take_activity_baseline(ch, now, commanded_pos, measured_pos)
                else:
                    # Retraction handling: only FORWARD commanded movement
                    # accumulates. A pure retraction/travel poll
                    # (commanded_delta <= 0) adds 0, so
                    # _commanded_since_movement stays below
                    # min_commanded_mm and no stall is evaluated.
                    ch._commanded_since_movement += max(commanded_delta, 0.0)
                    if (now - ch._last_movement_time >= ch.stall_timeout_s
                            and ch._commanded_since_movement >= ch.min_commanded_mm
                            and now >= ch.min_event_systime
                            and ch.sensor_enabled):
                        ch._lifetime_stall_count += 1
                        ch.min_event_systime = self.reactor.NEVER
                        ch._stall_commanded_mm = ch._commanded_since_movement
                        ch._stall_stalled_s = now - ch._last_movement_time
                        ch._stall_measured_mm = abs(
                            measured_pos - ch._measured_ref)
                        logging.info(
                            "BMCU ch%d: blockage detected commanded=%.2fmm "
                            "stalled=%.1fs measured=%.2fmm total_stalls=%d" %
                            (ch.channel_id, ch._stall_commanded_mm,
                             ch._stall_stalled_s, ch._stall_measured_mm,
                             ch._lifetime_stall_count))
                        self._reset_activity_tracker(ch)
                        self.reactor.register_callback(
                            lambda et, c=ch: self._stall_handler(et, c))
        else:
            self._reset_activity_tracker(ch)

    def _reset_activity_tracker(self, ch):
        """Clear the activity tracker, to be re-established from scratch on
        the next eligible poll.  Used where the current sample is itself
        untrustworthy or unavailable: the not-eligible-to-eligible
        transition, the trailing ineligible else, and the post-fire reset.
        See _take_activity_baseline for the case where the current sample
        IS trustworthy as a baseline.
        """
        ch._measured_ref = None
        ch._last_movement_time = None
        ch._prev_commanded_pos = None
        ch._commanded_since_movement = 0.0

    def _take_activity_baseline(self, ch, now, commanded_pos, measured_pos):
        """Set the activity tracker baseline directly from the CURRENT
        poll's values — the encoder is confirmed alive (or the tracker is
        being established for the first time) as of this poll.
        """
        ch._measured_ref = measured_pos
        ch._last_movement_time = now
        ch._prev_commanded_pos = commanded_pos
        ch._commanded_since_movement = 0.0

    def _update_encoder_fault(self, ch):
        """Debounced mag_status health check (E77-D). 'ok', 'unknown' and
        empty are healthy -- 'unknown' is the module's own initial value
        and what a channel reports before its first STATUS ok line, so it
        must never count as a fault (treating it as one would disable
        stall detection for every channel that has not yet reported in).
        Anything else (low/high/offline/OFFLINE/...) is unhealthy; after
        _MAG_FAULT_DEBOUNCE_POLLS consecutive unhealthy polls the channel
        is marked faulted, which _stall_eligible folds into the single
        stall_eligible local so a dead encoder cannot masquerade as a jam.
        Lowercasing before comparison is defensive -- the firmware emits
        lowercase today, but the module must not depend on that.
        """
        mag = str(ch.state.get('mag_status', '')).strip().lower()
        if mag in ('ok', 'unknown', ''):
            ch._mag_fault_streak = 0
            if ch._mag_faulted:
                ch._mag_faulted = False
                self.reactor.register_callback(
                    lambda et, c=ch: self._encoder_fault_cleared_handler(et, c))
            return
        ch._mag_fault_streak += 1
        if not ch._mag_faulted and ch._mag_fault_streak >= _MAG_FAULT_DEBOUNCE_POLLS:
            ch._mag_faulted = True
            self.reactor.register_callback(
                lambda et, c=ch: self._encoder_fault_handler(et, c))

    def _encoder_fault_handler(self, eventtime, ch):
        mag = ch.state.get('mag_status', 'unknown')
        self.gcode.respond_info(
            "BMCU ch%d: encoder fault — magnet status '%s', blockage "
            "detection suspended (this is a sensor fault, not a jam)" %
            (ch.channel_id, mag))
        self.gcode.respond_info(
            "BMCU_EVENT event=encoder_fault channel=%d mag_status=%s" %
            (ch.channel_id, mag))
        logging.warning(
            "BMCU ch%d: encoder fault — magnet status '%s'" %
            (ch.channel_id, mag))
        if ch.pause_on_encoder_fault:
            pause_resume = self.printer.lookup_object('pause_resume')
            pause_resume.send_pause_command()

    def _encoder_fault_cleared_handler(self, eventtime, ch):
        self.gcode.respond_info(
            "BMCU ch%d: encoder fault cleared — blockage detection resumed"
            % ch.channel_id)
        self.gcode.respond_info(
            "BMCU_EVENT event=encoder_fault_cleared channel=%d" % ch.channel_id)

    def _runout_handler(self, eventtime, ch):
        self.gcode.respond_info(
            "BMCU: filament runout on channel %d — pausing print" % ch.channel_id)
        self.gcode.respond_info(
            "BMCU_EVENT event=runout channel=%d" % ch.channel_id)
        if ch.pause_on_runout:
            pause_resume = self.printer.lookup_object('pause_resume')
            pause_resume.send_pause_command()
        self._exec_gcode(ch, ch.runout_gcode)

    def _insert_handler(self, eventtime, ch):
        self._exec_gcode(ch, ch.insert_gcode)

    def _stall_handler(self, eventtime, ch):
        commanded = ch._stall_commanded_mm
        measured = ch._stall_measured_mm
        stalled_s = ch._stall_stalled_s
        self.gcode.respond_info(
            "BMCU: blockage/stall on channel %d — commanded %.2fmm while "
            "the encoder went %.1fs without exceeding the %.2fmm movement "
            "floor (total_stalls=%d)" %
            (ch.channel_id, commanded, stalled_s, ch.min_measured_mm,
             ch._lifetime_stall_count))
        self.gcode.respond_info(
            "BMCU_EVENT event=stall channel=%d commanded_mm=%.2f "
            "measured_mm=%.2f stalled_s=%.1f total_stalls=%d" %
            (ch.channel_id, commanded, measured, stalled_s,
             ch._lifetime_stall_count))
        # Pause BEFORE the gcode template runs — _exec_gcode swallows
        # template exceptions, so the pause must not be downstream of the
        # user's (possibly broken or empty) stall_gcode.
        if ch.pause_on_stall:
            pause_resume = self.printer.lookup_object('pause_resume')
            pause_resume.send_pause_command()
        self._exec_gcode(ch, ch.stall_gcode)

    def _exec_gcode(self, ch, template):
        try:
            self.gcode.run_script("" + template.render() + "\nM400")
        except Exception:
            logging.exception("BMCU: script error on channel %d" % ch.channel_id)
        ch.min_event_systime = self.reactor.monotonic() + ch.event_delay

    def _handle_serial_error(self, msg):
        logging.error("BMCU serial error: %s" % msg)
        self.gcode.respond_info(
            "BMCU: serial error — interrupting print for running channels: %s" % msg)
        self.gcode.respond_info(
            "BMCU_EVENT event=serial_error msg=%s" % msg)
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
                    'feed_mm_since_reset': float(
                        ch.state.get('feed_mm', 0.0) - ch._feed_mm_at_reset),
                    'stall_count': int(ch._lifetime_stall_count),
                    'stall_min_rate_mms': float(
                        ch.min_commanded_mm / ch.stall_timeout_s),
                    'seconds_since_movement': float(
                        eventtime - ch._last_movement_time)
                        if ch._last_movement_time is not None else 0.0,
                    'commanded_since_movement': float(
                        ch._commanded_since_movement),
                    'encoder_fault': bool(ch._mag_faulted),
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
