# Will the pile gas eat the solder contacts?

**Asked 2026-09-04.** Short answer: **yes, that is a real and named failure mode,
the project already holds primary evidence for it, and the one decision that
matters most has — by luck or by good instinct — already been made correctly.**

**Revised the same day** once the concentration data was actually looked up
(§2.5): the exposure is 3–5 orders of magnitude above the levels behind the
industry failure literature, so this is not a background risk.

Nothing in the `o2-probe` hw repo mentions contact corrosion anywhere. This
document is the first place it is written down.

---

## 1. The evidence is already in the repo

`PLAN.md` risk 12 quotes Sensirion's *Handling Instructions SHTxx* (June 2025,
archived in the **compostlab-literature** repo at SHA `80be25d`):

> §4 "notes low-level corrosives spare the element but **corrode solder
> contacts** → passivate contacts (conformal coat over pads, aperture clear)"

That was recorded as an SHT45 sensor-survival note. It is not. It is a statement
about **every solder joint in the gas zone**, made by a vendor about exactly this
class of atmosphere, and it was filed under the wrong heading.

## 2. What actually attacks what

The pile gas carries **NH₃** and **H₂S** at ~100 % RH, up to 75 °C, with
condensation the whole probe is designed to fight. Three different mechanisms,
and they do not target the same metal:

| species | attacks | mechanism |
|---|---|---|
| NH₃ | **copper**, brass | cuprammonium complexing; SCC in stressed brass |
| H₂S | **silver**, copper | sulfidation — Ag₂S, Cu₂S |
| H₂S | exposed copper at the mask edge | **creep corrosion** (below) |

**Creep corrosion is the one to worry about.** In sulfur-bearing atmospheres,
copper sulfide nucleates at exposed copper — typically the pad/solder-mask
interface — and then *migrates across the mask surface* as a conductive film,
bridging adjacent pads. It is a documented industry failure (iNEMI and IPC work
following field failures in paper mills, waste-water plants and some data
centres) and it does not need condensation, only humidity and sulfur. A compost
pile is a textbook source atmosphere.

Note what makes it nasty: it is not loss of the joint. The joint stays fine and a
**new conductive path appears where the design assumed none** — which on this
board is the failure that `PLAN.md`'s ~1.8 MΩ / 335 nA arithmetic says fakes
0.1 % O₂.

## 2.5 How much H₂S — the data exists, and it is worse than "present"

An earlier draft of this document closed with "nobody has estimated the pile's
actual H₂S concentration". **That was wrong.** `research/COMPOST-GAS.md` in the
compostlab repo has it, inspected against primary sources:

| condition | H₂S | source |
|---|---|---|
| healthy aerobic pile | **~0** — "the channel reads ~0; it fires on anaerobic pockets with S-rich feedstock" | §3.2 |
| sludge exhaust, day 2 (ceased after day 5) | **49.7 mg/m³ ≈ 35 ppm** | Zheng 2022, partial |
| 10-s peaks, disturbing anaerobically-stored spent mushroom compost | **89–2083 ppm** | Velusami 2013, inspected |

`COMPOST-GAS.md` characterises it as **episodic**: "first days of sulfur-rich
feedstock, or on disturbing anaerobically stored material". Driver is
sulfate/protein-rich feedstock plus anoxia.

### Why this makes the risk larger, not smaller

Documented creep-corrosion field failures — the data-centre, paper-mill and
waste-water cases behind the iNEMI/IPC work — occur in ISA-71.04 **G2/G3**
environments, driven by H₂S at **single-digit to tens of parts per *billion***,
continuously, over years.

Our numbers are in parts per *million*. Even the modest 35 ppm figure is
**~3 orders of magnitude** above the concentrations that corrode electronics in
those cases, and the disturbance peaks are five. ISA-71.04 has no class for it;
GX ("severe") starts far below.

The honest counterweight is **dose**: theirs is continuous for years, ours is
near-zero most of the time with spikes. Integrated exposure may not be a thousand
times higher. But two things stop that being reassuring:

1. **H₂S partitions into condensate, and our cavity condenses by design.**
   `COMPOST-GAS.md` §3.2 cites Noble et al. 2001 (inspected, p. 763): bag samples
   after 24 h averaged only **52 % of the on-site value** — "H₂S disappears into
   surfaces/condensate". In a sampling line that is a measurement error. In our
   probe it is a *concentrating mechanism*: an episodic gas exposure is captured
   into a persistent liquid film, which is precisely the electrolyte creep
   corrosion needs. The probe is built to fight condensation and will not always
   win — that is why the heater exists.
2. **The exposure coincides with the measurement.** H₂S appears in anaerobic
   pockets. Anaerobic pockets are exactly what a buried O₂ probe exists to detect.
   The probe's most valuable moments are its most corrosive ones.

### The gap that is real

`COMPOST-GAS.md` states it plainly: **"No systematic pore-profile study for
ordinary green-waste windrows was found — data gap, not absence."** Every figure
above is *exhaust* or *disturbance-face* concentration. **Nobody has measured
pore-gas H₂S at depth in a windrow like ours**, which is the only number that
actually describes what this probe sits in. Treat the table as a bound on the
order of magnitude, not as the probe's service condition.

Feedstock is the discriminator, and it is knowable without new research: a
sulfate/protein-rich or manure-bearing farm pile is a plausible H₂S source; a
clean green-waste windrow is much less so. That question should go to the site
before any accelerated-ageing target is set.

## 3. The finish claim was WRONG, and inverted

**Retracted 2026-09-04**, after a browser-equipped research pass
(`reviews/ENIG-CREEP-CORROSION-2026-09-04.md`) and my own re-verification against
the primary.

An earlier version of this section said "ENIG is the **most**
creep-corrosion-resistant of the common finishes" and told the reader not to let
it be value-engineered to OSP. **Both halves are backwards.**

Primary, fetched and read directly (`thor.inemi.org/webdownload/2018/
Creep_Corrosion_APEX_Feb_2018.pdf`, 615 292 bytes, %PDF verified — Singh, Palmer,
Fu et al., *Round Robin Evaluation of iNEMI Creep Corrosion Qualification Test*,
IPC APEX 2018; IBM / iNEMI / iST / Lenovo / Dow / Nokia). Conclusions slide,
verbatim:

> ■ The test results in general agree with **the industry position** that
>    ▪ ENIG finished PCBs are **very prone** to creep corrosion and that
>    ▪ OSP finished PCBs are **very resistant** to creep corrosion.

Two things about that wording matter and are easy to miss. It says "in general
agree with the **industry position**" — so this is not one round robin's novel
result, it is a round robin *corroborating an existing consensus*, which makes it
considerably harder to dismiss as a single data point. And the leakage tables
carry it: ENIG rows read 160 / 260 / 270 / 280 / 320 / 520 / 980 kΩ (one at
0.01 kΩ), while **every OSP row at all three sites is `--`, no measurable
leakage, across all three humidity runs.**

**What survives from the old text:** immersion silver really is bad — ImAg rows in
the same tables read 24 / 53 / 384 / 580 / 702 kΩ. "Do not let it go to ImAg"
stands. "Do not let it go to OSP" does not.

**And SnPb HASL is the protective one**, for the reason of covering the copper
rather than plating over it — Xu et al. (Alcatel-Lucent / Flextronics / Sanmina):
"SnPb HASL offers excellent corrosion protection of the underlying copper due to
its thick coating". We are RoHS, so this is not available to us, but it confirms
that *exposed copper at the pad edge* is the mechanism.

### The tension the research pass glossed, and I only saw in the tables

The convenient synthesis is "flux, not finish, dominates" — and Xu et al.'s Table 2
does say that loudly (organic-acid flux 25 bad / 9 marginal / 7 good; rosin
0 / 2 / 16; bare board 0 / 0 / 11). **But the iNEMI round robin does not agree
for ENIG.** In its tables, ENIG leaked on **both** flux types — ENIG/RO (rosin)
rows still read 280 / 260 / 520 / 320 kΩ. Rosin flux did not rescue ENIG there.

So do not read "use rosin and clean well" as a licence to keep ENIG untouched.
Two primaries, two different dominant variables, and they were not run against
each other. Treat both as live.

