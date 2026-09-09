# Rev B CE protection and receiver-enable completion

**Implemented and reviewed; physical qualification remains open.**

Scope: integrate the existing `/RE` split into the routed two-layer candidate;
verify and finish the CE series-resistor / ESD implementation. Preserve the
WE/RE measurement path, driven guard, main-board heater and current cell mount.

Baseline: hardware HEAD `28b8a75` (includes the new revision-specific hardware
contracts); routed candidate under `routing/2layer-bom39`. Other sessions have
uncommitted changes in the main worktree. Work is isolated at
`/tmp/o2-revb-finish`.

## Source access log

Browser proof: separate Playwright context on existing scratch Chrome port
56285; `about:blank` navigation returned an empty HTML DOM, plain Chrome 152 UA.
No browser process launched. The private target was already closed at cleanup;
the client exited. See lifecycle details below.
In-app browser unavailable. Scratch port 9224 timed out before connection;
its process was independently identified as `--user-data-dir=/tmp/codex-chrome-7TRT8l`.
No source fetched through that failed connection.

## Search record

Local seeds inspected: `gen_sch.py` CE branch, `REVIEW-2026-09-04-AFE-DECISIONS.md`,
`AFE-BRING-UP-POSTMORTEM.md`, current bench notes, `POWER-BUDGET.md`, and routing
candidate provenance. Primary seeds: TI SNAS506I (LMP91000), TPD2E2U06,
THVD1410. The earlier dummy CE voltage and real-cell current are different
operating points; do not combine them. Latest bench board was Rev A, with
reference/interconnect faults; the supposed destructive fault-current figures
are not valid measurements.

## Verified findings and design decisions

The schematic generator is Rev B; the root PCB remains the fabricated Rev A
record. The fixed reference, WE/RE followers, RE guard and CE monitor were
already implemented in the schematic and BOM39 route. The later `/RE` split
was only in the schematic and firmware. The new candidate is
`routing/revb-interfaces/o2-probe.kicad_pcb`; the historical BOM39 route stays
unchanged and is the migration script's hash-pinned input.

### Receiver enable

U5.2 connects to U6.31 (PC7) and R45.1; R45.2 is ground. U5.3 stays on
PC6/DE with its independent R7 pulldown. R45 = 47k makes the receiver enabled
at reset; driver disable and bootloader reception remain independent.
THVD1410 SLLSEY3E p5 pin-functions table directly specifies active-low RE,
active-high DE, RE's internal 2 Mohm pullup and DE's pulldown. The existing
firmware already controls both pins. Its optional standby function is not a
new scheduling policy: the application must decide when it can stop listening.
R45's current while RE is high is approximately 3.3 V / 47k = 70.2 uA
(calculated nominal), so this board does not obtain the transceiver's bare-IC
shutdown current. The split still permits disabling the receiver during TX.

### CE resistor

R42 becomes **1k 1%, RC0603FR-071KL**, replacing 100R. This is a conditional
engineering bound, not a measurement of fault current or cell behaviour:

- Assume the CE lead is shorted to a local rail between ground and 3.366 V,
  with the AFE powered, and resistor temperature -40..85 C. This is not a
  bound on an external high-voltage surge or an unpowered pin injection.
- Yageo's part-specific sheet specifies 1% and 100 ppm/K. Taking the worst
  65 K departure from 25 C, Rmin = 1000 × 0.99 × (1 - 0.0065) =
  **983.565 ohm**; Rmax = **1016.565 ohm** (calculated).
- Short current ≤ 3.366 / 983.565 = **3.423 mA**. Allowing another
  3.366 / (182k × 0.99) = **18.7 uA** for the monitor gives **<3.45 mA**.
  The old 100R value permits about 34 mA under the same assumptions.
  LMP91000 SNAS506I p4 §6.1 gives 10 mA absolute maximum CE sink/source.
  Staying below absolute maximum does not promise accurate closed-loop
  regulation: p5 §6.5 specifies a minimum 750 uA operational drive.
- Use **130 uA** as an explicit qualification target, not a sourced maximum
  cell current: at that current the added drop is ≤ **132.2 mV**. At the
  750 uA drive limit it would be 762.4 mV, showing why resistance cannot be
  increased without regard to compliance. At 130 uA the resistor dissipates
  only 17.2 uW; the static short above dissipates about 11.6 mW. The sheet's
  100 mW rating is at 70 C; do not silently use that as an 85 C rating.
