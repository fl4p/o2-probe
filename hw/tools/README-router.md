# Grid maze-router for the o2-probe board

Written 2026-09-13 to route J107's five nets, after hand-placed segments failed
twice (32 DRC violations including seven shorts on the first attempt).

    board.py         parse a .kicad_pcb into segments, vias, pads, holes, edges
    route.py         rasterise obstacles onto a 0.05 mm grid; Dijkstra over two layers
    drive.py         route J107's nets in order, each new track blocking the next
    emit.py          write the result back as (segment ...) and (via ...)
    drive_tip_i2c.py re-route the tip ends of I2C_SCL / I2C_SDA (and a GND link)
                     so no B.Cu runs along the front band of HEATED_ISLAND_SPREADER
    emit_tip.py      write drive_tip_i2c.py's routes back, landing both ends on copper

Run `drive.py` then `emit.py`, then refill zones and run DRC. `VIA_COST` (in grid
units, 0.05 mm each) trades vias against length; 90 was used for the committed
J107 route.

The tip re-route, as committed (after stripping the old runs, see
`routing/revb-86-ring/README.md`):

    ORDER=scl,sda F_LIMIT_SCL=137.0 python3 drive_tip_i2c.py board.kicad_pcb
    python3 emit_tip.py /tmp/tip_i2c.pkl board.kicad_pcb
    ORDER=gnd python3 drive_tip_i2c.py board.kicad_pcb    # on the board with the I2C routes
    python3 emit_tip.py /tmp/tip_i2c.pkl board.kicad_pcb

The pickle is only ever this pipeline's own output, written locally one step
earlier; never feed it anything else.

## What it gets right, and why each mattered here

- **The board's own rules, not assumed ones.** Default netclass: 0.15 mm track,
  0.4/0.2 via, 0.1 mm clearance. A first run at 0.25 mm track and 0.6 mm vias
  declared the I2C pair unroutable; at the real widths both route.
- **A separate via-clearance grid.** A layer change needs the *via's* radius and
  hole-to-hole spacing, not the track's half-width. Without it, 30 of 43
  violations were my own vias.
- **Filled zones are not obstacles** — they are refilled afterwards and back off
  on their own. Keepouts and board edge are obstacles.
- **Snapping onto existing copper.** A route ending one 0.05 mm cell away from
  the track it joins reads as `track_not_centered_on_via`.
- **Keepout rule areas** (`drive_tip_i2c.py`). `board.py` does not read zones;
  the first tip run put SCL through U12's footprint no-track keepout and DRC
  reported `items_not_allowed`. Board- and footprint-level zones with
  `(tracks not_allowed)` are now filled and inflated onto the grid.
- **Component-aware targets** (`drive_tip_i2c.py`). Once a net is cut in pieces,
  "any same-net copper" lets the search stop on the piece it started from. The
  target is every labelled copper component except the source pad's own.
- **Starting on the pad, clamping into it** (`emit_tip.py`). Start cells lie on
  the pad copper, not in a radius around it, and the first point is clamped
  0.05 mm inside the pad rather than moved to its centre — U12's keepout cutout
  covers only the pad's inner end, so a centre stub crossed the keepout.
- **Edge arcs as true circles** (`route.py`). Two chords through the mid point
  under-blocked the thermal-slot apex and a route sat inside the 0.3 mm
  copper-edge clearance (`copper_edge_clearance` x4 at (101.2, 134.6)). Arcs are
  now sampled from the circle through start/mid/end at 0.05 mm steps.

## Known limits

- Track arcs are not parsed; this board has none in the routed region.
- No rip-up-and-retry: nets are routed in order and an early net can block a
  later one. `pair.py`-style retry was tried for the I2C pair and found there is
  only one corridor through Y 86..95 — the fix was to widen the search region to
  the whole board so SCL could reach its net further south, not to retry. At the
  tip, routing SDA before SCL left SCL with no path; the order is a parameter.
- **The router does not see zone fills**, so it cannot know a new track walls off
  part of a pour. The tip SCL leg did exactly that to a GND F.Cu pocket, and only
  DRC's unconnected item showed it. Refill with pcbnew and check islands after
  every emit; the fill is the arbiter, not any rule encoded here.
- Obstacles are rasterised, so clearances are respected to within half a cell.
  DRC is the arbiter; it has always been run after emitting.
