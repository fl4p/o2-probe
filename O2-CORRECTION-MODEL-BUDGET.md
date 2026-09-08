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
> exactly linear by construction. Adding synthetic temperature points **to the Monte
> Carlo** therefore cannot expose it — but a **real** multi-temperature campaign can,
> and directly: fit the affine model to measured data and read the curvature straight
> off the residuals against calibration temperature. (An earlier revision of this
> paragraph said the campaign itself could not expose the error. That was wrong, and it
> mattered: it would have argued against running the very experiment that settles the
> question. Corrected after the third review.) So step 1 of §7 should retain its
> residuals versus temperature, not just its fitted `α`.
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
**±1.3 %O₂ at air and ±0.3…0.5 %O₂ in the 2–5 % range, both at 55 °C**. Those are points
on a rising curve, not bounds: the same model gives **+1.47 %O₂ at air/60 °C** and
**0.58 %O₂ at 5 %O₂/65 °C**, outside the range just quoted. Never quote either figure
without the temperature attached. `O2P_TEMPCO_DEFAULT = 0` is correctly labelled in
`o2.h` as no compensation rather than a compensation.

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

## 10. Third adversarial review, 2026-09-08

A third reviewer was run against `d89765b`, told §8 and §9 were the thing under test, and
asked specifically to find where a claimed fix does not fix its stated problem or
introduced a new defect. It did both, and it found something neither earlier round had
looked at.

### The one that matters most: the probe was mute on the bus

**`s_frame_ms` was read by the Modbus response deadline and assigned nowhere.** It sat at
0 for the life of the probe, so `o2p_elapsed(0, 400)` was true for every frame once
uptime passed 400 ms, and every request was discarded as "too old to answer". A probe
polled every five minutes would have answered **nothing, ever**, from the first
half-second onward.

This is pre-existing — not from this review cycle's changes, and older than the
provenance and calibration work both earlier rounds spent their attention on. It survived
two adversarial reviews because `modbus_rtu.c` is excluded from the host build, so no
test could see it, and because the first two rounds were pointed at the conversion path.
The lesson is finding 12's, sharpened: **the untested files are where the fatal bug was**,
and a green 69/69 says nothing about them. Now timestamped where the end-of-frame gap is
detected.

Alongside it, `s_rx_poisoned` was also declared and never used, so the ISR's promise that
a parity or framing error produces silence was not kept: the error handler clears the
buffer and then falls through and re-stores the errored byte, restarting the frame from
it. A parity error whose data bits happen to be correct yields a valid CRC and the
request **executes**. Now set on the line error and tested at frame-ready.

### Regressions this cycle introduced, and other fixes

| # | Finding | Disposition |
|---|---|---|
| 3 | `commit_after_cal` could be stranded forever: `finish_o2()`'s ADS-failure early return never consumes it, and a repeatedly failing ADS still publishes and feeds the watchdog | **Confirmed regression, fixed.** The commit is released on that path, so an acknowledged config write is persisted instead of being lost at the next reboot. `cal_requested` stays set to retry. Worse than the race it replaced, exactly as claimed. |
| 4 | `o2p_calibrate_air()` stored `cal_temp_c100` unconditionally, so an automatic calibration could create a config that `o2p_config_valid()` rejects — **blocking every later Modbus write and commit** until someone repaired the register over a bus the probe had just made hostile | **Confirmed regression, fixed.** The bound is enforced at the point of storage. Swept by a test over the whole `int16` range asserting the two guards agree exactly. |
| 4b | The −20 °C floor was described as "the cell's rated range" and is not — DS-0637 rates **−40 °C** | **Confirmed, corrected to −40 °C.** The round-2 test asserting −36 °C implausible was itself wrong and is inverted. Note the consequence: round 2's attack config is legal again, because both values are individually legitimate. What catches the collapsed gain is the **runtime** `gain > 0.05` guard returning `UNEVALUABLE` — the right place, since it depends on measurement temperature and not on the config alone. Now tested. |
| 6 | A calibration could be taken during the mandatory 15-minute settle: the gate ran before `cycle_publish()` adds `SETTLING`, so a transient current could become the permanent air constant of a sample invalidated seconds later | **Confirmed, fixed.** The settle deadline is tested directly. |
| 8 | The reorder removed a real veto. A 180 µA reading used to convert to ~34.6 %O₂ against the old constants, trip `ADC_RANGE` and be refused; afterwards it was accepted and read back a perfect 20.946 % | **Confirmed, fixed** — and "loses no check that mattered" in §9 was false. A freshly *measured* air point is now held to 150 µA, above Issue 2's 130 µA population maximum, while the *stored* window stays 20–200 µA for aged and hand-entered constants. A cell does not gain sensitivity with age. |
| 13 | Issue 1 arithmetic still in six places: `0.07 mA` in the README chain, `0.04–0.10 mA` and `±43 %` in `faults.h`/`faults.c`/`main.c`/`FIRMWARE.md`, and a "true air reads 12 %" example | **Confirmed; §9's claim that these were fixed was wrong.** Issue 2 is 0.07–0.13 mA about 0.10 mA, i.e. **±30 %**, and substituting the nominal makes true air read **15.2–26.3 %**, not 12–30 %. All corrected. Stale test counts (61, 59) also corrected. |
| 14, 15 | §7 repeated ±1.3 / ±0.3–0.5 without the 55 °C qualifier; §5 concluded that a temperature campaign could not expose the curvature | **Both confirmed and corrected.** §15 mattered most: it argued against running the very experiment that settles the question. A real multi-temperature campaign exposes curvature directly through residuals against calibration temperature; only adding *synthetic* points to a linear-by-construction Monte Carlo cannot. |

