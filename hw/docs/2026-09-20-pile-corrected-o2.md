# The 2026-09-17 in-pile capture, corrected with the soak-fitted cell model

Status: measured, one capture. Figures in `2026-09-17-pile-evidence/`:
`o2-pile-corrected-24h.png` (the whole deployment, USE THIS ONE) and
`o2-pile-corrected.png` (the first afternoon only, written before Fab pointed
out the probe stayed in overnight). Data `o2-pile-corrected-24h.csv`, raw
export `pile-export-full.jsonl`. Produced by
`firmware/tools/o2p_pile_correct.py` (new).

## 1. There IS an in-pile capture, and it was not the soak

Looking for the probe's service temperature I found that on 2026-09-17 the probe
spent about four hours buried in the Strassenmiete, between two bench sessions.
It is the only in-pile record the probe has.

| | |
|---|---|
| in air on the bench | until 11:01, t_ext 19.9-20.3 C, stable |
| carried and inserted | 11:47, t_ext climbing 28.5 -> 52 C in 13 min |
| buried | 09-17 11:47 -> 09-18 11:59 local, 24.2 h |
| hottest | 09-18 ~07:00, chamber 77.4 C |
| removed | between 09-18 11:59:41 (chamber 67.4) and 12:14:13 (44.4, cell back to 99 uA) |

It is the pile and not a bench heater: heater duty ran 0.0-3.5 % throughout, which
cannot take a probe to 77 C, and the oxygen fell below 1 %vol, which no bench does.

**Read the 24 h figure, not the afternoon one.** My first pass stopped at 15:44
because that is where `gas_t_ext_c` stops, and I mistook the end of one SERIES
for the end of the deployment. The probe was in the pile for another twenty
hours and they are the most interesting part of the record.

## 2. Why nothing here could be fitted

In the oven the probe sat in air, the dry oxygen fraction was known, and every
wiggle was instrument - so n and alpha were fitted. In the pile the oxygen IS the
unknown. `o2p_pile_correct.py` therefore only APPLIES the soak model; a tool that
fitted on pile data would be fitting the biology into the instrument.

It reads the law constants out of `src/o2.h` at run time rather than copying them,
so the figure cannot drift away from the firmware it describes, and it mirrors
`o2p_cell_t_lnf()` exactly: 0.75 to the knee, a straight line in ln T to the
41.37 C anchor, a second to the 75.81 C anchor, held above.

The absolute scale rests on **one** anchor window - 19 samples at 20.05 C in
ambient air, 46 minutes before insertion, assumed 20.946 %vol dry. Cell current
99.692 uA, scatter 0.03 %. This capture cannot measure the cell constant.

Gating dropped 74 rows for ADC_RANGE (0x0800 and 0x0A00), 30 settling, 23 for
COMP_OK clear and 3 incomplete. **219 rows survived, 131 of them without a
cell-side temperature** - see section 4.

The window guard earned itself immediately: a bare `HH:MM` anchor matched BOTH
days, built the air anchor out of two windows 24 h apart, and reported 12.28 %
scatter as an absolute scale. Specs are now date-aware and an anchor scatter
over `--max-anchor-scatter` (1 %) is a refusal, not a printed number.

## 3. The result

The whole capture sits between 28.5 and 77.2 C - that is, almost entirely ABOVE
the 36 C where the 0.75 law's evidence ends, and the night sits ABOVE the
75.81 C top anchor, where the knee model HOLDS rather than extrapolating.

| local | T_cell | RH | firmware n=0.75 | knee model | knee vs fw |
|---|---|---|---|---|---|
| 09-17 11:47 | 28.5 C | 57.8 | 17.585 | 17.585 | +0.00 % |
| 09-17 12:22 | 56.2 C | 68.9 | 16.830 | 17.556 | +4.31 % |
| 09-17 16:32 | 66.1 C | 85.5 | 8.038 | 8.583 | +6.78 % |
| 09-17 19:04 | 70.9 C | 87.0 | 4.615 | 4.986 | +8.04 % |
| 09-18 00:35 | 74.4 C | 88.2 | 9.358 | 10.161 | +8.58 % |
| 09-18 03:37 | 76.0 C | - | 0.756 | **0.827** | +9.4 % |
| 09-18 04:32 | 76.6 C | 87.9 | 3.551 | 3.885 | +9.41 % |
| 09-18 11:59 | 67.4 C | 91.2 | 17.681 | 18.861 | +6.67 % |

