# Getting the face gland onto the build plate

**Question.** The retainer's sealing face should be a bed surface, not a top
surface. Printed that way (`face_groove_up = false`) the O-ring groove becomes a
void open to the plate and its roof bridges, which failed on the machine
2026-09-05. Can the groove move somewhere that prints without a bridge?

**Update 2026-09-06:** before conceding the bridge, the one lever never tried on it
-- `bridge_speed` 50 -> 25 -- has been sliced. See *The one untried lever*. The rest
of this document stands: it says where the bridge is and why moving it does not work,
and none of that is affected by whether 25 mm/s prints it cleanly.

**Verdict: the option I proposed -- move the groove into the carrier -- does not
work, for a reason that also kills every variant of "put it in the other part".**
The two-piece retainer looked like the survivor and does not survive either --
see option A, retracted. What is left is a self-supporting gland, machining the
groove after printing, or accepting a top-surface sealing face (groove-up).

## Status: RECORDED VARIANT, NOT BUILT

Decided 2026-09-05: **we stay with the single-piece retainer already printed.**
Option A below (the two-piece split) was written here as the recommended variant
and has since been **retracted** -- it does not work as described. Nothing in
`cad/` builds a gland ring or a cap plate, and no parameter selects one. It is
kept, struck through, because the reason it fails is worth not rediscovering.

`face_groove_up` stays `false`. If the variant is ever built, the entry points
are `clamped_bed_cuts()` in `membrane_cartridge_common.scad` (the groove would
become a through slot) and `retainer()` / `retainer_printed()` in
`o2_probe_head_end.scad` (which would split into two parts and two plates).

Also left undone deliberately: the stale `enable_support` reason in
`tools/seal_check.sh` (see below). That file had another session's uncommitted
edits at the time, so it was not touched.

## The measurement that started it

Groove-down, sliced 2026-09-05 from `exports/asa-retainer-print.stl`:

| | |
|---|---|
| `Bridge` extrusions, layer 17 | 549 |
| Bridged path length | 735 mm |
| Spans over 8 mm | 12 |
| Longest emitted move | 20.16 mm |

Layer 17 spans z 2.00 -> 2.12, and the groove cut runs from the underside up to
`face_seat_depth + face_groove_depth = 0.24 + 1.76 = 2.00`. At that height the
groove is the only void beneath, so the bridge *is* the groove roof -- that alone
identifies it, from the feature tag and the layer height.

A second number was offered here as independent corroboration and is **not** one.
The annulus is 212.882 mm2, which at the 0.4 mm bridge line width is 532.2 mm of
ideal path; the file actually contains 734.77 mm. That is **38.1% longer**.
Anchoring and boundary paths plausibly account for it, but until the overlap is
computed this is qualitative consistency, not a measurement that agrees.

**The span is not the groove's width.** The slicer fills a bridge region with
straight parallel lines, and straight lines across a ring are chords. The longest
chord that stays inside this annulus is

    2 * sqrt(12.05^2 - 8.8^2) = 16.47 mm

against a groove only 3.25 mm wide radially. `bridge_angle` cannot help: the ring
is symmetric, so every angle yields the same worst chord.

## The one untried lever: bridge speed 25 (sliced and PRINTED 2026-09-06, not yet measured)

Everything above says *where* the bridge is, not that it must fail. The groove-down
flip failed once, at the shared `bridge_speed` of 50 mm/s, and that was never varied.
Halving it doubles the time each unsupported strand has to freeze before the next one
pulls sideways on it, which is the mechanism that curls a bridge over a narrow void.

Applied per part in `print.sh` (`part_process_overrides`), not in
`process_asa_seal.json`: nothing else on this printer bridges over a *seal* surface,
and slowing the monobody's structural bridges would add hours to a 1119-layer tower
for nothing.

Verified in the emitted `print/retainer/plate_1.gcode`, not in the profile we passed
in -- the profile is the request, the gcode is the answer:

