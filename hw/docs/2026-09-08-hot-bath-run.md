# The 78 °C run of 2026-09-08, and what it can and cannot tell us

Three hours of probe telemetry, 60 uplinks, taken with the ring heater holding the
tip at 78.00 °C and the probe later suspended over a jar of 80 °C water.

Everything here is from `/api/v1/export` — genuine written points with their own
timestamps, not step-aligned range-query evaluations. That distinction is not
pedantry; see `farming:docs/telemetry-freshness-hardening.md`.

## Headline

**The run cannot be used to characterise the cell**, for three independent reasons
found in this order, each of which alone is disqualifying. It is still valuable: it
produced the first working closed-loop tip control, and it exposed four defects and
two unimplemented diagnostics that had been latent since Rev A.

## What happened

| time | phase | T_tip | duty | RH | cell µA | %O₂ |
|---|---|---|---|---|---|---|
| 10:53–11:37 | ambient, heater off | 25.6→26.3 | 0 | 9.2 | 100.85→101.05 | 20.84 |
| 11:37:35 | heater armed | 33.1 | 100 % | 9.0 | 101.04 | 20.45 |
| 11:42–12:46 | closed loop at 78.00 °C, dry | 78.00 | 80→65 % | 1.3 | 101.9→**105.24** | 18.62→19.14 |
| 12:51 | jar of 80 °C water | 78.00 | 65→46 % | 1.3→**13.1** | 105.22→103.16 | 19.14→19.31 |
| 13:01–13:50 | bath cooling | 78.00 | 38→47.7 % | 13.1→12.1 | →104.6 | →19.42 |

Tip control held **78.00 ± 0.02 °C for over two hours** through a duty swing from
80 % to 38 % and back. That loop is not in question anywhere below.

## Reason 1 — the cell was outside its rated envelope, in two ways

DS-0637 Issue 1 (07-Apr-2025), now filed at `datasheets/`:

- **Operating Temperature Range −40 °C to +60 °C.** The run held the cell at 78 °C
  for over two hours, 18 K past rated. Every performance parameter in that datasheet
  is void up there. This is exactly what the `TEMP_OVER` fault bit reports, and what
  `PLAN.md:211-228` means by "above 60 °C it is extrapolation by explicit decision".
- **Operating Humidity 15 % to 90 % RH continuous — but also `0–99 % RH (short
  term)`.** The chamber sat at 1.3 % RH for an hour. That is below the *continuous*
  floor and inside the *short-term* range, and DS-0637 does not define "short term",
  so **one hour cannot be adjudicated from the datasheet**. An earlier version of
  this note called it out-of-spec outright and inferred permanent electrolyte loss;
  both went further than the source. Corrected 2026-09-08 after a peer session's
  review. What remains true is that nothing in the firmware or the bench mode warns
  when the chamber leaves the continuous band.

The humidity excursion is **not** a design defect. The shipped RH loop targets 85 %
(`regmap.c:22`), comfortably in spec. It was the manual fixed-temperature hold, which
bypasses that loop, that drove RH to 1.3 %. Nothing warned us — a bench mode that can
take the cell outside its datasheet envelope should say so.

## Reason 2 — WITHDRAWN: the bias was never measured

**This section claimed the cell was not at its commanded bias. That claim is
withdrawn — it rested on a dead ADC channel, not on a measurement.**

What it said, and why it looked solid: `REFCN` commands 24 % of VREF with the sign
negative — **−598 mV**, against DS-0637's `−600 ± 10 mV`. `lmp_readback` = `0x0CCD`
proves the part accepted it, and the bench measured 597 mV on 2026-09-04. Against
that, telemetry read `cell_bias_mv` = **+341 mV** — wrong magnitude *and* wrong
sign, with `re_buf` at 1298 mV where internal-zero-plus-bias puts it near 2268. A
correct configuration with a wrong bias points at the loop, which closes through the
cell, so a badly-led cell was the obvious reading.

