# O₂ probe gas-window membrane

Research date: 2026-08-22
Revised: 2026-09-06 — qualification step 2 gained a written soak,
wetting-threshold and condensation procedure; the headline point is that a
clean-water soak sits ~54× below the minimum water-entry pressure and can only
decide specimen integrity, never material fitness. See
[Soak and wetting procedure](#soak-and-wetting-procedure).
Revised: 2026-09-03 — membrane perimeter seal sourced: **an O-ring, `ORS116731`
17.0 × 1.0, EPDM 70 Shore A peroxide — the same compound (127019011) as the
carrier ring `ORS116787`, so one test report now covers both seals.** EPDM's
ammonia compatibility closed against a primary and its organic-acid side left
open; a compression-flow defect found in the flat-gasket pocket, which the
O-ring resolves; carrier CAD changed from a flat pocket to a groove. See
[Membrane perimeter gasket sourced](#membrane-perimeter-gasket-sourced-2026-09-03).
Revised: 2026-09-02 — head hardware sourced (insert, O-ring, PP rod) with two
evidence gaps left open, see
[Head hardware sourced](#head-hardware-sourced-2026-09-02);
Porex sample sheet received (see
[Sample received](#sample-received-2026-09-02); identity check still to run);
enclosure material decided (printed ASA head on a bought tube body) and the
consequences for the membrane joint recorded under
[Enclosure material](#enclosure-material-printed-asa-decision-2026-09-02).
Revised: 2026-08-27 — Porex confirmed the sintered construction in writing and
supplied the official datasheet; direct purchase is closed off by MOQ and moves
to a distributor. Revised: 2026-08-26 — construction reclassified as sintered
PTFE, and the PP support backing demoted from design rule to test variable. See
[MEMBRANE-RESEARCH-2026-08-26.md](MEMBRANE-RESEARCH-2026-08-26.md) for the
second research pass, which also carries findings not folded in here: the
oleophobic-treatment airflow evidence, Porex's PMA line, the PMV10L temperature
caveat, third-party evidence on oil pore-blocking, and the dense-silicone
alternative architecture.
Status: Rev-A candidate selected; production material remains conditional on
complete-path wetting and fouling tests.

## Decision

Use **Porex Virtek PMV15T sintered PTFE membrane** as the Rev-A baseline for the
external gas window. Install it in a removable, drained carrier — preferably
ultrasonically welded into a replaceable PP disc — behind a separate coarse
debris guard. *Revised 2026-08-27:* the polypropylene **support** layer is no
longer part of the decision. It came from a Porex guide for the expanded family;
PMV15T is confirmed sintered and needs no support [S14a, S15], so the support is
carried as an arm of qualification step 1 rather than as a design rule. Obtain
**Gore MMS341** samples as the principal A/B challenger before freezing the
production material — the more so now that PMV15T's own MOQ puts it behind a
distributor.

This decision fills the open material choice in [PLAN.md](PLAN.md), which
originally specified only `slots + ePTFE membrane + mesh`; that wording was
corrected to sintered PTFE on 2026-08-27. The membrane is an enclosure
window; it does not replace or touch the SGX-OX-ROHS-Mini cell's own gas-facing
surfaces. Both cell faces and the rear PCB aperture must remain unobstructed.

PMV15T is the best publicly documented starting point, not a demonstrated
compost-lifetime solution. Vendor pressure-flow and water-entry figures do not
predict oxygen concentration response after condensate, organic films, fines,
or biofilm cover the membrane. The final choice therefore depends on tests with
the complete heated gas path and real compost exposure.

## Service environment and requirements

The gas window must operate under conditions substantially harsher than a
normal electronics enclosure vent:

- saturated compost pore gas, with condensation whenever an exposed surface is
  below the gas dew point;
- normal probe operation up to approximately 56–58 °C, set by the O₂ cell and
  heater limits in [PLAN.md](PLAN.md);
- NH₃, CO₂, CH₄, H₂S, volatile organic compounds and organic-acid vapours;
- condensate or leachate containing dissolved and entrained organic material,
  rather than clean water;
- abrasive compost fines, handling damage, microbial growth and biofilm;
- a continuous need for representative O₂ diffusion, including recovery after
  temporary wetting.

The membrane assembly consequently needs:

1. hydrophobic and strongly oleophobic behaviour;
2. enough gas permeability that it does not dominate probe response time;
3. chemical compatibility of the complete assembly—not only the PTFE base
   material;
4. support against handling, abrasion and pressure from lodged particles;
5. gravity drainage and no upward-facing liquid pocket;
6. inspection, cleaning and cartridge replacement without disturbing the
   potted electronics;
7. calibration and response testing in its final geometry.

Oleophobicity is important because a water-repellent membrane can still be
wetted by lower-surface-tension organic liquids. A liquid film need not pass
through the membrane to make the probe unusable; covering the pores is enough
to slow gas diffusion.

## Rev-A material: Porex PMV15T

The official material datasheet [S14], sent by Porex on 2026-08-27, supersedes
the product page [S1] as the citation of record. Every value the page carried is
reproduced identically on it; the datasheet adds the remaining rows and, more
importantly, the caveats.

| Property | Published value | Evidence status |
|---|---:|---|
| PTFE content | 100 %, CAS 9002-84-0 | datasheet |
| Oleophobic grade | 8 (AATCC TM 118-1997) | datasheet |
| Water-entry pressure | 265 mbar minimum; 370 mbar typical | datasheet, **Porex QC method, no national standard** |
| Airflow at 70 mbar differential | 45 minimum; 75 typical L h⁻¹ cm⁻² | datasheet, **Porex QC method, no national standard** |
| Thickness | 0.18 ± 0.03 mm | datasheet |
| Operating temperature | −40 to 260 °C | datasheet |
| Enclosure rating | IP64 and IP67 (BS EN 60529:1992) | **representative sample only; not part of roll approval** |
| Filtration efficiency | 0.4 µm under IEST RP-CC007.2:2009 | **representative sample only; not part of roll approval**; **not a pore-size claim** |
| Salt fog | passes ASTM B117-11 | datasheet |
| Compliance | PFOA-free; REACH (EC) 1907/2006; POP EU 2019/1021; RoHS; WEEE | datasheet |
| Hydrophobicity | naturally hydrophobic (not a coating) | datasheet |

**Read the evidence column before quoting these numbers.** The datasheet states
that airflow and WEP come from Porex's own QC methods and that "testing is not to
any national or international standard"; that the IP and filtration-efficiency
rows are measured on a representative sample and are *not* verified per roll; and
that "samples are intended for evaluation purposes only and not intended for
specification". None of these values is a guaranteed lot property, so none may be
carried into a specification or a guard threshold without our own measurement.
The "naturally hydrophobic" row is worth separating from the Grade-8 line: the
hydrophobicity is intrinsic to PTFE and cannot be washed off, whereas the
oleophobic treatment is applied and is the layer whose ageing behaviour in hot
NH₃-rich condensate remains unknown.

These figures make PMV15T the only exact candidate found with public minimum
airflow, water-entry and Grade-8 oleophobic values. Porex also markets the
material family for fast diffusion into gas sensors while excluding water,
oil, dust and other contaminants [S2].

The 370 mbar typical water-entry value is ample for a drained, non-pressurised
probe, but it is not the governing requirement. A surface water or biofilm
layer can block diffusion at essentially zero differential pressure.

Porex's compatibility chart marks unsupported PTFE membrane as resistant to
ammonia, acids, bases, alcohols and numerous hydrocarbon or solvent classes
[S3]. This is useful substrate screening only. It does not establish the
compatibility of PMV15T's oleophobic treatment, a backing laminate, an
adhesive, or the carrier seal with compost condensate.

### Construction: sintered, not expanded — confirmed

**Closed 2026-08-27.** Porex states in writing: *"Bei PMV15T handelt es sich um
gesintertes PTFE."* [S14a] The inference below was made independently on
2026-08-26 and is retained because it shows which vendor artefacts are reliable
when a product page contradicts itself: the technology **table** was right and
the surrounding **prose** was wrong.

The exact PMV15T product page still does not state the construction, but Porex's
portfolio page settles it by other means [S12]. Its
technology table attaches the `Virtek®` trademark to exactly two rows —
*Porex Virtek® PTFE **Sintered** Hydrophobic* and *Porex Virtek® PTFE **Sintered**
Oleophobic*, both **depth** filters marked **"No support required"** — while the
third row is plain *Porex Expanded PTFE Hydrophobic*, a **surface** filter
requiring **PP/PET lamination**. PMV15T is branded `POREX Virtek®` in its own
page title [S1], so it belongs to the sintered rows.

Porex's electrochemical-gas-sensor brochure says the same thing in prose:
Virtek is "manufactured via a proprietary sintering process", its "diffusion
rate does not change when handled as it does with ePTFE products", and it "does
not require scrim support that could absorb or desorb (release) gases, thereby
causing slower or false readings" [S13].

Two caveats kept this provisional until the vendor confirmation above:

- The prose *on the same portfolio page* says Virtek materials "include expanded
  or sintered engineered manufacturing options", contradicting its own table's
  trademark usage.
- PMV15T's 0.18 mm thickness falls inside **both** family ranges (sintered
  0.1–3.0 mm, expanded 0.14–0.22 mm), so thickness does not discriminate.

The label is therefore **sintered PTFE**, not `ePTFE`, throughout. `PLAN.md` was
corrected on 2026-08-27. No SEM is needed to settle it any more, though a coupon
micrograph remains worth taking for the pore-structure record.

Two design consequences follow directly, and both are load-bearing:

- **No support layer.** Sintered PTFE "doesn't require any support" [S15], which
  turns the PP backing from a precaution into pure cost — free area and series
  diffusion resistance spent for nothing. The bare arm of qualification step 1 is
  now the expected winner rather than an even bet.
- **Ultrasonic welding is available.** Porex's welding brief [S15] gives the
  process for bonding sintered PTFE vents directly to a plastic housing, with one
  hard constraint: the substrate must have good flow properties and a melting
  point **below 260 °C**. Polypropylene (~160 °C) satisfies this comfortably.

## Carrier construction

Use a mechanically retained cartridge, provisionally arranged as follows:

```text
compost
   ↓
replaceable coarse debris guard
   ↓
open drainage / stand-off gap
   ↓
PMV15T membrane — PP support on exposed side is NO LONGER ASSUMED (see below)
   ↓
heated probe gas chamber
   ↓
SGX-OX-ROHS-Mini, with both cell gas faces unobstructed
```

Design rules:

- Put gas openings on the side or underside of the tube and provide an
  uninterrupted drain path.
- Do not place mesh directly against the membrane where compost can press fines
  into it. Preserve a drainable stand-off gap.
- Mechanically clamp, heat-stake or weld the membrane carrier where practical.
  Do not make pressure-sensitive adhesive the only wet-side seal until the
  exact adhesive has passed hot-condensate ageing and peel tests.
  Porex's datasheet endorses five attachment methods for this grade [S14]:
  ultrasonic welding, thermal welding, over-moulding, pressure-sensitive
  adhesive and compression seal. Compression seal — the Rev-A choice — is
  therefore vendor-supported, not a workaround. **Preferred construction:
  ultrasonically weld the membrane into a PP carrier disc, and make the disc
  the replaceable item.** That keeps the wet-side seal a fused polymer joint
  rather than a clamped interface, without giving up field replaceability,
  and it removes the adhesive dependency entirely. Validate the weld to the
  brief's constraint: substrate melt point below 260 °C, horn temperature
  slightly above the substrate melt, dwell and pressure tuned so the melted
  substrate forms a mechanical bond into the porous structure [S15].
- **Treat the polypropylene support as a test variable, not a design rule.**
  *Revised 2026-08-26.* This rule was originally taken from Porex's **ePTFE**
  backing guide, which lists 100–300 µm PP support, a −40 to +100 °C range,
  strong acid/alkali resistance, toughness and abrasion resistance [S4]. That
  guide covers the **expanded** family — the one row in Porex's technology table
  that requires PP/PET lamination. PMV15T is confirmed sintered [S14a], and its
  row reads **"No support required"** [S12]; the welding brief repeats that
  sintered PTFE "doesn't require any support" [S15].

  The support is therefore not a free precaution. It costs free area — the model
  config already deducts "PP support-grid obstruction" to reach
  `free_membrane_area_mm2 = 193.05` from 200 mm² gross — and adds a series
  diffusion resistance, both against the response budget's most critical
  parameter. Qualification step 1 must compare a **bare** PMV15T coupon against a
  PP-supported one in the same carrier and decide on measured `t63`/`t90`, not on
  a guide written for a different material family. Keep the support only if the
  bare coupon fails mechanically or the measured response penalty is negligible.
- Make the outer guard independently replaceable. A moulded or perforated PP
  guard avoids a corrosion path and thermal bridge; any alternative metal mesh
  requires its own corrosion and cleaning justification.
- Keep the membrane accessible for visual inspection and cartridge replacement.
- Avoid a cold carrier connected directly to the outer tube where it would
  condense water despite the heated internal chamber.

No active-area dimension is frozen. Design the first carrier to accept
interchangeable coupons so that area and backing can be varied without changing
the probe body.

## Enclosure material: printed ASA (decision 2026-09-02)

Question: can the probe live in a 3D-printed ASA tube instead of the 32 mm OD
PVC-U pipe named in [PLAN.md](PLAN.md)? It belongs in this document because the
housing polymer decides which of Porex's five attachment methods stay available.

**Decision.** Rev-A enclosure is a **bought tube for the potted body plus a
printed ASA head** carrying the keyed coupon cartridges, guard stand-offs, drain
wells and board guides. A fully printed body is permitted for prototypes. Either
variant is released only after the connected-volume/leak gate in
[`cad/RESPONSE-CANDIDATE-VOLUME.md`](cad/RESPONSE-CANDIDATE-VOLUME.md) passes on
the actual printed part, not on an inspection of it.

The split follows the geometry. Two keyed facets at 45°/315°, recessed
cartridges with an outer drain well, a stand-off guard and an offset cable
passage cannot be made in a round extruded pipe — the models in `cad/` are
already printed-part geometry. The potted body, by contrast, needs nothing but a
straight bore and a seal that is beyond doubt. Printing the head and buying the
body puts the leak-critical simple part in extruded stock and the
geometry-critical replaceable part in a printed one.

### Temperature is not the binding constraint, but it is not generous either

The wall at the tip sees the ~75 °C pile gas accepted in `PLAN.md` (deployment
envelope, decision 2026-08-27) plus up to ~4 K heater rise, so call it **≈79 °C**.

| Vendor ASA | Tg (DSC) | HDT B, 0.45 MPa (ISO 75) | HDT A, 1.8 MPa (ISO 75) |
|---|---:|---:|---:|
| BigRep ASA [S17] | 105 °C | 94 °C | 86 °C |
| 3DXMAX ASA [S18] | 105 °C | 95 °C | not published |
| Polymaker ASA [S19] | 98 °C | 103 °C | 100 °C |

**Do not quote a single figure, and do not quote Polymaker's.** Its sheet puts
HDT at 1.8 MPa (100 °C) *above* its own Tg (98 °C), which is not physically
sensible for an amorphous polymer; the row is unreliable regardless of which
side of it is wrong. The two internally coherent sheets agree at Tg ≈ 105 °C,
HDT B ≈ 94–95 °C, HDT A = 86 °C.

Read against ≈79 °C that gives two different margins, and the difference is the
whole design rule:

- **Unloaded, the margin is ~26 K to Tg.** An enclosure that merely holds its
  own shape is not at risk.
- **Under sustained load, the margin is ~7 K to HDT A.** That is not enough, and
  HDT is a short-term test besides — creep over a buried season is the real
  mechanism.

**Rule: no part of the enclosure may carry sustained strain at temperature.** No
interference press-fits, no clamped preload expected to survive months at 75 °C.
Retention is by positive features plus a compliant elastomer seal that supplies
the sealing force, so the polymer is not the spring.

ASA's usual selling point is irrelevant here: the probe is buried and only the
cable exit sees sun. The choice rests on printability and temperature, not
weathering.

### Two risks, both testable

1. **FDM walls are not gas-tight, and here the wall is part of a measurement
   path.** The premise of the whole probe is that gas reaches the cell through
   ≥180 mm² of controlled membrane into ≤5.0 cm³ of connected volume.
   Bead-to-bead voids are an uncontrolled parallel diffusion path, a liquid route
   to the potted side, and the end of the sub-µA AFE leakage environment. Take
   all three mitigations: a deliberately solid wall band over the gas zone (many
   perimeters, no sparse infill touching the cavity); a sealing step — ASA is one
   of the few printable materials that solvent-smooths, with interior epoxy
   impregnation as the alternative; and, decisively, the existing
   pressure-expansion connected-volume measurement, which is a leak test wearing
   a different hat. A printed enclosure is released on that measurement, never on
   inspection. Note the tension in solvent smoothing: acetone/MEK is also the
   chemistry ASA is weakest against, so a smoothed part must repeat the ageing
   coupon below, not inherit its result.

2. **Environmental stress cracking, not corrosion.** ASA is a SAN-matrix
   styrenic, not a PTFE-grade plastic. Hot NH₃-rich condensate, organic acids and
   terpene VOCs against a styrenic under sustained load is the classic ESC
   combination — and ESC needs stress to appear, which is the second reason for
   the no-sustained-strain rule. Add printed coupons (smoothed and unsmoothed) to
   qualification step 3 alongside the membrane coupons. Acceptance: no crazing,
   no mass or dimensional drift, and a re-passed leak test after ageing.

Alternatives considered and rejected: PETG (HDT too low against a 79 °C wall);
PP (chemically the best fit and weldable to the PP carrier, but warps badly over
a 129 mm body); PC (temperature is fine, but it is attacked by ammonia and
alkalis — actively wrong for this service); PA (absorbs water).

### Consequence for the membrane joint

ASA changes exactly one thing in the attachment decision above:

- **PP and ASA cannot be welded to each other.** The preferred construction —
  PMV15T ultrasonically welded into a PP carrier disc — therefore survives as a
  *cartridge*: the membrane-to-PP joint stays a fused polymer joint, and the
  **PP-cartridge-to-ASA-housing joint becomes the compression seal**, elastomer
  gasket plus a positive retainer. Field replaceability wanted that interface
  anyway, and this keeps the fused joint on the wet side where it matters.
- **Welding PMV15T directly into ASA is plausible but unproven.** Porex's stated
  substrate criterion is good flow and a melting point below 260 °C [S15]; ASA is
  amorphous, has no melting point, flows around 220–250 °C, and amorphous
  styrenics are among the easiest ultrasonic welders. But every example in the
  brief is PP-family and Porex publishes no ASA result, so this route needs our
  own peel and leak coupons before it may be designed in.
- **Without an ultrasonic welder, thermal welding reaches the same fused key** —
  a heated annular tip or hot plate in a printed jig, temperature just above the
  substrate's softening point, dwell and pressure tuned so the melted substrate
  keys into the porous structure. Vendor-endorsed [S14], needs no special
  equipment, and is the Rev-A bench route if compression proves leaky.
- **Start Rev-A on compression regardless.** Qualification step 1 is an A/B of
  bare against PP-supported coupons; welding each variant makes coupon swaps
  expensive, and interchangeable coupons are an explicit goal above.

### The failure mode to design against

Whichever method is used, the seal is the coupon *perimeter*, and a bypass leak
**around** the membrane instead of through it presents as a suspiciously fast
`t63` with a wrong absolute O₂ — it looks like success. Two consequences:

- the perimeter seal takes the same pressure test as the enclosure;
- qualification step 1 must include a **deliberately bypassed coupon** as the
  known-bad case, so the test is shown to catch the failure rather than assumed
  to.

## Candidate comparison

| Candidate | Advantages | Unresolved issue / disposition |
|---|---|---|
| **Porex PMV15T** | Exact public grade; Grade-8 oleophobic; quantitative minimum flow and water-entry values; available as sheet material | Rev-A baseline; treatment, support and seal still require compost testing |
| **Gore MMS341** | Designed for gas, humidity and pressure sensors; oleophobic; Gore gives it the highest relative diffusion rating in the MMS family [S5] | Obtain sample and private numeric permeability, water-entry, thickness and temperature data; principal A/B challenger |
| **Gore PE120306 / PE130306** | Supported oleophobic ePTFE adhesive patches; 3 mm active diameter; −40 to +100 °C adhesive range and very high pressure airflow [S6] | Electronics pressure vents, not characterised O₂ concentration-diffusion windows; adhesive is a wet-service dependency; optional bench control |
| **Donaldson Tetratex / oleophobic press-fit** | Industrial ePTFE family; gas-sensor use; hydrophobic and oleophobic variants; chemically and thermally robust [S7, S8] | Public information does not identify an exact part with concentration-diffusion data; custom-source backup |
| **Sintered PTFE** | More resistant than delicate ePTFE to physical contact and may not require backing [S9] | No exact oleophobic sensor grade with PMV15T-equivalent public data was found; reconsider if Rev-A suffers mechanical damage |
| **Porex PMV10L** | Integrated polyolefin mesh backing and relatively high airflow [S10] | Hydrophobic but not specified Grade-8 oleophobic; useful as a hydrophobic control, not the baseline |

Pressure airflow is not interchangeable with concentration diffusion. The Gore
PE and Porex values may be compared only at the same stated pressure condition;
neither directly supplies the O₂ step-response of this chamber.

Generic PTFE discs, syringe-filter media and untraceable marketplace sheets are
not suitable design selections. A nominal micron rating alone establishes
neither oleophobicity, gas response, mechanical support nor assembly
compatibility.

## Qualification plan

Freeze the membrane only after PMV15T and MMS341 have been tested in identical
carriers. Set numerical acceptance limits from the required control/reporting
cadence and the probe error budget before testing; do not invent them from
vendor pressure-flow values.

### 1. Baseline diffusion

- Compare the bare cell, open carrier, PMV15T carrier and MMS341 carrier.
- Carry **bare PMV15T** and **PP-supported PMV15T** as separate arms, to settle
  the support question above on measured response rather than vendor guidance.
- **Treat this step as the `D_eff` determination, not only a ranking exercise.**
  `model/config/uncalibrated_example.json` currently assumes
  `Deff = 1e-5 m²/s` with `provenance: "sensitivity_only"` — that is
  `D_eff/D_free ≈ 0.49` against `D(O₂–air, 25 °C) ≈ 2.05e-5 m²/s`, a plausible
  but unverified mid-band value for a fibrous porous medium, and plausibly
  optimistic for a sintered depth film. Because window area and `D_eff` trade
  directly against each other in the response budget, this number must be pinned
  **before** the window geometry is frozen. Report the fitted `D_eff` with the
  coupon lot and carrier revision, and feed it back into the config in place of
  the sensitivity value.
- Step approximately 20.9 → 10 → 5 → 20.9% O₂ with traceable mixtures.
- Record `t63`, `t90`, steady-state bias, hysteresis and recovery.
- Repeat at room temperature, 40 °C and approximately 55 °C.
- Repeat with the heater controller active and log membrane-side and cell-side
  temperatures.

### 2. Humidity, condensation and leachate

- Repeat the O₂ steps in saturated gas.
- Apply clean-water droplets to the outer face and measure the response while
  covered, after gravity drainage and after drying.
- Repeat using actual compost condensate and representative leachate.
- Record whether blockage is reversible by drainage, rinsing or the intended
  field-cleaning method.
- Include the planned two-week saturated soak and condensation cycles from
  [PLAN.md](PLAN.md).

#### Soak and wetting procedure

*Added 2026-09-06.* The bullets above name the exposures; this subsection is the
procedure, and it exists mainly to stop the obvious version of the test from
being run and believed.

**What a clean-water soak can and cannot decide.** PMV15T's water-entry pressure
is 265 mbar minimum and 370 mbar typical (§ [Rev-A material](#rev-a-material-porex-pmv15t)),
which is **2.71 m and 3.78 m of water column** respectively. A coupon standing in
5 cm of water sees **≈ 4.9 mbar — about 1/54 of the guaranteed minimum**. Liquid
water therefore *must* not pass, and if it does the finding is a defect in that
specimen — a pinhole, a damaged weld, or bypass at the carrier seal — not a
property of the material. Run the clean-water immersion as an **integrity and
build check on every arm**, and never report its result as membrane
qualification.

Both WEP figures are Porex QC values with no national standard behind them and
are explicitly not specification values, so they bound our expectation only; they
are not an acceptance limit and must not become a guard threshold
(§ [Rev-A material](#rev-a-material-porex-pmv15t)).

**The failure mode that matters is blockage at zero differential pressure.** A
surfactant-bearing or organic film that wets the outer face covers the pores and
throttles O₂ diffusion without any liquid crossing the membrane. Every acceptance
criterion in this step is therefore a **gas-transport** measurement, not a
leak observation.

**Arms.** Carry three, because the membrane is not the only thing being soaked:

1. bare PMV15T coupon;
2. membrane ultrasonically welded into the replaceable PP disc;
3. the complete carrier with the `ORS116731` perimeter O-ring in its groove.

Arms 2 and 3 test open questions rather than the film: whether the weld densifies
the edge zone and moves local WEP or airflow (asked of Porex 2026-08-27, answer
outstanding — see [PMV15T-REPLY-2026-08-27.txt](PMV15T-REPLY-2026-08-27.txt)),
and whether the groove seal holds without a bypass path
(§ [Membrane perimeter gasket sourced](#membrane-perimeter-gasket-sourced-2026-09-03)).

**Dye every aqueous exposure** (fluorescein or methylene blue). Perimeter bypass
at the weld line or the O-ring groove is a more likely source of liquid on the
dry side than through-pore transport, and dye separates the two immediately.
Without it, a seal defect reads as a membrane failure.

**Measurement, per exposure state.** Record baseline → wetted → after gravity
drainage → after drying, for each arm:

- `t63` and `t90` on a 20.9 → 10 % O₂ step in the step-1 carrier, which is the
  quantity the probe actually depends on; airflow at fixed ΔP is an acceptable
  faster proxy for screening but is not the acceptance metric;
- specimen mass gain, as the direct indicator of pore filling;
- photographs, and a micrograph of the exposed face against the reserved
  unexposed control from the same lot (§ [Qualification plan](#qualification-plan),
  step 4).

Acceptance is **fractional recovery of `t63` against the arm's own dry baseline**
after drainage and again after drying. Set the fraction from the probe response
budget before testing, as required at the head of this plan — do not derive it
from vendor airflow figures.

**Wetting-threshold ladder.** Neither immersion nor leachate answers *how far* the
grade-8 treatment is from being wetted; a pass or fail gives no margin. Bracket
it with liquids of decreasing surface tension and record the highest surface
tension at which the face wets:

- an **aqueous** series — water/isopropanol or water/ethanol dilutions — covering
  roughly 72 down to ~22 mN m⁻¹. This is the band compost leachate lives in and
  the band the oil series below does not reach. Take the surface tension of each
  mixture from a cited table or measure it; do not interpolate by eye.
- the **AATCC TM118 oil series** itself, which is the scale the grade-8 claim was
  made on. Re-running it reproduces the vendor's own datasheet claim on the
  material we actually received. Grade 8 is the top of the scale, so a pass is
  `≥ 8` and does not resolve further. **We do not hold a copy of TM118**: take the
  liquid list and its surface tensions from the standard before quoting any
  number from it, and label the series `unverified` until that is done.

**This ladder doubles as the outstanding identity check.** The received sample
sheet has not been confirmed as PMV15T rather than untreated PMV15
(§ [Sample received](#sample-received-2026-09-02)); the two share thickness and
WEP and differ only in the oleophobic treatment
(§ [S16](#sources)). Untreated PMV15 will wet at a
markedly higher surface tension than the treated grade, so the aqueous series
discriminates them without a laboratory.

**Durations and conditions.**

- Clean-water integrity check: short, on every arm, before anything else.
- Leachate soak: the **two-week saturated soak at operating temperature** from
  [PLAN.md](PLAN.md), with wet/dry cycling, on real compost leachate. This is the
  exposure that can disqualify the material.
- **Condensation outranks immersion for realism.** The field case is a coupon
  held below the dew point in saturated compost gas, not a submerged one. Run the
  cold-coupon-in-warm-saturated-gas case alongside the soak and weight it higher
  when the two disagree.
- A hydrostatic WEP confirmation needs ~3 m of head or a pressure pot. Worth doing
  **once, on one coupon, as a lot check**; it is not worth repeating per arm.

**Handling rules, which are part of the procedure and not advice.**

- Never touch the membrane face. Skin oils wet a grade-8 surface and the result is
  indistinguishable from material failure.
- Never clean a test coupon with detergent. Surfactant residue blocks pores
  permanently and contaminates every later exposure of that specimen.
- Do not soak with the SGX-OX-ROHS-Mini fitted.
- Keep the reserved unexposed coupons from the same lot out of the test area
  entirely (§ [Qualification plan](#qualification-plan), step 4).

### 3. Chemical and mechanical ageing

- Expose the complete membrane, backing and seal to representative NH₃-bearing
  compost vapour and condensate at operating temperature.
- Cycle wet/dry exposure and the proposed cleaning procedure.
- Challenge the guard with compost fines and screened slurry without pressing
  material artificially through the carrier.
- Inspect for membrane tears, backing delamination, adhesive creep, loss of
  oleophobic behaviour and permanent airflow/response change.

### 4. Field fouling

- Deploy sacrificial PMV15T and MMS341 coupons in the intended orientation.
- Retest coupons after approximately 2, 6 and 12 weeks, while keeping an
  unexposed control from the same material lot.
- Photograph deposits and record wet and cleaned O₂ response.
- Derive the inspection or replacement interval from measured degradation, not
  from a generic calendar value.

Smith's marine field study found that membrane thickness, pore structure and
roughness materially changed diffusion and that all tested PTFE/HDPE membranes
were significantly fouled with reduced diffusion after six weeks [S11]. Marine
immersion is not compost, so this does not predict a six-week compost lifetime.
It is direct evidence that hydrophobicity alone does not prevent biological
fouling and supports the replaceable-cartridge and aged-response tests.

### 5. Final calibration

Perform final zero, span and response calibration through the complete gas path:

**outer guard + drainage gap + support + membrane + carrier + chamber + running
heater + O₂ cell**.

A bare-cell calibration is insufficient. Store the membrane material, lot,
active area, support, seal and carrier revision with the calibration record.

## Procurement

### Supply route: distributor, not Porex direct

**Settled 2026-08-27 [S14a].** Porex's minimum order quantity is **10,000 pieces
or two master rolls** of parent material. A master roll is 330 ± 5 mm wide [S14];
two of them are several hundred square metres. Our requirement is 30–80 discs of
Ø27 mm per year — roughly three orders of magnitude below the floor. Buying
direct is not a matter of negotiation, it is arithmetic.

Porex therefore refers small quantities to **ADDEV Materials Parafix**, their
distributor for non-adhesive vent material in custom rolls and die-cuts. Free
samples of PMV15T still come from Porex directly, against a postal address.

Consequences for the plan:

- Qualification proceeds on Porex samples, but the **production** material must
  be re-verified as the same grade through ADDEV. A distributor slitting from a
  different master roll is a different lot, and none of the datasheet values is
  roll-verified [S14].
- **The referral may not reach the qualified grade.** Parafix's public catalogue
  lists three Porex flat grades — MD10L, MD22 and **PMV15** — plus the PMV30C/I/N/W
  adhesive-backed discs. A site search for `PMV15T` returns **zero items** [S16].
  The grade they do list, PMV15, is the **untreated** 0.18 mm hydrophobic-only
  material: same thickness, same > 265 mbar WEP, marginally higher airflow
  (> 49 vs. 45 minimum L h⁻¹ cm⁻²), and **no oleophobic specification at all**.
  None of their listed Porex grades is oleophobic.

  That is precisely the substitution `PMV15T-REQUEST.txt` told Porex not to make.
  The Grade-8 treatment is the entire reason PMV15T was chosen: compost leachate
  carries surfactants and organic acids that wet plain hydrophobic PTFE, and the
  airflow difference is the signature of the coating that would be missing.
  A converter's public catalogue is not its full sourcing range, so this is a
  question rather than a verdict — but it must be asked before the referral is
  treated as a supply route.
- Ask ADDEV: can they supply **PMV15T specifically**, not PMV15 or a comparable
  vent grade; will they die-cut Ø27 mm at our volume; what is *their* MOQ, price
  and lead time; and can they supply lot documentation. If the answer is that
  they convert PMV15 only, the small-quantity route for the oleophobic grade
  does not yet exist and Gore MMS341 becomes the primary, not the challenger.
- The Gore MMS341 A/B arm gains weight. A single-source material behind a
  10,000-piece MOQ, from a vendor two weeks into a $9.25 bn integration, is not a
  supply position to design a sensor around without an alternative.

### Answered by Porex, 2026-08-27 [S14a]

- Construction: **sintered PTFE**, confirmed.
- Attachment: five endorsed methods, ultrasonic welding documented in detail
  [S15].
- Formats: master rolls 330 ± 5 mm on a 75 mm core, slit rolls, die-cut shapes.
- Application data: **none available.** "Daten zu Ihrem speziellen Anwendungsfall
  liegen uns momentan nicht vor." There is no O₂-diffusion figure to be had, so
  `D_eff` is ours to measure. Qualification step 1 is the only source of that
  number — it is not a ranking exercise that can be skipped.

### Sample received 2026-09-02

The free Porex sample arrived: **one rectangular sheet, A5 format (148 × 210 mm
nominal, unmeasured)**. Either dimension fits inside the 330 ± 5 mm master-roll
width [S14]. Everything else about the delivery is **unrecorded so far**
and must be filled in before the sheet is cut:

| Field | Status |
|---|---|
| Quantity of sheets | unrecorded |
| Lot / roll / order reference | unrecorded — the film itself carries no marking |
| Accompanying documentation (CoC, lot sheet, delivery note) | unrecorded |
| Which face was up in the packaging | unrecorded |
| Measured thickness against 0.18 ± 0.03 mm | not measured |
| Identity check (see below) | **not run** |

**Identity is not established by the delivery.** The plausible substitute,
PMV15 [S16], is visually indistinguishable — same 100 % PTFE, same 0.18 mm, same
> 265 mbar water-entry, same white sintered film — and differs only in the
Grade-8 oleophobic treatment, which is the whole reason this grade was chosen.
`PMV15T-REQUEST.txt` asked Porex explicitly not to substitute; that request is
not evidence that they did not. Run a treated/untreated screen before any coupon
enters qualification:

- Untreated PTFE wicks a low-surface-tension oil almost immediately; the treated
  grade beads it. Use the most aggressive liquid available — n-hexadecane or
  n-dodecane are AATCC TM 118 grades 3 and 5 and are real discriminators.
  Mineral oil (Nujol) is the scale's **grade 1** liquid, so beading it proves
  almost nothing.
- This is a **screen for the presence of the treatment, not an AATCC
  measurement**. It cannot confirm grade 8 and must not be recorded as if it
  had. A failure, however, is decisive: it means the referral risk in *Supply
  route* has already materialised, and Gore MMS341 becomes the primary material
  rather than the challenger.

Handling rules for this sheet, all of them one-way decisions:

- **Mark a face and an edge before the first cut.** If the treatment is
  one-sided the information is unrecoverable once the sheet is divided, and it
  decides which face goes wet-side. Mark a border strip that never becomes a
  coupon.
- **Reserve an unexposed control strip** (≈148 × 40 mm, about 19 % of the sheet)
  from the same lot, labelled and never cut into. Qualification step 4 compares
  2/6/12-week field coupons against exactly this.
- Gloves and a fresh blade or punch on a clean mat. Finger oils contaminate the
  oleophobic screen; sintered PTFE is a 0.18 mm depth film and a crushed edge
  matters where the coupon meets a compression-seal land. Store flat and sealed,
  away from oils, silicone and solvent vapour — including the ASA
  solvent-smoothing setup.
- **Do not pre-cut the full sheet.** Window area and `D_eff` trade against each
  other and the geometry is not frozen; step 1 is what pins `D_eff`. Cut only
  what step 1 consumes.

**The A5 sheet is a budgeted resource, not an abundant one.** Yield is roughly
**126 coupons at 15 × 15 mm** (a 10 mm window plus a 2.5 mm seal land) but only
**35 discs at Ø27 mm** — one year at the low end of the 30–80 disc annual
estimate, before qualification consumes any. Two consequences:

- The response-candidate geometry (two 10 × 10 mm coupons per probe) is roughly
  **3.6× more material-efficient** than the Rev-A Ø27 disc. That is not a reason
  to choose it, but it is a real cost difference to carry into the geometry
  decision while supply sits behind a 10,000-piece MOQ.
- **Request a second sheet from the same lot now**, while the Porex contact is
  warm and samples are still free against a postal address [S14a]. Weld and
  thermal-weld process development alone typically eats ten or more attempts,
  and steps 1–4 plus the known-bad bypassed coupon and the field sacrificials
  add up quickly. If this lot is exhausted mid-programme it cannot be
  re-bought — the MOQ is three orders of magnitude away and the distributor may
  carry only untreated PMV15 — and a replacement sheet from a different lot
  **breaks the same-lot control that step 4 depends on**.

Note that the datasheet declares samples "intended for evaluation purposes only
and not intended for specification" [S14]. Measurements from this sheet
characterise *this lot*; they do not become specification values, and the
production material from ADDEV must still be re-verified as the same grade.

### Head hardware sourced 2026-09-02

Three items for the printed-ASA head, researched in `tech/PROBE-CARRIER-SOURCING.md`
in the parent **farming** repository. **Identified and orderable; none ordered.**
InvenTree holds nothing on shelf or on order for any of them.

| Item | Part | Evidence status |
|---|---|---|
| Threaded insert, M2.5 | E-Z LOK **FL-M25-HI-CR**, stainless E-Z Sonic, flanged | bore Ø3.99 from E-Z LOK drawing D-S.113 Rev1; **depth 6.7 mm is inferred**, see below |
| Carrier O-ring | o-ring-stocks.eu **ORS116787**, EPDM 70 peroxide-cured, 24.0 × 1.5 DIN 3771 | vendor spec table + compound test report |
| PP rod for the carrier | Röchling **Polystone® P homopolymer** (PP-H), Ø40 stock art. 805216 | manufacturer TDS, PIM-ID 590980 |

Three findings that changed the design rather than merely supplying it:

- **The insert must be stainless, and that nearly did not exist.** Brass is the
  standard heat-set material and suffers ammonia stress-corrosion cracking; these
  inserts sit on the end face, outside the seal, in NH₃ condensate. Every European
  specialist checked — SPIROL, Böllhoff, Tappex, Inserco, Accu — makes stainless a
  special-order material only. The E-Z LOK US route is the one that works, with
  no EU distributor, a trade login required to buy direct, and five packs in stock
  at the only reachable reseller. **This is a sole source and it is fragile.** The
  stainless grade is also unstated by the manufacturer ("Steel – Stainless");
  either austenitic grade is immune to the ammonia mechanism, so the decision
  stands, but the grade is unverified.
- **Its Ø3.99 bore sets the head diameter**, via the bolt circle and SPIROL's boss
  rule — **46 mm**, not the 42 the placeholder Ø3.6 gave, and level with the
  written-off radial variant. It also grew the bolt circle past the carrier
  flange, and the flanged-only insert needs a counterbore or it holds the retainer
  off the face. Both are now gated by asserts in `cad/o2_probe_head_end.scad`.

  **That cost prompted a re-examination, and the insert is no longer the default.**
  The rule requiring metal threads — no sustained strain in plastic at 75 °C — was
  written when the screws clamped the seal. The radial O-ring removed that *for the
  carrier-to-head joint*.

  **Correction (2026-09-02, from an independent review): it did not remove the seal
  load entirely, and the ~6 N figure first recorded here was wrong.** The O-ring
  takes screw preload out of the carrier-to-head seal only.
  `cartridge_core_cuts_round()` still cuts a gasket pocket into the carrier's wet
  face — membrane thickness plus a 1.0 mm gasket at 25% compression — and the
  retainer lies directly over it, so those screws set the **membrane-perimeter
  gasket compression**. The ~6 N was the pressure force across a Ø16 window
  (265 mbar → 5.3 N), never a preload. Required preload is **unverified**: gasket
  material, hardness, compression force and minimum residual load are all unfixed,
  and sizing the screw needs them. Recorded as an open gap below.

  The re-examination's conclusion still holds, but on a narrower basis: the
  sustained strain is gasket compression in a printed boss, not the seal-clamping
  duty the metal-thread rule was written for. The default is therefore a
  **thread-forming screw for thermoplastics**
  (Delta PT / EJOT PT / Plastite, A2) straight into a printed boss, which drops
  the sole source, the counterbore and the
  heat-setting step beside the sealing bore. `fastening = "ptscrew" | "insert"`
  keeps both routes in one model, with the wall rule differing by mechanism:
  2.3 mm thermal for the insert, 1.45 mm hoop-stress for the screw. (Both walls are
  now measured to `well_d`, the bore the spigot actually seals into, not to
  `spigot_d`; the earlier figures were each 0.15 mm optimistic.) The trade
  accepted is finite re-insertion life in plastic — on a part that is printed, so
  a stripped boss is a reprint rather than a failure.
- **The O-ring size I specified does not exist.** 24.5 × 1.5 is unavailable in
  EPDM anywhere in the deepest catalogue found — that size exists only in FKM and
  FFKM, and fluoroelastomers are excluded precisely because ammonia attacks them.
  The design now uses the 24.0 that does exist, on a **Ø25.02** groove: 4.25 %
  install stretch, and 22.35 % squeeze once the stretch thins the cord.

  **Correction (2026-09-02): the tolerance chain behind those numbers was wrong
  twice, and the published data is worse than the guesses were.** It first counted
  only the well bore, then both surfaces, and in neither case the tolerance of the
  ring itself. The vendor publishes ±0.08 on a 1.5 mm cord (DIN 3771 / DIN ISO
  3601, archived under `tech/datasheets/probe-carrier/`), which alone spends 8.32
  of the 15 squeeze points the 15–30 % window allows. A reamed Ø27.3 H7 bore is
  +0.021/0 (ISO 286-2), five times tighter than the ±0.05 previously declared.
  Net: **a printed well no longer passes at all**, and the carrier groove must be
  either machined or paired with rings sorted by cord on receipt. See
  `cad/README.md`.

**Two evidence gaps, both deliberate and both open:**

1. **EPDM's ammonia compatibility is not verified.** EPDM was an input to the
   sourcing brief, not a conclusion drawn from a manufacturer chemical-resistance
   table — the public Parker material-selection page is too shallow and the
   handbook section was not opened. EPDM is the conventional choice for ammonia
   service and is expected to pass, but the entire carrier-to-head seal rests on
   it and expectation is not evidence. **Close this before ordering.**

   **Closed for ammonia, 2026-09-03.** The handbook section was opened: ORD 5700
   §VII rates EPDM 1 for ammonium hydroxide and anhydrous ammonia and 2 for hot
   ammonia gas, and rates FKM 4 on every ammonia row. See
   [Membrane perimeter gasket sourced](#membrane-perimeter-gasket-sourced-2026-09-03).
   **Still open on the organic-acid side**, where EPDM is rated 4 in hot lactic
   acid — which applies to `ORS116787` exactly as it does to the gasket.
2. **The thread-forming screw's pilot is not sourced.** `pt_pilot_d = 2.1` is a
   placeholder with no rationale — it was described here and in the CAD as "the
   conventional 0.75 × nominal", which is arithmetically false (2.1/2.5 = 0.84;
   0.75 × 2.5 = 1.875). PT-type pilots are brand-specific. The model echoes a warning on every render. This is not a
   detail: `pt_pilot_d` feeds `pt_seal_wall`, `bolt_r` and from there `head_od`,
   so a different vendor pilot moves the widest buried diameter. It moves `head_od`
   only, not the bolt circle — substituting `pt_seal_wall` into `bolt_r` cancels the
   pilot exactly. Measured: 2.10 → 2.25 holds the circle at Ø32.3 and takes the head
   from Ø40 to Ø42. The same gap
   covers the cap's `selftap_cap = 2.1` and the `m25_clear = 2.8` clearance hole,
   both declared defaults. Briefed as sourcing pass 2 in
   `tech/PROBE-SCREW-SOURCING-BRIEF.md`.
3. **The insert hole depth is cross-manufacturer inference.** E-Z LOK publishes no
   hole depth anywhere — dimensional drawing, installation page and drill/tap
   charts were all checked. The 6.7 mm comes from SPIROL's design-guide rule
   (insert length + 2 thread pitches) applied to E-Z LOK's own 5.74 mm body. The
   model echoes a warning; verify it on a test coupon before a print run.

4. **The membrane gasket's required preload is unknown**, and it is what the
   retainer screws must deliver. Gasket material, hardness, compression-force curve
   and minimum residual load are all unfixed. Until they are, no screw can be sized
   on anything but geometry.

   **Partly answered 2026-09-03, and the question was ill-posed.** Material and
   hardness are settled (peroxide-cured EPDM, 70 Shore A). The load is bracketed
   by calculation at **38–115 N per screw**, not published anywhere, with a named
   bench measurement to close it. But the preload is indeterminate as drawn
   regardless: a flat washer sits in a near-closed pocket and cannot reach 25 %
   compression without extruding into the gas window. **Resolved by dropping the
   washer for an O-ring face seal** (`ORS116731`, 17.0 × 1.0, same compound as
   the carrier ring) in a Ø17.0/Ø19.58 groove — the washer's 38–115 N/screw
   bracket does not transfer to it, so the screw is still unsized. See
   [Membrane perimeter gasket sourced](#membrane-perimeter-gasket-sourced-2026-09-03).

### Membrane perimeter gasket sourced 2026-09-03

Answers the sourcing brief in
[GASKET-SOURCING-BRIEF.md](GASKET-SOURCING-BRIEF.md). **Compound recommended, no
part ordered.** The brief's central question — whether EPDM's ammonia
compatibility survives scrutiny — is answered **yes, with one named exception**;
and the work turned up a geometry defect that has to be fixed before any gasket
can be specified at all.

#### The geometry blocks the specification (fix this first)

`cartridge_core_cuts_round()` cuts **one** pocket, Ø`coupon_d + 0.3` = **21.3**,
holding membrane *and* gasket. The gasket is Ø17.0/Ø21.0 × 1.0, so it sits in that
pocket with **0.15 mm of radial clearance** and a free bore. Rubber is
substantially incompressible (bulk modulus ~2 GPa against a shear modulus of a few
MPa), so compressing it 25 % does not reduce its volume — it moves it.

| quantity | value |
|---|---:|
| gasket volume, Ø17/Ø21 × 1.0 | 119.4 mm³ |
| volume displaced at 25 % compression | 29.8 mm³ |
| room available outward, to the Ø21.3 pocket wall | 7.5 mm³ |
| therefore forced **inward, into the bore** | 22.4 mm³ |
| resulting bore | **Ø15.84** |

The bore closes past the **Ø16.0 gas window**. Two consequences, both fatal to the
brief as written:

- The gasket stops sealing *beside* the gas path and starts covering it — exactly
  the failure the brief's "do not propose a bore ≤ 16.0 mm" rule exists to prevent.
  The rule was applied to the *free* bore; it was never applied to the bore
  **after compression**.
- Because the pocket is very nearly a closed die, the load needed to reach 25 %
  is not a material property of the gasket at all — it is set by how hard the
  rubber is being asked to extrude. **This is why brief §4's "minimum residual
  sealing load" has no answer as drawn**: the question is ill-posed until the
  rubber has somewhere to go.

The largest compression this pocket permits before the bore starts closing is
**7.7 %** — well under the 15–30 % a solid-rubber face seal normally needs.
Geometry must change; the gasket cannot be chosen around it.

**The fix adopted is to stop using a flat washer at all** — see
[The seal is an O-ring](#the-seal-is-an-o-ring-supersedes-the-cut-washer-shortlist)
below. A torus in a groove has void by construction, so the displacement problem
does not arise. Two flat-washer fixes were considered and rejected:

- *Open the pocket* to Ø22.4 (`coupon_d + 0.3` → `coupon_d + 1.4`; threshold is
  Ø22.17). Gas-volume cost zero, because the relief is radially outboard of the
  sealing band. But it costs the membrane its location fit (0.15 → 0.70 mm of
  radial float) and leaves an annular void under the membrane edge that can hold
  condensate.
- *Shrink the gasket OD* to ≤ Ø20.2. Works arithmetically, but drives the seal
  land to ≤ 1.6 mm and trips `assert(land >= 2.0)`.

#### EPDM survives, with one exception

Primary source: **Parker O-Ring Handbook ORD 5700**, © 2021, Section VII
compatibility tables. Ratings are 1 satisfactory, 2 fair (usually OK for a static
seal), 3 doubtful, 4 unsatisfactory, x insufficient data.

| medium | EPDM | VMQ silicone | FKM | NBR |
|---|:--:|:--:|:--:|:--:|
| Ammonia, gas, cold | 1 | 1 | 4 | 1 |
| **Ammonia, gas, hot** | **2** | x | 4 | 4 |
| Ammonium hydroxide, 3 molar | 1 | 1 | 3 | 1 |
| Ammonium sulfide | 1 | x | 4 | 1 |
| **Hydrogen sulfide, wet, hot** | **1** | **3** | 4 | 4 |
| Acetic acid, 5 % / 30 % / glacial | 1 | 1 | 2 | 2 |
| Propionic acid | 1 | 2 | 3 | 3 |
| Formic acid | 1 | x | 4 | x |
| Butyric acid | 2 | x | 2 | 4 |
| Lactic acid, cold | 1 | 1 | 1 | 1 |
| **Lactic acid, hot** | **4** | 2 | 1 | 4 |
| Steam below 400 °F | 1 | 3 | 4 | 4 |

Three things fall out of this, and the third is the finding:

1. **The fluoroelastomer exclusion is now sourced, not assumed.** FKM rates 4 on
   every ammonia row in the table. `MEMBRANE.md` and the brief already excluded
   FKM/FFKM; that decision now rests on a primary rather than on recollection.
2. **Silicone is worse than EPDM here, not better.** VMQ rates 3 (doubtful) on all
   four hydrogen-sulfide rows and x on hot ammonia gas. The brief asked for
   scepticism about silicone's hot-wet-alkaline stability; the answer is that it
   fails earlier than that, on H₂S. Silicone is out.
3. **EPDM's one weakness is hot lactic acid — rated 4.** Every other compost
   medium is 1 or 2. Lactic acid is a genuine compost constituent (a signature of
   anaerobic pockets and the early mesophilic phase), so this is not hypothetical
   in a pile with poor aeration. Parker does not define "hot", so the temperature
   at which the rating flips from 1 (cold) to 4 is **unverified** and could lie
   either side of 75 °C. *This is the single strongest argument against the
   recommendation below.*

Note what the table can and cannot do. Trelleborg's materials chemist Lacy Heyduk,
writing on compatibility charts: they "are most useful to determine the generic
susceptibility of general classes of polymers", are compiled from single-chemical
immersion specimens, and "most charts just list results from room-temperature
exposure"; determining a specific material–chemical pair "requires more research",
and an engineered grade may pass where the generic type fails. So the table above
reliably rules FKM and silicone **out**; it does not by itself qualify a specific
EPDM compound **in**. It also tests one chemical at a time — the mixed
NH₃ + H₂S + organic-acid + wet/dry duty is not represented anywhere in it.

#### The mechanical numbers brief §4 asked for

**§4.3 Hardness — answered.** 70 ± 5 Shore A (ASTM D2240) for Freudenberg
EP703901; the incumbent O-ring compound (Techniparts 127019011) is quoted as
70 ± 5 **IRHD** (ASTM D1415), which is a different scale and should not be
silently equated with Shore A.

**§4.4 Compression set — answered, better than expected.** Peroxide-cured EPDM,
DIN ISO 815 A:

| compound | 22 h / 100 °C | 70 h / 100 °C | 22 h / 125 °C | 22 h / 150 °C |
|---|:--:|:--:|:--:|:--:|
| Freudenberg EP703901 (peroxide) | **8 %** | 12 % | 10 % | — |
| RESOGOO E 9614 sheet (peroxide) | 25 % | — | — | — |
| Techniparts 127019011 (peroxide, the O-ring compound) | — | — | — | 19 % |

**And the long-duration answer, which no datasheet carries.** Anja Kömmling's TU
Berlin dissertation (BAM, 2017) aged EPDM, HNBR and FKM O-rings **at 25 %
compression** — our exact squeeze — at 150, 125, 100 and **75 °C** for up to two
years, measuring compression set, compression force *and* leak rate. Its EPDM is
peroxide-cured and carbon-black filled. Results:

- Failure was defined at the point where a *slightly unloaded* seal began to leak,
  which corresponded to a compression set of ~83 %; a conservative life criterion
  of **80 % DVR** was adopted.
- Measured: 80 % DVR at ~65 days at 150 °C, ~190 days at 125 °C.
- Extrapolated by time–temperature superposition: **3.6 years at 100 °C,
  14.6 years at 75 °C**, 48.6 years at 60 °C, with a cumulative error up to ±20 %.
- **The important qualitative result:** statically clamped O-rings showed *no
  gradual rise* in leak rate — they stayed tight until very advanced degradation,
  and then failed. Failure appeared *earlier* only in the test where the seal is
  slightly relieved during measurement, because that demands elastic recovery.

That last point matters more than the number. Our joint is thermally cycled and
wet–dry cycled in a printed boss that will itself creep, so the seal *is*
repeatedly slightly unloaded. The dynamic-recovery criterion is the applicable
one, not the static one — and "it was fine last time we checked" is exactly the
signature this failure mode produces.

Caveats, all load-bearing: that ageing is **thermo-oxidative in air**, not in
NH₃/H₂S/organic-acid condensate; it is a different compound from any proposed
here; and O-rings are not flat washers. It bounds the *thermal* life at 75 °C and
says nothing about the chemical one.

**§4.1 Minimum residual sealing load — no published value, and here is why.** No
manufacturer publishes a minimum seating stress for an elastomeric face seal of
this size; the quantity is joint-specific. The best available substitute is
Kömmling's criterion above, which expresses end-of-life as **retained
deformation (80 % DVR)** rather than as retained stress — a form our design can
actually be checked against, because DVR is measurable on a recovered gasket.

**§4.2 Compression modulus — calculated, not published, and stated as such.**
Nobody publishes a compression–force curve for a die-cut washer, because it
depends on shape factor rather than on the compound alone. Ours:

- Shape factor `S = (OD − ID) / 4t = (21.0 − 17.0) / 4.0 = **1.00**`.
- Freudenberg publishes a 100 % modulus of 4.5 MPa (ISO 37) for EP703901.
  Neo-Hookean `σ = G(λ − λ⁻²)` at λ = 2 gives `G = 4.5 / 1.75 = 2.57 MPa`,
  hence `E ≈ 3G = 7.7 MPa`.
- Gent–Lindley apparent modulus `Ea = E(1 + βS²)` (β = 2 for a bonded circular
  section, lower for carbon-black-filled rubber). Our washer is **unbonded**, so
  the true value lies between the free-slip and fully-bonded bounds:
  `Ea = 7.7 … 23.1 MPa`.
- Over the 119.4 mm² seal band at 25 % compression: **σ ≈ 1.9–5.8 MPa**,
  **F ≈ 230–690 N total, 38–115 N per screw** across six screws.

Tag that bracket honestly: *calculated*, from a vendor-specification modulus, via
a small-strain relation applied at 25 % strain where rubber is already stiffening
nonlinearly, and it presumes the pocket has been opened so the rubber is not
extruding. It is an order-of-magnitude sizing input for the thread-forming screw,
**not** a preload specification. A factor of three separates its bounds.

**The measurement that would settle §4.1 and §4.2 together**, and it is cheap:
compress an actual candidate washer between two flat platens in the bench press
with a load cell, recording force against displacement to 40 %; that yields the
real compression–deflection curve, the load at 25 %, and the bonded/unbonded
question at once. Then hold a set at 75 °C under 25 % compression and measure
DVR per ISO 815 at intervals, in air and in an NH₃/H₂S/organic-acid condensate,
to get the chemical life the literature does not provide.

#### The seal is an O-ring (supersedes the cut-washer shortlist)

**Previous conclusion, now withdrawn:** a die-cut washer in peroxide-cured EPDM
sheet (RESOGOO E 9614), with a DXF-cut 50 Shore A ring as the prototype
stand-in. That shortlist is kept below only as the fallback if the O-ring fails
its one open risk.

**What changed.** o-ring-stocks.eu's own catalogue carries a dense metric grid of
**peroxide-cured EPDM 70 Shore A** O-rings — 1 mm ID steps, cords 1.0/1.5/2.0,
all in stock at €0.15–0.27 — and the small sizes carry **material number
127019011**, which is the *same compound* as the carrier's radial ring
`ORS116787`. The compound test report already archived under
`tech/datasheets/probe-carrier/` therefore covers **both seals**.

| item | part | ID × cord | stock | price |
|---|---|---|---:|---:|
| **membrane perimeter seal (new)** | **ORS116731** | **17.0 × 1.0** | 1268 | €0.22 |

> **SUPERSEDED 2026-09-08 — this row describes the CONE bed, which is no longer
> built.** `d1c955a` moved the bed into the printed retainer, where a 1.0 cord
> cannot hold 15–30 % squeeze at any printable layer height: on the 0.12 grid one
> layer is 12 of the 15 available squeeze points, and 0.08 is this printer's
> minimum for a 0.4 nozzle. The bed ring is now **17.0 × 2.0**, ordered as eBay
> `157712596230` (EPDM-Peroxidvernetzt FDA, cure declared, compound not); the
> documented equivalents are `ORS116734` (17 × 2.5) and `ORS116732` (17 × 1.5),
> both material `127019011`. Reasoning and the sorting debt that comes with the
> 2.0: `cad/PRINTING-HEAD-END.md`, *The ring: 17.0 × 2.0, ordered*.
| — cord 1.5, *does not fit* (see below) | ORS116732 | 17.0 × 1.5 | 5487 | €0.20 |
| carrier radial seal (unchanged) | ORS116787 | 24.0 × 1.5 | — | — |

All three: EPDM 70 Shore A, peroxide-cured, DIN 3771, material 127019011,
FDA/EC1935-2004/NSF 61.

**One part cannot serve both seals, and that is geometry, not sourcing.** The
membrane seal nests *inside* the carrier that the other ring seals: the carrier
ring's ID is set by the Ø27.3 well, the membrane ring's OD must fit inside the
carrier's own wall. They are separated by the carrier wall thickness by
construction. Freeing the geometry does not change this.

**Why cord 1.0 and not 1.5.** Cord 1.0 at 25 % squeeze compresses to **0.750 mm
— exactly the `gasket_gap` the 1.0 mm sheet gave** — so `pocket_depth` stays
0.930 and the bore stays Ø17.0 beside a Ø16.0 window.

**Gas volume, measured on the mesh, not reasoned.** I first wrote that the change
left the connected volume "unchanged at 4849 mm³". That was an inference and it
was wrong. `make head-end-provisional` measures the `cavity` mesh, and:

| build | connected volume | margin to 5.0 cm³ |
|---|---:|---:|
| flat washer (HEAD, baseline) | 4849.2 mm³ | 3.0 % |
| **O-ring, cord 1.0 (this change)** | **4807.8 mm³** | **3.8 %** |

The O-ring **frees 41.4 mm³** — the groove is Ø19.58 where the washer pocket was
Ø21.3, and the disc seat above it is only 0.18 deep instead of 0.93. So the
change buys margin rather than spending it. (The repo's own rule applies: the
budget is a property of the mesh, so measure what was built.)

**Cord 1.5 is not a drop-in fallback**, which is also a measured result rather
than an estimate — two asserts fire:

1. `membrane_ledge` — cord 1.5 needs a Ø20.84 groove, leaving **0.23 mm** of
   ledge inside the Ø21.3 disc pocket. It needs `land ≥ 2.77`.
2. Raising `land` to 2.8 then grows the carrier, and the *carrier* ring's
   install stretch goes to **6.84 %, over its 5 % rule** (`o2_probe_head_end.scad`
   assert).

So cord 1.5 perturbs the head diameter chain and the carrier seal, and its gas
volume was not measured because the configuration will not render. **Cord 1.0 is
the only size that fits the existing geometry.** If the cold-flow risk below
turns out to be real, going to cord 1.5 is a carrier redesign, not a swap.

**Do not use 16 × 1.0** (`ORS116724`): its bore sits exactly on the window and
breaks the seal-beside-the-gas-path rule.

**CAD consequence — implemented.** In `cad/membrane_cartridge_common.scad`:

- new `mem_oring_cs = gasket_t` (cord ≡ free gasket thickness, so `gasket_gap`
  and `pocket_depth` are shared with the square bench fixture unchanged) and
  `mem_oring_fill = 0.80`;
- new `groove_od()`, `oring_vol()` and `membrane_ledge()`, giving a groove of
  **Ø17.0 / Ø19.577 × 0.75 deep** at 80 % fill, with a **0.862 mm** membrane rim
  ledge (both echoed by the model);
- `cartridge_core_cuts_round()` now cuts a membrane disc seat (Ø21.3 ×
  0.18 deep) over an O-ring groove, instead of one Ø21.3 × 0.93 pocket;
- a new assert that the ledge stays ≥ 0.5 mm, so the membrane rim can never end
  up unsupported over the groove;
- `assert(land >= 2.0)` keeps its threshold but changes meaning — `land` now
  sizes the membrane disc and its ledge, not a compression band.

Retention is on the groove's **outer** wall. The inner wall would be the flare
cone, only ~Ø16.5 at that depth and far too thin to print; the old Ø21.3 pocket
left the ring at 46 % fill, free to roll inward during assembly.

**Load.** The washer bracket (38–115 N/screw) **does not transfer** — an O-ring
seals on a line at far lower load, which is the point. The membrane-seal preload
is still unmeasured; the bench compression test named above is now easier,
because the part is a stock O-ring rather than a cut coupon.

#### Recommendation

**`ORS116731` — O-ring 17.0 × 1.0, EPDM 70 Shore A peroxide, material 127019011,
o-ring-stocks.eu, €0.22, in stock** — in a Ø17.0/Ø19.58 × 0.75 groove. Reasons:
EPDM is the only family rating 1 or 2 across ammonia, ammonium hydroxide, wet hot
H₂S, acetic, propionic and formic acid at once; peroxide cure buys the
compression set the joint depends on; it is the *same compound as the carrier
ring*, so one test report and one compression-set assumption cover the whole
head; it is a stocked standard part rather than a cut part at DIN 7715-5 P2; and
and it *frees* 41.4 mm³ of gas volume (measured), taking the margin from 3.0 % to 3.8 %.

**The single strongest argument against it** is no longer the sourcing but the
counterface: **an O-ring loads the 0.18 mm porous sintered-PTFE membrane in line
contact**, where the washer spread it over a 2 mm band. PTFE cold-flows under
concentrated stress at temperature and PMV15T is porous, so the ring may emboss
the membrane and the seal load then relaxes — which is precisely the failure mode
this whole section is trying to avoid. **This risk is absent in the production
route**, where PMV15T is welded into a PP cartridge and the joint becomes
PP-against-ASA, rigid on rigid. It applies only to the compression-only ASA
prototype, and it is the thing to test there.

The lactic-acid finding stands unchanged and remains the chemical argument
against EPDM in either form.

#### Fallback: the cut-washer shortlist (superseded, kept for the record)

| # | product | compound | hardness | temp range | CS (ISO 815) | price / MOQ / lead time |
|---|---|---|---|---|---|---|
| 1 | **RESOGOO EPDM E 9614** (art. 0153) sheet, cut to ring | EPDM, **peroxide-cured**, VW 2.8.1 G70 | 70 ± 5 Shore A | **−40 … +120 °C** | 25 % @ 22 h/100 °C | not published — quote required |
| 2 | **fugendichtband24** art. 5023 DXF-1 | EPDM, **cure not stated, no TDS** | 50 Shore A | not stated | not stated | **from €8.75 incl. VAT**, single pieces, 3–4 days |
| 3 | **ElastX24 EPDM 65** | EPDM, **cure not stated**; density 1.35 ⇒ heavily filled | 65 ± 5 Shore A | **−30 … +90 °C** | 30 % | account-gated, not obtained |
| — | **Freudenberg EP703901** | EPDM, peroxide-cured | 70 ± 5 Shore A | — | **8 % @ 22 h/100 °C** | **moulded-part compound; not sold as sheet or in single-digit quantities** |

EP703901 remains the benchmark that proves peroxide-cured EPDM can do this duty,
and remains unavailable in prototype quantities. If the O-ring's line contact
does damage the membrane, route 1 is the fallback — with the pocket opened to
Ø22.4 as described above, which that route still requires.

#### What this does and does not close

- **Brief §4 items 1–2 are not closed by a published number and cannot be.** They
  are answered with a calculated bracket and a named bench measurement. The screw
  can be sized provisionally against 38–115 N per screw; it should not be frozen
  against it.
- **Gap 1 in [Head hardware sourced](#head-hardware-sourced-2026-09-02) — "EPDM's
  ammonia compatibility is not verified" — is now closed for ammonia**, by
  ORD 5700 §VII: EPDM rates 1 for ammonium hydroxide and anhydrous ammonia and 2
  for hot ammonia gas, and this covers `ORS116787` as well as this gasket, as the
  brief anticipated. It is **not** closed for the organic-acid side.
- The **`land >= 2.0` assert and the `coupon_d + 0.3` pocket clearance now
  interact**, and the CAD does not know it. Whatever the pocket becomes, a
  compression-flow check belongs beside the existing `dry_side_gap()` assert:
  the free bore is checked, the compressed bore is not.

### Still open with Porex

- Compatibility of the Grade-8 treatment with NH₃-rich condensate, organic acids
  and H₂S at up to 75 °C, through repeated wet–dry cycles. This is the one
  question that can still disqualify the material, and it is unanswered.
- Recommended cleaning method for fouled discs.
- Lot-level airflow, water-entry and oleophobic test documentation — given that
  the datasheet disclaims per-roll verification, ask what *can* be certified.
- Whether Porex remains the contact after the Parker Hannifin close, and whether
  material or process changes and discontinuation are notified.

Ask Gore for MMS341 samples plus numeric permeability/diffusion, water-entry,
thickness, maximum continuous temperature and mounting data. PMV15T remains the
baseline unless MMS341 produces materially better retained wet/fouled response
without sacrificing mechanical integrity.

## Evidence limitations and decision boundary

- No direct compost-pile comparison of these exact membrane grades was found.
- No vendor publishes an in-compost service-life claim for the shortlisted
  material.
- The full RSC version of Smith et al.'s biofouling article was paywalled; the
  corresponding author's full University of Glasgow thesis supplied the
  inspected primary methods and results. Treat the thesis and article as one
  overlapping evidence set, not independent corroboration.
- Gore does not publish enough numeric MMS341 data for a paper-only comparison
  with PMV15T.
- PTFE chemical compatibility does not automatically extend to an oleophobic
  surface treatment, backing, adhesive or housing seal.
- The ASA temperature bracket comes from three vendor filament sheets [S17–S19],
  none of them the spool we will actually print with, and two of the three are
  product pages rather than signed TDSs. Re-check Tg and both HDT rows against
  the purchased filament's own sheet before the enclosure is frozen, and treat
  the numbers as bulk-moulded properties: a printed part is anisotropic and
  weakest in Z, and no vendor publishes creep data for it.
- Water-entry/IP results demonstrate liquid-ingress resistance in a qualified
  housing; they do not demonstrate retained O₂ response beneath a liquid or
  biofilm layer.

The production decision is therefore:

> Select the assembly that retains acceptable O₂ step response after real
> condensate, particulate and field-fouling exposure. Prefer PMV15T when results
> are equivalent because it has the stronger public minimum specification;
> prefer MMS341 only if its measured sensor response advantage survives ageing.

## Sources

All web sources were accessed and live-browser validated on 2026-08-22. PDF
tables used for the comparison were also render-checked.

- **S1 — Porex:** [PMV15T product specification](https://www.porex.com/product/virtek-ptfe-material/). Current HTML; inspected in full.
- **S2 — Porex:** [Gas sensor vents and filters](https://www.porex.com/industrial/gas-sensor-vents-and-filters/). Current HTML; inspected in full.
- **S3 — Porex:** [PTFE membrane chemical-compatibility chart](https://cdn.pathfactory.com/assets/10563/contents/519802/2460cfad-e97c-4a04-8c65-0f55ab5a4c8c.pdf). ©2022 PDF; inspected and render-validated. Chart is vendor screening guidance and requires application validation.
- **S4 — Porex:** [ePTFE membrane support-backing guide](https://learn.porex.com/ip-rated-protection-vents/eptfe-membrane-support-backing-guide). ©2024 one-page guide; inspected and render-validated.
- **S5 — W. L. Gore:** [GORE MEMS Membranes for Sensors datasheet](https://www.gore.com/sites/default/files/resources/pdf/2026-06/gore-mems-sensors-167-datasheet-en.pdf). `PTV-167-R1-DSH-EN-MAR26`; inspected and render-validated.
- **S6 — W. L. Gore:** [GORE Pressure Vents datasheet](https://www.gore.com/sites/default/files/resources/pdf/2026-06/gore-pressure-vents-datasheet-us.pdf). Current publisher PDF; product table inspected and render-validated.
- **S7 — Donaldson:** [Tetratex ePTFE membrane media](https://www.donaldson.com/en/products/eptfe-membrane-media/). Current HTML; inspected in full.
- **S8 — Donaldson:** [Press-fit vents](https://www.donaldson.com/en/products/venting/press-fit/). Current HTML; inspected in full. Exact material data are available only on request.
- **S9 — Porex:** [Difference between expanded and sintered PTFE](https://www.porex.com/blog/what-is-the-difference-between-eptfe-and-sintered-ptfe/). 2024-04-24 vendor technical article; inspected in full.
- **S10 — Porex:** [Porex Virtek PTFE hydrophobic membrane portfolio](https://www.porex.com/porous-polymers-technologies/porous-membranes/ptfe-hydrophobic-membranes/). Current HTML product table; inspected in full.
- **S11 — Smith, M. J. (2007):** [*The use of hydrogels to prevent biofouling on underwater sensors*](https://theses.gla.ac.uk/2541/), PhD thesis, University of Glasgow, Chapters 6–7. Full authorised repository PDF inspected; relevant pages render-validated. Related article DOI: [10.1039/B714187B](https://doi.org/10.1039/B714187B), abstract inspected, full publisher version paywalled.

Added 2026-08-26 (see [MEMBRANE-RESEARCH-2026-08-26.md](MEMBRANE-RESEARCH-2026-08-26.md)):

- **S12 — Porex:** [Porex Virtek® PTFE Hydrophobic Membrane portfolio](https://www.porex.com/porous-polymers-technologies/porous-membranes/ptfe-hydrophobic-membranes/). Current HTML; all four product/technology tables and the sintered/expanded prose inspected in the live DOM. Source of the sintered-vs-expanded classification, the "No support required" row, the max-operating-temperature column, and the PMA oleophobic line. Supersedes the 2019 brochure's numbers where they disagree.
- **S13 — Porex:** [Electrochemical Gas Sensor Solutions brochure](https://www.porex.com/wp-content/uploads/2020/01/Porex-Brochure-Electrochemical-Gas-Sensor-Components.pdf), ©2019, doc `PX-EL-BR-190528-1`. Inspected in full; text layer extracted and cross-checked against S12. **Cite only for its qualitative sintering/scrim/absorbing-filter statements** — its PMV10 and PMG20 numbers are superseded by S12.

Added 2026-08-27 (Porex e-mail, Porex application engineering, with two attachments):

- **S14 — Porex:** *POREX® Virtek™ PTFE Materials — Material Datasheet, PMV15T*, doc `CON-002454 Ver. 5`, Porex Technologies Ltd, Merlin House, Alness Point Business Park, Alness, Scotland IV17 0UP. Archived at [`vendor/porex-PMV15T-datasheet-CON-002454-Ver5.docx`](vendor/porex-PMV15T-datasheet-CON-002454-Ver5.docx), SHA-256 `beef06610d75712662df426b67f4dce3349774fe044bf4cab9a5d2e04165e2ef`. Full text extracted from the OOXML part; supersedes S1 for all specification values. Carries the QC-method, representative-sample and not-for-specification disclaimers quoted above.
- **S14a — Porex:** e-mail from Porex application engineering, 2026-08-27, in reply to our PMV15T enquiry. Load-bearing statements: PMV15T is sintered PTFE; MOQ 10,000 pieces or two master rolls; small quantities via ADDEV Materials Parafix; free sample against a postal address; no application-specific data available.
- **S15 — Porex:** *How to Ultrasonically Weld PTFE Protection Vents*, technical brief, ©2019, doc `PX-EL-TB-19530-1`. Archived at [`vendor/porex-ultrasonic-welding-PTFE-vents-PX-EL-TB-19530-1.pdf`](vendor/porex-ultrasonic-welding-PTFE-vents-PX-EL-TB-19530-1.pdf), SHA-256 `0a301572ec622ff8045302599baac72492f45e09d332848ad080934393f0d2fb`. Text layer extracted in full. Source of the no-support claim, the ePTFE-fragility contrast, and the substrate constraint (good flow, melting point below 260 °C). Marketing document for the Virtek line — its comparative claims about ePTFE are the vendor's own and are not independently verified here.

- **S16 — ADDEV Parafix (Parafix Tapes & Conversions Ltd, Lancing, West Sussex):** [non-adhesive vent material](https://parafix.com/product-groups/venting-materials/non-adhesive-vent-material/) and [Porex material PMV15](https://parafix.com/product/porex-material-pmv15-v2/), both retrieved 2026-08-27. Site search for `PMV15T` returned "0 items matching your criteria"; a search for `Porex` returned MD10L, MD22, PMV15 and the PMV30C/I/N/W disc family. The PMV15 page gives 0.18 mm, 100 % PTFE, airflow > 49 L h⁻¹ cm⁻² at 70 mbar, water intrusion > 265 mbar, IP67, filtration > 99.99 % at 0.4 µm, −40 to 260 °C, no oleophobic row. Public catalogue only — not a statement of what the converter can source.

Added 2026-09-02 (enclosure-material decision; filament property bracket):

- **S17 — BigRep:** [ASA filament product/specification page](https://bigrep.com/filaments/asa/), retrieved 2026-09-02. WebFetch returned HTTP 403 (Cloudflare); a UA-corrected `curl` on the first ladder rung returned the substantive page, and the thermal rows were extracted from the served HTML text: `HDT A - 1.8 MPa (ISO 75) 86 °C`, `HDT B - 0.45 MPa (ISO 75) 94 °C`, `Glass Transition Temperature (Tg) (DSC) 105 °C`. **Not render-validated in a live DOM**, and a vendor product page rather than a signed TDS. Internally coherent (both HDT values below Tg).
- **S18 — 3DXTech / 3DXMAX ASA:** [technical data sheet republished on the Rev1 Tech support portal](https://support.rev1tech.com/portal/en/kb/articles/technical-data-sheet-3dxmax-asa-3d-printing-filament), retrieved 2026-09-02 via WebFetch markdown conversion. Rows used: `Glass Transition Temperature (Tg), DSC, °C, 105` and `Deflection Temperature at 0.45 MPa (66psi), ISO 75, °C, 95`. **Second-hand host** — a reseller's knowledge base, not the manufacturer's own document — and not render-validated. No 1.8 MPa row published.
- **S19 — Polymaker:** [Polymaker™ ASA technical data sheet](https://wiki.polymaker.com/polymaker-products/more-about-our-products/documents/technical-data-sheets/abs-asa/polymaker-tm-asa), retrieved 2026-09-02 via WebFetch markdown conversion; not render-validated. Gives Tg 98 °C (DSC), Vicat 105 °C (ISO 306), HDT 103 °C at 0.45 MPa and 100 °C at 1.8 MPa (ISO 75). **Cited only as the outlier**: an HDT at 1.8 MPa above the sheet's own Tg is not physically sensible for an amorphous polymer, so no design value is taken from it.

### Research search record

Discovery and challenge searches used the following exact queries:

- `site:gore.com protective vents ePTFE oleophobic membrane water entry pressure datasheet`
- `site:donaldson.com venting ePTFE membrane oleophobic water entry pressure datasheet`
- `site:porex.com PTFE membrane hydrophobic oleophobic vent water intrusion pressure datasheet`
- `ePTFE membrane surfactant wetting biofouling gas diffusion oxygen sensor compost hydrophobic`
- `site:porex.com PMV15T oleophobic AATCC 118 Grade 8 support backing`
- `site:gore.com oleophobic oil rating 8 vent AATCC 118`
- `site:porex.com hydrophobic membrane surfactant low surface tension wetting oleophobic`
- `Effects of marine biofouling on gas sensor membrane materials DOI`
- `site:porex.com/industrial gas sensor vents filters Porex Virtek PMV15T`
- `site:porex.com ePTFE membrane support backing guide`
- `site:porex.com PMV15T sample membrane sheet Europe distributor`
- `ePTFE oxygen sensor membrane diffusion delay oleophobic response time study`
- `Effects of marine biofouling on gas sensor membrane materials PDF -researchgate -rsc.org`
- `b714187b pdf repository`
- `M. J. Smith gas sensor membrane materials pdf`
- `site:repository.* Effects of marine biofouling`
- `PMV15T failure oil wetting oleophobic ePTFE membrane gas sensor`
- `oleophobic ePTFE membrane gas diffusion slower response sensor`
- `hydrophobic oleophobic vent compost leachate fouling membrane`
- `sintered PTFE versus ePTFE gas sensor diffusion membrane`
- `site:porex.com sintered PTFE hydrophobic membrane gas sensor oleophobic airflow water entry pressure`

The challenge searches strengthened the mechanical case for sintered PTFE and
the fouling risk, but did not identify a better exact, publicly specified
oleophobic baseline than PMV15T.

## Source access log — gasket sourcing pass, 2026-09-03

Browser surface: Playwright MCP, Chrome/152.0.0.0 (plain-Chrome UA, no
`HeadlessChrome`), proven by navigating `about:blank` and reading the DOM before
any fetch. Archive: `tech/datasheets/probe-gasket/` in the parent **farming**
repository. Copyrighted vendor handbooks and the open-access thesis are recorded
as pointers with hashes rather than committed, on size grounds.

| # | document | evidence state | attempt history | route | validation | load-bearing |
|---|---|---|---|---|---|---|
| G1 | Techniparts/o-ring-stocks.eu **material test report 127019011**, EPDM 70 peroxide, rev 3, 2021-03-05. On disk: `tech/datasheets/probe-carrier/techniparts-epdm70-peroxide-127019011-material-test-report.pdf`, sha256 `9ea8816f…c92864` | **inspected** (1 p.) | task-local, already archived 2026-09-02 | raw text (`pdftotext -layout`) | validated (single page, self-consistent) | yes |
| G2 | **Parker O-Ring Handbook ORD 5700**, © 2021 Parker Hannifin, 292 pp. Retrieved `https://nianticseal.com/wp-content/uploads/2024/04/ORD-5700.pdf`, sha256 `01fe9293…4a8ba9` | **partial** — §VII fluid tables pp. 164–210, §2.4.6, §2.4.11 | curl rung 1 → 200, `application/pdf`, 9 754 056 B, `%PDF-1.6`. Identity reconciled against `parker.com` catalogue page (see G3) | raw text (`pdftotext -bbox`), column mapping derived per page from rotated header x-centres | **validated** — rendered pp. 164 & 188 at 200 dpi and read visually; a first pass using one global column mapping was wrong (gave EPDM 4 for steam) and was corrected | yes |
| G3 | ORD-5700 as currently published by Parker, `https://www.parker.com/content/dam/Parker-com/Literature/O-Ring-Division-Literature/ORD-5700.pdf` | **metadata only** | curl rung 1 → **403 (blocked, not absent)**; browser rung 4 same-origin fetch → 200, `application/pdf`, 29 925 776 B, `%PDF-1.7`. Embedded-asset XMP dates 2006–2008 ⇒ **an earlier manifestation than G2**, not a newer one | raw text (byte-level metadata only) | n/a | no — used only to establish that G2 is the later edition |
| G4 | **Freudenberg Sealing Technologies, Technisches Datenblatt EPDM EP703901**, Änderungsindex 3, 2022-11-09. Archived, sha256 `07ac41e8…226ba8` | **inspected** (p. 1 of 5; the ASTM/ISO property block) | curl rung 1 → 200, 213 255 B | raw text | validated | yes |
| G5 | **Kömmling, A., *Alterung und Lebensdauervorhersage von O-Ring-Dichtungen*, Dissertation, TU Berlin / BAM, 2017**, 131 pp. `https://depositonce.tu-berlin.de/bitstream/11303/6268/4/koemmling_anja.pdf`, sha256 `ee4f777b…4b02f9` | **partial** — Kurzfassung, §4.3 (ageing conditions, 25 % compression), §6 Zusammenfassung (life criterion, extrapolated lifetimes) | curl rung 1 → 200, 9 995 819 B | raw text | validated (text layer clean, figures not relied on) | yes |
| G6 | **RESOGOO EPDM E 9614 / art. 0153**, Technisches Datenblatt, 2018-09-29. Archived, sha256 `f39dd1de…c03788` | **inspected** (2 pp., DE+EN) | curl rung 1 → 200, 156 950 B | raw text | validated | yes |
| G7 | **ElastX24 (GM GmbH) EPDM 65** product page, `https://elastx24.de/epdm-65/` | **inspected** (property table) | browser rung 4, DOM read | raw text (live DOM, self-validating) | validated | yes |
| G8 | ElastX24 gasket configurator, `https://elastx24.de/shop/` | **de-scoped** — pricing only; no claim depends on it, and the shortlist reports the price as unobtained | browser rung 4 → app shell rendered, configurator did not; site is **B2B account-gated** ("Dieses Angebot richtet sich ausschliesslich an gewerbliche Kunden"). **Authentication boundary — not circumvented** | route: none | n/a | no |
| G9 | **fugendichtband24, art. 5023 DXF-1**, EPDM solid-rubber DXF cut gasket, `https://www.fugendichtband24.de/Zuschnitt-Flachdichtung-EPDM-Vollgummi-50-Shore-A-ohne-Kleber-DXF-Upload.htm` | **inspected** (price/thickness/lead-time block) | browser rung 4, DOM read | raw text (live DOM) | validated | yes — price and lead time |
| G10 | **o-ring-stocks.eu** product catalogue (nav enumeration) | **inspected** — complete top-level category list | browser rung 4, DOM read of `/` | raw text | validated | yes — supports a bounded absence claim |
| G11 | Koblar, D., Škofic, J., Boltežar, M., "Evaluation of the Young's Modulus of Rubber-Like Materials Bonded to Rigid Surfaces with Respect to Poisson's Ratio", *Strojniški vestnik – J. Mech. Eng.* **60**(2014)7-8, 506–511, **DOI 10.5545/sv-jme.2013.1510**. sha256 `fe0a082f…6950330` | **partial** — §0 Introduction, Eqs. (1)–(2) | curl rung 1 → 200, 2 278 380 B | raw text | validated | yes — the Gent–Lindley form used |
| G13 | o-ring-stocks.eu **EPDM O-ring catalogue**, filtered peroxide + 70 Shore A + ID 14–26 + cord 0.8–2.1: `https://www.o-ring-stocks.eu/epdm-o-rings/?filter[54156]=0.8;2.1&filter[54161]=70&filter[54162]=14;26&filter[54174]=Peroxide` | **inspected** — the filtered result grid (dimensions, stock, price) | browser rung 4. A composed filter URL returned an unrendered shell (client-side app, **not** a block); the live UI was driven instead — a geolocation modal intercepted the range toggles and was dismissed | raw text (live DOM) | validated | yes — sizes, stock, prices |
| G14 | o-ring-stocks.eu product pages **ORS116731** (17×1), **ORS116732** (17×1.5), **ORS116787** (24×1.5) | **inspected** — identity block: title, material number, DIN 3771 | browser rung 4, same-origin fetch + DOM parse | raw text | validated | yes — **material 127019011 confirmed identical across all three**, which is the whole basis for "one test report covers both seals" |
| G12 | Heyduk, L., "Looking Beyond Chemical Compatibility Charts: Matching Plastic and Elastomer Seals with Fluids", Trelleborg Sealing Solutions / *Chemical Engineering*, 2020. Archived, sha256 `db9edba3…1242fd8` | **inspected** (§"Chemical compatibility charts", author block) | curl rung 1 → 200, 1 219 161 B. **No text layer** — scanned images | **OCR / rendered-page vision** (`pdftoppm` 300 dpi → `tesseract`) | validated against the rendered pages the OCR came from | no — framing and caveats only |

**Build verification, 2026-09-03.** `make head-end-provisional` passes on the
O-ring geometry: both fastening routes (thread-forming and insert) render all
five parts as exactly one closed solid each — the target's own gate, which exists
because "an inverted cut that leaves a zero-thickness ring" once shipped a carrier
with no O-ring groove while every assert passed. Two errors were caught during
this change and are recorded because neither was visible from the source:

- **A name collision.** `oring_fill` is already defined in
  `o2_probe_head_end.scad` for the *carrier's* radial ring. OpenSCAD resolves the
  last top-level assignment across includes, so adding `oring_fill` to the shared
  file silently clobbered it. The membrane parameters are now `mem_oring_*`.
  Confirmed as newly introduced by rendering a pristine `git show HEAD:` copy,
  which is clean.
- **A verification that did not verify.** The first run was read as passing
  because `make … | tail -25` exited 0 — but a pipeline returns the *last*
  command's status, so a failing `make` would have been invisible. Re-run without
  the pipe.

**Bounded absence claim.** o-ring-stocks.eu/Techniparts — supplier of the
already-qualified EPDM 70 peroxide compound 127019011 — **does not sell flat
gaskets, washers, or sheet stock**. Searched their own site on 2026-09-03 by
enumerating every top-level product category from the live navigation: O-rings
(11 compound families), rubber round cords, back-up rings, X-rings, O-ring kits,
tools. Their on-site search redirects to the homepage. Confidence in absence
**high**, because the corpus is closed — a vendor's own complete catalogue
navigation.

**Consequence, revised 2026-09-03 after the O-ring pass.** The claim stands, but
the conclusion first drawn from it — "the incumbent compound cannot be bought in
this shape, so the shortlist must change supplier" — was wrong, because it
assumed the shape. The compound *is* available from this supplier in the shape
that matters, as an O-ring; what is absent is only the flat-washer form. An
absence claim about a *form* was allowed to stand in for a claim about the
*compound*, and it pointed the first sourcing pass at four new suppliers when the
answer was in the incumbent's own catalogue.

**Challenge searches (§2.1), run against the conclusion rather than for it.**
"EPDM peroxide vs sulphur compression set" returned only distributor marketing
pages, which the brief excludes as compatibility sources — the peroxide-cure case
therefore rests on G4/G6 datasheet values and G5, not on those pages. Searches
for EPDM seal failure in biogas/digestate/ammonia service and for microbial
biodeterioration of EPDM in buried/compost service returned no substantiated
failure mechanism; the nearest relevant hit, an EPA landfill-liner exposure
summary, reported that butyl and EPDM liner materials "changed little during the
exposure period", which corroborates rather than refutes. **The one refutation
that did land came from the primary itself**: ORD 5700 rates EPDM 4 in hot lactic
acid, and it is recorded above as the strongest argument against the
recommendation rather than buried.

**Unresolved and material.** No source found — vendor, standard or peer-reviewed —
tests any elastomer in the *combined* NH₃ + H₂S + organic-acid + wet/dry medium at
75 °C under sustained compression. Every compatibility datum above is
single-chemical immersion at unstated temperature, and every ageing datum is
thermo-oxidative in air. **What would discriminate:** compression set and
compression–deflection on the candidate compound, held at 75 °C under 25 %
compression, in air against a synthetic compost condensate, with lactic acid
present. If EPDM survives that, the recommendation is safe; if it does not, the
lactic-acid row was the reason, and FEPM (Aflas) is the nearest fallback — rated 1
in butyric acid and 2 in hot ammonia gas, the only family in the table to clear
both the ammonia and the organic-acid columns. It is not a drop-in answer: ORD 5700
rates FEPM **x — insufficient data** on all four hydrogen-sulfide rows, so it
trades a known weakness for an unmeasured one.
