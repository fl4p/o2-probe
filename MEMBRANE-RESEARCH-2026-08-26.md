# O₂ probe gas window — second research pass

Research date: 2026-08-26. Companion to [MEMBRANE.md](MEMBRANE.md) (Rev-A = Porex PMV15T).
Scope: extend, challenge and where possible close the open questions in MEMBRANE.md's
"Procurement questions" and "Evidence limitations" sections, and the questions sent to Porex
in `PMV15T-REPLY-2026-08-26.txt`. This pass deliberately does not re-derive material already
established in MEMBRANE.md.

**Headline: three of the five questions still open with Porex are now answered from public
vendor data, one of them against the current design.**

---

## 1. Findings

### F1 — The Grade-8 oleophobic treatment costs no published airflow or water-entry pressure

`PMV15` (untreated) and `PMV15T` (oleophobic Grade 8) publish **identical** values:
WEP min 265 / typ 370 mbar; airflow min 45 / typ 75 l·h⁻¹·cm⁻² at Δp 70 mbar; thickness
0.18 ± 0.03 mm; IP 64/67; filtration efficiency 0.4 µm (IEST RP-CC007.2). The only published
differences are that PMV15T lists `OLEOPHOBIC GRADE: 8` and omits the UL row, and PMV15 lists
`UL RATING: V–0, f2` and omits the oleophobic row.

- Evidence: **direct**, [S1] and [S2], "Measurements" block of each product page. Inspected.
- Tags: origin **vendor specification**; transformation **direct**; status **min** and
  **typical** as labelled (the portfolio table [S3] labels its column "Typical").

**Inference, not direct evidence:** identical numbers are equally consistent with Porex simply
reusing the base-material specification for the treated grade. Do not treat this as a measured
statement that the treatment is transport-neutral. It does, however, remove "the oleophobic
treatment will cost me conductance" as a reason to prefer an untreated grade *on paper*.

### F2 — A second, independent manufacturer publishes the same pattern

Nitto's automotive TEMISH table [S4] pairs oleophobic and non-oleophobic grades at matched
performance points:

| Item | Feature | Air permeability [cm³/min] | WEP [kPa] |
|---|---|---:|---:|
| C2-NTF1026-L01 | high water resistance | 50 | 100 |
| **C2-NTF210SL** | **oleophobic** / high water resistance | **50** | **100** |
| C2-NTF9208-L01 | high air permeability | 1500 | 20 |
| **C2-NTF220SL** | **oleophobic** / high air permeability | **1500** | **20** |
| E3-NTF111SL | high water resistance | 23 | 100 |
| **E3-NTF211SL** | **oleophobic** | **20** | **100** |

Two of the three pairs are identical; the third shows the oleophobic grade about 13 % lower
(20 vs 23 cm³/min).

- Evidence: **direct**, [S4], product tables on the Nitto EU automotive TEMISH page. Inspected.
- Tags: origin **vendor specification**; transformation **direct**; status **typical**.
- **Independence:** Nitto and Porex are unrelated manufacturers, so this is genuine
  corroboration under MEMBRANE.md's own §2.2-style test, not a second copy of one claim.
- **Commensurability warning:** Nitto's `cm³/min` is quoted without the area and Δp basis, so it
  is **not** convertible to Porex's `l·h⁻¹·cm⁻² @ 70 mbar`. Compare Nitto to Nitto only. The
  100 kPa (= 1000 mbar) WEP of C2-NTF210SL is *not* directly comparable to PMV15T's 370 mbar
  without the matching test method.

### F3 — Porex has an oleophobic "PMA" line that MEMBRANE.md does not list

The portfolio page [S3] carries a second table:

| Item | WEP typ mbar | Typ airflow l·h⁻¹·cm⁻² @70 mbar | Filt. eff. | Thickness mm | Max op °C |
|---|---:|---:|---:|---:|---:|
| PMA10 | 370 | 75 | 0.4 µ | 0.18 | 260 |
| PMA15 | 520 | 25 | 0.1 µ | 0.25 | 260 |
| PMA20 | 1050 | 7 | 0.1 µ | 0.19 | 260 |

**PMA10 is numerically identical to PMV15T** on every published axis. PMA15 is identical to
PMV20 and PMA20 to PMV27. The PMA line therefore reads as the oleophobic mapping of the PMV
line.

