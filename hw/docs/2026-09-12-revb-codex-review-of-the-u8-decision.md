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

## Two corrections from the Rev B session, both verified here

**My R32 / U3-EN item was VOID as a Rev B suggestion, and I had the evidence in
front of me.** I derived it from the Rev A netlist — where it is correct: Rev A's
`/+5V_ANALOG` carries `R32.2, U3.1(IN), U3.3(EN)` with EN strapped to its own
input behind a 10 Ohm series resistor, and `grep -c 'ref="U3"'` on that netlist
returns 6. But `place("U2"|"U3")` in `gen_sch.py` returns **0** — both LDOs are
gone, so Rev B has no EN pin to strap and R32 is now simply 10 Ohm from 3V3D to
3V3A, buck output straight to the AFE. I had already read that exact line while
verifying the buck finding and did not connect it to my own earlier suggestion.

The error was one of scope, not of fact: a correct Rev A finding appended to a
Rev B handover as a Rev B suggestion. **It remains the live bench hypothesis for
Rev A's intermittent 3V3A**, which does have U3, and the three R32 readings are
still the next bench step. Rev B simply cannot exhibit it.

**VDDCoeff verified independently:** DS12232 §5.3.4, `VDDCoeff` = **250 typ /
1200 max ppm/V** over 3.0 V < VDD < 3.6 V. This was never in the budget and it
lands on precisely the rail whose ripple is the open release gate.

**The Schottky item is promoted from a note to a design item.** Footnote 3 is a
CROSS-CHANNEL effect, and the consolidation onto one converter is what creates
it: four channels on one ADC plus an electrochemical cell on long buried leads
means a negative excursion on `/ADC_WE_BUF` or `/ADC_RE_BUF` corrupts the
**oxygen** reading. Correctly NOT implemented yet — adding parts to a contested
deletion would be building on it.

## If the decision is re-taken as "move VREF+ to the REF3425"

Recorded because it is the likely shape of a revised decision and it has a
consequence nobody has costed: the pin allocation is unaffected, but **every MCU
ADC channel's full scale changes from 3.3 V to 2.5 V**, so the rail monitors lose
over-range headroom and `CE_MON`, `VA_MON` and `VIN_MON` all need their divider
ratios reworked. That is the item I originally listed as rejection reason 2, and
it does not disappear when the reason for the move improves — it becomes work.

## The VREF+ trade, reduced to its actual shape (2026-09-12, after revB's costing)

revB costed the move and corrected my "three divider reworks" — it is **one
resistor**. Verified from the generator: `VA_MON` 47k/47k (R25 47k -> 27k gives a
6.85 V ceiling, *better* than today's 6.60, with source impedance falling 23.5k
-> 17.2k); `VIN_MON` 91k/10k keeps a 25.3 V ceiling on a 12 V input; `CE_MON`
91k/91k needs nothing, because `CELL_CE_DRV` is an LMP91000 output on a 3.3 V
supply and cannot exceed it — headroom above a rail an op-amp cannot drive past
is not headroom.

Their cost 1 is correct and is the sharpest thing anyone has found here.
**There is no divider on 3V3D** — verified, its only net members are the buck
inductor, decoupling, R32 and the I2C pull-ups. VDDA is known *only* through
`o2p_mcu_adc_read_vdda_mv` (`mcu_adc.c:115`), whose formula
`VDDA = TS_CAL_VDDA_MV * cal / raw` is valid precisely because FSR = VDDA. Move
`VREF+` and that conversion returns the reference instead, so **VDDA becomes
unmeasurable** on a board whose digital rail is a buck output and whose ripple
is the open release gate.

**But their cost 2 is overstated, and the correction matters.** With
`VREF+` = REF3425, converting VREFINT does not lose the reference check — it
*becomes* it. That was the original P0 mechanism. What is lost is only the
dedicated PA5 channel, which does go degenerate at code 4095.

So the trade is a symmetry, and stating it this way makes it decidable:

**VREFINT gives you exactly ONE of {VDDA, the reference} for free. The other
costs parts — and the two are not equally priced.**

| `VREF+` | free from VREFINT | the other one costs | extra parts |
|---|---|---|---|
| **VDDA, 3.3 V (buck)** | VDDA | `/VREF_TRIM` is 2.5 V, **under** FSR -> direct on a pin | **0** |
| **REF3425, 2.5 V** | the reference | VDDA is 3.3 V, **over** FSR -> needs a divider | **2** |

Neither option gives up observability. The asymmetry is only that 2.5 V fits
under a 3.3 V full scale for free while 3.3 V does not fit under 2.5 V.

**Which reframes the whole question as: is it worth two resistors to take the
buck's PFM ripple out of the ADC's full scale?** On the numbers — 4.63 mV RMS of
supply variation costs 0.1 %O2, plus VREFINT's 1200 ppm/V max landing on that
same rail — two resistors look cheap. It also buys 24 % more resolution on every
channel (LSB 806 -> 610 uV, AFE_VOUT 0.024 -> 0.018 %O2) and makes the RE
pedestal ratiometric: `V_RE` sits at 0.91 x full scale exactly, so 225 mV of
headroom becomes stable-tight rather than drifting-tight.

**The one objection that survives all of this** is unchanged and is not
answerable from a datasheet: every row of DS12232 Table 60 is specified at
`VDDA = VREF+`, and ST publishes no accuracy figure for `VREF+` < VDDA. That is
now the single open question gating the reference architecture — not parts, not
observability, not headroom.

## The last objection narrows: ST ships a feature whose purpose is `VREF+` < VDDA

Found by revB, verified here against the archived DS12232 Rev 5 — and two of the
three lines were already in my own earlier greps, unregistered. Second time
today that has happened; noting the pattern, not just the fact.

**Confirmed, exactly as stated:** every conditions cell in Table 60 reads
`VDDA = VREF+`. `ET`, `EO`, `EG`, `ED`, `EL` and `ENOB` are genuinely not
re-specified at a lower `VREF+`.

**But "uncharacterized" was too strong.** §3.16: the on-chip VREFBUF drives
`VREF+` to *"around 2.5 V (requiring VDDA equal to or higher than 2.8 V)"* —
a mode that **requires** `VREF+` < VDDA. Table 63 then specifies it in full:
`VREFBUF_OUT` 2.497 / 2.500 / 2.503 V at VRS = 1, trim step, load regulation,
PSRR, start-up, `CL` 0.5–1.5 µF, ESR ≤ 2 Ω. And LQFP48 pin 5 carries the
additional function `VREF_OUT`, the buffer's output, so this part has it;
§3.16's only exclusion is packages where the VREF+ pad is double-bonded.

So the honest restatement: **the ADC's INL, offset and gain are not re-specified
at a lower `VREF+`, even though ST ships and fully specifies a reference buffer
that puts you there.** That is a documentation gap in a SUPPORTED configuration,
not an excursion outside the datasheet — materially weaker than my wording.

**And it rules one thing out before anyone reaches for it.** VREFBUF is not a
substitute for the REF3425: Table 63 note 3 says the tempco at the `VREF+`
output is the **sum** of `TCoeff_vrefint` and `TCoeff_vrefbuf`, 50 + 50 =
**100 ppm/degC** max — worse than VREFINT alone and 17x worse than the
REF3425's 6. Its only value here is as evidence of ST's design intent.

Also worth knowing: **C10's 4.7 µF is outside Table 63's 0.5–1.5 µF `CL`
window.** Moot with VREFBUF disabled, and inside the REF3425's own 0.1–10 µF
stable range — but the two parts want different capacitors on the same pin, so
"enable VREFBUF as a fallback" is not free.
