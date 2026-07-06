---
phase: 06-feed-distance-tracking
plan: "01"
subsystem: firmware/tests
tags:
  - feed-distance
  - as5600
  - wrap-correction
  - test-fixture
dependency_graph:
  requires: []
  provides:
    - continuous-feed-distance-accumulation
    - mock-serial-zero-arg
  affects:
    - firmware/src/uart_protocol.cpp
    - tests/conftest.py
    - tests/test_bmcu_feeder.py
tech_stack:
  added: []
  patterns:
    - AS5600 wrap-around correction using 2048 midpoint threshold
    - Magnet-offline guard with early-return before any state mutation
    - Zero-arg serial.Serial() construction pattern in BmcuSerial.connect()
key_files:
  created: []
  modified:
    - firmware/src/uart_protocol.cpp
    - tests/conftest.py
    - tests/test_bmcu_feeder.py
decisions:
  - update_feed_distance runs every main-loop tick via uart_protocol_tick() hw_enabled for-loop
  - delta uses int32_t with explicit casts to avoid int16_t overflow at 0/4095 boundary
  - magnet-offline guard is the first statement, preceding even angle_initialized check
  - no motor_dir multiplication in feed_counts — stays raw encoder accumulation
  - MockSerial.open() sets is_open=True matching new zero-arg BmcuSerial.connect() pattern
metrics:
  duration: "~12min (including 108s test runtime dominated by connect() sleep)"
  completed: "2026-07-07"
  tasks_completed: 2
  files_modified: 3
---

# Phase 06 Plan 01: Feed Distance Accumulation Fix Summary

**One-liner:** AS5600 wrap-around correction with int32_t casts, magnet-offline guard, tick-level accumulation, and MockSerial zero-arg fixture restoration.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix update_feed_distance() with wrap correction, magnet guard, and tick-level call | 114604a | firmware/src/uart_protocol.cpp |
| 2 | Fix MockSerial to accept zero-arg construction | e980bae | tests/conftest.py, tests/test_bmcu_feeder.py |

## What Was Built

### Task 1: Firmware — Continuous Feed Distance Accumulation

Modified `update_feed_distance()` in `firmware/src/uart_protocol.cpp`:

1. **Magnet-offline guard** added as the very first statement: `if (MC_AS5600.magnet_stu[ch] == -1) return;` — prevents junk delta accumulation and `prev_angle` corruption when the AS5600 magnet is not detected.

2. **int32_t delta with explicit casts**: `int32_t delta = (int32_t)now - (int32_t)prev_angle[ch];` — the previous `int16_t delta = (int16_t)(now - prev_angle[ch])` was subject to overflow at the 0/4095 encoder boundary because the subtraction happened in uint16_t arithmetic before the cast.

3. **Wrap-around correction** matching `Motion_control.cpp` lines 2084-2086: `if (delta > 2048) delta -= 4096; if (delta < -2048) delta += 4096;` — corrects the AS5600's 12-bit (0-4095) circular boundary.

4. **Tick-level call**: Added `update_feed_distance(ch);` as the last statement inside the `if (hw_enabled)` for-loop in `uart_protocol_tick()`. Feed distance now accumulates every main-loop iteration (~1ms), not only on STATUS polls (~500ms).

5. **Removed stale call from `send_status_response()`**: Deleted the `if (hw_enabled) { for (...) update_feed_distance(ch); }` block that caused double-counting on every STATUS poll.

### Task 2: Test Fixture Restoration

Three changes to restore the 54 previously-broken tests and fix a pre-existing regression:

1. **MockSerial zero-arg construction** (`tests/conftest.py`): Changed `def __init__(self, port, baud, timeout=None)` to `def __init__(self, port=None, baud=None, timeout=None)`. Added `open()` (sets `is_open = True`), `reset_input_buffer()` (no-op), and `readline()` (returns `b"ENABLE ok\n"`) methods to match the `BmcuSerial.connect()` zero-arg serial construction pattern.

2. **Monkeypatch updates** (`tests/test_bmcu_feeder.py`): Updated all `lambda port, baud, timeout: MockSerial(port, baud, timeout)` to `lambda: MockSerial()` and all `def mock_serial_cls(port, baud, timeout):` to `def mock_serial_cls():` throughout the test file.

3. **Pre-existing `_dispatch()` bug fix** (Rule 1 deviation): The `TestBmcuDiagnostics._dispatch()` helper was generating STATUS lines missing the `ins=` field, causing the `_STATUS_FIELD_RE` regex to never match. This silently left all diagnostics tests returning 0.0 feed distance. Fixed by adding `ins=%d` parameter to the format string.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed missing `ins=` field in TestBmcuDiagnostics._dispatch()**

- **Found during:** Task 2 verification
- **Issue:** `_dispatch()` format string was `STATUS ok ch=%d fil=%d ...` but `_STATUS_FIELD_RE` requires `ch=(\d) ins=(\d) fil=(\d) ...`. The regex never matched, so all diagnostics tests (`test_reset_feed_*`, `test_feed_mm_since_reset_*`, `test_stall_count_*`) returned `feed_mm_since_reset = 0.0`.
- **Fix:** Added `ins=%d` to the format string and `ins=1` as a default parameter.
- **Files modified:** `tests/test_bmcu_feeder.py` (same commit as Task 2)
- **Commit:** e980bae

**2. [Rule 3 - Blocking] Updated test_bmcu_feeder.py monkeypatches to zero-arg**

- **Found during:** Task 2 — existing test lambdas `lambda port, baud, timeout: MockSerial(...)` fail when `serial.Serial()` is called with zero args.
- **Fix:** Replaced all 3-arg lambda/function patterns in test_bmcu_feeder.py with zero-arg equivalents. Also cleared `_written` after `connect()` in relevant test helpers since `connect()` now writes `b"ENABLE\n"`.
- **Files modified:** `tests/test_bmcu_feeder.py`
- **Commit:** e980bae (combined with MockSerial fix)

## Known Stubs

None. `GEAR_CIRCUMFERENCE_MM` is a pre-existing placeholder (30.0f) noted in PROJECT.md and not introduced in this plan.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Verification Results

- `grep -n "update_feed_distance" firmware/src/uart_protocol.cpp` shows exactly 2 matches: function definition (line 128) and tick call (line 641). No match in `send_status_response`.
- `python3 -m pytest tests/test_bmcu_feeder.py -q` shows **62 passed** (from 8 passing before this plan).

## Self-Check: PASSED

- firmware/src/uart_protocol.cpp: FOUND (modified)
- tests/conftest.py: FOUND (modified)
- tests/test_bmcu_feeder.py: FOUND (modified)
- Commit 114604a: FOUND
- Commit e980bae: FOUND
