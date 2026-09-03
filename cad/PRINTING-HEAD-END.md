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

**Carrier flange OD: 38.90 mm measured against 39.10 drawn — −0.20 mm, −0.512 %.**
That is ordinary ASA shrinkage, and it is the first real number this design has
had for a printed dimension.

It matters because the well is *bored* to size and therefore does not shrink,
while the spigot and groove root do. The two errors do not cancel — they add:

| | groove root | stretch | gland | squeeze |
|---|---|---|---|---|
| as drawn | 25.0404 | 4.33 % | 1.1298 | 23.01 % |
| at −0.512 % | 24.9123 | 3.80 % | 1.1938 | 18.87 % |

So uniform shrinkage costs **4.14 squeeze points**, and the design's worst-case
low end of 16.12 % would land near **12 %, under the 15 % floor**.

Three caveats, and they matter as much as the number:

- **One sample, one dimension.** This is the systematic *bias*, not the scatter.
  My ±0.15 mm figure for a printed groove root was about scatter and this does
  not replace it.
- **The bias is correctable, the scatter is not.** A known −0.5 % is just a
  bigger groove root. Only the scatter eats the tolerance budget.
- Shrinkage is not isotropic and a wide flange rim need not shrink like a small
  spigot, so **applying this factor to the groove root is an inference**.

Next measurements, in priority order, both off the part already printed: the
**spigot OD** (Ø27.000 drawn) and the **groove root** (Ø25.0404 drawn). Those two
set the seal directly; the flange OD only stands in for them.

## Surface defects on that print

**Webbing across the bore.** Confirmed in the sliced G-code: two annular ledges
that cantilever inward over open holes, at z = 1.20 (Ø21.60 → Ø16.86, 431
overhang-wall moves) and z = 5.20 (Ø22.30 → Ø18.30, 385 moves plus internal
bridging). Inherent to printing flange-down. The z = 5.20 step is a plain bore
step and could be coned; the z = 1.20 one is the membrane sealing land and cannot.
**This carrier therefore cannot be used to judge the membrane seal.**

**Voids around the bolt holes** — carrier on the upper face only, the rim on both.
Cause NOT established. Two hypotheses were tested against the G-code and neither
survived:

- *Six perimeters will not fit the 2.0 mm rim.* The arithmetic is right
  (6 × 0.42 = 2.52 mm) but the conclusion is wrong: rim fill measures 100 % at
  wall_loops 6, 98 % at 3 and 82 % at 2, because dropping perimeters hands the
  middle to 25 % sparse infill. Fewer walls is worse.
- *The top-surface pattern.* Switching `monotonicline` → `concentric` moves top
  material −26.8 % on the carrier and +26.3 % on the retainer — opposite
  directions, so it establishes nothing.

What IS evidence: the carrier's two faces have identical geometry around the
holes, and only the top is bad. Top uses `monotonicline`, bottom uses
`monotonic`. That is a real controlled comparison, confounded only by the bed
pressing the first layer flat. On that basis the one change worth trying is
`top_surface_pattern = monotonic`, matching the face that came out clean —
offered as the best available inference, not a diagnosis.

## What this print does and does not establish

**It is a fit and geometry check.** It establishes the bolt circle, the
flange/retainer stack height, the cap grip and cage, the socket over the tube,
and whether the carrier actually enters the well. That is worth having.

**It does not establish the seal**, and the numbers say so plainly. Running the
model with the carrier printed rather than turned:

| well | carrier | rings | band | |
|---|---|---|---|---|
| reamed H7 | machined | catalogue | 12.41 / 15 | PASS (production route) |
| reamed H7 | **printed** | **sorted** | 11.97 / 15 | PASS |
| reamed H7 | **printed** | catalogue | 19.24 / 15 | **FAIL** |
| printed | printed | sorted | 24.88 / 15 | **FAIL** |

So an as-printed pair does not seal, and no O-ring squeeze value exists that
satisfies both ends of the tolerance band. To get a *sealing* prototype out of
printed parts, two things must both happen:

1. **Bring the well to H7.** Ø27.3 H7 is not a stock machine-reamer size; the
   practical route is single-point boring on a lathe, which is diameter-agnostic
   and does not care that 27.3 is an odd number. Moving the well to a stock
   Ø27.5 reamer is *not* a drop-in — it pushes install stretch to 5.17 % and
   trips the 5 % rule, so it would need a different ring ID.
2. **Sort the rings by cord with a micrometer** and use the ones that fit.

Also note the printed-carrier figure of **±0.15 mm on the groove root is my own
estimate, not a measured value.** Route 2 above rests on it. Measuring the groove
root on this very print is the cheapest way to replace that estimate with a fact.

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
