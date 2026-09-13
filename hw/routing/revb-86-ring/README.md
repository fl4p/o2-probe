# revb-86-ring — ring lands + external-sensor pads (DO NOT FAB — see BLOCKER below)

Derived from the accepted [`routing/revb-86`](../revb-86) board on 2026-09-13,
after Fab: *"the pcb missed the ring pads at the tip. add them."* The accepted
board and its fabrication package are unchanged.

**State, 2026-09-13 (after the tip re-route below):** full native DRC with
`--schematic-parity` reports **12 violations — exactly the accepted board's
baseline** (the same 10 courtyard pairs and the same 2 GUARD_REPLICA
`track_dangling`, all individually documented in `revb-86`), **0 unconnected
items** and **0 schematic-parity issues**. `HEATED_ISLAND_SPREADER` fills as
**one** island holding both ring lands, RH1, RH2 and Q2.

**Not yet orderable.** `make_fab_revb_86.py` exports only behind a review gate
(`review-gate.json`, `status: REVIEWED`, with an independent review record and
matching input hashes), and its verifier `verify_revb_86.py` accepts only the
3 mm head trim against the 89 mm board. This board changes copper, so it needs a
ring-specific verifier/exporter and an independent review before a package can
exist. Nobody has reviewed it; do not write that gate by hand.

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
meant to escape). A **0.6/0.3 via at each land**, at (101.75, 137.0) and
(118.25, 137.0), ties the **front** land down to that pour. (Earlier versions of
this README said 0.4/0.2; the board has always carried 0.6/0.3 — read from the
native file on 2026-09-13 while writing the ring verifier.)

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

**Silkscreen, added 2026-09-13** after Fab reported the pads as missing. They
were not missing — they were **unmarked**: the footprint carried no B.SilkS at
all, with Reference and Value both hidden on B.Fab, which is not fabricated. Six
anonymous copper rectangles on the back of the board, with nothing saying which
one is SDA, read as absent and could not have been soldered to. Now on B.SilkS:

    3V3   GND   SDA   SCL   TX   RX        (at Y 59.75, each above its own pad)
    J107 EXT I2C / UART                    (at Y 58.20)
    a filled pin-1 dot                     (at X 101.90)

0.8 mm / 0.12 mm, the board's minimum text height and thickness — 0.55/0.09 was
tried first and DRC rejected it.

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
was not to force a second lane but to let SCL join its net further south. At
100 kHz with R10/R11 biasing the bus the extra length costs a few pF; if this bus
is ever run fast, re-examine this first. (The J107 routes end at their net well
north of the tip and are untouched by the tip re-route below.)

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

## BLOCKER: J107's I2C cannot clear the analog nets (measured 2026-09-13)

The independent review found J107's SCL run hugging `/GUARD_REPLICA`. Confirmed
and re-measured (`docs/2026-09-13-revb-86-ring-codex-review.md`):

| new J107 copper | runs beside | gap on this board | gap on accepted revb-86 |
|---|---|---|---|
| SCL, B.Cu X 101.1..101.2, Y 100..113.85 | `/GUARD_REPLICA` at X 101.5 | **0.100 mm** over ~9 mm | 0.625 mm |
| SDA, F.Cu X 118.35..118.95, Y 96.6..102.4 | `/VREF_TRIM` | **0.100 mm** over ~6 mm | not adjacent |

0.100 mm is the board minimum, so DRC is silent. A 100 kHz clock running
parallel to the working-electrode guard and to the ADC reference is an analog
defect that clearance rules do not catch.

**It is not a routing mistake, and no reroute fixes it.** Flood-fill
reachability with every sensitive net (`/CELL_*`, `/GUARD_REPLICA`, `/LMP_*`,
`/TMP_CELL*`, `/VREF*`, `/AFE_VOUT`) inflated by only **0.1 mm** beyond ordinary
clearance, ripping the **entire** J107 I2C route and allowing a join **anywhere**
on the bus:

    /I2C_SCL  target reachable: False   closest approach 3.29 mm
    /I2C_SDA  target reachable: False   closest approach 3.02 mm

Leave-one-out names the wall: SCL is blocked by the `/CELL_*` nets, SDA by
`/VREF_TRIM`. On 20 mm of two-layer board the analog section spans the width,
and the only corridor to the MCU's I2C is the one already taken at minimum
clearance. `/AFE_MENB` was excluded from the sensitive set after checking the
netlist — it is the LMP91000 module-enable input, a static digital line.

