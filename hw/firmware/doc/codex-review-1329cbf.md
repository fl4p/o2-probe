## ACCESS

1. Through the already-running headed Chrome, the TI product page returned `<title>` **“ADS1119 data sheet, product information and support | TI.com”**. The direct PDF rendered successfully in Chrome.
2. Live external query `site:ti.com ADS1119 SBAS925A conversion times internal oscillator accuracy` returned [TI’s ADS1119 datasheet](https://www.ti.com/lit/gpn/ADS1119) as result 1.

The previous “no available browser” diagnosis is refuted. The browser-client selector failed with `Browser is not available: chrome`, but the dedicated Playwright MCP attached successfully, listed the existing `about:blank` tab, and rendered TI pages.

Source access log:

- [ADS1119 datasheet, SBAS925A, revised November 2018](https://www.ti.com/lit/ds/symlink/ads1119.pdf) — inspected PDF pages 5, 19, 23, and 26: §6.5 oscillator limits, §8.3.6/Table 4, §8.5.1.3 DRDY, and §8.5.3.5 RDATA. Headed-Chrome rendered-page route; visually validated; load-bearing.
- [ADS1119 product page](https://www.ti.com/product/ADS1119) — live DOM/title inspected and validated; metadata only.
- Serper live Google result — metadata only, not used as technical evidence.

All citations below refer to commit `1329cbf`. No repository file was modified; Playwright’s temporary artifacts were removed.

## FINDINGS

1. **High — (c) Round three still does not close the intermittent-DRDY hole; it narrows the vulnerable time window again.** `src/ads1119.c:152-159,287-305`

   Table 4 gives the single-shot cycle counts; §8.3.6 adds 28.5 clock cycles after START/SYNC, and §6.5 guarantees `fCLK` from −2% to +2%:

   | SPS | Gate | Fastest START→DRDY | Slowest START→DRDY |
   |---:|---:|---:|---:|
   | 20 | 49 ms | 49.059 ms | 51.062 ms |
   | 90 | 10 ms | 11.092 ms | 11.545 ms |
   | 330 | 2 ms | 3.035 ms | 3.158 ms |
   | 1000 | 0 ms | 1.043 ms | 1.086 ms |

   Formula: `t = (Table-4 cycles + 28.5) / (1.024 MHz × {1.02, 0.98})`.

   The code starts trusting DRDY at the gate, not at the latest guaranteed completion time. A slow 20-SPS device can therefore still be converting for about 2.06 ms after the nominal 49-ms gate; tick phase can make the gate eligible almost another millisecond early. A floating line sampled low in that interval breaks the loop and issues RDATA. Per §8.5.3.5, RDATA then supplies the most recent completed conversion—the previous channel—while returning `O2P_ADS_OK`.

   The same ambiguity exists at 90 SPS, which is used for VREF and VIN. The correct invariant would require either checking the ADS1119’s internal status bit after the pin falls or waiting through the latest guaranteed conversion time. “Earliest possible” cannot authenticate which conversion caused a noisy pin level.

   For 1000 SPS, `o2p_elapsed(t0, 0)` is true immediately. Consequently the first branch handles every `ready` case and `ready && earliest == 0u` at lines 295-297 is dead code. That rate is entirely ungated. Current `main.c` does not call it, but the driver API exposes it.

2. **High — (c) `O2P_ADS_TIMEOUT` is not exclusively a pin fault, so mapping it to `ADS_DRDY_STUCK` creates the mirror diagnostic defect.** `src/main.c:318-334`; `src/ads1119.c:298-300`; `src/faults.h:41-47`

   Successful WREG and START transfers prove only that those I²C transactions were acknowledged. TIMEOUT can also result from:

   - an ADS1119 reset or brownout after START, with the external pull-up holding DRDY high;
   - a stalled internal oscillator or conversion engine;
   - an acknowledged but corrupted/ignored START command—I²C has no payload CRC;
   - a wrong or failing device that accepts configuration traffic but never converts;
   - GPIO/pin-path failure.

   Thus TIMEOUT proves “no sufficiently late DRDY-low was observed,” not “the pin failed.” The fault-bit documentation makes the contradiction explicit: `faults.h:41-47` describes only a pre-START low that failed to release, while this commit also routes post-START stuck-high/timeouts there. Oxygen invalidation is correct, but the repair diagnosis is not.

   This remapping is also a **mute rather than a fix**: it changes the warning label without adding evidence that distinguishes pin, ADC core, power, command, or bus-integrity failure.

3. **Medium — (c) Intermittent diagnostics remain operationally muted before they reach ChirpStack/Home Assistant.** `src/main.c:160-175`; `doc/GUARD-REVIEW-ads1119-recovery.md:112-127`

   `cycle_begin()` clears the fault word every second. With a five-minute uplink, a one-cycle DRDY/TIMEOUT event normally disappears before polling—roughly 299 times out of 300. This commit documents the missing cumulative recovery/error counter but does not implement it. That is honest documentation, but the new fault classification is still mostly ephemeral in the deployed system.

4. **Low — (a) The checklist contains its fourth false claim.** `doc/GUARD-REVIEW-ads1119-recovery.md:39-65`

   “Worse input cannot flip the verdict back to PASS” is false. An intermittent line that reads low before the gate is ignored, but the same faulty line reading low after the gate flips the outcome to `O2P_ADS_OK` with stale data. The later assertion that “the authority is the clock” is likewise unsupported: the clock only rejects impossibly early lows and leaves the entire plausible-but-not-yet-complete interval dependent on the pin.

## SURVIVED

- **The feared healthy-device false positive does not occur.** Even the +2% clock times above are later than the numeric gates. More importantly, if software latency makes a healthy completion precede the gate relative to `t0`, §8.5.1.3 says DRDY remains low in single-shot mode until result retrieval. The loop waits with `ready == true`, then exits when the gate becomes true; it does not run to timeout. `earliest < limit` for every rate.

- **The healthy 1-Hz loop closes.** There are 12 requested samples plus three configuration-change throwaways: `6 × 90 SPS + 9 × 20 SPS` (`src/main.c:64-69,597-616`).

  - Gate floor: `6×10 + 9×49 = 501 ms`; this is not additive to real conversion time.
  - Slowest guaranteed conversions: `6×11.544862 + 9×51.061763 = 528.825 ms`.
  - Each conversion uses `27` WREG clocks + `18` START clocks + `45` RDATA clocks = `90`; configuration verification adds `27+36=63` clocks on three changes.
  - Bus total: `(15×90 + 3×63) / 100 kHz = 15.39 ms`.
  - Conservative ADS subtotal: **544.215 ms**. Including SHT’s 12-ms wait, normal LMP/TMP traffic, and even the MCU ADC’s four defensive 15-ms wait envelopes remains about **620 ms plus small framing/software overhead**, comfortably below one second.

- TIMEOUT still invalidates all ADS-derived fields: `ADS_DRDY_STUCK` belongs to both `O2P_FAULTS_ADS_NO_CONVERSION` and `O2P_FAULTS_INVALIDATE_O2` (`src/faults.h:74-99`).

- The predecessor repairs for preserving drain-I²C errors, invalidating `s_last_cfg` after fast-path failures, adding `ADS_CONFIG_LOST`, and counting configuration verification at approximately 630 µs/change survive this review.

- The checklist’s admissions concerning same-config write verification, untested hardware recovery, 100-kHz arithmetic, and non-persistent recovery telemetry are accurate.
