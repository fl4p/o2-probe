# Potting the o2-probe PCB

**Status:** design decision written 2026-09-04 against `PLAN.md`, which specifies
that potting must be *specified before assembly* but never specifies it.
Compound sourced the same day: §3 now rests on both primary Electrolube data
sheets. The one property that decides the compound — polyether vs polyester
backbone — appears on neither sheet and is still open (§3.3). CTE is likewise
unsourced and §4 flags where that matters.

`PLAN.md` already fixes the architecture — potted zone `y = 0…82`, removable dam
at the `y = 82` datum, gas zone conformal-coated and never potted, cable strain
relief carried by the pot, cell inserted last. What is missing is the compound
class, the pour, and the sequence. This document supplies those, and opens with
the one thing that has to be fixed before any of it can be executed.

---

## 1. No trimmer — the cell must be swappable with the board potted

**Requirement, set by Fab 2026-09-04:** the cell is replaceable with the PCB
already potted. That is a stronger constraint than "the pot must not block
assembly", and it settles an open Phase 1 decision by elimination.

### 1.1 What the trimmer was actually for

`PLAN.md` option (a) is a per-board trimmed VREF, "trim measured as
`V_WE − V_RE` **with the real cell connected**". It reads like a reference
accuracy problem and it is not. The error being trimmed out is the LMP91000's
**internal** bias divider: the step tolerance is **±2 % of VREF ≈ ±50 mV**
(`PLAN.md`, AFE bias verdict), against a cell window of ±10 mV. Trimming VREF
compensates an internal percentage error by moving its input.

Two consequences follow immediately, and the second one corrects an earlier
version of this document:

- The trim needs the real cell, the cell may never see cure heat, and the trim
  network is on the potted side — so as written the board is potted before it can
  be trimmed and unadjustable afterwards. Under the swap requirement it is worse
  still: every cell replacement would need a trim the pot has made unreachable.
- **Measuring VREF with an ADC does not help.** An earlier draft of this section
  recommended routing the reference node to a spare ADC input; that is wrong.
  VREF is not where the ±2 % lives. The only node carrying the real information
  is the differential `V_WE − V_RE`.

### 1.2 Decision: fixed reference, measured bias, no adjustable part

**Keep VREF a fixed precision 2.5 V. Delete the trimmer. Measure the bias and
report it.**

Note that VREF is deliberately shared with the ADS1119's external reference
(`PLAN.md`, ADC) to make the chain ratiometric. So a *settable* VREF — a DAC or
digipot, floated in an earlier draft — is not a free substitute for the trimmer
either: it moves the ADC full scale along with the bias. Fixed is better on its
own merits, not merely simpler.

Measuring instead of setting is a half-loop, and the honest form of the argument
is this: bias error is **not** a gain term that can be divided out. It moves the
cell's operating point, and `dI/dV_bias` for this cell is uncharacterised,
especially at 75 °C. What makes measurement sufficient is the *plateau*: on the
diffusion-limited part of the O₂ reduction wave, sensitivity is flat, so an
in-situ calibration at whatever bias the board actually has absorbs the error.

**This is gated on one bench measurement that has never been made** (§1.4).

### 1.3 The measurement path pays for the guard

RE is the sub-µA node the driven guard exists to protect, so the ADS1119's
switched-cap input cannot sit on it. A low-leakage unity-gain follower is
required — and `PLAN.md` already asks for a buffer in this area for a different
reason: the driven guard is specified as a **buffered divider at ≈0.91·VREF**,
an *open-loop replica of the expected RE potential*.

**Buffer the actual RE node instead and one part does both jobs:** a guard that
tracks the real electrode rather than a prediction of it, and the ADC channel
that makes the bias telemetry. This is standard guarded-electrometer practice
and it is strictly better guarding than the divider.

To verify, not assume:

- **input bias current at 75 °C** — it roughly doubles per 10 K, but even 50 pA
  is about four decades below the 335 nA that represents 0.1 % O₂, so this is
  expected to close comfortably. Confirm from the datasheet curve, not the
  25 °C typ.
- **follower stability driving a large guard plane** — wants a series isolation
  resistor; this is a compensation question, not an afterthought.
- WE must be measured too. It is a driven node and therefore easier, but it must
  not be loaded either.

