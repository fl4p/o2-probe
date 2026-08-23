# O₂ probe Rev-A 3D model

This directory contains a superseded parametric mechanical study of the buried
compost oxygen probe. It is retained as enclosure research, not as the current
PCB or ring-carrier source of truth. Its OpenSCAD files still model:

- 32 mm OD / provisionally 28 mm ID PVC-U enclosure, 129 mm long;
- the obsolete 20 × 119 × 1 mm PCB envelope and SGX cell location;
- removable PMV15T coupon carrier with PP support grid;
- passive, drained and side-vented diffusion head with a coarse-debris guard;
- cable-end cap with PCB slot and an offset 6.4 mm cable passage.

Run `make all preview` in this directory to regenerate the meshes and preview.
The generated `exports/` directory contains the five individual parts plus a
colour-capable 3MF assembly.

## Model status

This is **not fabrication-release geometry** and must not be used to infer the
current 20 × 107 mm board end, soldered heater ring, or membrane spacing.
Those are controlled by the KiCad project, `PLAN.md`, and a future 1:1 ring/tube
coupon. The tube ID,
129 mm body length, slip fits, membrane active area, carrier pocket, cable bore,
head retention and guard details are provisional interfaces chosen to make a
complete Rev-A fit model.

The enclosure and PCB tip were shortened together by 6 mm. This preserves the
previous 7 mm nominal board-end-to-membrane clearance while reducing the
SGX-cell-centre-to-membrane datum from 38.5 mm to 32.5 mm.

Before printing a functional enclosure, measure and update:

1. actual minimum tube ID and ovality;
2. full populated-PCB front/back swept envelope, coating and potting flash;
3. physical SGX rear port, pin pattern, body standoff and both gas paths;
4. membrane laminate/support/seal stack and required active area;
5. cable OD, water-block termination and potting fixture;
6. head retention, drainage orientation, coupon exchange and compost-cleaning
   access.

The membrane surface in the CAD is visual geometry only. A printed plastic disc
is not a substitute for the specified porous PTFE membrane.

## Response candidate

`o2_probe_response_candidate.scad` is a second, non-release communication model
derived from the lumped response study. It moves the cell toward the board tip,
uses a measured ≤5.0 cm³ local shrouded plenum, and replaces the remote axial disc
with two recessed, supported 10 × 10 mm PMV15T coupons on keyed lower-side facets,
one on each PCB side. The dry membrane face must be ≤0.25 mm from the local cavity.
The gross coupon area is 200 mm²; the design gate is ≥180 mm² measured free
area after supports. Dry-side carrier heaters are shown because the existing
remote cell-island heater cannot be assumed to warm the membrane.

Run `make response-candidate` to produce `exports/response-candidate.3mf` and
`exports/response-candidate-preview.png`. The concept is not printable release
geometry: window sealing, guard retention, board rearrangement, cable-side gas
seal and actual effective volume still require detailed design and measurement.
The two dark end-gasket frames make the required PCB-crossing seals explicit;
one continuous bond/overmould fill closes and displaces the radial shroud/tube annulus
zone. They do not constitute a released seal design. See
`RESPONSE-CANDIDATE-VOLUME.md` for the end-land-corrected approximately
4.99 cm³ first-order connected-void budget and the ≤5.0 cm³ measurement gate. The CAD
also includes one 0.4 mm PP cross support per coupon, representing about
184 mm² projected free area across both 10 × 10 mm apertures.