> **Rows above were audited by the fourth review and five of them overstated
> completeness.** The `commit_after_cal` row fixed only the one-frame case and left
> the documented two-request procedure broken; the ADS-release row traded a stranded
> commit for a premature one that lost the calibration; the gain-guard row named a
> guard that a binary32 corner walks straight through; the fresh-air row rested on a
> claim DS-0637 does not make; and "all Issue 1 arithmetic corrected" was false for
> the second time. All are now genuinely fixed and recorded in §11. Treat any
> "confirmed and fixed" in this document as a claim to be re-tested, not a receipt.

### Still open, and now harder to defend

- **The async provenance window (7)** is unchanged, and the reviewer is right that the
  main loop polls Modbus *between* `PH_O2` and the publish step, so the window is wider
  than "inside one cycle". It argues this is a design defect needing a sample epoch, not
  a documentation note, because `CONFIG_CRC` is *presented* as provenance. That is a
  fair reading and it needs a register.
- **Silent flash-commit failure (9).** The reviewer rejects "all sixteen fault bits are
  allocated" as a reason, and is correct: a status register or a verifiable commit
  protocol needs no fault bit. This is now a design task, not a blocked one.
- **`CAL_ZERO_DEFAULT` (10)** and **the decoder/firmware register mismatch (11)** stand
  as in §9. On (11) the reviewer adds the operational consequence: the decoder accepts
  only 21- or 24-register replies while firmware serves 18 and **rejects longer reads
  with exception 02**, so a node issuing the documented poll gets no diagnostic block at
  all. That is a live integration defect, not future work.
- **No host test observes the sampler, the RTU ISR or flash (12)**, and this round
  proved what that costs. Two of the five round-2 tests were also judged weak: the
  calibrate-and-commit test observes only the intermediate flags, and the commit-alone
  test passes under both old and new behaviour. Both stand as regression guards, neither
  is evidence the fix completes.

## 11. Fourth adversarial review, 2026-09-08

Run against `1fca66f`, pointed at the files with no host coverage on the theory that round
3's fatal bug proved where the defects live. It cleared the drivers — **no second
`s_frame_ms` exists**; both Modbus fixes survive scrutiny, including the question of
whether a stranded poison flag could re-mute the probe (it cannot: every RTOF clears it).
The flash A/B protocol survives in full. But it found ten more, and its most useful work
was auditing §10's own honesty: **five of seven "fixed" rows overstated completeness.**

### The calibration command protocol was broken in three more ways

| # | Finding | Disposition |
|---|---|---|
| 1 | The **documented** commissioning procedure — write `CAL_TRIGGER`, then `COMMIT` as two requests — still persisted the pre-calibration image. The round-2 fix covered only both tokens inside one FC16 | **Confirmed and fixed.** A `COMMIT` arriving while a calibration is outstanding now defers exactly as the one-frame case does. This is the sequence the manual tells an operator to use, so the original fix closed the rare path and left the common one open. |
| 2 | Round 3's ADS-failure release traded a stranded commit for a **premature** one: it persisted the pre-calibration config while the request was still outstanding, and when the ADS recovered the air point landed in RAM with no commit behind it | **Confirmed and fixed.** The wait is now *bounded* (three cycles) rather than released immediately or held forever: a transient fault gets grace, a persistent one abandons the calibration explicitly and then releases the commit. Neither stranded nor premature. |
| 3 | A calibration was accepted with a **fabricated 25.00 °C** reference when both temperature sensors failed — temperature faults are deliberately outside the raw-O₂ validity mask, so nothing caught it | **Confirmed and fixed.** A calibration now requires a *measured* temperature. Substituting a fallback for the *conversion* is recoverable; storing one as the permanent calibration reference is not — the probe would carry a false reference for life while looking calibrated. |
| 5 | `gain > 0.05f` does not catch every legal collapsed gain: Tcal −40 °C, T +55 °C, α −10000 ppm/K gives exactly 0.05, which in binary32 rounds to 0.0500000119 and compares **greater** than the threshold. Returns **5.001 %O₂ with `O2P_OK`** from a negative current, every input inside its own published guard | **Confirmed and fixed.** The floor was the wrong *shape* — it asked "is K non-zero" when the question is "is this a plausible temperature correction". Now bounded to 0.5–2.0: a correction that halves or doubles sensitivity is a broken coefficient. Tested at the exact corner and swept for monotonicity. |
| 8 | The TMP117 range check was **tautological** — any `int16` raw word converts into the range it was tested against, so every bus pattern was accepted as a temperature. One flipped MSB turns 25 °C into −231 °C, which at a legal tempco turns a true 5 %O₂ into ~10 % | **Confirmed and fixed.** Bounded against the part's rated −55…+150 °C (SNIS189). This is the guard-checklist's "unevaluable input must not mean OK" failing in a driver no review had opened. |
| 6 | The 150 µA fresh-air ceiling rejects an allowed corner: 130 µA × 1.05 (temperature) × 1.05 (TIA gain) × 1.05 (lifetime drift, whose sign DS-0637 does **not** restrict) = 150.5 µA. The "a cell only loses sensitivity with age" rationale is not in the datasheet | **Confirmed and fixed** — ceiling raised to 155 µA. A destructive guard must not treat an allowed corner as impossible. The 180 µA wrong-gas case it exists for is still refused. |
| 7 | The SHT heater-recovery return skipped the `TEMP_OVER` test while `finish_o2()` still used the TMP117 fallback, so a 70 °C sample was published tempco-corrected without the extrapolation qualifier | **Confirmed and fixed.** The tip-temperature overtemperature test now runs on that path too. Round 3 raised this and it was not addressed then. |
| 4 | A refused calibration is still reported as Modbus success. `CAL_TRIGGER` reads back zero, there is no result/status register, and comparing constants is ambiguous when the old value matches | **Confirmed, NOT fixed — escalated.** With the settling, temperature, fresh-current and zero refusals now in place there are four ways to be silently refused, so this matters more than when it was one. It needs a command-result register, which is a contract change. |
| 9 | `s_safety_armed` reads back only `CONFIG`, never `THIGH`/`TLOW`, so a corrupted threshold still certifies the autonomous heater cutoff as armed | **Confirmed, NOT fixed — escalated.** Dormant (`O2P_HEATER_ENABLE=0`), but it is precisely the interlock `DESIGN.md` says must be fault-tested before the heater may ever run. It belongs with that bench test, not with a review fix. |
| 10 | "All Issue 1 arithmetic corrected" in §10 was **false for the second time** — stale values remained in `faults.h`, `DESIGN.md`, and four test fixtures | **Confirmed and fixed.** The new numbers themselves were verified correct: Issue 2 is 0.07–0.13 mA, ±30 %, true air reads 15.1705–26.3282 %. |