Candidate parts to fetch datasheets for, **not selections**: **ADA4530-1**
(femtoampere electrometer amplifier with an *integrated guard buffer*, close to
purpose-built for exactly this), LMP7721. Temperature grade is the first thing
to check on each — the probe's ambient is the pile, not a lab.

### 1.4 The measurement that decides it, and the fallback

Sweep the cell bias and record current in air, at **20 °C and again at 75 °C**.

- **Plateau comfortably wider than ±50 mV** → measurement is sufficient, and
  `PLAN.md`'s "fixed 2.5 V VREF is off the table" reopens in the fixed-plus-
  measured form above.
- **Plateau narrow** → the exit is the **discrete potentiostat**, `PLAN.md`
  option (b), already co-equal. It sets bias from a precision divider with
  op-amp accuracy and has no ±2 % internal step error to trim in the first
  place.

Neither exit contains a trimmer. The trimmer was only ever a workaround for one
part's internal tolerance, and it is the one option incompatible with a potted
board and a swappable cell. **Drop it from the Phase 1 option set.**

### 1.5 Consequences to carry

- **The release gate changes.** `PLAN.md` currently reads "AFE error budget
  closes: bias within ±10 mV incl. VREF + step tolerance". Under a measured
  bias it becomes: *bias known to ±X mV, reported as telemetry, with the
  sensitivity penalty across that range bounded by the §1.4 sweep.* That is a
  Phase 1 exit-criterion change, not only a schematic change.
- **Swap needs no electrical adjustment** — only recalibration in gas. Good, and
  the point of the whole exercise.
- **Two things do not exist yet and "swappable" is a lie without them:** a
  zero-gas procedure for a probe that cannot be opened at the potted end, and a
  **per-cell calibration constant writable over Modbus into NVM**. A swap that
  needs a programmer is not a field swap.
- **The mechanics are NOT already in place — I had this wrong.** An earlier
  draft of this section said "a printed head on an O-ring so the gas end opens
  without touching the pot". The head does not open: the sealing stack at the top
  of `cad/o2_probe_head_end.scad` **bonds the head to the tube**, continuously and
  circumferentially. So the head never comes off, and the only path a cell can
  take is axially out through the carrier well. Measured from the model on
  2026-09-04 (`CELL SERVICE:` echo, and the assert beside it):

  | | |
  |---|---|
  | extraction travel | 17.6 mm |
  | radial clearance in the neck | **1.0 mm** (Ø14.4 can in a Ø16.4 neck) |
  | radial clearance in the spigot bore | 1.8 mm (Ø18.0) |
  | blind reach, head end face to can top | 4.6 mm through an Ø18 bore |

  It fits — the geometry does clear, and there is now an assert that says so
  rather than prose. But fingers do not enter an Ø18 bore, **no extraction tool
  exists**, and re-insertion means aligning three pins into a socket you cannot
  see. Swappability is a *tooling* problem that is still entirely open, not a
  solved one.

## 2. What the pot is for, and the trap

The pot does three separable jobs:

| job | what actually delivers it |
|---|---|
| cable strain relief | the pot **plus a mechanical anchor** (§5) — not the pot alone |
| remove the condensing air volume over the AFE | absence of voids (§4) |
| raise creepage across wet surfaces | adhesion at the soldermask, over the driven guard |

**The trap: the pot is not a moisture barrier.** Every organic potting compound
is water-vapour permeable. Over months at ~100 % RH and up to 75 °C, water
reaches the copper through the bulk whatever is poured. The tube, its end seal
and the cable gland are the barrier; the pot is not, and must not be relied on
as one.

What potting *does* achieve is removing the places where that water can turn back
into a liquid film. The failure mode is therefore **a void, not permeation**. A
void at the LMP91000's RE escape is a condensation cell inside the pot, and
`PLAN.md`'s own arithmetic says ~1.8 MΩ of wet contaminated surface across
600 mV already fakes 0.1 % O₂ (≈ 335 nA). A 1 mm bubble against the guard ring
is exactly that resistance class. **Void-freedom over the AFE is the acceptance
criterion for this process**, and it is worth more than any property on a
datasheet.

## 3. Compound: Electrolube UR5604 (lead), UR5041 (runner-up)

**Sourced 2026-09-04.** Both primary technical data sheets have now been read
(Farnell mirrors — `2331334.pdf` UR5041, `1782236.pdf` UR5604, both 200/PDF),
plus the Electrolube product selector. The MacDermid and Gluespec pages remain
403-blocked; the datasheets came in around them, so nothing below is inferred
from a blocked page.

