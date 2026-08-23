COMPLETE WORKING CHECKPOINT

# O2 probe PTFE-membrane heater question

Date: 2026-08-23

Design-status update, 2026-08-24: the remote cell-island concept evaluated
below has been superseded by the dry-side heated-ring tip. The evidence and
qualification requirement remain applicable; the ring still needs saturated-gas
testing at the coldest membrane point before production qualification.

## Browser-control proof

- In-app browser discovery returned no available browser.
- Standalone Playwright 1.55-compatible Python connected to headless Google Chrome over CDP.
- Navigated to `about:blank`; rendered DOM read as `<html><head></head><body></body></html>`.

## Local design evidence

- `o2-probe/PROTOTYPE-RESPONSE.md`, Result: heater is for condensation margin only; 2 K membrane rise with <=4 K block rise requires measured coupling eta >=0.5, otherwise reject remote heating or add direct dry-side carrier heat.
- `o2-probe/MEMBRANE.md`, Carrier construction and Qualification: avoid a cold carrier tied to the tube; test membrane-side and cell-side temperatures with heater active; water films can block diffusion without penetrating PTFE.

## Source access log

- S1 `https://www.apogeeinstruments.com/so-431-0-30-sdi-12-output-oxygen-sensor/` — inspected relevant product description; first browser attempt returned rendered HTTP 200, correct H1/title and 2,976 body characters; route raw live DOM; validated; load-bearing yes. Locator: product description paragraph. Direct evidence: Apogee heats its Teflon membrane about 2 °C above ambient specifically to prevent condensation blocking the diffusion path.
- S2 `https://www.porex.com/product/virtek-ptfe-material/` — inspected relevant exact-grade product page; first browser attempt returned rendered HTTP 200, correct title and 1,423 body characters; route raw live DOM; validated; load-bearing yes. Locator: PMV15T specification table. Direct evidence: PMV15T is 100% PTFE, hydrophobic venting material, oleophobic grade 8, with 265 mbar minimum / 370 mbar typical water-entry pressure. Inference: these liquid-entry properties do not prove that a surface condensate film cannot block gas diffusion.
- S3 `https://sgxsensortech.com/uploads/f_note/DS-0637-SGX-OX-ROHS-Mini_iss2.pdf` — inspected operating-conditions table; browser first attempt returned HTTP 200 `application/pdf`; official PDF retrieved to temporary working storage, SHA-256 `4d1d4479580ab98bbc525aaf4aca353745b99368bc020a76d7f8ec12964ceae7`; raw PDF text extraction validated against a 240 dpi render of page 2 (document page 1/1); load-bearing yes. Identity: DS-0637, Issue 2, 28-May-2026. Direct evidence: 15–90% RH continuous, 0–99% RH short-term, explicitly non-condensing; temperature −40 to +60 °C.
- S4 `https://pmc.ncbi.nlm.nih.gov/articles/PMC9345167/` — de-scoped, no evidentiary dependency. One correctly rendered headless-browser attempt returned HTTP 200 but title `Checking your browser – reCAPTCHA`, no article H1, and only 131 body characters. This non-handoff-capable challenge ended automation for the target; no claim depends on this source. Route none; validation n/a; load-bearing no.

## Search record

- Serper, 2026-08-23: `site:apogeeinstruments.com oxygen sensor membrane heater condensation 2 C SO-431`; discovery only, followed official SO-431 result.
- Serper, 2026-08-23: `site:porex.com PMV15T PTFE membrane condensation hydrophobic water film`; no result, not treated as absence; exact official URL comes from the existing membrane research record.
- Serper, 2026-08-23: `site:sgxsensortech.com DS-0637 SGX OX ROHS Mini humidity non-condensing`; no result, not treated as absence; exact official PDF URL comes from the project source log.
- Challenge search via Serper, 2026-08-23: `hydrophobic PTFE membrane condensation water film gas diffusion heater does not prevent condensation`; found primary scholarly candidates about condensation blocking membrane pores, to be inspected if needed.

## Unresolved

- The current design has no measured block-to-membrane thermal coupling. Qualification must measure the coldest membrane point and either demonstrate eta >= 0.5 for the 2 K/4 K design point or use direct dry-side carrier heating.

## Findings

1. Direct evidence, S1 product description: established commercial precedent heats the membrane itself about 2 K above ambient to avoid condensation blocking diffusion.
2. Direct evidence, S3 operating-conditions table: the selected SGX cell is specified for non-condensing operation and only 15–90% RH continuously.
3. Direct evidence, S2 table plus engineering inference: PMV15T's hydrophobic/oleophobic and water-entry specifications do not establish that its exposed surface stays free of a diffusion-blocking condensate film.
4. Project-specific calculated screening, `PROTOTYPE-RESPONSE.md` Result and `thermal_sensitivity.csv`: eta = membrane-rise/block-rise; 2 K/4 K requires eta >= 0.5. This remains unmeasured, so the present cell-island heater cannot yet be credited with keeping the external PTFE membrane dry.

## Conclusion

Yes, preventing condensation on the PTFE membrane should be a heater requirement. No, the current remote PCB heater has not demonstrated that requirement. Instrument the membrane cold spot during saturated-gas cycling; retain the remote heater only if eta >= 0.5 and the membrane stays above dew point, otherwise add/enable the dry-side carrier-rim heater.