### What this round establishes about the process

Three rounds in a row have found that the previous round's fix was incomplete or
introduced a new defect, and this round found five of seven `§10` rows overstating what
was fixed. The failure mode is consistent and worth naming: **a fix aimed at the specific
case a reviewer described, rather than at the class it belongs to.** The one-frame
`CAL_TRIGGER`+`COMMIT` fix that missed the documented two-request sequence is the clearest
example; the near-zero gain floor that a rounding corner walks through is the same error
in arithmetic.

`main.c`, `modbus_rtu.c` and `config_flash.c` still have **no host coverage**, and the
calibration command path — now carrying four distinct refusal reasons, a bounded wait and
a deferred commit — is entirely inside `main.c`. Every fix in this section is verified at
the regmap boundary or by direct unit call, not end-to-end. That gap is now the largest
single risk in this firmware, ahead of anything in the correction model.

## 12. Fifth adversarial review, 2026-09-08

Run against `5b49a09` and told its primary job was to test whether round 4's fixes
repeated the pattern §11 named. **They did**, most importantly in the gain guard.

### The gain guard was the wrong mechanism, twice

Round 4 replaced `gain > 0.05f` with `0.5 < gain < 2.0`, and this review walked through it
**from the inside**: α = +9999 ppm/K over a 100 K span gives gain 1.9999, and a true
5 %O₂ reports as **2.53 %** with `O2P_OK`. Narrowing an interval does not close a class
when the damaging values are *inside* it. Worse, the same bound *rejected* a legal
configuration — α = +10000 ppm/K at the widest legal span gives gain exactly 2.0 and
returned `UNEVALUABLE` forever, a guard refusing inputs its own contract permits.

The mechanism was wrong from the start. A gain of 1.9999 is **not detectably bad at
conversion time**: if α really is that large the correction is correct, and if it is not,
nothing in `o2.c` can tell. So the defence moved to where it belongs:

- **`O2P_TEMPCO_ABS_MAX_PPM_K` 10000 → 5000**, i.e. 2.5× the published curve instead of
  5×. This is now the number that bounds the damage, so it is the number that has to be
  defensible — and 2.5× a published curve is, where 5× was not. Worst legal correction is
  now a factor of 1.5, not 2.
- **The runtime check is documented as a backstop**, sized to admit exactly the box the
  configuration validator accepts (0.45–1.55) and nothing else. It catches a corrupted
  float or an out-of-contract caller. It does not certify the coefficient, and the code
  now says so.

A wrong-but-legal α remains undetectable by any runtime check. Only characterisation
bounds it. That is a limitation to state, not to guard away.

### Also fixed

| # | Finding | Disposition |
|---|---|---|
| 2 | The "three-cycle" ADS wait actually waited **four** — `if (c < MAX) c++` | **Confirmed and fixed.** Small, but a bound nobody can compute is not a bound. |
| 3 | A repeated `CAL_TRIGGER` inherited the previous request's **exhausted** retry budget, so an operator retrying got a shorter grace period each time, silently | **Confirmed and fixed** with a renewal flag. |
| 5 | An ADS failure made the heater's supply interlock **fail open**: `finish_vin()` returns early on a latched ADS fault and never raises `VIN_LOW`, so an *unmeasured* rail authorised ~86 mA | **Confirmed and fixed.** An interlock whose input is missing must fail closed. Dormant only because the heater is compiled out. |
| 7 | `sht4x.c` **repeats the tautological-range-check defect** — both bounds equal the transfer function's own image over all 65536 words, so neither could ever fire | **Confirmed and fixed** against the part's rated −40…+125 °C and 0–100 %RH. The same class as the TMP117 bug found in round 4, in the driver next door. |
| 9 | `o2p_mcu_adc_read_vdda_mv()` bounded its inputs but not its **result**: a corrupted VREFINT sample yields 4350 mV on a part that cannot run there, and supervision only ever checks for *low* voltage | **Confirmed and fixed.** |
| 10 | The heater runaway detector accumulated its 60 s window **without requiring valid evidence**, so an outage followed by one high-ΔT sample latched immediately — contradicting its own "sustained" contract and permanently disabling heat for a reason that never happened | **Confirmed and fixed.** |
| 6 | `gen_hw_contract.py` checked the **wrong pins** for the I²C address straps — U8.2/U8.3 (DGND/AGND) and U10.5 (V+) instead of U8.15/16 and U10.4. It passed only because those power pins sit on the same nets | **Confirmed and fixed.** The strapping itself is correct and the addresses are right; the guard was proving it by coincidence. |
| 8 | §11 escalated the TMP117 threshold readback as bench work. It is ordinary firmware | **Correct, and I was wrong to escalate it.** `verify_safety()` now reads back `THIGH`/`TLOW` against what it programmed. The *physical* ALERT fault test remains a genuine release gate; conflating the two was over-broad scoping that deferred work I could simply do. |
| 12 | The TMP117 fix cited **SNIS189**; the datasheet is **SNOSD82D** | Fixed. The limits themselves were confirmed correct. |
| 11 | The 155 µA stack is arithmetically right, but the 1.05 temperature factor is a *mean* curve read by eye, so "covers the full legitimate population" is **unverified** | **Accepted as unverified**, and the unsupported "cells only lose sensitivity with age" rationale is deleted rather than re-argued. Resolved by digitising the curve, not by asserting harder. |

