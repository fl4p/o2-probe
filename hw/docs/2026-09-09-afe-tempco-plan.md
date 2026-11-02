# Characterising the AFE tempco: plan, tooling, and the state of the data

Status 2026-09-09 17:00 CEST: **in progress, no measurement yet.** The probe is out
of its enclosure in free air on the node, uplinking every 30 s, and everything it has
sent since it came back at 16:11 sits at room temperature. Nothing here is a result;
this note is the experiment design, the analysis tool, and the record of why the first
attempt could not have produced a number.

## What "the AFE tempco" is

The published cell current is

    I = (0.67 · VREF − VOUT) / R_TIA          R_TIA hardcoded 7000 Ω (sampler_logic.h)

`docs/2026-09-08-hot-bath-run.md` §Reason 3 bounds every term but one: ADS1119 gain
2 ppm/K, offset 0.1 µV/K, `TcVOS_RW` ±8 µV/K at the configured bias, VREF cancels.
`R_TIA` is the LMP91000's internal poly resistor, SNAS506I Rev I gives it 5 % accuracy
and **no temperature coefficient**, and it sits on the same die as the temperature
sensor that `T_AFE` (0x002C) reads. So the AFE tempco is, to within those bounds,
tc(R_TIA), and `T_AFE` is the right variable to fit it against. The hot-bath note's
decomposition of the observed ~800 ppm/K was

    a_cell · β + tc_RTIA · γ = 797 ppm/K

with β the cell's and γ the AFE's coupling to the tip. `T_AFE` measures γ directly.
What is still needed is tc_RTIA on its own, which needs a run where the cell does not
contribute — or two runs where it contributes differently.

A magnitude to expect: on-chip diffused or poly resistors are commonly several
hundred to over a thousand ppm/K. It is entirely possible that tc_RTIA · γ is most of
the 797. That is a prior, not a finding; the point of the run is to replace it.

## Why today's data cannot answer it

`T_AFE` has existed since codec `e2fd562` (2026-09-08 16:25 CEST). Between then and the
AFE collapse later that evening the cell current was not valid (`afe_mv` 24 mV, the open pin 11
of `2026-09-09-afe-rework-debug.md`). Since the reworked board came back at 16:11 CEST
today:

| | value |
|---|---|
| uplinks with `T_AFE` and a valid current | 36 (plus 17 still settling) |
| `T_AFE` | 24.24 … 24.61 °C, span **0.37 K** |
| `T_TIP` / `T_CHAMBER` | 23.5 / 23.4 °C |
| cell current | 99.13 µA mean |
| heater duty | 0 |

A 0.37 K span is three quanta of the register (the ADC's 1 mV step is 0.12 K through
the 8.2236 mV/K slope). The analysis tool below refuses it, as it should.

Pulled from `/api/v1/export`, not a range query, on 2026-09-09 16:40 UTC.

## The board, so the plan makes physical sense

From `PLACEMENT.md`, board-local y along the 107 mm length, cable end at 0:

| item | y |
|---|---|
| MCU U6 (`T_DIE`) | 44.5 |
| **LMP91000 U7 (`T_AFE`)** | **79.5** |
| pot line / thermal-barrier slots | 82 – 85 |
| SGX cell centre | 93.5 |
| heater elements RH1/RH2 | 96.5 |
| tip sensors TMP117 U10, SHT45 U12 | 101.5 – 102.5 |

The AFE is 17 mm behind the heater and on the cold side of the barrier slots. On
2026-09-08 a 78 °C tip put the MCU at 49 °C from a 26 °C ambient (γ_MCU ≈ 0.44), so the
AFE, halfway between, should see somewhere around half to two thirds of a tip
excursion — a 40 K tip step should move `T_AFE` by 20 K or more. That is plenty. It is a
guess until the run measures γ; the tool prints γ on every run.

## Experiment A — dummy load plus ring heater (recommended, do this first)

Replace the cell with a resistor pair in the cell socket, then drive the tip heater.
With no cell there is no cell tempco, no gas dependence and no 60 °C envelope; every
temperature-dependent thing left in the loop is the AFE. This is the same substitution
that settled the 2026-09-04 AFE failure (`AFE-BRING-UP-POSTMORTEM.md`), with values
chosen to reproduce the air current instead of a near-zero one.

