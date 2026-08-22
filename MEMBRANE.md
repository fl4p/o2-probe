# O₂ probe gas-window membrane

Research date: 2026-08-22
Status: Rev-A candidate selected; production material remains conditional on
complete-path wetting and fouling tests.

## Decision

Use **Porex Virtek PMV15T porous PTFE membrane** as the Rev-A baseline for the
external gas window. Install it in a removable, drained carrier with a smooth
polypropylene support and a separate coarse debris guard. Obtain **Gore MMS341**
samples as the principal A/B challenger before freezing the production
material.

This decision fills the open material choice in [PLAN.md](PLAN.md), which
specified only `slots + ePTFE membrane + mesh`. The membrane is an enclosure
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

The current Porex product page [S1] identifies PMV15T as a 100% PTFE membrane
sheet with the following values:

| Property | Published value | Evidence status |
|---|---:|---|
| Oleophobic grade | 8 | vendor specification |
| Water-entry pressure | 265 mbar minimum; 370 mbar typical | vendor specification |
| Airflow at 70 mbar differential | 45 minimum; 75 typical L h⁻¹ cm⁻² | vendor specification |
| Thickness | 0.18 ± 0.03 mm | vendor specification |
| Enclosure rating | IP64 and IP67 | vendor specification; final housing dependent |
| Filtration efficiency | specified at 0.4 µm under IEST RP-CC007.2 | vendor specification; **not a pore-size claim** |

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

The exact PMV15T product page does not state whether the supplied grade is
expanded or sintered PTFE. Confirm the construction with Porex rather than
carrying the plan's generic `ePTFE` label into the drawing unverified.

## Carrier construction

Use a mechanically retained cartridge, provisionally arranged as follows:

```text
compost
   ↓
replaceable coarse debris guard
   ↓
open drainage / stand-off gap
   ↓
PMV15T membrane with smooth PP support on exposed side
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
- Use a smooth polypropylene support or carrier on the exposed side. Porex's
  ePTFE backing guide lists 100–300 µm PP support, a −40 to +100 °C range,
  strong acid/alkali resistance, toughness and abrasion resistance [S4]. Adding
  support can change airflow, so test the actual laminate or sandwich.
- Make the outer guard independently replaceable. A moulded or perforated PP
  guard avoids a corrosion path and thermal bridge; any alternative metal mesh
  requires its own corrosion and cleaning justification.
- Keep the membrane accessible for visual inspection and cartridge replacement.
- Avoid a cold carrier connected directly to the outer tube where it would
  condense water despite the heated internal chamber.

No active-area dimension is frozen. Design the first carrier to accept
interchangeable coupons so that area and backing can be varied without changing
the probe body.

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

## Procurement questions

Ask Porex for:

- PMV15T samples and available sheet, roll and die-cut formats;
- confirmation whether PMV15T is expanded or sintered PTFE;
- nominal porosity or O₂/gas-diffusion data, if available;
- compatibility of the Grade-8 treatment with NH₃-rich condensate, organic
  acids, H₂S and the intended cleaning agents;
- PP-supported or laminated configurations and their resulting airflow;
- approved welding, clamping and adhesive options at 60 °C saturated exposure;
- lot-level minimum airflow, water-entry and oleophobic test documentation;
- price, minimum order quantity and lead time.

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
