# o2-probe

A buried oxygen probe for compost windrows. It combines an electrochemical
O₂ cell, its potentiostat, a heated membrane, and an STM32 that speaks
Modbus RTU, all on one elongated PCB inside a printed body that is potted at
one end and open to the pile gas at the other.

Measuring O₂ in a pile is mainly a condensation problem. Pore gas is
saturated and a buried probe conducts heat outward, so every surface sits
below the dew point. The cell, however, is rated 15–90 %RH *non-condensing*.
Most of this design exists to keep the membrane dry.

**View the board in the browser:**
[Rev B PCB and schematic in KiCanvas](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Ffl4p%2Fo2-probe%2Ftree%2Fmain%2Fhw%2Frouting%2Frevb-86)

## Status

Research hardware, not a product. A Rev A board runs on the bench and has
been in a pile. Rev B (20 × 86 mm, 2 layers, the ADS1119 replaced by the
STM32's own ADC) is routed and reviewed but not yet fabricated.
`hw/README.md` has the current board state.

## Layout

| path | contents |
|---|---|
| `hw/` | electronics: the KiCad project, its generators (`gen_sch.py` is the schematic's source of truth), audits, routing variants, fab packages, bench logs |
| `hw/firmware/` | STM32G071 firmware (PlatformIO). Its scale factors are generated from `../gen_sch.py` |
| `cad/` | the printed body, head end and fixtures (OpenSCAD), print profiles, the three.js viewer |
| `docs/` | system-level design records: membrane, potting, power, cable, condensation model, calibration budget |
| `model/` | lumped response and heater model (Python, uncalibrated) |
| `analysis/` | calibration and field-error budget scripts |
| `reviews/` | independent design reviews |
| `vendor/` | vendor documents for the membrane |
| `viewer/` | superseded Rev A three.js viewer |

## Where to start

- `docs/PLAN.md` is the system plan and indexes the other design records.
- `hw/DESIGN.md` covers the architecture, I²C address map, register map and
  release gates.
- `hw/firmware/FIRMWARE.md` covers the register map, fault semantics and
  bring-up.
- `docs/O2-CORRECTION-MODEL-BUDGET.md` shows what calibration can and cannot
  buy.
- `cad/README.md` covers the mechanical parts and how to build them.

## History

The electronics and firmware were developed in a separate monorepo and moved
here on 2026-11-02 with their history intact (`hw/`). Before that, this repo's
root held an older, frozen copy of the KiCad project. That copy was removed,
and git history still has it.
