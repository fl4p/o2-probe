# Measuring the probe's in-pile thermal resistance

**One number decides the battery and the panel, and nobody has measured it:**
θ, the thermal resistance from the heated tip to the surrounding medium, in
K/W. `compostlab/o2-probe/POWER.md` §3.2 sizes the whole power system off an
*assumed* heater duty; this procedure replaces that assumption with a
measurement. It is deliberately cheap — the method was proven on the bench on
2026-09-04 and takes about an hour in the field.

## 1. What is already known

**Bench reference, 2026-09-04, first article, no ring fitted, still air.** A
fixed 4.00 % duty step, held for 300 s:

```
baseline 26.02 C  ->  settled 30.06 C     DT = 4.04 K
P = duty * VIN^2 / R = 0.0400 * 11.96^2 / 140 = 40.9 mW
theta = 4.04 K / 40.9 mW = 98 K/W          tau ~ 77 s
```

That is the *upper* bound on θ — still air is the worst coupling the probe will
ever see. A potted board in wet compost will be far lower, and that is the whole
question.

Note τ = θ·C implies C ≈ 0.79 J/K, well under the ~7 J/K of the whole board.
The heated volume is local to the tip, as the transverse barrier intends
(`THERMAL-BARRIER.md`). Because τ scales with θ, a better-coupled probe settles
*faster*, so the field measurement is not slower than the bench one.

## 2. Why θ decides the battery

The target rise is set by the cell's 90 %RH rating and the 85 %RH setpoint.
Taking a saturated pile from 100 %RH to 85 %RH at constant vapour pressure needs

```
DT = ln(1/0.85) / (L/(R*T^2))  =  3.3 K at 60 C,  2.7 K at 25 C
```

so **ΔT ≈ 3 K** is the design point. With `P = ΔT/θ` and the probe's 40 mW idle,
POWER.md's own sizing rules (7-day autonomy, AGM at 50 % DoD, 0.7 cold derate,
plus the controller's 2.9 Wh/d) give `Ah = E_day * 1.667`. That formula
reproduces POWER.md's published table exactly, so the mapping below is on the
same footing as the numbers already in that document:

| θ (K/W) | duty for +3 K | load | energy/day | needed | nearest pack | panel |
|---:|---:|---:|---:|---:|---:|---:|
| 98 *(bench, still air)* | 3.0 % | 71 mW | 4.6 Wh | 7.7 Ah | 12 V 8 Ah | ~17 Wp |
| 50 | 5.9 % | 100 mW | 5.3 Wh | 8.8 Ah | 12 V 10 Ah | ~20 Wp |
| 20 | 14.7 % | 190 mW | 7.5 Wh | 12.4 Ah | 12 V 15 Ah | ~30 Wp |
| **10** | **29.4 %** | **340 mW** | **11.1 Wh** | **18.4 Ah** | **12 V 20 Ah** | **~40 Wp** |
| 5 | 58.7 % | 640 mW | 18.3 Wh | 30.4 Ah | 12 V 30 Ah | ~60 Wp |
| 3.4 | 86.4 % | 922 mW | 25.0 Wh | 41.7 Ah | 12 V 45 Ah | ~90 Wp |

Computed with `P_max = VIN^2/R = 11.96^2/140 = 1.022 W` from the measured rail.
POWER.md's own rows use a nominal 12.00 V (its 1068 mW row is 40 mW idle plus
12.00^2/140); feeding 12.00 V into the formula above returns 3.9/10.0/16.1/
28.4 Wh and 6.4/16.7/26.9/47.3 Ah against its published 3.8/10.0/16.2/28.5 Wh
and 7/20/30/50 Ah, i.e. the same table to rounding. The mapping is therefore on
POWER.md's own footing, not a parallel calculation.

The bolded row is what POWER.md's recommended 20 Ah pack implicitly assumes.
**A single measurement moves the recommendation by up to 4x in either
direction.** If θ is nearer 50 K/W the pack and panel are heavily over-bought;
if it is nearer 5 K/W they are under-bought.

## 3. Method

A fixed-duty step response. Two things make the field case harder than the
bench, and both have a fix:

**The pile drifts.** An active pile moves degrees over hours, which contaminates
a single step. So run a **square wave**: at least three cycles of `D` on / `0`
off, each half ≥ 5τ, and take mean(on asymptotes) − mean(off asymptotes). A
linear drift cancels to first order. Fit a drift term as well if the residual
looks sloped.

