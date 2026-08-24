# O2 Probe PCB — SGX-OX-ROHS-Mini buried compost probe

## Context

COMPOST-O2-SENSORS-BUDGET.md selected the SGX-OX-ROHS-Mini (46,20 €, −40…+60 °C,
biased 3-electrode EC cell) as the DIY scale-out cell, conditional on a heated
port: the buried probe conducts heat outward, so every surface otherwise sits
below the dew point of 100 % RH pore gas, and the cell's *continuous* rating is
only 15–90 % RH. This project builds that probe: cell + potentiostat AFE +
closed-loop ΔT heater + environment channels, as a Modbus RTU slave on the
existing farm RS485 bus. First deployment validates against the heated Apogee
reference per the report's first-experiment plan.

**Decisions locked with Fab:** LMP91000 AFE · probe-side MCU + RS485 Modbus
(4-wire farm convention: brown +12 V, white GND, green A, yellow B) · single
12 V feed (SDI-12-LB supply or PSU; design input 7–15 V) · closed-loop
membrane-ring heater (RH-primary, PWM) · one TMP117 at the warm tip with a
hardware heater-off ALERT path ·
SHT45-AD1F (**polyimide** membrane variant — not PTFE; corrected per Codex
review, matters for the NH₃ question) as a ±3–5 %RH condensation-margin
**health channel**,
not a calibrated hygrometer (datasheet: >80 %RH long-term gives ~+3 %RH
standing offset) · **no SCD41** — pore CO₂ (mean ~17.7 %, up to 75 %) pins its
4 % output cap permanently (COMPOST-GAS.md:230); replaced by an **expansion
connector** (12 V, 3.3 V, I2C, spare UART) on the sealed side for a future
SenseAir K33-ICB 0–30 % CO₂ head (51×57 mm module — needs its own housing) ·
DNP barometer footprint (BMP390).

Plan + review log live here (`farming/o2-probe/`). KiCad project target:
**`/Users/fab/dev/ee/hw/o2-probe/`** (the hw repo, beside tmp117-probe);
Phase 2 links/copies this plan there.

## Architecture

**One elongated 4-layer PCB with potted and gas zones separated by an assembly
potting datum** (silkscreen "POT TO HERE" line), followed by two horizontal
5.5 × 1.0 mm thermal-break slots at absolute y=134 mm.
Two-PCB head/body was rejected: an inter-board
connector adds a leakage path exactly where sub-µA integrity matters and
doubles the sealing problem.

```
[cable]── POTTED ZONE ──────────────────────────────┬─dam─┬── GAS ZONE ─────[tip]
  pads → protection → buck/LDOs → MCU + RS485      │       │ SGX-OX cell (TH)
  expansion + programming                             │       │ SHT45 + one TMP117
  trimmed VREF → LMP91000 → ADS1119                │       │ 2×2512 + heater FET
  driven guard around CELL_RE                         │       │ heated ring lands [tip]
```

### PCB outline (controlled layout datum)

Working KiCad design:
[`o2-probe.kicad_pcb`](/Users/fab/dev/ee/hw/o2-probe/o2-probe.kicad_pcb)
with [placement notes](/Users/fab/dev/ee/hw/o2-probe/PLACEMENT.md). The board is
schematic-linked and electrically routed; provisional mechanical interfaces are
called out in the notes. The working KiCad board is authoritative for the
bare-board first article. Freeze production geometry only after a paper print
plus a 1:1 dummy-board fit in the
actual 32 mm tube, with the cable termination, expansion connector, cell,
membrane carrier, and potting fixture installed.

Coordinate system: view from the component side, cable end at `y = 0`, probe tip
at `y = 107`, board centreline at `x = 10`. All dimensions below are mm.

