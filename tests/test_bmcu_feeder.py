"""
Unit tests for klippy/extras/bmcu_feeder.py

Task 1: BmcuSerial (6 tests, KL-01)
Task 2: BmcuChannel, BmcuFeeder config and lifecycle (6 tests, KL-02)
Plan 02-02 Task 1: GCode command handlers (6 tests, KL-03/04/05)
Plan 02-02 Task 2: Polling timer and STATUS parser (4 tests, KL-10/15)
"""

import pytest
from unittest.mock import patch, MagicMock

from klippy.extras.bmcu_feeder import BmcuSerial
from tests.conftest import (MockSerial, MockReactor, MockConfig, MockPrinter, MockGcmd,
                             MockIdleTimeout, MockPauseResume)


# ===========================================================================
# Task 1: BmcuSerial tests
# ===========================================================================

class TestBmcuSerial:

    def _make_serial(self, monkeypatch, mock_serial_instance=None):
        """Helper: create a BmcuSerial with a patched serial.Serial."""
        reactor = MockReactor()
        if mock_serial_instance is None:
            mock_serial_instance = MockSerial('/dev/ttyUSB0', 115200, timeout=0)
        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda port, baud, timeout: MockSerial(port, baud, timeout)
        )
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        return s, reactor, mock_serial_instance

    def test_serial_nonblocking(self, monkeypatch):
        """BmcuSerial.connect() opens serial with timeout=0 and registers fd."""
        reactor = MockReactor()
        created = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()

        assert len(created) == 1, "serial.Serial should have been called once"
        assert created[0].timeout == 0, "Serial must be opened with timeout=0 (non-blocking)"
        assert len(reactor.registered_fds) == 1, "fd must be registered with reactor"
        assert reactor.registered_fds[0].fd == 99, "registered fd must be the serial fileno()"

    def test_serial_send(self, monkeypatch):
        """BmcuSerial.send() writes ASCII-encoded bytes to the serial port."""
        created = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        reactor = MockReactor()
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()
        s.send("RUN 0\n")

        assert created[0]._written == b"RUN 0\n"

    def test_serial_rx_line_assembly(self, monkeypatch):
        """_handle_rx assembles complete newline-delimited lines."""
        created = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        reactor = MockReactor()
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()
        created[0]._read_data = b"STATUS ok ch=0\nSTATUS ok ch=1\n"
        s._handle_rx(0.0)

        lines = s.get_lines()
        assert len(lines) == 2
        assert lines[0] == ('LINE', 'STATUS ok ch=0')
        assert lines[1] == ('LINE', 'STATUS ok ch=1')

    def test_serial_rx_partial(self, monkeypatch):
        """_handle_rx buffers partial lines (no newline) and returns nothing."""
        created = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        reactor = MockReactor()
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()
        created[0]._read_data = b"STATUS ok"
        s._handle_rx(0.0)

        lines = s.get_lines()
        assert lines == [], "Partial line without newline must not be returned"

    def test_serial_error(self, monkeypatch):
        """_handle_rx returns ('ERROR', message) when serial.read raises OSError."""
        created = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        reactor = MockReactor()
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()
        created[0]._raise_on_read = OSError("device disconnected")
        s._handle_rx(0.0)

        lines = s.get_lines()
        assert len(lines) == 1
        kind, msg = lines[0]
        assert kind == 'ERROR'
        assert 'device disconnected' in msg

    def test_serial_disconnect(self, monkeypatch):
        """disconnect() unregisters the fd handle and closes the serial port."""
        created = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        reactor = MockReactor()
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()

        assert len(reactor.registered_fds) == 1
        s.disconnect()

        assert len(reactor.registered_fds) == 0, "fd handle must be unregistered"
        assert not created[0].is_open, "serial port must be closed"


# ===========================================================================
# Task 2: BmcuChannel and BmcuFeeder tests
# ===========================================================================

