# Independent 86 mm Rev B artifact review — 2026-09-12

**PASS for the completed local CAD artifact package**, with no remaining concrete finding from this review. Package: `fab/o2-probe-revb-86-4837fd61405f8b2b/o2-probe-revb-86.zip`. The package remains production-unqualified and no order has been submitted; prior procurement, physical assembly and first-article limits remain open.

| Bound object | SHA-256 |
|---|---|
| ZIP | `4837fd61405f8b2bfad1ab6e4232ef26eb348ea2dc40b9ec454e90aac05d31e2` |
| Manifest | `d0c9daea9442b72ce07342d2573e7ee6d6b2a0976abf92e78a1b02f46841c91c` |
| Live, packaged-source and exported 86 mm PCB | `9da60f0c3bbf4bc85fe11fb920bd16b3d50b55f7edb4ab5fc0db4f19af203794` |
| Pinned 89 mm reference PCB | `3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665` |
| Bound 86 mm PCB review | `37d16dd4543fa6486c381f389f8b029b1c4a962860b4fce62f7a879637476bf8` |

The live source, packaged source and refilled export-state PCB are **byte-identical** to the accepted 86 mm candidate. All 38 inventoried source/code/library files match their live reviewed hashes and packaged copies. The actual review gate and copied review record are correctly bound. All 74 SHA256SUMS entries and 75 unique ZIP entries match their files byte for byte, with no missing or extra archive member.

Both saved-fill and refilled native DRC reports have zero errors, zero opens, zero parity discrepancies and no ignored DRC checks. They retain exactly the ten individually reviewed courtyard warnings and two individually bound GUARD endpoint warnings. Both strict native comparisons pass: 83 footprints, 195 vias and all 2543 copper objects preserved, with only the six approved drawing changes and bounded top fill clipping. ERC reports zero findings under the same four pre-existing ignored categories: single_global_label, four_way_junction, simulation_model_issue and footprint_filter.

The corrected contour checker independently passes the actual nine Gerbers, including unambiguous metric units, absolute coordinate format, arc direction and swept side, the 20 × 86 mm outline, four thermal slots and thermal fill gap. All 204 plated and eight nonplated drill records match the native witness. The two independently reproduced parser defects—reversed arc direction and inch units being accepted—were fixed and calibrated before this package was generated; their evidence and code hashes are in `2026-09-12-revb-86-export-workflow.md`. These structure checks do not claim complete independent mask/paste geometry equivalence.

The native BOM contains 77 rows. C4 and C8 retain their DNP rows and are excluded from fitted placement output. No sourcing or population change was introduced by the shrink. Full builder runtime was 14.545 s; independent package revalidation took 0.078 s. The machine receipt is `routing/revb-86/evidence/independent-artifact-receipt.json`.

The parent engineer separately completed five successful `qpdf --check` runs and viewed the actual final front/back assembly and schematic PDF rasterizations. No additional shrink-related visual finding was reported: the CABLE annotation, shortened top corners, C/W/R mapping, slots, potting/keep-open labels and DNP crossouts remain visible. Attributed evidence is `routing/revb-86/evidence/pdf/checks.json` and `visual-review.json`. The individual raised/dressed cable and temporary programming-head fit limitations remain as documented; these visual checks do not measure external interface dimensions.

The bound PCB review, gate and package were not changed during this artifact review. The historical 89 mm board/package remains separately preserved.
