# revb-86-ring — ring lands + external-sensor pads (DO NOT FAB — no review gate)

Derived from the accepted [`routing/revb-86`](../revb-86) board on 2026-09-13,
after Fab: *"the pcb missed the ring pads at the tip. add them."* The accepted
board and its fabrication package are unchanged.

**State, 2026-09-14 (after the tip re-route, the J107 I2C relocation and the SMD UART taps below):** full native DRC with
`--schematic-parity` reports **12 violations — exactly the accepted board's
baseline** (the same 10 courtyard pairs and the same 2 GUARD_REPLICA
`track_dangling`, all individually documented in `revb-86`), **0 unconnected
items** and **0 schematic-parity issues**. `HEATED_ISLAND_SPREADER` fills as
**one** island holding both ring lands, RH1, RH2 and Q2.

**Not yet orderable.** The ring-specific toolchain now exists —
`verify_revb_86_ring.py` (PASS), `inspect_revb_86_ring_fab.py` (PASS: 87 parts,
216 PTH, 8 NPTH) and the gated `make_fab_revb_86_ring.py` — and the schematic
audit is a PASS over the live inputs (87 components, 72 nets). What does not
exist is a gate: the only two independent reviews on record are of *earlier*
states of this board, and the second one ended **DO NOT ISSUE**. The J107
relocation below answers its remaining blocker, so the next step is a fresh
independent review of the board as it now stands. Do not write that gate by
hand; `make_fab_revb_86_ring.py` refuses a record that does not itself say
`ISSUE REVIEWED GATE`.

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

## J107 / J108 / J109 — external-sensor solder lands (placed and routed)

Six plain SMD lands on **back** copper, 1.6 x 1.2 mm — and **three parts**, not
one. J107 is the four-land **row** at (110, 61.5), the cable end, where a flying
lead leaves with the cable, on 2.6 mm pitch. The I2C pair moved up the board on
2026-09-14 to get it away from the analog front end (the section on that is
below), and was then split out into two single-land parts so each land can be
placed on its own:

    J107  1 = 3V3D   2 = GND   5 = UART2_TX   6 = UART2_RX     row, Y 61.5
    J108  1 = I2C_SDA  at (118.82, 101.97)
    J109  1 = I2C_SCL  at (118.85, 100.00)

