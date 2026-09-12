# Costing: what a 2.5 V ADC full scale actually costs

> **ADOPTED — Fab, 2026-09-12: *"del u8"*, in the REF3425 form. This costing is
> now the record of how the price was arrived at, including the two things I got
> wrong; the binding spec is the foot of
> [`2026-09-12-revb-decision-delete-ads1119.md`](2026-09-12-revb-decision-delete-ads1119.md).
> All of it is implemented: `R25` 27k, `C26` 100 nF on `/VREF_TRIM`, `D8` on PA6,
> no divider, PA5 back to the pool.**

Written while the U8 deletion was contested and held, so that if Fab took it as
*"`VREF+` moves to the REF3425"* the work would already be priced. It is
arithmetic against the netlist, and two of its conclusions were corrected by
review before adoption — both corrections are in place below rather than
silently fixed.

Context: the Codex review overturned the reasoning that kept `VREF+` on VDDA —
VDDA is a buck output, not an LDO. The peer session's rejection reason 2 (the
rail monitors lose over-range headroom) does not disappear when the case for the
move improves; it converts from an objection into work. This is that work,
costed.

## The claim being tested

> "CE_MON, VA_MON and VIN_MON all need divider reworks."

**Overstated. One resistor changes.** Values read from the generator, not from
memory: `R24/R25` 47k/47k, `R26/R27` 91k/10k, `R43/R44` **91k/91k** (not the
100k pair an earlier note assumed).

| channel | divider | ratio | nominal | tap | max readable @3.3 V | @2.5 V | verdict |
|---|---|---|---|---|---|---|---|
| `VA_MON` | 47k/47k | 0.500 | 3.3 V | 1.650 V | 6.60 V | **5.00 V** | **rework** |
| `VIN_MON` | 91k/10k | 0.0990 | 12 V | 1.188 V | 33.3 V | 25.3 V | no change |
| `CE_MON` | 91k/91k | 0.500 | ≤3.3 V | ≤1.650 V | 6.60 V | 5.00 V | no change |

**`CE_MON` needs nothing.** `CELL_CE_DRV` is the LMP91000's CE output on a 3.3 V
supply, so it physically cannot exceed ~3.3 V and the tap cannot exceed 1.65 V.
Headroom above a rail an op-amp cannot drive past is not headroom.

**`VIN_MON` needs nothing.** A 25.3 V ceiling on a 12 V input is ample; the TVS
clamps below it.

**`VA_MON` is the only real one**, and it is one leg: `R25` 47k → **27k** gives
0.3649, so 3.3 V reads 1.204 V and the ceiling goes to **6.85 V** — better than
today's 6.60 V. Source impedance falls 23.5 k → 17.2 k, further inside the 50 kΩ
`RAIN` limit. One E24 value, one BOM line.

## Two costs I claimed, one of which was void

### 1. The 3V3D rail monitor — WITHDRAWN

I called this the sharpest cost in the thread. **It was wrong, and the second
review killed it on two independent grounds.** Both verified here:

- **Nothing consumes it.** `grep -c VDDA firmware/src/regmap.h` returns **0** —
  there is no VDDA register. And `R32` is 10 Ω into 3V3A carrying ~100–200 µA
  after the deletion, so **`VA_MON` already reads 3V3D to within 1–2 mV** —
  better than the proposed divider's own 70 nA x 23.5 kΩ = 1.65 mV of leakage
  error. Two parts for a worse copy of a reading that exists, and it would
  **re-create the 23.5 kΩ high-impedance node the VREF-monitor decision existed
  to destroy.**
- **It could not see the thing that justifies it.** `ts` = 160.5 cycles at
  `fADC` = 16 MHz (verified: `mcu.c:99`, HSI16 with HSIDIV = /1, no PLL) is a
  **10.03 µs boxcar with its first null at 99.7 kHz**. It averages the buck's
  switching content to nothing. The release gate needs a scope or a deliberate
  peak detector, not an ADC channel.

So the divider is **dropped**, and the summary below changes with it.

### 2. `/VREF_TRIM` on PA5 becomes degenerate — but the reference stays watchable

If `VREF+` **is** `/VREF_TRIM`, converting `/VREF_TRIM` reads exactly full
scale — code 4095, saturated, carrying no information. **PA5 returns to the
pool.**

> **Corrected 2026-09-12 by the peer session.** I first wrote that this makes the
> reference *unwatchable*. It does not: converting `VREFINT` against a 2.5 V full
> scale **becomes** the reference check, because `VREFINT` is a known voltage. The
> loss is the dedicated channel, not the observability.

### The symmetry, which is what makes this decidable

`VREFINT` gives you exactly **one** of {VDDA, the reference} for free. The other
costs parts, and they are **not** equally priced:

