"""
Mock Klipper objects for unit-testing bmcu_feeder.py without a live Klipper
instance or real serial hardware.
"""

import pytest


# ---------------------------------------------------------------------------
# Sentinel for optional parameters
# ---------------------------------------------------------------------------

_SENTINEL = object()


# ---------------------------------------------------------------------------
# Mock reactor
# ---------------------------------------------------------------------------

class MockFdHandle:
    """Opaque handle returned by MockReactor.register_fd."""
    def __init__(self, fd, callback):
        self.fd = fd
        self.callback = callback


class MockTimerHandle:
    """Opaque handle returned by MockReactor.register_timer."""
    def __init__(self, callback, waketime):
        self.callback = callback
        self.waketime = waketime


class MockReactor:
    NEVER = 9999999999999.0

    def __init__(self):
        self.registered_fds = []      # list of MockFdHandle
        self._timers = []             # list of MockTimerHandle
        self.callbacks = []           # list of callbacks registered via register_callback
        self._monotonic_time = 0.0

    def register_fd(self, fd, callback):
        handle = MockFdHandle(fd, callback)
        self.registered_fds.append(handle)
        return handle

    def unregister_fd(self, handle):
        if handle in self.registered_fds:
            self.registered_fds.remove(handle)

    def register_timer(self, callback, waketime):
        handle = MockTimerHandle(callback, waketime)
        self._timers.append(handle)
        return handle

    def unregister_timer(self, handle):
        if handle in self._timers:
            self._timers.remove(handle)

    def register_callback(self, callback):
        self.callbacks.append(callback)

    def monotonic(self):
        return self._monotonic_time

    def pause(self, waketime):
        pass


# ---------------------------------------------------------------------------
# Mock serial port
# ---------------------------------------------------------------------------

class MockSerial:
    def __init__(self, port=None, baud=None, timeout=None):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._written = b""
        self._read_data = b""
        self.is_open = False
        self._raise_on_read = None   # set to an OSError to simulate read errors
        self._readline_queue = []    # sequential responses consumed by readline()
        self._readline_first_call = True  # True until first unqueued readline call

    def open(self):
        self.is_open = True

    def fileno(self):
        return 99

    def read(self, size):
        if self._raise_on_read is not None:
            raise self._raise_on_read
        data = self._read_data[:size]
        self._read_data = self._read_data[size:]
        return data

    def readline(self):
        if self._readline_queue:
            return self._readline_queue.pop(0)
        # First unqueued call returns b"" to simulate BOOT phase timeout;
        # subsequent unqueued calls return b"ENABLE ok\n" for ENABLE handshake.
        if self._readline_first_call:
            self._readline_first_call = False
            return b""
        return b"ENABLE ok\n"

    def write(self, data):
        self._written += data

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


# ---------------------------------------------------------------------------
# Mock gcode template
# ---------------------------------------------------------------------------

class MockTemplate:
    def __init__(self, text):
        self.text = text

    def render(self):
        return self.text


# ---------------------------------------------------------------------------
# Mock gcode_macro
# ---------------------------------------------------------------------------

class MockGcodeMacro:
    def load_template(self, config, key, default=""):
        return MockTemplate(config.get(key, default))


# ---------------------------------------------------------------------------
# Mock mcu — provides estimated_print_time for the drift-aware stall detector
# ---------------------------------------------------------------------------

class MockMcu:
    """Mock of Klipper's mcu object.  estimated_print_time(eventtime) normally
    converts a reactor eventtime into an MCU print_time; tests can override
    via _print_time_value to decouple from eventtime, defaulting to identity.
    """
    def __init__(self):
        self._print_time_value = None  # None => identity (return eventtime)

    def estimated_print_time(self, eventtime):
        if self._print_time_value is not None:
            return self._print_time_value
        return eventtime


# ---------------------------------------------------------------------------
# Mock extruder — provides find_past_position for the drift-aware stall detector
# ---------------------------------------------------------------------------

class MockExtruder:
    """Mock of Klipper's extruder (toolhead trapq) object.  Tests script the
    commanded cumulative position returned by find_past_position via
    next_position (fixed value) or a queue (sequential values, one per call).
    """
    def __init__(self, position=0.0):
        self.next_position = position
        self._position_queue = []

    def find_past_position(self, print_time):
        if self._position_queue:
            return self._position_queue.pop(0)
        return self.next_position


# ---------------------------------------------------------------------------
# Mock gcode
# ---------------------------------------------------------------------------

