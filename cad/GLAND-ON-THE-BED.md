# Getting the face gland onto the build plate

**Question.** The retainer's sealing face should be a bed surface, not a top
surface. Printed that way (`face_groove_up = false`) the O-ring groove becomes a
void open to the plate and its roof bridges, which failed on the machine
2026-09-05. Can the groove move somewhere that prints without a bridge?

**Verdict: the option I proposed -- move the groove into the carrier -- does not
work, for a reason that also kills every variant of "put it in the other part".**
The two-piece retainer is the one that survives.

## Status: RECORDED VARIANT, NOT BUILT

Decided 2026-09-05: **we stay with the single-piece retainer already printed.**
The two-piece split below (option A) is written down as a variant so it can be
picked up later without re-deriving it; it is not implemented, and no parameter
in the model selects it. Nothing in `cad/` builds a gland ring or a cap plate.

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
groove is the only void beneath, so the bridge *is* the groove roof. The area
agrees independently: the annulus is 212.8 mm2, which at the 0.4 mm bridge line
width is 532 mm of path before anchoring overlap.

**The span is not the groove's width.** The slicer fills a bridge region with
straight parallel lines, and straight lines across a ring are chords. The longest
chord that stays inside this annulus is

    2 * sqrt(12.05^2 - 8.8^2) = 16.47 mm

against a groove only 3.25 mm wide radially. `bridge_angle` cannot help: the ring
is symmetric, so every angle yields the same worst chord.

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

### A. Two-piece retainer (recommended)

Split the retainer at the groove roof plane, z = 2.00:

- **Gland ring**, 2.00 mm thick. The groove stops being a pocket and becomes a
  *through* annular slot -- there is no roof, so nothing bridges. Its bed face is
  the sealing face, at bed quality.
- **Cap plate**, 2.04 mm thick, plain. Printed flat, its own bed face becomes the
  groove roof once stacked.

Both pieces print with zero bridges, and the surface that sets squeeze -- the
roof -- is upgraded from a 16 mm bridge to a build-plate surface. The six M2
clamp screws already pass through the full stack, so no new fastener is needed.

The honest cost is a new error term: the gland-ring/cap-plate interface. Squeeze
becomes (gland ring thickness + interface gap) instead of a printed depth. Both
mating faces are bed surfaces under six screws, which is the best flat-on-flat
contact the process offers, but the gap is not zero and is not currently
modelled. **Unmeasured -- this is the number to check before committing.**

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
  the roof is a dimension, not a surface: it sets squeeze. The usable face-seal
  band is 20-30% of the cord, which on the ~2.48 mm fitted cord is 0.248 mm of
  total travel, and `face_squeeze_target = 0.25` puts us mid-band. That leaves
  roughly +0.10 / -0.15 mm of roof error before the seal is out of band, which is
  the same order as support interface texture whether it is fused or gapped. It
  would print, look fine, and leak unpredictably. Removal is also a continuous
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

**The carrier and retainer now on the bench were printed from the 38.70 exports**
and are self-consistent with each other at that diameter, so they are fine to
keep and to assemble. What is NOT safe is printing one new part against them: a
fresh build gives 37.70 and would not match the pair in hand.

The working tree was left at the committed 38.70 exports on purpose, so the repo
keeps describing the hardware that exists. Before the next print of either part,
resolve this deliberately: find which parameter moved, decide whether 37.70 is
correct, and if it is, reprint the pair rather than mixing diameters. Do not just
run `make head-end-asa` and slice.

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
