# O₂ cell correction model — what a dilution + tempco calibration can and cannot buy

*2026-09-07. Estimate, not a measurement: no calibration data exists yet. Every number
below is propagated from part datasheets (cited inline) through the model the firmware
and `model/` package actually implement. Monte-Carlo scripts are reproduced in §7.*

> **Revised the same day after an adversarial Codex review (§8).** Four things
> changed and the changes matter: the cell datasheet is **Issue 2**, not Issue 1
> — 0.1 ± 0.03 mA in air, not 0.07 — and **Issue 2 publishes an output-versus-
> temperature curve**, so the claim that SGX publishes no tempco was wrong. The
> air-point reference uncertainty in `fit_mc.py` was 10× too large. And the
> "more dilution points make K worse" result is real only for an *unweighted*
> fit: weighted by each point's own reference uncertainty, they neither help
> nor hurt. The tables below are the corrected ones.

> **Second review, 2026-09-08 (§9).** A fresh reviewer was pointed at the committed
> state and told that §8 was the thing under test. It confirmed the corrected tables
> reproduce and survive every weighting variant tried, and found five things §8 had
> not: a **sample/config provenance gap** (a published value could carry a
> `CONFIG_CRC` describing a *different* calibration), a **combined
> `CAL_TRIGGER`+`COMMIT` frame** that persisted the pre-calibration image, **two
> unbounded config constants** that made a legal write return 4.503 %O₂ for a true
> 5.000 % with a clean fault word, a **wrong rationale** for the flash version bump,
> and the fact that the **vendor curve is materially non-linear**, so one `α` cannot
> close the model (§5). Fixed where fixable; §9 lists what is escalated rather than
> patched.

## 1. The model under test

`model/src/o2_lumped/physics.py` and `firmware/src/o2.c` share one static law:

```
I = I0 + K·(1 + α·(T − T0))·ln( 1 / (1 − C·p/p_ref) )
```

with `I0` the cell zero current, `K` the log-law sensitivity, `α` the fractional output
tempco. Fitting it is what "dilutions + tempco" means. Three structural facts decide the
whole budget:

1. **Multiplicative chain errors cancel.** `C` depends only on `S/K`, and `K` is derived
   from an air point taken through the *same* TIA, ADC and reference. The LMP91000's
   5 % transimpedance-gain accuracy and the ADS1119's ±0.01 % gain error (SNAS506I §6.5;
   SBAS925A §6.5) therefore do not enter the answer — only their *drift* does, and that
   is where the tempco term hides (§5).
2. **Additive errors do not cancel**, and the air point pins the top of the range, so an
   offset error rotates the whole low-O₂ end. This is the entire reason to run a
   dilution series rather than only an air point.
3. **The digitiser is not the limit.** Not remotely.

## 2. Chain resolution — irrelevant by two orders of magnitude

7 kΩ TIA (`main.c:113`, TIA_GAIN=011), ADS1119 gain 1, external 2.5 V ref, 16-bit
bipolar, DR = 20 SPS, 8 conversions averaged per sample (`O2P_N_O2`).

| quantity | value | as %O₂ near air |
|---|---|---|
| 1 LSB = 76.3 µV | 10.9 nA | 0.0020 %O₂ |
| ADC noise 62.5 µV<sub>RMS</sub> (SBAS925A Table 1, gain 1) ÷ √8 | 3.16 nA<sub>RMS</sub> | 0.0006 %O₂ |
| 20-sample (10 min) plateau mean | 0.7 nA | 0.0001 %O₂ |
| ADS1119 INL, ±15 ppm FSR | 10.7 nA | 0.002 %O₂ near air, 0.003 %O₂ at the N₂ end |
| LMP91000 internal-zero accuracy ±0.04 %, *typical* not a bound (SNAS506I §6.5) | ≤143 nA | 0.034 %O₂ at the N₂ end |
| **SGX cell zero signal, `< 0.4 %vol O₂` (DS-0637)** | **≤1706 nA** | **≤0.4 %O₂ at the N₂ end** |