class TestBmcuChannel:

    def _make_channel_config(self, extra=None, name="bmcu_channel 0"):
        params = {
            'extruder': 'extruder',
        }
        if extra:
            params.update(extra)
        cfg = MockConfig(params, name=name)
        return cfg

    def test_channel_config(self):
        """BmcuChannel reads all config keys with correct defaults."""
        from klippy.extras.bmcu_feeder import BmcuChannel
        cfg = self._make_channel_config()
        ch = BmcuChannel(cfg)

        assert ch.extruder == 'extruder'
        assert ch.event_delay == pytest.approx(3.0)
        assert ch.pause_on_runout is True
        assert ch.stall_threshold_mm == pytest.approx(0.5)
        assert ch.sensor_enabled is True

    def test_channel_gcode_templates(self):
        """BmcuChannel loads runout/insert/stall gcode templates via gcode_macro."""
        from klippy.extras.bmcu_feeder import BmcuChannel
        cfg = self._make_channel_config({
            'runout_gcode': 'PAUSE',
            'insert_gcode': 'RESUME',
            'stall_gcode': 'M600',
        })
        ch = BmcuChannel(cfg)

        assert ch.runout_gcode.render() == 'PAUSE'
        assert ch.insert_gcode.render() == 'RESUME'
        assert ch.stall_gcode.render() == 'M600'


