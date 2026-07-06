#!/usr/bin/env python3
"""
BMCU Libre firmware protocol test harness.

Requires: pyserial (pip install pyserial)
Usage: python tests/test_protocol.py [--port /dev/ttyUSB0] [--baud 115200]

Connect BMCU via USB-C before running. Tests validate the wire protocol
defined in .planning/phases/01-firmware/01-RESEARCH.md Pattern 3.
"""
import sys
import time
import argparse
import re

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: pip install pyserial")
    sys.exit(1)


def make_parser():
    p = argparse.ArgumentParser(description="BMCU protocol tester")
    p.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate")
    p.add_argument("--timeout", type=float, default=2.0, help="Read timeout (s)")
    return p


class BMCUTester:
    def __init__(self, port, baud, timeout):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.5)  # wait for boot message
        self.ser.reset_input_buffer()
        self.passed = 0
        self.failed = 0

    def close(self):
        self.ser.close()

    def send(self, cmd):
        self.ser.write((cmd + "\n").encode("ascii"))
        time.sleep(0.1)

    def readline(self):
        line = self.ser.readline().decode("ascii", errors="replace").strip()
        return line

    def send_recv(self, cmd):
        self.send(cmd)
        return self.readline()

    def assert_true(self, name, condition, detail=""):
        if condition:
            print(f"  PASS: {name}")
            self.passed += 1
        else:
            print(f"  FAIL: {name} {detail}")
            self.failed += 1

    # --- Test Functions ---

    def test_uart_connect(self):
        """FW-01: BMCU responds at 115200 8N1 over USB-C."""
        print("\n[test_uart_connect] FW-01")
        resp = self.send_recv("STATUS")
        self.assert_true("Got response", len(resp) > 0, f"empty response")
        self.assert_true("Response is ASCII", resp.isprintable(), f"non-printable: {resp!r}")

    def test_status_response(self):
        """FW-02, FW-05, FW-06, FW-07: STATUS returns parseable line."""
        print("\n[test_status_response] FW-02, FW-05, FW-06, FW-07")
        resp = self.send_recv("STATUS")
        self.assert_true("Starts with STATUS ok", resp.startswith("STATUS ok"), resp[:40])
        for ch in range(4):
            self.assert_true(f"Contains ch={ch}", f"ch={ch}" in resp)
        self.assert_true("Contains fil=", "fil=" in resp)
        self.assert_true("Contains mot=", "mot=" in resp)
        self.assert_true("Contains spd=", "spd=" in resp)
        self.assert_true("Contains dir=", "dir=" in resp)
        self.assert_true("Contains mm=", "mm=" in resp)
        self.assert_true("Contains mag=", "mag=" in resp)

    def test_run_stop(self):
        """FW-03: RUN and STOP commands per channel."""
        print("\n[test_run_stop] FW-03")
        resp = self.send_recv("RUN 0")
        self.assert_true("RUN ok", resp.startswith("RUN ok"), resp)
        self.assert_true("RUN ch=0", "ch=0" in resp, resp)

        resp = self.send_recv("STOP 0")
        self.assert_true("STOP ok", resp.startswith("STOP ok"), resp)
        self.assert_true("STOP ch=0", "ch=0" in resp, resp)

    def test_speed_dir(self):
        """FW-04: SPEED and DIR commands per channel."""
        print("\n[test_speed_dir] FW-04")
        resp = self.send_recv("SPEED 0 75")
        self.assert_true("SPEED ok", resp.startswith("SPEED ok"), resp)
        self.assert_true("spd=75", "spd=75" in resp, resp)

        resp = self.send_recv("DIR 0 REV")
        self.assert_true("DIR ok", resp.startswith("DIR ok"), resp)
        self.assert_true("dir=REV", "dir=REV" in resp, resp)

        # Reset
        self.send_recv("DIR 0 FWD")
        self.send_recv("SPEED 0 0")

    def test_motor_state(self):
        """FW-06: Motor state reflected in STATUS."""
        print("\n[test_motor_state] FW-06")
        self.send_recv("RUN 0")
        resp = self.send_recv("STATUS")
        # Find ch=0 section and check mot=1
        ch0_match = re.search(r"ch=0\s+fil=\d+\s+mot=(\d+)", resp)
        if ch0_match:
            self.assert_true("mot=1 while running", ch0_match.group(1) == "1")
        else:
            self.assert_true("ch=0 mot field found", False, resp[:80])

        self.send_recv("STOP 0")
        resp = self.send_recv("STATUS")
        ch0_match = re.search(r"ch=0\s+fil=\d+\s+mot=(\d+)", resp)
        if ch0_match:
            self.assert_true("mot=0 after stop", ch0_match.group(1) == "0")
        else:
            self.assert_true("ch=0 mot field found", False, resp[:80])

    def test_as5600_state(self):
        """FW-07: AS5600 magnet status in STATUS response."""
        print("\n[test_as5600_state] FW-07")
        resp = self.send_recv("STATUS")
        mag_values = re.findall(r"mag=(\w+)", resp)
        self.assert_true("4 mag fields", len(mag_values) == 4, f"found {len(mag_values)}")
        valid = {"ok", "low", "high", "offline"}
        for i, v in enumerate(mag_values):
            self.assert_true(f"mag[{i}] valid value", v in valid, f"got {v}")

    def test_error_handling(self):
        """FW-02: Invalid commands return ERR."""
        print("\n[test_error_handling] FW-02")
        resp = self.send_recv("BOGUS")
        self.assert_true("ERR response", resp.startswith("ERR"), resp)

        resp = self.send_recv("RUN 9")
        self.assert_true("ERR invalid channel", resp.startswith("ERR"), resp)

    def test_feed_distance(self):
        """FW-08: mm field in STATUS is a float."""
        print("\n[test_feed_distance] FW-08")
        resp = self.send_recv("STATUS")
        mm_values = re.findall(r"mm=([\d.-]+)", resp)
        self.assert_true("4 mm fields", len(mm_values) == 4, f"found {len(mm_values)}")
        for i, v in enumerate(mm_values):
            try:
                float(v)
                self.assert_true(f"mm[{i}] is float", True)
            except ValueError:
                self.assert_true(f"mm[{i}] is float", False, f"got {v}")

    def test_feed_continuous_accumulation(self):
        """Phase 6: mm= for ch=0 advances monotonically while motor is running."""
        print("\n[test_feed_continuous_accumulation] Phase 6")
        # Ensure motor is enabled before starting (Pitfall 4: test cannot
        # rely on prior ENABLE state from a previous test)
        self.send_recv("ENABLE")
        self.send_recv("RUN 0")

        mm_values = []
        for _ in range(6):
            time.sleep(0.5)
            resp = self.send_recv("STATUS")
            m = re.search(r"ch=0 [^\n]*mm=(-?[\d.]+)", resp)
            if m:
                mm_values.append(float(m.group(1)))

        self.send_recv("STOP 0")

        self.assert_true(
            "At least 3 STATUS samples collected",
            len(mm_values) >= 3,
            f"got {len(mm_values)} samples",
        )
        monotonic = all(mm_values[i + 1] > mm_values[i] for i in range(len(mm_values) - 1))
        self.assert_true(
            "mm= values increase monotonically during motor run",
            monotonic,
            f"values={mm_values}",
        )


def main():
    args = make_parser().parse_args()
    print(f"Connecting to {args.port} at {args.baud} baud...")

    try:
        t = BMCUTester(args.port, args.baud, args.timeout)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {args.port}: {e}")
        print("Is the BMCU connected via USB-C?")
        sys.exit(1)

    tests = [
        t.test_uart_connect,
        t.test_status_response,
        t.test_run_stop,
        t.test_speed_dir,
        t.test_motor_state,
        t.test_as5600_state,
        t.test_error_handling,
        t.test_feed_distance,
        t.test_feed_continuous_accumulation,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            t.failed += 1

    t.close()

    print(f"\n{'='*40}")
    print(f"Results: {t.passed} passed, {t.failed} failed")
    print(f"{'='*40}")
    sys.exit(1 if t.failed > 0 else 0)


if __name__ == "__main__":
    main()
