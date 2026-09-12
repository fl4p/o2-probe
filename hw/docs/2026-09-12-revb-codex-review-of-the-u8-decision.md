# Codex review of the U8-deletion decision — VERDICT: NO

Reviewer: `codex exec`, gpt-6-astra at `model_reasoning_effort=xhigh`, network on,
headed Chrome attached over CDP. Ran 14:59–15:10, exit 0. Log:
`~/codex-reviews/o2probe-revb-adc-20260912/review.log` (434 kB), prompt beside it.

**Its verdict: NO — do not delete the ADS1119 on the evidence as written.** Five
findings. **I verified the four load-bearing ones against the datasheets, the
firmware and the working tree, and all four hold.** This document records them;
the decision in
[`2026-09-12-revb-decision-delete-ads1119.md`](2026-09-12-revb-decision-delete-ads1119.md)
is annotated as CONTESTED and is Fab's to re-take.

## Access

Browser worked: it fetched TI's ADS1119 PDF and returned the true first-page
heading. **The VictoriaMetrics query came back `unverified` — `ssh` failed with
`Permission denied (publickey,password)`.** That was NOT the reviewer's fault and
it is worth recording as a tooling fact: the ssh-agent holds only an RSA key
(`fab@Franks-MBP`), which exhausts the auth attempts before the ed25519 key is
offered. `ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes root@100.64.0.3` works.
Earlier commands in the same session succeeded before the agent picked up that
key. I re-ran the analysis the reviewer could not, below.

## The four findings that hold

### 1. (a) The error budget priced ONE conversion; the calculation uses THREE

Oxygen subtracts two conversions and takes scale from a third. Independent INL at
the two input voltages gives `q(0.67*e_REF - e_AFE)` = `0.805664 * (2.01 + 3)` =
**±4.04 mV = ±0.122 %O2**, not the ±0.073 I wrote. Verified arithmetic.

**And `EO` should never have left the budget.** DS12232 Table 60 **footnote 2:
"ADC DC accuracy values are measured after internal calibration."** Verified by
rendering p.92. `ADCAL` is a *precondition of the spec*, not an improvement on
it, so my "removed by `ADCAL`" row was simply wrong. Worse, a common offset does
not cancel in the subtraction, because the coefficients sum to `0.67 - 1 =
-0.33`: at zero oxygen ±4.5 LSB contributes ≈ **±0.036 %O2**. VREFINT's own
conversion error adds ≈ **±0.042 %O2** in air.

Corrected worst case is ≈ **0.20 %O2** summed linearly (≈0.13 RSS) against the
cell's 0.38 %O2 over 20 K. **The margin is ~2x, not the 5–18x I claimed.**

### 2. (c) The premise changed under me: `VREF+` now sits on a BUCK output

`gen_sch.py:905` — *"REV B, 2026-09-12 — PATH A. U2 and U3 (both TPS7A2033) are
DELETED with the 5 V rail. 3V3D comes straight off the buck"*, and the generator
names *"the buck's PFM bursts"* in the very next note. Verified.

So "keep `VREF+` = VDDA, it's an LDO" was decided against a topology that no
longer exists. My own decision doc said this "must be coordinated with
`2026-09-12-revb-single-rail-supply.md`, not decided independently" — and then I
did not read it. That document already names the noise as **the release gate**.

The reviewer's sensitivity analysis: with unequal full scales at the two input
conversions an additive pedestal survives *even at zero oxygen* — "same cycle" is
not sufficient. Coupling ≈ **0.588 mV/mV in air, 0.718 mV/mV at zero**, so only
**4.63 mV RMS** of supply variation costs 0.1 %O2. It is fair and says LDO
*intrinsic* noise (7–10 µV RMS, SBVS338H p.7) would have been harmless — but
those LDOs are gone. It also found **VREFINT's voltage coefficient, 1200 ppm/V
max** over 3.0–3.6 V, a residual supply dependence I never accounted for.

**The categorical rejection of the `VREF+` move is overturned.** That does not
make a direct REF3425 connection proven — Table 60's characterization condition
is still a real objection — and the headroom objection can be answered by
rescaling dividers, which I treated as fixed.

### 3. (a) "The extra resolution never reached anyone" is false

I checked `afe_vout_mv` and missed the actual measurement channel.
`sampler_logic.h:40` computes the cell current from the **ADC code**, and
`main.c:1179` publishes `o2_raw` at **10 nA per count** — 70 µV across 7 kΩ,
which is the ADS1119's LSB. The register was sized to the ADS. Verified.

A bare MCU conversion is **10.6x coarser** into that channel. The resolution in
%O2 (0.024) is unchanged and still adequate for compost, so the *conclusion* may
survive — but the *argument* was wrong, and the reviewer is right that a
reversible firmware truncation cannot establish adequate hardware precision for
potted hardware.

### 4. (a) The 0.43 mV noise figure has no defensible status

Two parts, both correct. First, the filter I documented **was not in the
committed script** — it lived in a throwaway heredoc, so the published number was
not reproducible from the file I cited. Fixed: `o2p_adc_noise_from_vm.py` now
implements the die-temperature join (`--die`, `--dT`).

Second, `sd/sqrt(2)` needs zero adjacent covariance. **Measured lag-1
autocorrelation: r = +0.96.** So the estimator does not give `sd(Y)`. Being
precise about what that means, because the reviewer's wording could be read too
harshly: high positive r means the series is dominated by slow *real* variation,
which is exactly what differencing removes, so the figure is the high-frequency
component and that was the intent — `sd(Y) = 151 mV` here is oxygen, not noise.
What is *not* defensible is the number: with a 1 mV quantum and **72.1 % of
differences at zero**, the result is quantization-limited. The honest claim is
**"the chain's high-frequency noise is below 1 mV and this telemetry cannot
resolve it further"**, not "0.43 mV rms".

## Finding 5 (c), medium: diagnostic independence is reduced

VREFINT survives as an absolute reference independent of the REF3425, so a
reference collapse stays detectable — the reviewer explicitly declined to
overstate this. What is lost is the second *converter* and the ADS's
shorted-input offset self-check. Multiple channels on one ADC give consistency
evidence but cannot separate a reference-node fault from a selective ADC-input
fault — which is the exact ambiguity that cost five hours on 09-11.

## One thing the reviewer did not flag, found while verifying footnote 2

DS12232 Table 60 **footnote 3**: *"Injecting negative current on any analog input
pin significantly reduces the accuracy of A-to-D conversion of signal on another
analog input. It is recommended to add a Schottky diode (pin to ground) to
analog pins susceptible to receive..."* With all four channels on one converter
and a cell on long leads, a negative excursion on an electrode input degrades the
**oxygen** reading. The ADS1119, as a separate part, isolated that. This wants
Schottky clamps on the electrode inputs if the deletion proceeds.

## Where this leaves the decision

Not "the MCU ADC cannot do this". The resolution and leakage conclusions survive.
What collapsed is the *justification*: the budget was understated ~2–3x, one
argument was circular and factually wrong, the noise figure was overstated, and
the supply premise changed. Plus the buck.

The reviewer's own recommendation, which I endorse: **retain a precision
conversion option until the corrected static budget and a measured comparison
pass.** The Rev B PCB has not been updated, so keeping U8's footprint costs
almost nothing now and buys the measurement that settles it on real hardware.
