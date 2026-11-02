# O₂ probe prototype response decision

Date: 2026-08-23
Status: uncalibrated sensitivity decision; geometry is not fabrication release.

> **2026-09-05 — one gate below no longer describes the built geometry.**
> The build candidate's **"cell-to-membrane path: 5–10 mm"** was written for a
> cell facing the membrane down the probe axis. Fab put the cell back on a
> **standing** THT mount (PLAN.md option A): its gas face is **radial**, and it
> sits 13.5 mm behind the board tip. The path is now 8.3 mm of axial gas column
> (3.0 flange core + 5.3 spigot bore) and then a turn — not a straight 5–10 mm
> run, so the figure is not comparable and **must not be reported as met or
> missed** until the 3-D model is re-run against the standing geometry.
>
> The other two gates are unaffected in kind and both hold: connected volume
> **2.93 cm³** measured on the mesh against ≤5.0, and supported PMV15T free area
> **181 mm²** against ≥180. The ≤0.25 mm membrane dry-face-to-cavity access gap
> is a carrier feature and did not move.

## Result

The shortened axial Rev-A geometry is **not well mixed**. The corrected
heater-off model represents a 44 mm closed axial gas domain and reads the
sensor 32.5 mm behind the membrane. At the central, uncalibrated effective
diffusivity `D_eff = 2e-5 m²/s`, it reaches t90 in about **105 s** and settles
within 2% in about **171 s**. Across the `1e-5`–`3e-5 m²/s` sensitivity range,
central-case settling is about **332–118 s**; only the highest-diffusivity
central case reaches the 120 s screen.

The 19.7 s value assumes the entire enclosure volume mixes instantly.
It omitted the measured axial path and is not the original design's response
prediction. It remains in the output only as an explicitly labelled idealized
well-mixed screening estimate.

The effective-volume band is now 20.3–26.3 cm³ (23.3 cm³ nominal). It subtracts
the 3.69 cm³ gross volume of the removed 6 mm of 28 mm-ID tube from the prior
sensitivity band; it is not a measured or detailed CAD free-volume result.

The response-oriented **build candidate after the 3-D spatial screen** is a compact recessed-coupon microplenum:

- measured connected effective volume: **≤5.0 cm³**;
- supported PMV15T free area: **≥180 mm²**;
- local shroud: Ø23 mm ID with 15.9 mm clear axial length;
- membrane dry-face-to-cavity access gap: **≤0.25 mm**;
- cell-to-membrane path: 5–10 mm;
- cell centre moved toward board coordinate `y ≈ 107.5 mm`;
- both cell gas faces lateral and clear, with the routed rear PCB aperture kept;
- two recessed membrane coupons at keyed angles 45°/315°, one on each PCB side,
  both in lower quadrants with independent lower-edge drainage and stand-off guards;
- thermally bonded cell island plus a low-power dry-side carrier-rim heater,
  with temporary membrane cold-spot thermometry during qualification.

The governing 3-D voxel hard sensitivity uses 5% installed membrane
conductance, a 10 s cell lag, `D_eff = 1e-5`–`3e-5 m²/s`, and the full range from
rear-only to front-only sensor-port coupling. The revised geometry's worst 1 mm
grid result is about **116 s to the 2% band**; the 0.75 mm rear-port convergence
case is about **115 s**. The current same-side, outer-surface cartridge fails,
and its approximately 5.8 mm membrane-to-cavity access path invalidates the
earlier pass.

This is still an uncalibrated sensitivity result, not proof. The ≤5.0 cm³ and
≤0.25 mm gates are necessary conditions; lower installed conductance, water
films or fouling can exceed 120 s. Complete-path tests must establish the real
response.

The corrected axial equations include domain length and sensor depth for the
existing enclosure. They still lump PCB, package and port blockage into an
uncalibrated effective diffusivity. For the proposed concept, the 3-D model
resolves the finite windows, PCB, cell envelope, rear aperture, recessed access
gap and interface-adjacent gas slabs at both ports. Drainage, water films, true sensor-port coupling and
heater convection remain unvalidated.
The membrane-to-cavity access length is included as a quasi-steady series
diffusion resistance; the access channel itself is not voxelized.

Heater power is not credited as convective gas refresh. It is used only for
condensation margin. A 2 K membrane rise with no more than 4 K block rise
requires measured block-to-membrane coupling `η ≥ 0.5`; otherwise the remote
heater geometry is rejected or the carrier needs direct dry-side heating.

## Files

- Full generated report: [model/results/prototype-study/prototype_report.md](model/results/prototype-study/prototype_report.md)
- Nonlinear verification cases: [model/results/prototype-study/nonlinear_verification.csv](model/results/prototype-study/nonlinear_verification.csv)
- Existing-design axial sensitivity: [model/results/prototype-study/axial_diffusion_sensitivity.csv](model/results/prototype-study/axial_diffusion_sensitivity.csv)
- Candidate 3-D voxel report: [model/results/voxel-study/voxel_report.md](model/results/voxel-study/voxel_report.md)
- Candidate 3-D sensitivity matrix: [model/results/voxel-study/voxel_cases.csv](model/results/voxel-study/voxel_cases.csv)
- Complete sensitivity matrix: [model/results/prototype-study/prototype_cases.csv](model/results/prototype-study/prototype_cases.csv)
- Geometry frontier: [model/results/prototype-study/feasible_frontier.csv](model/results/prototype-study/feasible_frontier.csv)
- Thermal coupling sensitivity: [model/results/prototype-study/thermal_sensitivity.csv](model/results/prototype-study/thermal_sensitivity.csv)
- Candidate CAD source: [cad/o2_probe_response_candidate.scad](cad/o2_probe_response_candidate.scad)
- Candidate preview: [cad/exports/response-candidate-preview.png](cad/exports/response-candidate-preview.png)
- Connected-volume budget: [cad/RESPONSE-CANDIDATE-VOLUME.md](cad/RESPONSE-CANDIDATE-VOLUME.md)

## Release gates

Do not promote the concept until both PCB crossings and the continuous
circumferential shroud/tube bond seal the local domain, and connected effective volume and supported free area are
measured, PMV15T and MMS341 are compared in identical cartridges, and complete
path steps pass in dry, saturated, droplet-covered, drained, condensate-aged and
fouled states. Repeat with cell orientations horizontal, vertical and inverted;
key the membrane facets downward and include a deliberate bad-orientation test.
Every required regime must settle within 120 s on held-out data.
