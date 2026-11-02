# audit_mpn_package.py — independent adversarial review

Review date: 2026-09-01
Reviewer: independent Codex agent (`codex exec`, non-interactive), given a
headless Chrome attached over CDP on a scratch profile so every datasheet claim
could be checked against the primary PDF rather than marked unverified.

Scope: `audit_mpn_package.py` as the deliverable; the L1/DZ1/F1 component
selections in `gen_sch.py` and the arithmetic behind them as secondary targets.
`audit_bom.py` and `sourcing.json` were read as context only.

Primary documents inspected, each validated by content (byte count + `%PDF`
signature + named rendered pages), not HTTP status:
DS41326 Rev. 3-2 (AP63205), DS31524 Rev. 7-3 (DMP3130L),
DS35716 Rev. 5-2 (DMP3010LK3), DS32239 Rev. 13-3 (DMP3010LPS),
DS18004 Rev. 38-2 (BZT52C12), DS19002 Rev. 20-2 (SMBJ),
Bel 0ZCJ Rev. Sep2025, Bourns SRN6028C Rev. 04/23.

An earlier run of this review was interrupted; this is the completion pass over
the same locally validated evidence set.

FINDINGS

1. **High — (c) real design defect — Q1 lacks a supported orderable MPN.** [`gen_sch.py:380`](/Users/fab/dev/ee/hw/o2-probe/gen_sch.py:380) still assigns `DMP3010L-7` to SOT-23. DS35716 Rev. 5-2 p.1 identifies `DMP3010LK3-13` as TO-252; DS32239 Rev. 13-3 p.1 identifies `DMP3010LPS-13` as PowerDI5060-8; DS31524 Rev. 7-3 p.1 identifies `DMP3130L-7` as SOT-23. The exact `DMP3010L-7` remains unsupported in the checked official/current-distributor corpus, so the board cannot be assembled from its declared BOM. Smallest fix: change Q1 to the intended exact SOT-23 MPN—apparently `DMP3130L-7`—and requalify its ±12 V gate limit.

2. **High — (c) real design defect — DZ1 does not provably protect Q1’s gate.** [`gen_sch.py:382`](/Users/fab/dev/ee/hw/o2-probe/gen_sch.py:382), DS18004 Rev. 38-2 pp.2–3, DS31524 Rev. 7-3 p.2. At 15 V, assuming a 12 V clamp, R1 supplies only `(15−12)/100 kΩ = 30 µA`, 167× below the 5 mA test current. BZT52C12 is guaranteed only as 11.4–12.7 V at 5 mA and +25 °C; its temperature coefficient is also specified only at 5 mA. Low-current VZ and its temperature behavior are unspecified, and even the 5 mA maximum exceeds DMP3130L’s ±12 V absolute maximum. The typical I–V curve supplies no limit. Smallest fix: use a clamp guaranteed below 12 V with margin at the actual minimum current over −40…+85 °C, or redesign R1/clamp bias to operate at a guaranteed point.

3. **High — (c) real design defect — waivers do not verify the declared package.** [`audit_mpn_package.py:407`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:407). Any nonempty `package`, `source`, and `rationale` converts `unresolved`, `unmapped`, or a mid-sweep `unverified` result to `waived`; `package` is only printed. This contradicts the claimed evidence substitution and can silence the check. Smallest fix: make `unmapped` nonwaivable, canonicalize waiver packages, and require their intersection with `FOOTPRINT_PACKAGES[footprint]` before accepting `unresolved`/`unverified`.

4. **High — (c) real design defect — `--no-export` audits an unbound artifact.** [`audit_mpn_package.py:487`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:487), [`audit_mpn_package.py:506`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:506), [`audit_mpn_package.py:516`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:516). The code parses arbitrary existing XML but reports the current schematic’s hash. A stale or substituted XML can therefore PASS while the report attests to another schematic. Smallest fix: remove `--no-export`, export to a fresh temporary XML, parse that exact file, and record both hashes.

5. **High — (c) real design defect — an empty audit population passes.** [`audit_mpn_package.py:398`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:398), [`audit_mpn_package.py:518`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:518). Zero fitted MPN-bearing components produces no finding and no error, so a broken export/parser can look clean. Smallest fix: fail when `fitted` is empty; preferably also assert the expected component population or reference set.

6. **High — (c) real design defect — package tokenization admits wrong physical packages.** [`audit_mpn_package.py:153`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:153), [`audit_mpn_package.py:364`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:364). `package_tokens("0201 (0603 Metric)")` emits `0603`, allowing a three-terminal 0201 device to satisfy a two-pad 0603 footprint. Likewise, a 4.40 mm-wide `8-TSSOP` satisfies the 3.00 mm VSSOP map. Smallest fix: compare structured, complete package identities—including pin count and body dimensions—rather than arbitrary words extracted from parenthetical text.

