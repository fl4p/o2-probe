# What a two-layer floorplan would have to change

Written 2026-09-05, after establishing that the present placement does not fit
on two layers (`ROUTING.md`, "It does not fit").  This is the brief for that
work, not the work: it records what was measured so the next attempt starts
from the analysis rather than the search.

**Do not start from here without reading `ROUTING.md` first.**  Two of the
three plateaus that looked structural during that session were self-inflicted
walls in `critical_routes.py`, and the same trap is available to anyone moving
parts instead.

## The measurement that matters

Routing demand is not spread evenly.  Parts per 5 mm band, whole board, both
sides:

| band (local y) | parts | note |
|---|---:|---|
| 5–10 | 3 | |
| 20–25 | 1 | |
| 45–55 | 7+7 | MCU and RS-485 |
| **70–75** | **16** | AFE support passives |
| **75–80** | **11** | U4, U7, U8 and their decoupling |
| 80–85 | 6 | potting dam |
| 85–90 | 1 | gas dam, essentially empty |

**27 parts in the 10 mm from y=70 to y=80**, against 4 in the 10 mm from y=20
to y=30 and 1 in the 5 mm from y=85 to y=90.  Every open link at the 21-link
plateau terminates in that dense strip.

Local lane capacity is NOT the constraint — 6.8–18 mm of free horizontal lane
at every y in the band, on both layers, counting authored copper.  The problem
is that ~27 parts' worth of escapes and ~15 nets' worth of through-traffic want
the same 10 mm, and on two layers a through-route cannot dive under an escape.

## What that implies

1. **Spread the AFE support passives, not the ICs.**  U4, U7, U8 and U15 have
   to stay near their signals.  The R33–R44 and C28–C31 rows at y=70.8 and
   y=74.5 do not: they are decoupling and dividers whose exact position is
   worth millimetres of trace, not routability.
2. **y=85–90 is free and is on the wrong side of the potting datum.**  It is
   gas-side, unpotted and inside the heated island — fine for nothing analog.
   Do not spend it.
3. **y=15–30 is free and is the right side.**  It is potted, cable-side, and
   holds 5 parts across 15 mm.  That is where displaced passives go, at the
   cost of longer runs to the AFE.
4. **The 20 × 107 outline is controlled** (`DESIGN.md`) and `RING-PCB.md`
   already revises it to ≈20 × 120 for the fork — but that added length is at
   the GAS end, y > 107, which is the wrong end for this problem.  Growing the
   cable end is a separate change to the tube fit and is not currently costed.

## What not to do

- Do not trim function to make it fit.  Measured: removing all six `EXP_*`
  signals of the already-DNP expansion connector takes the residue from 21 open
  links to 20.  The shortfall is diffuse.
- Do not re-tune the router.  Six configurations plateaued at 18–21; thinner
  tracks were worse; pour-free routing was far worse; a full-privilege rescue
  moved nothing; and routing the stubborn nets first simply moved the failures
  onto thirteen previously-easy nets.
- Do not move parts by eye.  `gen_pcb.py`'s placement comments record that the
  first hand-guessed pass produced two pad-to-pad shorts and eight courtyard
  collisions, and this session added a third instance — a leg packed against U8
  shorted a pad that reached 0.28 mm further than its centre implied.  Solve
  against real pad extents.

## The cheaper alternative

Four layers routes this placement 61/61 with 197 vias, and every improvement
from the 2026-09-05 session — the driven guard, the ground stitching, the
written stackup, the CELL_RE leakage rule, the verification — is layer-agnostic
and applies unchanged.  The two-layer stackup in `critical_routes.STACKUP` is
the only piece that would revert.
