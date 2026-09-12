# BAT54W-G reverse leakage, digitized from Vishay Fig. 3

Digitization of `../BAT54W-G-vishay-85885-rev1.1.pdf`, page 2, **Fig. 3 —
Typical Reverse Current vs. Reverse Voltage vs. Various Temperatures**, produced
2026-09-12 for the D8 clamp-leakage question.

## STATUS: NOT YET HUMAN-VERIFIED

The overlay has been shown to Fab but **no approval has been given**, and the
standing rule for this tool is that an unvalidated chart category needs
human-verified overlay samples before its output is used. Treat every number
here as provisional until that happens.

## What these numbers are, and are not

They are a **digitized reading of a typical curve**. They are not a device
measurement, not a worst case, and not a qualification of any production part.

Vishay publishes exactly one leakage *maximum*: `IR = 2 µA at VR = 25 V, 25 °C`,
against roughly 0.2 µA typical at the same point — call it a 10× max/typ spread.
Nothing in this directory bounds a production part at 85 °C.

## Files

| file | contents |
|---|---|
| `values.json` | the digitizer's full output: per-temperature curves in (V, A), both axes' fitted models and ticks, plot box, and diagnostics |
| `curves.csv` | the same curves flattened to `temperature_c, vr_v, ir_a` — 3666 points |
| `interpolated.csv` | the derived table below |
| `overlay-p02-fig3.png` | source-versus-extracted overlay, the artifact a human review must look at |

## Result

All at **VR = 1.3314 V**, with the offset each leakage produces across the VIN
divider's source impedance R26‖R27 = 9.0 kΩ:

| Tj | Ir | offset |
|---|---|---|
| 25 °C | 0.051 µA | 0.5 mV |
| 50 °C | 0.830 µA | 7.5 mV |
| 75 °C | 4.585 µA | 41.3 mV |
| **85 °C** | **8.662 µA** | **78.0 mV** |
| 100 °C | 22.491 µA | 202.4 mV |
| 125 °C | 93.162 µA | 838.5 mV |

### Why 1.3314 V and not 1.2 V

VIN_MON sits near 1.19 V in normal operation, but the 100 °C curve **is not
plotted below 1.3314 V**, and the digitizer refuses to extrapolate rather than
invent the missing end of a curve. 1.3314 V is the largest voltage at which all
five curves exist. Leakage rises with reverse bias, so this is conservative for
the real node — but the figure must not be quoted as "at 1.2 V".

### Interpolation method for 85 °C

85 °C is not plotted. It is interpolated **between the plotted 75 °C and 100 °C
curves**, linearly in `log10(Ir)`:

```
log10(Ir_85) = log10(Ir_75) + (85 - 75)/(100 - 75) × (log10(Ir_100) − log10(Ir_75))
             = 0.6614       + 0.4 × (1.3520 − 0.6614)          [Ir in µA]
             = 0.9376                    →  8.662 µA
```

Log space is the point. Saturation current is exponential in temperature, so
interpolating linearly *in current* between 4.585 µA and 22.491 µA would give
11.75 µA — 36 % high. The digitizer refuses to extrapolate outside 25–125 °C
entirely.

## Reproducing

```sh
cd ~/dev/pv/ee/datasheet-chart-digitizer      # commit d6b59bc
.venv/bin/dsdig digitize-reverse-leakage --dpi 400 --out <outdir> \
    ~/dev/ee/hw/o2-probe/datasheets/BAT54W-G-vishay-85885-rev1.1.pdf
```

The chart class is new (`digitize-reverse-leakage`), written for this panel.
Its self-checks, recorded in `values.json` under `diagnostics`:

- `temperature_identity_from_noncrossing_vertical_order` — temperatures assigned
  by vertical order, which is sound only because reverse-leakage curves cannot
  cross;
- `noncrossing_verified_over_5_curves` — that assumption was *checked*, not
  assumed: a crossing would have raised rather than been reported;
- `current_axis_unit_read_from_panel_as_uA` — the µA prefix was read from the
  axis title, not assumed. Vishay plots µA, Nexperia nA, onsemi sometimes mA,
  and the printed decades are identical in all three.

## The decision this fed

Fab, 2026-09-12: relax D8's leakage gate and record the number. The original
`Ir ≤ 1 µA at 1.2 V, 85 °C` gate was derived from an 18 mV budget that was
itself picked rather than required. VIN_MON is health telemetry, nothing scales
by it, and its thresholds are 7 V and 15 V on a nominally 12 V rail.

**The error is signed.** D8's cathode is on VIN_MON, so its reverse leakage
flows out of the node into AGND and pulls the reading *down*. A low-reading
monitor moves toward the 7 V undervoltage trip and never toward 15 V, so the
margin that matters is the 5 V one — not the 3 V to the upper threshold.
0.79 V of apparent error against 5 V of margin is the accepted position.