- Evidence: **direct**, [S3], second product table. Inspected.
- **Inference:** PMV15T and PMA10 are the same or near-same material under two designations.
  This is a procurement question worth adding to the Porex thread — if PMA10 is the current
  orderable designation, asking for "PMV15T" may be routed to a legacy code or refused.

### F4 — Porex Virtek is *sintered*, is a depth filter, and needs **no support backing**

The technology table on the same page [S3]:

| Range | Pore size µm | Airflow min l·h⁻¹·cm⁻² | WEP min mbar | Thickness mm | Filter type | Supporting material |
|---|---|---|---|---|---|---|
| Porex **Virtek®** PTFE **Sintered** Hydrophobic | 0.22–50 | 0.25–70 | 10–800 | 0.1–3.0 | Depth | **No support required** |
| Porex **Virtek®** PTFE **Sintered Oleophobic** | 0.22–50 | 0.25–70 | 10–800 | 0.1–3.0 | Depth | **No support required** |
| Porex **Expanded** PTFE Hydrophobic (no Virtek mark) | 0.1–50 | 12–312 | 50–5000 | 0.14–0.22 | Surface | **PP/PET lamination** |

The 2019 electrochemical-gas-sensor brochure [S5] states the same thing in prose:
"POREX Virtek microporous PTFE membrane is manufactured via a **proprietary sintering process**",
"POREX Virtek diffusion rate **does not change when handled** as it does with ePTFE products",
and it "**does not require scrim support** that could absorb or desorb (release) gases, thereby
causing slower or false readings."

- Evidence: **direct** for both quotations, [S3] technology table and [S5] p. 3. Inspected.
- **Inference (strong, with a stated conflict):** PMV15T is branded `POREX Virtek®` in its own
  page title [S1], and the Virtek® trademark attaches in the table **only** to the two sintered
  rows. PMV15T is therefore **sintered, a depth filter, and needs no support layer.**
- **Conflict to resolve:** the prose *on the same page* [S3] says Virtek materials "include
  expanded or sintered engineered manufacturing options", which contradicts the table's
  trademark usage. PMV15T's 0.18 mm thickness falls inside **both** family ranges, so thickness
  does not discriminate. Keep this question in the Porex thread.

**This finding works against the current design.** MEMBRANE.md's carrier design rule —
"Use a smooth polypropylene support or carrier on the exposed side", citing Porex's
*ePTFE backing guide* — is imported from the **expanded** family, the one row in the table that
requires PP/PET lamination. If PMV15T is sintered Virtek, a PP support backing is not required,
and adding one:

- costs free area (the model config already deducts "PP support-grid obstruction" to reach
  `free_membrane_area_mm2 = 193.05` from a 200 mm² gross), and
- adds a series diffusion resistance,

both against the parameter your own letter calls the most critical. The PP support is currently
a self-inflicted conductance penalty justified by a guide for a different material family.

### F5 — Temperature headroom is large, and PMV10L is the outlier

PMV15T max operating temperature **260 °C** [S3], against a probe maximum near 58 °C. By
contrast **PMV10L is rated 100 °C** — because it is the grade with the integrated polyolefin
mesh backing. MEMBRANE.md lists PMV10L as the intended hydrophobic control; it is the one
member of the shortlist whose thermal margin is materially reduced, and the reason is exactly
the backing discussed in F4. All listed grades show salt fog "No penetration".

- Evidence: **direct**, [S3] hydrophobic table. Inspected. Tags: vendor spec, direct, typical/limit.

### F6 — Airflow specifications *cannot* be converted to diffusive conductance. This is provable, not just cautious.

Your letter asks Porex for concentration-diffusion data "since pressure-flow figures cannot be
converted to our response time". That instinct is correct, and the reason is structural rather
than a data gap Porex could fill from its standard tests:

Pressure-driven flow through a porous membrane depends on the group **ε·r²/τ** (Darcy /
Hagen–Poiseuille bundle). Diffusive conductance depends on **ε/τ alone**
(`D_eff = D · ε/τ`, `G = D_eff/L`). One measurement, two unknowns. **No airflow number
determines a diffusion resistance without independent pore-structure data.**

Worked check on PMV15T (calculated by me; formula and inputs below; recomputed once):

