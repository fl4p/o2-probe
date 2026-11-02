# O2 probe Rev A bare-board fabrication notes

Release class: first-article bare PCB only.

## Order parameters

- Finished board: 20.00 × 107.00 mm, R2 cable-end corners and square gas-side
  corners, 1.00 mm FR-4.
- Layer order: F.Cu / In1.Cu / In2.Cu / B.Cu.
- Copper: 1 oz outer layers, 0.5 oz inner layers.
- Finish: ENIG; green solder mask both sides; no legend Gerbers.
- Impedance control: none.
- Standard vias: tent both sides; no general plugging/filling/capping request.
- Minimum supplied feature: 0.09 mm trace, 0.15 mm clearance, 0.25/0.15 mm
  via/drill, 0.05 mm annular ring, and 0.20 mm copper-to-routed-edge clearance.
- Special process: two castellated, plated 1.00 × 2.00 mm slots on the
  left/right gas-side edges. Confirm plated-slot castellation capability before
  ordering; ordinary unplated profile routing is not an acceptable substitute.

The KiCad dielectric stack is a nominal 1.00 mm model, not an impedance coupon.
The fabricator may use its standard four-layer 1.00 mm dielectric construction
while preserving layer order, finished thickness, and copper weights.

## Mechanical and ring data

- Edge.Cuts contains the exact six-primitive outer contour (rounded cable end,
  square gas end) plus four internal routed thermal slots. Two horizontal
  6.75 × 1.50 mm capsules are centred at `(104.125,134.00)` and
  `(115.875,134.00)` mm. Two vertical 0.80 × 16.00 mm capsules are centred at
  `(101.20,145.00)` and `(118.80,145.00)` mm and span y=137.00–153.00 mm.
  Route all four closed contours as shown; do not omit, resize, join, or
  reinterpret them during CAM cleanup.
- The slots leave 0.75 mm FR-4 webs at the side edges and a 5.00 mm centre
  neck. Zone fill is excluded on all four copper layers across the full board
  width from y=133.00 to 135.00 mm. Do not restore plane copper in this strip
  during CAM cleanup: the remaining 14 explicit tracks, two crossing vias, and
  one 0.15 mm In2 GND bridge are intentional. The slots and fill gap form a
  partial transverse thermal break, not a mechanically free island.
- No track, via, or pad may bridge either vertical side slot. The B.Cu heater
  spreader must preserve both slot voids. The side slots begin 2.25 mm beyond
  the transverse-slot gas-side edge and are a lateral-coupling break, not a
  16 mm series barrier between tip and body.
- U11 contains a separate routed mechanical aperture: one 3.00 × 6.00 mm
  gasward-offset NPTH oblong centred at `(110.00,145.30)` mm in the Excellon
  data. Its nearest edge is 0.30 mm from U11 pad-2 copper. Do not convert it to
  a round drill, move it, or resize it without engineering approval.
- U11's three cell pads are a **socket land, not a pin land**. The oxygen cell
  may not be soldered (SGX DS-0317 Issue 2 note 3), so the holes take a
  receptacle. Finished hole **1.32 mm +0.10/−0.00** — one-sided, because only an
  undersize hole blocks insertion — on a 2.00 mm land, for TE Connectivity
  5050462. The land is oversized on purpose: an assembler may **bore these three
  holes to 1.40 mm** to fit Cambion 450-3703 instead, which leaves a 0.30 mm
  annular ring and is an approved build option. Do not shrink the land to
  "recover" clearance to the NPTH aperture; the 0.30 mm figure above already
  accounts for it, and `audit_pcb.py` asserts it.
- Assembly: degrease the board before the cell is fitted (DS-0317 Issue 2
  note 8), and fit the cell **last** — after clean, bake, coat, pot and cure.
  It may never see reflow, wash, or cure heat.
- J5 has two 2.00 × 3.00 mm through-hole pads centred at `(100.00,155.50)` and
  `(120.00,155.50)` mm. Each contains a 1.00 × 2.00 mm plated slot marked with
  KiCad's castellated-pad fabrication property. The finished left/right profile
  bisects the slot centreline; plate the slots before profiling so the exposed
  vertical sidewalls remain solderable. The pad copper reaches the square tip
  corners, and the two contacts are joined by 0.80 mm B.Cu inside the board.
- The user-supplied metal membrane-carrier ring is hand soldered after board
  fabrication. It is not part of the bare-board CAM data.
- J5 is switched `HEATER_LOW`, not ground. Assembly must keep the ring on the
  dry side and electrically insulated from the membrane wet face, enclosure,
  and accessible conductors.
- The F.Cu Gerber contains three deliberately stitched `GUARD_REPLICA` fill
  regions flanking CELL_RE. Do not strip, merge, or redraw these narrow regions
  during CAM cleanup; the release manifest records exact region and sample
  validation.
- The B.Cu Gerber contains a solid `/HEATER_LOW` spreader over the gas-side
  island beginning at y=135.00 mm. This is deliberate thermal copper and must
  not be stripped as an island. In2 GND is deliberately plotted as two regions
  separated by the pour gap and joined by the narrow routed bridge.
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
acceptance operations. The pre-measurement bare-PCB transverse estimate is
90–110 K/W; its assumptions and measurement method are in
`THERMAL-BARRIER.md`. See also `FAB-READINESS.md`.
