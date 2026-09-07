# O2 probe Rev A — independent schematic review

> Historical review record. Its original fail and 2026-08-21 re-review are
> superseded by the 2026-08-23 first-article release evidence in
> `FAB-READINESS.md`, `schematic-audit.rpt`, and `pcb-audit.rpt`.

Review date: 2026-08-21  
Reviewer: independent Codex agent  
Scope: `PLAN.md`, `DESIGN.md`, `gen_sch.py`, generated schematic/netlists,
project footprints, placement notes, KiCad ERC, and `audit_schematic.py`.

## Gate verdict

**FAIL — do not transfer this schematic into the routed PCB yet.**

The generated schematic is syntactically healthy and its intended named-net
connectivity is internally consistent, but U1's AP63205 package-pin mapping is
wrong on every pin. A PCB generated from the present netlist would therefore
wire the buck converter incorrectly. Findings C1 and H1–H4 below are blockers
to PCB capture. The fabrication-only gates may remain visibly provisional
during mechanical/placement work, but must be closed before manufacturing.

## Verification run

- `python3 gen_sch.py`: PASS; 96 components and 320 assigned package pins.
- KiCad 10.0.5 ERC with `--exit-code-violations`: PASS; 0 errors and 0 warnings.
- `python3 audit_schematic.py`: PASS; 96 components, 87 nets.
- PDF export: one A2 sheet; reviewed visually. Functional blocks are legible at
  normal zoom, although the sheet uses only its upper portion.
- Standalone Playwright 1.55 drove installed Google Chrome. The browser-control
  prerequisite was proven by navigating `about:blank` and reading the live DOM
  (`HTML` / `BODY`). Official product/document pages were used where reachable.

ERC and the custom audit do not validate semantic package-pin maps. Their PASS
therefore does not mitigate C1.

## PCB-capture blockers

### C1 — Critical: U1 AP63205 package pin map is completely wrong

**Direct evidence.** Diodes Incorporated DS41326 Rev. 3-2, November 2024,
Figure 1 and the Pin Descriptions table on PDF page 2 specify:

| TSOT26 pin | AP63205 function | Present generated symbol function |
|---:|---|---|
| 1 | FB | BST |
| 2 | EN | GND |
| 3 | VIN | FB |
| 4 | GND | EN |
| 5 | SW | VIN |
| 6 | BST | SW |

The present netlist consequently assigns pin 1 to `BUCK_BST`, pin 2 to GND,
pin 3 to `+5V`, pin 4 to `+12V_SW`, pin 5 to `+12V_SW`, and pin 6 to
`BUCK_SW`. None matches the physical package.

**Remediation:** replace the custom U1 symbol map with 1=FB, 2=EN, 3=VIN,
4=GND, 5=SW, 6=BST; reconnect according to DS41326 Figure 1; regenerate all
outputs; add explicit package-pin assertions for U1 to `gen_sch.py` and exported
net assertions to `audit_schematic.py`; rerun ERC and this review gate.

### H1 — High: the VREF buffer directly drives 4.7 uF without a stability design

U4A is a unity-gain OPA2333 follower and C10 places 4.7 uF directly from its
output to ground. TI OPAx333 SBOS351E, Figure 15 on PDF page 11, shows rising
overshoot over only 10 pF to 1000 pF; the plotted response is already about
40% at the upper end. The schematic load is 4700 times that plotted upper
capacitance, and the design record supplies no isolation resistor, loop analysis,
or bench validation. This does not prove oscillation, but it is far outside the
validated evidence and can corrupt both LMP91000 bias and ADS1119 reference.

**Remediation:** design and document a stable reference driver. The simplest
candidate is a small series isolation resistor between the op-amp output and
the bulk/reference node, with feedback taken from the appropriate side as
supported by analysis; then verify startup, settling, noise, and ADS1119 dynamic
reference current on the assembled circuit. Add a local 100 nF supply bypass at
U4. Do not merely delete C10 without checking the ADC-reference requirement.

### H2 — High: RS-485 surge protection has no selected topology or footprint

D2 and D3 are literally valued `RS485 TVS TBD` while carrying independent SMA
footprints. The design record correctly says the earlier SM712 interpretation
was invalid. A dual asymmetric RS-485 array, two bidirectional parts, and two
unidirectional parts are not footprint- or net-equivalent; clamp voltage,
capacitance, surge rating, temperature, grounding, and standoff remain unknown.