- SNAS506I p5 characterises A1's gain over 0.3 V to VS-0.3 V at ±750 uA,
  -40..80 C. Neither an 85 C accuracy guarantee nor the actual cell's CE
  voltage follows from this. Reject readings outside the firmware's
  compliance window; verify the entire cell operating envelope on hardware.

The earlier dummy-cell CE voltage and the real cell's roughly 100 uA reading
are different operating points. The Rev A repair session also had reference
and interconnect faults. Neither supports a claimed healthy CE headroom
margin for this resistor. Startup, oxygen/temperature extremes and loop
stability remain explicit tests below. No chart was visually digitized.

### CE ESD shunt

Primary inspection changed the previous conclusion that D7 was correctly
wired: **the old symbol grounded pin 2, but DBZ ground is pin 3**. The
correct complete orderable part is **TPD2E2U06QDBZRQ1**. D7 now connects
pin 1 IO1 to CELL_CE, pin 3 to GND, with pin 2 IO2 explicitly unused. The
non-Q1 TPD2E2U06 PDF was inspected first and lists different package choices;
it cannot establish this DBZ footprint's pinout. SLLSEJ9E p3 Table 5-1 and
the current ordering addendum p14 establish the exact Q1 selection directly.

D7 moves toward the cell CE land, with the CE connection passing through
its signal land and a short, dedicated ground via. TI SLVA680A p7 recommends
this flow-through topology and short return; SLYT492 p31 explains why an
IC may fail even while its external TVS survives the same discharge.

This is **CE transient mitigation, not qualified whole-probe ESD protection**.
SLLSEJ9E p5 §6.7 gives 6.5 V minimum breakdown at 1 mA (25 C), and
9.7 V typical clamp at 1 A TLP. Those are already above LMP91000's 6 V
absolute maximum between any two pins. R42 limits current into the AFE;
it does not prove a safe pin voltage. SNAS506I p4 footnote 2 identifies
snapback protection on non-power pins, so assuming ordinary rail clamps
would be wrong. No guaranteed high-current clamp ceiling or complete
system immunity level is established here.

D7 leakage is specified at **VIO = 2.5 V**, 10 nA maximum over the table's
temperature range. Do not extend that limit to every possible CE voltage.
Only CE is clamped: the spare channel is deliberately not connected to WE
or RE. RE's 900 pA maximum input-current specification (SNAS506I p5) makes
casual protection substitutions especially inappropriate. Leakage over the
actual CE voltage and temperature envelope remains a measurement gate.

## Qualification that needs hardware

1. On the assembled Rev B article, verify U5.2–PC7, U5.3–PC6, the two 47k
   pulldowns and D7 pin 3 ground continuity. Confirm receiver-on/driver-off
   at reset, bootloader reception, TX/RX turnaround and the selected standby
   policy, including lost-frame behaviour while reception is disabled.
2. With a cell simulator first, sweep both current polarities through the
   intended envelope (including the stated 130 uA target), supply corners,
   startup and bias changes. Measure CE_DRV and CE simultaneously. Confirm
   approximately I × R42 drop and compliance without oscillation or long
   settling. Then repeat with the real cell through its oxygen/temperature
   envelope. 85 C is outside the cited LMP gain-characterisation range.
3. Measure D7 leakage at the actual CE voltage extremes over temperature;
   record current offsets before/after fitting it. The 2.5 V table point
   alone is insufficient if the working CE voltage differs.
4. Set the product-level ESD target and discharge coupling arrangement.
   Measure residual pin voltage/current during controlled CE transients,
   and test functional recovery, calibration drift and latent leakage.
   Repeat on the intended enclosure/cabling/ground return. The TVS's own
   IEC rating is not a passed test of this probe. WE/RE immunity is outside
   this CE-only change and remains unqualified.

## Source access log (2026-09-09)

All attempted document downloads returned real PDF content on their first
HTTP fetch; no source remains behind a WAF, CAPTCHA or login. Retrieval was
ordinary curl from the official URL; extraction used the embedded PDF text
layer and the cited electrical tables/pinout pages were also rendered and
viewed. No intermediary model supplied numeric evidence. The table below
uses “inspected” for the sections used in this decision, not a claim of
reading unrelated sections. Vendor application notes provide the practitioner
axis as well as the device specifications. These documents are mutually
compatible; clamp limits versus AFE absolute maximum are a real design
limitation, not a contradiction to average away.