| `VREF+` | free from `VREFINT` | the other one | parts |
|---|---|---|---|
| VDDA, 3.3 V | VDDA | `/VREF_TRIM` is 2.5 V, **under** FSR → direct on a pin | **0** |
| REF3425, 2.5 V | the reference | VDDA is 3.3 V, **over** FSR → needs a divider | **2** |

Neither option gives up observability. The whole asymmetry is that 2.5 V fits
under a 3.3 V full scale for free and 3.3 V does not fit under 2.5 V.

So the question reduces to: **is it worth two resistors to take the buck's PFM
ripple out of the ADC's full scale?** At ~4.63 mV RMS per 0.1 %O2, with
`VDDCoeff` 1200 ppm/V max landing on that same rail, two resistors look cheap.

## One thing the move gains that nobody counted

**Resolution improves 24 % on every channel.** LSB goes 806 µV → 610 µV at 12
bits. `/ADC_AFE_VOUT` at 33.2 mV/%O2 goes 0.024 → 0.018 %O2 per count.

And the electrode pedestal stops being a coincidence: with `VREF+` = `VREF_TRIM`,
`V_RE` sits at (0.67 + 0.24) = **0.91 × full scale exactly, ratiometrically**, so
it tracks the reference instead of drifting toward the rail. The 91 % is tight —
225 mV of absolute headroom — but it is *stable* tight, not *drifting* tight,
which is the version that does not clip.

## Summary for the decision

| item | parts | note |
|---|---|---|
| `R25` 47k → 27k | 1 changed | restores `VA_MON` over-range past today's |
| `CE_MON`, `VIN_MON` | 0 | no change needed; the claim was overstated |
| 3V3D monitor divider | **0** | **withdrawn** — `VA_MON` already reads it to 1–2 mV |
| 100 nF at `VREF+` | +1 | required by the move |
| Schottky on **PA6**, not WE/RE | +1 | see below; my first placement was wrong |
| `/VREF_TRIM` self-check | — | moves to `VREFINT`, PA5 frees up |

Net: **one value change, one 100 nF, one Schottky** — against a reference 8x
better in tempco, 24 % more resolution, and the buck's ripple out of the ADC
scale entirely.

## The Schottky is on the wrong pins — mine were

I put the clamps on `WE_BUF`/`RE_BUF` on a "cell on long buried leads" premise.
**Both halves of that are wrong**, and the netlist says so plainly: `WE_BUF` is
`U4.1` + `U4.2` and `RE_BUF` is `U4.6` + `U4.7` — **OPA2333 outputs**, in
follower. The cell cannot back-drive them; that is the entire reason U4 exists.
U11 is also socketed on-board, so "long buried leads" was a bench condition.

**Table 50, read from a clean extraction** (an earlier pass collapsed its merged
first row):

| pins | negative injection | positive |
|---|---|---|
| all except PA4, PA5, PA6, PB0, PB3, PC0 | **−5 mA** | N/A |
| PA4, PA5 | −5 mA | 0 mA |
| **PA6**, PB0, PB3, PC0 | **0 mA** | N/A |

The exposed pin is **PA6 = `VIN_MON`**, rated **zero** negative injection and
reached through `R26`'s 91 kΩ from `+12V_SW` — the only analog channel with a
path to the external supply cable. My three new FT_a channels (PA0, PA1, PB1)
all sit in the −5 mA group. PA5 carries `/VREF_TRIM` and is one of the two rated
0 mA *positive*, which does not fire: at 2.5 V it is below VDDIO1, and SBAS804G's
zero-load dropout of 100 mV means the output tracks `VIN − 0.1 V` on the way up.

A design item, not an emergency — D3/D1 bound it to about −10 µA.

**The precise statement, which took both sessions to reach:** the exposed *pin*
is pre-existing — `git show HEAD:gen_sch.py` has `MCU_NETS[17] = VIN_MON` before
any of this, and PA0/PA1/PB1 are all in the −5 mA group, so the consolidation
adds no exposed pin. But the **coupling from that pin to oxygen is what the
deletion creates.** Before it, an injection on PA6 could degrade `CE_MON` and
`VA_MON` while oxygen sat on the ADS1119 and was immune *by being on a different
converter*. After it, footnote 3's "**another** analog input" includes oxygen.

So: a pre-existing item that the deletion **promotes from cosmetic to
load-bearing**. It should be fitted either way, and it belongs in this review
rather than in a general layout note.

> **Method note.** The pin classes above rest on **two independent renders** of
> Table 50 that agree — mine and the peer session's corrected one. An earlier
> `pdftotext` pass over that same table collapsed its merged first row and
> produced the wrong classes. A single unverified render of a merged-cell table
> is how a 14x leakage error got into this thread earlier the same day. Two
> renders is the standard for any merged table either session cites from here.

## The oxygen formula I was given is wrong for this architecture

This must not reach a sampler port. The handover carried
`I = VREF/FS x (0.67 x code_REF − code_AFE) / R_TIA`, which is the **VDDA form**.
With `VREF+` = `/VREF_TRIM`, `code_REF` converts the reference against itself and
**saturates at 4095**. Correct form:

```
I = V_REF x (0.67 − code_AFE / 4095) / R_TIA       V_REF a compile-time constant
```

The old form degenerates to the right answer only by luck and only for half the
population: at `EG` = −5 LSB the channel reads ~4090 and leaves **0.06 %O2 of
zero error** that an air-point gain calibration does not remove. It also makes
oxygen depend on a clipped channel, which `ads1119.h:126` and `main.c:1176` both
explicitly refuse to do. Same defect class as the `O2P_HW_DIV_VREF` landmine.

## Two free diagnostics the 2.5 V full scale creates

Neither is written down anywhere, and both replace something the ADS1119 took
with it:

1. **`ADC_CALFACT` is readable after `ADCAL`.** Publishing it per boot gives a
   per-part proxy for converter offset and its drift — a functional stand-in for
   the shorted-input self-check P4 built on the ADS, at **zero parts**.
2. **The pedestal becomes an absolute check.** Once `VREF+` = `/VREF_TRIM`,
   `V_WE` = 0.67 x FS exactly (**code 2744**) and `V_RE` = 0.91 x FS exactly
   (**code 3727**), both to the LMP91000's ±0.04 % internal-zero accuracy. So
   `WE_BUF` becomes an independent measurement, on a different pin, of the very
   pedestal the oxygen subtraction uses — a **stronger** per-channel leak
   detector than Rev A ever had.

## Reference drift: the term everyone mis-weighted

`VDDCoeff` (1200 ppm/V max) is **immaterial** — 0.0015 %O2 across the rail's own
60 mV range. Two passes over-weighted it, including mine.

What was badly under-counted is `VREFINT`'s **`ACoeff`: 1000 ppm max per 1000
hours**. A buried probe runs continuously, so that is **0.183 %O2 at a year** —
comparable to the entire static budget — against the REF3425's 25 ppm/1000 h.
A 40x argument for the REF3425 form, on the axis that actually matters for a
sensor nobody can reach.

## The surviving objection, run down

> "Every row of DS12232 Table 60 is specified at `VDDA = VREF+`, and ST publishes
> nothing for `VREF+ < VDDA`."

**Half of that is confirmed and half is too strong.** Checked directly against
the archived DS12232 Rev 5 — no fetch needed.

**Confirmed:** every conditions cell in the ADC accuracy table reads
`VDDA = VREF+ = 3 V`, `2 V < VDDA = VREF+ < 3.6 V`, or
`1.65 V < VDDA = VREF+ < 3.6 V`. There is no row with an unequal condition. `EL`,
`EO`, `EG`, `ET`, `ED` and `ENOB` are **not** re-specified at a lower `VREF+`.

**Too strong:** ST does not merely permit `VREF+ < VDDA`, it **ships a feature
whose entire purpose is that operating point**, and specifies it.

- §"Power supply schemes": *"When VDDA ≥ 2 V, VREF+ must be between 2 V and
  VDDA"* — explicitly permitted, not tolerated.
- §3.16 **VREFBUF**, the on-chip reference buffer, drives `VREF+` to **2.048 V or
  2.5 V** — the 2.5 V setting *requiring VDDA ≥ 2.8 V*, i.e. requiring
  `VREF+ < VDDA`.
- **Table 63** specifies that mode in full: `VREFBUF_OUT` 2.497/2.500/2.503 V at
  VRS = 1, line regulation, load regulation, PSRR, start-up, `CL` 0.5–1.5 µF.

And this part has it. Not inferred from the feature matrix, whose column
boundaries are ambiguous in the text layer — taken from the **pin table**, per
`PIN-IDENTITY-POSTMORTEM.md`: LQFP48 **pin 5 is `VREF+` with additional function
`VREF_OUT`**, which is the buffer's output. §3.16's only stated exclusion is
packages where the `VREF+` pad is double-bonded to VDD/VDDA; this package has a
dedicated pin.

### So the objection narrows, and it is worth restating precisely

Not *"an uncharacterized mode"*. It is: **the ADC's own INL, offset and gain are
not re-specified at a lower `VREF+`, even though ST ships and specifies a
reference buffer that puts you there.** That is a documentation gap in a
supported configuration, not an excursion outside the datasheet.

### One thing this rules OUT

**VREFBUF is not a substitute for the REF3425.** Table 63 note 3: the tempco at
the `VREF+` output is the **sum** of `TCoeff_vrefint` and `TCoeff_vrefbuf` —
50 + 50 = **100 ppm/°C max**, worse than `VREFINT` alone and 17x worse than the
REF3425's 6. Its value to this decision is purely as evidence that ST designs for
`VREF+ < VDDA`; as a reference for this board it is the worst of the three.

C10's 4.7 µF is outside Table 63's 0.5–1.5 µF `CL` window, which is moot with
VREFBUF disabled and inside the REF3425's own 0.1–10 µF stable range.
