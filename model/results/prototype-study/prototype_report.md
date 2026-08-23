# Prototype response study

Status: **uncalibrated sensitivity study**, not a validated compost response prediction.

## Screening outcome

Retain `dual_side_microplenum_candidate` as the response-oriented **build candidate**, not a verified response decision: compact recessed-coupon plenum screened in the separate 3-D voxel study

- effective gas volume target: 4.9 cm³ nominal, 4.8–5 cm³ study band;
- supported free membrane area: 184 mm² nominal, 180–190 mm² band;
- cell-to-membrane path: 5–10 mm;
- cell: cell centre moved to board y about 107.5 mm (assembly z about 112.5 mm), inside a measured local shroud; orientation: cell faces lateral; both unobstructed; 3 mm provisional rear PCB aperture retained;
- membrane: two recessed keyed PMV15T facets at 45/315 degrees, one on each PCB side and both draining at their lower edge behind a stand-off guard; dry-face cavity gap <=0.25 mm;
- heater: thermally bonded cell island plus separately controlled recessed dry-side carrier-rim heater; instrument membrane cold spot.

The current Rev-A is **not well mixed**. With its 44 mm closed axial domain and the cell 32.5 mm behind the membrane, the heater-off 1-D finite-volume model gives t90=105.2 s and 2% settling=171.2 s at the reference effective diffusivity 2e-05 m²/s. Across the uncalibrated 1e-05–3e-05 m²/s range, central-case settling spans 118.0–331.5 s. The 19.7 s current-design result is only an idealized well-mixed estimate that omitted the axial path; it is not the current geometry's predicted response.

Under the deliberately hard **well-mixed volume/area sensitivity** (largest volume, smallest area, 0.05× installed conductance, 10 s cell lag and 15 s empirical access lag), the proposed dual-side concept's linearized 2% estimate is 87.7 s and its nonlinear well-mixed check gives 87.5 s. The candidate's nominal-dry, no-access well-mixed estimate is 17.5 s. These screening numbers do not bound the spatial result. The separate `voxel` study represents the finite candidate geometry and is the governing numerical screen for its 1–2 minute target.

The 120 s result means only **“passes the chosen 0.05× conductance sensitivity scenario.”** It is not evidence that a wet or fouled PMV15T assembly retains that conductance. Lower conductance can exceed 120 s. The multiplier and any geometry-specific access lag must be measured.

The axial model explicitly includes the existing design's domain length and sensor depth. It still replaces PCB, package and port blockage by one effective diffusivity and therefore remains a sensitivity model. The separate 3-D voxel model resolves the candidate's finite windows, PCB, cell envelope, rear aperture and membrane access gap. Drainage, water films, heater convection and true sensor-port coupling remain unvalidated. Promote the geometry only with complete-path measurements.

## Why this geometry

The current axial membrane is about 32.5 mm from the cell and leaves roughly 23.3 cm³ effective gas volume. Its large membrane area makes the membrane/inventory time constant only a few seconds in the central sensitivity case; the explicit model shows the long axial diffusion path is the main response penalty. Moving the cell/window system into a local, filled or shrouded microplenum is intended to shorten that path while reducing inventory without deliberately restricting the membrane. Two drained side facets keep the membrane close to the cell's lateral gas faces and avoid an upward-facing liquid pocket. The routed rear PCB aperture remains mandatory.

Do not interpret the heater as an air pump. Heater power is absent from the gas-transfer equation because no calibrated power/orientation/convection law exists. Its job is condensation margin. With a maximum allowed block rise of 4 K and desired membrane rise of 2 K, measured membrane coupling must be at least η=0.50. A remote cell-island heater cannot be accepted if the measured coupling is lower; the proposed dry-side carrier-rim heater remains a concept until temporary cold-spot thermometry validates it. The one-node model provides only quasi-steady thermal screening.

## Build constraints

1. Seal the local cavity at both PCB crossings and on both sides of the radial shroud/tube annulus, then measure connected effective free volume; the response target is ≤5 cm³, not a geometric guess.
2. Measure projected free area after the PP support; the response target is ≥180 mm².
3. Key installation so membrane facets face sideways/downward and all lower edges drain into an open gap behind the debris guard.
4. Keep both SGX faces clear; retain the routed ~3 mm rear aperture until a physical cell establishes the true port size.
5. Thermally bond the cell body to the island, heat the membrane carrier from the dry side, and keep the membrane below vendor/material limits.
6. Preheat before accepting O₂ response data; thermal warm-up and O₂ settling are separate gates.
7. A/B test PMV15T against MMS341 in identical cartridges. Do not substitute vendor pressure airflow for concentration-step conductance.

## Required validation

Run complete-path steps at horizontal, vertical and inverted cell orientations; membrane facets keyed downward and deliberately misoriented; heater off and regulated; dry, saturated, droplet-covered, drained, condensate-exposed and aged/fouled states. The nonlinear verification uses dry transport equations with a 100% RH input; RH does not affect transport in V1 and this is not wet validation. Promote this geometry only when every required regime has a measured conductance multiplier and held-out 2% settling remains ≤120 s.

Generated from model version `0.1.0`. See `axial_diffusion_sensitivity.csv`, `prototype_cases.csv`, `design_summary.csv`, `nonlinear_verification.csv`, `feasible_frontier.csv`, `thermal_sensitivity.csv` and the plots for the full sensitivity matrix.
