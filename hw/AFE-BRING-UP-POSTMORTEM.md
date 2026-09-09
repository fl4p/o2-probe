# AFE bring-up postmortem, and the PCB changes it argues for

**Date:** 2026-09-04
**Board:** o2-probe Rev A, first article, at commit `021f61b`
**Outcome:** U7 (LMP91000SD/NOPB) replaced. Its control amplifier A1 had failed.

This document exists because finding that took most of an evening, and almost
none of that time was spent on the fault itself. It was spent establishing
which of four candidate parts was guilty, using a DMM on chip leads, because
the board cannot observe the two nodes that would have answered it in one
reading. The recommendations in section 3 all follow from that.

---

## 1. What failed

U7's control amplifier would not servo. Final state before replacement, with a
1 MOhm / 1 MOhm resistive dummy on the cell pads:

| node | measured | required |
|---|---|---|
| CE (U7.14) | 130 mV | 2870 mV |
| RE (U7.13) | 140 mV | 2271 mV |
| WE (U7.12) | 1678 mV | 1678 mV (correct) |

The decisive test was commanding **0% bias** (`REFCN = 0xC0`), which asks A1 for
the easiest setpoint it can be given: make RE equal WE, a voltage the chip
already generates internally and holds on the neighbouring pin. It did not
move. The load needed 0.6 uA against a 750 uA specified drive capability, so
this was not an overload.

After fitting a new LMP91000SD/NOPB, the same dummy gives:

```
CE 2875 mV   RE 2275 mV   WE 1678 mV      (predicted 2870 / 2271 / 1678)
RE - WE = 597 mV                          (commanded 598.56 mV, 0.3% error)
CE - RE = 600 mV, CE - WE = 1197 mV       both legs of the divider equal
```

Everything else on the original part was healthy and was proven so:

- **The TIA (A2)** was verified by stepping `TIACN` and confirming the implied
  current is invariant with feedback resistance: **61.31 / 62.39 / 61.71 uA** at
  2.75k / 3.5k / 7k, agreeing to 1.8% across a 2.5x gain change. This also
  distinguishes a real current from an amplifier output offset, which cannot
  scale with the selected resistor.
- **I2C, register readback, mode, LOCK** — correct after every reset.
- **Internal zero and the external reference** — WE held at 1671 mV, confirmed
  independently by DMM.
- **All three electrode connections** — pin 12 by the TIA holding its pad, pin
  14 by A1 driving its pad, pin 13 by a 0 Ohm continuity reading.

## 2. What it cost, and the pattern to break

While A1 was dead, the firmware's **only** complaint was `O2P_F_ADC_RANGE`
(bit 11, "converter saturated or out of window"). The converter was perfect.

This is not a harmless mislabel. Earlier in this project an **ADS1119 was
desoldered and replaced for nothing** on a symptom whose real cause was a
firmware bug: the ADS DRDY pin (PB1) was left in its analog reset mode, so
`IDR` read 0 permanently, the conversion-complete wait fell through on its
first evaluation, and every channel returned the *previous* channel's
conversion. The `O2P_ADS_TIMEOUT` guard was silently dead throughout.

Twice now, the fault vocabulary has pointed at the ADC when the ADC was fine.
Sections 3.3 and 5 are about ending that.

## 3. PCB changes

### 3.1 ESD protection on the cell connector — highest priority

`CELL_CE`, `CELL_RE` and `CELL_WE` at HEAD reach only:

```
CELL_WE : U7.12, U11.3, TP1
CELL_RE : U7.13, U11.2
CELL_CE : U7.14, U11.1, TP3
```

There is **no protection of any kind** on any of them. POTTING.md requires the
cell to be swappable with the board potted, which means these three pins are
handled by a person, in the field, as routine maintenance — and they run
straight into a 3.3 V analog front end.

What killed this A1 is unknown and will stay unknown. ESD during handling is
the obvious candidate and the cheapest to defend against.

**Constraint that disqualifies ordinary parts:** the RE node is budgeted in
picoamps. `gen_sch.py:495-506` argues the case explicitly — OPA333 at 200 pA
max, a real bound of ~400 pA for a follower, against the LMP91000's own
`IRE` of +/-900 pA max over temperature. A generic TVS leaks orders of
magnitude more than that, hot. This needs low-leakage diodes with a stated
leakage figure over the full temperature range, entered into that same budget.
Do not fit a general-purpose part here.

