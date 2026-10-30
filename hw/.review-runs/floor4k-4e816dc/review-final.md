## ACCESS

- Live VictoriaMetrics query succeeded: probe **3**, `gas_heater_duty_pct = 2.41`.
- Scratch Playwright loaded [TI’s TMP117 page](https://www.ti.com/product/TMP117), title: **“TMP117 data sheet, product information and support | TI.com”**. No WAF or fabchrome handoff was needed; my tab was closed.
- Requested 60 days of telemetry. Exact timestamp matching across all five metrics yielded **36,279 samples**, September 11–October 28.
- Reviewed HEAD `4e816dc`. No source edits or device/register writes; only permitted native build artifacts were created under `.pio`.

## FINDINGS

1. **P2 — (c) Real test-design defect: the unreachable-dwell output assertion now masks a broken withholding guard.**  
   [test_main.c:6919](/Users/fab/dev/ee/hw/o2-probe/firmware/test/test_logic/test_main.c:6919) replaces zero duty with merely `0 < duty < 10000`. In a fresh execution of this fixture, the detector fires at **607 s**: floor demand is **4.94%**, while the dew integral would produce **1.08%** if unreachable-demand withholding were omitted. `max()` therefore produces the same passing output either way. The dwell timing remains tested; withdrawal of dew demand does not.

   Restore an isolated assertion where the floor is satisfied and the dew ceiling is higher. I checked such an input against the unchanged controller: cell **50°C**, tip **54°C**, chamber **51.90°C**, RH **90.56%**, envelope **6 K** produces **10.10%** without `dew_unreachable`, versus **0%** with it and a future retry deadline. Also assert the dew integral is cleared. This tests the guard at [heater_ctl.c:1351](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:1351) without hiding it behind the floor.

2. **P3 — (c) Real test-design defect: the floor monotonicity sweep lost its turn-on region.**  
   [test_main.c:5940](/Users/fab/dev/ee/hw/o2-probe/firmware/test/test_logic/test_main.c:5940) still starts at a **54°C tip / 51°C cell**. The new target is **55°C**, so the sweep starts already **1 K short**, skipping the transition from zero demand through small positive errors. Derive its upper endpoint from `cell + FLOOR_DELTA + headroom`.

   This is a coverage regression, not a demonstrated controller defect: additional native evaluations across 55→53.75°C returned monotonic duties **0, 12.63, 25.25, 37.88, 50.50, 63.13%**.

3. **P3 — (b) Unstated sampling assumption: the historical baseline needs a filter or “typical” qualifier.**  
   The new measurement narrative in [heater_ctl.h:558](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.h:558), [regmap.h:1190](/Users/fab/dev/ee/hw/o2-probe/firmware/src/regmap.h:1190), and the commit message conflates a curing-period baseline with October 14–28 generally. That interval includes **13.89–57.11°C** cell readings. Samples consistent with the 2 K floor have median duty **2.37%**, with excursions outside **1.8–2.6%**. Those quoted figures are plausible representative operating points, but not bounds for the named interval.

## SURVIVED

- **Chamber interlocks:** these compare tip against **chamber**, not cell. October samples consistent with the floor had median tip–chamber **0.12 K**, maximum **0.21 K**; across the available history, their maximum was **0.58 K**. Existing approximately 4 K retry excursions also kept chamber close to tip. This supports substantial separation from **DT_LIMIT at 4 K**, its **3.5 K release**, and chamber runaway at **>6 K**, release **≤5 K**. [heater_ctl.c:214](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:214), [heater_ctl.c:418](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:418)

- **Die runaway and release fixtures:** October floor samples had median tip–die **2.08 K**, maximum **4.17 K**. Conservatively holding die temperature fixed and adding **2.06–2.25 K** puts that maximum around **6.23–6.42 K**, below the **9 K release** and **>10 K latch** boundaries. The older **7.10 K** burial transient could exceed the release boundary after extrapolation; it supports a possible release delay, not a permanently stranded latch. At a 4 K floor, release requires approximately `cell − die ≤ 5 K`. Moving `REL_DIE_C100` preserves the fixtures’ intended “signature cleared” condition. Release also explicitly bypasses the >5% duty exclusion while running under an existing latch. [test_main.c:7858](/Users/fab/dev/ee/hw/o2-probe/firmware/test/test_logic/test_main.c:7858), [heater_ctl.c:381](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:381)

- **Equal floor and ceiling:** no new arithmetic overflow, permanent detector latch, or sustained oscillation was demonstrated. Four **50,000-second** executions using the repository plant model, at 22/57°C ambient and 3/11% coupling, produced **no additional dew-controller heat during retries**. The unreachable flag still cleared at each retry and reasserted after its dwell; floor heating continued. Thus “retry pulses stop adding heat” survives as an operating expectation, not a measured result from the new firmware. Back-calculation applies strictly **above** the ceiling; at equality, integral duty can remain. `HEATER_LAW=DEW` names the combined law, not proof that dew demand wins. [heater_ctl.c:1288](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:1288), [heater_ctl.c:1336](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:1336)

- **Storage mode:** no threshold or credited-seconds arithmetic depends on a 2 K floor. The 6/5 K margin thresholds concern dew margin; the 120-second debt concerns observed controller operation. In the native plant exercise, the new floor reached 90% of its gradient in **10 s** and approximately **3.98 K** before gating at **120 s**. Permission, invalid-input handling, credit caps, and pile exit remain intact. [heater_ctl.c:818](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.c:818)

- **Hot pile:** with coupling \(k=0.03…0.11\), the additional cell warming is approximately  
  \(2k/(1-k)=\mathbf{0.062…0.247\ K}\).  
  Around 57°C this does not consume the remaining approximately 3 K margin to the cell’s limit. Around **59.75–60°C**, it can cross that limit. Neither the **79°C tip ceiling** nor **80°C TIP_LIMIT** protects a 60°C cell limit. That is an existing, explicitly documented control-policy limitation, not a newly introduced cutoff failure. [heater_ctl.h:416](/Users/fab/dev/ee/hw/o2-probe/firmware/src/heater_ctl.h:416)

- **Other changed tests:** the widened RH sweep, dry-end-zero assertion, and widened latch-withholding fixture retain meaningful stimuli. **2525** is correct: \(50×50+0.5×50\). The separate widened-envelope assertion still checks dew demand **253**. The 79°C floor clamp remains tested. The literal 4 K default/equality and fixed expected duty still pin the new setting. Reverting to 200 necessarily breaks the two identified tests; I did **not** independently rerun that mutant to establish the exhaustive failure count.

- **Validation and remaining claims:** direct native rebuilds with the configured flags and Unity dependency reproduced **455 cases: 452 passed, 3 skipped**. Standard PlatformIO was blocked by its external lock-file permission. No register/configuration migration changed. The **4.5–5%** expectation is reasonable near the current operating point; historical 4 K retry samples had median **4.40%**. Existing target artifacts reconcile the reported **48,348-byte / 90.8%** section accounting with a **48,556-byte binary**, still within the slot. Target rebuilding and `native_revb` were not repeated.

## VERDICT

fix-then-flash


