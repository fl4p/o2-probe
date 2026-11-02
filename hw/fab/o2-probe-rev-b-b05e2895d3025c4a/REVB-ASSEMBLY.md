# Rev B manual-assembly review

This record applies to `routing/revb-interfaces/o2-probe.kicad_pcb` after
`finish_revb_layout.py`. It replaces the Rev A exception table for this candidate.
The 15 courtyard warnings remain enabled and visible. They are individually
reviewed for manual assembly; this is not automated-assembly qualification.

The following are nominal distances derived from the routed board's Fab outline
centerlines and copper pad polygons, excluding nonplated holes. These are CAD
measurements, not measured component tolerances. The cable footprint's outline
is a wire-dressing envelope, not a rigid body. L1 uses the conservative outer
rectangle drawn in its footprint; test pads have no component body.

| Pair | Nominal body/envelope gap (mm) | Pad gap (mm) | Disposition |
|---|---:|---:|---|
| C14/C26 | 1.200 | 0.350 | Courtyard margin; no nominal body/land interference |
| D1/J102 | 1.650 | 10.675 | Courtyard margin; no nominal body/land interference |
| D1/J101 | 2.065 | 10.838 | Courtyard margin; no nominal body/land interference |
| R10/R11 | 0.788 | 0.383 | Courtyard margin; no nominal body/land interference |
| C3/L1 | 0.750 | 0.300 | Courtyard margin; no nominal body/land interference |
| C7/C8 | 0.849 | 0.446 | Courtyard margin; no nominal body/land interference |
| C1/U1 | 1.006 | 0.231 | Courtyard margin; no nominal body/land interference |
| C5/U2 | 1.500 | 0.425 | Courtyard margin; no nominal body/land interference |
| J104/R3 | 0.000 | 2.350 | Raised/laterally dressed cable; inspect before potting |
| D2/J103 | 0.100 | 2.387 | Raised/laterally dressed cable; inspect before potting |
| D2/J104 | 0.000 | 2.331 | Raised/laterally dressed cable; inspect before potting |
| TP3/U4 | — | 0.514 | Courtyard margin; no nominal body/land interference |
| J103/R2 | 0.000 | 2.350 | Raised/laterally dressed cable; inspect before potting |
| C4/C7 | 1.300 | 0.400 | Courtyard margin; no nominal body/land interference |
| Q2/TP6 | — | 0.915 | Courtyard margin; no nominal body/land interference |

## Required assembly operations

J103's conductor envelope overlaps R2's body and solder lands. J104's envelope
overlaps R3 and touches D2's body outline; J103's envelope is only 0.100 mm from
D2. Dress both actual insulated conductors clear of R2/R3/D2 and their joints,
without pressing on component edges. Inspect before potting. Actual cable
outside diameter, bend shape, strain relief and clearance must be checked on
the first article. No new interface dimension is assumed here.

The J103/J104 land and relief-hole geometry is unchanged. Their long wire-envelope
silkscreen lines are moved to F.Fab in the explicit local
`SolderWire_RaisedRelief_1x01` footprint. The envelope and conservative courtyard
remain in the assembly drawing and DRC; the crossing lines are no longer ink.

R17 is relocated from (105.0, 127.0) to (105.8, 121.8) mm, above U4, removing
its courtyard overlap and the previous 0.025 mm U4-body-to-R17-land gap. The
new nominal body gap is 3.033 mm, body-to-land gap 2.664 mm, and courtyard
gap 0.814 mm. Its
signal joins the existing MENB trunk at (104.9, 123.3); a ground stitch at
(105.1, 120.6) stays outside the solder land. No sensitive analog route moves.

The cell-body circle moves from silk to F.Fab. Potting/gas-path process text
and the back-side potting boundary line move to User.Drawings, including the old note
outside the board outline. Use the included front/back assembly PDFs: pot only to the marked
boundary and keep the cell gas path and aperture unobstructed. Connector and
WE/GUARD/CE/GND/VREF/TMP_CELL legends remain printed at their existing positions.

Inspect all nominal clearances, joints and test-point access on the first article.
The draft J5 ring interface, SGX cell fit/pin identity/gas path, and thermal,
leakage/compliance and ESD qualification remain open; this review does not close them.
