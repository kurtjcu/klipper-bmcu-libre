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
                             MockIdleTimeout, MockPauseResume, MockMcu, MockExtruder)


# ===========================================================================
# Task 1: BmcuSerial tests
# ===========================================================================

class TestBmcuSerial:

    def _make_serial(self, monkeypatch, mock_serial_instance=None):
        """Helper: create a BmcuSerial with a patched serial.Serial."""
        reactor = MockReactor()
        if mock_serial_instance is None:
            mock_serial_instance = MockSerial()
        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda: MockSerial()
        )
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        return s, reactor, mock_serial_instance

    def test_serial_nonblocking(self, monkeypatch):
        """BmcuSerial.connect() opens serial with timeout=0 and registers fd."""
        reactor = MockReactor()
        created = []

        def mock_serial_cls():
            ms = MockSerial()
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

        def mock_serial_cls():
            ms = MockSerial()
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        reactor = MockReactor()
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()
        created[0]._written = b""  # clear ENABLE handshake bytes written during connect()
        s.send("RUN 0\n")

        assert created[0]._written == b"RUN 0\n"

    def test_serial_rx_line_assembly(self, monkeypatch):
        """_handle_rx assembles complete newline-delimited lines."""
        created = []

        def mock_serial_cls():
            ms = MockSerial()
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

        def mock_serial_cls():
            ms = MockSerial()
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

        def mock_serial_cls():
            ms = MockSerial()
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

        def mock_serial_cls():
            ms = MockSerial()
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

    # -----------------------------------------------------------------------
    # Phase 10 Plan 01 Task 2: BOOT-driven handshake tests
    # -----------------------------------------------------------------------

    def test_boot_wait_success(self, monkeypatch):
        """connect() sees BOOT message, then ENABLE ok — timeout=0 and fd registered."""
        reactor = MockReactor()
        created = []

        def mock_serial_cls():
            ms = MockSerial()
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        # Queue: BOOT message first, then ENABLE ok response
        # Must set queue before connect() is called (MockSerial created inside connect)
        # Use a flag to set queue after creation
        original_cls = mock_serial_cls

        created2 = []

        def mock_serial_cls2():
            ms = MockSerial()
            ms._readline_queue = [
                b"BOOT mag0=OK mag1=OK mag2=OK mag3=OK\n",
                b"ENABLE ok fil=1234 mag=OK/OK/OK/OK\n",
            ]
            created2.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls2)
        reactor2 = MockReactor()
        s2 = BmcuSerial('/dev/ttyUSB0', 115200, reactor2)
        s2.connect()

        assert created2[0].timeout == 0, "Serial must be non-blocking (timeout=0) after connect"
        assert len(reactor2.registered_fds) == 1, "fd must be registered with reactor"

    def test_boot_wait_timeout_fallback(self, monkeypatch):
        """connect() gets no BOOT within deadline, falls back to ENABLE — succeeds."""
        reactor = MockReactor()
        created = []

        def mock_serial_cls():
            ms = MockSerial()
            # Queue: empty bytes simulates readline timeout (no BOOT),
            # then ENABLE ok for the ENABLE attempt
            ms._readline_queue = [b"", b"ENABLE ok\n"]
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        # Should not raise even without BOOT message
        s.connect()
        assert created[0].timeout == 0, "Serial must be non-blocking after connect"

    def test_enable_retry_loop(self, monkeypatch):
        """connect() retries ENABLE after failure; second attempt succeeds."""
        reactor = MockReactor()
        created = []

        def mock_serial_cls():
            ms = MockSerial()
            # BOOT seen, first ENABLE fails, second succeeds
            ms._readline_queue = [b"BOOT mag0=OK\n", b"ERROR\n", b"ENABLE ok\n"]
            created.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        sleep_calls = []
        monkeypatch.setattr('klippy.extras.bmcu_feeder._time.sleep',
                            lambda t: sleep_calls.append(t))
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        s.connect()

        assert len(reactor.registered_fds) == 1, "fd must be registered after retry success"
        assert len(sleep_calls) == 1, "_time.sleep must be called once between retries"
        assert sleep_calls[0] == pytest.approx(2.0), "retry delay must be 2.0 seconds"

    def test_enable_all_retries_fail(self, monkeypatch):
        """connect() raises Exception after 3 failed ENABLE attempts."""
        reactor = MockReactor()

        def mock_serial_cls():
            ms = MockSerial()
            # BOOT seen, then 3 ERROR responses
            ms._readline_queue = [b"BOOT mag0=OK\n", b"ERROR\n", b"ERROR\n", b"ERROR\n"]
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        monkeypatch.setattr('klippy.extras.bmcu_feeder._time.sleep', lambda t: None)
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        with pytest.raises(Exception, match="ENABLE handshake failed"):
            s.connect()

    def test_enable_ok_already_accepted(self, monkeypatch):
        """connect() accepts 'ENABLE ok already' as a successful ENABLE response."""
        reactor = MockReactor()

        def mock_serial_cls():
            ms = MockSerial()
            ms._readline_queue = [b"BOOT mag0=OK\n", b"ENABLE ok already\n"]
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        s = BmcuSerial('/dev/ttyUSB0', 115200, reactor)
        # Should not raise — "ENABLE ok already" starts with "ENABLE ok"
        s.connect()
        assert len(reactor.registered_fds) == 1

    def test_cmd_enable_no_sleep(self, monkeypatch):
        """_cmd_enable() sends ENABLE, reads response, echoes it — no sleep."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel 0')
        ch_cfg.printer = cfg.printer
        cfg.printer.add_object('bmcu_channel 0', BmcuChannel(ch_cfg))

        def mock_serial_cls():
            return MockSerial()

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()

        sleep_calls = []
        monkeypatch.setattr('klippy.extras.bmcu_feeder._time.sleep',
                            lambda t: sleep_calls.append(t))

        gcmd = MockGcmd({})
        feeder._cmd_enable(gcmd)

        assert len(sleep_calls) == 0, "_cmd_enable must not call _time.sleep"
        assert len(gcmd._responses) == 1, "_cmd_enable must call gcmd.respond_info once"
        assert "ENABLE" in gcmd._responses[0], "response must contain ENABLE"



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
        assert ch.min_commanded_mm == pytest.approx(5.0)
        assert ch.stall_timeout_s == pytest.approx(15.0)
        assert ch.min_measured_mm == pytest.approx(1.0)
        assert ch.sensor_enabled is True
        assert ch._deprecated_present == []

    def test_deprecated_options_still_parse(self):
        """A channel constructed with slip_ratio, stall_window_polls and
        stall_startup_ignore_polls all present succeeds, records all three
        in _deprecated_present, and exposes none of them as attributes --
        proving they are ignored rather than quietly consulted. The live
        printer sets all three and has no remote access to edit them."""
        from klippy.extras.bmcu_feeder import BmcuChannel
        cfg = self._make_channel_config({
            'slip_ratio': 0.5,
            'stall_window_polls': 3,
            'stall_startup_ignore_polls': 2,
        })
        ch = BmcuChannel(cfg)

        assert sorted(ch._deprecated_present) == sorted(
            ['slip_ratio', 'stall_window_polls', 'stall_startup_ignore_polls'])
        assert not hasattr(ch, 'slip_ratio')
        assert not hasattr(ch, 'stall_window_polls')
        assert not hasattr(ch, 'stall_startup_ignore_polls')

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

    _VALID_SERIAL = '/dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0'

    def _make_feeder_config(self, extra=None, name="bmcu_feeder"):
        params = {
            'serial': self._VALID_SERIAL,
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

        assert feeder.serial_port == self._VALID_SERIAL
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
            lambda: MockSerial()
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

        def mock_serial_cls():
            ms = MockSerial()
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
            lambda: MockSerial()
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

_VALID_SERIAL = '/dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0'


class TestBmcuGcodeCommands:
    """Tests for BMCU_RUN, BMCU_STOP, BMCU_SPEED, BMCU_DIR, BMCU_STATUS,
    SET_BMCU_SENSOR command handlers."""

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,)):
        """Helper: build a connected BmcuFeeder with the given channel IDs."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls():
            ms = MockSerial()
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()
        # Clear ENABLE handshake bytes so tests can assert on post-connect writes only
        for ms in serial_instances:
            ms._written = b""
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
# Phase 07 Plan 01 Task 1: direction_invert config option (DIR-INV-01..05)
# ===========================================================================

