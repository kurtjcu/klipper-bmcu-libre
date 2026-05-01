# Requirements: BMCU Klipper Libre

**Defined:** 2026-05-01
**Core Value:** Any BMCU 370C owner can plug it into their Klipper printer with a USB-C cable and get per-channel filament runout/blockage detection and feeder control — no BambuBus, no RS485 adapter, no ESP32 bridge.

## v1.1 Requirements

Requirements for v1.1 Refinement & Compatibility. Each maps to roadmap phases.

### Stall Detection

- [x] **STALL-01**: User can configure stall detection threshold (stall_threshold_mm) in printer.cfg
- [x] **STALL-02**: User can configure stall debounce count (consecutive polls below threshold before triggering) in printer.cfg
- [x] **STALL-03**: Stall detection ignores first N polls after motor start to prevent false positives
- [x] **STALL-04**: Stall detection resets previous-mm snapshot on direction change to prevent false triggers

### Feed Diagnostics

- [ ] **DIAG-01**: User can reset per-channel feed distance counter via BMCU_RESET_FEED GCode command
- [ ] **DIAG-02**: Per-channel feed_mm_since_reset is exposed via Moonraker get_status()
- [ ] **DIAG-03**: Per-channel cumulative stall_count is exposed via Moonraker get_status()

## Future Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Firmware Calibration

- **CAL-01**: GEAR_CIRCUMFERENCE_MM replaced with physically measured value in firmware

### Compatibility

- **COMPAT-01**: Happy Hare macro delegation shim (bmcu_hh_shim.cfg) calling MMU_PAUSE on runout/stall
- **COMPAT-02**: AFC macro delegation shim with appropriate pause macro
- **COMPAT-03**: Spoolman integration documentation (Moonraker [spoolman] config + spool-ID-per-tool workflow)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Native Happy Hare pre-gate sensor | HH expects GPIO pins; BMCU is USB serial — architectural mismatch |
| BMCU-to-Spoolman feed_mm bridge | Moonraker tracks extruder position natively; BMCU feed_mm is feeder-side and diverges |
| Motor PID tuning from Klipper | Stays on CH32 firmware; exposing it adds protocol complexity for no user value |
| OTA firmware updates | Enormous scope; document manual flash procedure |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| STALL-01 | Phase 4 | Complete |
| STALL-02 | Phase 4 | Complete |
| STALL-03 | Phase 4 | Complete |
| STALL-04 | Phase 4 | Complete |
| DIAG-01 | Phase 5 | Pending |
| DIAG-02 | Phase 5 | Pending |
| DIAG-03 | Phase 5 | Pending |

**Coverage:**
- v1.1 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0

---
*Requirements defined: 2026-05-01*
*Last updated: 2026-05-01 after roadmap creation*
