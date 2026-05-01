# Klipper Installation

## 1. Clone and install

```bash
cd ~
git clone https://github.com/kurtjcu/klipper-bmcu-libre.git
cd klipper-bmcu-libre
./install.sh
```

This symlinks `bmcu_feeder.py` into your Klipper extras directory. Unlike a copy, the symlink survives Klipper updates.

> If Klipper is not at `~/klipper/`, set the path: `KLIPPER_DIR=/path/to/klipper ./install.sh`

## 2. Find your serial path

The BMCU connects via a CH340 USB-to-serial chip. Because CH340 devices share the same VID:PID (`1a86:7523`) and have no unique serial number, you **must** use a `/dev/serial/by-path/` path for stable device identification. Bare `/dev/ttyUSBx` paths will change across reboots and the Klipper extra will reject them with a config error.

```bash
# With BMCU plugged in:
ls /dev/serial/by-path/

# Example output:
# platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-port0
```

Copy the full path — you will need it for `printer.cfg`.

## 3. Add configuration to printer.cfg

```ini
# Add to your printer.cfg:
[include config/bmcu_generic.cfg]
```

Then edit `config/bmcu_generic.cfg` (or inline the sections) and replace the example `serial:` path with your actual by-path value from step 2.

Refer to [configuration.md](configuration.md) for full configuration options and buffer mode setup.

## 4. Restart Klipper

```bash
sudo systemctl restart klipper
```

## 5. Verify

In the Klipper console (Mainsail/Fluidd):

```
BMCU_STATUS
```

You should see a per-channel status table showing filament presence, motor state, and feed distance for each configured channel.

## udev rules (optional)

### Why /dev/serial/by-path/?

CH340G chips have no EEPROM for storing a unique serial number. All CH340G devices report the same USB VID:PID (`1a86:7523`). This means `/dev/serial/by-id/` cannot distinguish between multiple CH340 devices — the symlink is unpredictable. `/dev/serial/by-path/` uses the physical USB port location, which is stable across reboots as long as you don't move the cable to a different port. This is the approach recommended by the [Klipper FAQ](https://www.klipper3d.org/FAQ.html).

### Custom symlink (single CH340 device only)

```bash
# Only use this if the BMCU is your ONLY CH340 device on this host.
# If you have multiple CH340 devices (e.g., another MCU board), use by-path instead.

# Create /etc/udev/rules.d/99-bmcu.rules:
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="bmcu"' \
  | sudo tee /etc/udev/rules.d/99-bmcu.rules

# Reload udev:
sudo udevadm control --reload && sudo udevadm trigger

# Verify:
ls -la /dev/bmcu
```

Then use `serial: /dev/bmcu` in your `printer.cfg` instead of the by-path string.

> **Warning:** If you later add another CH340 device, the `/dev/bmcu` symlink will be unpredictable. Switch back to by-path in that case.

### Scoping to a specific USB port (multiple CH340 devices)

If you have more than one CH340 device and want a custom symlink for the BMCU specifically, scope the udev rule to the physical USB port:

```bash
# Find the USB port path for your BMCU:
udevadm info -a /dev/ttyUSBx | grep KERNELS | head -5
# Look for a line like: KERNELS=="1-1.1:1.0"

# Create a port-scoped rule:
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", KERNELS=="1-1.1:1.0", SYMLINK+="bmcu"' \
  | sudo tee /etc/udev/rules.d/99-bmcu.rules
sudo udevadm control --reload && sudo udevadm trigger
```

Replace `1-1.1:1.0` with the `KERNELS` value from your own `udevadm info` output. This ensures the rule matches only the BMCU connected to that specific USB port, not other CH340 devices.

## Automatic updates via Moonraker

Add this to your `moonraker.conf` to get updates through Mainsail/Fluidd:

```ini
[update_manager bmcu]
type: git_repo
path: ~/klipper-bmcu-libre
origin: https://github.com/kurtjcu/klipper-bmcu-libre.git
primary_branch: main
install_script: install.sh
managed_services: klipper
```

Moonraker will check for updates and re-run `install.sh` automatically when you update.

## Next step

[Configure channels and macros](configuration.md)
