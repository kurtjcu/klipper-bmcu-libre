---
phase: 07-direction-mapping
verified: 2026-07-07T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
gaps:
deferred:
human_verification:
  - test: "Flash V2.2 hardware and issue BMCU_DIR CHANNEL=0 DIR=FWD with direction_invert: True in printer.cfg"
    expected: "Filament feeds inward (motor rotates toward printer) — not ejected"
    why_human: "Motor polarity and physical wire routing cannot be verified from code alone; requires V2.2 hardware under power"
  - test: "Issue BMCU_DIR CHANNEL=0 DIR=FWD without direction_invert (default False) on V2.2 hardware"
    expected: "Filament ejects (existing behavior — this confirms the uncorrected baseline for the release note)"
    why_human: "Baseline behavior is hardware-specific and cannot be inferred from code"
---

# Phase 07: Direction Mapping Verification Report

**Phase Goal:** FWD command currently ejects filament on V2.2 hardware — add direction_invert config option or swap direction in firmware so FWD feeds inward.
**Verified:** 2026-07-07
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | BMCU_DIR CHANNEL=0 DIR=FWD sends DIR 0 REV over serial when direction_invert is True | VERIFIED | `test_fwd_inverted_sends_rev` PASS; `_cmd_dir` lines 358-363 in bmcu_feeder.py: `wire_dir = 'REV' if direction == 'FWD' else 'FWD'` when `ch.direction_invert` |
| 2 | BMCU_DIR CHANNEL=0 DIR=FWD sends DIR 0 FWD over serial when direction_invert is False (default) | VERIFIED | `test_fwd_not_inverted_sends_fwd` PASS; `wire_dir = direction` path in `_cmd_dir` when `ch.direction_invert` is False |
| 3 | STATUS dir= field is stored raw in ch.state without inversion | VERIFIED | `test_status_dir_stored_raw` PASS; `_dispatch_status_line` lines 409-429 assigns `m.group(6)` directly to `ch.state['direction']` — no direction_invert reference in that method |
| 4 | Config files document the direction_invert option for V2.2 users | VERIFIED | `config/bmcu_generic.cfg`: 4 matching lines (comment + commented option in each of [bmcu_channel 0] and [bmcu_channel 1]); `config/bmcu_buffer_tapchanger.cfg`: 1 line directing users to bmcu_generic.cfg |
| 5 | Full test suite green (71 tests) | VERIFIED | `python -m pytest tests/ --tb=short` → 71 passed in 124.11s, exit 0 |
| 6 | TDD gate respected (RED before GREEN) | VERIFIED | Commits 6edf3e6 (failing tests) and 66f7c1b (implementation) are separate, in correct order per git log |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `klippy/extras/bmcu_feeder.py` | direction_invert config + _cmd_dir inversion logic | VERIFIED | Line 133: `self.direction_invert = config.getboolean('direction_invert', False)`; lines 358-363: wire_dir conditional; _dispatch_status_line unchanged |
| `tests/test_bmcu_feeder.py` | TestDirectionInvert class with 5 test methods | VERIFIED | Class exists at line 427; all 5 methods present and passing |
| `config/bmcu_generic.cfg` | Commented direction_invert option in both channel sections | VERIFIED | grep confirms 4 lines: comment + `# direction_invert: True` in [bmcu_channel 0] and [bmcu_channel 1] |
| `config/bmcu_buffer_tapchanger.cfg` | Note about per-channel options belonging in bmcu_generic.cfg | VERIFIED | Line 15: "Per-channel options (e.g. direction_invert) belong in the [bmcu_channel N] sections in bmcu_generic.cfg" |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `klippy/extras/bmcu_feeder.py` | `BmcuChannel.direction_invert` | `config.getboolean` in `__init__` | WIRED | Line 133: `config.getboolean('direction_invert', False)` — parsed from config at construction time |
| `klippy/extras/bmcu_feeder.py` | serial.send DIR command | `_cmd_dir` inversion logic with `wire_dir` | WIRED | Lines 358-363: `ch = self._channels[ch_id]`, inversion applied, `self._serial.send("DIR %d %s\n" % (ch_id, wire_dir))` |

### Data-Flow Trace (Level 4)