| | groove-down @ 50 | groove-down @ 25 |
|---|---|---|
| Bridge feature at | z 2.12 | z 2.12 |
| Bridge extrusions | 549 | 553 |
| Bridged path | 735 mm | 733.79 mm |
| Longest bridged move | 20.16 mm | 20.16 mm |
| Feedrate on those paths | 50 mm/s | **25 mm/s** (533 of 553 moves) |
| Model print time | -- | 13 m 23 s |

The geometry is byte-for-byte the same problem; only the feedrate moved. The 20 moves
that are *not* 25 mm/s are all **slower** (10-19 mm/s, Orca's short-segment
deceleration) bar two anchor moves at 30 -- so no bridged path runs faster than asked.

Two side effects worth knowing before reading a result:

- **`internal_bridge_speed` is `150%`, i.e. relative.** The internal bridge at z 3.56
  (over sparse infill, 294 moves) therefore fell from 75 to 37.5 mm/s as well. That is
  not a seal surface and the change is harmless, but it means this plate is not a
  single-variable experiment in the strict sense.
- **The fan on the bridge is 35%, not 100%.** `M106 S89` there is
  `overhang_fan_speed = 35`, which a bridge path takes unconditionally. On any other
  material the first thing you would do to a sagging bridge is blast it; ASA is
  capped at 35 on purpose (warping, layer adhesion) and that cap was itself only just
  restored after a bad profile rebuild. **Fan is the second lever, and it is not on
  this plate** -- changing two things at once and getting a good print tells you
  which of them worked: neither.

`bridge_flow` stays at 1 for the same reason.

### It printed, 2026-09-06 -- which is not the same as the bridge being good

Ran 33/33 layers, `FINISH`, `print_error 0`, **`no active HMS` for the whole job**.
Layer 17 went down at 12:01:33; the part stayed on the plate and there was no
spaghetti out of the empty middle, which is what killed the first groove-down
attempt.

**That settles adhesion and it settles nothing about the seal.** A bridge that sagged
is still a bridge that printed. The chamber camera cannot resolve 0.1 mm on a 0.245 mm
window, and the finished top face is 4.04 mm above a roof nobody has looked at. The
part has to come off and be gauged -- see *How the verdict gets made* below, which was
written before this print and is unchanged by it.

Two aborts preceded it, and what fixed them was not in the slicer: a strand on the
nozzle tip and the plate seating. Both attempts reached stage 14 identically and then
diverged at stage 1 -- abort on 2026-09-06 09:38, pass at 11:49. `stg_cur` at the
abort was the diagnostic, exactly as `doc/levelling-faults.md` says; the HMS text was
not. Neither latched code was the cause: `0300_0100_0003_0008` was the bed clamping
105 to 100, and `0300_0B00_0001_0004` is the nozzle-cleaning entry that
`doc/telemetry.md` records appearing on successful runs too.


**How the verdict gets made, and it is not by looking at it.** The whole squeeze
window is 0.245 mm wide (see *Numbers used*). A roof that has sagged 0.1 mm looks
perfect and has eaten 40% of the window. Measure the groove depth with a depth gauge
against the bed face, at several angles round the ring, and compare to
`face_groove_depth = 1.76`. Groove depth has never been measured on a printed part in
any orientation -- so this print also produces the first such number for the
groove-**up** parts already on the bench, if the same gauge is used on both.

**This plate does not mate with the parts on the bench.** It is sliced from the
committed `exports/asa-retainer-print.stl`, which is the Ø38.70 bolt circle -- see
*OPEN: the committed STLs do not match the committed sources*. That is deliberate:
the bench carrier is also Ø38.70, so this retainer can actually be bolted up and
squeeze-checked. A retainer rebuilt from today's sources would be Ø37.70 and fit
nothing that exists.

## Why the groove cannot move to the carrier

`carrier_printed()` mirrors the part:

```
// Flange DOWN: as modelled the flange overhangs the spigot, which is a
// 90-degree overhang all the way round.
module carrier_printed() {
    translate([0, 0, spigot_len + flange_t]) mirror([0, 0, 1]) carrier();
}
```

