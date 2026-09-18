# The probe is degrading in the pile — 2026-09-18

**Times UTC** (local = UTC+2). Dated record of one observation pass; add a new
one rather than rewriting this. Nothing was touched on the probe or the node to
produce it — all of it is read out of VictoriaMetrics.

## 1. Summary

Buried 2026-09-17 09:47, the probe ran ~14 h publishing oxygen with only
`TEMP_OVER` set. From ~00:13 on 09-18 it began raising converter and bus faults,
and at **07:12 all four I²C devices failed simultaneously** for three
consecutive frames. It recovered, and is settling as this is written.

The sequence — ADC range, then settle restarts, then I²C — is the **same order,
at the same temperature**, as the 2026-09-11 17:11 event that ended in the
board/AFE failure which took out U8, U3 and R36.

## 2. Timeline

Fault words decoded against `firmware/src/faults.h`:

| word | bits |
|---|---|
| 512 | TEMP_OVER |
| 513 | SETTLING + TEMP_OVER |
| 517 | SETTLING + I2C_FAIL_ADS + TEMP_OVER |
| 2560 | TEMP_OVER + ADC_RANGE |
| 2561 | SETTLING + TEMP_OVER + ADC_RANGE |
| **32799** | SETTLING + I2C_FAIL_**LMP** + **ADS** + **TMP** + **SHT** + HEATER_DISABLED |

| time | faults | what changed |
|---|---|---|
| 09-17 09:47 | — | buried; chamber 21.8 → 53 °C in 11 min, 58 °C by 10:20 |
| 09-17 12:00–22:00 | 512 | oxygen swinging 2.9–17.8 %vol, `settle_s` 0 throughout |
| 09-17 23:30 → | 512 | chamber climbs 74 → 77 °C |
| 09-18 00:13 | 2560 | **ADC_RANGE** — converter saturated or out of window |
| 09-18 04:57 | 513 | **first settle restart** (`settle_s` 514) |
| 09-18 05:34–05:52 | 2561 | ADC_RANGE + repeated restarts; no current published; chamber peaks **78.8 °C** |
| 09-18 07:05 | 517 | **I2C_FAIL_ADS** |
| 09-18 07:12–07:23 | **32799** | **total I²C bus failure**, three frames, no sensor data at all |
| 09-18 07:30 | 513 | recovered; `settle_s` 570 → 349, cell 59.9 µA, chamber 75.0 °C |

Four sensors on one bus failing together is a bus or supply event, not a
sensor. `HEATER_DISABLED` (bit 15) is set in v0 always and carries no
information here.

## 3. Conditions, against the cell's ratings

| | measured 09-18 | DS-0637 |
|---|---|---|
| chamber T | 75.0–78.8 °C | −40…+60 °C |
| chamber RH | 88 → **91 %**, rising | 15–90 % continuous |
| dew margin (chamber − dew pt) | **3.3 K → 2.2 K**, closing | — |

Dew point computed from the published `t_chamber_c`/`rh_chamber_pct` (Magnus),
because the probe's own `dew_margin` is in the truncated block: 72.8 °C against
a 75.0 °C chamber. `heater_duty_pct` has been 0–6 % throughout and cannot open
that margin — and note it is a **60 s trailing mean** since FW 0x0025
(ee 5ee0b52), so brief pulses are smoothed out of it. Which firmware the buried
probe runs is **not currently observable** — `gas_fw_version` is truncated.

**The heat is the pile's, not the heater's.** There is no setting to back off.

## 4. The 2026-09-11 precedent

From the hot-data inventory in the farming memory note
`o2-cell-tempco-is-unmeasured`: 09-11 17:11–17:20, cell-side 78.8 °C, AFE
80.5 °C, RH 95 % — current collapsed 99.5 → 42 µA, settle restarts, then
board/AFE failure (234 µA, −21 µA, bus-silent reset at 18:04). U8, U3 and R36
were replaced on 09-12.

Same peak temperature, same order of symptoms. **This is a resemblance, not a
demonstrated identity** — the 09-11 event had a wet steam exposure driving it
and this one does not, and the front end is the repaired one.

## 5. What cannot be seen, and why it matters now

Every channel that would characterise this failure is in the diagnostic block
the node is truncating at DR0: `va_mv`, `vref_mv`, `lmp_readback`, `t_afe_c`,
`t_ext_c`, `ads_fail_count`, `i2c_errs`, `settle_restarts`, `sample_seq`,
`reset_cause`.

The specific question that cannot be answered: **did the 3V3A rail sag at
07:12?** That is the obvious cause of four simultaneous I²C failures, `VA_LOW`
(bit 6) would say so, and `va_mv` would quantify it — and neither is arriving.
This is now the most expensive consequence of the DR0 truncation.

**Decoding caveat.** Two frames (09-17 22:53, 09-18 06:54) decoded `faults = 0`
with chamber and RH absent. That is not credible at 76 °C — TEMP_OVER is
latched — and at DR0 records are identified **by length alone**, so they are
most likely mis-identified records. Treated as suspect, not as data. They do not
affect the sequence above.

## 6. Consequence for OVEN-SOAK-TEST.md

That plan's §6 abort criteria are written for a controlled oven run. **The pile
is already meeting three of them**, unattended:

* *"a fault other than 512 (e.g. 2048 ADC_RANGE, VA_LOW, I²C errors)"* — 2560,
  2561, 517 and 32799 all seen;
* *"`settle_s` restarting"* — repeatedly since 04:57;
* *"cell current outside 80–120 µA"* — the range since burial is **1.95 to
  59.9 µA**.

The plan also rests on the cell surviving to be soaked ("this is the only probe,
and it is the one in the pile"). That premise is now in question, and the soak
is the measurement that would close the >36 °C tempco gap. Extraction timing is
Fab's call; this note only records that the window is not open indefinitely.

## 7. Correction carried over from the same day

An earlier reading of this pile data claimed the hot oxygen values were
"inflated ~43 % by the extrapolated tempco". **Wrong, in size and sign.**
Decomposed at P 930 hPa against CAL_TEMP 37.71 °C:

| | air 24.0 °C / 52.4 %RH | pile 74.2 °C / 87.5 %RH |
|---|---|---|
| dry-basis `1/(1−p_w/P)` | 1.017 | **1.548** (p_w 329 hPa) |
| tempco `(T/T_cal)^0.75` divisor | 0.967 | 1.087 |

Product predicts a 1.354 change in the published `pct_vol / cell_ua` ratio
against 1.430 observed. So **humidity +52 %, tempco −11 %**: the dry-basis term
dominates and the T-law makes the number *lower*, consistent with
OVEN-SOAK-TEST.md §8's expectation that the firmware under-reads hot.

The practical consequence is that the pile reading's largest multiplier is a
1.55× correction resting on the SHT45 reporting 87.5 %RH at 74 °C — and
OVEN-SOAK-TEST.md §6 deliberately excludes a humid point ("the pile case needs
its own design, later"). The unvalidated term is the dominant one.

## 8. Open

* Did 3V3A sag at 07:12? Not answerable until the diagnostic block returns.
* Are the intervals between episodes shortening? Two hours of data is too few
  to say; worth re-checking before deciding on extraction.
* Is the oxygen swing of 09-17 real pile gas? Section 2 of this note does not
  settle it — but every instrument-side channel that IS published (chamber T
  ±0.7 K, RH 87–88 %, dew margin 3.3 K, heater 0–6 %) was flat across a 6.5×
  current swing, and `settle_s` was 0 throughout, so the cell bias was
  continuous for all of it.
