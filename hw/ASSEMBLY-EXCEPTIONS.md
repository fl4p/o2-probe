# Rev A manual-assembly exceptions

This revision is for bare-board first articles and hand assembly, not automated
turnkey PCBA. KiCad reports 20 `courtyards_overlap` pairs and **zero**
`pth_inside_courtyard` / `npth_inside_courtyard`; all three checks are
configured `warning`/`error`/`error` and nothing is `ignore`, so that empty
enumeration is clean rather than unevaluable. The exact pair set is locked by
`audit_pcb.py` and matches this table with no strays in either direction.

Each pair is dispositioned individually below, with its own measured numbers —
courtyard intersection area, F.Fab **body** intersection area, body gap and
closest pad gap — because a grouped verdict can hide an outlier. Every pair is
**same-side**, so no height or standoff argument clears any of them. Measured
2026-09-04 from `newboard.kicad_pcb`.

| Pair | Side | Courtyard ∩ (mm²) | Body ∩ (mm²) | Body gap (mm) | Pad gap (mm) | Branch | Disposition |
|---|:--:|---:|---:|---:|---:|---|---|
| C1 / U1 | F | 0.200 | — | 0.873 | 0.200 | margin only | bodies and pads both clear |
| C14 / C26 | B | 0.217 | — | 1.100 | 0.350 | margin only | bodies and pads both clear |
| C25 / J2 ¹ | F | 0.619 | — | 0.125 | 0.185 | margin only | bodies and pads both clear |
| C3 / L1 | F | 0.606 | — | 0.650 | 0.300 | margin only | bodies and pads both clear |
| C5 / U2 | F | 0.206 | — | 1.400 | 0.425 | margin only | bodies and pads both clear |
| D1 / J101 | F | 0.150 | — | 1.550 | 1.285 | margin only | bodies and pads both clear |
| D1 / J102 | F | 1.162 | — | 1.550 | 0.300 | margin only | bodies and pads both clear |
| D2 / J103 | F | 2.304 | — | bbox only | 2.234 | margin only | bounding boxes overlap, drawn outlines do not |
| D2 / J104 | F | 2.586 | 0.1387 | overlap | 2.183 | wire envelope | J1.4's relief channel clips D2's body outline |
| D4 / R12 ¹ | B | 0.153 | — | 1.337 | 0.350 | margin only | bodies and pads both clear |
| D5 / R14 ¹ | B | 0.078 | — | 1.337 | 0.350 | margin only | bodies and pads both clear |
| D6 / J2 ¹ | F | 0.253 | — | 2.310 | 0.615 | margin only | bodies and pads both clear |
| J103 / R2 | F | 4.277 | 0.6132 | overlap | 2.350 | wire envelope | J1.3's relief channel runs over R2's body |
| J104 / R3 | F | 4.277 | 0.5095 | overlap | 2.350 | wire envelope | J1.4's relief channel runs over R3's body |
| J2 / TP1 ¹ | F | 0.734 | 0.1150 | overlap | 1.447 | provisioning | J2 is DNP; fitted, its body covers TP1 (CELL_WE) |
| J2 / TP5 ¹ | F | 0.734 | 0.1451 | overlap | 0.645 | provisioning | J2 is DNP; fitted, its body covers TP5 (GUARD) |
| Q2 / TP6 | B | 0.047 | — | 1.652 | 0.900 | margin only | bodies and pads both clear |
| R10 / R11 | B | 0.290 | — | 0.688 | 0.300 | margin only | bodies and pads both clear |
| R17 / U4 | F | 1.387 | 0.0205 | overlap | 0.309 | graze | 0603 body clips the VSSOP-8 outline corner |
| TP3 / U4 | F | 0.133 | — | 2.552 | 0.285 | margin only | bodies and pads both clear |

¹ at least one member is DNP.  
"bbox only" means the two footprints' Fab bounding boxes overlap while the
drawn outlines do not — an artifact of rotated parts, not interference.

**margin only (14 pairs).** The conservative courtyard envelopes touch; the
drawn bodies do not intersect at all and pads clear by 0.185–1.285 mm. The
envelopes are intentionally conservative and are not shrunk to silence the DRC.

**wire envelope (3 pairs).** J101–J104 are `SolderWire-…-Relief` lands, so
their F.Fab geometry is not a rigid body — it is the channel reserved for the
1.7 mm OD insulated conductor. That channel runs over R2 and R3 (0603 10R) and
clips D2 (SM712, SOT-23). Pads clear by ≥2.18 mm, so there is no copper
problem; what the finding says is that two hand-dressed cable conductors do not
lie flat on bare laminate but cross component bodies. Accepted for hand
assembly **with a build instruction**: dress J1.3 and J1.4 clear of R2/R3/D2
before potting, so no conductor is loaded against a component edge.
`D2 / J103` is margin only — its bounding boxes overlap but the outlines do not.

**provisioning (2 pairs).** J2 is DNP on every current build, so there is no
as-built interference. Recorded as a live constraint rather than closed:
**fitting J2 buries TP1 (`CELL_WE`) and TP5 (`GUARD`)** under its body. Those
are two of the six probing points, so J2 and full test-point access are
mutually exclusive as currently placed. If J2 is ever populated, either move
those test points or accept losing them.

**graze (1 pair).** R17's 0603 body clips the corner of U4's VSSOP-8 outline by
0.0205 mm² with 0.309 mm of pad clearance — placement and rework are
unaffected at this scale.

Six pairs from the previous revision are gone, for two unrelated reasons worth
recording so they are not treated as regressions if they reappear. C11 / C12,
C15 / R8 and C15 / R9 went when those three 100 nF capacitors were consolidated
onto the 0402 land every other 100 nF on the board already used. C31 / RV1,
R20 / RV1, R38 / RV1 and R22 / R23 went with the trim divider that `POTTING.md`
1.2 deleted. Nothing was added: the new ground test point TP2 was sited at the
one position that clears every courtyard outright while still leaving all six
test-point legends placeable, so the exception list got shorter, not longer.

Inspect component-body, hand-solder, and rework clearance on the first article.
J5 is a separate manual operation: inspect both plated castellation sidewalls,
verify ring material/plating, use controlled heat and flux, prevent solder
wicking into the membrane carrier, and inspect dry-side electrical insulation
before power is applied.

U11 is also a physical gate: fit an actual SGX-OX-ROHS-Mini, verify pin identity
from the PCB side, and confirm the rear gas path against the 3 × 6 mm NPTH
aperture. Any automated assembly release needs a new courtyard/process review.
