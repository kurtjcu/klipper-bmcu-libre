"""
Unit tests for klippy/extras/bmcu_feeder.py

Task 1: BmcuSerial (6 tests, KL-01)
Task 2: BmcuChannel, BmcuFeeder config and lifecycle (6 tests, KL-02)
"""

import pytest
from unittest.mock import patch, MagicMock

from klippy.extras.bmcu_feeder import BmcuSerial
from tests.conftest import MockSerial, MockReactor, MockConfig, MockPrinter


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
