# 2026-09-09: three rework defects on one package edge, and the false currents they produced

Bench session on the Rev A first article, roughly 12:45 to 13:45, over SWD (the
Modbus/LoRaWAN path was not used). It ends with the AFE in regulation and the cell
drawing **104 µA in room air** — the first trustworthy cell current this board has
produced.

The session is worth recording less for the repairs than for the reasoning: the AFE
was replaced *before* this session on the strength of a current figure that did not
exist, and during the session three more component-level diagnoses were wrong before
the right one. All of them shared a single mechanism, described under
"The trap" below.

Sibling record: `2026-09-08-evening-board-failures.md` (the preceding evening, ending
with a dead MCU). That MCU was replaced before this session.

## Corrections, appended 2026-09-09 after review

This record was reviewed the same day it was written and several of its claims
did not survive. They are corrected here rather than edited away, because the
wrong versions were acted on and the reasoning that produced them is the point.

1. **`t_afe` does not prove the AFE has its reference.** The body says a valid
   die temperature means pin 11 has its voltage. **SNAS506I §7.3.1.5 specifies
   the temperature output as ground-referred**; OP_MODE 111 only routes it to
   VOUT. The timeline below is its own counterexample: `t_afe` went valid at
   12:57, five minutes before the open pin 11 was found. The real test is
   WE ≈ 0.67 × VREF.

2. **The trimmer is not between the monitor and the AFE.** The body attributes
   the healthy `vref` reading to `ADC_VREF_MON` sitting upstream of a trimmer.
   On the fabricated board U7.11, U8.7 and the monitor divider R34 are all on
   `/VREF_TRIM` — one net — and RV1 is upstream on `/VREF_TOP`→`/VREF_WIPER`.
   The correct explanation is better: **the open was at the package pin**, so
   the net stayed at 2.5 V and the monitor read it correctly while the die was
   attached to nothing. No converter on this board can see that.

3. **The air-current band is wrong.** The body quotes DS-0637 **Issue 1**
   (0.07 ± 0.03 mA = 40–100 µA). **Issue 2, 28-May-2026, specifies 0.1 ± 0.03 mA
   = 70–130 µA**, and both PDFs are in `compostlab-literature/datasheets/`. So
   the settled **99.9 µA is mid-band nominal**, not "at the top of spec" — a
   materially different conclusion about the cell's health, from a datasheet
   this repo already had.

4. **"152 µA full scale" in the timeline is wrong**; 152 µA is the design point
   at 30 % O₂ (`lmp91000.h:41-43`). The arithmetic bound is ~239 µA, and even
   that is nominal — it assumes VOUT reaches exactly 0 V and R_TIA is exactly
   7 kΩ, neither of which SNAS506 guarantees.

5. **The bias polarity prose is inverted.** `BIAS_SIGN 0` means
   (V_WE − V_RE) < 0, i.e. **RE sits above WE**. The measured R − W of +600 mV
   was correct and agreed with the tables; the sentences saying "RE below WE"
   did not.

6. **"Neither AFE and neither cell was ever shown to be faulty" is too strong**
   for the section it appears in, and it blurs a real result. The AFE replaced
   on **2026-09-04 did fail** — separated decisively by the 0 %-bias dummy-load
   test, with a replacement that passed the same test (`AFE-BRING-UP-POSTMORTEM.md`
   §1). The claim is only about the chips handled on 2026-09-09, and even there
   "reproduced the symptom after replacement" does not prove the earlier part
   healthy when the rework itself can introduce a new fault — which, on this
   board, it demonstrably did.

7. **The process conclusion is a hypothesis, not a finding.** Three defects on
   one package edge is a pattern worth acting on, but nothing here measures the
   reflow profile or the paste volume, and no other cause was excluded.

The general procedure in `CELL-AFE-DEBUG.md` has been corrected accordingly;
prefer it over this file for any number you intend to act on.

## Timeline

