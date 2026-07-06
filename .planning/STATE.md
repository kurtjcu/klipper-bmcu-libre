---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Refinement & Compatibility
status: milestone_complete
stopped_at: ""
last_updated: "2026-05-02T00:00:00Z"
last_activity: 2026-05-02 -- v1.1 milestone complete
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 2
  completed_plans: 2
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-02)

**Core value:** Any BMCU 370C owner can plug it into their Klipper printer with a USB-C cable and get per-channel filament runout/blockage detection and feeder control — no BambuBus, no RS485 adapter, no ESP32 bridge.
**Current focus:** v1.1 complete — planning next milestone

## Current Position

Milestone: v1.1 Refinement & Compatibility — COMPLETE
Status: All phases shipped, milestone archived
Last activity: 2026-05-02 -- v1.1 milestone complete

```
v1.1 Progress: [██████████] 100% (2/2 phases) — SHIPPED
```

## Performance Metrics

**Velocity:**

- Total plans completed: 2 (v1.1)
- Average duration: 3min
- Total execution time: 6min

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 04-stall-detection-hardening | 1/1 | 3min | 3min |
| 05-feed-diagnostics | 1/1 | 3min | 3min |

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

### Research Flags (from research/SUMMARY.md)

- **Phase 4 (stall hardening):** stall_startup_ignore_polls default value (recommended: 2) needs empirical validation on hardware — motor acceleration at target PWM determines correct value
- **Phase 5 (diagnostics):** get_status() must return a fresh dict literal on every call; do not cache the dict between polls (Pitfall D from SUMMARY.md)
- **GEAR_CIRCUMFERENCE_MM:** Still a 30.0f placeholder — all stall thresholds and feed_mm values are systematically offset until physically measured and firmware rebuilt. Deferred to future CAL-01 requirement.

### Pending Todos

None yet.

### Blockers/Concerns

None currently active.

## Session Continuity

Last session: 2026-05-01
Stopped at: Completed 05-01-PLAN.md
Resume file: None
Next action: Phases 4 and 5 complete -- v1.1 milestone progress at 100% for stall hardening and feed diagnostics
