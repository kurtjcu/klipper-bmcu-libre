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

- [ ] Phase 6: Feed Distance Tracking (fix AS5600 polling — mm must accumulate during motor runs, not just on STATUS)
- [ ] Phase 7: Direction Mapping (FWD ejects on V2.2 — add direction_invert config or swap in firmware)
- [ ] Phase 8: Filament Sensor Investigation (fil= always 1 — identify V2.2 sensor type, fix ADC/GPIO mapping)
- [ ] Phase 9: All Channels Live (enable ch2→T2, ch3→T3, test all 4 under load)
- [ ] Phase 10: ENABLE Boot Timing (replace blocking sleep with faster handshake or auto-enable)
- [ ] Phase 11: Print Test (end-to-end print with BMCU buffer feeding on Tapchanger)

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Firmware | v1.0 | 3/3 | Complete | 2026-04-30 |
| 2. Klipper Extra | v1.0 | 4/4 | Complete | 2026-05-01 |
| 3. Buffer Mode and Docs | v1.0 | 2/2 | Complete | 2026-05-01 |
| 4. Stall Detection Hardening | v1.1 | 1/1 | Complete | 2026-05-01 |
| 5. Feed Diagnostics | v1.1 | 1/1 | Complete | 2026-05-01 |
| 6. Feed Distance Tracking | v1.2 | 0/1 | Planned | — |
| 7. Direction Mapping | v1.2 | 0/1 | Planned | — |
| 8. Filament Sensor Investigation | v1.2 | 0/1 | Planned | — |
| 9. All Channels Live | v1.2 | 0/1 | Planned | — |
| 10. ENABLE Boot Timing | v1.2 | 0/1 | Planned | — |
| 11. Print Test | v1.2 | 0/1 | Planned | — |
