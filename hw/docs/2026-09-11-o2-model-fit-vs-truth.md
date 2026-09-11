# The O₂ model tested against a known truth, 2026-09-06 … 09-10

**Revised 2026-09-11 after an independent Codex review**
(`~/codex-reviews/o2-model-fit/`, xhigh, network + browser, exit 0). The review
broke two of this document's claims and forced six fixes in the tool; §3's
headline is materially weaker than the first version's. §8 lists the changes.

**The probe was in ambient air for every bench run in this window** — room,
oven vessel, freezer — so the **dry-basis** oxygen fraction was 20.946 %vol, at
every temperature and every humidity. Water vapour cannot move it: the dry
basis is defined water-free. Spread in the published number across the sweep is
therefore system error, and no reference instrument is needed to see it.

**That premise is an experimental assumption, not an observation** (review
finding 1). Telemetry cannot exclude a changed dry composition — O₂ consumed,
CO₂ added — nor establish ventilation, nor measure the actual total pressure,
and there is no barometer. Nothing suggests any of those happened, but read
"the spread is model error" as "the spread is *system* error, of which the
model is one term". §4's rigid-vessel argument bounds the pressure term at one
end only.

**The two water-cooker tests of 09-10 are the exception** (§7): there the gas
was near-pure steam and the dry basis is undefined. Both are excluded by the
fault and settle guards before any fit sees them; §7.3 shows the rows.

Data: VictoriaMetrics `gas_*{probe="3"}`, 2026-09-06 23:12 … 2026-09-10 23:11
UTC — 11 686 uplinks, **10 760 usable**. Tool: `bench-logs/o2_model_fit.py`.
Rows dropped when `settle_s` is non-zero **or absent**, when faults intersect
`O2P_FAULTS_INVALIDATE_O2` (0x6866), when VREF was outside 2450–2550 mV, and —
for the truth test — when the temperature *range* over a ±5 min window exceeds
0.1 K/min, because the cell body lags the gas by ~18 min.

## 1. What the probe is actually running — and that it changed

`gas_pct_vol` is a function of the published `gas_cell_ua`, `gas_t_chamber_c`
and `gas_rh_chamber_pct` through `o2.c`, so an equivalent (K, α, tempco) can be
recovered from telemetry without a Modbus read. It closes to **0.003 %vol rms**
in every window.

| window (UTC) | n | K, nA | α | tempco, ppm/K |
|---|--:|--:|--:|--:|
| 09-06 23:12 … 09-07 16:56 | 8463 | 431 509 | 0.388 | +2859 |
| 09-08 10:36 … 14:25 | 237 | 431 478 | 0.388 | +2859 |
| 09-09 14:21 … 16:14 | 398 | 428 615 | **1.001** | **+1** |
| 09-10 18:12 … 21:31 | 120 | 416 554 | **1.000** | **0** |
| 09-10 21:58 … 22:59 | 51 | 416 587 | **1.001** | **+3** |

**This identifies behaviour, not registers** (review finding 5). The triple is
not unique: the tool assumes zero offset current, P = 930 hPa and a 25 °C
reference, while the firmware carries `CAL_ZERO_NA`, `CAL_TEMP_C100`,
`CAL_AIR_FRAC` and a `CAL_P_HPA` normalisation. `CAL_AIR_NA` and `CAL_AIR_FRAC`
are inseparable inside K; moving the reference temperature transforms K *and*
the numerical tempco; and an unknown configured pressure gives an exact α/P
ambiguity — α = 1 at 930 hPa is indistinguishable from α = 1.075 at 1000 hPa.
On the 09-09 window α ∈ {0.99, 1.00, 1.01} all fit at 0.0029 %vol.

**What survives is the change itself, and it is strongly supported.** Holding
α = 0.388 and refitting K and tempco gives 0.042 %vol rms on 09-09 and
0.537 %vol on the broad 09-10 window, against 0.003 — the old settings did not
continue. The probe's behaviour after the AFE-rework reflashes is
*indistinguishable from* `O2P_DIL_ALPHA_DEFAULT` (1.0) and
`O2P_TEMPCO_DEFAULT` (0), and distinguishable from what it ran before.

**What does not follow:** that a reflash *caused* it, or which registers to
write. That needs a readback — one `o2p-cmd read 0x0037:16`. Until then, treat
"the per-probe oxygen constants are not in force" as established and the
mechanism as unproven. Nothing in the fault word reports this: `CAL_DEFAULT`
covers only `CAL_AIR_NA`.

K's own −3.5 % step is **a fresh air point taken on the morning of 09-10**, not
the coating and not drift; §7.2 dates it and shows K stable to 0.01 % since.

## 2. The model against the truth, per config era

Spread = max − min of the model output over the window, relative. The *mean* is
left out on purpose: it is the air point's scale error, not a model property. K
is refitted per column, so each variant is judged on shape alone — read across
the rows, not down the columns.

