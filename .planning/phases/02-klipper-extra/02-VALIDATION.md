---
phase: 2
slug: klipper-extra
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-01
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (host-side unit tests) |
| **Config file** | `tests/conftest.py` — mock Klipper printer, reactor, serial, gcode fixtures |
| **Quick run command** | `pytest tests/test_bmcu_feeder.py -x` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_bmcu_feeder.py -x`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | KL-01 | unit | `pytest tests/test_bmcu_feeder.py::test_serial_nonblocking -x` | No — Wave 0 | pending |
| 02-01-02 | 01 | 1 | KL-02 | unit | `pytest tests/test_bmcu_feeder.py::test_channel_config -x` | No — Wave 0 | pending |
| 02-02-01 | 02 | 2 | KL-03 | unit | `pytest tests/test_bmcu_feeder.py::test_cmd_run -x` | No — Wave 0 | pending |
| 02-02-01 | 02 | 2 | KL-04 | unit | `pytest tests/test_bmcu_feeder.py::test_cmd_stop -x` | No — Wave 0 | pending |
| 02-02-01 | 02 | 2 | KL-05 | unit | `pytest tests/test_bmcu_feeder.py::test_cmd_status -x` | No — Wave 0 | pending |
| 02-02-02 | 02 | 2 | KL-15 | unit | `pytest tests/test_bmcu_feeder.py::test_cmd_speed -x` | No — Wave 0 | pending |
| 02-02-01 | 02 | 2 | KL-10 | unit | `pytest tests/test_bmcu_feeder.py::test_set_sensor -x` | No — Wave 0 | pending |
| 02-03-01 | 03 | 3 | KL-06 | unit | `pytest tests/test_bmcu_feeder.py::test_runout_event -x` | No — Wave 0 | pending |
| 02-03-01 | 03 | 3 | KL-07 | unit | `pytest tests/test_bmcu_feeder.py::test_insert_event -x` | No — Wave 0 | pending |
| 02-03-01 | 03 | 3 | KL-08 | unit | `pytest tests/test_bmcu_feeder.py::test_event_delay -x` | No — Wave 0 | pending |
| 02-03-01 | 03 | 3 | KL-09 | unit | `pytest tests/test_bmcu_feeder.py::test_pause_on_runout -x` | No — Wave 0 | pending |
| 02-03-02 | 03 | 3 | KL-13 | unit | `pytest tests/test_bmcu_feeder.py::test_blockage_detect -x` | No — Wave 0 | pending |
| 02-03-02 | 03 | 3 | KL-14 | unit | `pytest tests/test_bmcu_feeder.py::test_stall_gcode -x` | No — Wave 0 | pending |
| 02-04-01 | 04 | 4 | KL-11 | unit | `pytest tests/test_bmcu_feeder.py::test_get_status -x` | No — Wave 0 | pending |
| 02-04-01 | 04 | 4 | KL-12 | unit | `pytest tests/test_bmcu_feeder.py::test_serial_error -x` | No — Wave 0 | pending |
| 02-04-01 | 04 | 4 | KL-16 | unit | `pytest tests/test_bmcu_feeder.py::test_status_immutability -x` | No — Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — mock Klipper printer, reactor, gcode, gcode_macro, serial objects
- [ ] `tests/test_bmcu_feeder.py` — 16 test stubs covering KL-01 through KL-16
- [ ] `klippy/extras/bmcu_feeder.py` — stub file (class skeleton, no implementation) so tests import without error
- [ ] pytest install: `pip install pytest pyserial` in dev environment

*Wave 0 is satisfied by Plan 02-01 Task 1 which creates the test infrastructure.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Moonraker subscribes to bmcu_feeder status and Mainsail/Fluidd shows per-channel updates | KL-11, KL-16 | Requires running Klipper+Moonraker+frontend stack with real or simulated BMCU hardware | 1. Start Klipper with bmcu_feeder configured. 2. Open Mainsail/Fluidd. 3. Navigate to printer objects. 4. Confirm `bmcu_feeder` object appears with `channels` sub-keys updating in real-time. |
| BMCU_STATUS in Klipper console shows correct table format | KL-05 | Visual formatting verification | 1. Connect to Klipper console. 2. Run `BMCU_STATUS`. 3. Verify column alignment matches UI-SPEC.md. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
