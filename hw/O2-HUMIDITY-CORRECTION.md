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
* **The residual is unattributed.** Chamber temperature rose 1.6 K over the
  same window, and at the ~+0.2 %/K these cells show that would be +0.3 %, which
  closes the gap between the −0.8 % predicted and the −0.5 % observed. But a
  single uncontrolled 1.6 K rise cannot *separate* the cell's tempco from the
  TIA, the reference, chamber pressure, equilibration lag, or an error in the RH
  sensor itself — they all move together here. Treat the arithmetic as
  consistent, not as an identification. (Codex review, 2026-09-06.)

## 2. The physics

> **RETRACTED 2026-09-06.** An earlier version of this section asserted that
> the cell responds to the **partial pressure** of oxygen rather than to its
> mole fraction, and built a `P_cal/P_meas` correction on top of that. The
> source cited for it says the opposite — see §3a. The dilution physics below
> is unaffected and stands; it is a statement about mole fractions and never
> needed the partial-pressure premise.

Water vapour is a gas: adding it to a mixture **at constant total pressure**
displaces everything else pro rata. (Constant total pressure is the load-bearing
condition — in a sealed rigid volume the vapour would raise `P` instead and
dilute nothing.)

```
C_wet = C_dry * (P - p_w) / P
```

with `p_w = RH/100 * p_sat(T)` the vapour partial pressure and `P` the total
pressure. `p_sat` is already in the firmware — `psychro.c` computes it with
Sonntag Magnus coefficients for the dew-margin channel, and the same function
serves here.

Dry air is 20.946 %vol O₂ (`O2P_C_AIR`, `o2.h:29`). The same air, saturated —
computed with the **host** helper `o2p_psychro.py`, whose Magnus prefactor is
6.1094, not the firmware's 6.112 (`psychro.h:27`). The two disagree in the
fourth significant figure (firmware: 19.423 / 16.813 / 12.898 for the 40/60/75 °C
rows). These are therefore illustrative values, **not exact firmware test
vectors**; §5's vectors must be generated from `psychro.h` itself:

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

**RETRACTED 2026-09-06 — do not implement `P_cal/P_meas`.** The argument above
rests on `K` carrying `P_cal` inside it, i.e. on the cell being a partial-pressure
device. The paper cited for that says the opposite. VanderGheynst eq. (3) gives
`D ∝ 1/P`, eq. (8) *defines* `xO₂ = PO₂/P` as the oxygen **mole fraction**, and
eq. (9) is `V = −β₁D'·ln(1 − xO₂)`: the leading `P` of eq. (1) cancels and the
output is a function of mole fraction, near pressure-**independent**. That is the
capillary mass-flow law, the same shape as the SGX datasheet's own
`S = K·ln(1/(1−C))`. Alphasense AAN 009 pp. 1–2 draws exactly this line:
capillary mass-flow cells are nearly pressure-independent, membrane
partial-pressure cells scale with `P`.

