# Oven soak: how does the cell's current really follow temperature above 50 °C?

**Planned 2026-09-17. Not scheduled.** The probe is buried in the pile. Taking it
out, and when, is Fab's call. Predictions are recorded here before any run.

> **2026-09-18: §6's abort criteria are already being met in the pile**, unattended
> — faults other than 512 (2560, 2561, 517 and a 32799 total I²C failure),
> `settle_s` restarting repeatedly since 04:57, and cell current ranging 1.95 to
> 59.9 µA against the 80–120 µA abort band. The sequence resembles the 09-11
> event that cost U8/U3/R36. This does not change the plan, but it does put the
> premise "the cell is intact and in the pile" in question, and the soak is the
> measurement that would close the >36 °C gap.
> See `docs/2026-09-18-pile-failure-sequence.md`.

## 1. Why

The pile reached **73.7 °C** chamber on 2026-09-17 evening, and O₂ fell from
15 % to 3–8 %vol. Above 60 °C the probe raises `TEMP_OVER` (fault bit 512):
the cell is outside DS-0637's −40…+60 °C rating, and the conversion
extrapolates. The firmware divides the current by **(T/T_cal)^0.75**
(`o2.c`, on T_EXT). At 73.7 °C against CAL_TEMP 37.71 °C that divisor is
**1.086**.

Nothing supports that law above 36 °C:

* **Outdoor fit, 13–36 °C** (`docs/2026-09-13-outdoor-tempco-dilution-fit.md`):
  +2600 ppm/K, joint with dilution α ≈ 1. This is the only measurement behind
  the law.
* **The only valid hot window** is 2026-09-11 20:05–20:33. The probe was
  cooling out of an oven and cell-side T_EXT ≈ chamber ≈ AFE. Current is
  corrected to dry basis at 930 hPa and compared with the same evening's
  ambient (99.67 µA at 23.6 °C):

  | cell-side T | measured | law | ratio |
  |---|---|---|---|
  | 66.8 °C (heater holding) | +1.7 % | +10.7 % | 0.92 |
  | 64.0 °C | +2.7 % | +10.0 % | 0.93 |
  | 61.4 °C | +3.8 % | +9.4 % | 0.95 |
  | 55.2 °C | +4.6 % | +7.9 % | 0.97 |
  | 52.0 °C | +4.9 % | +7.1 % | 0.98 |

  So the current rose far less than the law, and above ~52 °C it *fell*. That
  run cannot give a coefficient:
  * The ADC reading the cell (U8), plus U3 and R36, were replaced on 09-12
    (`CELL-AFE-DEBUG.md`, the 2026-09-12 sections).
  * The same ADC saturated at 20:39–21:03.
  * The ambient baseline dropped 2.2 % across the 17:11 steam exposure.
  * It was a single cooling pass.
* **The other hot episodes have no usable current:**
  * Steam at ~80 °C (09-10 ~21:20–21:35; 09-11 17:11–17:20).
  * Dry soaks at 76 °C and 86 °C (09-11 22:51–09-12 04:50; 09-12 12:50–13:26).
  * The 7 h heater-held tip at 80 °C (09-11 01:36–08:46): AFE ~34 °C, so the
    cell was never hot.
  * The 09-08 hot bath (`docs/2026-09-08-hot-bath-run.md`).

This soak replaces the one cooling pass with held, bracketed points through
the repaired front end, on the same cell that is in the pile (Fab, 2026-09-17).

## 2. What it measures, and what it does not

**Measures:** the whole chain's response to temperature — cell + AFE + ADC —
with everything at one temperature. That is the case the firmware has to
correct in the pile, where the buried probe sits at pile temperature
throughout. It does **not** split cell from AFE; for that,
`docs/2026-09-09-afe-tempco-plan.md` is still the measurement.

**Why an oven and not the heater:** the ring heater heats the tip. Under drive,
dT_AFE/dT_TIP is 0.29, so the cell lags far behind the board sensors. Every
heater-held "isothermal" window so far was isothermal on the board only.

**Why no O₂ reference is needed:** vented oven air is ambient air, 20.95 %vol
dry. The only O₂ change is dilution by water vapour, which the SHT45 measures.

## 3. Setup

* **Electric oven, vented.** A gas oven puts combustion products in the air.
  **Never a sealed jar or lidded pot.** The cell reads O₂ *partial pressure*,
  and a sealed vessel's pressure rises with temperature:

  | T | 40 | 50 | 60 | 70 | 80 °C |
  |---|---|---|---|---|---|
  | sealed pO₂ rise | +5.0 % | +8.4 % | +11.7 % | +15.1 % | +18.4 % |

  That rise is as large as the effect being measured.
* **Thermal damping without sealing.** Stand the probe on, not in, a heavy
  aluminium block or a pot of dry sand, with the lid off. Kitchen ovens cycle
  ±5–10 K; the block damps what the cell sees.
* **Cable out through the door gap** to the node, or read over BLE. The BLE
  keeper is a lab tool and is fine for this. It is disabled at the pile.
* **Barometric pressure logged** at start, middle and end (phone or weather
  service). Rev A has no barometer, and the firmware assumes 930 hPa.
* **Heater:** leave the shipped dew law as it is. In dry oven air the dew
  margin is tens of kelvin and the law should not heat. `gas_heater_duty_pct`
  must read 0 through every hold; a hold with non-zero duty is void. Changing
  heater registers, or any probe state, needs Fab's explicit word.

## 4. Sequence

Holds in °C of **cell-side T_EXT**, not oven setting. First up, then down
(`~/dev/kb/measurement/unsettled-updown-ladder-identifies-tempco.md`): a
lag artefact reverses sign between the two legs, and a real response does not.

