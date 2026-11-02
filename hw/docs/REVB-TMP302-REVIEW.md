# Rev B TMP302 autonomous heater cutoff — engineering review

2026-09-11. Current candidate: `routing/revb-89-tmp302/o2-probe.kicad_pcb`.
The board remains 20 × 89 mm, two layers, 1 mm thick. Earlier candidates are
historical snapshots. This implements the hardware addition requested for P2;
thermal and fault qualification remains open. No firmware configuration is needed
for U16 itself.

U16 is fitted TMP302BDRLR. Pins 1 TRIPSET0, 6 TRIPSET1, 4 HYSTSET and 5 VS
connect to 3V3D; pin 2 is GND; pin 3 OUT connects to HEATER_GATE alongside
TMP117 ALERT. This selects nominal 85 °C trip and 10 °C hysteresis (nominal
75 °C release). C35 is the existing BOM family's 100 nF 0402 supply bypass.
R28 remains 10k, limiting a 3.3 V high PWM versus asserted clamp to at most
0.33 mA nominal. TI specifies VOL ≤0.4 V at 3 mA for VS >2 V.

## Placement and source evidence

U16 is on F.Cu at (114.4, 136.5) mm, on the heated island; C35 is at
(117, 136.5) mm. The existing 99 component poses, pads, outline, slots and
critical analog routing are retained. Three local 3V3D segments and one local
GND segment are replaced to make room. Thirty tracks/vias are added locally;
no routing crosses a thermal slot. The ground return is restored through R29's
GND land and the existing tip ground via. Local geometry inspection and a
connectivity scout identified this return; final copper is explicitly authored.

[TI TMP302 datasheet](https://www.ti.com/lit/gpn/TMP302), SBOS488E, Dec 2018,
with current package addendum and drawing 4223266/F (11/2024), is the source.
PDF SHA256: `5413acb9f08d49360a8f2f60474895ea84890e4a9bb20e06cbc03af96bfe275b`.
The pin-function table and independent top-view drawing were cross-checked
against the symbol and embedded footprint by a second reviewer.

Project footprint `o2-probe:TMP302_DRL6_TI` uses TI's recommended six
0.67 × 0.30 mm lands, 1.48 mm column spacing, 0.50 mm row pitch and 0.05 mm
corner radius. No exposed pad or holes. Pin 1 is upper left in the top view.
The installed SOT-563 footprint supplied the body/courtyard/3D geometry; its
lands were adjusted to TI's recommendation. The rendered TI land pattern and
top view were visually inspected. TI's linked SLUUBP1A guide was also retrieved;
it corroborates PCB temperature monitoring with TMP302 but contains no pin-level
schematic, so it is not used as pin-map authority. All requested sources returned
real content; no pending access challenge.

## Validation and limits

Run `python3 make_review_tmp302.py`. The review directory contains saved-fill
and independently refilled DRC, ERC, full board/schematic parity, native scoped
geometry checks, schematic and assembly PDFs, Gerbers and drills. Its manifest
fingerprints the candidate and validator inputs. These are engineering-review
exports, **not an order-ready release**. The historical builder does not select
this new candidate.

The layout has zero DRC errors, zero opens and zero parity findings, with the
same 15 explicitly enumerated manual-assembly courtyard warnings as the 89 mm
baseline. ERC has zero findings. The independent copper audit reports no shorts.
The scoped guard is exercised with wrong variant, wrong strap, wrong land,
changed retained copper and missing-part mutations. All must fail.

Qualification must measure the real cell/heater temperature relative to U16,
thermal delay and overshoot; 85 °C is a selected PCB trip point, not a proved
safe cell limit. Include threshold tolerance and nominal hysteresis variation.
Measure heater current at the worst hot clamped gate voltage, startup and supply
ramps. TMP302 takes about 35 ms to become functional after valid supply; do not
assume a guaranteed asserted output while starting or unpowered. Loss of 3V3D
and a shorted heater MOSFET are not covered. Automatic release can restart heating
if PWM remains asserted; exercise repeated trip/release under the intended fault.
Existing procurement, physical fit and analog-noise release gates remain open.

## Guard review contract

1. Missing/bad input raises; no cached PASS is consumed.
2. Mutations of a correct input fail; extra/missing parts and out-of-scope copper fail.
3. The builder invokes native geometry, live schematic mapping, ERC and both DRC modes.
4. The input manifest fingerprints deriving code and the pinned baseline as well as CAD.
5. A failed command prevents promotion of the temporary review directory.
6. Reports identify CAD-only evidence and leave physical qualification open.
7. Five intentionally broken boards calibrate the geometry guard; DRC is a separate gate.
8. The changes fix actual copper connectivity/clearances; no warning exclusion was added.

The native guard runs in approximately 0.2 seconds on this machine; the mutation
suite records its measured runtime. Its local geometry scope does not replace DRC.

## Independent review

The reviewer checked the TI pin map/land drawing, final CAD, all manifest hashes,
saved/refilled DRC, ERC and mutation tests. Two findings were fixed: the copied
README pointed at the historical exporter, and the replay helper wrote a library
before rejecting invalid invocations. The helper now checks its arguments and
pinned source before writing only to a new output directory; refused-invocation
checks and a successful replay verify the fix. Final front/back tip copper and
schematic drawings were visually inspected.
