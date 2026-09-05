# Codex review — the 2026-09-05 BOM/footprint reduction

Extracted from the reviewer's session log (1.99 MB) from the LAST `## ACCESS`
heading onward; `file:///` link wrappers reduced to `file:line`. The full log is
not archived — it is a session transcript, and everything load-bearing is below.

- **Subject:** the uncommitted BOM pass that became commit `ae019ee`.
- **Reviewer:** `codex exec -s workspace-write`, network on, Playwright MCP
  attached over CDP to a headed Chrome on 127.0.0.1:9412, detached in its own
  session (PGID 32744), ~26 min.
- **Browser actually used:** the log contains no `no connected browsers` and no
  `node_repl/js (failed)`, so it did not fall back to its own Browser skill.
- **Disposition:** findings 3, 4, 5, 6, 7 and the wrong TI document number were
  mine and are fixed in `ae019ee`. Findings 1 and 2 are pre-existing defects and
  are NOT fixed there. See `BOM-REDUCTION.md` "Review" for the point-by-point
  disposition.

**One correction to the reviewer's own ACCESS note.** It marked the current-revision
STM32G071 RAIN table `unverified`, having read DS12232 Rev. 1 through a DigiKey
mirror. That was already closed independently: the live ST PDF was fetched through
a separate scratch-profile Chrome after curl stalled, and Table 59 read directly —
**50 kΩ at 12 bits / 160.5 cycles**.

---

## ACCESS

Diodes product-page `<title>` fetched through the supplied Playwright/CDP browser:

`AZ431-A: ADJUSTABLE PRECISION SHUNT REGULATORS (AZ431-A)`

Final-snapshot output of `cd /Users/fab/dev/ee && git diff --stat -- hw/o2-probe`:

```text
 ee/hw/o2-probe/.gitignore                 |    37 +-
 ee/hw/o2-probe/DESIGN.md                  |    63 +-
 ee/hw/o2-probe/FAB-NOTES.md               |    14 +-
 ee/hw/o2-probe/FAB-READINESS.md           |    73 +-
 ee/hw/o2-probe/audit_schematic.py         |     7 +-
 ee/hw/o2-probe/erc.rpt                    |     2 +-
 ee/hw/o2-probe/firmware/FIRMWARE.md       |    50 +-
 ee/hw/o2-probe/firmware/src/board_pins.h  |    13 +-
 ee/hw/o2-probe/firmware/src/bridge_main.c |     9 +-
 ee/hw/o2-probe/firmware/src/hw_contract.h |    12 +-
 ee/hw/o2-probe/firmware/src/mcu_adc.c     |    15 +-
 ee/hw/o2-probe/gen_sch.py                 |   202 +-
 ee/hw/o2-probe/make_fab.py                |   114 +-
 ee/hw/o2-probe/o2-probe.kicad_pcb         | 51255 +++++++++++++---------------
 ee/hw/o2-probe/o2-probe.kicad_pro         |     6 +-
 ee/hw/o2-probe/o2-probe.kicad_sch         |   398 +-
 ee/hw/o2-probe/o2-probe.xml               |   738 +-
 ee/hw/o2-probe/pcb-audit.rpt              |    36 +-
 ee/hw/o2-probe/pcb-drc-release.json       |     2 +-
 ee/hw/o2-probe/pcb-drc-warnings.json      |  1062 +-
 ee/hw/o2-probe/repair_guard_fill.py       |    14 +-
 ee/hw/o2-probe/schematic-audit.rpt        |     4 +-
 ee/hw/o2-probe/sourcing.json              |     3 +-
 23 files changed, 25602 insertions(+), 28527 deletions(-)
```

The tree changed concurrently once during review; the report and stat above reflect the final snapshot. No project file was modified.