class TestDirectionInvert:
    """Tests for direction_invert config option on BmcuChannel."""

    def _make_feeder_with_invert(self, monkeypatch, ch_ids=(0,),
                                  invert_map=None):
        """Helper: build a connected BmcuFeeder where channels may have
        direction_invert set.  invert_map is {ch_id: True/False}."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        if invert_map is None:
            invert_map = {}

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            params = {'extruder': 'extruder'}
            if ch_id in invert_map:
                params['direction_invert'] = invert_map[ch_id]
            ch_cfg = MockConfig(params, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id,
                                   BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls():
            ms = MockSerial()
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial',
                            mock_serial_cls)
        feeder._handle_connect()
        # _handle_ready resolves ch._extruder_obj / ch._stall_enabled and
        # sets _estimated_print_time, matching real Klipper startup order
        # (the poll timer that drives _check_events is only ever registered
        # after _handle_ready). No 'extruder' object is registered here, so
        # this cleanly disables stall detection for these channels via the
        # existing extruder-lookup-failure path rather than leaving
        # _stall_enabled/_extruder_obj in the inconsistent __init__-only
        # state these direction-only tests don't exercise.
        feeder._handle_ready()
        feeder.reactor.unregister_timer(feeder._poll_timer_handle)
        for ms in serial_instances:
            ms._written = b""
        return feeder, serial_instances

    def test_fwd_inverted_sends_rev(self, monkeypatch):
        """BMCU_DIR CHANNEL=0 DIR=FWD with direction_invert=True sends 'DIR 0 REV\\n'."""
        feeder, serials = self._make_feeder_with_invert(
            monkeypatch, ch_ids=(0,), invert_map={0: True})
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 0, 'DIR': 'FWD'})
        feeder._cmd_dir(gcmd)
        assert ms._written == b"DIR 0 REV\n", (
            "direction_invert=True: FWD must be sent as REV on wire")

    def test_fwd_not_inverted_sends_fwd(self, monkeypatch):
        """BMCU_DIR CHANNEL=0 DIR=FWD with direction_invert=False (default) sends 'DIR 0 FWD\\n'."""
        feeder, serials = self._make_feeder_with_invert(
            monkeypatch, ch_ids=(0,), invert_map={0: False})
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 0, 'DIR': 'FWD'})
        feeder._cmd_dir(gcmd)
        assert ms._written == b"DIR 0 FWD\n", (
            "direction_invert=False: FWD must be sent as FWD on wire")

    def test_rev_inverted_sends_fwd(self, monkeypatch):
        """BMCU_DIR CHANNEL=0 DIR=REV with direction_invert=True sends 'DIR 0 FWD\\n'."""
        feeder, serials = self._make_feeder_with_invert(
            monkeypatch, ch_ids=(0,), invert_map={0: True})
        ms = serials[0]

        gcmd = MockGcmd({'CHANNEL': 0, 'DIR': 'REV'})
        feeder._cmd_dir(gcmd)
        assert ms._written == b"DIR 0 FWD\n", (
            "direction_invert=True: REV must be sent as FWD on wire")

    def test_status_dir_stored_raw(self, monkeypatch):
        """STATUS dir=REV on channel with direction_invert=True stores 'REV' raw (no inversion)."""
        feeder, serials = self._make_feeder_with_invert(
            monkeypatch, ch_ids=(0,), invert_map={0: True})

        # Inject a STATUS line with dir=REV directly
        feeder._serial._lines = [
            ('LINE',
             'STATUS ok ch=0 ins=1 fil=1 mot=1 spd=50 dir=REV mm=0.0 mag=ok')
        ]
        feeder._poll_status(0.0)

        assert feeder._channels[0].state['direction'] == 'REV', (
            "STATUS dir= must be stored raw — direction_invert must not affect "
            "the value written to ch.state['direction']")

    def test_channel_direction_invert_config(self, monkeypatch):
        """BmcuChannel parses direction_invert from config correctly."""
        from klippy.extras.bmcu_feeder import BmcuChannel

        cfg_true = MockConfig(
            {'extruder': 'extruder', 'direction_invert': True},
            name='bmcu_channel 0')
        ch_true = BmcuChannel(cfg_true)
        assert ch_true.direction_invert is True, (
            "direction_invert: True must set ch.direction_invert = True")

        cfg_default = MockConfig({'extruder': 'extruder'},
                                  name='bmcu_channel 1')
        ch_default = BmcuChannel(cfg_default)
        assert ch_default.direction_invert is False, (
            "Omitting direction_invert must default ch.direction_invert to False")


# ===========================================================================
# Plan 02-02 Task 2: Polling timer and STATUS response parser (KL-10, KL-15)
# ===========================================================================

class TestBmcuPolling:
    """Tests for _poll_status and _dispatch_status_line."""

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,)):
        """Helper: build a connected BmcuFeeder with the given channel IDs."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls():
            ms = MockSerial()
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()
        # _handle_ready resolves ch._extruder_obj / ch._stall_enabled and
        # sets _estimated_print_time, matching real Klipper startup order
        # (the poll timer that drives _check_events is only ever registered
        # after _handle_ready). No 'extruder' object is registered here, so
        # this cleanly disables stall detection for these channels via the
        # existing extruder-lookup-failure path rather than leaving
        # _stall_enabled/_extruder_obj in the inconsistent __init__-only
        # state these polling-dispatch tests don't exercise.
        feeder._handle_ready()
        feeder.reactor.unregister_timer(feeder._poll_timer_handle)
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
            ('LINE', 'STATUS ok ch=0 ins=1 fil=1 mot=1 spd=50 dir=FWD mm=142.5 mag=ok')
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
             'STATUS ok ch=0 ins=1 fil=1 mot=0 spd=0 dir=FWD mm=0.0 mag=ok '
             'ch=1 ins=1 fil=0 mot=1 spd=75 dir=REV mm=50.3 mag=ok')
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
             'STATUS ok ch=0 ins=1 fil=1 mot=0 spd=0 dir=FWD mm=0.0 mag=ok '
             'ch=3 ins=1 fil=1 mot=1 spd=50 dir=FWD mm=10.0 mag=fault')
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

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
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
            lambda: MockSerial()
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


