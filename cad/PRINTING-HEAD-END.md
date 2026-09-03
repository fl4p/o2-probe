# Printing the end-window head — ASA, 2026-09-03

Build file: `exports/head-end-plate.3mf` (all four parts, print-oriented, one file).

    make head-end-provisional

regenerates it along with the per-part STLs and re-runs every gate. Gates green at
the time of writing: both fastening routes render as closed solids, cavity mesh
**4849.2 mm³** against the 5.0 cm³ budget (3.0 % margin).

## What is on the plate

| part | volume | bbox | orientation | support |
|---|---|---|---|---|
| head | 28.4 cm³ | Ø42 × 33.6 | as modelled, well up | none |
| carrier | 5.6 cm³ | Ø39.1 × 9.6 | **flipped, flange down** | none |
| retainer | 2.9 cm³ | Ø39.1 × 3.0 | flat | none |
| cap | 17.6 cm³ | Ø47 × 32.5 | **flipped, nose down** | none |

≈ 54.5 cm³ of solid, so roughly **58 g** of ASA at 1.07 g/cm³ before infill relief.

Both flips exist for a reason and both are load-bearing:

- The **carrier** flange overhangs the spigot by a full 90° all the way round.
- The **cap**'s solid plowing face sits on top of the open cage band. Printed
  nose-up the slicer is asked to start a full Ø47 disc in mid-air on six 3 mm
  ribs — a ~39 mm island. Inverted, the nose is the first layer and the lower
  shell arrives last as a 3.45 mm annulus bridging rib to rib, anchored at both
  ends. Verified on the mesh: the plate's first layer in the cap quadrant is
  Ø39.00, the nose face, not the Ø47 rim.

The head needs no support as modelled — every diameter change going up is either
a shrink (a short annular bridge inward) or the well floor, which is solid
material. The two cap screw holes are Ø2.1 horizontal and self-bridge.

## Slicing — Bambu Lab P1P, 0.4 nozzle, Textured PEI

Profiles that actually apply (there is no `@BBL P1P` ASA profile; Bambu ships the
X1C one and marks P1P compatible):

- machine `Bambu Lab P1P 0.4 nozzle`
- process `0.20mm Strength @BBL P1P` — Strength, not Standard: the O-ring groove
  land and the six threaded bosses want the extra walls. Plus
  `curr_bed_type = Textured PEI Plate`, 5 mm outer brim.
- filament `Bambu ASA @BBL X1C 0.4 nozzle`, **flattened over its inherits chain**
  — see below.

Verified in the emitted gcode: `filament_type = ASA`, nozzle 270 °C, bed 100 °C,
`curr_bed_type = Textured PEI Plate`. **1 h 47 m, 40.67 cm³.**

Two traps, both caught by `~/dev/ee/zoe/enclosure/slice-check.sh` rather than by
reading the profile names:

1. **The CLI defaults to Cool Plate.** The fitted plate is Textured PEI and the
   P1P cannot detect it, so it has to be declared. ASA at a 100 °C bed on a plate
   sliced for Cool Plate is wrong in both directions.
2. **The CLI does not resolve a filament profile's `inherits` chain.** It loads
   only the leaf file's own keys, silently. The leaf sets the *specific* values
   and the parents hold the *general* ones, so the result is a hybrid that exists
   in no profile: nozzle 270 °C (ASA, from the leaf) over a bed at **45 °C**
   (PLA, defaulted) with `filament_type = PLA`. `filament_settings_id` in the
   header still names the ASA profile — the provenance is right while the values
   are wrong. Flatten the chain parent-first and pass one self-contained profile.
   Recorded in `~/dev/kb/3d-print/orcaslicer-cli-does-not-resolve-filament-inherits.md`.

- **Brim.** Three of the four parts are Ø39–47 flat discs. What warps first is
  the carrier flange and the retainer face, which are the two surfaces the seal
  stack clamps against.
- **This P1P is enclosed** (confirmed 2026-09-03), which is what makes ASA on
  Ø39–47 discs reasonable at all. A bare-frame P1P would warp them, and the first
  things to lift would be the carrier flange and the retainer face — the two
  surfaces the seal stack clamps against.
- **Do not** let the slicer put a seam or a gap-fill artefact inside the Ø27.3
  well or on the flange face. Those are sealing surfaces.

## Support: the answer is none, and here is the evidence

