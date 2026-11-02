# Independent schematic-to-routing migration review — 68e6bde

Reviewed 2026-09-12 by the independently assigned `final_reviewer` agent. Repository HEAD at inspection: `0627aff1a31493254dcb7558daab751160ba7fee`; the schematic change under review is `68e6bde`.

**Finding: correct D8 before importing this schematic into a PCB.** The surviving routed board is an earlier 101-component design; the current schematic has 83 components and changes the power and conversion architecture. Earlier fabrication-review acceptance does not apply. Lost temporary artifacts have not been recreated or treated as evidence.

This review is a non-visual mechanical and source-semantics comparison. It used the committed XML netlist, the embedded schematic symbol, the generator, and KiCad 10.0.5 bundled-Python SWIG pad/net inventory of `routing/revb-89-tmp302/o2-probe.kicad_pcb`. It does not claim visual review, physical fit, complete routing, current-return performance, DRC closure, or fabrication approval. The native inventory command completed successfully; its only KiCad diagnostic was the known `create wxApp before calling this` assertion. The first inventory attempt failed JSON serialization of a SWIG string; the corrected read-only attempt completed.

## Findings requiring correction

### F1 — D8 is wired in the opposite direction to its stated protection function

`gen_sch.py:243` defines `Device:D_Schottky` pin 1 as **K** and pin 2 as **A**. The embedded schematic independently contains those same names/numbers. `add_passive` maps the first supplied net to pin 1 and the second to pin 2. At `gen_sch.py:1447`, D8 receives `GND`, `VIN_MON`; the XML confirms D8.1 = GND and D8.2 = `/VIN_MON`.

The resulting diode has its cathode on ground and anode on the normally positive monitor. It forward-clamps the normal positive reading rather than providing the specified negative clamp. A 180-degree symbol rotation does not change pin numbering or remedy the electrical connection. The intended mapping is **K to VIN_MON, A to GND**, subject to the final selected package's pad numbering.

`gen_sch.py:1994` also explicitly asserts the wrong assignment. Correct the semantic assertion and calibrate it with the actual reversed connection; otherwise a passing guard merely preserves the defect. ERC alone cannot distinguish these two passive-pin assignments.

The selected MPN is `BAT54-7-F` while the assigned footprint is `Diode_SMD:D_SOD-123`. Exact manufacturer package and pin mapping require verification before placement; the root agent is independently checking manufacturer evidence. This review does not claim that external package verification has been completed.

### F2 — live implementation notes contradict the adopted reference architecture

The binding final specification begins at `docs/2026-09-12-revb-decision-delete-ads1119.md:202`. It connects U6.5 to `/VREF_TRIM`, leaves PA5/U6.16 unused, and uses the REF3425 as the ADC full scale. The current netlist agrees. Several live generator comments and emitted component notes contradict it:

- `gen_sch.py:1315` says VREF+ stays on VDDA and the reference is converted as another channel; `:1345` again assumes a 3.3 V full scale and arithmetic reference cancellation.
- R24's design note at `:1358` says VA_MON is 1:2 and firmware should multiply by two. Actual values are R24 = 47k and R25 = 27k, ratio **27/74**. C33's note at `:1459` retains the obsolete 23.5k source resistance.
- R33's emitted note at `:1395` says to place it and C28 at **U8 AIN0**, although U8 is deleted and the destination is **U6.20/PB1/ADC_IN9**.
- The comment at `:1462` still describes converting VREF_TRIM directly as a monitored ADC channel.

Correct current implementation notes before using them as routing or sampler instructions. Historical proposal passages explicitly marked superseded can remain historical; these present-tense implementation instructions should not govern the migration.

## Exact inventory change

Removed references (21): **C5, C6, C9, C18, C19, C27, C29, DZ1, Q1, R1, R8, R18, R19, R31, R34, R35, R36, R41, U2, U3, U8**.

Added references (3): **D3, D8, C36**. U8's footprint is dropped, not retained as DNP. C4 and C8 remain DNP land options; R39 remains the DNP 100k AFE input shunt option.

The native board has `/GND`; the current exported schematic uses global `GND`. This is an explicit ground-name migration, not a new electrical domain. Compare named endpoints with that one documented equivalence; do not preserve or infer net identity from integer net codes. Anonymous mechanical pads were excluded from electrical endpoint comparison.

Removed named nets are `/+5V`, `/+5V_ANALOG`, `/ADC_DRDY`, `/ADC_RESET`, `/ADC_VREF_MON`, `/VIN_GATE`, `/VREF_MON_RAW`, and `/VREF_SHUNT`. No additional non-NC named net is introduced: most new functions reuse existing net names, which makes a name-only comparison insufficient.

The old board still contains **380 track/via items** on those eight obsolete nets: 117, 115, 42, 5, 56, 11, 2, and 32 respectively. These are raw inventory counts, not proof that every item must be deleted: retained power copper may be deliberately reassigned after its endpoints and connections are reviewed. Removing footprints alone cannot establish that obsolete copper is harmless.

