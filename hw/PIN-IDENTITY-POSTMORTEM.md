# U11 pin identity — first-article post-mortem

Date: 2026-09-01
Scope: `U11` (SGX-OX-ROHS-Mini), its symbol, its footprint, and the four review
passes that cleared them.

Status: **the pin-identity DEFECT is confirmed** (datasheet drawings, board
geometry, and the as-built board's behaviour). **The corrected wiring has NO
end-to-end confirmation.** Two defects: pin map, and no-solder.

> **Do not read this document as a closed case.** An earlier revision declared
> the wiring confirmed on the strength of the settling curve below. That was
> withdrawn — see *The 75.6 µA curve does not confirm the wiring*.

> **The settling capture, 2026-09-01.** After Fab swapped the two outer flying
> leads, the cell produced a clean DS-0637 Note 1 transient:
>
> | t (s) | `o2_raw` | `afe_mv` |
> |---|---|---|
> | 1074 | −0.40 µA | 1681 (cell disconnected) |
> | **1082** | **−75.64 µA** | **2207** (reconnected) |
> | 1090 | −64.13 µA | |
> | 1098 | −60.80 µA | |
> | 1114 | −55.72 µA | |
> | 1135 | −50.56 µA | |
> | 1149 | −47.74 µA | |
>
> Monotonic decay from an initial **75.6 µA**, inside Issue 2's 70–130 µA band,
> with the transient shape DS-0637 Note 1 predicts. The cell conducts through
> the TIA — but see below for why that is **not** confirmation of the wiring.

## The defect in one line

The cell's pin map was taken from a **prose sentence** in the datasheet instead
of from the **pin drawing**, and the physical part is `C · W · R`, not `C · R · W`.

## Ground truth

`DS-0637 Issue 2, 28-May-2026`, SHA-256
`4d1d4479580ab98bbc525aaf4aca353745b99368bc020a76d7f8ec12964ceae7` — the exact
document `FAB-READINESS.md` names, re-fetched 2026-09-01 and hash-matched, now
archived at
`compostlab-literature/datasheets/SGX-OX-ROHS-Mini oxygen sensor datasheet DS-0637 Issue 2.pdf`.

Its "Product Dimensions" figure carries a **bottom view** (solid opaque base
with the pins drawn as visible dots and a Ø0.64 callout; the sensing ring face
is drawn separately above it). Leader lines traced individually:

| leader | terminates on |
|---|---|
| `Counter` | **left** pin |
| `Working` | **centre** pin |
| `Reference` | **right** pin |

So the part is **`C · W · R`** viewed from the pin face, and **`R · W · C`**
viewed from the top, which is the view a KiCad footprint on `F.Cu` is drawn in.

The prose on the same page reads *"a 3-pin configuration (Counter, Reference and
Working electrodes)"*. That sentence is a **list of electrodes, not a pin order**,
and it is what `pdftotext` returns. It is the only place `C-R-W` appears.

## What the board has

| artefact | says |
|---|---|
| `gen_sch.py:277` | `CELL = symbol("SGX_OX_MINI", [("1","CE"),("2","RE"),("3","WE")], "U")` |
| `gen_sch.py:594` | `net("U11",1,"CELL_CE"); net("U11",2,"CELL_RE"); net("U11",3,"CELL_WE")` |
| `SGX-OX-ROHS-Mini_ISS2.kicad_mod` | pad 1 at `x=-2.54`, pad 2 at `x=0`, pad 3 at `x=+2.54`; `F.Fab` labels `C`, `R`, `W` |

Top-view required: `R(-2.54) W(0) C(+2.54)`.
Top-view built:    `C(-2.54) R(0) W(+2.54)`.

**This is not a mirror.** A mirror of `C-R-W` is `W-R-C`; the required order is
`R-W-C`. The centre position disagrees in every case: the board wires the centre
hole to `CELL_RE`, and the part has its **Working** electrode there.

### Consequence: no rotation can fix it