They are separate components because a pad inside a placed footprint cannot be
dragged in pcbnew without Pad Edit Mode, and a board whose footprint no longer
matches its library fails DRC with `lib_footprint_mismatch`. Fab, 2026-09-14,
after trying it: *"the copy it opened still had SDA/SCL pads grouped, i could not
move them separately"*. As their own parts they drag with a plain click, and the
schematic, netlist and verifier all name them. Nothing moved when they were
split: J108 and J109 sit exactly where J107's pads 3 and 4 were, with the same
silk offsets, so DRC is unchanged at the accepted 12/0/0/0 baseline. Each land
carries a courtyard the size of its own pad — 1.6 x 1.2 mm and no larger,
because at pad-plus-0.15 the SDA land's courtyard collides with RH1's (RH1 is
0.725 mm from that land's centre), and a footprint with no courtyard at all is a
`missing_courtyard` **error**.

Y 61.5 is not a preference either: **Y 55..62 is the only band on this board with
zero B.Cu copper.** The region under the MCU, where these nets actually live, has
200+ segments in 6 mm and cannot take a 16 mm pad row.

**Silkscreen, added 2026-09-13** after Fab reported the pads as missing. They
were not missing — they were **unmarked**: the footprint carried no B.SilkS at
all, with Reference and Value both hidden on B.Fab, which is not fabricated. Six
anonymous copper rectangles on the back of the board, with nothing saying which
one is SDA, read as absent and could not have been soldered to. Now on B.SilkS:

    3V3   GND   TX   RX                    (at Y 59.75, each above its own pad)
    J107 EXT SENSOR / UART                 (at Y 58.20)
    a filled pin-1 dot                     (at X 101.90)
    SDA                                    (at (104.10, 124.55), beside J108)
    SCL                                    (at (118.60, 101.95), beside J109)

0.8 mm / 0.12 mm, the board's minimum text height and thickness — 0.55/0.09 was
tried first and DRC rejected it.

**All six lands are connected.** GND sits in `GND_PLANE_BCu`; the rest are routed:

| net | length | vias |
|---|---|---|
| `/3V3D` | 16.2 mm | 1 |
| `/I2C_SDA` | 5.3 mm | 2 |
| `/I2C_SCL` | 7.5 mm | 1 |
| `/UART2_TX` | 22.9 mm | 1 |
| `/UART2_RX` | 25.5 mm | 3 |

(The I2C rows are after the 2026-09-14 relocation. Routed from the row they cost
47.6 mm / 2 vias and 60.0 mm / 3 vias, and ran at the board minimum past the
guard and the ADC reference.)

Routed by [`tools/`](../../tools/README-router.md), not by hand — two hand
attempts had already failed, one with seven shorts.

**Why the row could not keep the I2C: one corridor.** The band under the MCU
(Y 86..95) has exactly **one**: whichever I2C net routes first takes it, and the
second is then fenced off its own target by 2.84 mm near (116.10, 93.90).
Rip-up-and-retry found no alternative corridor at all. That is what pushed the
first routing to 47.6 and 60.0 mm hugging the analog nets, and it is why the
answer in the end was to move the pads rather than to keep re-routing. The four
remaining row pads are unaffected: 3V3D, GND, TX and RX come nowhere near a
sensitive net (nearest approach > 0.8 mm).

### J108 placed by hand, 2026-09-14 — the two I2C lands are adjacent after all

Fab moved J108 himself once it was its own part: **(104.10, 125.95) →
(118.82, 101.97)**, which puts it **1.97 mm** from J109. That is the adjacency he
asked for on 2026-09-14 (*"move sda and scl pads next to each other. and not on
the tip please"*) and could not have while both lands were pads of J107. He
routed it too: **5.32 mm of new track and 2 vias**, plus two `/3V3D` segments
nudged aside to clear the run.

Measured on the result, not assumed:

| quantity | value |
|---|---|
| J108 land → nearest sensitive net | 0.545 mm (`/CE_MON`) |
| J109 land → nearest sensitive net | 1.657 mm (`/CE_MON`) |
| new SDA copper → nearest sensitive net | **0.235 mm** (`/CE_MON`, B.Cu, at (117.09, 103.01)) |
| length of that approach | ~0.6 mm — a corner graze, not a parallel run |
| GND pour | no orphaned island on either layer |

**State the cost, since this is the number the whole relocation was about.** At
the tip site J108's land stood 1.551 mm off the nearest analog net and needed no
track at all. Here the land is at 0.545 mm and its route grazes `/CE_MON` at
0.235 mm. Both are legal — the rule is 0.100 mm — and both are far better than
the 0.100 mm the original J107 route ran at for ~9 mm. But 0.235 mm is below the
0.50 mm `SENS_EXTRA` margin `tools/reroute_net.py` enforces on its own routes, so
this is a hand placement the router would not have produced. `/CE_MON` is a
91k/91k divider off `/CELL_CE_DRV` into U6 pin 15; the coupling is an ADC input
behind tens of k, and the approach is a corner, not a run.

The tip-site clearances are still on record in the table above and in
`docs/2026-09-14-revb-86-ring-dispositions.md` section 1, so the trade is
reversible: J108 is a footprint, and moving it back costs one drag and a
re-route.

### Addressing, for whatever gets soldered to these lands

The bus already carries U7 (LMP91000, 0x48), U10 (TMP117 CELL, ADD0 -> 3V3D, so
**0x49**) and U12 (SHT45-AD1F, 0x44). An external TMP117 must **not** strap ADD0
to GND — that is 0x48 and collides with the LMP91000. Use ADD0 -> SDA (0x4A) or
ADD0 -> SCL (0x4B). No ADD0 pad is provided: the strap belongs on the sensor's
own carrier. Do **not** add pull-ups on the lead; R10/R11 already bias this bus.
3.3 V logic only — PA2/PA3 are not 5 V tolerant.

Pads 5/6 duplicate the existing J105/J106 bench taps at (111.75, 97.8) and
(117, 97.8), which stay where they are. Retiring them was not asked for and was
not done.

## J105 / J106 — the UART bench taps are SMD lands now

Fab, 2026-09-14: *"replace the uart 2 pin headers with solder pads (smd)"*. Both
taps were `SolderWireNoRelief_*`: a 1.85 × 1.85 mm roundrect on **every** copper
layer over an **0.85 mm plated hole**. They are now the same 1.85 × 1.85 mm
roundrect as plain SMD lands on **back** copper only — same position, same net,
no drill:

    J105  /UART2_TX  (111.75, 97.80)   legend TX at (111.75, 96.10)
    J106  /UART2_RX  (117.00, 97.80)   legend RX at (117.00, 96.10)

Back copper is not a choice — both footprints were already placed on B.Cu, so
the back was the only face with an open mask. The front annulus was doing
nothing except holding a hole through the front ground pour, which has now
closed over it (F.Cu GND 972.58 → 982.18 mm²). The board drops from 215 to
**214 plated holes**.

**The legends are new.** These lands had no silkscreen at all — the same state
that made J107 read as *missing* on 2026-09-13. An unmarked copper rectangle on
the back of a board cannot be soldered to by anyone who does not already know
what it is.

**What this broke, and how it was fixed.** `/UART2_TX` reaches J105 on B.Cu and
was unaffected. `/UART2_RX` reached J106 on **F.Cu** and was using the pad's own
plated hole as its layer change, so with the hole gone its last stretch had to
move to the back: two accepted F.Cu segments deleted, 2.42 mm of new track and
one 0.4/0.2 via at **(117.40, 96.75)** — **0.125 mm clear of the land's edge**,
beside the joint and never in it. A route that stopped at the pad boundary put
the via *inside* the land; that was rejected, not accepted. Deleting accepted
copper is why `tools/smd_uart_taps.py` names those two segments explicitly:
`tools/reroute_net.py` refuses to rip copper that exists on the accepted board,
and it is right to.

    python3 tools/smd_uart_taps.py routing/revb-86-ring/o2-probe.kicad_pcb
    VIA_COST=40 python3 tools/reroute_net.py route <board> --net /UART2_RX \
        --rip 0,0,0,0 --reference routing/revb-86/o2-probe.kicad_pcb \
        --source 117.0,97.8 --target 117.4,94.4,119.6,96.6 --out rx.pkl
    python3 tools/reroute_net.py emit <board> --net /UART2_RX --pkl rx.pkl
    <kicad-python> tools/smd_uart_taps.py <board> --sync-library
    <kicad-python> tools/refill_zones.py <board>

The library copies are written **from the board** by `--sync-library`. A
hand-written `.kicad_mod` did not match what pcbnew holds — property angles, the
flip convention for a back-side part and the uuids are pcbnew's to decide — and
DRC said so with `lib_footprint_mismatch` on both taps.

The verifier pins this as a **wholesale footprint replacement**: not a field
edit but the complete new record, hashed, with named checks beside it for
position, angle, net, SMD-with-no-drill and back-copper-only, so a drift reads
as a sentence and not just a digest mismatch.

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

## J107's I2C lands moved off the analog front end — fixed 2026-09-14

As first routed, J107's SDA and SCL left the cable-end row and ran the length of
the AFE to reach the bus:

| J107 copper, as first routed | runs beside | gap | gap on accepted revb-86 |
|---|---|---|---|
| SCL, B.Cu X 101.1..101.2, Y 100..113.85 | `/GUARD_REPLICA` at X 101.5 | **0.100 mm** over ~9 mm | 0.625 mm |
| SDA, F.Cu X 118.35..118.95, Y 96.6..102.4 | `/VREF_TRIM` | **0.100 mm** over ~6 mm | not adjacent |

0.100 mm is the board minimum, so DRC was silent. A 100 kHz clock running
parallel to the working-electrode guard and to the ADC reference is an analog
defect that clearance rules do not catch.

**No reroute fixes it with the row's pads held fixed.** Flood-fill reachability
with every sensitive net inflated by only 0.1 mm beyond ordinary clearance,
ripping the entire J107 I2C route and allowing a join anywhere on the bus:

    /I2C_SCL  target reachable: False   closest approach 3.29 mm
    /I2C_SDA  target reachable: False   closest approach 3.02 mm

**That claim is true only of the row, and was once written as if it were
general.** A second independent review relocated individual pads and got a route
with 3.5 mm of clearance, which is what forced the question to Fab. His answer,
2026-09-14: *"i dont care where the pads are"*.

### Where they went, and why there

`tools/relocate_j107_i2c.py` moves pads 3 and 4 to the bus side of the AFE and
deletes the 90 segments and 5 vias that fed them; `tools/reroute_net.py` with
`SENS_EXTRA=0.3` routes the single new track.

| pad | from | to | new copper |
|---|---|---|---|
| 3 `/I2C_SDA` | (108.70, 61.50) | **(104.10, 125.95)** | none — the land sits on existing B.Cu SDA copper |
| 4 `/I2C_SCL` | (111.30, 61.50) | **(118.85, 100.00)** | 7.54 mm B.Cu + 1 via into U6 pin 45 |

107.68 mm of track and 5 vias out, 7.54 mm and 1 via in. The pour took the space
back: F.Cu GND 946.91 → 972.58 mm², B.Cu GND 828.88 → 875.17 mm².

Measured against every other net's copper on B.Cu:

| land | nearest copper of any net | nearest analog / ADC net |
|---|---|---|
| SDA (104.10, 125.95) | `/HEATER_PWM` 0.250 mm | `/CELL_CE` **1.551 mm** |
| SCL (118.85, 100.00) | `/AFE_MENB` 0.279 mm | `/CE_MON` **1.657 mm** |

15x on the quantity that mattered. What remains adjacent is digital:
`/HEATER_PWM` is the MCU's gate drive, `/AFE_MENB` the LMP91000 module-enable, a
static line (checked in the netlist, which is also why it is not in the sensitive
set).

The sites were not guessed. Candidate lands were screened on four measured
conditions — 0.25 mm from all copper, 1.00 mm from every analog/ADC net, inside
the outline and clear of the slots, clear of every back courtyard — and then
scored by a Dijkstra cost map of the *actual* routed length to the net, because
straight-line distance to the nearest copper is misleading here: the best
straight-line site for SCL, 3.9 mm from its bus, costs 22.9 mm of track once the
walls are taken into account.

### The sensitive-net set was too narrow

The reviewer's own counterexample put SCL 0.119 mm from `/CE_MON` and SDA
0.150 mm from `/3V3A`. `/CE_MON` is a 91k/91k tap off `/CELL_CE_DRV` into U6 pin
15; `/VA_MON` and `/VIN_MON` are the same shape; `/ADC_WE_BUF`, `/ADC_RE_BUF`,
`/ADC_AFE_VOUT` are the buffered cell measurements. All are ADC inputs behind
tens of k of source impedance, and none was in `reroute_net.SENSITIVE`. They are
now, and every number above is measured against the widened set.

### What it costs

**J107 is no longer one block.** 3V3D, GND and the UART pair stay in the row at
the cable end; the I2C lands are 64.5 mm and 38.5 mm up the board and 21 mm from
each other. A lead for an external TMP117 lands power and signal in different
places inside the potting rather than leaving with the cable.

Forced, not chosen: a search of the whole board for a site holding a complete
four-land block (3V3D, GND, SDA, SCL as 1.6 x 1.2 lands, each 0.30 mm from all
copper and 2.00 mm from every analog net, inside the outline, clear of the slots
and of every back courtyard) found **zero** sites at any pitch or orientation. A
three-land group exists only at X 116.4, Y 120.5..125.7, which still splits the
lead. The board is 20 x 86 mm and the AFE spans its width.

Both lands carry `SDA` / `SCL` legends on B.SilkS where they are, and J107's
Design Note says it in the schematic. DRC after the move is unchanged from the
accepted baseline: 12 warnings, 0 errors, 0 unconnected, 0 parity.

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
