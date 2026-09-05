# What a two-layer floorplan would have to change

Written 2026-09-05, after establishing that the present placement does not fit
on two layers (`ROUTING.md`, "It does not fit").  This is the brief for that
work, not the work: it records what was measured so the next attempt starts
from the analysis rather than the search.

**Do not start from here without reading `ROUTING.md` first.**  Two of the
three plateaus that looked structural during that session were self-inflicted
walls in `critical_routes.py`, and the same trap is available to anyone moving
parts instead.

## Status, 2026-09-05 12:30 — the premise below is partly withdrawn

Three things measured after this file was written change what it can claim.

**1. The "does not fit" conclusion was drawn on a nondeterministic generator.**
`pcbnew` assigns a fresh random KIID to every item and writes the file in KIID
order, so two runs of `gen_pcb.py` on identical inputs produced different item
order — and the router reads the file in order.  The same placement measured
**22, 28 and 36 open links across identical runs**.  `ROUTING.md`'s six
configurations "plateaued at 18–21" *inside a spread wider than that*, so the
plateau was not a plateau.  `canonicalize.py` (commit `1cbd21e`) pins item order
and uuids; three identical routes now score identically.  Every two-layer number
recorded before that commit is noise and must not be cited.

**2. The two-layer board routes better than this file assumed.**  On the pinned
generator, measured by `kicad-cli pcb drc` unconnected items (the same metric the
parallel session used, so the two are comparable):

| placement | KRT open links | DRC unconnected items |
|---|---:|---:|
| stock | 19 | 32 |
| stock, U8 rotated to 270° | 17 | — |
| + gated passive hill-climb (8 iterations) | **16** | **28** |

**3. Two of this file's own recommendations are refuted by measurement.**  See
the corrections inline below.  Both were measured twice, independently, by two
sessions that did not share a harness.

The four-layer fallback in "The cheaper alternative" stands as a fallback.  It is
no longer established that it is *necessary*.

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

> **Correction, measured 2026-09-05 (parallel session).**  The density figure
> above is real but is **not the binding constraint**.  A free-lane profile taken
> every 0.5 mm over y=62..86 finds **30–59 free lanes on both layers at every y**,
> and the worst horizontal cut has 37 lanes spare (demand 26 against capacity 63).
> The band is not congested in the capacity sense, so "27 parts in 10 mm" does not
> by itself explain the open links.  What follows about escapes-versus-through-
> traffic may still be the mechanism, but this table is not evidence for it.

Local lane capacity is NOT the constraint — 6.8–18 mm of free horizontal lane
at every y in the band, on both layers, counting authored copper.  The problem
is that ~27 parts' worth of escapes and ~15 nets' worth of through-traffic want
the same 10 mm, and on two layers a through-route cannot dive under an escape.

## What that implies

1. ~~**Spread the AFE support passives, not the ICs.**~~ **Refuted — measured
   twice, by two sessions, on two harnesses.**  The parallel session implemented
   exactly this proposal (R24–R27, R43/R44/C34, C10, U15, R39, R34/R35 moved to
   y=20..31 and y=62..69, each solved against real pad/courtyard/PTH geometry,
   decoupling and pin-local parts held, matched 0.1 % pairs kept adjacent) and
   measured **39 → 68 unconnected items**.  Total MST ratsnest went 1714.7 →
   1684.2 mm: the moved placement is 30 mm **shorter** and routes **worse**.
   This session independently moved eight passives the same way (R24–R27 to the
   MCU, R33/C28 to the ADC, R38/C31 near U4) and measured **19 → 22 open links**.
   Spreading the AFE passives is a regression, not an improvement, and optimising
   placement by wirelength is measurably the wrong objective on this board.
   What did help instead: rotating **U8 to 270°** (19 → 17) and a *gated* local
   hill-climb that only accepts candidates keeping the authored copper and zero
   shorts (→ 16).  The original text follows, for the record:

   ~~**Spread the AFE support passives, not the ICs.**~~  U4, U7, U8 and U15 have
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
- **Net ORDER is worth more than any router knob.**  Measured (parallel
  session, stock placement): routing the 12 longest-span nets (`+12V_SW` 85 mm,
  `3V3D` 68, `HEATER_PWM` 58, `I2C_SDA/SCL` ~54, `3V3A` 46, `VIN_MON`/`VA_MON`
  40, `AFE_MENB`, `CE_MON`, `ADC_DRDY`, `+5V_ANALOG`) first on empty copper and
  the residue afterwards with `--keep-input-copper` took **39 → 30 unconnected
  items, −23 %**.  It costs vias: 352 against 256.  Adding cost weights on top of
  the staged order (via 250, dir-pref 1200) undid it: 60.
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

## A measurement trap, if you score scratch boards

`kicad-cli pcb drc` on a board with no same-stem `.kicad_pro` beside it grades
against KiCad's **built-in defaults** (min track 0.20, min hole 0.30, clearance
0.20) — silently, with no warning.  The same board measured **322 clearance +
199 drill + 199 track_width + 199 via_diameter** violations without the project
file and **10 clearance** with it.  Copy both `o2-probe.kicad_pro` *and*
`o2-probe.kicad_dru` next to every scratch board before scoring it; the `.dru`
carries `cell_re_surface_leakage`, and a route measured without it is a route
against rules this design does not permit.

Related: KRT strips "dead-end input segments" after routing, which deletes the
driven guard rails — they dangle by design.  `--keep-input-copper` is mandatory
on this board, and every score taken without it was measured on a board that had
lost its guard, which routes *easier*.
