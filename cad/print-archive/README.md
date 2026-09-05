# Archived plates

One file per plate actually sent to the printer, named for the tag that
describes the tree it came from (`git show print/<name>`).

These are here because a `.3mf` is only reproducible under the same slicer
build. The mesh and the profiles are tracked normally and are recoverable from
the tag; the sliced plate is not. `cad/print/` stays ignored -- this directory
is the deliberate exception, and only finished runs belong in it.

| plate | tag | printed |
|---|---|---|
| `monobody-r1.gcode.3mf` | `print/monobody-r1` | 2026-09-05, ASA, first article |
