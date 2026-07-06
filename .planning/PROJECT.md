# BMCU Klipper Libre

## What This Is

An open-source firmware and Klipper integration for the BMCU 370C motorised filament feeder. Replaces the proprietary BambuBus communication layer with standard 8N1 UART over the onboard CH340 USB-to-TTL chip, enabling native Klipper integration via a single USB-C cable. Provides a generic Klipper extra for any printer, plus an opinionated buffer-mode configuration for toolchanger setups.

## Core Value

Any BMCU 370C owner can plug it into their Klipper printer with a USB-C cable and get per-channel filament runout/blockage detection and feeder control — no BambuBus, no RS485 adapter, no ESP32 bridge.

## Current State

Shipped v1.1 (Refinement & Compatibility) on 2026-05-02. Stall detection hardened with configurable thresholds, debounce, startup grace, and direction-change suppression. Feed diagnostics (feed_mm_since_reset, stall_count) exposed via Moonraker get_status() with BMCU_RESET_FEED command for per-job counter zeroing.

**Next milestone:** Not yet planned. Candidates: Happy Hare / AFC compatibility, Spoolman docs, GEAR_CIRCUMFERENCE_MM calibration, code review fixes.

## Requirements

### Validated

- ✓ Firmware: 8N1 UART protocol over CH340 USB-C replacing BambuBus — v1.0
- ✓ Firmware: Bidirectional command/response protocol (STATUS, RUN, STOP, SPEED, DIR) — v1.0
- ✓ Firmware: Per-channel filament presence, motor state, AS5600 motion, feed distance reporting — v1.0
- ✓ Klipper extra: Generic bmcu_feeder module with non-blocking reactor I/O — v1.0
- ✓ Klipper extra: GCode commands (BMCU_RUN, BMCU_STOP, BMCU_STATUS, BMCU_SPEED, BMCU_DIR, SET_BMCU_SENSOR) — v1.0
- ✓ Klipper extra: Configurable runout/insert/stall event macros with debounce — v1.0
- ✓ Klipper extra: Moonraker get_status() for Mainsail/Fluidd visibility — v1.0
- ✓ Klipper extra: Configurable stall detection thresholds (stall_threshold_mm, stall_debounce_count, stall_startup_ignore_polls) — v1.1
- ✓ Klipper extra: Direction-change stall suppression — v1.1
- ✓ Klipper extra: Per-channel feed_mm_since_reset and stall_count via Moonraker — v1.1
- ✓ Klipper extra: BMCU_RESET_FEED GCode command with optional CHANNEL parameter — v1.1
- ✓ Klipper extra: Serial disconnect handling with optional runout trigger — v1.0
- ✓ Buffer mode: Tapchanger toolchange integration (pick/drop/sensor suppression) — v1.0
- ✓ Docs: Complete user path from wiring to working BMCU_STATUS — v1.0

### Active

- [ ] Spoolman integration documentation
- [ ] Happy Hare / AFC compatibility layer
- [ ] GEAR_CIRCUMFERENCE_MM calibration on physical hardware (placeholder 30.0f)
- [ ] Fix _check_events early-return skipping state bookkeeping (CR-01)
- [ ] Fix _poll_status null dereference on disconnect race (CR-02)

### Out of Scope

- BambuBus compatibility — replaced entirely, standard Linux UART doesn't support 9-bit word length
- Multi-material/colour switching — each channel feeds or doesn't; tool selection stays in slicer/toolchanger
- ESP32 bridge — USB-C direct only
- RS485 adapter support — not needed with CH340
- Motor PID tuning from Klipper — stays on CH32 firmware; exposing it adds protocol complexity for no user value
- Mobile app or web UI — Klipper's existing interfaces (Mainsail/Fluidd/KlipperScreen) suffice
- OTA firmware updates — enormous scope; document manual flash procedure
- Auto-detect channel count — Klipper convention is explicit static config

## Context

Shipped v1.1 with ~2,466 LOC across firmware (C++), Klipper extra (Python), configs, and docs. v1.1 added 1,008 lines over v1.0.