The three pins are on symmetric 2.54 mm pitch with no keying feature, so the part
drops in either way round — and a 180° rotation exchanges only the two outer
pins. The centre pin stays put. **Every possible insertion connects the cell's
working electrode to the LMP91000's RE input**, which is a high-impedance sense
input, so no closed three-electrode loop exists in any orientation.

## Bench evidence (2026-09-01)

Measured at the cell pins with the board powered and settled 51 min:

| node | measured | expected | verdict |
|---|---|---|---|
| `TP1` / `CELL_WE` | 1.678 V | 67 % × 2505 mV = 1678 mV (LMP91000 internal zero) | AFE correct |
| centre hole / `CELL_RE` | 2.278 V | 2279 mV | AFE correct |
| V_WE − V_RE | **−600 mV** | DS-0637 `-600 ± 10 mV` | **AFE correct** |
| `afe_mv` | 1771 mV | — | — |
| `o2_raw` | **−13.30 µA** | DS-0637 **Issue 2** `0.1 ± 0.03 mA` = **70–130 µA** in air | **wrong sign, 5–10× low** |

`(1678 − 1771) mV / 7 kΩ = −13.29 µA`, matching the firmware's reported −13.30 µA.
The internal zero, the bias, the TIA gain, the ADC and the conversion maths are
all confirmed correct by direct measurement. `o2p_lmp91000_verify` reads TIACN /
REFCN / MODECN back clean every cycle.

Every instrument-side check passes because the instrument is correct. The
measured 13.3 µA is not a weak oxygen signal — it is leakage through a cell that
was never connected as a cell.

## How it got there

1. **The pin map was never derived from a drawing.** `gen_sch.py:277` encodes the
   prose order. No figure was consulted for identity, at any point, by anyone.

2. **The design pass held the right document and took only geometry.**
   `DESIGN.md:227` records *"product drawing visually validated at 300 dpi"* and
   extracts body Ø14.40, height 8.30, three Ø0.64 pins, 2.54 pitch, pin-row
   offset 2.50, tolerance ±0.15, plus the undimensioned rear port. Six dimensions
   and a gap — every geometric fact the figure carries. The electrode labels
   printed on that same figure are absent from the extraction. `FAB-READINESS.md:151`
   repeats the tell in its own words: *"Body and **pin geometry**"*. Geometry,
   never identity. **Resolution was never the binding constraint**; 300 dpi is
   ample to trace those leaders.

3. **The `_DRAFT` footprint listed what was unverified, and pin identity was not
   on the list.** Its `descr` read *"…general tolerance +/-0.15 mm; rear-port
   diameter and production hole fit require physical verification"*. The `C`/`R`/`W`
   labels were already present in that first commit (`28c85de`) and were not
   flagged.

4. **The `_DRAFT` → `_ISS2` promotion silently blessed them.** The rename dropped
   the word DRAFT and the caveat sentence, and asserted *"footprint from DS-0637
   Issue 2"* — for a fact Issue 2 was never consulted about. Nothing re-derived
   the pin map at promotion.

5. **The independent reviewer had no primary source for this part.**
   `SCHEMATIC-REVIEW.md` lists nine datasheets — AP63205, OPA333, LMP91000,
   ADS1119, THVD1410, TPS7A20, STM32G071, AN2606, BMP390. **The SGX cell is not
   among them.** Its declared scope was `PLAN.md`, `DESIGN.md`, `gen_sch.py`,
   generated netlists, project footprints, placement notes, ERC and
   `audit_schematic.py` — all eight are project artefacts. For the cell it
   reviewed the design against itself.

6. **The absence was recorded as an engineering judgement.**
   `SCHEMATIC-REVIEW.md:199` filed *"SGX cell pin identity/sign convention"* under
   **"Fabrication-only mechanical and environmental gates"**, next to drill fit,
   body tolerance and aperture, and concluded it *"require[s] a physical sample"*.
   Pin identity is a documentary fact printed in a figure the reviewer did not
   hold. An unread source was written down as a considered deferral.

### The reviewer could do this — it did it twice, on the parts it had

