# Rev B 95 mm compaction review — 10 September 2026

The separate [95 mm candidate](../routing/revb-95/README.md) is fully routed.
It reduces length from 107 to 95 mm with the original 20 mm width, two copper
layers, 1.0 mm thickness, circuit/BOM and design rules. The 107 mm alternative
remains in `routing/revb-interfaces/` for comparison. Neither candidate has new
physical qualification from this CAD work.

## What changed

The 42 footprints originally at board-local Y ≥ 66 mm translate by −12 mm as a
rigid group. Their 136 pads/drills retain their relative dimensions, orientation,
side and geometry. This includes U11's standing cell interface and gas aperture,
RH1/RH2, the analog ICs, the four thermal slots and the potting boundary. All 34
copper objects crossing the old thermal band retain exact translated geometry.
The 0.8 mm main-heater path is unchanged. Cable/power and MCU IC positions stay
fixed; the intervening contacts and passives are repacked on both faces.

C16's 3V3A bypass moves to F.Cu at absolute (113.4, 102.3) mm, and C33's VA_MON
filter moves to B.Cu at (112.0, 97.2) mm. These positions connect directly to the
main ground copper and existing supply/signal copper, eliminating two isolated
ground pockets. R19 moves to F.Cu at (113.4, 107.6) mm. TP5's two original feed
segments are replaced for its new location. The remaining 49 authored critical
copper items, including the full CELL_RE and CELL_WE routes and guard rails,
retain their translated geometry and locks.

Routing uses the existing 0.09 mm track and 0.25/0.15 mm through-via floors where
needed. No clearance or manufacturing rule was relaxed. Temporary router project
settings were discarded; the accepted `.kicad_pro` and `.kicad_dru` hashes are
identical to the 107 mm candidate.

## Checks and independent review

KiCad 10.0.5 saved-fill and fresh-refill DRC both report zero errors, zero open
connections, zero schematic-parity findings and zero silkscreen findings.
All-severity ERC is clean. The physical pin/value/MPN inventory matches the
schematic generator: 99 footprints and 299 assigned pins.

Export validation checks every expected Gerber layer, exact 20 × 95 mm outline
and four translated slot contours, the copper-free thermal fill gap, and every
PTH/NPTH drill or routed slot against the native board. Front/back assembly PDFs
were visually inspected. See the [manifest](../routing/revb-95/review/validation-manifest.json)
for exact inputs, commands and measured runtimes.

An independent agent reviewed CAD and validation code. Findings were fixed and
rechecked:

- A new I2C_SDA via approached CELL_RE at 0.185 mm. It now sits at
  (111.52, 113.405) mm with 0.265 mm copper-edge clearance. The added comparison
  check covers new/changed vias, including this regression. Existing closer
  ground/pad geometry is retained from the 107 mm design; this is **not** a claim
  that all foreign copper globally clears CELL_RE by 0.25 mm. In the guarded
  band, nearest guard/foreign copper measured 0.275/0.690 mm respectively.
- The geometry check now compares lower pad/drill geometry and board thickness,
  not only footprint origins. A deliberately altered cell aperture fails.
- The export manifest includes the actual schematic-generator, netlist parser,
  selected BOM39 critical-route definitions and resolved KiCad symbol sources.
  Input hashes are captured before validation and must remain identical before
  promotion of the exports.

The reviewer reported no remaining blocking findings in the inspected CAD/code.
Automated calibration: 8 compact-board tests plus 5 existing ring-retirement
checks passed in 11.285 s; 14 existing export-guard tests passed in 0.304 s.
A separate real-export provenance test changed a schematic input after the last
export and correctly prevented promotion, preserving the prior review (11.874 s).
The new geometry check takes about 0.4 s inside KiCad Python, excluding process
startup. See the regenerated manifest for the final measured build time.

## Assembly warning dispositions

All 16 courtyard warnings remain visible in the reports; no DRC exclusions were
added. Fourteen retain the [107 mm manual-assembly dispositions](REVB-ASSEMBLY.md).
The old R10/R11 overlap is gone. The two new pairs are:

| Pair | Disposition |
| --- | --- |
| R10 / J105 | Courtyard margins overlap; native Fab geometry shows at least 0.4875 mm between the resistor body and wire envelope. Fit R10 before attaching the debug wire. Confirm soldering access on the first article. |
| J3 / TP5 | Programming fixture courtyard overlaps a flush copper test point. There is no soldered TP5 body. Use programming and guard probing sequentially; verify the real probe/fixture approach before relying on simultaneous access. |

## Acceptance guard review

1. Missing/bad inputs raise or make the underlying command fail. Missing DRC
   fields, ignored checks, opens and parity findings cannot pass.
2. Near and far failures are tested: the original too-close via and a via placed
   on CELL_RE fail; small and large exported-outline changes fail.
3. The builder invokes native geometry checks, saved/refilled KiCad DRC, ERC,
   pin parity and export checks using their actual inputs; installed KiCad must
   be 10.0.5. Existing 107 mm tests still pass with default helper arguments.
4. PCB, rules, generator/parser/selected-route code, local libraries and actual
   external symbol sources are fingerprinted. Before/after comparison rejects
   changes while checks are running.
5. Failed builds leave staging evidence and do not promote it as the successful
   review directory. No failed or unevaluable probe is cached as verified.
6. This is validation/export of an authored PCB snapshot. The seeder is explicitly
   an unrouted starting point, not a claimed replay of the finished layout.
7. Known-bad calibration removes critical copper, alters U11's aperture, moves
   U11, corrupts board/DRC input and changes exported geometry; all are rejected.
8. The via fix changes its physical clearance, and ground fixes reconnect the
   actual copper. Warnings were not disabled to obtain a clean result.

## Remaining decisions

Fab's mechanical review must check the shorter overall envelope and shifted
potting/programming locations against the actual enclosure and fixtures. No
unmeasured enclosure dimension was inferred. The existing procurement gaps,
main-heater/input-protection qualification and environmental/thermal tests in
[Rev B scope](REVB-SCOPE.md) remain open. The original thermal island is preserved,
but changing the length of the electronics section still warrants thermal
verification on hardware. J5/F3 belong only to the deferred Rev C plan.
