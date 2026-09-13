# revb-86-ring — ring lands + external-sensor pads (WORK IN PROGRESS, DO NOT FAB)

Derived from the accepted [`routing/revb-86`](../revb-86) board on 2026-09-13,
after Fab: *"the pcb missed the ring pads at the tip. add them."* The accepted
board and its fabrication package are unchanged; this candidate is not fabricable
while the one item under **Blocked** stands.

Current DRC: **12 violations — exactly the accepted board's baseline** (10
courtyard overlaps + 2 `track_dangling`, all pre-existing and individually
documented there), **0 footprint errors**, and one unconnected item (below).

## J5 — the membrane-ring lands

Two lands, **2.8 x 2.0 mm, on front AND back copper**, centred X 101.75 / 118.25
at Y 137.65, so each spans Y 136.65..138.65 — 0.35 mm off the front edge where
the rule is 0.30. Plain SMD rectangles: no drills, no plated slots, no
castellations (Fab, 2026-09-13 — the ring is soldered flat, so none of that
tooling bought anything).

Width is 2x the first attempt. **Height stopped at 2.0 by measurement, not
preference:** `/I2C_SDA` on B.Cu reaches Y 136.45 directly under the left land.
Land area is 2.7x the first attempt.

All four pads are **number 1** with `duplicate_pad_numbers_are_jumpers no`: one
`/HEATER_LOW` node, so the ring is a heat spreader and never a conductor between
the lands. The **back** lands sit in the `HEATED_ISLAND_SPREADER` pour, which is
what connects them — no track is needed (Fab: *"the fill is enough"*; a track
tried in its place connected nothing, because it lay inside the island it was
meant to escape). A **0.4/0.2 via at each land** ties the **front** land down to
that pour.

Both thermal slots were **shortened 2 mm** at the tip end (apex Y 137.0 ->
135.0), restoring Rev A's 4.0 mm slot-to-tip bridge — the geometry the
theta = 68 K/W measurement (`aa6133d`) was actually taken on.

**C35 moved up 1.1 mm**, (117, 136.5) -> (117, 135.4), to clear the enlarged
right land. Moving a part on a routed board orphans its copper, so both feeds
were repaired: `/3V3D` now approaches from below the land, and the GND stub that
reached its old pad is pulled back to X 116.3 with the F.Cu plane connecting the
pad. C35 is U16's supply bypass and is now 1.1 mm further from it — still short,
but worth knowing if TMP302 behaviour is ever suspect.

## J107 — external-sensor / UART solder pads (placed and routed)

Six plain SMD lands on **back** copper, 1.6 x 1.2 mm on 2.6 mm pitch, at
(110, 61.5) — the cable end, where a flying lead leaves with the cable:

    1 = 3V3D   2 = GND   3 = I2C_SDA   4 = I2C_SCL   5 = UART2_TX   6 = UART2_RX

Y 61.5 is not a preference either: **Y 55..62 is the only band on this board with
zero B.Cu copper.** The region under the MCU, where these nets actually live, has
200+ segments in 6 mm and cannot take a 16 mm pad row.

**All six pads are connected.** GND sits in `GND_PLANE_BCu`; the rest are routed:

| net | length | vias |
|---|---|---|
| `/3V3D` | 16.2 mm | 1 |
| `/I2C_SDA` | 47.6 mm | 2 |
| `/I2C_SCL` | 60.0 mm | 3 |
| `/UART2_TX` | 22.9 mm | 1 |
| `/UART2_RX` | 25.5 mm | 3 |

Routed by [`tools/`](../../tools/README-router.md), not by hand — two hand
attempts had already failed, one with seven shorts.

**`/I2C_SCL` takes 60 mm and that is not waste.** The band under the MCU
(Y 86..95) has exactly **one** corridor: whichever I2C net routes first takes it,
and the second is then fenced off its own target by 2.84 mm near
(116.10, 93.90). Rip-up-and-retry found no alternative corridor at all. The fix
was not to force a second lane but to let SCL join its net further south — I2C
runs all the way to U10/U12 at the tip. At 100 kHz with R10/R11 biasing the bus
the extra length costs a few pF; if this bus is ever run fast, re-examine this
first.

### Addressing, for whatever gets soldered to J107

The bus already carries U7 (LMP91000, 0x48), U10 (TMP117 CELL, ADD0 -> 3V3D, so
**0x49**) and U12 (SHT45-AD1F, 0x44). An external TMP117 must **not** strap ADD0
to GND — that is 0x48 and collides with the LMP91000. Use ADD0 -> SDA (0x4A) or
ADD0 -> SCL (0x4B). No ADD0 pad is provided: the strap belongs on the sensor's
own carrier. Do **not** add pull-ups on the lead; R10/R11 already bias this bus.
3.3 V logic only — PA2/PA3 are not 5 V tolerant.

Pads 5/6 duplicate the existing J105/J106 bench taps at (111.75, 97.8) and
(117, 97.8), which stay where they are. Retiring them was not asked for and was
not done.

## Silk over the ring land — fixed

The existing `TMP_CELL` B.Silkscreen label clipped the left ring land, which
would have put silk ink under a hand-soldered joint. Moved (104.5, 138.2) ->
**(111.3, 138.2)**; the board now has **zero silk findings**.

Finding the spot took measuring rather than nudging. Four earlier positions and
two land widths each traded `silk_over_copper` for a `silk_overlap` against R28
or a `silk_edge_clearance`. The band **Y 137.6..139.0 between X 103.3 and 116.7**
is the only one on the back side with no pad in it: TP6 ends at Y 137.50, Q2.3 at
136.93, and the ring lands hold X <= 103.15 and X >= 116.85. Inside that band the
label still had to clear TP6's own silk circle at (108.3, 137.0) — (110.5, 138.2)
missed by 0.034 mm, (111.0, 138.3) still clipped, (110.5, 138.5) hit the board
edge. (111.3, 138.2) clears everything, and sits beside TP6, the testpoint it
names.

## Blocked: three `/I2C_SDA` segments, and that is the whole of it

`HEATED_ISLAND_SPREADER` fills as **two islands** that no copper joins, so the
left ring land does not reach the drive at Q2/RH1/RH2. This is the one
unconnected item in DRC, and it is a zone-to-zone item — not a land, which is how
we know the front-land vias work.

Pinned by experiment rather than by reading the map: delete these three
`/I2C_SDA` B.Cu segments, refill, and the pour merges to **one** island.

    (104.70, 137.20) -> (106.50, 138.50)
    (106.50, 138.50) -> (110.60, 138.50)
    (110.60, 137.95) -> (110.60, 138.50)

That run climbs to Y 138.5 — within 0.5 mm of the tip edge — to carry SDA across
to U10, the tip TMP117 at (110, 136.525). It is a wall across the island, and
0.5 mm of board cannot pass a pour.

**That is the real cost of having deleted J5.** Removing it did not only remove
two pads, it freed the tip corridor, and the router filled it with the I2C pair.
The remaining task is a bounded re-route of `/I2C_SDA` between X 104.7 and U10,
out of the B.Cu tip strip, with that strip a keepout for signal nets so the pour
stays whole. U10 and U16 both live there and both need I2C, so the corridor is
contested on F.Cu too — authored constraint, not a longer router run.