Support was enabled at the minimum useful setting — `normal(auto)`, build-plate
only, 30° threshold, 0.2 mm top gap — and the result sliced and analysed against
the plate layout. It costs +1.88 cm³ and +4 m 38 s, and this is where it goes:

| region | support moves | z | |
|---|---|---|---|
| head | 6283 | 0.20–15.80 | **inside the blind tube socket** |
| carrier | 420 | 0.20–0.80 | first layer under the bore |
| retainer | 10 | 0.20–3.00 | noise |
| cap | 5 | 14.80–15.80 | noise |

94 % of it is a **14 mm column packed inside the head's Ø32.4 blind tube socket**,
put there because the socket roof at z = 14 is a 90° annular ledge and the socket
floor is the build plate, so "build-plate only" does not exclude it. That socket
is a *bonding* surface — the tube glues into it across `bond_gap` — it is blind,
and you cannot reach in to clean it. Everything else support touches is 435 moves
of noise.

The ledge it wants to support is a 4.26 mm radial inward bridge. That is routine.

**So print with support off.** Both files are in `exports/` if you want to compare
in the slicer:

- `head-end-asa-pei.gcode.3mf` ← the one uploaded to the printer
- `head-end-asa-p1p-minsupport.gcode.3mf` (kept only to show what support does;
  sliced before the plate and filament were corrected, so do not print it)

They are gitignored: machine- and material-specific, several MB, regenerable from
the tracked plate.

## First printed part, measured 2026-09-03

Three diameters off the first ASA carrier, against the drawing:

| | drawn | measured | shrink |
|---|---|---|---|
| flange OD | 39.1000 | 38.870 (mean of 38.90, 38.84) | −0.588 % |
| spigot OD | 27.0000 | 26.830 (one reading) | −0.630 % |
| groove root | 25.0404 | 24.800 (one reading) | −0.960 % |

**Shrinkage is not one number.** The thin wall under the O-ring groove pulls
harder than the flange rim does, and the spread — 0.372 percentage points, or
0.093 mm on the root — is why a single XY scale in the slicer cannot fix this
part: the factor that corrects the root over-sizes the rim by the same stroke.
It also validates, and slightly exceeds, the ±0.15 mm estimate that Route 2
below used to rest on. That estimate is now a measurement.

The two errors do not cancel, they add, because **the well is bored to size and
therefore does not shrink while the carrier does**. Squeeze is (well − root)/2,
so all of the carrier's shrink lands on the seal:

| case | stretch | gland | squeeze |
|---|---|---|---|
| as drawn, bored well | 4.33 % | 1.1298 | 23.01 % |
| **measured root, bored well** | 3.33 % | 1.2500 | **15.25 %** |
| root at 24.75 (−0.05) | 3.12 % | 1.2750 | **13.65 % — out** |
| root at 24.85 (+0.05) | 3.54 % | 1.2250 | 16.86 % |
| measured root, **printed** well | 3.33 % | 1.1640 | 21.08 % |

Uncompensated, a printed carrier in a bored well sits at 15.25 % against a 15 %
floor, and the 0.1 mm of caliper resolution on that one reading is worth ±1.6
points on its own. **Mixing processes is what breaks the seal** — a printed
carrier in a *printed* well self-compensates and is nowhere near the floor.

Two caveats still stand. This is mostly the systematic **bias**, and only
scatter eats the tolerance budget: a known −0.96 % is just a bigger groove root.
And it is one part from one machine.

There is one direct scatter reading in here, and it is worth separating out: the
flange was measured **twice, at 38.90 and 38.84**, and 38.870 above is their
mean. A 0.06 mm spread on one diameter of one part is not a distribution, but it
is the only honest scatter number the design has, and it is comfortably inside
the 0.093 mm the three-feature bias spread covers. What is still unmeasured is
scatter *on the root*, which is the dimension that matters — hence the repeat
measurement asked for below.

### The compensation, and why only the root

`o2_probe_head_end.scad` compensates the groove root, and nothing else, when
`carrier_fab = "printed"`:

    carrier_shrink_root = 0.99040;      // 24.800 / 25.0404, measured
    groove_root_cut = groove_root_d / carrier_shrink_root;   // printed route only

Only the root moves the seal, so only the root is compensated. This is a
property of **this material on this machine**, not of the design, which is why
every seal calculation still uses the drawn `groove_root_d`: the compensated cut
is *expected to print* at the drawn value, and the machined drawing stays at
25.0404. Verified on the mesh rather than the echo — the groove root cut renders
at Ø25.0403 on the machined route and Ø25.2831 on the printed one, and both
routes report the same 22.65 % squeeze.

