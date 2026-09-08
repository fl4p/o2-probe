# Printing the end-window head — ASA, 2026-09-03

> **STALE DIMENSIONS BELOW — 2026-09-03, later the same day.** The spigot wall was
> split out of `land` into its own `spigot_land`, shrinking the head from Ø42 to
> **Ø40** and the cap from Ø47 to **Ø45**. The groove root moved 25.0404 → **24.8404**
> and the flange 39.1 → **38.9**.
>
> Every *measurement* in this document stands — those are readings off parts that
> were actually printed, and the shrink factor derived from them is a ratio, so it
> transfers unchanged. What does **not** transfer is any absolute cut diameter:
> **do not cut Ø25.2831 for a new carrier.** Re-read the compensated root from the
> model's own echo before the next print, and re-measure this table's bboxes off a
> fresh `make head-end-provisional`.

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

### Mechanism, settled: colliding perimeter loops in a rim that cannot be tiled

Two independent mechanisms, which is why five single-cause hypotheses all died.

**Bed-side voids: Arachne left residue unfilled. FIXED.** `wall_generator = arachne`
builds variable-width perimeters and absorbs narrow residue by widening neighbours;
where it cannot, it deposits nothing and emits no gap infill. Measured on the pair:
arachne **0** gap-infill blocks, classic **603**. `min_bead_width` is not the knob
(85 % -> 50 % -> 25 % all give 0). Printing the retainer at classic made the bed face
**visibly void-free**. Kept.

**Remaining voids: loops from the hole colliding with loops from the flange OD.**
Photographed 2026-09-03: lens-shaped slits *between* adjacent perimeters, along the
arc where the two loop families meet — not at the holes. Visible because the rim is
entirely perimeters, so nothing covers them.

The rim holds 4.4 beads at 0.45 mm and is asked for 6 from each boundary, so the
collision is structural. Even 3 loops per side over-subscribes it.

**They stack, and that is the part that matters.** In the rim annulus, 4.988 mm² of
footprint is touched and **3.517 mm² — 70.5 % — is present on every layer.** These are
vertically continuous channels, not surface marks, because the cross-section is
identical on every layer so the collision locus never moves.

**No slicer setting unstacks them.** Measured:

| | stacked, all layers |
|---|---|
| baseline 0.45 / 6 loops | 3.517 mm² |
| `alternate_extra_wall = 1` | 3.547 — worse |
| `+ seam_position = random` | 3.519 — no change |
| line width 0.40 | **3.039 — −14 %** |
| line width 0.50 | 4.183 — worse |
| 0.50 + 2 loops | 9.701 — far worse |

Seam randomisation cannot help: the seam is not where the slivers are. And no bead
width tiles the rim, because the hole and the flange OD are **both curved** — the gap
is 2.00 mm at the closest point, 2.30 mm at 40° round the hole and 3.34 mm at 90°.
There is no single width to divide.

Two settings that read like gap-fill switches and are not: `detect_thin_wall` and
`filter_out_gap_fill` produce no gap infill at all under arachne. Count
`; FEATURE: Gap infill` blocks in the emitted G-code, never the settings.

### Decision, 2026-09-03: accepted as cosmetic, geometry unchanged

Judged cosmetic on the printed part. The retainer clamps; the sealing surfaces are
the flange face and the O-ring groove, both clean. **Recorded against that decision:
70 % of the slits are through-channels, and a channel in a clamping face around a
screw hole under preload is a crack initiator.** Accepted knowingly, not overlooked —
revisit if a retainer ever cracks at a boss.

The cause-level fix was priced and declined: flange 39.1 -> 40.1 gives a 2.50 mm
narrowest gap for 0.5 mm of head wall and no gas volume. **Geometry left alone.**

0.40 mm line width was also declined despite being a free −14 %, because process
changes invalidate the shrink calibration: the factor is recorded as valid at a
specific `wall_generator`, flow, layer height and line width, so every process
change costs a carrier print to recalibrate. Adopting classic already forced one.
Settled process: **`wall_generator = classic`, 0.45 mm, flow 0.95, 0.2 mm layers.**

Also retired: four of my own metrics misread this. Fill-fraction returned 117–138 %;
a top-14 listing hid 493 regions; a sliver-area map ranked arachne better than the
eye did; an extruded-volume comparison ran 35 % high by counting retraction recovery
as deposition. The slicer's own `; filament used [cm3]` header was the correct check
and was present in every slice. A photograph settled in one frame what none of them
could.

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

**The printed-carrier tolerance is no longer a guess — but the void fix moved it
the wrong way.** ±0.15 mm was my own estimate. Under arachne, three readings gave
±0.030 half-range, doubled to **±0.06**, and that briefly let the catalogue-ring
route fit. The settled process is classic, and its carrier is **0.100 mm out of
round** — ±0.050 from ovality alone — giving **±0.11** after adding the arachne
between-part term and doubling for a sample of one:

| well | carrier | rings | band | |
|---|---|---|---|---|
| reamed H7 | machined | catalogue | 2.66 / 15 | PASS (production route) |
| reamed H7 | printed (classic) | **sorted** | **7.88 / 15** | **PASS** |
| reamed H7 | printed (classic) | catalogue | **15.14 / 15** | **FAIL, but only just** |
| printed | printed | sorted | — | FAIL |

**The catalogue-ring route sits exactly on the limit and must not be relied on:**
14.45 of 15 points at ±0.08, 15.14 at ±0.09. A sourcing decision resting on 0.55
points of a 15-point budget is not a margin. Micrometer-sorted rings pass at
**7.88 — about half the budget** — and that is the route to use. The seal-pair term
runs at **68.1 squeeze points per mm of tolerance**, making this the chain's
costliest axis.

**Third carrier, the classic process, seven angular positions** (cut 25.2831,
flow 0.95): 25.00, 25.10, 25.06, 25.00, 25.03, 25.08, 25.02.

| | mean | vs target | sd | squeeze at mean |
|---|---|---|---|---|
| arachne (2 positions) | 24.990 | −0.050 | — | 21.02 % |
| **classic (7 positions)** | **25.0414** | **+0.001** | 0.0393 | **22.69 %** |

**One micron off the 25.0404 target, and 22.69 % squeeze against a drawn 22.65 %.**
Every position lands between 21.34 % and 24.59 %, all inside the 15–30 % window.
The compensation is validated far better than the first two-position reading
suggested — that reading happened to catch the two extremes.

The 25.10 is kept. It sits 2.1 sd above the other six, which in a sample of seven
is not an outlier, and dropping it would tighten the tolerance — the direction
that flatters this model. Recorded so the choice is visible: without it, mean
25.0317 and sd 0.0325.

`wall_generator` still demonstrably moves the achieved root, by about +0.05 mm
against arachne, so calibrating against a process and then changing it was a real
risk. The factor is **not** re-tuned: the arachne-derived cut already lands the
classic mean one micron from target.

**And which spread dominates has flipped, which changes what to measure next.**
Under arachne the variation was part-to-part (0.050 mm) and not out-of-round
(0.020 mm), so more *parts* were informative. Under classic ovality is 0.100 mm and
dominates, so more *positions* on one part are now what pays. The old advice must
not be carried across the process change.

Suspected cause of the ovality regression, offered as a suspicion: classic fills
residue with gap infill, whose volume varies around the loop, where arachne
redistributes bead width smoothly — which would make the achieved diameter
angle-dependent. Unverified.

**The well still has to be bored to H7.** That has not changed and no
compensation touches it: the whole reason the root needs correcting is that the
well does *not* shrink with the carrier.

**The ASA carrier cannot carry the membrane.** The PMV15T disc is *welded* into
the production carrier, and the production carrier is machined PP-H for exactly
that reason. ASA is not weldable to PP. Treat the printed carrier as a fit model
of the seal geometry only.

## Still open, and unchanged by printing

- ~~`cell_axial_len = 13.0` is a placeholder.~~ **Deleted 2026-09-05:** the cell
  stands on the board again (`cell_mount = "standing"`), nothing projects past the
  board tip, and the neck it sized is gone. The volume margin no longer rides on
  it — the measured cavity is **2.93 cm³**, and what sets it now is `fast_hole_h`
  through `cav_board_len`. **Every head, carrier and retainer printed before this
  date was cut for the 34.3 mm head; the head is now 21.3 mm.** The carrier and
  retainer are unaffected in section but the carrier's flange went 5.0 → 3.0 mm,
  so those prints are superseded too.
- `cell_seated_h = 8.8` replaces it as the unmeasured input, and it is arithmetic
  (8.3 can + 0.51 socket flange), not a seated part. It sizes tube clearance, not
  head length.
- **EPDM ammonia compatibility is unverified**, gating both the O-ring and the
  membrane gasket.
- The membrane gasket is unsourced — material, hardness, thickness, preload.
- The 6 + 2 screws are unsourced, with an unsourced pilot diameter.

---

# The membrane bed did not print — diagnosis and fix, 2026-09-05

A carrier photographed on 2026-09-05 came off the plate with **filament strung
right across the aperture**, ragged slivers on the flange face, and a groove of
visibly uneven depth. Every gate in the model was green when it was exported.
This section is why, and what changed.

## Why it printed like that

`carrier_printed()` mirrors the part so it prints **wet face down**. That is not
a preference and it does not change below: the flange is 6.05 mm wider than the
spigot per side, so any other orientation puts that step in mid-air and needs
support. Printing wet face down turns every wet-side feature upside down, and
the legacy bed has three features that do not survive the inversion.

1. **The membrane seat is thinner than one layer.** It is `membrane_t` = 0.18 mm
   deep. At 0.2 mm layers there is no way to print a 0.18 mm step: the slicer
   drops it or places it a whole layer out. What is left of it is the 0.862 mm
   membrane ledge, printed as a single free-floating bead 0.18 mm above the
   plate. Those are the slivers on the face.
