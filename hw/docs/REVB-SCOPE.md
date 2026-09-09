# Rev B scope

## J5 and external heater ring — deferred

Fab, 9 September 2026: “J5 will be in RevC (if ever).”

J5 and the external heated ring are optional Rev C work. Their ring geometry,
measured fork interface, ring resistance and joint qualification are not Rev B
feature requirements. This decision supersedes the J5/ring release gates in the
earlier Rev B export, assembly and BOM reconciliation records.

F3 was part of that deferred branch: the pre-removal `gen_sch.py` connected it between `+12V_SW`
and `+12V_HTR`, which supplies J5. The main-board heaters RH1/RH2 connect
directly between `+12V_SW` and `HEATER_LOW`; their operation does not require
F3 or J5. The ring-specific F3 protection decision therefore belongs with the
optional Rev C ring. Rev B retains RH1/RH2 and their existing heater controls.

## Implemented Rev B scope

J5, F3 and their ring-only routing are removed from the current schematic and
routed candidate. RH1/RH2 retain their values, placements and main-board current
path. The former eight-error BOM snapshot is historical; the current regenerated
BOM has seven unordered exact-MPN groups and no unsourced fitted component.

The deferred design is indexed in [PCB plans](../plans/README.md), with an exact
recovery commit, routing/footprint references and unresolved requirements in
[the Rev C heated-ring plan](../plans/REVC-HEATED-RING.md).

Cell receptacle qualification, current component shortages, main-board heater
and input-protection qualification, and the remaining physical/electrical
checks continue to apply to Rev B.
