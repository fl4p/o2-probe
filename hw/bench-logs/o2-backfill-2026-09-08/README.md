# O2 back-fill, 2026-09-08

`gas_pct_vol` in VictoriaMetrics was recomputed from the retained raw channels
(`gas_cell_ua`, `gas_t_chamber_c`, `gas_rh_chamber_pct`) using the model
committed to the probe on 2026-09-08 00:04 CEST:

    cal_air_na 101652 nA   cal_air_frac 0.20867   cal_temp 27.29 C
    cal_p 963 hPa   tempco 2840 ppm/K   alpha 0.402   ASSUMED_P 963 hPa
    K = 434336 nA

Raw channels were never written. Everything here is recomputable from them.

## The 23:01:52 step

Normalised cell output (T and RH removed) drops 0.51 % across 2026-09-07
23:01:52 CEST and stays down, against a background drift of +0.013 uA/h.
Unchanged across it: TIA gain and bias (TIACN<<8|REFCN = 0x0CCD), ADC
reference (2492-2496 mV), tip-chamber offset (+0.117 -> +0.106 K), and the
acquisition code (no diff in ads1119.*, lmp91000.*, or main.c's sampling path
across the whole v2-layout-era -> HEAD span). Two probe reboots at steady
temperature moved the cell +0.05 % and -0.01 %, so a reboot alone does not
do this. The jar was not opened. Cause unknown.

## Why gas_pct_vol keeps the step

The air point was taken AFTER the step, so it anchors K to the post-step cell.
That is a scheduling accident, not evidence: `o2p_calibrate_air` assumes the
jar holds air and solves for K, so the post-step reading equals the assumed
value by construction. Calibrating 30 minutes earlier would have put the step
on the other side. Nothing in the data says which side is correct.

`gas_pct_vol`          - what the instrument reported. Step intact.
`gas_pct_vol_stepadj`  - pre-step cell current scaled by 0.99492 so the two
                         segments join. CONDITIONAL on assuming the gas did
                         not change; do not treat as measurement.

An untested third possibility: Rev A has no barometer and `ASSUMED_P` is fixed
at 963 hPa, so a 4.9 hPa fall would produce this step with the cell reading
correctly. ~12 hPa/h is implausibly fast and the record is flat either side
rather than ramping, but it has not been checked against station data.

## Files
    exp_gas_*.jsonl.gz          pre-overwrite export (original series, old model)
    backup_pre_step_fix.jsonl.gz  state after the first back-fill
    import.jsonl.gz             first back-fill (no step correction)
    import2.jsonl.gz            step-corrected version (superseded)
    import_revert.jsonl.gz      current gas_pct_vol
    import_stepadj.jsonl.gz     current gas_pct_vol_stepadj
    backfill.py backfill2.py revert.py   recomputation
    drift.py step2.py           step detection and measurement