2. **The O-ring groove becomes a ceiling, and its floor is unsupported.**
   Inverted, the groove's floor — the surface that *sets squeeze* — is an annulus
   running from the flare cone at Ø16.48 out to Ø19.58, printed over air at
   0.93 mm, with **the open aperture as its inner boundary**. It comes out as
   overhanging perimeters, and overhanging perimeters sag.

   **CORRECTED 2026-09-05; the first version of this claim was wrong.** It said
   the slicer *bridges straight across the Ø19.58 hole* and that those extrusions
   are the strands in the photograph. Measured instead of argued — single
   variable, the current model with `mem_seal="cone"` against the clamped bed,
   same profiles, same PROV flags, `radial_ring=onhand-22x2` both sides:

   | feature | legacy `cone` bed | clamped bed |
   |---|---|---|
   | `Overhang wall` | z = 0.32, **1.04**, 5.12, 8.72 | z = 8.72 only |
   | `Bridge infill` | **absent** | **absent** |
   | `Internal Bridge` | z = 3.68 (Ø22.38–32.92), 4.52 | z = 4.52 |

   The slicer **never bridges anything here.** The predicted overhang is real and
   is where it was predicted — z = 1.04 spanning Ø17.10–18.31, inside the
   Ø16.5–19.6 band — and the clamped bed removes all three legacy levels. The
   `Internal Bridge` at z = 3.68 is Orca's *solid-over-sparse-infill* feature,
   sits entirely **outboard** of the aperture, and has nothing to do with the
   window.

   So the uneven groove is explained. **The strands across the aperture are
   not.** Stringing on travel moves is the obvious candidate and it is untested.
   Nothing below should be read as explaining them.
3. **Nothing is a multiple of anything.** Groove 0.75 mm deep — 3.75 layers at
   0.2, 6.25 at the 0.12 this actually slices at — and 1.55 mm wide. Depth that
   is not an integer layer count is depth the *slicer* picks, and since
   `squeeze = 1 − gap/cord`, that pick is a seal dimension.

   (An earlier version added "so the floor is one bridged layer plus gap fill".
   **Withdrawn:** Arachne varies extrusion width and the archived Orca job
   records `gap_fill_target=nowhere` — no gap fill is emitted. That mechanism was
   asserted, never observed.)

The common cause is that the bed was designed in the orientation it is *drawn*
in (wet face up, where all three features are ordinary milling cuts) and printed
in the orientation the *flange* dictates.

## The fix: move the bed, do not tune it

The groove moves out of the carrier and into the **retainer**, whose underside it
is cut into. The retainer is a flat ring, so it can be printed groove-up on solid
material with no overhang anywhere. The carrier's wet face becomes a plain flat
land with one tapered aperture.

The seal is unchanged in kind. The membrane is still nipped between an O-ring on
one side and a flat land on the other; the stack is mirrored, not redesigned:

    retainer   ── O-ring in its groove ──┐
    membrane   ─────────────────────────┤  same joint, upside down
    carrier    ── flat land ────────────┘

Consequences, all of them wanted:

- the carrier has **no feature under one layer and no bridge**. Its aperture
  opens *downward* as an 11.31° cone from Ø16 at the wet face to Ø18 at the
  spigot bore, so every layer's hole is wider than the one below it, and the
  cone lands exactly on the bore so there is no ledge left anywhere in the part;
- the groove now has a **real inner wall**, 0.8 mm — two deliberate beads — on
  the retainer bore. The legacy bed had none at all: its inner boundary was the
  flare cone, which is also why `mem_ring_inner_d` could only ever tripwire;
- the groove sits on the **wet side** of the membrane, so it stops counting
  against the 5.0 cm³ connected-volume budget;
- the vestigial Ø22 heater counterbore goes with it — `RING-PCB.md` put the
  heater in the spigot bore, head-side — which removes 380 mm³ of cavity. Net,
  the core void drops from 1258 + 21 mm³ to **1136 mm³**.

`mem_seal = "clamped"` selects it and is now the default. `mem_seal = "cone"`
still builds the legacy bed, gates and all, for the machined-PP route.

## Which side of the membrane the ring sits on

Asked on review, 2026-09-05, and worth recording because the first answer —
"it is a mirror, so it does not matter" — is only true of the seal itself.

**The connectivity is symmetric; the contact mechanics are not** — and the first
version of this section slid from one to the other without earning it. The ring never seals against the
membrane as such; it nips the membrane against a rigid flat counterface, and the
chain from wet to dry has the same three interfaces either way, two elastomeric
and one rigid-on-rigid:

| interface | ring on the DRY side (legacy) | ring on the WET side (now) |
|---|---|---|
| groove floor ↔ ring | ASA ↔ rubber | ASA ↔ rubber |
| ring ↔ membrane | rubber ↔ PTFE | rubber ↔ PTFE |
| **membrane ↔ rigid land** | **PTFE ↔ retainer** | **PTFE ↔ carrier** |

