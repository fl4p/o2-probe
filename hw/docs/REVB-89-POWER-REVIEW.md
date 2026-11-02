# Rev B 89 mm power compaction — 10 September 2026

The [candidate](../routing/revb-89/o2-probe.kicad_pcb) measures 20 × 89 mm,
4 mm shorter than the retained [93 mm board](../routing/revb-93/README.md).
The cable end stays at absolute Y=50 mm; the tip is now Y=139 mm.

U2, U3, C5, C6, C7, C8, C27 and R32 move together to the back. Their global
pad coordinates follow x′=x, y′=167−y (millimetres), preserving the mirrored
component arrangement. Other components at source Y≥88 mm move toward the
cable by 4 mm. Input protection, U1, L1 and C1–C4 remain in place. All 13
BUCK_SW/BUCK_BST copper objects retain their exact source geometry and widths.
All 99 footprints and 299 assigned physical pins remain present.

The local power, RS-485, CE_MON and AFE_MENB connections are rerouted. Local
power and RS-485 additions use 0.18 mm tracks; the two control/sense nets use
0.09 mm. The new routing uses 0.25/0.15 mm vias. Unused branches were removed
only after checking pad connectivity. A ground via at (106.525,77.875) mm
rejoins the final isolated ground section. All buck and LDO capacitor ground
pads are in one connected copper component after refill. C8 uses a revised
back-only supply path; the source used a two-via path. This is a CAD connectivity
result, not measured equivalence of bypass impedance or analog noise.

Cell, RH1/RH2, aperture, thermal slots and lower critical routes translate
rigidly by 4 mm. The 93 mm tip shape and heater-spreader geometry remain
unchanged relative to that region. The closer placement behind the inductor
requires the existing analog-noise and thermal qualification before release.
This remains engineering review, with `order_ready: false`; procurement and
physical qualification gates remain open. J5/F3 remain optional Rev C work.

The acceptance profile permits exactly 15 documented manual-assembly courtyard
warnings: the prior C4/C7 overlap disappears because they are now on opposite
sides. It does not relax clearances or suppress other DRC findings. Reports
under `routing/revb-89/review/` record saved-fill and refilled DRC, ERC, parity,
Gerber outline/thermal contours, drills and source fingerprints.

Independent bounded review found no remaining blocking CAD or guard issue.
It confirmed exact buck copper, connected bypass grounds and critical geometry.
Two guard omissions (mirrored pad offset/delta and footprint side) were fixed;
independent corrupted-board checks now reject those mutations.

## Acceptance guard review

The existing [eight-point guard contract](REVB-95-REVIEW.md#acceptance-guard-review)
applies, extended as follows:

1. Missing source/export data, changed source hashes or unsupported profiles
   raise errors; they cannot produce a clean manifest.
2. Exact geometry/profile comparisons reject both near and large deviations;
   the 89 and 93 mm boards cannot pass each other's profile.
3. The export builder invokes native verification and both DRC passes using
   the explicit power profile before promoting exports.
4. It fingerprints the board, pinned comparison sources, validators, builder,
   seed generator, tests and this review document before and after validation.
5. A failed build does not replace the prior review directory or cache success.
6. The manifest reports executed commands and engineering-review scope;
   the placement seed is explicitly unrouted.
7. `test_revb_power.py` calibrates rejection of changed pad offset, incorrect
   footprint side, missing BUCK_SW copper and mismatched outline/courtyard
   profiles, alongside the real candidate acceptance check.
8. The geometry and routing changes remove the space requirement; the guard
   verifies those quantities. Rule-file hashes remain unchanged.

Native geometry verification takes approximately 0.6 seconds on this host.
The export manifest records measured full-build runtime and exact tool version.

`compact_revb_power.py --output /tmp/new-revb-power` creates an unrouted seed
from the pinned 93 mm source and refuses an existing output directory. The
committed board is the authored, locally routed result; the seed does not
reconstruct subsequent routing. Revalidate it before any use.
