# O2 probe thermal-barrier estimate

## Scope and result

The released four-slot geometry has an estimated **bare-PCB transverse thermal
resistance of about 98 K/W** between the gas-side island and the body, evaluated
across the all-layer pour-gap boundaries at absolute y=133 and y=135 mm. The
calculation interval is approximately **91–102 K/W**; use **90–110 K/W** as the
engineering bound until first-article measurement replaces it.

This result is consistent with the earlier approximately 95 K/W estimate. The
restored side slots do not materially change this transverse-barrier number:
they begin at y=137 mm, 2.25 mm beyond the gas-side edge of the transverse slots
at y=134.75 mm. They remove lateral coupling between the central tip and the
edge rails over y=137–153 mm, but the complete 16 mm side-slot length is not a
series heat path between the island and body.

The estimate is for PCB conduction only. It is not the ring-to-ambient or
heater-to-ambient resistance and does not include the ring, membrane stack,
potting, enclosure, wiring, convection, radiation, or condensation.

## Geometry and stackup used

All coordinates below are absolute KiCad coordinates.

- Board: 20.00 mm wide, 1.00 mm finished thickness, **two** copper layers
  (Fab, 2026-09-05; it was four through Rev A).
- Dielectric: a single 0.93 mm FR-4 core.
- Copper: 0.035 mm F.Cu and 0.035 mm B.Cu.

**The routed-copper conductance below is Rev A's and is STALE.** It was
computed against 14 crossings on four layers, two of them 0.5 oz inner copper.
Two layers changes the sum in both directions at once -- every crossing is now
0.035 mm rather than some of them 0.0175 mm, and there are more crossings
because the same nets have fewer layers to cross on -- so it cannot be scaled,
only recomputed from the routed board. The FR-4 web and air-gap terms below are
geometry and are unaffected.
- Transverse slots: two horizontal 6.75 x 1.50 mm capsules centred at
  `(104.125,134.00)` and `(115.875,134.00)` mm. At their centreline they
  leave two 0.75 mm edge webs and one 5.00 mm centre neck.
- Side slots: two vertical 0.80 x 16.00 mm capsules centred at
  `(101.20,145.00)` and `(118.80,145.00)` mm, spanning y=137.00–153.00 mm.
- The named rule area excludes zone fill on every copper layer over the
  complete x=100–120 mm strip from y=133–135 mm.
- The transverse crossing inventory is re-derived from the routed board. Rev A's
  fixed count of 14 track segments and two vias no longer applies. The side slots have no
  track, via, or pad crossing, and the saved B.Cu heater-spreader fill contains
  both slot voids.

The controlled geometry is defined in `thermal_design.py`; the independent
inventory and contour checks are in `audit_pcb.py` and `make_fab.py`.

## Calculation

The three axial paths are treated in parallel. This is a first-order,
steady-state conduction model, not a 2-D or 3-D field solution.

### Routed copper

Each of the 14 segments is clipped to y=133–135 mm and represented as

`R = L / (k_cu * width * layer_thickness)`.

Coincident endpoints and the two through vias are connected as a resistor
network rather than counting every centreline-crossing object as an independent
full path. Using `k_cu=385–400 W/(m*K)` and an assumed 15–25 um via-barrel
plating range gives approximately **8.7–9.2 mW/K**. This includes all accepted
crossings on `/I2C_SCL`, `/I2C_SDA`, `/CELL_WE`, `/CELL_RE`, `/CELL_CE`,
`/3V3D`, `/+12V_SW`, `/VA_MON`, `/GND`, `/HEATER_PWM`, and
`/GUARD_REPLICA`.

The exact laminate copper thickness tolerance and finished via plating are not
specified by the PCB source, so this is an assumed, calculated range rather
than a fabricator guarantee.

### FR-4 webs

The rounded slot ends leave more dielectric than a constant 6.50 mm neck. For
the 1.50 mm slot band, with `u = y - 134 mm`, the remaining FR-4 width is