There is **no separate carrier-to-membrane gasket in either version**, and there
never was one: that rigid interface *is* the seal, loaded through the membrane by
the ring, over the ring's footprint. Inboard of the footprint is legitimately
cavity, outboard legitimately wet. The in-plane bypass through the porous PTFE
exists identically in both, and is the same unverified-preload risk as before.

**What the symmetry does not establish is that either arrangement seals.**
Wet fluid can enter the porous PTFE at the disc rim, outboard of the ring, and
travel laterally *through the 0.18 mm membrane* beneath the sealing line — in
both layouts — unless the clamp collapses the media under the ring. Porex permits
a compression seal on PMV15T, so a second gasket is not automatically required;
but "no separate gasket is needed" is a claim about in-plane permeability under
load that **nobody here has measured**. The defensible statement is narrower: the
two layouts are equivalent in leak path, and both rest on the same unverified
assumption.

What differs is four other things, and they do not all point the same way.

**Favouring the wet side, where it now is:**

- **The membrane is backed everywhere.** This is the concrete one. In the legacy
  bed the membrane's rim *spanned its own O-ring groove* — 1.55 mm of
  unsupported PTFE with the ring pushing up into it from below, on top of the
  window. The carrier land is now flat from the aperture out to Ø26.85, so the
  only thing the membrane spans is the Ø16 window it is meant to span. Nothing
  to dish or extrude into.
- **Pressure loads the seal instead of unloading it.** Water head pushes the
  membrane onto its sealing land rather than off it.

  **Magnitudes corrected 2026-09-05 — the first version had both wrong.** It
  multiplied 265 mbar over the whole Ø26.85 *coupon* for ~15 N. The coupon is not
  the pressure-exposed area: the membrane spans the **Ø16 window**, 201 mm², so
  **~5.3 N**. And 265 mbar is Porex's minimum **water-entry test threshold**
  (~2.7 m of head), a breakthrough bound rather than an operating differential.
  The ~100 N preload was a guess; Parker ORD 5700 Figure 2-5, p. 2-11, gives
  roughly 10–20 lbf/in at 24–26 % squeeze on 70 Shore A, i.e. **~110–220 N** over
  the installed centreline circumference. The conclusion survives and is stronger
  than claimed — order 5 N against order 150 N — but on different numbers.

**Favouring the dry side, where it was:**

- **Chemical exposure.** A dry-side ring is shielded behind the membrane; a
  wet-side ring sits in the condensate. It is not new chemistry — the radial
  ring already lives there in the same EPDM 70 peroxide — but it is service life
  spent for nothing, and it is the strongest argument for putting it back.
- **The groove becomes a wet-side pocket** that can hold water against the
  membrane, which bends this project's own no-water-trap rule
  (`RESPONSE-CANDIDATE-VOLUME.md`, "Access-path constraint": *a recessed
  membrane with a water-trapping outer pocket is not acceptable*). Drain slots
  through the retainer's outer wall would fix it. **Not currently drawn.**

**So the side is a consequence of the printing constraint, not a sealing
judgement.** A dry-side ring means the groove is in the carrier; the carrier can
only print wet-face-down (the flange overhangs the spigot by 6.05 mm per side);
a groove in its wet face is therefore a ceiling over the open aperture, which is
the photograph. The two ways to have a dry-side ring anyway, both with a price:

1. **Give the groove a real inner wall** so its floor is a 3.6 mm bridge
   anchored on both sides instead of strands over a hole. It prints — but a
   bridged surface sags, and that surface is the groove depth, which is the
   dimension this whole change bought 6× more tolerance for.
2. **Print the carrier wet-face-up on support** under the flange overhang. The
   support scars land on the flange *seating* face, which the radial O-ring
   makes non-critical — it seals on the spigot, not the face. This is the option
   to take if the exposure argument wins.

**Weakest link, and it is unchanged by the side.** The rigid PTFE-on-printed-ASA
interface is the least trustworthy joint in the chain in *both* versions. On the
new carrier that land is the **first layer against a Textured PEI plate**, so it
carries the plate texture directly under the seal line — the legacy version had
the same problem on the retainer's plate-side face. Options, cheapest first: a
smooth plate for the carrier; let the ring's line load bed the PTFE into the
texture (plausible — PTFE cold-flows, which is listed as a risk elsewhere in this
file); or face 0.1 mm off. **Measure this before the squeeze number** — it is
ahead of everything else in the leak test.

## The ring: 17.0 × 2.0, ordered — and why the 2.5 below is superseded

**Superseded 2026-09-08. The section that follows is kept because its argument is
still correct; only its conclusion is dead.** Fab, 2026-09-08: the 17 × 2.5 in
the drawer *"is bad quality and not EPDM"*. That is not a tolerance judgement and
it cannot be traded against one. The entire ammonia case — compound `127019011`,
its compression-set table, and the Kömmling ageing data at 25 % compression — is
for **peroxide-cured EPDM 70**. A ring of unknown rubber is out on material, no
matter how well its cord band stacks up.

