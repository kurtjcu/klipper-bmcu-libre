"""
bmcu_feeder.py — Klipper extra for BMCU 370C multi-channel feeder control.

Exposes per-channel filament runout/blockage detection and feeder motor
control over USB serial. Drop this file into ~/klipper/klippy/extras/ and
restart Klipper.

Phase 2 plan 01: BmcuSerial, BmcuChannel, BmcuFeeder foundation.
"""

import serial
import logging
import re

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

    def _poll_status(self, eventtime):
        """Reactor timer callback — send STATUS query and reschedule."""
        if self._serial is not None:
            self._serial.send("STATUS\n")
        return eventtime + self.poll_interval

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
