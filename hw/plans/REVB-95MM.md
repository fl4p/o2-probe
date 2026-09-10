# Rev B 95 mm compaction

Authorized by Fab on 10 September 2026 after reviewing the 107 mm candidate.
Target: 20 × 95 mm, two copper layers, unchanged circuit/BOM. Work is isolated
in `routing/revb-95/`; `routing/revb-interfaces/` remains the 107 mm comparison.

The cable-end power and MCU IC placements remain fixed; nearby passives may move. The analog section from local
Y=66 mm onward, including the cell, heaters, thermal slots, gas aperture and
potting boundary, translates by −12 mm as a group. Intervening test/programming
contacts and passives are repacked across both faces. Enclosure length/retention
must be checked against this new board; no physical interface measurement is
inferred from the PCB file.

Routing intent: retain the reviewed cable/power, MCU escapes and lower analog/
cell copper wherever it stays outside the repacked band. Lock that retained
copper while routing the changed middle. Both F.Cu and B.Cu remain routing
layers with the existing ground pours; no extra layer or relaxed design rule.
Keep CELL_RE on F.Cu without vias and retain its guard/leakage clearance.
Keep the wide main-heater current path unchanged within the translated island.

Acceptance: schematic parity and full pin/value inventory; 20 × 95 mm outline;
rigid preservation of cell/slot/heater geometry; saved/refilled DRC with zero
copper errors and zero opens; original design rules; reviewed assembly/silk;
exported copper/drills and a clearly identified comparison board in KiCad.
The previous procurement and physical qualification gates remain applicable.

Status: implemented as a separate routed review candidate. See
[review results and remaining physical gates](../docs/REVB-95-REVIEW.md).