class TestBmcuFeeder:

    def _make_feeder_config(self, extra=None, name="bmcu_feeder"):
        params = {
            'serial': '/dev/ttyUSB0',
        }
        if extra:
            params.update(extra)
        cfg = MockConfig(params, name=name)
        return cfg

    def test_feeder_config(self):
        """BmcuFeeder reads serial, baud, poll_interval from config."""
        from klippy.extras.bmcu_feeder import BmcuFeeder
        cfg = self._make_feeder_config()
        feeder = BmcuFeeder(cfg)

        assert feeder.serial_port == '/dev/ttyUSB0'
        assert feeder.baud == 115200
        assert feeder.poll_interval == pytest.approx(0.5)

    def test_feeder_channels(self, monkeypatch):
        """BmcuFeeder discovers BmcuChannel objects in _handle_connect."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = self._make_feeder_config()
        feeder = BmcuFeeder(cfg)

        # Register two channels in the printer object registry
        ch0_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel 0')
        ch0_cfg.printer = cfg.printer
        ch1_cfg = MockConfig({'extruder': 'extruder1'}, name='bmcu_channel 1')
        ch1_cfg.printer = cfg.printer

        ch0 = BmcuChannel(ch0_cfg)
        ch1 = BmcuChannel(ch1_cfg)
        cfg.printer.add_object('bmcu_channel 0', ch0)
        cfg.printer.add_object('bmcu_channel 1', ch1)

        # Monkeypatch serial so _handle_connect doesn't fail opening the port
        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda port, baud, timeout: MockSerial(port, baud, timeout)
        )

        feeder._handle_connect()
        assert 0 in feeder._channels
        assert 1 in feeder._channels

    def test_feeder_lifecycle_connect(self, monkeypatch):
        """_handle_connect creates a BmcuSerial and calls connect()."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = self._make_feeder_config()
        feeder = BmcuFeeder(cfg)

        ch0_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel 0')
        ch0_cfg.printer = cfg.printer
        cfg.printer.add_object('bmcu_channel 0', BmcuChannel(ch0_cfg))

        serial_instances = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()

        assert feeder._serial is not None, "_serial must be set after connect"
        assert len(serial_instances) == 1, "serial.Serial should be called once"
        assert len(cfg.printer.get_reactor().registered_fds) == 1, "fd must be registered"

    def test_feeder_lifecycle_disconnect(self, monkeypatch):
        """_handle_disconnect calls serial.disconnect() and removes poll timer."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = self._make_feeder_config()
        feeder = BmcuFeeder(cfg)

        ch0_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel 0')
        ch0_cfg.printer = cfg.printer
        cfg.printer.add_object('bmcu_channel 0', BmcuChannel(ch0_cfg))

        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda port, baud, timeout: MockSerial(port, baud, timeout)
        )

        feeder._handle_connect()
        feeder._handle_ready()

        reactor = cfg.printer.get_reactor()
        assert len(reactor._timers) == 1, "poll timer must be registered after _handle_ready"

        feeder._handle_disconnect()

        assert feeder._serial is None, "_serial must be None after disconnect"
        assert len(reactor._timers) == 0, "poll timer must be unregistered"
        assert len(reactor.registered_fds) == 0, "fd must be unregistered after disconnect"


# ===========================================================================
# Plan 02-02 Task 1: GCode command handlers (KL-03, KL-04, KL-05)
# ===========================================================================

class TestBmcuGcodeCommands:
    """Tests for BMCU_RUN, BMCU_STOP, BMCU_SPEED, BMCU_DIR, BMCU_STATUS,
    SET_BMCU_SENSOR command handlers."""

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,)):
        """Helper: build a connected BmcuFeeder with the given channel IDs."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': '/dev/ttyUSB0'}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()
        return feeder, serial_instances

    def test_cmd_run(self, monkeypatch):
        """BMCU_RUN CHANNEL=0 sends 'RUN 0\\n'; CHANNEL=2 sends 'RUN 2\\n'."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0, 2))
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 0})
        feeder._cmd_run(gcmd)
        assert ms._written == b"RUN 0\n", "BMCU_RUN CHANNEL=0 must write 'RUN 0\\n'"

        ms._written = b""
        gcmd2 = MockGcmd({'CHANNEL': 2})
        feeder._cmd_run(gcmd2)
        assert ms._written == b"RUN 2\n", "BMCU_RUN CHANNEL=2 must write 'RUN 2\\n'"

    def test_cmd_stop(self, monkeypatch):
        """BMCU_STOP CHANNEL=1 sends 'STOP 1\\n'."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(1,))
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 1})
        feeder._cmd_stop(gcmd)
        assert ms._written == b"STOP 1\n", "BMCU_STOP CHANNEL=1 must write 'STOP 1\\n'"

    def test_cmd_speed(self, monkeypatch):
        """BMCU_SPEED CHANNEL=0 SPEED=75 sends 'SPEED 0 75\\n'."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 0, 'SPEED': 75})
        feeder._cmd_speed(gcmd)
        assert ms._written == b"SPEED 0 75\n", "BMCU_SPEED CHANNEL=0 SPEED=75 must write 'SPEED 0 75\\n'"

    def test_cmd_dir(self, monkeypatch):
        """BMCU_DIR CHANNEL=0 DIR=REV sends 'DIR 0 REV\\n'."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 0, 'DIR': 'REV'})
        feeder._cmd_dir(gcmd)
        assert ms._written == b"DIR 0 REV\n", "BMCU_DIR CHANNEL=0 DIR=REV must write 'DIR 0 REV\\n'"

    def test_cmd_status(self, monkeypatch):
        """BMCU_STATUS responds with header, column headers, separator, and data rows."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        # Pre-populate channel state with known values
        feeder._channels[0].state.update({
            'filament_present': True,
            'motor_running': True,
            'speed': 75,
            'direction': 'FWD',
            'feed_mm': 142.5,
            'mag_status': 'ok',
        })

        gcmd = MockGcmd({})
        feeder._cmd_status(gcmd)

        assert len(gcmd._responses) == 1
        output = gcmd._responses[0]
        assert "BMCU Status:" in output, "Status output must contain 'BMCU Status:' header"
        assert "CH" in output and "Filament" in output and "Motor" in output, \
            "Status output must contain column headers"
        assert "-" * 55 in output, "Status output must contain 55-hyphen separator"
        # Data row checks
        assert "present" in output
        assert "running" in output
        assert "142.5" in output

    def test_set_sensor(self, monkeypatch):
        """SET_BMCU_SENSOR CHANNEL=0 ENABLE=0 sets sensor_enabled=False; ENABLE=1 restores True."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        ch = feeder._channels[0]
        assert ch.sensor_enabled is True

        gcmd_off = MockGcmd({'ENABLE': 0})
        ch.cmd_set_sensor(gcmd_off)
        assert ch.sensor_enabled is False, "ENABLE=0 must set sensor_enabled=False"

        gcmd_on = MockGcmd({'ENABLE': 1})
        ch.cmd_set_sensor(gcmd_on)
        assert ch.sensor_enabled is True, "ENABLE=1 must set sensor_enabled=True"


# ===========================================================================
# Plan 02-02 Task 2: Polling timer and STATUS response parser (KL-10, KL-15)
# ===========================================================================

