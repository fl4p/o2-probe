# Cell-to-tip coupling, measured in situ — 2026-09-14

**Question.** Fab, 09:17: the o2-probe's cell temperature sits ~0.5 K above the
soil probes laid beside it — is that expected, and do we need more heat?

**Answer: expected, and more heat via the gradient floor does not fix it.**
`k` is NOT pinned by this session — two step runs were both rejected by their
own guards — but the decision is robust across the whole range `k` could
plausibly take.

## What the law was doing (measured, VM + live registers)

`HEATER_LAW` (0x0008) = 0x0004 `LAW_DEW`, no flags, all day. RH consent
0x0048 = 0x9C07, tip setpoint 0x0049 = 0x8000 (disarmed), override 0x0060 = 0.
So the autonomous dew+floor slot was genuinely in command.

The **gradient floor was the binding term**, not the dew law: tip − cell held
2.03–2.14 K against `O2P_HEATER_FLOOR_DELTA_K100` = 2.00 K, at 0–6 % duty,
every quiet sample. The dew law was asking for nothing, because the cell-side
margin was already over its 4.00 K target.

**The published dew margin is tip-referenced.** `psychro.c:73` computes
`T_tip − Td`, so `gas_dew_margin_k` overstates the margin at the surface the
law actually protects by the full gradient — every sample, not occasionally:

| 09-12 | published (tip) | cell-side (computed) |
|---|---:|---:|
| 22:40 | 6.62 K | 6.32 K |
| 23:50 | 7.86 K | 5.10 K |

Observability defect, same family as `DEW-MARGIN-IS-BLIND.md`: the number on
the dashboard is not the number the law regulates. Fix is a read-only register
plus a codec field — no config layout bump.

## Coupling: three estimates, none trusted

`cell_rise_over_ambient = k·delta/(1−k)`. Ambient reference is the two SMT100
soil probes beside the probe; this board has no ambient sensor, which is why
the floor is a gradient at all (`heater_ctl.h:487-499`).

| window | gradient | rise | k | verdict |
|---|---:|---:|---:|---|
| 09:05–09:50 quiet, pre-sun, floor only, OUTDOORS | 2.05 K | 0.33 K | **0.14** | probes agreed to 0.01 K, but wind-exposed |
| 10:16–10:52 step, tip 30 °C, outdoors | 3.88 K | 2.28 K | 0.371 | REJECTED — sun |
| 11:28–12:08 step, tip 30 °C, indoors | 5.64 K | 1.93 K | 0.255 | REJECTED — ambient span 109 % of rise |
| **14:40–15:20 step, tip 30 °C, INDOORS, settled** | **5.01 K** | **2.08 K** | **0.293** | **ACCEPTED — all guards pass** |

**The accepted run.** Ambient pinned at 23.02 °C, span 0.07 K against a 2.08 K
rise (3 %); the cell moved 1.03 K, an order more than ambient did, so the rise
is a response and not a slide; soil probes agreed to within 0.20 K throughout.
The cell asymptoted flat at 25.10 °C for the last 12 minutes. Holding the tip
at 30 °C cost 0–14 % duty.

**k depends on the environment, and that is the real result.** 0.293 in still
indoor air against 0.14 outdoors, wind-exposed, at the same 2 K floor gradient.
Wind strips the cell's rise for a given gradient. Both are honest measurements
of different plants, and **neither is the windrow.** Note also that 0.293 in
still air is roughly 3x the ~11 % still-bench-air figure quoted in
`heater_ctl.h`; that discrepancy is unexplained and should not be smoothed over
— the configurations may differ (this article's assembly vs. the bare board of
2026-09-12).

**Why the outdoor run failed.** Direct sun at 09:54 (Fab confirmed) moved the
cell 21.4 → 27.8 °C in five minutes *with the gradient pinned at 2.0 K* — the
whole assembly heated from outside, not by the heater. It drove the two soil
probes 1.9 K apart, so "ambient" stopped being a single number. The step began
at 10:16 while that was still decaying, which is why the cell appeared to fall
back under a held tip.