- Airflow typ 75 l·h⁻¹·cm⁻² @ Δp 70 mbar → superficial velocity
  `v = 75000 cm³ / 3600 s / cm² = 20.83 cm·s⁻¹ = 0.2083 m·s⁻¹`
- `B₀ = v·μ·L/Δp` with μ = 1.85e-5 Pa·s (air, 25 °C), L = 1.8e-4 m, Δp = 7000 Pa
  → `B₀ = 0.2083 × 1.85e-5 × 1.8e-4 / 7000 = 9.9e-14 m²`
- Poiseuille bundle `B₀ = ε r²/(8τ)`; solving at ε/τ = 0.49 gives **r ≈ 1.3 µm**
  (hydraulic pore diameter ≈ 2.5 µm)

Two consequences:

1. The effective hydraulic pore diameter is roughly **6× larger** than the 0.4 µm filtration
   rating. This is direct quantitative support for MEMBRANE.md's existing warning that
   filtration efficiency is not a pore-size claim, and it is consistent with Porex classifying
   the material as a **depth** filter (F4) that captures 0.4 µm particles by interception along
   a tortuous path rather than by sieving.
2. At that pore size the Knudsen number is `Kn = 68 nm / 2.5 µm ≈ 0.03`, i.e. essentially
   continuum flow, so the Darcy treatment is self-consistent at leading order.

- Tags: origin **calculated**; transformation **calculated** from [S1]/[S3] vendor values plus
  standard air viscosity and mean free path; status **derived screening estimate, not a
  measurement**. Significant figures kept to two.

### F7 — Your model's central `Deff = 1e-5 m²/s` implies ε/τ ≈ 0.49, which is plausible but unverified and sits mid-to-optimistic

`model/config/uncalibrated_example.json` sets
`window_conductance_mol_per_s` from "A=193.05 mm², L=0.18 mm, **Deff=1e-5 m²/s**, 101.325 kPa,
25 °C", with `provenance: "sensitivity_only"`.

`D(O₂–air, 25 °C) = 0.176 cm²/s × (298.15/273.15)^1.75 = 0.205 cm²/s = 2.05e-5 m²/s`.
So the model assumes **`D_eff/D_free = 1e-5 / 2.05e-5 = 0.49`**.

For fibrous porous media, Huang et al. [S6] report "tortuosity values range from 1.1 to 2.2 as
porosity increases from 61 % to 90 %", giving ε/τ ≈ **0.28 – 0.82**. 0.49 falls inside.

- Evidence for the tortuosity range: **direct**, [S6], §3 discussion accompanying Figure 8.
  Inspected.
- Tags for [S6]: origin **simulated** (lattice-Boltzmann and pore-network modelling of
  stochastically reconstructed structures); transformation **direct** quotation; status **range**.
- **Dependency/limitation, load-bearing:** [S6] models **porous metal fibre sintered sheet**,
  not PTFE, and is a simulation study. It establishes that 0.49 is *not physically absurd* for a
  fibrous porous medium. It is **not** validation of 0.49 for PMV15T, and if PMV15T is a sintered
  depth film (F4) rather than an expanded fibrous web, its porosity is plausibly lower and ε/τ
  toward the bottom of that band. A factor of ~1.8 error in D_eff against the central case is
  entirely available within the published evidence.

**This is the single most valuable measurement you are not yet treating as a measurement.**
MEMBRANE.md's qualification step 1 ("Compare the bare cell, open carrier, PMV15T carrier and
MMS341 carrier … record t63, t90") *already determines installed conductance* — it just is not
labelled as the D_eff determination. Because area and D_eff trade directly against each other in
the response budget, that number should be pinned **before** the window geometry is frozen, not
after.

### F8 — Your letter to Porex understates your own requirement by roughly 10×

`PMV15T-REPLY-2026-08-26.txt` §3 says: "Unsere Auslegung rechnet konservativ mit 5 % der
**offenen** Diffusionsleitfähigkeit und erreicht damit ca. 116 s".

`model/README.md` (the source of the 116 s figure) says the voxel matrix "uses **5 % installed
conductance**, 10 s cell lag, effective diffusivity `1e-5`–`3e-5 m²/s` … The revised candidate's
worst 1 mm-grid case is about 116 s".

The 5 % is a stress multiplier applied to the **installed** conductance, which is itself already
built on `D_eff = 1e-5 m²/s` ≈ 0.49 × free-air. It is not 5 % of open-air diffusion.