### Still open

Finding 1 is the one that keeps coming back and it is now clearly a **design** gap, not a
bug: the deferred calibration and commit are **not a transaction**. There is no
configuration snapshot, no request generation, no durability across reboot, and no
completion result — so a config write after `COMMIT` is swept into that commit, a reboot
between request and execution loses an acknowledged command silently, and a flash failure
is still discarded. Five rounds have each fixed one ordering; the class needs a snapshot
plus a generation counter plus a command-result register. That is a contract change and it
is Fab's call.

The review also corrected §11's scoping of the command-result register: a calibration can
be refused **eight** ways, not four — settling, invalid temperature, implausible current,
implausible zero, plus LMP I/O, AFE mismatch, `VA_LOW` and `ADC_RANGE` through
`o2p_o2_valid()` — and every one of them returns Modbus success.

## 13. Sixth adversarial review, 2026-09-08

Run against `561b5d0`, told to test round 5's central claim hardest and that a clean round
would be a valuable outcome. It was not clean, and its best finding was that **round 5's
"fix" to the tempco bound was itself unjustified**.

### The tempco bound was never a safety bound, and three rounds pretended otherwise

Round 5 tightened `O2P_TEMPCO_ABS_MAX_PPM_K` 10000 → 5000 and called it "2.5× the
published curve". The review dismantled that:

- The firmware stores a **lumped cell-plus-AFE** coefficient. DS-0637's ±3σ envelope alone
  implies 2000–3200 ppm/K for the *cell*, and **LMP91000 publishes no temperature
  coefficient for its TIA gain at all** — so the legitimate lumped value cannot be bounded
  from datasheets in either direction.
- Therefore 5000 risked **refusing a correctly characterised probe**, with no service
  override. That is worse than the failure it was meant to prevent: it blocks calibration
  outright, and this instrument has no calibration data yet.
- And it never limited damage anyway. At 5000 ppm/K over 100 K a true 5 %O₂ already reads
  **3.36 %** — an order of magnitude past the 0.1-point tolerance the probe exists for.

So the bound is back at 10000 ppm/K with an **honest and much narrower claim**: it rejects
gross corruption — a byte-swapped word, a misplaced decimal — and nothing else. It is not
an accuracy bound and the header now says so explicitly, along with the reasoning, so the
next round does not re-tighten it for the fourth time.

**The general lesson, now stated in the code:** accuracy is a property of the calibration
data. Three consecutive rounds tried to buy it with a range check, in three different
places, and each attempt either let the damaging case through, refused a legitimate one,
or both.

### The runtime guard was silently revoking a contract

Round 5 sized the runtime window to "admit exactly the legal box and nothing else". Both
halves were wrong. "Nothing else" is impossible — at ΔT = 0 *any* coefficient gives gain 1.
And "exactly the box" was computed over the **rated** −40…+60 °C range, while this firmware
deliberately keeps reading above 60 °C and flags `TEMP_OVER` as a still-valid
extrapolation. At 70 °C a legal configuration hit the window edge and returned
`UNEVALUABLE` — **the guard was cancelling the thermophilic-pile extrapolation the probe
exists to provide.** The check is now documented and sized as what it can honestly be: an
arithmetic guard that keeps K positive and finite and rejects NaN. A regression test pins
the above-60 °C contract.

### Also fixed

| # | Finding | Disposition |
|---|---|---|
| 4 | The round-5 TMP117 `THIGH`/`TLOW` readback was **unreachable**: `init()` set `s_safety_armed` after checking `CONFIG` alone, and the periodic verify ran only `if (!armed)` — so it never ran, and a part that lost its thresholds was never caught *because* nothing re-checked it | **Confirmed and fixed.** `init()` now certifies through the same routine, and the periodic check runs unconditionally. A verification that only runs when you already know the answer is not a verification. |
| 5 | The supply interlock **still failed open** on a different missing input: `finish_vref()` raises `ADC_RANGE` but keeps the 2500 mV default, and `finish_vin()` scales VIN with it — an actual 2.0 V reference makes an actual 8 V input measure ~10 V and pass the 9 V interlock. Round 5 fixed the instance it was shown, not the class | **Confirmed and fixed.** |
| 7 | The new SHT4x RH window **rejected datasheet-allowed output**: Sensirion permits values outside 0–100 %RH and directs clamping, and documents a temporary +3 %RH offset after long exposure above 80 %RH — exactly this application. A −3…103 % rejection would have refused readings from a wet probe, the condition the channel exists to observe | **Confirmed and fixed**, and the numbers are now labelled an engineering choice rather than a rated limit. |
| 8 | The round-5 runaway fix **opened a false negative**: restarting the window on any invalid sample let one bad reading per 59 s keep a genuinely runaway 1 W heater from *ever* latching. It also still timed zero duty rather than sustained high ΔT, so one high sample after a quiet minute latched | **Confirmed and fixed** by timing the *condition*: the window starts when ΔT is first high at zero duty, clears when ΔT is seen normal, and an unevaluable cycle **holds** rather than advancing or discarding. Both failure directions are now tested. |
| 9 | Three round-5 tests **passed with their implementation reverted** — they asserted header constants, not the code using them | **Confirmed and fixed properly.** The pure decision logic moved into the headers (`o2p_sht4x_decode`, `o2p_vdda_from_vrefint`), so the host tests exercise the shipped path; `sht4x.c`/`mcu_adc.c` still cannot compile on the host because they reach CMSIS. Verified by reverting the *logic* rather than the constants: three tests now fail. |

