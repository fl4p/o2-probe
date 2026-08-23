# Rev A manual-assembly exceptions

This revision is released for bare-board first articles and hand assembly. It
is not approved for automated turnkey PCBA. KiCad reports the following 28
courtyard pairs; their exact set is locked by `audit_pcb.py`:

| Pair | Pair | Pair | Pair |
|---|---|---|---|
| C1 / U1 | C3 / L1 | C5 / U2 | C11 / C12 |
| C14 / C26 | C15 / R8 | C15 / R9 | C25 / J2 |
| C31 / RV1 | D1 / J101 | D1 / J102 | D2 / J103 |
| D2 / J104 | D4 / R12 | D5 / R14 | D6 / J2 |
| J2 / TP1 | J2 / TP5 | J103 / R2 | J104 / R3 |
| R10 / R11 | R17 / U4 | R20 / RV1 | R22 / R23 |
| R38 / RV1 | RH1 / U10 | RH2 / U10 | TP3 / U4 |

Inspect paste access, component-body clearance, hand-soldering access, and
rework access on the first article. Any automated assembly release requires a
fresh courtyard review and a procurement BOM with exact passive MPNs.

U11 is a separate physical gate: fit an actual SGX-OX-ROHS-Mini, verify pin
identity from the PCB side, and confirm the rear gas path against the 3 × 6 mm
NPTH slot before production qualification.