So the bed moved to a **17.0 × 2.0**, and everything below about the fat cord
being *"half the fix"* remains true and is now the price being paid: cord
tolerance is an ABSOLUTE band, so it costs more squeeze points the thinner the
cord, which is exactly why the 2.0 no longer closes on the catalogue band and the
2.5 did. **The 2.0 is not an improvement. It is the cheapest ring with the right
cure.**

### What was ordered, 2026-09-08 (eBay)

| item | what it is | for |
|---|---|---|
| `157712596230` | O-Ring 17,0 × 2,0 mm **EPDM-Peroxidvernetzt FDA Konform** 70 Shore, 1 Posten = 20 St., €2.50 | **the bed ring.** Cure DECLARED; compound, lot and test report NOT |
| `168191533567` | O-Ring 17,5 × 2,5 mm EPDM 70 ±5 Shore A schwarz, 1 Posten = 20 St., €2.50 | trial stock for the OLD 2.5 bed — see the caveats below |

Neither carries a compound number, so **neither is a release part**. They are
bench rings. The documented equivalents at o-ring-stocks, all material
`127019011`, are `ORS116734` (17 × 2.5, €0.13), `ORS116732` (17 × 1.5, €0.22)
and — for the cable end, the last uncatalogued seal in the probe —
`ORS116765` (22 × 2, €0.17, listed *on order* rather than in stock).

**The 17,5 × 2,5 still fits the 2.5 bed, with two caveats.** Rendered against the
unchanged 1.92 groove it gives 22.98 % nominal on the **catalogue** band, gap
1.92 +0.080/−0.071, worst-corner fill 89.1 %. But:

- its cure is **not declared**. The seller labels their peroxide line explicitly
  in the title (`EPDM-Peroxidvernetzt FDA Konform`); this item does not carry
  that, and its description is a generic EPDM explainer that merely *mentions*
  the peroxide/sulphur difference and says so itself: *"Diese Information ist
  allgemeine Information."* Treat it as their standard grade;
- **install stretch is 0.571 %**, against 3.53 % for a 17.0, because the groove
  ID is pinned at Ø17.6 by the window and does not follow the ring. What that
  risks is the ring not staying seated during assembly — the same failure already
  carried as a live waiver on the cable end's 22 × 2 — not the seal itself;
- fill 89.1 % is inside the 90 % cap but no longer comfortable.

Useful for practising the assembly and for the seating/handling question. Not for
a probe that goes in a pile.

### Sorting is back on, and it is a debt against the bench

`face_sorting = "sorted"` — which **reverses Fab's 2026-09-06 call**, *"i dont
think it makes sense measuring these"*. The argument against measuring did not
get weaker; the ring changed underneath it. On a 2.0 cord the catalogue ±0.09
band closes at **no depth on the 0.12 grid**: swept targets 0.30/0.28/0.26/0.24
all overrun the 30 % ceiling and 0.22 drops under the 15 % floor. There is no
third option, so "sorted" is not a preference here — it is the only setting under
which this bed exists.

The warning next to that flag still binds and is now a debt, not a formality:
declaring "sorted" while nobody micrometers a ring does not tighten anything, it
only stops the model from saying so. **The 20 rings in lot `157712596230` must be
micrometered to ±0.01 on the cord and the out-of-band ones set aside.** The
20-piece lot is what makes that realistic where a handful of documented rings
would not. If they are not measured, put `face_sorting` back to `"catalogue"` and
buy `ORS116734` instead — the 2.5 is the ring that works *without* measuring, and
that is the whole reason it was chosen in the first place.

### The depth is chosen off this printer's measured error, not off a midpoint

`face_squeeze_target = 0.26`. On a 2.0 cord the 0.12 grid offers two depths:

| drawn | nominal | gap tolerance | binding end |
|---|---|---|---|
| **1.44** (12 layers) | 26.7 % | **+0.181 / −0.019** | ceiling — compression set, the benign failure |
| 1.56 (13 layers) | 20.6 % | +0.061 / −0.139 | **floor — leakage, the failure that matters** |

Both printed retainers gauge **1.95 against modelled 1.80/1.88**: this machine
cuts the bed deep by 0.07–0.15 mm, and a deeper groove is a bigger assembled gap,
i.e. it errs toward the FLOOR. 1.44 puts 0.181 mm of room on that side; 1.56 puts
0.061 and the measured print error alone overruns it. **The target that looks
less centred is the one that survives the error this machine actually makes.**

0.15 mm of print error against 0.181 mm of room is not margin to be casual with:
**measure the assembled gap.** The bed has not set squeeze by geometry since the
seat was deleted, so that measurement was already owed.

### Consequences elsewhere

- **The membrane blank shrinks: Ø25.96 → Ø24.688.** A hand-cut square must be at
  least 24.688 across the flats.
- Groove is now **Ø17.6/Ø22.688 × 1.44 = exactly 12 layers of 0.12**, worst-corner
  fill 84.7 %.
