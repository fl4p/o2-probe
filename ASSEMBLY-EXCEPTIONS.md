# Rev A manual-assembly exceptions

This revision is for bare-board first articles and hand assembly, not automated
turnkey PCBA. KiCad reports the following 29 courtyard pairs; their exact set
is locked by `audit_pcb.py`:

| Pair | Pair | Pair | Pair |
|---|---|---|---|
| C1 / U1 | C3 / L1 | C5 / U2 | C11 / C12 |
| C14 / C26 | C15 / R8 | C15 / R9 | C23 / U11 |
| C25 / J2 | C31 / RV1 | D1 / J101 | D1 / J102 |
| D2 / J103 | D2 / J104 | D4 / R12 | D5 / R14 |
| D6 / J2 | J2 / TP1 | J2 / TP5 | J103 / R2 |
| J104 / R3 | Q2 / TP6 | R10 / R11 | R17 / U4 |
| R20 / RV1 | R22 / R23 | R38 / RV1 | TP3 / U4 |
| U10 / U11 |  |  |  |

Inspect component-body, hand-solder, and rework clearance on the first article.
J5 is a separate manual operation: inspect both plated castellation sidewalls,
verify ring material/plating, use controlled heat and flux, prevent solder
wicking into the membrane carrier, and inspect dry-side electrical insulation
before power is applied.

U11 is also a physical gate: fit an actual SGX-OX-ROHS-Mini, verify pin identity
from the PCB side, and confirm the rear gas path against the 3 × 6 mm NPTH
aperture. Any automated assembly release needs a new courtyard/process review.
