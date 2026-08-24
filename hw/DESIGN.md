# O2 probe Rev A design record

## Status and source of truth

`gen_sch.py` is the source of truth for the schematic. Do not hand-edit the
generated `o2-probe.kicad_sch`; change the generator and regenerate it.

The schematic and PCB are released for a bare-board first article. This is not
an automated-PCBA or production-qualified release; SGX cell fit, enclosure fit,
manual assembly review, and bench qualification remain acceptance gates.

Regenerate and verify with:

```sh
python3 gen_sch.py
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc \
  --exit-code-violations -o erc.rpt o2-probe.kicad_sch
python3 audit_schematic.py
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch export pdf \
  -o o2-probe-schematic.pdf o2-probe.kicad_sch
```

Current generated result: 106 components, 336 assigned package pins, 92 nets,
KiCad ERC 0 violations, and `schematic-audit.rpt` PASS.

## Electrical architecture

- J1 is the fixed four-wire farm cable. Its individual solder lands are J101
  through J104 and are labelled as J1.1 brown +12 V, J1.2 white GND, J1.3 green
  RS-485 A, and J1.4 yellow RS-485 B.
- The 7–15 V input uses a resettable fuse, input TVS, reverse-polarity P-FET,
  AP63205 fixed 5 V buck, and separate TPS7A2033 digital and analog 3.3 V rails.
  The analog LDO input is isolated from `+5V` by fitted R32=10 ohm and bypassed
  locally by C7=10 uF X7R plus C27=100 nF on `+5V_ANALOG`. R32 uses an 0805
  option footprint that may take 0 ohm or a characterized bead after testing;
  a bead is not the default because its low-frequency inductance can resonate
  near the ADS1119 256 kHz modulator frequency.
- The O2 signal chain is SGX three-electrode cell -> LMP91000 -> ADS1119. A
  2 kOhm ten-turn trim and OPA2333 buffer establish `VREF_TRIM`; the second
  op-amp makes the approximately 0.91-times guard replica.
- The processor is STM32G071CBT7. USART1 on PA9/PA10 drives the THVD1410 farm
  RS-485 port. USART2 on PA2/PA3 is reserved for the expansion/recovery path.
- PC6 drives `RS485_DE`, placing the direction-control GPIO beside the USART1
  TX/RX pins, and PA7/ADC_IN7 measures `VA_MON`. These pin choices are
  generator-owned because they make the compact right-side MCU placement
  routable without changing the electrical functions.
- One TMP117 measures the warm tip near the membrane carrier. Its open-drain
  ALERT is wired directly to the MOSFET gate so a correctly configured active
  alarm can pull the heater off while MCU PWM drives through R28; R29 provides
  the passive default-off state. This is not credited as an autonomous
  overtemperature cutoff until firmware configures and fault-tests the TMP117.
  SHT45 is the chamber RH/dew-point channel. BMP390 remains an explicitly DNP
  pressure option at address 0x76.
- RH1/RH2 heat a manually soldered metal membrane-carrier ring through two J5
  plated-slot edge castellations. The ring is on switched `HEATER_LOW`, not GND,
  and must remain on the insulated dry side of the PTFE membrane stack.
- J2 is the DNP sealed-side expansion connector for a future external CO2 head:
  switched 12 V, protected 3.3 V, I2C, interrupt, and spare UART. It is not the
  programming connector.
- J3 is the sole pre-pot programming/recovery interface: VTREF, SWDIO, NRST,
  SWCLK/BOOT0, GND, and SWO. Post-pot firmware updates must use the RS-485
  application bootloader; the enclosure does not expose J3.

## Address map

| Device | Address / selection |
|---|---|
| SHT45 | `0x44` fixed |
| LMP91000 | `0x48` fixed |
| TMP117 cell | `0x49`, ADD0 to V+ |
| ADS1119 | `0x40`, A1=A0=GND |
| BMP390 DNP | `0x76`, SDO=GND and CSB=VDDIO |

## Controlled mechanical datums

- Board: 20.0 x 107.0 mm, R2.0 cable-end corners, square gas end, initially
  1.0 mm FR-4.
- Potting datum: y=82.0 mm; ordinary-component exclusion y=80–86 mm.
- Cell centre: (10.0, 93.5) mm; unrelated-part courtyard diameter 15.0 mm.
- Rear-flow aperture: a 3.0 × 6.0 mm vertical NPTH routed slot centred 1.8 mm
  gasward of the cell axis. Its nearest edge is 0.50 mm from the pad-2 copper
  edge. It spans the axis and provides a first-article
  airflow/fit window without inventing a rear-port diameter that DS-0637 Issue
  2 does not specify. Physical sample fit remains required for production.
