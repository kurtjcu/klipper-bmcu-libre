---
phase: 06-feed-distance-tracking
verified: 2026-07-07T12:00:00Z
status: human_needed
score: 8/9
overrides_applied: 0
human_verification:
  - test: "Connect BMCU via USB-C. Run: python3 tests/test_protocol.py --port /dev/ttyUSB0. Observe test_feed_continuous_accumulation output."
    expected: "mm= values for ch=0 increase monotonically across 6 STATUS polls taken at 0.5s intervals during motor run. All assertions pass."
    why_human: "Requires physical BMCU hardware. Cannot be verified without the device. This is the end-to-end proof that the firmware accumulates continuously between STATUS polls."
---

# Phase 6: Feed Distance Tracking — Verification Report

**Phase Goal:** Fix AS5600 polling — mm must accumulate during motor runs, not just on STATUS
**Verified:** 2026-07-07
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `update_feed_distance()` runs every main-loop tick, not only on STATUS poll | VERIFIED | `update_feed_distance(ch)` called at `uart_protocol.cpp:641` inside the `if (hw_enabled)` for-loop of `uart_protocol_tick()`. Only 2 occurrences of the identifier: line 128 (definition) and line 641 (tick call). |
| 2 | AS5600 wrap-around across 0/4095 boundary produces correct small deltas | VERIFIED | Lines 137-138: `if (delta > 2048) delta -= 4096; if (delta < -2048) delta += 4096;` — exact pattern from Motion_control.cpp. Delta declared `int32_t` with explicit casts at line 136. |
| 3 | Magnet-offline channels do not accumulate junk deltas or update prev_angle | VERIFIED | First statement of `update_feed_distance()` at line 129: `if (MC_AS5600.magnet_stu[ch] == -1) return;` — precedes all angle math including the `angle_initialized` check. |
| 4 | STATUS response no longer double-counts by calling `update_feed_distance()` | VERIFIED | `send_status_response()` at lines 195-232 contains no call to `update_feed_distance`. Comment at line 197 explicitly documents this: "Feed distance is accumulated every tick in uart_protocol_tick()." |
| 5 | MockSerial accepts zero-arg construction matching BmcuSerial.connect() usage | VERIFIED | `conftest.py:76`: `def __init__(self, port=None, baud=None, timeout=None)`. `open()` method at line 85, `reset_input_buffer()` at line 104, `readline()` returning `b"ENABLE ok\n"` at line 98. |
| 6 | Pytest verifies `feed_mm_since_reset` accumulates across multiple STATUS polls | VERIFIED | `TestFeedAccumulation::test_accumulates_across_polls` at `test_bmcu_feeder.py:1396`. 4 tests in the class all pass: `4 passed in 8.02s`. |
| 7 | Pytest verifies `feed_mm_since_reset` is zero when mm= values are constant | VERIFIED | `TestFeedAccumulation::test_mm_stable_shows_zero_delta` at `test_bmcu_feeder.py:1407`. Passes. |
| 8 | Hardware test verifies mm= values advance continuously during motor run | UNCERTAIN (human needed) | `test_feed_continuous_accumulation()` exists at `test_protocol.py:163`, is syntactically valid, and registered in `main()` tests list at line 214. Cannot execute without physical BMCU. |
| 9 | Full pytest suite passes with no regressions | VERIFIED | `python3 -m pytest tests/test_bmcu_feeder.py -q`: **66 passed, 0 failed** (62 from Plan 01 + 4 new TestFeedAccumulation). |

**Score:** 8/9 truths fully verified. Truth 8 is UNCERTAIN pending hardware execution.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `firmware/src/uart_protocol.cpp` | Continuous accumulation with wrap correction and magnet guard | VERIFIED | magnet guard line 129, int32_t delta line 136, wrap correction lines 137-138, tick call line 641, no call in send_status_response |
| `tests/conftest.py` | MockSerial zero-arg construction | VERIFIED | `__init__(self, port=None, baud=None, timeout=None)`, `open()`, `reset_input_buffer()`, `readline()` all present |
| `tests/test_bmcu_feeder.py` | TestFeedAccumulation class with 4 accumulation tests | VERIFIED | Class at line 1354, 4 test methods, all 4 pass |
| `tests/test_protocol.py` | `test_feed_continuous_accumulation` method in BMCUTester | VERIFIED (syntax) | Method at line 163, registered in main() tests list at line 214, syntax clean |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `uart_protocol.cpp:uart_protocol_tick` | `uart_protocol.cpp:update_feed_distance` | direct call at line 641 inside hw_enabled for-loop | WIRED | Confirmed by grep: exactly 2 occurrences of `update_feed_distance` — definition (128) and tick call (641) |
| `tests/conftest.py:MockSerial` | `klippy/extras/bmcu_feeder.py:BmcuSerial.connect` | monkeypatch replaces serial.Serial | WIRED | TestFeedAccumulation._make_feeder_with_channels uses `monkeypatch.setattr('klippy.extras.bmcu_feeder.serial.Serial', mock_serial_cls)` at test_bmcu_feeder.py:1383 |
| `tests/test_bmcu_feeder.py:TestFeedAccumulation` | `klippy/extras/bmcu_feeder.py:BmcuFeeder` | _poll_status with injected STATUS lines | WIRED | `_dispatch()` helper injects STATUS line into `feeder._serial._lines` and calls `feeder._poll_status(0.0)` — confirmed at lines 1390-1394 |
| `tests/test_protocol.py:test_feed_continuous_accumulation` | firmware UART protocol | serial send_recv STATUS | WIRED (syntax only) | Method sends ENABLE, RUN 0, then loops STATUS; regex parses mm= for ch=0. Hardware execution required to confirm end-to-end. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `test_bmcu_feeder.py:TestFeedAccumulation` | `feed_mm_since_reset` | Injected STATUS lines via `feeder._serial._lines` + `feeder._poll_status()` | Yes — values come from injected STATUS strings, parsed by `_dispatch_status_line()` in bmcu_feeder.py | FLOWING |
| `uart_protocol.cpp:update_feed_distance` | `feed_counts[ch]` | `MC_AS5600.raw_angle[ch]` read each tick | Yes — reads live AS5600 sensor angle (or firmware test equivalent) | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All pytest tests pass (66 total) | `python3 -m pytest tests/test_bmcu_feeder.py -q` | 66 passed, 0 failed in 116s | PASS |
| TestFeedAccumulation 4 tests | `python3 -m pytest tests/test_bmcu_feeder.py::TestFeedAccumulation -v` | 4 passed in 8.02s | PASS |
| test_protocol.py syntax valid | `python3 -c "import ast; ast.parse(...)"` | no syntax errors | PASS |
| update_feed_distance absent from send_status_response | `grep -n "update_feed_distance" uart_protocol.cpp` | 2 matches (def + tick call), none in send_status_response | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files found. Phase does not declare probes.