### Why this still does not simply mean "switch to OSP"

Three reasons, and none of them is settled:

1. **OSP leaves bare copper** under a thin organic film that degrades with time and
   heat. Bare copper is exactly what NH₃ attacks. The creep-corrosion literature
   is written for indoor air, not for a condensing ammoniacal cavity, and it does
   not score that failure at all.
2. **J5 is hand soldered *after* board assembly** (`FAB-NOTES.md`). OSP degrades
   with each thermal excursion and with shelf time; a late hand-solder onto OSP is
   the weakest version of that joint.
3. **But the galvanic finding cuts the other way.** Oh et al. 2018, *Metals and
   Materials International* 24:67 (DOI 10.1007/s12540-017-7262-z): in **ammonia
   solution**, copper coupled to gold corrodes at **67 → 1360 µA/cm² as the Au:Cu
   area ratio goes 0.5 → 25** — roughly 20x. An ENIG board is a large gold cathode
   over small copper anodes, and our copper anodes are precisely the
   deliberately-uncoated aperture edges. That is an ENIG-specific liability in
   *our* atmosphere that the creep-corrosion literature does not cover.

**Net:** the finish is now an open decision, not a settled one. What is NOT open
is that the old justification was wrong, and that the exposed-copper aperture
edges are the place all three mechanisms converge. Fixing the *geometry* — moving
exposed copper away from the guard, and coating everything that can be coated —
helps under every one of them, which is why it outranks the finish choice.

## 4. Where the design is still exposed

Three interfaces, in descending order of how worried I am:

### 4.1 The cell socket — the worst one, and already known

`PLAN.md` already says it: a serviceable cell means "the pin escape can never be
potted and the mating interface can never be coated: the highest-impedance node
in the design now ends in a bare separable contact inside a condensing volume".

Add sulfidation to that. A separable contact relies on a thin, clean, low-
resistance interface; Cu₂S and Ag₂S films are exactly what a separable contact
cannot tolerate, and unlike a soldered joint it cannot be coated shut. Contact
*resistance* still is not the worry (RE carries no current), but a creeping
sulfide film across the receptacle land toward the guard ring is.

**Action:** the SIR coupon `PLAN.md` already requires — measured with a socket
fitted, after the soak — must be run in an **H₂S-bearing** atmosphere, not a plain
humidity soak. A clean-air soak will pass and prove nothing.

### 4.2 The heated-ring joint (J5)

`FAB-NOTES.md`: "The user-supplied metal membrane-carrier ring is **hand soldered
after board** assembly." So it is a hand joint, made after the fab's finish and
possibly after conformal coat, with a flux residue the process does not control —
in the cavity, ~12 mm from the CELL_RE receptacle land.

This compounds the material question in `HEATED-SPREADER.md` §5. It is also the
strongest practical argument for the **PCB-ring** option in that section: a PCB
ring can be ENIG-finished and mask-defined like everything else, instead of being
a bare dissimilar metal wetted with unknown flux.

**Action:** whatever the ring becomes, the J5 joint must be cleaned and coated
*after* soldering, and that step needs to exist in the assembly order — it does
not today.

### 4.3 The gas-zone pads generally

`PLAN.md` already specifies "selective conformal coat (apertures clear)" for the
gas zone, and §1's Sensirion quote is the justification. That is the right
control. Two gaps:

- **The apertures are deliberately clear**, so the SGX rear-vent slot edge, the
  membrane-facing copper and any castellation are bare by design. Bare copper is
  the creep-corrosion initiation site. Minimise exposed copper at those edges and
  keep it away from anything the guard protects.
- **Coating coverage over a hand-soldered joint is not the same as coating
  coverage from the coating step.** See 4.2.

## 5. What this does not threaten

Worth stating so the risk is not overrated:

- **The solder itself is not the weak link.** Tin is reasonably resistant to
  ammonia. SAC305's 3 % silver sulfidises, but the bulk joint is not consumed on
  any relevant timescale — the failure is a surface film bridging *between*
  joints, not the joints dissolving.
- **The potted zone is out of scope.** It sees no gas; §2 of `POTTING.md` explains
  why permeation is not the mechanism there.
