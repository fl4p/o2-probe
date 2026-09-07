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

## Claim 2 (STANDS, measured after Fab's observation): the cell leads the SHT45

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

## Claim 4 (MADE): the cell cannot respond before the gas changes

So if the cell genuinely leads, either the SHT45 is slow in this cavity, or the
cell was kicked at t=0 by something that is not water - handling, or the jar's
air differing from room air in more than humidity. The blank (A -> out -> A,
zero gas change, identical handling) is what separates these, which promotes it
from a control to the test that decides the interpretation.

## A marginal feature, recorded so it is not silently dropped

A dip in `o2_raw` about 60 s BEFORE the RH departure: 30 s means 100.389
(t=-90), **100.328** (t=-60), 100.364 (t=-30), against a bin-to-bin scatter of
0.017 uA. About 2 sigma. Visible on a zoomed axis; not solid enough to call a
feature, not clean enough to ignore.

## Still open

* Venting of the glass jar is UNCONFIRMED.
* Whether the SHT45 in this cavity is genuinely ~160 s slow, which would be
  surprising for a part whose bare response is ~8 s.