### Still open

- **The calibration/commit transaction** (§12) is unchanged and remains the largest design
  gap: no snapshot, no generation, no durability across reboot, no completion result.
- **A corrupted-but-plausible VREFINT sample** is now pinned by a test rather than fixed.
  The window catches an impossible 4350 mV, but raw 1436 against a 1650 calibration reads
  3447 mV — enough to lift a real 3.000 V rail past the 3.130 V `VA_LOW` threshold.
  Closing it needs the **independent ADS1119 AIN2 measurement of 3V3A, which is wired and
  never sampled**. That is a sampler change, not a bound.
- **Host coverage** is worse than §11 recorded: besides `main.c`, `modbus_rtu.c` and
  `config_flash.c`, the native filter also excludes `sht4x.c`, `mcu_adc.c` and `tmp117.c`.
  Extracting their decision logic into headers narrows the gap but does not close it.

## 14. Seventh adversarial review — and the decision it forces

Its verdict on §13, quoted because it is correct: *"This is not a clean round. The
tempco/gain reversal is capitulation dressed as honesty."*

Round 6 talked me into removing the only enforced plausibility layer without adding the
calibration-quality mechanism the same prose said must own accuracy. That is the
guard-review checklist's **fix-vs-mute** failure — removing the warning without changing
the underlying quantity — and I committed it while quoting the checklist elsewhere in the
same document.

Concretely, widening to 10000 ppm/K with a 0.05 gain floor **reintroduced a failure round
4 had already found**: α = −10000 ppm/K, Tcal −40 °C, read at 55 °C gives a binary32 gain
of 0.0500000194, which passes `> 0.05f` and returns ≈5 %O₂ with `O2P_OK` **from a negative
current**. Verified here directly before acting.

### Rounds 6 and 7 disagree, and the disagreement is adjudicated rather than alternated

- **Round 6 was right** that 5000 ppm/K cannot be justified as "2.5× the published curve",
  and that refusing a real characterisation would block calibration outright.
- **Round 7 was right** that datasheet *silence* on the LMP91000 TIA gain tempco means
  **unknown, not arbitrarily large**, and licenses nothing.

The ceiling is back at **5000 ppm/K, explicitly provisional**: it is a corruption and
gross-implausibility screen, not an accuracy certificate, and if a real characterisation
lands above it the correct response is to *raise it against that measurement and record
the evidence* — not to treat the refusal as a hardware problem. Refusing is visible and
recoverable; accepting a wrong coefficient is silent and produces a wrong decision in a
pile. The runtime window returns to **0.5–2.0, justified by physics** rather than by a
computed box: the published curve moves output ~20 % across its whole range, so a
correction that halves or doubles sensitivity is not credible whatever the register says.
An extreme coefficient at an extreme calibration temperature now yields `UNEVALUABLE` —
no value, never a wrong one — and that distinction is pinned by its own test, alongside
one proving every *realistic* calibration converts through the 85 °C extrapolation.

I also dropped a false claim of my own: the bound is **not** a byte-swap screen. Tempco is
a single 16-bit register, and 1024 ppm/K (`0x0400`) swaps to 4 (`0x0004`) — both pass,
silently turning a real coefficient into no correction at all. (The example first used
here, 1000 → −6141, is actually *rejected* by the restored ±5000 bound; the conclusion
survives, the example did not. Corrected 2026-09-08.)

### Also fixed

| # | Finding | Disposition |
|---|---|---|
| 3 | The runaway detector **still counted invalid wall time as evidence**: round 6 held the start timestamp across invalid samples, so the elapsed test credited the unobserved gap and **two isolated high samples 60 s apart latched** | **Confirmed and fixed.** The state is now an *accumulator of observed valid high-ΔT seconds*, with each observation's contribution capped. The common bug in all three previous shapes was asking "how long ago did this start" instead of "how much have I actually seen". Four sequences tested, including clock wrap. |
| 4 | `ADC_RANGE` **conflates rail validity with O₂ range** — it is raised both by a bad VREF and by a saturating oxygen conversion, so my round-6 interlock disabled the heater for a polarity error or stale zero, as a "supply" fault | **Confirmed and fixed** with a cycle-local `vref_ok` predicate. The bit stays shared for O₂ validity; the interlock now tests what it actually means. Round 6 fixed the instance, not the class — again. |
| 5 | The SHT4x and TMP117 comments **confuse input ratings with guaranteed output bounds**, and TMP117's ±0.3 °C means a true 150.0 °C endpoint could read 150.3 °C and be refused | **Confirmed; comments corrected** to call these operational plausibility screens rather than bus-error proofs. The assumption that the probe's own ~85 °C limits leave ample margin is now recorded rather than relied on silently. |
| — | A duplicated `#include "heater_ctl.h"` in `regmap.c`, present since before this cycle and caught by no reviewer | Removed. |

