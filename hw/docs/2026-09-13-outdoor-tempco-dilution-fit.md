# Tempco + dilution fit on the outdoor run, 2026-09-12 18:40 → 09-13 11:23 UTC

Probe 3, cell #1, coated board after the C9 repair, air point of 09-12 18:35 UTC
(`CAL_AIR_NA` 101 327 nA, `TEMPCO` 0, `DIL_ALPHA` 1.000). **Fab, 2026-09-13: the
probe was outside the whole time**, so dry-basis O₂ is taken as 20.946 %vol
throughout. That is an assumption about the gas, not something telemetry shows.

Tool and raw data: `bench-logs/2026-09-13-outdoor-fit/` (`gas.ndjson` VM export,
`openmeteo.json`, `fit.py`, outputs `fit.out`, `resid.out`, `cross.out`).

## What the run contains

- 866 usable rows at 60 s (dropped: settle, `0x6866` faults, current outside 50–150 µA).
  Nine more with |residual| > 1 % were clipped: single-sample spikes of 87–102 µA,
  seven of them 03:42–04:30 during the θ-probe heater cycling, plus two in the evening.
- T_EXT (cell-side TMP117) **12.86 → 35.97 °C**: an overnight cool-down, then sun.
- p_w/P 1.11 → 3.11 %. Pressure: **Open-Meteo surface pressure at 48.04 N 8.03 E, a
  regional proxy, not a site reading** — 924.8–926.7 hPa, a 0.2 % band.
- Published `pct_vol` **20.39 → 21.42 %vol** (hourly medians). Cell current 98.5 → 102.4 µA.
- Heater: θ-probe cycling 21:00–07:00 (duty ≤ 5 % hourly median), dew/gradient law after.
  Four probe boots in the morning (FW 22, 23, 25, 26, plus a POR at 11:16). Median
  residual per boot segment: −0.08…+0.13 %, so no K step is visible across them.

## Model

`I = K · g(T) · L(C0·(1 − α·p_w/P)) / L(C0)`, where `L(c) = −ln(1−c)` and
`p_w = RH·psat(T_chamber)` (Buck). g is either a linear `exp(β(T−20))` or the
capillary law `(T_K/293.15)^0.75`, which has no free parameter (§9.3 of
`2026-09-11-o2-model-fit-vs-truth.md`).

## Results

**Temperature variable.** T_EXT fits clearly better than T_CHAMBER, the firmware's
regressor: rms 0.60 against 0.70 % unclipped, and the chamber fit lands on α −0.29.
The lag scan (τ 0…1800 s) leaves the rms flat to within 0.013 %, so τ is not identified.
T_AFE is collinear with T_EXT (r 0.994), so an AFE term cannot be separated here.

**Joint fit (clipped, T_EXT linear):** α **+0.98**, β **+2604 ppm/K**, rms 0.19 %.
The 30-min block bootstrap gives α 0.70…1.62 and β 2360…3150 ppm/K (95 %), with
**corr(α, β) = +0.97**. Only the pair is identified, not each value. Residual lag-1
autocorrelation is 0.90, so the effective n is far below 857.

**Capillary law, zero free temperature terms:** rms **0.19 %**, the same as the fitted
β, with α +0.90. Fitted separately to each half it gives α 0.68 (night) and 0.70 (day).
The linear model gives 1.65 and 0.73.

**Cross-prediction (night 18:40–07:00 ↔ day 07:00–11:23), K carried from the fitting half:**

| model | N→D rms / offset | D→N rms / offset |
|---|---|---|
| linear, α free | 0.52 % / +0.35 | 0.36 % / −0.30 |
| linear, α = 1 | 0.93 % / +0.94 | 0.38 % / −0.32 |
| linear, α = 0.4 | 1.42 % / +1.48 | 0.35 % / −0.26 |
| **T^0.75, α = 1** | **0.26 % / +0.005** | **0.18 % / −0.000** |
| T^0.75, α = 0.8 | 0.29 % / +0.22 | 0.30 % / −0.22 |
| T^0.75, α = 0 | 1.19 % / +1.01 | 1.08 % / −1.04 |
| no temperature term, α = 1 | 3.75 % / −4.00 | 3.18 % / +3.30 |

The physics law with full Dalton dilution carries K across the two halves with no
offset in either direction, and only K is fitted. The linear tempco extrapolates
from night to day with a 0.35–1.5 % offset.

**Corrected output** (T^0.75, α = 0.8, K 101 333 nA from all clean rows): hourly
medians **20.89–21.04 %vol**, minute sd 0.038 %vol. The published hourly medians
over the same rows run 20.39–21.42.

