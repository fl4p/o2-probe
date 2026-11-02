# On what basis should the primary O₂ register be published?

Research report, 2026-09-06. Companion to `O2-HUMIDITY-CORRECTION.md`, which
poses the question and — since Fab supplied Randle & Flegg (1978) — now answers
it. **This report does not change any file.** Every proposed edit is written out
as replacement text for review; nothing in `firmware/`, `PLAN.md`, `DESIGN.md`
or `regmap.h` was touched.

This is written against the **current** `O2-HUMIDITY-CORRECTION.md`, including
the Randle & Flegg material in §4 and the Sources section in §7. Its job is to
(a) close the three unretrieved primaries that file lists, (b) test whether the
dry-basis convention is universal or just one lineage, and (c) take the
biological question further.

Tags: `[COVERED]` already in our docs · `[SHARPENS]` we say something vaguer or
unsourced · `[NEW]` not in our docs · `[CONTRADICTS]` our docs say something
this evidence shows is wrong.

**Headline results:**

1. **Schulze 1962 is retrieved and read.** It is dry-basis, explicitly and in
   two independent places. But **Schulze never states a 5 % threshold** — the
   5 % is Randle & Flegg's reading of his *operating band*. `[SHARPENS]`,
   verging on `[CONTRADICTS]`, of the current §4 threshold paragraph.
2. **The dry-basis convention is NOT universal — it is an artefact of sample
   lines**, and the one standardised *in-situ* method (TMECC 05.08-C) has
   exactly the gap our probe was about to fall into. `[NEW]` and the direct
   answer to (b).
3. **Two respected sources use "corrected oxygen" to mean the WET value**, by
   applying Dalton's law in the opposite direction to ours. Our register prose
   must not say merely "corrected". `[NEW]`, and a documentation hazard.
4. **The microbial-ecology literature defines the aerobe/microaerophile niches
   in mg/L and µmol/L of dissolved O₂, not in %vol** — so pO₂, not any mole
   fraction, is the biologically correct variable, and the temperature coupling
   is quantitative and severe. `[NEW]`, and the direct answer to (c).

---

## 1. The three cited primaries — retrieved, and what they actually measured

`O2-HUMIDITY-CORRECTION.md` §7 lists these three as unretrieved. Two are now
read; the third is behind a subscriber login and is handed back.

### 1.1 Schulze 1962 — **RETRIEVED**, dry-basis confirmed twice over

Schulze, K.L. (1962), *Continuous thermophilic composting*, Appl. Microbiol.
10:108–122. Retrieved **at rung 5** (recipe in §7).

**Did he dry the sample? Yes, and he says so twice.** Method, p. 109:

> "The exhaust gas was led downward into a **water trap so that condensate could
> collect and overflow into a drain**. Through a T-piece the exhaust line was
> connected to a Beckman oxygen analyzer, model D-2. This allowed periodic
> analysis of the exhaust gas with respect to its residual oxygen
> concentration."

Discussion, p. 114, stating the reference frame outright:

> "The temperature inside the drum does not enter into these considerations
> because the air flow is measured at room temperature and **the oxygen
> concentration is also measured at room temperature in the Beckman analyzer**."

His drum ran at 53–68 °C "and at a relative humidity of nearly 100 %" (p. 118).
So the gas was saturated at 53–68 °C in the reactor and read at room temperature
behind a condenser: a dry-basis number in all but name. A third, independent
corroboration: his O₂-consumption arithmetic takes the inlet as the **dry** air
value — "Oxygen consumed is 0.21 − 0.03 = 0.18 liters per liter of air supply"
(p. 114). The Beckman D-2 is a paramagnetic analyser, an instrument type that is
always operated on dried gas.

**Is the "5 %" his? No.** `[SHARPENS]` / borderline `[CONTRADICTS]` — this is
the most important correction in this report to the current
`O2-HUMIDITY-CORRECTION.md` §4.

Schulze nowhere states a minimum, a threshold, or a limiting concentration. What
he did was *hold* a band by throttling air:

> "Air flow through the drum ranged from 0 to 30 cfh and was adjusted so that the
> **residual oxygen concentration in the exhaust gas remained between 5 and
> 10 %**." (p. 112)

and he reports individual runs at 6 % and 9.3 % average residual. His own
comment on the oxygen channel is about its use as an *activity indicator*, not
as a threshold:

> "The residual oxygen measurements in the exhaust provided a very sensitive
> indicator of the activity of the decomposition process." (p. 114)

So "thermophilic organisms are active in compost while the oxygen concentration
remains above 5 %" is **Randle & Flegg's inference from the band Schulze chose
to operate in** — a fair reading, but it is an operating setpoint promoted to a
biological threshold. Schulze never tested 4 %, or 3 %, or 2 %. Our docs should
say so, because it changes how much weight a 5 % alarm can bear.

**The designed experiment on the floor does exist, and it is in our own corpus.**
`[NEW]` — Suler & Finstein (1977), *Effect of temperature, aeration and moisture
on CO₂ formation in bench-scale composting*, Appl. Environ. Microbiol. 33:345–350,
already sitting in `compostlab-literature/fundamentals/`, deliberately varied the
O₂ residual as a factor at 2 %, 10 %, 18 % (and 25 %, 35 % enriched):

> "Relatively small amounts of CO₂ were formed when the O₂ residual was 2 %,
> regardless of temperature. Foul odors sometimes developed in these portions.
> Substantially more CO₂ was produced with residuals of 10 and 18 % ... Except
> at 68 °C, the 18 % O₂ residual was slightly more productive than the 10 %
> residual."

and their conclusion — the actual evidential basis for preferring 10 % over 5 %:

> "Generally, at the 10 % O₂ residual, CO₂ formation was only marginally less
> than at 18 %. ... these findings suggest that the intermediate aeration rate
> is adequate for metabolism and preferable for operating economy."

Their gas train is dry-basis by the same mechanism: "The exhaust stream from the
experimental chambers was passed through a **condensation trap** ... When an O₂
determination was required, the exhaust was diverted briefly ... to a chamber
fitted with a Beckman model 777 polarographic O₂ analyzer probe."

Suler & Finstein is a better citation for our alarm points than Schulze: it is a
factorial experiment that brackets the threshold, it is dry-basis, and it
supports 10 % rather than 5 % as the working floor.

### 1.2 Kane & Mullins 1973 — **paywalled**; but its mechanism is recoverable and it is dry-basis by construction

Kane, B.E. & Mullins, J.T. (1973), *Thermophilic fungi in a municipal waste
compost system*, Mycologia 65(5):1087–1100. DOI 10.1080/00275514.1973.12019529.

**Full text not retrieved.** Highest rung attempted: **5**, on two hosts —
`https://www.jstor.org/stable/3758290` and
`https://www.tandfonline.com/doi/abs/10.1080/00275514.1973.12019529`. Both
loaded correctly in the headed browser (real titles, no interstitial) and both
serve only the abstract behind an institutional **login wall**. Not bypassed.
See UNRESOLVED 1.

What I can state from retrieved material:

* **The abstract** (verified, Taylor & Francis) confirms the paper's three
  findings, one of which is "(2) **a requirement for aerobic growth
  conditions**" for the 304 thermophilic-fungal isolates. So it is a
  growth-vs-oxygen paper, and Randle & Flegg's citation of it is apt.
* **Google's index of the JSTOR full text** returns the fragment "…in the middle
  zones where the O₂ concentration drops below 5 % has been…", which confirms
  the paper does discuss a 5 % figure in the context of compost zones. This is a
  *search-engine snippet of a paywalled page*, not a retrieval — I record it as
  corroboration of the citation's existence, and explicitly **not** as verified
  content.
