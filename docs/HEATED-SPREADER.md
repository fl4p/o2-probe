# Heated membrane spreader — variant study

**Status:** design study, nothing modelled. Written 2026-09-03 from Fab's proposal
to "solder a metal ring on the tip". The instinct is right and a *ring* is the one
shape that cannot work; the reason is a single number, and the same number sizes
the shape that does.

**Read §0 first.** The heater is not an open choice; it already exists on the
board as J5, and this head geometry cannot use it.

**Nothing here should be built before the measurement in §7.** Every row below is
parameterised on `h`, the membrane's surface coefficient into the guard chamber,
and `h` has never been measured. It is the whole answer.

---

## 0. The ring already exists. This head has nowhere to put it.

**Added 2026-09-04, after the PCB tip was drawn into the exploded view.** Everything
below §1 was written as if the heater were a thing still to be chosen. It is not.
It is already on the board, and this document never checked where it lands.

`o2-probe.kicad_pcb` carries **J5**, two 2.0 x 3.0 mm castellated PTH pads on the
left and right board edges at `(0, 105.5)` and `(20, 105.5)`, bisected by the
finished side profile, joined by wide back copper on switched `HEATER_LOW`. Its
design note in the board file reads:

> "Manual-soldered dry-side metal membrane-carrier ring; duplicated lands are one
> HEATER_LOW node"

So Fab's "solder a metal ring on the tip" was not a new idea to evaluate — it is
the **existing** architecture. RH1 and RH2 (2512s at `(5, 96.5)` and `(15, 96.5)`,
~140 ohm for a ~1 W ceiling at 12 V) are the heat *source*; the ring is the
*spreader* that carries their heat forward to the membrane's dry side.
`PLAN.md` is explicit that it is "a thermal spreader, not an electrical jumper".

### Where it lands, and why that fails here

The board's gas end stops at `y = 107`, so J5 sits 1.5 mm behind the board tip.
In the **radial** head (`cad/o2_probe_head.scad`) that works: the windows are on
the tube's side walls, the board runs past them, and a ring soldered into both
edge castellations encircles the tip and can bear on the cartridge's heater shelf.

This **end-window** head is `PLAN.md` cell-orientation **option C — cell past the
board end, axis along the tube**. That choice moved the membrane off the side and
onto the end face, and it put the cell between the board and the window:

| | z (head frame) |
|---|---:|
| board tip, and therefore J5's ring | **16.0** |
| cell can, seated on its socket stand-off | 20.7 – 29.0 |
| carrier well floor | 29.0 |
| head end face | 33.6 |
| **heater shelf in the cartridge** | **34.6** |

**18.6 mm from the ring to the heater shelf, with a Ø14.4 cell filling the bore
for 8.3 mm of it.** A ring at J5 cannot reach the membrane in this geometry. To
get there it would have to become a ~19 mm sleeve around the cell — which is a
thermal shunt straight down the gas path, wrapped around the one component whose
rear vent `PLAN.md` marks DO NOT OBSTRUCT.

### The contradiction nobody had written down

- **The KiCad board** puts the heat source on the PCB and spreads it forward with
  a soldered ring.
- **Both CAD heads** put the heater on the cartridge's `heater_shelf` — a "dry-side
  heater seat... entirely inside the seat gasket's window, so heater leads cross
  no sealing surface". Neither model contains a ring at all.
- **This document's own eta column** (§1) assumed the cartridge-shelf heater, at
  "the modelled gap L = 3.82 mm". That gap only exists if the heater is *on the
  shelf*. It silently assumed the architecture the board does not build.

Three descriptions of the heater, none of which is the same heater.

### What follows

1. **The ring is not wrong; it is orphaned by option C.** Do not delete J5. If the
   radial head wins the comparison, J5 is exactly right and this whole document is
   about a problem that does not arise.
