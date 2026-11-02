# Rev B schematic and process adaptation — implemented

Archived 2026-09-12 after current83-part PCB closure, independent review and successful fabrication export. Final native checks have0errors,0opens and0schematic mismatches. The20×89mm outline, two layers and1.6mm profile are retained with the user's trace/spacing/via overrides. This archives PCB implementation; procurement, firmware sampler and first-article qualification remain separately open.

See the [final independent PCB review](../../2026-09-12-current-pcb-independent-review.md), [artifact review](../../2026-09-12-current-artifact-review.md) and [current board](../../../routing/revb-current/o2-probe.kicad_pcb). The historical work plan follows unchanged.

---

# Rev B Aisler adaptation

Status: in progress, updated 2026-09-12. User selected Aisler and requested the fix.
The 2026-09-12 schematic update (68e6bde) supersedes the candidate circuit.
PCB parity and release review must be re-established against the corrected new schematic.
Baseline: committed TMP302 candidate `routing/revb-89-tmp302/` (9c2832c).
Do not order that baseline from Aisler: its clean DRC used incompatible limits.

## Process and scope

Target Aisler 2-layer, 1.6 mm, 35 µm copper, ENIG. Retain the 20 × 89 mm outline. Adopt the updated schematic: AP63203 3.3 V
buck, R32-filtered AFE rail, REF3425 reference and MCU ADC, with U8 removed. The 1.0 → 1.6 mm change is part of this adaptation;
actual enclosure/potting fit and thermal conduction must be checked on the
first article and are not assumed qualified by CAD.

Official source, checked 2026-09-11:
https://community.aisler.net/t/2-layer-1-6mm-35-m-enig-design-rules/3732
and https://community.aisler.net/t/pcb-portfolio/101 . Real rendered content
retrieved through isolated Playwright; no outstanding access challenge.

User override, 2026-09-12: minimum track/spacing **0.10/0.10 mm**; minimum
via drill **0.20 mm** with retained 0.10 mm annular ring (**0.40 mm diameter**).
These three minima override the Aisler rules; describe the result as a user-overridden
engineering profile, not standard Aisler compliance. Other retained limits: copper to edge/NPTH slot 0.30 mm; copper to
round NPTH 0.25 mm; hole-to-hole 0.30 mm; PTH annular ring 0.30 mm; NPTH drill
0.50 mm, slot width 0.80 mm. Check pinhole classification and mask/paste separately.
Retain stronger analog leakage constraints. Native board count found 1,558 track
segments below 0.125 mm and 259 via drills below 0.25 mm in the baseline.

## Work and routing ownership

1. Establish explicit Aisler rules and inspect all transformed footprint pads,
   holes, slots and keepouts; fix placement/land problems before area routing.
2. Run a disposable router scout under the actual Aisler dimensions.
3. Author/preserve the critical skeleton: CELL_RE and driven guard, CELL_WE,
   heater power/thermal-barrier crossings, buck switch/bootstrap and local
   supply/decoupling connections. Adapt via dimensions with reviewed geometry.
4. Route routine digital/monitor connectivity around that skeleton using the
   project's existing KRT/Freerouting allowance. F.Cu and B.Cu are both signal
   layers with GND pours. Establish the return corridors and sensitive analog
   routes before routine routing. Use only through vias, minimum 0.40/0.20 mm. Capture actual router
   options/version, seed and accepted output; never promote scout geometry.
5. Validate fresh saved/refilled DRC, ERC/parity, manufacturer geometry,
   guard/thermal structure and fabrication exports. Independent review, fix
   findings, then commit the candidate and open it in KiCad.

## Layout log

2026-09-11: Isolated checkout `/tmp/o2-aisler-astra-0911`, source HEAD 702f0b0.
The prior TMP302 candidate is preserved. No manufacturing waiver is assumed.
A clean Aisler DRC is required; board expansion is not the initial strategy.


## Restart after the schematic change and lost temporary work

2026-09-12: `/tmp/o2-aisler-astra-0911` and the uncommitted final candidate/review
artifacts are absent after the reboot. The worktree registration is prunable;
no previous zero-open result is accepted as evidence for surviving files.
The persistent working checkout is `/Users/fab/dev-worktrees/o2-revb-current`.
The committed TMP302 board remains the recoverable geometry baseline.

Before footprint transfer, close the newly identified D8 polarity/package error
in the schematic generator. Schematic owner `revb-ee` and PCB owner
`codex-farming-h7ln` coordinate on channel `revB`. The independent migration
assessment is `docs/2026-09-12-68e6bde-routing-migration-independent-review.md`.

1. Freeze the corrected generator, schematic, exported netlist and symbol/footprint
   identities. Recheck ERC and the source-to-exported-netlist audit. Do not edit
   the user's open generated schematic.
2. Account for 21 removed references and three added references (D3, D8, C36),
   U15's SOT-23 to SOT-23-6 change and C26's 0603 to 0402 change. Preserve the
   declared ground rename `/GND` to `GND` without conflating other net names.
3. Rebuild the input-protection, supply, reference and MCU analog local connections.
   Remove obsolete copper deliberately; a removed footprint does not remove its
   routes. Place the three retained RC filters at their new MCU destinations.
4. Measure current placement lane capacity before any rip-up campaign. Retain the
   outline, cell interface and thermal structures; author the critical skeleton
   and return corridors. Bound and log any router scout and route pass.
5. Re-run full native connectivity/parity/DRC and the applicable critical-circuit,
   thermal, geometry and visual checks on the actual resulting PCB. Obtain an
   independent review, fix findings, then build fresh bound fabrication artifacts.

This remains an active plan. Neither the lost implementation nor the new schematic
has closed the current PCB, firmware-sampler or physical qualification gates.