| # | hold | where |
|---|---|---|
| R1 | ambient, ≥ 30 min | bench, oven closed but off |
| H1 | 40 | oven |
| H2 | 50 | oven |
| H3 | 60 | oven |
| H4 | 70 | oven (outside cell rating; see §6) |
| H5 | 80 | oven, **only on Fab's go at the time** |
| D1 | 60 | oven, descending |
| D2 | 40 | oven, descending |
| R2 | ambient, ≥ 60 min | bench, after cooling |

**A hold counts once all of these are true:**
* ≥ 30 min at the setting;
* the last 10 min have |dT_EXT/dt| < 0.05 K/min;
* T_EXT, chamber and T_AFE agree within 1 K;
* heater duty is 0;
* faults are only 0 or 512.

Use the mean of those last 10 minutes.

**Bracketing:** R1 and R2 must agree within 0.3 % dry-corrected, or the run
drifted and every hold is suspect. On 09-11 a steam exposure moved the
baseline 2.2 %.

## 5. Predictions, recorded before the run

Current relative to R1, dry-corrected, if the firmware's law is right:

| T | 40 | 50 | 60 | 70 | 80 °C |
|---|---|---|---|---|---|
| (T/298.15)^0.75 | +3.8 % | +6.2 % | +8.7 % | +11.1 % | +13.5 % |

If the 09-11 cooling pass holds: about +5 % at 50–52 °C, +3…+4 % at 60 °C,
and flat or falling beyond. That pass has no settled point below 52 °C, so it
predicts nothing at 40. The two predictions separate by ≈ 5 % at 60 °C and by
more above. The log resolution is 0.01 µA and the day scatter ±0.15 %, so either
outcome is decisive.

The expected dilution in dry oven air is small. Room air at ~10 hPa gives
RH 13.6 % at 40 °C and 2.1 % at 80 °C. p_w is unchanged by heating, so
dilution stays at ~1.1 % throughout and nearly cancels against R1.

## 6. Risks and aborts

* **This is the only probe, and it is the one in the pile.** Heat already
  destroyed it once: warm solvent from drying the coating at 09-11 22:24 took
  out U8, U3 and R36. The coating has had since 09-11 to cure, and the 86 °C
  soak on 09-12 came before the repair. Before the pile, the repaired board
  (repair closed 09-12 19:17) peaked at **49.4 °C AFE and 48.6 °C cell side**
  on 09-17 11:58. Its 66.9 °C on 09-13 09:50 was the heater on the tip, with
  the cell at 23.9 °C. The pile is already taking it further: 73.7 °C chamber
  on 09-17 evening. Hence the slow ladder, with H5 on explicit go.
* **Cell above its rating** at H4–H5, and dry below 15 %RH (rated 15–90 %
  continuous, 0–99 % short term). Keep H4 and H5 to the minimum hold. The
  09-13 steam exposure showed full recovery. The cell has already sat ~6 h dry
  at 76 °C cell side (09-11 22:51 – 09-12 04:50, RH 6 %), but its current was
  unreadable then (failed ADC). Any lasting effect is folded into the
  09-13 air calibration and cannot be separated from the repair.
* **Abort immediately and pull the probe to ambient on any of:**
  * a fault other than 512 (e.g. 2048 ADC_RANGE, VA_LOW, I²C errors);
  * `settle_s` restarting;
  * cell current outside 80–120 µA;
  * link loss > 5 min;
  * T_AFE > 85 °C.
* **No humid point in this run.** A water pan at 60 °C gives RH that nobody
  controls, and condensation when the oven cools. The pile case (p_w ≈
  300 hPa at 74 °C, 82 %RH on 09-17) needs its own design, later.

## 7. Analysis

1. Export `gas_cell_ua`, `gas_t_ext_c`, `gas_t_chamber_c`, `gas_t_afe_c`,
   `gas_rh_chamber_pct`, `gas_faults`, `gas_settle_s` and
   `gas_heater_duty_pct` from VictoriaMetrics (`/api/v1/export`: real points,
   not range-query steps).
2. Dry-correct each point with the measured barometric pressure:
   I_dry = I / (1 − p_w/P), p_w from SHT45 T and RH (Magnus).
3. Hold means per §4. Ratios to the mean of R1 and R2.
4. Compare against §5. Fit (T/T_ref)^n and a quadratic in T. Report n with its
   uncertainty from the hold-to-hold scatter, not from the sample count; the
   samples are autocorrelated.
5. Show up and down legs separately. If they disagree by more than the
   scatter, the holds were not settled; do not average them.
6. `firmware/tools/o2p_tempco.py --mode cell --cell-temp ext` gives the
   AFE/cell split only if the two moved differently. In an oven they will not,
   and the tool should say so.

## 8. What it changes

* **Result close to the law (ratio within ±1 %):** keep the conversion. Pile
  readings at 70 °C stand as published, and the TEMP_OVER extrapolation is
  supported.
* **Result close to the 09-11 pass:** the firmware under-reads hot, by about
  5–8 % of the value at 60–75 °C. Fix it by replacing the exponent above a
  crossover, or by a fitted table, **not** by writing a residual into
  TEMPCO_PPM_K (review F1, double counting). Backfill the pile series to a
  NEW VM metric name; re-importing a used name is destructive at 1 ms dedup.
* **Either way:** add a dated section to
  `docs/2026-09-11-o2-model-fit-vs-truth.md`, and update the farming memory
  note `o2-cell-tempco-is-unmeasured`.
