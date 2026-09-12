# Finished upper +12V route and via/land review

Reviewed exact board SHA-256 `3c24db8193af09d4d9ad07b2166c7f818885211b63b3e2af6e0c7cbec900c665` on 2026-09-12. The board was not edited during this review.

The upper +12V connection was followed on native front/back copper-and-pad renders, from its existing B.Cu supply near (108.55,104.55), through the five new layer transitions around the ADC/divider region, to the front guide via at (114.9,116.1). The route passes through available spaces between analog routes, including the back face of the reference region. All original REF3425 force/sense and bypass tracks remain intact; that physical proximity is not an analog-noise qualification. The three previously offset route endpoints are now centred on their vias. Native final DRC reports no ordinary dangling supply segment, copper error, hole-clearance error or open net. No further local route defect was found. The five transitions reflect the occupied two-layer layout; this review does not establish conducted-noise or thermal performance.

`no-via-in-pad.json` checks all **195 vias**, **237 SMD copper layer shapes**, **277 pad mask apertures** and **235 paste apertures**, including anonymous exposed-pad paste windows. Native zero-margin contacts found no via-copper/SMD-land overlaps, no drill/pad-mask-opening overlaps and no drill/paste-aperture overlaps. The exact board, project, rules and measurement-code fingerprints are recorded. Deliberate synthetic copper-land and paste-window contacts were both detected; the measurement took approximately 0.43 seconds.

All 195 vias resolve as tented on both faces in this design. The native pad mask expansion and paste margins are zero. These findings describe drawn geometry and KiCad settings: they do not qualify the fabricator's tenting, stencil process, mask registration or a filled/capped-via process. A positive gap below 0.20 mm is not treated as a violation of an undeclared universal rule.

The final native report retains only ten documented courtyard warnings and the two intentional guard-rail end warnings. Those are outside this supply-route/via-overlap finding. The separate independent guard/thermal review and final fabrication-package checks remain the authority for their scopes.

## Measurement implementation review

1. Missing files, changed board hashes, wrong inventory, native exceptions and unsupported nonzero mask/paste margins fail explicitly; they cannot produce a clean result.
2. The verdict is the presence of native geometric contacts at zero margin, without a fitted score or a far-tail pass branch; interior overlap is detected by the known-bad cases.
3. The installed KiCad 10.0.5 native binding was executed on the exact final board, including a paste-only window calibration.
4. The report fingerprints the measurement code, native binding, board, project and rule inputs.
5. There is no result cache or fallback path.
6. The report states the exact checked geometry and physical-process limits.
7. Temporary via discs placed inside a solder land and a paste-only window both triggered contact; neither was saved to the board.
8. No warning, rule, board object or margin was modified by this review; the report measures actual geometry.
