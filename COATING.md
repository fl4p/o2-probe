# Conformal coating: what goes on the board before the pot

**Status:** researched 2026-09-07 against `POTTING.md` (compound already chosen:
Electrolube UR5604 polyurethane), `PLAN.md` §"Gas zone: selective conformal coat
(apertures clear); cannot be potted", `CONTACT-CORROSION.md`, `MEMBRANE.md` and
Sensirion's SHTxx handling instructions. Primary sources are listed in §10; every
datasheet number below came out of a vendor TDS, not a marketing page.

`PLAN.md` and `POTTING.md` §8 both say *"conformal-coat gas zone"* and neither
has ever named a chemistry or a product. This document names one, says what to do
with the **potted** zone (which is a separate question and has a different
answer), and lists the two things that must be answered by Electrolube or by a
coupon before the first pour.

---

## 1. Answer first

- **Chemistry: polyurethane (UR). Not silicone, not acrylic, not epoxy.**
- **Lead product: Electrolube PUC** — modified one-part PU, MIL-I-46058C and
  IPC-CC-830 approved, −55…+130 °C, SIR 1×10¹⁵ Ω, explicitly *"resistant to acids
  and alkalis"*, brush/spray/dip, reworkable with Electrolube CCRG. 400 ml aerosol
  `PUC400` or 5 L bulk `PUC05L`.
- **Coat both zones, not just the gas zone** — but for different reasons, and the
  potted zone is gated on one adhesion answer (§4).
- **Runner-up for the gas zone only: HumiSeal 1B51NSLU** — synthetic rubber, MVTR
  <1 g/m²·day·mil, and it is on Sensirion's *tested-compatible* list for the
  SHT4x. Use it if the SHT45 turns out to be the binding constraint.
- **Best barrier on offer, and a real option for the gas zone: parylene C** — 12×
  lower water-vapour transmission than any liquid coating and near-inert to H₂S.
  It is a coating service, not a bench step, and it must **not** go under the pot
  (§3.4).

Why polyurethane and not the obvious "acrylic is easier": three independent
reasons, in §3.

---

## 2. What this coating actually has to survive

The probe is not a generic PCBA and the usual coating-selection guides do not
cover the three constraints that decide it here.

| Constraint | Source | Consequence for the coating |
|---|---|---|
| Service: ~5…75 °C, condensing, NH₃ and H₂S present | `PLAN.md`, `CONDENSATION-MODEL.md` | needs alkali resistance and a real max-continuous rating, not a thermal-shock number |
| An SGX **electrochemical O₂ cell** sits in the gas zone | `PLAN.md` | **no silicone anywhere on the assembly** (§3.1); solvent vapour during cure is a poisoning path |
| **PMV15T PTFE membrane**, handled "away from oils, silicone and solvent vapour" | `MEMBRANE.md` | coat and *fully cure* before the membrane goes in |
| **SHT45** in the gas zone | Sensirion handling instructions | sensor opening must stay bare; masked or protective-cover; ventilated cure; full cure before assembly |
| **Sub-µA RE node with a driven guard** | `POTTING.md` §1.3 | coating *raises* SIR — good — but only over a genuinely clean board (§6) |
| **Cell must be swappable with the board potted** | `POTTING.md` §1 | coating must not enter the cell socket contacts |
| Ring-tip castellation is a **mating contact** | `HEATED-SPREADER.md` §"Can a coating save a brass ring?" | mask it; a coated contact is not a contact |
| Pot is **Electrolube UR5604 PU**, poured over whatever the coating leaves behind | `POTTING.md` §3 | the coating/pot interface must bond, not release (§4) |

---

## 3. What is excluded, and why

### 3.1 Silicone — excluded on four independent grounds

This is the one that matters most, because silicone coatings otherwise look
attractive (widest temperature range, best humidity SIR in Electrolube's own
test data, soldering-through rework).

1. **Siloxane poisoning of gas sensors.** Volatile methylsiloxanes decompose on
   a sensor's catalytic surface and leave SiO₂; the effect is cumulative and
   irreversible. Documented for catalytic methane sensors since 1978 (US Bureau
   of Mines RI 8321) and still an active failure mode in the MOS/catalytic
   literature. Curing a silicone film 30 mm from an O₂ cell is not a risk anyone
   needs to take.
2. **`MEMBRANE.md` already forbids it** — the PMV15T is to be kept away from
   silicone. Coating the same assembly with a silicone contradicts a rule this
   project has already written down.
3. **`POTTING.md` §3.1 already rejected silicone for the pot** on adhesion
   grounds. The same argument applies to a coating that has to bond to the pot.
4. **Silicone is the number-one conformal-coating contamination source in its
   own right** — "even tiny amounts can spread across the surface and create
   large craters where conformal coating will not wet" (Nexus/SCH conformal
   coating design hub). Once silicone is on the assembly it is on every later
   process step too.

**Concretely excluded products:** Electrolube FSC, Dow DOWSIL 1-2620 and 1-2577.

