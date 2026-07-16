# Roadmap: BMCU Klipper Libre

## Milestones

- ✅ **v1.0 MVP** — Phases 1-3 (shipped 2026-05-01)
- ✅ **v1.1 Refinement & Compatibility** — Phases 4-5 (shipped 2026-05-02)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-3) — SHIPPED 2026-05-01</summary>

- [x] Phase 1: Firmware (3/3 plans) — 8N1 UART protocol on CH32V203
- [x] Phase 2: Klipper Extra (4/4 plans) — bmcu_feeder module with GCode commands, events, Moonraker
- [x] Phase 3: Buffer Mode and Docs (2/2 plans) — Tapchanger config + end-user documentation

</details>

<details>
<summary>✅ v1.1 Refinement & Compatibility (Phases 4-5) — SHIPPED 2026-05-02</summary>

- [x] Phase 4: Stall Detection Hardening (1/1 plans) — Configurable thresholds and false-positive fixes (completed 2026-05-01)
- [x] Phase 5: Feed Diagnostics (1/1 plans) — Per-channel feed distance and stall count via Moonraker (completed 2026-05-01)

</details>

### v1.2 Hardware Validation & V2.2 Compatibility

<details>
<summary>✅ Phase 6 (completed 2026-07-07)</summary>

- [x] Phase 6: Feed Distance Tracking (2/2 plans) — fix AS5600 polling, mm accumulation during motor runs
  - [x] 06-01-PLAN.md — Firmware fix (wrap correction, magnet guard, tick-level accumulation) + MockSerial fixture fix
  - [x] 06-02-PLAN.md — Pytest feed accumulation tests + hardware integration test

</details>

### Phase 7: Direction Mapping

**Goal:** FWD command currently ejects filament on V2.2 hardware — add direction_invert config option or swap direction in firmware so FWD feeds inward.
**Plans:** 1/1 plans complete

Plans:

- [x] 07-01-PLAN.md — Add direction_invert config option, _cmd_dir inversion, tests, config docs

<details>
<summary>✅ Phase 8 (completed 2026-07-07)</summary>

- [x] Phase 8: Filament Sensor Investigation — fil= sensor working correctly on V2.2 hardware (resolved during hardware testing, no code changes needed)

</details>

<details>
<summary>✅ Phase 10 (completed 2026-07-07)</summary>

- [x] Phase 10: ENABLE Boot Timing — BOOT-driven handshake with 5s deadline + 3-attempt ENABLE retry replacing sleep(2)/sleep(5)
  - [x] 10-01-PLAN.md — Rewrite connect() for BOOT wait + ENABLE retry, simplify _cmd_enable(), add 6 tests

</details>

### Phase 11: Print Test

**Goal:** End-to-end print with BMCU buffer feeding on Tapchanger — validate full workflow.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Firmware | v1.0 | 3/3 | Complete | 2026-04-30 |
| 2. Klipper Extra | v1.0 | 4/4 | Complete | 2026-05-01 |
| 3. Buffer Mode and Docs | v1.0 | 2/2 | Complete | 2026-05-01 |
| 4. Stall Detection Hardening | v1.1 | 1/1 | Complete | 2026-05-01 |
| 5. Feed Diagnostics | v1.1 | 1/1 | Complete | 2026-05-01 |
| 6. Feed Distance Tracking | v1.2 | 2/2 | Complete    | 2026-07-07 |
| 7. Direction Mapping | v1.2 | 1/1 | Complete    | 2026-07-07 |
| 8. Filament Sensor Investigation | v1.2 | 0/0 | Complete | 2026-07-07 |
| 10. ENABLE Boot Timing | v1.2 | 1/1 | Complete | 2026-07-07 |
| 11. Print Test | v1.2 | 0/1 | Planned | — |