Evidence was checked against the official [AZ431-A datasheet](https://www.diodes.com/datasheet/download/AZ431-A.pdf), [THVD1410 datasheet](https://www.ti.com/lit/ds/symlink/thvd1410.pdf), [TPS7A20 datasheet](https://www.ti.com/lit/ds/symlink/tps7a20.pdf), and [AP63205 family datasheet](https://www.diodes.com/assets/Datasheets/AP63200-AP63201-AP63203-AP63205.pdf). The current official [STM32G071 datasheet](https://www.st.com/resource/en/datasheet/stm32g071c8.pdf) loaded in Chrome, but command-line extraction was blocked by ST’s HTTP/2 behavior; the RAIN table was inspected in the ST-authored DS12232 Rev.1 [mirror](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/726/STM32G071_Rev1_DS.pdf). Therefore the current-revision table number is unverified; the 50 kΩ limit itself was verified.

The dependency search covered `firmware/src`, `firmware/tools`, tests, Python utilities, Markdown, and bench logs for all deleted references/nets plus `VA_MON`, `vam`, `va_mon`, `10/92`, `92000`, and `82k`, with only the user-listed generated/layout artifacts excluded.

## FINDINGS

1. High — **(c) real design defect:** VIN telemetry is reading the wrong physical channel, and low-VIN heater inhibition consequently does not work.

   The schematic sends `VIN_MON` to MCU PA6 and ADS1119 AIN3 to `ADC_RE_BUF` (`gen_sch.py:596`, `gen_sch.py:850`). Firmware still labels `PH_VIN` as ADS1119 AIN3 and samples it there (`main.c:142`, `main.c:617`). It then multiplies that RE-buffer voltage by 101/10 as though it were VIN (`main.c:398`).

   PA6 is neither configured nor read: initialization only puts PA7 in analog mode, and the only external-channel accessor is `o2p_mcu_adc_read_va_mv()` (`mcu_adc.c:51`, `mcu_adc.c:149`, `mcu_adc.h:18`). `board_pins.h` likewise has VA definitions but none for VIN (`board_pins.h:103`). Because `VIN_LOW` participates in `supply_ok`, this can leave heating enabled during an undervoltage (`main.c:541`). The stale `+12V_SW * 10/92` AIN3 comment corroborates the missed migration (`ads1119.h:33`).

2. Medium — **(c) real design defect:** the pinned AZ431 ordering code is the wrong accuracy grade for the stated contract.

   `AZ431BN-ATRG1` is covered by DS36721 Rev.6, but its ordering table identifies **B as 0.8%**, 2.480–2.520 V at 25°C; **A is 0.4%**, 2.490–2.510 V. The generator states the opposite and derives 2.480–2.520 V as a temperature-inclusive guaranteed range (`gen_sch.py:518`). Conservatively adding the datasheet’s 10 mV deviation over −40…85°C gives 2.470–2.530 V; over −40…125°C and 16 mV, 2.464–2.536 V. The generated 2480/2520 contract is therefore not the guaranteed range (`hw_contract.h:96`). The current ±100 mV runtime allowance masks this, and measured VREF removes most oxygen-scale impact, but the BOM identity and asserted specification disagree.

3. Medium — **(c) real design defect:** C7’s “strict improvement” is not specified by the source of truth.

   The old value explicitly required X7R; the new value is only `10u 25V`, and C1/C7 have no MPN (`gen_sch.py:490`, `BOM-REDUCTION.md:53`). Voltage rating and package size alone do not guarantee greater effective capacitance across unrelated MLCC series. The TPS7A20 documentation recommends X5R/X7R/C0G, discourages Y5V, and requires at least 0.47 µF effective input capacitance when source impedance is significant. Thus the “strict improvement” claim is **unverified** until an MPN/derating curve or at least an X5R/X7R sourcing constraint exists. This is a specification/guard defect, not evidence that the present nominal 10 µF circuit will oscillate.

4. Medium — **(c) real design defect:** several live scripts and one bench instruction still depend on deleted designators.

   `gen_pcb.py` retains J2/F2/R12–R16/D4–D6 and U14/C23/C24 placements and lacks J105/J106 (`gen_pcb.py:102`, `gen_pcb.py:109`, `gen_pcb.py:183`). Its missing-placement check will therefore reject a PCB generated from the new schematic (`gen_pcb.py:308`). This is about generator compatibility, not the excluded in-progress PCB.

   `audit_pcb.py`’s exact courtyard allowlist still requires several deleted pairs (`audit_pcb.py:53`, `audit_pcb.py:1173`); `route_heated_ring_tip.py` hard-fails without U14/C23/C24 (`route_heated_ring_tip.py:65`); and the bridge build instructions still tell the operator to solder to R15/R16 (`platformio.ini:131`). The `adopt_heated_ring_tip.py` and `adopt_tip_reposition.py` helpers are stale for the same reason.

5. Medium — **(c) real design defect:** the new footprint guard has a real exception leak.

   The comprehension excludes J5 before testing either condition, so J5 may become a Micro-Fit footprint—or remain any DRAFT footprint—and verification passes (`gen_sch.py:1185`). An in-memory mutation replacing J5’s footprint with a Micro-Fit produced `UNEXPECTED PASS`. If J5’s current ring footprint must remain DRAFT, only the DRAFT half should exempt J5; Micro-Fit should be forbidden globally.

   Separately, the VIN value checks use `startswith("91k")`, while `ohms()` uses a non-full-match regex despite promising to reject values it does not fully understand (`gen_sch.py:1202`, `gen_hw_contract.py:53`). The mutation `91k nonsense` passed both verification and parsing.

6. Low — **(a) arithmetic error:** 2.39 mA is not the worst-case AZ431 cathode current, and the rationale’s incremental-current figure is also wrong.

   The 2.39 mA calculation ignores the B-grade 2.520 V limit, 1% R41 tolerance, approximately 27 µA reference-divider load, temperature deviation, and R32 drop (`gen_sch.py:532`). Before the additional R32 drop from U3, a −40…85°C conservative calculation is approximately:

   `IKA = (4.900 − 2.530)/1.010k − 2.530/94k = 2.320 mA`

   It is about 2.314 mA over −40…125°C. Both remain safely over the 1 mA requirement. Changing 1.5 kΩ to 1 kΩ adds 0.833 mA nominal, not the `+1.8 mA / 9 mW` claimed in the rationale (`BOM-REDUCTION.md:98`); the incremental R32 drop is about 8.3 mV. The C9 stability note also still calls the cathode current approximately 1.6 mA (`gen_sch.py:541`).

7. Low — **(a) arithmetic error:** C33’s generated design note still says `R24||R25 = 5k`; it is now 23.5 kΩ (`gen_sch.py:910`). The operative ADC comment has the correct value, so this is stale design evidence rather than a circuit error.

## SURVIVED

- **R41’s electrical decision survives despite the arithmetic errors.** The exact MPN is covered by DS36721 Rev.6, whose recommended IKA range is 1–100 mA. Approximately 2.31–2.32 mA remains comfortable. The added 0.833 mA causes only about 8.3 mV additional drop across R32; the AP63205’s specified 4.95 V minimum output leaves ample TPS7A2033 input headroom. Nothing else is directly connected to `+5V_ANALOG` except U3, C7/C27, and the reference branch.

- **The R24/R25 claim survives.** Every live consumer was traced: VA is converted with the generated 47k/94k ratio, used for `VA_LOW`/settling, exposed as diagnostic telemetry, and used by `heater.c` only to verify PA7 remains analog (`mcu_adc.c:149`, `main.c:184`, `regmap.c:208`, `heater.c:20`). It never scales oxygen or another measurement; VREF does (`main.c:375`, `main.c:430`).

  The STM32 limit also passes: 23.5 kΩ is below the verified 50 kΩ maximum at 12-bit/160.5-cycle acquisition. At the table’s 35 MHz corner, 4.586 µs with the typical 5 pF sampling capacitor is about 39 ideal RC constants; 12-bit settling to ½ LSB needs approximately 9.0. C33 further reduces sampling kick. The limit is a datasheet ADC characteristic, not an RM maximum.

- **The VIN divider generator itself survives.** R26/R27, `gen_hw_contract.py`, and `hw_contract.h` all produce 10000/101000, and `--check` passed. No test or host parser hardcodes 10/92; occurrences in bench logs are historical. The end-to-end measurement nevertheless fails for the separate channel-routing defect above.

- **The access-point replacement survives.** J105/J106 are directly on UART2_TX/RX, and `board_pins.h` plus `bridge_main.c` agree. No live firmware behavior depends on the deleted EXP nets. Bench-log occurrences are historical evidence rather than consumers.

- **R5/R6 deletion survives for multidrop.** The cited identifier is wrong: the applicable current TI document is SLLSEY3E, §§9.3 and 10.2.1.4, not SLLSF11 §8.3. It explicitly provides open-, short-, and idle-bus receiver failsafe without external bias, and §10.2.1.3 permits up to 256 of these 1/8-unit-load receivers. That receiver behavior applies independently at every multidrop node. It does not replace end termination or protect against arbitrary induced differential noise; retaining DNP R4 for end nodes is correct.

- **The regulator-capacitance topology survives conditionally.** C7 is not the AP63205 output-stability capacitor; unchanged C3+C4 provide 44 µF, inside its stated 22–68 µF ceramic range. TPS7A20 is stable without CIN and recommends ≥0.47 µF effective when source impedance exceeds 0.5 Ω. A genuine 10 µF X5R/X7R 1206 part has ample margin. Only the claimed proof that the unspecified new part is strictly better failed.

- **The other named guards survive mutation testing.** The all-instance `0805` guard caught a reintroduced 0805, the EXP-net guard caught `EXP_TX`, and the exact DNP-set guard caught both an extra DNP and removal of R4. Baseline `verify()`, generated schematic parity, `gen_hw_contract.py --check`, and `git diff --check` all passed.
