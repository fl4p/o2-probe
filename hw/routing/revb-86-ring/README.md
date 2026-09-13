# revb-86-ring — J5 membrane-ring lands restored (WORK IN PROGRESS, DO NOT FAB)

Derived from the accepted [`routing/revb-86`](../revb-86) board on 2026-09-13,
after Fab: *"the pcb missed the ring pads at the tip. add them."*

## Done and verified

- **J5: two ring lands, 2.8 x 2.0 mm, on FRONT AND BACK copper** (Fab, 2026-09-13),
  centred X 101.75 / 118.25 at Y 137.65, so each spans Y 136.65..138.65 — 0.35 mm
  off the front edge, where the rule is 0.30. Plain SMD rectangles: no drills, no
  plated slots, no castellations.
  **Width is 2x the first attempt; height stopped at 2.0 and that is a measurement,
  not a preference** — `/I2C_SDA` on B.Cu reaches Y 136.45 under the left land, so
  anything taller shorts to it. Land area is 2.7x what it was.
- All four pads are **number 1** with `duplicate_pad_numbers_are_jumpers no`: one
  `/HEATER_LOW` node, so the ring is a heat spreader and never a conductor.
- The **back** lands sit in the `HEATED_ISLAND_SPREADER` pour, which is what connects
  them — no track needed (Fab: *"the fill is enough"*; a track tried in its place
  connected nothing, because it lay inside the island it was meant to escape). A
  **0.6/0.3 via at each land** (X 101.75 / 118.25, Y 137.0) ties the **front** land
  down to that pour.
- **C35 moved up 1.1 mm**, (117, 136.5) -> (117, 135.4), to clear the enlarged right
  land. Its two feeds were repaired rather than left dangling: `/3V3D` now approaches
  from below the land, (116.48, 137.5) -> (116.48, 136.45) -> (117, 136.0); the GND
  stub that used to reach its old pad is pulled back to X 116.3 and the F.Cu GND
  plane connects the pad. Note C35 is U16's supply bypass and is now 1.1 mm further
  from it — still short, but worth knowing if TMP302 behaviour is ever suspect.
- **Both thermal slots shortened 2 mm** at the tip end (apex Y 137.0 -> 135.0),
  restoring Rev A's 4.0 mm slot-to-tip bridge and the geometry the theta = 68 K/W
  measurement (aa6133d) was taken on.
- DRC: **0 footprint errors**, and the accepted board's 12-violation baseline
  (10 courtyard overlaps + 2 track_dangling, all pre-existing and documented).

### One accepted warning

`silk_over_copper`: the existing `TMP_CELL` B.Silkscreen label clips the left land.
Cosmetic, a warning not an error, but it means silk ink under a hand-soldered joint,
and the larger land makes the overlap bigger. Four label positions and two land widths
were tried earlier; each traded it for a `silk_overlap` against R28 or a
`silk_edge_clearance`. Left for a minute in the editor rather than moving an existing
marking to suit a new part.

## Blocked: three I2C_SDA segments, and that is the whole of it

The spreader fills as **two islands**, so the left land never reaches the drive
at Q2/RH1/RH2. The cause is now pinned exactly, by experiment rather than by
reading: delete these three `/I2C_SDA` B.Cu segments and refill, and the pour
merges to **one island**.

    (104.70, 137.20) -> (106.50, 138.50)
    (106.50, 138.50) -> (110.60, 138.50)
    (110.60, 137.95) -> (110.60, 138.50)

That run detours up to Y 138.5 - within 0.5 mm of the tip edge - to carry SDA
across to U10, the tip TMP117 at (110, 136.525). It is a wall across the island,
and 0.5 mm of remaining board cannot pass a pour.

**That is the real cost of deleting J5.** Removing it did not only remove two
pads, it freed the tip corridor, and the router took it. U10 and U16 both sit in
this strip and both need I2C, so the corridor is contested on F.Cu too.

The remaining task is therefore small and well-posed: **re-route I2C_SDA between
X 104.7 and U10 out of the B.Cu tip strip**, with that strip declared a keepout
for signal nets so the pour stays whole. Authored constraint, not a longer
router run. An earlier attempt to instead drive two straight tracks across the
strip produced 32 new violations including seven shorts.

Nothing here is fabricable. The accepted board and its package remain
`routing/revb-86`.