## How narrowly to read this

- **One run and one excursion.** The day half has r(T_EXT, p_w/P) = 0.91, so the
  morning's humidity and temperature moved together. The night half barely moved
  p_w (1.20–1.34 %). α stays weakly identified: 0.7–1.6 is what the bootstrap
  supports. α = 1 is favoured by the cross-prediction offset, not by the rms.
- The 0.75 exponent is assumed, not fitted. Its agreement with the data is
  evidence for it, not proof: a linear β around 2500 ppm/K is numerically close
  over 13–36 °C.
- T_EXT reads the enclosure wall. In the morning sun the wall probably leads the
  electrolyte, and τ is unconstrained.
- The whole run is ≤ 36 °C and mostly heater-light. It says nothing about the
  60–80 °C pile case.
- **Firmware consequence (proposal):** `o2p_gas_temperature()` still feeds
  chamber-else-tip into the tempco (`main.c:628`, `:1187`), and chamber is the worse
  regressor here. Writing a `TEMPCO` register would therefore apply a T_EXT-derived
  coefficient to the wrong sensor. The useful change is to regress on T_EXT, and
  better still the `(T_K/T_cal)^0.75` form with `DIL_ALPHA` 1.0, which is what the
  probe already runs.

## Against the datasheet (added 2026-09-13 afternoon, Fab's question)

Source: DS-0637 Issue 2 p.2, "%20 °C Output vs Temperature". **The canonical
digitisation is the 2026-09-11 one at `~/codex-reviews/ds0637-tempco-dsdig/out-issue{1,2}/`**
(later ports: `~/codex-reviews/dsdig-xy-engine/{port,postfix}-sensor*`). This section
first re-ran `dsdig digitize-output-vs-temperature` (worktree
`~/dev/pv/ee/dsdig-sensor-tempco`, xy-engine 7895d9d) because the search for the
existing output skipped `~/codex-reviews`. Checked afterwards: the Issue 2 re-run
matches all three 09-11 copies **exactly** (max difference 0.000 % on mean, +3σ and −3σ
at every 5 K sample), so every number below holds for the canonical curve.
Status **overlay-review-required, human_verified false**. The
overlay tracks all three traces by eye, with axis residuals of 0.29/0.24 px and 2 of
1193 band-order violations, but agent review cannot verify it. Issue 1's run was
**refused** (±3σ bounds traced in only 22 % of columns), so only its mean was ever
compared, on 09-11. Outputs are in `bench-logs/2026-09-13-outdoor-fit/ds0637/`, and
the comparison is `compare_datasheet.py` → `compare_datasheet.out`.

Over this run's T_EXT span (12.86 → 35.97 °C), as the output ratio converted to ppm/K:

| source | I(36)/I(13) | ppm/K |
|---|--:|--:|
| DS-0637 mean | 1.0530 | **+2235** |
| DS-0637 ±3σ traces | 1.0500 / 1.0557 | +2111 / +2344 |
| capillary (T_K)^0.75 | 1.0600 | +2522 |
| outdoor fit, linear on T_EXT, α free | — | **+2604** (95 % 2360–3150) |
| outdoor fit, α fixed 0.5 / 0.75 / 1.0 | — | +2226 / +2435 / +2646 |

The measured slope sits **about 15 % above the vendor mean**, but not significantly:
the bootstrap interval reaches 2360, and the gap is exactly what the α–β trade (corr
0.97) moves. At α = 0.5 the fit reproduces the vendor number. Two terms belong in the
measured value and not in the vendor's: the AFE (R_TIA), ~+230 ppm/K on 09-11 but not
established, and whatever the T_EXT-to-electrolyte lag does during the sun ramp.

**Using the vendor mean directly as g(T)**, with no temperature parameter:

| g(T) | α | all rms | night→day rms / offset | day→night rms / offset |
|---|--:|--:|--:|--:|
| DS mean | free → 0.66 | 0.199 % | 0.32 / −0.09 | 0.39 / −0.33 |
| DS mean | 0.8 | 0.212 % | **0.31 / −0.06** | **0.18 / +0.03** |
| DS mean | 1.0 | 0.268 % | 0.50 / −0.26 | 0.30 / +0.24 |
| (T_K)^0.75 | 1.0 | 0.19 % | **0.26 / +0.005** | **0.18 / −0.000** |

**This run cannot tell the two apart.** The vendor curve with α ≈ 0.8 and the capillary law
with α = 1 cross-predict equally well. The 12 % slope difference between them is absorbed
by α, the same collinearity as §Results. The ±3σ traces used as g(T) do worse (0.28–0.63 %
out of sample), which says the vendor's own spread is wider than this cell's behaviour here.