The two agree to 0.00 % at 28.5 C by construction - below the knee the knee model
IS the 0.75 law - and diverge monotonically with temperature to **+9.4 % in the
small hours**. **The correction is not a detail at the bottom of the range; the
pile lives where it is largest.**

The windrow went anaerobic overnight: the corrected oxygen fell below 1 %vol
between roughly 02:00 and 04:00 on 09-18 at 76 C, and swung between ~2 and
~16 %vol several times through the night. The swings are real in the sense that
all four curves show them, but nothing here establishes their CAUSE.

`FAULTS` carried TEMP_OVER (0x0200) from 12:54 onward, whose own comment in
`faults.h` reads "gas > 60 C: extrapolated, still valid". The firmware was
already saying it was extrapolating. It was.

## 4. The cell-side temperature sensor was absent for 22.8 h of it

`gas_t_ext_c` stops at 09-17 15:44:05 and does not return until 09-18 14:31:57 -
a 22.80 h hole covering nearly the whole deployment. `gas_dew_margin_cell_k`,
the other cell-side quantity, has **the identical gap to the second**, so this
is the cell-side chain being unavailable and not one field lost in a payload.
`COMP_OK` stayed set throughout: `o2p_cell_temperature()` fell back to the
chamber, exactly as designed, and the probe went on publishing.

Two things about it are NOT explained:

- **No TMP117 I2C fault.** `O2P_F_I2C_FAIL_TMP` (bit 3) appears in only 3
  samples all night, inside a 0x801F word that also carries the other three I2C
  fails. The chamber and tip TMP117s reported normally throughout. Whatever made
  the cell-side reading unusable did not announce itself in FAULTS.
- **It did not come back on removal.** The probe left the pile before 12:14 on
  09-18 and `t_ext` was still missing through 13:00. It returned at 14:31:57,
  which is the minute the NODE rebooted - not the minute the probe did (probe
  uptime says it booted 13:32). That points away from pile heat and towards
  something that survives a probe boot.

**This barely matters for the knee model and matters for the 0.75 law.** The
chamber runs about +2.0 K above the cell where both exist. On the plateau the
knee law is flat, so that 2 K costs:

| | gain at 75 C | gain at 77 C | cost of +2 K |
|---|---|---|---|
| knee model | 1.039268 | 1.039265 | **-0.0003 %** |
| 0.75 law | 1.135005 | 1.139892 | +0.4305 % |

A factor of about 1400. The model being flat where the probe is hot makes it
insensitive to exactly the sensor that failed. That is luck, not design - but it
does mean the overnight curve does not rest on the reconstruction.

## 5. What this figure does NOT establish

- **The 12:00-13:30 excursions are uncharacterised.** Oxygen swings 13 -> 18 %vol
  within minutes. That is far too fast for windrow biology and is more likely gas
  drawn down the insertion channel while the probe settled. It is not evidence of
  anything about the pile, and it is not a model artefact either - the three
  curves track each other through it.
- **131 of 219 rows are compensated off the chamber**, not the cell. See
  section 4 for why that is nearly free here and would not be below the knee.
- **Uplink cadence varies 1-30 min.** The figure marks real samples; lines
  across the sparse stretches are interpolation.
- **The published curve carries its own calibration era.** It sits above both
  model curves because it is anchored on the probe's stored air point, not on this
  window's anchor. The offset is not a model difference.
- **41.4-75.8 C is still two anchors and a straight line**, and this entire
  capture falls inside that span. The 55-60 C run remains the thing that would
  make the middle measured rather than interpolated - and this figure is the
  argument for running it, since 55-60 C is exactly where the probe works.

## 6. Version collision, confirmed

`O2P_FW_VERSION` in this tree is already `0x0027`, taken by another session's
dry-air idle gate. The knee model must be `0x0028`.
