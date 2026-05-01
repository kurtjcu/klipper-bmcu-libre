# Roadmap: BMCU Klipper Libre

## Milestones

- ✅ **v1.0 MVP** — Phases 1-3 (shipped 2026-05-01)
- 🚧 **v1.1 Refinement & Compatibility** — Phases 4-5 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-3) — SHIPPED 2026-05-01</summary>

- [x] Phase 1: Firmware (3/3 plans) — 8N1 UART protocol on CH32V203
- [x] Phase 2: Klipper Extra (4/4 plans) — bmcu_feeder module with GCode commands, events, Moonraker
- [x] Phase 3: Buffer Mode and Docs (2/2 plans) — Tapchanger config + end-user documentation

</details>

### 🚧 v1.1 Refinement & Compatibility (In Progress)

**Milestone Goal:** Harden stall detection to eliminate false positives, expose feed and stall diagnostics via Moonraker, and deliver macro-delegation compatibility for Happy Hare / AFC and Spoolman documentation.

- [x] **Phase 4: Stall Detection Hardening** — Configurable thresholds and false-positive fixes (completed 2026-05-01)
- [x] **Phase 5: Feed Diagnostics** — Per-channel feed distance and stall count via Moonraker (completed 2026-05-01)

## Phase Details

### Phase 4: Stall Detection Hardening
**Goal**: Users can configure stall detection sensitivity in printer.cfg and stall events fire only on genuine blockages, not at motor start or on direction changes
**Depends on**: Phase 3 (v1.0 complete)
**Requirements**: STALL-01, STALL-02, STALL-03, STALL-04
**Success Criteria** (what must be TRUE):
  1. User can set `stall_threshold_mm` in `[bmcu_channel]` config and stall fires only when feed delta falls below that value for the configured number of consecutive polls
  2. User can set `stall_debounce_count` in `[bmcu_channel]` config and a single below-threshold poll does not trigger a stall macro
  3. Stall macro does not fire on the first N polls after motor start, even when feed delta is zero (startup grace window active)
  4. Reversing motor direction (BMCU_DIR) resets the stall comparison snapshot so the direction change itself does not trigger a stall
**Plans:** 1 plan
Plans:
- [x] 04-01-PLAN.md — Debounced stall detection with startup grace window and direction-change reset

### Phase 5: Feed Diagnostics
**Goal**: Users can monitor per-channel feed distance and cumulative stall count from Mainsail/Fluidd and reset the feed counter between jobs
**Depends on**: Phase 4
**Requirements**: DIAG-01, DIAG-02, DIAG-03
**Success Criteria** (what must be TRUE):
  1. User can run `BMCU_RESET_FEED` (optionally with `CHANNEL=n`) to zero the feed distance counter for one or all channels
  2. `feed_mm_since_reset` for each channel is visible in the Moonraker objects panel and updates while the motor runs
  3. `stall_count` for each channel is visible in the Moonraker objects panel and increments only when the debounced stall logic fires
**Plans:** 1 plan
Plans:
- [x] 05-01-PLAN.md — Feed diagnostics: counters, BMCU_RESET_FEED command, get_status exposure

## Progress

**Execution Order:**
Phases execute in numeric order: 4 → 5

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Firmware | v1.0 | 3/3 | Complete | 2026-04-30 |
| 2. Klipper Extra | v1.0 | 4/4 | Complete | 2026-05-01 |
| 3. Buffer Mode and Docs | v1.0 | 2/2 | Complete | 2026-05-01 |
| 4. Stall Detection Hardening | v1.1 | 1/1 | Complete | 2026-05-01 |
| 5. Feed Diagnostics | v1.1 | 1/1 | Complete | 2026-05-01 |
