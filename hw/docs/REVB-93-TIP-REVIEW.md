# Rev B 93 mm tip trim — 10 September 2026

Fab requested a further 2 mm reduction at the tip of the 95 mm candidate.
The [new board](../routing/revb-93/o2-probe.kicad_pcb) measures 20 × 93 mm;
the cable end remains at absolute Y=50 mm and the tip moves from Y=145 to 143 mm.
The [95 mm comparison](../routing/revb-95/README.md) remains unchanged.

All 99 component positions, orientations, sides and pad/drill geometry stay
fixed, including the cell interface, aperture and RH1/RH2. The four thermal
slots and the main heater current tracks remain unchanged. This cut reduces
the tip substrate and heater-spreader area; it is not a claim of unchanged
thermal performance. Native filled heater-spreader area changes from 255.857 to
227.156 mm² (−11.22%). Existing physical/thermal qualification remains open.

Eleven ground copper items intersecting the removed strip/edge clearance were
removed. A 0.25/0.15 mm ground via at (111.35, 138.825) mm reconnects the affected
ground region. Three I2C_SDA segments at the tip retreat to Y=142.7 mm to retain
edge clearance. The TMP_CELL silkscreen label moves to (104.5, 142.2) mm.
No component movement or design-rule relaxation is used.

Validation and exports use `python3 make_review_revb_95.py --tip-trim-mm 2`.
The filename retains its original name; the explicit option selects
`routing/revb-93/` and a 93 mm acceptance profile. Without the option it still
checks/exports the 95 mm board. The native check additionally compares every
footprint/pad against the pinned 95 mm source. Gerbers must have the exact new
outline while retaining the same thermal-slot contours. DRC/ERC, pin parity,
drills, source fingerprints and input-drift rejection retain the existing
[guard contract](REVB-95-REVIEW.md#acceptance-guard-review).

This remains an engineering-review candidate, not order-ready. J5/F3 remain
optional Rev C work. See `routing/revb-93/review/` for current check reports,
assembly drawings and source hashes.

Independent bounded review found no blocking geometry/code issue. Side-slot
ends retain a 2 mm tip ligament; the nearest U10 copper retains 1.275 mm,
and the adjusted I2C_SDA route retains 0.21 mm copper-to-edge clearance.

`trim_revb_tip.py --output /tmp/new-revb-tip` reproduces the trim and local
ground/I2C/silk adjustments from the pinned 95 mm source into a fresh directory.
It refuses to overwrite an existing directory. Validate that result before use.