**Correction, 2026-09-07 — DCA SCC3 is not a silicone.** An earlier draft of this
list excluded it as "modified silicone", following the Electrolube brochure PDF,
which describes DCA as a *"high specification flexible modified silicone resin
conformal coating"*. The current vendor product page says twice that it is *"a
unique, modified **alkyd** coating"*. Two vendor sources disagree and the newer,
first-party one wins: **DCA is not excluded by §3.1.** It is still not the pick
here (an alkyd defence coating brings nothing PUC does not, and the conflict
itself is a reason to ask before putting it near an O₂ cell), but the silicone
claim was wrong and is withdrawn.

**Settled, 2026-09-18 — DCA is a modified alkyd, and the conflict was a dating
artefact.** The 2026-09-07 correction above was left resting on a single vendor
page against a single brochure, and `de.farnell.com` still sells the part today
as *"SCC3, **Silikonharz**"*, so it was reopened and closed properly. Every
source splits cleanly by date:

| Says **alkyd** | Says **silicone** |
|---|---|
| MacDermid Alpha product page — *"a unique, modified alkyd coating"*, twice (read live 2026-09-18) | Electrolube TDS **Revision 2, Jan 2014** (PDF created 2014-01-24) — *"Modified Silicone Conformal Coating (SCC3)"* |
| Current TDS, **Issue 09 March 2024** — *"Modified Alkyd Conformal Coating (Scc3)"* | `de.farnell.com` catalogue title *"SCC3, Silikonharz"* |
| electrolube.us product page | ulbrich-group.com product page |
| Electrolube DCT thinner bulletin — the whole family (DCA, DCABL, DCB) as *"Modified Alkyd"* | a 2014 Electrolube YouTube description |
| Silmid, dge-europe, henchman, oritech, ams-electronics, simpex | |

Everything dated 2014 or earlier says silicone. **The live Farnell DE and Ulbrich
pages still say silicone too**, so "everything current says alkyd" would be
circular — the honest statement is that both *first-party* sources (MacDermid's
product page and the 2024 TDS) say alkyd, and the dissenting pages are
distributor copy of unknown vintage, one of which still links the Jan-2014 TDS. The property tables either side of
the change are near-identical (same NATO stock numbers, same −70…+200 °C, CTE,
Dk, DF, IR; only dielectric strength moved 90 → 130 kV/mm), so this reads as
MacDermid correcting a long-standing wrong description rather than a
reformulation.

**Independent check — the SDS composition sections, which no marketing copy
touches.** Four were read, none contains a siloxane, silicone or silane:

| SDS | Section 3 ingredients |
|---|---|
| Current EN, aerosol (`farnell.com/datasheets/4548082.pdf`) | **extract of the 3 largest of 7 classified ingredients:** dimethyl**ether** 30-60 % (propellant), xylene 10-30 %, cyclohexane 10-30 %. The rest are ethylbenzene, a C7 hydrocarbon cut, propan-2-ol and toluene — all solvents, none a siloxane |
| SCC3 aerosol (`2880244.pdf`) | xylene, cyclohexane, ethylbenzene |
| SCC3, Rapid `87-1209s` | xylene, ethylbenzene, isothiazolinone biocide (the mould resistance) |
| **Oldest found**, bulk DCA01L, pre-CLP R-phrase era | xylene 30-60 %, 2-butoxyethanol 1-5 % |

Note dimethyl**ether** (CH₃-O-CH₃, CAS 115-10-6) is the propellant and is *not*
a siloxane — do not read "dimethyl" as polydimethylsiloxane. The oldest sheet
shows no silicone either. That is weaker than "never silicone-based" — four
sheets cannot establish what two decades of revisions declared — but there is no
positive evidence of a silicone formulation at any date, only of a silicone
*description*.

**Read the limit of this honestly:** an SDS Section 3 lists only *classified*
ingredients, so a non-hazardous resin — alkyd or PDMS alike — need not appear at
all. The SDS therefore cannot prove absence of silicone; it can only show that
no silicone was ever declared, across two decades of revisions. Combined with the
manufacturer's current and repeated first-party statement, **DCA is an alkyd and
§3.1 does not exclude it.**

**It stays excluded anyway, under §3.2, and the reason is stronger than for an
acrylic.** An alkyd is an ester-based resin and ester linkages hydrolyse under
alkali; this probe sits in an ammonia-rich condensing pile. (That mechanism is
chemistry reasoning, not a datasheet claim — but note the TDS makes *no* alkali
claim in either direction, where PUC's states acid and alkali resistance in its
headline.) DCA's solvent resistance is also conditional on a 2–24 h cure at
90–120 °C, and its CTI is >300 V where `POTTING.md` §3.2 wanted >600 V — though that is a
*certification* ceiling rather than a measured failure, and **PUC's own CTI is
"not stated" in §5**, so it cannot be applied as a hard coating gate without
disqualifying the recommended product too.
With PUC available there is no reason to accept even the residual siloxane
probability next to an SGX cell, where the cost of being wrong is cumulative and
irreversible.
Note that the last two appear on **Sensirion's compatible list** — Sensirion is
answering "will this harm the SHT4x", not "will this harm your O₂ cell". Their
list is not a substitute for this section.

Worth noting as a footnote: silicone would be a poor moisture barrier here in any
case. O₂ permeability of SR is 19 685 (cc·mm)/(m²·day·atm) against 78.7 for UR
(HZO comparison table) — a factor of 250.