The carrier's wet face -- the flange face that meets the membrane -- is at +Z in
the model and therefore **goes down onto the plate**. A groove cut into it would
be a void open to the bed with a bridged roof: the identical failure, moved to a
different part. And the carrier cannot print the other way up, because the flange
(Ø37.70) overhangs the spigot (Ø25.80) by 5.95 mm all round, a 90-degree overhang
that would need support under the whole annulus.

Generalising, the stack has four candidate faces and only one of them prints
upward:

| face | prints | groove there |
|---|---|---|
| carrier flange, membrane side | **down** (bed) | bridges -- same failure |
| carrier flange, head side | up | wrong side of the membrane |
| retainer underside, membrane side | **down** (bed) | bridges -- today's failure |
| retainer top | up | this *is* `face_groove_up = true` |

So "hide the groove in the other part" has nowhere to go. Both sealing faces of
the joint are bed faces by necessity, and a groove in a bed face is a bridge.

## What actually survives

### A. Two-piece retainer -- DOES NOT WORK AS DESCRIBED

**Retracted 2026-09-05, after an independent review.** It was written here as the
recommended option; the geometry does not support it, and the error was mine.

The proposal was to split the retainer at the groove roof plane z = 2.00 into a
2.00 mm **gland ring** whose groove becomes a *through* annular slot (no roof, so
nothing bridges) and a plain 2.04 mm **cap plate** whose own bed face becomes the
roof once stacked. Zero bridges in either piece, and the surface that sets
squeeze upgraded from a 16 mm bridge to a build-plate surface.

**Why it fails.** Making the groove a through slot cuts the Ø15.2-17.6 inner wall
free of the outer gland ring -- the annular slot has the window bore inside it and
nothing joining across. It is not two bodies, it is at least three. Worse, the
Ø26.5 membrane-seat cut removes everything under that inner ring for the first
0.24 mm, so it does not even start on the plate: it begins as an unsupported
island. The six screws sit outside it and give it no registration. See
`clamped_bed_cuts()` in `membrane_cartridge_common.scad:645`.

A three-piece version -- inner ring, outer gland ring, cap plate -- could be
drawn, but it adds a second uncontrolled interface rather than the one this
option was costed for, and the inner ring would need registration invented for
it. That is a different design, not this one.

The interface gap named below was therefore never the only new error term:

> Squeeze becomes (gland ring thickness + interface gap) instead of a printed
> depth. Both mating faces are bed surfaces under six screws, which is the best
> flat-on-flat contact the process offers, but the gap is not zero and is not
> currently modelled. **Unmeasured.**

### B. Self-supporting gland

A 45-degree trapezoidal groove closes its own roof. For the 2.5 mm cord at the
85% hydraulic-lock ceiling the section has to be about 4.8 x 2.4 mm against
today's 3.25 x 1.76. That grows the retainer and changes how the ring seats; a
vee gland is a different seal, not the same seal printed differently.

### C. Print flat, cut the groove afterwards

The retainer is round in section, Ø37.70. A single lathe pass gives a better
gland than any printer will, and the bed face stays untouched. Depends entirely
on having the machine.

## Rejected, with reasons

- **Brim across the groove.** A brim is one layer, ~0.2 mm, on the plate. The
  roof is 2.00 mm up. `brim_type: inner_and_outer` really would put a ring inside
  the groove's layer-1 outline, and it would stop 1.8 mm short.
- **Support inside the groove.** Uniquely available here, because the void is
  open to the plate -- `support_on_build_plate_only` would reach the roof. But
  the roof is a dimension, not a surface: it sets squeeze. The model asserts a
  20-30% face-seal band. Ø17.6 over Ø17.0 is 3.5294% install stretch, so the
  source's own thinning equation gives a fitted cord of
  `2.5 x (1 - 0.035294/2) = 2.45588` mm -- **not** the ~2.48 an earlier version of
  this file used -- and the ten-point band is 0.24559 mm of total travel. Against
  the nominal 1.82 mm gap that permits about **+0.1447 mm deeper / -0.1009 mm
  shallower**. (An earlier version said +0.10 / -0.15, which is both wrong and
  has the asymmetry the wrong way round; the same reversal is in the comment at
  `o2_probe_head_end.scad:2278` and has not been corrected there yet.) Fold in the
  sorted-cord, ring-ID and membrane tolerances the model already carries and the
  real requirement is tighter still: **+0.09395 / -0.05291 mm**. So the
  conclusion is not merely unchanged, it is stronger -- support interface texture,
  fused or gapped, is the same order as the whole remaining allowance. It would
  print, look fine, and leak unpredictably. Removal is also a continuous
  3.25 x 2.0 mm annular slot, not a set of pockets.

