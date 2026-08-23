# Rev-A oxygen-probe lumped model

This package is a calibratable, deliberately low-order model of the compost oxygen probe. It estimates the response of a protected SGX-style electrochemical O₂ cell behind a gas-permeable membrane and evaluates a simple anti-condensation heater. The checked-in configuration is **uncalibrated**: its useful output is sensitivity and experiment design, not a validated response-time prediction.

## Model boundary

The calibration and volume/area screening gas model is one well-mixed plenum. Its O₂ inventory obeys

`dn_O2/dt = x_breath dN/dt + G_window (x_external - x_plenum) - q_cell`.

For rising total inventory, `x_breath` is the external composition; for falling inventory, it is the plenum composition. This is a simple well-mixed make-up/expulsion assumption, not a compost pressure-flow model. The second term is installed-window conductance, and the third is electrochemical consumption calculated from current and Faraday's law. A fixed physical availability time scale smoothly limits the reaction near depletion, independent of solver step size. An optional empirical carrier lag can be promoted only with repeatable calibration and validation evidence; it is not interpreted as a rear-aperture flow law.

The SGX static transform uses O₂ partial pressure. The default dynamic state filters normalized logarithmic output, so raw current and the equivalent O₂ percentage at reference pressure retain the cell lag. Two O₂ outputs are intentionally separate: `o2_probe_equivalent_pct_at_reference_pressure` follows the physical cell state, while `o2_probe_pressure_compensated_pct_wet` divides by instantaneous measured pressure and can therefore jump during a pressure transient. `o2_probe_pct_wet` is the latter compatibility alias. Response-time metrics are invalidated whenever pressure changes materially across a step. Static zero, sensitivity and temperature coefficient are fitted separately from dynamics.

The V1 thermal plant is one heated-block RC state. Membrane temperature, membrane RH and dew margin are emitted only as **quasi-steady** values after a low-temperature-rate dwell. They are not condensation-transient predictions. A user-specified ΔT PI can run only after thermal resistance and capacitance have measured or fitted provenance.

Explicitly excluded from predictive V1 scope are condensation/evaporation dynamics, pressure-driven Darcy flow through compost, heater-induced enclosure convection, detailed enclosure breathing, biological O₂ consumption, and biofilm evolution. Wet and fouled behavior must be measured as named conductance multipliers before those regimes can run.

The existing long axial enclosure must instead use `simulate_axial_diffusion`. That model divides the membrane-to-potting gas path into finite volumes, applies the membrane as a Robin boundary, closes the potted end with a no-flux boundary, and reads the cell at its actual axial datum. Its effective diffusivity replaces unresolved PCB, package, port and cross-section obstruction; it is a sensitivity parameter until fitted to complete-path data. Heater power is rejected because no power/orientation/convection law is calibrated. Intrinsic membrane conductance is required: conductance fitted by the complete-assembly well-mixed model is explicitly rejected to prevent double-counting axial resistance.

## Install and run

From this directory:

```bash
uv sync --extra test
uv run o2-lumped simulate \
  --config config/uncalibrated_example.json \
  --experiment examples/dry_step.json \
  --out runs/dry-step

uv run o2-lumped sweep \
  --config config/uncalibrated_example.json \
  --sweep examples/geometry_sweep.json \
  --out runs/geometry-sweep

uv run o2-lumped prototype \
  --config config/uncalibrated_example.json \
  --study examples/prototype_study.json \
  --out runs/prototype-study

uv run o2-lumped voxel \
  --config config/uncalibrated_example.json \
  --study examples/voxel_candidate_study.json \
  --out runs/voxel-study

uv run pytest
```

Output directories are protected against accidental overwrite unless `--overwrite` is passed. Simulation and sweep outputs made with provisional values include `UNCALIBRATED.txt`; plots also carry an uncalibrated title where applicable.

## Required calibration order

1. `static`: declared steady windows are checked for reference, temperature and current stability, then plateau means fit `I0` and `K`; three or more distinct plateau temperatures are required before fitting the temperature coefficient.
2. `thermal`: open-loop measured-power steps fit block `Rth` and `Cth`; temporary membrane thermometry can fit only the quasi-steady coupling factor.
3. `bare`: fast reference transitions fit cell lag and experiment-specific input delays. Static parameters must already be measured or fitted.
4. `access`: carrier-only data may justify one generic empirical lag. Promotion requires at least three calibration experiments sharing an explicit replicate group, an identifiable fit with reportable bootstrap intervals, a bounded profile interval, ΔAICc of at least 6, and at least 10% standardized-residual RMSE improvement on held-out validation data.
5. `window`: installed-window transitions fit one conductance per tested free area. Cell parameters, effective plenum volume and free area must already be measured or fitted; calibration-time geometry overrides require their own measured provenance, uncertainty and source. An area-plus-access law needs at least five unique areas, valid reportable uncertainty on every conductance, and conditioning, residual and AICc checks. If no law is promoted, the exact nominal area must have been tested before a candidate configuration is emitted.