* **The follow-up study is retrievable and settles the basis question.**
  `[NEW]` Deploey, J.J. & Fergus, C.L. (1975), *Growth and Sporulation of
  Thermophilic Fungi and Actinomycetes in **O₂–N₂ Atmospheres***, Mycologia 67
  (JSTOR 3758339), abstract retrieved at rung 5. It opens by citing Kane &
  Mullins as its motivation — "Recently, Kane and Mullins (24) reported that six
  species of thermophilic fungi showed little or no growth when they were
  incubated in low oxygen…" — and its own experiments are done in **synthetic
  O₂–N₂ mixtures**, which is a *dry* basis by construction and is stated in the
  title.

  So the answer to "did they dry the sample" for this lineage is stronger than
  drying: the organisms' oxygen requirement was established in **blended dry
  gas**, with no water vapour in the system at all. A threshold derived that way
  is unambiguously a dry-basis mole fraction.

  Deploey & Fergus's abstract also carries the finding that matters most for a
  *diversity* objective (§4.3):

  > "None of these organisms grew in atmospheres of pure nitrogen. **The minimum
  > O₂ concentrations that allowed trace growth to occur were lower than those
  > that allowed measurable growth** ... Neither the fungi nor the actinomycetes
  > sporulated when only trace growth was observed. **The actinomycetes and fungi
  > required more O₂ for sporulation than for growth.**"

### 1.3 Waksman, Cordon & Hulpoi 1939 — **paywalled**, and not an oxygen source at all

Waksman, S.A., Cordon, T.C. & Hulpoi, N. (1939), *Influence of temperature upon
the microbiological population and decomposition processes in composts of stable
manure*, Soil Science. DOI 10.1097/00010694-193902000-00001.

**Not retrieved.** Highest rung attempted: **5**. `journals.lww.com` gave a
Cloudflare "Just a moment…" at rung 1 and the *correct citation page* at rung 5
(title `INFLUENCE OF TEMPERATURE UPON THE MICROBIOLOGICAL... : Soil Science`).
The page is marked "Original Article: **PDF Only**" with no abstract, behind
"Full Text Access for Subscribers / Log in for access". A login wall; not
bypassed. See UNRESOLVED 2.

Two things I *can* report, both `[NEW]`:

* **The page range in our citation is wrong.** The publisher's own citation line
  reads **Soil Science 47(2):p 83–114, February 1939**, not 83–98. Randle &
  Flegg give 83–98 and our §4 has inherited it. (SCIRP's citation database also
  gives 83–114.) Worth fixing wherever we cite it.
* **It is a temperature paper, and asking about its oxygen basis is a category
  error.** Randle & Flegg cite it for the 50–65 °C thermophile optimum, which is
  what our §4 uses it for, and that claim carries no gas-measurement basis at
  all. Nothing about the oxygen-basis question depends on retrieving it. What
  *would* depend on it is the 50–65 °C figure itself, which remains second-hand
  through Randle & Flegg.

### 1.4 Summary table

| source | dried the sample? | evidence | is the 5 % theirs? |
|---|---|---|---|
| **Schulze 1962** | **yes** — water trap, analyser at room temperature, stated twice | retrieved, rung 5 | **no** — it is his 5–10 % *operating band*, promoted to a threshold by Randle & Flegg |
| **Kane & Mullins 1973** | n/a — the oxygen work is culture incubation, and the follow-up (Deploey & Fergus 1975) used synthetic **O₂–N₂** mixtures, i.e. dry by construction | abstract retrieved; **full text behind a login wall** | discusses a 5 % figure per a search-engine snippet of the paywalled text; **unverified** |
| **Waksman et al. 1939** | n/a — a **temperature** paper, no gas basis involved | **behind a login wall**; citation page verified, pagination corrected to 47(2):83–114 | no — cited for the 50–65 °C optimum only |
| **Suler & Finstein 1977** *(not cited by Randle; in our corpus)* | **yes** — condensation trap, Beckman 777 | local | **the best evidence for a floor**: 2 % severely restricted, 10 % ≈ 18 % |

---

## 2. Is the dry-basis convention universal, or just this lineage? — the answer to (b)

**It is not universal. It is an artefact of sample lines, and it breaks exactly
where our probe sits.** `[NEW]` — nothing in our docs says this, and it is the
trap the coordinator suspected.

### 2.1 The convention holds wherever a sample line exists — and it holds because of the plumbing, not because anyone decided it

I checked the gas train of every compost O₂ study I could reach. Every one of
them cools the sample before the detector, and **not one states a basis**:

| study | what happens to the water |
|---|---|
| Schulze 1962 | water trap; analyser at room temperature |
| Suler & Finstein 1977 | condensation trap ahead of the Beckman 777 |
| MacGregor et al. 1981 | "a 2-liter **condensate trap** packed with glass wool" |
| Strom 1985 | "ct, condensate trap" in the reactor gas train |
| Randle & Flegg 1978 | "cold trap and silica gel indicator to cool and dry the sample" *(already in our §4)* |
| Beck-Friis 2000 | pile gas into vials, cooled to ambient, then GC |
| Joshua et al. 1998 | pumped 50–200 mL/min through 3 mm tubing to an external 15 kg zirconia analyser; cools in the line |
| Sundberg 2005 / Smårs 2002 | "part of the compost gas was circulated through **a cooler in which a condensate was formed**" |
| Zheng et al. 2018 | "lowering temperature, dehumidify, and clean" — 20 °C water bath, then **soda-lime** desiccant |
| Naser et al. 2025 | "inline **condensation traps** and particulate filters" |

`[NEW]` **MacGregor 1981 proves it from its own data without discussing it.**
Their piles ran at 45–65 °C set points, yet (p. 1324):

> "The overall mean of the sums (CO₂ plus O₂) was 20.78 (σ = 1.01) ... the O₂
> content could be estimated through the relationship **%O₂ = 20.78 − %CO₂**."

20.78 is dry air. Wet, saturated pore gas at 55 °C would have summed to about
17. The condensate trap is visible in their own numbers. This is the most
economical single piece of evidence in the whole file that the literature's
percentages are dry, because it needs no method statement at all.

`[NEW]` **Zheng 2018 is drier than dry.** Soda-lime scrubs CO₂ as well as water,
and he calibrates on dry blended N₂/O₂ at 0, 1, 3, 5, 9, 13, 17, 21 %. His
numbers are on a **dry, CO₂-free** basis, which at a pile CO₂ of 6 % puts them
~6 % above ours. His figures should not be adopted as alarm points without that
caveat.

### 2.2 Where it breaks: the in-situ probe, which is what we are building

**TMECC 05.08-C, "In-Situ Oxygen Refresh Rate"** is the only standardised method
that puts a probe *into* the pile — the closest published thing to our
instrument. It never states a basis, and its entire treatment of the problem is
one sentence (§6.4):

> "Frequent equipment re-calibration and cleaning is imperative to attain
> reliable readings. **Standard gases of fixed O₂ content may be blended to
> achieve 1, 5, 10 and 15 % O₂ for exact calibration trials.** Apparatus not
> adapted with **temperature compensation** can provide unpredictable results."

Calibrate on dry blended gas; insert in a saturated 60 °C pile; compensate for
*temperature*. **Water vapour is not mentioned anywhere in the method.** A probe
run exactly to TMECC 05.08-C produces wet-basis numbers and compares them against
dry-basis thresholds — the ~20 % error, in the anoxia-looking direction,
sanctioned by the field's own standard method. That is precisely the trap, and it
is written into the standard.