## Concrete routing constraints

| Circuit | Required migration |
|---|---|
| Reverse input protection | Replace Q1/DZ1/R1 with D3 PMEG4010CEH. Current D3.1/K = `+12V_SW`, D3.2/A = `+12V_FUSED`. Retire VIN_GATE copper. Preserve the fuse/TVS and intended input-current path; do not accidentally short around D3. |
| Buck | U1 changes AP63205WU-7 to AP63203WU-7, retaining TSOT-23-6 and BUCK_SW/BST pins. U1.1, L1.2, C3.1 and C4.1 change from +5V to 3V3D. Preserve/review the switching loop rather than treating the same pad count as proof of suitability. |
| Analog rail | Delete U2/U3 LDOs. R32 remains 10 ohms but now feeds **3V3D → 3V3A**. C7 changes from +5V_ANALOG to 3V3A; C8 remains on 3V3A. Retained copper must not bypass R32 or reconnect the deleted regulator pads as accidental junctions. |
| U15 reference | AZ431 SOT-23 becomes REF3425 **SOT-23-6**. Old U15.1/.2 were VREF_SHUNT and become GND; old U15.3 was GND and becomes EN/3V3D. New .4 = 3V3D, .5/.6 = VREF_TRIM. Replace the footprint and reroute the local network explicitly; reference and pad-number reuse is unsafe here. |
| Reference support | New C36 100n belongs at U15 input pin 4. C10 4.7u remains on VREF_TRIM and becomes the direct output capacitor. Remove R41/C9/R31 and VREF_SHUNT copper. Both force and sense pins must be connected; shared net names do not prove a suitable physical force/sense arrangement or return. |
| MCU reference | U6.5 changes **3V3D → VREF_TRIM**, while U6.4/.6 stay on 3V3D. Remove the old pin-5 supply strap without removing the adjacent supply feeds. C26 changes 1u/0603/3V3D to **100n/0402/VREF_TRIM** and must be local to pin 5. Its footprint change also needs explicit replacement. |
| MCU analog channels | U6.11/PA0 becomes ADC_WE_BUF; U6.12/PA1 becomes ADC_RE_BUF; U6.20/PB1 changes ADC_DRDY to ADC_AFE_VOUT. U6.16/PA5 remains NC. Remove the DRDY pull-up/branch; do not reuse that digital route without re-evaluating its new analog role. |
| SAR input filters | Preserve R33/C28, R37/C30, R38/C31. Their filtered destinations move from deleted U8 to the MCU pins above. Re-establish local capacitor returns and short filtered-side connections at the new converter. WE/RE inputs remain buffered; never substitute raw CELL_WE or CELL_RE for WE_BUF/RE_BUF. |
| Supply monitors | Keep R26/R27 VIN division and C32; add the corrected D8 clamp at the MCU monitor node. R25 changes 47k to 27k, retaining R24 = 47k and C33. CE_MON stays on U6.15, VIN_MON on .17, VA_MON on .18. |

The heater, autonomous TMP302 cutoff, sensor interface, guard, CE protection and RS-485 receiver-enable split remain in the netlist. That fact does not establish preservation of their geometry or return paths after this migration. Recheck against the actual resulting board, including thermal structures and critical local analog connections.

## Completion boundary

The surviving routing README's “current engineering-review candidate” describes its older schematic. It must not be read as parity with this one. `audit_layout.py` audits **schematic graphics**, not PCB layout or PCB-to-schematic parity.

Firmware remains an explicit separate gate: `firmware/src/ads1119.c:7` deliberately errors when the selected revision lacks ADS1119, and explains that the MCU sampler port has not landed. In particular, old PB1 GPIO behavior conflicts with its new analog input function. A successful Rev A/default firmware build does not validate the new board's sampler.

Next acceptance requires a corrected/fingerprinted schematic and fresh netlist, deliberate footprint/pad/copper migration, then native PCB parity, connectivity, geometry, visual/circuit review and newly built artifacts. Existing project qualification gates, including supply ripple and physical sensor fit, remain open; none is closed by this inventory review.

## Inspected input fingerprints

| Input | SHA-256 |
|---|---|
| `gen_sch.py` | `f66286ab65429ccd35e5f28ac74b41c6ccc2516d3d9a6c6fff8bd28efd5fecba` |
| `o2-probe.kicad_sch` | `8c3bc7bf12b678dc1b6a9b175b73e0c3fbd8e5e2582d9d9bd66fae44d8cb4d6d` |
| `o2-probe.xml` | `76266be9efbc2a65bef242ebd90e91c53338b815a240273cdbeb7afa62bf2674` |
| `routing/revb-89-tmp302/o2-probe.kicad_pcb` | `4520074e475656a14fe82fea1ac86e2004d09b85485ee1155a594fc5e271b303` |

No CAD, generator, firmware, authority bundle or acceptance record was changed by this reviewer. This report is a dated assessment of the inputs above; subsequent fixes require their own verification.
