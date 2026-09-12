# Two ground-island repairs — 2026-09-12

`apply_ground_islands.py` adds two locked 0.4/0.2 mm through vias to GND. SHA-256: `d526ad82cea74b8e682993df1ffb4163f7d06ad7c7b6d91780b5e6645fad4b46`. No existing object, footprint, track or zone definition is changed.

- (103.15,94.1) joins the F.Cu TP2 island to the existing B.Cu ground fill.
- (112.3,103.2) joins the B.Cu R25.2 island to the existing F.Cu ground fill.

The native filled polygons identified exactly these two pad-bearing ground islands without a stitch. Candidate positions were selected within the intersection of existing F/B fill polygons eroded by 0.23 mm, then checked against actual native pad shapes. This is two local repairs, not a new ground mesh.

After native save/reload and full CLI `--all-track-errors --severity-all --refill-zones --save-board`, both GND opens disappeared. Every saved track/via retained its expected net name. The two new via shapes have no intersection with any pad shape on either copper layer. The complete result, including all remaining error-severity findings and all opens, is in `evidence.json`; `drc.json` is the unfiltered native report.

The tested source snapshot retained two unrelated J3 clearance/hole-clearance errors involving the 3V3D F track and HEATER_PWM via at (101.825,97.55). Parent had already moved that via to y97.45 while this private check ran. The two pre-existing 3V3D/+12V_SW power connections remained open. This handoff does not claim those unrelated items closed; parent performs the fresh combined verification. R44 remains exclusively with the MCU-layout agent.
