---
phase: 06-feed-distance-tracking
plan: "02"
subsystem: tests
tags:
  - feed-distance
  - pytest
  - hardware-test
  - accumulation
dependency_graph:
  requires:
    - 06-01
  provides:
    - feed-accumulation-unit-tests
    - hardware-continuous-accumulation-test
  affects:
    - tests/test_bmcu_feeder.py
    - tests/test_protocol.py
tech_stack:
  added: []
  patterns:
    - _dispatch() helper pattern for injecting STATUS lines in pytest
    - monkeypatch serial.Serial zero-arg lambda for BmcuFeeder tests
key_files:
  created: []
  modified:
    - tests/test_bmcu_feeder.py
    - tests/test_protocol.py
decisions:
  - TestFeedAccumulation uses same _make_feeder_with_channels/_dispatch pattern as TestBmcuPolling/TestBmcuDiagnostics for consistency
  - hardware test sends ENABLE before RUN 0 to avoid reliance on prior test state (Pitfall 4)
  - hardware test polls 6x at 0.5s intervals for a 3s motor run window
  - monotonically increasing mm= assertion documents the firmware fix from Plan 01
metrics:
  duration: "~3min"
  completed: "2026-07-07"
  tasks_completed: 2
  files_modified: 2
---

# Phase 06 Plan 02: Feed Distance Tests Summary

**One-liner:** TestFeedAccumulation pytest class (4 unit tests) and test_feed_continuous_accumulation hardware integration test validating the Plan 01 firmware accumulation fix.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add TestFeedAccumulation pytest class | d4ef2a1 | tests/test_bmcu_feeder.py |
| 2 | Add hardware test for continuous feed accumulation | 756860c | tests/test_protocol.py |

## What Was Built

### Task 1: TestFeedAccumulation pytest class

Added `TestFeedAccumulation` class to `tests/test_bmcu_feeder.py` (after `TestBmcuDiagnostics`). The class includes:

- `_make_feeder_with_channels()` helper — same pattern as `TestBmcuPolling` (zero-arg monkeypatched serial.Serial, _handle_connect call)
- `_dispatch()` helper — same pattern as `TestBmcuDiagnostics` (injects STATUS line with ins= field, calls _poll_status)

Four test methods:

1. **test_accumulates_across_polls** — injects mm=10.0 (init), mm=20.0, mm=30.0; asserts feed_mm_since_reset == 20.0 (delta from init snapshot)
2. **test_mm_stable_shows_zero_delta** — injects mm=50.0 three times; asserts feed_mm_since_reset == 0.0 (documents pre-fix bug scenario)
3. **test_negative_mm_accumulation** — injects mm=100.0 (init) then mm=80.0; asserts feed_mm_since_reset == -20.0 (signed per project decision)
4. **test_reset_clears_accumulation** — injects mm=10.0 (init), mm=50.0, calls _cmd_reset_feed, injects mm=60.0; asserts feed_mm_since_reset == 10.0

Full pytest suite: **66 passed** (62 from Plan 01 + 4 new).

### Task 2: Hardware test for continuous accumulation

Added `test_feed_continuous_accumulation()` method to `BMCUTester` in `tests/test_protocol.py`:

- Sends ENABLE then RUN 0 (motor start)
- Loops 6 times with 0.5s sleep: sends STATUS, parses `mm=` for ch=0 using `re.search(r"ch=0 [^\n]*mm=(-?[\d.]+)", resp)`
- Sends STOP 0 after loop
- Asserts: at least 3 samples collected; mm= values are monotonically increasing

Registered as `t.test_feed_continuous_accumulation` in the `tests` list in `main()`, after `t.test_feed_distance`.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The hardware test requires a physical BMCU connected via USB-C. It cannot run in CI without hardware.

## Threat Flags

None. Test files only; no production code changed.

## Verification Results

- `python3 -m pytest tests/test_bmcu_feeder.py::TestFeedAccumulation -x -v`: 4 passed
- `python3 -m pytest tests/test_bmcu_feeder.py -q`: 66 passed, 0 failures
- `python3 -c "import ast; ast.parse(open('tests/test_protocol.py').read())"`: no syntax errors
- `grep -c "test_feed_continuous_accumulation" tests/test_protocol.py`: 3 (def + tests list + docstring context)

## Self-Check: PASSED

- tests/test_bmcu_feeder.py: FOUND (modified, contains `class TestFeedAccumulation`)
- tests/test_protocol.py: FOUND (modified, contains `def test_feed_continuous_accumulation`)
- Commit d4ef2a1: FOUND
- Commit 756860c: FOUND
