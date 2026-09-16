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
  argument, applicable with a brush, reworkable, and orderable in Germany today.
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
| Electrolube PUC, aerosol | `PUC400` | 400 ml | **Ordered from [dpv-elektronik.de](https://www.dpv-elektronik.de/Produkte/Chemie/Schutzlacke/PUC-Polyurethanschutzlack--400-ml-Spruehdose.html?language=de)** (2026-09-16); candidates were RS DE 7682312, Farnell, Ulbrich |
| Electrolube PUC, bulk | `PUC05L` | 5 L | Farnell / Ulbrich — **too much for 3 boards; buy the aerosol** |
| PU thinners (only if spraying bulk) | `PTH05L` | 5 L | — |
| Coating removal gel (rework) | `CCRG01L` | 1 L | — |
| SHT45 masking tape | 3M Kapton 92 | — | Sensirion-tested list |
| *(alternative)* HumiSeal 1B51NSLU | — | — | Chase/HumiSeal EU distribution — **not price-checked** |

One 400 ml aerosol covers ~5 m² at 25 µm. Three probes at ~20×107 mm both sides
is under 0.005 m². Coverage is not a constraint; shelf life (36 months) and
getting an even film by hand are.

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