**Why the indoor run failed.** The probes came indoors warm and shed ~2 K
during the run while the cell stayed nearly flat (cell span 1.34 K against
ambient span 2.11 K). The apparent rise grew because ambient slid underneath a
cell that had not reached steady state — not because the cell warmed.

**Endpoint drift laundered this.** The first summary reported −0.33 K end to
end because a ~1.2 K climb and a ~1.5 K fall cancelled. `analyze()` now reports
the ambient SPAN, which cannot cancel, plus the cell's own span, and rejects a
run where the cell moved less than half what ambient did.

## The decision, which does not need k pinned

Across the full plausible range k = 0.14–0.37:

| | k=0.14 (outdoors, wind) | **k=0.293 (still air, measured)** | k=0.37 |
|---|---:|---:|---:|
| floor delta 2.00 K (today) | 0.33 K | **0.83 K** | 1.18 K |
| floor delta 4.00 K (`DT_MAX_K`, the whole envelope) | 0.65 K | **1.66 K** | 2.35 K |

Doubling the floor delta buys **+0.3 to +1.2 K**, for a reflash plus continuous
duty in a self-heating pile. In saturated pore gas, where Td = ambient and the
floor's gradient is the entire protection, no legal gradient reaches a 4 K
margin. That is a thermal-path question, not a constant to tune.

**Solar gain is the dominant thermal input on this article as placed**: 6 K in
five minutes, against 0.65 K of heater authority at the full envelope. The
heater does not decide this cell's temperature outdoors.

## Not observed

No condensation risk has been measured in this placement. On clean nights the
cell-side margin decays gently 8.2 → ~5.0 K and never approaches the 4.00 K
target. The 2.61 K minimum on 09-12 22:50 is a SINGLE sample in which chamber T
spiked 3.5 K and returned — a disturbance, not a nightly dip. The −35.51 K
(09-11) and −19.59 K (09-13) minima are bench artifacts (steam bath, AFE
damage), not weather. **The windrow case — saturated pore gas — remains
untested, and it is the case where k decides whether the heater can do
anything at all.**

## Method

`farming/tech/bench/o2p_coupling_step.py`. Parks the stored tip loop at an
absolute setpoint, which outranks dew+floor and which `heater_ctl.c:977-983`
regulates WITHOUT `dew_ceiling_c100()` — so the setpoint is honoured in full
rather than clamped to cell + `DT_MAX_K`. Verified: tip reached 30.0 °C in 63 s
and `HEATER_LAW` read 3 (`TIP_AUTO`) throughout.

Nothing was committed in either run. `CONFIG_CRC` 0xAB3D before and after both,
so the flash record — including the air point and the RH consent — was never
touched, and any reset would have landed in the committed dew-law state.
Restore (consent 0x004A cleared first, then the 0x8000 sentinel into 0x0049)
runs in a `finally`, is readback-verified, and was confirmed independently
through the keeper after each run.

## Open

- **Falsify the k model against the floor.** k = 0.293 predicts that the
  gradient floor, back in command at 2.00 K indoors, should settle the cell
  **0.83 K** over ambient. That is a free prediction and a real test of the
  model: watch the relaxation after the step and check it. UNTESTED as of
  writing — the cell was still shedding the 30 °C step.
- **The windrow plant is still unmeasured**, and it is the only one that
  matters for the deployed question. Buried in a self-heating pile the cell is
  heated from OUTSIDE and the floor runs continuously
  (`heater_ctl.h:501-508`); neither indoor still air nor a wind-exposed bench
  predicts it.
- Publish the cell-side dew margin as its own channel (see above).
- `analyze()` rejects a run whose per-sample probe spread is unrecorded; the
  two runs here predate that column, which is why both now return no k.