### 3.2 Acrylic — not excluded, but it is the wrong pick here

Acrylic (Electrolube HPA/TFA/APL, HumiSeal 1B31) is the default hobby and
low-volume choice: cheap, fast, forgiving, easy to rework, and Electrolube's own
UV-weathering data ranks its acrylics best. Against this application:

- **Poor solvent and chemical resistance.** Electrolube grades its own range and
  the acrylics come out `GOOD` while PUC comes out `EXCELLENT` and UVCL `BEST`.
  No acrylic TDS in this survey claims alkali resistance; PUC's claims it in the
  headline bullets.
- **Low Tg / softening.** Coating vendors put traditional acrylics' Tg well below
  service temperature, and this probe runs at 75 °C continuously with a heater
  island beside it. An acrylic that is above Tg for its whole service life is a
  tacky film, not a barrier.
- **Redissolves in its own solvent.** That is the property that makes it
  reworkable, and it is the same property that makes an overpour of a
  solvent-bearing material unpredictable.

Acrylic remains the right answer if the goal changes to "protect a bench
prototype that will be reworked ten times". It is not the answer for a potted,
buried, 75 °C, ammonia-exposed article.

### 3.3 Epoxy coating — no

Rigid, effectively unreworkable, and it repeats every argument `POTTING.md` §3.1
used to reject epoxy for the pot (Shore D, ~3 GPa, cracks a constrained volume).
An epoxy *coating* is thin enough that the stress argument is weaker, but it buys
nothing over PU on moisture (WVTR 0.94 vs 0.93 g·mm/m²·day) and costs the rework.

### 3.4 Parylene — best barrier, but never under the pot

Parylene C is the only material in this comparison that is meaningfully better
than the rest, and by an order of magnitude:

| | WVTR (g·mm)/(m²·day) | H₂S perm. (cc·mm)/(m²·day·atm) |
|---|---|---|
| **Parylene C** | **0.08** | **5.1** |
| Parylene N | 0.59 | 313 |
| Epoxy (ER) | 0.94 | — |
| Polyurethane (UR) | 0.93 | — |

*(HZO parylene properties table; note the C-vs-N gap on H₂S is 60×, so "parylene"
without the letter is not a specification.)*

Two things stop it being the blanket answer:

- **It is a vacuum-deposition service.** Every aperture (cell port, SHT45 opening,
  membrane seat, ring castellation, socket contacts) has to be masked by the
  coater, and there is no bench fallback. German/Swiss providers exist —
  Plasma Parylene Systems (Rosenheim), Para-Tech via micrometal, COAT-X — but
  none of them has been quoted for this part. **Not sourced. Do not put it in a
  plan until someone has a price for three masked prototypes.**
- **The pot will not stick to it.** Parylene's low surface energy is exactly why
  it needs A-174 silane as an adhesion promoter to stick to *its own* substrate;
  a PU poured on top of a parylene film has a release plane waiting for it. That
  is precisely the compound/soldermask capillary path `POTTING.md` §2 exists to
  eliminate. **If parylene is used, it is gas-zone only, with the potted zone
  masked** — which is another mask, and another reason to get a quote before
  believing in it.

---

## 4. The potted zone: coat it, but prove the bond first

`PLAN.md` only ever asked for the gas zone to be coated. The potted zone deserves
a coating too, and the argument cuts both ways honestly:

**For:**

1. **The pot's failure mode is an interface, not bulk permeation.** UR5604
   absorbs <0.5 % water in 10 days and the path length is ~10 mm of compound —
   bulk ingress is not the threat. `POTTING.md` §2 says the threat is a
   *capillary path along the compound/soldermask interface*. A coating that bonds
   to soldermask **and** to the pot converts one weak interface into a bonded
   stack; a coating that bonds to soldermask and *not* to the pot converts it into
   two interfaces, one of which is a release plane. That is the whole decision.
2. **It protects the interval.** The board exists, cleaned and bare, from reflow
   until the pour — potentially weeks, with handling salts and bench humidity.
3. **SIR insurance on the guard.** If the pot ever does delaminate over the RE
   follower and guard region, a 25–75 µm PU film with 1×10¹⁵ Ω SIR is the
   difference between a degraded reading and a dead sub-µA node.

**Against, and the mitigations:**

- **Release-plane risk** — the one above. Mitigation: same chemistry family, and a
  peel coupon (§7). This is an assumption, not a sourced fact: no TDS in this
  survey states adhesion of a PU encapsulant to a cured PU conformal coating.
  **It goes into the Electrolube message alongside `POTTING.md` §9 item 2.**
- **Residual solvent outgassing into a curing pot.** PUC is 63 % VOC and its
  recommended drying is 24 h @ 20 °C or 90 min @ 65–80 °C. A tack-free film is
  not a cured film. Mitigation: heat-cure the coating and hold it before the pour.
- **Moisture on the board foams the pot.** Independent of the coating, and worth
  stating in the assembly drawing: *"Moisture reacts with the isocyanate in a
  polymer, which then produces carbon dioxide. CO₂ vapour manifests itself within
  the encapsulant as a bubble"* (HumiSeal). A void is the §2 failure mode. Bake
  the board dry, coat, cure, pot — and do not let the coated board sit in bench
  humidity between cure and pour.

