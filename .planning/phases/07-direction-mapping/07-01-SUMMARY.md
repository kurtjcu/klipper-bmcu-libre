---
phase: 07-direction-mapping
plan: "01"
subsystem: klipper-extra
tags: [direction-invert, config, tdd, v2.2-compatibility]
dependency_graph:
  requires: []
  provides: [direction_invert config option, FWD/REV inversion in _cmd_dir]
  affects: [klippy/extras/bmcu_feeder.py, tests/test_bmcu_feeder.py, config/bmcu_generic.cfg, config/bmcu_buffer_tapchanger.cfg]
tech_stack:
  added: []
  patterns: [config.getboolean with default False, wire_dir conditional inversion]
key_files:
  created: []
  modified:
    - klippy/extras/bmcu_feeder.py
    - tests/test_bmcu_feeder.py
    - config/bmcu_generic.cfg
    - config/bmcu_buffer_tapchanger.cfg
decisions:
  - direction_invert applied at _cmd_dir send time only — STATUS dir= stored raw to preserve stall detection direction-change comparison
  - Default False means no behavior change for existing users
metrics:
  duration: "14min"
  completed: "2026-07-07"
  tasks_completed: 2
  files_modified: 4
---

# Phase 07 Plan 01: Direction Invert Config Option Summary

**One-liner:** Per-channel direction_invert boolean config swaps FWD/REV in _cmd_dir for V2.2 reversed motor wiring, with 5 TDD tests and config file documentation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing direction_invert tests | 6edf3e6 | tests/test_bmcu_feeder.py |
| 1 (GREEN) | Implement direction_invert config + _cmd_dir inversion | 66f7c1b | klippy/extras/bmcu_feeder.py |
| 2 | Document direction_invert in config files | 4ad5c60 | config/bmcu_generic.cfg, config/bmcu_buffer_tapchanger.cfg |

## What Was Built

### BmcuChannel.direction_invert

Added `self.direction_invert = config.getboolean('direction_invert', False)` to `BmcuChannel.__init__` immediately after `self.pause_on_runout`. Defaults to `False` — no behavior change for existing users.

### _cmd_dir inversion logic

Modified `BmcuFeeder._cmd_dir` to look up the channel object and apply inversion:

```python
ch = self._channels[ch_id]
if ch.direction_invert:
    wire_dir = 'REV' if direction == 'FWD' else 'FWD'
else:
    wire_dir = direction
self._serial.send("DIR %d %s\n" % (ch_id, wire_dir))
```

`_dispatch_status_line` is unchanged — `STATUS dir=` is stored raw as the firmware value to preserve correct direction-change stall suppression in `_check_events`.

### TestDirectionInvert (5 tests)

- `test_fwd_inverted_sends_rev`: FWD -> REV on wire when direction_invert=True
- `test_fwd_not_inverted_sends_fwd`: FWD -> FWD on wire when direction_invert=False
- `test_rev_inverted_sends_fwd`: REV -> FWD on wire when direction_invert=True
- `test_status_dir_stored_raw`: STATUS dir=REV stored as 'REV' even when direction_invert=True
- `test_channel_direction_invert_config`: config parsing, True value and default False

### Config documentation

`config/bmcu_generic.cfg`: Added 2-line block (comment + commented option) in each of [bmcu_channel 0] and [bmcu_channel 1] after `stall_startup_ignore_polls`.

`config/bmcu_buffer_tapchanger.cfg`: Added note in header that per-channel options like direction_invert belong in bmcu_generic.cfg.

## Verification Results

- python -m pytest tests/test_bmcu_feeder.py::TestDirectionInvert: 5/5 passed
- python -m pytest tests/: 71/71 passed (full suite green)
- grep -v '^#' bmcu_feeder.py | grep -c 'direction_invert': 2 (BmcuChannel.__init__ + _cmd_dir)
- grep -c 'direction_invert' bmcu_generic.cfg: 4 (2 comment + 2 option lines)
- grep -c 'direction_invert' bmcu_buffer_tapchanger.cfg: 1

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Inversion only in _cmd_dir (not _dispatch_status_line) | STATUS dir= is firmware-reported value used for direction-change stall suppression in _check_events — inverting it would break stall detection |
| Default False | No behavior change for existing users; opt-in only |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None. No new trust boundaries — direction_invert is a config-time boolean parsed by Klipper's config system with safe default False. Serial protocol and firmware unchanged.

## TDD Gate Compliance

- RED gate: commit 6edf3e6 `test(07-01): add failing tests for direction_invert config option`
- GREEN gate: commit 66f7c1b `feat(07-01): add direction_invert config option to BmcuChannel`
- REFACTOR gate: not needed (implementation was clean)

## Self-Check: PASSED

- klippy/extras/bmcu_feeder.py: FOUND
- tests/test_bmcu_feeder.py: FOUND (class TestDirectionInvert with 5 test methods)
- config/bmcu_generic.cfg: FOUND (4 direction_invert lines)
- config/bmcu_buffer_tapchanger.cfg: FOUND (1 direction_invert line)
- Commits 6edf3e6, 66f7c1b, 4ad5c60: all present in git log