- Retainer sliced 2026-09-08: 11 m 29 s, 2.89 cm³, on the unchanged
  `process_asa_seal.json`. **No 0.06 mm profile and no nozzle change** — the
  machine's `min_layer_height` is 0.08 for the 0.4 nozzle, so the 0.06 route
  explored earlier was never available on this printer.
- **The 17 × 1 in the drawer is dead for this bed**, at any printable layer
  height, sorted or not: at 0.12 one layer is 12 of the 15 available squeeze
  points, and at 0.08 it is still 8. It was sized for the machined PP pocket that
  `d1c955a` deleted, where a fat cord had nowhere to extrude but across the gas
  window. That constraint no longer exists.

### Two labels that had gone stale, fixed in the same change

- **`gasket_id` vs `ORS116731`.** The cone bed's ring ID is derived
  (`window_d + 1.0`); the part number was chosen when `window_d` was 16.0, giving
  exactly 17.0. `window_d` then went to 15.2, the drawn ring followed it to
  Ø16.2, and the echo went on naming ORS116731 and its compound test report. The
  ring is now declared as data (`mem_oring_id`) and the derivation is **asserted**
  against it, so it fails at the drift instead of reporting it. It fails today, on
  purpose — that is the calibration.
- **The Makefile's provenance line** spelled `O-ring 17 x 2.5` as a literal and
  would have gone on claiming 2.5 forever. It now reads the ring out of the model.

Both are the same defect: a name kept while the value moved.

## The ring: 17.0 × 2.5, chosen from what is in the drawer — SUPERSEDED, see above

Three sizes were on hand — 17 × 2.5, 20 × 2, 14 × 2.5.

| | verdict |
|---|---|
| **17.0 × 2.5** | **chosen.** Groove Ø17.6/Ø23.96 × 1.92, no seat: the membrane must simply COVER Ø25.96 |
| 20 × 2 | rejected on **size**: its groove puts the membrane disc at Ø28.0 against a bolt-hole inner edge at Ø29.3 |
| 14 × 2.5 | rejected on sight: the bore is *inside* the Ø16 window |

The fat cord is not a compromise, it is the second half of the fix. The cord
tolerance is an **absolute** band, so ±0.09 on a 2.5 cord costs far less squeeze
than ±0.08 on the legacy 1.0 cord did. All figures below are the model's own
echo, on the **catalogue** cord band:

| | legacy 17 × 1.0 | clamped 17 × 2.5 |
|---|---:|---:|
| assembled gap | 0.750 | **1.920** |
| nominal squeeze | 25.0 % | **21.82 %** |
| depth may err by | ±0.032 mm | **+0.049 / −0.098 mm** |
| worst-corner fill | 78.2 % | **87.7 %** (see below — it is a stacked corner) |
| groove depth | 0.75 (3.75 layers) | **1.92 = 16 × 0.12** |

### 2026-09-06 REVERSED THE TWO DECISIONS BELOW. Read this before re-deriving them.

The section that follows this one used to say the band was 20–30 % and that
micrometer-sorting the rings was mandatory. **Both are now false**, and the
reasoning that produced them is kept below because it is sound and you will
otherwise rediscover it and change the model back.

Fab, 2026-09-06: *"i dont think it makes sense measuring these, as they are
somewhat not perfect anyway and we need to work with some tolerances anyways."*
`make head-end-asa` no longer passes `face_sorting="sorted"`. Nobody micrometers
these rings, so the model must not declare that they are micrometered — a
declared tolerance nobody verifies does not tighten a ring, it only stops the
model from saying so.

That single change forces three others, because the catalogue band genuinely is
harder to satisfy:

| constant | was → now | why it had to move |
|---|---|---|
| `face_floor` | 0.20 → **0.15** | on catalogue, the 20 % floor and the 85 % fill ceiling **cross**: the feasible assembled gap comes out inverted, 1.905…1.881 — empty by 0.024 mm. No groove depth satisfies both |
| `face_squeeze_target` | 0.25 → **0.22** | 0.25 solves the depth to 1.80, outside the new window, and the ceiling assert fires. 0.22 solves to 1.92. Anything 0.21–0.24 quantizes to the same 1.92 |
| worst-corner fill cap | 0.85 → **0.90** | that corner stacks the fattest cord against the shallowest groove the 30 % ceiling permits — an allowance against an allowance — and reaches 87.7 %. Expected fill at 1.92 is 71.2–84.4 % across the whole catalogue band, inside 85 % at every corner |

The alternative to the last one was widening `face_groove_w_factor` to ≥ 3.38.
That constant is Parker's gas/vacuum row, carries its own DO-NOT-CHANGE note, and
a wider groove is where the ring was seen climbing out on 2026-09-05.

**Why this needed no reprint.** Both printed retainers gauge **1.95** deep —
groove-up and groove-down, against modelled 1.80 and 1.88, so the print runs deep
and the two offsets do not agree, which still wants a caliper-zero check. At an
assembled gap of 1.95 on the full catalogue band the joint holds fill 70.1–83.1 %
and squeeze 17.1–23.9 %: only the thin-cord corner failed, only against the
floor, by 2.9 points. The requirement window is now 1.822–1.969 and 1.95 sits
inside it.