**There is no unheated reference on the board.** U10 (TMP117, tip) and U12
(SHT45, chamber) sit 6.6 mm apart on the same copper and are one thermal node —
`T_TIP − T_CHAMBER` is structurally ~0 and must **not** be used as ΔT (see
`FAB-READINESS.md`). ΔT is the *change in* `T_TIP` across the step, not a
difference between two sensors. If a neighbouring pile sensor is available, log
it too and subtract it as the drift reference.

## 4. Field procedure (Modbus only, no debugger)

The bench needed SWD because ambient RH was 47 %, below the 50 %RH validation
floor on `RH_SETPOINT`. **In a pile this is unnecessary**: RH is near 100 %, so a
legal setpoint of 50 % saturates the loop and pins duty at the clamp.

1. Record `VIN_MON` (0x0012) and the heater resistance in use. Power is
   `P = duty * VIN^2 / R`; R is `O2P_HW_HEATER_OHM` (140 Ω for RH1‖RH2 on
   Rev A) and **changes** if the heat source moves to the ring PCB — measure it,
   do not inherit this number.
2. Confirm `FAULTS` (0x0006) has no `HEATER_DISABLED`, and that the build has
   `O2P_HEATER_ENABLE=1`. v0 ships with it 0.
3. Write `RH_SETPOINT` (0x0033) = `5000` (50.00 %RH). The loop now saturates.
4. Square wave, ≥ 3 cycles. Write `HEATER_MAX_DUTY` (0x0035) alternately to `D`
   and `0`. Pick `D` so the expected rise is 2–5 K: start at `2000` (20.00 %)
   and adjust after the first cycle.
5. Log at ≤ 10 s intervals: `T_TIP` (0x0002), `HEATER_DUTY` (0x0005),
   `VIN_MON` (0x0012), `FAULTS` (0x0006). **Read duty back — do not assume it.**
   The controller publishes what the hardware applied, so an interlock that
   refused the command is visible in 0x0005.
6. Restore `HEATER_MAX_DUTY = 0` and `RH_SETPOINT = 8500` when finished. Do
   **not** write the commit magic — this configuration is not meant to persist.

## 5. Analysis

For each half-cycle fit `T(t) = T_inf - (T_inf - T_0) * exp(-t/tau)`, then

```
DT    = mean(T_inf, on) - mean(T_inf, off)
P     = duty * VIN^2 / R          (duty as read back from 0x0005)
theta = DT / P                    [K/W]
C     = tau / theta               [J/K]   sanity check, expect ~1 J/K
```

Report θ with the medium described (moisture, whether the probe was potted and
tubed, depth, and whether the pile was actively aerated). θ is a property of the
installation, not of the board.

## 6. Traps, all of them paid for on 2026-09-04

- **Duty is not commanded directly.** The PI loop targets RH. `HEATER_MAX_DUTY`
  is what pins it, and only while the loop is saturated.
- **Do not use `T_TIP − T_CHAMBER`.** One thermal node; see §3.
- **Do not derive θ from the initial slope.** It underestimates badly — the
  first sample is already well into the response. The bench slope method gave
  0.57 K/% against a true 1.01 K/%, an error of ~2x. Fit the asymptote.
- **Let it actually settle.** At 4 % the bench was still climbing at t = 140 s
  and only flat after ~250 s. Five time constants, verified flat, or the number
  is low.
- **The measurement must be done in the final mechanical configuration** —
  potted, in its tube. The potting and tube are most of the path.
- If you do halt the core over SWD for any reason, the IWDG is ~4.1 s and will
  reset the board mid-measurement unless `DBGMCU_APB_FZ1` bit 12 is set — and
  DBGMCU reads back 0 for every register unless `RCC_APBENR1` DBGEN is set
  first.

## 7. What to do with the result

Put θ and the conditions into `compostlab/o2-probe/POWER.md` §3.2, replace the
assumed-duty table with the measured row, and re-pick the panel and battery.
If θ lands above ~30 K/W, the recommended 60 Wp / 30 Ah is over-bought and the
saving is real money per node.

Two things the same dataset gives away for free:

- **kp/ki against a real plant.** `heater_ctl.h` says the gain "cannot be
  characterised anywhere but in a real pile"; τ and the DC gain from this test
  are exactly what tuning needs.
- **Whether `dt_max_k` can ever bind.** It cannot on Rev A (§3). If the ring
  moves off-board and the sensors stay put, it still cannot, and the interlock
  should be deleted rather than shipped as decoration.