### 3.1 Why polyurethane, and why not the alternatives

**Epoxy is rejected on stress, not exotherm.** It is a Shore D material at ~3 GPa,
and §4 shows the pot is volumetrically constrained; rigid plus constrained plus a
70 K annual swing cracks the pot or delaminates it from the soldermask, and a
delamination is exactly the void of §2. Epoxy also makes rework impossible on a
Rev-A board whose AFE topology is still unsettled. *(An earlier draft also
rejected epoxy on exotherm. The measured PU exotherm figures in §3.2 show that
argument was weak for this geometry and it should not be leaned on.)*

**Silicone is rejected on two independent grounds.** Best temperature and modulus
on offer, but (a) its adhesion is poor by design, so the compound/soldermask and
compound/tube interfaces become continuous capillary paths — the one thing the
pot exists to remove; and (b) `MEMBRANE.md` already requires the PMV15T membrane
to be handled "away from oils, **silicone** and solvent vapour". Curing 70 g of
silicone in the same tube as that membrane contradicts a rule this project has
already written down.

### 3.2 The two candidates, measured

| | **UR5604** | UR5041 |
|---|---|---|
| vendor tag | tough, flexible, thermally conductive, FR | sea-water resistant, low water absorption |
| Shore | **A75 / D25** | A85 |
| thermal conductivity | **0.45 W/m·K** | 0.25 |
| temperature range | −40 to **+130 °C** | −60 to +125 |
| short term (30 min) | **+155 °C** | +130 |
| exotherm (100 ml, Ø49.4 mm) | **< 35 °C** | < 50 °C |
| shrinkage | < 1 % | **< 0.5 %** |
| water absorption (10 d @20 °C / 1 h @100 °C) | <0.5 % / <1 % | <0.5 % / <1 % |
| **CTI** | **> 600 V** | **Not Measured** |
| **halogens** | **"Contains No Halogens"** | not stated |
| volume resistivity | 10¹⁴ Ω·cm | **10¹⁵** |
| usable life / gel (20–23 °C) | **40 / 90 min** | 20 / 60 min |
| mix ratio by weight | 5.21:1 | **3.64:1** |
| cured density | 1.54 g/ml | **1.18** |
| elongation at break | not measured | **200 %** |
| UL94 | V-0 | none |

Four things fall out of this table that could not be guessed:

1. **UR5041's specialist claim does not survive the comparison.** Its tag is
   sea-water resistance and low water absorption — but the measured water
   absorption is **identical on both sheets**, same test, same numbers. Its real
   datasheet differentiators are elongation (200 %) and one decade of bulk
   resistivity, not water uptake. The marketing tag pointed at our application;
   the measurement does not.
2. **UR5604 states CTI > 600 V; UR5041 states "Not Measured".** Comparative
   Tracking Index is precisely the surface-leakage-under-wet-contamination
   metric, and §2 says our failure mode is a wet surface path in the ~1.8 MΩ
   class. This is the single most relevant number on either sheet, and only one
   product has it.
3. **UR5604 states "Contains No Halogens".** That is §3.3's halide-free
   requirement, met explicitly on the sheet. UR5041 is silent.
4. **Bulk resistivity is not the discriminator it looks like.** UR5041's 10¹⁵ vs
   10¹⁴ Ω·cm is a decade — but our leak is a *surface* path, which is CTI, and
   both figures are astronomically above anything that matters here. Do not
   trade CTI away for it.

**Lead candidate: UR5604.** It wins on the two properties that map directly onto
this design's actual failure mode, and its 40 min usable / 90 min gel life is
double UR5041's — which is what makes the slow, careful, single-pass pour of §4
executable by hand.

**Counting against it, honestly:** shrinkage < 1 % against UR5041's < 0.5 %;
density 1.54 makes a heavier pot (§4); the 5.21:1 mix ratio is awkward for hand
batching and a mix-ratio error on a PU hurts cure quality directly; and there is
one ageing datapoint that deserves attention — **after 600 h at 155 °C it goes
A75 → A92 with 7 % weight loss.** That is an accelerated figure at twice our
service temperature, not a service prediction, but it says the compound
*embrittles* with thermal age, and §4's stress-relief argument depends on it
staying soft. UR5041's sheet offers no ageing data at all, which is not better —
it is unknown.