`W(u) = 9.5 - 4*sqrt(0.75^2 - u^2) mm`, for `|u| <= 0.75 mm`.

Including the two 0.25 mm full-width shoulders between the slot edges and the
y=133/135 model boundaries gives

`integral(dy/W) = 0.2367`.

With 0.895 mm dielectric thickness and an explicitly assumed in-plane FR-4
conductivity of `0.25–0.40 W/(m*K)`, the dielectric conductance is approximately
**0.95–1.51 mW/K** (`R_FR4` about 660–1060 K/W). The conductivity range is a
design assumption; the selected fabricator's actual laminate has not been
characterized.

### Slot air

Using an assumed stagnant-air conductivity near `0.026 W/(m*K)`, the two
transverse voids contribute only about **0.15–0.30 mW/K** after allowing for
their rounded ends and spreading. The vertical side-slot air paths are lateral
paths between the central island and edge rails, so they are not added to the
axial y=133–135 conductance.

### Combined bound

The summed conductance is approximately **9.8–11.0 mW/K**, or **91–102 K/W**.
Allowing for laminate anisotropy, copper/plating tolerances, 2-D spreading, and
model-boundary choice gives the recommended pre-measurement design range of
**90–110 K/W**.

At that bound, PCB heat leak is approximately:

| Tip-to-body difference | Heat conducted into body |
|---:|---:|
| 20 K | 0.18–0.22 W |
| 30 K | 0.27–0.33 W |
| 40 K | 0.36–0.44 W |

Routed copper carries roughly 80–90% of this calculated transverse heat flow.
Changing the side slots cannot remove that dominant path; increasing the
transverse resistance would require reducing the crossing copper conductance or
changing the transverse neck geometry.

## What the side slots do and do not do

The side slots reduce lateral FR-4 and copper coupling from the central heated
tip to the narrow board-edge rails over most of the tip length. This is useful
for limiting heat leakage into edge-attached mechanics and for keeping the
heater-spreader field concentrated around the membrane carrier.

They do not create a 16 mm serpentine series path to the body. Between the
transverse-slot gas-side edge at y=134.75 mm and the side-slot upper cap at
y=137.00 mm, 2.25 mm of unslotted board remains. The central island and edge
rails can redistribute heat through this region, and the unchanged transverse
copper inventory still crosses at y=134 mm. Therefore no defensible scalar
increase should be applied to the approximately 98 K/W transverse result from
the side-slot length alone.

The effective resistance from the heated metal ring to the body may be higher
than the transverse value because it also contains longitudinal spreading from
the ring to the barrier. That value depends strongly on the actual filled
spreader, component copper, ring joint, and environmental losses and is not
qualified by this one-dimensional estimate.

## First-article measurement

Measure the PCB barrier separately from the complete condensation assembly:

1. Bond small, low-mass temperature sensors immediately bodyward and gasward
   of the barrier near x=110 mm, nominally around y=132.5 and y=135.5 mm. Add
   ring, U10, membrane, and ambient sensors for the assembled test.
2. Hold the body side on a temperature-controlled fixture. Apply at least three
   calibrated DC heater-power steps and wait for steady state at each step.
3. For a quick conservative check, calculate `delta_T / electrical_power`.
   Because some heater power escapes from the gas side, this is a lower bound
   on the PCB thermal resistance, not the final value.
4. For an identified barrier value, measure heat reaching the body fixture with
   a heat-flow sensor/calorimeter, or perform the test in a guarded low-loss
   setup and subtract independently measured gas-side loss. Use
   `R_barrier = (T_gasward - T_bodyward) / Q_body`.
5. Repeat before and after installing the ring/membrane stack. Fit the system
   model to all temperature channels and power steps rather than forcing the
   full assembly into the bare-PCB resistance.

Production qualification must additionally repeat the test across controlled
dew-point crossings, airflow, expected potting, and enclosure conditions.
