# O₂ probe condensation-model research

Date: 2026-08-23
Question: How should condensation at the O2 probe PTFE membrane be modeled?

## Browser-control proof

- Surface: headless Google Chrome 151 over CDP at `127.0.0.1:9233`, controlled with Playwright.
- Proof: navigated to `about:blank`; live DOM read returned `<html><head></head><body></body></html>`.

## Provenance and archive

- Retrieval date: 2026-08-23.
- Browser route: Google Chrome 151 over CDP with Playwright; each relied HTML page was validated in its live rendered DOM.
- Buck PDF was downloaded only to temporary working storage, SHA-256 `6597d1f0da963a45313cbf46f5e7ce320c52e2f1db41bd2bdecf8d14bcdf8d3b`, OCRed for discovery, and the relied table was checked against rendered physical page 3.
- Archive unavailable because the user did not authorize a project research archive. Stable pointers are retained in the source access log; no downloaded source was added to the repository.

## Source access log

- **Buck (1981), “New Equations for Computing Vapor Pressure and Enhancement Factor,” DOI 10.1175/1520-0450(1981)020<1527:NEFCVP>2.0.CO;2, https://journals.ametsoc.org/view/journals/apme/20/12/1520-0450_1981_020_1527_nefcvp_2_0_co_2.xml** — evidence state: inspected for saturation definitions, Eq. 4 form, and Table 2 coefficients; attempt history: URL discovered through Serper; first headless Chrome/Playwright target attempt returned HTTP 202 with a rendered CloudFront 403 error page; one permitted presentation correction used a fresh context with plain Chrome 151 UA, de-DE locale, Europe/Berlin timezone and matching Accept-Language, which returned the real HTTP 200 article; PDF link discovered in that DOM and downloaded successfully with coherent UA/referrer; route: OCR from scanned PDF for discovery plus rendered-page vision for evidence; validation: validated against rendered physical page 3 (journal p. 1529), including Table 2; SHA-256 6597d1f0da963a45313cbf46f5e7ce320c52e2f1db41bd2bdecf8d14bcdf8d3b; load-bearing: yes.
- **NSF NCAR EOL, “Water Vapor Pressure Formulations,” page updated 2026-07-20, DOI 10.26023/S2SX-K278, https://www.eol.ucar.edu/data-software/conventions-and-standards/water-vapor-pressure-formulations** — evidence state: inspected sections “Vapor Pressure over liquid water below 0°C” and References; attempt history: first Playwright/Chrome target attempt returned the substantive HTTP 200 page; route: live DOM/raw text; validation: validated live page; load-bearing: yes. Exact finding: item 6 identifies the code's `18.678, 234.5, 257.14` formula as **Buck 1996, updated from Buck 1981**, while item 7 gives the distinct 1981 coefficients.
- **COMSOL 6.4, “Wet Surface,” https://doc.comsol.com/6.4/doc/com.comsol.help.heat/heat_ug_mt_features.10.34.html** — evidence state: inspected in full; attempt history: first Playwright/Chrome target attempt returned substantive HTTP 200 page; equation assets discovered from live DOM and fetched from the publisher asset path; route: live DOM/raw text plus rendered equation image; validation: validated live page and rendered Eq. image `heat_ug_mt_features.10.34.1.png`; load-bearing: yes. Direct formulation: `g_evap = M_v K(c_sat-c_v)`, with latent heat coupled into the thermal balance.
- **COMSOL 6.4, “Moist Surface,” https://doc.comsol.com/6.4/doc/com.comsol.help.heat/heat_ug_mt_features.10.21.html#633681** — evidence state: inspected in full; attempt history: followed the publisher's live-DOM link from “Wet Surface”; substantive HTTP 200 page; equation assets fetched from publisher path; route: live DOM/raw text plus rendered equation images; validation: validated live page and rendered images `10.21.01` and `10.21.02`; load-bearing: yes. Direct formulation: condensation proceeds when vapor concentration exceeds saturation and accumulates surface liquid through `M_v dc_l/dt = -g_evap`; evaporation is suppressed when the liquid inventory is zero.
- **Apogee Instruments SO-431 product page, https://www.apogeeinstruments.com/so-431-0-30-sdi-12-output-oxygen-sensor/** — evidence state: inspected Description section; attempt history: first Playwright/Chrome target attempt returned substantive HTTP 200 page; route: live DOM/raw text; validation: validated live page; load-bearing: yes. Direct vendor evidence: the product heats its Teflon membrane about 2°C above ambient to keep condensation from blocking its diffusion path; this is a precedent, not proof that 2 K is sufficient for this probe.
- **Miljkovic et al., “Continuous Droplet Removal upon Dropwise Condensation of Humid Air on a Hydrophobic Surface,” https://pmc.ncbi.nlm.nih.gov/articles/PMC4148149/** — evidence state: de-scoped — no conclusion depends on it because the proposed model already leaves nucleation/coverage/drainage empirical; attempt history: first headless Playwright/Chrome target rendered a reCAPTCHA interstitial; the one permitted presentation correction used a fresh plain-Chrome-UA context with de-DE locale, Europe/Berlin timezone and matching Accept-Language and rendered the same challenge; non-handoff-capable challenge rule stopped further requests; route: none; validation: n/a; load-bearing: no.

