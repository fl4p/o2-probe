# The SHT45 de-creep mask is 30 s and the disturbance lasts ~350 s

**Measured 2026-09-07 on the bench, twice, by accident.** `main.c:296-301` asks
for exactly this measurement and says the current value is a guess:

> The window is a conservative guess: Sensirion documents the heater commands
> but this firmware has not measured the recovery time on this part in this
> chamber. **Treat it as unverified until a bench run replaces it** - which is
> also the measurement that turns the slow-recovery signature into the
> DEW_SUSPECT classifier PLAN.md:312 asks for.

This is that bench run.

## What happened

Two events, both while nobody touched the bench:

| | |
|---|---|
| event 1 | 2026-09-06T23:17:35Z (inside the aborted heater run) |
| event 2 | 2026-09-07T07:16:59Z (inside RH step 1, probe in the dry jar) |
| interval | **7 h 59 m 24 s** |

`regmap.c:34` sets `sht_pulse_interval_h = 8u` ("PLAN.md:312, every 6-12 h") and
`main.c:861-870` fires `o2p_sht4x_heater_pulse(O2P_SHT_CMD_HEAT_200MW_1S)` on
that timer. The interval matches to within 36 s over eight hours. **These are
the scheduled de-creep pulses, not failures.**

Confirming it is the sensor's own 200 mW element and nothing else on the board:

* `heater_duty_pct` = 0.0 with `HEATER_DISABLED` set throughout - the probe's
  condensation heater is excluded.
* MCU die temperature does not move (25.1-25.7 C either side).
* The heat is local to the tip/chamber: `t_tip` (TMP117) rises **+0.24 K in 6 s**
  and `t_chamber` (SHT45) +0.17 K, both decaying together over ~3 min.
* `o2_raw` is undisturbed throughout, 100.60-100.71 uA. The cell does not care.

## The measurement

RH against the fitted drying curve (exponential, fitted on both sides with the
pulse window excluded; pre-pulse residual sd **0.054 %RH**, n=333):

| back to within | time after the pulse |
|---|---|
| 0.50 %RH | 115 s |
| 0.20 %RH | 228 s |
| **0.10 %RH** | **325 s** |
| 0.05 %RH | not reached inside the window |

`O2P_SHT_RECOVERY_MS` is **30 s** (`main.c:92`).

**At t+40 s - ten seconds after the mask expires - the published RH is
1.63 %RH LOW**, and it stays more than 0.2 %RH low until t+228 s.

## Why this matters

`sht4x.h` states the requirement and the failure mode itself: *"The pulse and
its settling window must be MASKED from the reported RH channel, or the
de-creep looks like the pile drying out."* With a 30 s mask against a ~350 s
disturbance, that is exactly what is published: **every 8 hours the probe
reports a 1.6 %RH downward step that decays over about six minutes, and calls
it humidity.** On a compost pile that is a drying event that did not happen.

Two further consequences, both observed:

1. **A scheduled pulse is published as `I2C_FAIL_SHT`** (`main.c:303` sets the
   fault for the whole mask window). A deliberate maintenance action is
   indistinguishable, at the Modbus interface, from a failed humidity sensor.
   Note `i2c_errs` stays at 0 throughout, so the counter and the fault bit
   disagree - a consumer cannot use the counter to tell them apart either.
2. **The condensation heater is disabled for the duration.** On 2026-09-06
   23:17 the heater was commanding 0.14 % duty; the pulse raised the fault and
   duty went to 0.0 in the same sample. The interlock behaves correctly, but
   the trigger was maintenance rather than a fault, so **in the field the
   condensation heater stops for ~25 s every 8 hours by design and nothing
   says so.**

## Recommendation

Raise `O2P_SHT_RECOVERY_MS` from 30 s to **at least 350 s**, and prefer a
distinct fault or status bit for "chamber masked, de-creep in progress" over
reusing `I2C_FAIL_SHT`. The 0.10 %RH criterion above is the one to design to;
0.05 %RH was not reached within the observation window and may need longer.

Both events are in `bench-logs/modbus-poll-2026-09-06.csv` and
`bench-logs/modbus-poll-2026-09-07.csv`.

## Caveats

* n = 2, one article, one chamber, ~22 C and 40-50 %RH. The recovery time will
  depend on temperature, on absolute humidity, and on whether the sensor has
  actually crept - the pulse's whole purpose is to drive off adsorbed water,
  so a sensor with more to drive off may take longer.
