# O2 probe Rev A bare-board fabrication notes

Release class: first-article bare PCB only.

## Order parameters

- Finished board: 20.00 × 125.00 mm, nominal R2 corners, 1.00 mm thick FR-4.
- Layer order: F.Cu / In1.Cu / In2.Cu / B.Cu.
- Copper: 1 oz outer layers, 0.5 oz inner layers.
- Finish: ENIG.
- Solder mask: green, both sides.
- Legend: none. No silkscreen Gerbers are included.
- Impedance control: none.
- Via treatment: tent standard vias both sides; no plugging, filling, or
  capping requirement.
- Minimum routed feature in supplied data: 0.09 mm trace, 0.15 mm clearance,
  0.25/0.15 mm via/drill, 0.05 mm annular ring.

The KiCad dielectric stack is a nominal 1.00 mm model, not an impedance coupon.
The fabricator may adjust prepreg/core thicknesses to its standard four-layer
1.00 mm process while preserving layer order, finished thickness, and copper
weights.

The source `POT TO HERE` and `DO NOT OBSTRUCT` legend marks are included in the
controlled multipage fabrication/assembly drawing, but not printed on these
first-article boards. The potting fixture owns the y=82 datum, and the assembly
traveller must keep the SGX slot and both gas faces unobstructed. Physical
legend is a production-release item after the dense placement is cleaned.

## Mechanical data

- Six closed routed slots are part of Edge.Cuts.
- The U13 thermal barrier is the pair of transverse 7.50 × 0.80 mm slots at
  local `y=114.0`. Preserve the 0.75 mm edge webs and 3.50 mm centre neck; do
  not rotate the slots or substitute the rejected longitudinal geometry.
- U11 contains one 3.00 × 6.00 mm gasward-offset NPTH routed slot. Do not
  convert it to a round drill or reduce it without engineering approval.
- PTH and NPTH drills are separated in the Excellon outputs. NPTH oblongs use
  route commands.
- Do not panelise through the gas-side end, sensor aperture, or potting slots
  without an engineering review.

## Release contents

The ZIP contains seven Gerbers (four copper, two mask, one outline), separated
PTH/NPTH Excellon data, drill map/report, the controlled fabrication/assembly
drawing including both source legend layers, DRC/audit evidence, manifest, and
checksums. Fabricate from the ZIP, not from editor plot settings.

First-article SGX fit, enclosure fit, manual assembly, and bench qualification
are acceptance operations; see `FAB-READINESS.md`.
