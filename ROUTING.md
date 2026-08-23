# Accepted routing provenance

The routed upstream board remains derived from bounded per-net
KiCadRoutingTools passes. The earlier base used commit
`81a3c1930892cf9170fd15f8d9e61327d8420596`; the dense MCU-cluster pass used
commit `1dd393eaaa895fd83d3acb40e603969f36542e0e`. The heated-ring revision is a
deterministic local migration and route owned by `adopt_heated_ring_tip.py` and
`route_heated_ring_tip.py`; `gen_pcb.py` owns final placement and outline while
`gen_sch.py` owns the MCU pin map.

The release uses a 0.09 mm track floor, 0.15 mm clearance, and 0.25/0.15 mm
advanced vias. Tip routing is separated by function:

- `HEATER_LOW` uses at least 0.80 mm B.Cu from RH1/RH2 and Q2 to the ring.
- J5's front/back lands are stitched with two 0.60/0.30 mm vias and joined by
  board copper, so the metal ring is not an electrical jumper.
- I²C lateral fanout uses separated In1 corridors with short F.Cu escapes.
- The heater PWM follows the right edge and crosses below the sensor routes.
- In2 is one filled GND plane across the complete slot-free board. Ground
  dogbones keep process vias out of the fitted U10/U12 pads.
- U10's exposed pad terminates at TP6 through a via inside the large test land.

The compact MCU pass treats the right-side U6/C8 placement as generator-owned.
All copper disturbed by that move is withdrawn as a complete net set before
rerouting; the AFE, CELL_RE guard, and heated-ring tip remain protected. A
partial-fragment reroute is forbidden because it produced normalization loops
and stranded same-net fragments during the exploratory pass.

The accepted compact pass first routes power and RS-485 A/B at 0.18 mm with
0.45/0.20 mm vias, then signals at 0.09 mm with 0.25/0.15 mm vias. It remaps
`RS485_DE` to PC6 and `VA_MON` to PA7/ADC_IN7, strips every dangling fragment
and exact same-net duplicate, and retains one continuous In2 GND plane.

Generated routing is never acceptance evidence. Every saved board is refilled
and checked by KiCad DRC, `audit_pcb.py --calibrate`, and `make_fab.py`.
