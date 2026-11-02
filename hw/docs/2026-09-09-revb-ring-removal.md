# Rev B external-ring retirement — 9 September 2026

Fab deferred J5 to optional Rev C, then authorized removing its branch from
Rev B and preserving a discoverable recovery record. The indexed
[Rev C plan](../plans/REVC-HEATED-RING.md) retains the exact pre-removal commit,
board hash, electrical connections and recovery commands. It explicitly records
that the enclosure study already superseded the original fork/neck geometry.
The plan is also included in the engineering-review ZIP.

## Implemented and checked

The schematic/generators and routed candidate remove J5, F3 and their branch:
13 track segments and 3 vias. An independent reviewer compared the before/after
physical inventory: no added tracks/vias, and every retained footprint's placement,
orientation, layers, pads and nets are unchanged. RH1/RH2 remain 280Ω from
`+12V_SW` to `HEATER_LOW`, with their main-board current path intact.
The hash-pinned BOM39 source and the root Rev A PCB are unchanged by this task.

KiCad 10.0.5 rebuild checks:

- 99 components; all 299 physical pins agree with the generated schematic.
- All 51 retained critical routing items present and locked.
- ERC passes; saved-fill and refilled DRC have zero errors, opens, parity
  findings or silkscreen warnings. The same 15 individually dispositioned
  manual-assembly courtyard warnings remain visible.
- Nine Gerber layers; 286 PTH and 8 NPTH drill features match actual board
  geometry. Four thermal slots and the thermal fill gap pass existing checks.
- 14 export-calibration tests pass (0.310 s), plus 5 ring-retirement calibration
  tests (4.278 s). No firmware changes; its earlier 253-test result is inherited,
  not a fresh firmware test run.
- BOM now has seven unordered exact-MPN groups, zero unsourced fitted parts.
  The [updated reconciliation](REVB-BOM-RECONCILIATION.md) uses the original
  explicitly dated stock/order observations after removing J5/F3 demand; it
  does not claim a new inventory query. Procurement, cell receptacle and
  physical qualification remain open.

Review package: `fab/o2-probe-rev-b-2959d79e8b31d893/o2-probe-rev-b-review.zip`.
ZIP SHA-256: `2959d79e8b31d893ad1d6a08f57c0cdcf19d83cb3ddfbf2313acdc150ec54310`.
This is an engineering-review package, not an order-ready release.

## Guard review

1. Unevaluable input: incomplete source footprints, missing pinned copper or
   wrong nets raise; missing dependencies/failed CLI checks stop export.
2. Monotonicity: calibration removes one branch item and all source tracks;
   both fail. Reintroducing either J5 or F3 also fails the current candidate
   inventory check. No tolerance or warning suppression was widened.
3. Preconditions: the actual generator and pinned-board migration run before
   the critical/interface/geometry checks in the exporter. Calibration mutates
   real produced boards in fresh KiCad processes, retaining detached SWIG
   proxies while using their board.
4. Source of truth: package and candidate manifests fingerprint the deriving
   scripts, pinned source, design rules and accepted candidate. Rebuilt geometry
   must agree with that candidate before any package is published locally.
5. Persistence: no successful-check cache is used. An observed KiCad CLI abort
   stopped an intermediate build; the latest pointer stayed on the previous
   successful package. A full subsequent build was required.
6. Provenance: BOM FAIL is packaged explicitly; old inventory timestamps and
   inherited firmware-test provenance remain visible. Only completed CAD checks
   are reported as current.
7. Known-bad calibration: missing main-heater and CELL_RE tracks fail the
   critical guard; missing/wrong-net branch copper fails retirement before edit;
   empty/already-retired input is rejected. Five calibration methods pass.
8. Fix versus mute: the actual optional footprints and copper are removed.
   Main-heater/analog requirements remain enforced. Critical checks measured
   0.339 s before and 0.330 s after on this host (single-run comparison;
   no meaningful added runtime demonstrated).

## Independent review

The reviewer confirmed the scope and preserved geometry. Its actionable finding
was that the packaged scope linked to Rev C plans absent from the ZIP. The
exporter now includes both plans, resolves links against the package layout and
labels repository-only references as such. The pre-removal F3 description was
also corrected to past tense. Final review closure is recorded in the candidate
[validation manifest](../routing/revb-interfaces/validation-manifest.json).
