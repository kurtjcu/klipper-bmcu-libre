# Firmware Flashing

The BMCU libre firmware is built from source using PlatformIO. Pre-built upstream firmware variants are available in `firmware/firmwares/` for reference, but the libre build (which includes the UART protocol required by the Klipper extra) must be compiled from source.

## Option A: bmcu-flasher (recommended)

The `bmcu-flasher` tool is included in this repo at `tools/bmcu-flasher/`. It handles automatic bootloader entry on Type-C mainboards (AutoDI) and provides both a GUI and CLI interface.

First, build the libre firmware:

```bash
cd firmware
pio run -e bmcu_libre
# Output: .pio/build/bmcu_libre/firmware.bin
```

Then flash it:

```bash
# USB mode (Type-C mainboard with CH340 AutoDI):
python3 tools/bmcu-flasher/bmcu_flasher.py .pio/build/bmcu_libre/firmware.bin --mode usb
```

> **Important:** You MUST use the `bmcu_libre` environment (`-e bmcu_libre`). Other environments in `platformio.ini` do not include the UART protocol changes and will behave like unmodified upstream firmware.

### If AutoDI does not trigger automatically

1. Unplug USB-C from BMCU
2. Hold the BOOT button on the BMCU mainboard
3. Plug USB-C back in
4. Release the BOOT button
5. Run the flash command above

> The `bmcu-flasher` also has a GUI (`bmcu_flasher_gui.py`) for those who prefer a graphical interface. Pre-built GUI binaries for Windows, macOS, Linux, and Android are available from the Releases page of the bmcu-flasher repository.

## Option B: wchisp (advanced)

`wchisp` is a Rust-based CLI tool for flashing CH32 microcontrollers over USB ISP. Use this if you prefer not to use Python or want a lower-level flashing tool.

```bash
# Install wchisp
cargo install wchisp --git https://github.com/ch32-rs/wchisp

# Linux udev rule for wchisp (one-time setup):
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="4348", ATTRS{idProduct}=="55e0", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/50-wchisp.rules
sudo udevadm control --reload && sudo udevadm trigger

# Enter bootloader: hold BOOT button, plug USB-C in
# Verify detection:
wchisp info

# Flash:
wchisp flash .pio/build/bmcu_libre/firmware.bin
```

The ISP mode USB identifiers are VID `4348`, PID `55e0` (different from the normal CH340 operating mode).

## Building from source (developers)

```bash
cd firmware
pio run -e bmcu_libre
# Output: .pio/build/bmcu_libre/firmware.bin
```

The `bmcu_libre` environment sets the following build flags:

| Flag | Value | Effect |
|------|-------|--------|
| `BMCU_LIBRE` | `1` | Enables libre firmware mode |
| `UART_BAUD` | `115200` | Sets UART baud rate for Klipper communication |
| `UART_PROTOCOL_ENABLED` | `1` | Enables the STATUS/RUN/STOP/SPEED/DIR protocol |
| `DISABLE_BAMBUBUS` | `1` | Disables the BambuBus protocol (not needed for Klipper) |

## Verify flash

After flashing, unplug and replug the USB-C cable to let the firmware start in normal mode, then open a serial terminal:

```bash
# Open a serial terminal at 115200 baud:
screen /dev/serial/by-path/YOUR_PATH_HERE 115200

# Type STATUS and press Enter. You should see output like:
# STATUS ok ch=0 fil=1 mot=0 spd=0 dir=FWD mm=0.0 mag=ok ch=1 fil=0 mot=0 spd=0 dir=FWD mm=0.0 mag=ok ...

# Press Ctrl-A then K to exit screen.
```

Replace `YOUR_PATH_HERE` with the full path from `ls /dev/serial/by-path/`.

## Next step

[Install the Klipper extra](klipper-install.md)