| ID | Official stable URL, version | Evidence and exact locator | Role |
|---|---|---|---|
| LMP | https://www.ti.com/lit/gpn/LMP91000 — SNAS506I, Dec 2014 | Inspected; identity/title and rendered p4 §6.1/footnote 2, p5 §6.5 | CE limits, snapback, compliance and RE input current |
| TVS-seed | https://www.ti.com/lit/gpn/TPD2E2U06 — SLLSEG9C | Inspected package-identification sections; title/package table, direct text extraction | Discovery only: non-Q1 part is not the DBZ selection |
| TVS | https://www.ti.com/lit/gpn/TPD2E2U06-Q1 — SLLSEJ9E, Oct 2022; ordering addendum Dec 12 2025 | Inspected; rendered p3 Table 5-1, p5 §6.7, PDF p14 orderable table | Correct pinout, full MPN, clamp and leakage limits |
| R42 | https://yageogroup.com/component-documentation/download/specsheet/RC0603FR-071KL — generated Sep 9 2026 | Inspected; rendered single-page part-specific specifications | 1k, 1%, TCR, power rating conditions |
| RE | https://www.ti.com/lit/gpn/THVD1410 — SLLSEY3E, May 2019 | Inspected; rendered p5 pin-functions table | Active levels, internal bias |
| Layout | https://www.ti.com/lit/pdf/SLVA680 — SLVA680A, Apr 2022 | Inspected; rendered p7 §2.4/Figures 2-6 and 2-7 | Clamp placement and return-path guidance |
| System | https://www.ti.com/lit/pdf/SLYT492 — Q4 2012 Analog Applications Journal | Inspected; rendered PDF p4, printed p31 | Component survival does not imply IC/system survival |

Official TI product pages for LMP91000, TPD2E2U06 and TPD2E2U06-Q1 were
also navigated and DOM-read in the isolated browser context to verify product
identity and discover datasheet links. These were supplementary successful
first-attempt HTML reads, not the source of the numeric limits. Their stable
URLs are https://www.ti.com/product/LMP91000,
https://www.ti.com/product/TPD2E2U06 and
https://www.ti.com/product/TPD2E2U06-Q1.

The initial browser connection to identified scratch port 9224 timed out;
no source navigation occurred there. An initial automatic approval rejection
was resolved by inspecting the scratch-profile command line, then using
working scratch port 56285. This session launched no browser process. At
cleanup, closing the private context returned TargetClosedError: that target
had already been closed externally. The Python client exited; no borrowed
browser process was killed.

Searches (Serper, Sep 9): `LMP91000 ESD protection series resistor counter
electrode clamp leakage`; `site:ti.com LMP91000 ESD protection CE resistor`;
`"TPD2E2U06QDBZR"`; `RC0603FR-071KL Yageo datasheet 1k 1% temperature
coefficient 100 ppm`. These challenge both the clamp assumption and the
resistor's temperature budget. No absence claim is made from search results.
The final evidence is manufacturer documentation, independent of search
snippets. Sources and hashes are indexed under `literature/ce-protection`.

## Validation and review

- KiCad 10.0.5 schematic ERC: **0 violations**. Schematic connectivity audit:
  **101 components, 85 nets, PASS**. The generator assigns 308 pins, including
  schematic-only power flags; **303 physical package pins** and 101 part
  values match the live generator in the candidate.
- Saved `pcbnew` fill and independent CLI `--refill-zones` DRC each report
  **0 copper errors and 0 unconnected items**. Reports retain **41 inherited
  non-copper warnings** and **5 inherited footprint-parity findings**: F3's
  polyfuse filter versus its existing zero-ohm resistor footprint, and the
  J105/J106 local no-relief substitutions/filter warnings. These remain
  visible release work. U6 pad 21 is now the correct explicit PB2 no-connect;
  stale footprint value/MPN/design-note fields were synchronized.
- **63/63 essential authored routes remain present and locked**, using the
  BOM39 candidate's essential verifier. Its full 156-item mode also checks
  old router-assist escapes that the baseline had already replaced; that
  full mode is not the accepted critical-route contract.
