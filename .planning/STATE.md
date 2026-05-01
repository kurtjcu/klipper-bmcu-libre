---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Refinement & Compatibility
status: executing
stopped_at: Roadmap created, ready to plan Phase 4
last_updated: "2026-05-01T03:12:53.823Z"
last_activity: 2026-05-01 -- Phase 5 planning complete
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 2
  completed_plans: 1
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-01)

**Core value:** Any BMCU 370C owner can plug it into their Klipper printer with a USB-C cable and get per-channel filament runout/blockage detection and feeder control — no BambuBus, no RS485 adapter, no ESP32 bridge.
**Current focus:** v1.1 Refinement & Compatibility — Phase 4: Stall Detection Hardening

## Current Position

Phase: 4 — Stall Detection Hardening
Plan: 1/1 complete
Status: Phase 4 complete, ready for Phase 5
Last activity: 2026-05-01 -- Phase 4 Plan 01 executed

```
v1.1 Progress: [█████░░░░░] 50% (1/2 phases)
```

## Performance Metrics

**Velocity:**

- Total plans completed: 1 (v1.1)
- Average duration: 3min
- Total execution time: 3min

**By Phase (v1.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 04-stall-detection-hardening | 1/1 | 3min | 3min |

**Recent Trend:**

- Last 5 plans: 04-01 (3min)
- Trend: baseline

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
- [v1.1 Phase 04-01]: get_status() stall_count exposure deferred to Phase 5 DIAG-03
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
Stopped at: Completed 04-01-PLAN.md
Resume file: None
Next action: Execute Phase 5 plans
