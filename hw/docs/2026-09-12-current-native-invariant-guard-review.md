# Current native invariants and process-rule calibration, 2026-09-12

`verify_revb_current.py` checks the current 83-component PCB against the authoritative XML and native 89 mm outline, enforces minimum native trace/via dimensions and CELL_RE via-free/F.Cu-only routing, and compares protected native copper plus footprint/pad geometry against a pre-route snapshot. It is intentionally narrower than a completed-board validator: it does not establish DRC/connectivity, guard shielding, filled-ground topology, thermal performance, return-current coupling or fabrication acceptance.

The footprint comparison covers UUID, value/FPID, pose and each pad UUID, number, net, position, size, drill, shape enum, attribute, layers and angle. It does not compare custom-pad primitive definitions, local pad-shape overrides, stencil/mask margins, footprint graphics or text. Those still need separate native and visual checks; this report does not claim an exact serialization comparison of every footprint field.

The pre-route scope record is `checks/current-skeleton-review/main-route-critical-snapshot.json`, derived from `checks/main-route-seed/o2-probe.kicad_pcb`. It records all locked copper, rather than inferring safety from the router flag. Its own PASS means only the named static invariants were evaluable and passed; recording a snapshot is not independent circuit acceptance. A later reviewed circuit change must be authored into a separately recorded source and reviewed explicitly, not normalized by silently refreshing the snapshot from a routed board. Exact project/rule hashes also prevent a changed process profile from passing under old evidence. A reviewed stackup-only correction therefore requires explicit source reconciliation.

## Eight-point review

1. **Unevaluable input:** The verifier writes UNVERIFIED before reads, returns nonzero on missing/malformed input or an empty scope, and requires the exact known baseline hash and a nonempty current 83-component netlist. Output paths cannot overwrite inputs. Missing critical nets or native/schematic mismatches fail. This is a fresh computation; no PASS cache is reused.
2. **Monotonicity:** Deleting a locked route, clearing its lock, reducing its width to 0.099 mm or far below to 0.01 mm, adding a CELL_RE via, and reducing via dimensions all fail. Protected equality is exact in native integer geometry, not an average score. The process-rule calibration tests both near misses and far failures, plus equal/above-threshold controls.
3. **Preconditions:** Tests launch the actual verifier under KiCad's bundled Python on saved native boards. The separate process calibration launches actual `kicad-cli pcb drc` and requires violations from the named custom rule, not a guessed geometric proxy. All process fixtures produce fresh JSON. No routing completion is inferred.
4. **Source of truth:** The snapshot and report fingerprint the verifier, native board, XML, baseline, project and rules. Check mode requires the same verifier hash as snapshot mode. Inputs are hashed again at the end. Native coordinates and drilled dimensions come from pcbnew. Process tests fingerprint their fixture producer, process DRU and project and reject mid-run changes.
5. **Persistence:** A calibrated run overwrote a prior PASS report with UNVERIFIED after the next XML parse failed. Missing inputs and empty critical inventories also returned UNVERIFIED/nonzero. The process calibration starts UNVERIFIED, records each completed case, and records FAIL on exceptions or unexpected native results.
6. **Provenance:** Reports state their limited scope. No native DRC, poured-ground or thermal claim is made by the invariant verifier. Process calibration checks the named rule result; unrelated DRC findings on synthetic fixtures are not a board-wide clean bill. The known wx duplicate-image-handler debug messages from native loading are preserved in logs and are not electrical findings.
7. **Known-bad calibration:** `checks/test_verify_revb_current.py` produced 12 cases in `checks/current-invariant-calibration-v1/summary.json`: unchanged PASS; deleted/unlocked/near-width/far-width/CELL_RE-via/via-floor/pad-parity/outline FAIL; prior-PASS then malformed XML, missing XML and empty snapshot UNVERIFIED. Total runtime 5.233 s; unchanged verification 0.345 s, fault cases 0.217–0.473 s.
8. **Fix versus mute:** The production fix is locking the authored MCU copper and verifying its survival after routing. The manufacturing rule change scopes the actual written NPTH limits correctly while retaining the baseline generic drilled-hole clearance. Neither validator ignores the target failure or turns a routing omission into PASS.

## Process-rule results

`checks/test_revb_current_process.py` generated and exported 20 actual native boards. All expected results matched in 36.476 s total (approximately 1.5–2.7 s per DRC invocation). Evidence: `checks/current-process-calibration-v1/summary.json` and each case's native board, project, rules, DRC JSON and log.

| Native rule | Failing values (mm) | Passing values (mm) |
|---|---|---|
| Round NPTH copper clearance | 0.05, 0.24 | 0.25, 0.26 |
| Round NPTH minimum drill | 0.05, 0.49 | 0.50, 0.51 |
| NPTH minimum milling width | 0.05, 0.79 | 0.80, 0.81 |
| Milled NPTH copper clearance | 0.05, 0.29 | 0.30, 0.31 |
| Component PTH annular ring | 0.05, 0.29 | 0.30, 0.31 |

The current rules use 0.20 mm generic drilled-hole/copper clearance, explicit 0.25 mm round-NPTH clearance and 0.30 mm milled-NPTH clearance. Native global edge clearance remains 0.30 mm and covers Edge.Cuts as well as oval pad holes. This matches the retained limits in `plans/REVB-AISLER.md`; it does not establish standard Aisler compliance under the user's overridden trace/spacing/via minima.

## Invocation

Run with `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3` from the project directory:

```sh
verify_revb_current.py snapshot checks/main-route-seed/o2-probe.kicad_pcb --netlist o2-probe.xml --baseline routing/revb-89-tmp302/o2-probe.kicad_pcb --out checks/current-skeleton-review/main-route-critical-snapshot.json
verify_revb_current.py check routing/revb-current/o2-probe.kicad_pcb --netlist o2-probe.xml --baseline routing/revb-89-tmp302/o2-probe.kicad_pcb --snapshot checks/current-skeleton-review/main-route-critical-snapshot.json --out checks/current-skeleton-review/post-route-invariants.json
```

The names above are arguments to the bundled Python executable; do not execute snapshot again after routing merely to make a changed candidate pass. Intentional C17/local-layout or stackup changes need their own explicit reviewed reconciliation.

## Canonical full-rule-template recheck

Root subsequently made `revb_current_process.kicad_dru` the complete template, including the inherited functional rule and version header, and corrected comments without changing process predicates/values. The fixture harness now copies that exact full template instead of adding another version header. All20 native cases passed again in49.095s; final evidence is `checks/current-process-calibration-v2/summary.json` with the new template/producer hashes.
