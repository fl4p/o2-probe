# Two-layer routed board, reduced BOM — provenance

**What this is.** The o2-probe routed on two copper layers by the Codex session (gpt-5.6-sol,
2026-09-05/06) against `AGENT-BRIEF.md`'s gate: 0 unconnected items, copper clean under the
project's own rules, zones refilled, route shape reported. Input was the 39-line BOM schematic and
`gen_pcb.py` at `fc84cfa` (100 footprints, 85 connected nets). Codex's own record is `README.md`;
its acceptance ledger is `acceptance-ledger.json`.

**Independent regrade (analysis session, 2026-09-06).** Board SHA-256 `e5518b69…` (matches
`README.md`). With the canonical `o2-probe.kicad_pro` / `.kicad_dru` beside it:

| refill path | unconnected | copper rule findings |
|---|---:|---|
| `kicad-cli pcb drc --refill-zones` | 0 | none |
| `pcbnew.ZONE_FILLER` then DRC | 3 GND records (2 zone–zone, 1 zone–track) | none |

**What differs from the generated design, and why it was accepted.**

- `critical_routes.py` here is Codex's rewrite (301 diff lines against the repo's). The repo's
  verifier reports 14 of its 57 locked items missing on this board: nine `/CELL_WE` tracks, two
  `/CELL_WE` vias, three `/GUARD_REPLICA` tracks. `/CELL_RE` is unchanged: one F.Cu polyline, no
  vias, guarded. Fab, 2026-09-06: "i never put these CELL_WE and guard rules, i dont care. if it
  works." The CELL_WE and guard-replica locks were agent-authored; waived.
- J105 and J106 use the project-local `SolderWireNoRelief_*` footprints in `lib/o2-probe.pretty`:
  the library part carries an unnumbered 2.2 mm relief NPTH 10.2 mm from origin that landed in the
  routing band (R41 at 0.185 mm against a 0.2 mm rule, on the unrouted seed).
- C34 rotated and moved (110.10, 127.50) → (110.10, 128.30) on B.Cu.
- Blocker tracks on `/HEATER_PWM`, `/+12V_SW`, `/HEATER_GATE` replaced by hand detours; four
  duplicate `/AFE_VOUT` segments and two GND stitch vias removed.
- `gen_pcb.py` was **not** updated: regenerating the board does not reproduce this copper. This
  directory is the board; the generator is the placement.

**Not release-ready.** `drc-final.json` keeps 41 non-copper warnings (16 courtyard overlaps, 13
silk overlaps, 11 silk over copper, 1 silk to edge) and schematic parity adds 13 (seven stale
symbol fields, three footprint-filter warnings, the two J105/J106 substitutions, the existing U6
pad-21 conflict). `FAB-READINESS.md` governs release, not this file.

**Where the rest went.** The four other sessions' boards (best 9–20 signal opens, authored copper
intact), their write-ups and tools: `~/dev/ee/hw/o2-probe-2layer-archive/`. Skill-level lessons:
`~/dev/ee/kicad-design/reviews/2026-09-05-cross-session-routing-evidence.md`.