**Remediation:** select an exact orderable protection topology against the
THVD1410 bus-pin ratings and the installation surge/EFT envelope, give every
device its exact symbol and land pattern, and locate it cable-side of R2/R3.
Capture and audit the actual pin map before placement/routing.

### H3 — High: the heater safety clamp is an unbounded output-contention path

TMP117 U10 ALERT is connected directly to `HEATER_GATE`; MCU PWM reaches that
node through R28=100 ohm. ALERT is open-drain. Whenever the MCU commands high
while ALERT asserts low, the nominal contention current is approximately
`3.3 V / 100 ohm = 33 mA`, before output resistances. No guaranteed ALERT sink
limit, MCU GPIO-current check, or fault-current design is recorded. This makes
the intended independent heater shutdown itself an electrical-stress risk.

**Remediation:** redesign the wired shutdown so both outputs remain within
guaranteed current limits (for example, increase the PWM series resistance
after checking MOSFET switching at the chosen PWM frequency, or use a small
logic gate/transistor implementing `PWM AND NOT_FAULT`). Program and verify the
TMP117 alert polarity/threshold before heater enable, retain the gate pulldown,
and prove the heater remains off during reset, I2C/config loss, and a stuck MCU.

### H4 — High: input TVS D1 is not tied to an exact package-compatible MPN

D1 is valued `SMBJ15A` but has no manufacturer-specific orderable MPN and is
assigned the KiCad SMA footprint `Diode_SMD:D_SMA`. `SMBJ` denotes an SMB/
DO-214AA-class family, not SMA/DO-214AC. The current combination cannot be
released or safely transferred as if the land pattern were settled. Its 15 V
standoff is also exactly the declared maximum normal input, so leakage,
breakdown tolerance, clamping at the AP63205 and 30 V MOSFET, pulse energy, and
high-temperature derating must be checked for the exact part.

**Remediation:** select an exact TVS MPN, use its documented land pattern and
polarity, and calculate the protected-node worst case with source impedance,
PTC behavior, pulse waveform, TVS tolerance, and temperature. Add the exact MPN
and datasheet URL to the schematic.

## Important corrections before fabrication release

### M1 — MCU reference/supply decoupling is one capacitor short of ST's scheme

The STM32G071 LQFP48 pin map itself is correct: pins 4/5/6/7 are VBAT, VREF+,
VDD/VDDA, and VSS/VSSA, and PA2/PA3 and PA9/PA10 provide USART2 and USART1
respectively (ST DS12232 Rev. 1, Figure 5 p.36, Table 13 pp.48–49). Figure 13
on p.53 calls for 100 nF + 4.7 uF at VDD/VDDA and 100 nF + 1 uF at VREF+.
The schematic has two 100 nF capacitors plus one 4.7 uF capacitor total on the
common 3V3D net, but no additional 1 uF part for VREF+. Add it and annotate the
required pin-local placement. This is electrically small but should be fixed
before PCB transfer if the PCB agent is expected to place final decoupling.

The compact-layout pin map uses PC6 as the `RS485_DE` GPIO and PA7/ADC_IN7 for
`VA_MON`; PA0 and PA1 are intentionally unused. This mapping must also be used
by firmware.

### M2 — recovery/programming claims exceed what J4 alone guarantees

J3 provides a viable pre-pot SWD set: VTREF, SWDIO, NRST, SWCLK/BOOT0, GND,
and SWO. J4 exposes BOOT0, USART2 TX/RX, and GND but no 3V3/VTREF pin, so a
standalone recovery fixture cannot sense target voltage or assert BOOT0 high
without borrowing J3 or sourcing a rail externally. The exact STM32G071 system-
memory bootloader peripheral/pin support was not established from the current
AN2606 because ST document retrieval had a transport failure in this review.
Further, the factory ROM bootloader cannot be assumed to manage the external
half-duplex RS-485 DE signal. `post-pot update over RS-485` therefore means a
tested application bootloader installed before potting, not guaranteed ROM
recovery.

**Remediation:** either make J4 a five-pin pad field with VTREF, or document the
combined J3/J4 fixture. Verify STM32G071 against the current AN2606/RM0444 and
test BOOT0/reset entry. Rename the post-pot path as the application RS-485
bootloader and specify rollback/recovery behavior.

### M3 — exact high-current/protection parts remain undefined

