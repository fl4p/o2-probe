# revb-86-ring — J5 membrane-ring lands restored (WORK IN PROGRESS, DO NOT FAB)

Derived from the accepted [`routing/revb-86`](../revb-86) board on 2026-09-13,
after Fab: *"the pcb missed the ring pads at the tip. add them."*

## Done and verified

- **J5 placed** at (110, 137.5), footprint `o2-probe:Heater_Ring_Solder_Lands`,
  copied from `routing/rev-a` rather than redrawn. Both castellated lands are
  pad number 1, one node on `/HEATER_LOW`, so the ring is a spreader and never
  carries current between the lands.
- **Both thermal slots shortened 2 mm** at the tip end (apex Y 137.0 -> 135.0),
  restoring Rev A's 4.0 mm slot-to-tip bridge. Rev B had tightened it to 2.0 mm,
  which is 1 mm less than the 3 mm lands need. Fab chose this over lengthening
  the board or shrinking the lands, 2026-09-13. It returns the tip to the
  geometry the theta = 68 K/W measurement (aa6133d) was actually taken on.
- **No join track.** Fab, 2026-09-13: *"it doesnt need that 0.8mm track, the
  fill is enough."* Correct, and measured: `HEATED_ISLAND_SPREADER` is a
  `/HEATER_LOW` pour over the whole tip island, so it reaches both lands by
  itself. A provisional 0.8 mm track was tried and removed - it changed nothing,
  because it lay *inside* the same island it was supposed to escape.
- DRC is back to the accepted board's exact baseline of 12 violations
  (10 courtyard overlaps + 2 track_dangling, all pre-existing and documented),
  0 footprint errors. Verified against a control: the unmodified board put
  through the same zone refill reports 0 unconnected pads, so the one remaining
  unconnected item is mine and not a refill artifact.

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
