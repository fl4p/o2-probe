# Rev B scope

## J5 and external heater ring — deferred

Fab, 9 September 2026: “J5 will be in RevC (if ever).”

J5 and the external heated ring are optional Rev C work. Their ring geometry,
measured fork interface, ring resistance and joint qualification are not Rev B
feature requirements. This decision supersedes the J5/ring release gates in the
earlier Rev B export, assembly and BOM reconciliation records.

F3 is part of that deferred branch: `gen_sch.py` connects it between `+12V_SW`
and `+12V_HTR`, which supplies J5. The main-board heaters RH1/RH2 connect
directly between `+12V_SW` and `HEATER_LOW`; their operation does not require
F3 or J5. The ring-specific F3 protection decision therefore belongs with the
optional Rev C ring. Rev B retains RH1/RH2 and their existing heater controls.

## Current CAD and next implementation step

This is a scope decision, not a claim that the CAD has already changed. The
current schematic and routed candidate still contain J5 and the F3 placeholder.
The next CAD cleanup should remove the deferred branch from the Rev B design
and regenerate its BOM and validation evidence. The existing dated inventory
snapshot and eight-error BOM audit describe the design before that cleanup.
Do not fit the ring branch based on those older assembly/BOM records.

Cell receptacle qualification, current component shortages, main-board heater
and input-protection qualification, and the remaining physical/electrical
checks continue to apply to Rev B.
