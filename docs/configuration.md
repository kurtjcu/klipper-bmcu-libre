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
min_measured_mm: 1.0        # Encoder movement (mm) within stall_timeout_s that counts as "alive"
stall_timeout_s: 15.0       # Seconds the encoder may go without movement before a stall fires
min_commanded_mm: 5.0       # Forward extrusion (mm) that must be commanded before a stall is evaluated
pause_on_encoder_fault: False  # Whether to auto-pause on a detected encoder fault (dead magnet sensor)
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
| `min_measured_mm` | `1.0` | Encoder movement (mm) within `stall_timeout_s` that counts as "alive" — the noise floor |
| `stall_timeout_s` | `15.0` | Seconds the encoder may go without confirmed movement before a stall fires. Wall-clock time, independent of `poll_interval` |
| `min_commanded_mm` | `5.0` | Forward extrusion (mm) that must be commanded since the last confirmed movement before a stall is even evaluated — ignores travel/retraction/slow features |
| `pause_on_encoder_fault` | `False` | Auto-pause on a detected encoder fault (non-ok magnet status) — see "Encoder faults" below |

Channels are numbered 0–3, corresponding to the physical BMCU channel connectors. Add one `[bmcu_channel N]` section per active channel. Unused channels can be omitted.

#### Deprecated options

`slip_ratio`, `stall_window_polls` and `stall_startup_ignore_polls` are accepted and silently ignored — Klipper rejects a config option no module reads, so removing them would stop an existing printer booting on an unedited config. They will be removed in a later release; delete them from your config once you've migrated to `min_measured_mm` / `stall_timeout_s` / `min_commanded_mm` above.

| Parameter | Status |
|-----------|--------|
| `slip_ratio` | Deprecated — accepted, ignored |
| `stall_window_polls` | Deprecated — accepted, ignored |
| `stall_startup_ignore_polls` | Deprecated — accepted, ignored |

#### Passive-encoder setups

During a normal print on most printers, the toolhead extruder pulls the filament and the BMCU feeder motor is idle, so `motor_running` reports `False` for the whole job. With the default `require_motor_running: True`, the detector is skipped entirely and `stall_count` stays `0` no matter how badly filament jams downstream of the BMCU.

Setting `require_motor_running: False` per channel makes the detector evaluate regardless of whether the feeder motor is running. The detector no longer compares magnitudes — it asks whether the encoder moved at all — so the compliance/slack between the BMCU and the toolhead (Bowden, buffer, spring slack) is no longer a source of false positives: once slack is taken up, the encoder moves whenever the extruder does, and any single poll of confirmed movement re-baselines the tracker. Partial slip — the encoder moving, but less than commanded — is deliberately not detected at all; calibrating a feeder-to-extruder ratio per channel was judged not worth the effort for a rare failure mode.

`min_commanded_mm` and `stall_timeout_s` interact: `min_commanded_mm` must be reachable within `stall_timeout_s` or the detector never fires. `min_commanded_mm / stall_timeout_s` is the implied minimum sustained extrusion rate below which the detector is inert by construction — `0.333 mm/s` at the shipped defaults (`5.0 / 15.0`). This is logged at Klipper startup and exposed live as `bmcu_feeder.channels.N.stall_min_rate_mms`, so a never-fires configuration is visible rather than silent.

If you are upgrading from the pre-260821-e77 defaults and still have `min_commanded_mm: 1.0` in your printer.cfg, raise it to `5.0` (the new shipped default) — at `1.0` the implied minimum rate falls to `0.067 mm/s`, well below any real print speed. Lowering `stall_timeout_s` detects a jam faster at the cost of tolerating less slack take-up before the encoder is judged to have moved.

#### Encoder faults

A non-`ok` magnet status (`low`, `high`, `offline`, or any value other than `ok`/`unknown`), debounced over 3 consecutive polls (~1.5s at the default `poll_interval`), raises an `encoder_fault` event instead of a blockage and suspends stall evaluation until the magnet reads `ok` again. A dead AS5600 and a real jam otherwise produce byte-identical `feed_mm` output — reporting the fault distinctly means a broken sensor is never mistaken for (or reported as) filament jamming.

`unknown` — the module's own initial value before the first `STATUS ok` line arrives — is never treated as a fault.

