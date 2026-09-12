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

VIN_MON sits near 1.19 V in normal operation. 1.3314 V is the **lowest** voltage
at which all five extracted curves exist — the low end of their common domain,
which runs 1.3314 … 29.6936 V. (An earlier version of this file called it the
"largest" such voltage, which is simply wrong: all five exist at 29.69 V too.
Corrected on the Codex session's reading, 2026-09-12.)

It is set by the 100 °C curve, whose extracted span starts there:

| Tj | extraction starts at |
|---|---|
| 125 °C | 1.0198 V |
| 25 °C, 50 °C | 1.1366 V |
| 75 °C | 1.2146 V |
| **100 °C** | **1.3314 V** |

**That is a limit of this extraction, not a statement about the source.** An
earlier version of this file said the 100 °C curve "is not plotted below
1.3314 V", which claims something about Vishay's figure that the digitizer
cannot establish: the curve may be drawn further left and merely not have been
recovered there, for instance where it runs into the frame or another trace.
Establishing where the printed curve truly begins needs a look at the figure,
not at this JSON.

Either way the digitizer refuses to extrapolate rather than invent the missing
end, so 1.3314 V is the honest query point. Leakage rises with reverse bias, so
evaluating at 1.3314 V is conservative for a node sitting at 1.19 V — but the
figure must not be quoted as "at 1.2 V".

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

## The decision this fed — and what it does NOT rest on

These are two separate things and are deliberately kept apart, because the first
is settled and the second is not.

**Fab's decision, 2026-09-12, settled:** retain D8 as BAT54W-G, relax its
leakage gate, and record the number. The original `Ir ≤ 1 µA at 1.2 V, 85 °C`
gate was derived from an 18 mV budget that was itself picked rather than
required. VIN_MON is health telemetry, nothing scales by it, and its thresholds
are 7 V and 15 V on a nominally 12 V rail. That decision rests on *what VIN_MON
is for*, not on any value in this directory, and it does not become unsettled if
the digitization is later corrected.

**The 0.79 V figure, provisional:** the offset referred to the rail, derived
from the unapproved 8.662 µA above. It illustrates the margin; it is not the
basis of the decision. If human verification revises the digitization, this
number changes and the decision does not.

**The error is signed** — this part is topology, not measurement, and holds
whatever the leakage turns out to be. D8's cathode is on VIN_MON, so its reverse
leakage flows out of the node into AGND and pulls the reading *down*. A
low-reading monitor moves toward the 7 V undervoltage trip and never toward
15 V, so the margin that matters is the 5 V one — not the 3 V to the upper
threshold.

(Separately, and not superseded by the above: describing 15 V as the "nearest"
threshold to 12 V was correct and describing it as 5 V away was not. The Codex
session caught that; it is a plain arithmetic error of mine, distinct from the
signed-error argument, which is why both are recorded.)
