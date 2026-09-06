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
scatter, so the sign alone decides it.

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
Any response there is subtracted from steps 1–3.

## 4. Predictions, written before the run

| | dilution only | film only | both |
|---|---|---|---|
| sign, A→K | **negative** | **positive** | fast −, slow + |
| speed | seconds to ~1 min (membrane-limited) | 10–40 min | two time constants |
| reversible K→A | fully | slowly, with hysteresis | mixed |
| shape vs RH | linear in p_w | knee near 85 %RH | knee on a slope |

**The discriminator is the shape of the step, not its endpoint.** If a fast
negative step is followed by a slow positive drift that overtakes it, both
mechanisms are present and their sizes fall straight out of the fit. That
conclusion survives even if the absolute magnitudes are off.

Hysteresis on K→A is close to decisive on its own: gas dilution has none.

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
  still works, at a smaller span
- silica gel packets, or salt/rice dried in the oven and cooled sealed
- something inert to stand the probe on above the slurry
- all of it left in the room overnight
