# PRD: BMCU 370C as Klipper Filament Feeder Assist — Voron V2.4 Tapchanger

## Overview

Repurpose a BMCU 370C (BLV Kit B, fully assembled) as a 4-channel motorised filament feeder assist for a Voron V2.4 Tapchanger. Each channel serves one independent toolhead over a ~500mm PTFE bowden run, acting as a secondary feeder behind an Orbiter v2 + Galileo 2 primary extruder.

This is **not** a multi-material/colour switching project. No filament hub. No AMS handoff logic. Each channel simply feeds or doesn't.

---

## Hardware

| Item | Detail |
|---|---|
| BMCU unit | BLV Kit B — 370C, Hall sensor, fully assembled |
| MCU | CH32V203 (RISC-V, 144MHz) |
| Channels | 4 independent — each has 370 DC motor + AS5600 Hall sensor + dual microswitches |
| Mainboard | Type-C version — onboard CH340 USB-to-TTL |
| Host | Raspberry Pi / BTT Pi running Klipper |
| Toolheads | 4x Dragon Burner on Tapchanger, Orbiter v2 + Galileo 2 extruders |

---

## The Problem

The BambuBus UART config used by stock and community firmware is:

```
Baud:        1,250,000
Word length: 9-bit
Parity:      even
Interface:   RS485
```

Standard Linux UART (RPi / CB1 / BTT Pi) does not support 9-bit word length. This is the single biggest blocker to native Klipper integration. An ESP32 bridge can work around it but adds hardware complexity.

---

## Quickest Path Forward

### Step 1 — Flash community firmware

Flash the jarczakpawel BMCU-C community firmware. This is an open-source reimplementation of the closed official BMCU-C firmware — fully functional, actively maintained.

**Repo:** https://github.com/jarczakpawel/BMCU-C-PJARCZAK

Flashing uses the onboard Type-C CH340 — just plug in a USB-C cable, no external adapter needed.

**Flashing reference:**
- https://wiki.yuekai.fr/BMCU/BMCU_Tutorial/BMCU_Flashing
- https://neo.bttwiki.com/en/docs/panda-series/module/bmcu370/

### Step 2 — Add standard UART mode to firmware

Modify `BambuBus.cpp` in the community firmware to expose a secondary UART on the CH340 USB-C port using standard settings:

```
Baud:        115200
Word length: 8-bit
Parity:      none (8N1)
```

The existing motion control PID loop and per-channel logic runs unchanged on the CH32. The new UART mode just replaces the heartbeat/enable signal — Klipper tells it to run, the CH32 does the rest autonomously.

Minimal command set needed:

| Command | Description |
|---|---|
| `RUN <ch>` | Enable motor on channel 0–3 |
| `STOP <ch>` | Disable motor on channel 0–3 |
| `STATUS` | Return per-channel filament presence + motion state |

### Step 3 — Write Klipper plugin

A simple Klipper extra (`bmcu_feeder.py`) that:

- Opens the USB serial port to the BMCU at startup
- Sends `RUN <ch>` when a toolhead is picked
- Sends `STOP <ch>` when a toolhead is dropped
- Polls `STATUS` for runout/jam detection per channel
- Exposes `BMCU_RUN`, `BMCU_STOP`, `BMCU_STATUS` gcode macros

**Reference repos:**
- Klipper extras examples: https://github.com/Klipper3d/klipper/tree/master/klippy/extras
- AFC Klipper Add-On (multi-channel filament manager, reference implementation): https://github.com/ArmoredTurtle/AFC-Klipper-Add-On
- Belay by Annex (single-channel sync extruder, Klipper native): https://github.com/Annex-Engineering/Belay

---

## Architecture

```
Klipper (RPi)
    |
    | USB-C (115200 8N1 — standard serial, no extra hardware)
    |
CH340 (onboard BMCU mainboard)
    |
CH32V203 (community firmware, modified BambuBus.cpp)
    |
4x independent channels:
    - 370 DC motor
    - AS5600 Hall sensor (actual mm feedback)
    - Dual microswitches (filament presence)
    - PID loop running autonomously
```

No ESP32. No RS485 adapter. Just a USB-C cable.

---

## Success Criteria

- [ ] Community firmware flashed and running
- [ ] BMCU responds to manual buffer arm press (test mode)
- [ ] Standard UART mode implemented in firmware fork
- [ ] Klipper sees BMCU as a serial device at boot
- [ ] `BMCU_RUN 0` and `BMCU_STOP 0` commands work from Klipper console
- [ ] Per-channel status readable from Klipper
- [ ] Runout detection triggers Klipper pause macro
- [ ] All 4 channels running reliably under print conditions

---

## Related Work

- Community firmware (jarczakpawel): https://github.com/jarczakpawel/BMCU-C-PJARCZAK
- Alternative community firmware (MillionthOdin16): https://github.com/MillionthOdin16/BMCU370t
- ESP32 BMCU port (confirms ESP32 handles BambuBus fine): https://github.com/druckgott/bambulab_ams_diy_esp32
- BMCU protocol deep dive: https://deepwiki.com/karlingen/BMCU
- BMCU wiki: https://wiki.yuekai.fr/BMCU
- High torque STLs (MakerWorld): https://makerworld.com/en/models/1412302
- Voron Tapchanger: https://github.com/viesturz/tapchanger

---

## Notes

- The jarczakpawel firmware developer is actively fundraising to build Klipper support — worth tracking and contributing to: https://github.com/jarczakpawel/BMCU-C-PJARCZAK
- GitHub issue filed against that repo proposing the standard UART approach
- No one has done BMCU + Klipper + Tapchanger feeder assist before — this is novel territory