class TestBmcuPolling:
    """Tests for _poll_status and _dispatch_status_line."""

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,)):
        """Helper: build a connected BmcuFeeder with the given channel IDs."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': '/dev/ttyUSB0'}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls(port, baud, timeout):
            ms = MockSerial(port, baud, timeout)
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()
        return feeder, serial_instances

    def test_poll_sends_status(self, monkeypatch):
        """_poll_status writes 'STATUS\\n' and returns eventtime + poll_interval."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch)
        ms = serials[0]

        # No queued lines
        ms._read_data = b""

        result = feeder._poll_status(10.0)
        assert b"STATUS\n" in ms._written, "_poll_status must send 'STATUS\\n'"
        assert result == pytest.approx(10.0 + feeder.poll_interval), \
            "_poll_status must return eventtime + poll_interval"

    def test_poll_dispatches_lines(self, monkeypatch):
        """When serial has a STATUS line for ch=0, _poll_status updates channel 0 state."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))

        # Directly inject a line into the serial's line buffer (bypass fd reading)
        feeder._serial._lines = [
            ('LINE', 'STATUS ok ch=0 fil=1 mot=1 spd=50 dir=FWD mm=142.5 mag=ok')
        ]

        feeder._poll_status(0.0)

        s = feeder._channels[0].state
        assert s['filament_present'] is True
        assert s['motor_running'] is True
        assert s['speed'] == 50
        assert s['direction'] == 'FWD'
        assert s['feed_mm'] == pytest.approx(142.5)
        assert s['mag_status'] == 'ok'

    def test_poll_multi_channel(self, monkeypatch):
        """Multi-channel STATUS line updates both channel 0 and channel 1."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0, 1))

        feeder._serial._lines = [
            ('LINE',
             'STATUS ok ch=0 fil=1 mot=0 spd=0 dir=FWD mm=0.0 mag=ok '
             'ch=1 fil=0 mot=1 spd=75 dir=REV mm=50.3 mag=ok')
        ]

        feeder._poll_status(0.0)

        s0 = feeder._channels[0].state
        assert s0['filament_present'] is True
        assert s0['motor_running'] is False
        assert s0['speed'] == 0
        assert s0['direction'] == 'FWD'

        s1 = feeder._channels[1].state
        assert s1['filament_present'] is False
        assert s1['motor_running'] is True
        assert s1['speed'] == 75
        assert s1['direction'] == 'REV'
        assert s1['feed_mm'] == pytest.approx(50.3)

    def test_poll_ignores_unconfigured(self, monkeypatch):
        """STATUS data for channel 3 is ignored when only channels 0 and 1 are configured."""
        feeder, serials = self._make_feeder_with_channels(monkeypatch, ch_ids=(0, 1))

        feeder._serial._lines = [
            ('LINE',
             'STATUS ok ch=0 fil=1 mot=0 spd=0 dir=FWD mm=0.0 mag=ok '
             'ch=3 fil=1 mot=1 spd=50 dir=FWD mm=10.0 mag=fault')
        ]

        feeder._poll_status(0.0)

        # Channel 3 must not exist in _channels
        assert 3 not in feeder._channels, "Unconfigured channel 3 must not be added"
        # Channel 0 should be updated
        assert feeder._channels[0].state['filament_present'] is True


# ===========================================================================
# Plan 02-03 Task 1: Event dispatch — runout, insert, event_delay, pause_on_runout
# ===========================================================================

