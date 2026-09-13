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

## Outcome: the two laws were combined, not chosen between (FW 0x0016)

Fab, 2026-09-13: *"should we combine +2k and the 4k dew margin?"* then *"lets
do it then"*, and on the cell's rating, *"ignore the rating, we will use it out
of spec"* - so the 79 C ceiling against the 60 C cell stops being an open
question and becomes a deliberate out-of-spec operating point.

**They were mutually exclusive before this.** `heater_ctl.c` selected one law
per cycle - override > stored tip setpoint > dew > RH - so arming a +2 K
setpoint would have SWITCHED THE DEW LAW OFF rather than adding to it. That is
what the bench probe has been doing all night at its 17.50 C setpoint.

Now the autonomous slot drives **`max(dew_duty, floor_duty)`**. Both laws are
lower bounds on how hard the ring must drive, so the binding one wins and
neither can turn the other down. Each keeps its own integrator, because the two
run in the SAME cycle and the mode tag can only arbitrate between laws that
take turns.

### The floor is a gradient, not "+2 K over ambient"

Worth stating plainly, because the request and the implementation are not the
same sentence. **This board has no ambient sensor.** T_EXT is simultaneously
the closest thing to ambient and the dew law's reference surface, so
"cell minus ambient" taken from it is identically zero. What two sensors can
state is a gradient: hold the tip 2.00 K above the cell side, i.e. never stop
pumping heat outward past the membrane.

What that buys, using this document's own numbers: at the measured **11 %
coupling** a 2 K gradient lifts the cell only ~0.22 K over true ambient in
still bench air; the bath data (cell gains ~0.4 K per K of tip) would make it
~0.8 K. **So the floor is not a 2 K dew margin and must not be quoted as one.**
It is a guarantee that heat never stops flowing outward.

### What it actually covers

The dew law's failure mode, from its own header: an SHT45 wetted and then
drying reads a falsely LOW humidity, so the computed dew point drops, the
margin looks generous, and **the law asks for zero duty while the membrane
condenses**. No interlock fires - every reading is valid. The law is being
lied to, and nothing inside it can tell.

The floor's value is that its sensor chain is DISJOINT from the one that can
lie: two TMP117s, no humidity, no Magnus form, no wettable sensing surface.

### The cost, and the monotonicity that had to be given up

**It runs continuously in a self-heating pile**, not only in wet gas: a pile
hotter than the probe heats the cell from outside, the tip lags, and the floor
demands duty to get back ahead. Bounded by the same 79 C ceiling and by
HEATER_MAX_DUTY - and in saturated pore gas the dew law was going to bind
anyway - but a buried power budget cannot be taken from the dew law alone.

**The combined law is not monotonic in cell temperature**, and cannot be: a
cell above the tip is the dew law's best case and the floor's worst. The
guarantee that survives is that each law is monotonic in its own error and
max() is monotonic in each argument; the test that asserted the old, stronger
property was rescoped to the dew law and the floor got its own.

### The calibration is not at risk from this reflash

Fab, 2026-09-13: *"we can't loose our calibration every re-flash."* Checked
rather than assumed:

- Config lives in flash pages 62-63, OUTSIDE the run and staging slots
  (`flash_map.h`), and `update_target.c` refuses any page outside staging. An
  OTA install cannot reach it.
- The only path that has ever discarded an air point is
  `config_migrate.c`, entered when `CONFIG_LAYOUT_VERSION` changes - and since
  v5 even that carries the air point forward.

So this change was built with **compile-time constants rather than holding
registers**. It bumps FW_VERSION 0x0015 -> 0x0016 and does NOT touch the
record layout, so K = 437977 survives the install. Cost: **+164 bytes of flash**
(86.1 % of the 52 KiB slot) and +4 bytes of RAM.

The old standing note "the O2 config is lost on every reflash" was retired the
same day as superseded: it generalised a single 2026-09-08 event into a
property of all reflashes, and the flash map does not support that.

**Not flashed.** The image builds and all 376 host tests pass; installing it on
probe 3 is a probe state change and waits for Fab's word.

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
- ~~The dew law's 79 °C tip ceiling against the cell's 60 °C rating.~~ CLOSED
  2026-09-13, Fab: *"ignore the rating, we will use it out of spec."* The
  ceiling stands as written; the cell is knowingly operated past its rating.
- ~~Installing FW 0x0016 on probe 3.~~ DONE 2026-09-13 on Fab's "flash it":
  46 056 B, CRC `1EAF8F3B`, 111 s, installed and verified through the keeper.
  **The calibration survived, measured rather than argued** — `CONFIG_CRC`
  bit-identical at 0xD1AA and CAL_AIR_NA still 101 327 nA across the install,
  with every other per-probe constant unmoved (`tech/bench/o2p_flash.py` in
  farming does the before/after comparison).
  Two things that install taught, both since fixed:
  - the image was stamped `8AA6133D` — a DIRTY tree at `aa6133d`, i.e. no
    reproducible provenance. A clean rebuild differs by exactly 12 bytes, the
    build id at three sites.
  - `--expect-build-id` could never have verified it: bit 30 is set at runtime
    by `regmap.c` on an `O2P_DEBUG_ENABLE=1` image and never stamped by the
    builder, so the bare equality in `o2p_update.py` failed on every image this
    probe can run (fixed in `c295364`).
- **FW 0x0016 is superseded by 0x0017** (`8bb8802`, the runaway latch firing on
  its own cool-down — seen live as `HEATER_BLOCK = RUNAWAY | BLIND` minutes
  after this install). Whatever is flashed next should be 0x0017 or later,
  built clean.
- The gradient floor and the dew law are **dormant while a stored tip setpoint
  is armed** — the precedence chain puts the setpoint first. Returning 0x0049
  to its sentinel is what puts the combined law in command.
