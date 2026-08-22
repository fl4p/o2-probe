# PCB connectivity completion report

KiCad strict DRC on 2026-08-22 reports:

- 0 unconnected items
- 0 schematic-parity issues
- 0 shorts, clearance, hole, edge, track-width, or silkscreen violations
- 29 courtyard-overlap warnings
- 110 footprint-library copy mismatch warnings

The former 45-item routing residual is closed. This file remains as a stable
handoff location so downstream checks do not mistake an absent report for an
unreviewed board.

The courtyard warnings are an assembly/fabrication release gate, not unrouted
electrical nets. They must be checked against physical parts and the enclosure
before ordering boards; none has been waived or excluded from `pcb-drc.rpt`.
