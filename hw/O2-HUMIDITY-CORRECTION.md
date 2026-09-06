# O₂ is published wet-basis and uncorrected for water vapour

**In a 60 °C pile at 100 %RH the probe will read 16.8 %vol in fully aerated
air.** That is a 20 % relative error, in the direction that looks like the pile
going anaerobic, and it is the exact condition the probe is built for. Nothing
is broken — the cell is reporting the oxygen that is actually there — but what
the register publishes is not the quantity anyone will think it is.

Observed on the bench 2026-09-06 while humidifying a chamber for the thermal
test, and quantified below. This document is the argument and the spec
decision; the implementation is a separate change.

## 1. What was measured

Raising a closed chamber from 42.3 %RH to 63.9 %RH (23.4 → 25.0 °C), with the
probe undisturbed and no fault flags:

```
observed  o2_comp  20.98 -> 20.88 %vol   = -0.48 %
observed  o2_raw  100.20 -> 99.68 uA     = -0.52 %
predicted from vapour dilution alone     = -0.80 %
```

Two things make this a physical result rather than a processing artefact:

* **The raw cell current fell by the same relative amount as the compensated
  value.** A compensation bug would make the two diverge. The `o2_comp`/`o2_raw`
  ratio is unchanged to five significant figures — which incidentally shows
  `TEMPCO_PPM_K` is zero and the temperature correction is doing nothing.
* **The residual is the cell's own temperature coefficient.** Chamber
  temperature rose 1.6 K over the same window; at the ~+0.2 %/K these cells
  show, that is +0.3 %. Dilution −0.8 % plus tempco +0.3 % gives the −0.5 %
  observed.

## 2. The physics

An amperometric cell responds to the **partial pressure** of oxygen, `pO₂`, not
to its mole fraction. Water vapour is a gas: adding it to a fixed-volume,
fixed-total-pressure mixture displaces everything else pro rata.

```
C_wet = C_dry * (P - p_w) / P
```

with `p_w = RH/100 * p_sat(T)` the vapour partial pressure and `P` the total
pressure. `p_sat` is already in the firmware — `psychro.c` computes it with
Sonntag Magnus coefficients for the dew-margin channel, and the same function
serves here.

Dry air is 20.946 %vol O₂ (`O2P_C_AIR`, `o2.h:29`). The same air, saturated:

| condition | p_w | reads | error |
|---|---:|---:|---:|
| 25 °C, 50 %RH | 1.58 kPa | 20.620 %vol | −1.6 % |
| 25 °C, 100 %RH | 3.16 kPa | 20.293 %vol | −3.1 % |
| 40 °C, 100 %RH | 7.36 kPa | 19.424 %vol | −7.3 % |
| **60 °C, 100 %RH** | **19.99 kPa** | **16.815 %vol** | **−19.7 %** |
| 75 °C, 100 %RH | 38.91 kPa | 12.902 %vol | −38.4 % |

`PLAN.md` puts the pile at 40–65 °C, so the middle two rows are the operating
point and the last is the excursion `psychro.h` already warns is outside the
Magnus fit's range.

**The heater does not fix this.** Holding the cell at the 85 %RH setpoint
instead of 100 % removes 15 % of the vapour term, not the term itself: at 60 °C
that is still 17.0 kPa and a 16.8 %vol → 17.4 %vol improvement. The heater
exists to stop the cell drowning, which is a different problem.

## 3. Three separate errors, only one of which is the headline

### 3a. Measurement-time dilution — up to 20 %, the one above

`o2.c` converts cell current straight to a volume fraction with no vapour term.
What comes out is the wet-basis fraction, which is the honest answer to "what
fraction of this gas is oxygen" and the wrong answer to almost every question
anyone will actually ask of a compost probe.

### 3b. Calibration-time vapour — 1–2 %, and it is baked in

`o2.c:47` computes `k = cal_air_na / O2P_LN_AIR`, where `O2P_LN_AIR` is
`ln(1/(1−0.20946))` — the **dry** air value. But the air point is taken in
ambient room air, which is moist. The cell current recorded at calibration
corresponds to the *wet* fraction, and attributing it to the dry one
mis-scales `K` for every subsequent reading:

| air point taken at | true C | K error |
|---|---:|---:|
| 23.4 °C, 42.3 %RH *(this bench)* | 0.2070 | +1.37 % |
| 25 °C, 60 %RH | 0.2055 | +2.15 % |
| 20 °C, 80 %RH | 0.2056 | +2.11 % |

This is not fixed by correcting the measurement — it is a bias in `K` itself,
and it must be fixed at the point the air cal is taken. A probe calibrated in a
damp shed and one calibrated in a dry lab do not agree today, by about 1 %.

### 3c. Total pressure — ±4.2 % from weather at the operating point, unmeasured

**Revised 2026-09-06 after an adversarial review of the implementation.** The
first version of this section said "8 % from altitude" and implied weather
largely cancels. Both halves were wrong in the same way: they quoted
differences in *absolute pressure* as if they were errors in the *published
number*, and they did not notice that `P` enters the calculation twice.

The cell reads `pO₂ = C · P`. Both corrections above need `P`, and **the BMP390
is DNP on Rev A**, so `PRESSURE_HPA` publishes 0 and the firmware uses the
`ASSUMED_P_HPA` config register instead.

```
altitude    0 m -> 101.3 kPa
altitude  715 m ->  93.0 kPa   (-8.2 %)   <- Steingrubenhof, 48.01475N 8.03294E
weather at one site: ~97-104 kPa          (+/- 3.5 %)
```

**Where `P` actually appears.** Twice, and in opposite directions:

1. In `K`. The air point fixes `K = S_air / ln(1/(1−C_cal))`, and `S_air` was
   produced at the calibration pressure, because the cell answers to `pO₂`.
   `K` therefore *carries* `P_cal` inside it.
2. In the dilution factor `P / (P − p_w)` that converts wet basis to dry.

Because the two uses partially cancel, an `ASSUMED_P_HPA` that is simply wrong
by a constant is far less damaging than the 8.2 % suggests. Calibrating **and**
deploying at sea level with the 930 hPa default left in place, air point at
25 °C/50 %RH and read out at 60 °C/100 %RH, publishes about **21.4 %vol, near
+2 % relative** — not 8 % low. (The review computed 21.386 %vol / +2.10 %;
recomputing it here against `psychro.c`'s own Magnus coefficients gives
21.417 %vol / +2.25 %. The two agree on the order and disagree on the last
digit, which is the point: the residual depends on both the calibration and the
measurement conditions, so it is a range and not a constant. Both are about
2 %, and neither is 8 %.)

**Weather does not cancel, and it is the larger error.** `P` moving after the
air point was taken changes the cell's gain without changing `K`. At the same
60 °C/100 %RH operating point, ±3.5 % of weather makes fully aerated air
publish about **20.073–21.813 %vol dry against a true 20.946 — −4.17 % to
+4.14 % relative.** That is the largest uncorrected term left in the oxygen
channel, roughly twice the in-situ altitude residual above, and about a fifth
of the vapour term this document was written about.

**What in-situ calibration does and does not buy.** It cancels the *systematic*
part — a constant offset in the assumed `P` appears in both `K` and the
dilution factor and largely divides out — so in-situ air calibration remains a
requirement rather than a convenience. It does nothing about weather, which
moves `P_meas` after `K` is already fixed.

**It is not correctable in firmware without a barometer.** It is not
uncorrectable in principle, and the distinction matters for Rev B: with a
populated BMP390 the fix is to normalise the measured current by `P_cal/P_meas`
before the inverse, which requires the calibration pressure to have been stored.
Correcting only the dilution factor against a real barometer reading — which is
what the first implementation of this document did — leaves about **−3.2 % to
+3.2 %** of the weather term on the answer, i.e. it fixes less than a quarter of
it. So the firmware now records `CAL_P_HPA` (`0x0044`) at the moment an air
point is taken and applies that normalisation. With no barometer fitted
`P_meas == P_cal == ASSUMED_P_HPA`, the ratio is exactly 1, and it changes no
number today; it is the structure without which even a populated barometer would
not fix this.

