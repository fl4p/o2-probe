# Vessel marks, 2026-09-07 (post-adapter-removal, LoRa record)

The 1 Hz cp2102 bench record ends 10:52:59Z (frozen at 911b843). Everything below
is the `farm-node-01` LoRa stream in VictoriaMetrics at 5-min cadence, resumed
11:15:00Z. Split the analysis at these marks.

## MARK: vessel N -> vessel A (dry), 2026-09-07T13:14:31Z

Last vessel-N sample before the move, @13:14:30Z:

| field | value |
|---|---|
| gas_pct_vol (dry basis) | 21.14 %vol |
| gas_cell_ua (RAW, uncorrected) | 101.08 uA |
| gas_t_chamber_c | 27.27 C |
| gas_t_tip_c | 27.36 C |
| gas_rh_chamber_pct | 66.38 %RH |
| gas_settle_s | 0 (settled) |
| gas_faults | 32768 (0x8000) |

Derived: es(27.27 C) = 36.15 hPa, p_w = 24.00 hPa. Saturated-NaCl target at that
temperature is 27.22 hPa, so the vessel was **3.22 hPa / 8.92 %RH SHORT of
equilibrium when it was removed** -- the N leg never reached its plateau.

Effective time constant at the moment of removal, from deficit/rate
(8.92 %RH at +0.72 %RH/h): **tau ~= 12.4 h**, so 95 % would have needed ~37 h.
An earlier estimate in this session of tau = 50 min was the HEADSPACE filling
only, and was wrong for the vessel as a whole. Do not reuse it.

## Why this leg matters

This is a **second drying leg**, and the direction is the point. The codex review
established that the p_w coefficient is not a material property but a trajectory
average, splitting on direction:

    drying   0.480 +/- 0.084
    wetting  0.948 +/- 0.115

and a ramp-rate test failed to explain the gap (wetting crossed at 5.94 hPa/h
against drying's 5.02 hPa/h). This leg is an independent replicate of the drying
direction, from a HIGHER starting p_w than this morning's A leg. If drying again
returns ~0.48 while the morning's wetting returned ~0.95, the asymmetry is real
and is a hysteresis, not a fitting artifact.

Watch for: the SHT45 de-creep pulse (masks RH, sets I2C_FAIL_SHT, interval 8 h)
and the room's own temperature ramp, which was +0.24 K/h over the last 30 min --
down from +1.23 K/h this morning but not zero, so the target still moves.