## A guard that went stale

`tools/seal_check.sh`:

```
eq enable_support 0 "no feature on this part overhangs; support inside a sealing bore is scrap"
```

The first clause stopped being true when the part flipped -- the groove roof
overhangs now. The conclusion is still right and still binds, but the stated
reason no longer matches the part, which is the same shape of defect as the
filament profile that passed every check while being for the wrong material.
Reword it against the seal argument above rather than against "nothing
overhangs".

## OPEN: the committed STLs do not match the committed sources

Found 2026-09-05 while rebuilding. Same ring (`onhand-22x2`, spigot Ø25.80 in
both), same triangle count, but the flange differs by a whole millimetre:

| | committed `exports/asa-*.stl` | fresh build from committed sources |
|---|---|---|
| flange dia | **38.70 mm** | **37.70 mm** |
| spigot dia | 25.80 | 25.80 |
| retainer height | 4.04 | 4.04 |

`exports/asa-PROVENANCE` says `radial onhand-22x2` in both, so the provenance
file recorded the intent and not the build -- it cannot distinguish these two.

**The moved parameter is now identified** (independent review, 2026-09-05):
it is the M2.5 -> M2 fastener change in commit `9935a7c`. Rendering the *current*
source with the old fastener set -- `pt_nominal=2.5`, `pt_pilot_d=2.1`,
`m2_clear=2.8` -- reproduces the committed retainer exactly: **bolt radius 15.55,
flange Ø38.70**. The current M2 set (1.60 pilot, 2.40 clearance) gives **bolt
radius 15.25, flange Ø37.70**. So the bolt circle moved inward **0.30 mm**, and
against M2's 0.40 mm of total clearance slop that is most of the budget. The
transition was never committed as a source revision -- the stale STL was
committed after the source had already moved -- so git cannot reconstruct it.

**The carrier and retainer now on the bench were printed from the 38.70 exports**
and are self-consistent with each other at that diameter, so they are fine to
keep and to assemble. What is NOT safe is printing one new part against them: a
fresh build gives 37.70 and would not match the pair in hand.

The working tree was left at the committed 38.70 exports on purpose, so the repo
keeps describing the hardware that exists. Before the next print of either part,
resolve this deliberately: the M2 geometry is presumably the wanted one, so the
honest fix is to reprint the carrier and retainer together rather than mix a
15.25 bolt circle against a 15.55 one. Do not just run `make head-end-asa` and
slice.

## Numbers used

| | |
|---|---|
| `flange_d` (retainer OD) | 37.70 mm |
| `retainer_t` | 4.04 mm |
| carrier | spigot Ø25.80 x 5.30, flange Ø37.70 x 3.00, total 8.30 |
| `window_d` | 15.2 mm |
| groove ID / OD / width | 17.6 / 24.1 / 3.25 mm |
| groove depth / seat depth | 1.76 / 0.24 mm |
| groove roof plane | z = 2.00 mm |
| `face_squeeze_target` | 0.25 |

Retainer and carrier dimensions read from `exports/asa-*.stl`; groove and bridge
figures from the emitted `print/retainer/plate_1.gcode`.

## Not verified

- The gland-ring/cap-plate interface gap in option A. Everything else about that
  option follows from geometry; this one needs a printed pair and a micrometer.
- Whether the membrane seat stays in the gland ring or moves to the carrier. The
  seat is a 0.24 mm recess Ø26.5 on the bed face, so it also bridges -- shallowly,
  over a 1.2 mm ledge, in a place that locates the disc rather than sealing. It
  needs its own decision, not an assumption.
- Groove depth has never been measured on a printed part in any orientation.