F1, DZ1, L1, D2/D3, RH1/RH2, and several capacitors are values/families rather
than orderable parts. **This is now machine-enforced**: `audit_bom.py` fails on
any fitted component lacking an MPN or a declared `sourcing.json` class, and the
finding here is no longer load-bearing prose. Recording it only in this document
is what let L1, DZ1 and F1 reach neither Rev A purchase order. At the declared 15 V maximum, two 140 ohm heaters draw
about 214 mA and dissipate about 1.61 W total (0.80 W each), not the 1.03 W
total at nominal 12 V. Exact 2512 resistor voltage/power derating, PCB thermal
rise, potting/island heat flow, PTC hold/trip current at temperature, inductor
saturation, and capacitor DC-bias derating are fabrication gates.

### M4 — VREF trim range is electrically broad and needs controlled adjustment

The 1.8 k + 2 k pot + 6.8 k chain produces an ideal wiper range of
`3.3*6.8/10.6 = 2.117 V` to `3.3*8.8/10.6 = 2.740 V`. The guard divider is
`100/(100+10) = 0.9091` of VREF. These calculations are internally consistent
with a 67% internal-zero and negative 24% LMP bias. TI LMP91000 SNAS506I,
REFCN register table p.22, confirms negative means `VWE - VRE < 0` and 24% is
the maximum step; the electrical table pp.5–6 gives the bias programming
resolution and offset limits. The range nevertheless permits a badly
misadjusted cell bias and has no hard stop.

**Remediation:** retain labelled WE/RE test points, define the safe trim
procedure and acceptance window using the real SGX cell, and consider resistor
limits that cannot exceed the cell's allowed bias. Verify the SGX sign
convention with the manufacturer; that remains a release gate.

### M5 — DNP expansion behavior needs a variant definition

J2 is DNP, but its PTC, five series resistors, and three TVS arrays are presently
not DNP. That is not electrically wrong, but the default assembly variant is
ambiguous. If a K33 head is fitted, `+12V_SW` can reach the declared 15 V input
maximum while the plan quotes a 14 V K33 ceiling. Define fitted/DNP groups and
resolve the connector's tube-chord fit and external-head supply limit.

## Fabrication-only mechanical and environmental gates

These do not block correcting the schematic and starting a controlled PCB
placement, provided the PCB remains explicitly non-fabrication:

- SGX cell pin identity/sign convention, drill/pad fit, rear-port diameter,
  body tolerance, and final aperture require a physical sample. The `_DRAFT`
  footprint status is honest.
- BMP390's pin map and 0x76 straps match Bosch DS002 Rev. 1.7, Figure 23/Table
  52 p.47 and Figure 25 p.48. Its custom land pattern remains deliberately DNP
  and assembly-unqualified.
- Dam slots, thermal-neck widths, cell aperture, tube chord, connector height,
  cable sealing, potting material/process, selective coating, and mesh/membrane
  response remain enclosure/process validation gates in `PLAN.md` and
  `PLACEMENT.md`.
- Exact MPN temperature ratings must be checked against the derated supported
  pile-gas ceiling and local heater temperature, not ambient catalogue ratings
  alone.

## Items that reviewed correctly

- LMP91000, ADS1119, THVD1410, BMP390, TMP117, SHT45 and STM32 LQFP48 package
  pin assignments inspected here are consistent with the cited primary pin
  tables; the AP63205 exception is the critical failure above.
- ADS1119 A1=A0=GND selects 0x40; the sole TMP117 straps to 0x49; BMP390
  SDO=GND/CSB=VDDIO selects I2C 0x76. The stated I2C map has no collision.
- THVD1410 `/RE` and DE share `RS485_DE`, with R7 pulldown, so the transceiver
  defaults to receive during MCU reset. Termination and bias are correctly DNP
  by default for a multidrop bus.
- The ADS1119 uses VREF_TRIM at REFP, GND at REFN, separate AVDD/DVDD, and
  brings AFE VOUT plus diagnostic divider signals to ADC inputs.
- The cell CE/RE/WE nets remain separate through the exported netlist, and the
  independent connectivity audit catches the previously possible label/stub
  shorts.

## Required re-review checklist

1. Correct C1, H1–H4 and M1 in `gen_sch.py` and regenerate the schematic.
2. Add package-pin assertions for every active IC, not only logical net/address
   assertions; audit the exported netlist against those tables.
3. Run KiCad ERC and `audit_schematic.py` from a clean regeneration.
4. Export and visually inspect the PDF and BOM/footprint list.
5. Re-open this gate before schematic-to-PCB transfer. A zero-warning ERC alone
   is not acceptance.

## Source access log

Research date: 2026-08-21. Load-bearing PDF text was extracted for discovery
and the cited pin/topology pages were checked against rendered pages. Working
copies remained under `/tmp/o2-datasheets`; no literature archive was added to
the project.

