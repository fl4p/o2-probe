# Isothermal RH step: does the cell see water vapour, or does the board leak?

**Planned 2026-09-06 for 2026-09-07.** Predictions are recorded here *before*
the run, deliberately.

## 1. The question

`O2-HUMIDITY-CORRECTION.md` §10: over 2026-09-06, thirteen out of thirteen
near-isothermal window pairs showed the cell current **rising** with water
vapour, at +0.11…+0.26 %/hPa, where the dilution model requires it to **fall**
at −0.10 %/hPa. Opposite sign, larger magnitude.

Two candidates, and nothing so far separates them because **every humidity
change on this bench came with a temperature change**:

* **Dilution (the model).** Water vapour displaces O₂ pro rata, current falls.
* **A moisture film.** Surface leakage on unpotted FR4 adds current into the
  TIA input, current rises. Same suspect as the +0.6 µA rise with the
  85–90 %RH knee in `DEW-MARGIN-IS-BLIND.md`.

These are not exclusive. Both are probably present; the question is their signs
and sizes on *this* article.

## 2. Design

Change RH at room temperature by moving the probe between vessels that have
already equilibrated over saturated salt slurries. The probe never changes
temperature because nothing is heated — the only knob is which vessel it is in.

Saturated-salt fixed points near 24 °C:

| vessel | agent | RH | p_w at 24 °C |
|---|---|---|---|
| **A** | silica gel / oven-dried desiccant | ~15 % | 4.5 hPa |
| **R** | room air (no vessel) | ~63 % | 18.8 hPa |
| **N** | saturated NaCl (table salt) slurry | 75.3 % | 22.4 hPa |
| **K** | saturated KCl (salt substitute) slurry | 84.3 % | 25.1 hPa |

A → K spans **20.6 hPa**, which is 2.0 % of total pressure. Signals expected:

* dilution alone: **−2.0 %** on `o2_raw`
* yesterday's fitted artefact: **+2.3 to +5.4 %**

Both are far above the 0.01 µA log resolution and the ±0.15 % day-scale
scatter.

**But the sign alone does NOT decide it** (corrected 2026-09-07). If the
artefact sits at the low end of its range, +2.3 % against a dilution of −2.2 to
−2.5 % nets out *negative*, and a run with both mechanisms present would be
read as "dilution only". The endpoint is a weak test; §4's shape test is the
real one, and §4 has its own limits.

The dilution magnitude itself is uncertain because **Rev A has no barometer and
the true ambient pressure is not measured.** At 930 hPa the A→K span is 2.22 %
of total and predicts −2.235 %; at 1013 hPa it is 2.04 % and −2.051 %. The
firmware's `ASSUMED_P_HPA` is 930 for a 715 m site, which is *not* where this
bench is. Record a local barometric reading — a phone or the weather service is
enough — before the run, and use it in the analysis rather than 930 or 1013.

## 3. Sequence

Poll at 5 s throughout, one continuous CSV, no reflash, no heater, no other
work on the bench.

| step | vessel | dwell | why |
|---|---|---|---|
| 0 | R | 60 min | baseline, continues tonight's soak |
| 1 | **A** | 60 min | dry end |
| 2 | **K** | 60 min | the step that matters |
| 3 | **A** | 60 min | reversibility and hysteresis |
| 4 | **A′** | 30 min | **blank**: identical vessel, same RH |
| 5 | N | 45 min | a mid point, if time allows |

Step 4 is not optional. It is the control that measures the handling artefact —
opening a lid, moving the probe, body warmth — against a gas change of zero.

**One late blank is not enough** (corrected 2026-09-07). Subtracting it from
A→K and K→A assumes the handling effect is stationary and additive, which is
exactly what a sorption artefact would violate. Run a blank at **both**
endpoints — A→A′ before step 2 and K→K′ after it — so the handling response is
measured at the humidity where it is used. If time forces a choice, keep the
wet-end blank: that is where a film is most likely.

## 4. Predictions, written before the run

| | dilution only | film only | both |
|---|---|---|---|
| sign, A→K | **negative** | **positive** | fast −, slow + |
| speed | seconds to ~1 min (membrane-limited) | 10–40 min | two time constants |
| reversible K→A | fully | slowly, with hysteresis | mixed |
| shape vs RH | linear in p_w | knee near 85 %RH | knee on a slope |

