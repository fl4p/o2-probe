# BOM population-status guard review — 2026-09-12

This review covers `audit_bom.py`, not board or procurement release. The native KiCad DNP property is authoritative: an intentionally unpopulated component may retain its numeric value. A value containing `DNP` while the property says fitted remains an error. DNP components contribute zero purchase quantity; fitted parts still require sourcing and the existing order checks.

Reviewed audit SHA-256: `cc1ed8b009177b8e9ae29a962326fba50a105325752eca0048dfa0d31ecb8f61`.

1. **Unevaluable input.** The audit publishes `UNVERIFIED` before probing and removes a stale CSV. Missing/malformed XML, sourcing or order data, empty component inventory, duplicate/empty references, and failed native exports exit nonzero. Failed probes cannot retain an earlier PASS report or purchase CSV. The schematic is required even when reusing XML.
2. **Monotonicity.** Population status is categorical: a false DNP property never becomes acceptable because the value includes DNP. Numeric and labelled DNP cases pass only with the explicit property. Missing, malformed and empty inputs fail rather than becoming an empty valid BOM. Fitted unsourced and unordered parts remain failures.
3. **Preconditions.** The calibration invokes copies of the actual CLI, exercises parsed native-style DNP properties, and checks output CSV fitted state, classification and quantity. Its export-failure case invokes the actual KiCad exporter on a malformed schematic. It does not substitute a fake successful exporter.
4. **Source of truth.** Reports fingerprint audit code, schematic, XML, sourcing and purchase orders. Inputs are rehashed before publication; a mutation during an otherwise real run produces FAIL. XML reuse is explicitly labelled and does not assert a fresh export or semantic parity with the schematic.
5. **Persistence.** Known-bad cases first obtain a PASS, then remove or corrupt the input and verify UNVERIFIED plus absent CSV. Default native export deletes the old XML first, so export failure cannot reuse it. Evaluated sourcing/order failures still emit an explicitly failed report and classified CSV, as before.
6. **Provenance.** The report distinguishes fresh native export from requested XML reuse. The isolated real-project comparison retains all nine existing purchase-order findings. This correction does not establish availability, approved substitutions or procurement completion.
7. **Known-bad calibration.** `checks/test_audit_bom_dnp.py` ran 22 CLI cases, all matching expectations; evidence is `checks/bom-dnp-calibration-v1/summary.json`. Cases include a DNP label with fitted property, fitted numeric values without sourcing or orders, missing/malformed/empty/duplicate inputs, failed export after PASS, and an actual mid-run input mutation. The former HEAD audit was also run on the numeric-DNP fixture and reproduced the false mismatch.
8. **Fix versus mute.** This changes the population contract, not the warning list: C4=22u and C8=1u remain explicitly DNP and excluded from purchasing. Incorrect DNP labels, fitted/no-source failures and order mismatches remain visible. Fail-closed persistence addresses stale results without accepting incomplete inputs.

The calibration took **3.861 s** in total. A separate isolated run using the real current project took **0.081 s**, compared with **0.063 s** for the former audit; this is one timing observation, not a general performance claim. That comparison is recorded in `checks/bom-dnp-real-project-v1/comparison.json`: the fixed audit reports nine existing procurement errors, and the former version reports those same nine plus false C4/C8 DNP mismatches. No live XML, sourcing, order, CSV or report was altered by the calibration.

Reproduce from the project directory with a fresh output directory:

```sh
python3 checks/test_audit_bom_dnp.py checks/bom-dnp-calibration-next
```
