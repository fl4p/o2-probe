# 2026-10-28 — probe 3 at the pile: O2 dropouts, heater duty, storage mode

Probe 3 (`dev_eui 34b7dafffe5b84e0` node), FW 0x002C, in the curing pile since
10-14. Sources: VictoriaMetrics `gas_*{probe="3"}` (raw export, 1 min) and two
LoRaWAN CTRL register reads this morning (`farming/.flash-runs/storage-read-2026-10-28.log`,
`heater-read2-2026-10-28.log`).

## Storage mode — cleared (measured)

- Register read 10-28: `0x0018` FW = `0x002C`, `0x004C` = `0x0000`.
- Cell side (`gas_t_ext_c`, the heater's `t_cell` via the cell bridge,
  `main.c:1592`) held 50..57 °C from 10-16 18:10 to 10-21 22:40 (500 samples at
  10-min steps), so the 0x002C auto-exit (cell >= 50.00 °C) had its condition.
  No manual clear found in logs or commits since 10-14.
- **Not established:** the exact clear time (storage state is not exported),
  and whether flash agrees with RAM (`0x004C` reads the RAM config; a failed
  commit would bring `0x5A` back on the next probe reset).
- Gap noted on 10-14, still open: a cool pile (< 50 °C, RH held < 95 % by the
  floor) never meets either exit condition. A margin-based exit was proposed,
  not built.

## Heater duty ~2 % — the floor alone (measured)

- Register read 10-28: `HEATER_LAW 0x0008` = `0x0104` (dew law + DEW_UNREACHABLE),
  `HEATER_MAX_DUTY` 100.00 %, `DT_MAX_K` 4.00 K, `HEATER_BLOCK` `0x8000`/`0xC000`
  (annotations only), faults 0.
- Ceiling = min(79 °C, cell + 4 K); at 3..11 % coupling the 4 K margin is
  unreachable there, the detector gives up after 600 s, and only the 2 K
  gradient floor runs: tip ≈ cell + 2 K at 1.8..2.6 % duty. Every 6 h the dew
  law retries for ~10 min at ~4.4 % (tip +2 K, chamber RH 79 → 73 %).
- Fab chose a 4 K floor (FW 0x002D, commit `4e816dc`, not flashed at time of
  writing). Expected ~4.5..5 % duty — unmeasured.

## O2 dropouts to ~1.5 µA — coincide with the retry pulses (measured; cause open)

Cell current fell from ~97 µA (air, 21 %) to a flat 1.1..1.9 µA (reads ~0.3 %
O2) with `comp_ok=1`, faults 0, no reset (`sample_seq` continuous, settle 0):

| edge | heater retry pulse | cell current |
|---|---|---|
| 10-24 down | 19:30–19:38 | noisy from 19:47, ~10 µA by 22:00 |
| 10-25 down | 01:38–01:48 | 9.8 → 1.6 µA at 01:41–01:44 |
| 10-25 up | none seen at 20-min resolution | back to ~100 µA ~05:20 |
| 10-27 down | 08:14–08:20 | 97.7 → 1.1 µA by 08:25 |
| 10-27 up | 20:31–20:41 | 1.6 → 13 → 236.7 µA ×3 (pct invalid) → 103 → 95 µA |

Raw samples < 5 µA per day (60 d): 09-11 52, 09-12 10, 09-17 4, 09-18 38,
**10-03 34**, 10-24 1, 10-25 258, 10-27 650.

**10-03 breaks the pulse correlation.** 02:49:09 96.2 µA → 02:52:09 1.6 µA in
one 3-min sample step (1-min samples either side), with **no heater pulse**:
duty steady 1.8..2.1 %, tip 16.9 °C flat, chamber RH 63 % (cell 16 °C, probe
not yet back in the pile). The only nearby event is chamber/RH invalid at
02:40–02:43 (an SHT45 de-creep window). It then sat at 1.3..2.2 µA, with
noisy partial recoveries (to ~19 µA at 04:39–05:18), until 21:45.

**Hypotheses, unproven:**
- Electrical/AFE state change (the cell or LMP91000 path flips into a ~1.5 µA
  state and back). Fits: a step inside one sample at constant heat and 63 % RH,
  the flat plateau, and the 236.7 µA ×3 (pct invalid) on the 10-27 recovery,
  which looks like an AFE limit. The 10-24..27 pulse coincidences would then
  be a trigger, not the mechanism, or chance.
- Liquid water in the diffusion path (cell-side margin 1.5..2 K at the pile).
  **Weakened by 10-03** (63 % RH, no thermal event, one-sample step).
- Real anoxia: against — 21 → 0.3 % in minutes and back to exactly ambient,
  in air on 10-03.

**Next:** look for a common trigger across all eight days (SHT45 de-creep
windows, CTRL bus claims, LoRaWAN sessions, node polls), and read the AFE
diagnostic registers during a dropout rather than after it.