**What it costs, so nobody rediscovers it as a surprise.** 17 % squeeze is less
sealing force than 20 %, and on a gas seal that is the direction that leaks. It
is defensible here — static face seal, room temperature, no fluid swell, fill
nowhere near its ceiling — but it is a *decision*, not a default. **If this bed
leaks, `face_floor` is the first suspect and the worst-corner fill cap the
second.** The fix that keeps 20 % is a 1.80 groove with the fill ceiling at 90 %,
which needs a reprint and does not cover the two retainers on the bench.

`oring_sorting` for the **radial** ring is untouched and still claims
micrometered Ø24 × 1.5. Same unverified shape, different ring, not covered by
this decision.

### The hand-cut square fouls the bolt circle, and the model says so

With no seat the membrane is not located by anything — it lies loose between the
retainer face and the carrier land. It only has to **cover** the ring: at least
**Ø25.96**, so the O-ring lands on membrane and not off its edge.

A *square* blank big enough to do that is 25.96 across the flats, and its corners
then reach **r 18.36** — against a bolt circle at **r 15.18**. The corners run
past the screws. Trim them, cut an octagon, or accept that the blank is pierced
when the screws go in. Fab, 2026-09-06: *"i cannot cut round circles so precisely
yet (we might have to make stencil)"* — a stencil at Ø25.96–28 is the clean fix
and is not built.

### The superseded argument, kept because it is correct on its own terms

**The band is 20–30 %, not 15–30 %.** Parker ORD 5700 Design Chart 4-3, p. 4-18,
gives 20–30 % for the nearest face-seal cross-section. The 15 % floor this
document and the model both carried was the *radial* rule, copied across from the
carrier-to-head ring — and a face seal has no gland-fill energisation to fall back
on. Raised to 20 % on 2026-09-05, **lowered again to 15 % on 2026-09-06** for the
reasons above: the 20 % floor is right in the abstract and unreachable on a ring
nobody measures.

**Sorting was therefore mandatory on this bed, and the model enforced it.**
With the 20 % floor, the catalogue cord band alone leaves *no* groove depth on the
0.12 mm grid that holds 20–30 % across the corners: 1.80 is too shallow at the fat
corner and the next step down, 1.68, reaches 33 %. That is still true — it is why
the floor had to move rather than the depth.

The tighter end is now the **floor** — the end that leaks — not the ceiling, and
the model reports which end binds rather than asserting it. Three inputs that were
missing or wrong until the review:

- **the membrane is part of the gland stack.** PMV15T is 0.18 ± 0.03, so it
  spends 0.06 mm of the gap band — more than a sorted cord does. It had been
  treated as exact.
- **d1 ≤ 18 is ±0.21**, not ±0.22; 17 sits in the first row and the code had the
  second.
- **`face_id_tol` reached nothing.** Both tolerance functions used the
  nominal-ID stretch, so the ring's own ID band never touched squeeze, fill or
  the quoted depth requirement. It was declared, echoed, and inert.

And the corner pairing was backwards. Stretch is `groove_id/ring_id − 1`, so a
*thin* ring stretches more and its cord thins more: the smallest fitted cord is
the thin cord on the **thin** ID, not the fat one. Pairing them the other way
flattered the floor and turned a failing build into a passing one.

## What this asks of the slicer

**The groove depth is an integer number of layers and that is a seal dimension.**
1.92 mm = **16 × 0.12**, and 0.12 is what `profiles/process_asa_seal.json`
actually slices at — not the 0.2 this section first assumed. **There is no
membrane seat any more** (`face_seat_depth = 0`, dropped 2026-09-06 on Fab's ask
— *"i just cut a square out of the PTFE and throw it there"*), so the old note
about the seat being `2 × face_layer_h` by construction no longer applies. With
no seat the retainer bottoms **on the membrane**, which means squeeze is no
longer set by geometry alone: it depends on where a hand-cut blank lands and how
much 0.18 mm PTFE creeps under six screws. The model echoes MEASURE IT, and that
measurement is the one that actually closes this bed. `profile_check.py`
compares the model's layer height, first layer and line width against the profile
that slices the plate, and `make head-end-asa` runs it before exporting.

Slice at any other layer height and the depth becomes whatever the slicer rounds
to. The model cannot see the slicer, so `face_layer_h` moves with the profile or
the guard is a decoration.

Orientation, both parts, no support:

- **carrier** — wet face down, unchanged (the flange step forces it). Note this
  puts the membrane sealing land on the **first layer**, against Textured PEI;
- **retainer** — **groove up**. Flat side down is what the legacy ring wanted and
  is exactly wrong now: it would put the bed's floor — the surface that sets
  squeeze — in the air over the retainer bore.

**Brim:** `brim_type` must stay `outer_only` for both parts. The shared profile
briefly carried `outer_and_inner` with `brim_object_gap 0` for a tall tower, which
would have fused a brim **inside the Ø16 aperture and all six bolt holes at z=0 —
i.e. onto the carrier's sealing land**. It is now a per-part override in
`print.sh`, with carrier and retainer pinned to gap 0.1 + `outer_only`.