```
                20.0
       x=0  ┌──────────────┐  x=20
            │ cable pads   │  y=0
            │ protection   │
            │ power / MCU  │  POTTED: y=0…82
            │ RS485 / AFE  │
            ├- - POT TO - -┤  y=82 datum
            │  dam / neck  │  TRANSITION: y=82…86
            ├──────────────┤
            │ heated tip   │
            │   ┌──────┐   │
            │   │  O2  │   │  cell centre (10,93.5)
            │   │ cell │   │  GAS: y=86…107
            │   └──────┘   │
            │ SHT45 TMP117 │
            │ring edge pads│
            └──────────────┘  y=107
                 tip
```

- **Outer `Edge.Cuts`:** 20.0 × 107.0 with nominal R2 cable-end corners and a
  square gas-side end. FR-4, 4 layers, 1.0 mm thickness; a different thickness
  is allowed only after the tube chord/assembled-height check. The 20 mm width leaves nominal 4 mm
  radial clearance per side in the ≈28 mm tube ID, but this is not a component
  height allowance: verify the complete swept envelope in section and include
  tube-ID tolerance, board bow, solder joints, coating, and potting flash.
- **No PCB mounting holes in Rev A.** The board is located by the end-cap/potting
  fixture and non-metallic tube guides. Do not add a screw beside the AFE or
  create another axial leak path merely to retain the PCB.
- **Potting datum:** `y = 82.0`, controlled on both source legend layers with
  `POT TO HERE` and an unbroken transverse line. Rev-A first articles omit
  physical legend, so the included fabrication/assembly drawing and potting
  fixture own this datum. Reserve `y = 80…86` from ordinary parts. The actual
  removable dam clamps around the PCB at this datum; its seal land and the
  cable-side meniscus must finish at or beyond `y = 82`, while every AFE
  high-impedance node remains on the potted side.
- **Thermal-break slots:** the potting boundary remains an assembly datum, not
  an `Edge.Cuts` feature. Two 5.5 × 1.0 mm horizontal slots follow at absolute
  y=134 mm, leaving 1 mm edge webs and a 7 mm centre neck. The In2 GND zone is
  clipped by the contours but remains electrically continuous through those
  webs/neck. The SGX footprint adds a separate 3 × 6 mm NPTH rear-flow oblong.
- **Primary cell datum:** SGX-OX-ROHS-Mini body centre `(10.0, 93.5)`, body
  envelope Ø14.4 + datasheet tolerance. Rotate it with the three-pin row toward
  the dam/AFE. Start the footprint from the datasheet's 2.54 mm pin pitch and
  2.50 mm pin-row offset, but verify a physical sample before production release.
  Keep a Ø15.0 courtyard free of unrelated parts and preserve access to the top
  gas face.
- **Rear gas path:** plated-copper-free 3 × 6 mm NPTH slot centred at
  `(10.0, 96.0)`, offset gasward from the cell centre while spanning its rear
  axis. The Issue 2 datasheet does not dimension the rear port, so this is an
  explicit first-article fit/flow feature rather than an invented port diameter.
  Confirm the opening against a physical sample before production release.
  Mark the controlled drawing `DO NOT OBSTRUCT`; solder mask/copper keepouts
  alone do not satisfy this.
- **Heated-ring tip:** RH1 and RH2 sit on the back at `(5,96.5)` and
  `(15,96.5)`. U12 is at `(3.5,101.5)`, U10 at `(10,102)`, and the DNP BMP390
  option at `(16.5,101)`. J5 provides two 2.0 × 3.0 mm PTH pads centred on the
  left/right board edges at `(0,105.5)` and `(20,105.5)`. Their 1.0 × 2.0 mm
  plated slots are explicitly marked castellated and bisected by the finished
  side profile. Both pads are joined by wide back copper on switched
  `HEATER_LOW`; the metal ring is a thermal
  spreader, not an electrical jumper. It must remain on the insulated dry side
  of the PTFE membrane stack.
- **Warm-tip sensing:** there is one TMP117, 3.5 mm from the J5 centreline. Its
  ALERT directly clamps the heater gate off. It is not a substitute for
  membrane cold-spot thermometry: qualification must temporarily instrument
  the membrane/carrier minimum and identify its mapping from U10, heater power,
  inlet state, and orientation.
