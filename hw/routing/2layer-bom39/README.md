# o2-probe two-layer routing handoff

Date: 2026-09-06

Status: **routing complete against `AGENT-BRIEF.md`**. This is the private
39-line-BOM board: 100 footprints, 85 connected nets, and two copper layers.

## Deliverable

- `o2-probe.kicad_pcb` — final routed and refilled board
- `o2-probe.kicad_sch`, `o2-probe.kicad_pro`, `o2-probe.kicad_dru` — matching
  BOM39 schematic, canonical project, and project rules
- `drc-final.json` — final KiCad DRC after a refill-and-save cycle
- `collisions-final.json` — independent effective-shape copper collision audit
- `route-shape.json` — required route-shape measurement
- `exact-duplicate-audit.json` — exact stacked track/via audit
- `render-top.png`, `render-bottom.png` — inspected 3D renders
- `copper-top.png`, `copper-bottom.png` — inspected copper plots
- `verify_critical.py`, `critical_routes.py`, `thermal_design.py` — pinned
  critical-copper verifier and its dependencies

The canonical project MD5 is `1b3814984628f69d9a377f7f18ed3125`.
The final board SHA-256 is
`e5518b691b8e102b25d7eba50df3a84a05001f40fe1d0e0a043a1fe01b1ee3da`.

## Frozen acceptance ledger

| Original requirement | Final evidence | Verdict |
|---|---|---:|
| Two copper layers | board reports 2 | PASS |
| Zero unconnected items | signal 0, GND islands 0, aggregate total 0 | PASS |
| Copper DRC clean under project rules | no clearance, short, crossing, hole-clearance, edge-clearance, dangling, isolated-copper, or disallowed-item findings | PASS |
| Zones refilled | final board was refilled and saved, canonical sidecars restored, then DRC'd again | PASS |
| Route-shape tool run | `route-shape.json` | PASS |

The split is retained even at zero: **0 signal opens / 0 refill-dependent GND
pour islands / 0 total**. Ranking on signal opens never weakened the literal
zero-total completion criterion.

## Independent checks

- KiCad 10 DRC: 0 unconnected and 0 copper findings.
- Independent effective-shape audit: 0 collisions across 1,962 copper items.
- Critical copper: 63/63 essential items present and locked. The verifier also
  confirms that CELL_RE has no vias, stays on F.Cu, preserves its leakage
  clearance, and remains guarded.
- Exact stacked geometry: 0 duplicate track/via groups.
- Route shape, report-only because the project has no calibrated thresholds:
  54 routed nets, 269 vias, 1,112 segments over 2,002.47 mm, median segment
  1.062 mm, and 10% of segments shorter than 0.2 mm.
- Top, bottom, and copper-plot review found no outline/slot intrusion or visible
  placement corruption.

## Deliberate local changes

- J105 and J106 use project-local one-hole, no-relief wire footprints. This
  removes the unnumbered remote NPTH pads that landed in the routing band.
- C34 was rotated and moved from `(110.10, 127.50)` to `(110.10, 128.30)` on
  B.Cu. Its CE_MON pad lands on the existing CE_MON copper and its GND pad lands
  in the connected plane, eliminating the last GND island without adding a
  signal detour.
- Local blocker tracks on HEATER_PWM, +12V_SW, and HEATER_GATE were replaced by
  legal exact-shape detours while preserving connectivity. The essential
  authored-copper audit remains fully green.
- Four exact duplicate AFE_VOUT segments and two redundant too-close GND stitch
  vias were removed.

## Findings outside the routing gate

`drc-final.json` intentionally keeps 41 non-copper warnings visible: 16
courtyard overlaps, 13 silkscreen overlaps, 11 silkscreen-over-copper warnings,
and one silkscreen-to-edge warning. Schematic parity adds 13 warnings (seven
stale symbol-field values, three footprint-filter warnings, two intentional
J105/J106 footprint substitutions, and one existing U6 pad-21 net conflict).
These do not invalidate the routing brief, but this package is not claimed as a
fabrication release until they are reviewed by the project owner.

## Reproduce the routing gate

Run from this directory:

```sh
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc \
  --severity-all --schematic-parity --refill-zones --format json \
  -o drc-final.json o2-probe.kicad_pcb
./split.py o2-probe.kicad_pcb
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  verify_critical.py o2-probe.kicad_pcb --expect-locked --essential-only
```
