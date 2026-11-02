# Oven soak, run log — 2026-09-19

**Live. Written while the run is in progress; every number here is a ramp
transient unless it says otherwise.** The plan is `OVEN-SOAK-TEST.md`; section
references below are to it. Evidence in `2026-09-19-oven-soak-evidence/`.

Observed from telemetry (farm-node-01, probe 3) — nobody wrote down the
physical setup, so the oven, the damping mass and whether the probe body was
dried after coming out of the pile are **unrecorded**. Several findings below
turn on exactly that.

## 1. Timeline

| clock | what |
|---|---|
| 2026-09-18 22:13 → 09-19 09:45 | probe at bench ambient, 20.9–21.5 °C. This is R1. |
| 08:19–08:35 | faults **2049** (ADC_RANGE + 1), `settle_s` restarting to 813. Cleared by 08:37. §6 abort criterion, met before the run started. |
| 09:48 | ramp starts |
| 09:58 | crosses 60 °C, faults → 512 (TEMP_OVER), as expected |
| 10:22 | 75.3 °C and still rising slowly; no §4 hold satisfied at any point yet |

The ramp went from ambient to ~74 °C in 25 minutes, **skipping H1/H2/H3**
(40/50/60 °C) of §4's up-leg. Whether that is deliberate is Fab's to say; as
run, the up-leg has no settled points below the top.

## 2. R1 is clean

09-18 22:15 → 09-19 00:00, n = 104, dry-basis current (α = 1, see §4 below):
mean **99.649 µA, sd 0.070 µA (0.07 %)**, T_EXT 21.17 °C. The 09:30–09:45
window immediately before the ramp gives 99.706 µA, **+0.06 %** against it.

So the baseline held overnight to well inside §4's 0.3 % bracketing
tolerance. R2 still has to close it after cooling.

Barometric pressure is **not measured at the bench** (Rev A has no barometer,
and the firmware assumes 930 hPa). Station-level pressure for Sankt Peter
(715 m) from the Open-Meteo model, *modelled and not a station reading*:
937.4 hPa at 22:00, 939.6 at 09:00, **940.9 at 10:00**. It rose 0.37 % between
R1 and the ramp, which is the same order as the 0.3 % bracketing tolerance, so
the analysis uses the hourly value rather than one constant.

## 3. The chamber is wet, and it was not supposed to be

§5 predicted dilution of about **1.1 % throughout**, nearly cancelling against
R1. Measured, it is an order of magnitude larger:

* RH stayed at 65–69 % while temperature went 21 → 45 °C. Absolute humidity is
  therefore **not conserved** — water is evaporating inside the chamber, not
  merely being carried up with the air.
* p_w reached **15.4 % of station pressure** (≈ 145 hPa) at 10:03.
* It is now falling again — 14.2 % at 10:12, 12.5 % at 10:22 — i.e. a finite
  wet source is being driven off.

The obvious source is the probe itself: it came out of a pile at 82 %RH
(`2026-09-18-pile-failure-sequence.md`) and nothing in the record says it was
dried first.

**Consequence 1 — the humidity correction now dominates the measurement.**
The effect being measured is ~13 % of current at 75 °C. The dilution
correction is now of the same size, so the run's answer is set by the
correction, not by the cell.

**Consequence 2 — the descent will condense on the cell.** At p_w ≈ 145 hPa
the chamber air's dew point is ~54 °C. §4's D1 (60 °C) clears it; D2 (40 °C)
does not. The cell would be taken through its own chamber's dew point, with
cell and gas at the same temperature so nothing keeps the condensate off it.
§6 excluded a humid point deliberately and has **no abort criterion for this**.
Unless the chamber is dry before the descent, D2 should not be run.

## 4. Which makes DIL_ALPHA, not the tempco, the run's largest unknown

§7 step 2 specifies `I_dry = I / (1 − p_w/P)`, i.e. α = 1. The repo's own
measured dilution response is **α = 0.402 ± 0.046** (2026-09-07 sweep,
register 0x0045; `o2p_backfill_dry.py` states none of the candidate values is
validated). With p_w at 1 % that choice was worth 0.6 % and could be ignored.
At 15 % it is worth 9 %, and it decides the result:

| α | 09:58, 62 °C | 10:03, 69 °C | 10:12, 74 °C | 10:22, 75 °C |
|---|---|---|---|---|
| 1.000 (§7) | +12.3 % | +14.2 % | +11.3 % | +8.5 % |
| 0.402 (0x0045) | +3.8 % | +4.4 % | +2.5 % | +1.2 % |
| 0.000 | −1.2 % | −1.2 % | −2.7 % | −3.1 % |
| **law predicts** | **+10.2 %** | **+12.1 %** | **+13.3 %** | **+13.5 %** |

α = 1 looks like "the law is confirmed and the 09-11 cooling pass is refuted".
α = 0.402 looks like "the 09-11 pass was right". Nothing in this run so far
separates them, and §8's two branches are exactly those two readings — so **as
it stands the soak cannot decide what it was built to decide.**

There is one internal check, and it does not favour α = 1. Between 10:12 and
10:22 the temperature was nearly flat (74.1 → 75.3 °C, worth +0.3 % on the
law) while p_w fell 14.2 → 12.5 %. A correct α leaves the corrected current
flat across that. Measured change: **−2.8 pp at α = 1, −1.3 pp at α = 0.402,
−0.5 pp at α = 0**. That is one short window on unsettled data, and it is not
a measurement of α — but it is evidence against the value §7 assumes.

