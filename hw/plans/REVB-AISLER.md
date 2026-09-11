# Rev B Aisler adaptation

Status: in progress, 2026-09-11. User selected Aisler and requested the fix.
Baseline: committed TMP302 candidate `routing/revb-89-tmp302/` (9c2832c).
Do not order that baseline from Aisler: its clean DRC used incompatible limits.

## Process and scope

Target Aisler 2-layer, 1.6 mm, 35 µm copper, ENIG. Retain 20 × 89 mm outline
and circuit if routable. The 1.0 → 1.6 mm change is part of this adaptation;
actual enclosure/potting fit and thermal conduction must be checked on the
first article and are not assumed qualified by CAD.

Official source, checked 2026-09-11:
https://community.aisler.net/t/2-layer-1-6mm-35-m-enig-design-rules/3732
and https://community.aisler.net/t/pcb-portfolio/101 . Real rendered content
retrieved through isolated Playwright; no outstanding access challenge.

Required floors: track/spacing 0.125/0.125 mm; via drill 0.25 mm with 0.10 mm
annular ring (0.45 mm diameter); copper to edge/NPTH slot 0.30 mm; copper to
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
   layers with GND pours; prefer the long Y axis on both, with local transverse
   crossings. Use only through vias, minimum 0.45/0.25 mm. Capture actual router
   options/version, seed and accepted output; never promote scout geometry.
5. Validate fresh saved/refilled DRC, ERC/parity, manufacturer geometry,
   guard/thermal structure and fabrication exports. Independent review, fix
   findings, then commit the candidate and open it in KiCad.

## Layout log

2026-09-11: Isolated checkout `/tmp/o2-aisler-astra-0911`, source HEAD 702f0b0.
The prior TMP302 candidate is preserved. No manufacturing waiver is assumed.
A clean Aisler DRC is required; board expansion is not the initial strategy.
