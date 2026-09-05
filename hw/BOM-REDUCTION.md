# Where the BOM and the footprint count can actually come down

**2026-09-05.** Measured against the current generated schematic (`o2-probe.xml`,
regenerated 2026-09-04 23:25) and `o2-probe.kicad_pcb`, not against
`o2-probe-bom.csv`, which is stale: it still lists RV1, R20–R23 and a 120R that
the AZ431 rework replaced.

## Applied 2026-09-05 — result, and two places this document was wrong

Fab approved §1+§2+§3 on 2026-09-05. All three are **in the generator**;
`gen_pcb.py` was deliberately not run (see "The board is behind" below).

| | before | after |
|---|---:|---:|
| components | 113 | **100** |
| fitted | 96 | **98** |
| DNP | 17 | **2** (R4, R39) |
| distinct fitted footprints | 26 | **24** |
| orderable lines | 45 | **39** |
| `audit_bom.py` errors | 22 | **18** |
| 0805 lands of any kind | 2 | **0** |

ERC 0 violations, `audit_schematic.py` PASS, all four firmware environments
build (`native` fails identically before and after — pre-existing).

**Correction 1 — R15/R16 were not deletable, and §3 was wrong to list them.**
`board_pins.h:56` and `bridge_main.c:16` both take the bench bridge's host TTL
lead off the **MCU-side pads of R15/R16**, in preference to the LQFP's 0.5 mm
pitch. Those two "never-fitted options" were load-bearing lands for a shipped
firmware image (`bridge_main.c`, `bridge_uart.c`, `o2probe_bridge.ld`), and
deleting them would also have broken `O2P_ASSERT_NET(UART2_TX/RX)` at compile
time. USART2 now ends on **J105/J106**, two solder-wire lands on the footprint
J101–J104 already use — a better tap than half of an unfitted resistor, at two
footprints instead of five and still no BOM line. This is why the fitted count
went *up* while the total went down.

**Correction 2 — R39 is kept.** §3 listed it because it sits next to the BMP390
block, not because its gate was closed. It is not: `ads1119.c` still reasons
about where the oxygen channel sits against full scale, and
`AFE-BRING-UP-POSTMORTEM.md:175` uses R39's DNP state in a live leakage
argument. 4.7 mm² and no BOM line does not buy foreclosing that. R4 (120 R
termination) and R39 are the two survivors, and both survive on argument: the
deleted DNPs were ideas left behind, these are decisions left open.

**One thing checked before it was taken, one after.** R41 1.5 k → 1 k raises the
AZ431 bias to 2.50 mA nominal / 2.39 mA worst case; Diodes **DS36721 Rev. 6**
(AZ431-A) Recommended Operating Conditions gives I_KA **1.0 to 100 mA**, so it
clears the floor by 2.4× where 1.5 k cleared it by 1.6×. R5/R6 were deleted as
*redundant*, not merely unfitted: **SLLSF11** §8.3 gives the THVD1410 open,
short and idle-bus failsafe "without the need for external failsafe biasing
resistors".

**A guard caught me.** The first attempt declared `C_1206|10u 25V` as
`generic-stock` so C1/C7 would stop reading as unsourced. `audit_bom.py`
rejected it — 25 V is a load-bearing specification and a specified part needs an
MPN, not a family name. It was right; the declaration was reverted, and C1/C7
remain unsourced exactly as C1 already was. When C1 gets an MPN, C7 now gets it
free.

### The board is behind the schematic, on purpose

The working tree holds **another session's in-progress two-layer layout** in
`o2-probe.kicad_pcb` (≈51 k changed lines). Running `gen_pcb.py` would have
destroyed it, so this pass stopped at the schematic. The board still carries
J2, U14, C23/C24, R5/R6, R12–R16 and D4/D5/D6, still has R32/C7 in 0805, and has
no J105/J106. **Every DRC and schematic-parity number in `DESIGN.md` predates
this change.** Regenerate once, deliberately, when that session lands — and that
is also when §3's routing value gets measured rather than argued.

