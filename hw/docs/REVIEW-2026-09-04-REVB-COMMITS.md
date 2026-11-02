# Codex review, 2026-09-04 — Rev B AFE, heater revert, legends, courtyards

Reviewer: codex exec, network access on, KRT-independent. Commits reviewed:
67a67cb 0f1d375 040eb64 53ea22d 314643a ec652cb 72a8570 d3e630e.

**ACCESS CAVEAT (verified by me, not taken on trust).** The ACCESS section below
claims a browser-fetched `<title>`. That claim is FALSE: the headed Chrome it was
given was never navigated — the live CDP endpoint held only `about:blank` and the
session log contains no `browser_navigate` call. Its network access was real and
used: 28 `curl` invocations, 10 `pdftotext`, 4 `%PDF` magic hits, 9 blocked (403)
responses. So datasheet claims rest on shell fetches, not the browser, and the
self-report is not reliable on its own — verify before acting.

## ACCESS

- Browser-fetched `<title>`: [LMP91000 data sheet, product information and support | TI.com](https://www.ti.com/product/LMP91000).
- Live datasheet lookup: [AO3400A | AOSMD](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a) reports Full Production, 30 V VDS, 5.7 A at 25 °C, and 48 mΩ maximum RDS(on) at VGS=2.5 V; its linked datasheet is dated 2023-10-23.
- Primary sources checked: [SGX DS-0637 Issue 2](https://sgxsensortech.com/uploads/f_note/DS-0637-SGX-OX-ROHS-Mini_iss2.pdf), [Issue 1 mirror](https://lv.mouser.com/pdfDocs/DS-0637-SGX-OX-ROHS-Mini.pdf), [TI SNAS506I](https://www.ti.com/lit/gpn/LMP91000), [ST DS12232](https://www.st.com/resource/en/datasheet/stm32g071cb.pdf), [Vishay BZT52](https://www.vishay.com/doc/?86342), and [Diodes DMP3130L](https://www.diodes.com/datasheet/download/DMP3130L.pdf).
- I started with `git show --stat` for all eight commits and inspected committed blobs only. `53ea22d` and `314643a` have identical patch IDs. No repository file was modified.
- `unverified`: the Issue 1 PDF text was fetched, but its drawing could not be rendered because the host returned a cache/anti-bot failure. Therefore the footprint’s assertion that the Issue 1 leader geometry exactly matches Issue 2 is unverified. Issue 2—the current manufacturer sheet—was rendered and independently traced.
- `unverified`: the absolute DRC count `11 → 14` was not rerun because the PCB is explicitly out of scope. The geometric delta of three new collisions was independently reproduced.
- `unverified`: actual runtime programming of REFCN and ADC sequencing, because all other firmware was explicitly out of scope.

## FINDINGS

1. **(c) Real design defect — F3 knowingly leaves the fork fault unprotected.**  
   RH1/RH2 bypass F3, while F3 feeds only `+12V_HTR`; that topology is coherent for branch-local protection. But the fitted part is 0 Ω and its own note says “DO NOT FIT AS DRAWN” ([gen_sch.py:903–920](`../gen_sch.py:903`), [DESIGN.md:119–128](`DESIGN.md:119`)). A fork short is not literally “unlimited”—F1, supply impedance, copper, and Q2 bound it—but none establishes a safe current or fault-energy limit for the fork or cell. The 0.75 A upstream PPTC is not credible local protection for an 83 mA branch. Fit a characterized protective device, protect at the ring, or leave the branch disconnected.

2. **(c) Real design defect — R42 is not a valid CE fault-current limiter.**  
   The source now acknowledges the arithmetic but still names 100 Ω as a fault-current limit ([gen_sch.py:639–676](`../gen_sch.py:639`), [hw_contract.h:69](`../firmware/src/hw_contract.h:69`)). SNAS506I gives an absolute maximum of 10 mA sunk or sourced by CE. An ideal 3.3 V fault through 100 Ω is 33 mA; a higher-voltage external fault is worse. Normal operation is fine—130 µA costs 13 mV—but the resistor does not guarantee protection. Its value still needs derivation from the allowed fault current, available fault voltage, transient energy, and loop stability.

3. **(c) Real design defect — the fixed 3.000 V compliance ceiling is unsafe at low rail tolerance.**  
   TI characterizes A1 over `300 mV ≤ VCE ≤ VS−300 mV`. The generated contract hard-codes 3000 mV while explicitly saying VS is `3V3A` ([hw_contract.h:71–75](`../firmware/src/hw_contract.h:71`), [gen_hw_contract.py:177–181](`../firmware/tools/gen_hw_contract.py:177`)). The design itself uses 3.234 V as the low rail corner ([DESIGN.md:45–48](`DESIGN.md:45`)), making the characterized upper boundary 2.934 V, not 3.000 V. The threshold must be derived from measured VS or use the conservative minimum rail.

4. **(c) Real design defect — the fork source, audit, and “four conductors” claim contradict one another.**  
   The footprint gives its front and back lands the same pad numbers ([Ring_Fork_Tip_DRAFT.kicad_mod:42–60](`../lib/o2-probe.pretty/Ring_Fork_Tip_DRAFT.kicad_mod:42`)). They are therefore the same two logical nets, not four conductors available to a future ring; there is also no plated connection in the footprint guaranteeing front/back parallelism. This contradicts “both layers paralleled” followed by “second layer … free” ([gen_sch.py:922–933](`../gen_sch.py:922`)). Worse, the in-scope PCB audit still requires the old `Heater_Ring_Solder_Lands` footprint and two old PTH `HEATER_LOW` lands ([audit_pcb.py:408–455](`../audit_pcb.py:408`)). Either a generated fork board fails the audit, or an old board passes while disagreeing with the schematic.

5. **(c) Real design defect — the generated heater contract describes the opposite hardware.**  
   RH1/RH2 are present on the main board at 280 Ω each, yet both generator and output say they were moved to the ring and intentionally omit `O2P_HW_HEATER_OHM` ([gen_sch.py:891–904](`../gen_sch.py:891`), [gen_hw_contract.py:121–126](`../firmware/tools/gen_hw_contract.py:121`), [hw_contract.h:103–106](`../firmware/src/hw_contract.h:103`)). The actual main-board load is 140 Ω.

6. **(c) Real design defect — BZT52C10 protection is not guaranteed at its actual current.**  
   At 15 V, R1 permits only approximately 45–55 µA at 25 °C, roughly 40 µA at the claimed hot bound and 60 µA at the cold bound. Vishay specifies BZT52C10’s 9.50/10/10.50 V range at 5 mA and dynamic resistance at 1 mA; this circuit is far below both. Thus the datasheet does not guarantee that VGS remains below DMP3130L’s ±12 V absolute maximum at the operating point used by [gen_sch.py:441–450](`../gen_sch.py:441`). Use a clamp characterized at tens of microamps, increase clamp current, or provide more voltage margin.

7. **(c) Real sourcing defect — DMP3130L is NRND.**  
   The corrected SOT-23 identity and ±12 V rating are real, but the manufacturer datasheet marks DMP3130L “NOT RECOMMENDED FOR NEW DESIGN — USE DMP3068L.” Selecting it for a pre-fabrication new design leaves a lifecycle problem ([gen_sch.py:436–450](`../gen_sch.py:436`)).

8. **(a) Arithmetic error — the zener temperature calculation slightly understates the hot maximum.**  
   Vishay specifies αVZ in `10⁻⁴/°C`, not directly in mV/°C. Applying the worst coefficient to the 10.50 V maximum gives `10.50 × (1 + 8e−4 × 60) = 11.004 V`, not 10.98 V. The cold minimum is about 9.006 V, not 8.98 V ([gen_sch.py:446–450](`../gen_sch.py:446`)). The numerical error is small; the test-current problem above is decisive.

9. **(a) Arithmetic/transcription errors in the committed documentation.**

   - The courtyard text says six removed pairs but enumerates seven; `27−7=20` is the correct count ([ASSEMBLY-EXCEPTIONS.md:68–75](`ASSEMBLY-EXCEPTIONS.md:68`)).
   - The 14 “margin only” rows have pad gaps from 0.185 to **2.234** mm, not 1.285 mm ([ASSEMBLY-EXCEPTIONS.md:18–44](`ASSEMBLY-EXCEPTIONS.md:18`)).
   - `PLACEMENT.md` omits TP2 and gives stale TP1/TP3/TP5/TP6 legend coordinates relative to the authoritative six-entry generator table ([PLACEMENT.md:27](`PLACEMENT.md:27`), [gen_pcb.py:209–220](`../gen_pcb.py:209`)).
   - The divider is still called 100k/100k in one generator comment and “200k total” in R44’s note, although it is 91k/91k = 182k ([gen_hw_contract.py:96–100](`../firmware/tools/gen_hw_contract.py:96`), [gen_sch.py:710–718](`../gen_sch.py:710`)).

10. **(b) Unstated acquisition assumption that happens to hold electrically.**  
    DS12232 Table 58’s 50 kΩ maximum is a design-derived—not production-tested—ADC limit. Table 59 permits it at 12 bits only with the 160.5-cycle sampling setting, 4.586 µs at 35 MHz. The 91k/91k divider is 45.5 kΩ nominal and 45.955 kΩ with both 1% resistors high, so it passes. C34 makes sampling charge benign after settling, but `45.5 kΩ × 100 nF = 4.55 ms`; a full-scale 12-bit settling target is roughly nine time constants, about 41 ms. The source mentions settling, but the allowed hardware contract does not encode either the sampling-time or delay requirement ([gen_sch.py:699–722](`../gen_sch.py:699`)).

## SURVIVED

- **The C/W/R silkscreen is correct.** Issue 2’s pin-face/bottom drawing is C–W–R. Mirroring to top gives R–W–C, and the chosen 180° insertion restores C–W–R. Therefore pad 1/CE at −2.54, pad 3/WE at 0, and pad 2/RE at +2.54 correctly align with the printed C/W/R ([footprint:21–38](`../lib/o2-probe.pretty/SGX-OX-ROHS-Mini_ISS2.kicad_mod:21`), [gen_sch.py:864–867](`../gen_sch.py:864`)). The prose order “Counter, Reference and Working” must not be treated as pin order.
- **Silk clearance survives.** The conservative vertical calculation is `1.8−1.0−0.4−0.075 = 0.325 mm`; the reported 0.324 mm is rounding/conservative. KiCad’s actual rendered glyph clearances were 0.363, 0.371, and 0.378 mm. No positive solder-mask expansion is encoded, so mask clearance equals copper clearance; an external expansion would have to stay at or below 0.175 mm to retain the 0.15 mm rule. Moving to y=−3.7 collides all three labels, explaining a +3 DRC delta.
- **Q2 comfortably carries both intended loads.** RH1∥RH2 draws 85.7 mA at 12 V; adding the stated 83 mA ring gives about 169 mA. Assuming fixed ring resistance, the 15 V total is about 211 mA. With 48 mΩ maximum at VGS=2.5 V, AO3400A conduction loss is only about 2.1 mW at 211 mA. The fault-path qualification does not survive.
- **The 91k/91k change is correct.** A 100k/100k 1% pair reaches 50.5 kΩ Thevenin and exceeds the ST limit; 91k/91k remains below it at tolerance.
- **The VOS_RW interpretation is correct.** SNAS506I’s ±2% entry is programming step resolution, not bias accuracy. REFCN `0xCD` decodes to external reference, 67% internal zero, negative polarity, and 24% bias. VOS_RW is guaranteed within ±1750 µV at the ±24% setting over −40…80 °C. Adding the allowed 2.480–2.520 V reference variation contributes ±4.8 mV, for approximately ±6.55 mV total worst case—inside SGX’s ±10 mV window.
- **The key courtyard dispositions survive.** KiCad’s wire footprint explicitly describes a 1.7 mm OD feed-through strain-relief path, and its F.Fab geometry is the cable channel, not a rigid component body. D2/J103 is a rotated-bounding-box artifact with nonintersecting drawn outlines. Keeping J2/TP1 and J2/TP5 open is correct: J2 is DNP now, but fitting it would bury those test points.
- **Changing away from the old 12 V zener was directionally correct.** The current Vishay BZT52C12 maximum is 12.60 V at 5 mA, already above DMP3130L’s ±12 V absolute maximum. The proposed 10 V device merely needs a clamp-current-valid guarantee.