- **Short gas end:** the square end stops at `y = 107`; the SGX centre is
  13.5 mm from that end. The enclosure, ring, and membrane carrier set the
  actual cell-to-membrane distance. Verify it on a 1:1 tube coupon.
- **Cable end:** reserve the first 8 mm (`y = 0…8`) for four staggered solder
  pads, water-blocking/strain-relief geometry, and polarity silkscreen. Copper
  and components may not project beyond the outline. Expansion-connector height
  is checked against the circular tube chord; use the documented pad-field
  fallback if the Micro-Fit swept envelope does not close.
- Put the outline, pot datum, cell centre, rear aperture, ring castellations, and
  maximum assembled-height/chord check into `DESIGN.md` as controlled dimensions.
  `audit_pcb.py` must reject an open/deformed outline, an unexpected or
  deformed board-native slot,
  moved/missing gas aperture, missing pot line, stale second-sensor copper,
  moved, deformed, or unplated ring castellations, narrow ring-heater copper, or a
  missing/unfilled continuous GND plane.

- Gas zone: selective conformal coat (apertures clear); cannot be potted.
- Potted zone: potted solid — covers LMP91000, the C/R/W traces, everything
  cable-ward. Potting is also the cable strain relief (no connectors buried).
- **LMP91000 placement:** potted side, <10 mm from cell pins. Leakage scale
  corrected per Codex (arithmetic verified): the threat is not pA — 0.1 % O₂
  ≈ 335 nA, so ~1.8 MΩ of wet contaminated surface across 600 mV already
  produces that error; a condensed pin escape is plausibly in that range.
  Error budget therefore targets **wet-board leakage into WE/RE/CE, flux
  residue, pin creepage** — controls are cleaning/bake/coat/pot process (with
  a leakage test coupon) plus a **driven guard**: guard the RE trace from a
  low-impedance replica of the RE target potential (≈0.91·VREF at the chosen
  internal zero; buffered divider). **A grounded guard is rejected** — with
  V_RE ≈ 2.275 V it maximizes the surface voltage instead of minimizing it.
  Guard potential is specified before layout, not deferred. No mask relief or
  vias on the RE trace.
- **AFE bias verdict (Codex, to re-confirm from LMP91000 Rev. I in Phase 1):**
  the 24 % bias step exists and BIASSIGN gives V_WE−V_RE < 0, but the step
  tolerance is **±2 % of VREF = ±50 mV at 2.5 V** against the cell's ±10 mV
  window → **fixed 2.5 V VREF is rejected.** Phase 1 decides between (a)
  per-board trimmed VREF (~2.31–2.73 V trim range, test points, trim measured
  as V_WE−V_RE with the real cell connected — viable for 3 prototypes) and
  (b) the discrete potentiostat (zero-drift op-amp pair), now co-equal rather
  than fallback. Also from the review: SGX's "−600 mV" sign convention is
  unstated — the vendor confirmation is necessary, not ceremonial; CE
  compliance is unspecified by SGX → bench-measure V_CE at 0 %/air/30 % over
  temperature.
- Membrane-ring heater: ~140 Ω effective RH1/RH2 load gives approximately
  1 W ceiling at 12 V. U10 supplies warm-tip temperature and a hardware-off
  limit; SHT45 supplies chamber RH/temperature. The release target is a
  positive minimum membrane dew margin over a 0–4 K operating rise, established
  by calibration rather than a two-sensor PCB ΔT assumption.
- tmp117-probe rules carried over: **no I2C pullups on sensed islands; ADD0
  never floats.**
- Tube target: 32 mm OD PVC-U pipe (ID ≈ 28 mm) clears the 14.4 mm cell can;
  Rev-A outline = 20 × 107 mm (dimensioned above); gas window = heated
  dry-side carrier ring + ePTFE membrane + mesh
  (enclosure work). Cell faces marked DO NOT OBSTRUCT: the rear vent needs a
  **routed aperture through the PCB (or specified standoff + lateral gap)**,
  not merely a copper keepout — copper keepout provides no gas flow (Codex).
  Gas openings oriented laterally/downward with a condensate drain path; the
  membrane can be diffusion-blocked by a water film/biofilm — response time
  tested with the final mesh + membrane wetted externally.
