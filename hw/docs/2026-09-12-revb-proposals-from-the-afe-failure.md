# Rev B proposals from the 2026-09-12 AFE failure

Every proposal here is derived from one incident and its five-hour diagnosis.
Primary record: `CELL-AFE-DEBUG.md`, sections dated 2026-09-12. Reviewer log:
`~/codex-reviews/o2probe-afe-20260912/review.log`.

**Scope.** ADC input path, VREF sense path, and firmware diagnostics only.
Supply and reference architecture are being reworked separately in
`docs/2026-09-12-revb-single-rail-supply.md` (already Codex-reviewed) — where a
proposal here touches the reference's output current or the 3V3A/3V3D split, it
is flagged as needing that document's numbers rather than asserting its own.

**What happened, in one paragraph.** Coating paint was applied ~22:03 on
09-11 and heat was applied at 22:24 to dry it. In that single minute
`VREF_MON` went 2496 → 78 mV, `VA_MV` 3114 → 4432, `AFE_VOUT` 980 → 43, and
`i2c_errs` 0 → 18 (VictoriaMetrics, 1-minute steps). Three of the ADS1119's
four analog inputs have been faulted since. The die reached only 48 °C and
**no ADC input has exceeded ~2.6 V against a 3.3 V supply in fourteen days of
telemetry**, so no over-voltage or over-temperature stress is recorded.
Root cause is a conductive film, most likely solvent-carried flux under the
package; the mechanism is not fully closed (a ~70 min soak at 85 °C did NOT
clear the leak, which refutes a water-based film).

---

## P0. DELETE THE ADS1119 — use the STM32's own ADC (Fab, 2026-09-12: "do we really need the ADS?")

This subsumes P1, P2, P4 and P5, and it is the most consequential idea to come
out of the failure. **Not yet validated** — three measurements are required
before committing (below). Recorded as a proposal, not a decision.

### The only real reason for the ADS1119 is ratiometry, and the MCU can have it

The cell current is `I = (0.67 x VREF - V_AIN0) / 7 kOhm` (`sampler_logic.h:25-27`,
TIA 7 kOhm, INT_Z 67/100). If the ADC's full-scale reference IS `/VREF_TRIM`,
then VREF cancels: a drift of d raises both the LMP's zero and its output by
0.67d, and the difference is unchanged. That is the documented design intent
(`gen_sch.py:917`), and `sampler_logic.h:51-53` records that the internal-
reference override deliberately BREAKS it.

**The STM32G071CBT7 has a dedicated VREF+ pin — LQFP48 pin 5** (Rev B's own pin
map, `gen_sch.py:428`), currently tied to `3V3D` (`gen_sch.py:1039`). Driving
it from `/VREF_TRIM` instead gives the MCU's ADC the same ratiometric property
the ADS was chosen for. One net change.

### Resolution is not the obstacle

O2 channel span: 1675 mV at 0 %O2 down to 982 mV in air = **33.2 mV per %O2**.
(982 mV computes from 99 uA x 7 kOhm subtracted from 0.67 x 2500, and matches
the 980 mV recorded at 22:23 on 09-11 before the failure.) With VREF+ = 2.5 V:

| mode | LSB | per %O2 |
|---|--:|--:|
| 12-bit raw | 610 uV | **0.018 %** |
| 16x hardware oversampling | 153 uV | 0.0046 % |
| 256x | 38 uV | 0.0011 % |

Compost work cares about tenths of a percent. Raw 12-bit is already ~10x
finer than required.

### The ADC was never the limiting error term

The O2 signal's observed tempco is **~800-1000 ppm/K**, of which the AFE half
is ~230 +/- 110 ppm/K; the cell contributes the rest and its own tempco is
formally UNMEASURED (memory: `o2-cell-tempco-is-unmeasured`). Specifying a
5 ppm/K reference chain to measure a ~1000 ppm/K sensor is over-engineered by
roughly 200x. The limiting element is the cell, not the converter.

### It deletes the network that failed today

With VREF+ = `/VREF_TRIM`, VREF health monitoring becomes an INTERNAL
measurement: convert the MCU's VREFINT bandgap channel and VREF_TRIM follows
directly — the same trick `read_divided_rail()` (`mcu_adc.c:160`) already uses
to derive VDDA.

**That removes R34, R35, R36 and C29 — precisely the high-impedance divider
whose ~800 Ohm leak caused this entire incident — and replaces it with a
measurement that has no external node to contaminate.** It also satisfies P1
(an independent VREF path) with zero added components, and makes P5's
pad-clearance problem disappear along with the pads.

Net BOM deletion: U8, C28, C29, C30, C31, R33, R36, R37, R38, the whole
`/ADC_*` stub family, and the I2C traffic and its failure modes.

### Required before committing — measure, do not assume