Not applicable — this phase adds a config-time option and command-dispatch mutation, not a data-rendering component. The flow is: config.getboolean → ch.direction_invert (bool) → _cmd_dir reads it → wire_dir → serial.send. All links verified at Level 3.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 5 TestDirectionInvert tests pass | `python -m pytest tests/test_bmcu_feeder.py::TestDirectionInvert -v` | 5/5 PASSED | PASS |
| Full suite remains green | `python -m pytest tests/ --tb=short` | 71/71 PASSED, exit 0 | PASS |
| direction_invert appears in non-comment code (2 uses) | `grep -v '^#' klippy/extras/bmcu_feeder.py \| grep -c 'direction_invert'` | 2 | PASS |
| direction_invert count in bmcu_generic.cfg | `grep -c 'direction_invert' config/bmcu_generic.cfg` | 4 | PASS |
| direction_invert count in bmcu_buffer_tapchanger.cfg | `grep -c 'direction_invert' config/bmcu_buffer_tapchanger.cfg` | 1 | PASS |

### Probe Execution

No probe scripts declared in PLAN or present in `scripts/*/tests/`. Step 7c: SKIPPED (no probes for this phase).

### Requirements Coverage

**WARNING: DIR-INV requirement IDs are orphaned — declared in PLAN frontmatter but undefined in REQUIREMENTS.md.**

The PLAN frontmatter declares: `requirements: [DIR-INV-01, DIR-INV-02, DIR-INV-03, DIR-INV-04, DIR-INV-05]`. Searching REQUIREMENTS.md for `DIR-INV` returns zero matches. The entire v1.2 section is absent from REQUIREMENTS.md — only v1.1 requirements (STALL-*, DIAG-*) are defined there.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DIR-INV-01 | 07-01-PLAN.md | Not defined in REQUIREMENTS.md | ORPHANED | No entry in .planning/REQUIREMENTS.md |
| DIR-INV-02 | 07-01-PLAN.md | Not defined in REQUIREMENTS.md | ORPHANED | No entry in .planning/REQUIREMENTS.md |
| DIR-INV-03 | 07-01-PLAN.md | Not defined in REQUIREMENTS.md | ORPHANED | No entry in .planning/REQUIREMENTS.md |
| DIR-INV-04 | 07-01-PLAN.md | Not defined in REQUIREMENTS.md | ORPHANED | No entry in .planning/REQUIREMENTS.md |
| DIR-INV-05 | 07-01-PLAN.md | Not defined in REQUIREMENTS.md | ORPHANED | No entry in .planning/REQUIREMENTS.md |

The implementation fully satisfies the phase goal in code. The orphaned IDs are a documentation gap: REQUIREMENTS.md was not updated to add a v1.2 section covering Direction Mapping. This does not prevent forward progress but should be resolved during Phase 7 close-out or at the next requirements review.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | No TBD/FIXME/XXX markers; no stub returns; no empty handlers in phase-modified files |

### Human Verification Required

#### 1. FWD-feeds-inward on V2.2 hardware with direction_invert: True

**Test:** Add `direction_invert: True` to `[bmcu_channel 0]` in printer.cfg on a V2.2 BMCU unit. Issue `BMCU_DIR CHANNEL=0 DIR=FWD`. Observe motor direction.
**Expected:** Filament feeds inward (toward printer/toolhead) — the reversal that motivated this entire phase.
**Why human:** Motor polarity and physical wire routing cannot be inferred from code. The code correctly inverts the serial command, but whether that maps to "inward" vs "outward" depends on the physical motor wiring of each unit.

#### 2. Baseline behavior confirmation (direction_invert: False, V2.2 hardware)

**Test:** With `direction_invert` commented out (default False), issue `BMCU_DIR CHANNEL=0 DIR=FWD` on V2.2 hardware.
**Expected:** Filament ejects — confirming the uncorrected baseline that the option is designed to fix.
**Why human:** Same reason as above — hardware observation only.

### Gaps Summary

No code gaps. All must-haves verified against the codebase.

One documentation gap exists: REQUIREMENTS.md does not define DIR-INV-01 through DIR-INV-05. The v1.2 milestone has no requirements section. This is a bookkeeping deficit, not an implementation deficit — the feature works correctly in code and all tests pass.

---

_Verified: 2026-07-07_
_Verifier: Claude (gsd-verifier)_
