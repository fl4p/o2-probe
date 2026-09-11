## ACCESS

1. **VictoriaMetrics — live query succeeded.**  
   Query: `gas_cell_ua{probe="3"}`  
   Result: `value=[1788822079,"101.46"]`, i.e. **101.46 µA at 2026-09-07 23:01:19 UTC**.

2. **External page — fetched through Playwright.**  
   [TI ADS1119 product page](https://www.ti.com/product/ADS1119) returned:  
   `<title>ADS1119 data sheet, product information and support | TI.com</title>`

## Verdict

The **0.510% step is real and reproducible**, but the proposed ADS1119 predecessor-channel settling mechanism is quantitatively contradicted. Its expected sign is backwards, and the firmware already discarded one complete 20-SPS conversion after every mux/reference change.

A real 12-V supply event has no surviving positive evidence. The root cause remains undetermined because the transition is unobserved, pressure is not measured, and firmware telemetry does not identify the installed build.

## Quantitative mux test

| Quantity | Before `e31d5ac` | After | Change |
|---|---:|---:|---:|
| Channel preceding O₂ | AIN3 / RE_BUF | AIN1 / VREF_TRIM÷2 | |
| Predecessor voltage | ≈1299 mV (`11950/9.2`) | ≈1247 mV (`2494/2`) | **−52 mV** |
| AIN0 telemetry | 954 mV at 20:49:15 UTC | 957 mV at 21:01:52 UTC | +3 mV |
| Normalized current | 102.3244 µA | 101.8096 µA | −0.5193 µA after drift |

The current conversion is `I=(0.67·VREF−V(AIN0))/7 kΩ` ([main.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/main.c:124)). Consequently, the observed step requires AIN0 to move upward by:

`0.5193 µA × 7 kΩ = 3.64 mV`.

That is **not 0.5% of 1.3 V**. The relevant signal is the approximately 714 mV TIA departure from the internal zero, not AIN3’s absolute voltage.

More decisively, ordinary residual mux memory would pull AIN0 toward the preceding input. Since the old predecessor was about 52 mV higher than the new one, it predicts the old AIN0 reading should be higher and the old reported current lower. The observation is the opposite.

The firmware sequence also defeats the settling argument:

- O₂ selects AIN0, external reference, **20 SPS**, eight included conversions ([main.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/main.c:685)).
- Every configuration change executes and discards a complete conversion before returning data ([ads1119.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/ads1119.c:190)). `git blame` dates that discard to `8d329cc`, four days before the event; it is present verbatim in `e31d5ac`.
- SBAS925A specifies **50.01 ms nominal** per 20-SPS single-shot conversion and a one-cycle-settling FIR filter. Thus the first included O₂ result finishes about **100.02 ms** after the change, or approximately 98.1–102.1 ms allowing the ±2% oscillator tolerance. The following seven results add another 350 ms. [ADS1119 datasheet, SBAS925A](https://www.ti.com/lit/ds/symlink/ads1119.pdf)
- A TI engineer’s recommended multichannel single-shot sequence is select channel, start, wait for DRDY, then read—without requiring a dummy conversion. This firmware is more conservative because it adds one. [TI E2E ADS1119 multichannel answer](https://e2e.ti.com/support/data-converters-group/data-converters/f/data-converters-forum/1069270/ads1119-acquiring-all-4-channels-in-continuous-mode)

SBAS925A provides **no numeric analog sampling-capacitance specification**. Its `Ci ≤ 10 pF` specification is for digital pins and must not be used as the analog sampling capacitor. The analog inputs are buffered; TI instead specifies typical absolute and differential input currents of ±5 nA and warns only that sufficiently high source impedance may still require buffering. AFE_VOUT is already an amplifier output.

Even if only the first of the eight included conversions were contaminated, it would need a 29.1 mV error—**56% of the entire predecessor-voltage change**—after the preceding 50-ms conversion had already been discarded. Normal specified settling cannot plausibly produce that.

## Cross-checks and alternatives

- **Step arithmetic:** Recomputing the retained raw series with the stated normalization gives 102.3244 versus 101.8096 µA, background drift +0.01332 µA/h, and a 0.51009% ratio. The equivalent drift interval is 38.98 h. The normalization code and windows are visible in [step2.py](/Users/fab/dev/ee/hw/o2-probe/bench-logs/o2-backfill-2026-09-08/step2.py:10).

- **Noise and flatness:** The same windows give detrended residual standard deviations of 0.0308 and 0.0355 µA, consistent with the claimed 0.032/0.037 µA. One-hour fits bordering the gap were −0.0167 and −0.0292 µA/h; exact slopes depend on window choice, but neither resembles a settling transient.

- **Reboot control:** The second install’s normalized 20-minute medians changed only 101.8216→101.8020 µA, −0.019%. It does not reproduce the first step.

- **Event time correction:** `21:01:52 UTC` is the first post-update telemetry, not application start. It carried `gas_probe_uptime_s=162`, placing app start near **20:59:10 UTC / 22:59:10 CEST**. Gas remained withheld until 21:14:35 UTC because of settling. This does not invalidate the step, but the causal timestamp is less precise than claimed.

- **Measurement chain:** At 20:49:15→21:01:52 UTC, `LMP_READBACK` remained 3277/`0x0CCD`, VREF 2494→2494 mV, VA 3286→3288 mV, ADS failure count 0→0 and I²C errors 0→0. Although telemetry omits MODECN, the firmware reads and validates MODECN every cycle ([lmp91000.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/lmp91000.c:67), [main.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/main.c:244)). `code_to_cell_na()` has been unchanged since August 31. From `e86579b` to `0521239`, `ads1119.c` and both LMP files have no diff; only the corrected AIN2/AIN3 comments changed in `ads1119.h`.

- **Thermal:** Median tip-minus-chamber offset was 0.110 K on both sides; means were 0.1093→0.1062 K. The claimed thermal exclusion survives. One caveat is that a sealed rigid vessel’s O₂ partial pressure also scales with absolute temperature: the endpoint chamber change 27.94→27.69°C predicts about −0.083%, roughly 16% of the observed step, even after correcting cell tempco. It cannot explain all 0.51%.

- **Pressure:** A 0.510% pressure explanation requires about 4.9 hPa. The external best-match model for the repo’s coordinates reported 940.5→940.2 hPa between 20:45 and 21:15 UTC—only 0.3 hPa. [Open-Meteo 15-minute series](https://api.open-meteo.com/v1/forecast?latitude=48.01475&longitude=8.03294&minutely_15=surface_pressure&start_date=2026-09-07&end_date=2026-09-07&timezone=UTC) This weakens the hypothesis but is model output, not an on-site or in-vessel observation. Rev A publishes pressure as zero ([regmap.h](/Users/fab/dev/ee/hw/o2-probe/firmware/src/regmap.h:66)), so a local pressure disturbance remains unexcluded.

- **Supply:** Before `e31d5ac`, `gas_vin_mv` is not VIN; after it, VIN is read from PA6 ([mcu_adc.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/mcu_adc.c:152)). Therefore **a real 12-V event is unverified**. Stable VA and VREF argue against a downstream rail/reference event, but regulated rails cannot prove that upstream 12 V was constant. There is no surviving evidence supporting the original 11950→10463 mV “drop.”

- **AIN3 plateaus:** “Only three discrete levels” is slightly overstated: the 15,042 pre-event samples contain **15 reported codes grouped into three clusters**. Counts include 11950×13,331, 11960×832, and 11941×114 around 1.299 V; several codes around 1.130 V; and 7958×88 plus 7967×1 around 0.865 V. The exact repeats are explained partly by the old integer-mV truncation before multiplication by 9.2 (`e86579b:main.c:398-410`). The large cluster changes align with resets:

  - 11:31:08 UTC: ≈865→1299 mV
  - 11:58:05 UTC: ≈1299→1132 mV
  - 13:19:18 UTC: ≈1130→1299 mV

  The old image exposed functioning `FAULTS_EVER`/`ADS_FAILS`, placing it after `e86579b` and therefore after the `b995f62` DRDY fix; see the contemporaneous [SWD capture note](/Users/fab/dev/ee/hw/o2-probe/bench-logs/swd-capture-2026-09-05-NOTES.md:15). Thus AIN3 was probably a valid digitization of **RE_BUF**, not a stale previous-channel conversion. The reset-correlated analog common-mode state is suspicious, but the data cannot distinguish the electrode, its buffer, or a temporary bias/reference interruption. Current firmware reads neither AIN2 nor AIN3 ([ads1119.h](/Users/fab/dev/ee/hw/o2-probe/firmware/src/ads1119.h:33)).

- **RESET_CAUSE:** Confirmed broken. The loader calls `o2p_clock_init()` first ([loader_main.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/loader_main.c:409)); that function latches RCC_CSR and clears RMVF ([mcu.c](/Users/fab/dev/ee/hw/o2-probe/firmware/src/mcu.c:25)). The loader then jumps directly to the application, whose own initialization reads already-cleared flags. All 15,184 retained samples are zero.

No repository files were modified.

## FINDINGS

1. **(a) Arithmetic/sign error — the leading mux-settling hypothesis is rejected.** The needed offset is 3.64 mV, not 0.5% of 1.3 V; normal predecessor memory predicts the opposite sign; and the first retained result comes only after two complete 20-SPS conversion intervals.

2. **(c) Real design defect — reset-cause telemetry is consumed by the bootloader.** `RESET_CAUSE` cannot diagnose any of these reboots without a loader-to-app handoff.

3. **(c) Real design defect — firmware provenance is not telemetered.** `O2P_FW_VERSION` remains hard-coded to `0x0001` ([regmap.h](/Users/fab/dev/ee/hw/o2-probe/firmware/src/regmap.h:228)); no build ID/SHA independently proves which binary caused the first step. Commit timing suggests `0521239`, but telemetry cannot establish it.

4. **(c) Real diagnostic defect — pressure and AIN2/AIN3 disappear exactly where they are needed.** The unobserved transition cannot be separated conclusively into cell, pressure, or analog-common-mode causes.

5. **(a) Timestamp error — 23:01:52 CEST is first telemetry, not app start.** Uptime places application start near 22:59:10 CEST; the actual reset/install began earlier.

6. **(a) Counting error — AIN3 has 15 codes in three clusters, not literally three values.** The plateaus and reset alignment are real; much of the exact pinning is integer telemetry quantization, not ADC rail quantization.

## SURVIVED

- The normalized step magnitude, +0.0133 µA/h background drift, approximately 39-hour equivalence, and similar noise on both sides.
- Reboot alone is not a sufficient explanation; the later firmware install did not reproduce the step.
- Constant LMP configuration, VREF, ADC health, and absence of ADS1119/LMP implementation changes across the relevant commit span.
- The thermal-offset exclusion and the conclusion that the post-event series is not an ongoing relaxation.
- The correction that pre-event `gas_vin_mv` was RE_BUF misscaled as VIN. No affirmative evidence of a real supply drop survives.
- The empirical lack of correlation between the large RE_BUF common-mode jumps and cell current.
- The old AIN3 samples were collected after the DRDY fix and are substantially more credible than the “previous channel” history initially suggests.
- The claim that the bootloader clears RCC reset flags before the application reads them.