| time | state |
|---|---|
| — | U7 (LMP91000) replaced by Fab after 2026-09-08; MCU also replaced |
| 12:48 | first read after replacement: `lmp_readback` 0x0000, `i2c_errs` +3/s — AFE not on the bus |
| ~12:55 | Fab reflows U7; I²C good (`0x0CCD`, `i2c_errs` 0) but `afe_vout` 3–7 mV |
| 12:57 | `t_afe` valid for the first time (31.9 °C, cooling) — die sensor alive |
| ~13:02 | W measured at 0 V. **U7 pin 11 (`VREF_TRIM`) found open**, repaired |
| 13:06 | cell OUT: `afe_vout` 1650 mV, ~2.5 µA — textbook |
| 13:08 | cell IN: `afe_vout` 22 mV, frozen to the LSB for 6 minutes |
| ~13:12 | second cell fitted — **identical 22 mV**, bit for bit |
| ~13:17 | **R–W found shorted** by Fab, cleared |
| 13:21 | still pinned at 19 mV; `vref` healthy at 2490 |
| 13:27 | `vref` collapses to 94 mV, `t_afe` invalid — reference network down |
| ~13:31 | Fab clears a short pulling the reference down; `vref` returns to 2496 |
| 13:34 | cell IN: C 2700 / R 2275 / W 2120. Loop out of regulation (R−W = 155 mV) |
| 13:36–13:38 | R−W climbs 155 → 285 → 320 mV |
| 13:39:49 | **loop closes.** R−W 600 mV, `afe_vout` 17 → 796 mV, current 236 → 125 µA |
| 13:40:49 | `afe_vout` 944 mV, **104 µA**, still decaying |

## The faults

**1. U7 pin 11 (`VREF_TRIM`) open.** The LMP91000 derives its internal zero as
0.67 × the voltage on pin 11. With pin 11 open the internal zero is 0, so the TIA
holds its virtual ground at 0 V and VOUT parks at ground. Everything else in the
chip keeps working — I²C, the register image and the on-die temperature sensor do
not depend on pin 11, which is why the part looked healthy on every digital check.

Diagnosed from two measurements: W sitting at 0 V with power on, and a diode test
(red on W, black on GND: 1.5 V; reversed: 0.5 V) showing W was *not* shorted to
ground and therefore was being actively driven there.

**2. A short between R and W.** With RE and WE shorted, A1 cannot establish
`V_RE − V_WE = −598 mV` at any output voltage, so it runs to a rail, and the current
it sources flows through the short into the TIA summing node. Result: `afe_vout`
pinned, noiseless, and **identical across two AFEs and two cells**.

Prime suspect was a bridge between U7 pins 12 (`CELL_WE`) and 13 (`CELL_RE`) — the
same package edge as the open pin 11, and adjacent to it.

**3. The reference network collapsing.** `ADC_VREF_MON` fell from 2454 mV to 94 mV
at 13:27, taking the internal zero, W, and `t_afe` with it. Cleared by Fab.

Note the ordering hazard this created: `ADC_VREF_MON` watches the reference
*network*, while U7 pin 11 is fed from it *through the trimmer*. A partial fault at
pin 11 can therefore show a healthy `vref` in telemetry while the chip has no usable
reference. The two are not the same node and must not be read as one.

**4. RE not properly in circuit (the last one).** At 13:34, with the reference
restored: C−W = 580 mV, essentially the commanded bias, while R−W = 155 mV, nowhere
near setpoint. The bias appearing across CE-to-WE instead of RE-to-WE is the
signature of a reference electrode that is not sensing. A supporting fingerprint:
RE read **2.275 V**, essentially identical to the **2.27 V** measured at U4 pins
5/6/7 — the guard replica. A floating high-impedance RE input sits at the guard
potential.

## The trap: currents computed through a missing reference

Every wrong conclusion in this session, and the AFE replacement that preceded it,
came from one arithmetic habit:

```
I = (0.67 × vref_board − afe_vout) / 7 kΩ
```

`vref_board` is `ADC_VREF_MON`. When U7's own reference is absent or sagging,
`afe_vout` parks at ground for a reason that has nothing to do with current, and
this expression returns **≈ 238 µA** — which is above the 152 µA full scale and
about 2.4× a healthy air current, so it reads as a dramatic, specific fault.

It was quoted as a measured current at least four times on 2026-09-08 and
2026-09-09. It was never a current. It is what the formula returns when its
denominator's premise has failed.

**Rule: an `afe_vout` at either rail invalidates the derived current.** Before
quoting a current, establish independently that the chip has its reference. The
cheapest positive evidence is `t_afe` being valid — the die sensor is referred to
the same rail, so a plausible temperature means the reference is present. `vref`
alone is not sufficient (see fault 3).

