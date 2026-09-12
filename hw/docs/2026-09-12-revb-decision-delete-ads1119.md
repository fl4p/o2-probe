# Rev B decision: delete the ADS1119 (U8)

**Decided 2026-09-12 by Fab.** Supersedes P0 of
[`2026-09-12-revb-proposals-from-the-afe-failure.md`](2026-09-12-revb-proposals-from-the-afe-failure.md),
which recorded this as a proposal. Extends
[`2026-09-12-revb-decision-vref-monitor.md`](2026-09-12-revb-decision-vref-monitor.md),
whose deferred item is resolved here as **rejected**, not adopted.

Every analog channel moves to the STM32G071CBT7's own ADC. U8 comes off the BOM.

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
3. **The ADC scale would depend on trimpot RV1** instead of an LDO. Cancels for
   O2 by construction; does not cancel for the rail monitors.
4. **A switched-cap load would land on `/VREF_TRIM`**, the net the LMP's 0.67x
   zero derives from.

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

## Pins

Not a constraint. `gen_sch.py:1082` assigns 22 of 48; PA0 (11), PA1 (12) and
PA5 (16) are already unassigned and ADC-capable, and deleting U8 frees PB1
(`ADC_DRDY`) on top of that. Four channels are needed.

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
4. Re-derive the VREF gate at `main.c:700` / `main.c:869` from an MCU channel;
   delete the `O2P_HW_*_ON_ADS` capability flags and regenerate
   `hw_caps_rev_b.h` from the new netlist.
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