Compensating the root **up** makes the groove shallower, so the wall under it
gets *thicker*. My first assert had that backwards. The two real risks are at
the other end and are now gated: wall left over the bore, and a groove too
shallow to retain the ring.

Next measurement, in priority order: **the groove root again, at two or three
positions**, to catch ovality. The whole compensation rests on a single 0.1 mm
reading of the highest-leverage dimension on the part.

### Reprinting it: the wipe temperature is part of the file

The first attempt at this reprint aborted in stage 14 (cleaning nozzle tip). The
nozzle wipe runs at `nozzle_temperature_initial_layer − 20`, so a 270 °C initial
layer wipes at 250 — the viscous end of ASA's 240–280 range. Slice the reprint
at `nozzle_temperature_initial_layer = 280` so the wipe runs at 260. Confirmed in
the executable stream, not the header: `M109 S250 → M109 S260` on both wipe
lines, while the body still drops to 270 for every layer above the first, so no
measured feature prints hotter than the part these numbers came from.

That is not a substitute for cleaning the tip by hand after a material swap —
see `~/dev/ee/p1p/doc/levelling-faults.md`. A hotter wipe produces less new
residue; it does not remove residue that is already there.

Two CLI traps cost an hour reproducing this slice, both worth knowing before you
try:

- **A process preset loaded from outside the vendor tree must keep its
  `compatible_printers`.** Drop it and the CLI prints exactly one line —
  `run found error, exit` — with nothing above it. This is the failure the
  `slicer-presets.md` advice ("the cause is the line above") does not cover,
  and it is what an earlier session here misattributed to `--arrange 0`.
  `--arrange 0` is a documented, valid option.
- **`--export-3mf` takes a bare filename, not a path.** An absolute path is
  concatenated onto `--outputdir`, giving `Project export to <outdir>/<abspath>
  failed`.

The preset was rebuilt from the previous slice's own resolved
`Metadata/project_settings.config` — 638 keys, no `inherits` left — and
validated the way `slicer-presets.md` prescribes: re-slicing reproduced the
source plate's time exactly, 25 m 7 s. `slice-check` then passed on the
**extracted** `plate_1.gcode`; handed the `.gcode.3mf` container it fails closed,
because it greps raw text and the container is a zip.

## Surface defects on that print

**Webbing across the bore.** Confirmed in the sliced G-code: two annular ledges
that cantilever inward over open holes, at z = 1.20 (Ø21.60 → Ø16.86, 431
overhang-wall moves) and z = 5.20 (Ø22.30 → Ø18.30, 385 moves plus internal
bridging). Inherent to printing flange-down. The z = 5.20 step is a plain bore
step and could be coned; the z = 1.20 one is the membrane sealing land and cannot.
**This carrier therefore cannot be used to judge the membrane seal.**

**Voids around the bolt holes.** Present on **every print so far, on both faces of
both parts**, four-fold symmetric around each hole, and scaling with line width.
Re-verified by eye 2026-09-03 after four prints.

That description is a correction. The first report was "carrier upper face only,
rim both faces", and two hypotheses were built on that asymmetry before a closer
look found small voids on the bed side of everything. The bed side was never
clean — squish shrinks the defect, it does not close it — so the top/bottom
difference is one of SIZE, not presence, and any explanation that needs a
top-surface mechanism is explaining something that is not happening.

Four hypotheses died, and each cost a plate except the last:

- *Six perimeters will not fit the 2.0 mm rim.* Arithmetic right, conclusion
  wrong: rim fill measures 100 % at wall_loops 6, 98 % at 3, 82 % at 2, because
  dropping perimeters hands the middle to sparse infill. Fewer walls is worse.
- *The top surface pattern.* `monotonicline` -> `concentric` moved top material
  -26.8 % on the carrier and +26.3 % on the retainer — opposite directions. And
  the reprint at `monotonic` voided anyway.
- *Narrow slivers go unfilled because thin-wall detection is off.* The slice emits
  **zero** gap infill with `detect_thin_wall` either off or on.
- *Under-extrusion.* `filament_flow_ratio` is 0.95 in the ASA profile, a
  deliberate 5 % under-extrusion documented in `~/dev/ee/p1p/doc/asa-and-the-mc-fan.md`.
  Raising it to 1.00 with the seal recipe cranked made the voids **worse**, not
  better, and turned the small bed-side voids into large ones.

