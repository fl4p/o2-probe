# O2 probe fabrication-readiness gate

Status date: 2026-08-22

## Passed from design artefacts

- Schematic ERC: 0 violations.
- Schematic connectivity audit: PASS, 111 components and 93 nets.
- PCB schematic parity: 0 issues.
- PCB electrical connectivity: 0 unconnected items.
- PCB completion-critical DRC: 0 shorts, clearance, hole, edge, track-width,
  dangling-copper, starved-thermal, or silkscreen violations.
- Controlled outline: 20.00 x 125.00 mm, 1.00 mm thick, four copper layers,
  six routed slots, cell centre `(10.00, 93.50)` mm.

## Open gates that prevent fabrication release

### Assembly placement

- Resolve and reroute the 31 courtyard overlaps reported in `pcb-drc.rpt`.
- Reconcile the 110 embedded-footprint/library-copy warnings by making the
  generated/project-local footprint source authoritative.

### SGX cell interface

The current SGX Issue 2 drawing defines the body and pins, but not the rear
gas-port diameter. For this prototype, the user explicitly accepted a
drawing-derived estimate and the aperture was increased from 2.5 to 3.0 mm.
This retains 0.20 mm copper clearance to the nearest 1.60 mm pin pad. Routed
copper is also kept outside a Ø4.50 mm construction envelope around the port.
That protects traces during careful prototype rework, but does not remove the
centre-pin-pad limit: a drill above Ø3.40 can begin cutting pad 2, and Ø3.00 is
the largest diameter retaining the audited 0.20 mm pad clearance. Before a
production release of `SGX-OX-ROHS-Mini_DRAFT`:

- measure the rear-port diameter and its offset from the body centre on the
  actual sample;
- gauge the three pin diameters and verify comfortable insertion into the
  proposed finished holes after plating tolerance;
- confirm Counter/Reference/Working identity as viewed from the PCB side;
- measure body-to-board standoff and confirm both gas faces remain open;
- compare the 3.0 mm estimated aperture with the measured port and run a 1:1
  dummy-board fit.

### Enclosure and potting fixture

- Record the minimum measured ID and ovality of the actual 32 mm PVC-U tube,
  not the nominal approximately 28 mm value.
- Record guide, membrane-carrier, potting-flash and solder-joint intrusions,
  then verify the full front/back swept component envelope.
- Decide J2 Micro-Fit versus the sealed pad-field fallback from that section.
- Freeze dam seal-land, slot endpoints, thermal-neck widths and cell/membrane
  carrier geometry from the actual fixture and thermal model.

### Fabricator capability

- Select the fabricator and obtain an accepted four-layer 1.0 mm stack-up.
- Obtain written capability acceptance for 0.075 mm tracks, 0.25/0.15 mm vias,
  0.05 mm annular rings and the routed-slot geometry.
- Re-run DRC against that fabricator's actual constraints before plotting.

### Bench qualification

- VREF stability, startup and noise with heater at 0%, intermediate and 100%.
- Heater 0–4 K thermal range, stuck-on safety and actual cell cold-spot test.
- TMP117 pair isothermal calibration and final gas-path calibration.
- N2 zero, air point and 30% O2 compliance across temperature.
- Saturated soak/condensation cycles, membrane wetting response, cable
  capillary soak and potting cure/process coupons.

Gerbers, drill files and placement outputs must not be labelled `RELEASED`
until every gate above is closed with a recorded measurement or test result.

## Source access log

| Source | Evidence state and locator | Attempt history and route | Validation | Load-bearing |
|---|---|---|---|---|
| SGX Sensortech product page, <https://sgxsensortech.com/sensor/sgx-ox-rohs-mini> | Inspected: product identity, description and live Issue 2 datasheet link | Standalone Playwright with installed Chrome; first rendered attempt returned substantive live DOM | Validated live DOM | Yes |
| SGX Sensortech `SGX-OX-ROHS-Mini`, DS-0637 Issue 2, 28-May-2026, <https://sgxsensortech.com/uploads/f_note/DS-0637-SGX-OX-ROHS-Mini_iss2.pdf> | Inspected: identity block, operating/physical tables and product-dimensions drawing, page 1/1 | Direct Chrome PDF navigation returned the browser viewer shell; exact DOM-derived manufacturer URL then retrieved with coherent desktop UA and product-page referrer. Route: raw PDF text plus rendered-page vision for drawing relations. SHA-256 `4d1d4479580ab98bbc525aaf4aca353745b99368bc020a76d7f8ec12964ceae7`. | Validated against 300 dpi rendered page | Yes |

Archive status: the retrieved PDF remains in temporary working storage because
no project literature-archive location was authorized for this hardware repo.