Read literally, your letter tells Porex you can tolerate `D_eff ≈ 0.05 × D_free ≈ 1e-6 m²/s`.
What you actually need from the clean membrane is `D_eff ≈ 1e-5 m²/s`. A vendor reading the
letter will conclude your requirement is an order of magnitude softer than it is, and may
recommend a tighter, lower-airflow grade accordingly.

- Evidence: **direct**, both project files, quoted above. Inspected.
- This is a correspondence defect, not a model defect. The model is *more* conservative than the
  letter claims.

### F9 — Porex does make combined absorbing/carbon filters, but publishes no O₂ delay for them

Answering the question in §3 of your letter. The brochure [S5] documents two relevant families:

- **Gas-specific absorbing filters** — absorbents/additives loaded into a glass-fibre porous
  matrix. Target gases listed: H₂S, SO₂, HMDS, volatile organic compounds, low-molecular-weight
  alcohols. Additives: silica compounds, metal oxides, proprietary formulations, swelling agents.
  Standard thickness **1.2 mm**; standard diameters 5, 7, 10, 11, 12 mm.
- **Activated carbon filters** — bonded carbon, marketed as a low-shedding replacement for
  carbon cloth, "efficiently absorb low molecular weight alcohols such as ethanol".
  Standard diameters 4, 10, 18 mm.

Notably: "constructed with safe-to-use additives versus competitive products with **toxic lead
acetate** components" — relevant given you are deliberately on a lead-free cell.

- Evidence: **direct**, [S5] pp. 2–3. Inspected.
- **Absence claim, bounded:** no O₂ diffusion delay, response-time penalty, or concentration-
  diffusion figure is published for either family. Searched porex.com and the brochure PDF on
  2026-08-26 (queries in §4). Confidence in absence for *public* data: **medium**, limited to
  the vendor's own web corpus and this brochure; Porex may hold the data internally, so ask.
- **Geometry mismatch:** these are sensor-*internal* discs at 4–18 mm diameter and 1.2 mm thick,
  shown inside the exploded electrochemical cell. They are not characterised as a 10 × 10 mm
  external window layer in series with a heated chamber. Treat as a lead to ask about, not an
  off-the-shelf answer.

### F10 — Corporate and procurement facts worth having before the next Porex mail

- **Porex is now Parker Hannifin.** A banner on every porex.com page reads "Parker Hannifin has
  completed its acquisition of Filtration Group Corporation" [S1, S3]. Porex sat under Filtration
  Group; the brochure contact addresses are still `@filtrationgroup.com` [S5].
- **EU entity, in Germany:** Porex Technologies GmbH, Strangenhäuschen 30, 52070 **Aachen**,
  T +49 241 910525-0, `info.porex.emea@filtrationgroup.com` [S5]. If your thread is currently
  with a US or a distributor contact, Aachen is the direct EU route for German delivery.
- **Stock adhesive vent formats** exist in the PMV15 series [S5]: OD/ID 7.0/3.0 (N), 10.0/7.0 (I),
  12.7/7.1 (W), 20.0/13.0 (C) mm. Your fallback round geometry wants ~19 mm clear opening — the
  largest stock vent clears only 13 mm, so the fallback needs flat stock and self-cutting, as
  your letter already proposes.
- Evidence: **direct**, [S1]/[S3]/[S5]. Inspected.

### F11 — Oil-induced pore blocking with permanent permeability loss is a documented PTFE vent failure mode

Pall Corporation's patent US6355081B1 [S7] states in its background: "Treating PTFE membranes
with steam can cause pore blockage due to condensation of oil from the machinery used to
generate the steam. **The resulting loss of air permeability reduces the membrane's ability to
serve as an air vent.**"

- Evidence: **direct**, [S7], "BACKGROUND OF THE INVENTION" §2. Inspected.
- This came from a search run **against** F1/F2 (looking for evidence that oleophobic treatment
  or oleophobic service costs airflow). It did not refute F1/F2 — the patent's own oleophobic
  PDMS coating is claimed to give "high water penetration pressures and **high air
  permeabilities**". What it does establish, from an independent manufacturer, is that
  **low-surface-tension liquid condensing into the pores of a PTFE vent is a real mechanism that
  permanently costs air permeability.** That is the compost-condensate scenario, and it is direct
  third-party support for MEMBRANE.md's insistence on oleophobicity and on aged-response testing
  rather than clean-coupon testing.
