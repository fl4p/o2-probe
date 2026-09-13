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

### J107 — external-sensor / UART solder pads (placed, NOT routed)

Six plain SMD lands on **back** copper, 1.6 x 1.2 mm on 2.6 mm pitch, at
(110, 61.5) — the cable end, where a flying lead leaves with the cable:

    1 = 3V3D   2 = GND   3 = I2C_SDA   4 = I2C_SCL   5 = UART2_TX   6 = UART2_RX

Placement is clean: no clearance, courtyard or hole violations, and it clears the
J101..J104 strain-relief NPTHs at Y 64.7 and D1/F1 at Y 69.5. It went to Y 61.5
because Y 55..62 is the only band on this board with **zero** B.Cu copper; the
region under the MCU, which is where these nets actually live, has 200+ segments
in 6 mm and no room for a 16 mm pad row.

**All six pads are connected** (2026-09-13). GND sits in `GND_PLANE_BCu`; the
other five are routed:

| net | length | vias |
|---|---|---|
| `/3V3D` | 16.2 mm | 1 |
| `/I2C_SDA` | 47.6 mm | 2 |
| `/I2C_SCL` | 60.0 mm | 3 |
| `/UART2_TX` | 22.9 mm | 1 |
| `/UART2_RX` | 25.5 mm | 3 |

Routed by `tools/` (see `tools/README-router.md`), not by hand — two hand
attempts had already failed, one of them with seven shorts. DRC afterwards is
back to the accepted board's 12-violation baseline with **0 footprint errors**
and the only unconnected item the standing spreader-island split.

**`/I2C_SCL` takes 60 mm and that is not waste.** The band under the MCU
(Y 86..95) has exactly **one** corridor: whichever I2C net is routed first gets
it, and the second is then fenced off its own target by 2.84 mm near
(116.10, 93.90). Rip-up-and-retry found no alternative corridor at all. The fix
was not to force a second lane through but to let SCL reach its net further
south — I2C runs all the way to U10/U12 at the tip, so there is copper to join
at the other end. At 100 kHz and with R10/R11 already biasing the bus, the added
length costs a few pF and nothing else; if this bus is ever run fast, this is
the first thing to re-examine.

### Addressing, for whatever gets soldered to J107

The bus already carries U7 (LMP91000, 0x48), U10 (TMP117 CELL, ADD0 -> 3V3D, so
**0x49**) and U12 (SHT45-AD1F, 0x44). An external TMP117 must therefore **not**
strap ADD0 to GND — that is 0x48 and collides with the LMP91000. Use ADD0 -> SDA
(0x4A) or ADD0 -> SCL (0x4B). No pad for ADD0 is provided: it is strapped on the
sensor's own carrier. Do **not** add pull-ups on the lead; R10/R11 already bias
this bus. 3.3 V logic only — PA2/PA3 are not 5 V tolerant.

Pads 5/6 duplicate the existing J105/J106 bench taps, which stay where they are
at (111.75, 97.8) and (117, 97.8). Retiring them was not asked for and was not done.

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
