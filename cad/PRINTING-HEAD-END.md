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

- `cell_axial_len = 13.0` is a placeholder. The 3.0 % volume margin rides on it.
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
2. **The O-ring groove becomes a ceiling, and its floor is bridged across the
   hole.** Inverted, the groove's floor — the surface that *sets squeeze* — is an
   annulus running from the flare cone at Ø16.48 out to Ø19.58, printed over air
   at 0.93 mm, and **its inner boundary is the open aperture**. An annular ledge
   with no inner anchor is not a bridge the slicer can span across 1.55 mm; it
   anchors on the far rim and lays lines straight over the window. That is the
   web in the photograph.
3. **Nothing is a multiple of anything.** Groove 0.75 mm deep (3.75 layers) and
   1.55 mm wide (≈3.9 beads at 0.4). The floor comes out as one bridged layer
   plus gap fill, at whatever height the slicer rounds to. Since
   `squeeze = 1 − gap/cord`, an uneven groove **is** an uneven seal — the
   unevenness is not cosmetic here the way the bolt-hole voids above are.

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

## The ring: 17.0 × 2.5, chosen from what is in the drawer

Three sizes were on hand — 17 × 2.5, 20 × 2, 14 × 2.5.

| | verdict |
|---|---|
| **17.0 × 2.5** | **chosen.** Groove Ø17.6/Ø24.85 × 1.8, membrane disc Ø26.85, 1.03 mm clear of the bolt holes |
| 20 × 2 | rejected on **size**: its groove puts the membrane disc at Ø28.0 against a bolt-hole inner edge at Ø29.3 |
| 14 × 2.5 | rejected on sight: the bore is *inside* the Ø16 window |

The fat cord is not a compromise, it is the second half of the fix. The DIN
ISO 3601 cord tolerance is an **absolute** band, so ±0.09 on a 2.5 cord costs
**5.34 squeeze points** where ±0.08 on the legacy 1.0 cord cost 12.1. That is
what buys the depth tolerance back:

| | legacy 17 × 1.0 | clamped 17 × 2.5 |
|---|---:|---:|
| assembled gap | 0.750 | 1.820 |
| nominal squeeze | 25.0 % | 25.9 % |
| depth may err by | **±0.032 mm** | **+0.192 / −0.039 mm** |
| worst-corner fill | 78.2 % | 78.8 % |

Both ends are quoted deliberately. The **floor** (15 %, a leak, now) is reached
by the thin end of the cord band in a groove cut too deep; the **ceiling** (30 %,
compression set, over years) by the fat end in one cut too shallow. The ceiling
is the tighter end on this bed and it is the benign one — quoting only the floor,
as the legacy bed did, would hide it. Micrometering the rings on receipt
(`face_sorting = "sorted"`) opens the ceiling from 0.039 to 0.094 mm and costs
nothing: the rings are here.

Install stretch is 3.53 % nominal onto the Ø17.6 inner wall, 4.89 % on a ring at
the thin end of the DIN d1 band — inside the 5 % rule, with 0.11 points to spare.
It is asserted at that end, not at the nominal.

## What this asks of the slicer

**The groove depth is an integer number of layers and that is a seal dimension.**
1.8 mm = 9 layers of 0.2. Slice this part at any other layer height and the depth
becomes whatever the slicer rounds to — the model asserts the multiple, but it
cannot see the slicer, so `face_layer_h` must be moved with the profile and the
depth re-derived.

Orientation, both parts, no support:

- **carrier** — wet face down, unchanged from before (the flange step forces it);
- **retainer** — **groove up**. Flat side down is what the legacy ring wanted and
  is exactly wrong now: it would put the bed's floor in the air over the retainer
  bore, which is the same bridge that ruined the carrier.

`retainer_t` moves 3.0 → **4.0**. The bed takes 2.0 mm out of the underside and
the web that reacts the ring would otherwise be 1.0 mm, which bows and gives back
the squeeze the groove depth was set to hold. It costs 1.0 mm of probe length
through `cap_stack`.

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
- **Nothing has been printed yet.** Every number above is from the model.
