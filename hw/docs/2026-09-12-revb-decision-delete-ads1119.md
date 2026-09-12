# Rev B decision: delete the ADS1119 (U8)

**Decided 2026-09-12 by Fab.** Supersedes P0 of
[`2026-09-12-revb-proposals-from-the-afe-failure.md`](2026-09-12-revb-proposals-from-the-afe-failure.md),
which recorded this as a proposal. Extends
[`2026-09-12-revb-decision-vref-monitor.md`](2026-09-12-revb-decision-vref-monitor.md),
whose deferred item is resolved here as **rejected**, not adopted.

Every analog channel moves to the STM32G071CBT7's own ADC. U8 comes off the BOM.

> **CONTESTED 2026-09-12, same day — DO NOT TREAT AS SETTLED.** A Codex review
> at xhigh returned **VERDICT: NO**, and I verified four of its five findings
> against the datasheets, the firmware and the working tree; all four hold. See
> [`2026-09-12-revb-codex-review-of-the-u8-decision.md`](2026-09-12-revb-codex-review-of-the-u8-decision.md).
> In short: the error budget below priced ONE conversion where oxygen uses
> THREE (corrected worst case ~0.20 %O2, not 0.073 — a ~2x margin over the cell,
> not 5-18x); `EO` should not have been removed, because DS12232 Table 60
> footnote 2 says the DC accuracy figures are already measured AFTER internal
> calibration; the "resolution never reached anyone" argument is FALSE, since
> `main.c:1179` publishes `o2_raw` at 10 nA/count = 70 uV = the ADS's LSB; and
> the supply premise changed underneath this document — **3V3D now comes
> straight off the AP63203 buck, both TPS7A20 LDOs deleted** (`gen_sch.py:905`),
> so the rejection of the `VREF+` move was decided against a topology that no
> longer exists and is **overturned**. The resolution and leakage conclusions
> survive. Recommendation: keep U8's footprint on Rev B until the corrected
> budget and a measured comparison pass. Fab's call to re-take.

> **IMPLEMENTED in the schematic the same day** by the Rev B session —
> `docs/2026-09-12-revb-ads1119-removal-implemented.md`. 82 components (was 89),
> ERC 0/0. The firmware sampler port is deliberately NOT done and
> `o2probe_revb` is out of `default_envs` until it lands. Their report also
> corrected two things in this document; both are marked below.

## The architecture: `VREF+` stays on VDDA, and the reference is MEASURED

This is the part that took two wrong turns to reach, so it is stated plainly.

```
VREF+ (pin 5)      = VDDA = 3V3D = 3.3 V     <- UNCHANGED
/VREF_TRIM         -> MCU ADC channel, direct, no divider   (2.5 V < FSR)
/AFE_VOUT          -> MCU ADC channel, via R33/C28          (982..1675 mV)
/WE_BUF, /RE_BUF   -> MCU ADC channels, via R37/C30, R38/C31

I = VDDA/FS x (0.67 x code_REF - code_AFE) / R_TIA,  VDDA from VREFINT
```

**The reference's drift cancels exactly, because it is measured on the same
converter, in the same units, in the same cycle.** That is the same
cancellation the ADS1119 gets from sharing `/VREF_TRIM` as its full scale —
performed by arithmetic instead of by wiring, and without requiring the
reference to BE the full scale. Rev A already relies on the measured value
rather than a nominal one: `ads_ext_scale_mv()` (`main.c:636`) returns
`g_cyc.vref_mv`.

### Why moving `VREF+` to `/VREF_TRIM` is REJECTED, not deferred

It was proposed under P0 as the mechanism for ratiometry. It is not needed for
it, and it costs four things the arithmetic form does not:

1. **Accuracy becomes uncharacterized.** Every row of DS12232 Rev 5 Table 60
   (`ET`, `EO`, `EG`, `ED`, `EL`, `ENOB`) is specified at `VDDA = VREF+`.
   Operation with VREF+ < VDDA is permitted (p.809-817) but ST publishes no
   accuracy figure for it. Keeping VREF+ = VDDA keeps the whole budget below
   inside its specified conditions.
