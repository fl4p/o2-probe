# Adversarial review — `CONTACT-CORROSION.md`, ENIG + selective conformal coat

**Date:** 2026-09-04 · **Target:** `compostlab/o2-probe/CONTACT-CORROSION.md` (as of the
2026-09-04 revision) · **Board:** `~/dev/ee/hw/o2-probe` — ENIG, green mask both sides,
1 oz/0.5 oz, FR-4, 4L; potted zone + selectively-coated gas zone with clear apertures;
separable O₂ cell socket (Cambion 450-3703); ~100 % RH, ≤75 °C, condensing, NH₃ + H₂S + CO₂.

---

## ACCESS

Browser control was proven before any retrieval: a Playwright context with a plain-Chrome
UA override navigated `about:blank` and read its DOM (`readyState: complete`), then fetched a
live external page.

- **External page fetched through the browser:** `https://www.inemi.org/creep-corrosion` —
  `<title>` = **"iMIS"**. This URL was *composed by me* from a guessed path and returned a
  genuine site-rendered **404** ("We couldn't find what you're looking for"), not a block —
  the rendered chrome, cookie banner and footer confirm the site served us normally. Later
  browser fetches of real URLs on the same and other hosts succeeded (e.g.
  `https://autotechnology.com/…/iec-60068-2-60-mixed-flowing-gas-testing/` →
  `<title>` = "Mixed Flowing Gas Testing | Auto Technology Company";
  `https://link.springer.com/article/10.1007/s12540-017-7262-z` → `<title>` = "Galvanic
  corrosion behaviors of Cu connected to Au on a printed circuit board in ammonia solution |
  Metals and Materials International | Springer Nature Link").
- **Live search result (Serper, 2026-09-04):** query `iNEMI creep corrosion flowers of sulfur
  test results ENIG ImmAg OSP HASL surface finish susceptibility` returned, among others,
  `https://thor.inemi.org/webdownload/2018/Creep_Corrosion_APEX_Feb_2018.pdf` with the snippet
  "ENIG finished PCBs are very prone to creep corrosion and that ▪ OSP finished PCBs are very
  resistant to creep corrosion." That PDF was then fetched (`%PDF-`, 615 292 bytes) and read
  in full.

One source was blocked and is marked as such: `ui.adsabs.harvard.edu` returned a
"Human Verification" challenge in a headless, non-handoff-capable session. Per the access
rules I did not retry around it; the same work was obtained from the publisher's own landing
page instead, so no claim rests on the blocked route.

---

## VERDICT

**Conditional — and one of the two load-bearing claims in the document is wrong.** ENIG is
**not** the most creep-corrosion-resistant common finish: the primary iNEMI/IBM round-robin
data say the opposite ("ENIG finished PCBs are very prone to creep corrosion … OSP finished
PCBs are very resistant"), and the Alcatel-Lucent primary says SnPb HASL "offers excellent
corrosion protection of the underlying copper due to its thick coating" — so your suspicion
about HASL is correct and your ENIG rationale is not. The spec nevertheless survives, because
the variable that actually dominates creep corrosion in every primary I inspected is **not the
finish at all** — it is **flux residue and ionic surface contamination**: clean FR-4 and clean
mask do not support creep corrosion, organic-acid flux residue does (25 of 25 bad boards vs
0 of 11 bare boards, Xu et al. Table 2), and iNEMI could not produce creep corrosion in the
FoS chamber at all until it deliberately deposited ammonium salts. Your gas zone is a
condensing ammonium-salt generator by construction, so the design changes that matter are
**rosin-only flux plus a real post-solder clean, a parylene (not sprayed acrylic/urethane) gas-zone
coat, and moving the exposed-copper apertures away from the guard** — keeping ENIG, but for a
different and much weaker reason than the document gives.

---

## 1. "ENIG is the most creep-corrosion-resistant of the common finishes"

**Verdict: FAILS.** The claim is not supported and is contradicted by the primary literature.
Your specific suspicion about HASL is **supported**.

### The direct contradiction (inspected primary)

Singh, Palmer, Fu, Lee, Lee, Guo, Li, Lee, Tong, Xu, *Round Robin Evaluation of iNEMI Creep
Corrosion Qualification Test*, IPC APEX Expo, Feb 2018 (IBM / iNEMI / iST / Lenovo / Dow /
Nokia). Retrieved as PDF from
`https://thor.inemi.org/webdownload/2018/Creep_Corrosion_APEX_Feb_2018.pdf`,
**inspected in full** (slide deck, 14 149 characters of text layer).

> "The test results in general agree with the industry position that
> ▪ **ENIG finished PCBs are very prone to creep corrosion** and that
> ▪ **OSP finished PCBs are very resistant to creep corrosion**."
> — Conclusions slide (final page). **Direct evidence.**

This is not an offhand remark; it is the stated conclusion of a three-company round robin over
ImAg, ENIG and OSP with OR and RO fluxes, at 50 °C in the iNEMI flowers-of-sulfur chamber, over
three 5-day runs at 31–45 %, 46–57 % and 61–78 % RH. The leakage-resistance tables in the same
deck show it quantitatively: in the 61–78 % RH run, ENIG/OR-flux boards at site B read
**240 kΩ, 210 kΩ and 800 kΩ** across land pairs, and in the 46–57 % run ENIG/OR at site B read
**160, 320, 980, 1.63, 72 and 270 kΩ** — while every OSP row in all three runs is "--" (no
measurable leakage) at all three sites. Values as low as **0.01–0.07 kΩ** appear on ENIG rows in
the first run. ImAg failed too, but on fewer rows than ENIG. Origin: measured. Transformation:
direct. Conditions: 50 °C FOS chamber, 20 rpm paddle wheel, 100 ml household bleach, RH as
stated.

A separate iNEMI-derived result, **secondary** (ResearchGate abstract of *Testing Printed
Circuit Boards for Creep Corrosion in Flowers of Sulfur Chamber: Phase 2*,
`https://www.researchgate.net/publication/398212387_…`), reads: "A surprising result was that
the iNEMI prepared **ENIG PCBs suffered creep corrosion even at the relatively low relative
humidity of 60 %**." I could not obtain the Phase 2 full text; treat this as corroborating
direction only, not as an independent number.

### Why ENIG is *not* protective here (mechanism)

ENIG's Au/Ni stack does not eliminate exposed copper; it changes its electrochemistry. The
gold is a large, noble, permanently-connected cathode. Any copper still exposed — at the mask
interface, at a mask-defined pad edge, at a routed edge or castellation, or at your
deliberately-clear apertures — becomes a **small anode coupled to a large cathode**, which is
the worst possible galvanic area ratio. This is measured directly in ammonia (see §5) and is
the standard reading of ENIG's creep-corrosion behaviour. **This is my inference from the two
primaries below plus §5's measurements**, not a sentence any single source states in this form.

### HASL — your suspicion is right

Xu, Smetana, Franey, Guerra, Fleming, Reents (Alcatel-Lucent), Willie (Flextronics), Garcia
(Sanmina-SCI), Encinas, Jiang, *Creep Corrosion of PWB Final Finishes: Its Cause and
Prevention*, IPC/electronics.org technical resource `E8&S28_02.pdf`, retrieved from
`https://www.electronics.org/system/files/technical_resource/E8%26S28_02.pdf`
(`%PDF-`, 1 579 737 bytes), **inspected** — abstract, §1 introduction, §3.1.1–3.1.4 and Table 2.

> "While **SnPb HASL offers excellent corrosion protection of the underlying copper due to its
> thick coating and inherent corrosion resistance**, the lead-free board finishes provide
> **reduced corrosion protection to the underlying copper due to their very thin coating**. For
> ImAg, the coating material itself can also corrode in more aggressive environments."
> — Abstract. **Direct evidence.**

The mechanism you guessed is also the one the industry gives: because HASL is a *soldering*
process rather than a plating process, the solder wraps the pad edge, so there is less copper
exposed at the mask/pad interface than on a thin immersion finish. Stated as expert opinion (not
data) by Jim Hall, ITM Consulting, in *Does HASL or ENIG Reduce Creep Corrosion in Corrosive
Environments?*, Circuitnet Board Talk, `https://www.circuitnet.com/board-talk/55998.html`,
**inspected** (full transcript rendered in browser):

> "I am guessing that the idea is that with hot air solder leveling because it is done as a
> soldering process it **coats the edges of the pad, perhaps better, than the plating processes
> do in your ENIG**. The exposure, the ability of that sulfur to get at some copper on the edges
> of the pad is **maybe a little more likely on an ENIG board rather than a HASL board**."
> — **Secondary / expert assertion**, explicitly hedged by its author ("my guess", "not well
> quantified", "the results that I have seen are not consistent").

A lead-free HASL result appears in Schueller, *Creep Corrosion on Lead-Free Printed Circuit
Boards in High Sulfur Environments*, SMTA International 2007 — reported in a ResearchGate
snippet as "OSP finish still experienced slight creep corrosion in 6 days. **LF HASL showed no
creep corrosion**". I could **not** obtain the Schueller full text; this is
**second-hand via a search-result summary of a ResearchGate page** and I am recording it as a
lead, not as evidence. Do not quote it as a finding.

### Where your ENIG belief probably came from

Every PCB-vendor and distributor blog says ENIG is the corrosion-resistant finish
(e.g. `hemeixinpcb.com`, `pcbcart.com`, `allpcb.com`, `ltcircuit.com` — all **secondary,
commercial, uncited**). They are talking about *shelf-life oxidation and solderability*, which
is what the finishes were designed for. Xu et al. say this explicitly:

> "Lead-free PWB final finishes have been developed with the primary design objective of
> providing a solderable and coplanar surface … While the **short-term corrosion resistance …
> is important for the purpose of maintaining shelf-life for solderability (up to 12 months),
> long-term corrosion resistance was neither required nor considered**."
> — §1 Introduction. **Direct evidence.**

**Ranking, on the evidence I inspected** (creep corrosion specifically, not oxidation):
SnPb HASL best → OSP very resistant → ImmSn/LF-HASL unresolved → **ENIG very prone** ≈ ImAg
worst-known-in-field. ImAg's notoriety is real (Dell field failures within 4 weeks of service,
Schueller 2007, cited in Fu et al. 2014 §1 — **inspected as a citation, not as the original**),
but it does not make ENIG good.

### Should you change the finish?

**No — but not for the reason in the document.** Reasons to keep ENIG anyway:

1. HASL's advantage is largely a *SnPb* HASL result. Your board is RoHS; lead-free HASL's
   creep-corrosion advantage is not established in anything I could inspect.
2. HASL is unsuitable for this board on other grounds: coplanarity for the SGX/SHT parts, and
   an uncontrolled, thick, non-flat finish under a socket land.
3. **The finish is second-order.** §§3–4 below show flux residue and ionic contamination
   dominate by a much larger margin than any finish difference in these tests.

**What must change in the document:** delete the sentence "ENIG is the most
creep-corrosion-resistant of the common finishes" and the ImAg/OSP comparison that follows it.
The "don't let it be value-engineered to ImAg" instruction still stands (ImAg *is* worse), but
"don't value-engineer to OSP" is now backwards — OSP tested *better* than ENIG on creep.

---

## 2. The ppb→ppm extrapolation and ISA-71.04

**Verdict: the ppb numbers and class boundaries SURVIVE — precisely. The "3–5 orders of
magnitude" arithmetic SURVIVES. The implied monotonic concentration→damage relation FAILS,
and iNEMI says so in as many words.**

### The class boundaries (inspected primary)

**ANSI/ISA-S71.04-1985**, *Environmental Conditions for Process Measurement and Control
Systems: Airborne Contaminants*, retrieved as PDF from
`https://webdelprofesor.ula.ve/ingenieria/oscaror/CursosDictados/web instrumentacion
industrial/3 desarrollo de proyectos/normas ISA/STANDARD/S_7104.PDF`
(`%PDF-1.2`, 153 532 bytes), **inspected** — §6.3 and **Table 3, p. 14**:

| Severity level | G1 Mild | G2 Moderate | G3 Harsh | GX Severe |
|---|---|---|---|---|
| Copper reactivity (Å after 1 month) | < 300 | < 1000 | < 2000 | ≥ 2000 |
| **H₂S (ppb)** | **< 3** | **< 10** | **< 50** | **≥ 50** |
| SO₂/SO₃ (ppb) | < 10 | < 100 | < 300 | ≥ 300 |
| Cl₂ (ppb) | < 1 | < 2 | < 10 | ≥ 10 |
| NOx (ppb) | < 50 | < 125 | < 1250 | ≥ 1250 |
| **NH₃ (ppb)** | **< 500** | **< 10 000** | **< 25 000** | **≥ 25 000** |

Units footnote: "mm³/m³ (cubic millimeters per cubic meter) **parts per billion average for the
test period**". Origin: standard. Status: classification limit. **Direct evidence.**

**So your "single-digit to tens of ppb for G2/G3" is exactly right** — G2 is < 10 ppb, G3 is
< 50 ppb. Arithmetic, recomputed independently:

- 35 ppm = 35 000 ppb → **3 500× the G2 boundary** (3.54 orders), **700× the G3/GX boundary**
  (2.85 orders). Your "~3 orders of magnitude" is correct.
- 2 083 ppm = 2 083 000 ppb → **208 300× G2** (5.3 orders), **41 660× G3/GX** (4.6 orders).
  Your "the disturbance peaks are five" is correct against G2.

### Two corrections to the framing

**(a) "ISA-71.04 has no class for it" is wrong.** GX is **open-ended** (`≥ 50 ppb`), so
2 083 ppm *is* GX. What GX means is written into the standard, §6.3.4, and it is worth
quoting because it is the actual verdict on this design:

> "**Severe** — An environment in which **only specially designed and packaged equipment would
> be expected to survive**. Specifications for equipment in this class are a matter of
> negotiation between user and supplier." — §6.3.4. **Direct evidence.**

**(b) Your NH₃ exposure is also GX, and the document does not say so.** The project's own
`COMPOST-METROLOGY.md` line 365 refers to "the **> 700 ppm** exhaust maxima cited above" for
NH₃. 700 ppm = 700 000 ppb = **28× the ISA GX threshold of 25 000 ppb**. NH₃ is a *copper*
attacker (§6.2.7: "Copper and copper alloys are particularly susceptible to corrosion in
ammonia environments") and §5 below shows it interacts badly with ENIG specifically. **The
document treats NH₃ as a secondary line in a table; it should be a co-equal driver.**

### Two multipliers in the standard that the document misses entirely

Both are in the Table 3 footnote and §3, and both apply to this probe:

> "The gas concentration levels shown below … are believed to approximate the Copper Reactivity
> Levels stated above, **providing the relative humidity is less than 50 %**. For a given gas
> concentration, the **Severity Level … can be expected to be increased by one level for each
> 10 % increase in relative humidity above 50 %** or for a relative humidity rate of change
> greater than 6 % per hour." — Table 3 note. **Direct evidence.**

> "**Chemical/temperature effects may cause the rates of destructive chemical reactions to more
> than double for every 10 °C increase in temperature.**" — §3.4. **Direct evidence.**

At ~100 % RH that is **five severity-level steps** on top of the concentration; at 75 °C versus
a 25 °C reference that is **more than 2⁵ = 32×** on rate. Neither is in `CONTACT-CORROSION.md`.
The gas table is stated at a condition (RH < 50 °C, ambient temperature) that your probe never
sees. **Inference: the honest statement is not "3–5 orders above G3" but "far outside the range
in which ISA-71.04's concentration table is even defined."**

### Is the relation monotonic? No — and that is the load-bearing correction

iNEMI, the body that owns this problem, says concentration is not usable as a predictor at all.
*iNEMI Position Statement on the Limits of Temperature, Humidity and Gaseous Contamination in
Data Centers and Telecommunication Rooms to Avoid Creep Corrosion on Printed Circuit Boards*,
20 April 2012, `https://thor.inemi.org/webdownload/projects/ba/Creep_Corrosion/iNEMI_Position_Paper_Creep_Corrosion_042012.pdf`,
**inspected in full** (2 pages), p. 1:

> "Gaseous contamination limits for the reliable operation of electronic equipment **cannot be
> specified in terms of the concentrations of gaseous contaminants in the air — metal corrosion
> is too complex a process to allow its rate to be determined from gaseous chemical
> composition.** A more convenient and quantitative approach is the so-called 'reactive
> monitoring' method described in ANSI/ISA-71.04-1985…" — **Direct evidence.**

Its recommended limits (p. 1–2), for reference: copper reactivity **< 30 nm/month**, silver
**< 20 nm/month**, temperature 18–27 °C, **RH < 60 %**, dew point 5.5–15 °C. Every one of those
is violated by your service condition, most by a wide margin.

There is also direct evidence of **saturation** in the mechanism. Fu et al. 2014 (§3, inspected)
report from Battelle's foundational work: "Creep corrosion of copper on porous Au-Ni-Cu plating
was found to be **accelerated by small amounts of NO₂, but large variations in concentration
had little added effect**." (Origin: cited from Abbott 1988 — **second-hand within an inspected
primary**; I did not obtain Abbott.) And in iNEMI's own chamber: "**The amount of sulfur has no
effect on the Cu and Ag corrosion rates**" (Singh et al. 2018, Conclusions, **direct**).

**Net for you:** the ppb figures and the order-of-magnitude arithmetic are right, but the
inference "1000× the concentration ⇒ 1000× the damage" is not supported and is contradicted
by two primaries. Below and above certain thresholds the rate is controlled by the *surface*
(electrolyte film, salts, flux residue), not by the gas concentration. That does **not** make
you safer — it moves the risk from a knob you can bound (concentration) to a knob you control
in assembly (contamination), which is §§3–4.

**Edition caveat:** the standard I inspected is the **1985** edition. ANSI/ISA-71.04-**2013**
exists and, per multiple secondary sources (`istgroup.com/en/tech_20200716-ansi-isa-7104`,
`corrosionmonitor.com`, `purafil.com` — all **secondary**), keeps the same copper reactivity
boundaries (300/1000/2000 Å per 30 days) and adds a silver reactivity criterion (G1 < 200
Å/month). **Whether the 2013 edition retains the gas-concentration table above is
`unverified`** — ISA sells the standard and I did not attempt to defeat that paywall. iNEMI's
2012 position statement and IBM's own documentation both normatively reference the **1985**
edition, so the 1985 table is the right one to cite; note the edition when you do.

---

## 3. Episodic vs continuous dose

**Verdict: PARTLY SURVIVES, but the reassuring half of your framing collapses. Creep corrosion
does not integrate gas dose — it integrates *surface state*. Your spikes deposit persistent
solid reaction products, and those do not decay when the gas goes away.**

### Creep corrosion needs a surface electrolyte, and iNEMI proved it by failing to reproduce it without one

Fu, Singh, Campbell, Zhang, Ables, Lee, Lee, Li, Zhang, Lee, *Testing Printed Circuit Boards
for Creep Corrosion in Flowers of Sulfur Chamber*, IPC APEX Expo 2014,
`https://thor.inemi.org/webdownload/2014/APEX/Creep_Corrosion_Paper.pdf`
(`%PDF-`, 585 982 bytes), **inspected** — abstract, §§ on dust/salts, Results, Conclusions:

> "**The presence of salt contamination, similar in composition to the fine dust (PM2.5), was
> found to be necessary for creep corrosion. PCBs from lots with history of creep corrosion
> related failures, did not suffer creep corrosion in FOS test unless contaminated with
> ammonium salts and NaCl.**" — Conclusions, final bullet. **Direct evidence.**

> "Figure 9a shows the non-contaminated PCB to have **heavy corrosion of the copper pads, but no
> creep corrosion**. Figure 9b shows **extensive creep corrosion in the local areas contaminated
> with the ammonium and NaCl salts**. The morphology of this creep corrosion is quite similar to
> that seen on the failed cards returned from the field." — Results. **Direct evidence.**

The four salts iNEMI used to *cause* creep corrosion were **(NH₄)₂SO₄, NH₄HSO₄, NH₄NO₃ and
NaCl**. Read that list against your gas: NH₃ + H₂S + oxidant + condensing water on a cold
surface produces ammonium sulfide/sulfate/bisulfate deposits. **You are not exposed to
ammonium salts as a contaminant; your probe manufactures them in situ.** This is my
inference from the chemistry, but the inputs are all in your own repo and the salt list is
verbatim from the primary. It is the single most consequential finding in this review.

iNEMI also quantify the electrolyte trigger: the deliquescent RH of that ammonium/NaCl dust
"is somewhere between 50 and 62 %", and their comb-coupon leakage current "was in the
**pico-Ampere range when the humidity was 50 % and spiked up when the relative humidity was
raised to 62 %**" (§ on DRH, **direct evidence**, origin: measured, transformation: direct).
Ammonium hydrogen sulfate is called out as "probably the most corrosive salt in fine dust
because of its **low deliquescent relative humidity of 40 %**". Your gas zone is at ~100 % RH
essentially always.

### Does a 10-second 2083 ppm spike matter?

**Answer, as an inference with a stated mechanism:** yes — not because of the corrosion it
causes in ten seconds, but because it **deposits a persistent solid**. Sulfidation converts
H₂S into Cu₂S/Ag₂S/(NH₄)ₓSᵧ, which stay on the surface after the gas clears. A short spike
therefore behaves like a small permanent step in surface contamination, and the subsequent
creep — which iNEMI shows is driven by the *surface*, not the gas — proceeds afterwards in the
near-zero-H₂S baseline, driven by the condensate that is present continuously. **The gas
exposure is episodic; the damage state it creates is monotonic and cumulative.**

Two things bound how badly:

- Ten seconds at 2083 ppm is 20 830 ppm·s ≈ the same *time-integrated* exposure as 0.24 ppm
  continuous for a day, which is comparable to the iNEMI MFG condition of 1200 ppb (see §9).
  So a single spike is roughly one day of accelerated MFG. **A handful of spikes per season is
  not negligible; it is a short MFG test run inside your probe.** (Calculation: 2083 ppm ×
  10 s = 20 830 ppm·s; 20 830 / 86 400 s = 0.241 ppm. Transformation: calculated; inputs are
  Velusami 2013 via `COMPOST-GAS.md` and the ppm↔ppb conversion. **This assumes dose-linearity,
  which §2 says is not established — treat it as an order-of-magnitude framing device only.**)
- The `COMPOST-GAS.md` figures are *exhaust* and *disturbance-face* concentrations. There is
  still no pore-gas profile at depth. That gap is correctly stated in your document and I found
  nothing to close it.

**What survives from your document:** the two counter-arguments in §2.5 (H₂S partitions into
condensate; the exposure coincides with the measurement) both hold, and the first is now
stronger than you wrote it — the condensate is not merely a concentrating mechanism, it is the
*necessary condition* iNEMI identified.

---

## 4. Does conformal coating stop creep corrosion, and what happens at a coating edge?

**Verdict: only parylene, on the one controlled study I could inspect. And a coating edge is
the worst place on the board — which is exactly where your apertures put one.**

Osterman (CALCE, University of Maryland), *Effectiveness of Conformal Coat to Prevent Corrosion
of Nickel-palladium-gold-finished Terminals*, IPC APEX Expo proceedings,
`https://www.smtnet.com/library/files/upload/effectiveness-conformal-coat.pdf`
(`%PDF-`, 760 103 bytes), **inspected** — abstract, Experiments, Table 1, Table 4, Conclusions.

Coatings tested: acrylic ×2 (machine spray, hand spray), silicone (spray), polyurethane
(spray), parylene C (vacuum deposition), ALD Al₂O₃ 200 nm. Stress: three temperature-cycling
profiles (100 cycles each, −55→+95 °C across the three), then **modified EIA-364-TP65A Class IV
MFG** — Table 4: **50 ± 2 °C, 75 ± 2 % RH, H₂S 200 ± 20 ppb, Cl₂ 30 ± 5 ppb, NO₂ 200 ± 50 ppb,
SO₂ 200 ± 50 ppb** — then 200 h at 50 °C/50 % RH.

> "**With the exception of parylene, the common conformal coating materials and the atomic layer
> deposition coating do not prevent corrosion of the terminal metallization in corrosive
> environments. Corrosion products were observed at regions of thinned coating thickness, in
> particular on the edges of the terminals.** … Product manufacturers with corrosive environment
> considerations should consider using parylene. … **Manufacturers should focus on terminal
> coverage and not rely solely on coating thickness on a flat surface when qualifying a coating
> process.** For this study, ALD is not recommended…" — Conclusions. **Direct evidence.**

> "Non-uniform coating thickness was observed in the areas of the terminals. On some areas,
> **little to no coating material was found for the acrylic, silicone, and urethane coatings.**
> Parylene, which had the most uniform coating, was found to provide the best resistance to
> corrosion…" — Abstract. **Direct evidence.**

Osterman's literature review adds, for sulfur specifically (**second-hand within an inspected
primary** — Hindin & Fernandez, 2003 Tri-Service Corrosion Conference, which I did not obtain):
"They found **epoxy-type coatings provided the best protection** and effectively prevented
sulfur from interacting with any underlying silver alloys. **Only a double coat of the urethane
acrylate provided performance similar to epoxy. None of the other coatings were able to provide
sufficient protection to sulfidation** if they were to be used in a high-sulfur environment."

**Discrepancy flagged:** Osterman's abstract says "eight hours of mixed flowing gas"; the
Experiments section says the Group 2 specimens "were exposed under the mixed flow gases (MFG)
conditions … **for 48 hrs**". I could not resolve which is correct from the text. Use 48 h with
the caveat; either way the exposure is short and the coatings still failed.

### The coating-edge question, answered directly

You asked whether the boundary between coated and deliberately-uncoated area is better or worse
than uncoated. **On this evidence: worse, for two independent reasons.**

1. **Osterman's failures were located at edges** — "regions of thinned coating thickness, in
   particular on the edges of the terminals". A masked aperture boundary is a deliberate,
   maximally-sharp version of exactly that geometry, and spray coatings thin at every convex
   feature and pull back from every step by surface tension. **Direct evidence for the
   mechanism; my inference that your aperture boundary is the same geometry.**
2. **A coating edge creates a differential-aeration / occluded cell.** Under the coat lip,
   oxygen and gas exchange are restricted while the electrolyte film is retained; just outside,
   they are not. That is a classic crevice geometry, and it concentrates attack at the line
   rather than spreading it. **This is my inference**, consistent with (but not stated by)
   the sources; I did not find a study of coating edges next to intentional apertures. If you
   want it decided, it is decidable — see "what would discriminate" below.

There is one genuinely reassuring primary here, from Xu et al. (**inspected**, abstract):

> "**mixed flowing gas testing (MFG) provides a realistic accelerated test for simulating the
> creep corrosion in the laboratory without requiring condensing conditions.**"

Meaning: the mechanism runs sub-condensation, so a coating that works only when dry buys you
nothing. Coverage is the whole story.

**Practical read for the gas zone:** sprayed acrylic or urethane over the gas zone with clear
apertures is, on this evidence, close to worthless at the aperture boundary — the one place it
must work. Parylene C is the only chemistry with positive controlled evidence, it is the only
one that will actually cover an aperture edge conformally, and it is maskable (parylene houses
mask apertures routinely). Epoxy has one positive result but it is second-hand and it is not
sprayable to a clean aperture edge.

---

## 5. Nickel + ammonia — is ENIG's Ni layer a liability?

**Verdict: the nickel is not the problem you feared. The GOLD is — and it is a bigger problem
than the nickel would have been.**

### The nickel

I found no evidence that gaseous NH₃ attacks the electroless-Ni barrier layer in service.
ANSI/ISA-S71.04-1985 §6.2.7 (**inspected**) names the victims of ammonia explicitly and nickel
is not among them:

> "Reduced forms of nitrogen (ammonia, amines, ammonium ions) occur mainly in fertilizer plants,
> agricultural applications, and chemical plants. **Copper and copper alloys are particularly
> susceptible to corrosion in ammonia environments.**" — **Direct evidence.**

Nickel-ammine complexes ([Ni(NH₃)₆]²⁺) are real and do form, but the conditions in the
literature I saw are aqueous ammoniacal solutions at concentrations far above a condensate
film, or supercritical/high-temperature systems (e.g. Yang et al. 2017, *Int. J. Hydrogen
Energy*, 6000 ppm NH₄Cl at 400 °C/24 MPa — **metadata only**, ScienceDirect abstract, and
**not commensurable** with your service condition; I record it only to say I checked and
rejected it). **Bounded absence claim:** searched Google/Serper on 2026-09-04 across the axes
{ENIG + ammonia, electroless nickel + ammonia gas, nickel ammine + electronics, nickel
atmospheric corrosion}, in English, unbounded by date, following references from the Nickel
Institute and EPA HERO entries. **No evidence found within that scope** that NH₃ at compost
concentrations attacks the Ni underlayer of ENIG in service. Confidence in absence: **medium**,
limited by not having searched the nickel-plating trade literature or non-English corpora.

### The gold — the finding that matters

Oh, Kim, Jung, Park, Shon, Kwon, *Galvanic corrosion behaviors of Cu connected to Au on a
printed circuit board in ammonia solution*, **Metals and Materials International 24(1),
67–72 (2018)**, DOI **10.1007/s12540-017-7262-z**. Publisher landing page fetched and rendered
through the browser (`link.springer.com`); **abstract inspected, full text paywalled**. Numbers
quoted are from the abstract:

> "During etching treatments of printed circuit board (PCB) with ammonia solution, **galvanic
> corrosion occurs between electrically connected gold and copper** … The difference of the
> corrosion rate … of Cu connected to Au (**117 μA/cm²**) and of single Cu (**86 μA/cm²**) …
> As the stirring speed increases from 0 to 400 rpm, the corrosion rate of galvanic coupled Cu
> to Au increases from **36 to 191 μA/cm²**. Furthermore, we confirm that **an increase in the
> area ratio (Au/Cu) from 0.5 to 25 results in a higher rate of corrosion of Cu connected to
> Au. The corrosion rate … is approximately 20 times higher when the area ratio of Au to Cu is
> 25 (1360 μA/cm²) than when the ratio is 0.5 (67 μA/cm²).**"

Origin: measured (electrochemical). Transformation: direct. Status: measured rates under the
paper's stated conditions. **Direct evidence for the effect; my inference for the application.**

**Commensurability warning, stated plainly:** this is an *ammonia etching solution*, a bulk
electrolyte at process concentration, not a thin condensate film at 100 % RH. The absolute
current densities do **not** transfer to your probe. What transfers is the **scaling law**: in
an ammoniacal aqueous environment, copper coupled to gold corrodes faster than copper alone,
and the acceleration scales strongly with the Au:Cu **area ratio**.

**Your board is the bad end of that scaling.** ENIG gives you a large, continuous, gold-covered
cathode area, connected through the copper pour to a small exposed-copper anode area at each
deliberately-clear aperture edge and each routed/castellated edge. Au:Cu area ratio at those
features is plausibly ≫ 1. In an NH₃-bearing condensate, that is the 20× case, not the 1×
case.

**So the answer to your question is: yes, ENIG is an NH₃ liability — via the gold, not the
nickel — and specifically at the apertures you cannot coat.** This, and not the H₂S story, is
the strongest technical argument against ENIG on this board. It is also the strongest argument
for **covering every exposed copper edge in the gas zone**, by any means: coating, mask
pull-back geometry that keeps copper away from the aperture, or simply removing copper from
the aperture region entirely.

---

## 6. The separable gold contact

**Verdict: SURVIVES and should be escalated. Your §4.1 is directionally right; the named
mechanisms are pore corrosion, corrosion creep across the gold, and fretting, and your
service condition is beyond the worst class the connector industry defines.**

*iNEMI Connector Reliability Test Recommendations Project*, SMTAI 2016,
`https://thor.inemi.org/webdownload/2016/SMTAI/Connector_reliability.pdf`
(`%PDF-`, 1 322 716 bytes), **inspected** — Table 3, p. (text line 442):

| Class | General environmental characteristics | Degradation mechanisms | Typical application |
|---|---|---|---|
| A | Good temperature and humidity control | Dry air oxidation | Office, home |
| B | Some external T/RH variation; **condensation possible**; low-level pollutant gas | **Pore corrosion**, moderate loss of normal force, **fretting motion** | Light industrial, automotive cabin |
| **C** | T/RH poorly controlled or uncontrolled; **condensation is likely**; **moderate to high levels of particulate and pollutant gas** | **Corrosion creep**, major loss of normal force, **fretting motion** | Indoor heavy industrial, automotive under-hood, outdoor |

**Direct evidence.** Class C is the top of the scale, and it is defined for *"moderate to high"*
pollutant gas — your GX-class atmosphere is off the end of it. The mechanism the table names
for Class C is literally **"Corrosion Creep"**, on a separable contact.

Independent confirmation of the mechanism list, from a test-lab description of what
IEC 60068-2-60 exists to find (Auto Technology Company,
`https://autotechnology.com/materials-and-corrosion-testing-laboratory/iec-60068-2-60-mixed-flowing-gas-testing/`,
**inspected**, **secondary** — a commercial lab page, not a standard):

> "**Pore corrosion in gold, silver, tin, and nickel finishes driven by sulfur and chlorine
> species.** Creep corrosion on printed circuit boards — especially under high-sulfur
> conditions. … **Contact resistance instability caused by oxide growth and corrosive film
> formation. Connector fretting vulnerability under corrosive atmospheric environments.**"
> and, in the failure-mechanism list: "**Plating pore breakthrough and undercutting; sulfide
> film growth on gold and silver.**"

Element's MFG article (`https://www.element.com/resources/articles/understanding-mixed-flowing-gas-testing`,
**inspected**, **secondary**) names the same discriminators the test is designed to expose:
"**pore corrosion, edge effects, tendency for edge creep, plating coverage, plating integrity,
and 'sheltering' effect**". Note "**edge creep**" and "**sheltering**" — a sheltered, unwiped,
low-force separable interface inside a condensing cavity is the sheltering case.

