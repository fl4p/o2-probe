# O2 probe Rev A bare-board fabrication notes

Release class: first-article bare PCB only.

## Order parameters

- Finished board: 20.00 × 107.00 mm, nominal R2 corners, 1.00 mm FR-4.
- Layer order: F.Cu / In1.Cu / In2.Cu / B.Cu.
- Copper: 1 oz outer layers, 0.5 oz inner layers.
- Finish: ENIG; green solder mask both sides; no legend Gerbers.
- Impedance control: none.
- Standard vias: tent both sides; no general plugging/filling/capping request.
- Minimum supplied feature: 0.09 mm trace, 0.15 mm clearance, 0.25/0.15 mm
  via/drill, and 0.05 mm annular ring.

The KiCad dielectric stack is a nominal 1.00 mm model, not an impedance coupon.
The fabricator may use its standard four-layer 1.00 mm dielectric construction
while preserving layer order, finished thickness, and copper weights.

## Mechanical and ring data

- Edge.Cuts contains the exact eight-primitive outer R2 contour plus two
  5.50 × 1.00 mm horizontal internal routed slots centred at `(103.75,134.00)`
  and `(116.25,134.00)` mm. Route both closed contours as shown; do not omit,
  resize, join, or reinterpret them during CAM cleanup.
- The slots leave 1.00 mm FR-4 webs at the side edges and a 7.00 mm centre
  neck. They form a partial transverse thermal break, not a mechanically or
  thermally isolated island.
- U11 contains a separate routed mechanical aperture: one 3.00 × 6.00 mm
  gasward-offset NPTH oblong in the Excellon data. Do not convert it to a round
  drill or resize it without engineering approval.
- J5 has four paste-free, mask-open 5.00 × 1.50 mm solder lands: two positions,
  each on front and back. Two 0.60/0.30 mm vias stitch the face pairs.
- The user-supplied metal membrane-carrier ring is hand soldered after board
  fabrication. It is not part of the bare-board CAM data.
- J5 is switched `HEATER_LOW`, not ground. Assembly must keep the ring on the
  dry side and electrically insulated from the membrane wet face, enclosure,
  and accessible conductors.
- PTH and NPTH drills are separate; the NPTH oblong uses route commands.
- Do not panelise through the gas-side end or SGX aperture without review.

The source `POT TO HERE` and `DO NOT OBSTRUCT` marks appear only in the
controlled multipage drawing. The potting fixture owns local `y=82`, and the
traveller must keep both gas faces and the SGX aperture unobstructed.

## Release contents

The ZIP contains seven Gerbers, separated PTH/NPTH Excellon data, drill
map/report, fabrication drawing, DRC/audit evidence, manifest, and checksums.
Fabricate from that ZIP, not from editor plot settings. SGX fit, enclosure fit,
ring assembly, and condensation/thermal qualification remain first-article
acceptance operations; see `FAB-READINESS.md`.
