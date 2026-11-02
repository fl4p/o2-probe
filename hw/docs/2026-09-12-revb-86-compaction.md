# Rev B cable-end compaction — 2026-09-12

The user requested a shorter Y dimension after the 89 mm PCB was committed. The new candidate is `routing/revb-86/o2-probe.kicad_pcb`, derived from accepted 89 mm board SHA `3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665`. The 89 mm candidate and its immutable export package remain available.

The board now spans X100..120 and Y53..139: **20 × 86 mm**, a 3 mm reduction. Only the cable-end straight edge, two 2 mm corner arcs and the two side endpoints move. The existing CABLE annotation rotates into the gap between the inner cable lands. All components, numbered and anonymous pads, holes, tracks, vias, thermal slots and cell geometry retain their original coordinates. No routing pass is needed.

The closest cable lands have centre Y=54.5 mm and 1.85 mm copper diameter. Their nominal copper-to-top-edge gap is 0.575 mm under the retained 0.30 mm edge rule; their 0.85 mm drills retain 1.075 mm nominal web to that edge. Their centres are inside the straight edge, so the rounded corners do not reduce those figures. This trim uses spare board margin; it does not infer or change wire, cell or programming-fixture interface dimensions.

The two copper layers, 1.6 mm thickness and user 0.10 mm trace/spacing and 0.20 mm via-drill minima are unchanged. The candidate has 83 footprints and 195 vias. First saved/refilled native check: 0 errors, 0 opens, 0 schematic mismatches, with the same ten individually documented courtyard and two intentional guard-endpoint warnings.

Independent geometry, fill and artifact review is recorded separately before promotion. Procurement and first-article mechanical/electrical/thermal qualification remain open.

## Enclosure revision boundary

The root-level historical `o2-probe.kicad_pcb` is still the 107 mm design; it is not the source of this trim. The current 89 mm source is explicitly `routing/revb-current/o2-probe.kicad_pcb`. On 2026-09-12 the separate historical enclosure project at `~/dev/ha/farming/compostlab/o2-probe/cad/` still declares `board_len=107.0` in `o2_probe_body_tube.scad` and `body_board_len=107.0` in `o2_probe_head_end.scad`. It is not a matched enclosure release for either compact Rev B candidate. This PCB change does not update those physical-interface models; a Rev B enclosure adaptation must use the chosen board artifact and actual assembly/fit requirements.