- **Cable:** water-blocked cable or individual-conductor sealing at the pot —
  stranded conductors and jacket interfaces are capillary paths that bulk
  potting alone does not stop; soak/cross-section test in bench phase.
- **Potting process specified before assembly:** low-exotherm, low-shrink,
  low-ionic-content compound; max cure temperature; pour depth per pass;
  pre-bake/clean; cure before mounting the EC cell where possible (WSON/DFN
  shrink stress and exotherm are latent-failure sources).
- **Deployment ceiling corrected:** with the heater riding up to ~4 K above
  pile gas, the cell's +60 °C limit caps supported pile-gas temperature at
  **~56–58 °C**, not 60 (Codex). TEMP_OVER flag fires at the derated
  ceiling; > 60 °C cell temperature invalidates data per COMPOST-O2.md §6.

**I2C map (conflict-checked):** 0x44 SHT45 · **0x48 LMP91000 (fixed)** ·
TMP117 at 0x49 (ADD0→V+) · ADS1119 at 0x40 (A1=A0=GND) ·
0x76 DNP BMP390 (**SDO strapped
low, CSB defined** — must not float) · 0x68 reserved for K33 on expansion.
**Bus at ≤100 kHz** (LMP91000 is standard-mode only). MENB MCU-controlled
**with defined reset state** (pullup or tied), so I2C availability is
deterministic through MCU reset.

