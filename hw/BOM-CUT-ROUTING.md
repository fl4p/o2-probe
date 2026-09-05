# Does the BOM/footprint reduction help routing?

Measured 2026-09-05 against `fc84cfa` (100 parts) and `451e04a` (113 parts), two
layers, gated on critical copper intact and zero shorts. All counts are
`GetUnconnectedCount(True)` **after** a zone refill.

## Short answer

On its own, no — it makes routing **worse**. What it buys is tolerance of a
router setting the old board could not survive, and the two together land at
roughly the old board's level, not beyond it.

## The 2x2

Four net orderings per cell (`default`, `mps`, `original`, `inside_out`):

| board | `KICAD_SEAM_REASK=1` (default) | `KICAD_SEAM_REASK=0` |
|---|---|---|
| 113-part (`451e04a`) | 21 / 21 / 24 / 26 | **999** / 999 / 26 / 33 |
| 100-part (`fc84cfa`) | 26 / 26 / 31 / 31 | 17 / 17 / 25 / 25 |

`999` is the gate: the seam-off runs on the old board produced a short and lost
authored guard copper. That is a failure, not a high score.

Read the table by column and by row:

- **The BOM cut alone costs 5 links**, consistently, in every ordering. The
  problem got 12.5% smaller (368 -> 323 pads, 273 -> 239 pads on routable nets,
  courtyard 1638.6 -> 1430.0 mm2) and the result got worse. Nothing was
  re-floorplanned into the freed area, so the deletions bought empty board
  rather than shorter routes.
- **The seam knob alone breaks the old board** and helps the new one by 9.
- **Together: 17 best, 25 worst-of-four**, against the old board's 21 best and
  26 worst-of-four.

## Why 17 is not a win

The acceptance rule on this board is worst-of-four, because the ordering spread
is 5 links and single-ordering wins have been noise five times today. By that
rule the improvement is **25 vs 26 — one link**. The 17 is a best-of-four and
carries no more weight than the 18s and 20s already rejected.

The distributions do differ in shape: the new board's four orderings are
{17,17,25,25} against {21,21,24,26}. That is a bimodal split, not a shift, and
two of the four orderings are worse than the old board's worst.

## What the seam re-ask actually does, and what it does not

`#444 seam re-ask` re-routes a net whose tree exceeds its MST bound. On `/3V3A`
the log reads: `Retry SUCCESS (N=1): 6 -> 0 failed edges`, then
`tree is 2.10x its MST bound -- re-asking whole`, then
`tree replaced (185.2 -> 166.8 score)`.

That looks exactly like a length optimiser discarding a connectivity win, and
it is the mechanism this document originally claimed. **It is wrong.** With
`KICAD_SEAM_REASK=0`, `/3V3A` still ends with 6 disconnected pads. The knob is
worth 9 links on this board, but not through `/3V3A`, and the mechanism behind
the 9 is not established.

## /3V3A is the largest single target and a pour does not fix it

`/3V3A` is 9 pads spanning 45.6 mm: the LDO output at local y 35.0 (U3 pad 5,
C8) and six loads clustered in the AFE at y 74.5..80.7 (U4, U7, U8, R24, C18,
C16). It accounts for 6 of the best board's 17 remaining links.

A B-side `/3V3A` pour over the AFE (x 0.5..19.5, y 73.0..82.0, priority above
the ground plane) was authored and measured: **25 against 17**. The pour fills
107.6 mm2 and displaces B-side ground across the whole AFE, closing the only
B-side channel through that region. It costs more than the tree it saves.
Refuted.

## A measurement trap, again

The first run of the pour experiment returned four orderings **byte-identical**
to the run without it, while printing `authored 1 rail zone(s)`. `gen_pcb.py`
does `from critical_routes import ensure_gnd_plane`, which binds the function
into `gen_pcb`'s namespace at import time; patching `critical_routes`'s module
attribute changed a name nobody read. The zone was never on the board.

The reassuring log line came from the patch installer, not from the board. Only
counting zones in the saved file caught it. Anything that claims to change
generated geometry has to be verified **in the artefact**, not in the generator's
own output.

## Unrelated defect found while measuring

`J105`'s strain-relief NPTH lands inside `R41`'s courtyard:
`npth_inside_courtyard`, severity **error**, on the board `fc84cfa` generates.

`Connector_Wire:SolderWire-...-Relief` places its 2.20 mm relief hole 10.2 mm
from the solder pad. `J105`/`J106` were placed at y 57.5 to keep the USART2 runs
short; their relief holes therefore land at y 67.7 — within 0.7 mm of where
`J2`'s two 2.41 mm holes used to be. On two layers those are holes through both
layers, so the mid-board obstruction `J2`'s deletion was expected to remove is
substantially still there, and one of the two now collides with a courtyard.

Placing these is an assembly-interface decision (where a human solders a wire,
and clearance to the potting dam), so it is not mine to move.
