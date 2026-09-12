# Second independent review of the U8 deletion — VERDICT: YES, in the REF3425 form

Reviewer: independent Claude agent (Opus), 46 tool calls, ~18 min. Pointed
deliberately away from the Codex pass's ground at the part nobody had reviewed:
whether the REVISED architecture is sound. Eleven findings, and it re-verified
Codex's four independently.

**Verdict: delete U8 — YES, but only with `VREF+` = REF3425**, plus five
corrections. I verified its load-bearing and surprising claims; they hold,
including one where my own text extraction had been wrong.

## It found the decisive argument, and it favours the revision

Supply coupling with `VREF+` = VDDA, the three conversions taken at different
times on a rail with no LDO:

| perturbed conversion | mV output error per mV VDDA | VDDA change costing 0.1 %O2 |
|---|---|---|
| `code_REF` | 0.508 | 6.5 mV |
| `code_AFE` (air) | 0.298 | 11.2 mV |
| VREFINT | 0.210 | 15.8 mV |
| **worst pair at zero O2** | **0.718** | **4.63 mV** |

**With `VREF+` = REF3425 this coupling is not reduced — it is zero.** VDDA
appears nowhere in the re-derivation. Residual paths are the LMP's PSRR at RE
(80 dB min / 110 dB typ, SNAS506 p.7) and the TIA's unspecified supply
sensitivity, both behind R32/C7. A 20 mVpp burst envelope costs ~0.1 %O2 under
the VDDA form and ~1e-3 %O2 under the REF3425 form — **a ~1000x term, larger
than everything else in the budget.** And `2026-09-12-revb-single-rail-supply.md:414`
already named the mechanism; nobody connected it.

## Five corrections, all verified here

**1. Drop the 3V3D divider. It is redundant AND blind.** This kills what the
cost doc called "the sharpest cost of the move".
- Redundant: there is **no VDDA register in `regmap.h`** (verified, count 0) and
  `o2p_mcu_adc_read_vdda_mv()` has only two internal consumers. More decisively,
  **R32 is 10 Ohm from 3V3D to 3V3A** and 3V3A's post-deletion load is
  ~100-200 uA, so **`VA_MON` already reads 3V3D to within 1-2 mV** — better than
  the proposed divider's own 1.65 mV leakage error. Two parts for a worse copy
  of a reading that exists.
- Blind: `ts` = 160.5 cycles at **fADC = 16 MHz** (verified, `mcu.c:99`: HSI16,
  HSIDIV=/1, no PLL) is a **10.03 us boxcar, first null 99.7 kHz**. The buck's
  switching content is averaged to nothing by the aperture alone. **The monitor
  cannot answer the release gate that is its reason for existing** — that needs a
  scope or a peak detector. Useful corollary: the same aperture also shields the
  *oxygen* channel from switching ripple, leaving the low-frequency **burst
  envelope** as the term that actually hurts.

**2. The oxygen formula I carried into the revised architecture is wrong.** With
`VREF+` = `/VREF_TRIM`, `code_REF` converts the reference against itself and
saturates at 4095. The correct form has no `code_REF` at all:
`I = V_REF x (0.67 - code_AFE/4095) / R_TIA`, with `V_REF` a **compile-time
constant** and PA5 returned to the pool. My formula degenerates to the right
answer only by luck and only for half the population: at `EG` = -5 LSB the
channel reads ~4090 and leaves **0.06 %O2 of zero error** that an air-point gain
calibration does not remove — and it makes oxygen depend on a **saturated
channel**, which every other guard in this firmware explicitly refuses
(`ads1119.h:126`, `main.c:1176`). Same defect class as the `O2P_HW_DIV_VREF`
landmine. **This must be written down before anyone ports the sampler.**

**3. The Schottkys are on the wrong pins, and I had the table wrong.** Rendered
DS12232 **Table 50** (p.80) — my `pdftotext` had collapsed its merged first row:

| pin class | negative injection | positive |
|---|---|---|
| all except PA4, PA5, PA6, PB0, PB3, PC0 | -5 mA | N/A |
| **PA4, PA5** | -5 | **0** |
| **PA6, PB0, PB3, PC0** | **0** | N/A |

`/ADC_WE_BUF` and `/ADC_RE_BUF` are **OPA2333 outputs**, not electrodes
(`gen_sch.py:979`, and `:1381` says so), so the cell cannot back-drive them and
the "cell on long buried leads" premise is a bench condition — U11 is socketed
on-board. **The exposed pin is PA6** = `VIN_MON`, rated **0 mA** negative
injection, reached through R26 91 kOhm from `+12V_SW` — the only analog channel
with a path to the external supply cable. Bounded by D3/D1 to ~-10 uA, so a
design item and not an emergency, but outside a 0 mA characterization on the pin
that footnote 3 says corrupts *other* channels. Page header quantifies the
consequence: "ADC error above ... 5 LSB TUE" plus induced leakage on adjacent
pins. **PA5 is one of the two pins rated 0 mA POSITIVE**, and carries
`/VREF_TRIM` with no series resistance — checked and it does not fire, since
SBAS804G's zero-load dropout is 100 mV so the output tracks VIN - 0.1 V.

**4. `VREF+` gets no local decoupling — +1 part nobody listed.** Moving pin 5
off 3V3D leaves its only capacitor as C10 at U15, the far end of the schematic,
while `VREF+` now sources every conversion's 5 pF switched-cap charge. Table 63
note 4 states ST's intent: *"the capacitive load must include a 100 nF capacitor
in order to cut off the high frequency noise."*