The cell's own zero is 12–150× every electronic term. A zero-gas point is worth taking;
a 16-bit-resolution argument is not worth having.

## 3. What the fit actually resolves (Monte Carlo, 1500 trials per design)

Truth used: `K` = 425.5 µA/ln-unit (DS-0637 **Issue 2** nominal 0.1 mA in air), `I0` =
0.2 %vol equivalent (half the datasheet limit), `α` = +0.2 %/K (§5, read off Issue 2's
curve). Plateau noise = ADC noise ⊕ 0.1 % of reading for short-term cell/gas stability.
Temperature: TMP117 ±0.1 °C (SNIS189) plus a 0.5 K electrolyte-to-sensor gradient drawn
**once per temperature level** — it is a property of the setup at that bath temperature,
not of each gas level. Reference-gas grades: N₂ zero exact; air 20.946 % dry corrected
for RH and pressure → ±0.005 %O₂; two-MFC blend ±1 % rel; certified cylinder ±2 % rel.

Field columns are RMS error in **percentage points O₂** from calibration parameter
uncertainty alone — inside a correct-model universe, and with nothing from §4–§6.

**Weighted fit** (each residual scaled by its own total uncertainty, current noise ⊕
`K·σ_C/(1−C)`):

| design | σ(K)/K | σ(I0) | σ(α) | 21 %@25 °C | 21 %@55 °C | 10 %@45 °C | 5 %@55 °C | 2 %@60 °C |
|---|---|---|---|---|---|---|---|---|
| A air point @20 °C only (**today's firmware**) | 0.15 % | — | — | 0.19 | **1.28** | 0.57 | 0.49 | 0.33 |
| B N₂ + air @20 °C | 0.14 % | 1.1 nA | — | 0.19 | **1.29** | 0.47 | 0.34 | 0.16 |
| C N₂ + air × 5 temperatures | 0.094 % | 0.5 nA | 4e-5 /K | 0.015 | 0.017 | 0.007 | 0.004 | 0.002 |
| D 6 MFC dilutions × 5 T | 0.097 % | 0.5 nA | 4e-5 /K | 0.016 | 0.018 | 0.007 | 0.005 | 0.002 |
| E 6 cylinder dilutions × 5 T | 0.093 % | 0.5 nA | 4e-5 /K | 0.015 | 0.017 | 0.007 | 0.004 | 0.002 |
| F 4 dilutions × 3 T (lean) | 0.120 % | 0.6 nA | 5e-5 /K | 0.019 | 0.024 | 0.009 | 0.006 | 0.003 |

**Unweighted fit**, same data, for the one row that changes the advice: σ(K)/K becomes
0.42 % for D, **0.84 % for E** and 0.51 % for F, against 0.094 % for C. Designs A–C are
identical either way.

Read four things off that.

**The tempco is the whole game.** Designs A and B — everything achievable without a
temperature-controlled bench — carry ~1.3 %O₂ of error at 55 °C in air and 0.3–0.5 %O₂
in the 2–5 % range where the compost decision lives. Any temperature sweep collapses
that below 0.03 %O₂. σ(α) lands near 4e-5 /K against a true 0.002, so the coefficient is
identifiable to ~2 % of itself even in the lean design.

**Weighting is not optional, it is the difference between two opposite conclusions.**
Unweighted, every blended point injects its own 1–2 % reference error into a fit whose
air point was already good to ±0.005 %O₂, and adding points *degrades* `K` by up to 9×.
Weighted by each point's own reference uncertainty, the same points neither help nor
hurt — σ(K) stays near 0.1 % across C, D, E and F. So the design question is not "how
many dilution points" but "does the estimator know which points it can trust". Hand an
unweighted design matrix to `least_squares` and the certified cylinders will quietly
drag the air point off.

**What the blends are actually for**, then: the zero, and detecting departures from the
log law. They cannot do the latter below ~1 % of reading, which is where their own
reference sits — a clean residual at a blended point is not evidence the law holds.

**To test the log law itself**, use *pressure* dilution: sealed chamber of air, vary
total pressure, `pO₂` known to a barometer's 0.05 %. DS-0637 rates the cell
800–1200 mbar, so this only spans ≈16.5–24 %O₂ equivalent, but over that span it is a
20× better reference than any blend.

**Expected residuals, and what a residual means.** At air and N₂ points, residual RMS
should sit at ~0.1 % of reading (≈100 nA at air) — the assumed cell/gas stability, with
the ADC contributing 1 % of it. At MFC-blended points the residual will be ~1 % of the
point's current, dominated by the reference. A >0.3 % structured residual versus C at
the air/N₂ ends is real model error; anything under ~1 % at the blended points is
invisible under the reference gas.

## 4. What the calibration does not fix — and these are larger

At the Steingrubenhof site (715 m, 93.0 kPa, −8.2 % vs sea level):

| term | size | status |
|---|---|---|
| **Water-vapour dilution** of pore gas at 100 %RH: reading is wet-basis | at 55 °C the wet reading is 17.4 % where dry is 20.95 %; **−0.18 %O₂ per K** of gas temperature | no dry-basis conversion in firmware; needs pore-gas T and p |
| **Barometric weather**, ±2 kPa, no compensation | ±0.45 %O₂ at air, ±0.11 %O₂ at 5 % | **BMP390 is DNP** (`regmap.h:48`, PRESSURE_HPA reads 0) — uncorrectable on-board |
| **CO₂ enhancement**, 0.3 % of signal per 1 % CO₂ (SGX DS-0143, 4-series) | at O₂ = 5 % with CO₂ ≈ 16 %: **+0.23 %O₂**; peak +0.31 %O₂ near 10 % | figure is for the 4-series galvanic cell, **unverified for the Mini** |
| **Long-term drift** `< 5 % over operating life` (DS-0637) | ±1.0 %O₂ at air, ±0.25 %O₂ at 5 % | needs periodic re-span; the air point is the field span |
| **Above 60 °C** | cell rated to +60 °C, pile runs to ~75 °C | out of spec; α extrapolated, as `o2.h` already says |

The water-vapour term is the biggest single number on this page and it is not a sensor
error at all — it is a definition. Decide explicitly whether the published channel is
wet- or dry-basis before the calibration, because the tempco fit and the vapour
correction both key off temperature and will otherwise absorb each other.

## 5. The tempco: SGX does publish a curve, in Issue 2

**Correction.** The first version of this document said SGX publishes no output-versus-
temperature data for this cell. That was true of **DS-0637 Issue 1** (07-Apr-2025), which
is what the firmware header was written against. **Issue 2 (28-May-2026) carries a
`%20 °C Output vs Temperature °C` plot** — mean with ±3σ bands, −40 to +60 °C — on page
2, alongside the revised `0.1 ± 0.03 mA` air output. Read off the plot: about 84 % of the
20 °C output at −40 °C rising to about 105 % at +60 °C, i.e. **≈ +0.2 %/K**, and the ±3σ
spread means the *population* varies enough that a per-unit fit is still worth doing.

That value is **eyeballed, not digitised**, so it is not yet a sourced number and
`O2P_TEMPCO_DEFAULT` stays 0. Digitising it with `dsdig` is the next step and it is
cheap.

> **The curve is visibly not a straight line, and a single `α` cannot close it.**
> The 2026-09-08 review read the mean curve as roughly 97.3 / 100 / 104.1 / 104.9 /
> 106.2 % of the 20 °C output at 10 / 20 / 40 / 50 / 60 °C — flattening markedly above
> 40 °C. A best affine fit over 10–60 °C gives ≈ +0.176 %/K and leaves residuals near
> ±0.8 % of the 20 °C output, i.e. **≈ ±0.15 %O₂ near air** — three times the ±0.05
> headline of §3, and a term §3 *cannot* see, because `fit_mc.py` makes the response
> exactly linear by construction. Adding temperature points to the campaign therefore
> cannot expose this error; only fitting real data against a real curve can.
>
> **These readings are a second eyeballing, not a digitisation** — a model's visual
> reading of a chart, recorded here as UNVERIFIED. They are strong enough to retire
> "one linear coefficient is sufficient" as an assumption and not strong enough to put
> a number in firmware. `dsdig` settles both, and this is now the reason it is not
> optional: if the curvature is real, the fit needs a quadratic term or a restricted
> temperature range, which is a change to the model, not to a constant.

What the eyeballed slope already settles:

- **The magnitude is the capillary one.** A continuum-diffusion barrier gives
  `D ∝ T^1.75` against a molar density `∝ 1/T`, so `I ∝ T^0.75` → +0.25 %/K at 300 K.
  The published curve sits at ≈ +0.2 %/K. Independent derivation and vendor plot agree
  to 20 %, which is as much as either deserves.
- **The +2 %/K "solid-membrane" branch is dead**, and with it the worry that a 1 K
  electrolyte-vs-TMP117 gradient could cost 0.37 %O₂. At +0.2 %/K it costs 0.037 %O₂ at
  air and 0.010 %O₂ at 5 %O₂ — the TMP117 is roughly 20× better than this needs.
- **Do not confuse the regimes.** An earlier draft labelled the T^0.75 law
  "capillary/Knudsen-limited". Those are opposite: *Knudsen* diffusivity scales as `√T`,
  which with the same density term gives `I ∝ T^-0.5`, about **−0.17 %/K** — the wrong
  sign. The derivation above is the continuum one, and the vendor curve confirms the
  continuum regime is what this cell is in.

Sensitivity per **1 K of cell-temperature error**:

| α | error at 21 %O₂ | error at 5 %O₂ |
|---|---|---|
| **+0.2 %/K (Issue 2 curve, eyeballed)** | **+0.037 %O₂** | **+0.010 %O₂** |
| +0.25 %/K (continuum T^0.75 derivation) | +0.046 %O₂ | +0.012 %O₂ |
| −0.17 %/K (Knudsen, for contrast — not this cell) | −0.031 %O₂ | −0.008 %O₂ |

**The confound to design out remains.** The LMP91000 specifies neither TIA-gain drift nor
internal-zero-divider drift over temperature (only `TcVOS_RW`, ±4…8 µV/°C, which moves
the bias, not the gain). An isothermal whole-probe sweep therefore fits `α_cell + α_AFE`,
not `α_cell`. For a probe whose cell and AFE share one board that lumped coefficient is
the *right* one to use in the field — **except** when the heater is on and splits the
two temperatures. So run both: (i) whole probe isothermal, several temperatures → the
lumped α firmware uses; (ii) AFE held fixed while gas/cell temperature moves → the
split, needed to know whether heater duty biases the reading. The vendor curve does not
replace either: it is the cell alone, from a different population, without our
electronics.

The 4-series still publishes nothing — DS-0143 says *"please contact SGX for temperature
performance other than 20 °C"* — so if the installed cells turn out to be an
Issue-1-qualified lot, that provenance has to be recorded before Issue 2's curve is
applied to them.

## 6. Firmware gaps this analysis exposed — all closed 2026-09-07

- **No zero-current register.** ~~`regmap.h` held only `CAL_AIR_NA`, `CAL_TEMP_C100`,
  `TEMPCO_PPM_K`.~~ **Fixed:** `CAL_ZERO_NA_HI/LO` at `0x0042/0x0043`, `I0` in the law,
  bounded on both write paths, `CONFIG_LAYOUT_VERSION` 2 → 3.
- **Tempco applied to `S`, not `K`.** ~~Algebraically equivalent only while `I0` was
  absent.~~ **Fixed:** the gain now scales `K`; the zero is subtracted uncorrected,
  because no zero-versus-temperature figure has been measured.
- **No fault bit for a missing zero.** **Fixed:** `CAL_ZERO_DEFAULT`, bit 13, taken from
  the never-written `EXP_PRESENT`. It invalidates nothing — the error it announces is
  bounded at 0.4 %O₂ — and the decoder's positional table moved with it.
- **The calibration cache could lie.** *Found by the review, not by this document.*
  A Modbus write updated `g_rm.cfg` — and therefore the readback and `CONFIG_CRC` —
  while conversion kept using a `g_cal` copy refreshed only at boot and after `COMMIT`.
  A master could verify its calibration by CRC and still be reading numbers produced by
  the previous one. The heater had always read `g_rm.cfg` live; calibration was the
  outlier. **Fixed:** the cache is gone, `cal_from_config()` builds the constants fresh
  every cycle.
- **`PRESSURE_HPA` is still a stub**; §4's ±0.45 %O₂ cannot be corrected until a
  barometer is fitted or an external pressure is published into the register from the
  gateway. Given the site is at 715 m and calibrated in situ, only the ±2 kPa weather
  residual is at stake — but that is still an order of magnitude above design C's
  calibration uncertainty.
- **Still open: HI/LO halves are not atomic.** Each 16-bit half is applied independently
  and only the *composed* value is bounds-checked, so a single-register FC06 write of one
  half is accepted whenever the result happens to be plausible. Inherent to a 16-bit
  register file; FC16 multi-register writes are all-or-nothing, and any composed value
  must still pass the bound. Use FC16 for calibration, and do not read the FC06 path's
  acceptance as atomicity.

## 7. Recommended calibration, and the honest accuracy claim

Minimum useful campaign — design **F** in §3, upgraded where it is free:

1. **N₂ zero + dry air**, at 5 temperatures spanning 10…60 °C, whole probe isothermal,
   ≥10 min plateaus, 30 s cadence. Log RH and absolute pressure at the air point and
   correct it to wet basis (±0.005 %O₂ achievable; ignoring the humidity of room air at
   22 °C/50 %RH is a 0.28 %O₂ error — the single most common way to poison an air span).
2. **4–6 blended points** at 2 or 3 of those temperatures, weighted by their reference
   uncertainty, to fit `I0` and to *look for* structured residuals in `C`.
3. **A pressure-dilution pass** near air (800–1200 mbar) to test the `pO₂` law itself.
4. **A CO₂ pass**: air blended with 5/10/20 % CO₂ at fixed O₂, to check the 0.3 %/1 %CO₂
   figure on the Mini. In a compost pile this is a +0.2…0.3 %O₂ bias that no O₂-only
   calibration will ever see.
5. **A split-temperature pass** (§5) if and only if the α that comes out of step 1 is
   large enough for heater gradients to matter.

With that in hand the defensible statement is:

> **calibration parameter uncertainty ≈ ±0.05 %O₂ (1σ, ±0.1 at k = 2)** across 0–21 %O₂
> and 10–60 °C for design C/F, §3 — *provided the fit is weighted by reference
> uncertainty*. That figure is parameter uncertainty inside a correct-model universe: it
> does not cover model closure, a repeatable temperature gradient (a gradient that
> changes by 1 K across the sweep biases α by ~5e-5 /K, comparable to σ(α) itself), or
> anything in §4. The field budget is dominated by vapour-basis definition (up to
> 3.5 %O₂ at 55 °C if wet/dry is confused), barometric weather (±0.45 %O₂ at air,
> uncorrectable today), CO₂ enhancement (+0.2…0.3 %O₂ at compost concentrations) and
> cell ageing (±1 %O₂ at air over life, re-spanned by the field air point).

Without the temperature sweep — i.e. exactly what ships today — the honest claim is
**±1.3 %O₂ at air and ±0.3…0.5 %O₂ in the 2–5 % range**, and `O2P_TEMPCO_DEFAULT = 0`
is correctly labelled in `o2.h` as no compensation rather than a compensation.

## 8. Adversarial review, 2026-09-07

A Codex `xhigh` review with live network and a headed browser attacked this document,
the firmware change and the decoder contract. Its access was verified: it fetched the
ADS1119 PDF (1 798 760 bytes, `%PDF`) and the LMP91000 product page through the browser,
reproduced this document's tables from the scripts, and re-ran the host tests.

Accepted and fixed in this revision:

| finding | disposition |
|---|---|
| Air reference encoded ±0.05 %O₂ where the prose said ±0.005 — a 10× typo in `fit_mc.py` | fixed; σ(K) for design C falls 0.29 % → 0.094 % |
| "More points make K worse" is an artefact of an unweighted estimator | accepted; §3 now reports both, and weighting is the recommendation |
| DS-0637 **Issue 2** supersedes Issue 1: 0.1 ± 0.03 mA, **and it publishes a temperature curve** | accepted; §5 rewritten, `o2.h` nominal 70 000 → 100 000 nA |
| "Capillary/Knudsen" conflates opposite scalings (Knudsen is `√T`, giving −0.17 %/K) | accepted; §5 corrected |
| The public claim lacks coverage semantics and systematic-error scope | accepted; the claim above now states 1σ/k=2 and what it excludes |
| **The calibration cache could report a CRC-verified new calibration while converting with the old one** | accepted; `g_cal` removed (§6) |
| The two-word HI/LO write is not atomic, and the test did not prove it was | accepted as a documented limitation (§6), not a defect to fix in a 16-bit register file |
| Gradient error drawn per point rather than per temperature level | fixed in `fit_mc.py`; σ(α) for D/E rises 2e-5 → 4e-5 /K |

Argued but not changed:

- **`CAL_ZERO_DEFAULT` should invalidate the compensated channel.** At the datasheet zero
  limit a missing zero moves a true 2.00 % to 2.35 % and a true 4.70 % to 5.00 %, which
  does cross a decision threshold. Left non-invalidating: invalidating blanks every probe
  built so far, which is how a guard gets switched off rather than satisfied. If the
  2–5 % band is to be trusted to 0.1 %O₂, the answer is to *take a zero point*, not to
  suppress the reading — the flag exists to say which regime a number came from. Fab's
  call if a degraded-quality state is wanted instead.
- **float32 can reject a mathematically in-range 30.0000 % result** (one-ULP effect at
  the overload boundary, found by five-million-case fuzzing that otherwise showed
  ≤0.000008 %O₂ error). Not worth double precision on a Cortex-M0+ soft-float build.
- **Fault bit 14 still disagrees** — `EXP_FAIL` in `faults.h`, `ads_config_lost` in the
  decoder. Nothing writes either, so nothing is wrong today; it belongs to whoever lands
  the ADS supervision.

## Sources

- SGX **DS-0637 Issue 2** (28-May-2026), SGX-OX-ROHS-Mini — the current issue, held at
  `compostlab-literature/datasheets/`: 0–25 %, output **0.1 ± 0.03 mA in air**, zero
  signal < 0.4 %vol O₂ @20 °C, `S = K·ln(1/(1−C))`, bias −600 ± 10 mV, −40…+60 °C,
  800–1200 mbar, long-term drift < 5 % over life, **and a `%20 °C Output vs Temperature`
  plot with ±3σ bands on page 2**. Issue 1 (07-Apr-2025) gave 0.07 ± 0.03 mA and no
  curve; it is what `o2.h` was originally written against.
- SGX **DS-0143** Issue 3 (4-series SGX-4OX): CO₂ enhancement ≈ 0.3 % of signal per
  1 %CO₂; *"please contact SGX for temperature performance other than 20 °C"*.
  Fetched via Angst+Pfister (Mouser's copy is behind PerimeterX).
- TI **SNAS506I** LMP91000: TIA gain accuracy 5 %, linearity ±0.05 %, internal-zero
  accuracy ±0.04 %, load accuracy 5 %, `TcVOS_RW` ±4…8 µV/°C. No TIA-gain tempco given.
- TI **SBAS925A** ADS1119: 62.5 µV<sub>RMS</sub> noise at gain 1 (all data rates),
  INL ±15 ppm FSR, gain error ±0.01 %, gain drift 2 ppm/°C max, offset drift 0.1 µV/°C max.
- TI **SNIS189** TMP117: ±0.1 °C max, −20…50 °C.

Scripts: `analysis/budget.py`, `analysis/fit_mc.py`, `analysis/field.py`; each is ~60 lines and
takes the constants above as its only inputs.

## 9. Second adversarial review, 2026-09-08

A second Codex reviewer was run against the committed state of `f4aac90` + `b5554e2`,
told explicitly that §8 was under test and not to be trusted, and asked to find where a
claimed fix does not fix the stated problem. It verified its own access (911 kB TI PDF
fetched through the browser, page 2 of DS-0637 Issue 2 rendered and hashed) and re-ran
the host suite itself. Thirteen findings; every one was re-derived here before acting.

### Fixed in code

| # | Finding | Disposition |
|---|---|---|
| 1 | `finish_o2()` converted the sample, *then* applied a requested air point, so `PH_PUBLISH` shipped the old value under the new `CONFIG_CRC` | **Confirmed and fixed.** The air point is now taken *before* the conversion, so the published value, the readback and the CRC are one calibration. Also makes a calibration cycle read ~20.95 % immediately instead of one cycle late. |
| 2 | One FC16 spanning `CAL_TRIGGER` and `COMMIT` raised both flags, and the main loop persisted the **pre**-calibration image while the calibration stayed in RAM | **Confirmed and fixed.** A co-requested commit is deferred until `finish_o2()` has taken the point (`commit_after_cal`). A lone commit is unaffected. Two tests. |
| 3 | `tempco_ppm_per_k` and `cal_temp_c100` were unbounded: `α` = +20000 ppm/K at 60 °C returns **4.503 %O₂ for a true 5.000 %** with `O2P_OK`; a far-negative `T0` collapsed the gain term to 0.04 | **Confirmed and fixed.** Both bounded in `o2p_config_valid()` (`o2.h`: ±10000 ppm/K = 5× the vendor slope; `T0` to the cell's rated −20…+60 °C). Three tests, verified by known-bad calibration — with the bound widened the write is *accepted*. A plausibility bound, not a correctness guarantee: a legal +3000 ppm/K over 40 K still moves 5.000 % to 4.880 %. |
| 8 | The "1-in-65536" rationale for the flash version bump was wrong | **Confirmed and fixed**, and re-derived independently here. Reading a v2 record as v3 hashes `msg ‖ CRC16(msg) ‖ 00 00`, which is identically zero and matches the relocated zero CRC field — the CRC check **passes** deterministically. What rejects a v2 record is `slave_addr` landing on a zeroed reserved byte. Two stale notes telling a maintainer to make the already-made bump were removed. |
| 9 | `O2P_ZERO_CAL_ABS_MAX_NA` documented as "about 3× the worst in-spec cell"; 5000/2218 = 2.25× | **Confirmed and fixed** (2.9× nominal, 2.25× worst-case). The Issue-1-derived **1194 nA** also still appeared in `regmap.h` and `FIRMWARE.md`; both now 1706 nA. |
| 10 | The derived net-air window assumed, without asserting, a non-negative zero magnitude and `AIR_MIN ≤ AIR_MAX` | **Confirmed and fixed.** Three more `_Static_assert`s. Editing only `O2P_AIR_CAL_MAX_NA` to 9000 used to invert the window and make *every* conversion unevaluable while the existing assertion passed. |
| 11 | The GLS weight used `dI/dC = K/(1−C)`, omitting the gain factor | **Confirmed and fixed.** Re-ran: σ(K)/K unchanged at 0.094/0.097/0.093/0.120 % — weights only need to be right up to a common scale. Corrected anyway, because a wrong derivative in a reusable weighting rule is load-bearing the next time. |
| 5, 6 | The accuracy headline is a simulation target quoted without scope, and the vendor curve is materially non-linear | **Confirmed; claims rewritten.** ±1.3 %O₂ is the **55 °C** value (+1.47 at 60 °C, 0.58 at 5 %O₂/65 °C), now stated with the temperature attached in `FIRMWARE.md`. The non-linearity is recorded in §5 as **UNVERIFIED** — it is a second eyeballing of a plot, not a digitisation, and per project rule a model's visual chart reading is never promoted to a sourced number. It is enough to retire "one linear coefficient suffices" as an assumption. |

### Escalated, not patched — these need a decision

- **The remaining provenance window (from #1).** A sample still carries no config
  identity, so an asynchronous Modbus write between `PH_O2` and `PH_PUBLISH` can still
  pair a value with a CRC describing a different config. Closing it means latching a
  config CRC or epoch **into the sample**, which costs a diagnostic register — and the
  diagnostic block is exactly where the decoder has already drifted (below). Documented
  in `FIRMWARE.md` as open rather than papered over.
- **A failed flash commit is silent** (#2). `o2p_config_store()`'s return is discarded
  in `main.c`. It cannot simply be reported: **all sixteen fault bits are allocated**,
  bit 13 having just gone to `CAL_ZERO_DEFAULT`. This needs a fault-word decision, not
  a patch.
- **No v2→v3 config migration** (#7). A reflashed probe loses air calibration, address,
  baud and parity together, so a re-addressed probe presents as *dead*, not reset.
  Harmless only while nothing is deployed; write the migration before the first field
  unit, or plan bench re-provisioning.
- **`CAL_ZERO_DEFAULT` is transmitted but nothing downstream acts on it** (#4). The
  decoder names bit 13 correctly yet still derives `comp_ok` from the sentinel alone;
  the Grafana panel still calls bit 13 `ADS_DRDY_STUCK` and treats `0xB000` as unknown.
  The reviewer argues the missing state is a machine-actionable **degraded quality**,
  which is neither today's fully-valid number nor the blanking §8 rejected. That is the
  same open decision §8 left for Fab, now with the downstream evidence attached.
- **The decoder reads three registers the firmware never implemented** (#13). It decodes
  `t_die`, `faults_ever` and `ads_fail_count` past the end of an 18-register diagnostic
  block, and Grafana queries `gas_faults_ever`. The firmware, not the decoder, is behind:
  a fault-ever latch and an ADS failure counter are real work, and they interact with
  both bullets above. Bit 14 (`EXP_FAIL` vs `ads_config_lost`) remains adrift.
- **No host test observes the sampler** (#12). `platformio.ini` excludes `main.c`,
  `config_flash.c` and `modbus_rtu.c`, so the cache removal, the publish ordering, the
  flash migration and the serial handover are all untested by construction — the two
  ordering fixes above are verified at the regmap boundary, not end-to-end. The suite
  is 66/66 and that number should not be read as covering the state machine.

### Survived

The corrected tables reproduce. "Weakly-referenced dilution points are harmless under
proper weighting" survived oracle-K, fitted-K, fully temperature-dependent weights,
iterative reweighting and a deliberately remote starting point. Drawing one gradient per
temperature level is the right correction. Rejected Modbus writes are genuinely
all-or-nothing. The flash record is exactly 64 bytes and a v2 record cannot be accepted
as v3. Removing `g_cal` did fix the unbounded stale-cache bug. The `0.00005/0.2095` air
reference is the correct spelling of ±0.005 %O₂. `≈ +0.2 %/K` survives as sign and order
of magnitude — but not as proof the single linear coefficient closes the model.