## 5. Heater duty is not zero, and §3 voids every hold on that alone

`gas_heater_duty_pct` has read **1.7–2.9 %** continuously: all night at
ambient, through the whole ramp, and at 75 °C right now. §3 requires 0 through
every hold and calls a hold with non-zero duty void.

It is a real 60 s trailing mean of applied duty (`heater_ctl.c:1235`, FW
0x0025), not a display artefact. At ambient there is an explanation — chamber
22.9 °C at 68 %RH puts the dew point at 16.8 °C and the cell-side margin at
~4.2 K, right on the 4 K law's threshold, so it chatters. At 75 °C with a
22 K margin there is **no explanation yet**, and the dew law should be asking
for nothing. This wants resolving before any hold from this run is analysed.

## 6. Section 6 status, continuously checked

`firmware/tools/o2p_soak_watch.py` polls VictoriaMetrics and prints
ABORT / WARN / UNEVALUABLE / OK against §6 and §4, appending every poll to
`2026-09-19-oven-soak-evidence/watch.jsonl`. UNEVALUABLE is not OK: staleness
is tested before any threshold, because a stale sample sitting inside the band
is what a silent failure looks like.

Calibrated against real producer output, not fixtures: replayed over the
08:19 window it returns ABORT on both `faults=2049` and `settle_s=685`; the
same data offset 40 minutes returns UNEVALUABLE, as does an empty export.

Current standing verdict: **WARN** — heater duty, §5 above. No §6 abort
criterion is met: faults 512 only, `settle_s` 0, cell 94.7 µA (band
80–120 µA), T_AFE 76.3 °C (limit 85 °C), link live.

## 7. What would make this run answer the question

1. **Hold at the top until the chamber stops drying** — p_w is falling on its
   own. A §4 hold taken once p_w is back down to a few percent has a small
   correction again, and α stops mattering.
2. **Do not descend below ~60 °C while p_w is high**, or the cell is taken
   through the dew point (§3, consequence 2).
3. **The drying itself is a free α measurement**: temperature flat, p_w
   sweeping over a decade, which is precisely the regressor separation
   `o2p_tempco.py` refuses to work without. A long top hold gives both.
4. Resolve the non-zero heater duty, or every hold is void by §3.

None of that is a probe-state change, and no probe state has been touched.

---

## 8. The fit, 11:25 — the exponent is below 0.75 whatever α is

The probe is in air, so the dry-basis fraction is a constant 20.946 %vol and
every excursion is instrument. `firmware/tools/o2p_soak_fit.py` fits the
firmware's own two terms in logs,

    I = I0 * (T_EXT/T_ref)^n * (1 - alpha * p_w/P)

over 161 gated samples, 07:39–11:23 (settle_s = 0, COMP_OK set, faults in
{0, 512}). Pressure is the Open-Meteo hourly station value, 937–941 hPa,
interpolated — a model value, not a station reading. Uncertainties are a
delete-one-block jackknife over 10 contiguous blocks, never the covariance:
minute uplinks against a cell time constant of tens of minutes are
autocorrelated, and O2-HUMIDITY-CORRECTION.md §14 already measured that
penalty as roughly ten times.

**The joint fit is a ridge, as the plan's own design guaranteed.** Over the
whole run the two regressors correlate at **r = −0.95**: temperature and
humidity moved together, so n and α cannot be split. The tool says
UNEVALUABLE rather than printing the ridge minimum as a result
(n = −0.08, α = +0.08) — that pair describes the data and neither number
stands alone.

**Cut the ridge at each candidate α and the answer is the same:**

| α | n | residual rms |
|---|---|---|
| 1.000 (§7's assumption) | **+0.498 ± 0.114** | 1.51 % |
| 0.645 (measured below) | **+0.263 ± 0.067** | 0.97 % |
| 0.402 (register 0x0045) | **+0.110 ± 0.039** | 0.68 % |
| — | *firmware uses 0.750* | — |

**n < 0.75 on every cut, and the most favourable one is 0.50 ± 0.11.** This is
§8's second branch: the firmware divides by too much at temperature, so it
**under-reads O₂ when hot**. The published series shows it directly — in air,
`gas_pct_vol` reads 20.70 %vol at 21 °C and **19.61 %vol at 75.8 °C**, a
−6.4 % excursion where the truth did not move.

**α itself is measured, on the window that breaks the collinearity.** From
10:27 the temperature has been flat (75.3–75.9 °C) while the chamber dried,
p_w/P sweeping 15.4 → 8.6 %. There r = +0.61, and with n pinned at the
firmware's 0.75 (temperature has no leverage in a flat window, so it must be
pinned, and an unpinned fit ran away to n = −3.6 and dragged the O₂ scale to
36 %vol):

**α = 0.645 ± 0.081** (jackknife over 6 blocks, range 0.61–0.72), residual
rms 0.16 %.

That sits above register 0x0045's 0.402, above §14's break-even 0.546, and
clearly below §7's 1.0. It is one 55-minute window, and any slow drift at
fixed temperature — cell recovery, the board still equilibrating — maps onto
α, so it is a result from this run and not yet a calibration.

