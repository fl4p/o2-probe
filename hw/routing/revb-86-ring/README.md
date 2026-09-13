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
- **Left land tied into `HEATED_ISLAND_SPREADER`** with 0.8 mm B.Cu in the empty
  X 100..102.5 corridor. Zones refilled.
- DRC is back to the accepted board's exact baseline of 12 violations
  (10 courtyard overlaps + 2 track_dangling, all pre-existing and documented),
  0 footprint errors.

## Blocked: one unconnected item, and it is not a patch

`HEATED_ISLAND_SPREADER` fills as **two islands** that no copper joins, so the
left land does not reach the drive at Q2/RH1/RH2.

Rev A solves this with a single 0.8 mm B.Cu track at **Y = tip - 0.75 mm**
running the full width (X 100.75 -> 119.25), threading both lands. The
equivalent here is Y = 138.25.

**`/I2C_SDA` is routed through that corridor** — X 104.70..106.50 at
Y 137.20..138.50, X 106.50..110.60 at Y 138.50, and X 110.60 at Y 137.95..138.50.
`/I2C_SCL` and `/3V3D` occupy the same strip on F.Cu.

That is the actual cost of the deletion: removing J5 did not just remove pads,
it freed the tip corridor, and the router filled it with the I2C pair. Putting
the lands back requires a **bounded re-route of I2C_SDA (and likely I2C_SCL and
3V3D) out of the Y 137..139 strip** — constraint-authoring work, not a search
problem. See [`kicad/routing-failure-is-rarely-cross-section-capacity`](https://github.com/fl4p/kb)
in the kb before widening any router run.

Nothing here is fabricable. The accepted board and its package remain
`routing/revb-86`.
