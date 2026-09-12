# Saved-reference overlap screen and D8 source correction

Independent reviewer follow-up, 2026-09-12. No electrical or PCB changes.

The layout audit missed D8's reference overlapping U10 because its legacy model put reference text at the symbol centre and `y-half_height-1.8`; the generator emits it at `x-5.08,y-half_height-5.08`. The mismatch was visible in the actual KiCad PDF even when the audit reported zero collisions.

`audit_layout_references.py` adds a bounded screen using saved reference positions, font sizes and symbol poses from the generated schematic. It checks horizontal reference fields on 0/180-degree instances against generator-derived body boxes. The report explicitly gives its coverage: 38 references checked, 45 quarter-turn reference fields excluded, 88 non-power instances inventoried. It excludes hidden power fields, values, labels, pins and wires from this added check. Existing model-box and label-wire heuristics remain; none constitutes rendered visual signoff. The coarse 0.4 mm overlap threshold and estimated glyph width are screening choices, not exact KiCad text outlines.

The same saved D8 reference overlap passes the old audit and fails the new one. A deeper overlap also fails; corrected placement and a legal reference move pass. Missing and malformed schematics return UNVERIFIED. Actual KiCad PDF exports of the good and original-overlap fixtures were produced; the known-bad crop was visually inspected after the same-session blind vision probe passed.

## Eight-point review

1. **Unevaluable:** input files must be readable; reference instances must be nonempty, unique, complete against the model and use matching library IDs. Unbalanced syntax, unsupported field orientation/justification and invalid geometry raise UNVERIFIED. Missing and malformed fixtures demonstrate the nonzero result.
2. **Monotonicity:** increasing the tested D8 overlap remains a failure. Missing/malformed far-tail subjects are not zero-hit successes. Estimated boxes and the declared threshold delimit the claim; this does not guarantee detection of every rendered overlap.
3. **Preconditions:** the helper is called by `audit_layout.py` on the saved schematic. Six real subprocess fixtures exercise that integration; two also produce native KiCad PDFs. This parser targets the generator's serialized format and rejects unsupported encodings.
4. **Source of truth:** the audit prints hashes of itself, the helper, generator and schematic. Fixture reports additionally hash the calibration producer and native PDFs. Body dimensions still originate in the generator model and are identified as such. This is a single-writer review tool, not an atomic concurrent-edit validator.
5. **Persistence:** this layout audit has no success cache or persistent report; verdict is the current process status/stdout. Missing/unsupported input exits2; callers must not reuse an earlier stdout log as current evidence.
6. **Provenance:** saved anchors are read from the actual schematic. Approximate glyph/body extents and excluded classes are explicit. Native rendering is additional evidence, not simulated by the detector.
7. **Known-bad calibration:** the exact original D8 reference/U10 collision fails specifically as `D8.ref (saved anchor) <-> U10 body`. Old audit returns PASS on that same fixture. Deeper overlap, missing and malformed inputs are also calibrated; legal alternatives pass.
8. **Fix vs mute:** the added check detects the original missed geometry. It neither exempts D8 nor suppresses legacy findings. The existing corrected D8 placement passes because the reference moved clear of U10.

Run `python3 test_audit_layout.py checks/layout-reference-calibration-final` from the project directory. All six outcomes passed. Final measured whole-audit times: good0.129s, original-overlap0.647s, deeper-overlap0.126s, legal-move0.101s, malformed0.097s, missing0.029s. A preceding run was approximately0.100–0.109s for all present-file cases; the0.647s sample illustrates wall-clock variability. The old audit on the bad fixture took0.101s. No isolated parser-cost or statistically stable performance claim is made.

## Source citations and native ERC

The archived Vishay PDF is document **85885, Rev1.1,22-Feb-2018**. Fig3 reverse-current curves are25/50/75/100/125°C; the -40/25/125°C curves belong to Fig1 forward current. `gen_sch.py` and `datasheets/PROVENANCE.md` are corrected. The PDF filename and provenance were subsequently reconciled with peer commit98290a2; the numerical by-eye leakage estimates were not adopted. No branch or index merge was performed.

The 25°C/25V maximum does not establish an85°C/1.2V leakage error budget. The former18mV calculation is explicitly disclaimed as a high-temperature bound. No by-eye peer estimate was promoted. Digitization can support a typical estimate; the physical leakage qualification remains OPEN.

Fresh isolated generation after these comment-only changes produced a schematic byte-identical to the reviewed source, SHA256 `9f06ced24c53ee2e52a823052d4e7d5a4581eef53be99d1e067ee78b1f6a5aba`. Native ERC with violation exit status returned **0 errors/0 warnings**,1.424s. The first isolated attempt omitted the footprint table and correctly failed on eight library-link warnings; rerunning with the original project libraries resolved through an isolated absolute-path table fixed the test environment. No ERC severity was changed. Existing exclusions remain listed in the native report.

Persistent evidence: `checks/layout-reference-calibration-final/` contains the six fixtures, hashes, logs, native PDFs and old-audit comparison. `checks/layout-reference-calibration/regenerated/verification.json` records byte identity and fresh ERC. This review is not fabrication acceptance.