The physics is well established and old: gold plating is porous; in a sulfur-bearing
atmosphere the base metal corrodes *through* the pores and the corrosion product creeps out
over the gold surface, degrading the contact from outside the pore. The foundational reference
is Krumbein, *Corrosion Through Porous Gold Plate*, IEEE Trans. Parts, Materials and Packaging
5(2), 89 (1969), `http://ui.adsabs.harvard.edu/abs/1969ITPMP...5...89K/abstract` —
**metadata only**; the ADS page returned a "Human Verification" challenge in this headless
session and I did not retry around it. Cited here for provenance of the mechanism name only;
no number in this review depends on it.

### What connector makers specify

I could not find a connector manufacturer publishing a sour-gas/sewage/agricultural
service rating for a socket of the Cambion 450-3703 class. **Bounded absence:** searched
Google/Serper 2026-09-04 across the axes {gold separable contact + H₂S; pore corrosion +
nickel underplate; connector plating + biogas/sewage/agricultural; MFG connector class}, in
English, unbounded by date, plus vendor blogs (Samtec, Advanced Plating, Tyco/Myers 2009).
No such rating was found within that scope. Confidence in absence: **low-to-medium** — I did
not query Cambion/Bel, TE, Mill-Max or Preci-Dip datasheets directly, and I did not read
Telcordia GR-1217. **This is the one attack target where the answer is "the industry answer is
'don't put a separable contact there', so nobody publishes a rating for it."**