### Corrected O₂ over the last 3 h

`2026-09-19-oven-soak-evidence/o2-corrected-3h.png`, data in the CSV beside
it. Every curve is anchored to read dry air over 08:40–09:45, so the absolute
scale is owned by that anchor, not by a K carried over from another
calibration era. Spread against the constant that ought to be there:

| series | span over 3 h | at the 75.8 °C hold |
|---|---|---|
| probe published | 1.97 %vol | 19.61 (−6.4 %) |
| firmware model, n = 0.75, α = 1 | 1.79 %vol | 19.70 (−5.9 %) |
| uncorrected | 1.02 %vol | 20.50 (−2.1 %) |
| fitted, n = 0.263, α = 0.645 | 1.37 %vol | 20.75 (−0.9 %) |

Two things to read off it, and one not to:

* **The firmware's corrections, applied together, are worse than no correction
  at all here** — 1.79 %vol of spread against 1.02. That is §14's break-even
  argument showing up as a measurement rather than an estimate.
* **The fitted model is the only one that lands near air at the hold**, but its
  3 h *span* is still 1.37 %vol, all of it spent in the 09:48–10:30 ramp.
* **Do not read the ramp as model error.** T_EXT is the cell-side TMP117, not
  the cell; through a 25 K/10 min ramp the cell lags it, and a model fitted
  over that attributes lag to n. The settled top hold is the only part of this
  that is a measurement of anything, and it is 55 minutes old.

### What this does not yet close

* n is quoted **per α**, and α rests on one drying window. The down-leg is what
  separates them properly — §4 wants it precisely because a lag artefact
  reverses sign between the legs and a real response does not.
* R2 has not been taken, so §4's 0.3 % bracket is still open.
* Heater duty is still non-zero (§5), which by §3 voids the hold this fit
  leans on.
* `o2p_backfill_dry.py` cannot process this run as-is: its plausibility gate is
  `-40 < t < 80` on both the chamber and T_EXT, and the chamber has been at
  77–78 °C. Another kelvin or two and every sample is silently dropped with
  "0 samples — every point was unevaluable".

---

## 9. How long, and what follows — 11:30

**The clock that matters is the chamber drying, not the cell settling.**
Temperature is already settled by §4's drift test: +0.002 K/min over the last
30 min. The cell current is *not* flat — it is rising **+1.9 µA/h at constant
temperature** — but that is the drying, not a drift: p_w fell 90 → 78 hPa over
the same 30 min, which at α = 0.645 predicts +1.6 µA/h of the +1.9 observed.

Water vapour is decaying exponentially with **τ = 144 min** (fit from the
10:03 peak of 142.6 hPa; now 78.3 hPa, dew point 41.1 °C). Projected against
the temperature each leg needs, with 4 K of dew margin:

| step | needs p_w below | reached at |
|---|---|---|
| D1, 60 °C | 165 hPa | already clear |
| D2, 40 °C | 59 hPa | **~12:05** |
| R2, ambient 21 °C | 19 hPa | ~14:45 *if drying kept τ = 144 min* |

That last projection is optimistic and should not be planned on: evaporation is
temperature-driven, so τ lengthens as the probe descends. The top hold is the
only place the chamber dries fast.

### Recommended schedule

| from | step | why this long |
|---|---|---|
| now → **12:10** | stay at 75.8 °C | clears D2's dew gate at 12:05, and gives a 100 min flat-temperature window with p_w sweeping 143 → 55 hPa, a factor 2.6. That is the α measurement, and it is the only leverage this run has on the ridge. |
| 12:10 → 13:10 | **D1, 60 °C** | ~15 min to settle, then §4's 30 min. First settled point of the whole run at a stated temperature. |
| 13:10 → 14:10 | **D2, 40 °C** | same. |
| 14:10 → until p_w < 19 hPa | **hold at 40 °C** | do the remaining drying here, not at 75 °C: 40 °C is inside the cell's rating, so a long dwell costs nothing, and R2 must not be entered while the chamber can condense on the way down. |
| then | **R2, ambient, ≥ 60 min** | closes §4's 0.3 % bracket against R1. |

**Skip H5 (80 °C).** The chamber is already at 77.9 °C, the cell is 17 K over
its rating, and the up/down identification §4 is built on does not need it.

**Add a 50 °C hold on the way down if there is appetite for it.** The up-leg
was ramped straight through, so it has no settled points at all: the descent
is carrying the entire ladder, and three points beat two for fitting n.

### The tension this schedule is resolving

Drying faster means staying hot, and §6 says to keep H4/H5 to the minimum
hold. The cell has been above its 60 °C rating since 09:58; by 12:10 that is
2.2 h. Holding at 75 °C until the chamber were dry enough for a direct return
to ambient would mean ~14:15, i.e. **4.3 h** over rating — that is not a
minimum hold, and it is what the schedule above avoids by moving the drying to
the 40 °C step. The 09-11 precedent (6 h dry at 76 °C cell side) is not a
licence; it is an unrepeated survival.

### Two criteria that will not be met, whatever the schedule