| Source / revision | Evidence state and locator | Attempt history / route / validation | Load-bearing |
|---|---|---|---|
| Diodes AP63200/AP63201/AP63203/AP63205, DS41326 Rev. 3-2, Nov. 2024, <https://www.diodes.com/assets/Datasheets/AP63200-AP63201-AP63203-AP63205.pdf> | inspected: Figure 1 and Pin Descriptions p.2; application Figure 21 p.9 | first direct fetch succeeded; raw PDF text plus rendered-page vision; validated | yes |
| TI OPAx333, SBOS351E, Dec. 2015, <https://www.ti.com/lit/gpn/OPA333> | partial: electrical characteristics and Figure 15 p.11 | direct TI PDF succeeded; raw PDF text plus rendered-page vision; validated | yes |
| TI LMP91000, SNAS506I Rev. I, Dec. 2014, <https://www.ti.com/lit/gpn/LMP91000> | inspected for claims: pin table p.3, electrical tables pp.5–6, variable bias/internal zero pp.14–15, REFCN p.22 | TI product page rendered cleanly in Playwright; PDF direct fetch succeeded; raw text plus rendered-page vision; validated | yes |
| TI ADS1119, SBAS925A Rev. A, Aug. 2026, <https://www.ti.com/product/ADS1119> | inspected for claims: WQFN pin table p.3, address table, RTE0016D outline | TI product page rendered cleanly in Playwright; PDF direct fetch succeeded; raw text plus rendered-page vision; validated | yes |
| TI THVD1410, SLLSEV6E Rev. E, <https://www.ti.com/product/THVD1410> | inspected for claims: SOIC-8 pin table p.5 and receiver/driver controls | TI product page rendered cleanly in Playwright; PDF direct fetch succeeded; raw text plus rendered-page vision; validated | yes |
| TI TPS7A20, SBVS338H Rev. H, Jul. 2024, <https://www.ti.com/lit/ds/symlink/tps7a20.pdf> | inspected for claims: DBV top view and pin table p.4; capacitor requirements section 7.1.2 | direct TI PDF succeeded; raw PDF text, relevant pin page checked; validated | no |
| ST STM32G071x8/xB, DS12232 Rev. 1, Nov. 2018, <https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/726/STM32G071_Rev1_DS.pdf> | partial: LQFP48 Figure 5 p.36, pin table, alternate-function Table 13 pp.48–49, supply Figure 13 p.53 | live ST page returned `ERR_HTTP2_PROTOCOL_ERROR`; authorized-distributor PDF succeeded; raw text plus rendered-page vision; validated historical/old revision | yes |
| ST AN2606 current application note, <https://www.st.com/resource/en/application_note/an2606-stm32-microcontroller-system-memory-boot-mode-stmicroelectronics.pdf> | metadata only; no technical claim drawn | official URL provenance confirmed from an ST Community link; Playwright target returned `ERR_HTTP2_PROTOCOL_ERROR`; plain and HTTP/1.1 fetches had transport timeout/failure; alternate Farnell-hosted copy also had HTTP/2/timeout failure; route: none; validation n/a | no |
| Bosch BMP390 DS002, document BST-BMP390-DS002-07 Rev. 1.7, Mar. 2021, <https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp390-ds002.pdf> | inspected for claims: Figure 23/Table 52 p.47, I2C Figure 25 p.48 | official PDF direct fetch succeeded; raw text plus rendered-page vision; validated | yes |

The non-clean source rows are the old STM revision/distributor manifestation and
the AN2606 transport failure. The former is sufficient for the reviewed LQFP48
pin geometry but not current suffix-7 lifecycle/temperature metadata. No
bootloader-peripheral claim in this report relies on the latter.

## Corrective re-review — current gate status

Re-review date: 2026-08-21  
Generated result: 98 components, 326 assigned package pins  
**Current PCB-capture verdict: PASS.**

This section supersedes the original FAIL verdict above for the corrected
generator and its regenerated outputs. It permits schematic-linked PCB capture
and routing. It is not a fabrication-release approval; the physical-sample,
enclosure, thermal, potting, protection-stress, and bench-validation gates
listed above remain open.

### Closure of original PCB-capture blockers

- **C1 AP63205 pin map — closed.** U1 now uses the official DS41326 map:
  1=FB (`+5V`), 2=EN (`+12V_SW`), 3=VIN (`+12V_SW`), 4=GND,
  5=SW (`BUCK_SW`), and 6=BST (`BUCK_BST`). C2 is between pins 6 and 5,
  L1 leaves pin 5, and the feedback pin senses `+5V`. Both generator assertions
  and exported-net assertions cover the load-bearing map.
