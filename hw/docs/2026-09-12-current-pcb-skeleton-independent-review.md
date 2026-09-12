# Current Rev B PCB skeleton: independent review, 2026-09-12

This is an early review of the migrated 83-component design while ordinary routing is unfinished. It is not a completed-board review or fabrication acceptance. The durable inspected snapshot is `checks/current-skeleton-review/b7444ffc508a/o2-probe.kicad_pcb`, SHA-256 `b7444ffc508a390fa29af8cbfb4524ced46c3884eb39b92253f8ed762cb6f489`. Its baseline is `routing/revb-89-tmp302/o2-probe.kicad_pcb`, SHA-256 `4520074e475656a14fe82fea1ac86e2004d09b85485ee1155a594fc5e271b303`. Subsequent tip/MCU fixes and completed routing require fresh native verification.

## Findings and disposition

1. **MCU local circuits were eligible for route rip-up.** The initial `author_revb_mcu.py` track/via constructors left their items unlocked, while `route_revb_current.py` requests `--rip-existing-nets '*'`. In the pinned router source, `--keep-input-copper` protects post-route cleanup; it does not prevent the separate collateral rip-up selection. The initial native snapshot had zero locked items on each of ADC_AFE_VOUT, ADC_WE_BUF and ADC_RE_BUF. The latest adapter now calls `SetLocked(True)` in both constructors. Root reports all 55 authored items selected for preservation. The regenerated board still needs an exact native pre/post-route item comparison; a source fix does not establish that an older saved board has these locks.

2. **Guard and thermal copper are retained with deliberate geometry changes.** `migrate_revb_current.py` raises retained traces to at least 0.10 mm and retained vias to at least 0.40/0.20 mm. Native comparison found 113 surviving copper UUIDs changed, including driven-guard and lower sensor/thermal geometry. This is the requested manufacturing-profile migration, but it must not be described as exact copper preservation. Explicitly inventory allowed width/drill changes, recheck foreign-net spacing and guard shielding, and remeasure thermal copper crossings on the actual current geometry.

3. **The initial global 0.25 mm drill-to-copper floor overgeneralizes the written NPTH requirement.** `plans/REVB-AISLER.md` specifies 0.25 mm copper-to-round-NPTH and 0.30 mm copper-to-edge/NPTH-slot. The baseline generic hole-to-copper floor was 0.20 mm. Keeping that generic floor and adding the named NPTH conditions matches the written process intent; it must not suppress genuine NPTH violations. The installed KiCad manual defines `hole_clearance` from the drill rim, and `edge_clearance` includes Edge.Cuts plus oval pad holes. Thus retain global edge clearance 0.30 mm as well as the appropriate pad-specific rules. The generic 0.20 mm drill-rim clearance combined with a 0.10 mm via annulus permits the user's 0.10 mm copper spacing; a generic 0.25 mm would unnecessarily require 0.15 mm there. Validate scoped rules with native known-bad fixtures, including a round NPTH and a milled slot.

## Electrical review so far

The AP63203 power adapter connects local C1 directly to U1 VIN pin 3 and GND pin 4; pin 2 is EN, not VIN. The bootstrap capacitor connects BST pin 6 to SW pin 5 locally, with SW continuing to L1. This agrees with the manufacturer's pinout and avoids the misleading inference that a nearby unconnected EN pin is a missing VIN bypass. Final feedback routing and the poured output-capacitor return remain part of completed-layout review.

REF3425 force/sense pins are intentionally joined locally: OUT_S pin 5 to OUT_F pin 6 and GND_S pin 2 to GND_F pin 1. C10 closes the local output bypass loop, and C36 provides the input bypass. TI SBAS804G section 9.2.2.2 permits this three-terminal connection when lead IR drop is negligible or additional traces are unavailable. It is not remote Kelvin sensing. The shared VREF+ distribution and actual MCU/AFE/reference ground path still require review after routing and zone refill.

The MCU adapter explicitly places the three RC filter pairs near U6, routes the filtered nodes to MCU ADC pins, and supplies a local VREF+ reservoir and ground connection. Final verification should preserve those exact local paths, identify ground returns that depend on poured copper, and examine heater/supply return currents relative to MCU and AFE analog grounds. Topological connectivity alone does not bound heater-induced measurement offset. No numerical accuracy tolerance is inferred from ADC code width.