**Verdict: coat the whole board, both zones, one material, one pass** — subject to
the adhesion answer. If Electrolube says the pot will not bond to cured PUC, the
fallback is to coat only `y > 82` (the gas zone, as `PLAN.md` originally had it)
plus a deliberate 5 mm overlap band below the datum, and leave the deep potted
region bare.

---

## 5. The comparison, with numbers

| | **Electrolube PUC** (lead) | **Electrolube 2K301P** | HumiSeal 1B51NSLU | Electrolube HPA (acrylic) | Parylene C |
|---|---|---|---|---|---|
| chemistry | modified PU, 1-part | PU, 2-part, solvent- and silicone-free | synthetic rubber | acrylic | poly(chloro-p-xylylene) |
| operating range | −55…+130 °C | **−65…+150 °C** | thermal shock −65…+125 °C (max-continuous not stated) | — | −? (inert) |
| solids / VOC | 37 % / 63 % VOC | **98.5 % / solvent-free** | 22 % / 708 g/L | — | n/a |
| SIR | 1×10¹⁵ Ω | **2×10¹⁶ Ω** | 2×10¹⁴ Ω | — | — |
| CTI | not stated | **>600 V** | not stated | — | — |
| Tg | not stated | **< −60 °C** | 14 °C (DSC) | — | ~90 °C |
| film thickness | 25–75 µm | **200–350 µm** | 25–75 µm | 25–75 µm | 5–25 µm |
| MVTR | not stated | not stated | **<1 g/m²·day·mil** | — | 0.08 g·mm/m²·day |
| alkali resistance | **stated explicitly** | not stated | not stated | not claimed | inert |
| approvals | MIL-I-46058C, IPC-CC-830, DEF-STAN 59/47 | IPC-CC-830, BMW GS95011-5 | — | MIL-I-46058C | — |
| Sensirion-listed | no | no | **yes (1B51NSLU)** | no | no |
| rework | CCRG gel | hard | Stripper 1080 | easy (Ultrasolve) | none |
| bench-applicable | **yes** (brush/aerosol) | needs meter-mix | yes | yes | service only |

Reading of the table:

- **2K301P is technically the best liquid coating here, by a distance.**
  (Updated 2026-09-07: the live product is 2K301P, TDS 01 April 2025 — the 2K300
  sheet used in an earlier draft was a 2017 *provisional* TDS for a superseded
  grade.) Solvent-free and explicitly **silicone-free**, so nothing outgasses into
  the curing pot and §3.1 is satisfied by formulation rather than by care;
  SIR 2×10¹⁶ Ω; CTI >600 V (the same surface-leakage metric that decided UR5604 in
  `POTTING.md` §3.2); −65 to **+150 °C**; 200–350 µm film with enhanced edge
  coverage; Tg below −60 °C. Electrolube's own selection guidance says
  solvent-free coatings at 100–350 µm give *"superior protection in harsh
  conditions"* against solvent-based ones at 25–75 µm, and 2K301P's page claims
  exactly our environment: *"superior protection in harsh environments, especially
  in high humidity and condensation conditions."*

  **It is unusable by hand.** 4:1 by volume, **10–15 minutes** usable life, and
  the TDS specifies selective spray with high-accuracy volumetric metering
  (progressive-cavity pumps, 60 °C heated applicator block). Package sizes are
  "contact your customer service representative" — it is not a distributor part.
  **This is the production answer and a Rev-B ask, not something to buy for three
  hand-built prototypes.** It is also the honest counterweight to §1: the vendor's
  own harsh-environment recommendation is not PUC.
- **PUC is the right prototype answer**: the same alkali/solvent resistance
  argument, applicable with a brush, and reworkable. (An earlier draft added
  "orderable in Germany today" — **that is now false**; see §8.2.)
- **1B51NSLU's edge is narrow but real** — Sensirion has actually tested it
  against an SHT4x, and its MVTR is the best liquid figure in the survey. Its Tg
  of 14 °C means it is a rubber at service temperature (fine for a rubber,
  disqualifying for an acrylic). Its alkali/NH₃ behaviour is unstated.

---

## 6. Cleanliness is not optional, and it is not a detail

Every TDS in this survey opens with the same warning, and `CONTACT-CORROSION.md`
§4.2 has already flagged the specific version of it for this board:

> "Substrates should be thoroughly cleaned before coating… all flux residues must
> be removed as they may become corrosive if left on the PCB." (Electrolube PUC)

> "Contamination under the coating could cause problems that may lead to assembly
> failures." (HumiSeal 1B51LU)

For a board carrying a sub-µA electrode node under a driven guard, this is the
whole game. **A coating over ionic residue is worse than no coating**: it seals
the contaminant in with whatever moisture permeates, and it removes the
possibility of ever washing it out. Specifically:

1. **No-clean flux is not "no clean" under a coating.** Hand-soldered joints are
   the risk (`CONTACT-CORROSION.md` §4.2 — coverage over a hand-soldered joint is
   not the same as coverage from the coating step).
2. **Clean, then verify.** At minimum a documented IPA/DI wash and a visual under
   UV; ideally a ROSE or SIR check on the guard comb region before coating.
