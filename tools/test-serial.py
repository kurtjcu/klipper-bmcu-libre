#!/usr/bin/env python3
"""BMCU Libre firmware protocol test.

Usage: python3 tools/test-serial.py [--port /dev/ttyUSB0]

IMPORTANT: The CH340 RTS line controls NRST. Pyserial must keep RTS=False
(deasserted) to avoid resetting the MCU.
"""
import serial
import time
import sys
import argparse

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    args = p.parse_args()

    print(f"Opening {args.port} at {args.baud} baud...")
    ser = serial.Serial()
    ser.port = args.port
    ser.baudrate = args.baud
    ser.timeout = 2
    ser.dsrdtr = False
    ser.rtscts = False
    ser.open()

    # DTR=True, RTS=False — don't trigger BOOT or RESET
    ser.dtr = True
    ser.rts = False
    time.sleep(1)

    # Drain any boot output
    ser.read(ser.in_waiting or 1)
    ser.reset_input_buffer()

    passed = 0
    failed = 0

    def send_recv(cmd, delay=0.3):
        ser.reset_input_buffer()
        ser.write((cmd + "\n").encode("ascii"))
        time.sleep(delay)
        return ser.readline().decode("ascii", errors="replace").strip()

    def check(name, condition, resp=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  FAIL  {name}  got: {resp!r}")
            failed += 1

    # --- ENABLE ---
    print("\n=== ENABLE / DISABLE ===")
    r = send_recv("ENABLE", delay=3)
    check("ENABLE starts with 'ENABLE ok'", r.startswith("ENABLE ok"), r)
    check("ENABLE contains fil=", "fil=" in r, r)
    check("ENABLE contains mag=", "mag=" in r, r)

    # --- STATUS (pre-ENABLE already done above) ---
    print("\n=== STATUS ===")
    r = send_recv("STATUS")
    check("STATUS starts with 'STATUS ok'", r.startswith("STATUS ok"), r)
    check("Contains ch=0", "ch=0" in r, r)
    check("Contains ch=3", "ch=3" in r, r)
    check("Contains ins=", "ins=" in r, r)
    check("Contains fil=", "fil=" in r, r)
    check("Contains mot=", "mot=" in r, r)
    check("Contains spd=", "spd=" in r, r)
    check("Contains dir=", "dir=" in r, r)
    check("Contains mm=", "mm=" in r, r)
    check("Contains mag=", "mag=" in r, r)

    # Print full STATUS for visual inspection
    print(f"  STATUS: {r}")

    # --- RUN / STOP ---
    print("\n=== RUN / STOP ===")
    for ch in range(4):
        r = send_recv(f"RUN {ch}")
        check(f"RUN {ch}", r == f"RUN ok ch={ch}", r)
    for ch in range(4):
        r = send_recv(f"STOP {ch}")
        check(f"STOP {ch}", r == f"STOP ok ch={ch}", r)

    # --- SPEED ---
    print("\n=== SPEED ===")
    r = send_recv("SPEED 0 75")
    check("SPEED 0 75", "SPEED ok" in r and "spd=75" in r, r)
    r = send_recv("SPEED 2 100")
    check("SPEED 2 100", "SPEED ok" in r and "spd=100" in r, r)
    r = send_recv("SPEED 0 0")
    check("SPEED 0 0 (reset)", "SPEED ok" in r and "spd=0" in r, r)

    # --- DIR ---
    print("\n=== DIR ===")
    r = send_recv("DIR 0 REV")
    check("DIR 0 REV", "DIR ok" in r and "dir=REV" in r, r)
    r = send_recv("DIR 0 FWD")
    check("DIR 0 FWD", "DIR ok" in r and "dir=FWD" in r, r)

    # --- ERROR HANDLING ---
    print("\n=== ERROR HANDLING ===")
    r = send_recv("BOGUS")
    check("Unknown command → ERR", r.startswith("ERR"), r)
    r = send_recv("RUN 9")
    check("Invalid channel → ERR", r.startswith("ERR"), r)
    r = send_recv("DIR 0 SIDEWAYS")
    check("Invalid direction → ERR", r.startswith("ERR"), r)

    # --- MOTOR STATE IN STATUS ---
    print("\n=== MOTOR STATE IN STATUS ===")
    send_recv("SPEED 1 50")
    send_recv("DIR 1 REV")
    send_recv("RUN 1")
    time.sleep(0.3)
    r = send_recv("STATUS")
    check("ch=1 mot=1 after RUN", "ch=1" in r and "mot=1" in r, r)
    send_recv("STOP 1")
    send_recv("SPEED 1 0")
    send_recv("DIR 1 FWD")

    # --- DISABLE ---
    print("\n=== DISABLE ===")
    r = send_recv("DISABLE")
    check("DISABLE ok", r.startswith("DISABLE ok"), r)

    # STATUS should still work when disabled (returns default values)
    r = send_recv("STATUS")
    check("STATUS works after DISABLE", r.startswith("STATUS ok"), r)

    # RUN should fail when disabled
    r = send_recv("RUN 0")
    check("RUN fails after DISABLE", r.startswith("ERR"), r)

    # Re-enable for clean exit
    r = send_recv("ENABLE", delay=3)
    check("Re-ENABLE ok", r.startswith("ENABLE ok"), r)

    # Summary
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*40}")

    ser.close()
    return 1 if failed > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
