# Configuration

## Generic mode

Generic mode provides per-channel feeder control with runout/insert/blockage detection. This works with any Klipper printer — no toolchanger required.

### bmcu_feeder section

```ini
[bmcu_feeder]
serial: /dev/serial/by-path/YOUR_PATH_HERE
baud: 115200
poll_interval: 0.5   # Status query interval in seconds
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `serial` | (required) | Serial path to BMCU — must use `/dev/serial/by-path/` |
| `baud` | `115200` | Baud rate — must match firmware |
| `poll_interval` | `0.5` | How often to query BMCU status (seconds) |

Replace `YOUR_PATH_HERE` with the full path from `ls /dev/serial/by-path/`. See [klipper-install.md](klipper-install.md) for how to find it. The simplest way to get started is:

```ini
# Add to your printer.cfg:
[include bmcu/bmcu_generic.cfg]
```

Then edit `config/bmcu_generic.cfg` and update the `serial:` path.

### Channel sections

```ini
[bmcu_channel 0]
extruder: extruder          # Which extruder this channel feeds
runout_gcode:
    PAUSE                   # GCode to run when filament runs out
insert_gcode:               # GCode to run when filament is inserted (optional)
stall_gcode:
    PAUSE                   # GCode to run on blockage (filament present but not moving)
event_delay: 3.0            # Debounce delay in seconds before triggering events
pause_on_runout: True       # Whether to auto-pause on runout
direction_invert: False     # Set True if FWD ejects filament instead of feeding
require_motor_running: True # Set False for a passive-encoder setup (see below)
pause_on_stall: True        # Whether to auto-pause on a detected blockage
min_commanded_mm: 1.0       # Minimum commanded extrusion (mm) over the window before a stall is evaluated
slip_ratio: 0.5             # Trip when measured feed is less than this fraction of commanded
stall_window_polls: 3       # Consecutive polls forming the cumulative evaluation window
stall_startup_ignore_polls: 2  # Polls to skip once the channel becomes eligible for stall detection
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `extruder` | (none) | Klipper extruder name this channel feeds. Without it, stall detection is disabled entirely for the channel; runout/insert are unaffected |
| `runout_gcode` | (empty) | GCode macro to execute on filament runout |
| `insert_gcode` | (empty) | GCode macro to execute on filament insertion |
| `stall_gcode` | (empty) | GCode macro to execute on blockage/stall |
| `event_delay` | `3.0` | Seconds to debounce before triggering events |
| `pause_on_runout` | `True` | Auto-pause print on runout |
| `direction_invert` | `False` | Set True if FWD ejects filament instead of feeding (some V2.2 hardware has reversed motor wiring) |
| `require_motor_running` | `True` | Whether the BMCU's own feeder motor must be running for stall detection to evaluate. Set False for a passive-encoder setup — see "Passive-encoder setups" below |
| `pause_on_stall` | `True` | Auto-pause print on a detected blockage, independently of `stall_gcode` — see the upgrade callout below |
| `min_commanded_mm` | `1.0` | Minimum commanded extrusion (mm) over the window before a stall is even evaluated — ignores travel/retraction/slow features |
| `slip_ratio` | `0.5` | Trip when measured feed is less than this fraction of commanded — `0.5` means fed less than half of what Klipper commanded |
| `stall_window_polls` | `3` | Number of consecutive polls forming the cumulative evaluation window — this IS the debounce (a real jam must persist across the whole window) |
| `stall_startup_ignore_polls` | `2` | Number of polls to skip once the channel becomes eligible for stall detection (grace window for motor acceleration, or for the channel becoming eligible on a passive setup) |

Channels are numbered 0–3, corresponding to the physical BMCU channel connectors. Add one `[bmcu_channel N]` section per active channel. Unused channels can be omitted.

#### Passive-encoder setups

During a normal print on most printers, the toolhead extruder pulls the filament and the BMCU feeder motor is idle, so `motor_running` reports `False` for the whole job. With the default `require_motor_running: True`, the drift check is skipped entirely and `stall_count` stays `0` no matter how badly filament jams downstream of the BMCU.

Setting `require_motor_running: False` per channel makes the detector compare Klipper's commanded extrusion against the encoder's measured feed regardless of whether the feeder motor is running. The false-positive guards — `min_commanded_mm`, the retraction handling, the direction-change reset, and `stall_startup_ignore_polls` — all remain active in this mode. The grace window is armed when the channel becomes eligible (filament present and sensor enabled) rather than at motor start, since a passive channel may never see a motor-off-to-on edge at all.

