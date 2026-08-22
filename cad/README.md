# O₂ probe Rev-A 3D model

This directory contains a parametric mechanical study of the buried compost
oxygen probe. The OpenSCAD source and browser model use the same Rev-A concept:

- 32 mm OD / provisionally 28 mm ID PVC-U enclosure, 135 mm long;
- actual 20 × 125 × 1 mm PCB datum and SGX cell location;
- removable PMV15T coupon carrier with PP support grid;
- passive, drained and side-vented diffusion head with a coarse-debris guard;
- cable-end cap with PCB slot and an offset 6.4 mm cable passage.

Run `make all preview` in this directory to regenerate the meshes and preview.
The generated `exports/` directory contains the five individual parts plus a
colour-capable 3MF assembly.

## Model status

This is **not fabrication-release geometry**. The PCB dimensions, pot datum,
cell centre and SGX body dimensions are controlled project values. The tube ID,
135 mm body length, slip fits, membrane active area, carrier pocket, cable bore,
head retention and guard details are provisional interfaces chosen to make a
complete Rev-A fit model.

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