### 3.2 Series resistor in the CE line, 100 Ohm to 1 kOhm

The resistor sits **inside** the feedback loop — RE is sensed separately — so
A1 compensates for it and measurement accuracy is unaffected. What it buys is
a ceiling on the current A1 can deliver into a fault.

Standard potentiostat practice, one part, and it would have limited whatever
this amplifier was driving into when it died.

### 3.3 Make CE, RE and WE observable

This is the change that would have saved the evening, and it is the one that
matters once the probe is potted and a DMM is no longer an option.

Rev B (currently uncommitted, in another session's working tree) already moves
`ADC_RE_BUF` and `ADC_WE_BUF` onto U8 pins 4/5. **That change is correct and
this postmortem is the evidence for it** — with those two channels, "is the
cell biased to -600 mV?" becomes one register read instead of a DMM session.

**Add CE as well.** RE-WE tells you the bias is wrong; CE tells you *why*:

| CE reads | meaning |
|---|---|
| railed low or high | A1 driving into a fault, or overloaded |
| sitting at the internal zero | A1 idle or dead |
| tracking WE + 2x bias | healthy |

A second, stronger argument for CE is quantitative rather than diagnostic.
SNAS506 specifies A1's operating current capability only over
`300 mV <= VCE <= VS - 300 mV`, which at 3.3 V is a ceiling of **3000 mV**. The
healthy replacement part sits at **2875 mV — 125 mV of margin**. As cell
impedance rises with age, CE walks toward that ceiling, and the probe leaves
the region where the amplifier's drive is specified at all. The failed part sat
at 130 mV, *below* the 300 mV floor.

So CE is not merely the node that diagnoses this failure after the fact: it is
the only node that gives **warning before it**. Note that Rev B as currently
drafted still does not route it.

That distinction is the whole diagnosis. CE is a low-impedance driven node, so
it needs a divider only — no precision buffer, no leakage budget.

**There is a free channel for it.** AIN2 currently carries 3V3A/2, but the same
rail is *also* read by the MCU ADC: `va_mv` continued to report 3288 mV
throughout a period when every ADS1119 channel was failing, which proves that
reading does not depend on the ADS. AIN2 is redundant and can be repurposed.

### 3.4 Test point on CELL_RE, and a local ground

TP1 is on CELL_WE and TP3 on CELL_CE. **CELL_RE has none** — and it was
precisely the net whose connection could not be verified tonight without
metering a 0.5 mm chip lead directly.

Add a test point on CELL_RE, and a ground test point beside the group so a
probe has a local reference. Two pads, no cost, and they are the difference
between a ten-second check and an hour of inference.

### 3.5 Switched dummy load — study, not yet a recommendation

The measurement that ultimately settled everything was substituting a known
resistor for the cell. A permanently-fitted dummy switched in by a GPIO would
let the firmware run that test itself — in the field, on a potted probe — and
would have found this fault in seconds.

**Why it is not a recommendation yet:** any switch on the RE leg adds leakage
to the node protected at picoamps per 3.1, and most analog switches are orders
of magnitude worse than that at temperature. A dummy on the CE-WE path alone
avoids the leakage problem but leaves RE floating, which rails A1 and is not a
clean test.

Worth a proper evaluation, because once the board is potted this is the *only*
way to distinguish a dead cell from a dead AFE. It needs a real part with a
real leakage number over temperature before it goes on a schematic.

### 3.6 Split the THVD1410's /RE off DE — IMPLEMENTED in `gen_sch.py`, 2026-09-07

Not an AFE ask, and not argued by this postmortem's failure. It is recorded
here because §3 is where this project keeps its Rev B PCB asks, and because
this one is **already in the generator** rather than still being asked for —
whoever freezes the respin needs to know it is in the netlist, not on a wish
list. It does not touch, contradict or reorder any of 3.1–3.5, all of which
remain open on their own terms.

`U5` pin 2 is `/RE` (receiver enable, **active low**, 2 MΩ internal pull-up)
and pin 3 is `DE` (driver enable, **active high**, 2 MΩ internal pull-down).
Rev A tied both to the single net `RS485_DE` on PC6, so the four-state part had
two reachable states and the useful one — `/RE` high, `DE` low, 0.1 µA typ —
was not among them. The receiver therefore burned **700 µA typ / 960 µA max**
forever, 24 % of the board's idle draw (`POWER-BUDGET.md`).

What changed in `gen_sch.py`:

- `U5.2` moves to a new net `RS485_RE`;
- `MCU_NETS` gains **pin 31 = PC7**, the package neighbour of PC6. Pin identity
  taken from DS12232 Rev 1 Table 12 "Pin assignment and description", LQFP48
  column — *not* from prose, per `PIN-IDENTITY-POSTMORTEM.md`. PC7's
  "Additional functions" cell is empty, so it carries no ADC channel and cannot
  collide with `mcu_adc.c`;
- **`R45`, 47 k to GND on `RS485_RE`** — the part of this change that is
  load-bearing for safety rather than for power. `/RE` floats *high* (deaf) on
  its internal pull-up, and every MCU GPIO is high-impedance out of reset;
  without R45 a probe that reset into the RS-485 bootloader would come up
  unable to hear the bus, and a potted one would be unrecoverable. R45 makes
  receiver-enabled the passive default exactly as **R7 makes driver-disabled
  the passive default. R7 is untouched**, so `main.c`'s bus-jam argument — the
  reset, plus R7's pull-down, is a release path that does not depend on this
  CPU running code — still reads true word for word.

**The saving is 630 µA, not 700 µA, and that is a property of R45.** Commanding
standby means driving `/RE` high against 47 k, which is 3.3 V / 47 k = 70 µA.
Standby is therefore ~70 µA, not the datasheet's 0.1 µA — a 10× cut on the
transceiver, not 7000×. At the duty-cycled floor of ~29 µA in `POWER-BUDGET.md`
R45 would be the largest single load on the board. 220 k (327 mV against a
0.8 V V_IL, 15 µA) or 470 k (628 mV, 7 µA) buy that back at the cost of noise
margin on an enable line TI's own guidance wants driven from 1–10 k.
**That is a decision for Fab, and it is open**; 47 k is what is in the
generator today because it is the house value and matches R7.

Firmware: `board_pins.h` binds `O2P_RS485_RE_*` and asserts the net/pin pairing;
`modbus_rtu.c` drives `/RE` exactly where the old shared net went high, so
**runtime behaviour is unchanged**, and adds `o2p_modbus_rx_standby()` which
**nothing calls** — the state is now reachable, wiring it into the sampler is a
protocol decision (see `POWER-BUDGET.md` on unsolicited transmission).
`loader_uart.c` and `bridge_uart.c` drive it too, for echo suppression only,
and both return it low on every exit path.

**Not done, and it is the gate on this being real hardware: the PCB.** `U5.2`
is still shorted to `U5.3` in copper and PC7 is unrouted. This is a schematic +
firmware change only.

### 3.7 Monitor `VREF_TRIM` at U7 pin 11 — new, 2026-09-09, highest diagnostic value

**The gap.** `ADC_VREF_MON` (AIN1, via R34/R35) watches the reference *network*.
U7 pin 11 is fed from that network **through the trimmer**. They are different
nodes, and a fault between them — an open joint at pin 11, a sagging wiper —
shows a perfectly healthy `vref` in telemetry while the chip has no usable
reference at all.

**What that costs.** The LMP91000 derives its internal zero as 0.67 x pin 11. With
pin 11 open the internal zero is 0, the TIA holds its virtual ground at 0 V, and
VOUT parks at ground. Every digital check still passes: I2C, the register image
and the on-die temperature sensor do not depend on pin 11. The part looks alive
and the output looks railed.

Firmware then computes

```
I = (0.67 x ADC_VREF_MON - VOUT) / 7 kOhm
```

and returns **~238 uA** — just above the DS-0637 air spec of 40-100 uA, and
essentially exactly the TIA clip point of 1672 mV / 7 kOhm = 239 uA. It reads as
a dramatic, specific overcurrent. It is an artefact of a missing denominator.

That number was quoted as a measured current at least four times across
2026-09-08 and 2026-09-09, and an AFE was replaced on the strength of it. The
replacement reproduced the identical figure, because the fault was an open pin 11
that survived the swap. Both chips were healthy. Full narrative:
`docs/2026-09-09-afe-rework-debug.md`.

**The ask.** Make pin 11 observable, so "does the AFE have its reference?" is a
register read.

**Open question, and it is a real trade — do not treat this as settled.** The
obvious cheap version is to move R34/R35's tap from the network output to the
wiper side, which costs no ADC channel. But R34/R35 are 47k/47k, i.e. a 94 kOhm
load on the trimmer wiper, which will shift the very reference it is meant to
verify. Options, in rough order of preference:

1. Re-tap `ADC_VREF_MON` to the wiper side **and** re-size the divider up, or
   compensate the trimmer range for the known load. Free in channels; needs the
   error budget worked through.
2. Buffer the wiper into a spare MCU ADC input. The MCU ADC needs a low source
   impedance too, so this means a follower, not just a divider — but U4 already
   has the topology and one section is the guard replica.
3. Spend an ADS1119 channel. See the channel-budget conflict in 3.9.

Whichever is chosen, the firmware rule that follows is in `CELL-AFE-DEBUG.md` 2:
**VOUT at either rail invalidates the derived current**, and `t_afe` being valid
is the cheapest positive evidence that the reference is present, because the die
sensor is referred to the same rail.

### 3.8 Fix the cell connector pin order — new, 2026-09-09

The Rev A connector is **C-R-W**; the cell is **W-R-C**. The bench article
compensates with flying copper wires, and that harness is where an R-W short was
found on 2026-09-09 — a short that pinned VOUT at 22 mV across *two* AFEs and
*two* cells, and was the reason both swaps appeared to prove the cell and the
chip guilty.

Correct the order on the board and the crossing wires disappear. This is a
footprint/net change with no BOM or area cost, and it removes a failure mode that
has already consumed a chip, a cell, and most of two bench sessions.

See `PIN-IDENTITY-POSTMORTEM.md:445-450` for the lead-crossing history.

### 3.9 The ADS1119 channel budget does not close — resolve before layout

Collecting the asks, four nodes now want a channel and there are four inputs
total, one of which is already spoken for:

| node | asked by | status |
|---|---|---|
| `AFE_VOUT` | — | AIN0, non-negotiable |
| `WE_BUF` | 3.3 | Rev B draft moves it to AIN2 |
| `RE_BUF` | 3.3 | Rev B draft moves it to AIN3 |
| `CE_MON` | 3.3 | **no channel left** |
| `VREF_TRIM` | 3.7 | **no channel left** |

3.3's argument that AIN2 is free rests on `va_mv` being independently readable by
the MCU ADC, which is measured and correct — but that frees exactly one channel,
and the Rev B draft has already spent it and AIN3 on WE/RE.

CE is the easier of the two to move off the ADS: it is a low-impedance driven
node, so a plain divider into a spare MCU ADC input is sufficient, no buffer and
no leakage budget. `VREF_TRIM` is the harder one (3.7). **Decide this explicitly
before layout** rather than discovering it during routing.

Priority if only some can be had, on the evidence of three sessions:
`VREF_TRIM` > `RE_BUF` > `CE_MON` > `WE_BUF`. `VREF_TRIM` is first because its
absence does not merely hide a fault, it manufactures a false one.

### 3.10 Rev A telemetry field names are actively misleading — firmware, not PCB

Recorded here because it is the same root cause. On the fabricated Rev A board
(commit `16b5a606`) AIN2/AIN3 are `ADC_VA_MON` and `ADC_VIN_MON`, so:

- `we_buf` is the VA rail, `re_buf` is the VIN rail
- `cell_bias_mv`, derived from both, **has never measured the cell**
- the bias guard therefore raises `AFE_CONFIG_MISMATCH` (`faults` bit 5) on a
  quantity unrelated to the electrodes
- `ce_mv` reported 1806 mV while CE measured 3280 mV at the pin, and the
  R43/R44 91k/91k divider reconciles with neither — scaling unverified

**Firmware follow-up: the bias guard must report `unverified`, not a verdict,**
on a board where the source nodes are not the electrodes. Open as of 2026-09-09.

## 4. Resolve before freezing a respin

Two measurements from tonight remain unexplained, and both sit on the ADC path:

- **77 mV between the DMM at U7 pin 8 and the ADC's reading of that node.**
  R33 is 1 kOhm, R39 is DNP, and the ADS1119 draws +/-5 nA, which predicts about
  5 uV of drop. The topology was independently confirmed. The gap is real, and
  still unexplained - but see 6b: a second apparent witness for it, found on
  2026-09-05, turned out to be a measurement artefact and must not be counted.
- **AIN2 anomaly — RESOLVED: an open solder joint on U8 pin 5.** Localised by
  elimination: the R24/R25 divider junction read 1643 mV (correct, and not
  sagging, so nothing downstream drew current, which cleared R37 and C30), while
  the ADS converted AIN2 as a value that decayed monotonically through
  366 / 129 / 108 / 42 / 9 mV — a floating die node bleeding through C30, not a
  wrong fixed value. Both differential modes failed with the *opposite sign*
  from a healthy input, so the fault was not specific to the single-ended path.
  U8 is a WQFN (`Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm`),
  leadless, so an open joint and an open bond wire could not be separated by
  probing — only by reflow. Reflowing pin 5 restored every channel to within
  3 mV of prediction, stable, including AIN2-AIN3 at +339.9 mV against +343
  expected. **Silicon exonerated; it was assembly.**

  **Instance or systematic?** The stencil hypothesis was checked and cleared:
  the footprint gives pad 17 F.Cu and F.Mask with no paste, plus four separate
  0.32x0.32 mm apertures, i.e. 0.4096 mm2 against a 0.64 mm2 EP = 64 % and
  segmented — correct practice for this package.

  But the decisive point is simpler, and it means this failure carries **no
  information about production assembly either way**: this ADS1119 is the
  REPLACEMENT part, fitted by hand after the original was desoldered for
  nothing. Its joints were never made by the stencil-and-reflow process at all.
  A hand-reworked 0.5 mm-pitch WQFN with one open perimeter joint is an
  unremarkable outcome, and it says nothing about a board built normally.

  Confirmed for this board: `ASSEMBLY-EXCEPTIONS.md:3` records the revision as
  bare-board first articles and **hand assembly**, not turnkey PCBA, so no
  stencil was involved at all. Instance defect is the parsimonious reading.

### 4.1 Latent defect found while checking the above: the paste layer is never exported

Chasing the stencil hypothesis turned up a real defect that is unrelated to
tonight's fault and outlives it. `make_fab.py` exports
`F.Cu, In1.Cu, In2.Cu, B.Cu, F.Mask, B.Mask, Edge.Cuts` — **there is no F.Paste
and no B.Paste**, and grepping the file for "paste" returns nothing.

So the carefully segmented 64 % EP aperture exists in KiCad and never leaves the
project. Anyone ordering a stencil from the fab ZIP gets apertures the fab
generates from copper — for a WQFN-16 that means a 1:1 EP opening, the part
floats on paste during reflow, and perimeter joints starve. That is exactly the
failure mode seen on pin 5 tonight, arriving by a different route, and it would
appear on the first stencil-built batch rather than on any hand-built first
article.

This is the same class as the silkscreen finding (`silkscreen_exported false`,
so no test-point labels reach a physical board): the design is correct and the
fab output silently drops it. **Neither is visible by inspecting the KiCad
project — only by reading the export layer set.**

Neither is a blocker for the current board. Both are blockers for trusting a
new layout.

## 5. Firmware companion work

The PCB changes above make the AFE *observable*. Making it *self-diagnosing* is
separate work. Five guards were proposed and then adversarially reviewed; the
review killed two outright and materially changed the rest:

- **TIA gain-ratio self-test — DROPPED.** The gain sweep in section 1 that
  proved A2 healthy was run *on the board with the dead A1*. Automating it
  yields a guard that returns PASS on a potentiostat which cannot bias the
  cell. A1 and the TIA are independent blocks (SNAS506 sections 7.3.1.1 and
  7.3.1.2), so no measurement taken through A2 says anything about A1.
- **Cell-current sign plausibility — DROPPED.** It would encode the SGX sign
  convention as firmware truth while `SCHEMATIC-REVIEW.md` M4 and
  `PIN-IDENTITY-POSTMORTEM.md` both hold that gate explicitly OPEN, and it
  would destroy the negative-fraction evidence the bench build exists to
  collect. It also adds no detection: `ADC_RANGE` already fires on a negative
  fraction.
- **Rail-versus-range — half dropped.** The high side is unmeasurable. AIN0 is
  converted against `VREF_TRIM` ~2500 mV while the amplifier rail is 3V3A
  ~3300 mV, so anything above 2.5 V reads full scale and the converter
  saturates roughly 118 uA before the amplifier rails. The salvageable core is
  a distinct code for "the converter clipped at +/- full scale", which costs
  zero conversions.
- **DRDY liveness — BUILD, and extend it.** Init-only is not enough: a DRDY
  that fails *after* init restores the original stale-conversion bug with no
  fault raised. Verify DRDY reads high immediately after START, on every
  conversion. One register read, zero I2C, zero conversions.
- **Bias-response test — BUILD, two-sided.** As first worded ("command 0% bias,
  confirm the current collapses") it **passes on a dead A1**, because the
  current has already collapsed. It must require *both* substantial current at
  24% bias *and* collapse at 0%. In that form it is the only one of the five
  that detects this failure.

  **And it needs a plausibility BAND on the differential, not a clip check.**
  This is a Rev B consequence of the AIN2 fault and it belongs here. On Rev A a
  floating AIN2 costs a redundant rail monitor and looks obviously broken: it
  reads a couple of hundred millivolts where 1644 was expected, and the MCU
  reads the same rail anyway. On Rev B the identical open costs **half the bias
  pair**, and it does *not* look broken — WE_BUF falls to ~0, so AIN2-AIN3 reads
  about -2275 mV where the design says -600 mV, and at gain 1 the FSR is
  +/-2494 mV, so it converts cleanly, in range, with no clipping and no
  saturation flag. A valid-looking number from a disconnected input. The guard
  must therefore assert the measured bias falls inside a window around the
  commanded value; a clip check alone will pass it silently. Note this is caught
  by the section 7 rule only in its property form, not in the rail form — which
  is precisely why the rail form was inadequate.

A committed-code defect surfaced during the review: **`main.c:596` discards the
return of `o2p_ads1119_init()`**, so the ADS config-probe failure path has no
consumer and a failed probe reads as OK.

An earlier draft of this document claimed the fault word is full. That is wrong
in the way that matters: all 16 bits in `faults.h` are *assigned*, but
`O2P_F_EXP_PRESENT` (bit 13) and `O2P_F_EXP_FAIL` (bit 14) are **written by no
code in the tree** — J2 is DNP on Rev A and `main.c:529` hard-writes the
expansion register invalid. Two bits are free without touching the published
map at 0x0006.

**The conclusion that matters:** on Rev A a dead A1 is **not detectable by any
amount of firmware**, because CE and RE reach no converter. That is a PCB
problem, not a firmware problem, and it is why section 3.3 outranks everything
in this section.

### 5.1 Review of the guards as actually implemented (2026-09-04)

Three of the agreed guards were implemented in a parallel session and reviewed
adversarially. The die-temperature channel survived the full guard checklist
with no findings. The ADS1119 work did not. Every claim below was re-verified
against the code before being written down.

**The per-conversion DRDY check can latch permanently.** `ads1119.c:146`
returns before START and before RDATA. In single-shot mode only a successful
RDATA releases DRDY — the auto-release in SBAS925A 8.5.1.3 is continuous-mode
only, and CM is always 0 in this driver. So an I2C failure at the RDATA
transfer, or a conversion completing just after the timeout, leaves DRDY low;
every later cycle then hits the pre-check and returns *without ever issuing the
RDATA that would clear it*. `o2p_ads1119_init()` is the only reset and
`main.c:613` its only call site, so one transient glitch on a four-device bus
blanks oxygen until power-cycle. The direction of the trade is still correct —
silently returning stale data was worse — but the guard needs a recovery path:
re-run init on a non-OK status.

**The `(void)o2p_ads1119_init()` justification is false.** The comment at
`main.c:606` claims a config that will not read back returns `O2P_ADS_CONFIG`
from each conversion. `read_cfg()` has exactly one caller, `ads1119.c:80`,
inside init; `convert_once` never verifies the config it wrote, so
`O2P_ADS_CONFIG` is unreachable outside boot. The ADS1119 *identity* proof is
boot-only for the same reason, and its result is discarded. This is worse than
the bare `(void)` it replaced: a future reader has no reason to doubt a comment
that specific. **A comment asserting a check that does not exist is checklist
item 8 — a mute button.**

**A new distinct status is destroyed at its only consumer.** `main.c:299`
collapses every non-OK status into `O2P_F_I2C_FAIL_ADS`, so the new
`O2P_ADS_DRDY` is invisible in telemetry: from a buried probe the operator sees
the *I2C* bit — the same misdirection that got a healthy ADS1119 replaced.
Fix this before adding any further status, or each new one meets the same end.

**Cross-session contamination worth recording as a hazard in its own right.**
`firmware/src/hw_contract.h` in the shared working tree is generated Rev B
output while the physical board is Rev A. `VREF_MIN/MAX` moved 2357/2750 ->
2480/2520, which through `main.c:361` narrows the accepted window from
2257..2850 to 2380..2620 mV. A Rev A board trimmed anywhere legal outside that
raises `ADC_RANGE`, which is in `O2P_FAULTS_INVALIDATE_O2` — blanking oxygen on
good hardware. The one measured article reads 2492 mV, so **this passes on the
bench and would ship undetected.** Generated headers describing a *different
revision of the hardware* are a guard-input source-of-truth failure
(checklist item 4), and the shared worktree is how it got there.

**Still unimplemented:** AIN0 clip detection (fault bits 13/14 remain free and
written by no code) and the two-sided commissioning bias-response test. Two
constraints for whoever builds them: `accumulate()` at `main.c:296` retains no
per-conversion code, so detection on the 8-sample average misses partial
clipping; and commanding 0% bias *is* a bias interruption costing 15+ minutes
of `O2P_F_SETTLING`, so that test must be commissioning-gated and unreachable
from a Modbus trigger a field operator could fire.

## 6. Resolved: the "607 uA" cell — retracted

An earlier revision of this document recorded an open hardware issue: with the
new U7 fitted, the cell appeared to draw **more than 607 uA** against a 70-130
uA specification (0.1 +/- 0.03 mA, DS-0637), "steady for six minutes at every
selectable gain", and concluded the current was real because the AFE was by
then proven good.

**That was wrong, and it is the cleanest example of section 7 in this whole
document.** The channel was *saturated*, not steady: at 7 kOhm the TIA clips,
and 622 uA and 240 uA read out identically. What looked like a flat line was
polarisation current decaying behind the rail, invisible because the rail
cannot report how far past itself the signal is. The cell settled at
**+99.09 uA**, mid-specification. Nothing was wrong with it.

The reasoning error is worth naming precisely: *"steady for six minutes, so
not a transient"* is only valid if the channel can distinguish steady from
pinned. This one could not, and no amount of re-reading it would have said so.

## 6a. Still open at time of writing

- ~~**The board lost its supply**~~ — **RETRACTED, it never happened.** The
  symptoms (uptime counting backwards 1436 -> 1434 -> 1432, VREF 32769, VA
  ~600 mV falling, `O2_COMP 30.00 %vol` off a "collapsing rail") were produced
  by decoding a healthy dump with a STALE STRUCT LAYOUT: `t_die` had just been
  appended to `o2p_snapshot_t`, moving every field after it. Confirmed by
  decoding one dump both ways and reproducing the exact numbers. The board's
  own uptime showed no reset. **The blanket instruction to distrust every bench
  number after that point was therefore wrong, and is withdrawn** - those
  readings are good.
- **77 mV** between a DMM at U7 pin 8 and the ADC reading of that node,
  **still open**. A leaky C28 at roughly 13 kOhm fits the observation. Re-tested
  2026-09-05 and NOT reproduced by a second method; see 6b.
- **`CAL_DEFAULT` cleared** without any calibration having been triggered.

## 6b. The 77 mV, re-examined 2026-09-05 — and a trap worth keeping

An attempt to corroborate the 77 mV by reading AIN0 directly over SWD, with the
core halted and the firmware out of the loop, appeared to confirm it: 1047.8 mV
direct against the firmware's 973 mV, a 75 mV gap of almost exactly the right
size. **That was an artefact of the reading method, not a second witness.**

What settled it was arithmetic, before any further measurement. At the 67 %
internal zero and the 7 kOhm TIA, the firmware's 973 mV is 99.5 uA, which
against the air calibration is 20.8 %vol - correct for a probe sitting in room
air. The direct read's 1047.8 mV is 88.8 uA, or 18.6 %vol, which it plainly was
not. **The reading that disagreed with the firmware was the wrong one.**

Then three variants, all at a byte-identical config (`0x61`: AIN0, gain 1,
20 SPS, single-shot, external reference):

```
A  back-to-back AIN0, config written once   956.78 -> 998.99 -> 1007.81 mV
B  AIN0 after 3 s quiet gaps                -293.63,  0.00,  962.71 mV
C  AIN2 immediately before AIN0             968.49 mV        (firmware: 964)
```

**C is the firmware's own channel sequence, and it agrees to 4.5 mV** — about
0.6 uA, i.e. noise. Hammering one channel without ever leaving it drifts the
result upward by tens of millivolts; interleaving another channel returns it to
truth. No mechanism is asserted here, but the pattern is consistent with the
ADS1119's sampling network working against the LMP91000's output through R33
and recovering when the multiplexer moves away.

Three things to carry forward:

1. **The driver's channel interleaving is load-bearing.** An out-of-band read
   that skips it returns a *stable-looking* wrong answer, which is far more
   dangerous than an obviously broken one. B is the tell: the same method also
   produced -293.63 mV and 0.00 mV, so no single output of it should ever have
   been promoted to a finding.
2. **A second witness that shares no method with the first is worth more than
   agreement in magnitude.** This one agreed to within 2 mV of the original
   77 mV and was still wrong. The coincidence made it more persuasive, not less.
3. **The original DMM-vs-ADC gap is untouched by all of this.** It compares the
   ADC against a meter; this compared the ADC against itself. Closing it still
   needs a DMM on U7 pin 8 alongside a firmware reading of the same node.

## 7. The lesson that generalises: channels that cannot say "I don't know"

Four separate errors tonight were the same error wearing different clothes. The
tempting statement of it is about saturation — "a reading at a rail is not a
measurement" — but that only covers two of the four. The property underneath is
broader:

> **Any channel that cannot express "I do not know" will answer anyway, and the
> answer will look valid.**

Rail-pinning is one way a channel loses that expressiveness. A stuck pin, a
timed-out probe and a swallowed error code are others. All four instances:

- **`ADC_RANGE` raised while A1 was dead.** The converter was healthy and said
  so in the only vocabulary it had: "out of window". Read as a statement about
  the ADC, it was a statement about the *boundary*, with the cause two blocks
  upstream. This has now cost one ADS1119, replaced for nothing.
- **The cell "steady at >607 uA for six minutes".** `AFE_VOUT` was clipped, and
  622 uA and 240 uA produce the same reading there. The trace looked flat,
  flatness was read as steady state, and a good cell was declared out of spec.
  It was polarising throughout and settled at 99 uA, mid-spec. **Flatness in a
  clipped channel is not evidence of a steady value** — it is the absence of
  evidence.
- **The DRDY bug.** No rail was involved. PB1 sat in analog reset mode, `IDR`
  read 0 permanently, and "not ready" was encoded *identically* to "ready". The
  channel had no representation for absence, so the wait fell through and every
  conversion returned the previous channel's result.
- **`main.c:596` discarding `o2p_ads1119_init()`'s return.** The config-probe
  result has no consumer, so a failed probe is encoded identically to a passed
  one. No rail, no stuck pin — same class.

The obligation this creates is guard-checklist item 1, and it applies to every
channel, not only to converters: **unevaluable input must not mean OK.** A
clipped code, a probe that timed out, a pin that cannot be read and a status
nobody consumes must each be carried as their own state — `UNVERIFIED`,
`CLIPPED`, `FAILED` — never folded in with real values and never differenced
against them.

The bench corollary, for the saturation cases specifically: **when a channel is
against its limit, change the range before drawing any conclusion from it.** The
TIA gain is selectable precisely so this is cheap — stepping to 2.75 kOhm would
have shown the cell decaying instead of a flat line.

## Appendix: measurements this document rests on

```
Old U7, 1M/1M dummy, 24% bias : CE 130 mV   RE 140 mV   WE 1678 mV
Old U7, 1M/1M dummy,  0% bias : CE 130 mV   RE 140 mV   WE 1678 mV   (no response)
New U7, 1M/1M dummy, 24% bias : CE 2875 mV  RE 2275 mV  WE 1678 mV

TIA gain sweep, old U7 (proves A2 healthy, current real not offset):
  2.75k -> 168.6 mV -> 61.31 uA
  3.5k  -> 218.4 mV -> 62.39 uA
  7k    -> 431.9 mV -> 61.71 uA

LMP91000 SNAS506 limits used above:
  A1 minimum operating current   750 uA sink / source     (section 6.5)
  A1 minimum charging capability  10 mA sink / source     (section 6.5)
  A1 characterised VCE range     300 mV .. VS-300 mV      (section 6.5)
  IRE input bias current         +/-900 pA max, -40..80 C (section 6.5)
```
