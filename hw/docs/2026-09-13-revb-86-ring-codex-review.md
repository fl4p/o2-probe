# Rev B 86 mm ring board — independent Codex review, 2026-09-13

**Outcome: gate NOT issued.** Reviewer recommendation: *DO NOT ISSUE*. No
`review-gate.json` exists for `routing/revb-86-ring`; do not order this board.

| | |
|---|---|
| Commit reviewed | `2dc5d15` (board work `d875ef1`..`aec4509`, tooling `2dc5d15`) |
| Reviewer | `codex exec`, codex-cli 0.154.0, reasoning xhigh, workspace-write + network, Playwright over CDP |
| Access proven | curl `https://docs.kicad.org/` -> 200; the author's own scratch Chrome showed a tab `https://docs.kicad.org/` titled "Documentation \| KiCad" |
| Log | `~/codex-reviews/o2-revb86-ring/review.log` (374 kB, exit 0) |
| Reviewer limitation | full CLI and Python DRC aborted in its sandbox (macOS app registration); its run did not reproduce the 12-warning DRC. Refill, Gerber plotting and ERC (0) did run. |

## Author's verification of each finding (not a relay)

1. **J107 SCL beside the analog nets — CONFIRMED, but mis-attributed.** Measured
   on both boards: SCL↔`/CELL_WE` minimum edge gap is 0.100 mm on F.Cu at
   Y 116.9 on the *accepted* revb-86 board as well — inherited, not new. The new
   regression is on B.Cu: J107's SCL run at X 101.2 (Y 104.85..113.85) passes
   **0.100 mm from `/GUARD_REPLICA`** at X 101.5, where revb-86 kept **0.625 mm**.
   A 100 kHz clock beside the working-electrode guard is a real analog defect,
   introduced by the J107 routing (`dd45b61`). Blocker.
2. **Verifier does not pin geometry — CONFIRMED.** Moving the added SCL segment
   (101.2,104.85)-(101.2,113.85) to (110,110)-(110,112) still returns PASS.
   Added/removed copper is pinned only by (type, net) count; new footprints
   omit angle, shape, mask/paste overrides. Blocker.
3. Tip ground dependencies (U10.2/C20.2 via a 6.37 mm, 3-via link; U12.4 via a
   single via) — should-fix, not yet re-measured by the author.
4. Spreader: one 215.13 mm² island; left-land bottleneck 0.68 mm at X 108.8 —
   connectivity proven, thermal adequacy not.
5. J5/J107 emit F/B.Paste apertures — needs an assembly disposition (pre-tin
   or suppress). Design decision for Fab.
6. `tools/route.py` hole-to-hole default 0.25 mm vs project 0.30 mm — no
   violation resulted (nearest new drill gap 0.578 mm); fix the default.

## Reviewer's final sections, verbatim

### FINDINGS

1. **(c) blocker — J107 SCL enters the electrode/guard corridor.**  
   The new 9 mm B.Cu segment runs from **(101.2,104.85) to (101.2,113.85)**, between `/CELL_WE` and `/GUARD_REPLICA`. SCL–WE clearance falls **2.274 → 0.100 mm**; SCL–guard clearance falls **1.989 → 0.100 mm**. The electrode copper remains unchanged, but its surroundings do not. This introduces a clock interference path that generic manufacturing clearance cannot qualify. Reroute it or establish a measured AFE-noise disposition before ordering.

   Location: [board:33041](/Users/fab/dev/ee/hw/o2-probe/routing/revb-86-ring/o2-probe.kicad_pcb:33041). Evidence: `KIPY /tmp/codex-o2-ring-review/measure.py` and `details.py`; [comparison image](/tmp/codex-o2-ring-review/scl-analog.png). Noise magnitude remains unverified.

2. **(c) blocker — the verifier does not pin every allowed change.**  
   Added/removed copper is principally checked by **type/net counts**, allowing arbitrary geometry on permitted nets. New-footprint checks omit pad angle, shape, mask/paste overrides and complete serialization.

   `KIPY /tmp/codex-o2-ring-review/mutations.py` returned **PASS** after each of these independent mutations:

   - Moving an added SCL track to `(110,110)..(110,112)`.
   - Moving an added UART via to `(110,110)` and enlarging it to **1.0/0.6**.
   - Rotating one J5 rectangular pad **90°**.
   - Adding J5 solder-mask margin **−0.6 mm**.

   Locations: [verifier:112](/Users/fab/dev/ee/hw/o2-probe/verify_revb_86_ring.py:112), [verifier:181](/Users/fab/dev/ee/hw/o2-probe/verify_revb_86_ring.py:181). [Mutation results](/tmp/codex-o2-ring-review/mutation-results.json). Pin complete added/removed records and new footprints. The outer gate still rejects changed source hashes; these are demonstrated verifier failures, **not a demonstrated bypass of that hash gate**.

3. **(b) should-fix — new tip ground dependencies reduce return robustness.**  
   **U10.2/C20.2** now occupy a **14.63 mm²** F.Cu component returned through four **0.15 mm** tracks totaling **6.373 mm**, with three added vias. Transitions at **(106.1,132.35)** and **(103.35,132.15)** are individually indispensable. The existing local via does not provide an independent return.

   **U12.4**, at `(102.8,135.9)`, now occupies a **0.832 mm²** pocket dependent on the single **0.4/0.2 via at (102.3,135.9)**. These dependencies are new. They are electrically connected; measured annular contact is approximately **95–100%**, so they are not sliver contacts.

   Evidence: `measure.py`, `details.py`, `final_metrics.py`; [tip geometry](/tmp/codex-o2-ring-review/tip-copper.png).