**Expansion connector** (replaces SCD41): 8-pin — 12 V, GND, 3V3_D, SDA, SCL,
EXP_INT/GPIO, UART_TX/RX (STM32G071's second USART; degrades to GPIO if pins
run out — K33 speaks I2C anyway). On-board: Molex Micro-Fit 3.0 2×4
(−40…+105 °C) in the potted zone just above the pot line (pad-field fallback
if mated height ~10 mm doesn't clear the tube ID). Enclosure side: second
cable gland or field-sealed M12 8-pin A-coded on the end cap; blanked when
unused. K33 ICB powers from the 12 V pin (it wants 4.5–14 V — verify in
Phase 1). TVS array (TPD4E05-class) + series R on expansion signals; 3V3
expansion budget documented as a hard number (e.g. 200 mA max); I2C bus
capacitance budget for the pigtail recorded in DESIGN.md.

**ADC:** **ADS1119** (16-bit, I2C, REFP/REFN external-reference pins,
−40…+125 °C) referenced to the same 2.5 V VREF — true ratiometric. (The
originally planned ADS1115 has only an internal reference; "ratiometric
against VREF" was not implementable as written — Codex finding, verified
against the ADS1115 block diagram. ADS1114/MCP3421 share the problem.)
TIA: LMP91000 internal **7 kΩ** (internal options are 7/14 kΩ, not 10 kΩ);
full-scale headroom sized for ≥150 µA — SGX's log response with a
high-tolerance cell gives ~152 µA at 30 % O₂ (100 µA × ln(1/0.7)/ln(1/0.791)),
→ ~1.06 V excursion from the 67 % internal zero, inside 0–3.3 V. 0.1 % O₂
≈ 335 nA — comfortably resolved.

**MCU:** STM32G071CB, −40…+105 °C grade (ESP32-C3 rejected: 85 °C modules,
radio is dead weight in a buried tube). USART+DE for Modbus RTU. SWD via
TC2030 pads **plus** BOOT0 + UART header for probe-less field reflash.

**RS485:** THVD1410/SN65HVD72 class (−40…125 °C). Failsafe bias **and**
termination both DNP by default — a shared bus gets exactly one bias network
(normally at the master); per-slave bias loads the bus and can fight another
installation (Codex). **DE hardware pulldown** so the slave cannot transmit
during MCU reset; firmware Modbus rules: never transmit unsolicited, enforce
turnaround timing, survive stuck master/truncated frames.

**Power tree:** 12 V → buck 5 V (≥400 mA, fixed ≥600 kHz, shielded inductor)
→ 3.3VD (logic/RS485/sensors) and 3.3VA low-noise LDO (TPS7A20-class: VREF,
LMP91000, ADS1119). **Bias supervision (Codex — LDOs don't guarantee it):**
LMP91000 powers up in deep sleep with volatile config, and MENB only gates
I2C — a 3.3VA brownout with the MCU alive silently drops bias without a cold
boot. Firmware: periodic LMP91000 register readback, 3.3VA/brownout monitor,
and the 15-min SETTLING timer restarts on any config-mismatch or rail event,
not just power-on. **Return-path rules:** heater pulse (~86 mA) and
buck-switch loops routed to cable-entry ground away from AFE ground;
continuous plane; RC at the ADC; EMI validated with heater at 0 %,
intermediate, and 100 % duty — not only heater-off.

## Firmware sketch (register map committed to DESIGN.md)

Input regs: O2 raw (µA×100) · O2 compensated (%vol×100) · T_tip · T_chamber
(0.01 °C) · RH_margin (0.01 %) · EXP data (e.g. K33 CO₂; 0xFFFF = absent) ·
VREF/VOUT diag · pressure (0 if DNP) · heater duty · ΔT target · fault
bitfield · uptime · settle-timer · fw version.
Fault bits: SETTLING (boot, 15 min) · I2C_FAIL per device · HEATER_RUNAWAY ·
VIN_LOW · TEMP_OVER (T_gas > 60 °C, log-only) · DEW_SUSPECT ·
EXP_PRESENT/EXP_FAIL (boot-time auto-probe of reserved addresses).
Holding regs: slave addr, baud, ΔT setpoint, heater max duty, cal constants
(log-linearity K, air-point), SHT45-pulse trigger.
Heater control: **primary loop
regulates measured chamber RH** (SHT45, hold ~85–90 % — the actual controlled
quantity: condensation margin + the cell's 90 % continuous-RH spec). The one
TMP117 provides an independent warm-tip limit and its ALERT is a hardware-off
clamp. If SHT45 fails, firmware may run only a conservatively bounded fallback
derived from the validated membrane thermal model; otherwise safe state is
heater off and data invalid. Psychrometric screening: +2 K
gives only ~90–91 % RH on saturated gas; 85 % needs ~3.1–3.7 K at 40–65 °C —
**design the thermal path for a 0–4 K ΔT range**, not a fixed 2 K. **SHT45
placement: in the warmed cell microclimate** (same heated volume as the
cell), not at a remote unheated inlet. **Cold-spot problem:** U10 measures PCB
copper, but
the 5 g ABS cell couples via three pins and gas — the cell cap or vent can
sit at dew point while the PCB reads warm. The ring directly heats the dry
membrane carrier; instrument the actual coldest membrane/carrier surface during
qualification. **Stuck-on safety (hardware, not firmware):** FET gate
pulldown, watchdog-bounded enable, absolute cell-temperature cutoff, heater
resistors and ring safe at 100 % duty. Use approximately 1 Hz PI, ~1 kHz PWM,
anti-windup, and a duty clamp. SHT45 heater-pulse routine (every 6–12 h + on demand): de-creep plus
dew detection — dry sensor recovers RH quickly post-pulse, wetted sensor shows
the slow-recovery signature → DEW_SUSPECT classifier; pulse + settling window
masked from the RH_margin channel; pulse duty limit per SHT4x datasheet
(exact figure verified in Phase 1).
O₂ compensation: datasheet output-vs-T curve + air-point cal; report raw AND
compensated.

## Scaffolding (reuse from tmp117-probe)

Generated schematic and deterministic PCB migration/routing, keeping the
verification discipline established by `/Users/fab/dev/ee/hw/tmp117-probe/`:

- `project_settings.py` — verbatim pattern (pcbnew `.kicad_pro` clobber guard;
  `verify()` stays a gate).
- `audit_pcb.py` + `--calibrate` inject-defect discipline — checks the RE
  guard, exact outer/thermal-slot contours, SGX NPTH, plated ring castellations, heater
  copper floor, continuous filled In2 GND plane, obsolete-sensor absence,
  cable-pads↔logic creepage, expansion-connector clearance to the potting
  line, SHT45 hand-rework accessibility (it's a maintenance consumable —
  replaced at cell-service intervals).
- Project-local footprints include the first-article SGX pattern and the
  two-contact castellated heated-ring interface.
- TMP117 symbol/footprint from `tmp117-probe/lib/`; everything else new in
  per-project `lib/o2-probe.{kicad_sym,pretty}` (repo convention: no shared
  lib table).
- Gates: `kicad-cli sch erc --exit-code-violations`, `kicad-cli pcb drc
  --severity-all --schematic-parity --exit-code-violations`, netlist-vs-intent
  review, `project_settings.verify()`, audit pass. BOM export **without**
  `--group-by` (tmp117-probe lesson: grouping merged DNP variants).
- `DESIGN.md` skeleton: verification-status table · per-part datasheet fact
  tables with citations · partitioning rationale · AFE error budget
  (bias/VREF/TIA/leakage) · power tree · heater thermal sizing · I2C map ·
  Modbus map · mechanical/potting · risks · fab notes.

## Phases

1. **Datasheet verification (blocking).** Fetch & verify (kicad-happy:digikey
   / lcsc skills): **LMP91000** — the go/no-go: 600 mV = 24 % × 2.5 V is the
   top bias step; confirm step existence/tolerance, BIASSIGN polarity for this
   cell, 3-lead mode, VREF input range, TIA gain for 0.1 mA FS with
   log-linearity headroom (S = K·ln(1/(1−C))), internal-zero offset, 85 °C
   derating. If tolerances don't close the cell's ±10 mV bias window →
   fallback discrete potentiostat (zero-drift op-amp pair) decided HERE. Also:
   STM32G071 105 °C order code + LCSC stock, RS485 xcvr, buck, LDOs, VREF,
   ADS1119, SHT45-AD1F, BMP390, heater FET, **SGX-4OX-ROHS outline** (rear
   vent → combined footprint vs adapter), Sensirion "Handling Instructions
   SHT". Send the SGX CO₂-cross-sensitivity inquiry (whole OX family) now.
2. **Scaffolding.** Create `o2-probe/`, copy scripts, DESIGN.md skeleton,
   `PLAN.md` (this file).
3. **Symbols/footprints.** New parts + TMP117 reuse; cell footprint.
4. **Schematic.** Blocks above; ERC gate; address/strapping asserted; AFE
   error-budget table written alongside.
5. **Layout.** Zone partition, guard ring, pot datum, compact heated-ring tip; buck
   far from AFE + LC post-filter; DRC + settings verify.
6. **Audit.** Rewrite audit.py checks, `--calibrate`, record in DESIGN.md.
7. **Fab outputs.** BOM/CPL/Gerbers and capability confirmation from the
   selected fabricator; do not infer JLCPCB or any other vendor.

## Verification

- Every gate in §Scaffolding green; DESIGN.md status table complete.
- AFE error budget closes: bias within ±10 mV incl. VREF + step tolerance;
  0.1 % O₂ resolution at the ADS1119 with stated noise.
- Bench before pile (report's discriminating tests + Codex additions): 2-week
  saturated soak with condensation cycles; heater loop holds target RH/ΔT
  across the 0–4 K range; zero-check in N₂ (cell zero < 0.4 % vol spec);
  air-point cal stability; U10/ring/membrane thermal-map calibration; V_CE compliance
  measured at 0 %/air/30 % O₂ over temperature; cell orientation
  characterized (horizontal/vertical/inverted — SGX is silent; assert
  nothing untested); heater stuck-on case exercised; cable soak/capillary
  test; **final calibration with the complete gas path** (membrane, window,
  chamber, heater running) — bare-cell calibration is insufficient.
- Field: probe joins the RS485 bus beside the Apogee reference per
  COMPOST-O2-SENSORS-BUDGET.md §First-experiment.

## Codex review (2026-08-18) — disposition

Adversarial review ran against the initial plan with the LMP91000/ADS1115/TMP117/
SHT4x/BMP390/K33 primary datasheets (full log:
`codex-plan-review-2026-08-18.log` beside this file).
Confirmed findings are integrated above; headline changes: fixed 2.5 V VREF
rejected (±2 % bias-step tolerance vs ±10 mV cell window) → trimmed-VREF vs
discrete potentiostat decided in Phase 1; ADS1115 → **ADS1119** (external
reference); SHT45 membrane is polyimide, not PTFE; ΔT design range 0–4 K
(psychrometrics) with SHT45 moved into the cell microclimate; grounded guard
rejected → driven guard at RE-replica potential; leakage threat re-scaled to
nA/MΩ wet-surface class; deployment ceiling derated to ~56–58 °C; RS485
bias/termination DNP + DE pulldown; bias supervision via register readback +
rail monitor; rear-vent routed aperture; potting/cable/drainage/orientation/
final-path-calibration requirements added. The later 2026-08-23 ring-tip
revision supersedes that review's two-TMP117/sensor-isolation control structure:
one TMP117 remains, the two transverse y=134 thermal-break slots remain, and
the membrane is heated directly through the manual-solder dry-side ring. The
I2C map, 3-lead LMP91000 topology/current range, 7 kΩ TIA headroom, ~1 W heater
ceiling, RH health channel, and calibrated-audit discipline remain.

## Risks / open questions

1. LMP91000 bias tolerance (±50 mV at 2.5 V vs cell ±10 mV — re-confirm from
   Rev. I in Phase 1): trimmed per-board VREF vs discrete potentiostat is the
   Phase 1 decision; fixed VREF is off the table. SGX bias sign convention
   and CE compliance unspecified → vendor question + bench measurement.
2. LMP91000 85 °C max vs 65 °C ambient + heater proximity + potting (no
   convection) — placement away from island, junction budget documented.
3. SGX CO₂ cross-sensitivity answer pending — affects compensation needs.
4. 12 V continuity from SDI-12-LB unverified (bias must never drop); if
   switched per-poll → dedicated PSU. Verify before deployment, not layout.
5. 4OX mechanical compatibility (rear vent, 20 mm can vs board width) —
   Phase 1.
6. SHT45 accelerated ageing at permanent high RH — treat as maintenance
   consumable alongside the cell; health-channel framing only.
7. Pile positions above **~56–58 °C** exceed cell spec once heater rise is
   included — deployment constraint (TEMP_OVER at the derated ceiling), not
   solvable on the PCB.
8. Potting boundary quality is load-bearing for the RE leakage claim — audit
   check + assembly note.
9. Expansion-connector sealing: an unused mating half above the pot line is a
   condensation/creepage point — connector body in the pot with only the
   mating face proud, dielectric grease + dust cap when unused; audit check.
10. K33 form factor (51×57 mm) fits no slim tube — future CO₂ = fatter tip
    chamber or separate probe on the expansion pigtail; deferred, doesn't
    block this board. If SGX confirms CO₂ cross-sensitivity, the K33 head
    shifts from optional to required (correction input).
11. SHT45 NH₃ compatibility — **resolved (2026-08-18, adverse but managed)**:
    Sensirion "Handling Instructions SHTxx" (June 2025, archived in
    `literature/datasheets/`, SHA `80be25d`) §1.3 lists **NH₃ among chemicals
    that can irreversibly damage the sensor**, with no concentration
    threshold; §4 puts validation burden on the user and notes low-level
    corrosives spare the element but corrode solder contacts → passivate
    contacts (conformal coat over pads, aperture clear). Mitigation stands:
    polyimide-membrane AD1F variant, replacement-interval framing, and the
    §4 reconditioning recipe (bake 100–105 °C < 5 %RH 10 h, re-hydrate
    ~75 %RH 12 h over saturated NaCl) as the service procedure for pulled
    probes. Treat NH₃ damage as a when-not-if wear item in manure-rich
    piles; the TMP117-vs-SHT45 disagreement channel is the failure detector.