2. **If the end-window head wins, the heater has to move to the cartridge** — and
   then it needs a lead path from the board, past the cell, through the Ø18 spigot
   bore, that nothing has designed. `RING-PCB.md` answers this: the fork carries
   four conductors forward and needs no harness at all. (The
   `cartridge_tsense_axial()` pocket had the identical problem and was removed on
   2026-09-04 — the heater's own PCB now carries its sensor.)
3. **And then it is a consumable.** The cartridge is the replaceable membrane part.
   A heater and a temperature sensor built into it get thrown away at every
   membrane change, and re-made blind through the same Ø18 bore that §1.5 of
   `POTTING.md` says has no cell-extraction tool either. A heater that stays with
   the head while the cartridge is swapped is a different part again.
4. **None of this rescues a ring thermally.** Even placed perfectly, §1 shows a rim
   ring warms an annulus 1-3 mm wide against an 8 mm window radius and leaves a
   cold disc across 40-75 % of the membrane. Placement is the *second* problem.
   The shape is the first.

**This is now the decision that gates the heater, ahead of the `h` measurement in
§7:** the radial-vs-end-window head comparison is no longer only about diameter
and gas volume, because the two heads do not admit the same heater.

## 1. The number: heat does not travel 8 mm through 0.18 mm of PTFE

A thin sheet heated at its edge and losing heat from its faces is a fin problem.
The distance heat penetrates before it is lost is

    L_fin = sqrt(k·t / h)

with the repo's own membrane: `membrane_t = 0.18` mm and k ≤ 0.25 W/m·K (bulk
PTFE — PMV15T is *porous*, so its real conductivity is lower and every figure here
is optimistic). That gives **k·t = 4.5 × 10⁻⁵ W/K**.

| h (W/m²K) | L_fin | η, existing gas-gap heater |
|---:|---:|---:|
| 5 | 3.00 mm | 0.59 |
| 10 | 2.12 mm | 0.42 |
| 25 | 1.34 mm | 0.23 |
| 50 | 0.95 mm | 0.13 |
| 100 | 0.67 mm | 0.07 |

The window radius is **8 mm**. So rim heat reaches between 8 % and 38 % of the way
in. A ring — heated to any temperature you would tolerate — warms an annulus
1–3 mm wide and leaves a cold disc of radius 5–7 mm, which is **40–75 % of the
window, in the middle**. That is the worst possible place for it: condensation
would form as a central blind spot on the controlled area.

This is not a power problem and not a scale problem. `L_fin` depends on the radius
*ratio* nowhere and on the membrane thickness only, so it is unchanged by shrinking
the probe and unchanged by heating the ring harder.

η in the right-hand column is the existing dry-side heater, `1/(1 + hL/k_air)` at
the modelled gap `L = 3.82` mm. Note that **both paths fail in the same regime**:
below h ≈ 7 the existing heater already meets the ≥ 0.5 coupling target and no new
part is needed; above h ≈ 25 both the gas gap and the rim are hopeless and only a
spreader works. The entire decision is `h`.

## 2. What has to be true instead

If no point on the membrane is further than one `L_fin` from metal, the whole
window stays warm. Two ways to get there, and only one survives:

**Make the apertures small.** Aperture radius ≤ `L_fin` → holes of Ø2.7 mm at
h = 25, Ø4.2 mm at h = 10. Comfortable.

**Make the spreader itself conduct.** This is the constraint that kills fine woven
mesh. The spreader must carry heat to the middle of the field, so it needs

    k_s · t · φ  ≥  h · r²        (φ = solid fraction, r = field radius = 8 mm)

A 0.03 mm-wire stainless mesh at 80 % open has `k·t` only about twice the
membrane's own — it improves `L_fin` by √2 and nothing more. **A mesh is mostly
holes, and holes do not conduct.** Solid foil is required:

| h | required `k·t` | 316 foil (k = 15), thickness × solid fraction |
|---:|---:|---|
| 10 | 6.4 × 10⁻⁴ | 0.043 mm → **0.17 mm** at 75 % open |
| 25 | 1.6 × 10⁻³ | 0.107 mm → **0.43 mm** at 75 % open |
| 50 | 3.2 × 10⁻³ | 0.213 mm → **0.85 mm** at 75 % open |

So **0.3–0.9 mm of perforated 316** covers the whole plausible range. The thermal
side of this is easy. The cost is somewhere else.

