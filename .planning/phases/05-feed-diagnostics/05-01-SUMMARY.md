---
phase: 05-feed-diagnostics
plan: 01
subsystem: klipper-extra
tags: [diagnostics, feed-tracking, stall-count, gcode-command, moonraker]
dependency_graph:
  requires: [04-01]
  provides: [feed_mm_since_reset, stall_count, BMCU_RESET_FEED]
  affects: [bmcu_feeder.py, bmcu_generic.cfg]
tech_stack:
  added: []
  patterns: [snapshot-delta for feed tracking, optional CHANNEL param for reset command]
key_files:
  created: []
  modified:
    - klippy/extras/bmcu_feeder.py
    - tests/test_bmcu_feeder.py
    - tests/conftest.py
    - config/bmcu_generic.cfg
decisions:
  - "feed_mm_since_reset is signed (negative on reverse) not absolute -- matches firmware encoder semantics"
  - "BMCU_RESET_FEED resets both feed distance and stall count -- single command for START_PRINT macro"
  - "First-poll initialization sets _feed_mm_at_reset to firmware value so feed_mm_since_reset starts at 0.0"
metrics:
  duration: 3min
  completed: "2026-05-01T03:32:26Z"
  tasks: 2
  files: 4
  tests_added: 12
  tests_total: 62
---

# Phase 5 Plan 01: Feed Diagnostics Summary

Per-channel feed distance tracking with snapshot-delta pattern, cumulative stall counting at the debounce firing point, and BMCU_RESET_FEED GCode command with optional CHANNEL parameter for Moonraker/Mainsail visibility.

## What Was Done

### Task 1: Write diagnostics tests and fix MockGcmd bug (RED)
- **Commit:** a9e5b3e
- Fixed MockGcmd.get_int to return None when key absent and default=None (was raising TypeError from int(None))
- Added TestBmcuDiagnostics class with 12 test methods covering DIAG-01, DIAG-02, DIAG-03
- Tests cover: single/all channel reset, invalid channel, stall count reset, feed_mm_since_reset computation, negative delta on reverse, first-poll initialization, stall count lifecycle

### Task 2: Implement feed diagnostics (GREEN)
- **Commit:** 35f0ca3
- Added `_feed_mm_at_reset`, `_lifetime_stall_count`, `_feed_mm_initialized` fields to BmcuChannel.__init__
- Added first-poll initialization in `_dispatch_status_line` -- sets `_feed_mm_at_reset` to firmware's reported value on first STATUS response, preventing a large jump in `feed_mm_since_reset`
- Added `ch._lifetime_stall_count += 1` in stall firing block, with updated logging to include total_stalls count
- Registered `BMCU_RESET_FEED` command with optional `CHANNEL` parameter (default=None resets all channels); also zeros `_lifetime_stall_count`
- Added `feed_mm_since_reset` and `stall_count` to `get_status()` dict comprehension -- preserves fresh-dict-per-call property for Moonraker change detection
- Documented all GCode commands and Moonraker objects in `config/bmcu_generic.cfg`
- Fixed 2 test methods that needed `min_event_systime` reset after insert event suppression

## Requirements Satisfied

- **DIAG-01:** BMCU_RESET_FEED zeros feed distance counter for one channel (CHANNEL=N) or all channels (no param); also resets stall_count
- **DIAG-02:** feed_mm_since_reset visible in get_status() per channel, computed as current feed_mm minus snapshot at reset; initializes correctly from first STATUS poll
- **DIAG-03:** stall_count visible in get_status() per channel, increments only when debounced stall fires, resets on BMCU_RESET_FEED

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed insert event suppression in stall tests**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** Two stall-related diagnostics tests failed because the first `_dispatch` call triggered an insert event (filament absent->present), which set `min_event_systime = NEVER` and suppressed all subsequent events including stall detection
- **Fix:** Added `ch.min_event_systime = 0.0` after first dispatch and callback clearing in `test_reset_feed_resets_stall_count` and `test_stall_count_increments_on_stall_fire`
- **Files modified:** tests/test_bmcu_feeder.py
- **Commit:** 35f0ca3

**2. [Deviation] Plan stated 13 test methods but listed 12 (a-l)**
- The plan frontmatter says "13 test methods" but items a through l enumerate exactly 12 methods. All 12 were implemented. This is a plan counting discrepancy, not a missing test.

## TDD Gate Compliance

- RED gate: a9e5b3e (`test(05-01)`) -- 12 tests added, 11 fail (1 MockGcmd fix test passes immediately)
- GREEN gate: 35f0ca3 (`feat(05-01)`) -- all 62 tests pass (full suite)
- REFACTOR gate: not needed -- no cleanup required

## Known Stubs

None -- all data paths are wired from firmware STATUS responses through to Moonraker get_status().

## Self-Check: PASSED