1. **ADC noise against the real signal.** The ADS1119 at 20 SPS is genuinely
   ~30x quieter per sample. Oversampling should close the gap for a
   multi-second measurement, but that is a datasheet argument, not evidence.
   **Bench-compare both converters on a GOOD board** before deciding.
2. **STM32G0 ADC input leakage is far worse than the ADS's +/-5 nA typ** — up
   to +/-1 uA over temperature. Into the 1 kOhm AFE_VOUT series that is 1 mV,
   i.e. 0.03 %O2 of static offset, which calibration absorbs. Into anything
   high-impedance it is fatal, so **P2 becomes mandatory rather than
   optional** for every retained divider.
3. **VREF+ draws switched-cap current during conversions.** Whether the Rev B
   series voltage reference can supply it is a question for
   `2026-09-12-revb-single-rail-supply.md`, not for this document.

Further open items: the WE/RE electrode buffer channels need MCU pins (free
pins exist — 22 of 48 assigned); existing dividers are sized against a 3.3 V
FSR and need rescaling for 2.5 V; and the MCU's ADC sits in the digital
domain, which is part of why 3V3A/3V3D are split at all, so grounding and
coupling need deliberate attention rather than a net rename.

## P1. Put VREF on the MCU's own ADC — a second, independent path

**Highest value of anything here.** The entire five-hour investigation existed
because the only measurement of the 2.5 V reference ran through **one ADS1119
input**. When that input developed a ~800 Ω leak, the firmware could not tell
"the reference collapsed" from "the sense path is broken", and neither could I:
I published and retracted *four* diagnoses on that ambiguity alone
(open `/VREF_TRIM`, a shorted C29, a damaged AIN1, supply-dependent conduction).

What actually broke the deadlock was **PA7's independent reading of
`/VA_MON`**, which disagreed with the ADS and turned out to be right. That
redundancy is the single most valuable feature the board has, and VREF does
not have it.

- Rev B as of today still routes VREF health only through `R34/R35 → R36 →
  ADC_VREF_MON → U8` (`gen_sch.py:1319,1326,1331`), and `MCU_NETS`
  (`gen_sch.py:1039`) carries `CE_MON`, `VIN_MON`, `VA_MON` — **no VREF**.
- 22 of the STM32G071CBT7's 48 pins are assigned, so a channel is available.
  (A specific free ADC pin must be confirmed against the LQFP48 pinout; the
  mapping is not asserted here.)
- Cost: one resistor divider tap plus a series R. The existing
  `/VREF_MON_RAW` node can feed both, with its own series resistor per ADC so
  neither input's leakage pulls the other.

**Acceptance test:** with the ADS's AIN1 deliberately loaded (a 3 kΩ pull-up to
3.3 V reproduces today's condition exactly), the MCU path must still report
VREF correctly and the firmware must name which path disagreed.

## P2. Lower the VREF sense divider impedance — INTERACTS with the reference redesign

R34/R35 are 47k/47k, a 23.5 kΩ Thévenin source. An ~800 Ω leak collapsed the
tap to **2.9 %** of nominal — 36 mV where 1250 mV was due. At 4.7k/4.7k the
same leak would give ~19 %, which still faults but reports as *low* rather than
*absent*, and any leakage of any origin matters ~10× less.

- Current cost: 2500 mV / 94 kΩ = 27 µA. At 4.7k/4.7k: 266 µA.
- **This is not mine to decide.** Rev B is moving to a series voltage reference
  (`2026-09-12-revb-single-rail-supply.md` §6, §173) whose output current
  budget governs. 266 µA may be trivial or may matter. Take the number from
  that document.
- Note the divider's own tolerance is already handled: R34/R35 are 0.1 % parts
  and the ratio cancels, so lowering the value costs nothing in accuracy.

## P3. A diagnostic channel must not disable the measurement channels — firmware, free

`finish_vref()` (`main.c:700`) raises `ADC_RANGE` and leaves `vref_measured`
false when `VREF_MON` is out of band, and `finish_electrode()`
(`main.c:869`) then returns early for every externally-referenced channel. So
one leaking *diagnostic* input suppressed VIN, VA, WE, RE and the O2 reading
for hours — while VIN was perfectly measurable the whole time.

**Proof it was measurable:** forcing the ADS's internal 2.048 V reference via
diag opcode 9 brought VIN straight back at **13138 mV**, correct, with no other
change.

**Proposal:** on a sense-tap fault, fall back automatically to the internal
2.048 V reference instead of suppressing, and publish the fallback state in a
register so it is never silent. The debug opcode already proves the mechanism;
this only makes it automatic and observable.

This is the highest value-per-effort item on the list: no board change, and it
would have turned a total telemetry blackout into a degraded-but-reporting
state.

## P4. Detect a stuck mux — firmware, free