**Dummy.** `BIAS_SIGN 0`, 24 % of VREF puts RE 600 mV above WE. A resistor R_d from RE
to WE then carries 600 mV / R_d into the TIA, supplied by CE through a second resistor:

| position | value | why |
|---|---|---|
| RE – WE | **6.04 kΩ**, 0.1 %, **≤ 25 ppm/K** metal film (E96) | 600 mV / 6.04 kΩ = 99.3 µA, the air point this cell sits at |
| CE – RE | 1 kΩ, anything | gives A1 a path; drops ~0.1 V, well inside CE headroom |

Use the lowest-tempco resistor to hand for R_d: its tempco subtracts directly from the
result. A 25 ppm/K film limits the answer to ±25 ppm/K, which is fine against a
quantity expected in the hundreds; a 50 ppm/K thick-film chip is not.

**From stock (InvenTree, 2026-09-09).** Nothing at 6.04 kΩ, but better parts than the
plan asked for, all 0603, so they need a carrier (two header pins or a protoboard
scrap) to sit in the cell socket:

| R_d option | parts in stock | current at 600 mV | TCR |
|---|---|---|---|
| 2 × TNPU06033K01BZEN00 in series = 6.02 kΩ | 10 | 99.7 µA, the actual air point | ±5 ppm/K (Vishay TNPU e3, `Z` code) |
| 2 × P2TC0603D1002LNTA in parallel = 5.00 kΩ | 4 | 120 µA | ±2 ppm/°C (Vishay P2TC) |
| 1 × TNPU06037K50BZEN00 = 7.50 kΩ | 10 | 80 µA | ±5 ppm/K |
| CE – RE: RC0603FR-071KL 1 kΩ 1 % | 25 | — | irrelevant, it is outside the measured path |

The series pair of 3.01 kΩ is the pick: it reproduces the cell's own operating point
to 0.5 %, and 5 ppm/K is 1 % of the quantity expected. CMF555K0000BHEK (5 kΩ axial,
5 in stock) would drop straight into the socket, but its TCR code was not verified.

VREF drops out completely here: the bias is 0.24 · VREF, the internal zero 0.67 · VREF,
and the ADC's reference is the same rail, so the output code depends only on
R_TIA / R_d. The slope of the published µA against `T_AFE` is tc(R_TIA) − tc(R_d) plus
the bias DAC's ratio drift, and `TcVOS_RW` bounds the last of those at about
13 ppm/K (8 µV/K over 600 mV).

**Drive.** `tools/o2p_thermal.py` is the fixture: it saturates the RH loop, pins
`HEATER_MAX_DUTY`, square-waves the heater, logs every 5 s, and restores the probe on
every exit path including Ctrl-C. Over the bridge board's serial line:

```sh
cd ~/dev/ee/hw/o2-probe/firmware
python3 tools/o2p_thermal.py --port /dev/cu.usbserial-XXXX --preflight
python3 tools/o2p_thermal.py --port /dev/cu.usbserial-XXXX afe-tempco-A.csv \
    --duty 60 --half 1500 --cycles 2 --tip-max 80 --poll-csv afe-tempco-A-poll.csv
```

`--tip-max 80` is deliberate and only legitimate **with the dummy fitted**: the 55 °C
default guards DS-0637's cell limit, and there is no cell. Two 25-minute halves at
60 % should walk the tip past 60 °C and back, which is a 20 K-plus AFE excursion twice.
Both the up and the down leg are fitted, so any hysteresis between them is visible in
the residual rather than hidden in the slope.

If the probe stays on the node instead of the bridge, the same run can be driven with
`TIP_SETPOINT` (0x0049) plus its consent register, and the data comes back through
VictoriaMetrics at 30 s. The bridge is better: six times the samples, and the fixture
restores itself.

**Analyse.**

```sh
python3 tools/o2p_tempco.py --csv afe-tempco-A.csv --mode dummy --plot afe-tempco-A.png
```

Output: the slope in ppm/K of the mean current with its standard error, R², the
residual RMS, the `T_AFE` span, and γ = dT_AFE/dT_TIP.

## Experiment B — the real cell, two decorrelated excursions