# ===========================================================================
# Plan 02-03 Task 2: Blockage/stall detection (KL-13, KL-14)
# ===========================================================================

class TestBmcuStallDetection:
    """Tests for the activity (liveness) stall detector: a stall fires when,
    over the trailing stall_timeout_s, forward commanded extrusion reaches
    min_commanded_mm while total encoder movement stays under
    min_measured_mm. No ratio, no correlation, no window list, no
    partial-slip detection."""

    def _make_feeder_with_channel(self, monkeypatch, min_commanded_mm=1.0,
                                   slip_ratio=0.5,
                                   stall_window_polls=3,
                                   stall_startup_ignore_polls=0,
                                   stall_timeout_s=1.0,
                                   min_measured_mm=1.0,
                                   use_module_defaults=False,
                                   with_extruder=True,
                                   require_motor_running=None,
                                   pause_on_stall=None):
        """Helper: build a connected, ready BmcuFeeder with one stall-configured
        channel. When with_extruder is True, a MockExtruder is registered as
        'extruder' and channel 0 is configured to use it; _handle_ready is
        called so _estimated_print_time and ch._extruder_obj are populated.
        When False, the channel has no extruder configured at all (extruder-less
        path), so stall detection is disabled after _handle_ready.

        require_motor_running and pause_on_stall default to None and are
        only injected into ch_params when not None, so the module defaults
        (both True) stay exercisable by simply not passing them.

        The harness default stall_timeout_s=1.0 (module default 15.0) keeps
        the fast-crossing tests fast; combined with poll_interval 0.5 and
        _poll's clock advance, a 1-baseline + 2-poll sequence genuinely
        crosses the timeout.

        use_module_defaults=True injects NONE of the six stall knobs, so
        the module's own shipped defaults (min_commanded_mm=5.0,
        stall_timeout_s=15.0, min_measured_mm=1.0) apply -- used by tests
        that must exercise the real shipped configuration.
        """
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        ch_params = {
            'runout_gcode': 'PAUSE',
            'insert_gcode': 'RESUME',
            'stall_gcode': 'M600',
        }
        if not use_module_defaults:
            ch_params.update({
                'min_commanded_mm': min_commanded_mm,
                'slip_ratio': slip_ratio,
                'stall_window_polls': stall_window_polls,
                'stall_startup_ignore_polls': stall_startup_ignore_polls,
                'stall_timeout_s': stall_timeout_s,
                'min_measured_mm': min_measured_mm,
            })
        if require_motor_running is not None:
            ch_params['require_motor_running'] = require_motor_running
        if pause_on_stall is not None:
            ch_params['pause_on_stall'] = pause_on_stall
        if with_extruder:
            ch_params['extruder'] = 'extruder'
        ch_cfg = MockConfig(ch_params, name='bmcu_channel 0')
        ch_cfg.printer = cfg.printer
        cfg.printer.add_object('bmcu_channel 0', BmcuChannel(ch_cfg))
        cfg.printer._objects['idle_timeout'] = MockIdleTimeout(state='Printing')
        cfg.printer._objects['pause_resume'] = MockPauseResume()
        if with_extruder:
            cfg.printer._objects['extruder'] = MockExtruder()

        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda: MockSerial()
        )
        feeder._handle_connect()
        feeder._handle_ready()
        # Timer callback itself isn't exercised by these tests; unregister
        # so no dangling timer handle lingers across tests.
        feeder.reactor.unregister_timer(feeder._poll_timer_handle)
        # Prime filament_present=True directly (bypassing _check_events) so
        # the first _poll() call below does not trigger an insert event —
        # an insert event sets min_event_systime=NEVER, which would suppress
        # all subsequent stall evaluation in the test.
        ch = feeder._channels[0]
        ch.state['filament_present'] = True
        return feeder

    def _poll(self, feeder, ch, commanded_pos, measured_mm,
              filament_present=True, motor_running=True, direction='FWD',
              at=None):
        """Drive one poll: set the extruder's commanded position and the
        channel's measured feed_mm, then call _check_events with the
        previous state snapshotted beforehand.

        When at is given, the reactor clock is set to that absolute value;
        otherwise it advances by feeder.poll_interval, so a sequence of
        _poll() calls approximates real elapsed time between polls.
        """
        if at is not None:
            feeder.reactor._monotonic_time = at
        else:
            feeder.reactor._monotonic_time += feeder.poll_interval
        old_state = dict(ch.state)
        extruder = ch._extruder_obj
        if extruder is not None:
            extruder.next_position = commanded_pos
        ch.state.update({
            'filament_present': filament_present,
            'motor_running': motor_running,
            'feed_mm': measured_mm,
            'direction': direction,
        })
        feeder._check_events(ch, old_state)

    def test_partial_slip_never_fires(self, monkeypatch):
        """Commanded advances steadily; measured advances slightly less but
        still well above min_measured_mm every poll -- partial slip is not
        a detected condition, however long the run."""
        feeder = self._make_feeder_with_channel(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll — establishes the activity tracker.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0)
        reactor.callbacks.clear()

        # Steady partial slip: commanded advances 5mm/poll, measured
        # advances 4mm/poll (well above min_measured_mm=1.0), so the
        # tracker rebaselines every poll and never accumulates toward the
        # timeout.
        commanded, measured = 0.0, 0.0
        for _ in range(20):
            commanded += 5.0
            measured += 4.0
            self._poll(feeder, ch, commanded_pos=commanded, measured_mm=measured)

        assert len(reactor.callbacks) == 0, \
            "partial slip must never trip a stall, however long it runs"

    def test_slack_takeup_then_movement_no_stall(self, monkeypatch):
        """(260821-akv incident shape) feed_mm stays flat for the opening
        slack take-up, then the encoder starts moving every poll while
        commanded extrusion keeps advancing — at the shipped defaults this
        must never fire, run well past stall_timeout_s."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, use_module_defaults=True)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0)
        reactor.callbacks.clear()

        commanded = 0.0
        # Slack take-up: ~2s of flat measured while commanded keeps
        # advancing at the incident's rate (2.2mm per 0.5s poll, 4.4mm/s).
        for _ in range(4):
            commanded += 2.2
            self._poll(feeder, ch, commanded_pos=commanded, measured_mm=0.0)
        assert len(reactor.callbacks) == 0, \
            "slack take-up alone must not trip a stall"

        # Slack taken up: the encoder starts moving every poll, well above
        # min_measured_mm, so the tracker rebaselines continuously. Run
        # well past stall_timeout_s (15.0s, ~45s here) to prove it stays
        # quiet rather than merely surviving one timeout window.
        measured = 0.0
        for _ in range(90):
            commanded += 2.2
            measured += 2.0
            self._poll(feeder, ch, commanded_pos=commanded, measured_mm=measured)

        assert len(reactor.callbacks) == 0, \
            "the incident shape (slack take-up then normal movement) must " \
            "not trip a stall even run well past stall_timeout_s"

    def test_sustained_jam_fires_stall(self, monkeypatch):
        """Commanded keeps advancing >= min_commanded_mm while measured
        stays flat past stall_timeout_s -- exactly ONE stall fires with a
        commanded/stalled_s/measured report."""
        feeder = self._make_feeder_with_channel(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        gcode = feeder.gcode

        # Baseline poll at t=0.5s.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0)
        reactor.callbacks.clear()

        # Real jam: commanded advances every poll, measured never moves.
        # stall_timeout_s=1.0, poll_interval=0.5 -> 2 more polls to reach
        # the timeout from the baseline.
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0)
        assert len(reactor.callbacks) == 0, \
            "must not fire before stall_timeout_s has elapsed"
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0)

        assert len(reactor.callbacks) == 1, \
            "a sustained real jam must fire exactly one stall"

        # Execute the fired callback and check the report format.
        reactor.callbacks[0](0.0)
        assert any('commanded_mm=' in r for r in gcode._responses)
        assert any('measured_mm=' in r for r in gcode._responses)
        assert any('stalled_s=' in r for r in gcode._responses)
        assert not any('ratio=' in r for r in gcode._responses), \
            "the activity detector does not compute a slip ratio"

        # Further sustained-jam polls (tracker was reset on fire) do not
        # immediately double-fire — min_event_systime suppresses until
        # handled.
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=15.0, measured_mm=0.0)
        assert len(reactor.callbacks) == 0, \
            "min_event_systime suppression must prevent an immediate re-fire"

    def test_retraction_no_stall(self, monkeypatch):
        """Commanded moves negative (retraction) or forward movement stays
        below min_commanded_mm -- no stall, even with flat measured, even
        run past stall_timeout_s repeatedly."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, min_commanded_mm=5.0)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0)
        reactor.callbacks.clear()

        # Retraction: commanded position decreases (negative delta) — only
        # forward delta accumulates, so commanded_since_movement never
        # reaches min_commanded_mm=5.0 no matter how flat measured stays.
        self._poll(feeder, ch, commanded_pos=-2.0, measured_mm=0.0)
        self._poll(feeder, ch, commanded_pos=-4.0, measured_mm=0.0)
        self._poll(feeder, ch, commanded_pos=-6.0, measured_mm=0.0)

        assert len(reactor.callbacks) == 0, \
            "pure retraction/travel must not trip a stall"

        # Small forward moves, individually and cumulatively still below
        # min_commanded_mm=5.0, run well past stall_timeout_s.
        self._poll(feeder, ch, commanded_pos=-5.0, measured_mm=0.0)
        self._poll(feeder, ch, commanded_pos=-4.0, measured_mm=0.0)
        self._poll(feeder, ch, commanded_pos=-3.0, measured_mm=0.0)

        assert len(reactor.callbacks) == 0, \
            "forward movement below min_commanded_mm must not trip a stall"

    def test_extruderless_channel_skips_stall(self, monkeypatch):
        """(e) A channel with no extruder configured disables stall detection
        entirely after _handle_ready (with a one-time warning), while runout
        still fires normally."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, min_commanded_mm=1.0, slip_ratio=0.5, stall_window_polls=2,
            with_extruder=False)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        assert ch._stall_enabled is False
        assert ch._extruder_obj is None

        # Jam-like scenario: motor running, filament present, measured flat.
        # commanded polling would normally accumulate here, but with no
        # extruder object the stall block must be skipped entirely (it must
        # not attempt to call find_past_position on None).
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=10.0)
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=10.0)
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=10.0)
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=10.0)

        assert len(reactor.callbacks) == 0, \
            "extruder-less channel must never fire a stall"

        # Runout still works: filament present -> absent while printing.
        old_state = dict(ch.state)
        old_state['filament_present'] = True
        ch.state['filament_present'] = False
        ch.min_event_systime = 0.0
        feeder._check_events(ch, old_state)
        assert len(reactor.callbacks) == 1, \
            "runout must still fire for an extruder-less channel"

    def test_one_time_warning_logged_for_extruderless_channel(self, monkeypatch, caplog):
        """A channel with extruder=None logs exactly one warning at ready-time."""
        import logging as _logging
        with caplog.at_level(_logging.WARNING):
            feeder = self._make_feeder_with_channel(
                monkeypatch, with_extruder=False)
        warnings = [r for r in caplog.records if r.levelno == _logging.WARNING
                    and 'ch0' in r.message and 'stall detection disabled' in r.message]
        assert len(warnings) == 1, \
            "extruder-less channel must log exactly one warning at ready-time"

    def test_no_stall_without_filament(self, monkeypatch):
        """When filament_present=False, no blockage event fires even with a jam-like pattern."""
        feeder = self._make_feeder_with_channel(monkeypatch, stall_window_polls=2)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   filament_present=False)
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   filament_present=False)
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   filament_present=False)

        assert len(reactor.callbacks) == 0, "no stall when filament absent"

    def test_no_stall_motor_stopped(self, monkeypatch):
        """When motor_running=False, no blockage event fires even with a jam-like pattern."""
        feeder = self._make_feeder_with_channel(monkeypatch, stall_window_polls=2)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   motor_running=False)

        assert len(reactor.callbacks) == 0, "no stall when motor stopped"

    def test_activity_tracker_resets_when_motor_stops(self, monkeypatch):
        """The activity tracker's last-movement clock does not carry across
        a motor stop/start cycle -- it re-baselines to the restart time, not
        the original pre-stop baseline."""
        feeder = self._make_feeder_with_channel(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll at t=0.5s.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0)
        reactor.callbacks.clear()

        # One jam-like poll at t=1.0s, 0.5s into the stall_timeout_s=1.0
        # window -- not yet enough to fire.
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0)
        assert len(reactor.callbacks) == 0

        # Motor stops — tracker resets.
        old_running = dict(ch.state)
        ch.state['motor_running'] = False
        feeder._check_events(ch, old_running)
        assert ch._measured_ref is None

        # Motor restarts at the SAME clock time (t=1.0s) — re-baselines
        # from the restart moment, not the original t=0.5s baseline.
        old_stopped = dict(ch.state)
        ch.state['motor_running'] = True
        feeder._check_events(ch, old_stopped)
        reactor.callbacks.clear()
        assert ch._last_movement_time == pytest.approx(1.0)

        # A poll 0.5s after restart (t=1.5s) is only 0.5s past the RESTART
        # baseline, even though it is 1.0s past the ORIGINAL baseline. If
        # the tracker had carried the original _last_movement_time, this
        # would wrongly fire; it must not.
        self._poll(feeder, ch, commanded_pos=8.0, measured_mm=0.0)
        assert len(reactor.callbacks) == 0, \
            "activity tracker must not carry its clock across motor stop/start"

    def test_channel_config_defaults_require_motor_running_and_pause_on_stall(
            self, monkeypatch):
        """With neither key present in the config section, require_motor_running
        and pause_on_stall both default True."""
        feeder = self._make_feeder_with_channel(monkeypatch)
        ch = feeder._channels[0]
        assert ch.require_motor_running is True
        assert ch.pause_on_stall is True

    def test_passive_channel_sustained_jam_fires_stall(self, monkeypatch):
        """A channel with require_motor_running False, filament present, and
        motor_running False for every poll fires exactly one stall once
        stall_timeout_s elapses — the entire point of the fix.
        _commanded_since_movement is non-empty after an ordinary
        (non-final) poll, proving the trailing else is not wiping it every
        poll (the regression this test guards against)."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, require_motor_running=False)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll, motor stopped throughout.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()

        # Real jam: commanded advances every poll, measured never moves,
        # motor never runs (passive encoder — toolhead extruder pulls).
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   motor_running=False)
        assert ch._commanded_since_movement > 0.0, \
            "commanded_since_movement must accumulate on a passive " \
            "channel poll, not be wiped by the trailing else"

        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   motor_running=False)

        assert len(reactor.callbacks) == 1, \
            "a sustained jam on a passive (motor-never-running) channel " \
            "must fire exactly one stall"

    def test_default_require_motor_running_blocks_passive_stall(self, monkeypatch):
        """A channel left at the default require_motor_running (True) with
        motor_running False never evaluates a stall — behaviourally
        identical to HEAD. This duplicates test_no_stall_motor_stopped's
        intent explicitly under the require_motor_running name."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, min_commanded_mm=1.0, slip_ratio=0.5,
            stall_window_polls=2)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        assert ch.require_motor_running is True

        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   motor_running=False)

        assert len(reactor.callbacks) == 0, \
            "default require_motor_running must keep the motor-stopped gate"

    def test_pause_on_stall_default_pauses_before_gcode(self, monkeypatch):
        """When a stall fires with pause_on_stall at its default (True),
        send_pause_command() is called and the stall_gcode template still
        executes."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, require_motor_running=False)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        gcode = feeder.gcode
        pause_resume = feeder.printer.lookup_object('pause_resume')
        assert ch.pause_on_stall is True

        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   motor_running=False)
        assert len(reactor.callbacks) == 1

        reactor.callbacks[0](0.0)
        assert pause_resume.pause_called is True, \
            "pause_resume.send_pause_command() must be called on stall"
        assert any('M600' in s for s in gcode._scripts_run), \
            "stall_gcode template must still execute when pause_on_stall is True"

    def test_pause_on_stall_false_skips_pause_but_still_runs_gcode(self, monkeypatch):
        """With pause_on_stall False, send_pause_command() is NOT called but
        the stall_gcode template still executes."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, require_motor_running=False, pause_on_stall=False)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        gcode = feeder.gcode
        pause_resume = feeder.printer.lookup_object('pause_resume')
        assert ch.pause_on_stall is False

        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   motor_running=False)
        assert len(reactor.callbacks) == 1

        reactor.callbacks[0](0.0)
        assert pause_resume.pause_called is False, \
            "pause_resume.send_pause_command() must NOT be called when " \
            "pause_on_stall is False"
        assert any('M600' in s for s in gcode._scripts_run), \
            "stall_gcode template must still execute when pause_on_stall is False"

    def test_passive_channel_retraction_no_stall(self, monkeypatch):
        """Passive channel, pure retraction / sub-threshold forward
        movement: no stall, because commanded_since_movement stays below
        min_commanded_mm even with measured flat and the motor never
        running."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, min_commanded_mm=5.0, require_motor_running=False)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll, motor stopped throughout.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()

        # Retraction: commanded position decreases -- only forward delta
        # accumulates, never reaches min_commanded_mm=5.0.
        self._poll(feeder, ch, commanded_pos=-2.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=-4.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=-6.0, measured_mm=0.0,
                   motor_running=False)
        assert len(reactor.callbacks) == 0, \
            "pure retraction on a passive channel must not trip a stall"

        # Sub-threshold forward movement, individually and cumulatively
        # still below min_commanded_mm=5.0.
        self._poll(feeder, ch, commanded_pos=-5.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=-4.0, measured_mm=0.0,
                   motor_running=False)
        self._poll(feeder, ch, commanded_pos=-3.0, measured_mm=0.0,
                   motor_running=False)
        assert len(reactor.callbacks) == 0, \
            "sub-threshold forward movement on a passive channel must " \
            "not trip a stall"

    def test_sensor_disable_mid_jam_resets_tracker(self, monkeypatch):
        """Setting ch.sensor_enabled = False mid-jam resets the activity
        tracker on the next poll; re-enabling re-baselines through the
        normal eligibility transition."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, require_motor_running=False)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0,
                   motor_running=False)
        reactor.callbacks.clear()

        # Mid-jam: one real accumulating poll.
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=0.0,
                   motor_running=False)
        assert ch._commanded_since_movement > 0.0

        # Disable the sensor administratively -- the next poll must reset
        # the tracker, since eligibility becomes False purely from
        # sensor_enabled (the passive-mode equivalent of the motor-stop
        # reset).
        ch.sensor_enabled = False
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=0.0,
                   motor_running=False)
        assert ch._measured_ref is None, \
            "disabling the sensor mid-jam must reset the activity tracker"
        assert ch._commanded_since_movement == pytest.approx(0.0)

        # Re-enable -- the next poll is a not-eligible -> eligible
        # transition, which re-baselines the tracker from this poll.
        ch.sensor_enabled = True
        self._poll(feeder, ch, commanded_pos=15.0, measured_mm=0.0,
                   motor_running=False)
        assert ch._measured_ref is not None, \
            "re-enabling the sensor must re-baseline the activity tracker"
        assert ch._commanded_since_movement == pytest.approx(0.0)

    def test_real_jam_fires_at_shipped_defaults(self, monkeypatch):
        """A channel commanding 4.4 mm/s with feed_mm pinned flat raises
        exactly one stall once stall_timeout_s (15.0s, the shipped
        default) has elapsed, and none before. Proves the suite is not
        merely asserting the absence of false positives on a detector that
        can never fire."""
        feeder = self._make_feeder_with_channel(
            monkeypatch, use_module_defaults=True)
        reactor = feeder.reactor
        ch = feeder._channels[0]
        assert ch.min_commanded_mm == pytest.approx(5.0)
        assert ch.stall_timeout_s == pytest.approx(15.0)
        assert ch.min_measured_mm == pytest.approx(1.0)

        # Baseline poll.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=0.0)
        reactor.callbacks.clear()

        commanded = 0.0
        # 4.4 mm/s at poll_interval=0.5s -> 2.2mm per poll. 15.0s /
        # 0.5s = 30 polls to reach the timeout from the baseline.
        polls_to_timeout = int(ch.stall_timeout_s / feeder.poll_interval)
        for _ in range(polls_to_timeout - 1):
            commanded += 2.2
            self._poll(feeder, ch, commanded_pos=commanded, measured_mm=0.0)
            assert len(reactor.callbacks) == 0, \
                "must not fire before stall_timeout_s has elapsed"

        commanded += 2.2
        self._poll(feeder, ch, commanded_pos=commanded, measured_mm=0.0)
        assert len(reactor.callbacks) == 1, \
            "a real jam must fire exactly once at the shipped defaults"

    def test_reverse_encoder_movement_counts_as_alive(self, monkeypatch):
        """feed_mm decreasing by more than min_measured_mm per poll
        (reversal) with commanded advancing: absolute displacement counts
        as alive -- no stall."""
        feeder = self._make_feeder_with_channel(monkeypatch)
        reactor = feeder.reactor
        ch = feeder._channels[0]

        # Baseline poll.
        self._poll(feeder, ch, commanded_pos=0.0, measured_mm=10.0)
        reactor.callbacks.clear()

        # Encoder reverses every poll while commanded keeps advancing
        # forward -- absolute displacement from the last baseline stays
        # above min_measured_mm each time, so the tracker keeps
        # rebaselining and never accumulates toward the timeout.
        self._poll(feeder, ch, commanded_pos=5.0, measured_mm=7.0)
        self._poll(feeder, ch, commanded_pos=10.0, measured_mm=4.0)
        self._poll(feeder, ch, commanded_pos=15.0, measured_mm=1.0)
        self._poll(feeder, ch, commanded_pos=20.0, measured_mm=-2.0)

        assert len(reactor.callbacks) == 0, \
            "reverse encoder movement must count as liveness, not shortfall"

    def test_removed_drift_internals_are_gone(self, monkeypatch):
        """Neither BmcuChannel nor BmcuFeeder still carries the old
        windowed-drift-detector internals."""
        feeder = self._make_feeder_with_channel(monkeypatch)
        ch = feeder._channels[0]
        removed_channel_attrs = (
            '_stall_window', '_prev_measured_pos', '_stall_window_commanded',
            '_stall_window_measured', '_startup_polls_remaining',
            '_direction_just_changed',
        )
        for attr in removed_channel_attrs:
            assert not hasattr(ch, attr), \
                "BmcuChannel must not carry removed attribute %s" % attr
        assert not hasattr(feeder, '_prev_mm'), \
            "BmcuFeeder must not carry removed attribute _prev_mm"


# ===========================================================================
# Plan 02-04 Task 1: get_status() and serial disconnect handling (KL-11, KL-12, KL-16)
# ===========================================================================

class TestBmcuGetStatus:
    """Tests for get_status() Moonraker visibility and serial disconnect handling."""

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,)):
        """Helper: build a connected BmcuFeeder with the given channel IDs."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls():
            ms = MockSerial()
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()
        return feeder, serial_instances

    def test_get_status(self, monkeypatch):
        """get_status(eventtime) returns a dict with a 'channels' key."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0, 1))
        result = feeder.get_status(0.0)
        assert isinstance(result, dict), "get_status must return a dict"
        assert 'channels' in result, "get_status must return dict with 'channels' key"
        channels = result['channels']
        assert isinstance(channels, dict), "'channels' must be a dict"
        assert '0' in channels, "channel 0 must appear as string key '0'"
        assert '1' in channels, "channel 1 must appear as string key '1'"
        ch0 = channels['0']
        assert 'filament_present' in ch0
        assert 'motor_running' in ch0
        assert 'feed_mm' in ch0
        assert 'speed' in ch0
        assert 'direction' in ch0
        assert 'mag_status' in ch0
        assert 'sensor_enabled' in ch0

    def test_status_immutability(self, monkeypatch):
        """Two consecutive get_status() calls return different dict objects."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        result1 = feeder.get_status(0.0)
        result2 = feeder.get_status(0.0)
        assert id(result1) != id(result2), \
            "get_status must return a NEW dict each call (different object identity)"

    def test_status_type_casts(self, monkeypatch):
        """get_status() values are proper Python types: bool, float, int."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        # Set up known state
        feeder._channels[0].state.update({
            'filament_present': True,
            'motor_running': False,
            'feed_mm': 12.5,
            'speed': 75,
            'direction': 'FWD',
            'mag_status': 'ok',
        })
        result = feeder.get_status(0.0)
        ch = result['channels']['0']
        assert isinstance(ch['filament_present'], bool), \
            "filament_present must be bool, got %s" % type(ch['filament_present'])
        assert isinstance(ch['motor_running'], bool), \
            "motor_running must be bool, got %s" % type(ch['motor_running'])
        assert isinstance(ch['feed_mm'], float), \
            "feed_mm must be float, got %s" % type(ch['feed_mm'])
        assert isinstance(ch['speed'], int), \
            "speed must be int, got %s" % type(ch['speed'])
        assert isinstance(ch['direction'], str), \
            "direction must be str, got %s" % type(ch['direction'])
        assert isinstance(ch['sensor_enabled'], bool), \
            "sensor_enabled must be bool, got %s" % type(ch['sensor_enabled'])

    def test_serial_error_logs(self, monkeypatch):
        """_handle_serial_error logs 'BMCU serial error: {msg}' via logging.error."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch)
        log_calls = []
        monkeypatch.setattr('klippy.extras.bmcu_feeder.logging.error',
                            lambda msg, *args: log_calls.append(msg % args if args else msg))
        feeder._handle_serial_error("device disconnected")
        assert len(log_calls) == 1, "logging.error must be called once"
        assert "BMCU serial error: device disconnected" in log_calls[0], \
            "log message must contain 'BMCU serial error: device disconnected'"

    def test_serial_error_triggers_runout(self, monkeypatch):
        """When _handle_serial_error called and channel has motor_running=True + sensor_enabled=True,
        a runout callback is registered for that channel."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        reactor = feeder.reactor
        ch = feeder._channels[0]
        # Set channel as active (motor running, sensor enabled)
        ch.state['motor_running'] = True
        ch.sensor_enabled = True

        monkeypatch.setattr('klippy.extras.bmcu_feeder.logging.error', lambda *a, **k: None)
        feeder._handle_serial_error("USB disconnect")

        assert len(reactor.callbacks) == 1, \
            "runout callback must be registered for active channel on serial error"

    def test_serial_error_no_runout_inactive(self, monkeypatch):
        """When _handle_serial_error called and channel has motor_running=False,
        no runout handler is registered."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        reactor = feeder.reactor
        ch = feeder._channels[0]
        # Channel inactive (motor stopped)
        ch.state['motor_running'] = False
        ch.sensor_enabled = True

        monkeypatch.setattr('klippy.extras.bmcu_feeder.logging.error', lambda *a, **k: None)
        feeder._handle_serial_error("USB disconnect")

        assert len(reactor.callbacks) == 0, \
            "no runout callback must be registered when motor_running=False"