| era (UTC), probe config | steady n | T span | published | α=1, tc=0 | α=0.402, tc=0 | no vapour corr | best fit |
|---|--:|---|--:|--:|--:|--:|--:|
| 09-06 23:12…09-07 20:49, α .388 tc 2859 | 8462 | 21.6…42.2 °C | **0.81 %** | 4.53 % | 4.66 % | 4.89 % | 0.42 % |
| 09-08 10:36…14:25, α .388 tc 2859 | 184 | 28.6…77.8 °C | **9.36 %** | 7.09 % | 4.47 % | 3.35 % | 1.66 % |
| 09-10 18:12…22:59, defaults | 45 | −21.0…79.8 °C | **19.43 %** | 18.49 % | 12.63 % | 9.44 % | 4.82 % |

Two windows the first version reported are now refused: 09-07 21:56…09-08 06:34
(T span 2.6 K) and 09-09 14:21…16:14 (2.2 K), both under the 8 K minimum. A
spread quoted over 2 K says nothing about a model whose error is a function of
temperature.

**Three results:**

1. **In the 22–42 °C band the flashed config was good**: published spread
   0.81 % over 8462 samples, ±0.09 %vol on a 20.9 %vol reading. The model is
   not broken; it is *locally* calibrated.
2. **It does not extrapolate.** The same config at 77.8 °C published
   **19.05 %vol** in air — 9.0 % low.
3. **On defaults, over the full −21…+80 °C sweep, the vapour correction as
   configured makes the answer worse than not correcting at all**: 18.49 %
   spread at α = 1 against 9.44 % with the correction off. That is the
   threshold argument in `o2.h` (α = 1 beats no correction only above
   α = 1/(1+f) ≈ 0.545) showing up in data. It is a descriptive result about
   these samples with K refitted per variant — not, on its own, proof of the
   fixed-condition threshold. The published series ran **19.23 … 23.30 %vol**
   in air.

The best-fit column also shows the parameters are not shared: 22–42 °C wants
(α 0.458, +2490 ppm/K), 29–78 °C wants (α 0.101, +672), the full sweep wants
(α 1.309, +2506). **A model whose coefficients must be refit per band is a
curve fit, not a correction** — and this result does not depend on α being
separately identified.

## 3. α — one clean determination, and one that is not identified

α and the temperature term are correlated over any window that moved both, so
only a segment with temperature *pinned* can identify α. Slope of `ln I`
against p_w/P, converted to the concentration domain by the cell law's local
gain d ln S/d ln C = 1.1273 (verified algebraically in review; the sign
convention is correct).

The scanner now enumerates **every maximal isothermal window** rather than one
greedy partition, because the greedy answer depended on where the export
happened to start (0.398 from midnight, 0.496 from 06:30, none at all from
07:00 — review finding 7). The spread across windows is the **procedure
spread**, and it is the honest error bar; a single regression's ± is not.

| cluster | windows | procedure spread | longest window | α (no drift term) | with drift term |
|---|--:|---|---|--:|--:|
| ~22 °C | 39 | **0.136 … 0.509** | 09-07 06:49…08:24, n = 1778 | 0.398 ± 0.003 | 0.444 (−0.03 %/h) |
| ~28 °C | 3 | 0.247 … 0.512 | 09-08 13:20…14:05, n = 89 | 0.247 ± 0.042 | −0.168 (+0.47 %/h) |
| ~34 °C | 1 | — | 09-09 15:03…15:07, n = 46 | *rejected*, +17.8 %/h drift | — |
| ~78 °C | 1 | — | 09-08 10:36…12:18, n = 91 | 0.099 ± 0.015 | 0.196 (+0.47 %/h) |
| ~80 °C | 1 | — | 09-10 19:39…20:07, n = 26 | *rejected*, −12.9 %/h drift | — |

**At room temperature α is real and low.** Thirty-nine windows, the longest
three (n > 1700) all landing 0.398–0.415, the heater off throughout so no duty
confound can exist, drift below 0.03 %/h. Call it **α ≈ 0.40–0.45 at 22 °C,
procedure spread 0.14–0.51** — well below 1, which is the operationally
important part.

**At 78 °C α is NOT identified, and the first version of this document was
wrong to claim it was** (review finding 2). Holding 78 °C requires the ring
heater, and in that window the heater duty falls 66 → 38 % as humidity rises:

```
09-08 10:36..12:18  n=91  T span 0.18 K  duty 38..66 %  corr(p_w/P, duty) = -0.910
  regressors: p_w                 alpha = +0.099 +/- 0.015   rms 0.267 %
              p_w + time          alpha = +0.196 +/- 0.019   rms 0.217 %
              p_w + duty          alpha = -0.144 +/- 0.024   rms 0.170 %
              p_w + time + duty   alpha = -0.708 +/- 0.073   rms 0.130 %
```

The residual improves at every step, so no term is obviously spurious, and α
swings from +0.20 to −0.71. Duty is not a nuisance variable: it *is* heater
power into the tip, so the cell body temperature moves with humidity even at
fixed chamber and tip temperature. Nothing in the data measures the cell body,
so this cannot be resolved from the export. The 22.4 °C window is clean of it
only because the heater was off.