AIN0's fault is that its mux does not connect, so the converter returns the
**previous channel's sample**. This was detectable only by coincidence:
`AFE_VOUT` happened to equal `VREF_MON/2`, and the historical record shows the
two tracking to within 4 mV from 22:24 onward while being independent before
it. Nothing in the firmware noticed for fourteen hours.

Two cheap detectors:

1. **Identical consecutive codes.** A stuck mux returns the prior sample, so
   two different channels yielding bit-identical accumulator codes is a direct
   signature. Cost: one comparison per phase.
2. **Offset self-check.** ADS1119 `MUX=111` shorts the inputs internally
   (SBAS925A Table 10). Convert it once per cycle and assert it reads near
   zero. This also catches the offset drift noted below.

## P5. Keep GND pads away from high-impedance analog nodes

The fault is a conductive film, and the layout offers it short paths:

| pads | separation | nets |
|---|--:|---|
| C29.1 / C29.2 | **0.96 mm** | `/ADC_VREF_MON` ↔ GND |
| R34.1 / R35.2 | **1.35 mm** | `/VREF_TRIM` ↔ GND |

Residue across the C29 footprint is *still* an unexcluded candidate for today's
fault — it survived the C29 removal test, because removing a capacitor does not
remove residue between its pads.

**Proposal:** on the VREF sense node and the ADC input stubs, route GND returns
away, widen pad-to-pad clearance, and consider extending the existing
`GUARD_REPLICA` plane concept (`gen_sch.py:945`, driven by U4B through R40 47R)
to enclose the VREF sense node. Rev B already has a driven guard plane — it
guards the cell electrodes, not the node that actually failed.

## P6. `/ADC_VIN_MON` exceeds abs-max on every power-up

VIN is upstream of the entire supply chain (VIN → U1 buck → +5V → R32 →
+5V_ANALOG → U3 → 3V3A), but `/ADC_VIN_MON` is fed directly from the VIN
divider through R38 1 kΩ. So that input is biased **before AVDD rises**,
exceeding SBAS925A §6.1's `AVDD + 0.3 V` limit, on every single startup.

Honest quantification (Codex review, finding 9): the clamp current is **60–78 µA**
depending on the fitted divider, against a ±10 mA continuous input-current
rating. So it is an abs-max *voltage* violation well inside the *current*
rating — a real hazard, **not** a demonstrated cause of this failure, and
notably AIN3 is the one undamaged channel.

**Proposal:** raise R38 from 1 kΩ to ~100 kΩ. The ADC input is high-impedance,
and with C31 100n that is a 10 ms RC — irrelevant for a slow rail measurement.
Cuts the clamp current ~100×, to sub-µA.

## P7. Process rule: never heat-dry coating on a populated board

This is the root cause, and it belongs in `ASSEMBLY-EXCEPTIONS.md` /
`FAB-NOTES.md` rather than the schematic:

- Conformal coating and paint must **air-cure**. Applying heat to accelerate it
  mobilises solvent, which wicks under packages by capillary action carrying
  dissolved no-clean flux with it.
- **High-impedance analog nodes should be masked from coating entirely** — the
  VREF sense node, the ADC input stubs, and the cell electrode traces.
- Corollary already learned on 09-10 and re-learned today: an in-circuit
  two-terminal reading measures the whole net, not the part under test.

## P8. Cell over-temperature is only a flag

Today the cell-side sensor sat at **86.4 °C** against the SGX-OX-ROHS-Mini's
**60 °C** rating, with `TEMP_OVER` set but nothing else happening. The heater
is interlocked; externally applied heat is not, and nothing warns the operator.

**Proposal:** low effort, no board change — the bench dashboard should alarm
on `TEMP_OVER`, consistent with the standing rule that dashboards state their
failure states explicitly rather than showing a plausible number.

---

## Also worth carrying forward, not proposals

- **The ADS read 3–4 % low against a meter** at two operating points (36 vs 35,
  775 vs 742 mV). Direction and magnitude were consistent, suggesting a gain
  error most plausibly in the internal reference. Unverified — the comparison
  was not simultaneous or controlled (Codex finding 7). **Check the
  internal-reference gain against a meter on the replacement part before
  trusting any O2 calibration.**
- **PA7's ÷2 scaling** uses `O2P_HW_DIV_VA_NUM/DEN` = 47000/94000 while Rev A
  fits 10k/10k. Both are ratio 1:2 so voltage reconstruction is correct, but
  the contract carries a *resistance* that is not the fitted one — harmless
  today, a trap for any future current calculation.
- **3V3A remains intermittent and unexplained.** If the single-rail work
  removes the 3V3A/3V3D split, it also removes the "AVDD absent while DVDD
  present" condition that every dropout ran. Worth checking whether that is an
  intended consequence of that design, because it would retire a whole failure
  class.