`[NEW]` **The vendor of the reference sensor we will sit beside has the same
tension inside its own documentation.** Apogee's *Oxygen Sensor FAQs* says:

> "It is the absolute amount of oxygen (measured as **partial pressure in
> kilopascals**) that nearly always determines oxygen availability, but we think
> of oxygen as a percent of the total number of molecules in the air (20.95 %).
> ... The Apogee sensor measures gaseous O₂ as a percentage. **Gas sensors read
> out in percent because this value does not change with temperature or
> pressure.**"

That last sentence is true only on a **dry** basis. Apogee's own technical note
(Blonquist et al., *Estimation of Soil Respiration*) supplies the missing half:

> "As the humidity in the atmosphere increases, water vapor molecules displace
> and dilute other gas molecules, causing the output of a gas sensor to
> decrease. ... **humidity effects are accounted for to yield relative gas
> concentrations for a dry atmosphere.**"

> "In soil environments RH is generally always 100 %, unless the soil is
> extremely dry. Thus, the water vapor effect can be accounted for as a function
> of temperature."

So Apogee's *convention* is dry basis, and their corrections are referenced to
**calibration** conditions (`BP_C`, `T_C`, `e_AC`) rather than to a standard
atmosphere — the same structure our §3b argues for, arrived at independently.
But a user who reads only the FAQ, buries the probe, and trusts "percent does
not change with temperature or pressure" gets a wet-basis number and believes it
is dry. The trap is one document away from the vendor's own correct answer.

**Practical consequence for us:** the field plan puts our probe on the bus beside
an Apogee reference. If the Apogee's vapour correction is not applied, the two
instruments will *agree* — and both will be ~20 % low at pile temperature. Two
agreeing instruments is not a validation. `[NEW]`, and it bears on the field
commissioning gate in `compostlab/o2-probe/PLAN.md`.

### 2.3 What I did *not* find

I looked for, and did not find: any compost paper that **states its gas basis
explicitly** as a basis (as opposed to describing a drying train in the methods),
and any paper that **compares wet- and dry-basis readings** in a pile. Searching
"wet basis"/"dry basis" in the compost literature returns moisture content of the
*solids*, every time; the phrase is simply not used of the gas. So the claim
"this is a real and citable error in the field" is, on my evidence, **an
inference from the method statements, not a documented finding**. I flag that
distinction rather than dressing the inference up. It is a strong inference —
TMECC 05.08-C is a standard method with the gap in plain sight — but nobody has
published the comparison. Our bench data (§1 of `O2-HUMIDITY-CORRECTION.md`) may
be the first.

---

## 3. The biological question — the answer to (c)

Randle & Flegg's conclusion that "microbial activity was restricted by
overheating in the stack rather than by lack of oxygen" is already in our §4.
Here is what the wider literature adds, and it strengthens the case that
temperature and oxygen must be read **together**.

### 3.1 The niche categories are defined in dissolved-oxygen units, not %vol

`[NEW]`, and the direct answer to the coordinator's second flagged question.

Prakash et al. (2025), *The Study of Microbial Physiology Under Microoxic
Conditions Is Critical but Neglected*, Environ. Microbiol. (PMC12169914),
retrieved at rung 5, is a current review of exactly the aerobe/microaerophile
niche question. Its Table 1 — the definitions — is given in **concentration**:

* **Nanaerobic / Nanoxic** — "operate at nanomolar levels of oxygen
  (**< 1 µmol L⁻¹**)"
* **Dysaerobic / Dysoxic** — "low oxygen levels of **0.1–2.0 mg/L**"
* **Microaerobic** — the *only* category given in gas-phase terms, and loosely:
  "generally **1 %–10 %** concentrations"

and the review's own complaint is that the gas-phase framing is unusable:

> "The exact definition of the terms 'microoxia' or 'hypoxia' and its correlation
> with available oxygen levels is lacking in microbiology, geology and other
> related literature. The concept of hypoxia is broad, as any environment or
> niche with 0 %–21 % oxygen ... can be defined as micro-oxic/hypoxic."

