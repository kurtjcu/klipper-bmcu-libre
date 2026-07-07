---
phase: 10-enable-boot-timing
plan: 01
subsystem: serial-handshake
tags: [boot-timing, serial, enable-handshake, retry-logic, unit-tests]
dependency_graph:
  requires: []
  provides: [BOOT-wait-connect, ENABLE-retry-connect, simplified-cmd-enable]
  affects: [klippy/extras/bmcu_feeder.py, tests/conftest.py, tests/test_bmcu_feeder.py]
tech_stack:
  added: []
  patterns: [readline-deadline-loop, for-else-retry, _readline_queue-fixture]
key_files:
  created: []
  modified:
    - klippy/extras/bmcu_feeder.py
    - tests/conftest.py
    - tests/test_bmcu_feeder.py
decisions:
  - Promoted import time as _time to module level; removed all local import time statements
  - BOOT loop uses _time.monotonic() deadline (5s) with break on empty readline or BOOT prefix
  - ENABLE retry uses for/else idiom: else clause raises Exception after 3 failed attempts
  - _cmd_enable() temporarily sets timeout=2 for blocking read, restores to 0 after
  - MockSerial._readline_first_call flag returns b"" on first unqueued call (simulates
    BOOT phase hardware timeout), then falls back to b"ENABLE ok\n" for ENABLE phase;
    this avoids 5s CPU spin in existing tests while preserving all test semantics
metrics:
  duration: "~15 minutes"
  completed: "2026-07-07"
  tasks_completed: 2
  files_modified: 3
---

# Phase 10 Plan 01: ENABLE Boot Timing Summary

## One-liner

BOOT-driven handshake with 5s deadline + 3-attempt ENABLE retry replacing sleep(2)/sleep(5).

## What Was Built

### Task 1: Rewrite connect() and _cmd_enable()

`klippy/extras/bmcu_feeder.py` was modified:

1. `import time as _time` promoted to module level (was local in connect() and _cmd_enable(), also cleaned up _cmd_disconnect).

2. `BmcuSerial.connect()` rewritten with BOOT-driven handshake:
   - Sets `s.timeout = 5` for blocking BOOT/ENABLE phase (was `s.timeout = 2`)
   - BOOT readline loop: polls `s.readline()` with `_time.monotonic()` deadline of 5.0s; breaks on empty bytes (hardware timeout) or line starting with "BOOT"; logs warning if no BOOT seen
   - ENABLE retry loop: `for attempt in range(3)` with `for/else` idiom; retries with `_time.sleep(2.0)` between attempts; `else` raises `Exception("BMCU: ENABLE handshake failed after 3 attempts ...")` if all fail
   - Removed: `sleep(2)`, `reset_input_buffer()`, `sleep(3)`, ad-hoc retry block
   - Preserved: `s.dtr = True; s.rts = False` immediately after `s.open()` (CH340 NRST invariant)

3. `BmcuFeeder._cmd_enable()` simplified:
   - Removed `import time as _time` and `sleep(5)`
   - Sets `self._serial._serial.timeout = 2` before read, restores to 0 after
   - Reads firmware response and echoes it via `gcmd.respond_info("BMCU: ENABLE response: %s" % resp)`

### Task 2: MockSerial update and 6 new tests

`tests/conftest.py` MockSerial updated:
- Added `self._readline_queue = []` — sequential responses for test control
- Added `self._readline_first_call = True` — tracks first unqueued call
- `readline()` now: pops from `_readline_queue` if non-empty; else returns `b""` on first unqueued call (simulates BOOT phase timeout); else returns `b"ENABLE ok\n"` (ENABLE handshake fallback)

`tests/test_bmcu_feeder.py` — 6 new tests added to `TestBmcuSerial`:

| Test | Covers |
|------|--------|
| `test_boot_wait_success` | BOOT message detected, ENABLE succeeds, timeout=0 set |
| `test_boot_wait_timeout_fallback` | No BOOT within deadline, ENABLE fallback succeeds |
| `test_enable_retry_loop` | First ENABLE fails, second succeeds; sleep called once with 2.0 |
| `test_enable_all_retries_fail` | 3 failures raise Exception matching "ENABLE handshake failed" |
| `test_enable_ok_already_accepted` | "ENABLE ok already" accepted by `startswith("ENABLE ok")` |
| `test_cmd_enable_no_sleep` | _cmd_enable sends ENABLE, echoes response, _time.sleep not called |

## Test Results

```
77 passed in 0.05s
```

All 71 existing tests continue to pass. 6 new tests added. Total: 77.

## Verification

```
grep -c "time.sleep(2)" klippy/extras/bmcu_feeder.py  → 0
grep -c "time.sleep(5)" klippy/extras/bmcu_feeder.py  → 0
grep -c "reset_input_buffer" klippy/extras/bmcu_feeder.py  → 0
grep -c 'startswith.*BOOT' klippy/extras/bmcu_feeder.py  → 1
grep -c "_readline_queue" tests/conftest.py  → 3
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed local import time from _cmd_disconnect**
- **Found during:** Task 1
- **Issue:** `_cmd_disconnect` still had `import time as _time` locally after the module-level import was added
- **Fix:** Removed the local import; uses module-level `_time`
- **Files modified:** klippy/extras/bmcu_feeder.py

**2. [Rule 1 - Bug] MockSerial.readline() default behavior causes 5s CPU spin**
- **Found during:** Task 2
- **Issue:** The plan specified `b"ENABLE ok\n"` as the default fallback when `_readline_queue` is empty. With the new BOOT loop running until `_time.monotonic()` deadline (5 real seconds), MockSerial would spin the CPU for 5s per test — 71 existing connect()-calling tests × 5s = 355s total. The old code had `sleep(2)` and the old suite took ~126s.
- **Fix:** Added `_readline_first_call` flag to MockSerial. When queue is empty, first readline() call returns `b""` (simulates hardware BOOT phase timeout, breaks the loop immediately), subsequent calls return `b"ENABLE ok\n"` (ENABLE handshake success). All existing test semantics preserved.
- **Files modified:** tests/conftest.py

## Commits

| Task | Hash | Message |
|------|------|---------|
| Task 1 | `2a90c69` | feat(10-01): rewrite connect() and _cmd_enable() for BOOT-driven handshake |
| Task 2 | `5ace6c1` | feat(10-01): update MockSerial with readline queue and add 6 boot timing tests |

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The changes are confined to local USB serial handshake logic (T-10-02 and T-10-03 mitigations implemented as planned).

## Self-Check: PASSED

- klippy/extras/bmcu_feeder.py: FOUND
- tests/conftest.py: FOUND
- tests/test_bmcu_feeder.py: FOUND
- Commit 2a90c69: FOUND
- Commit 5ace6c1: FOUND
