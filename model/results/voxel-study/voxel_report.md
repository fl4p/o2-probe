# Candidate 3-D spatial response study

Status: **uncalibrated CAD-derived voxel sensitivity**, not a response guarantee.

The existing same-side coupon layout fails the hard spatial sensitivity: it does not reach the 2% band within 400 s in 1 tested case(s); its slowest completed result is 398.4 s. The proposed
`compact_drainable_split_hard` geometry gives 116.3 s
in its worst tested effective-diffusivity/port-coupling case and
passes
the 120 s screening limit across the declared matrix.

The candidate screen requires:

- connected effective gas volume no greater than 5 cm³;
- supported projected free membrane area at least 180 mm²;
- local shroud ID 23 mm;
- membrane-to-cavity access length no greater than 0.25 mm;
- membrane facet centres at 45/315 degrees in the keyed
  installation datum, placing one coupon on each PCB side while both remain in
  the two lower/drainable quadrants;
- the rear PCB aperture retained and both modeled sensor port surfaces open;
- no response credit from heater convection.

The screen spans effective diffusivity 1e-05–3e-05 m²/s and front-port coupling weights
0–1, including rear-only and front-only endpoints.
Diffusivity, installed conductance scale, and sensor port coupling are unmeasured.
The voxel model resolves the finite window height, PCB, cylindrical cell envelope,
rear aperture and interface-adjacent gas slabs at both ports, but it is not CFD and does not model
compost flow, water films, heater convection or cell consumption. Confirm with
complete-path dry/wet/fouled steps before fabrication release. The declared
membrane-to-cavity access length is a quasi-steady series resistance; the access
channel itself is not voxelized, so the existing 5.8 mm-path failure is a robust
screen rather than a resolved channel-flow prediction.