So `P` appears **once**, in the dilution factor — not twice — and normalising the
current by `P_cal/P_meas` would inject a pressure error rather than remove one.
VanderGheynst's device is also a heated zirconia FCX-UW (p. 1042), not an SGX
biased liquid-electrolyte cell, so that paper cannot settle the SGX either way.
Reopening this needs an SGX-specific construction or pressure-coefficient
statement, or a controlled pressure sweep at constant mole fraction on this cell.
Until then the pressure work item is **withdrawn**, and the "defect" it described
in `o2.c` is not a defect.
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

   **An earlier draft of this section also argued that the paper corroborates
   itself numerically** — that its outer zone at "about 20 %" and "greater than
   18 %" at 50–60 °C could not have come from a wet-basis instrument. *That
   argument does not hold and has been withdrawn.* Adversarial review read the
   zone-by-zone data it rested on: the outer-**top** region is near 20 % but
   generally **below 30 °C**, and the outer-centre/bottom is above 18 % at
   50–60 °C — where saturated air still reads about 18.4 %. The paper never
   measured RH in those boundary zones, and they are plausibly cooler and drier
   from ambient ventilation. The values are *consistent* with the stated dried
   method; they do not independently prove it. The method statement carries this
   on its own.

   **The independent confirmation comes from other instruments instead**, and
   there are three (§7): Kane & Mullins' Orsat, which is dry-basis *provided it
   is operated the standard way* — Shepherd's NBS description (Res. Paper 266,
   p. 147) saturates the gas before every measurement and equalises temperature
   and pressure, so the vapour cancels out of the volume ratio. Kane names a
   "modified Hays Orsat" (p. 1089) but documents neither the modification nor the
   confining liquid, so for that instrument this is **inference from general
   practice, not source verification** (corrected 2026-09-06). Then Schulze's
   ambient condensate trap, which is *condensed-to-room-temperature* rather than
   dry: the residual is whatever saturation holds at the trap temperature, 2.30 %
   at 20 °C and sea level but ~3.12 % at 25 °C. Schulze states a condensate trap
   (p. 109) and room-temperature analysis (p. 115) but gives neither the room
   temperature nor the outlet RH, so the defensible statement is
   "room-temperature condensate basis, probably near saturation", not a fixed
   2.3 % (corrected 2026-09-06). And — the one that matters most —
   VanderGheynst *et al.* (1997), who built an **in-situ** O₂/RH/temperature probe
   for exactly this environment, calibrated its water-vapour response
   experimentally, published on a dry air basis, and validated against gas
   chromatography. Stated precisely, because an earlier version of this document
   ran two separate tests together (corrected 2026-09-06): sensors stayed
   operational and calibratable after **as many as** 71 days in situ (pp. 1041,
   1049); the GC comparison was a **separate 42-day** test, of which 17 days were
   above 60 °C (p. 1048); and the manual samples were drawn **within 15 cm of**
   the probe rather than from the same gas volume — the authors invoke that
   separation themselves to explain the residual disagreement (pp. 1043, 1048).
   Its oxygen element was a heated zirconia FCX-UW (p. 1042), not an SGX cell, so
   it is a precedent for the *basis convention*, not for this cell's behaviour. The
   convention is not an artefact of sample lines that we are the first to notice
   in situ; someone reporting an in-situ cell in hot saturated gas already made
   the same choice.
3. **Both**, on separate registers.

**Recommendation: publish dry-basis on `O2_COMP` and keep wet-basis available.**
The primary register is the one a Dragino uplinks and a dashboard trends, and a
channel that moves 20 % with temperature is not a channel anyone can act on.
`O2_RAW` already carries the uncorrected cell current, so the raw evidence is
never lost.

Whatever is chosen, the register map's prose must say which basis it is. A
number whose basis is undocumented is worse than either choice.

### The thresholds are on the same basis — but the famous one is not a measurement

**The practically important consequence of this document** is that a probe
publishing wet-basis crosses a 5 %vol alarm line *while the pile still holds
6.2 %vol dry* at 60 °C, flagging anaerobia that is not there. Correcting to
dry-basis puts our register on the same footing as the published numbers, so no
threshold has to be restated as a function of temperature — which is not a thing
anyone will do correctly in a dashboard.

**What must not be claimed is that the thresholds therefore transfer unchanged**,
because the most-quoted one does not survive contact with its own sources. Randle
& Flegg (1978) p. 322 attributes it: "There is evidence (Schulze, 1962; Kane and
Mullins, 1973) that thermophilic organisms are active in compost while the oxygen
concentration remains above 5 %." Both were read (§7):