## 3. The cost is open area, and it lands on head diameter

`MEMBRANE.md` requires **≥ 180 mm² of controlled membrane**. The window is Ø16.0 =
201 mm², and the seal bounds it — the O-ring's inner contact sits at about Ø16.5,
so the active area cannot grow without moving the whole seal outward.

| open fraction | gross area needed | field Ø | head / cap |
|---:|---:|---:|---|
| 55 % | 327 mm² | 20.4 | 46 / 51 |
| 65 % | 277 mm² | 18.8 | 44 / 49 |
| 75 % | 240 mm² | 17.5 | 42 / 47 |
| 85 % | 212 mm² | 16.4 | 42 / 47 |
| — (today) | 201 mm² | **16.0** | **40 / 45** |

Head diameter moves in 2 mm steps because `head_od` takes `ceil()` of the bolt
circle, and the current 40 needs `bolt_r ≤ 16.05`. **Any window above Ø16.1 costs
2 mm of head.** So the trade is binary and small:

- **Keep Ø40.** Spreader at 80 % open over the existing Ø16 window → **161 mm²**
  against 180 required. Roughly 11 % less membrane, so ~1.1× slower response.
- **Keep 180 mm².** Window grows to ~Ø17.5, head returns to **Ø42** — this
  morning's size, undoing the `spigot_land` split.

Neither is dramatic. Which one is right depends on the response margin in
`PROTOTYPE-RESPONSE.md`, which this study has not read against a number.

## 4. Put it on the DRY side — this is the important architectural point

The obvious placement is the wet side, in the retainer. **Do not.** The spreader
needs heater leads, the wet face sits in the guard chamber which is *outside* the
seal, and that means a new feedthrough crossing the membrane seal — next to the one
joint in the probe that must not leak.

The dry face over the window is **inside the sealed cavity**, inboard of the
O-ring's Ø16.5 inner contact. A spreader there:

- needs no feedthrough at all; its leads run straight to the board;
- is not exposed to compost, so corrosion and fouling largely drop away;
- blocks exactly the same open area (the gas path is the same path), so §3 is
  unchanged;
- leaves the retainer as a purely structural part.

**Open question, and it is a real one:** the membrane over the window is clamped
only at its rim and is unsupported across the Ø16 span. A spreader pressed against
its dry face pushes it outward into the guard chamber. It needs light controlled
contact, a support off the flare cone, or a bond — and nothing bonds to sintered
PTFE, which is the same problem the membrane joint has everywhere else. Contact
resistance across a pressed PTFE/metal interface is also unquantified and sits
directly in series with the whole scheme.

## 5. Material

**Not brass, not copper**, however good the conductivity looks. Ammonia stress-
corrosion cracking of copper alloys ("season cracking") is the textbook failure for
exactly this environment, and the membrane is gas-permeable, so NH₃ reaches the dry
side too. **316 or titanium.** Both are ~15–22 W/m·K, which §2 shows is ample.

### The ring's material is UNSPECIFIED, and that is an open action, not an oversight

Checked 2026-09-04 across the hw repo. The ring has **no material, no coating, no
drawing and no MPN anywhere**. J5's footprint carries an empty `Datasheet` and an
empty `Description`; the board calls it only "metal". Two documents already record
this as owed work rather than settled:

- `PLACEMENT.md`: *"Provide the ring drawing/material/coating, confirm its dry-side
  insulation, membrane clamping, solder access, and thermal contact before ordering
  volume."*
- `ASSEMBLY-EXCEPTIONS.md`: *"verify ring material/plating, use controlled heat and
  flux…"*
- `FAB-NOTES.md` calls it **user-supplied** and hand-soldered after board assembly.

So it is a part Fab supplies, and nobody has said what it is made of.

### The conflict that decides it

An earlier version of this section said "prefer spot-welding or a mechanical
terminal for the heater connection". That was written without checking the board.
**It is not a preference — J5 is a solder joint**, two plated castellations, hand
soldered. So the material has to satisfy two requirements that pull opposite ways:

| | survives NH₃/H₂S + condensate | solders to a plated castellation |
|---|---|---|
| brass, copper | **no** — ammonia season cracking | yes, easily |
| 316 stainless | yes | **poorly** — needs aggressive acid (ZnCl₂/HCl) flux |
| titanium | yes | **effectively not at all** without special preparation |

The easy-to-solder metals are the ones ammonia attacks; the durable ones are the
ones that resist solder. And aggressive flux is not a free choice here: the ring
sits at `y = 105.5`, roughly **12 mm from the CELL_RE receptacle land**, on a
board section that is conformal-coated but never potted — the same surface whose
~1.8 MΩ wet-leakage budget `PLAN.md` says fakes 0.1 % O₂.

Three ways out, in the order I would try them:

1. **316 with a nickel strike / solderable plating.** Base metal takes the
   chemistry, plating takes the solder, ordinary no-clean or rosin flux is enough.
   This is the standard answer for solderable stainless and it is the one to price
   first.
2. **A mechanical terminal** — screw or spring clamp to the ring, so the ring's
   own metal never has to be wetted. Costs a part and some height; removes the
   flux question entirely, and makes the ring replaceable.
3. **Bare 316 with acid flux**, only with a validated clean-and-verify step and a
   surface-insulation-resistance coupon measured *after* it. Do not do this
   silently.

Also unchecked: **galvanic coupling.** Ring / solder / copper land is a
three-metal stack in a condensing, ammoniacal film — which is precisely the
condition this probe is designed to sit in. Whatever the ring turns out to be,
the couple needs a look before volume.

### Can a coating save a brass ring? (asked 2026-09-04)

Short answer: **a coating mitigates, it does not fix, and brass is not buying us
anything here.**

**Why coating is weak against this specific failure.** Ammonia season cracking is
stress-corrosion cracking, not surface loss. It needs residual tensile stress plus
the environment, and it initiates at a *point*. A barrier coating only works while
it is perfectly continuous, so one pinhole, one handling scratch, one sheared edge
or one solder-heat-affected zone is enough — and the crack then propagates
*underneath* the coating with nothing visible on the surface. Coating a
susceptible alloy converts a slow, inspectable, distributed problem into a fast,
hidden, localised one. That is the wrong direction for a part buried in a compost
pile for a season.

**And the one place you cannot coat is the worst place.** J5 is a soldered joint,
so the castellation contact must either be masked before coating — leaving bare
brass exactly where residual stress, flux residue and the copper couple all
concentrate — or coated afterwards, over the flux residue. There is no version of
this where the joint is both soldered and fully coated.

**The thermal cost, which is the argument that actually settles it.** The heater
ledge in `membrane_cartridge_common.scad` is an annulus Ø18 → Ø22, so the ring's
contact area is

    A = pi/4 * (22^2 - 18^2) = 125.7 mm^2 = 1.26e-4 m^2

At the ~1 W heater ceiling that is ~7950 W/m^2 through the joint. Parylene C, the
best conformal barrier on offer, runs k ~ 0.084 W/m.K (class figure, confirm):

| coating | thickness | ΔT across it at 1 W |
|---|---:|---:|
| parylene C | 12 µm | **1.1 K** |
| parylene C | 20 µm | **1.9 K** |
| parylene C | 25 µm | **2.4 K** |

The design range for the whole membrane rise is **0–4 K**. A dielectric barrier
thick enough to be pinhole-scarce spends a quarter to half of that budget before
any heat reaches the membrane — on a heat path §0 already shows is 18.6 mm too
long in this head. (A conductive plating avoids the ΔT, but nickel is itself
complexed by ammonia and thin electroless Ni is porous, which puts a galvanic cell
on top of a susceptible alloy.)

**Brass is not earning its place.** The two reasons to want brass are conductivity
and solderability. Conductivity is not a constraint — §2 shows the required `k·t`
is met by 316 at 15 W/m·K with 0.2–0.9 mm of foil, and for a *rim* ring §1 shows
the material's conductivity barely matters because the membrane's own `L_fin` is
what limits the reach. So the only real argument is solderability, and §5 already
has two clean answers to that (nickel-strike plated 316, or a mechanical terminal).
Coating brass is paying a thermal and inspection penalty to keep a material chosen
for a property we do not need.