- No mounting holes. Two exact 6.75 × 1.5 mm horizontal Edge.Cuts slots at
  absolute y=134 mm form a partial thermal break between the potted body and
  gas-side tip while retaining 0.75 mm edge webs and a 5 mm centre neck. Two
  additional 0.8 × 16 mm vertical side slots centred at `(101.2,145.0)` and
  `(118.8,145.0)` mm remove lateral coupling over y=137–153 mm. Their upper
  caps are 2.25 mm gasward of the transverse-slot edge, so they are not a
  16 mm series barrier to the body. A named rule area excludes zone fill on all
  four copper layers across y=133–135 mm; only the audited 14 track segments
  and two vias may cross it. The gas-side B.Cu island has a solid
  `/HEATER_LOW` thermal-spreader zone with voids for both side slots. Cable
  strain relief, expansion-connector chord clearance, ring/membrane carrier,
  and gas volume require the tube/fixture fit check in `PLACEMENT.md`.

## Release gates and provisional choices

- Fit a physical SGX-OX-ROHS-Mini sample before production qualification. The
  released first-article footprint is `SGX-OX-ROHS-Mini_ISS2`; the elongated
  aperture is deliberately a prototype fit feature, not a datasheet dimension.
- Independently recheck the BMP390 bottom-view numbering and land geometry. The
  DNP draft follows Bosch DS002 Figure 26 but has not been assembly-qualified.
- D2 is one Littelfuse `SM712-02HTG` asymmetric RS-485 array in SOT-23:
  pin 1=A, pin 2=B, pin 3=GND, cable-side of R2/R3. It replaces the invalid
  earlier interpretation of SM712 as two independent SMA diodes.
- U1's package mapping is locked by generator and exported-net assertions to
  AP63205 DS41326: 1=FB, 2=EN, 3=VIN, 4=GND, 5=SW, 6=BST.
- U4A feeds the 4.7 uF reference node through 47 ohm isolation with unity-gain
  feedback taken directly at the op-amp output. Stability/startup/noise still
  require bench verification, but the PCB no longer hard-wires a 4.7 uF load
  directly onto OPA2333.
- Derive the worst-case `3V3A` current budget and verify U3 input headroom with
  R32 tolerance and temperature. Compare 0 ohm, 10 ohm, and any proposed bead
  by measuring the `+5V_ANALOG` spectrum around 256 kHz, 1.1 MHz, and PFM burst
  components, plus ADS1119 mean/offset at heater 0%, intermediate, and 100%
  duty. Do not qualify this filter using RMS noise alone.
- J2 may become a sealed pad field if the Micro-Fit swept envelope does not fit
  the actual tube.
- Confirm every exact MPN/package pin map, MCU alternate-function assignment,
  input protection rating, heater steady-state temperature, and component
  ambient rating in the independent review before PCB transfer.
- Bare-board first articles may be ordered after schematic/PCB parity, DRC,
  exact outline/SGX-aperture validation, and ring-land review pass. A 1:1
  board/ring/tube coupon, real cell fit, and potting-fixture interface review
  remain mandatory before production or automated assembly.

## Source access log

Research date: 2026-08-21. A standalone Playwright 1.55 session drove installed
Google Chrome and validated the rendered TI product pages and their current
datasheet links. PDF load-bearing pin tables were also rendered and visually
checked after download.