# ===========================================================================
# Plan 02-04 Task 2: Serial path validation (prevents bare ttyUSB pitfall)
# ===========================================================================

class TestBmcuSerialPathValidation:
    """Tests for serial path validation in BmcuFeeder.__init__."""

    def test_serial_path_validation_rejects_ttyUSB(self):
        """Creating BmcuFeeder with serial='/dev/ttyUSB0' raises config error containing 'by-path'."""
        from klippy.extras.bmcu_feeder import BmcuFeeder
        cfg = MockConfig({'serial': '/dev/ttyUSB0'}, name='bmcu_feeder')
        with pytest.raises(Exception) as exc_info:
            BmcuFeeder(cfg)
        assert 'by-path' in str(exc_info.value), \
            "Error message must contain 'by-path' to guide user to stable path"

    def test_serial_path_validation_rejects_ttyACM(self):
        """Creating BmcuFeeder with serial='/dev/ttyACM0' raises config error containing 'by-path'."""
        from klippy.extras.bmcu_feeder import BmcuFeeder
        cfg = MockConfig({'serial': '/dev/ttyACM0'}, name='bmcu_feeder')
        with pytest.raises(Exception) as exc_info:
            BmcuFeeder(cfg)
        assert 'by-path' in str(exc_info.value), \
            "Error message must contain 'by-path' for ttyACM paths too"

    def test_serial_path_validation_accepts_by_path(self):
        """Creating BmcuFeeder with serial='/dev/serial/by-path/...' does not raise."""
        from klippy.extras.bmcu_feeder import BmcuFeeder
        cfg = MockConfig(
            {'serial': '/dev/serial/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0'},
            name='bmcu_feeder'
        )
        # Should not raise — by-path is acceptable
        feeder = BmcuFeeder(cfg)
        assert feeder.serial_port.startswith('/dev/serial/by-path/')

    def test_serial_path_validation_accepts_by_id(self):
        """Creating BmcuFeeder with serial='/dev/serial/by-id/...' does not raise."""
        from klippy.extras.bmcu_feeder import BmcuFeeder
        cfg = MockConfig(
            {'serial': '/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0'},
            name='bmcu_feeder'
        )
        # Should not raise — by-id is also acceptable
        feeder = BmcuFeeder(cfg)
        assert feeder.serial_port.startswith('/dev/serial/by-id/')