**If brass is nonetheless forced** — say a ring already exists in a drawer — then
in order of actual effectiveness:

1. **Stress-relieve it** (~250–300 °C for brass). SCC needs tensile stress; this
   is the classical mitigation and it beats any coating, because it removes one of
   the two necessary conditions rather than trying to exclude the other.
2. **Drop the zinc.** SCC susceptibility in Cu-Zn rises steeply above roughly 15 %
   Zn, so CuZn15 or lower is far less prone than common CuZn37. Arsenical/DZR brass
   addresses dezincification but **not** SCC — do not let the two be conflated.
3. **Then** coat, as a third layer of defence, never as the plan.

**Do not let the ring be sourced as "some stainless washer" either.** It is a
soldered, in-cavity, dissimilar-metal part next to the highest-impedance node on
the board.

### A PCB with copper fill, instead of a metal ring (asked 2026-09-04)

**This is the best option on the table.** It wins on the numbers, not just on
convenience — and it is the only candidate that also fixes the joint.

**Conductivity: copper wins by 27x, so thickness stops mattering.** §2's
requirement is `k_s · t · φ ≥ h · r²` with r = 8 mm, so `h·r²` = 6.4e-4 (h = 10)
to 3.2e-3 W/K (h = 50). Copper at 400 W/m·K:

| | `k·t` solid | vs h = 50, solid | vs h = 50, **at 75 % open** |
|---|---:|---:|---:|
| 1 oz (35 µm) | 1.40e-2 W/K | 4.4x | **1.09x** — meets it, no margin |
| **2 oz (70 µm)** | 2.80e-2 W/K | 8.8x | **2.2x** |
| 3 oz (105 µm) | 4.20e-2 W/K | 13.1x | 3.3x |

§2 asked for **0.213 mm of solid 316** for the same job. Copper does it in
**70 µm**, because k is 27x higher. So a 2 oz PCB spreader beats the foil this
document specced, in a part that is cheaper, dimensionally exact, natively
solderable, and can be *routed* into the perforated pattern §2 wants rather than
etched or punched.

**Specify 2 oz explicitly.** `FAB-NOTES.md` puts the main board at **1 oz outer**,
and the table shows 1 oz at 75 % open clears h = 50 by only 1.09x — no margin at
all. The ring is a separate small PCB and can carry its own stackup; do not let it
inherit the motherboard's.

**Corrosion: this is the strongest argument, and it is a consistency argument.**
Copper foil laminated to FR-4 is essentially *unstressed*, so ammonia
stress-corrosion cracking — which needs residual tensile stress — does not apply
the way it does to a formed brass ring. It is mask-covered everywhere but the
pads. And decisively: **the gas-zone end of the main board is already
copper-on-FR-4-under-mask, sitting in this same cavity.** If a PCB ring cannot
survive there, neither can the board that is already there, and the whole probe is
void. A PCB ring adds no new material to the environment. Every metal ring does.

**Bonus, and it may be the real prize: put RH1 and RH2 *on* the ring.** They
currently sit on the main board at `(5, 96.5)` / `(15, 96.5)` and the ring only
carries their heat forward. If the ring is a PCB it can carry its own resistors and
the cold-spot sensor §7 needs, right at the membrane. J5 then becomes an
*electrical* interface instead of a *thermal* one — a far easier joint, and it
retires the thermal-contact-resistance unknown in §8's assumptions table.

**What it does NOT fix, and this matters:**

1. **Placement is unchanged.** §0's 18.6 mm still stands in the end-window head:
   J5 is at the board tip and the heater shelf is past the cell. And a PCB *finger*
   reaching forward cannot get there either — the neck is Ø16.4 with a Ø14.4 cell
   in it, a 1 mm annulus, and widening it to Ø18 over the 13 mm clear length costs
   **562 mm³ against a 192 mm³ cavity-budget margin**. There is no room. This
   remains a head-architecture decision, not a materials one.
