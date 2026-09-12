# Rev B 86 mm export workflow — 2026-09-12

The 86 mm board has its own `verify_revb_86.py` and `make_fab_revb_86.py`. The 89 mm scripts, snapshots and reviews remain unchanged. No schematic regeneration, copper replay, variant framework or new approval stage is introduced.

The verifier pins the accepted 89 mm PCB SHA-256 `3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665`. It compares complete native token trees while retaining UUIDs: all 83 footprints and their complete pads/attributes/graphics, all 2,543 copper objects including 195 vias, zone definitions and all remaining board metadata must remain exact. Only the five specified Edge.Cuts objects and one front CABLE annotation may differ, at explicit absolute coordinates independently read from the accepted contour. The top straight is y53, corner joins y55, sides end at y139: 20 × 86 mm.

Native fill is unfractured before polygon comparison. No copper may be added; only GND removal above y55.3 is allowed. All filled geometry below y55.3 must remain unchanged, with a 1e-8 mm² numerical area tolerance. The 0.3 mm beyond the corner join covers the existing edge clearance. Measured changes are 58.197 mm² of removed top GND per side, with zero added copper, zero change below y55.3 and identical HEATER_LOW fill.

## Commands

From the o2-probe repository root:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  verify_revb_86.py routing/revb-86/o2-probe.kicad_pcb \
  --reference routing/revb-current/o2-probe.kicad_pcb \
  --out checks/revb-86-verified.json

python3 make_fab_revb_86.py \
  --write-gate-template checks/revb-86-workflow/final-review-gate.json
```

The existing review-gate convention is reused. The template is UNREVIEWED. The completing engineer/reviewer supplies the final repository-relative `review_record` and its `review_record_sha256`, confirms the exact input/code/library hashes, and marks the gate REVIEWED after review. `reference_board` defaults to `routing/revb-current/o2-probe.kicad_pcb`; its PCB hash is pinned by the verifier. The two existing GUARD endpoint warning dispositions must each carry the exact native UUID, 86 mm board hash, net and reviewed reason. Ten specific courtyard warnings remain individually documented in the existing current assembly review.

```sh
python3 make_fab_revb_86.py \
  --review-gate checks/revb-86-workflow/final-review-gate.json
