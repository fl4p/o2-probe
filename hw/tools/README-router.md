# Grid maze-router for the o2-probe board

Written 2026-09-13 to route J107's five nets, after hand-placed segments failed
twice (32 DRC violations including seven shorts on the first attempt).

    board.py   parse a .kicad_pcb into segments, vias, pads, holes, edges
    route.py   rasterise obstacles onto a 0.05 mm grid; Dijkstra over two layers
    drive.py   route J107's nets in order, each new track blocking the next
    emit.py    write the result back as (segment ...) and (via ...)

Run `drive.py` then `emit.py`, then refill zones and run DRC. `VIA_COST` (in grid
units, 0.05 mm each) trades vias against length; 90 was used for the committed
route.

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

## Known limits

- Track arcs are not parsed; this board has none in the routed region.
- No rip-up-and-retry: nets are routed in order and an early net can block a
  later one. `pair.py`-style retry was tried for the I2C pair and found there is
  only one corridor through Y 86..95 — the fix was to widen the search region to
  the whole board so SCL could reach its net further south, not to retry.
- Obstacles are rasterised, so clearances are respected to within half a cell.
  DRC is the arbiter; it has always been run after emitting.
