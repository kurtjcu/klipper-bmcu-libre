---
phase: 04-stall-detection-hardening
verified: 2026-05-01T20:15:00Z
status: passed
score: 6/6 must-haves verified
---

# Phase 4: Stall Detection Hardening Verification Report

**Phase Goal:** Users can configure stall detection sensitivity in printer.cfg and stall events fire only on genuine blockages, not at motor start or on direction changes
**Verified:** 2026-05-01T20:15:00Z
**Status:** PASSED
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Stall macro does not fire on the first N polls after motor start (startup grace window) | VERIFIED | `_startup_polls_remaining` countdown in `_check_events` (line 365-367); `test_startup_grace_window_suppresses_stall` passes |
| 2 | Stall macro fires only after stall_debounce_count consecutive below-threshold polls | VERIFIED | `ch._stall_counter >= ch.stall_debounce_count` gate (line 372); `test_stall_fires_after_n_consecutive_polls` passes |
| 3 | A single below-threshold poll does not trigger a stall when debounce_count > 1 | VERIFIED | Counter increments per poll, fires only at threshold; `test_stall_no_fire_single_poll_with_debounce` passes |
| 4 | Reversing motor direction resets the stall comparison snapshot and suppresses stall evaluation on the direction-change poll | VERIFIED | `_direction_just_changed` flag set on `old_dir != new_dir` (line 356), checked and cleared in stall block (line 362-364); `test_direction_change_resets_prev_mm` passes |
| 5 | User can set stall_debounce_count and stall_startup_ignore_polls in printer.cfg | VERIFIED | `config.getint('stall_debounce_count', 3, minval=1)` (line 108); `config.getint('stall_startup_ignore_polls', 2, minval=0)` (line 110-111); both documented in `config/bmcu_generic.cfg` (lines 32-34) |
| 6 | Existing tests continue to pass (backward compatible with debounce_count=1) | VERIFIED | `_make_feeder_with_channel` defaults to `stall_debounce_count=1, stall_startup_ignore_polls=0`; all 5 original stall tests pass; full suite 50/50 green |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `klippy/extras/bmcu_feeder.py` | Debounced stall detection with startup grace and direction-change reset | VERIFIED | Contains `stall_debounce_count` (2 occurrences: config read + comparison), `_direction_just_changed` (5 occurrences: init, set, check, clear, else-reset), `stall_startup_ignore_polls` (3 occurrences: config read, assignment on motor start, decrement) |
| `tests/test_bmcu_feeder.py` | Tests for STALL-01 through STALL-04 | VERIFIED | 7 new test methods added; 12 total stall tests (5 existing + 7 new); all pass |
| `config/bmcu_generic.cfg` | Documentation of new config keys | VERIFIED | `stall_debounce_count: 3` and `stall_startup_ignore_polls: 2` documented in channel 0 section; commented-out equivalents in channel 1 section |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `BmcuChannel.__init__` | `config.getint('stall_debounce_count')` | Klipper config API | WIRED | Line 108: `self.stall_debounce_count = config.getint('stall_debounce_count', 3, minval=1)` |
| `_check_events` | `ch._stall_counter` | consecutive poll counter | WIRED | Line 372: `ch._stall_counter >= ch.stall_debounce_count` gates stall callback registration |
| `_check_events` | `ch._startup_polls_remaining` | startup grace countdown | WIRED | Line 365: `ch._startup_polls_remaining > 0` branch decrements and holds counter at 0 |
| `_check_events direction-change block` | `ch._direction_just_changed` | per-channel boolean flag | WIRED | Line 356: set True on direction change; line 362: checked in stall block; line 364: cleared after skip |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| STALL-01 | 04-01-PLAN | User can configure stall_threshold_mm in printer.cfg | SATISFIED | Pre-existing config key; now works correctly with debounce (test_stall_threshold_configurable passes with debounce_count=1) |
| STALL-02 | 04-01-PLAN | User can configure stall_debounce_count | SATISFIED | `config.getint('stall_debounce_count', 3, minval=1)` in __init__; debounce counter logic in _check_events; tested by 3 dedicated tests |
| STALL-03 | 04-01-PLAN | Stall detection ignores first N polls after motor start | SATISFIED | `stall_startup_ignore_polls` config + `_startup_polls_remaining` countdown; tested by test_startup_grace_window_suppresses_stall and test_startup_grace_resets_on_motor_restart |
| STALL-04 | 04-01-PLAN | Stall detection resets prev_mm snapshot on direction change | SATISFIED | `_direction_just_changed` flag mechanism; tested by test_direction_change_resets_prev_mm |

No orphaned requirements found -- REQUIREMENTS.md maps STALL-01..04 to Phase 4, and all four are covered by plan 04-01.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | - |

No TODO/FIXME/placeholder comments, no empty implementations, no stub patterns found in any modified file. The old single-poll pattern (`prev = self._prev_mm[ch.channel_id]`) has been fully replaced.

### Human Verification Required

### 1. Motor Start Grace Window Timing

**Test:** Start a BMCU motor with `BMCU_RUN CHANNEL=0` while filament is loaded but not being pulled by the extruder. Observe whether stall fires within the first 1.0s (2 polls at default 0.5s interval).
**Expected:** No stall fires during the grace window; stall fires after ~1.5s (grace + 1 debounce poll) if filament truly is not moving.
**Why human:** Empirical motor acceleration timing on real BMCU 370C hardware cannot be verified programmatically.

### 2. Direction Change Suppression

**Test:** Run `BMCU_RUN CHANNEL=0`, wait for stable feed, then `BMCU_DIR CHANNEL=0 DIR=REV`. Observe Klipper logs.
**Expected:** No "blockage detected" log line on the direction-change poll. Stall detection resumes normally after one poll.
**Why human:** Real direction-change feed_mm behavior depends on firmware AS5600 reading which may differ from unit test mocks.

### Gaps Summary

No gaps found. All 6 observable truths verified with supporting artifacts and key links. All 4 requirements (STALL-01 through STALL-04) satisfied. Full test suite passes (50/50). No anti-patterns detected in modified files.

---

_Verified: 2026-05-01T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
