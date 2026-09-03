# Agent brief: source the membrane perimeter gasket

**Status:** open. This is the last unsourced elastomer in the O₂ probe head, and it
blocks more than itself — see *Why this is on the critical path*.

Everything below marked **FIXED** is a real interface and must not be changed.
Everything marked **ASSUMED** is a design default with nothing behind it; you may
propose a different value if the market offers a better one, subject to the stated
constraints. Everything marked **UNKNOWN** is what this task exists to answer.

---

## 1. What the part is

A thin elastomer washer that seals the *perimeter* of an O₂-permeable membrane disc
onto the wet face of the probe's membrane carrier. Six M2.5 screws pass through a
retainer plate and clamp the stack:

    retainer  →  membrane disc  →  GASKET  →  carrier wet face

Rendered, top to bottom, in `cad/exports/head-end-exploded-labelled.png`
(the red ring). Geometry lives in `cad/membrane_cartridge_common.scad`
(`gasket_t`, `gasket_squeeze`, `gasket_id()`) and is consumed by
`cad/o2_probe_head_end.scad`.

**It is not the carrier-to-head seal.** That is a separate, already-sourced radial
O-ring (`ORS116787`, EPDM 70 Shore A peroxide-cured, 24.0 × 1.5, DIN 3771). Do not
re-source that, and do not assume the same product line answers this need — the duty
is different (static face seal under screw preload, versus radial squeeze).

## 2. Geometry

| | value | status |
|---|---|---|
| Bore (ID) | **17.0 mm** | **FIXED** — `gasket_id() = window_d + 1.0` |
| Outside diameter | **21.0 mm** | **FIXED** — `window_d + 2 × land`, land = 2.5 mm |
| Free thickness | 1.0 mm | **ASSUMED** |
| Compression | 25 % | **ASSUMED** |
| Compressed thickness | 0.75 mm | derived from the two above |
| Pocket depth in the carrier | 0.93 mm | derived: membrane 0.18 + gasket 0.75 |

**Why the bore is deliberately larger than the window.** The gas window is Ø16.0 and
the bore is Ø17.0, so the gasket seals *beside* the gas path rather than in front of
it. A bore at or below the window diameter would sit inside the carrier's flare cone
and put one compressed gasket thickness of straight, dead-ended channel in series
with the membrane. **Do not propose a part whose bore is ≤ 16.0 mm.** A bore larger
than 17.0 is acceptable only if it still leaves a continuous seal land inside
Ø21.0 — state the land width you are leaving.

**If you propose a different free thickness**, both of these must still hold:

- Compressed thickness must be re-checked against the connected gas volume budget of
  **5.0 cm³**, which currently stands at 4849 mm³ — a **3.0 % margin**. A thicker
  gasket enlarges the pocket and eats into it. Report the volume delta, do not
  hand-wave it.
- The carrier pocket is machined/printed to `pocket_depth`, so a thickness change is
  a CAD change, not a drop-in. Say so explicitly if you propose one.

## 3. Environment — this is the gating specification, not the dimensions

The probe is **buried in active compost** for extended periods. The gasket sees:

- **NH₃-rich condensate** (ammonia, in solution and as vapour)
- **organic acids**
- **H₂S**
- **up to 75 °C**
- **repeated wet–dry cycling**
- sustained compressive strain for the whole service life (it is under screw preload
  continuously, so **compression set** matters as much as chemical resistance)

**The known hard exclusion:** fluoroelastomers. FKM and FFKM are attacked by
ammonia. Do not propose them however good the temperature rating looks — this has
already been decided in `MEMBRANE.md` and is not open for re-litigation.

**The open question you must actually answer:** EPDM is the incumbent assumption,
carried over from the O-ring, and **its ammonia compatibility at these conditions is
recorded as UNVERIFIED in this repo.** It is not enough to find an EPDM sheet washer
in stock. Either:

1. produce primary evidence — a manufacturer's chemical-compatibility table, a
   compound test report, or a peer-reviewed source — that a *specific* EPDM compound
   holds up against NH₃ + organic acids + H₂S at 75 °C under sustained compression;
   **or**
2. name a better-evidenced alternative and show why it beats EPDM on that evidence.