### The decision this forces, and it is Fab's

**The firmware has no calibration-quality gate, and that is now the load-bearing gap.**
`CAL_DEFAULT` clears the moment `cal_air_na > 0`; nothing records whether a *temperature*
characterisation ever happened. So a probe calibrated with N₂ + air at one
temperature, with `tempco = 0` against a true +2000 ppm/K cell, reports a true 5 %O₂ as
**5.34 %** and a true 2 % as **2.14 %** — with a completely clean fault word. (An earlier
revision said "air alone"; that case additionally raises `CAL_ZERO_DEFAULT`, so the fault
word is not clean even though the value is still published. The one-temperature N₂+air
case is the one that shows the gap with nothing set at all.) That is the project's own §3 result
(0.3–0.5 points at 55 °C for air-only) arriving as an unmarked number.

No range check can fix this, which is the one thing every round since the third has
agreed on. What would:

1. **Record calibration provenance and completeness**, not just constants — which points
   were taken, over what temperature span, with what residuals.
2. **Do not present a compensated value as fully valid until temperature characterisation
   exists.** All sixteen fault bits are allocated, so this means either broadening
   `CAL_DEFAULT` to "calibration model incomplete" or publishing quality in a **new status
   register**.
3. **An acceptance target computed per probe, not a stored constant.** To hold 0.1
   percentage points at a true 5 %O₂ the coefficient error must be within roughly
   **+565/−543 ppm/K over a 40 K span** and **+251/−241 ppm/K over 100 K** — *for a cell
   near +2000 ppm/K*. The limit depends materially on the fitted coefficient itself: at
   −3200 ppm/K it tightens to about **±439 ppm/K over 40 K** and **±137 ppm/K over 100 K**,
   and applying the +2000 figures there would admit 0.13–0.18 points of error. (An earlier
   revision of this section quoted ±550/±245 as universal limits. They are not; verified
   and corrected 2026-09-08.) **The gate must compute its limit from the fitted
   coefficient and the operating span**, not store one universal pair. Either way it is
   **9× to 37× tighter** than the ±5000 register bound (5000/565 through 5000/137), which
   is why the bound was never the answer. (An earlier revision said "two orders tighter";
   that overstated it, though not the conclusion.)

4. **Acceptance rules the §14 sketch did not include**, and each is needed before the
   compensated channel is certifiable to 0.1 points: a valid **zero** point (today
   `CAL_ZERO_DEFAULT` is non-invalidating), an explicit **residual / model-closure**
   criterion, and a check that the probe is **operating inside the characterised span**
   (today `TEMP_OVER` extrapolates past it and stays valid). Recording points, span and
   residuals is the foundation, not the gate.

Option 2 changes what the instrument publishes and would mark every existing probe's
compensated channel as incomplete. **That is a contract decision, not a review fix**, and
it is the same open question as `CAL_ZERO_DEFAULT` from §8 — now with a second, larger
instance behind it. It sits with the calibration/commit transaction (§12) as the two
things a reviewer cannot decide for you.

## 15. Eighth adversarial review — the adjudication holds, the accounting did not

The verdict I asked for, and it settles the oscillation between §13 and §14:

> **"The 5000 ppm/K and 0.5–2.0 adjudication itself lands reasonably."**

Independently checked and confirmed: DS-0637's plot runs ~84 % at −40 °C to 105–106 % at
+60 °C, so ±5000 ppm/K and a factor-of-two runtime window sit generously outside observed
cell behaviour without pretending to certify accuracy. And across the whole realistic space
— Tcal 0…40 °C × coefficient ±3200 ppm/K × measurement −10…85 °C — **gain stays within
0.728…1.272, so nothing realistic is refused.** The explicit `UNEVALUABLE` corner is a
coherent tri-state policy rather than a revoked contract. That question is closed.

### The runaway detector was wrong a fourth time, in a fourth way

Capping each observation's contribution at 5 s **still credited the cap across a blind
gap**: thirteen instantaneous high observations 100 s apart accumulated 60 s of "evidence"
and latched with the condition never actually watched. My own test stopped after the
second isolated sample, when the false evidence was only 5 s, so it missed the class it was
written for — the same mistake in the test as in the code.

A gap longer than the cap now **discards** the accumulated evidence rather than clipping
its contribution: after a real outage the honest state is "start again". The alternating
valid/invalid case still accumulates, correctly — seeing high ΔT at both ends of a
two-second interval is genuine evidence about that interval — and both directions are now
tested, including the 20-burst sequence that defeats clipping.

**Crediting that interval is an explicit sampling assumption, not continuous
observation** — §15 first called it "genuine evidence", which overstated it. Within the
cadence bound the condition is *taken* to have persisted between two observations of it.
That is why the bound is a statement about the caller's rate rather than a tuning knob,
and the ninth review showed what happens when it is wrong in the other direction: at a 6 s
cadence against the original 5 s bound, valid high samples at 0, 6, 12 … **never
accumulated at all**, masking a genuine runaway forever. The bound is now 10 s, tied
explicitly to the sampler's nominal 1 Hz cycle, with both failure modes recorded at the
constant.

Four rewrites, four different accounting errors, on ~20 lines. Worth recording as a
pattern: every one of them came from *choosing a proxy for the thing being measured* —
elapsed wall time, then time-since-start, then capped-gap — instead of accumulating the
observation itself.

### Arithmetic and documentation errors in §14 itself

