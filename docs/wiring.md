# Wiring

## Requirements

- BMCU 370C with **Type-C mainboard** (onboard CH340 USB-to-TTL chip)
- Sub-board V2 (Hall sensor version — the 370C, not the 370X photoelectric)
- USB-C cable (data-capable, not charge-only)
- 24V DC from your printer's PSU (via the 4-pin MX3.0 AMS connector)
- Klipper host (Raspberry Pi, BTT Pi, CB1, or any Linux SBC)

## Power

The BMCU runs on **24V DC**, supplied via the **4-pin MX3.0 AMS connector** on the mainboard. The onboard power circuit converts 24V down to 3.3V for the CH32 and all logic. Motors run directly off 24V (the 370 motor is rated 5–24V).

USB-C alone powers the CH32 and basic logic (the RGB LED goes blue), but **motors will not run without 24V on the AMS connector**.

### Connections

| Connection | Connector | Pins | Purpose |
|------------|-----------|------|---------|
| Power | 4-pin MX3.0 AMS connector | Pin 1 (24V), Pin 2 (GND) | 24V DC from printer PSU for motors and logic |
| Data | USB-C | — | Firmware communication (UART via CH340) |

Wire 24V and GND from your printer's PSU to pins 1 and 2 of the AMS connector. You can either modify the original BMCU AMS cable or make a custom cable with an MX3.0 plug. Pins 3–4 (RS485 Signal A/B) are unused — all communication goes over USB-C.

> **⚠ Do NOT use a Bambu AMS Lite cable** — the AMS Lite has a different pinout that reverses the signal and power pins.

### Bench testing without a Bambu printer

Connect 24V and GND from a bench PSU to the AMS connector pins (pins 1 and 2), plus USB-C for firmware communication. The 370 motor is rated 5–24V, so 12V works fine for bench testing.

### D4 diode warning

Some mainboard variants have a known issue with the **SS54 diode at position D4** that can cause unexpected reboots or damage the 24V-to-3.3V conversion circuit. The community recommendation is to **not solder this diode** and instead bridge the pads directly with copper wire or a resettable fuse. Check whether your board has this diode and if it has been patched.

### Schematics

Full KiCad schematics and Gerbers are on [OSHWhub](https://oshwhub.com/bamboo-shoot-xmcu-pcb-team/bmcu). The Type-C variant (@XC's board) is a separate design on the same platform.

## USB connection

Plug one end of the USB-C cable into the Type-C port on the BMCU mainboard and the other end into a free USB port on your Klipper host. No RS485 adapter, no ESP32 bridge, no additional wiring is required. The CH340 chip on the mainboard handles USB-to-serial conversion. Linux loads the `ch341` driver automatically on the first connection — no manual driver installation is needed.

## Verify connection

```bash
# With BMCU plugged in, check dmesg for CH340 detection:
dmesg | tail -5
# Look for: ch341-uart converter now attached to ttyUSBx

# Confirm the device exists:
ls /dev/serial/by-path/
# You should see a path like:
# platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0
```

Copy the full path shown by `ls /dev/serial/by-path/` — you will need it when configuring Klipper.

> **Note:** The BMCU Klipper extra requires a `/dev/serial/by-path/` path. Bare `/dev/ttyUSBx` paths change across reboots and will be rejected with a config error. See [klipper-install.md](klipper-install.md) for details.

## Confirmed hardware

| Kit | Mainboard | Status |
|-----|-----------|--------|
| BLV Kit B | Type-C | Confirmed working |
| Trianglelab Kit A | Type-C | Compatible (untested by maintainer) |

## Next step

[Flash the firmware](flashing.md)
