# Six lower via/paste-land repairs — 2026-09-12

Accepted handoff: `apply_six_pad_vias.py`, SHA-256 `2270c31240d01ffaad233333e695daf052d98367ba8a52467cad3fc99e093264`. Its inherited opening docstring says seven, but its explicit plan and `apply()` result contain exactly six via changes. Do not use `apply_pad_vias.py`: that earlier seven-site experiment removes the R44 stitch and leaves a ground island disconnected.

The six changes remove actual copper overlap/touch between enlarged vias and the C20.2, C21.2, R29.2, Q2.2, U16.3 and Q2.1 SMD lands. Native global pad shapes were checked, including the rotated Q2 pads. No extra arbitrary 0.2 mm same-net pad gap was required. No footprint or bus item is changed. All additions are locked; existing track/via lock state is preserved.

| Land | Via before (mm) | Via after (mm) | Diameter / drill after (mm) |
|---|---|---|---|
| C20.2 | 106.5, 135.1 | 106.55, 135.1 | 0.4 / 0.2 |
| C21.2 | 112.5, 136.2 | 111.85, 136.2 | 0.45 / 0.2 |
| R29.2 | 114.1, 134.8 | 114.1, 134.45 | 0.4 / 0.2 |
| Q2.2 | 111.35, 134.825 | 111.55, 134.825 | 0.4 / 0.2 |
| U16.3 | 113.7, 137.35 | 113.7, 137.42 | 0.45 / 0.2 |
| Q2.1 | 109.05, 134.3 | 108.5, 133.8 | 0.4 / 0.2 |

Nine attached same-net track endpoints follow their vias. Three short back-copper stubs join the Q2.1, Q2.2 and R29.2 lands. Exact UUIDs, original and replacement endpoints, net names and added geometry are recorded in `six-evidence.json` and the adapter's literal `PLAN`; source checks fail if these scoped objects differ.

Verification on `six.kicad_pcb`, a fresh live-board copy before applying these six changes: every track/via net identity preserved after native save and reload. Native CLI DRC used `--all-track-errors --severity-all --refill-zones --save-board`: zero error-severity violations across all types, 17 pre-existing power connections still open, no GND opens. `six-drc.json` contains the complete result, including 14 non-error findings. The six vias have zero native-shape intersections with any SMD copper land on either copper layer, measured at a zero collision margin after native refill/save (`six-evidence.json`). This is scoped geometry/connectivity evidence, not whole-board fabrication closure.

R44 is intentionally unchanged in this handoff. Its existing back-layer ground land encloses a stitch at 108.5,110.7. Removing that stitch and tying U7.7 directly to EP on F.Cu disconnects the local back ground island. The upper-layout agent owns a separate placement/stitch correction; parent may route the three missing power nets in parallel.