3. **Bake dry before coating and again before potting.** FR-4 holds water; the
   pot's isocyanate finds it and makes CO₂.
4. **Do not coat above 75 % RH or below 16 °C** (PUC TDS) — a real constraint in
   an unconditioned workshop.

---

## 7. Process, in the order it has to happen

This replaces the single line `POTTING.md` §8 currently has
(`conformal-coat gas zone (apertures clear)`):

```
build → clean (flux fully removed, verified) → bake dry
      → MASK (list below)
      → coat, 25–75 µm, brush or aerosol, 2 thin passes not 1 thick one
      → cure FULLY: 90 min @ 80 °C or 24 h @ 20 °C, ventilated
      → hold, do not let it re-absorb bench humidity
      → demask, inspect under UV (PUC fluoresces)
      → fit dam at y=82, pour per POTTING.md §4/§6
      → ... membrane, SHT45 recondition bake, cell LAST
```

**Must be masked — nothing on this list may take coating:**

| Feature | Why |
|---|---|
| SHT45 sensor opening | Sensirion: *"the sensor opening must remain uncovered and free of any coating"*. Use the protective-cover part option, or 3M Kapton 92 / Nitto EM-310 / tesa HAF 58470 — Sensirion's tested tape list. |
| O₂ cell socket contacts | the cell is a field-swappable part (`POTTING.md` §1); coating in a spring contact is a permanent open |
| Ring-tip castellation | mating contact (`HEATED-SPREADER.md`) |
| Membrane seat / gas port | flow path; also `MEMBRANE.md`'s solvent rule |
| Test points, J3 SWD pads | recovery access (`README.md`: J3 is not exposed once potted, so anything reachable stays reachable) |

**Two Sensirion rules that are easy to skip and expensive to skip:**

- *"solvent vapours are produced during the curing and processing of the coating…
  use ovens with fresh air supply."* Cure ventilated, not in a sealed box with
  the sensor.
- *"Tack-free state of the coating is not an indication of full curing… use the
  maximum provided time value before assembling the sensor."* Take the long
  number, not the short one.

**Coupons to run before the first real pour** (each is cheap and each closes an
assumption this document is currently making):

1. **Peel/adhesion coupon:** FR-4 + soldermask → PUC, cured → UR5604 poured on
   top. Cut and try to separate the pot from the coating. This is the §4
   release-plane question and nothing in any datasheet answers it.
2. **Void coupon:** the same stack in a section of tube, cross-sectioned — folds
   into the `POTTING.md` §9 item 7 void-inspection problem, which is already
   budgeted a sacrificial prototype.
3. **Cell-adjacent cure coupon:** cure PUC in a closed tube with a spare SGX cell
   present but *not yet installed*, then check the cell against a fresh one in
   air. If this shows anything, the whole "coat before cell" sequencing has to
   become "coat in a different room".

---

## 8. Ordering (DE)

| Item | Code | Pack | Where |
|---|---|---|---|
| Electrolube PUC, aerosol | `PUC400` | 400 ml | Order code **1898441** on both `nl.farnell.com` (€51,29 excl. BTW) and `uk.farnell.com` (£35,09 ex VAT) — 152 in stock, 72 incoming, same figure on both, so it is one stock pool. Verified live 2026-09-18. See §8.2: **most German-facing channels for this part are dead** |
| Electrolube PUC, bulk | `PUC05L` | 5 L | Farnell / Ulbrich — **too much for 3 boards; buy the aerosol** |
| PU thinners (only if spraying bulk) | `PTH05L` | 5 L | — |
| Coating removal gel (rework) | `CCRG01L` | 1 L | — |
| SHT45 masking tape | 3M Kapton 92 | — | Sensirion-tested list |
| *(alternative)* HumiSeal 1B51NSLU | — | — | Chase/HumiSeal EU distribution — **not price-checked** |

One 400 ml aerosol covers ~5 m² at 25 µm. Three probes at ~20×107 mm both sides
is under 0.005 m². Coverage is not a constraint; shelf life (36 months) and
getting an even film by hand are.

**The order code is now verified.** An earlier draft of this section carried
1898441 from a search snippet and said so ("Check it in the basket"). The live
`uk.farnell.com` product page was read on 2026-09-18 and the code, the EAN
(5028356102020) and the `EPUC400` alias all match. Manufacturer lead time is 18
weeks, so the 152 units on the shelf are the whole story — this is not a part to
re-decide slowly.

### 8.1 `de.farnell.com` has no polyurethane coating at all — measured 2026-09-18

Worth writing down because it is the reason every Farnell link that comes up in
a search for this board is an acrylic, and the next session will otherwise
re-evaluate the same three products.

All 233 products in *Chemikalien & Betriebsausstattung → Farben & Lacke* were
enumerated (10 pages). Five urethane entries exist and four are dead:

| Product | Farnell DE | status |
|---|---|---|
| MG Chemicals 4223F-1L / -55ML / -312G | 2889790 / 3255891 / 2889765 | **Wird nicht mehr hergestellt** (all three) |
| Kontakt Chemie Urethan 71, 200 ml | 801069 | **nicht mehr auf Lager** |
| Kontakt Chemie Urethan 71, 400 ml | 837167 | *"Verfügbarkeitsinformationen können nicht abgerufen werden"* |