Each manifest declares observation uncertainties; those values set Gaussian residual weights for both fitting and profile likelihood. Quick fits use fewer than 1,000 valid moving-block bootstrap refits and are labelled diagnostic. Reportable intervals require at least 1,000 successful, interior, identifiable refits; experiment residuals stay in separate resampling groups, and failed or rejected refits, bound hits, profile intervals, absolute scaled information and the scaled-Jacobian condition number are reported.

## CSV and manifest conventions

`o2_reference_pct_wet` is wet-basis mole percent, and `pressure_reference_kpa` is total absolute pressure. Core columns are `time_s`, `o2_reference_pct_wet`, `pressure_reference_kpa`, and `temp_ambient_c`. `temp_inlet_c` is preferred for plenum inventory; ambient is an explicitly reported fallback. Current is `cell_current_mA`. Heater power is nonnegative watts and may not exceed the configured hardware ceiling.

Environmental references are linearly interpolated. `heater_power_w` is zero-order held. Simulation-only manifests are resampled to solver output cadence; experimental observations remain at their actual sample times so interpolated pseudo-observations do not enter fit or RMSE calculations.

`input_delay_s` delays only the O₂ boundary reference. Response metrics remain relative to the raw recorded reference step, so the reported time includes that declared input delay as well as probe transport and cell response.

## Response and validation criteria

Response metrics use the external reference plateau as the target—not the model's own finite late-window mean. A 2% settling time is reported only if samples are no more than one second apart, the response remains within 2% of the commanded step for at least 10 seconds, and the declared steady window has both acceptable bias and slope. Pressure-changing steps are marked invalid for response-time analysis. These gates prevent sparse or unfinished slow responses from looking fast.

Before using the model for enclosure decisions, reserve independent validation sequences and require all of the following:

- plateau bias no worse than ±0.3 percentage points O₂;
- predicted `t90` error no worse than the larger of 5 seconds or 15%;
- at least 8 of 10 held-out step responses inside their reported 95% predictive interval;
- no fitted parameter at a bound and scaled-Jacobian condition number at most `1e8`;
- the 60–120 second settling requirement met across the measured wet/fouled multiplier range, orientations, temperature range and credible volume/area tolerances.

The last requirement cannot be certified with the checked-in dry sensitivity case. It becomes a design gate only after installed-window, wetting and fouling measurements exist.

## Prototype response study

The `prototype` command screens the existing axial Rev-A envelope and two
smaller-plenum concepts with the idealized well-mixed volume/area model, then
runs a separate 1-D finite-volume sensitivity for designs whose axial geometry
is specified. The checked-in hard well-mixed screen combines 5% of central
installed window conductance, a 10 s cell lag, and a 15 s empirical access lag.
These are design stress values, not probabilities or measured compost degradation.

For the existing Rev-A, the explicit heater-off domain is 50 mm long and the
sensor is 38.5 mm behind the membrane. At the reference uncalibrated effective
diffusivity `2e-5 m²/s`, it gives about 135 s to t90 and 220 s to the 2% band;
the `1e-5`–`3e-5 m²/s` sweep spans about 428–151 s settling. The former 20 s
well-mixed result omitted this path and is not a prediction of the actual enclosure.

The response-oriented candidate now targets a sealed and measured ≤5.0 cm³
effective local plenum, ≥180 mm² supported free area, a Ø23 mm × 15.9 mm clear
cavity, and a ≤0.25 mm dry membrane-face-to-cavity gap. It uses two recessed,
keyed side coupons at 45°/315°, one on each PCB side and both in drainable lower
quadrants, plus a separately heated dry-side carrier rim.

The separate `voxel` command resolves the finite 10 × 10 mm windows, PCB,
cylindrical cell envelope, rear aperture and interface-adjacent gas slabs at
the front/rear sensor ports.
Its hard uncalibrated matrix uses 5% installed conductance, 10 s cell lag,
effective diffusivity `1e-5`–`3e-5 m²/s`, and the full rear-only to front-only
port-coupling range. The revised candidate's worst 1 mm-grid case is about
116 s; a 0.75 mm convergence case is about 115 s. The current outer cartridge's
roughly 5.8 mm access path fails. Drainage, real port coupling, water films and
heater convection remain qualification variables.
Its non-release CAD communication
model is `../cad/o2_probe_response_candidate.scad`.

## Geometry variables

The useful first-order levers are effective plenum volume and installed free membrane area. Membrane material/thickness enters only through fitted installed conductance; fitting diffusivity and thickness separately is not identifiable here. Rear aperture diameter and sensor orientation are recorded experimental metadata but are intentionally not sweepable until a calibrated law connects them to transport. Heater geometry is likewise evaluated thermally after power-step calibration; the model does not infer “fresh-air convection” from heater power.