**So "α falls with temperature" is a hypothesis, not a measurement.** The
pointer in `O2-HUMIDITY-CORRECTION.md` has been corrected to say so. Two things
that are *not* the explanation, both far too small: the Magnus extrapolation
(NIST's saturation table gives 431.68 hPa at 77.7 °C against Magnus 436.01, so
Magnus is **1.00 % high** — and correcting it moves the inferred α *up*, i.e.
in the direction that partly explains a low estimate, not against it), and a
chamber thermal gradient (the correction depends on p_w, uniform in a mixed
volume). The SHT4x's own accuracy is *not* dismissible: 1–13 %RH at 78 °C is
outside Sensirion's 5–60 °C / 20–80 %RH recommended range, and this document
does not budget that uncertainty.

**Provenance of the two prior repo numbers, corrected.** §12 of
`O2-HUMIDITY-CORRECTION.md` (the 13:20Z vessel transfer) reports obs/pred = 0.60
of the current change, i.e. α = 0.60/1.1273 = 0.53; the scanner's window
spanning that transfer gives **0.572 ± 0.039** (`--iso-span-k 1.5`), consistent
within the procedure spread. §15's regression yields 0.453 in the log domain,
α = 0.402; the tightest window here gives 0.398, log-domain 0.449. Both
reproduce. *The first version attributed the 0.538 figure to §12's window; it is
not that window, and the claim is withdrawn.*