---

## Baseline, measured

| | |
|---|---:|
| footprints on the board | **113** |
| fitted | 96 |
| DNP | **17** |
| distinct fitted footprints | **26** |
| orderable lines (MPN or `sourcing.json` class, test pads and pigtails excluded) | **45** |
| total courtyard area, both sides | 1595.3 mm² |
| courtyard belonging to DNP parts | **329.2 mm² — 20.6 %** |
| board | 20 × 107 mm, y 50…157 (cable end y=50) |

Everything below is ordered by confidence, not by size. Nothing here is applied.

---

## 1. Four purchase lines that cost nothing to remove

Same circuit, same package, same tolerance where tolerance matters. Each of
these is a singleton MPN whose value already exists as a stock line.

| ref | now | to | why it is free |
|---|---|---|---|
| **R27** | 10k 1 % `RC0603FR-0710KL` | generic-stock 10k 0603 | Bottom of the VIN_MON divider into the MCU ADC. `RC0603FR-0710KL` *is* a generic 1 % 0603; the line exists already for R8/R18/R19/R28. |
| **R26** | 82k 1 % `RC0603FR-1082KL` | 91k `RC0603FR-0791KL` | The 91k line already exists for R43/R44. 91k/10k gives 1.485 V at 15 V in and 0.693 V at 7 V — both comfortably inside the 3.3 V ADC, same as the 1.63/0.76 V the 82k gives. |
| **R41** | 1.5k 1 % `RC0603FR-071K5L` | generic-stock **1k** 0603 | Biases the AZ431 shunt from +5V_ANALOG. `DESIGN.md` requires I_KA ≥ 1.0 mA; 1k gives (5.0 − 2.5)/1k = **2.5 mA** nominal, **2.32 mA worst case**, at a cost of **+0.83 mA** (8.3 mV more drop across R32). *(Both numbers corrected after review — see §Review.)* |
| **R24/R25** | 10k **0.1 %** `P2TC0603D1002LNTA` | generic-stock **47k** 0603 | See below — this one is worth its own paragraph. |

**R24/R25 in particular.** VA_MON is a 1:1 divider on 3V3A read by the MCU ADC
(PA7). It is rail *health*, not a calibration path — nothing downstream scales a
measurement by it, unlike VREF_MON (§4). 0.1 % is over-spec there, and it is
paid for three times: an extra MPN line, **165 µA drawn continuously off the
analog rail that feeds U4/U7/U8**, and a placement constraint — the parallel
session's refloorplan attempt explicitly held "matched 0.1 % pairs adjacent".
47k generic drops the draw to 35 µA and releases all three.

Source impedance goes 5 k → 23.5 k. `mcu_adc.c:76` already sets `SMPR = 7`
(160.5 cycles, the longest the G0 has). **Verified against the primary source:**
ST **DS12232** (STM32G071x8/xB) Table 59, *Maximum ADC RAIN*, allows **50 kΩ at
12 bits and 160.5 sampling cycles** — 2.1× margin, and more in practice because
Table 59 is quoted at a 35 MHz ADC clock where this board runs HSI16 with no PLL
(`mcu.c:35`). It also fixes a ceiling: 100 kΩ legs would sit exactly *on* the
50 kΩ limit, so this divider must not be raised further. The comment at
`mcu_adc.c:73` naming "10k‖10k = 5k" is updated with the change.

**Net: 45 → 41 orderable lines, no circuit change.**

---

## 2. Two footprints that exist for one part each

| ref | now | to | effect |
|---|---|---|---|
| **C7** | 10u 10V X7R **0805** | the same part as C1 — 10u 25V **1206** | `C_0805_2012Metric` is on the board for this one capacitor. 1206 is already there for C1/C3/C4. Costs ~4.6 mm² of courtyard. **−1 footprint, −1 line.** |
| **R32** | 10R **0805** | 10R **0603** | `R_0805_2012Metric` is on the board for this one resistor. `DESIGN.md` chose 0805 so the pad could later take a characterised ferrite bead — but 0603 beads are as available as 0805 (Murata BLM18, TDK MPZ1608), so the option survives the change. 10R then merges into the existing 0603 line with R2/R3. **−1 footprint, −1 line.** |