### 3.3 The question neither datasheet answers

**Polyether vs polyester backbone.** Both sheets say only "Base Material:
Polyurethane". Polyester-based PU hydrolyses in hot, wet, alkaline service —
a literal description of this probe, with ammonia supplying the alkalinity.

This is the one open item that can still overturn the selection, and it must go
to Electrolube directly, together with:

- polyether or polyester, in writing;
- hydrolysis performance at ~75 °C / ~100 % RH, and behaviour against NH₃ and
  H₂S;
- confirmation that "Contains No Halogens" extends to total ionic/extractable
  content, which is what the sub-µA leakage claim actually rests on;
- adhesion data to FR-4 soldermask and to the tube stock once §9.3 fixes it.

### 3.4 Ordering

| | order code | pack | price (ex VAT) |
|---|---|---|---|
| UR5604 | Farnell DE **2377534** (`UR5604RP250G`) | 250 g resin pack | € 27.14 |
| UR5041 | RS DE **1608481** | 250 g pack | € 31.19 |
| UR5044 *(soft, **re-enterable**)* | Farnell DE **108787** | 250 g pack | € 29.53 |

At 71 g/probe (§4), three probes need 213 g — so a single 250 g pack covers the
run with no margin for a practice pour, the leakage coupon, or one failure.
**Buy 2 × 250 g.** A 5 kg kit exists (simpex.ch) but is only worth it with bulk
mixing gear.

**The resin-pack format is a real process advantage and partly replaces a vacuum
chamber.** Electrolube's sheet states both parts are *evacuated prior to packing*
and mixed inside the sealed bag, "ready for use immediately after mixing" — so
the compound arrives degassed and never sees open air before the pour. Note the
consequence: a pack cannot be resealed, so **one pack, one session**, and the
whole pour must fit inside the 40 min usable life.

**UR5044 is worth one pack as insurance.** Its specialist property is
*re-enterable* — it can be dug out for rework. On a Rev-A board where §1's bias
architecture is still undecided, being able to recover one prototype from a
mistake may be worth more than any property in §3.2. Shore A40, −60/+120,
k 0.25.

## 4. Geometry, volume, and why the free surface is a design rule

Bore ≈ 28 mm, potted length 82 mm:

    cavity  = π/4 · 28² · 82   ≈ 50.5 cm³
    board + components         ≈  4–5 cm³
    compound per probe         ≈ 46 cm³  →  71 g at UR5604's 1.54 g/ml

Three probes = 213 g, plus mixing loss, a practice pour and the leakage coupon.
**Buy 2 × 250 g** (§3.4). The earlier 50–65 g estimate used a guessed density;
the real figure is higher because the lead candidate is mineral-filled.

**The free surface.** Rubber-like compounds are shear-soft and bulk-*in*compressible
— the same fact the membrane O-ring analysis turns on. Softness relieves stress
only if the displaced volume has somewhere to go. Differential expansion against
the tube over a 5 → 75 °C swing:

    ΔCTE ≈ 100 ppm/K (PU ~150–200 vs PVC-U ~70–80)   [unverified, class figures]
    ΔT = 70 K → 0.7 % linear ≈ 2.1 % volumetric
    excess ≈ 46 cm³ × 0.021 ≈ 0.95 cm³
    over the 6.16 cm² bore → ≈ 1.5 mm of axial creep

So:

- **The pot must have exactly one free surface, and it is the dam end at
  `y = 82`.** The cable end is closed by the cap and gland. If both ends are
  confined, that 2 % has no relief path and a 2 GPa bulk modulus turns it into
  hydrostatic pressure on the board.
- **Budget ~1.5 mm of hot axial creep past `y = 82`.** `PLAN.md` already reserves
  `y = 80…86` from ordinary parts, so it fits — but terminate the meniscus *at*
  82, not at 84, and put the creep figure in the assembly drawing so nobody
  later reads the reserved band as spare room.
- Centre the board with the non-metallic guides so there is no zero-gap contact
  against the tube wall. A board touching the bore is an unfillable line, not a
  small one.