* **§4's "T_EXT, chamber and T_AFE agree within 1 K."** The spread is stable at
  2.01 K (chamber above cell-side) and 0.80 K (AFE above cell-side). It is the
  oven's air running hotter than the damped probe, not a transient, so it will
  not close by waiting. Either the criterion gets a documented exception for
  this setup, or the damping mass has to grow.
  **CORRECTED IN §16, 14:25: it is not the oven, it is the heater.** The
  gradient floor holds the tip 2.00 K above the cell by design, and the chamber
  SHT45 tracks the tip. Growing the damping mass would change nothing.
* **§3's zero heater duty.** Still 1.6–1.7 %, unexplained at a 34 K dew
  margin.

Both need Fab's call before any hold from this run is treated as a §4 hold.

---

## 10. A 12-minute blind gap, and it was another agent session — 12:40

**Every `gas_*` series stopped at 12:27:06 and returned at 12:39:23.** The node
was never the problem: it kept uplinking throughout (RSSI −65 dBm, ingest lag
2.1 s, other sensors emitting), and node-side Modbus diagnostics showed the
probe answering with `modbus_exception` 0 and `codec_ok` 1.

Cause, confirmed by the session responsible (`farming-77`, asked directly
rather than inferred): it was driving CTRL sessions on f_port 13 with
**CLAIM_BUS**, and Modbus relay on f_port 10 to slave 3, to push probe
firmware 0x0026 and run a heater duty staircase. CLAIM_BUS takes the RS-485
pair off the node's scheduled poll — which is exactly the signature: gas
payloads on f_port 2/12 stopped, f_port 13/10 traffic started 12:28:32,
`node_*` untouched. It has stopped and is holding off the probe until this run
is finished.

**Interventions in this run's window that are NOT the experiment**, per that
session, to be attributed before any of this data is fitted:

* heater duty override 10 % for ~80 s at 08:32Z;
* a 0/3/6 % duty staircase from ~12:29 local, killed mid-run;
* several node resets over USB, the last ~12:38 — so node rejoins and fCnt
  resets in this window are not the experiment either.

Exact timings requested. **This does not explain §5**: applied duty has read
1.6–2.9 % continuously since 22:13 last night, which predates all of it. Duty
read 0.53 % on the first sample after the gap.

Also flagged by that session and worth recording: `o2p_update.py`'s status
decode aliased TEMP_OVER (0x0200) onto "state READY, error NONE", so a
firmware push at a hot probe could be told an erase finished when it had not.
Fixed there today. This probe has carried TEMP_OVER continuously since 09:58.

## 11. The condensation projection was wrong, and the measurement says so

§9 projected the descent against **p_w conserved** — absolute humidity fixed,
so the dew point stays at 37.6 °C and the cell crosses it on the way down.

The first descent sample refutes that. Over 12:27 → 12:39, T_EXT fell
75.92 → 62.71 °C and:

| | 12:27 | 12:39 |
|---|---|---|
| chamber RH | 14.7 % | 15.2 % |
| p_w | 64.7 hPa | 36.9 hPa |
| dew point | 37.6 °C | 27.6 °C |
| dew margin | 38.3 K | 35.1 K |

**RH is the conserved quantity here, not p_w.** The dew point is falling with
the temperature and the margin is holding near 35 K. The chamber is not a
sealed volume — vapour leaves as fast as the temperature drops. If RH stays
near 15 %, the dew point at ambient 21 °C is about 5 °C and **there is no
condensation hazard on this descent at all.**

That is one sample after a 12-minute gap, so it is a mechanism seen once, not
a law. The watcher alarms at 12, 8 and 4 K of margin, which is the guard that
matters if it turns out to be wrong.

Descent rate is **1.08 K/min** — far too fast for any hold to form.

## 12. §5 resolved: the standing duty is the gradient floor, and it is by design

`farming-77` proposed the mechanism from a reading of `heater_ctl.h` (v0.22):
FW 0x0025 high-selects the dew-margin law against a **gradient floor**, a PI
loop on (T_cell + 2.00 K) − T_tip that has no dew term at all. It offered this
as a hypothesis to test, not a result. **The telemetry confirms it**, over 356
samples spanning 04:55–10:47 and 21 → 76 °C:

| local | T_EXT | T_tip | (T_EXT+2) − T_tip | duty |
|---|---|---|---|---|
| 04:55 | 21.00 | 22.98 | +0.02 | 1.89 % |
| 07:36 | 20.86 | 22.96 | −0.10 | 1.68 % |
| 09:50 | 28.73 | 30.71 | +0.02 | 1.60 % |
| 10:47 | 75.75 | 77.73 | +0.02 | 1.72 % |

The gradient error stays inside ±0.05 K across a **55 K** change in absolute
temperature. That is not a coincidence, it is a controlled variable: the loop
is holding the tip 2.00 K above the cell and ~1.8 % is the steady-state drive
it takes. Nothing is faulty.

**Consequence for the plan:** §3's "a hold with non-zero duty is void" is
**unsatisfiable on this firmware** without disarming the gradient floor. That
is a design question for Fab — either §3 gets amended to "no *dew-law* duty",
or the floor is disarmed for soak runs and the 2 K gradient goes away with it.
It should not be quietly worked around.

It also means the tip has run 2 K above the cell for the entire run, R1
included, so it is common-mode in every ratio taken here.

## 13. α, with the contaminated samples removed

§8's α = 0.645 ± 0.081 was fitted over 10:27–11:23, and that window contains
another session's heater intervention (verified independently below). Refitting
from 10:37, after it:

**α = 0.715 ± 0.052**, residual rms **0.09 %**, regressor correlation r = +0.84.

Cutting the ridge at that α gives **n = +0.308 ± 0.075**. The conclusion of §8
is unchanged and slightly firmer: n is well below the firmware's 0.75.

### Verifying the intervention rather than relaying it

The session's own log said 10 % duty for ~85 s at 08:32:20–08:33:45Z, aborted
at tip 81.12 °C. Checked against telemetry, which nobody edits:

* peak `gas_t_tip_c` for the day is **79.5 °C at 10:34:32 local** (= 08:34:32Z)
  with T_EXT 75.89 — a real tip excursion at the stated time, one minute after
  the stated stop, which is what a 60 s trailing mean does;
* peak `gas_heater_duty_pct` for the day is **3.67 %**, at the same sample.
  A 10 % rung held 85 s should drag the 60 s mean far higher. Either the
  1/min sampling missed the peak, or the applied duty was clamped below the
  commanded 10 % — that session was reading HEATER_MAX_DUTY at the time.

So the event is real and correctly timed in UTC; the amplitude in that log is
not corroborated. The session's casual "staircase starting ~12:29 local" was
its own slip — the staircase was 10:29–10:37 local, and the 12:27 outage was
its console pokes and firmware-push attempts.

Also confirmed from its log: probe firmware **0x0026 was never installed**;
every push failed before transferring a block, so the probe is still on
0x0025 / BUILD_ID 0x49314A4C and nothing about the image changed mid-run.

---

## 14. D2 settled at 41.5 °C — and the exponent is not a constant

The descent arrested at **41.4 °C cell-side from ~13:03** and held: over
13:05–13:30, 15 samples, T_EXT sd **0.165 K**, drift −0.03 K/min, dry-basis
current sd **0.092 µA (0.09 %)**. Faults **0** — TEMP_OVER cleared on the way
down — and `settle_s` 0. This is the run's first genuinely settled point at a
stated temperature.