`pause_on_encoder_fault` defaults to `False`: losing sight of the filament is a loss of observability, not a detected failure, and stopping a good print to guard against a jam that may not exist is the more expensive mistake. Set it `True` per channel to stop the print rather than continue unwatched.

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
| `BMCU_RESET_FEED` | Reset feed distance counter and the activity tracker (all channels or `CHANNEL=N`). Call this from `PRINT_START` so the opening purge starts from a clean slate |
| `SET_BMCU_SENSOR CHANNEL=N ENABLE=0\|1` | Disable/enable runout detection for channel N |

### Moonraker objects

Status objects are available at `printer.bmcu_feeder.channels.N`:

| Key | Type | Description |
|-----|------|-------------|
| `feed_mm` | float | Raw encoder distance (mm) |
| `feed_mm_since_reset` | float | Distance since the last `BMCU_RESET_FEED` |
| `stall_count` | int | Cumulative stall events since the last reset |
| `filament_present` | bool | Filament sensor state |
| `motor_running` | bool | Motor running state |
| `mag_status` | str | Raw magnet status reported by firmware (`ok`/`low`/`high`/`offline`/`unknown`) |
| `sensor_enabled` | bool | Whether `SET_BMCU_SENSOR` has this channel's sensor enabled |
| `stall_min_rate_mms` | float | Implied minimum sustained extrusion rate (`min_commanded_mm / stall_timeout_s`) the detector can catch |
| `seconds_since_movement` | float | Time since the encoder last showed confirmed movement |
| `commanded_since_movement` | float | Forward mm commanded since the last confirmed movement |
| `encoder_fault` | bool | True while the magnet status is faulted and stall evaluation is suspended |

---

## Buffer mode (toolchanger) {#buffer-mode-toolchanger}

Buffer mode integrates the BMCU with [viesturz/klipper-toolchanger](https://github.com/viesturz/klipper-toolchanger) to automatically activate/deactivate channels on tool pick/drop events. Runout detection is suppressed during toolchange transitions to prevent spurious pauses while filament is briefly absent from the microswitch.

### Prerequisites

- [viesturz/klipper-toolchanger](https://github.com/viesturz/klipper-toolchanger) installed and configured (version 2026.2.15+)
- Generic BMCU config working (`BMCU_STATUS` returns clean output)

### Setup

```ini
# Add to printer.cfg:
[include bmcu/bmcu_buffer_toolchanger.cfg]
```

Then merge the `[toolchanger]` gcode sections from `config/bmcu_buffer_toolchanger.cfg` with your existing `[toolchanger]` section, and add the `params_bmcu_channel`, `pickup_gcode`, and `dropoff_gcode` lines to each of your `[tool Tx]` sections as shown in that file.

### How it works

The toolchange sequence for a T0 to T1 change:

1. `before_change_gcode` — disables ALL BMCU sensors to suppress runout events during the mechanical transition window
2. `dropoff_gcode` (T0) — stops the motor on the dropped tool's channel (`BMCU_STOP CHANNEL=0`)
3. `pickup_gcode` (T1) — starts the motor on the picked tool's channel (`BMCU_RUN CHANNEL=1`)
4. `after_change_gcode` — re-enables the sensor **only** for the newly picked channel

This ensures the sensor is always disabled before any gantry motion begins and re-enabled only after the mechanical pick is confirmed.

### Troubleshooting

- **Runout fires during toolchange:** Check that `before_change_gcode` in your `[toolchanger]` section contains `SET_BMCU_SENSOR CHANNEL=N ENABLE=0` for all configured channels. The sensor must be disabled before any gantry motion begins. If the disable is only in `dropoff_gcode`, it fires too late.

- **`pickup_tool` is undefined error:** Your klipper-toolchanger version is too old. Update to 2026.2.15+ or use the per-tool fallback described in `config/bmcu_buffer_toolchanger.cfg`, which adds `SET_BMCU_SENSOR CHANNEL=N ENABLE=1` directly to each tool's `pickup_gcode` instead of using the Jinja2 variable lookup.

- **Config error on `[tool T0]`:** The `[tool]` section type requires viesturz/klipper-toolchanger. Do not include `bmcu_buffer_toolchanger.cfg` on printers without klipper-toolchanger — use `bmcu_generic.cfg` only.

---

## Moonraker / Mainsail / Fluidd

The BMCU extra exposes per-channel status via Klipper's status reporting system. Moonraker-compatible frontends (Mainsail, Fluidd, KlipperScreen) can display channel status automatically. No additional Moonraker configuration is needed — status objects are available at `printer.bmcu_feeder.channels`.