So this is a design decision, not a DRC fix: **J107's SDA/SCL pads cost 0.100 mm
of separation between I2C and the analog front end.** J107's 3V3D, GND, TX and RX
pads have no sensitive-net proximity at all (nearest approach > 0.8 mm) and are
unaffected either way. Until that decision is made, this board is not fabricable.

## The split spreader — fixed 2026-09-13

`HEATED_ISLAND_SPREADER` used to fill as two islands, with the left ring land
alone in an orphan strip (X 100.30..106.42) and RH1, RH2, Q2 and the right land
in the other. The left land carries no heater current either way, so this was
not a broken circuit — but that land exists to conduct heat into the left half
of the ring, and it was not doing so.

### What was believed, and what measurement changed

This section previously said *"three `/I2C_SDA` segments, and that is the whole
of it"*, with a bounded SDA-only re-route as the fix. Both halves were wrong:

- **It was four B.Cu segments**, not three: the run from the via at
  (104.2, 136.55) to (104.7, 137.2) belongs to the same wall. Measured with
  pcbnew's own `ZONE_FILLER`, deleting exactly these four, and nothing else,
  refills the pour as one island; the vias at both ends are not implicated:

      (104.20, 136.55) -> (104.70, 137.20)
      (104.70, 137.20) -> (106.50, 138.50)
      (106.50, 138.50) -> (110.60, 138.50)
      (110.60, 138.50) -> (110.60, 137.95)

  The mechanism is geometric: the B.Cu band along the front edge,
  Y ~136.6..138.70, is the **only** copper joining the left land to the body
  (the GND, HEATER_PWM and SDA verticals on the left all stop above it), and
  that run lay along it. The zone's `min_thickness` is 0.09 mm; the run at
  Y 138.5 left 0.025 mm.

- **SDA could not be moved alone.** U10's SDA pad (pad 6, south row of the DFN)
  sits in a sealed F.Cu pocket: the 3V3D bus and via to the north, the F.Cu
  front-band run of `/I2C_SCL` (the U12 <-> U10 hop) to the south, the board
  edge below. With no B.Cu allowed in the band, a flood fill from that pad
  reached 438 cells and no exit.

### What was done

Routed by [`tools/drive_tip_i2c.py`](../../tools/drive_tip_i2c.py) and written
by `tools/emit_tip.py`, with DRC and a pcbnew refill after every step:

1. **Removed** the four B.Cu SDA segments above, the U10-end SDA via
   (110.6, 137.95) with its F.Cu stub, and the 33 F.Cu segments of SCL's
   front-band U12 <-> U10 hop (38 segments, 1 via).
2. **`/I2C_SCL`, U12 pad 2 -> SCL copper north of the tip**, 11.7 mm on F.Cu,
   F.Cu below Y 137.0 refused so it cannot re-enter the band. It leaves pad 2
   from the pad's east end: U12's footprint carries a no-track keepout under
   the SHT45, and a stub from the pad centre crossed it (`items_not_allowed`,
   caught by DRC on the first attempt; the router now reads keepouts).
3. **`/I2C_SDA`, U10 pad 6 -> the via at (104.2, 136.55)**, 7.1 mm on F.Cu
   along Y ~138.0..138.1 plus a 0.7 mm B.Cu hop at Y 136.45, one new via. No new
   B.Cu below Y 136.5.
4. **A GND link from C20.2**, 6.3 mm, 3 vias. Step 2's SCL leg, the existing SCL
   run down to U10.1 and the 3V3D track together enclose an F.Cu GND pocket
   holding **C20.2 and U10.2** (Q2's source is not in it). DRC reported it as a
   GND F.Cu <-> B.Cu unconnected item. No straight two-via jumper fits — 620
   positions across both SCL walls, best margin -0.079 mm against RH1.2 and the
   0.8 mm HEATER_LOW run — so the router found a bent one: C20.2 north on F.Cu,
   B.Cu west under both SCL legs, F.Cu past HEATER_PWM, and a via onto the
   existing B.Cu GND vertical at X 102.25.
5. **Re-ended** the existing SDA segment (102.7, 134.95) -> (104.2, 136.45) onto
   its via centre at (104.2, 136.55); it had always been 0.1 mm short, and DRC
   only reported `track_not_centered_on_via` once the neighbouring run was gone.

Two dead ends are recorded because they are the evidence for the final shape:
joining SCL further east (X >= 107) or keeping it east of X 104 found no path at
all, and routing SDA before SCL left SCL with no path.

The J5 Design Note's "height capped at 2.0 by `/I2C_SDA` reaching Y 136.45 under
the left land" still holds: that is the SDA segment in step 5, which stays.