`retainer_t` is **4.04** = `0.2 + 32 × 0.12`, derived onto a layer boundary rather
than rounded to 4.0: the part prints groove-up, so its top face is the bed's
reference plane. The bed takes 2.04 mm out of the underside and the web that
reacts the ring would otherwise be 1.0 mm, which bows and gives back the squeeze
the groove depth was set to hold.

## Still open on this bed

- **The rings are uncatalogued.** 17 × 2.5 is a size in a drawer, not a part
  number: material, hardness, cure system and cord tolerance are all assumed
  (EPDM 70 peroxide and the DIN band are what the model uses). Micrometer the
  cord before trusting any squeeze figure here, and do not carry the
  ammonia-compatibility argument over from `ORS116731` — that argument rests on
  a **specific compound test report**, which these rings do not come with.
- **Preload is still unverified**, exactly as for the legacy bed: an O-ring
  seals on a line at far lower load than the washer bracket assumed, and PTFE
  cold-flows. Mirroring the joint does not change that risk, it only moves which
  face the line lands on — now the membrane's **wet** face.
- **Nothing has been printed yet.** Every number above is from the model or from
  a sliced plate, not from a part.
- **The strands in the photograph are unexplained.** The uneven groove is
  accounted for (unsupported overhang perimeters, measured); the web across the
  aperture is not. Stringing is the untested hypothesis.
- **In-plane permeation under the seal line is unmeasured**, and both bed layouts
  depend on it. This is the one that decides whether the bed seals at all.
- **The wet-side groove has no drainage.** Moving the bed into the retainer put it
  on the compost side, where it can hold water against the membrane. Drain slots
  through the retainer's outer wall are the fix and are not drawn.
- **The sealing land carries the plate texture.** The carrier prints wet face
  down, so the land the membrane seals against is a first layer on Textured PEI.
  Measure this before the squeeze number.
- **The rings are uncatalogued.** 17 × 2.5 is a size in a drawer: material,
  hardness, cure system and cord tolerance are all assumed, and the ammonia
  argument does **not** carry over from `ORS116731` — that rests on a specific
  compound test report these rings do not have.
- **Groove width is 3.625 mm**, which exceeds Parker Chart 4-3's nearest-row
  maximum by 0.018 mm for liquids and 0.450 mm for gases/vacuum. This is a gas
  seal. It is out of the chart on a nonstandard 2.5 mm cord, and narrowing it to
  the gas row would push worst-corner fill from 74.5 % to about 90 %, over the
  85 % lock limit. Unresolved — it needs either a standard cord or an argued
  deviation, not a silent one.

## The bore entry at the monolithic joint (fixed 2026-09-06)

The monobody prints cable-end-down, so the head's bore lands on top of the tube's.
Those bores are not the same size — tube `body_tube_id` 27.20, head `bore_d` 25.18 —
and the difference used to arrive as a **square annular ledge 1.01 mm wide**, hanging
over the tube bore with nothing under it. Around a 79 mm circumference at a 0.6 mm
line that is roughly 1.7 perimeters printed entirely in air.

Observed on the first monobody, by Fab: *"spiderweb filament … filament spans across
the hole"*, right below the neck. The same failure the membrane carrier had.

**The slicer had already reported it and nobody read the report.** `plate_1.gcode`
carried `; FEATURE: Overhang wall` at `Z_HEIGHT 124.16` — model z 0.10, this ledge and
no other. Extracting them is one line and is worth doing on every new plate:

```sh
awk '/^; Z_HEIGHT: /{z=$3} /^; FEATURE: Overhang wall/{print z}' plate_1.gcode \
  | sort -n | uniq -c
```

The fix is geometry, not a slicer setting: `bore_lead_h`, a 45° cone from the tube
bore up to the head bore. 45° because it is the self-supporting limit *and* because it
falls under Orca's overhang classifier — at 0.12 mm layers on a 0.6 mm line a 45° wall
is 20 % unsupported against a 25 % threshold, so the feature stops being an overhang
rather than merely becoming a better-printed one.

Verified: the `Z 124.16` entry is gone from the re-slice, every other overhang is
unchanged, print time moved 4 h 00 m 34 s → 4 h 00 m 23 s, and the head's mesh volume
fell 5712.9 → 5671.7 mm³ (−41.2), against 41.4 mm³ predicted for the cone.

The cone is cut in `cavity()` as well as in the head body. Leaving it out of the
cavity would have made the measured gas volume describe a part other than the one
being printed — the same defect the 2026-09-05 review found in this module.

**Bonded is deliberately untouched.** There the step is at the socket floor, it is
3.6 mm rather than 1.01, and it is the tube's stop face — a functional surface, not a
transition. If the bonded head is ever printed this way up it needs its own answer.

**Still open:** 8 `Overhang wall` entries remain at model z 6.10, inside the head above
the neck. Not investigated.