**The discriminator is the shape of the step, not its endpoint.** If a fast
negative step is followed by a slow positive drift that overtakes it, both
mechanisms are present and their sizes fall straight out of the fit.

**But this is suggestive, not identifying** (corrected 2026-09-07). A single
humidity-sensitive assembly can have a fast electrical/diffusive component and
a slow sorption or electrolyte component *of opposite sign*, and hysteresis can
come from the vessel or the PCB equilibrating rather than from a leakage film.
A two-exponential fit separates timescales; it does not assign mechanisms to
them. Treat two components as evidence that two processes exist, and let the
potted repeat — not this fit — say which is which.

## 4b. Define the pressure boundary — the control that was missing

The cell answers to O₂ *partial* pressure, so what the vessel does to *total*
pressure changes the expected signal, and the plan did not say (review 2026-09-07):

* **rigid sealed jar** — vapour adds to the gas already there, total pressure
  rises, and O₂ partial pressure barely moves. **Expected dilution ≈ 0.**
* **vented, constant total pressure** — vapour displaces dry gas pro rata, O₂
  partial pressure falls. This is the case the correction models.
* **an imperfect lid or a cable exit** — an uncontrolled mixture of the two.

With no barometer on Rev A this is unmeasurable from inside, and **a sealed jar
alone can produce "no dilution" from a perfectly normal cell** — which is a
candidate explanation for §10's whole result that has nothing to do with a
leakage film.

**Therefore: vent every vessel.** A hypodermic-needle or pinhole vent in the lid
equalises pressure on a timescale of seconds while leaving the vapour
equilibrium hours-long. Record which vessels were vented. An unvented run does
not test what this document claims to test.

## 5. Handling rules

* **Never let the board touch the slurry or a droplet.** It is unpotted. Suspend
  it above the liquid; a slurry, not a solution — thick enough not to slosh.
* All vessels sit in the same room for **≥ 4 h** before the run so they are at
  room temperature. This is what makes the test isothermal.
* Handle by the cable. Each move should take seconds and the lid goes straight
  back on.
* Record wall-clock for every move; they become the step markers.
* **Reject any step whose `t_chamber` moves more than 0.3 K** across the
  analysis window — that is the whole point of the design, and it must be
  checked rather than assumed.

## 6. Analysis

Use **`o2_raw` only.** `o2_comp` is `o2_raw` times a constant on this firmware
(§9), so it carries no independent information, and the offline dry-basis
correction is the thing under test — applying it here would assume the answer.

For each step fit `I(t) = I_∞ + a·exp(−t/τ_fast) + b·exp(−t/τ_slow)` and report
`a`, `b`, and both time constants with the measured Δp_w and ΔT beside them.

## 6b. Also do the temperature step here — it cannot be done in room air

The complementary experiment (**hold p_w, step T**) gives the cell tempco, which
`O2-HUMIDITY-CORRECTION.md` §10 showed is not identifiable from any data so far.
It belongs in this session, over the **KCl** jar, and the reason is a control
constraint discovered the hard way on 2026-09-06 (below).

Over a saturated slurry, only the board is heated. The slurry is a large
room-temperature vapour reservoir, so it **pins p_w** while the board's
temperature rises — a genuine constant-`p_w` step, which is exactly what the
open bench cannot give.

Steps 0 → 2 → 4 → 0 % of `HEATER_MAX_DUTY`, 45/45/60 min. Separate by time
constant as in §4: fast (τ ≈ 110–130 s) is the tempco, slow (10–40 min) is the
film desorbing. The return to 0 is the reversibility test.

**Corrected 2026-09-07 after review — the original plan said 4 → 9 % and would
have failed exactly as the open-bench run did.** RH headroom is not linear
subtraction: heating divides RH by the saturation-pressure ratio. From 84.3 %RH
at 24 °C,

| duty | P | ΔT at 98 K/W | RH after | ΔT at 117 K/W | RH after |
|---|---|---|---|---|---|
| 2 % | 20.6 mW | 2.02 K | 74.8 % | 2.41 K | 73.1 % |
| 4 % | 41.1 mW | 4.03 K | 66.4 % | 4.81 K | 63.5 % |
| 6 % | 61.7 mW | 6.05 K | 59.1 % | 7.22 K | 55.3 % |
| **9 %** | 92.6 mW | 9.07 K | **49.8 %** | 10.83 K | **45.1 %** |

