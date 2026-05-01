# bmcu-klipper-libre

A Klipper integration layer for the BMCU 370C, exposing a standard UART interface in place of BambuBus.

---

## What this is

The BMCU 370C is a 4-channel motorised filament feeder with per-channel AS5600 Hall sensor feedback, dual microswitches, and a capable CH32V203 MCU. It is sold as a Bambu AMS alternative but the hardware is well-suited to non-Bambu use cases.

This project replaces the BambuBus communication layer with a standard 8N1 UART interface exposed over the onboard Type-C USB port, and provides a Klipper extra to drive it. The CH32 motion control loop, PID tuning, and per-channel logic run unchanged — only the communication layer is replaced.

The target use case is a Voron V2.4 Tapchanger where each BMCU channel acts as a secondary feeder assist behind a primary extruder (Orbiter v2 + Galileo 2) on a ~500mm bowden run. This is not a multi-material/colour switching project — each channel simply feeds or doesn't, triggered by toolhead pick/drop events in Klipper.

---

## Why

The stock BMCU firmware and the existing community reimplementations all use BambuBus:

```
Baud:        1,250,000
Word length: 9-bit
Parity:      even
Interface:   RS485
```

Standard Linux UART (Raspberry Pi, CB1, BTT Pi) does not support 9-bit word length. This makes native Klipper integration impossible without additional hardware. This project solves that by replacing the communication layer in firmware with standard 8N1 UART, routed through the onboard CH340 USB-to-TTL chip present on Type-C mainboard variants.

No ESP32. No RS485 adapter. Just a USB-C cable between the BMCU and your Klipper host.

---

## Status

- [x] Hardware confirmed working (BLV Kit B, Type-C mainboard)
- [x] Standard UART firmware (`firmware/` — 8N1 over CH340 USB-C)
- [x] Klipper extra (`klippy/extras/bmcu_feeder.py`)
- [x] Generic config (`config/bmcu_generic.cfg`)
- [x] Buffer mode config for Tapchanger (`config/bmcu_buffer_tapchanger.cfg`)
- [x] Documentation (`docs/`)

---

## Quick start

1. **Flash firmware** — see [docs/flashing.md](docs/flashing.md)
2. **Install Klipper extra** — see [docs/klipper-install.md](docs/klipper-install.md)
3. **Configure** — see [docs/configuration.md](docs/configuration.md)

For Tapchanger buffer mode, also include `config/bmcu_buffer_tapchanger.cfg` — see [docs/configuration.md](docs/configuration.md#buffer-mode-tapchanger).

---

## Hardware requirements

- BMCU 370C with **Type-C mainboard** (onboard CH340) — required for USB-C direct connection
- Sub-board V2 (Hall sensor version) — this is the 370C, not the 370X photoelectric version
- USB-C cable to Klipper host
- No RS485 adapter, no ESP32 bridge

The BLV Kit B fully assembled unit with Type-C mainboard has been confirmed working. The Trianglelab Kit A with Type-C mainboard is also compatible.

---

## Architecture

```
Klipper (RPi / BTT Pi)
    |
    | USB-C  (115200 8N1)
    |
CH340 (onboard BMCU mainboard)
    |
CH32V203  (modified community firmware)
    |
4x independent channels:
    ├── 370 DC motor
    ├── AS5600 Hall sensor  (actual mm of filament fed)
    ├── Dual microswitches  (filament presence detection)
    └── PID loop            (runs autonomously per channel)
```

---

## Klipper interface

The Klipper extra exposes the following gcode commands:

| Command | Description |
|---|---|
| `BMCU_RUN CHANNEL=0` | Enable feeder on channel 0–3 |
| `BMCU_STOP CHANNEL=0` | Disable feeder on channel 0–3 |
| `BMCU_STATUS` | Report per-channel filament presence and motion state |
| `BMCU_SPEED CHANNEL=0 SPEED=50` | Set motor speed on channel 0–3 (0–100%) |
| `BMCU_DIR CHANNEL=0 DIR=REV` | Set motor direction on channel 0–3 (FWD/REV) |
| `SET_BMCU_SENSOR CHANNEL=0 ENABLE=0` | Disable/enable runout detection for channel 0–3 |

Runout detection on any active channel triggers a configurable Klipper pause macro.

---

## Firmware

This project forks the [jarczakpawel BMCU-C community firmware](https://github.com/jarczakpawel/BMCU-C-PJARCZAK) and modifies `BambuBus.cpp` to add a standard UART mode on the CH340 port alongside the existing BambuBus RS485 interface.

The fork lives in `/firmware` in this repo.

---

## Related projects

| Project | Description |
|---|---|
| [jarczakpawel/BMCU-C-PJARCZAK](https://github.com/jarczakpawel/BMCU-C-PJARCZAK) | Open source BMCU-C community firmware — base for this project |
| [MillionthOdin16/BMCU370t](https://github.com/MillionthOdin16/BMCU370t) | Alternative community firmware |
| [druckgott/bambulab_ams_diy_esp32](https://github.com/druckgott/bambulab_ams_diy_esp32) | ESP32 BMCU port — confirms BambuBus protocol is fully reversible |
| [ArmoredTurtle/AFC-Klipper-Add-On](https://github.com/ArmoredTurtle/AFC-Klipper-Add-On) | Multi-channel filament manager for Klipper — reference implementation |
| [viesturz/tapchanger](https://github.com/viesturz/tapchanger) | Voron Tapchanger — the toolchanger this was built for |
| [BMCU wiki](https://wiki.yuekai.fr/BMCU) | Community BMCU documentation |
| [BMCU protocol deep dive](https://deepwiki.com/karlingen/BMCU) | BambuBus protocol reverse engineering |

---

## Contributing

This is early-stage work. If you have a BMCU 370C and a non-Bambu printer, issues and PRs are welcome. The firmware fork in particular would benefit from testing across different mainboard revisions.

---

## License

Firmware modifications are subject to the upstream [jarczakpawel/BMCU-C-PJARCZAK](https://github.com/jarczakpawel/BMCU-C-PJARCZAK) license. Klipper extra and macros are MIT.