Silicone (VMQ) is worth checking and worth being sceptical about: good temperature,
but hydrolytic stability in hot wet alkaline conditions needs evidence, not
assumption. Peroxide-cured versus sulphur-cured matters for EPDM in this service;
say which you are quoting.

## 4. What is UNKNOWN and must come back with a number

These are the reason this task blocks other work. **The screws cannot be sized until
these exist.**

1. **Minimum residual sealing load** — the compressive stress the joint must retain,
   after compression set, to keep a gas-tight perimeter.
2. **Compression–force curve or compression modulus** for the proposed compound and
   hardness, so the load at 25 % (or your proposed) compression can be computed.
3. **Hardness** (Shore A), stated, not inferred.
4. **Compression set** at temperature over time (ISO 815 / ASTM D395 style data).

A brief that returns a part number without items 1–3 has not finished the job. If
the data does not exist publicly, say so plainly and say what measurement would get
it — do not substitute a plausible number.

## 5. Sourcing constraints

- **EU availability**, small quantities (prototype: single-digit pieces; pilot: tens).
  Use `country="DE"`, `search_lang="de"` for distributor and pricing queries.
- Cut sheet washers, die-cut parts, and O-ring-style moulded washers are all
  acceptable. Cutting from sheet stock is acceptable **if** you state the sheet
  product, its compound, and how the 17.0/21.0 diameters are to be produced
  repeatably.
- Note lead time and minimum order quantity. A part that only sells in 1000s is a
  finding, not a solution — report it as such rather than discarding it silently.

## 6. Deliverables

Write findings into **`MEMBRANE.md`**, which already holds the sourcing table and the
open-gaps list (see its "Still open" section, item 4, which is this task). Do not
create a parallel document. Deliver:

1. **A ranked shortlist**, two or three candidates, each with: manufacturer, compound
   designation, hardness, dimensions, thickness, EU distributor, price, MOQ, lead time.
2. **The chemical-compatibility evidence** for each, cited to a primary source with a
   reachable URL and the exact document title. A distributor's marketing page is not
   a compatibility source.
3. **The mechanical numbers** from §4, or an explicit statement that they are
   unavailable plus the measurement that would settle it.
4. **A recommendation**, with the reason, and the single strongest argument *against*
   it stated as well.
5. **Any CAD consequence** — if your recommendation changes thickness, bore or
   compression, say exactly which parameter in
   `cad/membrane_cartridge_common.scad` moves and what it costs in gas volume.

## 7. Rules — these are not optional

- **A 402/403 or other failed fetch means BLOCKED, not absent.** Never conclude that
  a vendor does not publish a datasheet from a failed request. Climb the
  blocked-fetch ladder in `~/.claude/CLAUDE.md` from cheapest to most expensive and
  stop at the first real response. Judge responses by content, never status code.
- **Never guess an interface dimension of a real object.** If a dimension cannot be
  read from a primary source, ask — do not interpolate from a drawing or a photo.
- **Do not invent findings.** If EPDM survives scrutiny, say so plainly. A brief that
  manufactures a problem to look thorough is worse than one that reports "the
  incumbent choice is fine, here is the evidence".
- **Mark every unverified claim as unverified**, inline, where it is made. One
  blocked check must not abandon the task: mark that claim `unverified` and continue
  with what the rest can decide.
- **Distinguish the compound from the family.** "EPDM" is not a specification;
  "EPDM 70 Shore A, peroxide-cured, compound X" is.
- Do not commit private credentials or lab network details.

## Why this is on the critical path

- **The screws cannot be specified without it.** `pt_pilot_d = 2.1` is a bare
  placeholder in the CAD with no rationale, and the thread-forming screw choice
  (Delta PT / EJOT PT / Plastite, A2) has no preload target to be sized against
  until §4 exists.
- **It gates the ASA prototype's validity.** With a printed ASA carrier there is no
  weld, so the membrane is compression-only and the gasket carries the whole
  membrane seal. A styrenic under sustained gasket load in NH₃ is an
  environmental-stress-cracking risk, so the gasket's required load is also what
  decides whether a printed carrier can hold a membrane at all.
- **It shares the ammonia question with the O-ring.** Whatever evidence settles EPDM
  here settles it for `ORS116787` too — one of the two remaining blockers on the
  whole head.