7. **Medium — (c) real design defect — L1’s land mismatch is real.** [`gen_sch.py:398`](/Users/fab/dev/ee/hw/o2-probe/gen_sch.py:398), [`o2-probe.kicad_pcb:7018`](/Users/fab/dev/ee/hw/o2-probe/o2-probe.kicad_pcb:7018), Bourns SRN6028C Rev. 04/23 p.1. The current 1.5 × 2.4 mm pads at ±2.75 mm overlap each nominal 5.8 × 1.6 mm terminal by `1.0 × 2.4 = 2.40 mm²`, only 25.9% of its 9.28 mm² area. “Solderable for a first article” is not supported by the datasheet. Smallest fix: create the recommended 2.0 × 6.5 mm lands with centers at ±2.25 mm. Height is **2.6 ± 0.2 mm; 2.8 mm is maximum**, not nominal.

8. **Medium — (c) real design defect — lookup evidence is not bound to manufacturer or retrieval context.** [`audit_mpn_package.py:243`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:243), [`audit_mpn_package.py:296`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:296), [`audit_mpn_package.py:342`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:342). Live matching checks only `ManufacturerProductNumber`; cached passes contain only tokens, with no manufacturer, raw source fields, timestamp/TTL, locale, endpoint, or client/API version. A same-MPN collision or stale/corrected record can pass. Smallest fix: require an expected manufacturer identity and cache the raw package fields plus provenance and expiry.

9. **Low — (b) unstated assumption that happens to hold in the searched corpus — the “only/never existed” claim is too strong.** [`audit_mpn_package.py:11`](/Users/fab/dev/ee/hw/o2-probe/audit_mpn_package.py:11). DS35716 and DS32239 positively establish TO-252 and PowerDI5060-8 DMP3010L variants, and official searches found no SOT-23 `DMP3010L-7`; they do not form a closed all-time catalogue. Smallest fix: say “no SOT-23 DMP3010L variant was found in the inspected primary/current official corpus” rather than “never existed.”

SURVIVED

1. **The direct F1-versus-D1 rating allegation is refuted.** Bel 0ZCJ Rev. Sep2025 pp.1/3 and DS19002 Rev. 20-2 p.3. D1’s 24.4 V value is its downstream node-to-ground clamp at 24 A; F1 instead sees `VRAW − VFUSED`, not 24.4 V. Thus `24.4 > 16` alone does not prove F1 exceeds Vmax. Bel defines Vmax as a Vdc fault-withstand rating and provides no transient-overvoltage allowance; its spike caution confirms it is not a pulse rating. Actual transient coordination remains unverified because no upstream surge waveform or source impedance was specified.

2. **The current audit does fail the known bad board.** Its report returns `unresolved` for Q1 and `unmapped` for RV1/U11. Distributor initialization/control failure fails closed; per-part request failures become `unverified`; `mismatch` is nonwaivable; `--refresh` bypasses the cache; family-hint failure affects only an already-failing result; stale waivers and waivers on `ok` parts fail safely. Canonical SOT-23-3, SOT-23-5, and TSOT-23-6 strings remained distinct.

3. **L1’s electrical selection is supported apart from its lands.** DS41326 Rev. 3-2 p.13 explicitly recommends 4.7 µH for AP63205. At 12 V→5 V and 1.1 MHz, nominal ripple is 0.564 A. SRN6028C-4R7M is listed at 4.7 µH ±20%, 30 mΩ DCR, 3.1 A Irms typical, and 3.2 A Isat typical. Those current ratings are typical, not guaranteed limits.

4. **The proposed small parallel-inductor alternatives remain rejected under the supplied premises.** A 2.0 mm 0805 body cannot bridge L1’s 4.0 mm inner pad gap. With one −20% inductor and the others +20%, that branch takes 60% of two-way ripple or one third of four-way ripple, before DCR mismatch. Exact stock MPNs remain unverified: the InvenTree helper failed DNS, and the attached browser reached only the unauthenticated InvenTree login page.

5. **The DMP package conclusion is bounded.** DS35716 p.1 verifies `DMP3010LK3[-Q]-13`/TO-252; DS32239 p.1 verifies `DMP3010LPS-13`/PowerDI5060-8; DS31524 p.1 verifies `DMP3130L-7`/SOT-23. Only the universal historical absence remains unproved.

6. **Source access/provenance.** The supplied CDP browser was re-proved through `about:blank`; no browser was launched or replaced. The local AP632xx, DMP3130L, DMP3010LK3, DMP3010LPS, 0ZCJ, SMBJ, BZT52, and SRN6028C PDFs were inspected through raw text and validated against the rendered pages cited above. The inherited live-DOM DigiKey rows supplied the `0201 (0603 Metric)` and 4.40 mm `8-TSSOP` counterexamples. Official-domain DMP3010L searches found no SOT-23 result but did not close historical absence. `AP63205-real.pdf` was an HTML error payload and was de-scoped; nothing depends on it. No persistent archive was authorized, so the validated copies remain scratch-only.