`PUC400`, `EPUC400` and `humiseal` each return **zero results** on the German
site. The PU family is simply not carried there; the UK site carries it fine.
**Buy PUC on `uk.farnell.com`, not `de.farnell.com`.**

What the German site *does* stock, all evaluated and all rejected above:
`AFA200` (§3.2 acrylic), `HPA200H` (§3.2, the best of the acrylics — MIL-I-46058C,
mould-resistant, still no alkali claim, and still *above* its Tg at 75 °C
so the film is soft in service — §3.2),
`APL400H` (§3.2 acrylic), `DCA200H` (§3.2 — a modified alkyd, settled 2026-09-18 in §3.1;
Farnell's *"Silikonharz"* listing is stale copy, but the alkyd is excluded on
alkaline-service grounds regardless), Ambersil 1666251 (acrylic, and **−40…+60 °C**, disqualifying on its own),
Dow 1-2577 and 3140 (§3.1 silicone). `BLV15ML` is a Bloc'lube screw-marking
lacquer, not a conformal coating.

### 8.2 Getting PUC into Germany is the actual constraint — 2026-09-18

Three of the German-facing channels named in earlier drafts of §8 are dead.
Checked, and corrected here rather than left to be rediscovered:

| Channel | Status |
|---|---|
| dpv-elektronik.de | trade account; **may never be onboarded** (Fab, 2026-09-18) |
| RS Austria `7682312` | **does not deliver to Germany** (Fab, 2026-09-18) |
| RS Germany | `PUC400`, `EPUC400` → **zero results**. The "RS DE 7682312" in an earlier draft was an *Austrian* code and the claim was wrong |
| ivh-ullrich.de | **no stock, delivery time unknown** (Fab, 2026-09-18) |
| `de.farnell.com` | zero results — §8.1 |
| `at.farnell.com` | zero results |
| `nl.farnell.com` | stocks it (1898441, €51,29 excl. BTW, 152 units) but **ships to NL only** (Fab, 2026-09-18) |
| Bürklin | carries **no Electrolube at all** |
| PK Elektronik | no Electrolube; also B2B-only since 2023-01-01 |
| **Ulbrich GmbH (DE)** | **carries PUC** — enquiry-only, *"Dieses Produkt anfragen!"*, no webshop, no published price. https://www.ulbrich-gmbh.de/electrolube-puc-polyurethan-schutzlack |
| **`uk.farnell.com`** | **in stock**, code 1898441, £35,09 ex VAT, 152 units |
| **Rapid Electronics (UK)** | **in stock**, code 59-2126, £33,70 ex VAT, 10 units, same-day despatch |

**The finding is that PUC has no German webshop channel with stock**, bounded to
the channels actually checked (listed above; not an exhaustive market survey).
Every German route found is a trade-account enquiry (dpv, Ulbrich) or out of stock
(ivh-ullrich). Stock exists at `nl.farnell.com`, `uk.farnell.com`, Rapid and RS
Austria — note `at.farnell.com` is a *different* storefront and returns zero — but
only the two British ones are both in stock and not already known to refuse a
German address.

**Unresolved, and to be settled at checkout rather than assumed:** whether either
UK source will ship a flammable aerosol (UN1950) to a German address. That is a
customs export *and* a dangerous-goods consignment, which is the combination
couriers most often refuse. Note also that `de.farnell.com` not listing the part
at all — while NL and UK do — is consistent with a country-level restriction on
this item rather than a catalogue accident.

**Ulbrich is the route with no border problem**, since a German distributor
shipping domestically faces neither the customs nor the cross-border hazmat
question. It costs a day and an email rather than a click.

*Detail worth keeping, from Ulbrich's PUC page:* PUC **"enthält kein Isocyanat"**.
That bears directly on §4 — the pot's void mechanism is isocyanate reacting with
residual moisture to make CO₂, so an isocyanate-free coating under a PU pour is
one fewer gas source at the interface.

**Fallback that is unambiguously deliverable today:** Kontakt Chemie
**Urethan 71**, 400 ml — **Conrad `886409`, €20,99 incl. MwSt., plus shipping, 64
in stock**, sold to private customers, no onboarding of any kind. Conrad's own
text: *"Lufttrocknender Einkomponenten-**Polyurethan-Alkydharzlack**"*,
−40…+120 °C, *"durch die chemische Vernetzung während der Trockenzeit schützt er
auch bei feuchten oder aggressiven Umgebungsbedingungen"*.

Its own TDS (CRC *Technisches Merkblatt*, Ref. 20750) rather than the shop copy:

| | Urethan 71 | PUC (for comparison) |
|---|---|---|
| chemistry | 1-part **polyurethane-alkyd**, air-drying | modified PU, 1-part |
| cure mechanism | **thermoset — chemically crosslinks**, does *not* redissolve | solvent-release |
| touch dry | ~120 min | — |
| **full cure** | ***"mehrere Tage"* at room temperature; 24 h @ 60 °C reaches only 90 % crosslink** | 24 h @ 20 °C or 90 min @ 65–80 °C |
| range | −40…+120 °C (*adhesion*) | −55…+130 °C |
| alkali | **no claim** | *"resistant to acids and alkalis"* |
| thinner | acetone | PTH |