Tech stack:
- **Firmware:** CH32V203 (RISC-V), WCH nonos-sdk, PlatformIO, USART1 8N1 at 115200 baud
- **Klipper extra:** Python, pyserial, Klipper reactor fd-watching (no threads)
- **Configs:** Klipper .cfg with Jinja2 macros for Tapchanger integration
- **Tests:** pytest (62 unit tests), hardware test harness (test_protocol.py)

Hardware confirmed on BLV Kit B (Type-C mainboard). Trianglelab Kit A compatible (untested by maintainer).

Upstream fork: [jarczakpawel/BMCU-C-PJARCZAK](https://github.com/jarczakpawel/BMCU-C-PJARCZAK)

Known issue: GEAR_CIRCUMFERENCE_MM is a 30.0f placeholder — needs physical measurement for accurate feed distance.

## Constraints

- **Hardware**: Type-C mainboard variant required (has CH340). Non-USB mainboards are not supported.
- **Firmware platform**: CH32V203 — toolchain is MounRiver Studio or GCC with WCH extensions.
- **Klipper integration**: Must follow Klipper extras conventions (`klippy/extras/`). No kernel modules, no custom serial daemons.
- **Protocol**: Standard 8N1 UART at 115200 baud. Must work reliably over USB-C cable lengths typical in printer enclosures.
- **Upstream license**: Firmware modifications subject to upstream jarczakpawel/BMCU-C-PJARCZAK license. Klipper extra and macros are MIT.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Replace BambuBus entirely (no dual mode) | Standard Linux UART doesn't support 9-bit word length; dual mode adds complexity for no benefit since target users are non-Bambu | ✓ Good — clean separation, no legacy code paths |
| Static channel-to-toolhead mapping in printer.cfg | Simpler, predictable, matches how Klipper configures other peripherals | ✓ Good — standard Klipper convention |
| Two-layer Klipper code: generic extra + buffer mode config | Generic layer enables community adoption; buffer mode serves the specific Tapchanger use case without polluting the base module | ✓ Good — zero Python changes needed for buffer mode |
| Configurable event macros (not hardcoded pause) | Users have different workflows — some want pause, some want cancel, some want custom recovery | ✓ Good — follows filament_switch_sensor pattern |
| USART1 (PA9/PA10) for protocol, not USART2 | USART1 routes to CH340 TX/RX on Type-C mainboard; USART2 does not connect to USB | ✓ Good — discovered during hardware bring-up |
| Motor control via Motion_control_set_PWM directly | ams_state_set_loaded/unloaded are flash-persistence helpers, not motor drivers | ✓ Good — correct API for real-time motor control |
| Reactor register_fd for serial I/O (no threads) | Klipper issue #2187: background threads cause reactor.monotonic() warnings | ✓ Good — zero reactor warnings in testing |
| Symlink install (not copy) | Survives Klipper updates; Moonraker update_manager re-runs install.sh | ✓ Good — standard pattern for Klipper addons |
| Debounce default 3 polls (1.5s) | Balances false-positive prevention with detection latency | ✓ Good — empirically tuned for typical print speeds |
| Startup grace default 2 polls (1.0s) | Motor acceleration produces zero/low delta that would trigger stall | ✓ Good — eliminates all motor-start false positives |
| Direction-change flag (not snapshot skip) | Skipping one poll without resetting _prev_mm avoids both false stall and missed real stall | ✓ Good — single poll gap is minimal |
| Signed feed_mm_since_reset (not absolute) | Matches firmware encoder semantics; more informative for debugging | ✓ Good — users can see net direction |
| BMCU_RESET_FEED resets both feed + stall count | Single command for START_PRINT macro; avoids split-reset confusion | ✓ Good — simpler UX |
| First-poll snapshot for feed_mm_at_reset | Firmware may report accumulated encoder value on reconnect | ✓ Good — feed_mm_since_reset starts at 0.0 regardless |

---
*Last updated: 2026-05-02 after v1.1 milestone*