* Event 2 fell inside a window where three pollers were contending on the
  serial port (my error), which raised the sample rate to ~1 s and produced one
  corrupt row. It does not affect the RH timing above, which is derived from
  the SHT channel and cross-checked against a 1061-point fit.
* `vin_mv` and `vref_mv` report a single value across the whole log and cannot
  show a transient, so "no dip on VIN" is not evidence about the pulse current.
  `va_mv` resolves 2 mV and shows no dip, which bounds the rail impedance
  rather than excluding the draw.

## Acted on, 2026-09-09

The mask is now **350 s**. `O2P_SHT_RECOVERY_MS` used to be defined in `main.c`
while the cache bound derived from it lived in `o2.h`, with nothing enforcing
the relation across the file boundary — that is why the recommendation above
could sit here unimplemented without anything complaining. Both constants now
live in `o2.h`.

**Corrected the same day, after review.** The first version of this change also
raised the chamber cache from 45 s to 400 s "so the cache covers the mask", with
a `_Static_assert` binding the two. That was circular — sizing a staleness
budget to the length of the gap you want to paper over justifies any number —
and the number it justified publishes a materially wrong reading. The cache
carries chamber **temperature** as well as humidity, and temperature enters the
dry-basis correction through `p_sat(T)`, which is exponential: a 5 K stale
temperature is **−6.3 % at 60 °C and −10.8 % at 70 °C**, against **−0.4 %** for
the 1.6 %RH artefact this mask exists to suppress. The mechanism makes it worse,
not better — the RH loop stands down for the whole mask, so the membrane heater
is off and the chamber is *drifting* during exactly the window the cached value
covers.

So the bound is back at **45 s**, `O2_COMP` takes its sentinel for the remaining
~305 s of each mask, and the assertion is not reinstated in either direction.
`O2_RAW` needs no SHT45 and publishes throughout, which is what makes that
affordable: the probe's physical measurement of the cell never pauses, only the
dry-basis conversion does. The heater's dT clamp got its own bound
(`O2P_HEATER_CHAMBER_MAX_AGE_S`, also 45 s) so an oxygen data-age policy cannot
move a thermal interlock's trip point again.

The second recommendation — a distinct signal for "chamber masked, de-creep in
progress" — was met **by subtraction**. There is no room for a positive one:
all sixteen fault bits are allocated and the diagnostic block is full at
0x0010–0x002F. So the mask now raises *nothing*, and the discrimination is:

| | chamber registers | fault word |
|---|---|---|
| scheduled mask | sentinels | **no `I2C_FAIL_SHT`** |
| dead/absent SHT45 | sentinels | `I2C_FAIL_SHT`, from the first failed read |

Which is strictly more information than before, when the two were identical.
`o2p_sht_masked()` and `o2p_sht_phase_faults()` in `sampler_logic.h` are the
two halves of the rule; `phase_sht()` calls both, and
`test_a_scheduled_mask_is_not_a_fault` exercises those functions rather than a
restatement of them. The guard was calibrated against the known-bad behaviour:
made to raise the bit while masked, the test fails with
`Expected 0x0000 Was 0x0010`.

One case the first version got wrong and this one handles: `main.c` enters the
mask whether the heater command succeeded **or not**, so with the unconditional
fault removed, a pulse that failed on the bus spent its whole 350 s window
looking like healthy maintenance — an already-observed I2C failure laundered
into silence. `o2p_sht_phase_faults()` now takes the pulse outcome and keeps
raising `I2C_FAIL_SHT` across a mask entered by a failed pulse.

Consequence 1 of "Why this matters" is therefore fixed. **Consequence 2 is
not** — it is accepted and documented instead. The condensation heater's RH
loop still stands down for the whole mask, which is now 350 s rather than 25 s,
about 1.2 % of the time at the default 8 h interval. It is not silent: the
reason appears as `NO_RH` in `HEATER_BLOCK` (0x002E), and the persistent tip
loop keeps running on the bridged chamber temperature. Refusing is also the
correct answer at this length rather than merely the cautious one — the pulse
drives measured RH *low*, so a loop regulating on it would read the chamber as
drier than it is and under-heat, which is the direction that condenses.

**Still open from this run.** The 0.05 %RH criterion was never reached inside
the observation window, so 350 s is bounded by 0.10 %RH and not by the sensor
returning to true. The caveats above still hold in full: n = 2, one article,
one chamber, ~22 °C, 40–50 %RH. A sensor with more adsorbed water to drive off
may take longer, and a hotter, wetter pile is exactly that case. And the
DEW_SUSPECT classifier this run was supposed to feed (`PLAN.md:312`) still does
not exist.