It fails two of §4's five tests, and both are the structural ones already
documented: the chamber/cell-side spread is 2.0 K (§9, and see §16 — that
spread is the gradient floor's own setpoint, not the oven), and heater duty is
1.93 % because of the same floor (§12). Nothing about it is transient.

**Effective exponent between R1 and each settled window**, where n_eff is
defined by I_dry(T)/I_dry(R1) = (T/T_R1)^n_eff:

| window | T_EXT | p_w | n_eff at α=0.402 | at α=0.715 | at α=1.0 |
|---|---|---|---|---|---|
| top hold 11:10–11:23 | 75.81 °C | 81.7 hPa | +0.095 | +0.225 | +0.348 |
| **D2 13:05–13:30** | **41.47 °C** | **19.5 hPa** | **+0.570** | **+0.575** | **+0.580** |

**D2 is α-independent.** At 41 °C and 22 %RH the dilution term is small enough
that the whole α controversy moves the answer by 0.010 — so
**n_eff(41.5 °C) = 0.575** is a measurement, not a cut through a ridge. It is
the first number from this run that does not depend on the humidity model at
all. Against it the firmware's 0.75 predicts +5.20 % where +3.96 % was
measured.

The top hold stays α-dependent, and that is now the *only* thing α is needed
for. But at **every** α it lies below the 41 °C value.

**So the effective exponent falls as the probe gets hotter** — 0.575 at 41 °C
against 0.10–0.35 at 76 °C. The cell's current rises with temperature less
than a 0.75 power law, and progressively less the hotter it is. That is the
shape the 2026-09-11 cooling pass suggested (rising far less than the law, and
falling above ~52 °C) on data that could not carry the claim.

**This is §8's second branch, and it rules out the lazy fix.** A single
different exponent cannot describe both anchors. §8 already named the right
remedies — a crossover above which the exponent changes, or a fitted table —
and explicitly not a residual in TEMPCO_PPM_K. The two settled anchors here
are the first real constraints on such a table.

Caveats, stated because the number looks clean: two anchors do not establish a
curve; R2 has not closed the bracket; and both anchors carry the 2 K tip
gradient common-mode.

### Still to do

1. **R2 at ambient, ≥ 60 min** — the bracket. Dew point at D2 is 17.1 °C
   against a 21 °C room, so ambient is ~4 K of margin: the same chattering
   condition the probe sat in all last night, not a new hazard.
2. Read **HEATER_LAW (0x0008)** to confirm §12's floor mechanism against the
   register rather than against a correlation. It costs a bus claim, so it
   waits until after R2.

## 15. D2 closed, R2 begun — 14:02

The oven went off at about **13:52**: T_EXT held 41.2–41.5 °C from 13:05 to
13:54 with drift under 0.01 K/min through most of it, then broke away —
−0.037, −0.185, −0.239 K/min and accelerating.

**D2 final, 13:05–13:54, 30 samples:**

* T_EXT **41.37 ± 0.163 K**
* dry-basis current **103.029 ± 0.076 µA** (0.07 %)
* **+3.94 %** against R1
* n_eff **+0.567 / +0.574 / +0.580** at α = 0.402 / 0.715 / 1.000

Fifty minutes, and the α spread is 0.013 across the whole plausible range. The
number did not move as the hold aged (§14 had +0.573 over its first 34 min),
which is the check that separates a hold from a slow drift.

R2 is now running: ambient arrival, then ≥ 60 min. Dew point is 17.6 °C
against a ~21 °C room, so the descent ends at about 4 K of margin — the
standing overnight condition, not a new hazard.

## 16. Correction: the 2 K spread is the heater, not the oven

§9 and §14 called the chamber-to-cell spread "the oven's air running hotter
than the damped probe". **That is wrong, and the data say so plainly.**

`gas_t_tip_c` − `gas_t_ext_c` over 879 samples spanning 20.3–75.9 °C:

| T_EXT band | n | tip − cell |
|---|---|---|
| 20–25 °C | 760 | +2.066 ± 0.180 K |
| 25–50 °C | 44 | +2.050 ± 0.058 K |
| 50–80 °C | 75 | +2.072 ± 0.209 K |
| **all** | **879** | **+2.065 ± 0.178 K** |

and chamber − cell runs +1.98 to +2.12 K over the same bands (±0.074 K in the
quiescent ambient window). The chamber SHT45 tracks the tip; both sit 2 K above
the cell.

**+2.00 K is the gradient floor's setpoint** (§12). The firmware is holding
that gap deliberately, at a cost of ~1.8 % duty, and it holds it to ±0.06 K in
the quietest window. An oven gradient would not survive the oven being off —
this one is identical overnight at ambient with the oven cold, at 75 °C inside
it, and during the uncontrolled cool-down now in progress.

**So §4's "T_EXT, chamber and T_AFE agree within 1 K" is not a statement about
the setup at all — it contradicts the firmware's own control law.** No amount
of damping mass, oven choice or patience can satisfy it while the gradient
floor runs. §9's suggestion to grow the damping mass was treating a symptom
that does not exist.

That makes the ruling owed in §12 sharper rather than softer. The choice is:

* **amend §4** to require the three sensors to agree to within the floor's
  setpoint plus a tolerance, i.e. test that the spread is STABLE rather than
  small — it held ±0.07 K overnight, which is a far stronger statement than
  "< 1 K" and is the thing that actually matters for a hold; or
* **disarm the gradient floor for soak runs**, which closes both this and §3's
  zero-duty requirement in one move, at the cost of losing whatever the 2 K
  gradient is there to do.

Either is defensible. Quietly running soaks that fail two of five criteria by
design is not.

---

## 17. R2 closed, and the run is complete — 16:02

The probe was taken out of the oven at **15:48–15:49**, which the trace dates
without being told: drift goes from −0.007 to −0.11 K/min, the cell current
starts swinging ±1.5 µA against a 0.06 % baseline, and `gas_afe_mv` breaks out
of its steady 984–988 mV into 974–1000. Same signature as the open door at
14:10, and the same cause — room air moving over a probe whose heater is
holding a 2 K gradient.

**R2, 15:11–15:48, 38 samples, 37 minutes:**

| | |
|---|---|
| T_EXT | 23.70 ± 0.078 K, drift −0.0065 K/min |
| I_dry (α = 0.715) | 99.572 ± 0.062 µA (0.06 %) |
| raw vs R1 | **+0.449 %**, at an offset of +2.79 K |

The room was 2.79 K warmer than it was overnight, so the bracket needs that
offset removed before it can be compared with §4's ±0.3 %:

| assumed n | expected from +2.79 K | residual |
|---|---|---|
| **0.573** (the D2 anchor) | +0.542 % | **−0.093 %** |
| 0.300 (the top-hold fit) | +0.283 % | +0.166 % |
| 0.750 (the firmware) | +0.710 % | −0.261 % |

**The bracket closes on every candidate exponent.** The baseline held across
seven hours, a 55 K excursion, a chamber that went to 15 % water and back, a
twelve-minute telemetry blackout and two spells of forced convection. That is
what makes the two anchors quotable.

**Deviation, stated rather than buried: R2 ran 37 minutes, not §4's 60.** The
probe left the oven before the hour was up. The shortfall costs precision that
was not needed — the window's own scatter is 0.06 %, so the mean is determined
to about 0.01 %, two orders below the 0.3 % tolerance, and the drift test it
had to pass is a rate, not a duration. It does not cost comparability, which
is what the hour is actually for, because the window is settled throughout. A
reader who wants the strict §4 bracket does not have one.

### Run summary

| window | T_EXT | n | result |
|---|---|---|---|
| R1 09-18 22:15 – 09-19 00:00 | 20.91 °C | 104 | I_dry 99.127 µA, sd 0.07 % |
| top hold 11:10–11:23 | 75.81 °C | 14 | n_eff +0.095…+0.348, α-dependent |
| D2 13:05–13:54 | 41.37 °C | 30 | n_eff **+0.573 ± 0.010**, α-independent |
| R2 15:11–15:48 | 23.70 °C | 38 | bracket closes, −0.09 % at n = 0.573 |

**The answer to the question this run was built to ask** (§1, §8): the
firmware's (T/T_cal)^0.75 is wrong, and wrong in the direction the 09-11
cooling pass suggested. The effective exponent is 0.573 at 41 °C and no higher
than 0.35 at 76 °C, so it **falls** with temperature and no single power law
describes both. The firmware therefore over-corrects hot and under-reads O₂ at
pile temperatures — measured here as `gas_pct_vol` reading 19.61 %vol in air at
75.8 °C where the truth is 20.946.

Per §8 the remedy is a crossover or a fitted table, not a residual in
TEMPCO_PPM_K, and these two anchors plus R1/R2 are its first real constraints.

### Owed to Fab, unchanged

1. §3 and §4 versus the gradient floor (§12, §16): amend the criteria or
   disarm the floor for soak runs. Two of five criteria currently fail by
   design.
2. The dilution response α is still the ridge's only free parameter above
   40 °C. This run measured 0.715 ± 0.052 on one isothermal drying window.
3. HEATER_LAW (0x0008) read at the bench to confirm §12 against the register.

## 18. The corrected O₂ curve

`2026-09-19-oven-soak-evidence/o2-corrected-final.png`, data in
`o2-corrected-final.csv`. Five series, all anchored to read dry air over
08:40–09:45 so the absolute scale is owned by the anchor rather than by a K
from another calibration era. The probe is in air throughout, so the dashed
20.946 %vol line is truth and every excursion from it is instrument.

Means over the four settled windows:

| window | T_EXT | uncorrected | published | firmware 0.75/α=1 | single n=0.32 | **measured n(T)** |
|---|---|---|---|---|---|---|
| R1 08:40–09:45 | 20.91 °C | 20.946 | 20.692 | 20.946 | 20.946 | 20.946 |
| top hold 11:10–11:23 | 75.81 °C | 20.735 | 19.612 | 19.700 | 20.658 | **20.946** |
| D2 13:05–13:54 | 41.37 °C | 21.654 | 20.488 | 20.735 | 21.271 | **20.948** |
| R2 15:11–15:48 | 23.70 °C | 21.127 | 20.588 | 20.858 | 20.973 | **20.928** |

as error against truth:

| window | uncorrected | published | firmware | single n | n(T) |
|---|---|---|---|---|---|
| top hold | −1.01 % | **−6.37 %** | −5.95 % | −1.38 % | **−0.00 %** |
| D2 | +3.38 % | −2.18 % | −1.01 % | +1.55 % | **+0.01 %** |
| R2 | +0.86 % | −1.71 % | −0.42 % | +0.13 % | **−0.09 %** |

**Read the n(T) column honestly. Two of those three are fitted, not
predicted** — the top hold and D2 ARE its anchors, so landing on truth there is
arithmetic, not evidence. **R2 is the out-of-sample point, and it is −0.09 %.**
That is the only number in the column that tests anything, and the model was
not shown it.

The n(T) curve is a linear interpolation of the effective exponent in
temperature between 41.37 °C → 0.573 and 75.81 °C → 0.225, clamped outside
that range rather than extrapolated, with α = 0.715. It is a description of
this cell over 21–76 °C, not a physical law, and the clamp is deliberate: two
anchors constrain a line between them and say nothing beyond them, and an
extrapolated exponent compounds into the exponent of a ratio.

What the figure shows at a glance:

* **The published series is the worst of the five at every temperature.**
  −6.37 % at the top hold, in air, where the truth did not move.
* **The firmware's own model is barely better than no correction at all**, and
  at the top hold it is worse: −5.95 % against the uncorrected −1.01 %.
* **A single exponent cannot fit both ends.** The best one, n = 0.32, is
  −1.38 % at 76 °C and +1.55 % at 41 °C — it splits the difference and misses
  both, which is the same conclusion as §14 in picture form.
* The three excursions that are NOT model error: the 10:00 ramp spike (the
  cell lagging T_EXT through 2 K/min), the 12:45 descent bump, and the noise
  after 14:10, which is forced convection from the open oven door and later
  the probe being lifted out (§17).

## 19. The register read, on the image this log describes — 16:20

`farming-77` read the bench registers on FW 0x0025 before flashing 0x0026, so
these describe the probe this entire run was measured on, not its successor.
Read through the confirmed-read path (two agreeing reads of different width),
not the retry path that produced this morning's stale 0x2710.

| register | value | what it settles |
|---|---|---|
| HEATER_LAW 0x0008 | **4 = O2P_HEATER_LAW_DEW**, no high-byte flags | §12: the standing duty is the dew-law family, not the RH loop, not a tip setpoint, not an override |
| HEATER_BENCH 0x0060 | **0** | no override armed, nothing left behind by this morning's session |
| HEATER_MAX_DUTY 0x0035 | 10000 = 100.00 % | the duty cap was not clamping anything |

**State the first one precisely, because it is one step short of what §12
claimed.** The law word names the dew-margin law as in command. The gradient
floor lives *inside* that law — it is high-selected against the dew demand
(`heater_ctl.c:1173`) — so LAW = DEW does not by itself separate "the dew term
is driving" from "the floor term is driving". What separates them is the
telemetry: the dew margin ran 20–35 K through every window in this log, where
the dew term has nothing to ask for, while (T_EXT + 2.00 K) − T_tip held inside
±0.05 K across 55 K with duty working 1.6–2.9 % to keep it there.

So the register establishes the family and the telemetry identifies the term.
Together they close §12. Neither does it alone, and this log should not be read
as though the register alone confirmed it.

0x0060 = 0 also closes the other open question from this morning: combined with
the 884-sample run-length check (§ the exact-zero analysis), no override was
armed and no membrane was left driving.

## 20. The 41–76 °C gap cannot be filled by the heater — 16:40

§17 leaves the effective exponent measured at two points 34 K apart, with a
straight line between them by assumption. The obvious cheap way to test that
line is the tip heater. **It cannot reach.**

Cell-side coupling, measured in situ (`docs/2026-09-14-cell-tip-coupling-in-situ.md`,
the accepted 14:40–15:20 window, three of four windows rejected by its own
guards): **k = 0.293**, plausible range 0.14–0.37. Note that document's own
warning — 0.293 is about 3× the ~11 % figure quoted in `heater_ctl.h`, and the
discrepancy is unexplained. Use the measurement, not the header.

From a 21.6 °C cell against 0x0026's 92.00 °C tip clamp, i.e. 70.4 K of tip
rise:

| k | cell reaches |
|---|---|
| 0.14 (outdoors, wind-exposed) | 31.5 °C |
| **0.293 (measured, still air)** | **42.2 °C** |
| 0.37 (top of range) | 47.6 °C |

So a heater-driven cell anchor lands between 31 and 48 °C — at the measured k
it sits on top of D2's 41.37 °C, and only at the top of the range does it enter
the gap at all. **A 57 °C cell needs 35.4 K of rise, which is a 117 °C tip at
k = 0.37 and a 142 °C tip at the measured 0.293.** Both are past the clamp and
past anything that should be driven at a cell rated to 60 C.

**The midpoint is an oven measurement or it does not exist.** Proposed to Fab
2026-09-19: one setpoint at 55–60 °C cell-side, which is *below* the cell's
rating and therefore the safest run yet — no TEMP_OVER, no extrapolation — and
much cheaper than today because the chamber is now dry, so the humidity
confound that dominated §3, §4 and §13 is spent. Roughly three hours: ambient
baseline, ramp, ≥45 min hold, cool, closing baseline. Door shut throughout;
today's two noise episodes were both forced convection (0.03 % scatter closed
against 1.3 % open, §17).

