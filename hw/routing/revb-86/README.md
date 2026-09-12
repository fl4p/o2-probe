# Rev B — 20 × 86 mm

The user-requested Y compaction removes 3 mm from the unused cable-end margin of the accepted 89 mm board. `o2-probe.kicad_pcb` is the routed native candidate; its adjacent project, rules and schematic form its verification context. The previous 89 mm board and its fabrication package remain under `routing/revb-current/` and `fab/o2-probe-revb-current-8eef4aa26e24a6cb/`.

All 83 component/pad records, 195 vias, tracks, holes and thermal slots retain their positions. The only intended non-fill changes are five top-outline primitives and the CABLE annotation. `trim_revb_y.py` derives this candidate from the exact accepted source, with no autorouting.

The schematic and process profile are unchanged: two copper layers, 1.6 mm nominal thickness, 0.10 mm minimum trace and copper spacing, 0.20 mm minimum via drill with 0.40 mm diameter. The result uses the user-overridden process profile, not standard Aisler-compliance certification.

See `docs/2026-09-12-revb-86-compaction.md` and the independent review from the project root. Manufacturing, assembly and first-article qualifications retain their existing scope; shrinking unused margin does not close those checks.
