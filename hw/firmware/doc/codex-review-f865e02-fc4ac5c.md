## ACCESS

1. TI browser `<title>` / first line: **unverified** — the browser runtime reported no available browser. A separate direct live fetch of the official PDF returned “ADS1119 4-Channel, 1-kSPS, 16-Bit, Delta-Sigma ADC With I2C Interface,” but I did not count that as satisfying the browser check.
2. Live external query result: [ADS1119 datasheet — Texas Instruments](https://www.ti.com/lit/gpn/ADS1119), returned first for `site:ti.com ADS1119 START SYNC DRDY SBAS925A`.

Source access log:

| Source | State and route |
|---|---|
| [TI ADS1119 SBAS925A](https://www.ti.com/lit/ds/symlink/ads1119.pdf), Aug. 2018/rev. Nov. 2018 | Relevant pages 19, 21, 23, 25, and 26 inspected from direct official PDF text and validated against rendered pages. Browser attempt unavailable. Load-bearing. |
| Serper live search, 2026-09-04 | Metadata only; raw JSON result. Not load-bearing. Challenge searches for contradictory DRDY/START behavior and ADS1119 errata found no exact ADS1119 contradiction; no absence claim rests on that. |

No file was created or modified.

## FINDINGS

1. **High — (c) The intermittent-DRDY hole is still open, so round two can still silently return the previous conversion.**  
   [ads1119.c:241-270 at `fc4ac5c`] samples DRDY high exactly once after START, then [ads1119.c:259-263] accepts the first later low as conversion completion. A floating pin or open R19 can read high at line 250 and spuriously low at the next loop evaluation, before the real 11.29 ms or 50.01 ms conversion completes. RDATA then returns the “most recent conversion result” per SBAS925A §8.5.3.5, and the code accepts it as current data. The checklist’s claim that the second sample “closes the hole” is therefore false ([GUARD-REVIEW-ads1119-recovery.md:37-43]). An authoritative status-register confirmation after GPIO falls, or a conservative minimum-conversion-time gate, is still required.

2. **High — (c) DRDY stuck high is still reported as an I²C failure.**  
   `O2P_ADS_TIMEOUT` explicitly means “DRDY never asserted” ([ads1119.h:46-54]), and is returned only after WREG and START succeeded ([ads1119.c:234-262]). Nevertheless the `default` arm maps it to `O2P_F_I2C_FAIL_ADS` ([main.c:323-327]). Thus an open/stuck-high DRDY pin again tells the operator “I²C,” the same diagnostic misdirection these commits were meant to eliminate. Oxygen is invalidated correctly, so this is diagnostic rather than data corruption, but on a potted probe it can still trigger the wrong physical intervention.

3. **Medium — (c) Configuration loss can still publish a plausible oxygen value, despite “all three fail closed.”**  
   Readback occurs only when `cfg != s_last_cfg` ([ads1119.c:153-190]); every same-config conversion writes WREG but does not verify it ([ads1119.c:208-213]). The checklist itself eventually admits that a failure during the final eight-sample O₂ phase can be published before the next channel change detects it ([GUARD-REVIEW-ads1119-recovery.md:138-149]), contradicting “All three fail closed” at lines 20-25. At the committed 100 kHz bus speed, twelve additional one-byte RREG operations cost about `12 × 36 clocks / 100 kHz = 4.32 ms`, while the ADC portion already finishes in roughly 0.53 s. The 1 Hz deadline does not justify knowingly retaining this “unknown configuration looks valid” path.

4. **Medium — (a) The claim that recovery hides no prior fault is false at the actual reporting cadence.**  
   The checklist says a stranded-result failure was already reported and therefore later recovery “hides nothing” ([GUARD-REVIEW-ads1119-recovery.md:90-93]). But `cycle_begin()` clears faults every second ([main.c:160-175]), while the deployed uplink is every five minutes ([tech/RS485-LS-SMT100.md:25-36 at `5d5fd18`]). `I2C_ERRS` is in the diagnostic block, deliberately outside the polled primary block ([regmap.h:28-42,58]). A one-cycle failure followed by a successful drain will normally never reach ChirpStack or Home Assistant.

5. **Low — (a) The checklist retains the pre-fix drain-status description.**  
   It says a failed drain transfer returns `O2P_ADS_DRDY` unless DRDY rises ([GUARD-REVIEW-ads1119-recovery.md:20-25]). The committed implementation correctly returns `O2P_ADS_IO` for that transfer failure ([ads1119.c:119-133]). Later prose describes the correction, leaving the document internally contradictory.

6. **Low — (a) The “corrected” runtime-cost arithmetic still uses the wrong bus rate.**  
   The checklist claims approximately 165 µs per configuration change and 500 µs per cycle ([GUARD-REVIEW-ads1119-recovery.md:125-130]); the driver is configured for 100 kHz, not 400 kHz ([i2c1.c:6-15]). WREG plus RREG requires at least 27 + 36 clocks, about 630 µs per change or 1.89 ms per cycle. The related “~50 µs” per-conversion readback claim is likewise wrong ([ads1119.c:165-169]). This does not endanger the 1 Hz loop.

7. **Low — (b) The post-START assertion also assumes bounded software latency.**  
   SBAS925A guarantees conversion timing from command latch, not how quickly firmware resumes after the I²C call. A sufficiently long interrupt before [ads1119.c:250] could let a healthy 1-kSPS conversion complete and cause a false DRDY fault. That assumption happens to hold here: committed call sites use only 90 SPS and 20 SPS ([main.c:64-69,593-607]), and the enabled SysTick/USART handlers are short. It is not a datasheet-only guarantee as the comment implies.

## SURVIVED

- There is no legitimate ADS1119 hardware path that makes DRDY low immediately after START in the committed sequence. The stale result is drained first; WREG and START reset/restart any ongoing conversion; the 28.5-tCLK latency delays rather than accelerates completion. The post-START check therefore does not false-positive from an earlier result, WREG race, or normal converter timing.
- `drain_stale_result()` now preserves `O2P_ADS_IO`, `O2P_ADS_DRDY`, and `O2P_ADS_OK` without narrowing. Drain-I/O and final-RDATA-I/O are not distinguishable, but both truthfully mean an ADS-directed I²C transaction failed; stage-level distinction is less important than the missing event persistence identified above.
- Fast-path invalidation is correct. It changes no healthy-cycle timing, and `o2p_ads1119_average()` propagates the first error while the next same-config call performs re-verification and a throwaway.
- A healthy cycle still performs exactly 15 conversions: `(2+1)` VREF, `(2+1)` VIN, and `(8+1)` O₂. Nominal conversion time is `6×11.29 + 9×50.01 = 517.83 ms`; including 100-kHz command traffic gives roughly 0.53 s, leaving substantial margin inside one second.
- All three accumulator consumers use `O2P_FAULTS_ADS_NO_CONVERSION` at [main.c:368], [main.c:398], and [main.c:422]. The mask includes I²C, DRDY, and configuration failures; no remaining bare `O2P_F_I2C_FAIL_ADS` validity gate was found.
- At the named commit states, bit 13/14 are correctly positional in the ChirpStack decoder and Grafana description. Direct evaluation produced `bit13=ads_drdy_stuck` and `bit14=ads_config_lost`; the decoder’s 73 assertions pass. No live Python, YAML, JavaScript, Grafana, or firmware consumer retaining the old positional names was found.
- `fc4ac5c` correctly repairs the three explicit `f865e02` regressions: drain bus errors retain `O2P_ADS_IO`, configuration mismatch gets bit 14, and fast-path failures invalidate the cache.