Worth stating for the follow-up, since §8's remedy depends on it: at k = 0.37 a
92 °C tip leaves the cell at 47.6 °C, comfortably inside the 60 °C datasheet
maximum. The 90 °C tip ladder pushes the TIP, not the cell.

## 21. The 08:19 blip was a node reboot, and the node does it every few hours

§1 recorded an unexplained event: "08:19–08:35, faults **2049** (ADC_RANGE + 1),
`settle_s` restarting to 813, cleared by 08:37. §6 abort criterion, met before
the run started." It is explained.

`node_uptime_s` and `gas_probe_uptime_s`, exported over three days and read for
resets:

| node boot | previous uptime | probe boot |
|---|---|---|
| 09-18 14:30:28 | 86.9 h | 09-18 13:32 |
| 09-18 16:10:13 | 1.7 h | 09-18 16:10 |
| 09-18 20:21:14 | 3.6 h | 09-18 20:27 |
| 09-18 20:28:48 | 0.1 h | 09-18 20:37 |
| 09-18 20:37:25 | 0.1 h | — |
| **09-19 08:17:37** | **11.7 h** | **09-19 08:17:39** |
| **09-19 11:38:15** | **3.3 h** | **09-19 11:38:17** |
| 09-19 16:58:15 | 5.3 h | 09-19 17:00:15 |

