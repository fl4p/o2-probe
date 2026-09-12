# Thermal relaxation: ambient, θ and τ for the Rev A probe — 2026-09-12/13

Measured overnight on the bench probe, cell #1 fitted, board in its enclosure
with the membrane. Tool: `farming/tech/bench/o2p_theta_probe.py` (commit
`dae2120`), raw samples in `theta-20260912.csv` (209 rows, 3 cycles).

**Why.** The tip loop holds an ABSOLUTE setpoint. Fab asked for a constant +2 K
over ambient, and Rev A cannot see ambient while heating — tip and chamber are
one thermal node (`DT_MAX_K` is documented inert for exactly this reason). His
proposal: cut the heater and read ambient off the cool-down. With the heater
off, `C dT/dt = −(T − T_amb)/θ`, so **the decay asymptote is ambient** and θ
never enters that fit; θ then comes from the steady state recorded just before
the cut.

## Results

| cyc | T_amb (fit) | τ | θ | tip rise | steady duty | rms |
|---|---|---|---|---|---|---|
| 1 | 14.581 °C | 167.4 s | 1.099 K/%duty | 2.957 K | 2.69 % | 0.019 K |
| 2 | 14.413 °C | 152.1 s | 0.816 K/%duty | 3.110 K | 3.81 % | 0.027 K |
| 3 | 14.290 °C | 147.3 s | 0.849 K/%duty | 3.214 K | 3.79 % | 0.027 K |

Residuals of 19–27 mK against a TMP117 LSB of 7.8 mK — the single-exponential
tail model fits about as well as the sensor allows.

**Cycle 1 is contaminated and should not be averaged in.** Its steady window
caught the cell still soaking down from the preceding long hold, and its duty
average (2.69 %, spread 6.02 pp over 10 samples) is not a steady state. Cycles
2 and 3 agree closely and are the result:

- **θ = 0.83 ± 0.02 K per % duty** (bench, still air, enclosure fitted)
- **τ = 150 ± 3 s**

θ in K/W and C in J/K need the ring's power at 100 % duty, which is **not
measured**. At an assumed 1 W: θ ≈ 83 K/W, C = τ/θ ≈ 1.8 J/K — a small heated
mass, consistent with the tip ring being thermally separate from the stem.
Measure the ring's resistance and rail before quoting either number.

## The absolute setpoint drifted, exactly as predicted

`TIP_SETPOINT` held 17.50 °C throughout. Ambient fell **14.581 → 14.290 °C**
over the 45-minute run — an ordinary overnight room — so the commanded margin
grew:

| | cycle 1 | cycle 2 | cycle 3 |
|---|---|---|---|
| achieved rise | 2.957 K | 3.110 K | 3.214 K |

**The 2.0 K that was set at 23:00 was 3.2 K forty-five minutes later**, from
nothing but the room cooling. This is the direct demonstration that an absolute
setpoint is the wrong law; it is not an argument, it is a measurement.

## The cell-side TMP117 is a usable ambient reference

This is the operationally important finding. `T_EXT` sits close to the fitted
ambient and does so repeatably:

| cyc | cell − T_amb, while heated | cell − T_amb, end of cut | coupling |
|---|---|---|---|
| 1 | +0.298 K | −0.261 K | 18.9 % |
| 2 | **+0.101 K** | **−0.243 K** | **11.1 %** |
| 3 | **+0.098 K** | **−0.240 K** | **10.5 %** |

Cycles 2 and 3 agree to **3 mK** on the heated offset and **3 mK** on the
settled one. Cycle 1 is again the soak-down outlier.

Two numbers fall out, and they are consistent with each other:

1. **The fitted asymptote is ~0.24 K above where the cell settles.** This is
   the self-heating term the method cannot remove: with the heater off the
   plant relaxes to `T_amb + P_idle·θ`, not to `T_amb`. It is constant to
   ±3 mK across cycles, therefore calibratable — but it is not zero, and a
   fitted "ambient" must not be quoted as absolute room temperature.
2. **The cell is ~11 % coupled to the tip heater.** A 3.1 K tip rise lifts the
   cell 0.34 K (0.27 K after subtracting the 0.07 K the room fell during the
   cut). The two views close: `0.101 + 0.243 = 0.344 K`.

### Consequence for a `T_EXT + offset` law

A law of the form `setpoint = T_EXT + Δ` has a **gain error from that 11 %
coupling**: raising the tip raises `T_EXT`, which raises the setpoint. It
converges rather than running away —

    achieved ≈ Δ / (1 − k),  k ≈ 0.11   →   Δ = 2.0 K gives ≈ 2.25 K

— so a commanded 2 K lands at about 2.25 K. Scale the offset by `(1 − k)`
(i.e. write 1.78 K to get 2.0 K) or simply accept a 12 % high margin. Either
way it is bounded, unlike the absolute setpoint's unbounded drift with ambient.

**This makes the +2 K law implementable on Rev A today**, without the
relaxation cycles in the control path at all: `T_EXT` is the reference, and the
heater-off measurement becomes the occasional calibration that validates it
rather than a required step.

## Extrapolating to a windrow — bounded at one end only

θ = 83 K/W (assumed P) is **still air inside an enclosure**, the most
favourable case. Buried in moist compost the coupling is far better and θ far
smaller. If a buried probe reaches θ ≈ 2–5 K/W, a 1 W ring buys 2–5 K, so:

- **+2 K is achievable buried.** 
- **The dew law's 4 K is marginal at best**, and at the top of that range the
  loop would sit near 100 % duty permanently.

This is an inference from one end of the range. The buried θ is unmeasured, and
the tool exists to measure it: bury the probe in damp compost and run the same
three cycles. That single number decides whether the margin target is 2 K or
something smaller, and whether the power budget or the cell rating is the
binding constraint.

## Method notes

- **The cuts were genuinely free**: duty read exactly 0.00 in all 181
  off-phase samples, verified from the CSV rather than assumed from the write.
- The fit discards the first 0.5 τ. The plant is multi-mass — tip, chamber,
  cell and stem — and only the tail is one exponential.
- The fit is linear in (A, B) once τ is fixed, so it searches τ on a log grid
  and solves the 2×2 normal equations exactly: no scipy, no local minima.
  Checked against a synthetic exponential before touching hardware — recovers
  `T_amb` to 1.7 mK and τ to 0.4 % under ±1 LSB dither, returns `None` for
  n < 4, and does not invent an asymptote from flat data.
- **Steady duty is the noisy quantity**, not temperature: spreads of 6–10
  percentage points against means of 2.7–3.8 %. The loop is nearly bang-bang at
  this demand, so θ's uncertainty is dominated by the duty average, not by the
  fit. Lengthen `--pre-s` if θ needs to be tighter than ±2 %.
- The heater was re-armed and **verified** after every cut; `TIP_CONSENT` read
  back non-zero all three times. Nothing was committed, so the flash record
  kept its setpoint and consent throughout.

## Open

- Ring power at 100 % duty — the missing input for θ in K/W and C in J/K.
- Buried θ, per above.
- Whether τ's downward trend (167 → 152 → 147 s) is real or fit noise.
- The dew law's 79 °C tip ceiling against the cell's 60 °C rating still stands
  as a separate open item; see the heater standing-order memory.