## Current findings

- Project-local model already implements Buck saturation pressure, dew point, local RH, a one-node block thermal RC, and a quasi-steady membrane coupling `T_mem = T_ambient + eta (T_block - T_ambient)`.
- The local code's `Buck (1981)` docstring is misattributed: its coefficients are the Buck 1996 update. This is a source-label issue, not evidence that the implemented saturation pressure is unusable in the probe's above-freezing range.
- Project-local release logic explicitly treats that thermal model as screening only; water films, drainage, heater convection, and wet conductance remain unvalidated.
- The response candidate calls for a dry-side carrier-rim heater and temporary cold-spot membrane thermometry.
- A minimal dynamic extension can use the same surface-flux/sign convention as COMSOL: vapor-concentration driving force, a nonnegative liquid inventory, and latent heat feedback. Drainage and O2-conductance loss remain probe-specific empirical closures.
- For saturated 40–60°C inlet gas, the Buck-1996 formula gives approximately 90.0–91.2% local RH at a surface 2 K warmer and 81.0–83.3% at +4 K. These are calculated screening values, not a wet-surface validation.
- The model should use the minimum temperature over each PTFE coupon, carrier bottom edge, and any thermally bridged guard, not U10/U13 or average membrane temperature.
- A nonnegative surface-water inventory is essential: after a cold startup creates condensate, crossing back above dew point starts evaporation but does not make the membrane instantly dry.
- Direct droplets/leachate require a separate imposed liquid-load term; a condensation-only model cannot demonstrate resistance to gross wetting.

## Challenge searches

- Serper, 2026-08-23: `surface temperature above dew point does not prevent condensation hydrophobic membrane limitations`. Results did not overturn the equilibrium onset criterion; they highlighted that practical margins and non-condensation liquid sources are application-specific. No claim was taken from snippets.
- Serper, 2026-08-23: `lumped condensation mass transfer model overestimates hydrophobic surface nucleation drainage`. Results identified surface-specific nucleation/dropwise-drainage literature, reinforcing the decision not to derive drainage or coverage from first principles. The one primary selected for inspection hit the logged non-handoff-capable challenge and was de-scoped because no conclusion depends on it.

## Recommended model

Use a calibrated hybrid model:

1. Psychrometric boundary: `p_v = RH_in p_sat(T_in)` and `T_dew = p_sat^-1(p_v)`.
2. Multi-node thermal RC: cell block, each membrane/carrier cold spot, and outer tube/guard. Include direct carrier-heater power and condensation/evaporation latent heat.
3. Signed surface mass flux, positive for condensation: `j = M_v k_m[c_v - c_sat(T_surface)]`, with negative flux clamped when no liquid remains.
4. Surface inventory: `dm_l/dt = A j + m_dot_imposed - m_dot_drain`; use a fitted retention threshold and drainage time constant by orientation/contamination state.
5. Wet coverage and O2 conductance: fit `f_w = F(m_l, orientation, contamination)` and `G_O2 = G_dry[(1-f_w) + gamma_wet f_w]`; use `gamma_wet = 0` as the conservative uncalibrated screen.
6. Feed time-varying `G_O2` into the existing spatial O2 transport model and predict response time, bias, and wet-recovery delay.

## Calibration/validation plan

- Dry heater-power steps at multiple orientations and gas temperatures; temporary sensors at block, both coupon cold spots, carrier lower edge, tube/guard, and inlet gas; identify the thermal network and uncertainty.
- Controlled saturated-gas sweeps through positive and negative dew margin; photograph droplet coverage and record condensation, drainage, and evaporation transients.
- O2 concentration steps in dry, condensed, externally droplet-covered, drained, and condensate-aged states; identify wet coverage versus conductance.
- Validate on held-out cold-start, heater-loss, ambient-temperature-step, orientation, and direct-liquid-load cases.
- Release gate: a conservative uncertainty bound on minimum surface dew margin stays positive in normal operation, the model never misses an observed wet interval, and held-out wet/drained O2 response remains within the project's 120 s settling limit.

## Remaining engineering uncertainty

- `k_m`, drainage retention/time constant, wet-area map, and wet/dry conductance ratio are not identifiable from PCB temperatures alone; the prototype needs temporary cold-spot thermometry plus optical/wet O2 tests.
- A one-node block model cannot prove membrane dryness; direct dry-side carrier heating remains the appropriate controllable actuator if remote coupling is insufficient.

## Next unfinished step

None for the modeling recommendation. Implementation would extend the existing Python package with membrane/carrier thermal nodes, surface-water state, and time-varying membrane conductance.
