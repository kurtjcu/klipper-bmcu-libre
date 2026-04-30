# BMCU Klipper Libre

## What This Is

An open-source firmware and Klipper integration for the BMCU 370C motorised filament feeder. Replaces the proprietary BambuBus communication layer with standard 8N1 UART over the onboard CH340 USB-to-TTL chip, enabling native Klipper integration via a single USB-C cable. Provides a generic Klipper extra for any printer, plus an opinionated buffer-mode configuration for toolchanger setups.

## Core Value

Any BMCU 370C owner can plug it into their Klipper printer with a USB-C cable and get per-channel filament runout/blockage detection and feeder control — no BambuBus, no RS485 adapter, no ESP32 bridge.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Firmware: Replace BambuBus with 8N1 UART over CH340 USB-C
- [ ] Firmware: Bidirectional protocol — Klipper sends commands, BMCU reports status
- [ ] Firmware: Report filament presence per channel (microswitches)
- [ ] Firmware: Report motion/stall state per channel (AS5600 Hall sensor)
- [ ] Firmware: Report actual feed distance in mm per channel (AS5600 encoder)
- [ ] Firmware: Report motor state per channel (running, stopped, speed, direction)
- [ ] Firmware: Accept run/stop commands per channel
- [ ] Firmware: Accept speed and direction commands per channel
- [ ] Firmware: Accept status query command
- [ ] Klipper extra: Generic `bmcu_feeder` module — not tied to any toolchanger
- [ ] Klipper extra: Static channel-to-toolhead mapping in printer.cfg
- [ ] Klipper extra: Configurable event macros for runout/blockage/stall
- [ ] Klipper extra: BMCU_RUN / BMCU_STOP / BMCU_STATUS gcode commands
- [ ] Klipper extra: Query and display per-channel status
- [ ] Buffer mode: Opinionated config for toolchanger filament buffer use case
- [ ] Buffer mode: Channel activated/deactivated on tool pick/drop events
- [ ] Docs: Wiring guide (USB-C from BMCU to RPi)
- [ ] Docs: Firmware flashing instructions
- [ ] Docs: Klipper installation and configuration guide
- [ ] Docs: Example printer.cfg snippets

### Out of Scope

- BambuBus compatibility — replaced entirely, not dual-mode
- Multi-material/colour switching — each channel feeds or doesn't
- ESP32 bridge — USB-C direct only
- RS485 adapter support — not needed with CH340
- Motor PID tuning from Klipper — stays on CH32 firmware
- Mobile app or web UI — Klipper's existing interfaces suffice

## Context

- The BMCU 370C hardware has a CH32V203 MCU running a PID-controlled motor loop per channel. The motion control, PID tuning, and per-channel logic are mature and run autonomously on the MCU — Klipper acts as supervisor, not motor controller.
- The onboard CH340 USB-to-TTL chip on Type-C mainboard variants provides the physical serial bridge. Klipper sees it as a standard `/dev/ttyUSB*` or `/dev/ttyACM*` device.
- Upstream firmware: [jarczakpawel/BMCU-C-PJARCZAK](https://github.com/jarczakpawel/BMCU-C-PJARCZAK) — the community firmware this project forks.
- Hardware confirmed working on BLV Kit B (Type-C mainboard). Trianglelab Kit A (Type-C) also compatible.
- Target use case: Voron V2.4 Tapchanger with 4 toolheads, each with an Orbiter v2 + Galileo 2 primary extruder on ~500mm bowden. BMCU channel per head acts as secondary feeder assist / filament buffer.
- The generic Klipper layer must be printer-agnostic so the community can use it for any setup — standalone feeder, buffer, runout sensor, etc.

## Constraints

- **Hardware**: Type-C mainboard variant required (has CH340). Non-USB mainboards are not supported.
- **Firmware platform**: CH32V203 — toolchain is MounRiver Studio or GCC with WCH extensions.
- **Klipper integration**: Must follow Klipper extras conventions (`klippy/extras/`). No kernel modules, no custom serial daemons.
- **Protocol**: Standard 8N1 UART at a sensible baud rate (115200 or similar). Must work reliably over USB-C cable lengths typical in printer enclosures.
- **Upstream license**: Firmware modifications subject to upstream jarczakpawel/BMCU-C-PJARCZAK license. Klipper extra and macros are MIT.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Replace BambuBus entirely (no dual mode) | Standard Linux UART doesn't support 9-bit word length; dual mode adds complexity for no benefit since target users are non-Bambu | — Pending |
| Static channel-to-toolhead mapping in printer.cfg | Simpler, predictable, matches how Klipper configures other peripherals | — Pending |
| Two-layer Klipper code: generic extra + buffer mode config | Generic layer enables community adoption; buffer mode serves the specific Tapchanger use case without polluting the base module | — Pending |
| Configurable event macros (not hardcoded pause) | Users have different workflows — some want pause, some want cancel, some want custom recovery | — Pending |

---
*Last updated: 2026-05-01 after initialization*
