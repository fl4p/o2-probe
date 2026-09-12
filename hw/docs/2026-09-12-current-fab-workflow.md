# Current Rev B fabrication-export workflow — 2026-09-12

`make_fab_revb_current.py` exports the current 83-footprint, two-layer, 20 × 89 mm design from `routing/revb-current/`. It does not run `gen_sch.py`, the migration, any authoring adapter, or a router. The older `make_fab_revb.py` still targets its historical 107 mm candidate and must not be used for this design.

The final accepted native snapshot and an explicit review record are still supplied by the completing engineer/reviewer. This preparation has not produced a final package or accepted the unfinished PCB.

## Run after final board and review closure

Use repository-relative paths from the o2-probe root. Substitute the actual final reconciled snapshot path; do not substitute an unrestricted new snapshot for the independently reviewed expected inventory.

```sh
python3 make_fab_revb_current.py \
  --snapshot checks/current-skeleton-review/FINAL-REVIEWED-SNAPSHOT.json \
  --write-gate-template checks/current-fab-workflow/final-review-gate.json
```

The new file has `status: UNREVIEWED`; template generation does not export anything or signify review. The reviewer confirms the exact board/project/rules/schematic/netlist/code/library hashes, the final snapshot and the ten named assembly dispositions, records the repository-relative final review file in `review_record` and its exact SHA-256 in `review_record_sha256`, then sets `status` to `REVIEWED`. Any changed input requires a refreshed template and review. The review file must exist within this repository and match that hash at the start and end of export; its exact bytes are copied into the package. This establishes content provenance, not an automated assessment of the reviewer’s conclusions.

For each GUARD_REPLICA rail endpoint that still carries an intentional native `track_dangling` warning, the reviewer may supply an exact row in `reviewed_guard_endpoints`:

```json
{
  "uuid": "exact-native-track-uuid",
  "net": "/GUARD_REPLICA",
  "board_sha256": "exact-current-source-board-sha256",
  "reason": "Specific reviewed shielding purpose and evidence that the opposite end connects"
}
```

The array defaults to empty. No other net, unmatched UUID, empty reason, stale board hash, extra endpoint warning, or missing expected warning is accepted. This preserves intentional shielding without creating a blanket dangling-track waiver. Actual guard continuity remains part of the independent electrical review and final native checks.

```sh
python3 make_fab_revb_current.py \
  --snapshot checks/current-skeleton-review/FINAL-REVIEWED-SNAPSHOT.json \
  --review-gate checks/current-fab-workflow/final-review-gate.json
```

The script requires KiCad CLI 10.0.5 and its bundled native Python. It writes a new immutable local directory and ZIP under `fab/o2-probe-revb-current-<zip-hash-prefix>/`. It places no order, sends no message, pushes nothing and updates no existing release pointer. Failed runs leave their staging log/evidence and do not produce a promoted release.

## Package contents and checks

- Nine X2 Gerbers: F/B copper, mask, paste and silkscreen, plus Edge.Cuts. Existing `check_gerbers(compact_95=True, tip_trim_mm=2, power_compact_mm=4)` checks exact outline/slot primitives and the thermal fill gap.
- Separate plated/nonplated metric Excellon files, drill maps/report. Existing `check_drills` matches each hit/slot against the current native witness, including plating and quantization.
- Schematic PDF, front/back assembly PDFs, native BOM CSV with MPN and DNP fields, and all/fitted position CSVs. Current native BOM smoke output contains 77 rows; the remaining six of the 83 footprints are BOM-excluded test points TP1–TP6. DNP rows remain visible in the BOM.
- Full saved-fill and refilled native DRC reports with all track errors, all severities and schematic parity. Every error, open, parity discrepancy, ignored check and non-dispositioned warning rejects the run. The ten reviewed courtyard pairs remain visible with `assembly-dispositions.md`.
- Native invariant checks before and after refill against the final supplied snapshot; native ERC; 83-part exact drill witness. The witness reuses `verify_revb_current.load_state` for native/netlist inventory, pad-net parity, 89 mm baseline edges and minimum/critical-copper constraints.
- Exact accepted source tree and relevant code/library bytes with input hashes. Refill runs on a separate working copy; the exported native state is included under `export-state/`, so the accepted source is not silently overwritten. The manifest records both input and exported-board hashes, CLI version, commands, timings and validation results.
- Full package SHA256SUMS and ZIP inventory/byte verification before promotion. Manifest states CAD export scope and `production_qualified: false`; it does not replace first-article thermal, mechanical or electrical qualification.

## Bounded validation performed