- Tags: origin **author assertion in a granted patent**; transformation **direct** quotation;
  status **qualitative**.

### F12 — The architecture your shortlist does not contain: a *dense* membrane

Every candidate in MEMBRANE.md is a **porous** membrane, so every one of them can in principle be
wetted, blinded or fouled through its pores. The soil-science community, working the same
problem (trace gas concentrations in wet, biologically active porous media), routinely uses a
**non-porous** membrane instead.

Petersen 2014 [S8]: "The probe has a 10-ml diffusion cell with a 3-mm diameter opening covered by
a **0.5-mm silicone membrane**." The probe "can be deployed with minimum disturbance of in-situ
conditions, and also **at sites with a high or fluctuating water table**", and the laboratory
tests evaluated "equilibration of CH₄, N₂O and CO₂ **in air and water**".

- Evidence: **direct** from the abstract/Summary, [S8]. Evidence state: **metadata/abstract
  only** — the full text is paywalled and was not obtained; nothing below depends on the body.
- A dense silicone (PDMS) membrane transports gas by solution-diffusion, so there are no pores to
  wet, blind or biofilm shut. This is why it survives a fluctuating water table.
- **This is almost certainly not your Rev-A window.** Solution-diffusion through 0.5 mm of PDMS
  is far slower than porous diffusion, and Petersen's protocol is flush-equilibrate-withdraw
  sampling, not continuous sensing; the paper tests CH₄/N₂O/CO₂ and **not O₂**. Against a 120 s
  settling limit it is the wrong tool.
