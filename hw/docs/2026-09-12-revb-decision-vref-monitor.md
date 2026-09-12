# Rev B decision: the VREF monitor is a direct MCU measurement

**Decided 2026-09-12 by Fab.** Scope: the reference-monitoring path only. This
resolves P1 and P2 of
[`2026-09-12-revb-proposals-from-the-afe-failure.md`](2026-09-12-revb-proposals-from-the-afe-failure.md)
and takes one step of P0. It does **not** decide U8's fate.

## ADOPTED — measure `/VREF_TRIM` directly on a free MCU ADC pin

`/VREF_TRIM` is 2.500 V, which is **below** VDDA (3.3 V), so the MCU can
convert it with **no divider at all**. Source impedance is the OPA2333 output
plus R31's 47 Ohm, actively driven, against the 50 kOhm `RAIN` limit of
DS12232 Table 59.

**Delete R34, R35, R36, C29** (`gen_sch.py:1362-1375` — 47k 0.1 %, 47k 0.1 %,
1k, 100n), and with them the nets `/VREF_MON_RAW` and `/ADC_VREF_MON`.

Pin: one of PA0 (11), PA1 (12) or PA5 (16) — all unassigned and ADC-capable.
`gen_sch.py:1082` assigns 22 of 48 pins, so this costs nothing that was wanted
elsewhere.

### Why this beats lowering the divider impedance (the original P2)

| | 23.5 kOhm divider | direct, 47 Ohm |
|---|---|---|
| leak-sensitive node | yes, two | **none** |
| error from 70 nA pad leakage (DS12232 Table 51) | 1.6 mV | **3 uV** |
| sample-cap charge | from the divider | **from the op-amp** |
| parts | 4 | **0** |

P2 proposed making the failure *less likely*. This removes the node the
failure needs.

### What it fixes, stated narrowly

It does not make an in-package leak impossible. **It makes one unable to blind
the reference monitor**, because the monitor no longer runs through U8 at all.
That is the durable win and it is larger than the four parts: the 2026-09-12
investigation cost five hours because the only view of the 2.5 V reference ran
through the single ADS1119 channel that was lying about it.

## DEFERRED — moving `VREF+` (pin 5) from 3V3D to `/VREF_TRIM`

Proposed under P0 and **not adopted now**. Its only benefit is ratiometry for
an MCU-side O2 conversion, which pays off only if U8 is deleted, and it carries
costs the direct measurement above does not:

- **Every MCU ADC channel's full scale drops 3.3 V -> 2.5 V.** The existing
  dividers all fit nominally (VA_MON 1650 mV, CE_MON <= 1650 mV, VIN_MON
  ~1190-1390 mV) but the rail monitors lose over-range headroom: 3V3A excursing
  to 5 V puts the VA tap at exactly full scale and clips above it. Quantifying
  an over-voltage is not hypothetical — it is the check run across 14 days of
  telemetry on 2026-09-12 to date the failure.
- **The MCU's ADC scale becomes dependent on trimpot RV1** instead of an LDO.
  Cancels for O2 by construction; does **not** cancel for the rail monitors.
- **A third, switched-cap load lands on `/VREF_TRIM`**, the net the LMP's 0.67x
  zero derives from. R31's 47 Ohm should swamp 0.26 uA average
  (`IDDV(ADC)`, DS12232 Table 58) but the sampling transient injects onto a
  signal-path reference.
- Accuracy under this condition is **uncharacterized**: every row of DS12232
  Table 60 is specified at `VDDA = VREF+`. Operation with VREF+ < VDDA is
  permitted (p.809-817) but ST publishes no accuracy figure for it.

Revisit with the U8 decision, not before.

## Follow-on work this decision creates

1. **Assign the pin and rewire** in `gen_sch.py`; drop the four parts and the
   two nets; regenerate `hw_caps_rev_b.h` with `tools/gen_hw_caps.py` (it reads
   the revision's own netlist, which is why Rev A's caps header and the
   hand-written `hw_contract.h` disagree on the VA divider today).
2. **U8's AIN1 must not be left floating** if U8 stays fitted. Tie it to AGND
   or guarantee firmware never selects it —
   `~/dev/kb/adc/floating-mux-input-mirrors-previous-channel.md` is exactly
   this failure, and it is what AIN0 has been doing since 22:24 on 09-11.
3. **Firmware: re-derive the VREF gate.** `finish_vref()` (`main.c:700`) reads
   the ADS AIN1 and reconstructs x2 via `O2P_HW_DIV_VREF_NUM/DEN`
   (`hw_contract.h:64-65`); with no divider the factor is 1 and the source is
   an MCU channel. The consumer is the early return in `finish_electrode()`
   (`main.c:869`), which is the guard that muted every externally-referenced
   channel on 09-11 — it is being rewritten under P3 regardless.
4. Keep the `VREF_MON_MV` register (0x0010) and its units. The telemetry
   history is the only record of the failure and must stay comparable.