**Net: 41 → 39 lines, 26 → 24 distinct fitted footprints.**

---

## 3. The DNPs are a fifth of the board's courtyard, and one of them is in the way

17 never-fitted parts hold **329.2 mm²** of courtyard. They cost nothing to buy.
What they cost is area, library surface, and — for one of them — routing.

```
J2   Micro-Fit 3.0 2x04       17.2 × 13.0 = 224.8 mm²   y 110.5…123.5
D4 D5 D6  SOT-23 (TPD2E2U06)   3.5 ×  4.0 =  13.8 each   y 110
F2   PTC 1206                  2.4 ×  4.7 =  10.9        y 112
U14  BMP390 LGA10 DRAFT        2.4 ×  2.4 =   5.7        y 151
C23 C24  0402                  1.9 ×  1.0 =   1.9 each   y 151/152
R4 R5 R6 R12–R16 R39  0603     3.0 ×  1.6 =   4.7 each
```

**J2 is 224.8 mm² — 14 % of every courtyard on the board — for a connector that
is never fitted**, and it carries two Ø2.41 mm NPTH mounting holes. On two
layers an NPTH is a hole through both. It sits at y 110.5–123.5, i.e. **local
y 60.5–73.5**: the run-up to, and the leading edge of, the local-70–80 AFE band
the two-layer work is fighting.

Commit `877ac52` measured that deleting the connector's **six EXP_ signals**
buys one open link. That is not the same experiment as deleting its
**footprint** — the signals are copper the router can reroute; the NPTH pair and
the 17.2 × 13.0 mm courtyard are geometry it cannot. Worth re-measuring on the
pinned generator (`canonicalize.py`, `1cbd21e`) before concluding either way.

**Keep R4.** 120R is the RS-485 end-of-bus termination option, and a farm cable
can genuinely need it. Everything else is a stale option:

- **U14 + C23 + C24 + R39** — the whole BMP390 pressure channel, 14.2 mm², and
  it is the only user of the `o2-probe:BMP390_LGA10_DRAFT` footprint. Delete
  unless pressure is still planned for this revision.
- **R12–R16** (5 × 33R), **R5/R6** (680R RS-485 bias), **F2**, **D4/D5/D6**.

Deleting all 16 (J2 included, R4 kept): **113 → 97 footprints**, ~324 mm² freed,
and two footprints leave the library entirely — the Micro-Fit and the DRAFT
BMP390. Zero change to what is bought.

---

## 4. One question I could not close, worth more than everything above

The VREF monitor chain — **R34, R35 (47k 0.1 %), R36, C29, TP4, and one ADS1119
mux channel**.

I went looking for a self-reference bug here and did not find one: `ads1119.h`
lines 7–11 already knows that "a converter referenced to the thing it is
checking cannot detect that thing", and the health read is taken against the
ADS1119's internal 2.048 V.

But it is not only a health check. `main.c:394` promotes the measured value into
`g_cyc.vref_mv`, which `code_to_cell_na()` uses as the scale factor for the cell
current. **The divider's ratio error lands directly on the oxygen reading** —
which is exactly why R34/R35 are 0.1 % and why they should stay 0.1 % if the
chain stays.

The chain's accuracy is therefore (R34/R35 ratio) ⊕ (ADS1119 internal 2.048 V
initial accuracy). The alternative is to trust the AZ431**B**'s own initial
accuracy as a constant 2500 mV and keep only a coarse alive/sane band.

**So: what is SBAS925's internal-reference initial accuracy, max — not typ?**
If it is worse than the AZ431B grade's ±0.5 %, this path is *degrading* the O2
reading rather than trimming it, and R34/R35/R36/C29 plus one mux channel can
go: −4 parts, −1 MPN line, −1 of the four ADS conversions per cycle. If it is
better, the chain is earning its parts and none of this applies.