- **FR-4 and mask are fine.** 75 °C is far below Tg, and CAF needs a voltage
  gradient between adjacent nets that most of the gas zone does not have.

## 6. Open

1. **Re-file `PLAN.md` risk 12.** It is currently an SHT45 note; it is a gas-zone
   assembly rule. The Sensirion quote applies to every contact out there.
2. **Add ENIG to the controlled fab requirements with its reason**, so it survives
   a re-quote.
3. **The SIR coupon needs an H₂S atmosphere**, not clean humidity (4.1).
4. **Add a clean-and-coat step after the J5 hand solder** to the assembly order.
5. Decide the ring material — `HEATED-SPREADER.md` §5. The PCB option removes most
   of this document's 4.2.
6. ~~Nobody has estimated the H₂S concentration.~~ **Closed — see §2.5.** It is
   in `research/COMPOST-GAS.md`, inspected: ~0 on a healthy pile, ~35 ppm in early
   sludge exhaust, 89–2083 ppm on disturbing anaerobic material. That is 3–5
   orders of magnitude above the ppb levels that drive documented creep-corrosion
   failures, so **this section is now the load-bearing risk in this document, not
   a footnote to it.**
7. **What replaces it:** no pore-gas H₂S profile exists for a windrow like ours
   (`COMPOST-GAS.md` calls this a data gap explicitly). Establish the site's
   feedstock sulfur first — it is the driver, and it is a question for
   Steingrubenhof, not for the literature.
8. ~~Re-check whether ENIG + selective conformal coat is sufficient.~~ **Done —
   `reviews/ENIG-CREEP-CORROSION-2026-09-04.md`, and §3 above is rewritten.** The
   finish rationale was wrong. Actions that came out of it, in priority order:

   1. **Bury ISA-71.04 copper + silver coupons at probe depth for 30 days this
      season.** Two coupons and an analysis convert our acknowledged pore-gas data
      gap (§2.5) into a number on the axis the entire literature uses. Nothing
      else on this list can be sized without it, and it costs almost nothing.
   2. **Parylene C for the gas zone, not sprayed acrylic/urethane/silicone.**
      Osterman (CALCE): only parylene resisted; the sprayed coatings left "little
      to no coating material… in particular on the edges of the terminals" — and
      edges are the whole problem here. Mask the apertures.
   3. **Rosin-only flux plus a real post-solder clean, and an assembly step that
      says so** — especially for the J5 hand solder. Necessary under Xu et al.,
      *not sufficient* under the iNEMI data (§3).
   4. **Move exposed copper away from the guard.** This is the one action that
      helps under creep corrosion, galvanic Au/Cu attack *and* plain NH₃ attack
      simultaneously, which is why it outranks the finish decision.
   5. **Re-open the finish choice** as a real trade (§3), not a default.

9. **`(NH₄)₂SO₄ is the mechanism, and this probe manufactures it.** iNEMI's 2014
   work could not reproduce creep corrosion in the flowers-of-sulfur chamber until
   ammonium salts were deliberately deposited on the coupons. NH₃ + H₂S +
   condensate is a synthesis route for exactly those. This flips §2.5's
   reassurance: the *gas* exposure is episodic, but the *salt* it leaves behind is
   cumulative and monotonic. Episodic gas does not mean episodic risk.

10. **NH₃ is also ISA-71.04 GX and this document buried it in a table row.** The
    GX threshold for ammonia is 25 ppm; `research/COMPOST-METROLOGY.md` cites
    >700 ppm exhaust maxima — 28x over. §2 treats NH₃ as the brass problem; it is
    also a board problem.

11. **The ISA gas table only holds below 50 % RH**, with roughly +1 severity level
    per 10 % RH above it, and >2x rate per 10 °C. At ~100 % RH and 75 °C those
    multipliers are not a footnote. Neither was in this document.

12. **Our exposure exceeds the accelerated tests, not merely the field failures.**
    The most aggressive published mixed-flowing-gas test found is 1.7 ppm H₂S
    (Alcatel-Lucent). Our 35 ppm is 20x that; the disturbance peaks are ~1200x.
    There is no standard qualification that reaches our environment, so a bench
    test will have to be argued rather than cited.