The 9 % step crosses the 50.00 % floor on *either* θ, drops the loop out of
saturation, and limit-cycles. **6 % is the last step with real margin and 4 %
is the safe one.** The claim that 34 points of headroom "survives a 10 K step"
was the same linear-subtraction error that produced the failed open-bench run,
made twice in one night.

### The constraint: RH_SETPOINT has a 50 % floor and the loop is positive-acting

`HEATER_MAX_DUTY` does not command duty. It **caps** it. Duty comes from the RH
loop, which asks for heat only while measured RH is **above** `RH_SETPOINT`, and
`RH_SETPOINT` cannot legally go below **50.00 %** (`regmap.c
o2p_config_valid`). The fixture works by driving the setpoint to that floor so
the loop saturates and duty pins at the cap.

**Attempted 2026-09-06 22:51Z on the open bench at 54.4 %RH and it failed.**
4 % duty dried the chamber through the setpoint in under two minutes; the loop
left saturation, duty collapsed, RH recovered, duty returned:

```
   60 s  RH 51.38     120 s  RH 49.14     181 s  RH 50.14
  241 s  RH 49.84     301 s  RH 49.82     361 s  RH 50.36
```

A limit cycle around the 50 % floor, tip oscillating 24.3–26.5 °C. No step, no
time constant, nothing fittable. Aborted at 1690 s and the registers restored.

`o2p_thermal.py` preflight states this outright — at or below the floor "NO
legal setpoint saturates it and the heater cannot be commanded over Modbus at
all", with a warning band just above it. The check passed in the jar at 95 %RH
the day before and was not re-run after the board was dried to room air.

**So: the heater needs ≥ ~60 %RH ambient to be commandable at all, and more
headroom the harder it is driven.** The KCl jar at 84.3 % gives 34 points of margin at
room temperature, which is worth about a 6 K step and no more — see the table
in §6b. This is also a product finding: *a buried probe in
dry gas cannot use its own heater*, because the setpoint floor removes the only
control handle.

Fitting a tempco to the limit cycle is refused. What can be said is that
`o2_raw` stayed within 100.66–100.80 µA through ~2 K of tip oscillation at
constant `p_w`, which hints the tempco is small — a hint, not a number.

### Script requirement

Handle **SIGTERM** as well as SIGINT. The 2026-09-06 script caught only
`KeyboardInterrupt`; SIGINT did not take, SIGTERM killed it outright, and it
died with `HEATER_MAX_DUTY` still at 4 % — the registers had to be written back
by hand. `o2p_thermal.py`'s own `main()` installs a SIGTERM handler that raises
`KeyboardInterrupt` for exactly this reason. Copy it.

## 7. What is not available

The clean electrical discriminator — sweep the LMP91000 bias and see whether
the humidity-dependent excess scales with it, as a resistive leak must and a
diffusion-limited cell current must not — needs a writable bias register. Only
`LMP_READBACK` (0x001B) is exposed, and flashing is blocked by the
board-revision decision. It is the follow-up if the gas test comes out
ambiguous.

## 8. What it cannot settle

This is still the **bare, unpotted, untubed** article. If the artefact is a
surface film, potting should remove it, and that is a separate run on different
hardware. A null result here does not clear the product; a positive result here
does condemn *this* article's dry-basis number, which is enough to decide
whether `fe27d20` should be flashed.

## 9. Fab needs, before starting

- two or three sealable jars, ideally identical (step 4 needs two)
- table salt, and salt substitute (KCl) if the supermarket has it — NaCl alone
  still works, at a smaller span. **Check the labels**: iodised salt with
  anti-caking agent and "salt substitute" cut with NaCl are not the pure fixed
  points Greenspan tabulates. They will still give a stable, repeatable
  humidity, which is what this test needs — but do not quote 75.3 / 84.3 % as
  measured values afterwards. The SHT45 reading is the humidity of record.
- silica gel packets, or salt/rice dried in the oven and cooled sealed
- something inert to stand the probe on above the slurry
- all of it left in the room overnight