## FW 0x001E and its review (added 2026-09-13 afternoon)

Implemented as `82aa9e9` (law on T_EXT, fallback chamber-else-tip), flashed
14:3x CEST through the keeper: BUILD_ID 0x4B6AD5BD (b6ad5bd), every per-probe
constant and CONFIG_CRC 0xE25C unchanged (`bench-logs/2026-09-13-outdoor-fit/flash-0x001E.log`).

Codex xhigh review, `~/codex-reviews/o2p-cell-t-law-82aa9e9/review.log`
(access proven: live VM query, sgxsensortech.com title visible in the attached
Chrome). Findings, each checked against source:

1. **P1** — an old *whole* tempco (e.g. 2859 ppm/K) still in a record now
   double-counts on top of the law, 1.157× at 75 °C (true 5.00 → ~4.34 %vol).
   Nothing detects it; layout version 8 is unchanged, so no migration runs.
   **Probe 3 holds 0 — not affected.** Needs a decision: persisted model
   version / migration that zeroes TEMPCO, or accept documented risk.
2. **P2** — `tmp117.c:269` clears ext presence after 3 failed reads, so a
   disconnected T_EXT lets an air point store a chamber reference that the
   conversion later measures against T_EXT. Verified. Needs the calibration's
   sensor identity persisted (layout change).
3. **P2** — the T_EXT ↔ board fallback moves the published number without
   provenance (4 K ≈ −0.05 %vol at 5 %vol; 30 K ≈ −0.32). Design choice:
   refuse O2_COMP instead of falling back on a probe with T_EXT, or publish
   provenance somewhere.
4. **P2, fixed** in the follow-up commit — the fallback admitted a stale tip.

Survived: gain/sentinel arithmetic, float range, the heater refactor being
behaviour-identical, bridge expiry (note: frozen reading usable ~12 s, not
10), the two changed tests not being mutes.

### Air point on 0x001E, and what the old point said first

Taken 14:3x CEST, outdoors in open air, heater near idle (duty 0–3 %), after
the post-flash settle (`bench-logs/2026-09-13-outdoor-fit/cal-air-0x001E.log`):
cell 103.00 µA, 120 s spread 0.11 %, T_EXT creeping 36.7 → 37.4 °C
(~0.05 K/min). Stored: CAL_AIR_NA **102 966 nA**, CAL_TEMP **37.71 °C** (T_EXT —
chamber read 39.14), CAL_AIR_FRAC 0.20472, CONFIG_CRC 0xAB3D, K **449 513 nA**,
O2_COMP 20.95 %vol right after. 0x001E's gate stored the cell-side reference,
as designed.

**The minutes between flash and recalibration are a free two-point check**, and it
does not come out in the law's favour. Same cell current (~103.0 µA), same
temperature (~37–38 °C T_EXT), same RH (~30 %):

| image, air point | published | vs 20.946 |
|---|--:|--:|
| 0x001A (no temperature term), 09-12 point @ 21.54 °C | 21.47–21.51 %vol | **+0.55** |
| 0x001E (law), same 09-12 point | 20.69–20.70 %vol | **−0.26** |
| 0x001E, new point @ 37.71 °C | 20.95–20.97 %vol | (by construction) |

Hand arithmetic reproduces the middle row (20.68). Read as a slope from the 09-12
evening point to now, the effective dependence is ~**+1700 ppm/K** over 16 K, while
the law applies +2520 and the DS-0637 mean +2235. The morning fit said +2600 for
13–36 °C on the same probe. Candidates, none tested: the 09-12 point was taken
1.5 h after the C9 repair on a board that had just been reworked and cooled; its
CAL_TEMP is the chamber (the T_EXT reference would make the gap slightly *larger*);
T_EXT on the sun-heated housing leads the electrolyte, so the 37 °C side
overstates the cell's temperature; the pressure day-to-day is unknown (Open-Meteo
says ~0.2 %). **One two-point comparison across a day, sun-loaded, not an
isothermal measurement** — enough to say the law is not yet shown to be right to
better than ~1 % at 37 °C, not enough to replace it.

Consequence for the firmware change: the physics law and the vendor mean are
**equivalent on this evidence**. The law is the one with no digitisation behind it that
still needs human verification, and it extends past 60 °C, where the vendor chart
ends. Separating them needs an excursion where p_w stays flat while T moves ≥ 20 K, or
an isothermal humidity step.
