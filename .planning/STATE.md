---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Hardware Validation & V2.2 Compatibility
status: executing
stopped_at: Phase 10 Plan 01 complete
last_updated: "2026-07-07T00:00:00.000Z"
last_activity: 2026-07-07
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 3
  completed_plans: 3
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-02)

**Core value:** Any BMCU 370C owner can plug it into their Klipper printer with a USB-C cable and get per-channel filament runout/blockage detection and feeder control — no BambuBus, no RS485 adapter, no ESP32 bridge.
**Current focus:** Phase 07 — direction-mapping

## Current Position

Phase: 10
Plan: 01 complete
Milestone: v1.2 Hardware Validation & V2.2 Compatibility
Status: Phase 10 complete
Last activity: 2026-07-16 - Completed quick task 260716-hn6: drift-aware stall detection

```
v1.1 Progress: [██████████] 100% (2/2 phases) — SHIPPED
```

## Performance Metrics

**Velocity:**

- Total plans completed: 5 (v1.1)
- Average duration: 3min
- Total execution time: 6min

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 04-stall-detection-hardening | 1/1 | 3min | 3min |
| 05-feed-diagnostics | 1/1 | 3min | 3min |
| 06 | 2 | - | - |
| 07 | 1 | - | - |

**Recent Trend:**

- Last 5 plans: 04-01 (3min), 05-01 (3min)
- Trend: consistent

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.0 Phase 01-firmware]: GEAR_CIRCUMFERENCE_MM defined as #ifndef-guarded 30.0f placeholder — actual gear circumference requires physical measurement on BMCU 370C hardware
- [v1.0 Phase 02-klipper-extra]: Stall detection skips first _prev_mm observation to prevent false-positive on startup (partial fix; v1.1 Phase 4 hardens this with a configurable grace window and debounce counter)
- [v1.1 Phase 04-01]: Debounce default 3 polls (1.5s) balances false-positive prevention with detection latency
- [v1.1 Phase 04-01]: Startup grace default 2 polls (1.0s) for motor acceleration; tunable per-user
- [v1.1 Phase 04-01]: Direction-change uses _direction_just_changed flag to skip one poll without losing _prev_mm snapshot
- [v1.1 Phase 04-01]: get_status() stall_count exposure deferred to Phase 5 DIAG-03 -- RESOLVED in 05-01
- [v1.1 Phase 05-01]: feed_mm_since_reset is signed (not absolute) -- matches firmware encoder semantics
- [v1.1 Phase 05-01]: BMCU_RESET_FEED resets both feed distance and stall count -- single command for START_PRINT macro
- [v1.1 Phase 05-01]: First-poll initialization sets _feed_mm_at_reset to firmware value so feed_mm_since_reset starts at 0.0
- [v1.0 Phase 02-klipper-extra]: reactor.register_fd with timeout=0 for serial I/O — no background threads (Klipper issue #2187)
- [v1.0 Phase 02-klipper-extra]: Motor RUN/STOP use Motion_control_set_PWM directly, not ams_state_set_loaded
- [v1.2 Phase 10-01]: BOOT wait uses _time.monotonic() deadline (5s) with break on empty readline — no sleep(2) or reset_input_buffer()
- [v1.2 Phase 10-01]: ENABLE retry uses for/else idiom; raises Exception after 3 failures to halt Klipper startup cleanly
- [v1.2 Phase 10-01]: _cmd_enable() sets timeout=2 temporarily, reads/echoes response, restores timeout=0

### Research Flags (from research/SUMMARY.md)

- **Phase 4 (stall hardening):** stall_startup_ignore_polls default value (recommended: 2) needs empirical validation on hardware — motor acceleration at target PWM determines correct value
- **Phase 5 (diagnostics):** get_status() must return a fresh dict literal on every call; do not cache the dict between polls (Pitfall D from SUMMARY.md)
- **GEAR_CIRCUMFERENCE_MM:** Still a 30.0f placeholder — all stall thresholds and feed_mm values are systematically offset until physically measured and firmware rebuilt. Deferred to future CAL-01 requirement.

### Pending Todos

None yet.

### Blockers/Concerns

None currently active.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260716-gto | Add console reporting when the print pauses (runout, stall, serial error) | 2026-07-16 | cdd1385 | [260716-gto-add-reporting-when-it-pauses-the-print-c](./quick/260716-gto-add-reporting-when-it-pauses-the-print-c/) |
| 260716-hn6 | Drift-aware stall detection (commanded-vs-measured slip ratio) + fixed stall reporting | 2026-07-16 | 6992447 | [260716-hn6-drift-aware-bmcu-stall-detection-compare](./quick/260716-hn6-drift-aware-bmcu-stall-detection-compare/) |

## Session Continuity

Last session: 2026-07-07T00:00:00.000Z
Stopped at: Phase 10 Plan 01 complete
Resume file: None
Next action: Phase 10 complete — BOOT-driven handshake implemented and tested
