---
status: issues_found
phase: 04-stall-detection-hardening
depth: standard
files_reviewed: 3
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
---

# Code Review: Phase 4 — Stall Detection Hardening

## Files Reviewed
- klippy/extras/bmcu_feeder.py
- tests/test_bmcu_feeder.py
- config/bmcu_generic.cfg

## Findings

### CR-1 — Startup grace poll consumed on motor-start transition itself
- **Severity:** Critical
- **File:** `klippy/extras/bmcu_feeder.py`
- **Lines:** 344-348, 363-367
- **Description:** When the motor transitions from stopped to running, `_check_events` sets `_startup_polls_remaining = stall_startup_ignore_polls` at line 347. However, execution continues into the debounced blockage detection block (lines 359-386) within the *same* call. If `_prev_mm` already has an entry for this channel (which it will after the first poll cycle ever), the startup grace counter is immediately decremented at line 366 during the same invocation that set it. This means the effective grace window is `stall_startup_ignore_polls - 1`, not `stall_startup_ignore_polls` as configured. For example, with `stall_startup_ignore_polls=2`, only 1 subsequent poll is actually suppressed after the motor-start call rather than 2.
- **Impact:** Users who configure `stall_startup_ignore_polls=1` get zero actual grace polls, making a single-poll grace window impossible. With `stall_startup_ignore_polls=2`, only one real grace poll is suppressed. This is an off-by-one that directly undermines the hardening goal.
- **Recommendation:** Either (a) add an early return or `else` guard so the stall-detection block is skipped on the same call that detects motor start, or (b) set the grace counter to `stall_startup_ignore_polls + 1` to compensate. Option (a) is cleaner. Note: the test `test_startup_grace_resets_on_motor_restart` at line 924 explicitly documents this off-by-one in a comment ("this call sets grace=2, then enters stall block which decrements grace to 1"), meaning the test was written to match the buggy behavior rather than the intended behavior.

### WR-1 — `_direction_just_changed` flag not cleared when motor stops
- **Severity:** Warning
- **File:** `klippy/extras/bmcu_feeder.py`
- **Lines:** 382-385
- **Description:** When the motor stops (the `else` branch at line 382), `_stall_counter` and `_startup_polls_remaining` are reset to 0, and `_direction_just_changed` is set to `False`. This is correct. However, consider the sequence: motor running, direction changes (flag set to True), then in the *same poll* the motor also stops. The direction-change block at line 352-356 sets the flag, but then the else-branch at line 382-385 clears it. This specific sequence is fine. However, if direction changes while motor is already stopped (an unlikely but not impossible firmware response), the flag gets set at line 356 but the else-branch at line 385 clears it, which is correct but only by accident -- the clearing happens because `motor_running` is false, not because the code was designed for this edge case.
- **Impact:** Low risk in practice, but the implicit dependency on execution order within `_check_events` is fragile.
- **Recommendation:** Consider clearing `_direction_just_changed` explicitly in the direction-change detection block when the motor is not running, to make the intent explicit rather than relying on the else-branch.

### WR-2 — Stall fires even when `min_event_systime` was set to NEVER by a prior runout/insert
- **Severity:** Warning
- **File:** `klippy/extras/bmcu_feeder.py`
- **Lines:** 372-381
- **Description:** After a runout or insert event fires, `min_event_systime` is set to `reactor.NEVER` (line 337 or 341). The stall detection check at line 374 correctly guards with `now >= ch.min_event_systime`. However, once `_exec_gcode` runs, it resets `min_event_systime` to `monotonic() + event_delay` (line 405). If the runout callback hasn't executed yet (it's deferred via `register_callback`), but the poll timer fires again before the callback runs, the stall check sees `min_event_systime == NEVER` and correctly suppresses. This is fine. But the concern is: after the runout callback runs and sets `min_event_systime = 0.0 + 3.0 = 3.0` (since `MockReactor.monotonic()` returns 0.0), subsequent stall checks with `now = 0.0` will be suppressed because `0.0 < 3.0`. In production, `monotonic()` advances, so this works correctly. No actual bug, but the `event_delay` interaction with stall detection is not tested.
- **Impact:** If `event_delay` is set to 0 and monotonic time is exactly at the boundary, a stall could fire immediately after a runout event, leading to double-action.
- **Recommendation:** Add a test that verifies stall detection is suppressed during the `event_delay` window after a runout event fires.

### WR-3 — `_prev_mm` not cleaned up for removed channels
- **Severity:** Warning
- **File:** `klippy/extras/bmcu_feeder.py`
- **Line:** 386
- **Description:** `_prev_mm` is a dict keyed by `channel_id` that grows but is never pruned. If a channel is removed from config and Klipper is restarted, stale entries persist until the object is recreated. In practice this is harmless since `_prev_mm` is instance-level and `BmcuFeeder` is recreated on config reload, but it represents a minor memory hygiene issue.
- **Impact:** Negligible -- Klipper recreates extras on config reload.
- **Recommendation:** No action needed; informational only.

### IR-1 — Config comment for `stall_gcode` in `bmcu_generic.cfg` is missing
- **Severity:** Info
- **File:** `config/bmcu_generic.cfg`
- **Lines:** 25-26
- **Description:** The `stall_gcode` parameter has no inline comment explaining what it does, unlike `stall_threshold_mm`, `stall_debounce_count`, and `stall_startup_ignore_polls` which all have descriptive comments. Since `stall_gcode` is the user-facing action for blockage detection, a brief comment would improve usability.
- **Recommendation:** Add a comment like `# GCode to run when filament blockage is detected (feed stall while motor running)`.

### IR-2 — Test helper duplication across test classes
- **Severity:** Info
- **File:** `tests/test_bmcu_feeder.py`
- **Lines:** 313, 426, 531, 684, 1007
- **Description:** The `_make_feeder_with_channels` / `_make_feeder_with_channel` helper method is duplicated across five test classes with minor variations. This creates maintenance burden if the setup pattern changes.
- **Recommendation:** Extract a shared fixture or factory function into `conftest.py` with parameters for channel count, gcode templates, and stall config.

## Summary

The stall detection hardening implementation is well-structured overall, with proper debounce counting, startup grace windows, and direction-change suppression. The test suite covers the key scenarios including counter resets, grace window behavior, and direction changes.

One critical off-by-one bug was found: the startup grace counter is consumed on the same poll that detects motor start, making the effective grace window one poll shorter than configured. The test suite was written to match this behavior rather than the documented intent, which masks the bug. Three warnings were identified around edge case handling and test coverage gaps. Two informational items relate to documentation and test maintainability.
