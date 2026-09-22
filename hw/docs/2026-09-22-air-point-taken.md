# Air point taken at ambient, 2026-09-22

Probe 3, FW 0x002C, build id 0x49C5E15C (commit `9c5e15c`, clean tree).
Taken over LoRaWAN with `tech/chirpstack/o2p_lorawan_cmd.py`, on Fab's
instruction ("take airpoint measurement now"). Probe on the bench in room
air, 19.5 C, ~48 %RH, `gas_faults` 0.

## What was there before

| reg | before | after |
|---|---|---|
| 0x002A CMD_RESULT | 0x**00**02 (cal NONE, commit OK) | 0x**02**02 (cal **OK**, commit OK) |
| 0x002B CAL_STATE | 6 | 6 (unchanged - see below) |
| 0x0037/38 CAL_AIR_NA | 103 030 nA | **97 229 nA** |
| 0x0039 CAL_TEMP_C100 | 3771 (**37.71 C**) | **1952 (19.52 C)** |
| 0x0043 CAL_AIR_FRAC | 20607 | **20767** |
| 0x0044 CAL_P_HPA | 930 | 930 |
| 0x0045 DIL_ALPHA | 715 | 715 |
| 0x003F CONFIG_CRC | 0xC118 (2026-09-21) | **0xD13F** |

MEASURED, not assumed: every row above is a register read in a CTRL session
either side of the trigger, not a prediction.

The point that was in the probe had been taken at **37.71 C**, so every
reading since had the cell tempco law extrapolating ~18 K downward to reach
bench ambient. The new point is referenced where the gas is actually known.

## Proof it took, and that it reached flash

`CAL_TRIGGER` (0x003D = 0xCA11) and `COMMIT` (0x003E = 0x5AC1) were written as
two frames; regmap.c:2196 makes a COMMIT-only frame wait on a pending
calibration, so the image that reached flash is the post-calibration one.

Both are trigger registers that store nothing, so neither has a readback.
The evidence is elsewhere and it is independent of my own session:

- **0x002A went 0x0002 -> 0x0202.** The high byte is the calibration result;
  0x02 is `O2P_CMD_OK`. It was `O2P_CMD_NONE` before, so this is not a stale
  success from an earlier attempt.
- **`gas_cal_result` = 2 in the scheduled uplinks at 08:50:40, 08:51:38 and
  08:52:38**, with `bus_claimed` false - read from the node's own telemetry
  after the bus was released, not from the session that did the write.
- CONFIG_CRC moved 0xC118 -> 0xD13F. That covers the LIVE config only and so
  does not prove persistence by itself; `gas_commit_result` 2 does, because it
  is `o2p_config_store()`'s return value.

No reboot was performed, so "survives a power cycle" is inferred from
`commit_result`, not observed.

## CAL_STATE stays 6, and that is correct

6 = `NO_ZERO` (0x02) | `BIAS_UNVERIFIED` (0x04). Neither bit is about the air
point:

- `BIAS_UNVERIFIED` is permanent on this article. Rev A wires AIN2/AIN3 to the
  VA and VIN rail monitors, so `O2P_HW_BIAS_ADC_REACHES_ELECTRODES` is 0 and
  the bias verdict can never be anything but unknown. main.c:1330 substitutes
  the 70-130 uA plausibility window; the measured 97.2 uA passed it. The point
  is real, but nothing proved the cell was at its commanded bias when it was
  taken, and the bit says so.
- `NO_ZERO` still stands. **The zero point remains untaken** - that needs
  nitrogen, not a register write, and nothing here changed it. Every uplink
  still carries the decoder warning that the cell dark current is
  unsubtracted, biasing low-O2 readings high.

`AIR_DEFAULT` (0x01) was already clear before and after: an air point existed,
it was simply an old and distant one.

## What the reading did, and the one thing worth chasing

`gas_pct_vol` moved **20.50 -> 20.94 %vol** at 19.5 C. 20.94 against
`O2P_C_AIR` 0.20946 is self-consistency, NOT accuracy - the probe was just
calibrated in this gas, so it is required to agree with it. It confirms the
arithmetic closed; it measures nothing.

The 0.44 %vol the reading moved is the interesting part. Comparing the two air
points through the law:

```
gain(37.71 C) = 1.038613    gain(19.52 C) = 0.996453    law ratio = 1.04231
103030/0.20607 = 499976     97229/0.20767 = 468190      measured  = 1.06789
                                                residual  = +2.45 %
```

So the two air points disagree by **2.45 %** after the tempco law has been
allowed to account for the 18.2 K between them, with the older, hotter point
reading high.

**This is an observation, not a verdict on the law**, and three confounds are
unresolved:

1. The old point's date is not recorded in the register block. If it is the
   2026-09-12 air point referred to in main.c, two weeks of electrochemical
   cell drift is of this order on its own.
2. The old point's ORIGINAL air fraction is not recoverable - 20607 is what
   the 2026-09-21 `DIL_ALPHA` write restated it to under alpha 0.715. The
   comparison inherits whatever that restatement assumed.
3. 19.52 C and 37.71 C both sit essentially on the 0.75 capillary leg
   (the knee is at 36.00 C), so this says nothing at all about the
   41.37-75.81 C segment, which is still what Test C is for.

A clean version of this test is two air points a day apart at the same
temperature - that would separate drift from law error. Not run.

## Not changed

Heater untouched (`gas_heater_duty_pct` 0 throughout). No reflash. Zero point
still untaken. The alpha disagreement (0.402 bench vs 0.715 oven, 4.5 sigma)
is exactly where 2026-09-21 left it - this calibration was taken UNDER
alpha 0.715 and so cannot arbitrate it.