Routine unfinished opens are not new findings in this skeleton review. Native final connectivity, parity, DRC and filled-ground topology remain required.

## Physical hole inventory

Native pad inventory is unchanged from the baseline. These are actual pad drills; anonymous paste apertures are excluded.

| Feature | Drill / pad dimensions (mm) | Result against stated size or annulus floor |
|---|---|---|
| U11 pins 1–3 | Round drill 1.32, copper pad 2.00 | 0.34 mm annulus exceeds 0.30 |
| J101–J106 pin 1 | Round drill 0.85, copper pad 1.85 | 0.50 mm annulus exceeds 0.30 |
| J101–J104 relief | Round NPTH 2.20 | Exceeds 0.50 mm |
| J3 three mechanical holes | Round NPTH 0.9906 | Exceeds 0.50 mm |
| U11 central opening | Oblong NPTH 3.00 × 6.00 | Minor width exceeds 0.80 mm |

U7's four anonymous 1.05 × 1.05 mm pads are SMD, F.Paste only, zero drill and no copper. They are EP stencil apertures; changing them to satisfy a drill minimum would corrupt the footprint.

The native transverse Edge.Cuts slots occupy y117.25–118.75, with 1.50 mm width. Side slots occupy x100.8–101.6 and x118.4–119.2, with 0.80 mm width and rounded overall y121.0–137.0 extent. Do not use historic thermal-model coordinates around y133–135 to audit this shortened board. The table establishes hole-size and nominal annular-ring compatibility; it does not establish copper/hole spacing, registration tolerance, connector mechanical qualification or final mask geometry.

## Proposed current-design native verification contract

- Bind the exact generated schematic, exported netlist, migration and authoring scripts, project/rules, baseline and candidate hashes. Compare every numbered native pad against the current netlist; verify the exact 83-reference set, values, FPIDs and net assignments, including D8 K/pin 1 on VIN_MON and A/pin 2 on GND.
- Save the regenerated skeleton's protected native item inventory before routing. Compare UUID, net, layer, endpoints, width, drill, lock and relevant rule-area geometry after routing and refill. Treat removed or changed critical items as failures. Baseline-to-skeleton changes need their own explicit bounded review; they cannot be hidden by accepting the entire skeleton as historically identical.
- Assert concrete local connections for AP63203 input/bootstrap/output and feedback loops, REF force/sense and bypasses, MCU ADC RC pairs and VREF+ bypass, AFE bypass and cell protection, heater gate/cutoff. Where a return depends on a zone, inspect the filled polygon connection and actual return geometry; label any no-pour diagnostic accordingly.
- Inventory crossings and copper widths at the native thermal slots, preserve cell-interface pads and driven-guard continuity/placement, and recheck spacing after enlarged vias. Keep CELL_RE's stronger functional leakage constraint independently of the 0.10 mm generic spacing floor.
- Run native DRC with current profile, full unconnected-items and schematic parity reporting. Do not reuse the removed ADS1119/LDO checks or a 101-component expected inventory. Test the new scoped manufacturing constraints with actual failing native fixtures and fingerprint the checker's code as well as inputs.
- Review actual final copper/ground geometry and readable silkscreen before fabrication exports. Bind any completed-board review to the exact emitted artifact inventory and hashes. D8 leakage at 85 °C and physical heater-on/off measurement performance remain unqualified. Fab has retired the arbitrary D8 1 µA numerical selection gate and retained the part; do not reintroduce that gate as a release blocker.

The interpretation of custom-rule semantics above is based on the installed KiCad manual at `/Applications/KiCad/KiCad.app/Contents/SharedSupport/help/en/pcbnew.html`, sections for `hole_clearance`, `edge_clearance`, `hole_size`, `Pad_Type` and `Hole_Size_X/Y`. The electrical reference source is `/Users/fab/dev/ee/datasheets/TI-REF3425-SBAS804G.pdf`; the power agent's exact source/land-pattern notes are in `checks/power-layout/notes.md`.