## 4. The decision this needs, which is a spec decision

There are three defensible things `O2_COMP` could publish, and the firmware
must not guess:

1. **Wet-basis** — what it does now. Honest about the gas present. Falls with
   humidity even when aeration is unchanged, which makes the primary channel
   track the weather and the heater duty rather than the pile.
2. **Dry-basis** — oxygen as a fraction of the water-free gas. This is what
   the compost literature means by "O₂ %", and what is comparable across sites
   and seasons. It is also what makes a trend line mean respiration rather than
   humidity.

   **This is now sourced rather than assumed.** Randle & Flegg (1978),
   *Oxygen measurements in a mushroom compost stack*, Scientia Horticulturae
   8:315–323, states the method outright (p. 317): samples were "passed
   through a **cold trap and silica gel indicator to cool and dry the sample**
   before it was passed through a paramagnetic oxygen analyser, Taylor-Servomex
   model OA/250". The gas is desiccated before it reaches the instrument, so
   every percentage in that paper is dry-basis.

   The paper corroborates itself: it reports the stack's outer zone at "about
   20 %" and "always greater than 18 %" at 50–60 °C. Wet-basis, ambient air at
   60 °C and saturation reads 16.8 %vol (§2). A wet-basis instrument could not
   have produced those numbers. Two independent confirmations — the stated
   method and the value it yields in near-ambient gas.
3. **Both**, on separate registers.

**Recommendation: publish dry-basis on `O2_COMP` and keep wet-basis available.**
The primary register is the one a Dragino uplinks and a dashboard trends, and a
channel that moves 20 % with temperature is not a channel anyone can act on.
`O2_RAW` already carries the uncorrected cell current, so the raw evidence is
never lost.

Whatever is chosen, the register map's prose must say which basis it is. A
number whose basis is undocumented is worse than either choice.

### The thresholds are dry-basis too, so the alarm points do not move

The number everyone quotes — 5 %vol as the floor for aerobic activity — traces
through Randle & Flegg (1978) p. 322 to its primary sources: "There is evidence
(Schulze, 1962; Kane and Mullins, 1973) that thermophilic organisms are active
in compost while the oxygen concentration remains above 5 %." Both are measured
with the dried-sample method above.

**That is the practically important consequence of this whole document.** Since
the published thresholds are dry-basis and the probe currently publishes
wet-basis, a probe left uncorrected would cross a 5 % alarm line *while the
pile still held 6.2 %vol dry* at 60 °C — flagging anaerobia that is not there.
Correcting to dry-basis means the existing literature thresholds transfer
unchanged; no alarm point needs re-deriving. Publishing wet-basis would require
every threshold to be restated as a function of temperature, which is not a
thing anyone will do correctly in a dashboard.

### What that paper says about the actual goal

Relevant to an operator aiming at a diverse microbiome rather than merely
"not anaerobic" — its conclusion is that oxygen was *not* the limiting factor
(p. 322–323):

> Compost temperatures exceeded 65 °C for much of the time in the inner and
> middle zones which comprise 60 % of the stack volume, indicating that
> **microbial activity was restricted by overheating in the stack rather than
> by lack of oxygen**, a situation which probably occurs widely in commercial
> mushroom production.

Optimum for the three thermophile groups — fungi, actinomycetes, bacteria — is
50–65 °C (Waksman et al., 1939). O₂ exceeded 5 % in 86 % of the stack volume
and 10 % in 79 %, while temperature was out of range in 60 % of it. If that
generalises, **the probe's temperature channel is at least as load-bearing as
its oxygen channel**, and the pairing is what diagnoses a pile — which is an
argument for the diagnostic block being uplinked, not just `O2_COMP`.

Two further observations from the same dataset that bear on deployment:

* **Oxygen varies more horizontally than vertically**, and the inner-bottom
  region sat below 2 %vol continuously while the outer zone stayed near
  ambient. A single buried probe reports its own region, not the stack. Probe
  placement is a measurement decision, not an installation convenience.
