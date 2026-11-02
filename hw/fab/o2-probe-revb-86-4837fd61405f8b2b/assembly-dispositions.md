# Current Rev B nominal assembly review, 2026-09-12

This review applies to the ten named courtyard pairs on PCB SHA-256 `0ab6c7d57ef5040e48fbe07a75c69c1efedaed9a31eaa8847592d10277bdafcd`, privately saved in `checks/current-assembly-review-v2/board.kicad_pcb`. Their native footprint UUIDs and positions match the ten warnings in `checks/bus-nrst-d8-drc.json`. Routing can change later without changing these nominal gaps; any footprint or pad geometry change requires a fresh comparison. This replaces the old 15-pair candidate-specific dispositions only for these ten current pairs.

Distances are derived from native Fab body outlines, the existing nominal cable-envelope circles, and native copper-pad polygons. They are **CAD measurements**, not measured package tolerances or actual cable dimensions. Pad polygon chord tolerance is0.0001mm; reported values are rounded to0.001mm. Nonplated holes are excluded from copper-pad distance. Test pads have no component body. The Tag-Connect footprint has no Fab body for an installed connector; the temporary mating head is not modelled here.

| Current pair | Body / wire-envelope gap (mm) | Copper-pad gap (mm) | Specific disposition |
|---|---:|---:|---|
| D1 / J102 | 1.650 | 10.675 | Positive nominal body/envelope and land clearance; retain warning for manual assembly. |
| D1 / J101 | 2.065 | 10.840 | Positive nominal body/envelope and land clearance; retain warning for manual assembly. |
| R10 / J105 | 0.488 | 0.350 | Back-side wire tap has0.488mm nominal body/envelope gap; dress and inspect its actual wire/joint. |
| R3 / J104 | 0.000 | 2.350 | Nominal cable envelope overlaps resistor body and lands; raise/laterally dress J104 before potting. |
| D2 / J103 | 0.100 | 2.388 | Only0.100mm nominal body/envelope gap; dress J103 away from D2 and inspect before potting. |
| D2 / J104 | 0.000 | 2.332 | Nominal envelope touches D2 body outline; raise/laterally dress J104 and inspect before potting. |
| TP3 / U4 | — | 0.515 | Bare CELL_CE test pad; no component-body collision. Preserve pre-pot probe access. |
| R2 / J103 | 0.000 | 2.350 | Nominal cable envelope overlaps resistor body and lands; raise/laterally dress J103 before potting. |
| Q2 / TP6 | — | 0.916 | Bare TMP_CELL_EP test pad; no component-body collision. Preserve pre-pot probe access. |
| J3 / TP5 | — | 2.318 | No installed connector body or test-pad body. Temporary SWD-head access/clearance remains a first-article check; remove head before probing GUARD. |

The closest R10 body-to-J105 land gap is0.413mm, while J105’s nominal cable envelope is0.425mm from R10’s lands. The U4 body remains1.562mm from TP3 copper; Q2 body remains0.628mm from TP6 copper. These checks distinguish bare-pad courtyard overlaps from actual body-to-land interference.

J103/J104 use the previously reviewed raised-relief cable footprint. The nominal1.7mm envelope comes from its existing Fab circles; the additional outer Fab guide lines are drawing guides, not a newly measured cable size. The native envelope overlaps R2/R3 lands and touches or closely approaches D2, as explicitly listed above. Actual insulation outside diameter, bend, solder fillet, height, strain relief and clearance must be inspected on the first assembly. No new physical interface dimensions are assumed.

The ten warnings are acceptable as **individual nominal CAD/manual-assembly dispositions with the listed operations**. They remain enabled and visible. This is not an automated-assembly clearance qualification, a guarantee of actual component tolerances, a blanket courtyard waiver, or fabricated first-article evidence. The SGX cell interface, gas path, potting boundary and thermal/mechanical qualification are outside these ten pair measurements.

Measurement producer: `checks/review_current_assembly.py`; exact results and source/DRC/producer hashes: `checks/current-assembly-review-v2/measurements.json`. No PCB or footprint was changed by this review.
