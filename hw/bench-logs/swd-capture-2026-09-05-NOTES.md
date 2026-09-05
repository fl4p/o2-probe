# SWD capture, 2026-09-05 — what is in these files and what not to trust

A 12 h read-only regmap capture of the Rev A first article, started 02:17 and
run over a shared bench while another session did AFE bring-up on the same
board. That is why this note exists: three of the discontinuities in the data
are the bench, not the probe, and one row is wrong while claiming not to be.

## The files

| File | Columns | Span | Rows |
|---|---|---|---|
| `swd-capture-2026-09-05-12h.csv` | 23 | 02:17:59 – 09:36:31 | 854 ok, 6 failed, **1 bad** |
| `swd-capture-2026-09-05-12h.2.csv` | 25 | 09:40:39 – | see file |

Two files because the firmware gained `FAULTS_EVER` (`0x0023`) and `ADS_FAILS`
(`0x0024`) mid-run, so the tool's column set changed. They are not merged:
filling the two new columns for the earlier 854 rows would mean inventing them.

## The one row that lies

    2026-09-05T09:36:31,ok,215547903,2470,0,236.41,0.00,0xffff

**`status=ok` and every field is garbage.** Uptime 215547903 s, all fault bits
set, cell 236 µA. Discard it. It is not deleted on purpose — it is the evidence
for `2a1ad62`, and a dataset that quietly loses its own worst row teaches
nothing.

Cause: `o2p_capture.py --count N` resolves the address and the struct layout
once and holds them for the whole run. At 09:33 a rebuild grew
`o2p_snapshot_t` from 52 to 56 bytes and moved `g_rm`; the running process
could not notice. The VREF plausibility check caught the sample before it and
missed this one — a wrong layout can put a plausible number in the very field
being checked. Fixed twice since, in different places: `2a1ad62` samples by
re-exec so a rebuild is picked up next sample, and `12ed6c6` refuses to start
when `sizeof(g_rm)` in the ELF disagrees with `REGMAP_LEN`.

Use `tools/o2p_capture_loop.py` for anything longer than a few minutes.

## Discontinuities that are the bench, not the probe

- **09:04:03 – 09:06:34, 5 `failed` rows.** Board reflashed from the 02:03
  build. `g_rm` moved `0x200000F0` → `0x200000F4`. Part 1 ran pinned to the old
  address with `--addr`; part 2 resolves it from the ELF.
- **09:07:04 and 09:07:34, `cell_ua = -117.34`, `faults 0x8801`. INJECTED.**
  A GAIN=4 fault injection pinned the ADS1119 channel at +32767, so the AFE
  output read 2491 mV — within 1 mV of VREF — instead of its usual ~962 mV.
  Not a board fault. Exclude from any cell statistics: it is a pinned
  converter, not a current.

  Worth keeping for what it exposed. `ADC_RANGE` (bit 11) caught it but
  `afe_rail` read **0**, because that column only tested 0 V and VA and
  2491 mV is nowhere near either. The ADS1119 converts against the external
  reference, so its full scale is VREF — a full 800 mV below VA — and a
  converter can be hard against its own ceiling while the supply-rail test
  sees nothing. Fixed since: the converter's full scale now counts as a rail,
  and `cell_ua` is withheld rather than derived from a pinned conversion.
- **Three resets between 09:06 and 09:08**, visible as `uptime_s` restarting.
- **09:45:39 and 09:46:09, 2 `failed` rows.** The capture tool itself was
  rewritten under the run. Both are honest failures — a `TypeError` in an
  intermediate commit, then `12ed6c6`'s new size guard correctly rejecting a
  160-byte assumption against a 152-byte ELF. Recovered by itself at 09:46:43.

## The fault bits between 09:40:39 and 09:42:09 are INJECTED

`faults = 0xa001` — bit 13, `ADS_DRDY_STUCK` — in that window is **deliberate**.
The other session drove PB1 to analog over SWD to calibrate the guard. Observed
clearing between uptime 370 (09:42:09) and 400 (09:42:39).

`FAULTS_EVER` keeps `0xa001` **permanently** and `ADS_FAILS` is frozen at 32 for
the rest of the run. Both are latched history of that injection, not a live
fault. Do not read either as a defect in this board.

Note the new bit-13 latch holds for 330 s past the fault, by design — a
one-cycle converter fault used to be published for one second against a
five-minute poll and vanished ~299 times in 300.

## A sampling caveat

Every sample halts and resumes the target, and a halted target does not advance
`uptime_s`. So this capture perturbs, slightly, any timing reasoned out of its
own `uptime_s` column — including the 330 s latch window above.

## What the data actually says

Over 02:17 – 09:03, undisturbed, on one image: cell current **100.23 – 101.23 µA,
σ 0.14 µA, mean 100.78 µA** — ±0.5 % of reading, mid-band against the 70–130 µA
datasheet spec in air. Ambient obliged with a 3.3 K overnight swing
(25.6 → 22.3 °C), giving a first estimate of the cell tempco: **+0.184 µA/K,
~1830 ppm/K**. Provisional — tip and chamber moved together, so this cannot
separate a cell tempco from a TIA or reference tempco, and it needs a deliberate
two-point soak. It is not negligible: 0.6 µA across that swing, ~0.13 %vol O₂.
The firmware ships `tempco_ppm_per_k = 0` because SGX publishes no curve.

Dew margin never closer than **7.18 K**. RH tracked the inverse of temperature
at roughly constant absolute humidity, 47.2 → 64.3 %.
