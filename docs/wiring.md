# Wiring

## Requirements

- BMCU 370C with **Type-C mainboard** (onboard CH340 USB-to-TTL chip)
- Sub-board V2 (Hall sensor version — the 370C, not the 370X photoelectric)
- USB-C cable (data-capable, not charge-only)
- Klipper host (Raspberry Pi, BTT Pi, CB1, or any Linux SBC)

## Connection

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