**What actually falsified it (2026-09-08, farming-b5's swing test).** With the cell
removed, the bridge cleared, and the cell refitted, the WE node was driven to three
genuinely different voltages — **2485 → 1680 → 771 mV**, confirmed at the pads with
a DMM. Across all three, `we_buf_mv` reported **1639** and `re_buf_mv` reported
**1296**, unchanged. `cell_bias_mv` is computed as the difference of those two
(`main.c`, `finish_electrode()`), so it reported a constant 343 mV throughout. A pair
of numbers that does not move while the node moves by 1.7 V is not measuring the
node. The +341 mV in this run is the same constant, four days and a firmware
revision earlier.

**It is not a firmware fault, and specifically not a stale value.** `main.c:284-288`
rebuilds the staging snapshot from `INVALID` at the start of every cycle — the
comment there names this exact hazard — and `o2p_snapshot_reset()` sets all three
fields to `0xFFFF`. Every refusal path in `finish_electrode()` is a bare `return`, so
a refused reading publishes the sentinel, not a plausible number. `SAMPLE_SEQ`
advances, so cycles complete. The firmware is faithfully converting and being handed
a constant code: the fault is in the **ADS1119 AIN2/AIN3 input path**.

**What this invalidates beyond this section.** The bias-versus-commanded fault added
on 2026-09-08 in response to Reason 2 is fed by this same dead input, so it is a
guard fed by a constant and **can never fire on the condition it was built for** —
it needs a source-of-truth fix before it means anything. Any other conclusion in this
repository resting on `cell_bias_mv`, `we_buf_mv` or `re_buf_mv` inherits the same
defect and should be re-derived.

**What survives.** Nothing here rules the bias *correct* either — a dead channel is
silence, not a clean bill of health. The commanded bias is still `0x0CCD` and still
provably accepted by the part; the cell's actual potential during this run is simply
**unknown and now unknowable**, because the only instrument that watched it was not
working. `ads1119-inputs-not-dead` records that a "dead ADS1119 input" conclusion was
wrong once on this project and a part was swapped for nothing, so the AIN2/AIN3
verdict wants an independent SWD read of the raw codes before anyone replaces U8.

Anything derived from cell current here remains suspect at the root — for Reason 1
and Reason 3, which stand on their own evidence.

## Reason 3 — the AFE's own drift is inseparable from the cell's

The published current is `(0.67·VREF − VOUT)/R_TIA` with `R_TIA` **hardcoded at
7000 Ω**. SNAS506I Rev I specifies that resistor's *accuracy* (5 %) and publishes **no
temperature coefficient and no gain-versus-temperature curve** — confirmed by
enumerating all 35 figures, not by keyword search.

Everything else in the chain is bounded and small:

| term | bound | source |
|---|---|---|
| ADS1119 gain drift | 2 ppm/K max | SBAS925A 6.5 |
| ADS1119 offset drift | 0.1 µV/K max | SBAS925A 6.5 |
| `TcVOS_RW` at 24 % bias | ±8 µV/K | SNAS506I 6.5 |
| VREF | cancels — internal zero and ADC reference are the same rail | `ads1119.h:7` |

So `R_TIA` is the **one uncharacterised term**, and it drifts with the AFE's
temperature. What the run measured is therefore

    a_cell·β + tc_RTIA·γ = 797 ppm/K

where β is the cell's coupling to the tip and γ the AFE's — and the board is **not
isothermal**: T_TIP 78.0, T_CHAMBER 77.7, T_DIE 49.0, a 29 K spread. Nothing measured
the AFE's temperature, so γ was unknowable. `T_AFE` (`0x002C`) now measures it.

**There is no independent isothermal measurement, and an earlier version of this
note claimed there was.** The "730–780 ppm/K bath ramp" it cited as corroboration is
*this same run*, analysed with a different endpoint — 101.04 → 104.83 µA at 12:02
rather than the equilibrated 105.24 at 12:38. Same cell, same hours, same
unmeasured β and γ. Two analyses of one dataset agreeing is not two experiments
agreeing, and presenting it as a cross-check was circular. That figure lives only in
an agent memory note; it is not in `~/dev/kb` and there is no primary record of a
separate ramp. Found by the `probe-char` session, 2026-09-08.

So β and γ remain **entirely unconstrained** by anything measured to date.

The operational conclusion survives anyway, and does not need them. The firmware
compensates using the *gas* temperature, and what this run measures is the published
signal's actual dependence on that same variable: **~800 ppm/K**. Config flash
applies **2840**. Whatever physically splits the 800 between cell and TIA resistor,
the correction is ~3.5× larger than the dependence it is correcting — which is a
self-contained statement about one measured variable, not a claim about the cell.
`O2P_TEMPCO_DEFAULT` is deliberately `0.0f` because "an invented coefficient would
be worse than none", and DS-0637 has no tempco curve at all, so the 2840 has no
datasheet basis either.

## Corrections to earlier readings of this data

- **α ≈ 0.27, derived here from the 12:46→13:01 water step, is withdrawn.** That
  window has three simultaneous transients — humidity still rising (RH 8.20 at 12:51,
  13.13 at 13:01), the cell warming on its own ~10 min constant, and the bath cooling.
  The configured **α = 0.402 ± 0.046** comes from a properly *isothermal* 18.2 hPa
  dry-down (`O2-HUMIDITY-CORRECTION.md`) and stands.
- **The ~10 min cell time constant is real and is the run's most reusable result.**
  The tip heats fast; the free-hanging cell lags. The −2.2 %vol dip at 11:42 is
  entirely that: the firmware compensated for 51 K the cell had not yet experienced.
  Any tempco correction driven by `T_TIP` is wrong for ~30 min after a thermal step.

## What was built in response

| change | why |
|---|---|
| `T_AFE` `0x002C` | measures γ — the AFE temperature nothing measured |
| `CE_MV` `0x002D` | names *which* hardware fault: register image can read back perfect while the loop is open |
| bias-vs-commanded fault | ~~the probe measured its own broken bias for hours and said nothing~~ **INEFFECTIVE — see Reason 2. It compares `cell_bias_mv`, which is fed by a dead ADC channel, so it is a guard fed by a constant and cannot fire on the condition it was built for.** |

`CE_MV` is bench-only by design: the uplink is at 96 bytes with 4 bytes of DR3
headroom, and this is a question a laptop on the bus answers in the same session it
asks it. The **fault** reaches the radio.

Grafana: all four board temperatures now share one axis with DS-0637's +60 °C limit
drawn, and the cell-bias panel carries the commanded −24 %·VREF line — though that
panel is presently plotting a constant, for the reason given in Reason 2. Both were
chosen so the failures above are visible without anyone deriving anything.

## Do differently next time

1. **Bond the cell thermally, or measure its temperature.** Suspended on leads it has
   its own 10 min constant and an unmeasured steady-state offset. (The claim that this
   also "broke the bias" is withdrawn with Reason 2 — the bias was never measured. This
   is one fix for one problem.)
2. **Stay inside 60 °C and 15 % RH** for anything meant to characterise the cell, or
   state up front that the result is extrapolation.
3. **Check `cell_bias_mv` against the command before trusting a run.** Automatic since
   2026-09-08, but *currently meaningless*: the channel it reads is dead, so the check
   passes and fails on a constant. Fix the input before trusting the guard — and note
   the general lesson, which outlives this board: **a guard is only as good as the
   channel feeding it, and this one was added, tested and believed without anyone
   confirming its input was live.**
4. **Actually do an isothermal run.** Immersing the whole probe makes β and γ
   irrelevant by construction. No such measurement exists yet — the figure that was
   believed to be one is this run under another name — so the cell's tempco is at
   present unmeasured, not merely imprecise.

## Provenance

Data: VictoriaMetrics `/api/v1/export`, `gas_*`, 10:00–14:00 local 2026-09-08.
Datasheets read for this note: DS-0637 Issue 1, SNAS506I Rev I, SBAS925A Rev A.
Firmware at the time of the run: `204f0f9`. Bias and tempco figures above are from
telemetry, not from a meter on the cell.
