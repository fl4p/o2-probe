# Pre-reboot snapshot, 2026-09-20 16:38:54 local

Taken because farming-77 is about to reboot the node, which takes the PROBE's
rail with it (farming-77's own measurement, 2026-09-19: eight node reboots in
three days, `gas_reset_cause` 12 = PIN | PWR each time). A reboot reloads the
COMMITTED config record, not RAM, so this is the before-picture for the
calibration as much as for the counters.

Nothing in my own analysis needs live continuity - the 2026-09-17 pile capture
and the 2026-09-19 soak are exported and committed. This exists so that if the
calibration comes back different, that is visible rather than inferred later.

| register | value | why it is here |
|---|---|---|
| `gas_fw_version` | 37 = **0x0025** | the knee model is NOT live; 0x0028 is the target |
| `gas_build_id` | 1227967052 = **0x49314A4C** | see the correction below - the acceptance value I wrote here was wrong |
| `gas_hw_rev` | 10 | Rev A |
| `gas_cal_state` | **6** | the air point in force |
| `gas_cal_result` | 0 | last calibration outcome |
| `gas_commit_result` | 0 | last NVM commit outcome |
| `gas_faults` | 0 | clean at snapshot |
| `gas_faults_ever` | 2049 = 0x0801 | ADC_RANGE \| SETTLING, since power-up |
| `gas_settle_restarts` | 1 | flat all day; NOT evidence of a restart |
| `gas_probe_uptime_s` | 85178 s = 23.7 h | monotonic across the 208 min examined |
| `gas_sample_seq` | 19640 | advancing at exactly 1 Hz |
| `gas_reset_cause` | 12 = PIN \| PWR | NRST + power-on; no IWDG, no software reset |

**The air check.** At snapshot the probe sat in bench air at `t_ext` 21.51 C,
chamber 23.48 C, RH 43.67 %, drawing **98.39 uA** and publishing **20.66 %vol**.
If it reads materially different at the same temperature after the reboot, the
committed record did not survive and that is a finding, not noise. The
2026-09-19 R1/R2 bracket already showed the calibration surviving two power
cycles and two config reloads to -0.09 %, so the expectation is that it holds.

**What the reboot costs.** ~15 min of untrustworthy oxygen while the probe
re-settles (`O2P_SETTLE_SECONDS` 900 - and `settle_s` COUNTS DOWN, so 900
means it just started), a restart of `gas_probe_uptime_s` and
`gas_sample_seq`, and the 88 bytes sitting in the loader's staging slot.

**What it buys, and it is the good part.** The slot emptying separates the two
hypotheses for the write stall. Every push that moved blocks today went through
CMD_BEGIN; the run that stalled resumed at block 1 and `push()` skips
CMD_BEGIN on the resume path, so it sent a block write to a loader that never
got BEGIN in that session. After a power cycle the next push starts from BEGIN
anyway. If writes are answered then, it was the resume path; if they are still
not answered, it is the probe's reply path and no transport change fixes it.


---

## CORRECTED 2026-09-20 17:xx, after the flash landed

**The flash landed. Probe 3 reads `gas_fw_version` = 40 = 0x0028 and
`gas_build_id` = 1119350026 = 0x42B7ED0A. The knee model is live.**

**The acceptance value above was wrong and it was my error.** I wrote
"becomes 0x02B7ED0A" by taking the commit prefix `2b7ed0a` and padding it,
without checking how `regmap.c` composes the word it actually publishes.
farming-77 caught it. `regmap.h:214-231` and `regmap.h:1140-1141`:

| bits | meaning |
|---|---|
| 31 | working tree was dirty at build time (`O2P_BUILD_ID_FLAG_DIRTY`) |
| 30 | debug build (`O2P_BUILD_ID_FLAG_DEBUG`) |
| 29..28 | reserved |
| 27..0 | 7-hex-digit commit prefix |

Decoding both images with that:

| | raw | dirty | debug | commit |
|---|---|---|---|---|
| before | 0x49314A4C | 0 | **1** | 9314a4c |
| after | 0x42B7ED0A | 0 | **1** | **2b7ed0a** |

So the running image IS commit 2b7ed0a, from a CLEAN tree. The only difference
from what I expected is bit 30.

**The right test is to mask, not to match**, because it survives someone
building with debug off:

    (gas_build_id & 0x0FFFFFFF) == 0x2B7ED0A

**The debug bit is not disqualifying, and saying otherwise would invalidate my
own baselines.** `platformio.ini:92` carries `-DO2P_DEBUG_ENABLE=1` in the
DEFAULT environment ("Enabled by default for bench bring-up and
characterization"); a separate env sets it to 0. It gates the Modbus peek/poke
mailbox, GPIO diagnostics and crash breadcrumbs - diagnostic surface, not the
measurement path. And the pre-flash image has bit 30 set too, which means every
number in the oven-soak and in-pile analyses was measured on a debug build. A
standard that rejects this image rejects the evidence the model was fitted
from.

**The premise of this snapshot did not happen as stated.** I took it expecting
the node reboot to power-cycle the probe. `node_uptime_s` shows **zero resets**
across the whole operation - 84157 at 16:20:51 through 85748 at 16:47:22,
continuous - while `gas_probe_uptime_s` reset once, 85299 -> 23 between
16:40:55 and 16:45:15. So the probe was restarted by its own INSTALL, not by
the node's rail going away. The caveat farming-77 raised stands and I am not
claiming past it: a software `esp_restart()` folds elapsed time into the RTC
clock (`main.cpp:2701`) and would look identical to no reboot at all.

The snapshot was still worth taking - the bench-air comparison it sets up is
unaffected, and that is the test that matters next.