* **Schulze 1962 does state a 5 % minimum** — corrected 2026-09-06; an earlier
  version of this document claimed he states none. His conclusion (p. 121) reads:
  "The rate of aeration can be controlled by measuring the residual oxygen
  concentration in the exhaust gas. **A minimum of 5 % residual oxygen by volume
  should be maintained.**" What survives of the criticism is narrower and still
  matters: this is a prescriptive *operating* minimum for the mixed **exhaust
  gas** of a 55-gallon drum — the same band he ran experimentally at 5–10 %
  (p. 111) — not a pore-gas figure and not a measured biological floor.
* **Kane & Mullins 1973 does report an O₂ observation** — corrected 2026-09-06;
  an earlier version claimed its only "5 %" was the 95 % N₂ / 5 % CO₂ culture
  mixture. That mixture is present (pp. 1090, 1097), but so is this, on p. 1090:
  "thermogenesis is reduced in the middle zones where the O₂ concentration drops
  below 5 %. It has been reported that insufficient O₂ can result in poor
  thermogenesis." It is an **observational association** in a depth profile, not
  a manipulated-variable experiment — the zone that was low in O₂ also differed
  in temperature, aeration and position — but it is not absent.

So the canonical 5 % is real in the literature, and is an exhaust-gas operating
target plus an observational association. What it has never been is a
manipulated pore-gas threshold. **The figure with an actual
manipulated-variable experiment behind it is Suler & Finstein 1977** — 2 % O₂
severely restricted CO₂ formation, while 10 % performed the same as 18 %. Cite
them for an alarm, and Schulze only for the basis pedigree. Note also what Suler
& Finstein do *not* establish: that 10 % is a universal biological floor. It is
the level at which their system stopped being limited by oxygen.

**Setting the alarm number is therefore out of scope for this document**, which
is about the measurement basis. It needs its own evidence, and the temperature
coupling makes a flat percentage suspect in any case: oxygen is less soluble in
warm water, so a hot pile needs a *higher* gas-phase O₂ to deliver the same
dissolved O₂ to organisms living in wet biofilms.

### What that paper says about the actual goal

Relevant to an operator aiming at a diverse microbiome rather than merely
"not anaerobic" — its conclusion is that oxygen was *not* the limiting factor
(p. 322–323):

> Compost temperatures exceeded 65 °C for much of the time in the inner and
> middle zones which comprise 60 % of the stack volume, indicating that
> **microbial activity was restricted by overheating in the stack rather than
> by lack of oxygen**, a situation which probably occurs widely in commercial
> mushroom production.

Waksman *et al.* (1939) tested discrete temperatures and found the most rapid
decomposition at **50 °C** with thermophilic fungi active there, while at 65 °C
bacteria and actinomycetes predominated and fungi were "seldom found" (p. 97);
75 °C was rejected. So the paper supports useful thermophilic activity **across**
50 and 65 °C with a shifting community, *not* a common 50–65 °C optimum shared by
all three groups — corrected 2026-09-06, an earlier version claimed the latter.
For a diverse microbiome that distinction is the point: 65 °C is already past the
fungi. O₂ exceeded 5 % in 86 % of the stack volume
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

## 8. Reproducibility of the O₂ channel: what actually moves it

Measured 2026-09-06 on the bench rig (bare probe, **open** glass jar, wet paper
towel, still room air, 12.0 V). Three disturbances were separated by direct
experiment, and two of the three turned out not to matter.

| disturbance | effect on `o2_raw` | persistence |
|---|---:|---|
| heater excursion, 5.3 K (4 % duty, 600 s) | **+0.3 %** | transient, ~20 min, recovers |
| clean restart, cell unbiased 10 min | **+0.03 %** | none — within noise |
| restart accompanying a flash/SWD session | **±0.16 … 0.52 %** | persistent, sign random (n = 5) |

![O₂ across a heater step and a clean restart](doc/img/o2-heater-step-recovery-2026-09-06.webp)