4. **(b) note — the spreader has a real connection with a narrow thermal corridor.**  
   Fresh native refill produces **one 215.13 mm² island**, containing both back J5 lands, RH1.2, RH2.2 and Q2.3. The left-land-to-body bottleneck measures **0.6796 mm**, including **X108.825, Y138.0199..138.6995**. Polygon erosion independently gives the same limiting width. Both land vias have full B.Cu annular contact.

   Evidence: `KIPY /tmp/codex-o2-ring-review/refill.py` succeeded in **0.543 s**; `measure.py` measured the corridor. This establishes connectivity and width, not adequate thermal conductance or transferability of the predecessor’s thermal measurement.

5. **(b) should-fix for stencil ordering — hand-solder lands emit paste apertures.**  
   Native Gerbers contain **2.8 × 2.0 mm apertures at both J5 positions on both paste layers**. Paste is reasonable only if intentional pre-tinning belongs to the assembly process; that disposition is missing. Suppress these apertures for hand-solder-only assembly or explicitly document pre-tinning. Apply the same decision to J107.

   Location: [land definition:97](/Users/fab/dev/ee/hw/o2-probe/lib/o2-probe.pretty/Heater_Ring_Lands.kicad_mod:97). Evidence: `plot_gerbers.py` and emitted F/B.Paste flashes under [exports](/tmp/codex-o2-ring-review/exports).

6. **(c) note — router hole spacing differs from the fabrication profile.**  
   [route.py:58](/Users/fab/dev/ee/hw/o2-probe/tools/route.py:58) defaults hole-to-hole spacing to **0.25 mm**, while the project requires **0.30 mm**; `drive.py` does not override it. No resulting violation was measured here: the nearest new-via drill gap is **0.578 mm**, at `(116.85,102.4)`.

   Evidence: targeted source inspection and `KIPY /tmp/codex-o2-ring-review/manufacturing.py`.

### SURVIVED

- **Protected copper and retained objects:** `/CELL_RE`, `/CELL_WE` and `/GUARD_REPLICA` native track/via records are exact. Retained footprints are compared completely, rather than merely matched by UUID. Duplicate root UUIDs are rejected.

- **Zone settings, metadata and C12:** unfilling removes saved fill geometry while retaining fill-affecting settings. Changing minimum thickness correctly fails. C12’s exception permits precisely the property-layer change; unhiding it fails. Metadata/setup/layers are compared. `.12g` formatting constructs expected tokens; it does not round arbitrary candidate values into acceptance.

- **Known-bad calibrations:** the unlocked land via and the actual two-island fill from `604b2c3` both return **UNVERIFIED** for the stated reasons. A synthetic hole test confirms `Contains` respects holes. Its pad-centre test remains a contact check, not a thermal-width or pad-coverage check.

- **Ground fragmentation:** the reported counts reproduce:

  | Fill | Islands | Largest island, mm² |
  |---|---:|---:|
  | F.Cu | 14 → 19 | 618.98 → 354.70 |
  | B.Cu | 21 → 24 | 657.92 → 354.58 |

  Including tracks, pads and through connections, **every GND component reaches input ground**. No new upper-board single-via bottleneck was found. The separated regulator/transceiver ground component has three vias; the MCU component has four. U7’s dependencies at **(108.475,114.1)** and **(105.75,112.75)** are inherited. Local AFE ground fill at X104..118/Y107..117 is essentially unchanged.

- **I²C topology and lengths:** J107 adds **60.030 mm SCL/3 vias** and **47.652 mm SDA/2 vias**, consistent with the approximate claims. Whole-net lengths become **149.647 mm SCL** and **114.235 mm SDA**. The tip SCL branch measures **11.764 mm**. R10/R11 remain **4.7 kΩ**; schematic and firmware agree on **0x48/0x49/0x44**, at **100 kHz**. LMP_C1/LMP_C2 separation is unchanged; TMP_CELL_EP separation improves or stays equal. Flying-lead capacitance and rise-time limits remain unverified.

- **Manufacturing geometry:** **85 footprints, two layers, 1.6 mm**, correct J5 placement and **0.350 mm edge clearance**, locked **0.6/0.3** land vias, and compliant small-via dimensions. Project/rules files are byte-identical to the accepted package’s profile. Shortened slots and directed contour pass the native-Gerber comparison.

- **Witness/exporter:** candidate-derived drills appropriately check export fidelity. Native inventory is compared against independently parsed Excellon geometry: **219 PTH and 8 NPTH** match; moving one exported drill **0.010 mm** fails. All twelve listed local producer files—including the named imported exporters/checkers—are fingerprinted. Old-board hashes in GUARD endpoint rows fail. The **Y117..119 thermal-gap clip remains correct and clear**. Schematic-audit tests reject missing/UNVERIFIED results, wrong counts, duplicates and missing/wrong hashes. [Tool-check results](/tmp/codex-o2-ring-review/tool-checks.json).

- **Validation limitation:** fresh **ERC = 0 violations**. Native refill and native Gerber plotting succeeded. Full CLI DRC repeatedly aborted in macOS application registration; Python DRC also failed. Therefore the author’s exact **12 warnings / zero errors / zero unconnected / zero parity** result is **unverified in this run**, and no complete silk/mask DRC clearance claim is made.

### GATE RECOMMENDATION

**DO NOT ISSUE** — blockers **1: SCL/electrode routing regression** and **2: verifier geometry omissions**. Fresh complete DRC also remains unverified. Ground-return, thermal and stencil dispositions remain necessary before ordering.


