# Rev B export and assembly completion — 2026-09-09

The default `make_fab.py` target now rebuilds and packages the two-layer Rev B
candidate. `--revision rev-a` retains the historical exporter. Changes were made
in an isolated checkout; concurrent Rev A board/export work is preserved.

The five inherited footprint-parity findings are fixed at their source: F3's
symbol now describes its fitted resistor link, and J105/J106 explicitly use their
accepted no-relief lands. J103/J104 use local versions of the same land/relief
geometry with their wire-envelope silk on the assembly layer. The cell-body
circle and process annotations also move to the assembly drawing. No courtyard
was shrunk or DRC category disabled.

Independent assembly review identified R17's nominal U4-body-to-land gap of
0.025 mm as insufficient. R17 now sits above U4, its body-to-land gap is 2.664 mm
and courtyard gap 0.814 mm. Its MENB branch is shorter and uses the existing
trunk; the obsolete branch is removed. Its new ground via is outside the solder
land and clears both copper layers. All 63 locked analog/thermal routes survive.
The remaining 15 courtyard pairs are recorded in [REVB-ASSEMBLY.md](REVB-ASSEMBLY.md).

## Verification and independent review

- Fresh rebuild agrees with the accepted board after ignoring only fresh IDs,
  serialization ordering and exact forward-collinear interior vertices.
- ERC: zero violations. Schematic audit and all 303 package pins/101 part values
  and MPNs pass; firmware hardware contract and revision capabilities remain current.
- Saved-fill and CLI-refilled DRC: zero errors, zero opens, zero parity and zero
  silk findings; exactly 15 documented courtyard warnings, no ignored checks.
- Export: correct nine-layer Gerber set, exact outline/four thermal slots and
  thermal fill gap, all 289 PTH and eight NPTH drill records matched, checksummed
  source snapshot and byte-verified ZIP. The 0.001 mm Excellon quantization is
  explicit; matching allows at most half a quantum in coordinates/diameters.
- Full isolated export: 14.28 seconds. Fourteen guard-calibration tests pass
  (0.587 seconds in the reviewed run); native firmware: 253 tests pass.
- BOM audit remains **FAIL: 17 procurement errors**. Six fitted items remain
  unsourced and the historic order snapshot has missing/substituted items and
  stale declarations. The new wire-land identities retain their correct
  not-purchased classification. No part was silently declared sourced.
- Front/back assembly drawings were rendered for visual inspection. All process
  instructions remain in the assembly documentation and the test/connector
  legends remain on the board.

The independent reviewer found the intermediate ground-via collision and a
missing staged critical-route dependency; both were fixed and rechecked. The
reviewer then constructed three malformed drill witnesses (empty slot endpoints,
missing Y coordinates and NaN diameter) that exposed a false pass. All are now
rejected by explicit structural/finite-number checks, with regression cases.
The final reviewer recheck confirmed all findings closed. It also independently
confirmed that collinear subdivision is ignored while a 1 nm bend, backtracking
and reversed vertex order remain detectable.

## Guard review checklist

1. **Unevaluable input:** missing reports, omitted severity sets, unknown findings,
   ignored/excluded checks, malformed/nonfinite drill records, incomplete files,
   unsupported copper-region commands and failed tools raise. BOM failure remains
   FAIL; it never becomes a verified parts basket.
2. **Monotonicity:** calibration covers near and far copper violations, changed
   drill coordinates/diameters, wrong layer identities, missing/extra layers,
   and increasingly wide thermal-gap bridges. Worse input does not restore PASS.
3. **Preconditions:** the complete build invokes actual KiCad generation, refill,
   ERC and DRC with the source project's real sidecars. The critical-route
   module and its thermal-design dependency are copied and executed. Both
   package and witness come from that staged board.
4. **Source of truth:** the manifest hashes staged input files and every local
   derivation/check script, libraries and project rules, and identifies KiCad
   10.0.5. It also records the emitted board and its normalized form. The
   accepted candidate is snapshotted before comparison.
5. **Persistence:** no validation cache is used. A failed build retains staging
   evidence, exits nonzero and cannot update the successful-package pointer.
6. **Provenance:** saved-fill and fresh-refill reports are separate. All commands,
   return codes and runtimes are recorded. The manifest always says engineering
   review and `order_ready: false`; product qualification is not inferred.
7. **Known-bad calibration:** the actual misplaced via produced KiCad shorting
   findings and blocked acceptance. Automated mutations exercise missing and
   malformed reports/files, extra warnings, bad drills and the three reviewer
   false passes. Positive fixtures are the actual exported package.
8. **Fix versus mute:** R17 physically moves and reconnects; conflicting ink is
   moved to the assembly drawing and omitted from the actual silk layers.
   Conservative courtyards and all 15 findings remain visible. Precision
   normalization removes only mathematically identical edges/export rounding.

CAD/export completion does not freeze the draft ring interface or close heater,
F3/input protection, exact procurement, physical fit, cable dressing, compliance,
leakage, thermal or ESD qualification. See [REVB-FAB.md](REVB-FAB.md).
