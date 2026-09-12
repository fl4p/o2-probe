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

### Ring power, from the netlist — and θ in real units

The ring is **RH1 ∥ RH2, 280 R 1 W each = 140 Ω**, fed from `/+12V_SW` and
switched to ground by Q2 (AO3400A, whose R_DS(on) is negligible against 140 Ω).
J5 is the `HEATED MEMBRANE RING` solder land. At the measured `VIN_MON` of
**13.092 V**:

    I = 93.5 mA        P_max = V²/R = 1.224 W

**Independent confirmation of the 140 Ω**: at 12.000 V that ring draws
85.7 mA, and `heater_ctl.h` describes the load as "86 mA" — an exact match to a
number written from the schematic, not from this calculation.

So:

| | cycle 2 | cycle 3 |
|---|---|---|
| **θ** | **66.6 K/W** | **69.3 K/W** |
| **C = τ/θ** | 2.28 J/K | 2.13 J/K |

**θ = 68 ± 2 K/W, C = 2.2 ± 0.1 J/K** for the ring-to-ambient path in still
air, enclosure fitted. P scales with VIN², so both move with the supply.

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

## This closes a gap the firmware names as open

`heater_ctl.h:24-31` says, in as many words:

> THE PLANT GAIN IS UNKNOWN. THERMAL-BARRIER.md:5-9 gives 98 K/W (interval
> 91-102, engineering bound 90-110 K/W) for the bare-PCB transverse path, and
> :18 says plainly that this "is for PCB conduction only. It is not the
> ring-to-ambient" path — which is the one that actually sets how many kelvin
> a watt buys in wet pore gas.

**That ring-to-ambient path is what the 68 K/W above measures** — in still
bench air, which is the easy end, but it is the first number of that kind this
project has. The gains in `heater_ctl.h` are described as "conservative
starting points, NOT design values … exposed as holding registers precisely
because they cannot be known until the loop runs on hardware". The loop has now
run on hardware.

## RETRACTION: "the dew law's 4 K is unreachable" was not supported

Stated on 2026-09-12 evening, before this measurement: that a <1 W heater could
not hold 4 K in a buried probe, so the dew law would pin at 100 % duty forever.
**That rested on a guessed buried conductance of 0.2–0.5 W/K, and nothing
measured.** The bench number gives it no support: 1.224 W at 68 K/W buys 83 K
in still air, and the buried value is simply unknown — somewhere between that
and the couple of K/W the guess assumed. The claim should not have been made
with the confidence it was.

What can honestly be said: **buried θ is the one number that decides the
thermal design**, and it is one bucket of damp compost and three cycles of this
tool away.

## And PLAN.md already argued against a fixed +2 K

Worth surfacing before any fixed-offset law is built, because it is the
project's own prior decision (`heater_ctl.h:14-18`, quoting PLAN.md:300-302):

> "+2 K gives only ~90-91 % RH on saturated gas; 85 % needs ~3.1-3.7 K at
> 40-65 C — design the thermal path for a 0-4 K dT range, not a fixed 2 K." A
> fixed offset that is right at 40 C is wrong at 65 C, and the pile spans both.

An independent check of that arithmetic agrees: 2 K of superheat leaves local
RH at ~92 % at 70 °C and ~89 % at 20 °C. So a fixed 2 K does keep liquid water
off the membrane, but it does **not** reach the 85 % the plan targets, and the
required ΔT genuinely does rise with temperature. **The dew-margin law's 4 K is
the design intent, not an arbitrary number** — it sits inside the 3.1–3.7 K
band PLAN.md asks for.

This does not settle 2 K vs 4 K; it means the choice is between "keep liquid
water off" (2 K, cheap, achievable) and "hold the RH the plan specified"
(3–4 K, cost unknown until buried θ is measured). That is Fab's call, and it
should be made with PLAN.md's reasoning in front of it rather than around it.

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

- **Buried θ** — the one number that decides the thermal design.
- Whether τ's downward trend (167 → 152 → 147 s) is real or fit noise.
- The dew law's 79 °C tip ceiling against the cell's 60 °C rating still stands
  as a separate open item; see the heater standing-order memory.