### The mechanism: Arachne deposits nothing where it cannot redistribute

`wall_generator = arachne` builds **variable-width** perimeters and absorbs narrow
residual regions by widening neighbouring beads. Where it cannot, the region gets
no material and no gap infill is generated. Measured on this plate:

| `wall_generator` | gap-infill blocks | pair time |
|---|---|---|
| arachne (the profile default) | **0** | 49m 19s |
| classic | **603** | 54m 20s |

`min_bead_width` is not the knob: swept 85 % -> 50 % -> 25 % under arachne, gap
infill stays at 0. Line width is second-order (603 blocks at 0.65, 559 at 0.45).
**`wall_generator` is the only lever found that changes whether the residue is
filled at all.**

This accounts for every observation the four dead hypotheses could not: indifference
to wall count, top pattern and flow, all of which are downstream of bead
redistribution; worse at 0.65 than 0.45, because wider beads leave more residue;
perfect systematic repeatability, because it is deterministic geometry; four-fold
symmetry, from the medial axis of a round hole in a rim; and small-but-present on
the bed side of every print.

**Still a hypothesis, not a result.** What is measured is the slicer's output, not
a printed part. The test is the retainer at `wall_generator = classic` with every
other setting left at the values the existing retainer was printed with — one
variable, and a directly comparable part already in hand.

## What this print does and does not establish

**It is a fit and geometry check.** It establishes the bolt circle, the
flange/retainer stack height, the cap grip and cage, the socket over the tube,
and whether the carrier actually enters the well. That is worth having.

**It now DOES establish the seal, which is a change from what this file said an
hour ago.** The compensated carrier was cut at Ø25.2831 and measured Ø24.98 and
Ø25.00 at two angular positions — mean **24.99** against a 25.0404 target, a
−0.04 mm residual.

| | groove root | stretch | squeeze |
|---|---|---|---|
| drawn / machined target | 25.0404 | 4.33 % | 22.65 % |
| printed, uncompensated | 24.800 | 3.33 % | **14.90 % — out** |
| printed, **compensated** | **24.99** | 4.13 % | **21.02 %** |

Three things follow, and the third is the useful one.

**Ovality is not the threat.** 0.020 mm out of round, worth 0.65 squeeze points.
The between-part spread is 0.050 mm — **2.5× larger than the within-part ovality**
— so the uncertainty lives in the shrink factor, not the geometry. Another part
improves the estimate; another position on the same part does not.

**Under-compensation fails safe.** Too little correction leaves the root small,
the gland wide and the squeeze *high*. The −0.04 mm residual cost nothing.

**The printed-carrier tolerance is no longer a guess, and that re-opens the
route table.** ±0.15 mm was my own estimate with nothing behind it; three
readings normalised by the diameter each part was actually cut at give a
half-range of ±0.030 mm, doubled to **±0.06 mm** for a sample of two parts:

| well | carrier | rings | band | |
|---|---|---|---|---|
| reamed H7 | machined | catalogue | 2.66 / 15 | PASS (production route) |
| reamed H7 | printed | sorted | **5.84 / 15** | PASS (was 11.97) |
| reamed H7 | printed | **catalogue** | **13.09 / 15** | **PASS — was 19.24, a FAIL** |
| printed | printed | sorted | 24.88 / 15 | FAIL |

So **sorting rings with a micrometer may no longer be required** for a printed
prototype. Treat that with suspicion: 13.09 of 15 leaves 1.9 points of headroom
and rests entirely on the ±0.06 mm, which has two parts behind it. At ±0.10 the
catalogue route fails again. Sorted rings stay the prudent choice until more
carriers are measured — the point is that the *step is now inside the budget*,
not that it should be skipped today.

**The well still has to be bored to H7.** That has not changed and no
compensation touches it: the whole reason the root needs correcting is that the
well does *not* shrink with the carrier.

**The ASA carrier cannot carry the membrane.** The PMV15T disc is *welded* into
the production carrier, and the production carrier is machined PP-H for exactly
that reason. ASA is not weldable to PP. Treat the printed carrier as a fit model
of the seal geometry only.

## Still open, and unchanged by printing

- `cell_axial_len = 13.0` is a placeholder. The 3.0 % volume margin rides on it.
- **EPDM ammonia compatibility is unverified**, gating both the O-ring and the
  membrane gasket.
- The membrane gasket is unsourced — material, hardness, thickness, preload.
- The 6 + 2 screws are unsourced, with an unsourced pilot diameter.
