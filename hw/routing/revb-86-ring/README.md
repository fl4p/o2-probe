# revb-86-ring — J5 membrane-ring lands restored (WORK IN PROGRESS, DO NOT FAB)

Derived from the accepted [`routing/revb-86`](../revb-86) board on 2026-09-13,
after Fab: *"the pcb missed the ring pads at the tip. add them."*

## Done and verified

- **J5 placed at (110, 137.9)** — two **plain SMD lands on back copper**, 1.4 x 1.5 mm
  at X 101.1 and X 118.9, hard against the front edge (0.35 mm to it, rule is 0.30).
  **No drills, no plated slots, no castellations** (Fab, 2026-09-13): the ring is
  soldered flat, so none of that tooling bought anything, and it drops the 1.00 mm
  castellation tool and its two routed slots from the fab data entirely.
- **B.Cu on purpose.** That is the layer `HEATED_ISLAND_SPREADER` pours on, so the
  lands tie into `/HEATER_LOW` with no copper added at all — Fab, 2026-09-13:
  *"it doesnt need that 0.8mm track, the fill is enough."* Confirmed: a provisional
  0.8 mm track was tried and removed, and refilling with and without it gives the
  same result, because it lay *inside* the island it was meant to escape.
- Both lands are **pad number 1**, and KiCad records
  `duplicate_pad_numbers_are_jumpers no` — one node, not a net-tie. The ring is a
  heat spreader and never a conductor between them.
- **Both thermal slots shortened 2 mm** at the tip end (apex Y 137.0 -> 135.0),
  restoring Rev A's 4.0 mm slot-to-tip bridge and the geometry the theta = 68 K/W
  measurement (aa6133d) was taken on.
- DRC: **0 footprint errors**, and the accepted board's 12-violation baseline
  (10 courtyard overlaps + 2 track_dangling, all pre-existing and documented).

### One accepted warning

`silk_over_copper`: the existing `TMP_CELL` B.Silkscreen label clips the left land.
Cosmetic, and it is a warning rather than an error, but it means silk ink under a
hand-soldered joint. Four positions for the label and two land widths were tried;
each traded it for a `silk_overlap` against R28 or a `silk_edge_clearance`. Left as
the least-bad of those, with the label in its original position rather than moving
an existing marking to suit a new part. **Worth one minute in the editor before fab.**

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