- Firmware hardware contract regenerated for 1000 ohm; both contract/capability
  staleness checks pass. Existing fabricated-Rev-A parser/capability checks
  pass, and **242/242 native firmware tests pass** on baseline 28b8a75 plus
  this change. No firmware behaviour was added beyond the generated constant.
- The migration checks the original source-board hash, preserves fabrication
  sidecars and existing authored copper except the named local changes,
  refills, and refuses to save on a failed build/fill or an open connection.
  KiCad assigns fresh UUIDs to added items; reproduction is geometric rather
  than a promised byte-identical board hash.

The receiver escape uses six vias outside the SMD solder lands. A local
0.3793 mm maximum jog of one adjacent 3V3D segment opens the corridor past the
DE via; no other supply routing was changed. R45 activated ground polygons
which had previously contained no pad and were removed as islands. Three
local ground stitches connect the involved front/back regions. A separate
extension of the existing narrow thermal-web ground strap reaches a proper
main-plane stitch outside the barrier; its cross-barrier width is unchanged.
D7 has a dedicated short ground stitch on the cell side. Thermal/ESD system
performance still requires qualification of this completed geometry.

The reviewer found and the implementation corrected:

1. A same-net CE crossing bypassed D7's land. The two branches now meet only
   within pad 1; the old overlapping cell-side tail was also removed.
2. Duplicate footprint references could be overwritten by the pad parser.
   The checker now reads bounded blocks and rejects duplicate references
   and unexpected repeated electrical pads before building dictionaries.
3. D7's placement comment quoted a displacement measurement from its former
   position. That obsolete number and rationale were removed.
4. Connectivity/fill boolean failure returns were ignored. They are now
   required to succeed before the live ratsnest can authorize a save.

### Guard review checklist

1. **Unevaluable input:** missing, empty, truncated, duplicate and inconsistent
   board data raise; failed connectivity builds/fills raise before save.
2. **Monotonicity:** missing R45, a wrong D7 ground, extra wrong R45 and duplicate
   pad are rejected. R42 mutations at 100R, 0R and 1M all fail; a more extreme
   value cannot restore PASS. Failed fill never falls back to cached copper.
3. **Preconditions:** the real candidate exercised the installed KiCad loader,
   zone filler and connectivity builder. Physical pins are compared against
   the live generator; a generated schematic alone cannot satisfy the check.
4. **Source of truth:** the input route is SHA-256 pinned. Verification prints
   hashes for the actual board, generator, checker and parser; the candidate
   manifest also fingerprints the migration code and constraints.
5. **Persistence:** there is no verification-result cache. Failure does not
   overwrite the output with a newly “verified” board.
6. **Provenance:** reports distinguish actual saved/CLI fills, static pin checks,
   inherited warnings, native tests and unperformed hardware qualification.
7. **Known-bad calibration:** empty/truncated files, missing/duplicate R45,
   duplicate pad, wrong D7 ground and all three resistor mutations were rejected.
   Removing RE copper failed the connectivity gate; modifying one byte of
   the pinned input failed before output creation. Mocked false-return filler
   and pre-build calls also failed despite an initially connected board.
8. **Fix versus mute:** actual copper, pad assignments and resistor value changed.
   No clearance, island-removal or DRC-severity setting was relaxed. The ground
   fix joined real filled regions; it did not discard an open report.

Measured local runtime: static pin/value checker **0.049 s**; real zone-fill
and connectivity gate **0.409 s** in the calibration run. The fail-closed
boolean tests do not add another fill pass. Timing is environment-specific,
not a benchmark guarantee.

### Integration check against newer committed firmware

Main HEAD advanced to `7c3b7a1` during this work. An isolated checkout of that
unmodified commit passed **251/251 native tests**, and the exact staged
hardware changes applied to that clean checkout also passed **251/251**.
The archived 242-test result above belongs to the earlier reviewed baseline.

A run in the actively edited main checkout failed the crash-mailbox test:
another session's uncommitted `regmap.c` change restricts crash clearing to
`CRASH_BUILD_ID_LO` (0x007F), while its test still writes `CRASH_BASE` (0x0077).
The reviewer traced the mismatch independently. That unrelated in-progress
runtime/test change is not part of this commit and was preserved. The final
commit's validation uses its staged contents on clean committed firmware.
