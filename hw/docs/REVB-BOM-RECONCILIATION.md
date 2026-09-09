# Rev B BOM reconciliation — 9 September 2026

The schematic now names exact parts for C1/C7 and C9. J3 and J5 are declared
bare lands, and the two stale sourcing declarations are removed. The refreshed
purchase-order snapshot reduces the BOM audit from 17 errors to **8**: F3 has
no approved fitted part, and seven exact-MPN groups have no historical order.
This does not make the board ready to order or assemble.

The inventory calculation assumes **one board**, without assembly spares. It
covers 85 fitted positions, including the unresolved F3 placeholder; it excludes
six `exclude_from_bom` test pads, eight bare connector/wire lands, and two DNP
positions. Three additional cell receptacles are required separately (see below).
Across 36 grouped requirements, recorded stock covers 16 groups;
eight have a recorded stock shortage, seven exact-MPN groups have no catalog
match, four generic specifications are not mapped to stock, and F3 is unresolved.

## Selections and sourcing corrections

- **C1/C7: KEMET C1206C106K3RACTU**, 10 µF ±10%, 25 V, X7R, 1206.
  Manufacturer page 1 verifies the specification; DigiKey lists the exact part
  in cut tape, SKU `399-C1206C106K3RACTUCT-ND`, with 32,611 available at retrieval.
  [Manufacturer specification](https://yageogroup.com/component-documentation/download/specsheet/C1206C106K3RACTU?lang=en),
  [distributor](https://www.digikey.com/en/products/detail/kemet/C1206C106K3RACTU/3317476).
- **C9: KEMET C0603C102J5GACTU**, 1 nF ±5%, 50 V, C0G, 0603.
  Manufacturer page 1 verifies the specification; DigiKey lists the exact part
  in cut tape, SKU `399-C0603C102J5GACTUCT-ND`, with 464,623 available at retrieval.
  [Manufacturer specification](https://yageogroup.com/download/specsheet/C0603C102J5GACTU),
  [distributor](https://www.digikey.com/en/products/detail/kemet/C0603C102J5GACTU/608471).
- **J3** needs no fitted connector body. The reusable TC2030 cable/holding
  fixture is separate programming equipment.
- **J5** is a bare main-board land pattern. The external ring PCB, measured fork
  interface, assembly procedure and heater protection are still open gates.
- The unused `100n / 0603` and former metal-ring sourcing entries are removed.
  **F3 remains unsourced:** its design note explicitly says “DO NOT FIT AS DRAWN.”
  Assigning a generic zero-ohm resistor would conceal an unresolved design decision.

These capacitor selections preserve the existing values and footprints. Nominal
manufacturer capacitance is specified at 1 kHz/1 Vrms for C1/C7 and 1 MHz/1 Vrms
for C9. The voltage-rating ratios at the documented nominal operating limits are
25/15 = 1.67 for C1, 25/5 = 5 for C7 and 50/2.5 = 20 for C9. These are rating
ratios, not effective-capacitance guarantees or transient qualification. DC-bias,
ripple and first-article behavior remain part of electrical qualification.
No chart was visually digitized or used for a sourced numeric claim.

Murata GRM31CR71E106KA12L also matches the nominal C1/C7 specification, but its
exact DigiKey row showed zero stock and an expected receipt on 23 September.
Its substitute table's 32,611 figure belongs to the selected KEMET part. No
supplier substitution label was accepted without manufacturer verification.

## Current stock and shortages

Read-only InvenTree catalog capture: **2026-09-09**, exact timestamps and relevant
raw observations in [the inventory snapshot](../procurement/revb-inventory-2026-09-09.json).
The complete query returned 590 parts, 577 manufacturer parts and 602 supplier
parts. The order query returned 264 lines across 16 orders, all marked Complete.
There are **no currently open purchase orders** in that snapshot.

The table uses **unallocated physical stock**, grouped by InvenTree part PK before
subtracting demand. For example, the six 1 kΩ positions share PK384, and the six
47 kΩ positions share PK547; neither pool is counted twice. The four generic
47 kΩ positions use the stocked 0.1% part, alongside R34/R35. Generic mappings
use the catalog's explicit value, package and specifications; they do not rewrite
the schematic's generic parts into new approved exact-MPN requirements.

`unknown` means no resolved stock pool, not verified zero inventory. Those rows
require locating matching stock or procuring the listed demand. Recorded-zero
rows need the stated shortage unless a physical count and inventory correction
establish otherwise. Historical ordered/received quantities and distributor
availability never add to physical stock. Nothing was reserved, purchased or
changed in InvenTree.

| Refs | Exact MPN or generic requirement | Need | Unallocated | Shortage | Status |
|---|---|---:|---:|---:|---|
| F3 | 0R FITTED / R_0603_1608Metric | 1 | unknown | unknown | unresolved F3 design |
| F1 | 0ZCJ0075AF2E | 1 | 20 | 0 | recorded stock covers demand |
| R2, R3, R32 | 10R / R_0603_1608Metric | 3 | unknown | unknown | generic specification not mapped to stock |
| R10, R11 | 4.7k / R_0603_1608Metric | 2 | unknown | unknown | generic specification not mapped to stock |
| C10, C14 | 4.7u / C_0603_1608Metric | 2 | unknown | unknown | generic specification not mapped to stock |
| R31, R40 | 47R / R_0603_1608Metric | 2 | unknown | unknown | generic specification not mapped to stock |
| U8 | ADS1119IRTER | 1 | 0 | 1 | recorded stock shortage |
| Q2 | AO3400A | 1 | 50 | 0 | recorded stock covers demand |
| U1 | AP63205WU-7 | 1 | 0 | 1 | recorded stock shortage |
| U15 | AZ431BN-ATRG1 | 1 | unknown | unknown | no catalog match |
| DZ1 | BZT52C10-E3-08 | 1 | 20 | 0 | recorded stock covers demand |
| C9 | C0603C102J5GACTU | 1 | unknown | unknown | no catalog match |
| C1, C7 | C1206C106K3RACTU | 2 | unknown | unknown | no catalog match |
| C11, C12, C13, C15, C16, C18, C19, C2, C20, C21, C25, C27, C28, C29, C30, C31, C32, C33, C34 | CL05B104KO5NNNC | 19 | 0 | 19 | recorded stock shortage |
| R1, R17, R29, R9 | CRCW0603100KFKEA | 4 | 100 | 0 | recorded stock covers demand |
| RH1, RH2 | CRCW2512280RFKEG | 2 | 0 | 2 | recorded stock shortage |
| Q1 | DMP3130L-7 | 1 | 0 | 1 | recorded stock shortage |
| C3, C4 | EMK316BB7226ML-T | 2 | 50 | 0 | recorded stock covers demand |
| C17 | GRM1885C1H103JA01J | 1 | 50 | 0 | recorded stock covers demand |
| U7 | LMP91000SDX/NOPB | 1 | 0 | 1 | recorded stock shortage |
| U4 | OPA2333AIDGKR | 1 | 0 | 1 | recorded stock shortage |
| R18, R19, R27, R28, R8 | RC0603FR-0710KL | 5 | 100 | 0 | recorded stock covers demand |
| R33, R36, R37, R38, R41, R42 | RC0603FR-071KL | 6 | 25 | 0 | recorded stock covers demand |
| R26, R43, R44 | RC0603FR-0791KL | 3 | unknown | unknown | no catalog match |
| R24, R25, R34, R35, R45, R7 | RT0603BRD0747KL | 6 | 100 | 0 | recorded stock covers demand |
| U11 | SGX-OX-ROHS-Mini | 1 | 4 | 0 | recorded stock covers demand |
| U12 | SHT45-AD1F-R2 | 1 | 5 | 0 | recorded stock covers demand |
| D2 | SM712-02HTG | 1 | 20 | 0 | recorded stock covers demand |
| D1 | SMBJ15A-13-F | 1 | 25 | 0 | recorded stock covers demand |
| L1 | SRN6028C-4R7M | 1 | 10 | 0 | recorded stock covers demand |
| U6 | STM32G071CBT7 | 1 | unknown | unknown | no catalog match |
| U5 | THVD1410DR | 1 | 10 | 0 | recorded stock covers demand |
| C26, C5, C6, C8 | TMK107B7105KA-T | 4 | 25 | 0 | recorded stock covers demand |
| U10 | TMP117AIDRVR | 1 | 0 | 1 | recorded stock shortage |
| D7 | TPD2E2U06QDBZRQ1 | 1 | unknown | unknown | no catalog match |
| U2, U3 | TPS7A2033PDBVR | 2 | unknown | unknown | no catalog match |

[Shortage/unresolved CSV](../procurement/revb-shortages-2026-09-09.csv) contains
the 20 PCB groups still requiring action plus the cell-receptacle assembly row. It is a reconciliation worksheet,
not a basket to submit: F3 is a design hold, and unknown stock is not a measured
shortage. Quantities exclude spares and external assemblies.

F1, DZ1, L1 and R34/R35 were missing only from the old order snapshot: their
exact parts are now recorded in stock. Conversely ADS1119, AP63205, the heater
resistors, DMP3130L, LMP91000, OPA2333, TMP117 and the selected 100 nF/0402 stock
pool currently show zero, despite complete historical orders.

The stocked `STM32G071CBT6TR` (PK532, quantity 10) is not accepted as an alias
for `STM32G071CBT7`. The selected temperature grade remains unchanged. Likewise
1 kΩ is not 91 kΩ; TPS3840 is not TPS7A20; 220 pF is not C9's 1 nF; and the
stocked 10 µF/16 V/X6S/0805 capacitor does not satisfy C1/C7's requirement.

### Cell receptacles — separate required assembly parts

U11 requires **three PCB receptacles**, explicitly called out in the SGX footprint
description. They are not included in the schematic cell line. Inventory PK551
contains ten `5050462-2` receptacles, but the local footprint evidence specifies
the TE 5050462 family rather than this exact suffix. The snapshot and CSV carry
this as an open socket qualification: demand 3, candidate stock 10, approved
coverage/shortage unknown. Confirm the exact suffix and fit against the approved
socket drawing before assigning these three pieces to the build. This is an
assembly requirement, not an optional consumable.

## Remaining decisions

The seven unordered exact groups are C1/C7, C9, U15, R26/R43/R44, U6, D7 and
U2/U3. Resolve these and the current-stock worksheet before assembling a board.
F3 requires an actual heater/protection decision. J5 requires measured interface
geometry and the external ring design. L1's existing land-pattern/manual-assembly
qualification remains open even though its exact MPN is in stock. The existing
[release gates](REVB-FAB.md#open-release-gates) and
[assembly dispositions](REVB-ASSEMBLY.md) still apply.

## Source access log and provenance

All public sources below were inspected on 9 September 2026. Their exact URLs,
locators, archived PDFs or evidence pointers and hashes are in the
[capacitor source index](../literature/bom-capacitors/INDEX.md). Manufacturer
specification facts are direct evidence; choosing matching nominal parts is an
engineering inference. Distributor stock is a dated observation, not a promise.

| ID | Work / version | Attempt history | Evidence / route / validation | Load-bearing |
|---|---|---|---|---|
| M1 | Murata GRM31CR71E106KA12L product page, live | Browser initially returned product shell; same context after 10-second wait rendered specification and packaging tables | Inspected / native DOM / validated | Yes, candidate comparison |
| K1 | KEMET C0603C102J5GACTU specsheet, generated 09/09/2026 | First curl retrieved genuine four-page PDF; page 1 extracted and rendered | Inspected / raw PDF text / visually validated page 1 | Yes |
| K2 | KEMET C1206C106K3RACTU specsheet, generated 09/09/2026 | First curl retrieved genuine PDF; page 1 extracted and rendered | Inspected / raw PDF text / visually validated page 1 | Yes |
| D1 | DigiKey GRM31CR71E106KA12L, live | Initial curl: interstitial. Coherent Sec-Fetch-header retry: real 472,613-byte HTML, exact title/attributes/availability. An additional scratch-browser attempt remained on security verification after 35+45 seconds; the source was already obtained through curl | Inspected / native HTML / validated | Yes |
| D2 | DigiKey C0603C102J5GACTU, live | Initial curl: interstitial. Coherent-header retry: real 382,702-byte HTML, exact title/attributes/availability | Inspected / native HTML / validated | Yes |
| D3 | DigiKey C1206C106K3RACTU, live | Link discovered in D1; first coherent-header curl retrieved exact product HTML | Inspected / native HTML / validated | Yes |
| I1 | InvenTree catalog and purchase orders, timestamps in snapshot | Authorized read-only API, pagination completed; identity matching and stock arithmetic performed locally | Inspected / structured API / validated required numeric fields and order statuses | Yes |

Browser control was proven before public retrieval by creating an isolated context
in an existing scratch Chrome (PID 34708, port 9333, profile
`/var/folders/dq/0l3glys549x48y9pbgh3075c0000gq/T/agent-chrome-ble-telem-review-do9WZI`),
navigating `about:blank` and reading its DOM and normal Chrome 152 user agent.
An earlier scratch endpoint 9224 timed out; the in-app browser was unavailable.
This run launched no browser and touched no live user profile. The owned context
was closed and its client exited normally; the pre-existing browser and its other
contexts were left running. No interactive CAPTCHA was encountered or bypassed.
No source remains unobtained.

Discovery used Serper queries for `10uF 25V X7R 1206 Murata GRM31 product`,
`GRM31CR71E106KA12L site:murata.com`, `GRM31CR71E106KA12L DigiKey`,
`1nF C0G 0603 50V Kemet C0603C102J5GACTU`, and
`C1206C106K3RACTU site:yageogroup.com`. Snippets served only to locate sources.
The source seeds were the existing schematic values/notes and sourcing file.
This was matching frozen passive specifications, so application/practitioner
literature was not used to introduce a circuit change. Catalog non-matches are
bounded to the captured inventory, not claims that parts are unavailable globally.

## Validation and review

The Rev B engineering package rebuilt successfully with KiCad 10.0.5: zero ERC,
copper, connectivity, schematic-parity or silkscreen findings; the same 15 reviewed
manual-assembly courtyard warnings remain. All 303 physical pins/101 component
fields and 63 locked critical-route items pass. BOM remains FAIL with 8 errors.

Latest package: `o2-probe-rev-b-0c6dbe69dcaf3f52`, ZIP SHA-256
`0c6dbe69dcaf3f5280f3242a7ac3e3e73092f73f02d07cf567965dcc54cdb510`. It remains explicitly `order_ready: false`.
The accepted PCB diff adds only three MPN properties; normalized comparison
confirms the reviewed geometry is unchanged.

Independent review identified the omitted cell receptacles; the separate
three-piece requirement and its unresolved exact-suffix qualification are now
included in the report, snapshot and CSV. Re-review found no unresolved findings. All 14 existing export calibration tests
passed in 0.320 seconds. Firmware tests were not rerun because this change only
adds sourcing metadata; the earlier native-test record is labeled inherited.