class TestBmcuEventDispatch:
    """Tests for KL-06, KL-07, KL-08, KL-09, KL-13, KL-14 event dispatch."""

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,),
                                   runout_gcode='PAUSE', insert_gcode='RESUME',
                                   stall_gcode='M600',
                                   pause_on_runout=True):
        """Helper: build a connected BmcuFeeder with event-enabled channels."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': '/dev/ttyUSB0'}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_params = {
                'extruder': 'extruder',
                'runout_gcode': runout_gcode,
                'insert_gcode': insert_gcode,
                'stall_gcode': stall_gcode,
                'pause_on_runout': pause_on_runout,
            }
            ch_cfg = MockConfig(ch_params, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        # Register idle_timeout and pause_resume in the shared printer
        cfg.printer._objects['idle_timeout'] = MockIdleTimeout(state='Printing')
        cfg.printer._objects['pause_resume'] = MockPauseResume()

        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda port, baud, timeout: MockSerial(port, baud, timeout)
        )
        feeder._handle_connect()
        return feeder

    def test_runout_event(self, monkeypatch):
        """When filament transitions present->absent during printing, runout_gcode fires."""
        feeder = self._make_feeder_with_channels(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        gcode = feeder.gcode

        # Set up: filament was present
        old_state = dict(ch.state)
        old_state['filament_present'] = True
        ch.state['filament_present'] = False

        feeder._check_events(ch, old_state)

        # A callback must have been registered
        assert len(reactor.callbacks) == 1, "runout callback must be registered"
        # Execute the callback
        reactor.callbacks[0](0.0)
        assert len(gcode._scripts_run) == 1, "runout_gcode must be run"
        assert 'PAUSE' in gcode._scripts_run[0]

    def test_insert_event(self, monkeypatch):
        """When filament transitions absent->present, insert_gcode fires regardless of print state."""
        feeder = self._make_feeder_with_channels(monkeypatch)
        # Change idle_timeout to Ready (not printing) — insert should still fire
        feeder.printer.lookup_object('idle_timeout')._state = 'Ready'
        reactor = feeder.reactor
        ch = feeder._channels[0]
        gcode = feeder.gcode

        old_state = dict(ch.state)
        old_state['filament_present'] = False
        ch.state['filament_present'] = True

        feeder._check_events(ch, old_state)

        assert len(reactor.callbacks) == 1, "insert callback must be registered"
        reactor.callbacks[0](0.0)
        assert len(gcode._scripts_run) == 1, "insert_gcode must be run"
        assert 'RESUME' in gcode._scripts_run[0]

    def test_event_delay(self, monkeypatch):
        """After a runout event fires, a second state change within event_delay is suppressed."""
        feeder = self._make_feeder_with_channels(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # First runout
        old_state = dict(ch.state)
        old_state['filament_present'] = True
        ch.state['filament_present'] = False
        feeder._check_events(ch, old_state)
        assert len(reactor.callbacks) == 1, "first event must register callback"

        # Execute callback to set min_event_systime
        reactor.callbacks[0](0.0)
        reactor.callbacks.clear()

        # Immediately attempt insert while still within event_delay window
        # monotonic() returns 0.0 and event_delay defaults to 3.0 so min_event_systime > 0
        old_state2 = dict(ch.state)
        old_state2['filament_present'] = False
        ch.state['filament_present'] = True
        feeder._check_events(ch, old_state2)

        assert len(reactor.callbacks) == 0, "second event within event_delay must be suppressed"

    def test_pause_on_runout(self, monkeypatch):
        """When pause_on_runout=True, send_pause_command() is called before runout_gcode."""
        feeder = self._make_feeder_with_channels(monkeypatch, pause_on_runout=True)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        pause_resume = feeder.printer.lookup_object('pause_resume')

        old_state = dict(ch.state)
        old_state['filament_present'] = True
        ch.state['filament_present'] = False
        feeder._check_events(ch, old_state)

        assert len(reactor.callbacks) == 1
        reactor.callbacks[0](0.0)
        assert pause_resume.pause_called is True, "pause_resume.send_pause_command() must be called"

    def test_sensor_disabled_no_events(self, monkeypatch):
        """When sensor_enabled=False, filament state changes do NOT trigger any events."""
        feeder = self._make_feeder_with_channels(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        ch.sensor_enabled = False

        old_state = dict(ch.state)
        old_state['filament_present'] = True
        ch.state['filament_present'] = False
        feeder._check_events(ch, old_state)

        assert len(reactor.callbacks) == 0, "disabled sensor must not fire events"

    def test_runout_only_when_printing(self, monkeypatch):
        """When filament is removed but idle_timeout state is 'Ready', runout does NOT fire."""
        feeder = self._make_feeder_with_channels(monkeypatch)
        # Override to Ready (not printing)
        feeder.printer.lookup_object('idle_timeout')._state = 'Ready'
        reactor = feeder.reactor
        ch = feeder._channels[0]

        old_state = dict(ch.state)
        old_state['filament_present'] = True
        ch.state['filament_present'] = False
        feeder._check_events(ch, old_state)

        assert len(reactor.callbacks) == 0, "runout must not fire when not printing"
