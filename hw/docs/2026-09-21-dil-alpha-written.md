# DIL_ALPHA written to probe 3 - 0x0045 = 715

2026-09-21, ~20:44 CEST. Fab: "do 4", on the item "DIL_ALPHA is still unwritten".

Probe 3 (`dev_eui 34b7dafffe5b84e0`), FW 0x0028, on the bench at ambient
(T_EXT 20.96 C, chamber RH ~51 %). Keeper is down and the node is out of
farmgw's BLE range, so the whole exchange went over the LoRaWAN CTRL path:
`tech/chirpstack/o2p_lorawan_cmd.py --server farmgw:8080 --resend-s 75`.

## What was wrong

`O2P_DIL_ALPHA_DEFAULT` is **1.0**, and the register had never been written, so
the probe applied the FULL gas-law vapour dilution. The 2026-09-19 oven soak
measured this cell's share of it at **alpha = 0.715 +- 0.052** from one
isothermal drying window, and `O2P_CELL_T_TOP_LNF` - the knee model's 75.81 C
anchor, live in this image - is derived AT that alpha. The probe and its own
temperature law were assuming different physics.

## What was done

Two writes in one session, then a readback in a fresh one:

| register | before | after |
|---|---|---|
| 0x0045 DIL_ALPHA | 1000 | **715** |
| 0x0043 CAL_AIR_FRAC | 20472 | **20607** |
| 0x0044 CAL_P_HPA | 930 | 930 (untouched) |
| 0x003F CONFIG_CRC | 0x90BD | **0xC118** |

CAL_AIR_FRAC was **not** written by hand. `reference_air_frac()` restates it
after the frame, because the stored fraction is `C_air * f_eff(alpha_old)` and
K is fixed against it - leaving it alone would rescale every later reading by
the alpha ratio. `f_eff` inverts exactly, so **nothing had to be re-measured**.
Predicted in float32 before the write as **20607** and read back as 20607; the
amplification ratio 0.715 is well inside `O2P_AIR_FRAC_MAX_AMPLIFY` (10.0) and
the result is inside `O2P_CAL_FRAC_MIN/MAX`.

## It is in flash, and the probe says so

`gas_commit_result` moved **0 -> 2** (`O2P_CMD_OK`) after the COMMIT, which is
`o2p_config_store()` returning true. 0x003F is the CRC of the LIVE config only,
so it could not have answered this; the commit result could. No reboot was
needed and none was performed.

`gas_faults` stayed 0 throughout.

## The published oxygen moved +0.06 %vol

`gas_pct_vol` 20.47 -> **20.53** at ambient, across the write. Small because
the air point was taken at a humidity not far from the present ~51 % RH - the
restatement cancels the change AT the calibration humidity by construction, and
what is left is the difference in how the two alphas extrapolate away from it.
The correction grows with vapour pressure, so the pile is where it will matter.

## OPEN: the two alphas disagree by 4.5 sigma

- **0.402 +- 0.046** - 2026-09-07 bench sweep, at bench temperature
  (O2-HUMIDITY-CORRECTION.md 15.3).
- **0.715 +- 0.052** - 2026-09-19 oven soak, one isothermal drying window
  above 40 C.

These do not overlap. Either alpha is temperature-dependent or one leg is
wrong, and the register holds ONE number. **0.715 was written because the live
temperature law's top anchor is derived at it** - consistency with the knee
model was the deciding argument, not a belief that 0.715 is the better
measurement. A second isothermal drying window is still owed; until then the
value above 40 C rests on a single window, as `2026-09-19-oven-soak-run.md`
line 613 already says.