*The canonical five-panel figure. The heater step is the feature at 14:00 — tip
and chamber up 5.3 K, RH falling 70.5 → 54.7 %, duty flat at 4.0 %, VIN steady.
O₂ is drawn on both wet and dry basis. The gap near 15:10 is the bias-interruption
test: the probe was parked in its bootloader for 10 min with the cell unbiased,
then served its 15-minute `SETTLING` window.*

**The heater excursion is real but transient.** +0.3 %, peaking about five
minutes *after* the heater goes off and decaying over ~20 min — two orders of
magnitude slower than the thermal τ, so it is a cell process, not temperature
tracking. It never undershoots. Two confounds were excluded rather than assumed:
absolute humidity *rose* slightly across the step (p_w 23.0 → 24.2 hPa), which
pushes O₂ **down**; and exchange with room air would pull the reading toward
20.95 %vol dry, also **down**. Both point the wrong way, so neither explains it.

**A clean restart does essentially nothing — +0.03 %.** This was measured by
writing `CMD_STAY` (0xB005) to `O2P_REG_UPD_CMD`, which resets the app into the
loader; the loader holds the cell **unbiased** in service mode and calls
`start_application()` after `SERVICE_IDLE_MS` (10 min) with no frames addressed
to the probe. The poller must be stopped for the window or its own traffic
refreshes that idle timer and strands the probe. Nothing is flashed:
`cmd_boot` is gated on a staged image, `cmd_stay` is not.

This is the useful result, and it corrects a working assumption held earlier the
same day. **A restart is not worth ±0.5 %.** The 15-minute `SETTLING` window is
conservative in the right direction and the cell genuinely returns to where it
was. Note also that an MCU reset alone would *not* have tested this: `main.c`
only re-verifies the LMP91000 and skips reconfiguration when the registers read
back intact, so the bias survives a plain reset. Ten minutes in the loader is
what actually drops it.

**What remains unexplained** is the ±0.4 % scatter across the five logged
reboots, since neither a thermal excursion nor a bias interruption produces a
persistent step of that size. What those five have in common is that each
accompanied a **flash or SWD session**, so the candidate is the flash write or
the debug attach disturbing the analog rail or the LMP91000 reference while the
cell is biased. Untested — it needs a stage-and-abort (`CMD_BEGIN` then
`CMD_ABORT`) to get the flash-write disturbance without changing the running
image, which writes to the staging slot and so needs a decision first.

**A fourth disturbance, larger than all of these, is condensation.** Measured
2026-09-06: a slow **+0.6 µA** surface-leakage term appearing above ~85–90 %RH,
and transient **−0.67 µA** dips from liquid water over the diffusion capillary.
Opposite signs, different timescales, so they neither cancel nor calibrate out
together — and the probe raises no fault while either is happening. See
`DEW-MARGIN-IS-BLIND.md`.

**Consequence for use.** Absolute O₂ is reproducible to ~0.03 % across a
restart, ~0.3 % for twenty minutes after a duty change, and to no better than
~0.5 % across a flashing session. Rates measured over windows long compared to
20 minutes are unaffected by all three, which is the standing argument for
treating rates as the robust product of this channel.

## 7. Sources

* Randle, P. and Flegg, P.B. (1978). *Oxygen measurements in a mushroom compost
  stack.* Scientia Horticulturae 8:315–323. Elsevier. Local copy:
  `~/dev/ha/farming/oxygen-mushroom.pdf`. Read in full. The method statement on
  p. 317 is the load-bearing citation for the dry-basis question.