# ===========================================================================
# Phase 5 Plan 01: Feed diagnostics tests (DIAG-01, DIAG-02, DIAG-03)
# ===========================================================================

class TestBmcuDiagnostics:
    """Tests for Phase 5 feed diagnostics: DIAG-01, DIAG-02, DIAG-03."""

    def _make_feeder_with_channel(self, monkeypatch, ch_ids=(0,),
                                   min_commanded_mm=1.0,
                                   slip_ratio=0.5,
                                   stall_window_polls=3,
                                   stall_startup_ignore_polls=0):
        """Helper: build a connected, ready BmcuFeeder with diagnostics-ready
        channels, each with a MockExtruder so stall detection is active."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_params = {
                'extruder': 'extruder',
                'runout_gcode': 'PAUSE',
                'insert_gcode': 'RESUME',
                'stall_gcode': 'M600',
                'min_commanded_mm': min_commanded_mm,
                'slip_ratio': slip_ratio,
                'stall_window_polls': stall_window_polls,
                'stall_startup_ignore_polls': stall_startup_ignore_polls,
            }
            ch_cfg = MockConfig(ch_params, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))
        cfg.printer._objects['idle_timeout'] = MockIdleTimeout(state='Printing')
        cfg.printer._objects['pause_resume'] = MockPauseResume()
        cfg.printer._objects['extruder'] = MockExtruder()

        monkeypatch.setattr(
            'klippy.extras.bmcu_feeder.serial.Serial',
            lambda: MockSerial()
        )
        feeder._handle_connect()
        feeder._handle_ready()
        feeder.reactor.unregister_timer(feeder._poll_timer_handle)
        return feeder

    def _dispatch(self, feeder, ch_id, feed_mm, fil=1, mot=1, spd=50,
                  direction='FWD', mag='ok', ins=1):
        """Helper: inject a STATUS line and poll to update channel state."""
        feeder._serial._lines = [
            ('LINE', 'STATUS ok ch=%d ins=%d fil=%d mot=%d spd=%d dir=%s mm=%.1f mag=%s'
             % (ch_id, ins, fil, mot, spd, direction, feed_mm, mag))
        ]
        feeder._poll_status(0.0)

    def test_reset_feed_single_channel(self, monkeypatch):
        """BMCU_RESET_FEED CHANNEL=0 resets only channel 0; channel 1 keeps its first-poll init."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0, 1))
        # Initialize both channels via first poll
        self._dispatch(feeder, 0, 100.0)
        self._dispatch(feeder, 1, 200.0)
        # Reset only channel 0
        feeder._cmd_reset_feed(MockGcmd({'CHANNEL': 0}))
        # Advance both channels
        self._dispatch(feeder, 0, 150.0)
        self._dispatch(feeder, 1, 250.0)
        status = feeder.get_status(0.0)
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(50.0)
        assert status['channels']['1']['feed_mm_since_reset'] == pytest.approx(50.0)

    def test_reset_feed_all_channels(self, monkeypatch):
        """BMCU_RESET_FEED without CHANNEL resets all channels."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0, 1))
        self._dispatch(feeder, 0, 100.0)
        self._dispatch(feeder, 1, 200.0)
        # Advance
        self._dispatch(feeder, 0, 150.0)
        self._dispatch(feeder, 1, 250.0)
        # Reset all
        feeder._cmd_reset_feed(MockGcmd({}))
        # Advance again
        self._dispatch(feeder, 0, 170.0)
        self._dispatch(feeder, 1, 280.0)
        status = feeder.get_status(0.0)
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(20.0)
        assert status['channels']['1']['feed_mm_since_reset'] == pytest.approx(30.0)

    def test_reset_feed_invalid_channel(self, monkeypatch):
        """BMCU_RESET_FEED CHANNEL=9 responds with 'not configured', no crash."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        gcmd = MockGcmd({'CHANNEL': 9})
        feeder._cmd_reset_feed(gcmd)
        assert any("not configured" in r for r in gcmd._responses)

    def test_reset_feed_resets_stall_count(self, monkeypatch):
        """BMCU_RESET_FEED zeros _lifetime_stall_count."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,),
                                                 min_commanded_mm=1.0)
        ch = feeder._channels[0]
        extruder = feeder.printer.lookup_object('extruder')
        reactor = feeder.reactor
        # Initialize with first poll (insert event fires, clears min_event_systime)
        extruder.next_position = 0.0
        self._dispatch(feeder, 0, 10.0)
        reactor.callbacks.clear()
        ch.min_event_systime = 0.0  # reset event suppression from insert
        # Sustained jam: commanded advances, measured stays flat. Advance
        # the reactor clock past stall_timeout_s (module default 15.0s)
        # before the next dispatch so the activity detector actually fires.
        extruder.next_position = 5.0
        reactor._monotonic_time += ch.stall_timeout_s + 1.0
        self._dispatch(feeder, 0, 10.0)
        assert ch._lifetime_stall_count == 1
        # Reset
        feeder._cmd_reset_feed(MockGcmd({'CHANNEL': 0}))
        assert ch._lifetime_stall_count == 0
        assert feeder.get_status(0.0)['channels']['0']['stall_count'] == 0

    def test_feed_mm_since_reset_in_get_status(self, monkeypatch):
        """get_status shows feed_mm_since_reset as delta from first-poll init."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 100.0)  # first poll inits _feed_mm_at_reset=100
        self._dispatch(feeder, 0, 150.0)
        status = feeder.get_status(0.0)
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(50.0)

    def test_feed_mm_since_reset_updates_after_poll(self, monkeypatch):
        """feed_mm_since_reset updates with each poll."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 100.0)  # init
        self._dispatch(feeder, 0, 200.0)
        assert feeder.get_status(0.0)['channels']['0']['feed_mm_since_reset'] == pytest.approx(100.0)
        self._dispatch(feeder, 0, 300.0)
        assert feeder.get_status(0.0)['channels']['0']['feed_mm_since_reset'] == pytest.approx(200.0)

    def test_feed_mm_since_reset_negative_on_reverse(self, monkeypatch):
        """feed_mm_since_reset is signed (negative when reversed)."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 100.0)  # init
        feeder._cmd_reset_feed(MockGcmd({'CHANNEL': 0}))
        self._dispatch(feeder, 0, 80.0)
        assert feeder.get_status(0.0)['channels']['0']['feed_mm_since_reset'] == pytest.approx(-20.0)

    def test_stall_count_starts_at_zero(self, monkeypatch):
        """stall_count starts at 0 in get_status."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        assert feeder.get_status(0.0)['channels']['0']['stall_count'] == 0

    def test_stall_count_increments_on_stall_fire(self, monkeypatch):
        """stall_count increments when the activity detector fires."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,),
                                                 min_commanded_mm=1.0)
        ch = feeder._channels[0]
        extruder = feeder.printer.lookup_object('extruder')
        reactor = feeder.reactor
        # First poll: baseline (insert event fires, sets min_event_systime=NEVER)
        extruder.next_position = 0.0
        self._dispatch(feeder, 0, 10.0)
        reactor.callbacks.clear()
        ch.min_event_systime = 0.0  # reset event suppression from insert
        # Sustained jam: commanded advances, measured (feed_mm) stays flat.
        # Advance the reactor clock past stall_timeout_s before the next
        # dispatch so the activity detector actually fires.
        extruder.next_position = 5.0
        reactor._monotonic_time += ch.stall_timeout_s + 1.0
        self._dispatch(feeder, 0, 10.0)
        assert len(reactor.callbacks) >= 1
        assert feeder.get_status(0.0)['channels']['0']['stall_count'] == 1

    def test_stall_count_no_increment_on_motor_stop(self, monkeypatch):
        """Motor stop does not increment stall_count."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 10.0, mot=0)
        assert feeder.get_status(0.0)['channels']['0']['stall_count'] == 0

    def test_feed_mm_initialized_from_first_poll(self, monkeypatch):
        """First STATUS poll sets _feed_mm_at_reset to firmware value; feed_mm_since_reset starts at 0."""
        feeder = self._make_feeder_with_channel(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 1500.0)  # firmware accumulated value
        assert feeder.get_status(0.0)['channels']['0']['feed_mm_since_reset'] == pytest.approx(0.0)

    def test_mock_gcmd_get_int_none_default(self):
        """MockGcmd.get_int with default=None and missing key returns None."""
        gcmd = MockGcmd({})
        result = gcmd.get_int('CHANNEL', default=None)
        assert result is None


# ===========================================================================
# Phase 06 Plan 02 Task 1: TestFeedAccumulation (D-06)
# ===========================================================================

class TestFeedAccumulation:
    """
    Unit tests for feed_mm_since_reset accumulation in BmcuFeeder.

    These tests inject mm= values directly into STATUS lines via _poll_status()
    rather than converting from encoder counts. The GEAR_CIRCUMFERENCE_MM
    firmware constant (placeholder 30.0f) does not affect these assertions —
    the Klipper extra tracks whatever float the firmware emits in mm=.
    """

    def _make_feeder_with_channels(self, monkeypatch, ch_ids=(0,)):
        """Helper: build a connected BmcuFeeder with the given channel IDs."""
        from klippy.extras.bmcu_feeder import BmcuFeeder, BmcuChannel

        cfg = MockConfig({'serial': _VALID_SERIAL}, name='bmcu_feeder')
        feeder = BmcuFeeder(cfg)

        for ch_id in ch_ids:
            ch_cfg = MockConfig({'extruder': 'extruder'}, name='bmcu_channel %d' % ch_id)
            ch_cfg.printer = cfg.printer
            cfg.printer.add_object('bmcu_channel %d' % ch_id, BmcuChannel(ch_cfg))

        serial_instances = []

        def mock_serial_cls():
            ms = MockSerial()
            serial_instances.append(ms)
            return ms

        monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)
        feeder._handle_connect()
        # _handle_ready resolves ch._extruder_obj / ch._stall_enabled and
        # sets _estimated_print_time, matching real Klipper startup order
        # (the poll timer that drives _check_events is only ever registered
        # after _handle_ready). No 'extruder' object is registered here, so
        # this cleanly disables stall detection for these channels via the
        # existing extruder-lookup-failure path rather than leaving
        # _stall_enabled/_extruder_obj in the inconsistent __init__-only
        # state these feed-accumulation tests don't exercise.
        feeder._handle_ready()
        feeder.reactor.unregister_timer(feeder._poll_timer_handle)
        return feeder, serial_instances

    def _dispatch(self, feeder, ch_id, feed_mm, fil=1, mot=1, spd=50,
                  direction='FWD', mag='ok', ins=1):
        """Helper: inject a STATUS line and poll to update channel state."""
        feeder._serial._lines = [
            ('LINE', 'STATUS ok ch=%d ins=%d fil=%d mot=%d spd=%d dir=%s mm=%.1f mag=%s'
             % (ch_id, ins, fil, mot, spd, direction, feed_mm, mag))
        ]
        feeder._poll_status(0.0)

    def test_accumulates_across_polls(self, monkeypatch):
        """feed_mm_since_reset accumulates as firmware mm= advances across polls."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        # First poll initialises _feed_mm_at_reset=10.0; feed_mm_since_reset starts at 0
        self._dispatch(feeder, 0, 10.0)
        self._dispatch(feeder, 0, 20.0)
        self._dispatch(feeder, 0, 30.0)
        status = feeder.get_status(0.0)
        # delta = 30.0 - 10.0 (init snapshot)
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(20.0)

    def test_mm_stable_shows_zero_delta(self, monkeypatch):
        """feed_mm_since_reset is zero when firmware mm= does not change between polls.

        This documents the pre-fix bug scenario where the firmware did not
        accumulate feed distance between polls, so the delta was always zero.
        """
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 50.0)  # init
        self._dispatch(feeder, 0, 50.0)
        self._dispatch(feeder, 0, 50.0)
        status = feeder.get_status(0.0)
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(0.0)

    def test_negative_mm_accumulation(self, monkeypatch):
        """feed_mm_since_reset is negative when firmware mm= decreases (reverse feed).

        feed_mm_since_reset is signed per the project key decision 'Signed
        feed_mm_since_reset (not absolute)'.
        """
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 100.0)  # init
        self._dispatch(feeder, 0, 80.0)
        status = feeder.get_status(0.0)
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(-20.0)

    def test_reset_clears_accumulation(self, monkeypatch):
        """BMCU_RESET_FEED sets a new baseline; subsequent delta is from reset point."""
        feeder, _ = self._make_feeder_with_channels(monkeypatch, ch_ids=(0,))
        self._dispatch(feeder, 0, 10.0)  # init
        self._dispatch(feeder, 0, 50.0)  # feed_mm_since_reset = 40.0
        feeder._cmd_reset_feed(MockGcmd({}))
        # After reset _feed_mm_at_reset = 50.0 (current firmware value)
        self._dispatch(feeder, 0, 60.0)
        status = feeder.get_status(0.0)
        # delta = 60.0 - 50.0 reset point
        assert status['channels']['0']['feed_mm_since_reset'] == pytest.approx(10.0)