2. **Every MCU ADC channel's full scale would drop to 2.5 V**, costing the rail
   monitors their over-range headroom. 3V3A excursing to 5 V would put the VA
   tap at exactly full scale and clip above it. That is not hypothetical: the
   14-day over-voltage sweep that dated this failure is precisely that
   measurement.
3. ~~**The ADC scale would depend on trimpot RV1** instead of an LDO.~~
   **STRUCK 2026-09-12** — wrong for Rev B. There is no trimpot: Rev B's
   `/VREF_TRIM` is U15, a **REF3425IDBVR** series reference, Kelvin-sensed
   (`gen_sch.py:930`, `:945`, `:1499`), with C10 4.7 uF. The RV1/OPA2333
   divider is Rev A's topology and I carried it across by mistake.
4. ~~**A switched-cap load would land on `/VREF_TRIM`**~~ **WEAK** — the
   REF3425 sources +/-10 mA (SBAS804G Table, `IL`) into a 0.1-10 uF stable
   load range. 0.26 uA of `IDDV(ADC)` is not a load it notices.

**And one reason pointed the other way, which is worth stating rather than
quietly dropping.** With `VREF+` = VDDA the scale factor is VREFINT at 50
ppm/degC max; with `VREF+` = the REF3425 it would be **6 ppm/degC max**
(SBAS804G, 2.5 typ), an 8x better tempco. Over a 20 K swing that is 120 ppm
against 1000 ppm — 0.0025 %O2 against 0.021 %O2.

**The decision stands, on reasons 1 and 2 alone.** Both remaining terms are
18x to 150x under the cell's own 0.38 %O2 over the same swing, so the
better tempco buys nothing measurable, while reason 1 (uncharacterized
accuracy outside `VDDA = VREF+`) and reason 2 (the rail monitors' over-range
headroom) are real and unmitigated. But it rests on two reasons, not four.

## Error budget, entirely from datasheets — no bench measurement required

DS12232 Rev 5 Table 60 (12-bit, `TA` = entire range) and section 5.3.4.
O2 span 33.2 mV/%O2; FSR 3.3 V gives 806 uV/LSB.

| term | spec | -> %O2 |
|---|---|---|
| integral linearity `EL`, max | +/-3 LSB = +/-2.42 mV | +/-0.073 |
| LSB at 3.3 V FSR | 806 uV | 0.024 |
| `VREFINT` tempco, max 50 ppm/degC over 20 K | 1000 ppm | 0.021 (gain) |
| `VREFINT` long-term, max | 1000 ppm / 1000 h | 0.021 (gain) |
| `Ilkg` +/-70 nA into 1 kOhm (R33) | 70 uV | 0.002 |
| offset `EO` | removed by `ADCAL` | — |
| gain `EG` | absorbed by the air calibration | — |
| **cell drift, ~900 ppm/K over 20 K** | **12.5 mV** | **0.38** |

Every term is 5x to 18x under the cell's own drift. The converter is not the
limiting element under any of them, which was the whole question.

Supporting, from the telemetry rather than the datasheets
(`CELL-AFE-DEBUG.md`, 2026-09-12 14:00): the firmware publishes the O2 channel
as `uv / 1000` — whole millivolts (`main.c:1066`) — while the ADS resolves
76 uV/LSB, so **13x of its resolution was already being discarded before
transmission**, and the measured in-situ chain noise of 0.43 mV rms sits below
that 1 mV grid. 806 uV/LSB is still finer than the number anyone receives.

## BOM: what goes, and what stays

**Deleted:** U8 and its local decoupling; R34, R35, R36, C29 and the nets
`/VREF_MON_RAW` and `/ADC_VREF_MON` (per the VREF-monitor decision); the I2C
traffic to U8 and its failure modes; `ADC_DRDY`, freeing PB1.