**Credit where it is due, and it matters for §4:** Urethan 71 is a *thermoset*.
CRC's own English page says *"because it is a thermoset material, it is more
difficult to solder through the URETHAN 71 film."* A crosslinked film does not
redissolve in its own solvent, which addresses one of the three §3.2 objections
to the acrylics in §8.1. Read the limit: non-redissolution is not resistance to
swelling or adhesion loss, and no solvent attack by a UR5604 overpour has
actually been demonstrated on any of these films. A point in its favour, **not**
a demonstrated superiority over AFA / HPA / APL / Ambersil.

**Three reasons it is still not the answer:**

1. **The alkyd fraction.** The §3.1 saponification argument against DCA has to be
   applied here too, and it lands softer rather than not at all: a
   urethane-*modified*, crosslinked alkyd is the classic middle case — better
   hydrolytic resistance than a straight alkyd like DCA, worse than a true PU
   like PUC. Weaker than PUC, stronger than DCA. It is not equivalent to either.
2. **Cure is measured in days.** §7 requires a *fully* cured film before the pour
   (uncrosslinked residue outgassing into curing PU is the §4 void mechanism) and
   before the SHT45 and cell go in. "Touch dry in 2 h" is not that. Budget
   **24 h @ 60 °C**, or several days at bench temperature — but note the TDS
   separates solvent evaporation from subsequent crosslinking and does **not**
   say the residual uncrosslinked fraction is volatile. "24 h @ 60 °C is enough"
   therefore cannot be asserted from this sheet; it needs its own acceptance
   basis before it satisfies §7's full-cure gate.
3. **No alkali claim, and +120 °C is an adhesion range**, not a
   chemical-resistance rating. The alkali claim is the entire reason PUC was
   picked in §1.

**Verdict: a good bench coating, not a probe coating.** Use it on boards being
handled and debugged; do not put it on an article that gets potted and buried.

**One high-value use while PUC is in transit:** run a **Urethan-71 / UR5604 peel
coupon**. It does not substitute for coupon 1 (§7), which tests the PUC/UR5604
interface specifically — but it is a cheap rehearsal of the §4
experiment: it exercises the dam, cure and pour process and yields one real
coating/pot interface to pull apart. **Its result is specific to Urethan 71** —
it cannot be generalised to "urethane-family coatings bond to UR5604", and it
does not resolve the PUC interface. Process de-risking, not an answer.

**Access note (2026-09-18):** `de.farnell.com` and `uk.farnell.com` both return
403 to curl with a Chrome UA, to curl with full `Sec-Fetch-*` headers, and to
headless Chromium with a plain-Chrome UA. A headed scratch-profile Chrome over
CDP got exactly one page through (DCA200H) and 403'd on the rest. Every figure
in §8, §8.1 and §8.2 — and the MacDermid page that settled §3.1 — was read at
rung 5 through the Playwright MCP **browser extension** driving Fab's own Chrome,
token supplied by him. Nothing in these sections is inferred from a blocked page.

---

## 9. Open items

1. **Ask Electrolube: does UR5604 bond to cured PUC?** Put it in the same message
   as `POTTING.md` §9 item 2 (polyether/polyester, ionic content, NH₃/H₂S,
   soldermask adhesion). Until it is answered, §4's "coat the potted zone too" is
   a recommendation resting on chemistry-family reasoning, not on data.
2. **Ask for PUC's maximum-continuous rating *in an alkaline, condensing
   environment***, not just the −55/+130 range. The TDS's "resistant to acids and
   alkalis" is a headline bullet with no test behind it on the sheet.
3. **Run coupon 1 (§7) regardless of the answer to 1.** A vendor "yes" and a peel
   test are not the same evidence.
4. **Get a parylene quote** for three masked prototypes from Plasma Parylene
   Systems / micrometal / COAT-X, gas zone only. If it is affordable it is the
   best gas-zone barrier available and the numbers in §3.4 are not close. If it
   is not, that is a sourced decision instead of an assumption.
5. **1B51NSLU's alkali and max-continuous data** is missing from its TDS. If the
   SHT45 becomes the binding constraint, that gap has to be closed before it
   displaces PUC.
6. **Update `POTTING.md` §8** — the sequence there coats the gas zone only and
   does not mention masking, cure-before-pour, or the cleanliness gate.