- **It is worth knowing as the robustness benchmark**, and as a candidate for a slow, deliberately
  fouling-immune *reference channel* against which the fast porous window's drift can be audited
  in the field — which is exactly the failure mode MEMBRANE.md's field-fouling plan is trying to
  catch. Related classic: Kammann, Grünhage & Jäger, silicone-tubing sampling at defined soil
  depths (surfaced in [S8]'s "Recommended" list; not retrieved).

### F13 — The 2019 brochure is superseded; do not quote its numbers

Where the brochure [S5] and the live portfolio table [S3] overlap they disagree:

| Grade | Brochure (2019) | Live table (2026) |
|---|---|---|
| PMV10 airflow | 125 | **107** |
| PMV10 WEP | 270 | 270 |
| PMG20 | 750 / 15 | **765 / 17** |

Use [S3] and the product pages [S1] for numbers; use [S5] only for the qualitative
sintering/scrim/absorbing-filter statements, cited as ©2019 `PX-EL-BR-190528-1`.

---

## 2. What this changes in MEMBRANE.md

| MEMBRANE.md says | This pass finds | Action |
|---|---|---|
| "Confirm the construction with Porex rather than carrying the plan's generic `ePTFE` label into the drawing unverified" | Virtek® is trademarked only on the **sintered** rows; brochure says sintered + no scrim. Prose on the same page still says "expanded or sintered". | Change the working label from ePTFE to **sintered PTFE**, flagged provisional; keep the question in the Porex thread. Update `PLAN.md`'s `ePTFE membrane` wording. |
| "Use a smooth polypropylene support or carrier on the exposed side" (cites Porex's **ePTFE** backing guide) | Sintered Virtek is a depth filter with **"No support required"**; the PP/PET lamination row is the *expanded* family. | **Re-open this design rule.** Test a *bare* PMV15T coupon against a PP-supported one in qualification step 1. Recover the free area currently deducted for support-grid obstruction. |
| PMV10L listed as hydrophobic control | PMV10L max operating temp **100 °C** vs 260 °C for the rest, because of its mesh backing | Keep as control but record the thermal caveat; it is not representative of the family. |
| Candidate table lists PMV15T, PMV10L, Gore, Donaldson, sintered PTFE | **PMA10** publishes values identical to PMV15T; PMA15/PMA20 identical to PMV20/PMV27 | Add the PMA line to the candidate table; ask Porex which designation is orderable. |
| "Oleophobicity is important because a water-repellent membrane can still be wetted by lower-surface-tension organic liquids" | Independent third-party support: Pall US6355081B1 documents oil condensing into PTFE vent pores with permanent air-permeability loss | Cite [S7] against the existing claim; it is currently unsourced. |
| Every candidate is porous | Dense-silicone diffusion probes are the soil-science standard for fluctuating water tables | Add as a documented alternative architecture + possible fouling-immune reference channel. |
| — | The letter's "5 % der offenen Diffusionsleitfähigkeit" ≠ the model's "5 % installed conductance" | Correct in the next mail to Porex before they size a grade against the wrong requirement. |

## 3. What would discriminate

| Open question | Observation that settles it | Which outcome favours what |
|---|---|---|
| Is PMV15T sintered or expanded? | One sentence from Porex; or SEM of a coupon (sintered skived film vs node-and-fibril web is unmistakable) | Sintered → drop the PP support, recover area. Expanded → keep support, and the ePTFE backing guide applies as MEMBRANE.md assumed. |
| Is the treatment really transport-neutral? | Measure t63/t90 on PMV15 and PMV15T coupons in the same carrier | Equal → treat oleophobicity as free, always specify it. Unequal → the identical spec sheets are spec reuse, and the trade must be priced. |
| Is `D_eff = 1e-5 m²/s` right? | Two-chamber (Wicke–Kallenbach) steady counter-diffusion, or the bare-cell-vs-carrier O₂ step already in qualification step 1 | ≥1e-5 → the 116 s budget holds with margin. ≤5e-6 → the window area or the plenum must grow before the geometry freezes. |
| Do PMV15T and PMA10 differ? | Porex confirmation | Same → order whichever is stocked. Different → the identical published table is a documentation artefact and both need testing. |
| Can a carbon/absorbing layer be added without breaking the response budget? | Porex response-time data, or your own step test with a 1.2 mm absorbing disc in series | Acceptable delay → NH₃/H₂S cell protection becomes available. Unacceptable → cell poisoning must be handled by cell choice and replacement interval, as MEMBRANE.md already assumes. |

## 4. Search record (challenge and absence searches)

Serper (Google), 2026-08-26, English, unbounded by date:

- `Nitto TEMISH waterproof breathable membrane gas sensor vent oleophobic water entry pressure`
- `Sumitomo POREFLON PTFE membrane gas sensor vent water entry pressure oleophobic datasheet`
- `GVS Sefar Saati ePTFE oleophobic vent membrane gas sensor water entry pressure airflow datasheet`
- `membrane oxygen sensor response time diffusion resistance effective diffusion coefficient ePTFE porosity tortuosity Fick`
- `buried soil gas sampling probe diffusion membrane silicone tubing Accurel polypropylene oxygen carbon dioxide in situ`
- `gas sensor vent combined activated carbon chemical filter membrane assembly oxygen diffusion delay Porex Gore`
- `ePTFE membrane wetting by surfactant leachate low surface tension failure hydrophobic vent breakthrough biofilm`
- `Wicke-Kallenbach cell measure effective diffusivity porous membrane equimolar counter-diffusion vent membrane test method`
- `"Gurley" OR "air permeability" correlate gas diffusion resistance porous membrane Knudsen viscous flow separator convert`
- `porosity tortuosity expanded PTFE membrane measured effective gas diffusion coefficient ratio Deff/D 0.5 vent membrane`
- `Nitto TEMISH oleophobic type vent filter water entry pressure air permeability NTF table specifications`
- `Petersen 2014 diffusion probe gas sampling undisturbed soil European Journal Soil Science silicone membrane`

**Challenge search** against F1/F2 (that the oleophobic treatment is airflow-neutral):
`oleophobic treatment reduces airflow permeability PTFE vent membrane penalty coating pore blocking criticism`.
Result: did not refute F1/F2. The nearest counter-evidence, Pall US6355081B1 [S7], concerns oil
*contamination* blocking pores rather than the treatment itself, and that patent's own oleophobic
coating claims high air permeability. Recorded as F11 instead.

**Bounded absence claim (F9):** no public O₂ diffusion-delay or response-time penalty figure for
Porex absorbing/carbon filters was found within porex.com and [S5], searched 2026-08-26 with the
queries above. Confidence **medium**, limited to the vendor's public corpus. This is not a claim
that the data does not exist.

**Not searched / out of scope this pass:** Gore MMS341 private data (MEMBRANE.md already records
that Gore does not publish enough numerically); Donaldson exact part data (available only on
request); Sumitomo POREFLON, GVS, Saati, Sefar, Cobetter and Membrane Solutions were surfaced but
not inspected to product-page level — none of them published an oleophobic sensor grade with
Porex-equivalent public minimum values in the search results, but that is **not** an absence
claim, only an unexplored branch.

## 5. Source access log

All accessed 2026-08-26. Browser surface: Playwright MCP (headless Chromium), proven before first
fetch by navigating `about:blank` and reading the returned DOM.

| ID | Identifier | Evidence state | Attempt history | Route | Validation | Load-bearing |
|---|---|---|---|---|---|---|
| S1 | https://www.porex.com/product/virtek-ptfe-material/ (PMV15T) | inspected — full Measurements block | first Playwright target attempt, HTTP 200 substantive page | live DOM / raw text | validated (live DOM) | yes |
| S2 | https://www.porex.com/product/virtek-ptfe-materials-8/ (PMV15) | inspected — full Measurements block | first attempt, HTTP 200 | live DOM / raw text | validated | yes |
| S2b | https://www.porex.com/product/virtek-ptfe-materials-3/ (PMV10) | inspected — Measurements block | first attempt, HTTP 200 | live DOM / raw text | validated | no |
| S2c | https://www.porex.com/product/virtek-ptfe-materials-12/ (PMG20) | inspected — Measurements block | first attempt, HTTP 200 | live DOM / raw text | validated | no |
| S3 | https://www.porex.com/porous-polymers-technologies/porous-membranes/ptfe-hydrophobic-membranes/ | inspected — all four product/technology tables + sintered/expanded prose | first attempt, HTTP 200; tables extracted from live DOM | live DOM / raw text | validated | yes |
| S4 | https://www.nitto.com/eu/en/products/temish_search/003/ (redirected from /us/en/) | inspected — all product tables | first attempt, HTTP 200, followed vendor redirect to EU site | live DOM / raw text | validated | yes |
| S4b | https://www.nitto.com/us/en/products/temish_search/001/ | inspected — punched-product tables | first attempt, HTTP 200 | live DOM / raw text | validated | no |
| S5 | https://www.porex.com/wp-content/uploads/2020/01/Porex-Brochure-Electrochemical-Gas-Sensor-Components.pdf — ©2019, doc `PX-EL-BR-190528-1` | inspected — full document (4 pp.) | curl with plain-Chrome UA, HTTP 200, `application/pdf`, 1,214,065 bytes, `%PDF-1.5` magic verified | raw text (`pdftotext -layout`, text layer) | validated — extracted table cross-checked against the product tables in S3; two disagreements found and reported as F13 | yes |
| S6 | Huang et al., "Effective Diffusion in Fibrous Porous Media", https://pmc.ncbi.nlm.nih.gov/articles/PMC7914409/ | inspected — Abstract, §1 Introduction, and §3 discussion at Figure 8 (the tortuosity range) | first attempt, HTTP 200 | live DOM / raw text | validated | yes |
| S7 | Wang & McDonogh (Pall Corp), US6355081B1, https://patents.google.com/patent/US6355081B1/en | inspected — Abstract and Background §§1–2 | first attempt, HTTP 200 | live DOM / raw text | validated | yes |
| S8 | Petersen, S. O. (2014), *Diffusion probe for gas sampling in undisturbed soil*, European Journal of Soil Science **65**(5), 663–671, DOI 10.1111/ejss.12170 | **metadata / abstract only** — Summary inspected, full text paywalled and not obtained; no claim depends on the body | ADS mirror `ui.adsabs.harvard.edu/abs/2014EuJSS..65..663P` returned a rendered CAPTCHA ("Human Verification", HTTP 405) in a headless non-handoff-capable session → logged as an access failure, session not replaced and challenge not retried around; publisher of record then reached directly at the Wiley DOI landing page, HTTP 200 substantive page | live DOM / raw text | validated | no — architectural context only |

**Archive:** `archive unavailable` — no user-authorized project research archive exists for this
repository, consistent with the decision recorded in `CONDENSATION-MODEL.md`. The Porex brochure
was downloaded only to session working storage and was not added to the repository. Stable URLs
above are the retained pointers.

**Non-clean rows to note:** S8 is **abstract-only** and its full text was **not** obtained
(DOI 10.1111/ejss.12170); one CAPTCHA access failure is logged against its ADS mirror. Everything
load-bearing is `inspected` + `validated`.
