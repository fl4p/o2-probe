# Rev-A footprint placement draft

> **Superseded by the schematic-linked first-article release dated
> 2026-08-23.** This file records the earlier placement study only. Fabricate
> from `fab/o2-probe-rev-a-fab.zip`; current geometry and gates are in
> `FAB-READINESS.md` and `FAB-NOTES.md`.

This is an **unrouted mechanical placement study**, not a schematic-derived
board. Its purpose is to force the enclosure, pot boundary, thermal slots,
component heights, cell gas path, and rework access into one KiCad artefact
before schematic capture.

## Files

- `o2-probe-placement.kicad_pcb` — editable KiCad 10 board.
- `draft_placement.py` — deterministic source for the placement study.
- `o2-probe-placement-preview.svg` — component-side plot.
- `o2-probe-placement-back-preview.svg` — solder-side plot, mirrored as viewed
  from outside the board.
- `placement-drc.rpt` — placement DRC; zero violations as generated.
- `lib/o2-probe.pretty/SGX-OX-ROHS-Mini_ISS2.kicad_mod` — released
  first-article cell footprint derived from DS-0637 Issue 2.

## Controlled datums

| Item | Draft value |
| --- | --- |
| Board | 20.0 × 125.0 mm, R2.0 corners, 1.0 mm, 4 layers |
| Board-local origin | cable-end left corner `(0, 0)` |
| Pot line | `y = 82.0 mm` |
| Gas zone | begins after transition at `y = 86.0 mm` |
| Cell centre | `(10.0, 93.5) mm` |
| Cell pin row | `y = 91.0 mm`, toward cable/AFE |
| LMP91000 centre | `(10.0, 79.5) mm` |
| LMP CELL_RE pad to cell RE pin | 9.652 mm |
| Rear-flow first-article aperture | 3.0 × 6.0 mm vertical NPTH slot, centred 2.5 mm gasward |

The cell moved from the outline sketch's original `y = 105 mm` to `y = 93.5
mm`. At 105 mm the cell pins were roughly 20 mm beyond the pot boundary, which
contradicted the plan's short high-impedance AFE-run requirement. At 93.5 mm the
Ø14.4 mm body starts at `y = 86.3 mm`, just inside the gas zone, while the pin
row is 11.5 mm from the LMP centre. The verified production footprint must put
the C/R/W-side pads toward the dam, targeting an approximately 9.5 mm pad-row to
pin-row run; this placeholder cannot prove final trace length.

## Placement structure

- Front, cable to tip: cable pads; input protection; buck; digital/analogue
  rails; RS485 and MCU; programming; expansion connector; heater/guard/AFE/ADC;
  O₂ cell; SHT45; gas-reference TMP117 and DNP BMP390.
- Back: expansion TVS, DNP bias/termination, three AFE test points, two 2512
  heater resistors, and cell-block TMP117.
- The draft used six NPTH routed slots, including a provisional longitudinal
  gas-reference sensor tab. That U13 geometry was rejected because it ran
  parallel to heater-to-sensor heat flow. The released board instead uses the
  audited transverse barrier documented in `DESIGN.md` and `FAB-NOTES.md`.

## Footprints that are explicitly provisional

- SGX rear-port diameter, drill/pad annuli, and physical sample tolerance.
- LMP91000 land pattern: the board uses a geometrically representative 4 × 4 mm
  DFN-14 placeholder until the exact package drawing is verified.
- BMP390: a 2 × 2 mm LGA-10 placement envelope is used; pin-land geometry is
  marked `FP TBD` and must not reach fabrication.
- Buck, PFET, VREF option, heater FET, expansion TVS, and passives await the
  Phase-1 part choices.
- Micro-Fit 2×4 is intentionally present at full footprint size so its tube
  chord and mated-height failure is visible; replace it with the pad-field
  fallback if the mechanical section does not close.

Do not route this file. Build the schematic and verified custom footprints,
then transfer the accepted coordinates into the schematic-linked PCB.