class MockGcode:
    def __init__(self):
        self._commands = {}
        self._mux_commands = {}
        self._scripts_run = []
        self._responses = []

    def register_command(self, name, handler, desc=""):
        self._commands[name] = handler

    def register_mux_command(self, name, key, value, handler, desc=""):
        self._mux_commands[(name, key, value)] = handler

    def run_script(self, script):
        self._scripts_run.append(script)

    def respond_info(self, text):
        self._responses.append(text)


# ---------------------------------------------------------------------------
# Mock printer
# ---------------------------------------------------------------------------

class MockPrinter:
    def __init__(self):
        self._reactor = MockReactor()
        self._objects = {}
        self._event_handlers = {}
        # Pre-register standard objects
        self._objects['gcode'] = MockGcode()
        self._objects['gcode_macro'] = MockGcodeMacro()
        self._objects['mcu'] = MockMcu()

    def get_reactor(self):
        return self._reactor

    def lookup_object(self, name):
        if name not in self._objects:
            raise KeyError("Unknown object: %s" % name)
        return self._objects[name]

    def load_object(self, config, name):
        if name not in self._objects:
            raise KeyError("Unknown object: %s" % name)
        return self._objects[name]

    def register_event_handler(self, event, callback):
        self._event_handlers.setdefault(event, []).append(callback)

    def add_object(self, name, obj):
        self._objects[name] = obj

    def config_error(self, msg):
        return Exception(msg)


# ---------------------------------------------------------------------------
# Mock config
# ---------------------------------------------------------------------------

class MockConfig:
    def __init__(self, params=None, name="bmcu_feeder"):
        self._params = params or {}
        self._name = name
        self.printer = MockPrinter()

    def get_printer(self):
        return self.printer

    def get_name(self):
        return self._name

    def get(self, key, default=_SENTINEL):
        if key in self._params:
            return self._params[key]
        if default is _SENTINEL:
            raise KeyError("Missing config key: %s" % key)
        return default

    def getint(self, key, default=_SENTINEL, minval=None, maxval=None):
        if key in self._params:
            val = int(self._params[key])
        elif default is not _SENTINEL:
            val = default
        else:
            raise KeyError("Missing config key: %s" % key)
        if minval is not None and val < minval:
            raise ValueError("%s below minval %s" % (key, minval))
        if maxval is not None and val > maxval:
            raise ValueError("%s above maxval %s" % (key, maxval))
        return val

    def getfloat(self, key, default=_SENTINEL, minval=None, maxval=None):
        if key in self._params:
            val = float(self._params[key])
        elif default is not _SENTINEL:
            val = float(default)
        else:
            raise KeyError("Missing config key: %s" % key)
        if minval is not None and val < minval:
            raise ValueError("%s below minval %s" % (key, minval))
        if maxval is not None and val > maxval:
            raise ValueError("%s above maxval %s" % (key, maxval))
        return val

    def getboolean(self, key, default=_SENTINEL):
        if key in self._params:
            raw = self._params[key]
            if isinstance(raw, bool):
                return raw
            return str(raw).lower() in ('1', 'true', 'yes')
        if default is not _SENTINEL:
            return default
        raise KeyError("Missing config key: %s" % key)

    def error(self, msg):
        return Exception(msg)


# ---------------------------------------------------------------------------
# Mock GCode command object
# ---------------------------------------------------------------------------

class MockGcmd:
    def __init__(self, params=None):
        self._params = params or {}
        self._responses = []

    def get_int(self, key, default=None, minval=None, maxval=None):
        val = self._params.get(key, default)
        if val is None:
            return None
        return int(val)

    def get(self, key, default=None):
        return self._params.get(key, default)

    def respond_info(self, text):
        self._responses.append(text)

    def error(self, msg):
        return Exception(msg)


# ---------------------------------------------------------------------------
# Mock idle_timeout
# ---------------------------------------------------------------------------

class MockIdleTimeout:
    def __init__(self, state='Ready'):
        self._state = state

    def get_status(self, eventtime):
        return {'state': self._state}


# ---------------------------------------------------------------------------
# Mock pause_resume
# ---------------------------------------------------------------------------

class MockPauseResume:
    def __init__(self):
        self.pause_called = False

    def send_pause_command(self):
        self.pause_called = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_printer():
    p = MockPrinter()
    p._objects['idle_timeout'] = MockIdleTimeout()
    p._objects['pause_resume'] = MockPauseResume()
    return p