- **AP63205**: gate verdict **FAIL** — *"U1's AP63205 package-pin mapping is wrong
  on every pin."* Same defect class, caught, blocking.
- **BMP390**: verified — *"pin map and 0x76 straps match Bosch DS002 Rev. 1.7,
  Figure 23/Table 52 p.47."*

Its method is visible in the evidence column of every verified row: *"pin table
p.3"*, *"WQFN pin table p.3"*, *"SOIC-8 pin table p.5"*, *"DBV top view and pin
table p.4"*, *"LQFP48 Figure 5 p.36, pin table"*. **The method was "find the pin
table."** The SGX one-pager has no pin table — only a labelled drawing — so the
part fell out of the method instead of escalating.

## The gate was carried faithfully and never discharged

`SCHEMATIC-REVIEW.md:199` → `FAB-READINESS.md:113` (*"Fit a real
SGX-OX-ROHS-Mini, gauge its pins, verify PCB-side CE/RE/WE"*) →
`ASSEMBLY-EXCEPTIONS.md:22` (*"U11 is also a physical gate … verify pin identity
from the PCB side"*).

Three documents, faithfully. Executed zero times. And it could not have worked
anyway: **an unkeyed part cannot be validated by inspection**, because every
orientation looks correct.

## The audits locked the error in

### Correction: `audit_schematic.py` is NOT one of them

An earlier revision of this document claimed `audit_schematic.py:82-86` encoded
the defect as a passing test. **That was wrong**, and the claim is retracted.
Its assertions

```python
"CELL_WE": {"U7.12", "U11.3", "TP1.1"},
"CELL_RE": {"U7.13", "U11.2"},
"CELL_CE": {"U7.14", "U11.1", "TP3.1"},
```

are **symbol pin numbers**, and the symbol was never wrong. `gen_sch.py:277`
has always declared pin 1 = CE, 2 = RE, 3 = WE, and `gen_sch.py:594` wires them
to the matching nets. The schematic's electrical intent was correct throughout.

The defect was **purely footprint geometry** — which pad *number* sits at which
*x* coordinate — so it lives entirely in the `.kicad_mod`, and that is where it
was fixed. Editing `audit_schematic.py` to match the physical pin order would
break a correct check and decouple it from the netlist it exists to verify.

This distinction is the whole anatomy of the bug and is worth stating plainly:
**the netlist was right, the symbol was right, and the pads were in the wrong
places.** Fixing it in the netlist instead would have left the footprint's
`F.Fab` `C`/`R`/`W` labels lying about the physical part — which is precisely
how the error survived review the first time.

(Credit: this correction came from the concurrent session that fixed the
footprint. My original claim was an assumption about which artefact carried the
error, asserted without checking whether the symbol numbering was independent of
the pad positions.)

`audit_pcb.py:499-503` then spends a bespoke guard — `U7.13`→`U11.2` must stay
under 10 mm because RE is high-impedance — and `audit_pcb.py:476` forbids a `TP2`
test point to protect that same net from wet leakage. Both are correct reasoning
about a reference electrode. Both are applied to `U11.2`, **the cell's working
electrode**.

(The absence of `TP2` is therefore a deliberate, guarded, sound decision. It is
not an oversight and must not be "fixed" by adding one.)

## Third defect: the cell is not a solderable part

Raised by Fab from the bench — *"i dont think this cell is made for direct
soldering, the plastic melts so easily and the pins get out of their positions."*

**This is a third, independent defect.** It is not a consequence of the pin-map
error and would have bitten a board with a perfect footprint. Rev A asks for an
assembly operation the part does not support.

**Evidence.** Both issues were searched for `solder`, `reflow`, `wave`,
`peak temp`, `MSL`, `moisture`, `J-STD`, `iron`, `260`, `250 C`, `profile`,
`mount`, `assembly`, `lead-free process` — **0 hits in either issue.** For a
through-hole part in an ABS housing, a total absence of any soldering or
handling guidance is a specification by omission.

The positive evidence is stronger than the omission. The **only** temperatures
DS-0637 specifies for this part, in any state, are:

| | |
|---|---|
| Operating temperature | −40 °C to **+60 °C** |
| **Storage temperature** | **0 °C to +20 °C** |

The highest temperature this datasheet permits the part to reach, anywhere, is
**60 °C** — and it will not tolerate being *stored* above 20 °C. A soldering
iron runs 300–350 °C. The industry norm for electrochemical gas cells is sockets
or spring contacts, and this datasheet is consistent with that norm.

**This retro-fits the first failure.** The original cell lost a pin to iron heat
softening the ABS *before* any disassembly began. That event was logged as an
accident during desoldering. It was not operator error — it was the first
symptom of this defect, and it was misfiled at the time.

> ### Confound: hold this before interpreting the next reading
>
> **Both** cells that have been on this board have taken iron heat directly on
> their pins, and heat conducts to the electrolyte and the electrode stack. A
> cell can survive soldering mechanically and still come out electrochemically
> degraded.
>
> So if the outer-lead swap is correct and the current still returns low,
> **thermal damage is the next suspect, not a new electrical mystery.** The two
> are indistinguishable from the electrical data alone, and a day has already
> been lost to one misattribution. Bench work on the swap should use micro-hook
> clips, not solder, so the test adds no further thermal cycles.

### Rev B: socket the cell — a blocker, not a nicety

Machined pin receptacles on 2.54 mm pitch for the Ø0.64 × 4 mm pins. Solder the
socket; insert the cell afterwards. Nothing suitable is in InvenTree, so this
needs sourcing. Three independent reasons, any one of which is sufficient:

1. **No heat ever reaches the cell.** Closes this defect outright.
2. **The cell becomes field-replaceable** — mandatory for a >60-month consumable
   in a probe destined to be buried and potted. Today established that "remove
   the cell" currently means "destroy the cell."
3. **A keyed socket plus honest `C`/`W`/`R` silkscreen is the durable fix for the
   pin-identity failure class at *both* levels** — the footprint and the hand
   rework. It converts the rule in the section above into a physical constraint,
   which is the only form that survives a confident repair.

## WITHDRAWN: the firmware sign and `INT_Z` are NOT defects

An earlier revision of this document recorded two further defects — an inverted
sign in `code_to_cell_na`, and `INT_Z = 67 %` allocating headroom the wrong way,
with a clipping analysis showing 30 % O2 exceeding VREF. **Both are withdrawn.
The firmware and the AFE configuration are correct.**

**Documentary evidence, from the vendor document that defines the convention.**
TI SNAS506I, page 6 spec table, footnote (7):

> *"For negative bias polarity the Internal Zero is set at 67% VREF."*

TI pairs a **negative-bias** sensor with the **high** internal zero. That pairing
only makes sense if the signal swings **downward** from the zero. `lmp91000.h`
was following TI's own stated recommendation, not betting against it.

**And the physics agrees.** At the working electrode O2 is *reduced*, consuming
electrons that the electrode draws from the external circuit. Electrons flow
wire -> electrode, so conventional current flows electrode -> wire, i.e. **into**
the LMP91000's WE pin. Current entering the TIA summing junction must leave
through R_TIA toward the output, which puts **VOUT below the internal zero**.

So `code_to_cell_na` computing `zero_uv - uv` — positive current = VOUT below
zero — is **correct**, and the downward span of 1678 mV = **240 uA** comfortably
clears the 197 uA worst case at 30 % O2. There is no clipping problem.

**`SCHEMATIC-REVIEW.md` M4 therefore stays OPEN.** An earlier revision claimed
its sign-convention gate had been closed empirically and against the design.
Withdrawn: that measurement was taken through wiring now believed to be still
incorrect, so it settles nothing about the convention.

### The 75.6 uA curve does not confirm the wiring

The capture shows correct **magnitude**, correct **transient shape**, and
**inverted sign**. That combination is fully reproduced by a different
miswiring: **W and C swapped**. In a three-electrode cell the counter electrode
carries the same current as the working electrode with opposite sign, so putting
the TIA on C yields a textbook-looking curve with the sign flipped.

Note this is physically reachable here precisely *because* the Rev A board in
hand still has the **old** hole order (`CE`, `RE`, `WE` at -2.54, 0, +2.54). The
correct rework is therefore **not** centre-to-centre — cell W (centre pin) must
reach the +2.54 hole — so a hand-wiring permutation that moves W is available in
a way a footprint mirror never was.

**Falsifiable prediction.** With C -> `CELL_CE` (-2.54), W -> `CELL_WE` (+2.54),
R -> `CELL_RE` (centre), `o2_raw` should read **positive, 70-130 uA**, with
`afe_mv` **below** 1678 — about **1188 mV** for a 70 uA cell (1678 - 70 uA x
7 kOhm), down to 768 mV at 130 uA. A repeat of the inverted result falsifies the
wiring hypothesis rather than the sign convention.

> ### Method lesson 3: a confirming observation is a reason to check the model
>
> The 75.6 uA curve was the most convincing evidence produced all day, and it
> was consistent with two very different wirings. A wrong model that *predicts*
> the observation is far harder to dislodge than one that does not — you get a
> result that "works" and stop looking. **An observation that confirms your
> model is the moment to check the model, not to promote it.**
>
> Both failures here were one `curl` from being avoided: the vendor document
> defining the convention was never opened, and a device polarity was asserted
> from memory instead. That is the same failure as the 45 Ohm estimate, which
> imported an unverified current limit while the measurement sat unread.
>
> **This document's own failure is narrower and worth recording.** The
> derivation above — reduction at WE puts current *into* the summing junction,
> so VOUT goes *down* — was performed here **before** the section was written,
> and it contradicted the mechanism being proposed. What got recorded was a
> hedge ("flagged rather than asserted") instead of the contradiction. A
> flagged doubt is not a check, and hedging let a wrong conclusion into the
> document with a disclaimer attached. **State the contradiction, or resolve it
> — do not annotate it.**

### Cost of the pad fix: `/HEATER_PWM` now runs beside `CELL_RE`

Recorded here so it is not rediscovered later as a mystery. Moving `RE` east is
inherent to the correction, and it brought `/HEATER_PWM` to **0.252 mm** from
`CELL_RE` (was 1.375 mm) at its `(112.00, 135.00)` turn — inside the thermal
pour gap, the one place the guard cannot reach because zone fill is forbidden at
`y = 133–135`. Legal by DRC, but it is a **switching net beside the
high-impedance reference electrode**. Guard flanking below the gap is now 23/24,
was 24/24.

The heater is disabled in v0, which is a schedule reprieve and not a fix. It must
be corrected before the heater is ever enabled — by moving `HEATER_PWM`'s barrier
crossing to another layer; the locked 14-segment count survives a layer change.

## Corrective actions

### Done (2026-09-01)

- DS-0637 Issue 2 re-fetched, hash-verified against `FAB-READINESS.md:151`, and
  archived in `compostlab-literature` with its SHA-256 registered. It previously
  existed only under `/tmp/o2-datasheets` — `SCHEMATIC-REVIEW.md:242` states *"no
  literature archive was added to the project"* — so the document grounding the
  footprint had been lost. Issue 2's pin figure is identical to Issue 1's.
- `SCHEMATIC-REVIEW.md` marked **discarded for U11**.
- `audit_pcb.py` gained a pin-map provenance check (`PINMAP_PROVENANCE`),
  scoped to project-library footprints with ≥3 pads.
- `kicad-design` skill updated: `FOOTPRINTS.md` pin-identity rules, `SETUP.md`
  reviewer source preconditions and the discard rule.
- `BMP390_LGA10_DRAFT` provenance recorded (Bosch DS002 Rev. 1.7 Table 52 p.47,
  TOP view, table-derived).

**Footprint corrected in the library by a concurrent session**, independently and
correctly. Verified here against the pads themselves rather than its description:

| pad | signal | x | |
|---|---|---|---|
| 1 | `CE` | −2.54 | |
| **3** | **`WE`** | **0** | centre pad is now Working, matching the part |
| 2 | `RE` | +2.54 | |

Symbol pin numbering is unchanged, so only pad positions moved — the minimal
correct fix. The chosen `C·W·R` top-view arrangement is the 180° insertion, and
its stated rationale checks out on measurement: `U7.13` (the LMP91000's RE input)
sits at `x = 111.0`, right of centre, so this insertion puts `CELL_RE` **9.723 mm**
from it, inside the `<10 mm` guard, while the alternative would be **10.232 mm**
and would break it.

### Open — required before this fix reaches anything

Owned by the concurrent session that made the footprint fix; listed here for
completeness, not as unassigned work.

1. **Regenerate the board.** `audit_pcb.py` reads the footprint copies *embedded
   in* `o2-probe.kicad_pcb`, not the library, so a library-only fix is invisible
   to both the board and the audit until the footprints are synced. The
   reproducible evidence is the KiCad DRC **`lib_footprint_mismatch` on U11**.
   The board still carries the old pad order.
2. **Update `audit_pcb.py`'s expected pad geometry**, now stale against the
   corrected library: it asserts `"2": (110.0, 141.0), "3": (112.54, 141.0)`,
   which must become `"2": (112.54, …), "3": (110.0, …)`. The `U7.13`→`U11.2`
   distance guard still passes at 9.723 mm. This one *is* a hand-typed expected
   value that went stale the moment the artefact changed — the real instance of
   the pattern rule 5 below describes.
3. **Add the provenance tokens to the SGX footprint `descr`.** Its corrected
   provenance is currently written as prose, so `PINMAP_PROVENANCE` still flags
   it. Now that the pads are right, adding `pinmap:` / `view:` / `leaders:` is a
   legitimate record rather than a mute button.

### Separately: DS-0637 Issue 2 moved the output spec

| | Issue 1 (07-Apr-2025) | **Issue 2 (28-May-2026)** |
|---|---|---|
| Output signal in air | 0.07 ± 0.03 mA (40–100 µA) | **0.1 ± 0.03 mA (70–130 µA)** |
| Bias voltage | −600 ± 10 mV | −600 ± 10 mV (unchanged) |

Nominal range, maximum overload and zero signal are unchanged. Eleven sites in
this repo still quote the Issue 1 band. Most are explanatory comments, but two
are worth attention:

- `firmware/src/o2.h:73-74` — the air-point acceptance window is
  `O2P_AIR_CAL_MIN_NA 20000` … `O2P_AIR_CAL_MAX_NA 200000`. **No functional
  defect**: it was deliberately widened beyond the datasheet population, and
  Issue 2's 70–130 µA band sits well inside it. Only its justifying comment is
  stale.
- `firmware/src/o2.h:81` — `O2P_CAL_AIR_NOMINAL_NA 70000` **is** Issue 1's
  nominal and should become `100000`. Impact is limited because this value is
  only used when no calibration exists, which sets `CAL_DEFAULT` and already
  invalidates `O2_COMP`; but it is the wrong number against the current issue.

Also note the RTIA sizing in `lmp91000.h` (7 kΩ, ~152 µA at 30 % O₂) was derived
from a 100 µA air current, i.e. **Issue 2's nominal**, so the headroom analysis
survives unchanged. Re-checked against Issue 2's worst case: a 130 µA cell gives
197 µA at 30 % O₂ = 1.38 V across the TIA, still inside the 1.678 V available
below the internal zero. It is the acceptance bands that move, not the hardware.

### Rev A bench fix

Lift `U11` and refit it on three short wires, **crossing W and R**. Board holes
are `A(-2.54)=CELL_CE`, `B(0)=CELL_RE`, `C(+2.54)=CELL_WE`:

- cell **C** → hole **A** (straight)
- cell **W** → hole **C** (centre pin crosses out to the far hole)
- cell **R** → hole **B** (outer pin returns to the centre)

Identify the cell's pins from its **pin face with the vent hole uppermost**:
`C · W · R` left to right. Allow the full 15-minute settle (DS-0637 Note 1);
expect **+70…130 µA** (Issue 2 band).

### Bench status — first rewired attempt FAILED

The original cell was **destroyed during desoldering**: a pin pulled out of the
ABS body under heat, taking the top seal and the gold-on-carrier working
electrode with it. A cell was refitted on flying leads with W and R crossed.
Result, n = 45 post-settle:

| | measured | expected if wiring were correct |
|---|---|---|
| `o2_raw` | **−0.43 µA** (≈ zero) | +70…130 µA |
| `afe_mv` | 1681.2, flat | ≈ 1678 − I·R_TIA |
| `WE` | 1.678 V | 1.678 V |
| `RE` | **1.657 V** | 2.278 V |
| `CE` | 1.644 V | — |
| V_WE − V_RE | **+21 mV** | −600 mV |

**The bias is not being established at all**, while the LMP91000's own registers
verify correct and `AFE_CONFIG_MISMATCH` is clear. All three electrodes sit
within 34 mV of each other and of the internal zero.

It is not yet known whether the damaged cell or an undamaged spare was refitted
— that is the single highest-value unknown and it is being checked first.

**Hypothesis (a), a degenerate/shorted cell, is refuted.** It was proposed here
on the grounds that CE is not railed, which looks like a current-limited
amplifier driving a near-short (estimated ~45 Ω). Two independent refutations:

1. **`WE` is the TIA summing junction, so it is a direct ammeter on that node.**
   Any CE→WE path is measured. A 45 Ω path at 34 mV would pass 756 µA, which
   through R_TIA = 7 kΩ demands a 5.3 V output swing — hard railed. Measured
   `afe_mv` is 1681.2 against a 1678 zero, i.e. **0.457 µA**. Inverting gives
   **R ≥ 74 kΩ**, and realistically far more since much of that 0.43 µA is
   probably amplifier offset rather than real current. The estimate was wrong by
   ~1650×. Note this bound needs **no** assumption about the LMP91000's CE drive
   limit — the datasheet parameter the estimate leaned on was never required.
(A second argument was offered — that `RE` drifting 10 mV between readings while
`WE` moved 1 mV proved `RE` was *floating*, hence the connections were open.
**That argument is withdrawn; see below.** Hypothesis (a) remains refuted by the
ammeter bound alone, which needs no assumption about drift.)

### The connections are NOT open either — measured

The decisive measurement was taken with the **cell removed**, establishing this
board's true open-circuit signature:

| | `WE` | `RE` | `CE` |
|---|---|---|---|
| **no cell** | 1.677 V | **0.003 V** | **0.001 V** |
| **cell fitted** | 1.677 V | **1.657 V** | **1.644 V** |

A genuinely open loop rails `RE` and `CE` to the bottom rail, 1–3 mV. With the
cell fitted they sat at ~1.65 V — 550× and 1640× away from that signature. **The
cell was connected and loading the loop throughout.** "Open connections" is dead.

The withdrawn inference was that a drifting node must be untied. A 10 mV wander
is equally what a *real electrode* does when sensed by a high-impedance input
that is not holding it. The reference signature for "open" simply had not been
measured yet, and the strong reading was asserted without it.

> **Method lesson, and it caught both sessions within one hour.** The 45 Ω
> estimate reasoned from a voltage and imported an unverified vendor current
> limit while `afe_mv` — a direct ammeter on the very node in question — sat
> unread in the data. The floating-`RE` claim named a failure mode without ever
> measuring what that failure mode looks like on this hardware. Two rules:
> **when a node is instrumented, read the instrument before modelling the node**;
> and **before claiming a failure mode, measure its signature on the actual
> hardware** — the known-bad calibration rule, applied to diagnosis rather than
> to guards.

### Leading hypothesis: the two outer flying leads are swapped

| LMP91000 pin | is wired to | consequence |
|---|---|---|
| `WE` | cell **W** ✓ | correct — why the TIA still behaves |
| `RE` | cell **C** ✗ | counter electrode sensed high-Z, free to wander → the drift |
| `CE` | cell **R** ✗ | **the amplifier drives the reference electrode** |

A reference electrode passes essentially no current by design, so the loop is
driven into the one terminal that cannot conduct. That predicts every
observation at once: cell connected, loop loaded, electrodes at plausible
mid-rail potentials, bias unestablished, and ≈ 0 µA into the TIA.

Verified here: mirroring the rework swaps **exactly the two outer leads** and
leaves `W → CELL_WE` untouched, because W is the centre pin. Identification rule
for the fix — hold the cell with the **pins toward you and the vent at the top**;
left to right is then `C · W · R`. From the body side it reads mirrored. Swap the
two outer leads; do not touch the centre one.

### The workaround is the same defect, one layer up

This deserves stating plainly rather than as an aside. We responded to a
pin-identity defect by hand-building a **new pin mapping with no key, no
silkscreen, no audit, and no continuity check before power-up** — three flying
leads, deliberately crossed, on a part whose electrodes are physically
indistinguishable. Every property that made the original defect possible is
present again in the fix.

If the leads turn out to be wrong, that is not bad luck. It is the same root
cause recurring inside its own remedy, and it is the strongest argument in this
document for rule 6 below: **an unkeyed mapping must be verified electrically
before power is applied**, whether it was made by a PCB house or by hand at the
bench five minutes ago. A rework is a pin map. It gets the same gate.

**And on current evidence it is not hypothetical — it is literally the case, and
it is the same error.** The leading hypothesis above is that the two outer leads
are swapped, which is a **mirror**: the identical viewing-side confusion that
produced the `C-R-W` footprint in the first place. The same mistake recurred
inside its own remedy, within hours, made by hand, by people who had just spent
a day diagnosing it — and it recurred precisely because the remedy was exempted
from the rule the diagnosis had just established.

That is the finding to carry out of this document. A pin-identity rule that
applies only to footprints, and not to the bench rework that fixes them, does not
work. The moment of highest risk is not the original design; it is the confident
repair.

**Method note carried over from this failure:** an earlier claim in review that
"RE reads 2.278 V regardless of wiring, because the amplifier forces
V_WE − V_RE = −600 mV" is **wrong**. It holds only while the loop can close at
the demanded bias. When it cannot — as here — RE moves, and it turns out to be
the *most* diagnostic of the three electrodes rather than an invariant. A
control loop's setpoint is evidence about the loop's health, never a constant
you can assume.

### Rev B

- Correct the footprint pad net assignment and the `F.Fab` `C`/`R`/`W` labels,
  which currently assert the wrong order.
- Move pin-identity labels to `F.SilkS`. They are on `F.Fab` today, i.e. invisible
  on the physical board. For an unkeyed part, silkscreen is the last line of
  defence and costs nothing.
- Regenerate `audit_schematic.py`'s expected net map **from the figure citation**,
  not by hand alongside the design.
- Keep `TP2` absent and keep the `U7.13`→`U11.2` proximity guard, but re-point it
  at whichever pad carries `CELL_RE` after the fix.

## Rules adopted

1. **A pin map comes from a drawing, never from prose, and never from
   `pdftotext`.** A sentence listing signal names is not a pin order.
2. **Record the view and the traced leaders**, because neither can be written
   down without being performed. Leaders cross; label stacking order is not pin
   order. A proximity heuristic returns the *wrong* answer on this exact figure.
3. **A reviewer without the primary source is not a reviewer.** Its findings on
   that component are void and must be discarded, not downgraded or caveated.
4. **Reviewers get a browser and every datasheet before they start.** A review
   that cannot reach a source reports a blocked read, never a deferral.
5. **An audit's expected value must not share an ancestor with the thing it
   checks**, or it converts the defect into a passing test.
6. **An unkeyed part cannot be validated by inspection.** Its identity must be
   established electrically, on the real part, before the board is populated.
   For this cell: bias at −600 mV through a resistor and find the pin pair giving
   ~70 µA in air. Ten minutes, before any solder.
7. **A deferral must cost something every time it is carried**, or it becomes
   furniture — as it did across three documents here.