#### Behaviour change on upgrade: `pause_on_stall`

`pause_on_stall` defaults to `True`. An existing install that left `stall_gcode` empty previously logged a detected blockage silently (the old stall path had no pause of its own); it will now pause the print when a stall fires. Set `pause_on_stall: False` per channel to restore the old silent-logging behaviour.

### GCode commands

| Command | Description |
|---------|-------------|
| `BMCU_STATUS` | Print per-channel status table |
| `BMCU_RUN CHANNEL=N` | Start motor on channel N (0–3) |
| `BMCU_STOP CHANNEL=N` | Stop motor on channel N (0–3) |
| `BMCU_SPEED CHANNEL=N SPEED=S` | Set motor speed (0–100) on channel N |
| `BMCU_DIR CHANNEL=N DIR=FWD\|REV` | Set motor direction on channel N |
| `BMCU_ENABLE` | Send ENABLE to firmware (init hardware) |
| `BMCU_DISCONNECT` | Disable firmware and release serial port for flashing |
| `BMCU_CONNECT` | Reconnect serial port after flashing |
| `BMCU_RESET_FEED` | Reset feed distance counter (all channels or `CHANNEL=N`) |
| `SET_BMCU_SENSOR CHANNEL=N ENABLE=0\|1` | Disable/enable runout detection for channel N |

---

## Buffer mode (Tapchanger) {#buffer-mode-tapchanger}

Buffer mode integrates the BMCU with [viesturz/klipper-toolchanger](https://github.com/viesturz/klipper-toolchanger) to automatically activate/deactivate channels on tool pick/drop events. Runout detection is suppressed during toolchange transitions to prevent spurious pauses while filament is briefly absent from the microswitch.

### Prerequisites

- [viesturz/klipper-toolchanger](https://github.com/viesturz/klipper-toolchanger) installed and configured (version 2026.2.15+)
- Generic BMCU config working (`BMCU_STATUS` returns clean output)

### Setup

```ini
# Add to printer.cfg:
[include bmcu/bmcu_buffer_tapchanger.cfg]
```

Then merge the `[toolchanger]` gcode sections from `config/bmcu_buffer_tapchanger.cfg` with your existing `[toolchanger]` section, and add the `params_bmcu_channel`, `pickup_gcode`, and `dropoff_gcode` lines to each of your `[tool Tx]` sections as shown in that file.

### How it works

The toolchange sequence for a T0 to T1 change:

1. `before_change_gcode` — disables ALL BMCU sensors to suppress runout events during the mechanical transition window
2. `dropoff_gcode` (T0) — stops the motor on the dropped tool's channel (`BMCU_STOP CHANNEL=0`)
3. `pickup_gcode` (T1) — starts the motor on the picked tool's channel (`BMCU_RUN CHANNEL=1`)
4. `after_change_gcode` — re-enables the sensor **only** for the newly picked channel

This ensures the sensor is always disabled before any gantry motion begins and re-enabled only after the mechanical pick is confirmed.

### Troubleshooting

- **Runout fires during toolchange:** Check that `before_change_gcode` in your `[toolchanger]` section contains `SET_BMCU_SENSOR CHANNEL=N ENABLE=0` for all configured channels. The sensor must be disabled before any gantry motion begins. If the disable is only in `dropoff_gcode`, it fires too late.

- **`pickup_tool` is undefined error:** Your klipper-toolchanger version is too old. Update to 2026.2.15+ or use the per-tool fallback described in `config/bmcu_buffer_tapchanger.cfg`, which adds `SET_BMCU_SENSOR CHANNEL=N ENABLE=1` directly to each tool's `pickup_gcode` instead of using the Jinja2 variable lookup.

- **Config error on `[tool T0]`:** The `[tool]` section type requires viesturz/klipper-toolchanger. Do not include `bmcu_buffer_tapchanger.cfg` on non-Tapchanger printers — use `bmcu_generic.cfg` only.

---

## Moonraker / Mainsail / Fluidd

The BMCU extra exposes per-channel status via Klipper's status reporting system. Moonraker-compatible frontends (Mainsail, Fluidd, KlipperScreen) can display channel status automatically. No additional Moonraker configuration is needed — status objects are available at `printer.bmcu_feeder.channels`.
