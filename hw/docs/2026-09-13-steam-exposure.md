# Steam exposure, 2026-09-13 — what the probe did, and what it proves

Unplanned bench event: Fab put the Rev A probe through "a brief steam bath" and
asked for the data afterwards. Probe 3, FW 0x0024, bus 9600 8E1, telemetry via
farm-node-01 into VictoriaMetrics (`gas_*{probe="3"}`, ~60 s effective spacing).
All times UTC. Nothing here was commanded by an agent; the probe was left alone.

**Headline: the probe rode it out. No faults, no reset, no condensation risk, no
lasting change in the cell.** The interesting part is a by-product — the event
put a clean number on the cell's thermal lag, and that number says why
`RH-STEP-TEST.md` has to be isothermal.

## 1. Two exposures, not one

| | A | B (the steam bath) |
|---|---|---|
| start | 15:23 | 16:00 |
| peak | 15:25–15:26 | 16:03–16:05 |
| chamber T | 27.57 → 30.63 °C (+3.1 K) | 26.39 → **45.96 °C (+19.6 K)** |
| chamber RH | 34.5 → 40.0 % | 39.3 → 43.8 % |
| p_w (Magnus) | 12.68 → 17.55 hPa | 13.50 → **42.90 hPa** (x3.2) |
| cell current | 101.10 → 100.26 µA | 100.80 → **98.80 µA** (−2.0 %) |
| O2_COMP | 20.97 → 20.75 %vol | 20.98 → **20.43 %vol** |
| dew margin min | 14.90 K | **14.32 K** |

A is a smaller first pass of the same thing ~37 min earlier. B is the event
worth recording.

`t_tip` tracked `t_chamber` within 0.2 K the whole way through both
(16:04: 44.92 vs 45.05), so the heat arrived from **outside**. This was not the
tip heater — see §4.

## 2. Nothing broke

Live register read at 16:45, and the VM series across the event:

* `FAULTS` 0x0000 throughout. `FAULTS_EVER` 1, unchanged — the same single
  historical bit that was already latched before the event.
* `probe_uptime_s` climbed monotonically through the event (5999 s at 16:36, no
  discontinuity). **The probe did not reset.** `RESET_CAUSE` 20, stale.
* `I2C_ERRS` 0, `ADS_FAIL_COUNT` 0, `MB_CRC_ERRS` 0. Neither the SHT45 nor the
  TMP117s nor the ADC glitched at 46 °C.
* `MB_FRAME_ERRS` 572 — all of it from today's 115200 negotiation attempts,
  nothing to do with the steam.
* Rails flat: `VREF_MON` 2506 mV, `VA_MON` 3298 mV, `VIN_MON` 13092 mV, before,
  during and after. `AFE_VOUT` moved 973 → 984 → 972 mV, tracking temperature.
* `SETTLE_RESTARTS` 1, unchanged — the settle state machine was never retriggered.

**Dew margin never came near the clamp.** Its minimum over the whole three hours
was 14.17 K against `DT_MAX_K` = 4.00 K. At 46 °C the saturation pressure runs
away far faster than 43 %RH can chase it, so the *hot* part of a steam bath is
the safe part. The dangerous case for this probe remains cooling *into* a wet
atmosphere, which is not what happened here.

## 3. The cell recovered completely

Like-for-like, before and after, at matched temperature and vapour pressure:

| | T_ch | p_w | cell |
|---|---|---|---|
| 15:58, before | 26.32 °C | 13.39 hPa | 100.70 µA |
| 16:40, after | 26.85 °C | 14.78 hPa | 100.98 µA |

Predicted from the two known terms — (T/T_cal)^0.75 gives +0.13 %, dilution
against 930 hPa gives −0.15 % — is −0.02 %. Measured is +0.28 %. The residual
is inside the ±0.15 % day-scale scatter plus normal drift. **No step, no
offset, no film that outlived the event.**

`O2_COMP` is back at 21.02–21.03 %vol against 20.98 before, and `CAL_STATE` is
unchanged at 6.