**5. Re-base the acceptance criterion.** The "cell dominates" yardstick is
mis-attributed (it is the whole signal, on a *board* temperature), **circular**
(it contains the ADS path's own tempco), and a **category error** — the cell's
tempco is *corrected* in firmware, INL/offset/gain are not. Subtracting the two
candidate AFE shares puts the cell at 876 or **540 ppm/K**, so the margin is
between **1.9x and 0.9x** — possibly negative. `o2-cell-tempco-is-unmeasured`
says no isothermal run exists, and only the dummy-cell run in
`2026-09-09-afe-tempco-plan.md` closes it.
**But the decision does not need it:** compost aeration decisions are taken at
whole-percent thresholds, against a budget of 0.14-0.20 %O2 — **~5x margin
against a requirement that exists** instead of ~1x against a quantity that does
not. This is the highest-value edit to these documents and it makes the decision
survive rather than sink.

## Two budget corrections, opposite directions

- **`ACoeff` was under-counted and it favours the revision by 40x.** DS12232
  Table 24: VREFINT long-term is 1000 ppm max **per 1000 hours**, and a buried
  probe runs continuously — 8760 h is **0.183 %O2**, comparable on its own to
  the entire static budget. REF3425 is **25 ppm/1000 h** (verified, SBAS804G
  front page and §7.2). Another strong argument for the REF3425 form.
- **`VDDCoeff` is immaterial and both prior passes over-weighted it, mine
  included.** 1200 ppm/V max across the rail's own 60 mV range is **72 ppm =
  0.0015 %O2**. It is 20-100x under terms already in the budget and is not a
  reason to do anything.
- Also: the VREFINT-conversion term is still ~2.5x understated — Codex used
  `EL` only; `±(EO+EL)` gives **±0.104 %O2**, so the VDDA form's honest linear
  worst case is ~0.26 %O2, not 0.20.

## The cell-population term nobody carried

`o2.h:271` quotes DS-0637 Issue 2 at **0.1 ± 0.03 mA in air** — a ±30 % band.
The 33.2 mV/%O2 span is one bench cell at 99 uA, and the cell is **socketed and
drifts down over life**:

| cell in air | span | ±7.5 LSB at 2.5 V FS |
|---|---|---|
| 130 uA | 43.5 mV/%O2 | 0.105 %O2 |
| 99 uA (this cell) | 33.2 | 0.138 |
| **70 uA (band bottom)** | **23.4** | **0.195** |
| 20 uA (`O2P_AIR_CAL_MIN`) | 6.7 | 0.684 |

**A legal in-spec replacement cell inflates the whole budget by 1.4x.** Express
the budget in mV at the TIA output, and quote %O2 only at a named cell output.

## Diagnostics: the claim holds, but it is a collapse detector

A REF3425 **drift** under ~0.2 % is undetectable and cannot be otherwise —
VREFINT's own tempco and `ACoeff` are 8x and 40x worse than the reference it
watches. Say "collapse detector", not "drift monitor". Two free replacements for
the lost shorted-input self-check, neither written down anywhere:
1. **`ADC_CALFACT` is readable** — publish it per boot as a per-part proxy for
   converter offset and its drift. Zero parts.
2. **Two exact ratiometric constants the Rev A wiring could not exploit:** once
   `VREF+` = `/VREF_TRIM`, `V_WE` = 0.67 x FS exactly (code 2744) and `V_RE` =
   0.91 x FS exactly (code 3727), both to the LMP's ±0.04 % internal-zero
   accuracy. `WE_BUF` becomes an **independent measurement of the very pedestal
   the oxygen subtraction uses**, on a different pin — a stronger per-channel
   leak detector than Rev A had, created by the 2.5 V full scale.

## The strongest objection, in neither prior pass

**Correlated failure.** The Rev A event took three of four inputs on one
converter, by a board-level mechanism — and the same mechanism already hit an
**MCU-side** net (`VA_MON`'s surface leak, memory `o2-probe-afe-postmortem`).
Rev A survived *because there were two converters*. One converter means one
event takes out oxygen, both electrodes, the reference, all three rails and the
die temperature at once. `VREF+` (pin 5) also sits between two 3.3 V pads on a
0.5 mm pitch.

Two things stop it sinking the decision, and both belong in the record: the
09-11 redundancy **was never exploited** — the failure was caught by eye after
14 hours — and unused redundancy is one more part to fail, the part that failed.
And the hard-driven reference is a real robustness win: an 800 Ohm leak from
pin 4 or 6 into pin 5 is 1 mA, which the REF3425 absorbs at 43-75 ppm/mA =
**0.19 mV**, where the same leak on Rev A's 47k/47k node destroyed the reading.

## Survived

The signal chain end to end (TIA 7 kOhm and INT_Z 67 % are real SNAS506
settings; `REFCN` 0xCD decodes correctly; 33.16 mV/%O2 confirmed). The retained
RC filters, fully: 1 kOhm is 50x inside `RAIN`, `ts` is 2.2x longer than
Table 59 assumes, per-conversion redistribution is **59 uV = 0.0018 %O2** — no
settling or crosstalk error worth budgeting, and "a SAR needs them more" is
right. `VREF+` < VDDA as a specified range (Table 58 gives min 2 V, max VDDA).
The RE headroom, and it is more robust than stated — 0.91 is the *architectural*
maximum, so no register corruption can exceed FS while the external reference is
selected. And Codex's four findings, re-verified independently.

**Unverified:** whether STM32G0 errata affect the `CHSELR`/`CCRDY` handshake
`convert()` relies on. The errata sheet is not archived.