| # | Finding | Disposition |
|---|---|---|
| 3 | **±550/±245 ppm/K are not general acceptance limits.** They are local to a true +2000 ppm/K cell. At −3200 ppm/K the limits tighten to ±439 over 40 K and ±137 over 100 K, and applying the +2000 figures there admits 0.13–0.18 points of error | **Confirmed and corrected**, recomputed here independently. The gate must compute its limit **from the fitted coefficient and span**, not store a universal pair. |
| 2 | The §14 gate sketch is **not yet a sufficient specification**: "temperature characterisation exists" does not require a valid zero point, a residual/model-closure criterion, or that the probe is operating *inside* the characterised span | **Accepted; §14 amended** with those three acceptance rules. Recording points, span and residuals is the foundation, not the gate. |
| 4 | The byte-swap example was wrong: swapped 1000 → −6141 **is** rejected by the restored ±5000 bound | **Corrected.** The conclusion survives with a real example: 1024 (`0x0400`) swaps to 4 (`0x0004`) and both pass, silently turning a real coefficient into no correction at all. |
| 5 | "Air-only has a completely clean fault word" is false — it also raises `CAL_ZERO_DEFAULT` | **Corrected.** The case that genuinely shows the gap with *nothing* set is a one-temperature N₂+air calibration. |
| 6 | The comment cleanup **missed the public headers**: `tmp117.h` and `sht4x.h` still called an out-of-range result a bus error, and stale test prose still said "five times the curve" and called −10000 ppm/K legal | **Confirmed and fixed.** §14's "comments corrected" row was overstated, exactly as §§10–13 were. |

### Standing

`vref_ok` survives full scrutiny — cleared in `cycle_begin()`, set only on the valid branch,
cannot be stale, and removing `ADC_RANGE` from the interlock loses no real protection.
`runaway_evidence_s` cannot overflow. The remaining open items are unchanged and both are
Fab's: the **calibration-quality gate** (§14, now with a sharper specification) and the
**calibration/commit transaction** (§12).

One honest note on coverage, from the review: of the tests added last round, one would have
passed against the parent implementation, and **no host test covers the `vref_ok`
integration at all** because `main.c` is excluded from the native build. That remains the
structural gap behind every "verified" claim in these sections.

## 16. Ninth adversarial review — the runaway detector's fifth shape

It broke the fifth shape too, from the direction the fourth had over-corrected into.

**The sampling cadence was an unstated assumption, and it was wrong.** Valid high-ΔT
observations at 0, 6, 12 … seconds accumulated **nothing** against the 5 s gap bound, so a
caller only slightly slower or more jittery than 1 Hz would have masked a genuine runaway
forever. Requirement (c) — never preventable from latching — failed.

That is the same defect as the one before it wearing the opposite sign, and the reason is
now written at the constant: **the detector cannot derive the caller's rate, and without it
"sparse sampling of a real runaway" and "isolated glimpses across blindness" are the same
data.** `O2P_HEATER_RUNAWAY_MAX_GAP_S` is therefore documented as a statement about how
often we look — 10 s, ten missed cycles against the sampler's nominal 1 Hz — with both
failure modes recorded beside it, and an instruction that it must change if the cadence
does. It is not a tuning knob.

I also stopped calling the credited interval "genuine evidence". It is an explicit
**sampling assumption**: within the cadence bound the condition is *taken* to have persisted
between two observations of it.

### And a test that could not have caught it

The cadence test I first wrote looped `period` up to `O2P_HEATER_RUNAWAY_MAX_GAP_S`, so it
adapted to whatever the constant became and passed happily with the bound tightened back to
5 s. That is exactly the "asserts the constant, not the behaviour" weakness the sixth
review identified — repeated by me, two rounds later, in the fix for the finding it
produced. The periods are now absolute (1, 2, 5, 6, 8 s), and the known-bad calibration
fails as it should.

### Corrections

| # | Finding | Disposition |
|---|---|---|
| 3 | "Two orders tighter than any register bound" overstates it — the ratios are 5000/565 ≈ 8.8× to 5000/137 ≈ 36.5× | **Corrected to 9×–37×.** The conclusion is unaffected. |
| 4 | §15's cleanup claim was **overstated again**: a test still called −10000 ppm/K "legal by design" (stale across the round 6/7 reversal, and contradicted by another current test), `sht4x.h` said the rejection was *not* proof of failure and then that out-of-range *means the part is failing*, and `faults.h` said `CAL_DEFAULT` "does NOT invalidate either" while the bit has always been in `O2P_FAULTS_INVALIDATE_O2_COMP` | **All three confirmed and fixed.** The `faults.h` one mattered most: the mask was right and the prose contradicted it, in the file that defines what the fault word means. |
| 5 | `o2p_ads1119_code_to_uv()` documented as returning **millivolts** though it returns microvolts and every caller assumes so; and `0x30420F13` decodes to `SCLDEL=4, SDADEL=2`, not `SCLDEL=0, SDADEL=4` — the comment mis-assigned the reserved `[27:24]` nibble | **Both fixed.** Neither changes behaviour; both are the kind of comment a future reader would have trusted. |

### Standing

Nine rounds. The detector alone has now been rewritten five times; every failure came from
substituting a proxy for the thing being measured, and the fifth shape's proxy — a fixed
gap bound — is at least now *named as an assumption about the caller* rather than presented
as a property of the data.

The open items are Fab's: the **calibration-quality gate** (§14, sharpened by §15), the
**calibration/commit transaction** (§12), and — a third, which §16 first wrongly omitted —
the **sample/config atomicity window** (§9, §12), where a poll landing between the
conversion and the publish can pair an old-calibration reading with a new `CONFIG_CRC`.
No reviewer can decide any of them; all three change what the instrument publishes.

## 17. Tenth review, and where this stops