## 4. The heater did what the dew law tells it to

`HEATER_LAW` reads 4 = `O2P_HEATER_LAW_DEW`, and `HEATER_RH_CONSENT` holds
0x9C07 (`O2P_HEATER_RH_CONSENT_MAGIC`), so the autonomous dew loop is consented
and live. `HEATER_TIP_CONSENT` is 0 and `HEATER_TEST_ARM` is 0 — the bench
overrides are both disarmed.

Baseline `HEATER_DUTY` dithers between 0.00 and ~7 % sample to sample (24 h mean
2.68 %). During the event it rose to **21.73 %** at 16:02 and decayed with the
transient. `t_tip − t_chamber` stayed at +0.1…+0.5 K throughout, so whatever the
duty register says, the delivered heat is small and the 4 K clamp was never
approached.

**Flagged, not acted on:** the standing order since 2026-09-11 is that the
heater is off and changes need Fab's word. The *bench* heater paths are indeed
disarmed, but the shipped dew loop is consented and is drawing a few percent
continuously. That is a long-standing state, not something this event caused —
over 7 days, 321 of 1606 samples show non-zero duty, with 100 % spikes on 09-11
evening and 09-13 07:50. Whether the dew loop should be consented on a bench
article is Fab's call.

## 5. What this actually proves: the cell's thermal lag dominates a transient

This is the part worth keeping.

Take two samples with essentially the same chamber temperature and the same
water-vapour pressure, one on the way up and one on the way down:

| | T_ch | p_w | cell | |
|---|---|---|---|---|
| 16:03 | 40.76 °C | 33.58 hPa | 98.80 µA | heating |
| 16:07 | 40.65 °C | 32.63 hPa | 101.96 µA | cooling |

Same state by every measured variable, **3.2 % apart in cell current**, four
minutes apart. A second pair confirms it:

| | T_ch | p_w | cell | |
|---|---|---|---|---|
| 16:02 | 34.13 °C | 22.75 hPa | 99.33 µA | heating |
| 16:12 | 33.97 °C | 22.47 hPa | 101.75 µA | cooling |

+2.4 %, ten minutes apart. The loop closes as the transient dies: the same pair
at 27.1 °C (16:01 vs 16:37) is only +0.67 %.

The mechanism is not in doubt — the cell body has its own thermal mass and lags
both the SHT45 in the chamber and the cell-side TMP117 (`t_ext` read 42.91 °C
when the chamber read 45.05 °C). The compensation uses the sensors, not the
cell, so it over-corrects on the way up and under-corrects on the way down.
That is exactly the visible shape of `O2_COMP`: down to 20.43 %vol at the peak,
then **overshooting to 21.35 %vol at 16:14** on the way back, before settling.

### Why this matters for RH-STEP-TEST

`RH-STEP-TEST.md` §1 asks whether the cell current rises with water vapour (a
moisture film) or falls (dilution), and notes the obstacle: *"every humidity
change on this bench came with a temperature change."* This event is the
extreme case of that obstacle, and it puts a number on it.

Over event B the dilution term is worth −3.2 % (Δp_w = +29.4 hPa against
930 hPa) — a big signal, larger than anything the planned salt-vessel ladder
produces. It is nonetheless **useless as a discriminator**, because the
lag artefact measured above is ±3.2 % on its own and has the wrong shape to
subtract: it depends on the *direction* of travel, not the state.

So this run does **not** touch the film-vs-dilution question, in either
direction. It is positive evidence for the test design rather than a substitute
for it: the isothermal salt-vessel method in `RH-STEP-TEST.md` §2 is not
fastidiousness, it is the only way to get a number here. Any future attempt to
shortcut it with a "just breathe on it" step should be refused on this page.

## 6. Open, unchanged by this

* The dew loop's consent on a bench article (§4) — Fab's call.
* 115200 on the RS-485 bus still returns zero reply bytes; unrelated, and the
  572 frame errors above are its fingerprint.