**Pour cable-end up, in one pass.** An earlier draft called for two ~25 cm³
passes to hold the exotherm down. **The measured data retires that argument:**
UR5604's exotherm is < 35 °C on a *100 ml* sample in a *Ø49.4 mm* cylinder — a
larger mass in a wider bore than ours, so our 46 cm³ in a Ø28 mm tube is not an
exotherm case at all. Two passes also cannot be poured from one resin pack
(40 min usable life against a 90 min gel), so the two-pass process would have
doubled the compound spend to solve a problem that does not exist.

Single pass, and spend the effort on voids instead: the compound arrives
pre-evacuated in the pack (§3.4), so pour slowly down one side so air is pushed
ahead of the front rather than trapped under components, then pull a vacuum cycle
on the *assembly* before gel. The 90 min gel time is what makes that unhurried.

Electrolube's sheet adds one rule that applies directly: *"Do not heat cure large
volumes immediately. Allow these to gel at room temperature and post-cure."*
At 46 ml we are inside their "small volumes (250 ml) may be heat cured
immediately" allowance, but there is no reason to take it — gel at room
temperature, then post-cure.

**The dam is a fixture, not a part.** A machined two-piece clamp on the `y = 82`
datum with a soft face, removed after cure — `PLAN.md` already assigns it the
datum ownership because Rev-A boards have no physical legend.

## 5. The cable is the actual leak path

Bulk potting does not stop capillary flow **inside** a stranded conductor. Two
independent measures, both cheap:

- **Water-blocked cable**, or, failing that, **fully tin each conductor through
  its whole stripped length** so solder fills the interstices, and keep both the
  jacket cut and the tinned length inside the pot. Solder is the strand block.
- **A mechanical anchor inside the pot** — a clamp, tie or knot on the jacket —
  so cable tension is reacted by the anchor and never by the solder joints. The
  pot is a *distributor* of strain relief, not the origin of it.

Abrade and degrease the jacket where the pot grips it; jacket compounds are often
exactly the materials PU does not stick to. The gland in the end cap is the
second, independent barrier and should be specified for the actual cable OD, not
for its nominal range.

Soak-and-cross-section a terminated sample in the bench phase, as `PLAN.md`
already requires. That test is what closes this section.

### 5.1 The cable, by part number

`CABLE-SOURCING.md` closes the cable half of item 4 below.

**Bought 2026-09-05: LAPP UNITRONIC SENSOR FD Lif9Y11Y 4x0,25, article 7038890**
— PUR, unshielded, UV- and oil-resistant, **−40…+80 °C fixed, −25…+80 °C
flexed**, **OD 3,80 mm**, €1,70/m net from automation24. Chosen under a
later OD < 5 mm constraint that excluded every candidate below. It is
dimensionally the same cable as Truebner's TrueFlex but with a *published*
temperature rating, which is what TrueFlex lacked.

Previously recommended, and still the answer if vendor chemistry language
outranks diameter:

- **LAPP ÖLFLEX ROBUST 215 C 4X0,5, article 0022704** — TPE, shielded, UV and
  ozone resistant to EN 50396 / HD 605 S2, −50…+80 °C fixed, **OD 6,6 mm**.
  LAPP's 2017 application sheet names composting plants and claims "good
  resistance" to ammonia compounds and bio-gases. Treat that as application
  guidance, **not qualification**: LAPP publish no concentration, duration,
  temperature or test method behind it, and the current product page omits the
  language entirely. It is still the only candidate whose vendor names the medium
  at all. Avoid the `4G` variant 0022703: the G forces a green-yellow core.
- **Fallback above ~75 °C at probe depth:** ÖLFLEX HEAT 125 C MC 4X0,75, article
  1024482, −55…+125 °C, OD 8,4 mm.

Four consequences for this section:

1. **Nothing here is water-blocked.** The tinning fallback in the first bullet
   above is therefore not a fallback but the plan.
2. **PUR is the right jacket family for a PU pot** — which is why the
   fluoropolymer options (ÖLFLEX HEAT 205 C MC, FEP, −100…+205 °C) were not
   chosen despite their temperature: FEP is exactly the material this section
   warns that PU does not stick to. But "a PU pot will grip PUR once abraded" is
   a **materials-class expectation, not a measured result** — adhesion is
   formulation-dependent and no peel or pull test has been run. The terminated-
   cable coupon this section already prescribes is what settles it; until that
   coupon survives thermal and wet exposure, the bond is assumed, not known.