- **H1 VREF capacitive load — closed for PCB capture.** U4A is a follower with
  output and inverting input on `VREF_BUF`; R31=47 ohm then feeds
  `VREF_TRIM`, where C10=4.7 uF and all LMP91000/ADS1119/guard loads connect.
  The feedback is deliberately taken before R31, so the isolation resistor is
  inside neither the op-amp feedback path nor a direct 4.7 uF output load. C25
  adds the missing local 100 nF supply bypass. Startup, settling, noise and
  reference accuracy remain appropriate bench tests, not capture blockers.
- **H2 RS-485 TVS — closed.** D2 is one exact Littelfuse `SM712-02HTG` in
  SOT-23. The manufacturer's Rev. 06/22/19 PDF, page 1 pinout and RS-485
  application drawing, show pins 1 and 2 as the two protected bus lines and pin
  3 as the common ground. The application drawing assigns A to pin 1 and B to
  pin 2; the corrected schematic matches it and places D2 on the cable side of
  R2/R3. Pins 1 and 2 are electrically equivalent branches in the shown
  topology, but the documented A/B convention is nevertheless preserved.
- **H3 heater shutdown contention — closed for PCB capture.** R28 is now 10 k,
  limiting nominal PWM-high versus ALERT-low current to approximately
  `3.3 V / 10 k = 0.33 mA`; R29 remains the 100 k gate pulldown. The larger
  resistor makes gate-edge/PWM-frequency verification a firmware and thermal
  bench requirement. It does not defeat the reset-off or ALERT clamp topology.
- **H4 input TVS package — closed.** D1 is exact `SMBJ15A-13-F` with the
  compatible SMB/DO-214AA `D_SMB` footprint. Pin 1 is on `+12V_FUSED` and pin
  2 is GND, matching the normal unidirectional cathode-to-positive placement.
  Surge-energy and hot-leakage calculations remain release tests.

### Other remediation checked

- C26=1 uF was added on 3V3D with an explicit placement note for MCU VREF+
  pin 5, completing the datasheet decoupling set together with C12–C14.
- J4 was subsequently removed as redundant with the complete J3 SWD fixture.
  The post-pot RS-485 updater still means a tested application bootloader, not
  an assumed factory-ROM RS-485 protocol.
- J2, F2, R12–R16 and D4–D6 now share the DNP default variant, removing the
  assembly ambiguity.
- RH1/RH2 are two 280 ohm, 1 W `CRCW2512280RFKEG` parts in parallel. Ideal
  total heater power is 1.03 W at 12 V and 1.61 W at 15 V; the latter remains
  the hot-input thermal/derating case for validation.

### Re-run evidence

- `python3 gen_sch.py`: PASS, 98 components and 326 assigned package pins.
- KiCad 10.0.5 ERC with `--exit-code-violations`: PASS, 0 errors/0 warnings.
- `python3 audit_schematic.py`: PASS, 98 components and 88 nets.
- Exported-net audit explicitly checks U1 pins 5/6 and their bootstrap/inductor
  nodes, D2 line pins, `VREF_BUF`, `VREF_TRIM`, cell nets, bus nets, and SWD.
- Independent inspection of `gen_sch.py` and `o2-probe.xml`
  found the corrected topology represented in the generated artifacts.

### Re-review source access addition

| Source / revision | Evidence state and locator | Attempt history / route / validation | Load-bearing |
|---|---|---|---|
| Littelfuse SM712 Series, Rev. 06/22/19, <https://www.littelfuse.com/assetdocs/littelfuse-tvs-diode-array-sm712-datasheet?assetguid=8313a28c-8802-4d47-a2a7-e30b5b1f67d8> | inspected: page 1 pinout/functional block and RS-485 application example | URL was discovered from a clean Playwright-rendered component record; the default browser presentation first received Akamai 403, then the single corrected current-Chrome UA/locale presentation returned the exact five-page PDF as `application/pdf` with 1,162,494-byte content length; Chrome's rendered PDF page was visually inspected; validated rendered-page vision | yes |

The first-page diagram directly confirms physical SOT-23 pin numbering:
top-view pins 2 and 1 are the two line terminals and pin 3 is common. The
adjacent RS-485 example connects A to pin 1, B to pin 2, and pin 3 to ground.
No unresolved source gap affects the corrected PCB-capture PASS.