| Source | Access result | Use |
|---|---|---|
| TI LMP91000 product page, <https://www.ti.com/product/LMP91000> and current Rev I PDF <https://www.ti.com/lit/gpn/LMP91000> | Clean rendered DOM in Playwright; PDF retrieved and rendered | WSON-14 pin table, DAP to AGND, fixed I2C address |
| TI ADS1119 product page, <https://www.ti.com/product/ADS1119> | Clean rendered DOM in Playwright; current Rev A PDF retrieved and rendered | RTE WQFN pin table and address straps |
| TI THVD1410 product page, <https://www.ti.com/product/THVD1410> | Clean rendered DOM in Playwright; current Rev E PDF retrieved and rendered | SOIC-8 pin table and half-duplex interface |
| ST STM32G071CB product page, <https://www.st.com/en/microcontrollers-microprocessors/stm32g071cb.html> | Non-clean: Chrome returned `ERR_HTTP2_PROTOCOL_ERROR`; curl also failed. Current ST product identity was recovered through indexed ST search results; ST DS12232 Rev 1 was obtained through DigiKey and its LQFP48 pin figure was rendered | MCU identity and preliminary LQFP48 map. Exact suffix-7 temperature/rating and current revision remain reviewer checks |
| Bosch BMP390 DS002, <https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp390-ds002.pdf> | Direct official PDF retrieved; pin table and package drawing rendered | DNP I2C wiring, 0x76 strap, provisional LGA-10 footprint |
| Diodes AP63205 family DS41326 Rev. 3-2, <https://www.diodes.com/assets/Datasheets/AP63200-AP63201-AP63203-AP63205.pdf> | Direct official PDF retrieved and pin/application page rendered during independent review | Corrected and asserted TSOT-23-6 pin map |
| Littelfuse SM712 series, <https://www.littelfuse.com/assetdocs/tvs-diode-array-spa-sm712-datasheet?assetguid=8313a28c-8802-4d47-a2a7-e30b5b1f67d8> | Official indexed datasheet result; exact `SM712-02HTG` topology selected | RS-485 cable-side TVS pin map and footprint |
| Diodes SMBJ series, <https://www.diodes.com/assets/Datasheets/ds19002.pdf> | Official indexed datasheet result; exact `SMBJ15A-13-F` selected | Input TVS value and SMB/DO-214AA footprint |
| SGX Sensortech `SGX-OX-ROHS-Mini`, DS-0637 Issue 2, 28-May-2026, <https://sgxsensortech.com/uploads/f_note/DS-0637-SGX-OX-ROHS-Mini_iss2.pdf> | Official product page rendered in Playwright and its exact manufacturer PDF retrieved; product drawing visually validated at 300 dpi | Body Ø14.40 mm, height 8.30 mm, three Ø0.64 mm pins at 2.54 mm pitch, pin-row offset 2.50 mm, general tolerance ±0.15 mm. The drawing does not dimension the rear gas port; the first article uses a gasward-offset 3 × 6 mm fit/flow slot. |

The retrieved PDFs were used as working evidence in `/tmp/o2-datasheets` and
were not silently promoted into the repository as a permanent literature
archive.

## PCB capture status

PCB first-article release date: 2026-08-24. `o2-probe.kicad_pcb` is linked to
the 106-footprint schematic and preserves the exact 20 × 107 mm outline with
R2 cable-end corners and a square gas end, local y=82 pot line, and SGX centre
`(10,93.5)`. The four-layer 1.0 mm stack is
nominal ENIG with 1 oz outer and 0.5 oz inner copper.

The tip has no second TMP117. Two horizontal thermal-break slots are centred at
local y=84.0, immediately gasward of the potting datum; two vertical side slots
are centred at local x=1.2/18.8, y=95.0. They are not a sensor-isolation
feature. The calculated transverse bare-PCB resistance is about 98 K/W, with a
90–110 K/W engineering bound pending first-article measurement; the side-slot
length is not added in series. See `THERMAL-BARRIER.md`. RH1/RH2, Q2, U10,
U12, and the DNP pressure option are aligned behind J5. J5 provides two exact
2.0 × 3.0 mm PTH pads at local x=0/20, y=105.5. Their 1.0 × 2.0 mm plated
slots are centred on the left/right profile and explicitly marked as
castellated; wide B.Cu joins them independently of the hand-soldered ring. The
cell centre is 13.5 mm from the board end and U10 is 2.975 mm from the
ring-contact centreline.

The dense digital cluster places U6 at local `(14.5,44.5)`, rotated 180° in
the right-side lane beside U5. C8 moves to `(18,37.5)` to preserve a clean U6
courtyard without separating the analog-LDO output bypass from U3.

CELL_RE remains one 9.652 mm F.Cu segment with no via/test point and a driven
guard. `repair_guard_fill.py` physically stitches three saved F.Cu fill regions
on both sides of the trace; the source outline alone is not credited as guard
copper. The all-layer thermal rule area divides the In2 GND pour into two saved
regions, joined only by one explicit 0.15 mm three-segment jog through the left
web. The heated tip has a solid B.Cu `/HEATER_LOW` spreader immediately gasward of the
barrier.
KiCad 10.0.5 reports 0 DRC errors, 0 unconnected items, and 0 parity issues;
the calibrated audit rejects 33/33 known-bad variants. The
27 exact courtyard pairs are
manual-assembly exceptions and legend layers are not exported. See
`FAB-READINESS.md`, `ASSEMBLY-EXCEPTIONS.md`, and `FAB-NOTES.md` for release
scope and remaining qualification work.