---

### Requirements Coverage

The PLAN frontmatter declares requirement IDs D-01 through D-07. These are **implementation decision IDs** defined in `06-CONTEXT.md` and `06-RESEARCH.md`, not entries in `REQUIREMENTS.md`. REQUIREMENTS.md contains only STALL-xx and DIAG-xx IDs (Phases 4-5). Phase 6 does not claim to satisfy any REQUIREMENTS.md entries — it is a bug-fix/hardware-validation phase that addresses pre-existing implementation decisions tracked in the phase context documents.

| Decision ID | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| D-01 | Call `update_feed_distance()` every main-loop tick | SATISFIED | Line 641 of uart_protocol.cpp inside uart_protocol_tick() |
| D-02 | Gate accumulation on `hw_enabled` | SATISFIED | The tick call is inside the `if (hw_enabled)` else-branch at line 619 |
| D-03 | int32_t delta with wrap-around correction | SATISFIED | Lines 136-138 of uart_protocol.cpp |
| D-04 | Skip accumulation and prev_angle update when magnet offline | SATISFIED | Line 129 — early return before all angle math |
| D-05 | Keep feed_counts as raw encoder (no motor_dir multiplication) | SATISFIED | Line 139: `feed_counts[ch] += delta;` — no motor_dir in expression |
| D-06 | Pytest tests for Klipper-side feed_mm accumulation | SATISFIED | TestFeedAccumulation 4 tests all pass |
| D-07 | Hardware test validating continuous firmware accumulation | PARTIAL — test exists, hardware execution pending | test_protocol.py:163 exists and is registered; requires physical BMCU |

**REQUIREMENTS.md orphan check:** REQUIREMENTS.md traceability table maps no IDs to Phase 6. No orphaned requirements found.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `firmware/src/uart_protocol.cpp` | 39 | `/* placeholder — measure on physical hardware */` for GEAR_CIRCUMFERENCE_MM | Info | Pre-existing since Phase 1; tracked as CAL-01 (future requirement, explicitly deferred). Not introduced by Phase 6. Does not affect correctness of accumulation logic — only affects the mm= scaling factor. |

No TBD, FIXME, or XXX markers found in any Phase 6 modified files.

---

### Human Verification Required

#### 1. Hardware Integration Test (D-07)

**Test:** Connect BMCU device via USB-C. Run `python3 tests/test_protocol.py --port /dev/ttyUSB0` (adjust port as needed).

**Expected:** `test_feed_continuous_accumulation` passes — mm= values for ch=0 increase monotonically across all 6 STATUS polls taken at 0.5s intervals while motor is running. Test output shows "mm= values increase monotonically during motor run: PASS".

**Why human:** Requires physical BMCU hardware connected via USB serial. Cannot be simulated in CI. This is the end-to-end proof that the firmware fix (continuous accumulation in uart_protocol_tick) actually produces advancing mm= values between STATUS polls, not just on the STATUS trigger.

---

### Gaps Summary

No gaps. All automatically-verifiable truths are VERIFIED. Truth 8 (hardware integration test) is UNCERTAIN pending physical hardware execution — this is expected per the phase design (D-07 is explicitly flagged as a manual-only verification in `06-VALIDATION.md`).

The phase goal "Fix AS5600 polling — mm must accumulate during motor runs, not just on STATUS" is demonstrably achieved in the codebase:
- `update_feed_distance()` now runs every main-loop tick (not just on STATUS)
- Wrap-around correction eliminates wrong deltas at the 0/4095 boundary
- Magnet-offline guard prevents junk accumulation
- `send_status_response()` no longer double-counts
- 66 pytest tests pass, including 4 new TestFeedAccumulation tests that directly validate the Klipper-side accumulation behavior
- Hardware test is present, syntactically valid, and registered — awaiting physical device execution for final end-to-end confirmation

---

_Verified: 2026-07-07T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
