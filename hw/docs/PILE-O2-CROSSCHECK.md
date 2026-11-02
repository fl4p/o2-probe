# Cross-checking the pile O₂ reading with the OxyScan 300

**Written 2026-09-17, not yet run.** The buried probe published 5.2–6.5 %vol dry
at 72–74 °C on the evening of 09-17, with fault 512 (`TEMP_OVER`) set: above
60 °C the cell is outside DS-0637's rating and the conversion extrapolates. The
estimated error is about −6 % / +14 % of the value, and two hot runs suggest the
firmware reads 4–5 % low (`OVEN-SOAK-TEST.md` §1). Nothing has ever checked the
probe against a second instrument **in the pile**.

Fab has a **UMS OxyScan 300**. It is for dissolved oxygen, and it measures
exactly the right quantity anyway: a Clark-type membrane sensor answers to
oxygen **partial pressure**, in liquid or in gas.

## 1. What the instrument gives us

From the UMS manual (`ums-gmbh.de/Download/files/OxyScan_300_Bedienungsanleitung.pdf`):

| | |
|---|---|
| sensor | electrochemical membrane (Clark type), consumes a little O₂ |
| calibration | in its own chamber, on a **damp sponge** = water-vapour-saturated air |
| units | %Sat, or **mmHg** — partial pressure directly (PC software, Display tab) |
| barometer | built in, 50–1150 mbar, **±0.5 mbar** |
| temperature | 0–60 °C, 0.1 °C |
| resolution | 0.1 %Sat |
| orientation | the tip must never sit higher than the back of the sensor |

Two things this solves at once:

* **mmHg mode removes the saturation convention.** %Sat is referenced to
  water-vapour-saturated air, so a dry sample reads ~3.5 % high at 25 °C. In
  mmHg there is nothing to unpick.
* **Its barometer replaces the firmware's assumed 930 hPa**, which is ±2 % of
  the published reading on its own. Note the pressure on every visit, whatever
  else happens.

## 2. What it must not do

* **Never put it in the pile.** Sensor and meter stop at 60 °C; the pile core is
  at 74 °C. Sample through a tube and let the gas cool.
* **Keep the membrane wet.** Re-wet it from the calibration chamber sponge
  before the gas reading. A dry membrane drifts.
* **Keep exposure short.** Pile gas carries high CO₂ and traces of ammonia and
  organic acids; they do not fool a Clark cell but do age its electrolyte.
* **Condensation on the membrane is fine** — it is a dissolved-oxygen sensor,
  and a water film in equilibrium with the gas carries the same pO₂.

## 3. Procedure

1. **Calibrate** in the chamber on the damp sponge, per the manual. Note the
   meter's barometric pressure **P**.
2. **Switch to mmHg** if the PC software is at hand. If not, use %Sat and §4.2.
3. **Take the sample at the probe's depth.** Push a tube (stainless or PTFE)
   in beside the buried probe, to the same depth. Purge at least three tube
   volumes with a hand or aquarium pump, then fill a bag or a jar and close it.
4. **Let it cool** to under 40 °C, 10 minutes or so. Water will condense; that
   is expected, and it means the gas in the bag is saturated at the bag's
   temperature.
5. **Read.** Sensor tip down, in the bag's gas space, not in the condensate.
   Wait for a stable reading, at least 2 minutes. Note pO₂ (mmHg), the sensor's
   temperature, and P.
6. **Bracket with room air**, before and after: air should read about
   0.2095 × (P − p_sat(T)) in mmHg, or 100 %Sat.
7. **Three samples**, a few minutes apart. The pile's own gas moved 5–7 %
   within minutes on 09-17, which is larger than the instrument error.
8. **Note the time of each sample.** Compare against the probe's uplink nearest
   that minute, not against a daily mean.

## 4. Turning the reading into a comparison

The buried probe publishes **dry-basis** volume fraction. Convert the meter's
reading the same way.

### 4.1 From mmHg

```
p_O2 [hPa] = reading [mmHg] * 1.33322
O2_dry [%] = 100 * p_O2 / (P - p_w)
```

with P from the meter and p_w = p_sat at the bag temperature when the bag has
condensate in it (Magnus: p_sat = 6.112·exp(17.62·T/(243.12+T)) hPa).

### 4.2 From %Sat

%Sat is referenced to water-vapour-saturated air at the sensor's temperature
and pressure, so

```
p_O2 [hPa] = (%Sat / 100) * 0.2095 * (P - p_sat(T))
```

and then the same dry-basis step. The two routes differ by the saturation
convention only; if both are available, record both.

### 4.3 What to expect if the probe is right

Probe reading 6.5 %vol dry, bag at 25 °C and saturated, P = 930 hPa:

| | value |
|---|---|
| p_w at 25 °C | 31.7 hPa |
| p_O2 expected | 0.065 × (930 − 31.7) = **58.4 hPa = 43.8 mmHg** |
| room air for comparison | 0.2095 × 898 = 188 hPa = **141 mmHg** |
| the same as %Sat | about **31 %** |

If the probe reads 4–5 % low as the hot runs suggest, expect about 46 mmHg
(33 %Sat) instead. **That 5 % difference is inside the instrument's own error
in gas, so this check cannot resolve it.** What it can do is decide the things
that matter now:

* is the pile core **below 10 %** (43.8 mmHg vs 67 mmHg — unmistakable);
* is it **above or below 5 %**, the anaerobic line (43.8 vs 33.7 mmHg);
* has the cell lost sensitivity in the heat — a 30 % loss would show as the
  meter reading about 63 mmHg against the probe's 43.8.

## 5. Recording

Add the numbers to `farming:docs/` as a dated note, with: the meter's P, each
sample's raw reading and units, bag temperature, the computed dry-basis
percentage, the probe's published value at that minute, and its
`gas_t_chamber_c`, `gas_rh_chamber_pct` and `gas_cell_ua`. If the two disagree
by more than 20 %, that is a result about the buried probe, not about the meter,
and the calibration case in `OVEN-SOAK-TEST.md` §8 gets stronger.
