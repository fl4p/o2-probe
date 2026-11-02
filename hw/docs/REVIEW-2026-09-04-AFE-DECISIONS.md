# Independent review of the 2026-09-04 AFE/fab decisions

Reviewer: `codex exec`, `model_reasoning_effort=xhigh`, workspace-write with
network access and a headed Chrome attached over CDP. 21 minutes, exit 0.

Its ACCESS section was checked against the browser's own history rather than
believed: SNAS506I, SBAS925A, the STM32G071CB datasheet (including a page-89
fetch), RM0444 and DS-0637 were all genuinely retrieved. Two claims it marked
`unverified` are honest -- it could not re-run `kicad-cli pcb export gerbers`
(exit 134 in its sandbox), and `POTTING.md` lives outside this repo.

Verdicts below are the reviewer's. What was done about each is in
`## Disposition` at the end.

## ACCESS

- Live web query run: `LMP91000 SNAS506 datasheet VCE 300 mV control amplifier` → first result was TI’s [LMP91000 Sensor AFE System](https://www.ti.com/lit/gpn/LMP91000).
- Browser fetch: I opened TI’s LMP91000 product page through the attached headed Playwright-over-CDP browser. Exact `<title>`: `LMP91000 data sheet, product information and support | TI.com`.
- Primary sources verified:
  - [SNAS506I](https://www.ti.com/lit/ds/symlink/lmp91000.pdf), §§5, 6.5, 7.3.1 and register definitions.
  - [SBAS925A](https://www.ti.com/lit/ds/symlink/ads1119.pdf), §§6.3, 8.3.1–8.3.3, Equation 4, Tables 3 and 10.
  - [STM32G071CB DS12232 Rev 5](https://www.st.com/resource/en/datasheet/stm32g071cb.pdf), Table 12 and §5.3.18 Tables 58–59.
  - [RM0444](https://www.st.com/resource/en/reference_manual/rm0444-stm32g0x1-advanced-armbased-32bit-mcus-stmicroelectronics.pdf) was fetched successfully in Chrome; its large PDF text extraction was incomplete, so the numerical ADC verdict relies on the device datasheet’s directly applicable Tables 58–59.
  - [DS-0637 Issue 2](https://sgxsensortech.com/uploads/f_note/DS-0637-SGX-OX-ROHS-Mini_iss2.pdf), page 1.
- `unverified`: a clean-room `kicad-cli pcb export gerbers` rerun exited 134 in this environment. Static tracing of `LAYERS → GERBERS → manifest`, the footprint, and the existing release artifact was verified; only my independent executable replot is unverified.
- `POTTING.md` is not present inside this project; the path referenced by source comments is outside the permitted review scope. Therefore quantitative cured-potting leakage is `unverified`.
- No repository file was modified.

## FINDINGS

1. **File:** [gen_sch.py:639](../gen_sch.py:639), [AFE-BRING-UP-POSTMORTEM.md:123](AFE-BRING-UP-POSTMORTEM.md:123).  
   **Claim attacked:** D3, that the evidence selects 100 ohm and that the transient case needs no real-cell CE baseline.  
   **Verdict:** Your self-correction is right: 2875 mV came from the 0.6 uA equal-resistor dummy and cannot be combined with 99.09 uA from the real cell. The real-cell CE operating voltage was never measured; DS-0637 specifies output current but gives no CE impedance or potential from which it can be derived. SNAS506 §6.5 applies `300 mV <= VCE <= VS−300 mV` specifically as a test condition for A1 **open-loop gain**, not as a hard output-compliance or current-capability limit. At 3.3 V, the upper edge of that characterized region is 3000 mV, and the actual margin is `3000 − VCE_pin`, presently unknown. Because `VCE` is the voltage at U7’s CE device pin, a resistor between that pin and the electrode does count: for the observed sourcing direction, `VCE_pin = VCE_electrode + Icell·R`. At 99.09 uA the additions are 9.91 mV and 99.09 mV for 100 ohm and 1 kohm; at the DS-0637 maximum 130 uA they are 13 mV and 130 mV. Neither can be judged without the real-cell baseline and its temperature/O₂/age envelope. The `>607 uA` transient also supplies only a lower bound on resistor drop, not the missing electrode voltage. **The evidence supports a footprint and characterization, but not choosing either value yet.**  
   **Tag:** **(c) real design defect.**

2. **File:** [gen_sch.py:645](../gen_sch.py:645).  
   **Claim attacked:** “Same fault ceiling either way” and “100R limits to 33 mA … well under A1’s 10 mA charging spec.”  
   **Verdict:** VERIFIED arithmetic contradiction: 3.3 V / 100 ohm is 33 mA, which is **above**, not below, 10 mA. A 100-ohm resistor therefore does not impose a ceiling below the device’s cited 10 mA charging capability; 1 kohm would give an entirely different ideal ceiling of 3.3 mA. The required resistor must be derived from a defined maximum fault current, worst available voltage, pulse energy, and control-loop stability—not from “standard potentiostat practice.”  
   **Tag:** **(a) arithmetic error.**

3. **File:** [AFE-BRING-UP-POSTMORTEM.md:190](AFE-BRING-UP-POSTMORTEM.md:190), [Texas_RTE0016D footprint:330](Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm.kicad_mod:330).  
   **Claim attacked:** D1’s 64.0% exposed-pad paste ratio.  
   **Verdict:** The footprint genuinely has four 0.32 × 0.32 mm round-rect F.Paste apertures and a 0.8 × 0.8 mm copper/mask-only pad 17. But 64% treats the apertures as square. With radius `0.32 × 0.25 = 0.08 mm`, each area is `0.32² − (4−π)·0.08²`; total coverage is 0.387625 / 0.64 = **60.57%**. Current [make_fab.py:28](../make_fab.py:28) has corrected this; the postmortem has not.  
   **Tag:** **(a) arithmetic error.**

4. **File:** [fab-manifest.json:17](../fab/o2-probe-rev-a/fab-manifest.json:17), [FAB-READINESS.md:109](FAB-READINESS.md:109).  
   **Claim attacked:** that D1/D2 are already effective in the fabrication release.  
   **Verdict:** Current source includes F.Paste/B.Paste and a waiver, but the existing release directory and ZIP still contain only copper, mask, and Edge.Cuts Gerbers. Their manifest has neither paste layers nor `silkscreen_waiver`. Thus the source change is mechanically sound but the presently orderable artifact still has the original defect. `FAB-READINESS.md:128` incorrectly says its manifest records the waiver, and lines 138–140 also repeat the stale paste-less layer list.  
   **Tag:** **(c) real design defect.**

5. **File:** [make_fab.py:41](../make_fab.py:41), [make_fab.py:572](../make_fab.py:572).  
   **Claim attacked:** D2’s promised guard.  
   **Verdict:** No actual guard exists. `GERBERS` is derived from `LAYERS`, so adding F.Silkscreen/B.Silkscreen would make the set assertion accept them. The parser remains safely copper-only, but `silkscreen_exported` is hardcoded `False`; the manifest could therefore claim silk is absent while exporting it. The waiver needs an explicit assertion excluding both silk layers while active, and the manifest booleans should be derived from `LAYERS`.  
   **Tag:** **(c) real design defect.**

6. **File:** [gen_sch.py:676](../gen_sch.py:676).  
   **Claim attacked:** D4’s 100k/100k ADC feasibility.  
   **Verdict:** VERIFIED, but only with an acquisition assumption omitted from the decision wording. STM32 DS12232 Table 58 gives typical sampling capacitance `CADC = 5 pF` and maximum source resistance `RAIN = 50 kohm`. Table 59 permits 50 kohm at 12-bit resolution with the maximum 160.5-cycle sampling time: 4.586 us at 35 MHz, which is achievable. A nominal 100k/100k divider is exactly 50 kohm Thevenin, but 1% worst case is 50.5 kohm, so it has no bare-divider production margin. The largest equal 1% nominal legs satisfying 50 kohm are 99.01 kohm; 97.6 kohm is the largest E96 choice, while 91 kohm is more comfortable. They draw approximately 14.7 uA and 15.8 uA respectively at 2875 mV, so lowering the divider does not recreate a serious A1 load. The already-present 100 nF C34 is 20,000× `CADC` and supplies sampling charge locally; its 5 ms divider time constant merely requires settling after startup/bias changes.  
   **Tag:** **(b) unstated assumption that happens to hold.**

7. **File:** [gen_sch.py:694](../gen_sch.py:694).  
   **Claim attacked:** D7, ordinary low-capacitance TVS on CE and WE now, with RE left open.  
   **Verdict:** Reject as stated. “Low capacitance” does not establish acceptable WE leakage over temperature; TVS leakage enters the 70–130 uA measurand directly. The current source has already backed away from D7 and protects **CE only**, deferring WE as well as RE. INFERRED from the SNAS506 §7.3.1 three-electrode topology: clamping CE/WE to board ground while leaving RE floating can convert an RE/common-mode strike into differential current through the cell toward those clamps. Whether that is worse than no protection is `unverified` without the sensor’s transient model, protection return geometry, clamp curves, and pin-to-pin/common-mode ESD testing. Partial protection must therefore be qualified as a network; it is not automatically benign.  
   **Tag:** **(c) real design defect.**

8. **File:** [AFE-BRING-UP-POSTMORTEM.md:177](AFE-BRING-UP-POSTMORTEM.md:177), [AFE-BRING-UP-POSTMORTEM.md:262](AFE-BRING-UP-POSTMORTEM.md:262).  
   **Claim attacked:** D8’s instance-defect conclusion and leaving half the bias telemetry on pin 5 without mitigation.  
   **Verdict:** Reflow restoring every channel, combined with the hand-fitted replacement’s provenance, is strong evidence for an instance interconnect defect. It is not literal proof of a solder joint rather than a heat-responsive package/bond fault, so “silicon exonerated” is overstated. More importantly, the postmortem itself demonstrates that an open AIN2 produces an in-range gain-1 result near −2275 mV; clipping cannot detect it. Keeping the allocation is sound, but doing so without a commanded-bias plausibility window and production assembly inspection would be unsound. I did not inspect out-of-scope firmware, so implementation of that mitigation is unverified.  
   **Tag:** **(c) real design defect.**

9. **File:** [gen_sch.py:746](../gen_sch.py:746), [DESIGN.md:76](DESIGN.md:76).  
   **Claim attacked:** the ADS1119 differential-channel arithmetic.  
   **Verdict:** SBAS925 Table 10 verifies `001 = AIN2−AIN3` and `010 = AIN1−AIN2`. `VWE−VRE = −600 mV`, 96% of gain-4’s ±625 mV FSR, is correct. The shared external reference makes the nominal ratio VREF-independent, but not “exact”: LMP91000 ladder/offset and ADS1119 gain/offset errors remain. The stated 2.27 V “common mode” is wrong; `(1.675 + 2.275)/2 = 1.975 V`. Gain 1 gives 1.9 V to the nearer negative full-scale rail, not 2.5 V of headroom. Neither arithmetic error overturns the gain-1 recommendation.  
   **Tag:** **(a) arithmetic error.**

10. **File:** [audit_pcb.py:1009](../audit_pcb.py:1009), [audit_pcb.py:1392](../audit_pcb.py:1392), [gen_pcb.py:180](../gen_pcb.py:180).  
    **Claim attacked:** that the test-point audit proves every pad’s identity.  
    **Verdict:** It is not furniture: the four mutations genuinely exercise missing, undersized, stranded, and geometrically ambiguous text. But the property is incomplete. The audit accepts any non-`reserved` silk text as a label and checks only proximity, side, height, and count; swapping WE/CE/GUARD strings in place passes. The hardcoded `reserved` set is fragile when unrelated silk is added. Direct centre-distance calculation gives the narrowest current runner-up ratio as about 1.61 for CE, versus the arbitrary 1.4 threshold—not the claimed “wide margin”—and text extents are not checked. Add independent expected text-to-pad/net mapping and swapped/wrong-label calibration mutations. Also, under D2 these checks protect only source/drawing silk, not the manufactured board.  
    **Tag:** **(c) real design defect.**

11. **File:** [AFE-BRING-UP-POSTMORTEM.md:115](AFE-BRING-UP-POSTMORTEM.md:115), [gen_sch.py:664](../gen_sch.py:664).  
    **Claim attacked:** “CE tracking WE + 2× bias means healthy.”  
    **Verdict:** That relationship was established only by the equal 1 Mohm/1 Mohm dummy: each resistor carried the same current and therefore dropped one bias voltage. SNAS506 requires A1 to move CE as necessary to regulate the separately sensed RE–WE bias; it does not prescribe CE–RE for a real electrochemical cell. Real-cell CE depends on counter-electrode polarization and cell impedance. CE telemetry remains valuable for rail/headroom diagnosis, but its healthy band must be characterized across real cells, O₂, temperature, aging, and polarization—not copied from the dummy.  
    **Tag:** **(c) real design defect.**

## SURVIVED

- D1 survives as a source-level change: adding F.Paste/B.Paste propagates correctly through `LAYERS`, `GERBERS`, X2 validation, and the manifest, while copper-region parsing remains copper-only. The release must still be regenerated. The claim that every assembler would automatically create a 1:1 copper-derived stencil is vendor-dependent and unverified; losing the specified segmented paste data is sufficient justification without it.
- D2 survives as policy: withholding silk while 33 legend violations remain is defensible. Its guard and released waiver do not yet survive.
- D4 survives: PA0/PA1/PA4/PA5 are LQFP48 pins 11/12/15/16 and ADC1_IN0/1/4/5 respectively, per DS12232 Table 12. Current source uses PA4/pin 15 for CE_MON; the other three remain available. Use C34 and a defined settling/sampling policy, or reduce the equal divider to 97.6k/97.6k or preferably 91k/91k.
- D5 survives.
- D6 survives exactly as conditional. A 1 mm pad is not intrinsically a picoamp leakage source, and a correctly enclosed driven guard can suppress planar leakage, but exposed metal/potting interfaces and three-dimensional return paths remain unquantified. With no validated leakage budget, dropping CELL_RE’s test point is sound.
- D8’s decision not to reopen ADS1119 channel allocation survives, conditional on a bias plausibility/self-test requirement and normal WQFN assembly inspection.
- The central self-correction—that dummy CE margin and real-cell current cannot be combined—survives.
- The ADS1119 differential topology, gain-4 96% calculation, MUX codes, first-order ratiometric cancellation, and recommendation to use gain 1 survive.

=== CODEX EXIT 0 ===

## Disposition

| # | Tag | Action |
|---|---|---|
| 1 | (c) | Accepted. The 100R rationale is rewritten as the low-regret choice under an uncharacterised baseline, not as an evidence-selected optimum. SNAS506 6.5 is now described as the open-loop-gain characterisation condition, not a hard compliance limit. |
| 2 | (a) | Accepted, flat error of mine. "100R limits to 33 mA, well under A1's 10 mA" is backwards -- 33 mA is above 10 mA. Sentence removed and the real position stated. |
| 3 | (a) | Already corrected in `make_fab.py` before the review landed (60.57 %). `AFE-BRING-UP-POSTMORTEM.md` still carries 64 %; that is another author's file and is flagged, not edited. |
| 4 | (c) | Accepted. `FAB-READINESS.md` now separates the source change from the released artifact, which still contains the paste-less Gerbers. |
| 5 | (c) | Accepted. Manifest booleans are derived from `LAYERS`; `check_silkscreen_policy()` refuses a build where the waiver and the layer set disagree, calibrated against both known-bad states. |
| 6 | (b) | Accepted. 100k/100k is exactly `RAIN(max)` and over it at 1 % tolerance; changed to 91k/91k (45.5 kohm nominal, 16 uA load). |
| 7 | (c) | Accepted as a recorded open qualification. Partial protection is not asserted to be safe; the CE-only clamp carries the unverified common-mode concern in the schematic source. |
| 8 | (c) | Accepted. The allocation stands; the plausibility-window requirement is recorded in the generated hardware contract. Assembly inspection is a first-article gate. |
| 9 | (a) | Accepted. Common mode is 1.975 V (not 2.27 V, which is V_RE) and gain-1 headroom is 1.9 V (not 2.5 V). The ratiometric cancellation is now stated as first-order, not exact. |
| 10 | (c) | Accepted and gone further. A `TESTPOINT_LABEL_IDENTITY` check now requires each legend to be a token run of its pad's own net, with a swap mutation in the calibration suite. The reviewer's own suggestion -- substring matching -- was tried first and caught only ONE side of a WE/CE swap, because "CE" is the first two letters of "CELL_WE". Its arithmetic on the CE margin (1.61x) does not reproduce; measured on the final board it is 1.83x, and the narrowest is GUARD at 1.41x. The overclaim it correctly objected to ("by a wide margin") is removed. |
| 11 | (c) | Accepted. The "CE tracks WE + 2x bias means healthy" band was dummy-derived; the source now says so and defers the healthy band to characterisation. |