**KEPT — correcting P0, which listed these as deletions:** R33/C28, R37/C30,
R38/C31 (1k + 100n, `gen_sch.py:1332-1352`). A SAR needs them *more* than a
delta-sigma does. The 100 nF sources the charge kick of the ADC's 5 pF sample
capacitor (`CADC`, Table 58) so the op-amp does not, and 1 kOhm is far inside
the 50 kOhm `RAIN` limit. Deleting them would have been a real error.

I2C pull-ups also stay — the bus is shared with the other sensors.

## Pins — as allocated by the Rev B session, verified here

The allocation is theirs, and it applies the leakage argument further than this
document did: `Ilkg` differs by pad type (DS12232 Table 51), so the three
1k-sourced signals take the quieter `FT_a` pads and the reference — driven by
U15's output, where even 150 nA is negligible — takes the `TT_a` one.

| pin | port | channel | pad | net |
|---|---|---|---|---|
| 11 | PA0 | ADC_IN0 | FT_a, +/-70 nA | `/ADC_WE_BUF` |
| 12 | PA1 | ADC_IN1 | FT_a, +/-70 nA | `/ADC_RE_BUF` |
| 16 | PA5 | ADC_IN5 | **TT_a, +/-150 nA** | `/VREF_TRIM`, undivided |
| 20 | PB1 | **ADC_IN9** | FT_a, +/-70 nA | `/ADC_AFE_VOUT` |

Verified against DS12232 Rev 5 on 2026-09-12: the pad types are exactly as
claimed, and **PB0 is ADC_IN8 while PB1 is ADC_IN9** — their correction to my
handover message, which had the channel numbering wrong. `ADC_IN17`/`IN18` are
not on any LQFP48 port pin. Whoever writes `mcu_adc.c` needs IN9, not IN17.

Putting WE and RE on adjacent pins of identical structure is deliberate: their
leakage common-modes out of the WE-RE difference, which is the quantity the
bias check actually uses.

## Design work this creates — tasks, not open questions

1. **The signal now crosses domains.** The LMP91000 and OPA2333 sit in 3V3A;
   the converter sits in the digital domain, which is part of why 3V3A/3V3D are
   split at all. This is the real work of the change and it must be coordinated
   with `2026-09-12-revb-single-rail-supply.md`, not decided independently.
2. **`ADCAL` after every power-up** becomes a firmware requirement, not an
   option — DS12232: *"It is recommended to perform a calibration after each
   power-up."* It is what removes `EO`.
3. Rescale the retained dividers for the channels' operating ranges, and choose
   a long sampling time (160.5 cycles allows 50 kOhm `RAIN`).
4. Re-derive the VREF gate at `main.c:700` / `main.c:869` from an MCU channel.
   **Partly done** — the Rev B session moved the divider constant out of the
   generated contract and into the per-revision caps headers as
   `O2P_HW_DIV_VREF_MON_NUM/DEN` (A: 47000/94000, B: 1/1), which had to happen
   first: `hw_contract.h` is GENERATED from `gen_sch.py`, so deleting R34/R35
   would have rescaled the constant that `main.c:770` applies to the **Rev A
   bench board**, which really does read a halved copy. Rev A would have
   published 1250 mV and tripped its own VREF gate. Caught by them, not by me.
5. Oversampling is available and not required. Do not spend it to chase the
   ADS's 76 uV — the `uv / 1000` publication grid throws that away. If the
   register format is ever widened, revisit.

## Retracted

My own claim that this decision needed measurements on Rev B hardware. It did
not. The blocker was self-inflicted: U8's deletion had been welded to the
`VREF+` move, and only the `VREF+` move hits an uncharacterized condition.
Fab: *"why can't we answer the ADS-out question from the datasheets?"* — it
can be, and the answer is above.

**One thing still not answerable from a datasheet**, recorded so it is not
mistaken for settled: whether the MCU's conversions pick up noise from its own
digital activity, the RS-485 traffic and the LoRa duty cycle. Table 60's
`ENOB` comes from ST's evaluation conditions, not from a probe with a radio.
This is a layout and sampling-timing concern with standard mitigations, and the
margin above would have to be wrong by ~5x for it to matter — but it is the
one term that Rev B itself will have to confirm.