## What a healthy board looks like (measured this session)

| signal | value | note |
|---|---|---|
| `vref` (`ADC_VREF_MON`) | 2496 mV | |
| internal zero | 1672 mV | 0.67 × vref; **WE should measure this** |
| WE at the connector | 1678 mV | |
| R − W | 598–600 mV | the commanded bias; the loop is in regulation |
| `afe_vout`, cell OUT | ~1650 mV | ~2.5 µA |
| `afe_vout`, cell IN, air | 944 mV and rising | 104 µA and decaying |
| `t_afe` | 25–27 °C | valid = reference present |
| `lmp_readback` | 0x0CCD | |
| `i2c_errs` | 0 | |

DS-0637 gives 0.07 ± 0.03 mA in air, i.e. 40–100 µA, so 104 µA is at the top of
spec and still settling downward at the end of the session.

## Diagnostic notes for next time

**A value frozen to the LSB across a component swap is an interconnect fault, not a
device fault.** `afe_vout` read 22 mV with two different AFEs and two different
cells. A real electrochemical cell dithers in the low bits and a polarising one
ramps; a bit-identical reading is a hard electrical condition. This signature was
present for over an hour before it was read correctly, and it is the cheapest
available discriminator — it costs nothing but looking at the digits.

**An ohmmeter cannot exonerate or convict an oxygen cell.** A cell under bias is a
current source set by oxygen diffusion, not an ohmic path; it passes ~100 µA while
reading >1 MΩ to a meter. A low reading proves a short; a high reading proves
nothing. Reasoning that treats the measured C−W voltage divided by the TIA current
as a cell resistance is invalid, and produced a spurious "≤1.7 kΩ" figure here.

**Cell out / cell in is the fastest board-vs-cell split**, and it needs no meter.
Cell out should give `afe_vout` ≈ 1650 mV / ~2.5 µA. If the board is clean with the
cell out and pinned with it in, the current enters through the connector.

**Not every telemetry field measures what its name suggests.** On this fabricated
Rev A board (commit `16b5a606`) `we_buf` and `re_buf` are the VA and VIN **rail
monitors**, not electrode buffers — AIN2/AIN3 are `ADC_VA_MON` and `ADC_VIN_MON`.
`cell_bias_mv` has never measured the cell. `ce_mv` reported 1806–1820 while CE
measured 3280 mV at the pin, and the R43/R44 91k/91k divider reconciles with
neither, so its scaling is also unverified. **Prefer the meter over these fields**
until each is checked against the netlist. Extract the fabricated netlist with
`git show 16b5a606` — earlier work read a *different* PCB revision and sent Fab
after R37/R38/U4 followers that do not exist on the bench board.

**Loop convergence can look like a plateau.** R−W read 155 → 285 → 320 mV, steps of
+130 then +35. Extrapolating the ratio predicted an asymptote near 335 mV and a loop
that would never reach setpoint. It reached 600 mV two minutes later. Those three
points were the middle of an S-curve, not the approach to a limit — do not
extrapolate a settling curve from three samples.

**The non-halting SWD sampler tears across buffer flips.** `/tmp/o2p_probe.py` reads
the live snapshot without halting, so it occasionally returns a row with
`lmp_readback = 0x0000`, `ce = 33`, `t_afe = 0`. One such row looked exactly like the
AFE dropping off the I²C bus. Re-read before reporting; a torn row does not repeat.

## Process observation

Three defects — an open pin 11, a bridge on 12–13, and a compromised RE — appeared
in sequence on **one package edge** across repeated rework on the same part. Two of
them appeared *after* rework that was intended to fix the previous one. This looks
like accumulating damage around U7 rather than one elusive original fault.

Neither AFE and neither cell was ever shown to be faulty. The chip replaced before
this session was, on the evidence available now, healthy.

Before the next AFE comes off this board, it is worth asking whether the reflow
profile and paste volume on that edge are what keep producing these, and whether
the cell should be characterised in a known-good fixture instead of on the Rev A
first article.

## Firmware follow-up

`cell_bias_mv` on this board is derived from the rail monitors, so the bias guard
raises `AFE_CONFIG_MISMATCH` (`faults` bit 5) on a quantity that does not measure
the cell. It should report `unverified` rather than a verdict. Unfixed as of this
session.
