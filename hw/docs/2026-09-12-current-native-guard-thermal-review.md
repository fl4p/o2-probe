# Current native guard and thermal-crossing review, 2026-09-12

This bounded review inspects the saved filled-copper geometry of board SHA-256 `cd2440c410530d2d570ddeca60f96469a61ae51d3bdbf5ae08b8a5ca1d64ed4c`, privately preserved at `checks/current-native-guard-thermal-v2/board.kicad_pcb`. It does not accept later routing changes or claim measured leakage/thermal performance. The source is the current 83-component PCB, not the former ADS1119 design or an old Aisler review manifest.

## Findings

All eight routed CELL_RE copper items are front-layer tracks, with no vias. The intentional cell's plated through-hole land still spans the board; “front-layer only” here describes the routing, not removal of that mechanical interface.

The guard feed and rails form one connected copper group. This diagnostic includes native front/rear track, via and pad polygons, saved filled guard polygons, and seven plated inter-layer ties. Polygon components are evaluated separately before the through connections join them; a disconnected island is not made connected merely because it belongs to the same zone object.

Along the actual CELL_RE segment band y117.0–123.6, 267 samples at no more than 0.025 mm spacing found the guard nearer than every foreign front copper object. The comparison includes tracks, vias, pads and saved filled zones. Sampled guard edge gaps span approximately 0.2250–0.3326 mm. No sampled point lacked guard within the legacy 0.60 mm reach criterion. This is a sampled geometry result, not a proof that every infinitesimal point has the same ordering.

The narrowest sampled shielding margin is only about **0.0161 mm**, at CELL_RE `(111.5, 123.6)`: guard edge gap 0.225001 mm; nearest foreign copper is the GND fill at approximately 0.241135 mm. The inherited functional CELL_RE clearance rule explicitly applies to track-to-track comparisons. Therefore this result must not be restated as a whole-net 0.25 mm copper clearance. The guard remains nearer in this snapshot, while practical surface leakage and contamination behavior remain outside the geometry measurement.

Intersecting **all** saved GND copper with the horizontal line y118 on both layers finds exactly one crossing: front-layer track UUID `e5c418ee-ce00-48fa-99bb-1452609f54ce`, occupying x100.30–100.45 (0.15 mm width, centre x100.375). No other GND track, via, pad or filled-zone polygon crosses that line. This confirms the requested single ground crossing at the inspected barrier line; it does not calculate thermal conductance or prove all possible multi-dimensional heat paths.

## Method and evidence

The producer is `checks/review_current_guard_thermal.py`. It reads pcbnew objects directly. Track/via/pad point distances use native effective shapes. Filled zones use saved native polygons, with native `Unfracture` to recover separately represented holes before planar analysis. Polygon conversion uses at most 0.001 mm chord error. The script refuses malformed extracted polygons rather than silently repairing them with a zero-width buffer. The first attempted extraction stopped on native linked-hole fracture representation and emitted no successful review; the corrected v2 uses the native operation designed for it.

`checks/current-native-guard-thermal-v2/review.json` records all sample locations, nearest object UUIDs/nets/types, layer components, plated ties and GND crossing geometry. Runtime was 58.777 seconds. These are diagnostic measurements with explicit limitations; they are not a general-purpose guard or fabrication release validator. Final routing and zone refill must be followed by a fresh check bound to the final board.

## Known-bad diagnostic calibration

A private saved/reloaded board adds a HEATER_PWM trace atx111.78,y120–122 and a second GND crossing atx109,y117.5–118.5. The diagnostic reports107 samples with foreign copper nearer than the guard, and reports the additional GND intervalx108.95–109.05 at the barrier line. Evidence: `checks/current-native-guard-thermal-known-bad-v2/review.json`; runtime44.421s. The original board is unchanged.

The first intrusion trial accidentally overlapped CELL_RE, and native SaveBoard reassigned that test trace to CELL_RE. That trial was rejected as an invalid foreign-net calibration. The corrected non-overlapping trial explicitly verified HEATER_PWM after save/reload before measuring it. Thus the calibration does not rely on an in-memory SetNet call or on the intended mutation name.