The tenth reviewer was asked for an explicit convergence verdict and told that a clean one
would end the loop. It returned:

> **NOT CONVERGED: the calibration/commit protocol can acknowledge and then lose a
> calibration on power cycle, while the absent calibration-quality gate can publish
> decision-wrong O₂ with a clean fault word. The runaway loop itself has converged.**

That splits the work cleanly, and it is why the review loop stops here.

### The runaway detector is done

Five rewrites and five accounting errors, and the sixth shape survives a full adversarial
pass: a first observation contributes zero, valid high-to-high intervals within the cadence
contract add their exact delta, a valid normal observation clears everything, a longer gap
discards it, commanded duty clears timing, and wraparound and accumulator bounds are sound.
**No sixth accounting error was found inside the chosen contract.** Its residual limits —
it can false-latch if two high observations bracket unobserved normal behaviour inside
10 s, and can miss a runaway if jointly valid observations stay more than 10 s apart — are
inherent to observing a process at a finite rate, and are now stated at the constant rather
than hidden.

### Fixed in this round

- **`SETTLE_S` reported "settled" before the first publish.** `memset` left it at 0, and 0
  explicitly *means* settled, so a master polling in the boot second read the contradictory
  pair `SETTLING=1, SETTLE_S=0`. A commissioning script trusting the dedicated countdown —
  which is what it is for — would trigger a calibration that firmware silently refuses
  against its own deadline while Modbus reports success. Now initialised to the full
  period, with a `_Static_assert` tying the register map's placeholder to `main.c`'s
  authoritative deadline so the two cannot drift.
- **§16 claimed only two items remained.** There are three: the sample/config atomicity
  window is a distinct open item, not a sub-case. Corrected.

### The three that stop being "open" and start being release-blocking

The reviewer's judgement, which I agree with after nine rounds of trying to fix around
them: these are not preferences awaiting a tidy moment. Each produces a wrong outcome in a
realistic commissioning, and each needs a decision that changes the published contract.

1. **A successful Modbus reply does not mean the calibration was taken or persisted.**
   `CAL_TRIGGER` returns success on setting a RAM flag; the point is taken cycles later;
   the flash store happens later still and its result is discarded. Trigger, commit, both
   acknowledged, power-cycle before the next `finish_o2()` — the calibration is gone, and a
   flash failure is externally identical. **Needs**: a command-result register, a
   generation/epoch, and a reported store outcome. **The command-result register and the
   store outcome are now built — see §18. The generation/epoch is deliberately deferred.**
2. **A one-temperature N₂+air calibration publishes with a completely clean fault word**,
   and at a true +2000 ppm/K cell used 35 K from its calibration point that is a true
   5.00 % reading as 5.34 % — across the turn/no-turn threshold. **Needs**: recorded
   calibration provenance and a rule that withholds full validity until characterisation
   exists (§14, with the acceptance limits computed per probe, §15).
3. **A poll landing between the conversion and the publish** pairs an old-calibration
   sample with a new `CONFIG_CRC`. **Needs**: a config epoch latched into the snapshot.

All three cost register-map space, and the diagnostic block is exactly where the ChirpStack
decoder has already drifted ahead of the firmware (§9, §11) — so they should be designed
together with that reconciliation, not one at a time.

### Why the loop ends here

Ten rounds; every round through the ninth changed code. The tenth changed one register
initialisation and otherwise re-derived the same three items. A eleventh would re-derive
them again: **a reviewer cannot decide a contract, and these three are contract changes.**
The largest structural risk is also unchanged and not a review finding — `main.c`,
`modbus_rtu.c` and `config_flash.c` have no host coverage, which is where two of the three
fatal bugs found in this whole cycle lived.

## 18. `CMD_RESULT`, and what deliberately stays undone

Item 1 above is closed, and the framing that left it open was wrong. Calling it "a contract
change only the operator can decide" made a single diagnostic register sound like a
negotiation: nothing in the published map is renumbered, nothing already deployed changes
meaning, and the diagnostic block had room. The escalation cost more than the fix.

`CMD_RESULT` (`0x0022`) reports the outcome of the last calibration trigger in its high byte
and the last flash store in its low byte — 0 none, 1 pending, 2 OK, 3 failed. It closes
three failures that were previously indistinguishable from success on the bus:

- a calibration refused by `finish_o2()` (still settling, no measured gas temperature,
  invalid raw O₂, current outside the fresh-air window),
- a calibration abandoned after the bounded converter wait,
- a flash store that failed — `o2p_config_store()`'s return value was discarded outright,
  so a worn page or a brownout mid-write left the master believing the config was persisted
  while the probe still ran from RAM.

The commissioning protocol is now: write the trigger, poll `CMD_RESULT` until neither byte
reads 1, require 2 in both. Each byte latches until its own command is issued again, so a
commit outcome can never overwrite a calibration that is still outstanding — that packing
mistake is what the fourth new test constructs and observes fail.

**Not built, on purpose.** The generation/epoch counter of item 1, item 2's calibration
quality gate and item 3's config epoch are all deferred: this probe is going into a pile,
and the register that was actually missing is the one that says whether the last command
worked. The remaining two are real and stay open — §14 and §15 hold the numbers — but they
want evidence from a deployment rather than more design against an imagined one. The
acceptance limits in §15 cannot be validated on a bench that has never seen the cell drift.

**Test-coverage caveat, stated rather than papered over.** The new tests drive the register
and the setters end-to-end over Modbus, and three of the five fail when the decision logic
is reverted. That `main.c` calls the setter on each refusal path is verified by reading
`main.c` — it reaches CMSIS and does not build on the host. `main.c` remains the largest
untested surface in the tree.
