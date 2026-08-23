# Compact response-candidate connected-volume budget

Status: communication-model arithmetic; release requires a CAD Boolean and a
physical connected-volume measurement on the populated, sealed assembly.

The spatially screened candidate in `o2_probe_response_candidate.scad` uses a
23.0 mm-ID shroud. The two 3.55 mm end lands leave 15.9 mm clear axial length.
The central cylindrical volume is therefore:

`π × (23.0 mm / 2)² × 15.9 mm = 6,607 mm³ = 6.61 cm³`.

First-order solid displacement inside that domain is:

| Solid or void | Approximate contribution |
|---|---:|
| 20 × 1 × 15.9 mm PCB segment | −0.32 cm³ |
| Ø14.4 × 8.3 mm SGX body envelope | −1.35 cm³ |
| Central cylinder less known solids | **4.94 cm³** |
| Two 10 × 10 × 0.25 mm dry-side membrane gaps, before support obstruction | +0.05 cm³ |
| First-order connected gas | **approximately 4.99 cm³** |

The shroud/tube radial clearance is continuously bond-filled and is not gas
inventory. The deep outer cartridge wells are on the compost side of the
membrane and are likewise outside the connected sensor volume. Heater, solder,
coating, support bars and gasket intrusion should reduce the estimate slightly;
local clearances can increase it. The acceptance gate is therefore a measured
connected effective volume **≤5.0 cm³**, not this arithmetic value.

## Access-path constraint

The membrane is recessed to the inner end of each deep keyed cartridge. Its dry
face must be no more than **0.25 mm** from the local cavity. This dimension is a
response-critical gas path, not a generic assembly clearance. The current
outer-surface cartridge leaves roughly 5.8 mm and fails the hard 3-D spatial
sensitivity. Measure the finished dry-side gap or inspect it by sectioning/CT;
reject any assembly above 0.25 mm.

The two cartridge centres are 45° and 315° in the keyed installation datum.
This places one window on each PCB side while keeping both in the two lower
quadrants. Each outer well needs an unobstructed lower drain behind its stand-off
guard; a recessed membrane with a water-trapping outer pocket is not acceptable.

## Sealing and measurement

The board end seals close both PCB crossings. A continuous circumferential
bond/overmould fills the entire shroud/tube annulus; two isolated end bands that
trap an annular gas sleeve no longer satisfy the volume model.

For release, seal a representative populated assembly, connect a known small
reference volume, and determine connected free volume by pressure expansion or
calibrated liquid fill on a nonfunctional sealed mockup. Record temperature,
fixture volume and uncertainty. Separately verify supported projected membrane
free area ≥180 mm² and the ≤0.25 mm dry-side access gap.
