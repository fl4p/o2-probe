# The dry-air idle gate, measured on probe 3 — 2026-09-20

**Status: MEASURED.** FW 0x0029, BUILD_ID `0x46E4440D` (commit `6e4440d`, dirty
bit clear, bit 30 is the runtime debug flag). Probe 3 on the bench in room air,
nobody commanding the heater, bus quiet. All values from VictoriaMetrics on the
VPS, `gas_*` series, 60 s cadence.

`HEATER_DUTY` (0x0005) is the **60 s trailing mean** since FW 0x0024, so every
edge below is smeared by up to a minute. Timings are quoted with that in mind;
`HEATER_DUTY_NOW` (0x0009) would sharpen them and was not sampled.

## What the gate is for

The dew law is already free in dry gas — its error goes negative and `pi_core()`
clamps to zero. The **gradient floor** was the one spending: it demands
`T_tip = T_cell + 2.00 K` on every cycle and has no humidity input by design. A
probe on the bench or in transit therefore held that gradient forever.

Measured before the change, five hours of it:

    gas_t_chamber_c - gas_t_ext_c   held 1.89 .. 2.10 K   12:11 -> 16:41

That is the floor's own 2.00 K setpoint read back through the chamber's copper,
which on Rev A is the tip's copper. ~3 % steady duty; POWER-BUDGET.md puts that
at ~80-84 d of the 10 Ah battery against 233 d idle.

## 1. Gating

    16:43   duty 2.23   gradient ~2.00      old image, floor holding
    16:50   duty 0.00                       gate engaged
    ...     duty 0.00                       25 min
    17:15   duty 0.00   chamber-cell -0.03

The chamber-cell gradient collapsed from 2.00 K to -0.03 K and the duty went to
exactly zero, with the floor 1.9 K short of its setpoint and therefore demanding
drive. That is the gate withholding it.

## 2. The opening debt

A fresh state OWES `O2P_HEATER_DRY_ASSERT_S` of floor before the gate may
engage, because a reset is the one moment nothing is known about the gas. The
flash reboot exercised it:

    17:52   duty 13.57   tip-cell 2.59      fresh boot: floor RUNS
    17:53   duty  1.90   tip-cell 1.99
    17:54   duty  0.74   tip-cell 1.21
    17:55   duty  0.00   tip-cell 0.58      gate engages

The 13.57 % opening is the PI starting from a zeroed integrator, not a
consumption figure. Boot at 17:51:11; the gate engaged at ~169 s of uptime.

## 3. The periodic re-assert — the whole cycle

    17:55 -> 18:23   duty 0.00   gradient 0.05 .. 0.09   29 min of zero
    18:24            duty 8.04   gradient 2.22           premium
    18:25            duty 2.04   gradient 2.05
    18:26            duty 0.61   gradient 1.07           decaying
    18:27            duty 0.00   gradient 0.52           gated again

Re-assert detected at uptime **1965 s**, against a gate engaged at ~169 s: a gap
of **~1796 s** where `O2P_HEATER_DRY_IDLE_MAX_S` is 1800. The premium itself ran
~120 s of drive, which is `O2P_HEATER_DRY_ASSERT_S`.

**THE GRADIENT IS THE EVIDENCE, NOT THE TIMING.** The floor regulates TO 2.00 K,
so a floor-driven event converges on 2.00 and a commanded one does not. This one
went 2.22 -> 2.05. Earlier the same afternoon a 6.00 % spike at 17:16 was
initially read as this same re-assert and was NOT: its gradient hit **4.44 K**,
which the floor cannot produce, and it was a peer session's bench override at a
commanded 10 %. Same test, opposite verdicts. A timing argument would have
accepted both — the 17:16 event fell inside the window the premium was due in.

That contaminated window also cost the measurement: under the debt rule, seconds
the floor drives FOR ANY REASON pay the premium down, so the override's 36 s of
drive credited against it. The two mechanisms cannot be separated in that data
and it was discarded rather than rescued.

## 4. The gate warms its own humidity sensor

Not designed, not in the codex review, found by watching the probe afterwards.
The SHT45 is in the chamber; the chamber shares the tip's copper on Rev A.

    gas_rh_chamber_pct   flat at ~43.7 % all afternoon
    43.67 -> 44.90 -> 46.93 -> 48.03   as the copper cooled after gating

About **+1.6 points of RH per kelvin** at this humidity, so ~3 points for the
~2 K the chamber gives up. Gating RAISES the humidity the gate reads.

Direction is safe — it pushes toward the exit threshold, toward heating — but:

1. The exit band must exceed the self-induced rise or the gate limit-cycles.
   9000 -> 9500 is 5 points against a measured ~3. **It holds by 2 points, by
   luck and not by calculation.** Anyone narrowing that band must re-measure
   this slope first.
2. The saving shrinks exactly where the ambient is damp. Correct behaviour, not
   a free lunch.

## What is NOT established

- **The gate is not a condensation safeguard under a FAULTY humidity sensor.**
  The two conditions are not independent evidence: at chamber 50.00 C, cell
  46.20 C and a reported 60 % RH the gate idles, while an actual 84 % puts the
  cell 0.34 K BELOW the dew point. The 1800 s cap bounds that exposure and does
  not refute it. Sound as a storage energy policy; an explicit storage mode is
  the honest form. Fab's call.

  **ANSWERED 2026-09-21, FW 0x002B.** That mode is now register 0x004C,
  HEATER_STORAGE, and the gate does nothing without it. Everything measured on
  this page still describes what the gate DOES - it was measured with the gate
  free to engage, which is what permission now grants - but it no longer
  describes what a probe does by default. **A probe with no permission heats as
  it did before FW 0x0027.** The energy saving is opt-in.

  Note what this does NOT change: the gate's conditions are exactly as unable
  to detect a lying sensor as they were. Nothing was made smarter. The
  authority to trade the floor away was simply moved to somebody who can see
  where the probe is.
- **The energy figures are modelled, not measured.** ~14 % of the continuous
  floor's energy, ~184 d, from the bench thermal model (theta 68 K/W, tau 150 s)
  — not a battery observation on a potted probe.
- **DRY_IDLE cannot be read from telemetry.** HEATER_LAW (0x0008) bit 11 is
  published by the firmware but the node codec does not decode that register, so
  every conclusion here is inferred from duty and the gate's inputs rather than
  read from the flag. Decoding it would make this directly observable.
- **The pile lockout added in FW 0x002A is a HOT-pile discriminator only.**
  The v0.41 version note claimed 35.00 C sits "far below any pile"; that was
  wrong and is retracted. A curing or cooling heap sits near ambient, and the
  DWD 1991-2020 normals for Villingen-Schwenningen (719 m) are 8.1 / 3.2 /
  -0.1 C for Oct / Nov / Dec. The sub-35 C hole is what FW 0x002B's storage
  mode closes, and it closes it by asking rather than by inferring.

- Everything is one probe, one plant, room air. Nothing here is a pile.
