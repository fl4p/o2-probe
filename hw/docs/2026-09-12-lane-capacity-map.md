# 2026-09-12 — Is the Rev B placement routable under the new rules? (lane-capacity map)

**Question.** The Aisler re-route session (Codex `01a08f49…`) produced 698
board variants under `/tmp` between 2026-09-11 11:47 and 2026-09-12 09:25.
Before spending more on candidates: does the placement have enough corridor
capacity under the rules at all, and what did the rule change actually cost?

**Tool.** `~/.claude/skills/kicad-design/scripts/kicad_lane_capacity.py`,
written today, calibration in the skill's
`reviews/2026-09-12-lane-capacity-map.md`. Cross sections every 0.5 mm along
the board; per layer, lanes that fit between pads, holes, keepouts and the
edge; against that, the nets that must cross because they have pads on both
sides. Demand is a lower bound, capacity is optimistic, so a ratio near 1 is
already infeasible.

## Inputs

| | |
|---|---|
| source board | `routing/revb-89-tmp302/o2-probe.kicad_pcb` (routed under the old rules, 283 vias) |
| latest candidate | `/private/tmp/o2-bus-review-ground-leaf/o2-probe.kicad_pcb`, 09:25, DRC-clean under the override, 210 vias |
| old rules | 0.09 track / 0.15 clr / 0.25-0.15 via / 0.20 hole clr / 0.20 edge |
| aisler rules | 0.125 / 0.125 / 0.45-0.25 / 0.25 / 0.30 |
| override (Fab, 00:47) | 0.10 / 0.10 / 0.40-0.20 / 0.25 / 0.30 |
| pour | `/GND` excluded from demand; B.Cu optionally reserved |

## Findings (measured)

1. **Not capacity-bound anywhere.** Worst cross section is the 5 mm
   thermal-barrier neck at y ≈ 118 mm, carrying +12V_SW, 3V3D, HEATER_PWM,
   I2C_SCL/SDA, CELL_CE/RE/WE. With B.Cu wholly reserved for the pour, F.Cu
   alone is at 0.73 (old), 0.84 (aisler), 0.70 (override) of capacity there.
   Using both layers: 0.36 / 0.42 / 0.35. Along the length: 0.07.
2. **The override is looser for tracks than the old rules** (0.70 vs 0.73 at
   the neck). Its cost is via room: each via blocks a 0.76 mm strip on both
   layers instead of 0.66 mm; 283 vias went from 5.5 % to 7.2 % of the board
   area, the candidate's 210 vias at 0.45/0.25 are 6.7 %.
3. **The candidate is not congested.** Residual mode (existing copper as
   obstacles): no cut at capacity; densest F.Cu cut y = 107.75 (AFE row) at 14
   used / 8 free lanes, next 107.25 at 18/18, everything else ≤ 38 % full.
4. **The rule change altered no fine-pitch escape.** U4, U6, U7, U8, U10, U16
   never allowed a track between adjacent pads (0.15–0.25 mm gaps) under any
   rule set; the override newly allows it only on the SOT-23-5 / TSOT-23-6.
5. Known-bad calibration: 0.5 mm track / 0.5 mm clearance flags the neck and
   the AFE row at 1.00, so the map can fail.

## Reading

The churn was never about corridor capacity. What the session was iterating
on is what neither the router nor this map scores: the ground-return path
between the AFE and the ADC (its reviewer's last three findings), the CELL_RE
guard, pour integrity on B.Cu, and the via budget. Those are authored
constraints. The productive order is: fix the via budget and the B.Cu
corridor plan (which nets may cut the pour, and where), hand-route the neck
and the AFE row, then let the router close the remainder once from a clean
seed. Candidate count is not progress.

## Reproduce

```sh
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
T=~/.claude/skills/kicad-design/scripts/kicad_lane_capacity.py
$PY $T routing/revb-89-tmp302/o2-probe.kicad_pcb --pour-net /GND --exclude-layer B.Cu \
  --rules old:0.09,0.15,0.25,0.15,0.20,0.20 \
  --rules aisler:0.125,0.125,0.45,0.25,0.25,0.30 \
  --rules override:0.10,0.10,0.40,0.20,0.25,0.30 \
  --csv /tmp/lanecap.csv --svg /tmp/lanecap.svg
$PY $T <candidate.kicad_pcb> --rules override:0.10,0.10,0.40,0.20,0.25,0.30 \
  --pour-net /GND --residual --exclude-layer B.Cu --show 0
```

Model limits (bounding-box pads, one crossing per net, vias ignored in
placement mode, net-specific clearance rules not modelled) are listed in the
skill's calibration note.