* VanderGheynst, J.S., Walker, L.P. and VanderGheynst, G.B. (1997).
  *Development and analysis of oxygen-sensing probes for in situ monitoring of
  unsaturated solid-state biodegradation processes.* J. Air & Waste Manage.
  Assoc. 47(10):1041–1050. DOI 10.1080/10473289.1997.10464402. **Read in full.**
  The in-situ precedent: an O₂ + RH + temperature probe, water-vapour response
  calibrated experimentally, output published on a dry air basis. Corrected
  2026-09-06 — an earlier version overstated this on two counts. (i) The tests
  are separate: operational/calibratable after **as many as** 71 days in situ
  (pp. 1041, 1049), while the GC comparison was a **42-day** test with 17 days
  above 60 °C (p. 1048), and its manual samples came from **within 15 cm of** the
  probe, not the same gas volume (pp. 1043, 1048). (ii) It is **not**
  architecturally near-identical: its oxygen element is a heated zirconia FCX-UW
  (p. 1042), not a biased liquid-electrolyte three-electrode cell. It is a
  precedent for the dry-basis *convention* and nothing more.
  Its eq. (1) was previously read as writing the cell law over *total* pressure
  and used to justify §3c's `K` normalisation. That reading is **wrong and now
  retracted**: eq. (3) gives `D ∝ 1/P`, eq. (8) defines `xO₂ = PO₂/P` as the
  **mole fraction**, and eq. (9) is `V = −β₁D'·ln(1 − xO₂)`. The pressure
  cancels; the sensor is near pressure-independent.
* Schulze, K.L. (1962). *Continuous thermophilic composting.* Appl. Microbiol.
  10(2):108–122. DOI 10.1128/am.10.2.108-122.1962. **Read in full.** Cited as
  the primary source for the 5 % threshold; it **does contain one** — "A minimum
  of 5 % residual oxygen by volume should be maintained", p. 121 (corrected
  2026-09-06; this entry previously said it did not). It is an operating minimum
  for mixed *exhaust gas*, matching the 5–10 % band he ran at (p. 111), not a
  pore-gas or biological floor. Measured through an ambient condensate water
  trap, so condensed-to-room-temperature rather than dry; the residual vapour
  depends on the unstated trap temperature.
* Kane, B.E. and Mullins, J.T. (1973). *Thermophilic fungi in a municipal waste
  compost system.* Mycologia 65(5):1087–1100. DOI 10.1080/00275514.1973.12019529.
  **Read in full.** The other cited source for the 5 % threshold; it **does
  report one**, as an observational association — "thermogenesis is reduced in
  the middle zones where the O₂ concentration drops below 5 %", p. 1090
  (corrected 2026-09-06; this entry previously said it contained none). Not a
  manipulated-variable experiment: the low-O₂ zone also differed in temperature,
  aeration and depth. Sampled through a **modified** Hays Orsat (p. 1089); a
  standard water-confined Orsat is dry-basis by construction, but the
  modification and confining liquid are undocumented, so treating this as a
  second independent confirmation is inference, not verification.
* Suler, D.J. and Finstein, M.S. (1977). — the figure that *does* rest on a
  manipulated-variable experiment: 2 % O₂ severely restricted CO₂ formation,
  10 % ≈ 18 % (pp. 348–349, confirmed first-hand by the 2026-09-06 review).
  Already in `compostlab-literature`. Still the only manipulated-variable O₂
  figure in the corpus.
* Waksman, S.A., Cordon, T.C. and Hulpoi, N. (1939). *Influence of temperature
  upon the microbiological population and decomposition processes in composts of
  stable manure.* Soil Sci. 47(2):83–114. DOI 10.1097/00010694-193902000-00001.
  Corrected 2026-09-06: does **not** establish a 50–65 °C optimum common to
  fungi, actinomycetes and bacteria. Most rapid decomposition at **50 °C** with
  thermophilic fungi active; at 65 °C bacteria and actinomycetes predominated and
  fungi were "seldom found" (p. 97); 75 °C rejected.
  (Randle & Flegg cite this as 83–98 and as "microbial population"; both are
  wrong — the paper begins on p. 83 and says "MICROBIOLOGICAL".)

All five are archived in `compostlab-literature/` with checksums — see its
`monitoring-control/INDEX.md` and `microbiology/INDEX.md`, which record for each
what it does and does not support.