`firmware/tools/o2p_backfill_dry.py` is **current and correct** — it prefers the
probe's own `DIL_ALPHA` and cites 0.402, mentioning 0.60 only as history. The
first version criticised a `--response 0.60` recommendation that exists only in
the **stale farmgw copy** (`~/blepush/o2probe/o2p_backfill_dry.py`, md5
`0f774f93…` against the repo's `673a9eb6…`), which also still hardcodes
K = 425 557 nA. That copy would now produce a mis-scaled backfill; it is the
standing drift `farmgw-verify.sh` exists to catch.

## 4. The temperature term — a joint parameter, not a measured coefficient

### 4.0 Every temperature this analysis regresses on is a BOARD temperature

Raised by Fab, 2026-09-11, and it is the most consequential correction to this
document after the review. TMP117 (tip) and SHT45 (chamber) are **on the PCB**,
a few millimetres from the ring heater. The ADS1119 die (`T_AFE`) is further
along the same copper. **The cell is on flying leads** — the highest thermal
resistance of the three, and coupled to the gas rather than to the board.
Nothing in the telemetry measures the cell.

> **Addendum 2026-09-11 afternoon — the cell now has a thermometer.** A second
> TMP117 (ext I2C 0x4A, register 0x001F `EXP_DATA`) is attached to the side of
> the cell enclosure, on the side **far from the pins** (Fab) — the end away
> from the lead path to the board. Which end is the sensing face is **not
> settled**: the DS-0637 Issue 2 drawing marks DO NOT OBSTRUCT on both faces
> (the large opening opposite the pins, and the small pin-face port that
> `DESIGN.md:735` calls the rear gas port and the board's flow slot serves),
> and names neither as the membrane. It reads the outside of the ABS housing,
> not the electrolyte; its lag behind the electrolyte is **unmeasured**.
> Published as `gas_t_ext_c` from 13:43 (before that, raw centi-°C in
> `gas_exp_data`, mostly solder heat); fit with `o2p_tempco.py --mode cell
> --cell-temp ext`. The sentence above still holds for every dataset in this
> document — all of it predates the sensor.
>
> **Not new, but not carried into this tree:** DS-0637 Issue 2 carries a
> temperature chart ("%20°C Output vs Temperature", −40…60 °C, mean ±3σ, PDF
> page 2). `compostlab/o2-probe/O2-CORRECTION-MODEL-BUDGET.md` §5 recorded it
> on 2026-09-07/08 with eyeballed readings — ≈ +0.2 %/K, flattening above
> 40 °C, **UNVERIFIED** — and named `dsdig` digitisation as the next step; it
> has not been done. `2026-09-08-hot-bath-run.md:144` ("no tempco curve at
> all") cites Issue 1; the firmware comments carried the same Issue 1 claim. Published as `gas_t_ext_c` from 13:43
> (before that, raw centi-°C in `gas_exp_data`, mostly solder heat); fit with
> `o2p_tempco.py --mode cell --cell-temp ext`. The sentence above still holds
> for every dataset in this document — all of it predates the sensor.

The ladder is visible in the data, and its rungs depend on *where the heat
enters*:

| regime | dT_AFE / dT_TIP | n |
|---|--:|--:|
| heater driving (duty > 20 %) | **0.286 ± 0.021** | 34 |
| heater off, ambient excursions | **0.708 ± 0.076** | 158 |
| 09-10 21:11…22:59, freezer and warm-up only | 0.632 ± 0.042 | 46 |

The 20:51 step makes it concrete: tip 29.8 → 79.9 °C in two minutes while the
AFE reaches only 48.9 °C — 39 % of the move, still climbing. Heat injected at
the tip produces a standing gradient across the board; ambient excursions
carry every node together. **The cell sits beyond the AFE on that ladder, so
under heater drive it must see less than 0.29 of a tip excursion, with a
longer time constant** (the fitted lag is τ ≈ 1080 s against the AFE's
visible one-to-two minutes).

**Consequence 1 — the "band-dependent" tempco is probably one coefficient,
mis-referenced.** §4's two bands differ in regime, not only in temperature:
22–42 °C is heater-off (regressor ≈ cell temperature, apparent +2490 ppm/K),
29–78 °C is heater-driven (regressor is a board node moving several times more
than the cell, so the apparent coefficient is divided by that ratio, +672
ppm/K). The ratio required to reconcile them is 2490/672 = **3.7**, i.e. the
cell seeing 27 % of the board's swing — against the 0.286 measured for the AFE
under heater drive. That is a consistency argument, not a measurement, because
no cell temperature exists; but it explains the band dependence better than
the cell's physics changing between 40 and 70 °C.

**Consequence 2 — the 78 °C window was isothermal on the BOARD only.** The
control loop pinned tip and chamber to ±0.09 K while duty fell 66 → 38 %, so
the *heat flux* through the assembly fell and the cell cooled even though both
sensors did not move. This is the physical mechanism behind the review's
statistical finding (§3): duty is not a nuisance regressor, it is the only
available proxy for cell temperature. The 22 °C windows are clean precisely
because the heater was off, so no gradient existed and the board sensors *did*
represent the cell. **There is therefore no α determination at high cell
temperature in this dataset — the hot estimate was taken at an unknown cell
temperature well below 77.7 °C.**

**Consequence 3 — the deployed probe lives permanently in the bad regime.**
Buried, the RH loop drives the heater continuously, so the pile case is the
high-gradient case. Worse, the firmware's own tempco regressor is
`o2p_gas_temperature()` — chamber-else-tip, both board nodes dominated by the
heater (`main.c:1049`). In the pile, the input to the temperature correction
is largely *heater state*, not gas temperature. A coefficient fitted on a
heater-off bench and applied in a heated pile is referenced to the wrong
temperature by roughly the factor above.


Per band, with α free alongside it: **+2490 ppm/K over 22–42 °C**, **+672 over
29–78 °C**, **+2506 over −21…+80 °C**. These are joint-fit parameters,
correlated with α within each band; quote the pair or neither.

`o2p_tempco.py --mode cell` on 09-09…09-10 splits the AFE from the cell for the
first time (T_AFE span 83.7 K, r = 0.807, 740 rows):

```
AFE tempco  +230 +/- 110 ppm/K
cell, apparent, per K of lagged chamber temperature  +797 +/- 95 ppm/K
combined on T_AFE alone  +974 +/- 68 ppm/K      R2 0.286, residual 2.385 uA rms
```

**Those error bars are too small and the split is not established** (review
finding 3). The standard errors assume independent residuals; adjacent
residuals correlate at **0.852** within 120 s, and clustering into 10-minute
blocks inflates them to roughly **±472 / ±340 ppm/K**. The lag τ is selected on
the same data used for the uncertainty, and moving it from 600 to 1800 s moves
the AFE share from **124 to 457 ppm/K** with almost no change in residual. So:
the combined dependence is around +1000 ppm/K and real; "the AFE contributes
about a quarter" is a plausible reading of one fit, not a measurement. It does
not close the gate of `2026-09-09-afe-tempco-plan.md` — the dummy-cell run
still would.

**Not a rigid sealed vessel.** A rigid sealed vessel taken over the 09-08
heat-up's actual endpoints, 26.19 → 77.70 °C, raises P by 350.85/299.34 =
**+17.2 %** and would masquerade as +3300 ppm/K. Measured over exactly those
endpoints: **+3.5 %** of current (101.05 → 104.62 µA, 09-08 09:37 → 09:57).
That bounds the strong case; it assumes the whole enclosed inventory saw the
chamber sensor's rise, and slow venting stays unconstrained.

## 5. What to do

1. **Read the config back** — `0x0037:16` — before writing anything. §1
   establishes that the behaviour changed, not which registers hold what.
2. **Do not flash an α from this document.** 0.40 is defensible at room
   temperature; nothing here supports a value for the 40–65 °C band, and the
   78 °C estimate is unidentified. What *is* supported: α = 1 is the worst
   available choice over a wide temperature range.
3. **The missing measurement is an isothermal RH sweep at pile temperature**,
   designed against §3's failure: verified gas exchange, the cell's thermal
   state held or measured (not merely the chamber's), humidity moved in **both**
   directions, heater duty logged and ideally constant, settling judged by an
   observed criterion. **At τ ≈ 18 min a 30-minute hold leaves 19 % of a
   first-order transient** — budget ≥ 3τ, an hour per point.
4. **A cell-body thermometer is the fix for §4.0, and it has to be ON THE
   CELL.** All three existing sensors are board nodes on one heat path, so no
   combination of them substitutes; adding a fourth board sensor would buy
   nothing. Not another I²C device either — that bus already carries four
   parts and has died twice; an NTC or PT1000 into an MCU ADC channel is the
   right shape (ADS1119 AIN0–AIN3 are all in use). ~0.2 K resolves 1000 ppm/K
   to a few percent, so the sensor's accuracy is not the hard part; the
   thermal bond to the cell can is.
5. **Re-measure on the probe as it now is.** Every α in §3 is from an uncoated,
   pre-rework board (§7.1). The air point was retaken on 09-10 and has held to
   0.01 % across the coating, a freezer soak and a 100 °C steam blast (§7.2),
   so the scale is not what needs redoing.
6. **Next cheap run: overnight outdoors** (§7.4).

## 6. Provenance

`bench-logs/o2_model_fit.py --export gas.ndjson --plot …`, figure
`bench-logs/o2-model-fit-2026-09-11.png`. Export command in the tool's
docstring.

Every number in §1–§3's tables is printed by that tool. The exceptions, named
because the first version claimed otherwise: the duty-regressor block in §3 and
the block-clustered error bars in §4 come from diagnostic runs, not the tool;
the AFE/cell split is `firmware/tools/o2p_tempco.py`; the NIST saturation value
was fetched live during review; the heat-up endpoints in §4 are `gas_*` at
09-08 09:37 and 09:57.

The tool refuses rather than answering when a window has fewer than 40 steady
rows, spans under 8 K, or its config recovery exceeds 0.02 %vol — and, since
the review, a window whose recovery **failed** can no longer reappear as an era
in §2 (it previously printed `UNEVALUABLE` and then a confident spread anyway),
a missing `settle_s` no longer reads as zero, a mixed-probe export is refused
instead of silently merged, a fit that lands on a bound is labelled, and the
steady mask measures the **range** over its window rather than the difference of
its endpoints (an 80 K symmetric excursion used to score as steady).

## 7. Hardware history that the data has to be read against

**The board is conformally coated, and the coated probe survived a 20 s exposure
to 100 °C water vapour in a water cooker.** Fab, 2026-09-11: the coating went on
*right after the last VREF failure was fixed, which followed the first
water-cooker test*. That closes the "coating verdict" open item of the 09-10
evening log — and it dates the coating inside the telemetry, because both the
failure and the fix are visible in it.

### 7.1 The timeline, from the telemetry

| UTC 09-10 | what | evidence |
|---|---|---|
| 15:00:12 | **first water-cooker test** — last good sample reads T 47.0 °C, RH 92 %, cell 91.85 µA | `gas_*` |
| 15:01:12 | VREF invalid (65535), faults `0x811f`; the cell stops publishing | fault word |
| 15:40 … 18:02 | VREF **collapsed**, reading 186 → 338 mV and creeping up | `gas_vref_mv` |
| 17:48 … 18:01 | bake, 100 % duty, chamber 75–78 °C at RH 1–4 % | `gas_heater_duty_pct` |
| **18:02:13 → 18:03:13** | **VREF recovers, 210 → 2494 mV** — the fix | `gas_vref_mv` |
| 18:07 | cell current back to 103 µA, `pct_vol` publishing again | `gas_cell_ua` |
| *right after* | **coating applied** | Fab, 2026-09-11 |
| 18:12 … 22:59 | the −21…+80 °C sweep of §2 row 3 | — |
| 23:01 … 23:11 | **second water-cooker test**, 20 s at 100 °C — survived | §7.3 |

So the split is clean: **§2's last row and every 09-10 evening number are the
COATED probe. Every α determination in §3, and both narrow bands in §4, are
PRE-coating** — 09-07 and 09-08, before the AFE rework as well. There is **no
usable post-coating α**: the only post-coating isothermal window (19:39–20:07
at 79.7 °C) sits on −12.9 %/h of VREF-recovery drift.

### 7.2 The coating did not move the scale

K recovered per window across the coating, same method as §1 (residual
0.003 %vol throughout):

| window (UTC 09-10) | n | K, nA | relative to 14:31 |
|---|--:|--:|--:|
| 09:00 … 12:00 | 40 | 416 543 | — |
| 14:31 … 15:01 — **pre-coating** | 20 | 416 535 | — |
| 18:07 … 19:00 — **post-coating** | 28 | 416 543 | **+0.002 %** |
| 19:34 … 21:31 | 70 | 416 556 | +0.005 % |
| 21:58 … 22:59 | 51 | 416 587 | +0.012 % |

**K is unchanged across the coating to 0.01 %**, through a first water-cooker
test, a VREF collapse and recovery, a coating, a freezer soak and a 100 °C
steam blast. Coating in or near the cell socket narrowing the diffusion
capillary — the obvious worry — would show here first, and it does not. It does
not formally exclude a changed α, but a restriction that changes transport
without changing the air-point current is a strained hypothesis.

**The −3.5 % K step therefore is not the coating.** It happened between 09-09
16:14 (428 615 nA) and 09-10 09:00 (416 543 nA), and `CAL_DEFAULT` (fault bit
12) is raised in the 06:00–08:00 hours of 09-10 and gone by 09:00 — the
calibration was lost and a **fresh air point** was taken that morning. Scale
history: 431 500 (through 09-08) → 428 615 (09-09, post-rework) → 416 543
(09-10 morning, recalibrated), stable since.

### 7.2a The first coating was PARTIAL — a second one followed on 09-11

Fab, 2026-09-11: **"the board analog circuitry is now fully coated."** So the
coating dated to ~20:00 on 09-10 in §7.1 was not full coverage, and the timeline
has two coating events, not one:

| when | what | evidence |
|---|---|---|
| 09-10 ~20:00 | **first coating**, after the last VREF failure was fixed | VREF collapse 17:46–19:47 (192–336 mV), recovery to 2492 mV at 20:17 |
| 09-11 01:07 | VA_MON begins decaying — 5 h after that coating, on a node it did not cover | `va_mv` 3282 → 2008 mV, `VA_LOW` latched 7 h 54 min |
| 09-11 ~09:15 | air-gun + clean; `va_mv` recovers 1338 → 3282 mV in one frame | `2026-09-11-va-mon-collapse.md` §2.1 |
| 09-11 ~09:34 | **second coating — analog section now full** | VREF dipped to 2418 mV for one minute, `ADC_RANGE`, settle re-armed (inferred, not stated) |

This matters for reading §7.2 above. "The coating did not move the scale" was
measured across the **first, partial** coating, so it is evidence about that
coverage only. The 09-11 coating is wider and has **not** been tested against K
— no post-09:34 window long enough to refit exists yet, and the probe is at
room temperature with the heater off, so nothing is being driven across the
range that would expose a transport change.

**Retest K when the next heated run happens.** The §7.2 method applies
unchanged: refit K per window, residual under 0.003 %vol, compare against
416 543–416 587 nA. A capillary restriction from the wider coat would appear
there first, exactly as the earlier worry predicted and did not find.

The falsifiable prediction that the second coating creates — whether a fully
coated analog section stops the VA_MON leak recurring, and what a recurrence at
~14:30 would instead implicate — is in `2026-09-11-va-mon-collapse.md` §7.1.
Its one extent question is answered: Fab confirmed R24/R25, the VA_MON divider,
are inside the coating.

### 7.3 The steam test, and why it is not in any fit

```
22:59:00  T 48.2 C  RH 85.5 %  I 96.81 uA  faults 0x8000            used
23:00:00  T 47.6 C  RH 85.9 %  I 98.29 uA  faults 0x8800  ADC_RANGE excluded
23:01:00  T 62.6 C  RH 96.1 %  I 88.00 uA  faults 0x8e00            excluded
23:05:01  T 68.7 C  RH 96.3 %  I 70.15 uA  faults 0x8a00            excluded
23:07:01  T 65.5 C  RH 95.7 %  I 79.66 uA  faults 0x8241  VA_LOW +
                                            settle_s 900            excluded
23:11:02  (last uplink of the era)
```

Chamber temperature and humidity step together at 23:01, the cell current
collapses to 70 µA, and `settle_s` goes to 900 — the cell bias was interrupted,
which is what a saturated 60–70 °C blast should do. The SHT45 peaks at 68.7 °C
rather than 100 °C: it lags, and its reading is the chamber, not the steam.
Every row is dropped by the fault and settle guards, not by hand. **The oxygen
numbers in that window are not measurements** — p_w approaches P, the dry basis
stops meaning anything, and the firmware's own `O2P_VAPOUR_MAX_PW_FRACTION`
refusal is the correct behaviour.

### 7.4 What this changes

1. **The constants in §1–§4 belong to an uncoated, pre-rework probe** for §3
   and §4. Before any of them is flashed, α has to be re-measured as the probe
   now is.
2. **The coating removes the standing objection to a condensing run.** The
   failure that killed the I²C bus twice on 09-10 was moisture on a bare board;
   a coated board that took 20 s of 100 °C steam can be left in a dew-forming
   environment overnight. What the coating does **not** protect is the cell
   itself (rated 15–90 %RH, non-condensing), its socket, or liquid pooling in
   the chamber — and 20 s of steam is not 10 h of condensation, which is a
   slower, different failure mode.
3. That makes an **overnight outdoor run** the cheapest way to get what the
   model lacks. Outdoors, temperature falls 7–10 K overnight while RH rises to
   compensate, so p_w stays nearly constant (~12 → 10 hPa, 0.2 % of P): a
   near-pure temperature lever in the relevant range, **with the heater off** —
   which is exactly the confound that wrecked §3's hot estimate. Dawn supplies
   the up-then-down loop that
   `~/dev/kb/measurement/unsettled-updown-ladder-identifies-tempco.md` says
   breaks this degeneracy. It stays in ambient air, so §2's truth test re-runs
   unchanged, and it characterises the coated probe. It is also a coating
   endurance test and should be run as one on purpose.

## 8. What the review changed

Codex xhigh, `~/codex-reviews/o2-model-fit/{prompt.txt,review.log}`, exit 0,
with live VictoriaMetrics access and a browser (NIST saturation table, SHT4x
datasheet; SGX's site timed out and stayed `unverified`).

**Broken, and fixed here:** the 78 °C α was presented as identified when it is
confounded with heater duty at r = −0.910 (§3); the §12 provenance of the 0.538
figure was wrong and is withdrawn (§3); the criticism of `o2p_backfill_dry.py`
described a stale farmgw copy, not the repo file (§3); Magnus is 1.00 % above
NIST, not 1.8 %, and the direction of that correction was stated backwards
(§3); the rigid-vessel figure now names its endpoints (§4); usable rows are
10 760.

**Guard defects, fixed in the tool:** a failed config recovery could still
become an era with a confident spread; a missing `settle_s` read as zero; the
steady mask compared window endpoints, so a symmetric excursion of any size
passed; a mixed-probe export merged silently; fits on a bound printed as
values; the isothermal scanner's answer depended on the export's start.
Re-running after those fixes moved several numbers — §2's steady counts and the
09-10 spreads — and widened §3 from a single ±0.003 to a procedure spread of
0.136–0.509.

**Survived:** the config-table reproduction and the defaults-like conclusion,
the cell-law gain and sign, the fault-mask arithmetic, the dry-basis
conversion, the room-temperature α, and §2's central result that no fixed
parameter pair serves both bands.

## 9. Do higher-order models serve? (Fab's question, 2026-09-11)

§2 said no fixed parameter pair serves both bands. The obvious next move is
α(T) and tempco(T). **Tested, and it does not work** — and §4.0 says why it
cannot.

### 9.1 Cross-band prediction, which is the only honest test

Fit on one band, predict the other, unchanged. Both bands are the same probe,
same config, same era (A: 09-06/07, heater **off**, 21.6–42.2 °C, n = 8462.
B: 09-08, heater **driven**, 28.6–77.8 °C, n = 184).

| model | in-band rms | fit A → predict B | fit B → predict A | pooled A+B rms |
|---|--:|--:|--:|--:|
| fixed α, fixed tempco | 0.05 % | **4.38 %** | **0.73 %** | 0.25 % |
| α linear in T | 0.04 % | 2.06 % | 0.76 % | 0.23 % |
| α and tempco both linear in T | 0.04 % | 3.15 % | 1.73 % | **0.09 %** |

The four-parameter model is the **best** in sample (0.09 % pooled) and the
**worst** out of band in both directions. In-band rms barely moves at all
(0.05 → 0.04 %), because the two-parameter model already fits its own band to
the noise floor; the extra freedom buys nothing there and buys negative
predictive value elsewhere.

Worse than the rms: the added coefficient's **sign flips with the fitting
window**. dα/dT is +0.0218 /K fitted on A, −0.0032 /K fitted on B, +0.0103
pooled at third order, −0.0061 pooled at fourth. A parameter whose sign
depends on which half of the data you show it is not describing the cell.

### 9.2 Why no order of polynomial can work in this variable

§4.0 is the reason, and it is a statement about functions, not about fit
quality. The model's temperature input is a **board** node. The cell's
temperature is not a function of it: the board→cell map depends on heater
state (dT_AFE/dT_TIP is 0.286 under drive against 0.708 on ambient), and on
history through an ~18-minute lag.

The 78 °C window makes it airtight. There the board temperature is **constant
to ±0.09 K** while the cell demonstrably moves — duty falls 66 → 38 % and the
current changes. Any function of board temperature, of any order, is constant
across that window. It cannot reproduce a change. **Higher order in the wrong
variable is unreachable, not merely inefficient.**

### 9.3 The move that does work is fewer parameters, not more

For a capillary/Stefan-diffusion-limited cell — which is what the log law
`S = K·ln(1/(1−C))` in `o2.h` already asserts this cell is — the limiting
current at fixed mole fraction and fixed total pressure follows from
Chapman–Enskog directly:

```
J = D dC/dx,   D ~ T^1.75 / P,   C ~ x·P/RT    =>    I ~ T_K^0.75
d lnI/dT = 0.75/T :   +2516 ppm/K at 25 C,  +2321 at 50 C,  +2138 at 77.7 C
```

Against the heater-off band, where the regressor is trustworthy:

| band A model | free parameters (besides K and α) | rms | spread | α |
|---|--:|--:|--:|--:|
| fitted linear tempco | 1 (+2490 ppm/K) | 0.05 % | 0.42 % | 0.458 |
| **I ∝ T_K^0.75, physics only** | **0** | **0.05 %** | **0.41 %** | 0.458 |

**The law with no free temperature parameter fits as well as the fitted
coefficient**, lands within 1 % of it (2516 predicted against 2490 fitted),
and leaves α unchanged at 0.458. Treat the agreement as encouraging rather
than settled: it is one band of one probe, α is still free alongside it and
partly correlated with the gain, and the AFE's own contribution (~+230 ppm/K
by the split in §4, itself not established) sits *inside* the measured 2490
but is not part of the physics — subtracting it would leave the cell at ~2260
against a predicted 2516, a 10 % gap.

On band B the same law gives rms 2.08 % and drives α to 1.537. That is not
evidence against the law: it is the §4.0 failure again, since the law is a
function of the **cell's** absolute temperature and band B supplies a board
node instead.

### 9.4 What this means for the model

1. **Do not add parameters.** Every richer static model tested here improves
   in-sample fit and degrades out-of-band prediction, which is the definition
   of fitting the confound.
2. **Fix the regressor first.** Either measure the cell (§5.4) or estimate it
   with a small *dynamic* model — a two-node RC driven by heater duty and
   ambient, identified from step responses like 09-10 20:51 (tip +50 K in two
   minutes, AFE +19.5 K) rather than from oxygen residuals. That is
   "higher-order" in the right sense: dynamics in the right variable, with
   parameters that have independent meaning and an independent test.
3. **Then re-run this exact cross-band protocol.** The acceptance criterion is
   out-of-band prediction, never in-band rms — otherwise the richer model wins
   by construction, as it did above.
4. **Candidate firmware change, proposal only:** replace the linear
   `TEMPCO_PPM_K` gain with `(T_cell/T_cal)^0.75`, which has no calibration
   constant at all and is right by construction at every temperature. It is
   worth nothing until `T_cell` exists — with a board temperature in it, it is
   the same mistake in a nicer algebraic dress.

## 10. The overnight run: two 80 °C α windows, and α is still not identified

Added 2026-09-11 morning from a fresh export (09-10 02:37 → 09-11 08:36 CEST).
§3 recorded that no α determination at high **cell** temperature existed. Two
board-isothermal windows now do exist, and they both say α is far larger than the
0.099 ± 0.015 §3 reported as confounded. Neither one identifies it.

**Read `2026-09-11-va-mon-collapse.md` first.** The probe published **no oxygen at
all** from 01:37 to 09:30 (`VA_LOW` ∈ `INVALIDATE_O2`), so window B below is a fit
to `gas_cell_ua` while the rail monitor read 2.0 V. That document argued the rail
was fine and the *monitor* was broken — **confirmed 09:15**, when Fab air-gunned
and cleaned the board and `va_mv` recovered 1338 → 3282 mV in one frame, a thing no
LDO does. So window B stands: the cell, its converter and its reference were all
healthy throughout, and only the rail *monitor* was displaced. Window A predates
the event entirely and never needed the argument.

Method as in §3: regress `ln I` on `ln f`, `f = (P − p_w)/P` from the chamber
SHT45, and divide the slope by the log-law gain 1.1273 to get the
concentration-domain α the firmware consumes.

| | **A** 09-10 21:40–22:07 | **B** 09-11 02:30–08:24 |
|---|---|---|
| n | 25 | 244 |
| duration | 0.45 h | 5.90 h |
| `t_tip` | 79.95–80.00 (**±0.05 K**) | 79.92–80.03 (±0.11 K) |
| `t_chamber` | 79.62–79.75 | 79.19–79.49 |
| RH % | **17.16 → 28.57** | 8.33 → 5.29 |
| `cell_ua` | 91.70–98.74 | 100.49–103.65 |
| `va_mv` | **3286, constant** | 2008–2168, drifting |
| `vref_mv` | 2496, constant | 2490–2492 |
| duty % | 35.6–51.1 | 79.1–85.1 |
| faults | `0x0200` (TEMP_OVER) | `0x0241` |
| **α, `ln f` alone** | **0.996**, rms 0.33 % | **0.726**, rms 0.19 % |
| α, + duty | 1.358 | 0.639 |
| α, + `va_mv` | n/a (constant) | 0.789 |
| α, + hours | **1.820** | **−0.029** |

Window A is the better measurement by every criterion that matters: the rail and
the reference are bit-constant, the board is isothermal to ±0.05 K, and the
humidity swings 11.4 points in 27 minutes — a real excursion, not a slow drift. It
lands on **α = 1.00**, i.e. full water-vapour dilution, with a 0.33 % residual.
Window B, six hours of the chamber drying out by 3 RH points, gives 0.73.

**But α is still not identified, and for the same structural reason as §3.** In
both windows the humidity change is nearly collinear with elapsed time —
r(ln f, hours) = **+0.987** in A and **+0.965** in B. Adding a linear drift term
moves α to 1.820 in A and to −0.029 in B, at *lower* residual in both cases. A
slow monotone drift in the cell and a slow monotone change in humidity are the same
regressor here. Window B adds a second partner: r(ln f, `va_mv`) = **−0.979**,
because the VA_MON decay and the drying ran in parallel all night.

So the honest statement is the same shape as §3's, with the numbers moved:

- α at 80 °C board temperature is **not** 0.099. That figure came from a window
  where α traded against heater duty at r = −0.910 and should be considered dead.
- The best single estimate now available at high temperature is **α ≈ 1.0** from
  window A, 27 minutes long, confounded with time at r = 0.987.
- The firmware's configured 0.402 and §12's 0.60 are both inside the room-
  temperature spread of 0.14–0.51 from §3 but **below** everything either 80 °C
  window returns under any specification.
- Nothing here changes §9's verdict. α ≈ 1 is a *physics-shaped* answer — full
  dilution is what the Dalton argument predicts with no free parameter — which
  points the same way §9.3 does: fewer fitted constants, not more.

**The measurement that would settle it, unchanged from §5:** an isothermal RH
sweep with humidity stepped in **both directions** at a fixed board temperature,
≥ 3τ ≈ 1 h per point, duty logged. Both directions is the whole point — it breaks
the collinearity with time that has now defeated four separate windows. Window A is
what the first half of that experiment looks like when it happens by accident.