Every instrument it surveys for this work is dissolved-oxygen instrumentation —
polarographic and optical DO sensors, STOX sensors to 0.5–10 nmol/L. **Nobody
studying microaerophile niches works in %vol.** So: yes, the argument in the
brief is made, and pO₂ (through Henry's law to dissolved O₂) is the quantity the
microbial-ecology literature actually uses.

### 3.2 The compost-specific version of the argument exists, and gives a number

`[NEW]`. UK Environment Agency, *Oxygen solubility in compost*, Odour Technical
Guide 3 (v1.0, 19 July 2012; contact Nick Sauer, National Technical Advisor,
Environment Agency), retrieved at rung 1. Its stated conclusion:

> "**Oxygen measurements from composting systems operated at high temperatures
> cannot be used directly to assess whether conditions are aerobic or
> anaerobic.** Temperature is one important risk factor in this assessment."

> "It is often presumed that as long as sufficient oxygen is present in these air
> spaces (5 to 10 % is often quoted), then compost will be aerobic, **but this is
> only part of the story**."

Its rule of thumb:

> "As a rule of thumb, saturation concentrations **below 2 parts per million
> (ppm)** in active composting systems may not prevent anaerobic conditions from
> developing. Highly active or wet materials, such as food waste, may require
> **3 ppm or more**."

**The two literatures converge on the same number**: the EA's 2 ppm floor and
Prakash/Berg's dysaerobic ceiling of 2.0 mg/L are independent and identical. That
is a cross-check worth having, and it gives a defensible biological setpoint that
the compost %-thresholds cannot supply.

I reproduced the EA's table exactly from its two stated constants
(k_H = 0.0013 mol L⁻¹ atm⁻¹, van 't Hoff 1700 K) — 20 % at 20 °C → 9.17 mg/L,
matching their cell — so the arithmetic below is traceable to the source rather
than to my own choice of solubility data.

### 3.3 Oxygen and temperature are not separable, and the numbers are severe

`[NEW]`. Computed at P = 93 kPa (715 m) and 100 %RH pore gas.

Dissolved O₂ at the biofilm surface, mg/L, for a given **dry-basis** reading:

| dry-basis reading | 40 °C | 45 °C | 55 °C | 60 °C | 65 °C | 75 °C |
|---|---|---|---|---|---|---|
| 20.95 % (fully aerated) | 5.60 | 5.01 | 3.94 | 3.45 | 2.97 | **2.05** |
| 15 % | 4.01 | 3.59 | 2.82 | 2.47 | 2.13 | 1.47 |
| **10 %** | 2.68 | **2.39** | 1.88 | **1.65** | 1.42 | 0.98 |
| 5 % | 1.34 | 1.20 | 0.94 | 0.82 | 0.71 | 0.49 |

Dry-basis reading required to hold a given biofilm DO:

| target | 40 °C | 45 °C | 50 °C | 55 °C | 60 °C | 65 °C | 70 °C | 75 °C |
|---|---|---|---|---|---|---|---|---|
| **2.0 mg/L** (EA floor = dysaerobic ceiling) | 7.5 % | 8.4 % | 9.4 % | 10.6 % | **12.2 %** | 14.1 % | 16.7 % | 20.5 % |
| 3.0 mg/L (wet/active materials) | 11.2 % | 12.5 % | 14.1 % | 15.9 % | 18.2 % | — | — | — |

Three consequences:

1. **A fixed dry-basis alarm is not a fixed biological condition.** The same 10 %
   reading is 2.39 mg/L at 45 °C and 1.65 mg/L at 60 °C — a 31 % fall in the
   oxygen actually reaching the biofilm, crossing the 2 mg/L line near 52 °C. A
   flat 10 % alarm is *most permissive exactly where the pile is hottest*.
2. **Above ~65 °C the pile is oxygen-limited at the biofilm however well it is
   aerated.** At 75 °C, *fully aerated* pore gas at our altitude delivers
   2.05 mg/L — on the dysaerobic boundary. This is a quantitative, independent
   route to Randle & Flegg's conclusion that overheating, not aeration, was the
   restriction. The 75 °C excursion `PLAN.md` admits is a **cooling** problem,
   not an aeration problem, and no amount of air fixes it.
3. **Altitude costs ~10 % of the delivered oxygen.** For an identical 10 % dry
   reading at 60 °C: 1.83 mg/L at sea level, 1.65 mg/L at 715 m. A threshold
   copied from a sea-level operation is optimistic here.

### 3.4 Niche partitioning: what a "diverse microbiome" actually requires

`[NEW]`. Three retrieved findings, which together say that a *single* oxygen
setpoint is the wrong shape of target for a diversity objective:

* **Growth and sporulation have different oxygen requirements.** Deploey &
  Fergus 1975 (abstract, verified): "The minimum O₂ concentrations that allowed
  trace growth to occur were lower than those that allowed measurable growth ...
  **The actinomycetes and fungi required more O₂ for sporulation than for
  growth**." A pile held just above a growth threshold sustains biomass but not
  reproduction — which over weeks is a diversity outcome, not a rate outcome.
* **Some compost thermophiles prefer microaerobic conditions.** Maheshwari &
  Bharadwaj (2000), *Thermophilic Fungi: Their Physiology and Enzymes*
  (PMC99000, retrieved rung 5), "Oxygen Requirement" section: "**Humicola
  insolens was reported to grow better under anaerobic or microaerobic
  conditions than under aerobic conditions at elevated temperatures**", and
  anaerobiosis in *Talaromyces duponti* switches it from the conidial to the
  sexual stage. A uniformly high-O₂ pile is not self-evidently the diversity
  optimum; some of the diversity lives in the gradient.
* **The one compost study that measures diversity against a process variable
  finds temperature, not oxygen.** Strom 1985 (in our corpus): species diversity
  "decreased markedly in laboratory composting at 60 °C and above ... the maximum
  desirable composting temperature based on species diversity is thus 60 °C" —
  at a comfortable 16 % interstitial oxygen throughout. Oxygen was not the
  variable.

**I found no study relating compost microbial diversity to an oxygen threshold
on any basis.** Anyone reasoning from "diverse microbiome" to an O₂ setpoint is
reasoning from niche theory, not from a compost measurement. That should be
labelled as such in our docs rather than implied.

### 3.5 Therefore: uplink O₂ **and** temperature

The current §4 already says "the probe's temperature channel is at least as
load-bearing as its oxygen channel" on Randle & Flegg's evidence. §3.3 turns that
from an observation into an arithmetic necessity: **the oxygen number cannot be
interpreted at all without the temperature it was taken at**, because the same
percentage means a 31 %-different biological condition across the pile's own
operating range. Both channels are already in the primary block
(`O2_COMP` 0x0000, `T_TIP` 0x0002, `T_CHAMBER` 0x0003), so this costs nothing —
but it should be stated as a *requirement on the uplink*, not left as an
inference a future payload-trimming exercise could undo.

---

## 4. Recommendation

### 4.1 Primary register: **dry-basis mole fraction**. Confirmed, and the
existing decision stands.

The reasoning in `o2.h`, `regmap.h` and `O2-HUMIDITY-CORRECTION.md` §4 reaches
the right answer. This report replaces its single-source support with a
convergent body of it, and adds one argument our docs do not make:

`[NEW]` **Dry basis is also the most robust choice given that Rev A has no
barometer** — which is the argument that decides the case against publishing pO₂
as primary. Because K is fixed by an air point,

```
C_dry = 0.20946 · (I/I_cal) · (P_cal − p_w_cal) / (P − p_w)
```

and the assumed-P error largely **cancels** between numerator and denominator.
Concretely: true P = 96.5 kPa, assumed 93.0, p_w_cal = 1.5 kPa, p_w_meas =
20 kPa (60 °C saturated) gives a true ratio of 1.2418 against an assumed 1.2534
— a **+0.93 %** error. The same 3.5 kPa error in an *absolute* pO₂ register is
**−3.7 %**, and it is baked in permanently at calibration because there is
nothing to cancel it. The channel that needs the BMP390 least is the dry-basis
one. That is worth recording, because §3c currently frames the missing barometer
as a straightforward liability.

Supporting reasons, now sourced rather than asserted:

* **Comparability.** Every threshold in §1 was established on dried or synthetic
  gas. Dry basis is the quantity those instruments actually measured, whatever
  their authors thought. Our alarm numbers transfer **unshifted** — which is
  what §4 already says, now resting on five primaries instead of one.
* **Basis-invariance.** Dry-basis mole fraction is the one number preserved
  across a condensation step. That is *why* the literature is accidentally
  self-consistent despite nobody stating a basis, and it is why our register can
  be compared against a hand-held meter on a sample line, a GC, or the Apogee
  next to us on the bus.
* **Trend meaning.** Dry-basis O₂ in fully aerated pore gas is 20.95 % at any
  altitude, weather or pile temperature. A trend in it is a trend in respiration.

### 4.2 Why not pO₂ as primary, despite its being the biologically active quantity

It is genuinely what the cell responds to and what Henry's law needs. Three
things disqualify it as the *primary trend*:

* It moves with weather (±3.5 %), altitude (−8 % here) and strongly with pile
  temperature. A pO₂ trend falls when a pile heats up even if aeration is
  unchanged — the same failure we rejected wet basis for.
* It is **not** comparable to any published threshold, because pO₂ is precisely
  the quantity destroyed by the condensation step every published instrument
  performed. The literature's numbers survive as dry mole fractions; they do not
  survive as partial pressures.
* Absolute pO₂ needs an absolute P at calibration, and that error never cancels
  (§4.1).

Its one real advantage — per-reading it needs no live P or RH — makes it a
candidate **fallback**: when the SHT45 has failed and `O2_COMP` correctly
publishes 0xFFFF, a pO₂-flavoured value is still computable from `O2_RAW` and the
calibration alone. A future use of `O2_RAW`, not a reason to move the primary.

### 4.3 No single basis serves both comparison and control — but the extra
channels are *derived*, not measured

The brief asked me to flag this explicitly if true. It is true: dry basis is the
comparison quantity, dissolved O₂ is the control quantity, and they diverge by a
temperature-dependent factor (§3.3). But this needs **no new measurement and
probably no new register**. `O2_COMP`, `T_CHAMBER` and `RH_CHAMBER` are already
in the primary block and `ASSUMED_P_HPA` is a config register, so both other
quantities are exactly recoverable downstream:

```
pO₂    = C_dry · (P − p_w(T_gas))              [kPa]
DO_sat = k_H(T_pile) · pO₂/101.325 · 32000     [mg/L]
k_H(T) = 0.0013 · exp(1700·(1/T − 1/298.15))   [mol L⁻¹ atm⁻¹]
```

One caveat that is a real design point: **the Henry's-law step needs the *pile*
temperature, not the probe's own.** The heater deliberately holds the chamber
warm, so neither `T_TIP` nor `T_CHAMBER` is the temperature the biofilm sees. The
site already has SMT100 probes on the same RS485 bus. That is a positive reason
to compute DO **on the dashboard rather than in the firmware** — the probe does
not know the pile temperature and should not pretend to. `[NEW]`

So:

* **`O2_COMP` (0x0000): dry-basis %vol. Unchanged. Primary.**
* **`O2_RAW` (0x0001): unchanged.** Raw evidence, and the only channel that
  survives an SHT45 failure.
* **Add the derivation, not the registers.** Document the two formulas in
  `regmap.h`/`FIRMWARE.md`; put the DO trace on the dashboard beside the
  dry-basis trace, using the SMT100 pile temperature.
* **If a register is added anyway**, prefer `PO2_PA` in the *diagnostic* block
  (0x0010 range), fail-closed on the same inputs as `O2_COMP`. Do **not**
  displace a primary-block channel — the block is at its 8-register limit for
  the reasons `regmap.h` already gives.

### 4.4 Alarm structure

* Keep a **10 % dry-basis** alarm for literature comparability. Cite **Suler &
  Finstein 1977** for it, not Schulze — they bracketed it experimentally
  (2 % ≪ 10 % ≈ 18 %), Schulze did not (§1.1).
* Add a **biofilm-DO** condition on the dashboard at **2.0 mg/L**, which by §3.3
  is a *temperature-dependent* dry-basis floor: 7.5 % at 40 °C, 10.6 % at 55 °C,
  12.2 % at 60 °C, 14.1 % at 65 °C.
* Above ~65 °C, treat it as a temperature problem. Both Randle & Flegg's
  conclusion and Strom 1985's diversity collapse point the same way, and §3.3
  shows no aeration can fix it.
* For the diversity objective specifically, the pair of controls is a
  temperature-dependent oxygen floor **and** a temperature ceiling near 60 °C —
  not a flat percentage.

---

## 5. Proposed edits, tagged against the CURRENT docs

Written in each doc's voice, ready to paste after review. **I applied none of
them.**

### 5.1 `[SHARPENS]`/`[CONTRADICTS]` — `O2-HUMIDITY-CORRECTION.md` §4, "The thresholds are dry-basis too, so the alarm points do not move"

Currently:

> The number everyone quotes — 5 %vol as the floor for aerobic activity — traces
> through Randle & Flegg (1978) p. 322 to its primary sources: "There is evidence
> (Schulze, 1962; Kane and Mullins, 1973) that thermophilic organisms are active
> in compost while the oxygen concentration remains above 5 %." Both are measured
> with the dried-sample method above.

The conclusion is right; two details are not. Schulze does not state a threshold,
and "both are measured with the dried-sample method above" is an assumption about
Kane & Mullins that I could not verify (their full text is behind a login wall,
and their oxygen work is culture incubation, not stack sampling). Proposed
replacement:

> The number everyone quotes — 5 %vol as the floor for aerobic activity — traces
> through Randle & Flegg (1978) p. 322: "There is evidence (Schulze, 1962; Kane
> and Mullins, 1973) that thermophilic organisms are active in compost while the
> oxygen concentration remains above 5 %."
>
> **Schulze 1962 is retrieved, and it is dry-basis beyond doubt** — the exhaust
> "was led downward into a water trap so that condensate could collect and
> overflow into a drain" before the Beckman D-2, and he states the frame outright:
> "the air flow is measured at room temperature and the oxygen concentration is
> also measured at room temperature in the Beckman analyzer", with the drum at
> 53–68 °C "and at a relative humidity of nearly 100 %". His O₂-consumption
> arithmetic takes the inlet as the dry 0.21.
>
> **But the 5 % is not his.** Schulze states no minimum anywhere. What he did was
> throttle air "so that the residual oxygen concentration in the exhaust gas
> remained between 5 and 10 %" — an operating band, promoted to a biological
> threshold by later reading. He never ran 4 %, or 3 %, or 2 %. The 5 % figure
> should be treated as a convention with a dry-basis pedigree, not as a measured
> floor.
>
> **The measured floor exists and is stronger.** Suler & Finstein (1977) varied
> the O₂ residual factorially: "Relatively small amounts of CO₂ were formed when
> the O₂ residual was 2 %, regardless of temperature. Foul odors sometimes
> developed ... Substantially more CO₂ was produced with residuals of 10 and
> 18 %", and 10 % was "only marginally less" productive than 18 %. Their gas
> train was a condensation trap ahead of a Beckman 777 — dry basis again. **Cite
> Suler & Finstein for the 10 % working floor, and Schulze only for the pedigree
> of the basis.**
>
> Kane & Mullins (1973) is behind an institutional login wall and unverified; its
> abstract confirms "a requirement for aerobic growth conditions" for 304
> thermophilic-fungal isolates, and its follow-up, Deploey & Fergus (1975),
> *Growth and Sporulation of Thermophilic Fungi and Actinomycetes in O₂–N₂
> Atmospheres*, established the requirement in **synthetic O₂–N₂ mixtures** —
> dry by construction, with no water in the system at all.
>
> The practical conclusion is unchanged and now rests on five primaries rather
> than one: the published thresholds are dry-basis, so correcting to dry basis
> means they transfer unchanged and no alarm point needs re-deriving.

### 5.2 `[NEW]` — `O2-HUMIDITY-CORRECTION.md` §4, a new subsection after the above

> **The dry convention is an artefact of sample lines, and it does not extend to
> in-situ probes.** Every compost O₂ study whose gas train can be inspected cools
> the sample before the detector — Schulze's water trap, Suler & Finstein's and
> Strom's condensation traps, MacGregor's 2-litre glass-wool trap, Randle &
> Flegg's cold trap and silica gel, Sundberg's cooler, Zheng's 20 °C bath and
> soda-lime, Naser's inline condensation traps — and **not one states a basis**.
> MacGregor (1981) demonstrates it without meaning to: at 45–65 °C set points
> their O₂ + CO₂ summed to 20.78, which is dry air, where saturated pore gas
> would have summed to about 17.
>
> The exception is the instrument class we are building. **TMECC 05.08-C,
> "In-Situ Oxygen Refresh Rate", is the one standardised method that puts a probe
> into the pile, and it never mentions water vapour**: "Standard gases of fixed
> O₂ content may be blended to achieve 1, 5, 10 and 15 % O₂ for exact calibration
> trials. Apparatus not adapted with temperature compensation can provide
> unpredictable results." Calibrate dry, insert saturated, compensate for
> temperature only. A probe run exactly to that standard publishes wet-basis
> numbers against dry-basis thresholds — the ~20 % error, in the anoxia-looking
> direction, sanctioned by the field's own method.
>
> This is the error this document exists to prevent, and it is worth being blunt
> that we could not find it documented anywhere: no compost paper states its gas
> basis as a basis, and none compares the two. The inference is from the method
> sections, and it is strong, but it is an inference.

### 5.3 `[NEW]` — `O2-HUMIDITY-CORRECTION.md` §4 or `regmap.h`: the "corrected" hazard

> **A warning about the word "corrected".** The UK Environment Agency's composting
> odour guidance, and Sauer & Crouch in *BioCycle* (December 2013), describe our
> exact situation and use "corrected (actual) oxygen" to mean the **wet** value.
> They are correcting a condensed sample-line reading back *into* the pile —
> Dalton's law applied in the opposite direction to ours. Their worked example:
> "If a meter reading indicates 5 percent oxygen at a moderate compost
> temperature of 113 °F (45 °C) ... the corrected (actual) oxygen level [is] 4.6
> percent." (Their arithmetic checks: 5 × (101.3 − 9.59)/101.3 = 4.53.)
>
> So a competent compost operator who has read either source will read a register
> labelled "corrected oxygen" **backwards**. `O2_COMP` must never be documented as
> merely "corrected"; the prose must say **dry basis** in as many words, every
> time.
>
> The EA is not arguing that wet basis is the right reporting quantity — for them
> the wet mole fraction is an intermediate on the way to dissolved oxygen. Which
> is the better argument, and is dealt with below.

### 5.4 `[NEW]` — a biology subsection for `O2-HUMIDITY-CORRECTION.md` §4 or `PLAN.md`

> **A fixed percentage is not a fixed biological condition, and the temperature
> coupling is severe.** Microbes live in the water film and oxygen reaches them by
> Henry's-law dissolution from the pore gas, so the controlling quantity falls
> with temperature twice over — once because vapour displaces oxygen, once
> because solubility drops. From the Environment Agency's own constants
> (k_H = 0.0013 mol L⁻¹ atm⁻¹, van 't Hoff 1700 K; *Oxygen solubility in compost*,
> Odour Technical Guide 3, 2012) at our 93 kPa: a 10 % dry-basis reading is
> 2.39 mg/L at 45 °C but only 1.65 mg/L at 60 °C. The EA's floor is 2 mg/L
> ("below 2 ppm ... may not prevent anaerobic conditions"), which coincides
> exactly with the dysaerobic ceiling in the microbial-ecology literature
> (Prakash et al. 2025, Table 1: "Dysaerobic — low oxygen levels of 0.1–2.0
> mg/L"). Holding 2 mg/L therefore needs 7.5 % dry basis at 40 °C, 10.6 % at
> 55 °C, 12.2 % at 60 °C and 14.1 % at 65 °C.
>
> Two consequences for the 75 °C excursion this plan already admits. **Fully
> aerated pore gas at 75 °C and 715 m delivers 2.05 mg/L** — the pile is
> oxygen-limited at the biofilm no matter how it is aerated, so that excursion is
> a cooling problem and no amount of air fixes it. This is an independent,
> arithmetic route to Randle & Flegg's conclusion that overheating rather than
> lack of oxygen was the restriction. And Strom (1985) found bacterial species
> diversity collapsing above 60 °C at a comfortable 16 % oxygen.
>
> **For a diversity objective the pair of controls is a temperature-dependent
> oxygen floor and a temperature ceiling near 60 °C**, not a flat percentage.
> Three further findings point the same way: Deploey & Fergus (1975) found that
> compost thermophiles "required more O₂ for sporulation than for growth", so a
> pile held just above a growth threshold sustains biomass but not reproduction;
> *Humicola insolens* "was reported to grow better under anaerobic or microaerobic
> conditions than under aerobic conditions at elevated temperatures" (Maheshwari &
> Bharadwaj 2000), so some of the diversity lives in the gradient rather than at
> the top of it; and the microbial-ecology literature defines these niches in
> mg/L and µmol/L, not %vol, because "the concept of hypoxia is broad, as any
> environment or niche with 0 %–21 % oxygen can be defined as micro-oxic"
> (Prakash et al. 2025).
>
> No study relates compost microbial **diversity** to an oxygen threshold on any
> basis. That step is niche theory, not a compost measurement, and should be
> labelled as such.

### 5.5 `[SHARPENS]` — the missing-barometer framing in §3c

Add at the end of §3c:

> One consolation the section above understates: the missing barometer hurts the
> **dry-basis** channel least. Because K is fixed by an air point, the assumed-P
> error largely cancels between calibration and measurement — a true 96.5 kPa
> against an assumed 93.0, with p_w 1.5 kPa at cal and 20 kPa at 60 °C
> saturation, gives a ratio error of only **+0.93 %**. The same 3.5 kPa error in
> an *absolute* pO₂ would be **−3.7 %** and permanent, because nothing cancels it.
> That is a reason to prefer dry basis on Rev A specifically, not merely to
> tolerate it.

### 5.6 `[SHARPENS]` — `o2.h` and `regmap.h`, the "Draeger tube" example

Both cite "a Draeger tube" as an exemplar of what reports dry-basis O₂. I found
no compost study measuring **oxygen** with a Dräger tube. Joshua et al. 1998, the
one paper in our corpus that used them, used Dräger tubes for the
*anaerobic-indicator* gases — NH₃, H₂S, acetic acid, alcohol — and measured O₂
with a Novatech zirconia analyser on a pumped sample line. Proposed: replace
"a Draeger tube" with **"a pumped sample line to any hand-held meter"**, which is
true, is the mechanism the EA guidance describes, and is the actual reason the
convention exists.

### 5.7 `[SHARPENS]` — the field-commissioning gate in `compostlab/o2-probe/PLAN.md`

The plan puts the probe on the bus beside an Apogee reference. Proposed addition:

> The Apogee reference is only a reference if its **vapour correction is
> applied**. Apogee's own FAQ says "Gas sensors read out in percent because this
> value does not change with temperature or pressure", which is true only on a dry
> basis; the correction that makes it true lives in a separate technical note
> (Blonquist et al., *Estimation of Soil Respiration*, Eq. 6), which converts the
> raw reading "to yield relative gas concentrations for a dry atmosphere". An
> uncorrected Apogee in 100 %RH pore gas reads wet basis. If we compare a
> corrected probe against an uncorrected Apogee they will *disagree* by ~20 % at
> pile temperature; if we compare two uncorrected instruments they will **agree
> and both be wrong**, which is worse. State which correction the reference is
> running before the comparison counts as a gate.

### 5.8 `[COVERED]` — Apogee independently validates the heater design

Not an edit, but worth knowing that a second party reached our heater decision
for our reason. Apogee's Oxygen Sensor FAQ:

> "In order to keep condensation from forming on the sensor's Teflon membrane
> (where oxygen diffusion occurs), the built-in heater is designed to warm the
> sensor to a temperature slightly above the ambient temperature. **This is
> particularly important in soil applications where the relative humidity is
> normally at 100 %. For this reason, it is recommended that the heater be
> continuously powered.** Once condensation forms on the membrane, the sensor must
> be removed from the humid environment and allowed to dry ... If the heaters are
> turned off and condensation forms, the heaters don't supply enough energy to
> evaporate the condensation once they are turned back on."

The last sentence is the interesting one — condensation on the membrane is a
**latching** failure that the heater cannot clear. That is an argument for our
`DEW_SUSPECT` bit being a latched, service-visible state rather than a transient
flag, and for the heater never being duty-cycled to save power. If `POWER.md`
contemplates duty-cycling the heater, this is evidence against it.

### 5.9 `[NEW]` — citation fix

Waksman, Cordon & Hulpoi 1939 is **Soil Science 47(2):83–114**, per the
publisher's own citation page, not 83–98. Our §4 inherited the 83–98 from
Randle & Flegg. Also worth a parenthesis that it is a *temperature* paper and
carries no gas-measurement basis, so nothing in the basis argument depends on it.

### 5.10 `[COVERED]` — checked and found already right

* Randle & Flegg's method quote, the ">18 % at 50–60 °C" self-corroboration, the
  overheating conclusion, the horizontal-vs-vertical variation, and the
  O₂/temperature anti-correlation across a turn — §4. All correct; §3.3 adds an
  independent quantitative route to the overheating conclusion.
* Wet basis reads 16.8 %vol at 60 °C/100 %RH — §2. Correct at 101.3 kPa. At our
  93 kPa it is 16.4 %; the table is fine as stated but is not the site.
* The altitude and weather terms, and in-situ calibration cancelling altitude but
  not weather — §3c. Correct; §5.5 adds the quantitative reason this favours dry
  basis.
* Tri-state/fail-closed handling — `o2.h`, `regmap.h`. Correct, and more
  important than the docs make it sound: a silently uncorrected value at 60 °C is
  20 % wrong.
* `ASSUMED_P_HPA` default 930 hPa with bounds, and the 80 °C / p_w ≤ 0.5·P
  clamps — correct. §3.3 gives an independent reason the 65–75 °C band is
  special.

---

## 6. Candidates for `~/dev/kb` rather than this repo

Three claims generalise beyond the o2-probe. I did **not** write them; flagging
for Fab. `~/dev/kb/INDEX.md` currently has one composting entry
(`composting/farming-docs-pointer.md`, a pointer) and nothing on gas-measurement
basis.

1. **"A gas-concentration threshold inherits the basis of the sampling train, not
   of the medium."** Any published %-gas threshold measured through a cooled
   sample line is a dry-basis number whatever the paper says, and an in-situ
   sensor reporting wet basis alarms early against it by p_w/P. Best evidence:
   MacGregor 1981, because the 20.78 sum is *self-verifying* — the basis is
   readable off the data without any method statement. A measurement-technique
   note, not a compost note.
2. **"'Corrected' on a gas reading has two opposite meanings in the field."**
   EA/BioCycle correct dry→wet; Apogee and we correct wet→dry. A
   convention-hazard note, and the kind of thing that silently inverts a spec.
3. **"Apogee publish buried galvanic O₂ cells on a dry-atmosphere basis, with all
   corrections referenced to calibration conditions — and the FAQ contradicts the
   technote."** Plus the latching-condensation behaviour of the membrane heater.
   A vendor-behaviour note, reusable next time a soil or pile gas sensor is
   specified.

---

## 7. SOURCES

New in this report unless marked. "Local" = already in
`/Users/fab/dev/ha/farming/compostlab-literature`.

| source | URL / location | retrieved? | authority |
|---|---|---|---|
| **Schulze, K.L. 1962. Continuous thermophilic composting. *Appl. Microbiol.* 10:108–122** | https://pmc.ncbi.nlm.nih.gov/articles/instance/1057822/pdf/applmicro00340-0018.pdf | **yes, rung 5** | One of the two primaries §7 lists as unretrieved. Now read: dry-basis confirmed twice; the 5 % is *not* his. |
| Suler, D.J. & Finstein, M.S. 1977. Effect of temperature, aeration and moisture on CO₂ formation… *AEM* 33:345–350 | Local: `fundamentals/` | yes, local | The factorial experiment that actually brackets the floor (2 % / 10 % / 18 %). Condensation trap + Beckman 777. |
| MacGregor, S.T. et al. 1981. Composting process control… *AEM* 41:1321–1330 | Local: `monitoring-control/` | yes, local | `%O₂ = 20.78 − %CO₂` — self-verifying evidence of a dry basis. |
| Strom, P.F. 1985. Effect of temperature on bacterial species diversity… *AEM* 50:899–905 | Local: `microbiology/` | yes, local | The only diversity-vs-process-variable primary in the corpus. Its answer is temperature, not oxygen. |
| Zheng, G. et al. 2018. Oxygen monitoring equipment for sewage-sludge composting. *Sensors* 18:4017 | Local: `monitoring-control/` | yes, local | Closest published analogue to this instrument. 20 °C bath + soda-lime; dry **and CO₂-free**. |
| Joshua, R.S. et al. 1998. Characterization of temperature and oxygen profiles… *Compost Sci. Util.* 6(4) | Local: `monitoring-control/` | yes, local | Pumped sample line to an external zirconia analyser. Source of the Dräger correction in §5.6. |
| Sundberg 2005 (SLU thesis) / Smårs et al. 2002 | Local: `monitoring-control/` | yes, local | 16 % setpoint held on cooled, condensed reactor gas. |
| Beck-Friis, B. et al. 2000 | Local: `emissions/` | yes, local | Pore-gas primary; vials + GC, condensed at ambient. |
| Naser et al. 2025. A real-time gas sensor network… | Local: `monitoring-control/` | yes, local | Most recent sensor-network paper; "inline condensation traps". |
| **USDA/USCC 2002. TMECC method 05.08-C, In-Situ Oxygen Refresh Rate** | Local: `fundamentals/` | yes, local | The one standard method for in-pile O₂. Calibrates on dry blended gas, never mentions water vapour. Central to §2.2. |
| Rynk, R. (ed.) 1992. *On-Farm Composting Handbook*, NRAES-54 | Local: `fundamentals/` | yes, local | Table 2.1 "Greater than 5 %"; and the honest p. 57 caveat that the 5 % guide fails in both directions. |
| **Oshins, C. et al. 2022. "The composting process", ch. 3 of *The Composting Handbook*** | https://ucanr.edu/sites/default/files/2022-04/365893.pdf | **yes, rung 1** (4.48 MB, `%PDF-1.7`) | Current authority; supersedes NRAES-54. Names Schulze 1962 as the supporting research for 5 %, and records the modern 10 %/18 % range as a practice consensus with no primary. |
| **Environment Agency (UK). *Oxygen solubility in compost*, Odour Technical Guide 3, v1.0, 19 July 2012** | https://compostsystems.com/wp-content/uploads/2021/08/Oxygen-Solubility-in-Compost-Odor-Technical-Guide-1.pdf | **yes, rung 1** (346 kB, `%PDF-`) | Regulator guidance. The Henry's-law argument, the 2/3 ppm rule, and the constants I reproduced the table from. Vendor-hosted copy; EA original not located (UNRESOLVED 3). |
| **Sauer, N. & Crouch, E. 2013. "Measuring Oxygen In Compost". *BioCycle*, Dec 2013** | https://www.biocycle.net/measuring-oxygen-in-compost/ | **yes, rung 1** (132 kB, correct `<title>`) | Trade journal of record. Source of the opposite-direction "corrected (actual)" usage; worked examples verified arithmetically. |
| **Blonquist, J.M. et al. *Estimation of Soil Respiration* (Apogee technical note)** | https://www.apogeeinstruments.com/content/O2_Sensor_Soil_Respiration.pdf | **yes, rung 1** (5.39 MB, `%PDF-`) | Vendor of the reference sensor. Dry-atmosphere convention; corrections referenced to calibration conditions. |
| **Apogee Instruments, *Oxygen Sensor FAQs*** | https://www.apogeeinstruments.com/oxygen-sensor-faqs/ | **yes, rung 1** | "Gas sensors read out in percent because this value does not change with temperature or pressure" — true only on a dry basis. Also the heater rationale and the latching-condensation behaviour (§5.8). |
| **Prakash, O. et al. 2025. The study of microbial physiology under microoxic conditions is critical but neglected. *Environ. Microbiol.*** | https://pmc.ncbi.nlm.nih.gov/articles/PMC12169914/ | **yes, rung 5** | Current review of the microaerophile niche question. Table 1 defines the niches in mg/L and µmol/L. |
| **Deploey, J.J. & Fergus, C.L. 1975. Growth and sporulation of thermophilic fungi and actinomycetes in O₂–N₂ atmospheres. *Mycologia* 67** | https://www.jstor.org/stable/3758339 | **abstract only, rung 5** — full text behind JSTOR login | The follow-up to Kane & Mullins, and the reason their lineage is dry-basis by construction. Growth-vs-sporulation threshold split. |
| **Maheshwari, R. et al. 2000. Thermophilic fungi: their physiology and enzymes. *Microbiol. Mol. Biol. Rev.*** | https://pmc.ncbi.nlm.nih.gov/articles/PMC99000/ | **yes, rung 5** | "Oxygen Requirement" section; *Humicola insolens* preferring microaerobic conditions. Notably gives **no** numeric O₂ thresholds — a negative result worth recording. |
| Kane, B.E. & Mullins, J.T. 1973. *Mycologia* 65:1087–1100 | see UNRESOLVED 1 | **abstract only** | — |
| Waksman, S.A. et al. 1939. *Soil Science* 47(2):83–114 | see UNRESOLVED 2 | **citation page only** | — |
| Haug, R.T. *The Practical Handbook of Compost Engineering*, ch. 7 | https://slunik.slu.se/kursfiler/TE0014/20061.1920/F06._Haug_-_Kapitel_7.pdf | **yes, rung 1** (3.14 MB, `%PDF-1.4`) | Standard engineering text; retrieved and checked, adds no basis statement. Cited as checked-and-negative. |
| Randle, P. & Flegg, P.B. 1978 | `/Users/fab/dev/ha/farming/oxygen-mushroom.pdf` | yes, user-supplied | Already in §4. Method quote verified against the local PDF. |

---

## 8. UNRESOLVED

Exact URL and the **highest rung actually attempted**. Nothing here is treated as
absent and no content was inferred for any of it.

1. **Kane, B.E. & Mullins, J.T. (1973). "Thermophilic fungi in a municipal waste
   compost system." *Mycologia* 65(5):1087–1100.**
   URLs: https://www.jstor.org/stable/3758290 and
   https://www.tandfonline.com/doi/abs/10.1080/00275514.1973.12019529
   **Highest rung attempted: 5** (headed Chrome on 127.0.0.1:9456, 30 s dwell
   each). Both pages loaded correctly — real titles, no interstitial — and both
   serve only the abstract behind an **institutional login wall** ("Log in
   through your school or library" / "Read this article … needAccess=true").
   Not bypassed, per house rules. **IN PROGRESS, not closed.**
   *What is still missing:* whether the "5 %" is Kane & Mullins' own measured
   figure or their reading of a compost system, and on what basis their field O₂
   was taken. A Google index snippet of the JSTOR full text reads "…in the middle
   zones where the O₂ concentration drops below 5 % has been…", which I record as
   corroboration that the figure appears in the paper and explicitly **not** as
   verified content.
   *What does not depend on it:* the dry-basis conclusion, which Schulze,
   Suler & Finstein, MacGregor, Randle & Flegg and Deploey & Fergus establish
   independently. *What does:* whether §5.1's proposed replacement text can say
   anything stronger about Kane & Mullins than "unverified".

2. **Waksman, S.A., Cordon, T.C. & Hulpoi, N. (1939). *Soil Science*
   47(2):83–114.** DOI 10.1097/00010694-193902000-00001
   URL: https://journals.lww.com/soilsci/citation/1939/02000/influence_of_temperature_upon_the_microbiological.1.aspx
   **Highest rung attempted: 5.** Rung 1 returned a Cloudflare "Just a moment…"
   (403, 6 kB); rung 5 with a 45 s dwell returned the real citation page (title
   `INFLUENCE OF TEMPERATURE UPON THE MICROBIOLOGICAL... : Soil Science`, 520 kB).
   The record is marked "Original Article: **PDF Only**", carries no abstract, and
   the full text is behind "Full Text Access for Subscribers / Log in for access /
   Not a Subscriber? Buy". A **login-and-paywall**; not bypassed.
   **IN PROGRESS, not closed.** Recovered from the citation page anyway: the
   correct pagination, 47(2):83–114 (§5.9). Nothing in the basis argument depends
   on it — it is a temperature paper — but the 50–65 °C thermophile optimum our
   §4 quotes remains second-hand through Randle & Flegg.

3. **Environment Agency, Odour Technical Guide 2** — the Dalton correction table
   itself, which Guide 3 says "must be used first to correct oxygen
   measurements".
   **No URL found to climb against.** Two Serper searches; the exact phrase
   `"Odour Technical Guide 2"` returned **no web results at all**, and a
   site-scoped search returned only Guide 3. This is a *search* failure, not a
   *fetch* failure, so no rung applies. The substance is covered — *BioCycle*
   reproduces the same table as its Table 1 and I verified its arithmetic
   independently — but the EA original and its exact wording are missing.
   Suggested next steps, neither attempted: the EA contact named in Guide 3
   (nick.sauer@environment-agency.gov.uk), or the CompostManager O₂ calculators
   the BioCycle article cites at `compostmanager.com/en/o2-calculators`.

4. **Deploey & Fergus 1975 full text** — https://www.jstor.org/stable/3758339
   **Highest rung attempted: 5**; abstract retrieved, full text behind the same
   JSTOR login wall as UNRESOLVED 1. The abstract carries the two findings I use
   (§3.4) verbatim, but **the actual minimum-O₂ percentages are in the tables and
   I do not have them.** A search for them returned only the table footnote "The
   number in parentheses indicates the atmosphere containing the lowest
   concentration of oxygen that allowed sporulation to occur". If those numbers
   matter — and for a diversity-driven threshold they might be the best numbers in
   the whole literature — this is the one to unlock.

5. **Koledzi 2021, *AJEST***, surfaced in search with "in the context of carbon
   financing it is required that the rate oxygen inside the windrows exceeds 8 %".
   URL: https://academicjournals.org/journal/AJEST/article-full-text/2D78B4167107
   **Highest rung attempted: 0 — not fetched.** A secondary repetition, and the
   8 % is a carbon-accounting requirement rather than a biological one. Recorded
   rather than dropped; fetch it before anyone cites an 8 % number.

6. **Randle & Flegg 1978 at the publisher** —
   https://www.sciencedirect.com/science/article/pii/0304423878900535
   **Highest rung attempted: 5**, before Fab supplied the local PDF. ScienceDirect
   served an explicit CAPTCHA ("Please confirm you are a human by completing the
   captcha challenge below", reference `a36d95dbb9f4a3e5`) on two navigations
   (25 s and 75 s dwells). Not solved. **Moot** — the local copy at
   `/Users/fab/dev/ha/farming/oxygen-mushroom.pdf` was read instead and every
   quote in this report comes from it. Recorded for the access log only. A tab may
   still be open on that URL in the Chrome on port 9456; it can be closed.

### Tool and access notes

* **`mcp__serper__search_rag_context` (rung 6) is currently broken** on this
  machine: two calls returned `MCP error -32603: Search failed: Cannot read
  properties of undefined (reading 'replace')`. Rung 6 was therefore unavailable
  for the paywalled items; I used ordinary `search_web` instead. Worth knowing
  before someone plans a ladder around it.
* **PMC PDF recipe** (used for Schulze). Article *pages* fetch fine at rung 5,
  but `/articles/instance/<id>/pdf/...` is fronted by an invisible Google
  Enterprise reCAPTCHA. It **clears itself** in a real headed browser: navigate a
  target straight to the PDF URL and dwell ~45 s (the tab title becomes the PDF
  filename), then run an in-page `fetch(..., {credentials:'include'})` from the
  article origin and base64 the bytes back over CDP. curl at rungs 1–2 returns an
  1.8 kB HTML stub with a **200** status — judged by content, not status, as the
  house rule requires.
* `journals.asm.org` returned 403 with a 5.8 kB HTML body for the same paper at
  rung 1; PMC was the working route.
* `journals.lww.com` is Cloudflare-fronted and passes at rung 5 with a 45 s dwell.
  The DOI `https://doi.org/10.1097/...` redirects to Ovid and returns 200 with an
  empty `<title>` — a dead end; use the `journals.lww.com` citation URL.
