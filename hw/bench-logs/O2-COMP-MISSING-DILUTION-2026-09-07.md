# The published O2_COMP carries no humidity correction

**2026-09-07, farm-node-01 / probe 3, found on the dry-jar transfer at 13:20 UTC.**

## What was seen

Moving the probe from the saturated-NaCl vessel to the dry jar dropped chamber RH
66.4 % -> 29.6 % in ~20 min. The Grafana oxygen trace rose 21.14 -> 21.30 %vol.

That direction is the wrong one. Water vapour displaces oxygen, so drying the gas
*raises* the wet-basis reading and leaves the **dry basis flat**. A probe that
publishes a dry-basis number should not have moved.

## The discriminator

`O2_COMP` is documented as dry basis: `C_dry = C_wet / f`, `f = (P - p_w)/P`
(`firmware/src/o2.c:87` `o2p_dry_from_wet`). `O2_RAW` is the uncorrected cell
current. K is a stored calibration constant, so for every sample

    K = cell_na / ln(1 / (1 - C_wet))

must come out the same, whichever model is right. Fit K both ways over three days
of recorded telemetry, bucketed by RH:

| RH bucket | n | K, assuming the dilution term IS applied | K, assuming it is NOT |
|---|---|---|---|
| 20-30 % | 1 | 431 285 | 425 547 |
| 30-40 % | 1 | 432 945 | 425 456 |
| 60-70 % | 13 | 437 877 | 425 570 |
| **spread (cv)** | | **0.457 %** | **0.014 %** |

Model "no dilution" is constant to 1.4e-4 across the full RH range. Model "with
dilution" drifts monotonically with RH, which is the signature of a correction
that was never applied being fitted as though it had been.

**The deployed image publishes the wet-basis fraction under the dry-basis name.**
The source in this repo does apply the term; the flashed image is older than it.
Probe uptime at discovery was 80 762 s (last reset 2026-09-06 ~17:00 UTC).

## Size of the error

The published number is low by `(1 - f)`:

| condition | p_w | f | published reads low by |
|---|---|---|---|
| dry jar, 29.6 %RH @ 27.7 C | 11.0 hPa | 0.988 | 1.2 % |
| NaCl vessel, 66.4 %RH @ 27.3 C | 24.0 hPa | 0.974 | 2.6 % |
| **pile, 100 %RH @ 55 C** | **157.8 hPa** | **0.830** | **20.4 %** |

On the bench this is a fraction of a percent and easy to miss. In a pile it is
the dominant error in the instrument: a true 12.0 %vol dry would publish as
10.0 %vol. It is also *correlated with the thing being measured* - a hot, wet,
actively rotting zone is exactly where p_w is largest - so it biases the
respiration signal, not just the level.

## What this invalidates

Nothing recorded is lost: `gas_cell_ua` (O2_RAW), `gas_rh_chamber_pct` and
`gas_t_chamber_c` are all logged, so every past sample can be corrected
retrospectively with the table above. What must not be trusted is any
`gas_pct_vol` comparison **across different humidities** - including the
NaCl-vessel settling run, whose whole point was a humidity step.

## Next

**Superseded in part.** This log was written before reading
`../O2-HUMIDITY-CORRECTION.md`, which had already established the same thing in
its section 9 on 2026-09-06 - and whose section 10 measured that the correction
this log recommends applying **overshoots on this hardware**. The measurement
above stands as independent confirmation; the recommendation to "reflash and
treat the dashboard as wet basis" does not.

Read section 12 of that file instead: the vessel transfer of 2026-09-07T13:20Z
is the near-isothermal step section 10 asked for, and it puts the cell's
response at ~60 % of the modelled dilution - right sign, ~1.75x too strong.
Flashing is still net-positive in pile conditions but it is not the clean fix
this log assumed, and it blanks the oxygen channel until a fresh air point is
taken.