I have not fetched the datasheet. This is a question, not a recommendation.

---

## What I looked at and am not proposing

- **R34/R35 47k 0.1 % → 1 %.** No. §4 — their ratio is on the O2 reading.
- **Unifying all four monitor dividers on one value.** They have different node
  constraints: R43/R44's 182 k total is the CE node's load budget, R34/R35 sit on
  the reference net, R24/R25 on the analog rail. One value cannot serve all
  three well; one *series* (§1) is the achievable version.
- **Collapsing U2/U3 to one LDO** and dropping R32/C7/C27. The analog/digital
  rail split is the AFE's noise floor. Keep.
- **Dropping TMP117 for the SHT45's temperature.** Different locations — TMP117
  is the tip interlock at the cell, SHT45 is the chamber. Both needed.
- **Deleting the AZ431 reference** (U15, R41, R31, C9, C10 — five parts) and
  running the LMP91000 VREF and the ADS1119 REFP both from 3V3A. It stays
  ratiometric, so it is not obviously wrong, but it puts TPS7A2033 noise onto the
  cell bias and onto the ADC reference, and the reference was deliberately
  reworked on 2026-09-04 (`DESIGN.md`, trimmer removal). Not proposed without a
  noise measurement.
- **The six test points.** Bare copper, nothing placed, no line.

---

## Summary

| | now | §1 | +§2 | +§3 |
|---|---:|---:|---:|---:|
| orderable lines | 45 | 41 | **39** | 39 |
| footprints on board | 113 | 113 | 113 | **97** |
| distinct fitted footprints | 26 | 26 | **24** | 24 |
| DNP courtyard | 329 mm² | 329 | 329 | **~5 mm²** (R4) |

§1 and §2 are six edits to `gen_sch.py` and one comment in `mcu_adc.c`, with no
circuit change beyond R41's bias current and R24/R25's source impedance — both
checked above. §3 is a deletion whose routing value should be **measured**, not
assumed, on the pinned generator. §4 is a datasheet lookup that may be worth
more than §1–§3 combined.

---

## Review, 2026-09-05 — Codex, network + headed Chrome over CDP

Seven findings. Five were mine and are fixed; two are **pre-existing defects the
review surfaced**, and they go to Fab rather than into this commit.

### Fixed in this change

| # | finding | fix |
|---|---|---|
| 3 | **C7 lost its dielectric.** The old value was `10u 10V X7R`; inheriting C1's bare `10u 25V` dropped the X7R. Package and voltage rating do not imply a dielectric — Y5V would have satisfied both, and TPS7A20 (SLVSD95) discourages Y5V on the LDO input. | Both C1 and C7 are now `10u 25V X7R`, and `verify()` asserts the full string, not just the value. |
| 5 | **My new footprint guard leaked.** `if r != "J5"` excluded J5 *before* testing either condition, so J5 could have become a Micro-Fit and still passed — the reviewer mutated it and got `UNEXPECTED PASS`. | Micro-Fit is now forbidden globally; J5 is exempt from the DRAFT half only. |
| 5b | **`startswith("91k")` accepted `"91k nonsense"`**, and `gen_hw_contract.py`'s `ohms()` parsed it as 91 k while its docstring promised to reject what it did not fully understand — `re.match` anchors only the start. | Value checks are exact; `ohms()` now anchors the trailer to a closed vocabulary (tolerance, power rating, turns) and rejects `91k nonsense`, `91k 1% junk`, `91kk`. |
| 6 | **R41's worst case used the wrong grade.** U15 is AZ431**B**N; DS36721 Rev. 6's ordering table is A = 0.4 % (2.490–2.510 V), **B = 0.8 % (2.480–2.520 V)**. I used 2.510. And "+1.8 mA / 9 mW" was simply wrong. | Recomputed at 2.530 V (2.520 + 10 mV over temperature), R41 +1 %, rail 4.900 V: **2.32 mA**, still 2.3× the 1.0 mA floor. The increment is **+0.83 mA / 8.3 mV**. C9's stability note, which still said "~1.6 mA cathode current", is updated too. |
| 7 | C33's note still said `R24||R25 = 5k`. | Now 23.5 k — and the note says why that makes C33 *more* load-bearing, not less. |
| 4 | **Stale downstream references.** `gen_pcb.py` still placed J2/F2/R12–R16/D4–D6/U14/C23/C24 and had no J105/J106, so its missing-placement check would have rejected a board built from the new schematic. `platformio.ini:131` still told the operator to solder the bench-bridge lead to R15/R16. | Both updated. `gen_pcb.py`'s placement set now matches the schematic exactly (0 in one and not the other). |
| — | My **SLLSF11 §8.3** citation for the THVD1410 failsafe was the wrong document. | Corrected to **SLLSEY3E §§9.3 / 10.2.1.4**, which also settles the multidrop question the reviewer raised: §10.2.1.3 allows 256 of these ⅛-unit-load receivers and the failsafe is per-node. Failsafe still is not termination, which is why R4 stays. |