`checks/current-fab-workflow/calibration.json` records thirteen rejected bad inputs, derived from actual saved native reports or their deliberate corruptions: two real native power opens, a real far-tail annulus failure, absent/truncated/missing-field reports, 200 repeated native opens, changed actual board and producer hashes, an unbound guard warning disposition, missing/changed review content, and one removed native drill hit. No fabricated clean-board report was used as acceptance evidence. Positive full-board DRC acceptance and complete export execution await the finished reviewed board.

The 83-part native witness ran on the current design. A drill-only smoke export matched all 195 plated and eight nonplated records in that snapshot. The matching check took about 10 ms; mean rejection time for a native DRC report was 44 µs over 1,000 calls. The initial witness before provenance hardening took about 0.5 s, and the drill export about 0.7 s. The hardened standalone witness, including native producer fingerprints and in-run rehashing, took 1.2–1.5 s on the first lifecycle pass and 0.51–0.54 s on the final warm pass recorded in `witness-calibration.json`. These are measured preparation costs, not a claimed full-package runtime. The final manifest measures the full run.

## Eight-point guard review

1. **Unevaluable input:** absent/malformed report arrays, missing tools/libraries/input files, invalid snapshot, bad JSON, command failure and exceptions fail the run. No fallback manufactures PASS.
2. **Monotonicity:** any added error/open/parity/ignored check rejects; only the exact reviewed warning multiset passes. The 200-open far tail remained rejected. Removing a required reviewed finding also forces a new review rather than silently changing scope.
3. **Preconditions:** full native CLI reports are produced in this workflow, with all required flags. The current witness and actual drill exporter were executed together; the final supplied snapshot is checked by the existing invariant checker before export and after refill.
4. **Source of truth:** the review gate binds exact board, project, rules, schematic, XML, checker/exporter/generator code and local footprint/symbol-library hashes, plus the final snapshot and assembly document. The final review file is separately bound by an exact content hash in the gate, checked again before promotion and copied into the package. Inputs are rehashed after copying and before promotion; accepted source bytes remain separate from refilled output.
5. **Persistence:** no verification cache exists. The standalone witness writes UNVERIFIED before native imports, records board/netlist/baseline/project/rules and Python/native producer paths/hashes, rehashes them before PASS, and leaves UNVERIFIED on failure. The builder requires an explicit fingerprinted PASS before consuming its drill inventory. Templates remain UNREVIEWED; failed builds retain diagnostic staging evidence but have no promoted output or latest pointer. A later successful run is new work, not a cached acceptance.
6. **Provenance:** native reports, full commands, return codes, output/source hashes and timing are archived. The manifest distinguishes CAD export from production qualification. No full export or clean-board acceptance is claimed by this preparation.
7. **Known-bad calibration:** the thirteen cases above were actually run and rejected. `checks/current-fab-workflow/witness-calibration.json` additionally records real success followed by a missing netlist and success followed by a native 83-part XML reduced to 82 parts, both reusing the same output: prior PASS was replaced by UNVERIFIED with no old drill/footprint inventory. A reserved output equal to the input netlist was rejected without changing input bytes. The existing drill checker accepted the real current export and rejected removal of one native expected hit. Final clean-path execution remains pending and is not inferred from those tests.
8. **Fix versus mute:** errors and opens require physical corrections. Ten exact courtyard warnings and, only if individually reviewed, each exact intentional guard endpoint warning stay enabled and visible. No native DRC exclusion or board-rule relaxation is added by the exporter.

## Independent producer review

The independent reviewer inspected `make_fab_revb_current.py`, `inspect_revb_current_fab.py` and the invoked Gerber/drill checks. A concrete standalone persistence defect was found: the original witness wrote only after successful inspection, leaving an earlier valid-looking output after a failed later probe. The current implementation fixes that underlying lifecycle. An independent rerun on the actual native83-part candidate obtained PASS in0.564s, then reused the same output with a missing XML and obtained exit2/UNVERIFIED in0.242s with no retained drills or footprint inventory. Evidence is `checks/independent-fab-witness-review/summary.json`, bound to inspector SHA `9f302291d13bc009398745617bd002ff69c74d3a7d7d27e97cf29ea22982599a`.

The exact source/code/library/snapshot gate, actual review-file hash and individually bound GUARD endpoint dispositions were reviewed without a further concrete finding. The Gerber checker proves its stated layer/outline/slot/filled-gap structure, and the drill checker matches the actual source drill inventory; these do not constitute a complete independent mask/paste geometry analysis. Final native and artifact inspection remain necessary. This source review and the witness regression do not accept an unfinished PCB or an export package that has not yet been generated.
