# Current Rev B route ownership

Circuit: 83 components, native schematic parity checked on 2026-09-12.
Outline: retained 20 x 89 mm, two copper layers, 1.6 mm board.

Both F.Cu and B.Cu prefer the long Y axis. Both carry ground pours; neither
is an uninterrupted reference plane. Short local X connections are allowed
inside component clusters. Through vias are 0.40/0.20 mm minimum. Ordinary
trace/spacing minima are 0.10/0.10 mm by explicit user override. The remaining
process limits and stronger CELL_RE leakage rule are retained.

The committed 89 mm TMP302 geometry supplies the cell interface, outline and
thermal isolation layout. Its smaller vias and narrow tracks need explicit
process migration; this is not exact copper preservation. Critical repairs
are recorded separately. The actual saved board must pass native DRC and a
review of guard/thermal crossings after those edits.

Hand-authored owners: power/bootstrap/reference, local bypass and analog rail
filter, MCU ADC filters/reference bypass, cell/guard/heater/thermal skeleton.
KRT owns routine connections around this fixed copper. The entrypoint pins
router commit, source hash, flags, via cost, long-axis direction preferences,
and project-rule fingerprints. A separate exploratory scout is never promoted.

Current acceptance: PCB implementation complete, 2026-09-12. Native0errors/0opens/0parity and explicit independent review are in `evidence/final/`. The exact source and successful fabrication exports are bound by `fab/o2-probe-revb-current-8eef4aa26e24a6cb/fab-manifest.json` from the project root. Both intentional guard endpoints and ten assembly courtyards remain visible. The implemented plan is archived. D8 is retained by the documented design decision; its digitized typical-curve estimate remains provisional. Procurement, firmware sampler port and first-article qualification remain separate work.