Deliberately **not** changed: `audit_pcb.py`'s exact-courtyard allowlist (lines
56–61, 375–377) and `route_heated_ring_tip.py`, which still require the deleted
designators. They operate on the **existing** board, which still has those parts.
Stripping them now would make them wrong for the board that exists and right only
for one that does not. **They must be updated in the same pass that regenerates
the PCB**, along with the `adopt_*.py` helpers.

### Not mine — two pre-existing defects, for Fab

**A. VIN telemetry reads the wrong physical channel, and the undervoltage half
of the heater interlock is dead.** `main.c:618` samples **ADS1119 AIN3** for VIN
and scales it by the VIN divider ratio — but the schematic has AIN3 =
`ADC_RE_BUF`, the buffered reference electrode. `ads1119.h:34-36` still documents
the *old* map (`AIN2 = 3V3A/2`, `AIN3 = +12V_SW * 10/92`), which is where the
migration was missed when the rail monitors moved to the MCU ADC. There is no
PA6/VIN reader at all: `mcu_adc.h` exposes only `o2p_mcu_adc_read_va_mv()`. So
`s->vin_mv` is not the input rail, and because `O2P_F_VIN_LOW` feeds `supply_ok`
(`main.c:544`), an undervoltage need never inhibit the heater.
*This predates the BOM pass.* My ratio change (92 → 101) alters the magnitude of
an already-meaningless number; it does not create or worsen the defect. Corroborating
but not diagnostic: `bench-logs/shipped-2026-09-05.csv` reports `vin_mv` with a
median of 4876 and a range of 3404…12852 on a nominally 12 V supply.
**VA is unaffected** — it is read correctly from PA7.

**B. The AZ431 grade claim, and the firmware VREF band built on it.**
`gen_sch.py`'s U15 note reasons from "the 2.510 V grade limit", which is the
**A** grade's number applied to a **B** part. `hw_contract.h`'s
`O2P_HW_VREF_MIN/MAX = 2480/2520` happens to match B's 25 °C range but is
described as a guaranteed range; adding the datasheet's ±10 mV over −40…85 °C
gives 2.470–2.530 V. The ±100 mV runtime allowance in `finish_vref` masks it
today, and measuring VREF removes most of the oxygen-scale impact — but the
asserted specification and the ordered part disagree. Fixing it is a decision
about the contract band, not a BOM edit.

### On the reviewer's own access

It fetched the AZ431, THVD1410, TPS7A20 and AP63205 datasheets, and got the
STM32G071 RAIN table from a DigiKey mirror of DS12232 Rev. 1, marking the
current-revision number `unverified`. **That one I had already closed myself**:
I pulled the live ST PDF through my own scratch-profile Chrome after curl stalled,
and read Table 59 in it directly — 50 kΩ at 12 bits / 160.5 cycles. The log shows
no `no connected browsers` and no `node_repl/js (failed)`, so the browser surface
was actually used.