```

The exporter checks the exact trim before and after native refill, runs native saved/refilled DRC with all track errors, all severities and schematic parity, and runs ERC. It reuses the existing strict DRC warning-set checker. The accepted source tree remains separate from refilled working/export state. Inputs and the actual review file are fingerprinted at the start and end, and copied into the package. Any failure leaves staging diagnostics and does not promote a release.

The package includes nine Gerbers, separate metric PTH/NPTH Excellon files and maps/report, schematic PDF, front/back assembly PDFs, BOM and all/fitted placement CSVs, native reports, exact source/code/library bytes, hashes and a verified ZIP. Source filenames remain `o2-probe`; the immutable output directory/ZIP uses `revb-86`. There is no order, push or automatic update of a historical release pointer.

The contour checker compares the actual exported Gerber line/arc multiset to the strict verifier’s schema-2 native 86 mm edge primitives, including the rounded corners and all four thermal slots. Ordered native arc endpoints and the actual midpoint identify the swept side; G02/G03 direction is retained, including under equivalent reverse traversal. Every Gerber requires exactly one metric declaration, absolute 4.6 coordinates and one terminal M02. The Edge.Cuts parser accepts only the emitted KiCad 10 record subset; unsupported drawing/transform records fail. Layer identities, completeness and thermal copper-fill gap are checked using the existing parser conventions. This does not claim complete mask/paste geometric equivalence. The original drill witness is generated afresh from the pinned accepted 89 mm board; full native copper/footprint equivalence proves that the 86 mm holes are unchanged. Current smoke export matches 204 plated drill records (195 vias plus plated footprint holes) and eight nonplated records.

## Validation and eight-point guard review

Actual native mutations on private copies were rejected: top outline shifted 0.01 mm, the same outline shifted 10 mm, copper width changed 0.01 mm, a pad moved 0.01 mm, via drill changed 0.01 mm and footprint DNP changed. A valid result followed by a missing board on the same output became UNVERIFIED with no old edge witness. The actual finished board passed. `checks/revb-86-workflow/calibration.json` records these results and producer hashes.

The nine-Gerber/drill smoke check passed in 0.039 s. Independent review then exposed two real gaps in the first 86 mm comparator: ignored arc direction and unchecked Gerber units. They were corrected in the new 86 mm files only. The current directed-contour check accepts the actual export in 0.032 s and rejects nine actual-file mutations: a 90°→270° corner reversal, opposite semicircle side, inch units on Edge.Cuts/F.Cu, duplicate/missing units, unsupported D03 draw, scale transform and early M02. Exact evidence and current code hashes are in `directed-gerber-calibration.json`; the earlier unsupported acceptance is superseded, not treated as a pass. A changed actual Gerber contour coordinate was rejected. The native DRC report passed with zero errors, zero opens, zero parity findings and the exact 12 visible reviewed warnings (`gerber-drc-calibration.json`). Full verifier cost was 0.69–0.99 s warm in calibration (1.72 s initial standalone); mutation rejection cost was 0.22–0.24 s. Complete package runtime is recorded by the eventual export, not inferred here.

1. **Unevaluable input:** malformed/missing native files, source-hash mismatch, absent fields/UUIDs, unfilled/invalid zones or missing dependencies produce UNVERIFIED/nonzero, never PASS.
2. **Monotonicity:** exact object equality rejects both the 0.01 mm and 10 mm outline failures. Any additional copper, pad, drill, attribute or metadata mutation rejects; there is no score that can improve farther outside a tolerance.
3. **Preconditions:** the exporter invokes the new strict verifier before and after native refill. Existing native DRC and drill checks still execute. Actual native boards, Gerbers and Excellon output were exercised, not mocked native records. The current native arc witness schema is required, preventing a stale directionless witness from being consumed.
4. **Source of truth:** the 89 mm source PCB is pinned. The 86 mm board, companion files, producer/dependency code and actual final review file are fingerprinted and rechecked. Native primitives are exported only after the exact six-change proof passes.
5. **Persistence:** the standalone verifier writes UNVERIFIED before native imports/probing and replaces prior PASS on failure. Fresh staging and immutable promotion are reused; failed builds create no release pointer.
6. **Provenance:** reports preserve native findings, individual visible warnings, input/code hashes, timings and exact source/export state. Calibration and partial smoke exports are distinguished from a final package and physical qualification.
7. **Known-bad calibration:** actual private PCB and actual Gerber mutations above were observed to fail. Missing-input-after-success was also tested on the same report path. Evidence resides in `checks/revb-86-workflow/`.
8. **Fix versus mute:** no board DRC rule/exclusion is changed. Full copper/footprint equality forbids hiding a geometry defect by moving/removing functional objects. Existing specific assembly/guard warning dispositions stay visible; the shortened outline is validated as concrete geometry.

Tracked copies of the successful calibration script and JSON receipts are retained in `routing/revb-86/evidence/workflow/`; private mutated boards and temporary smoke files remain under ignored `checks/`.

## Independent producer review closure

The independent reviewer reproduced both initial Gerber failures using copies of the actual nine-layer export: reversing a corner's G02/G03 command and replacing Edge.Cuts metric units with inches both incorrectly passed the former comparator. The corrected producer was independently rerun against those same fixtures: each now rejects in approximately0.004s, while the untouched actual export passes in0.033s. Evidence is `checks/revb-86-independent/fixed-guard-calibration.json`. Accepted code hashes are verifier `b54f810d5f85a36bf614401b9f17721286814d9459be5790b87896485119bd9a` and exporter `d4e8ade0a7f3c887c024b53fe8f7b9d324d98e0efe0298304c2ba1db2e026320`. No89mm producer was changed.

The raw native object proof and fail-closed lifecycle were independently inspected. The fill rule permits only GND removal aboveY55.3; it does not calculate equality to one expected clipping polygon. Separate actual-candidate native polygon measurement establishes that the real difference is solely the top/corner clip. Final artifact review must additionally verify the exact accepted source/export-state PCB hash. Contour coordinates/centers use the existing0.001mm comparison precision, with the newly preserved arc swept side; this is not a nanometre-level export-equivalence claim. No further concrete source finding remained after these bounded corrections.