7. **Evaluate Peters ELPEGUARD SL 9407 FLZ against 2K301P for Rev B**
   (found 2026-09-18; TDS `peters.de/wp-content/uploads/2025/03/sl9407flz_301492d_vtm_001.pdf`,
   read). §5 named 2K301P as "the production answer", and this may beat it on the
   one axis §5 could not source:

   > *"beste Beständigkeitsklasse **GX** gegen Schadgase nach ISA 71.04-2013"*

   GX is the most severe corrosive-gas class in that standard — an actual
   measured rating where PUC offers only the headline phrase "resistant to acids
   and alkalis" that §9 item 2 exists to chase. Also: 2-pack **polyurethane**
   resin (UR), −65…+130 °C, **no Tg between −50 and +150 °C**, CTI ≥600 (the
   `POTTING.md` §3.2 bar), ~95 % solids on the /730 grade, surface resistance
   ≥1×10¹³ Ω, and condensation resistance ≥2×10⁹ Ω measured *under 12 V bias at
   40 °C and 100 % RH* — a closer analogue than most published figures, though
   **not** this probe's service exposure (5…75 °C with NH₃ and H₂S, coated and
   potted). Useful qualification evidence, not service proof. Peters is in Kempen, so a domestic supply route avoids §8.2's cross-border
   problem entirely — but note this is a **2-pack liquid, not an aerosol**; the
   400 ml spray can Bürklin stocks is the acrylate SL 1307, not this.

   Three caveats, all real. **The TDS is explicitly provisional** — it is headed
   *"Vorläufiges Technisches Merkblatt der Reihe ELPEGUARD® SL 9407 FLZ"* — so
   these figures are the vendor's own preliminary data. **Pot life ~20 min**
   (2-pack; mix ratios are on page 3 — /730 is **100:78 by weight**, /45 is
   **100:56** — though brushing is a listed application method and 20 min is workable by hand
   on a 20×107 mm board, unlike 2K301P's 10–15 min meter-mix spray), and Peters
   sells B2B via sample request / distributors such as Bürklin. **Not sourced and
   not priced for this part — do not put it in a plan until someone has a quote.**

   **Do not buy the wrong Peters.** Bürklin stocks `SL 1307 FLZ/S` (12L715,
   €39,15 incl. MwSt. plus shipping, 79 units, and B2B-only —
   *"nicht verkäuflich an Endverbraucher"*) — a 400 ml spray can, in stock, and the one you land on
   searching for a German Peters coating. It is **not** the polyurethane: the
   family TDS states *"Basis: **Acrylatharze (AR)**"*, so it is excluded by §3.2
   like every other acrylic in §8.1, its CTI ≥600 notwithstanding. **SL 9407 FLZ
   is the polyurethane; SL 1307 FLZ is an acrylate.** Only the 9407 series
   carries the GX rating.

---

## 10. Sources

Primary (fetched and read):

- Electrolube **PUC** Polyurethane Coating TDS — `farnell.com/datasheets/2332383.pdf`
- Electrolube **2K300** Two-Component Polyurethane Coating TDS (provisional) —
  `farnell.com/datasheets/2619464.pdf`
- Electrolube **Conformal Coatings** brochure (product range, SIR after humidity /
  salt mist / corrosive gas / water immersion, solvent-resistance grading) —
  `sigerom.ro/sigerom/doc/conformal-coatings-brochure-electrolube.pdf`
- **HumiSeal 1B51LU** Synthetic Rubber Conformal Coating TDS — `cdnresources.chasecorp.com`
- **Sensirion**, *Handling Instructions for SHTxx Humidity and Temperature
  Sensors*, v9, June 2025 — `sensirion.com/resource/user_guide/sht/handling_instructions`
  (§3 coating rules, compatible-coating and tested-tape tables)
- Electrolube **UR5041 / UR5604** TDSs — already read for `POTTING.md` §3
  (`farnell.com/datasheets/2331334.pdf`, `1782236.pdf`)

Secondary (vendor/technical, used for comparative figures only):

- HZO, *Parylene coating properties* — WVTR and gas-permeability comparison table
- HumiSeal/Chase blog, *5 Simple Steps to Eliminate Bubbles in Potting
  Encapsulants* — the isocyanate/CO₂ mechanism
- Nexus/SCH conformal-coating design hub, *Material compatibility* — silicone
  de-wetting
- SCS, *Parylene and A-174 silane* — parylene adhesion promotion
- US Bureau of Mines RI 8321 (Chilton, 1978), *Silicone vapor poisoning of
  catalytic methane sensors*; and the current MOS-siloxane-poisoning literature

**Access note (2026-09-07):** every Electrolube figure above comes from a Farnell
datasheet mirror or the distributor brochure PDF, both of which returned real
content (`%PDF`, 110–760 kB). No figure here is inferred from a blocked page.

**`macdermidalpha.com` is now read** (2026-09-07). curl with a Chrome UA and with
full `Sec-Fetch-*` headers → 403; a headed scratch-profile Chrome over CDP got one
page at 200 and then hit a persistent Cloudflare interstitial that did not clear
in 90 s. It came through on the **Playwright MCP browser extension** driving Fab's
own Chrome — rung 5 with his session, supplied by him. Four things changed as a
result and they are marked in place: the DCA chemistry correction (§3.1), 2K301P
replacing the superseded 2K300 (§5), the vendor's solvent-free-for-harsh-service
guidance (§5), and, in `POTTING.md`, UR5604's corrected thermal conductivity plus
the UR5118 finding (§3.3b there).

**Still unverified:** the PUC400 price and German stock. The UR5604 Farnell page
fetched fine at the start of the session; every later Farnell `/dp/` and `/search`
URL, and RS DE, then returned 403 — a rate-triggered WAF state, not a missing
product. The order code 1898441 in §8 comes from Farnell's own UK/AT listings via
search snippets, not from a page actually read. Check it in the basket.

Gluespec (2K350 detail) also 403s and was not needed; the 2K300 sheet carries the
same chemistry.