What the industry *does* publish is the qualification route: **EIA-364-65 mixed flowing gas
for connectors**, and its severity classes (Osterman's Class IV, §4 above, is one of them).
That is a test, not a rating, and it is the right test for your socket — see §9.

**On your specific worry — a creeping sulfide film across the receptacle land toward the guard
ring — I found no source that treats it, and it is the correct worry.** It is precisely the
Class C "Corrosion Creep" mechanism plus your 1.8 MΩ leakage budget. Contact *resistance* is
indeed irrelevant (RE carries no current); **surface insulation resistance from the socket land
to the guard is the parameter, and it is not a parameter any connector datasheet reports.**

---

## 7. Condensation

**Verdict: your claim "it does not need condensation, only humidity and sulfur" SURVIVES as
literally written, but it is materially incomplete — it also needs an ionic surface film, and
once liquid water is present the mechanism changes and gains a second, faster failure mode
that your board is uniquely exposed to.**

### Non-condensing is sufficient — confirmed

Xu et al. (**inspected**, abstract): "mixed flowing gas testing (MFG) provides a realistic
accelerated test for simulating the creep corrosion in the laboratory **without requiring
condensing conditions**." iNEMI's FoS work reproduces creep corrosion at 60–82 % RH, and Phase
2 reportedly saw it on ENIG at **60 % RH** (secondary, §1). ISA §6.2.3 (**inspected**) adds
that sulfide attack "still occurs in low relative humidity environments", while "the presence
of moisture and small amounts of inorganic chlorine compounds **greatly accelerates** sulfide
corrosion".

### But "only humidity and sulfur" is not sufficient

Fu et al. 2014 (§3 above): salt contamination was **necessary**. Xu et al. Table 2: **all
eleven bare boards showed no creep corrosion** at 5 days MFG. Clean mask and clean FR-4 do not
support creep. So the correct sentence is:

> Creep corrosion needs **sulfur + an adsorbed electrolyte film + an ionic/organic surface
> contaminant**. Condensation is not required, but every factor that makes a thin adsorbed film
> thicker, more ionic and more persistent accelerates it.

### What changes when liquid water IS present

**This is inference, clearly labelled, built on the primaries above.** With a real condensate
film carrying dissolved NH₃ and H₂S you leave the domain the creep-corrosion literature
describes and enter bulk aqueous electrochemistry:

- **The film becomes a genuine bulk electrolyte.** Ammonium sulfide/bisulfide is a conducting,
  buffered, aggressive solution. The Oh 2018 galvanic result (§5) is *measured in exactly this
  kind of medium* and shows the Au/Cu couple accelerating by up to 20× on area ratio.
- **A second mechanism switches on that creep corrosion does not have: electrochemical
  migration (ECM).** ECM requires a bias between adjacent conductors and a continuous
  electrolyte; creep corrosion requires neither. The distinction is stated cleanly by Jim Hall
  (Board Talk, **secondary**): "Electro-migration dendrites require an electrical potential to
  drive the reaction … **That is not true with creep corrosion.**" Your document dismisses CAF
  because "most of the gas zone" has no voltage gradient — but the **guard ring is biased by
  construction**, and guard-to-signal is exactly the pair where 1.8 MΩ matters. Once liquid
  water bridges the guard gap, ECM is live and it is faster than creep.
- **Dissolution transport replaces surface creep.** A corrosion product that must creep across
  dry mask takes months; a dissolved species in a liquid film moves in minutes.

So: **not merely faster — a different and more dangerous failure regime.** Your document is
right that the probe fights condensation and will not always win. What it does not say is that
losing that fight is not a linear worsening; it is a mode change.

**And note the compounding with §3:** each wet/dry cycle deposits salts, and each dry period
then has a richer, lower-DRH salt film to work with. The heater does not undo the salt.

---

## 8. Prior art — what people actually do

**Verdict: your document has no prior-art section, and the honest finding is that the named
industrial practice is "keep the electronics out of the gas", which your architecture cannot
do. This is a real gap, not a place to invent generalities.**

Named, citable practices I could actually verify:

1. **USDA NRCS Conservation Practice Standard, Anaerobic Digester (Code 366)** —
   `https://www.nrcs.usda.gov/sites/default/files/2024-10/DRAFT_366_OH_CPS_Anaerobic_Digester_2024.pdf`.
   **Metadata + snippet only** (I read the search-result snippet, not the PDF): "**Protect
   electrical controls from corrosion due to exposure to biogas or locate them in a separate
   room or building away from the digester and generator**". This is a named
   agency standard prescribing *physical separation* as the primary control. **Flagged: I did
   not fetch this PDF; the quote is second-hand from a search snippet and must be verified
   before it is cited anywhere load-bearing.**

2. **ISA-71.04 §6.3.4 itself (inspected primary):** GX = "only specially designed and packaged
   equipment would be expected to survive … a matter of negotiation between user and supplier."
   There is no off-the-shelf answer at your severity; the standard says so.

3. **iNEMI's own answer for data centres (inspected primary, 2012 position statement):** do not
   harden the board — **change the environment**. Seal openings, add gas-phase filtration, hold
   RH < 60 %. Two of those three are unavailable to a buried probe; the third (RH control in a
   local volume) is what your heater is already trying to do, and it is the *right* strategy
   according to the only body that has studied this.

4. **Connector industry (inspected primary, iNEMI 2016 Table 3):** the top class, C, tops out at
   "indoor heavy industrial / automotive under-hood". There is no class above it, which is the
   industry's way of saying separable contacts are not specified for your environment.

5. **Corrosion-control filtration as a product category** (Purafil, PureAir/Bry-Air) sells
   ISA-71.04 class remediation into paper mills, waste-water plants and refineries — **secondary,
   vendor marketing**, listed only to show the standard practice is *environmental*, not
   *board-level*.

**Bounded absence claim.** Searched Google/Serper on 2026-09-04 across the axes {biogas plant +
PCB/electronics + corrosion protection; anaerobic digester + electrical controls; H₂S sensor +
conformal coating; poultry/swine barn + ammonia + sensor electronics failure; geothermal +
electronics + H₂S}, English, unbounded by date, following references from the NRCS standard and
the iNEMI corpus. **I found no published board-level hardening practice — no named coating
stack, no finish specification, no qualification protocol — for electronics deliberately placed
inside a sour, condensing, biologically active gas volume.** Confidence in absence:
**medium**. Limited by: I did not search German-language agricultural-engineering literature
(KTBL, DLG) where biogas instrumentation practice is likely to be documented, and I did not
search patents. **If you want this closed, the German biogas trade literature and the
gas-detector manufacturers' (Dräger, MSA, Honeywell BW) design notes are the corpora to hit.**

**What this means for you:** you are not doing something with a known recipe. Every commercial
answer separates the electronics from the gas. Your probe cannot, because the cell must see the
gas. That is a genuine novelty in the design and the document should say so.

---

## 9. What test would actually qualify this board

**Verdict: there is a lab-accessible answer, and your existing plan (an SIR coupon in H₂S) is
the right instinct but under-specified in three ways.**

### The candidate tests, with what I could verify

| Test | What it is | Verified conditions | Accessible? |
|---|---|---|---|
| **IEC 60068-2-60** | The international MFG benchmark; four methods (Ke1–Ke4) | Method 4 is the one commonly referenced by OEMs (Element, **secondary**). **Per-method gas tables: `unverified`** — IEC sells the standard | Contract labs: Element (Seattle), Auto Technology, iST. Cost/lead time not obtained |
| **EIA-364-65 (TP65A)** | MFG for *connectors* — the right family for your socket | **Class IV, as run by Osterman (inspected primary, Table 4): 50 ± 2 °C, 75 ± 2 % RH, H₂S 200 ± 20 ppb, Cl₂ 30 ± 5 ppb, NO₂ 200 ± 50 ppb, SO₂ 200 ± 50 ppb**, 48 h (abstract says 8 h — discrepancy noted) | Same labs |
| **ASTM B845 / B827** | US MFG guide + practice for electrical contacts; B810 is the copper/silver coupon corrosivity verification | Named by Element and Auto Technology (**secondary**) as the routinely-offered pair | Same labs |
| **iNEMI flowers-of-sulfur (FoS)** | The purpose-built creep-corrosion test, and **the only cheap one** | **Inspected primary (Fu 2014, Singh 2018): 300 mm acrylic cube in an oven, bed of sulfur, saturated-salt RH control, paddle wheel at 20 rpm or forced air at 1 m/s, 50–60 °C, 5-day runs** | **Buildable in-house.** This is the one that fits a 3-prototype project |
| **ANSI/ISA-71.04 reactivity coupons** | Copper + silver coupons, 30-day exposure, corrosion-film thickness | Inspected primary, §6.3 + Appendix C | Cheap; commercial coupon services exist |

### The MFG concentrations in context (inspected primary — Fu et al. 2014, Table 1)

| Organization | T (°C) | RH (%) | H₂S (ppb) | Cl₂ | NO₂ | SO₂ | Cu rate (nm/day) |
|---|---|---|---|---|---|---|---|
| Battelle Columbus (Abbott 1988) | 50 ± 2 | 75 ± 2 | **200** | 50 ± 5 | 200 ± 25 | — | — |
| Rockwell Automation (Veale 2005) | 28.5 ± 0.5 | 75 | **100** | 20 | 200 | 200 | 350 |
| Alcatel-Lucent (Xu 2009) | 40 | 69 | **1700** | 20 | 200 | 200 | 600 |
| Univ. of Maryland (Zhang 2010) | 32 ± 1 | 75 ± 1 | **1050 ± 50** | — | — | — | — |
| iNEMI (Fu 2011/2012) | 40 | 70–75 | **1200** | 20 | 200 | 200 | 500 |

**This is the number that should recalibrate the document.** The most aggressive published
accelerated MFG condition is **1.7 ppm H₂S**. Your modest field figure is **35 ppm — 20× the
most aggressive accelerated test**, and your disturbance peaks are **1200× it**. You are not
"three orders above the field failures"; you are **more than an order of magnitude above the
laboratory acceleration used to produce those failures in days**.

### The three fixes to your existing SIR-coupon plan

1. **The atmosphere is not enough — the surface matters more.** Per Fu et al. 2014, a clean
   coupon in an H₂S atmosphere may pass and prove nothing, exactly as a clean-air soak would.
   The coupon must carry **the real assembly's flux residue and, ideally, deposited ammonium
   salts** ((NH₄)₂SO₄ / NH₄HSO₄ / NH₄NO₃, per iNEMI's recipe). A coupon that is cleaner than
   your board is a coupon that cannot fail.
2. **Measure the right pair at the right bias.** The failure is guard-to-CELL_RE leakage at
   ~600 mV, and the acceptance threshold is **> 1.8 MΩ** by your own arithmetic (600 mV / 335 nA
   = 1.79 MΩ; recomputed — **calculated**, inputs from `PLAN.md`). That is a *very* loose
   threshold by SIR standards, which is good news: the binding constraint is not sensitivity,
   it is **running the test on the real geometry, with the socket fitted, with the real flux
   residue, in the right atmosphere**. Log resistance continuously through the soak, not just
   before and after — creep corrosion produces a step, and a spot check can miss it and miss
   the recovery too.
3. **Add temperature cycling before the gas exposure.** Osterman's sequence (100 cycles ×3
   profiles, *then* MFG) exists because thermal cycling cracks and thins coatings, and his
   conclusion explicitly flags it: "Temperature cycling may play a role in the degradation of
   coatings … and increasing their susceptibility to corrosion." Your probe cycles daily with
   the heater. A coating qualified without cycling is qualified for a probe you do not have.

**Recommended qualification for 3 prototypes, cheapest first:**
(a) Build the iNEMI FoS chamber — a 300 mm box, sulfur bed, saturated-salt RH control, an oven
at 60 °C. Both primaries give enough construction detail to replicate. Run 5 days at ≥ 80 % RH
with salted, flux-residue-bearing coupons of your actual gas-zone artwork, socket fitted, guard
biased, resistance logged.
(b) In parallel, expose ISA-71.04 copper and silver coupons **in the actual pile at depth for
30 days**. This is the single highest-value measurement available to you: it converts your
unbounded "no pore-gas profile exists" gap into a *number on the axis the whole industry uses*,
for the price of two coupons and an analysis. It also directly closes open item 7 in your
document, which currently has no plan at all.
(c) Only if (a) or (b) is marginal, buy one EIA-364-65 Class IV run at a contract lab with the
socket fitted.

---

## RECOMMENDATIONS

Ordered by expected risk reduction per unit of effort. Each is tied to the evidence above.

1. **Bury ISA-71.04 copper + silver coupons at probe depth in the pile for 30 days, this
   season.** [ISA-S71.04-1985 §6.3 + Appendix C, inspected; iNEMI 2012, inspected: "corrosion is
   too complex a process to allow its rate to be determined from gaseous chemical composition"]
   This is the only measurement that puts your actual service environment on the axis the
   entire literature uses, it closes the pore-gas data gap without new research, and it costs
   almost nothing. **Do this before any other corrosion decision.**

2. **Specify rosin (RO) flux only, everywhere in the gas zone, and clean after the J5 hand
   solder.** [Xu et al., inspected, Table 2: bad/marginal/good = 25/9/7 for organic-acid flux vs
   0/2/16 for rosin vs 0/0/11 for bare board; "no creep corrosion was observed" even at 20 days
   MFG with RO flux] **This is the largest single effect in the entire body of evidence — larger
   than any finish choice.** Your hand-soldered J5 ring with uncontrolled flux is currently the
   worst-controlled surface on the board and it sits 12 mm from CELL_RE. Ban OR/water-soluble
   flux in the fab notes and the assembly instruction, and add the clean-and-coat step your
   document's open item 4 already identifies.

3. **Change the gas-zone coating to parylene C with masked apertures.** [Osterman, inspected,
   Conclusions: only parylene resisted; acrylic/silicone/urethane had "little to no coating
   material" on lead edges; "focus on terminal coverage and not rely solely on coating
   thickness on a flat surface"] A sprayed acrylic or urethane will thin or pull back at exactly
   the aperture boundary where it must work. Parylene houses mask apertures as routine work.
   If parylene is impossible, a double coat of urethane-acrylate is the only fallback with any
   positive evidence, and that evidence is second-hand (Hindin 2003).

4. **Eliminate exposed copper from the gas zone by geometry, not by coating.** [Oh et al. 2018,
   abstract inspected: Cu-to-Au corrosion rate rises from 67 to 1360 μA/cm² as Au:Cu area ratio
   goes 0.5 → 25 in ammonia solution] Your ENIG board presents a large gold cathode to whatever
   small copper anode is left at an aperture edge, castellation or routed edge — the 20× case.
   Pull copper back from every aperture, avoid castellations in the gas zone, and keep any
   remaining exposed copper as far as possible from the guard ring and CELL_RE. **This is the
   change that most directly attacks the 1.8 MΩ failure.**

5. **Correct §3 of `CONTACT-CORROSION.md`.** [Singh et al. 2018, inspected: "ENIG finished PCBs
   are very prone to creep corrosion … OSP finished PCBs are very resistant"] Keep ENIG — for
   coplanarity, for the socket land, and because RoHS removes the SnPb-HASL option — but delete
   the claim that it is the most creep-resistant finish, and delete "do not let it be
   value-engineered to OSP". Replace the fab-note rationale with: *ENIG is specified for
   coplanarity and socket-land quality, not corrosion resistance; ImAg is prohibited; the
   corrosion controls are flux chemistry, cleaning and coating coverage.*

6. **Rewrite §2.5's conclusion from "concentration" to "surface state".** [Fu et al. 2014,
   inspected, Conclusions: "The presence of salt contamination … was found to be necessary for
   creep corrosion"] The four salts iNEMI had to deposit to make creep corrosion happen —
   (NH₄)₂SO₄, NH₄HSO₄, NH₄NO₃, NaCl — are what NH₃ + H₂S + oxidant + condensate produce in your
   cavity. The document currently treats the ppm figures as the risk; the ppm figures are the
   *source term*, and the risk is the salt film they leave behind, which does not decay between
   episodes.

7. **Add NH₃ to the document as a co-equal driver, at GX severity.** [ISA-S71.04-1985 Table 3,
   inspected: NH₃ GX ≥ 25 000 ppb; `COMPOST-METROLOGY.md` line 365: "> 700 ppm exhaust maxima"]
   Your NH₃ exposure is ~28× the ISA severe threshold, ammonia is the named copper attacker in
   the standard, and §5 shows it activates the Au/Cu galvanic couple. It currently gets one
   table row.

8. **Re-scope the SIR coupon per §9:** real geometry, socket fitted, real flux residue,
   deliberately salted, temperature-cycled first, guard biased, resistance logged continuously,
   pass threshold > 1.8 MΩ. Build the iNEMI FoS chamber rather than buying MFG time.

9. **State the prior-art gap explicitly in the document.** [NRCS CPS 366, second-hand; ISA
   §6.3.4, inspected] Every named industrial practice separates the electronics from the sour
   gas. This probe deliberately does not. That is a design novelty and it should be written
   down as one, with the German biogas trade literature named as the unsearched corpus that
   might contain a counter-example.

### What would discriminate the open questions

- **Is the coating edge worse than bare?** Decidable with one FoS run: three coupon variants —
  fully coated, fully bare, and coated-with-aperture — same artwork, same flux residue, same
  salt loading, resistance logged. If the aperture coupon fails before the bare coupon, the
  edge is an active site and the aperture geometry must change. **This experiment does not
  exist in the literature I searched and it is cheap.**
- **Is the pile's H₂S actually a threat at depth?** The 30-day buried ISA coupon (rec. 1). A
  copper reactivity below 1000 Å/month would put you in G2 and change the entire risk posture;
  above 2000 Å/month confirms GX and justifies parylene plus geometry changes unconditionally.
- **Is the feedstock sulfur-bearing?** Still a question for Steingrubenhof, exactly as your
  document says. Nothing in the literature answers it.

---

## SURVIVED

Claims of yours that held up under attack:

- **The ppb figures for documented creep-corrosion environments.** G2 < 10 ppb, G3 < 50 ppb
  H₂S — verified verbatim against the primary standard. ✔
- **The "3–5 orders of magnitude" arithmetic.** Recomputed independently: 3.5 orders for
  35 ppm vs G2, 5.3 orders for 2083 ppm vs G2. ✔
- **"GX starts far below."** GX starts at 50 ppb; your exposure is 700–41 660× that. ✔ (But
  "ISA-71.04 has no class for it" is wrong — GX is open-ended and *is* the class.)
- **"Creep corrosion does not need condensation."** Verified — Xu et al. state MFG reproduces
  it "without requiring condensing conditions", and iNEMI reproduce it at 60–82 % RH. ✔
  (Incomplete: it *does* need an ionic surface film.)
- **"The failure that matters is leakage, not joint loss."** Fully supported. iNEMI 2012:
  "the extent of creep corrosion may be so high as to electrically short circuit-adjacent pads
  and traces"; the 2018 round robin measures the failure as leakage resistance, in kΩ, exactly
  as you framed it. ✔
- **"The solder itself is not the weak link."** No source contradicts this; the entire
  literature frames the failure as a surface film bridging *between* features. ✔
- **§4.1 — the separable socket is the worst exposure.** Confirmed and escalated: iNEMI's
  connector Class C names "Corrosion Creep" as the mechanism for a condensing, high-pollutant
  environment, and Class C is the top of the scale. ✔
- **§4.2 — the J5 hand joint is a serious hazard.** Confirmed and *promoted to the top of the
  risk list*: flux residue is the dominant variable in the whole corpus, and J5 is your only
  uncontrolled-flux joint. ✔
- **"The SIR coupon must be run in an H₂S atmosphere; a clean-air soak proves nothing."** ✔ —
  and strengthened: a *clean* coupon in an H₂S atmosphere also proves nothing.
- **"The apertures are the initiation site."** ✔ — and §5 gives it a much sharper mechanism
  (Au:Cu area ratio) than the document has.
- **"The exposure coincides with the measurement"** and **"H₂S partitions into condensate."**
  Both hold; the second is stronger than written, since the condensate is the necessary
  condition, not merely a concentrator. ✔

**Claims that FAILED:**

- **§3: "ENIG is the most creep-corrosion-resistant of the common finishes."** Contradicted by
  the primary iNEMI/IBM round robin. ✘
- **"The gold-over-nickel stack leaves far less exposed copper at the pad edge than immersion
  silver or OSP"** — unsupported, and OSP tested *better* than ENIG. ✘
- **"Do not let it be value-engineered to … OSP"** — backwards on the creep-corrosion evidence.
  ✘ (The ImAg half stands.)
- **The implicit monotonic concentration→damage model in §2.5.** Contradicted by iNEMI's
  position statement and by two saturation observations. ✘
- **§2's mechanism table, "it does not need condensation, only humidity and sulfur"** — true as
  far as it goes, incomplete in the way that matters: it also needs ionic contamination. ✘
  (partial)
- **§5's dismissal of a voltage-driven mechanism** ("CAF needs a voltage gradient … that most of
  the gas zone does not have") — the guard ring is biased, and once a condensate film bridges
  guard-to-signal, ECM is live. ✘ (partial)

---

## SOURCES

### Source access log

| # | Identifier (untruncated) | Evidence state | Attempt history | Route | Validation | Load-bearing |
|---|---|---|---|---|---|---|
| S1 | `https://webdelprofesor.ula.ve/ingenieria/oscaror/CursosDictados/web%20instrumentacion%20industrial/3%20desarrollo%20de%20proyectos/normas%20ISA/STANDARD/S_7104.PDF` — ANSI/ISA-S71.04-**1985**. No DOI found (standards document; ISA does not assign DOIs). | **inspected** (§§3.4, 3.5, 6.2.3, 6.2.7, 6.3.1–6.3.4, Table 3 p. 14, Appendix B) | curl + Chrome UA, first attempt, HTTP 200, `%PDF-1.2`, 153 532 B | raw text (pdftotext -layout, clean text layer) | validated (table structure, page numbers and section numbering coherent; footnotes align with body §6.3) | **yes** |
| S2 | `https://thor.inemi.org/webdownload/2018/Creep_Corrosion_APEX_Feb_2018.pdf` — Singh, Palmer, Fu, Lee, Lee, Guo, Li, Lee, Tong, Xu, *Round Robin Evaluation of iNEMI Creep Corrosion Qualification Test*, IPC APEX Expo, Feb 2018. No DOI found (conference presentation; searched by title + venue). | **inspected** (full deck) | curl + Chrome UA, first attempt, HTTP 200, `%PDF-`, 615 292 B | raw text | validated (leakage tables and conclusion slide internally consistent) | **yes** |
| S3 | `https://thor.inemi.org/webdownload/2014/APEX/Creep_Corrosion_Paper.pdf` — Fu, Singh, Campbell, Zhang, Ables, Lee, Lee, Li, Zhang, Lee, *Testing Printed Circuit Boards for Creep Corrosion in Flowers of Sulfur Chamber*, IPC APEX Expo 2014. No DOI found. | **inspected** (abstract, §1, MFG conditions Table 1, dust/DRH sections, Results, Conclusions, reference list) | curl + Chrome UA, first attempt, HTTP 200, `%PDF-`, 585 982 B | raw text | validated | **yes** |
| S4 | `https://thor.inemi.org/webdownload/projects/ba/Creep_Corrosion/iNEMI_Position_Paper_Creep_Corrosion_042012.pdf` — *iNEMI Position Statement…*, 20 April 2012. No DOI found. | **inspected** (both pages) | curl + Chrome UA, first attempt, HTTP 200, `%PDF-`, 594 778 B | raw text | validated | **yes** |
| S5 | `https://www.electronics.org/system/files/technical_resource/E8%26S28_02.pdf` — Xu, Smetana, Franey, Guerra, Fleming, Reents, Willie, Garcia, Encinas, Jiang, *Creep Corrosion of PWB Final Finishes: Its Cause and Prevention*. No DOI found. | **inspected** (abstract, §1, §3.1.1–3.1.4, Table 2) | earlier composed URL `circuitinsight.com/pdf/second_round_robin_…` returned a 65 066 B HTML shell (site serves the same shell for any `/pdf/` path — a wrong-URL provenance failure, not a block); recovered the real URL by search; curl + Chrome UA, HTTP 200, `%PDF-`, 1 579 737 B | raw text | validated | **yes** |
| S6 | `https://www.smtnet.com/library/files/upload/effectiveness-conformal-coat.pdf` — Osterman (CALCE), *Effectiveness of Conformal Coat to Prevent Corrosion of Nickel-palladium-gold-finished Terminals*, IPC APEX Expo. No DOI found. | **inspected** (abstract, Experiments, Tables 1–4, Conclusions, references) | earlier composed URL `smtnet.com/library/files/upload/second-round-robin-creep-corrosion.pdf` → genuine 404; recovered real URL by search; curl + Chrome UA, HTTP 200, `%PDF-`, 760 103 B | raw text | validated (internal 8 h vs 48 h MFG-duration discrepancy noted in §4 — a source inconsistency, not an extraction artifact) | **yes** |
| S7 | `https://thor.inemi.org/webdownload/2016/SMTAI/Connector_reliability.pdf` — *iNEMI Connector Reliability Test Recommendations Project*, SMTAI 2016. No DOI found. | **partial** — Tables 3 and 4 and surrounding text only | curl + Chrome UA, first attempt, HTTP 200, `%PDF-`, 1 322 716 B | raw text | validated | **yes** |
| S8 | `https://link.springer.com/article/10.1007/s12540-017-7262-z` — Oh, Kim, Jung, Park, Shon, Kwon, *Galvanic corrosion behaviors of Cu connected to Au on a printed circuit board in ammonia solution*, Metals and Materials International **24**(1), 67–72 (2018). DOI **10.1007/s12540-017-7262-z** | **metadata only** (abstract; full text paywalled — publisher paywall, not circumvented) | Playwright + Chrome UA, first attempt, rendered landing page | raw text (DOM) | validated (self-validating DOM) | **yes** |
| S9 | `https://www.circuitnet.com/board-talk/55998.html` — Zarrow & Hall (ITM Consulting), *Does HASL or ENIG Reduce Creep Corrosion in Corrosive Environments?* | **inspected** (full transcript) | Playwright + Chrome UA, first attempt | raw text (DOM) | validated | no (used as expert opinion only) |
| S10 | `https://www.circuitnet.com/programs/56361.html` — Shah (LILOTREE), Lee & Lee (iST), *Surface Finish Can Achieve Robustness Against Copper Creep Corrosion*, SMTA Proceedings | **partial** — summary + conclusions on the page; the underlying SMTA paper (with the ENIG/ImmSn/HASL/OSP comparison data I wanted) was **not** obtained | Playwright + Chrome UA, first attempt; the "DOWNLOAD" link leads to a gated form, not followed | raw text (DOM) | validated | no |
| S11 | `https://autotechnology.com/materials-and-corrosion-testing-laboratory/iec-60068-2-60-mixed-flowing-gas-testing/` | **inspected** (full page) | Playwright + Chrome UA, first attempt, `<title>` "Mixed Flowing Gas Testing \| Auto Technology Company" | raw text (DOM) | validated | no (commercial lab page; mechanism list only) |
| S12 | `https://www.element.com/resources/articles/understanding-mixed-flowing-gas-testing` — Tait, Element | **inspected** (full article) | Playwright + Chrome UA, first attempt | raw text (DOM) | validated | no |
| S13 | `https://www.inemi.org/creep-corrosion` | **de-scoped** — URL composed from a guessed path; site returned a rendered 404. No claim depends on it; it exists in this log only as the browser-control proof. | Playwright + Chrome UA, HTTP 404 rendered, `<title>` "iMIS" | raw text (DOM) | validated (as a 404) | no |
| S14 | `http://ui.adsabs.harvard.edu/abs/1969ITPMP...5...89K/abstract` — Krumbein, *Corrosion Through Porous Gold Plate*, IEEE Trans. PMP **5**(2), 89 (1969). Identifier unverified — DOI lookup not run. | **inaccessible** | Playwright + Chrome UA → rendered "Human Verification" challenge in a headless, non-handoff-capable session. Per the challenge rule: stopped requests from that session, did **not** open a replacement session or change identity to retry. No further rung is permitted against a CAPTCHA. | route: none | n/a | no — cited for mechanism provenance only; no number depends on it |
| S15 | `https://www.researchgate.net/publication/398212387_Testing_Printed_Circuit_Boards_for_Creep_Corrosion_in_Flowers_of_Sulfur_Chamber_Phase_2` — Fu, Singh et al., Phase 2 | **second-hand** (via the search-result description of the ResearchGate page; the page itself not fetched) | not fetched — de-prioritised once S2 and S3 gave the same conclusion from inspected primaries | route: none | n/a | no — explicitly marked as a lead in §1 |
| S16 | Schueller, *Creep Corrosion on Lead-Free Printed Circuit Boards in High Sulfur Environments*, SMTA International 2007, pp. 643–654 (also J. Surface Mount Technology, 2008). Identifier unverified — no DOI found by title+venue search. | **second-hand** (search-snippet summary of a ResearchGate page) | not fetched — ResearchGate full text is gated | route: none | n/a | no — flagged in §1 as *not* evidence |
| S17 | `https://www.nrcs.usda.gov/sites/default/files/2024-10/DRAFT_366_OH_CPS_Anaerobic_Digester_2024.pdf` — USDA NRCS Conservation Practice Standard 366 (Ohio draft, 2024) | **second-hand** (search-result snippet only) | not fetched | route: none | n/a | no — flagged in §8 as requiring verification before load-bearing use |
| S18 | `https://www.sciencedirect.com/science/article/abs/pii/S0360319917319444` — Yang et al. 2017, *Int. J. Hydrogen Energy* | **metadata only** (search-result abstract) | not fetched — rejected on commensurability before retrieval (400 °C / 24 MPa supercritical water) | route: none | n/a | no |
| S19 | `/Users/fab/dev/ha/farming/compostlab/research/COMPOST-METROLOGY.md` (line 365) and `research/COMPOST-GAS.md` — project's own inspected-source documents | **inspected** (grep-located lines) | local filesystem | raw text | validated | **yes** (the > 700 ppm NH₃ figure in §2) |
| S20 | `/Users/fab/dev/ha/farming/compostlab/o2-probe/CONTACT-CORROSION.md` — the review target | **inspected** (full) | local filesystem | raw text | validated | **yes** |

**Non-clean rows to note explicitly:** S14 (`inaccessible` — CAPTCHA, no claim depends on it),
S15/S16/S17 (`second-hand`, all three flagged in the body as leads requiring verification),
S8 (`metadata only` — paywalled full text, abstract numbers quoted verbatim), S10 (`partial` —
the finish-comparison data behind that summary was not obtained), S18 (`metadata only`,
rejected on commensurability).

### Challenge searches run (§2.1)

| Conclusion cluster | Refutation query | Result |
|---|---|---|
| ENIG is *not* creep-resistant | `ENIG resistant to creep corrosion field failures immersion silver worst finish ranking contradictory evidence sulfur` | Returned a wall of **PCB-vendor marketing** asserting ENIG's corrosion resistance (hemeixinpcb, pcbcart, allpcb, ltcircuit, pcbsync — all secondary, uncited, and all discussing shelf-life oxidation). **No peer-reviewed or industry-consortium source was found supporting ENIG as creep-resistant.** The conflict is real and is exposed in §1 rather than resolved silently. |
| HASL is better at the pad edge | same query + `creep corrosion HASL lead-free solder surface finish resistant "no creep corrosion" comparison ENIG OSP immersion tin study` | Found the Xu et al. primary (supports) and the Board Talk transcript (supports, hedged). Found no source claiming HASL is *worse*. |
| Ni is not the NH₃ liability | `nickel corrosion resistance ammonia gas atmosphere ammoniacal solution nickel dissolution oxygen Ni(NH3)6 electronics plating` | No evidence of service-condition NH₃ attack on ENIG's Ni found; the search instead surfaced the Au/Cu galvanic result that redirected the finding. Recorded as a bounded absence in §5. |
| No board-level prior art exists for sour condensing service | `electronics protection biogas plant anaerobic digester H2S sensor PCB conformal coating potting practice corrosion gas detector` + `ammonia corrosion electronics poultry swine barn sensor PCB failure` | Only *environmental*/separation practices found. Recorded as a bounded absence in §8 with the unsearched corpora named. |

### Source independence (§2.2)

S2, S3, S4 and S15 are **one programme** — the iNEMI creep-corrosion project, sharing authors
(Singh, Fu, Lee, Lee), one chamber design, and overlapping specimen lots. Their agreement is
**not** independent corroboration. S5 (Alcatel-Lucent / Flextronics / Sanmina) is genuinely
independent of them in authorship, method (MFG rather than FoS) and specimens, and Chen Xu
appears on both S2 and S5 — a partial author overlap, recorded rather than used to discount.
S6 (CALCE) is independent of both. S8 (KAIST/Korean) is independent of all of them and uses a
different method entirely (electrochemical, aqueous). **The ENIG finding rests on S2 alone
among primaries** — S5 and S9 support the *HASL* half, not the ENIG-vs-OSP ranking. That is the
weakest link in this review and it is worth saying so: one round robin, three sites, one
chamber design. It is nevertheless the only quantitative primary evidence in either direction,
and it is not contradicted by anything I could find that is not vendor marketing.

### Archive

**`archive unavailable`** — no user-authorized literature archive location was identified for
this repository. The seven PDFs (S1–S7) currently live in this session's scratchpad at
`/private/tmp/claude-503/-Users-fab-dev-ha-farming/195e841b-9cae-4ac1-b2e1-9716f29c3712/scratchpad`
and will not survive the session. All are freely downloadable from the stable URLs above.
**If you want them retained, the `compostlab-literature` repo is the obvious home and they
should be filed there with hashes** — the four `thor.inemi.org` documents in particular are the
evidentiary backbone of this review and are hosted on a single consortium server.

---

## EVIDENCE ARCHIVE (added 2026-09-04 by the reviewing session, not the research agent)

The research agent fetched its primaries into a **session scratchpad**, which is
ephemeral. They have been copied to a durable staging directory so the evidence
chain survives this session:

    compostlab-literature/_staging-corrosion-2026-09-04/

SHA-256 sums are in `SHA256SUMS.txt` beside them. The load-bearing file is
`inemi2018.pdf` (`dd4cf82d…`, 615 292 bytes) — Singh, Palmer, Fu et al., *Round
Robin Evaluation of iNEMI Creep Corrosion Qualification Test*, IPC APEX 2018,
retrieved from `thor.inemi.org/webdownload/2018/Creep_Corrosion_APEX_Feb_2018.pdf`.

**These are NOT yet archived properly.** `compostlab-literature` stores PDFs via
Git LFS with a per-directory `INDEX.md` carrying full citations, and its working
tree currently also holds another session's untracked Cambion datasheets. Filing
these correctly — descriptive dated filenames, LFS, INDEX entries, root
`SHA256SUMS` — is a separate task in that repository and has not been done.

## RE-VERIFICATION BY THE REVIEWING SESSION

The headline finding was independently re-fetched and checked against the primary
rather than taken from the agent's summary. Two corrections to how it was
reported:

1. **The finding is STRONGER than the agent's "rests on one round robin" caveat.**
   The conclusions slide reads "The test results in general agree with **the
   industry position** that…" — this is a round robin *corroborating an existing
   consensus*, not a standalone result.
2. **The agent's "flux, not finish, dominates — by a mile" overstates its own
   evidence.** That conclusion comes from Xu et al. In the iNEMI round robin's own
   leakage tables, ENIG leaked on **both** flux types — ENIG/RO (rosin) rows still
   read 280 / 260 / 520 / 320 kΩ. Rosin did not rescue ENIG there. Two primaries,
   two different dominant variables, never run against each other. Treat both as
   live; see `CONTACT-CORROSION.md` §3.

Also confirmed from the same tables and not in the agent's summary: **ImAg leaked
too** (24 / 53 / 384 / 580 / 702 kΩ), so the original document's "ImAg is the
notorious one" survives; only the ENIG half was wrong. And the chamber runs were
at **31–78 % RH and 50 °C** — milder than this probe's ~100 % RH at up to 75 °C.