2. **A PCB presents only 35–70 µm of copper at its rim.** Fine for face contact;
   poor if the thermal joint is edge-on, which is what the *radial* head would
   want. If the contact is at the rim, plate the edge (castellations around the
   perimeter) or move the contact onto the face near the rim.
3. **Solder mask sits in the thermal path**: ~25 µm at k ≈ 0.25 W/m·K is **0.80 K**
   at 1 W over the 125.7 mm² ledge. Real but smaller than parylene's 1.1–2.4 K.
   Specify mask-free ENIG on the contact face and the penalty goes away.
4. **FR-4 conducts at ~0.3 W/m·K through thickness.** Put the copper on the
   membrane-facing side, or stitch with thermal vias. Do not let heat cross the
   laminate.
5. **Outgassing** onto the SHT45, per `POTTING.md` §6. Small part, same family of
   concern, same mitigation.

CAF is a non-issue here: the ring is a single net.

## 6. One thing this makes better, and one it does not

**Better:** today's O-ring change made the membrane squeeze **geometry-set** — the
stack bottoms out on the ledge and the retainer is what it bottoms against. A
printed-ASA retainer creeps under sustained load at 75 °C; that creep now feeds
straight into seal squeeze. Anything that stiffens the retainer is worth having
independently of the heater.

**Not better:** ASA conducts at ~0.17 W/m·K. "Coupling against the ASA head" works
as a mechanical seat but not as a thermal path — the head will not carry heat to or
from the spreader. That is the *good* outcome here: the ASA isolates the spreader,
so heater power goes into the membrane instead of into the head and the compost.
Do not plan to conduct heat through it.

## 7. The measurement that decides all of this

Everything above is a function of `h`, and the two outcomes are opposite:

- **h ≲ 7 W/m²K** → the existing dry-side heater already reaches η ≥ 0.5. Build
  nothing. The spreader is wasted area and wasted head diameter.
- **h ≳ 25 W/m²K** → neither the gas gap nor a rim reaches the membrane, and the
  dry-side spreader of §2–4 is the only option on the table.

**Superseded 2026-09-04.** The instrumentation was a 1.2 mm pocket in the heater
ledge (`cartridge_tsense_axial()`), added 2026-09-03 back when the heater was
assumed to live in the carrier. It is **removed**: `RING-PCB.md` puts the heater
on a small PCB carried forward on the main board's fork, so the heat source now
carries its own reflow-soldered sensor on two of the fork's four conductors —
easier to source, to assemble and to connect than a sensor buried in a printed
pocket with its own lead through the same bore.

That still gives the **warm end**. A temporary sensor on the membrane face during
qualification gives the **cold end**. The pair yields η directly, and `h` by
inversion of `η = 1/(1 + hL/k_air)`. Note that neither ever saw the membrane's
*centre* cold spot — that sits over the flare cone with nothing to bore into.

`RING-PCB.md` §3 also prices the mounting position: head-side, the ring sits
8.12 mm from the membrane rather than 3.82 mm, and on the gas-gap path **cannot
reach η ≥ 0.5 at any plausible h**. So the first ring is the instrument that
settles §7, not the finished heater.

Run that before drawing any of this.

## 8. Assumptions, all load-bearing

| | value | basis |
|---|---|---|
| membrane k | ≤ 0.25 W/m·K | bulk PTFE; **porous PMV15T is lower**, so `L_fin` is optimistic |
| membrane t | 0.18 mm | datasheet, `membrane_t` |
| gas gap L | 3.82 mm | modelled: heater ledge to membrane dry face |
| k_air | 0.028 W/m·K | ~50 °C |
| radiation | ~6.7 W/m²K | 4εσT³ at 320 K, ε ≈ 0.9 — **scale-invariant**, and roughly doubles both sides |
| h | **UNMEASURED** | the entire result; §7 |
| contact resistance, spreader→membrane | **UNMEASURED** | in series with everything in §2 |
| 316 k | 15 W/m·K | handbook |

The η column of §1 also omits the wet-side radiative term, which partly cancels the
dry-side one. Treat all η figures as indicative of *regime*, not as predictions.
