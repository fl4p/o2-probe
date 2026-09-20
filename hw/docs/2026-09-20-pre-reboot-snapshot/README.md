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
| `gas_build_id` | 1227967052 = **0x49301C0C** | becomes **0x02B7ED0A** if the flash lands - this is the readback that proves it |
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
