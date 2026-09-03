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

## Settings that matter

- **Enclosure, and a brim.** The three large flat discs are Ø39–47 ASA on a hot
  bed; warping lifts the flange and the retainer face, which are the two surfaces
  the seal stack clamps against.
- **Do not** let the slicer put a seam or a gap-fill artefact inside the Ø27.3
  well or on the flange face. Those are sealing surfaces.
- Solid enough through the O-ring groove and the bosses: this is not a display
  print. The bosses are threaded into by 6 thread-forming screws.

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