3. **The ordered cable is unshielded and has no defined A/B pair.** See
   `CABLE-SOURCING.md` §1: if the heater is ever enabled, scope A−B at worst-case
   PWM duty and count CRC errors before trusting the link.
4. **The colour convention breaks on the ROBUST parts** (cores numbered on black,
   not DIN 47100 white/brown/green/yellow), so if one of those is bought instead,
   record the number→function map in `DESIGN.md` and on the probe label.

### 5.1.1 The gland

**LAPP SKINTOP INOX-R M12x1,5, article 53806749** — 316L body, **silicone** seal
and O-ring, clamping **3,0–5,0 mm** (the cable's 3,80 mm sits at 40 % of the
band), −40…+100 °C, IP68 10 bar / IP69, thread length 6,5 mm, SW 16. Sold in
fives at roughly €19–21 each. Full reasoning and alternatives:
`CABLE-SOURCING.md` §5.2.

Two things drive that choice, and both are chemistry rather than fit:

1. **No brass, ever, on this probe.** Ammonia is the classic stress-corrosion-
   cracking agent for brass, the effect is *worse in vapour than in liquid*, and
   the literature's own example of the hazard is ammonia from decaying organic
   matter. A gland is a pre-stressed brass part; a windrow is an ammonia vapour
   generator. That rules out the entire default nickel-plated-brass category.
2. **No FKM seals.** LAPP's SKINTOP HYGIENIC-R fits the cable better than
   anything else found (3,0–4,5 mm) and is 316L, but its seals are FKM — the one
   elastomer family whose published exception list names ammonia, strong bases
   *and* hot water. Silicone and TPE are both ordinary ammonia-service choices.

**Do not tap the gland thread directly into the plastic cap.** `MEMBRANE.md`'s
rule against sustained strain in plastic at 75 °C applies exactly here: the cap
would creep and the seal relax. Use a thin cap wall plus a stainless locknut so
the load path is metal-to-metal — but note the arithmetic, because it is tight:
thread length 6,5 mm minus a 2,8 mm M12 locknut leaves a **maximum ~3,7 mm cap
wall**. If the cap must be thicker, a stainless M12x1,5 threaded insert is the
alternative. This is an enclosure decision that `PLAN.md` has not yet made.

Still measure the delivered cable's OD before fitting: 3,80 mm is a nominal, and
a gland working at the bottom of its clamping range is the leak this whole
section exists to prevent.

### 5.2 If the run has to be joined

A joint is permitted; an improvised joint is not. Two sanctioned routes:

- **Soldered inline splice**, per Truebner's own procedure
  (`truebner.de/de/anleitung_kabelverlaengerung.php`), **sited above grade or in
  an accessible hand-hole, not buried** — Truebner's FAQ says the contact point
  must never sit in soil, and their extension guide never withdraws that: stagger
  the four core lengths, **solder only** — Truebner rule out clamp, crimp and screw joints for
  long-term corrosion resistance — one adhesive-lined sleeve per core, then a
  **25 cm** adhesive-lined outer sleeve, sized for the ground. Truebner's named
  part is CellPack SRH2 8/2 (Voelkner X774691), which fits TrueFlex's 3,8 mm —
  **and therefore fits the ordered 7038890 unchanged**, since it shares that OD;
  a 6,6 mm ROBUST 215 C would need roughly 19/6 instead.
- **A field-terminable connector pair**, per
  [`../../tech/CONNECTORS.md`](../../tech/CONNECTORS.md), when the joint has to
  be serviceable.

What is forbidden is what Truebner's FAQ warns about: tape or non-adhesive
heat-shrink, buried.

## 6. Cleaning, bake, and a hazard `PLAN.md` has not caught

Before the pour: **no no-clean flux left under the pot.** Ionic residue plus the
water vapour that §2 says will arrive is the leakage mechanism, and it is sealed
in permanently. Use cleanable flux, wash, DI rinse, and bake (100–125 °C, ≥ 2 h)
to drive out absorbed moisture — PU cure is moisture-sensitive too, so a damp
board foams the compound at the very interface that must be void-free. Pot within
hours of the bake, and run a **leakage/SIR coupon through the identical process,
with a socket fitted, measured after the soak** — as the socket bullet in
`PLAN.md` already demands.