* **O₂ and temperature are anti-correlated with a specific, diagnosable
  signature** across a turn: turning cools the pile toward 50 °C, which
  stimulates activity and crashes O₂; O₂ recovers once temperature plateaus
  near 70 °C and activity is suppressed by heat. A probe logging both should
  reproduce that shape, which makes it a field validation target for this
  hardware rather than only a biological observation.

## 5. Proposed change

* Correct the **air point** when it is taken (3b): compute the true `C` at the
  cal-time `T`, `RH` and assumed `P`, and store `K` from that rather than from
  `O2P_LN_AIR`. This is a change at `o2p_o2_calibrate()`, not in the hot path.
* Correct the **measurement** (3a): convert the wet-basis fraction the cell law
  returns into dry-basis with `C_dry = C_wet * P / (P - p_w)`.
* Add a config register for **assumed total pressure** in hPa, defaulting to a
  documented value, used whenever `PRESSURE_HPA` is 0 because the BMP390 is
  DNP. Without it the correction has no `P` at all.
* Reuse `psychro.c`'s saturation-pressure function. Do not add a second Magnus
  implementation — two copies of the same coefficients is how they diverge.

### Guard rules this must obey

The repo's guard checklist applies, and this is a correction that can silently
poison the primary channel:

* **Unevaluable input must not mean "no correction".** If RH or chamber
  temperature is missing or sentinel, the corrected value cannot be computed —
  publish the O₂ sentinel, or a clearly-labelled uncorrected value with a fault
  bit. Falling back to the uncorrected number *while still calling it
  corrected* is the exact failure mode `o2.h` was written to avoid.
* **Monotonicity.** As humidity rises, the correction must not fold back.
  Test at 100 %RH and at 75 °C, not just near room conditions.
* **Bounds.** `p_w` approaching `P` sends the correction to infinity. Above
  ~85 °C at saturation this is no longer a small correction, and the Magnus fit
  is already out of range at 75 °C. Clamp and raise a fault rather than
  publishing a large number.
* **Do not silently change what a stored calibration means.** An existing
  `cal_air_na` was taken under the old assumption. Either migrate it with the
  config version, or require recalibration and say so.

### Test vectors

Every row of the table in §2 is a test vector, plus:

* dry air at 0 %RH — the correction must be exactly a no-op
* the bench observation in §1 — 42.3 → 63.9 %RH must move corrected O₂ by less
  than the measurement noise, where uncorrected moved 0.48 %
* RH sentinel, temperature sentinel, `P` of zero — all must fail closed

## 6. What this does not change

The cell law itself (`S = K·ln(1/(1−C))`, DS-0637) is untouched: it relates
current to the fraction the cell actually sees, and that is still the wet-basis
fraction. Everything here is about what is done with that fraction afterwards,
and about calibrating `K` against the right number in the first place.

## 7. Sources

* Randle, P. and Flegg, P.B. (1978). *Oxygen measurements in a mushroom compost
  stack.* Scientia Horticulturae 8:315–323. Elsevier. Local copy:
  `~/dev/ha/farming/oxygen-mushroom.pdf`. Read in full. The method statement on
  p. 317 is the load-bearing citation for the dry-basis question.
* Schulze, K.L. (1962). *Continuous thermophilic composting.* Appl. Microbiol.
  10:108–122. — cited by the above as a primary source for the 5 % threshold.
  NOT YET RETRIEVED.
* Kane, B.E. and Mullins, J.T. (1973). *Thermophilic fungi in a municipal waste
  compost system.* Mycologia 65:1087–1100. — the other primary source for the
  5 % threshold. NOT YET RETRIEVED.
* Waksman, S.A., Cordon, T.C. and Hulpoi, N. (1939). *Influence of temperature
  upon the microbial population and decomposition processes in composts of
  stable manure.* Soil Sci. 47:83–98. — source for the 50–65 °C thermophile
  optimum. NOT YET RETRIEVED.