With the cell fitted the current follows both temperatures, and a single heater run
moves them together. The tool then finds `T_AFE` and the lagged chamber temperature
collinear and refuses to split them (it prints the combined slope, which is all such a
run supports). To separate the two without the dummy you need two legs whose
dT_AFE : dT_cell ratios differ:

1. **AFE end warm, tip cold.** Warm the board around y = 80 mm from the cable side —
   a lamp or a warm block against the back of the board, nothing that blows on the
   tip — until `T_AFE` has risen 10 K or more while `T_CHAMBER` moved a fraction of
   that. Let it settle, then let it cool.
2. **Tip warm, AFE following.** The ring heater as in A, but `--tip-max 55` and
   watch the chamber RH: this leg is inside the cell's envelope or it is not usable.

Log the whole thing in one CSV and fit it in one call:

```sh
python3 tools/o2p_tempco.py --csv afe-tempco-B.csv --mode cell --plot afe-tempco-B.png
```

The tool scans the cell's lag constant τ (the ~10 min the hot-bath run found),
reports r(T_AFE, lagged T_CHAMBER), and only prints two numbers when |r| ≤ 0.95. The
cell number it prints is a_cell · β, the cell's apparent dependence on the *gas*
temperature; the cell's own tempco still needs the isothermal run the hot-bath note
asks for.

If A has been done, B collapses to one leg: `--afe-ppm-k <A's result>` fixes the AFE
share and the heater run alone yields a_cell · β.

## What was found while setting this up

- **The bench CSV writers were dropping `T_AFE`.** `o2p_poll.py` decoded 0x002C
  since `e2fd562` but its `CSV_COLUMNS` never listed it, and `DictWriter(...,
  extrasaction="ignore")` discarded it silently. `o2p_thermal.py` has the same
  schema, and `o2p_plot.py`'s temperature panel did not draw it. All three carry
  the column now, and the poll printout has an "AFE temp" line. Had experiment A
  been run through these tools before today, its log would have had every column
  except the one the run was for. `o2p_capture.py` (the SWD struct reader) still
  does not carry it; its layout is offset-fragile and was left alone.
- **`o2p_thermal.py` refused to start**: its self-check looked for `O2P_VIN_LOW_MV`
  in `main.c`, and the constant lives in `faults.h` now. Fixed to look where the
  constant is defined and to say which file disagreed.
- **The Grafana dashboard already plots `gas_t_afe_c`** (`oxygen.json`, temperature
  panel) — nothing needed there.

## Guard review, for `o2p_tempco.py`

1. *Unevaluable input.* Fewer than 20 usable rows or a `T_AFE` span under 8 K
   returns no number, prints why, and exits 2. A collinear cell-mode run returns no
   split. Rows that are settling, faulted (`O2P_FAULTS_INVALIDATE_O2`, checked
   against `faults.h` at startup) or missing a regressor are dropped and counted.
2. *Monotonicity.* There is no PASS verdict to flip; it reports a slope with its
   standard error or refuses.
3. *Preconditions.* The fault mask is compared with `faults.h` on every start and the
   tool exits 1 on disagreement.
4. *Source of truth.* Both loaders are exercised against each other in
   `test_tempco.py` on the same synthetic rows.
5. *Persistence.* Nothing is cached.
6. *Provenance.* The report names the mode, the rows used and dropped by cause, the
   span, and whether the AFE share was fitted or fixed.
7. *Known-bad calibration.* `test_tempco.py` plants +650 ppm/K and recovers it, feeds
   a flat run and a collinear run and checks both are refused, and confirms the
   decorrelated two-leg run of experiment B is separable.
8. *Fix vs mute.* The 8 K floor does not quiet a warning; it withholds a number that
   would have been noise.

Runtime: under a second on 1200 rows, pure Python.

## Provenance

Telemetry: VictoriaMetrics `/api/v1/export`, `gas_*` for `probe="3"`, 2026-09-06 to
2026-09-09 16:51 UTC. Geometry: `PLACEMENT.md`. Bounds: `2026-09-08-hot-bath-run.md`
§Reason 3 and the sources it cites (SNAS506I Rev I, SBAS925A, DS-0637). Firmware on
the probe: build `1196516090` per `gas_build_id`.