**New hazard — potting outgassing versus the SHT45.** The O₂ cell is protected by
being absent, but the SHT45 is reflow-soldered and cannot be. Sensirion's
handling instructions warn about outgassing from potting compounds and adhesives
contaminating RH sensors, and 50 g of curing PU is a large source inside a tube
whose other end is the gas chamber. Mitigations, in order:

1. cure with the gas end **open and ventilated**, never capped;
2. treat the RH channel as suspect until re-baselined;
3. **reuse the reconditioning recipe already in `PLAN.md`** — bake 100–105 °C at
   < 5 %RH for 10 h, re-hydrate ~75 %RH for 12 h over saturated NaCl — as a
   scheduled *post-potting* step, not only as a service procedure for pulled
   probes.

That third item costs nothing; the recipe is already written down for a different
reason.

## 7. Thermally, potting is a net win — risk #2 should say so

`PLAN.md` risk #2 lists "the potting ΔT (no convection)" as a consumer of the
LMP91000's ~6 K budget. That framing is backwards. The unpotted alternative is a
sealed 50 cm³ air column in a buried horizontal tube, where convection is weak
and still air conducts at 0.026 W/m·K. Even an unfilled compound at ~0.2 W/m·K is
an order of magnitude better, and a mineral-filled one reaches 0.5–1.0 W/m·K.
Potting **couples the AFE to the tube wall**, and the tube wall is at pile
temperature.

The consequence is the honest one: potted or not, the LMP91000 cannot be cooler
than the pile. The 6 K budget is spent on **self-heating and on proximity to the
heater island**, not on the pot. Potting improves both terms. Choose a filled
compound for the thermal conductivity if the junction budget is tight — but note
that filled compounds are stiffer and more abrasive, which trades against §4.

## 8. Sequence

```
build → clean → bake → conformal-coat gas zone (apertures clear)
      → (no trim step: fixed VREF, bias is measured not set)  ← §1
      → fit dam at y=82, mount board on tube guides
      → degas, pour pass 1 (~25 cm³), vacuum cycle, gel
      → pour pass 2, vacuum cycle, cure (gas end OPEN) ← §6
      → remove dam, inspect meniscus at y=82
      → SHT45 recondition bake                         ← §6
      → electrical test with socket dummy load
      → insert cell by hand
```

## 9. Open, in priority order

1. **Run the bias-plateau sweep (§1.4) before layout freeze.** It decides
   measured-bias vs discrete potentiostat, and both are schematic changes that
   are free now and impossible after the pour. The RE follower / guard buffer
   (§1.3) lands in the same edit.
2. **Ask Electrolube the polyether/polyester question (§3.3).** Both TDSs are
   now read and neither states the backbone; it is the one open item that can
   still overturn UR5604. Put the ionic-content, NH₃/H₂S and adhesion questions
   in the same message. Note that CTE and cure shrinkage-vs-temperature are also
   absent from both sheets — §4's creep figure still rides on a class estimate.
3. Confirm the tube stock (PVC-U vs other) before quoting adhesion, and confirm
   its CTE — §4's 1.5 mm creep figure rides on it.
4. ~~Specify the cable~~ **done and ordered, §5.1 / `CABLE-SOURCING.md`** (LAPP
   7038890, OD 3,80 mm); ~~specify the **gland** by part number~~ **done, §5.1.1
   / `CABLE-SOURCING.md` §5.2** (LAPP SKINTOP INOX-R M12, 53806749) — still
   verify against the *measured* OD, and settle the cap wall thickness, which
   §5.1.1 shows is constrained to ~3,7 mm by the gland's thread length. Run the
   soak/cross-section. Two claims in §5.1 are still
   *assumed*: that a PU pot bonds to this PUR jacket (needs the coupon and a peel
   test), and that an unshielded, untwisted run survives heater PWM (needs an
   A−B scope trace and a CRC-error count once the heater is enabled).
5. Add to `audit_pcb.py`: reject a board carrying any adjustable component on
   the potted side, and reject one whose `V_WE − V_RE` sense path is missing or
   is not guarded up to the follower input (§1.3).
6. Define the field cell-swap procedure: zero gas without opening the potted
   end, and the writable per-cell calibration constant (§1.5).
7. Void inspection method for a potted 28 mm tube is unsolved. Cross-sectioning a
   sacrificial article is the fallback and should be budgeted as one of the three
   prototypes, not improvised later.