**Eight node reboots in three days**, and the probe follows each one down
within seconds. `gas_reset_cause` = 12 = PIN | PWR — NRST plus BOR/power-on,
with no watchdog (0x20) or software (0x10) bit — so the probe is not hanging
and not resetting itself: its rail goes away with the node.

`settle_s` **counts down**, which is what makes the 08:19 record fit exactly:
probe boot 08:17:39, `settle_s` 813 at 08:19:06 is 900 − 87 s of a 15-minute
settle, and the 08:37 clear is 900 s after boot. Nothing anomalous happened —
the probe was power-cycled and served its settling window.

**Two reboots fell inside the run**: 08:17 (23 min before R1's anchor window
opens at 08:40) and **11:38, between the top hold ending 11:23 and the descent**.
Neither contaminated a result, and that is not luck — the fits gate on
`comp_ok == 1` and `settle_s == 0`, so every settling sample was dropped before
it reached an average.

**It also means the bracket is stronger than §17 claimed.** A probe reboot
reloads the COMMITTED config record rather than RAM, so R1 and R2 sit either
side of two power cycles and two config reloads and still agree to −0.09 %.
The calibration is stable across reboots, which nothing in this run set out to
test.

### What this changes for the next run

The 55–60 °C oven run proposed in §20 assumes about three hours of continuous
telemetry. Against a node that reboots every 3–12 hours that is not a safe
assumption, and the failure is not graceful: a reboot costs the probe 15
minutes of settling on top of the gap.

So the follow-up must be **restartable**, not merely watched:

* every hold judged on its own settled window, with no quantity accumulated
  across the whole run;
* the ambient bracket taken as R1 and R2 windows that can each be re-taken
  after an interruption rather than one continuous baseline;
* `settle_s` and `comp_ok` gating kept exactly as it is — it is what made
  today's two reboots harmless;
* and the run's state written to telemetry as it goes, so an interrupted run is
  resumable from the record rather than restarted.

This is the same lesson a failed firmware push learned the hard way the same
afternoon: a 47-minute transfer against a node that reboots every few hours is
a coin flip, and that push had no resume.
