# RH step, step 1 (room -> A dry): live notes and the claims made from them

Written during the run. Numbers from `modbus-poll-2026-09-07.csv`, marker
`06:54:05Z` (set from the RH departure in the trace, not wall clock; Fab's
verbal report was ~40 s later). P = 965 hPa, dilution reference
**-0.1052 %/hPa**.

## What is not in doubt

* The step is genuinely isothermal: T span **0.12 K** over the first 9 min,
  against the 0.3 K rejection threshold in `RH-STEP-TEST.md` section 5. No
  previous humidity change on this bench was isothermal.
* `p_w` swept 16.06 -> 13.2 hPa and `o2_raw` rose 100.40 -> 100.51 uA.
* **The sign is dilution**: vapour leaves, current rises.

## Claim 1 (MADE, THEN RETRACTED): two mechanisms are present

The %/hPa computed within successive windows decays with time:

| window | %/hPa |
|---|---|
| first 1.5 min | -0.084 |
| 1.5-4 min | -0.068 |
| 4-10 min | -0.044 |

I first read this as fast dilution plus a slow positive component eating it,
i.e. section 4's "both mechanisms" case, and argued transport lag could not
explain it because a lagging **cell** makes the early slope *shallow* and
steepen with time, which is the opposite of what is seen.

**Retracted the same hour.** Fab observed from the plot that the cell responded
*earlier* than the SHT45. That is the other lag - a lagging **reference** - and
it produces exactly this decay with no second mechanism required.

## Claim 2 (RETRACTED as an inference; the observation is explained by geometry)

> **2026-09-07, after review and after Fab reported the assembly.** The cell is
> **not on the PCB** - the footprint has the wrong pin order, so it flies on
> copper wires and sits **closer to the membrane than the SHT45**. The lead is
> therefore where the sensors are, not what they are. Nothing below is evidence
> about the cell, a film, or the humidity correction.
>
> The statistics were also weaker than presented:
> * The fractional table normalises to each channel's value at +8 min, which is
>   **not a plateau** - `p_w` was 13.39 hPa there and still falling to 11.63 at
>   +20 min. With a -300..-120 s baseline instead of the last minute the
>   midpoint difference is **68 s, not 104 s**, and the five differences span
>   37-140 s rather than approximating a constant delay.
> * The cross-correlation is **inconclusive**. A phase-randomised null
>   preserving the derivative spectra puts the 95th percentile of the scanned
>   maximum at **0.203**, above the quoted 0.177; the lag was chosen by
>   searching, which biases the maximum upward.
> * `t = 0` is taken from the SHT45's own departure - the **downstream** sensor.
>   Circular.
> * The "6x" ratio at t=0 rests on a 0.045 uA numerator against a 0.039 % cell
>   noise floor: about 1.15 sigma.
>
> What survives: the cell's response precedes the SHT45's, and the reason is
> that it is nearer the gas.

### The original claim, kept for the record: the cell leads the SHT45

Fraction of each channel's +8 min change:

| fraction | cell | SHT45 | cell leads |
|---|---|---|---|
| 10 % | -1 s | 36 s | +37 s |
| 25 % | 22 s | 75 s | +53 s |
| 50 % | 60 s | 164 s | **+104 s** |
| 75 % | 171 s | 300 s | +129 s |
| 90 % | 267 s | 407 s | +140 s |

Cross-correlation of d(raw)/dt against -d(p_w)/dt: best lag **+54 s**, cell
leading, r = 0.177 (r = 0.104 at lag 0).

An N-sigma onset test says the opposite (SHT45 first). That is a
signal-to-noise artefact: `p_w` baseline noise is 0.0145 hPa against a 3 hPa
swing, so it crosses its threshold almost immediately, while the cell's
0.039 % noise hides its start. The fractional comparison is the valid one.

Same conclusion from the ratio of observed rise to the rise dilution predicts
for the `p_w` reported by then:

| t | d p_w | dilution predicts | observed | ratio |
|---|---|---|---|---|
| 0 s | -0.07 hPa | +0.007 uA | +0.045 | 6x |
| +30 s | -0.37 | +0.039 | +0.075 | 2x |
| +390 s | -2.41 | +0.250 | +0.179 | 0.7x |

Over-responds 6x early, under-responds by the end. One mechanism with a correct
humidity reference cannot do that; a lagging reference does exactly that.

## Claim 3 (MADE): the endpoint, not the ramp, is the estimator to use

With a lagging reference the within-ramp regression is biased, but the
difference between two fully equilibrated states is not, whatever either
sensor's time constant. Hence: dwell to equilibrium in each vessel and difference
the plateaus; stop quoting ramp slopes.

## Claim 4 (WRONG - the dichotomy was not exhaustive)

The claim was: the cell cannot respond before the gas changes, so either the
SHT45 is slow in this cavity, or the cell was kicked at t=0 by something that is
not water.

**There is a third option and it is the true one.** The gas does not change
everywhere at once. In one slowly drying, unstirred vessel the two sensors sit
at different depths in the diffusion path, and the cell - flying on wires,
nearer the membrane - reaches the new humidity first. The premise "the cell
cannot respond before the gas changes" is true and useless: the gas *at the
cell* changed first.

The review raised this as a possibility before Fab reported the assembly. Both
arrived at it independently; only one of them was me.

The blank is still worth running, but it no longer decides the interpretation -
it now measures the handling artefact it was always meant to measure.

## A marginal feature, recorded so it is not silently dropped

A dip in `o2_raw` about 60 s BEFORE the RH departure: 30 s means 100.389
(t=-90), **100.328** (t=-60), 100.364 (t=-30), against a bin-to-bin scatter of
0.017 uA. About 2 sigma. Visible on a zoomed axis; not solid enough to call a
feature, not clean enough to ignore.

## Still open

* Venting of the glass jar is UNCONFIRMED.
* ~~Whether the SHT45 is genuinely ~160 s slow.~~ **Closed.** Sensirion v7.3
  Table 1 gives RH **tau63 = 4 s** at 25 C and 1 m/s airflow, and 6.1 says the
  integrated membrane does not alter the specified response time. (The "~8 s"
  written here was wrong by 2x.) A ~160 s *system* response in stagnant cavity
  gas remains entirely plausible - the datasheet makes application response
  design-dependent - but it is the cavity and the sensor placement, not the
  part.
* **The source CSV was not committed when these claims were written**, and the
  window contains 42 duplicate UTC values and 51 duplicate `sample_seq` values
  from three pollers contending on the port (my error). Pseudo-replication of
  that kind inflates the degrees of freedom behind any correlation here.
