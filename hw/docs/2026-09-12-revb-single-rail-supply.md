# Rev B: collapsing the supply to one 3.3 V rail

**Status: proposal with one open measurement gate.** Nothing in `gen_sch.py` has
been changed. Fab's decision on 2026-09-12 is that this lands in **Rev B**, not a
later revision; what follows is what the datasheets allow and the one number that
is still missing.

Goal, in Fab's words: **fewer parts.** Energy is secondary — `POWER-BUDGET.md`
already shows the heater is 90-98 % of the budget at any nonzero duty.

## 1. What is actually on 5 V

Every `+5V` / `+5V_ANALOG` consumer in the schematic (`gen_sch.py:498-595`):

- U2 `TPS7A2033` input (-> 3V3D)
- U3 `TPS7A2033` input (-> 3V3A), behind R32 = 10 R + C7
- R41 = 1 k, the AZ431 shunt bias

Nothing else. Every IC on the board is a 3.3 V part; the heater is on `+12V_SW`
and is unaffected. **The 5 V rail exists only to give the AZ431 its headroom**
(`gen_sch.py:581`, `DESIGN.md:53-55`). Remove the shunt and the rail has no
remaining reason to exist.

Correction to `power_budget.py`, found while costing this: the script has **no
AZ431 line**, so its "17.15 mW / 233 d" omits the shunt's 2.5 mA at 5 V - the
second-largest always-on load on the board. `POWER.md` §2 does count it. Real
as-built is ~32 mW, ~127 d on 10 Ah LiFePO4 with the heater off.

## 2. The proposal: one LDO as analog supply AND reference

> **SUPERSEDED 2026-09-12 by section 8 — do not build from this section.** The
> 2.500 V variant below is dead on a fact this section never checked: SNAS506I
> Table 6.3 gives the LMP91000's supply range as **2.7 to 5.25 V**. Read section 8
> first; the surviving recommendation is Path A, and the CE gate in section 3 is
> overstated.

12 V -> buck **3.3 V** (digital, direct) -> **one LDO** whose output is both the
analog supply and `VREF_TRIM`. Deletes U2, C5, C6, U15, R41, C9, R31, C10 =
**8 parts**, leaves two regulators on the board, and - unlike a bare buck-to-3.3
- keeps an LDO between the switcher and the AFE, so the PFM/burst and RS-485
transient noise never reaches the analog domain.

Ratiometry survives: one node still feeds the LMP91000 REF pin and the ADS1119
REFP, which is what `sampler_logic.h:33-37` requires.

The reference metrology also survives, and it is stronger than it looks:
`main.c:709` measures `VREF_TRIM` **absolutely** by reading the R34/R35 half
divider against the ADS1119's *internal* 2.048 V reference (±0.25 %, 5 ppm/°C,
SBAS925 p.329), faulting and restarting settling if it leaves the trim band. The
LDO's real output is therefore observed every cycle, not assumed.

### 2.1 The voltage is forced to 2.500 V, not 3.0 V

The LMP91000 bias is a *percentage* of the reference, and the ladder offers only
1, 2, 4, 6 ... 24 % (`lmp91000.h:118-124`). An exact -600 mV therefore admits
only three references: 3.000 V @ 20 %, 2.727 V @ 22 %, 2.500 V @ 24 %.

From a 3.3 V rail only **2.500 V** is legal. TPS7A20's entire electrical table is
specified at `VIN = VOUT(NOM) + 0.3 V` minimum (SBVS338H §5.5); the 3.3 V rail's
worst case is 3.234 V (`DESIGN.md:54`), which leaves

| V_OUT | headroom at V_IN = 3.234 V | vs the 0.3 V spec condition |
|---|---|---|
| 3.000 V | 234 mV | **outside** |
| 2.727 V | 507 mV | inside, but not a stock value |
| **2.500 V** | **734 mV** | inside |

2.500 V is also the value that costs **nothing in firmware**: `REFCN` stays
`0xCD` (24 %), `O2P_HW_VREF_TARGET_MV` stays 2500, `finish_vref`'s trim band is
unchanged.

### 2.2 The reference tolerance requirement

Because the bias is a percentage, the bias error is exactly

    bias error = 600 mV x (reference relative tolerance)

independent of which reference voltage is chosen. Against DS-0637's
**-600 ± 10 mV** (`PIN-IDENTITY-POSTMORTEM.md:93,421`):

| candidate | tolerance | bias error | verdict |
|---|---|---|---|
| TPS7A20, DBV, V_OUT >= 2.8 V | ±1.5 % over line/load/temp (SBVS338H §5.5) | ±9.0 mV | **disqualified** - 90 % of the window, nothing left for the LMP91000 ladder |
| AZ431BN (today) | ±0.8 % | ±4.8 mV | current design |
| series ref, REF33xx class | ±0.15 % | ±0.9 mV | ample |

**The LDO family already on the board cannot be the reference.** The part must be
<= 1 % total, ideally <= 0.5 %, and that fights the µA-class quiescent current
this budget wants. Shortlist pending.

## 3. OPEN GATE: real-cell CE compliance

Merging supply and reference forces `V_S = V_REF`. SNAS506 §6.5 characterises A1
over `300 mV <= V_CE <= V_S - 300 mV`:

| analog rail | CE ceiling |
|---|---|
| 3.3 V (today) | 3.00 V |
| 3.0 V | 2.70 V |
| **2.5 V (the version that works)** | **2.20 V** |

`REVIEW-2026-09-04-AFE-DECISIONS.md:33` states the real-cell CE potential was
never measured and the margin `3000 - VCE_pin` is "presently unknown". Searched
2026-09-12 across `*.md`, `docs/` and `bench-logs/`: **no `CE_MV` reading from a
real cell exists anywhere in this repo.** The only CE numbers on record
(`AFE-BRING-UP-POSTMORTEM.md:37`, CE-RE = 600 mV) come from the equal-resistor
dummy and are explicitly rejected as inapplicable to a real cell
(`REVIEW-2026-09-04-AFE-DECISIONS.md:83`).

So this proposal spends **800 mV of an unbounded margin**, at the pin whose
failure mode - A1 driving CE against a rail while the register image reads back
perfect - this board has already produced once (`DESIGN.md:284-293`).

**The gate:** read `CE_MV` (`0x002D`) on a real cell, in air and at low O2, and
record the numbers here.

- CE comfortably below ~1.9 V -> the single-LDO scheme lands as -8 parts with no
  firmware change.
- CE at or above ~2.2 V -> the analog rail must stay at 3.3 V and the reference
  must remain its own part (§4).

`CE_MV` is on the **MCU** ADC (`CE_MON`, U6 pin 15), so it survives the ADS1119
input damage of `5d967a0`. It does require `VREF_TRIM` to actually reach U7 pin
11, which is the open net of `935ca72`. Expect this measurement to wait on the
U8 replacement and that repair.

## 4. Fallback if CE runs high

Analog rail stays at 3.3 V straight off the buck; the reference becomes a 2.5 V
**series** reference (one part plus its output cap, replacing U15/R41/C9/R31).
Net **-6 parts**, no CE change, no bias change, reference tolerance improves to
±0.15 %. `gen_sch.py:610-616` already anticipated this part class: the note
explaining R31 records that it "would have been WRONG for a series reference like
the REF33xx, which requires 0.1-10 uF ON its output pin" - C10 is that cap.

What this fallback loses is the LDO's PSRR in front of the AFE, which makes the
ripple measurement already queued at `DESIGN.md:704-706` a release condition
rather than an open question.

## 5. Rejected alternatives, and why

- **Rail as reference (no reference part at all).** Fails the bias spec
  structurally: 3.3 V x the available 18 %/20 % steps gives -594 mV or -660 mV,
  and the rail's own ±2 % adds ±12 mV on top of a ±10 mV window. It also blinds
  `VREF_MON`, the diagnostic that separates "no reference" from "no current" -
  the confusion that produced a fictitious 238 µA quoted as measured four times
  (`CELL-AFE-DEBUG.md:97-108`).
- **STM32G071 VREFBUF on pin 5.** Electrically excellent - 2.498/2.500/2.502 V,
  ±0.08 %, 4 mA drive (DS12232 Table 61), and pin 5 is VREF+ on this LQFP48,
  currently strapped to 3V3D (`gen_sch.py:718`). Rejected because it makes the
  cell bias depend on MCU reset and sleep state: every reflash would drop the
  reference, drop the bias, and restart `O2P_SETTLE_SECONDS` = 900. Also needs
  C10 changed to 1 µF (VREFBUF wants C_L = 0.5-1.5 µF, ESR <= 2 R).
- **An ADC with a pinned-out internal reference** (AD7124 `REFOUT`, ADS125x
  `VREFOUT`). Larger, hungrier, dearer than the ADS1119 and each brings its own
  support parts: a net parts *increase* to save one reference.

## 6. Part shortlist, 2026-09-12

**No LDO qualifies, and it is not a near miss.** Every µA-class TI LDO checked
specifies the same ±1.5 % total, which is ±9.0 mV of a ±10 mV bias window:

| part | output tolerance | source |
|---|---|---|
| TPS7A20 (on the board) | ±1.5 % over line/load/temp | SBVS338H §5.5, DBV, V_OUT >= 2.8 V |
| TPS7A21 | ±1.5 % over line/load/temp | SLVSHF datasheet, Features + §5 |
| TPS7A02 | ±1.5 % over temperature | Features; "Accuracy over temp" row, V_OUT >= 1.5 V |

DigiKey and Mouser API credentials are not configured on this machine and
distributor parametric data does not expose output tolerance anyway, so this was
done datasheet-first. LCSC's jlcsearch API was used for stock only.

### The right part class is a series voltage reference, not an LDO

A precision series reference *is* a regulator, and this one has enough output
current to carry the whole analog domain. **TI REF3425**, SOT-23-6 (DBV),
`ref34.pdf` (REF34xx family datasheet, fetched 2026-09-12):

| parameter | value | consequence here |
|---|---|---|
| initial accuracy | **±0.05 % max at 25 °C** | bias error **±0.3 mV** (600 mV x 0.05 %) |
| temperature coefficient | 2.5 typ / **6 ppm/°C max**, −40…125 °C, box method | +/-0.36 mV of bias over a 100 K swing |
| output current | ±10 mA | analog domain draws ~400 µA (ADS1119 310 + LMP 10 + 2x OPA2333 34 + R34/R35 27) |
| quiescent current | 72 typ / **95 µA max** | replaces the AZ431's **2.5 mA** bias - saves ~2 mA, ~10 mW at 12 V |
| dropout | 100 mV max at 0 mA, 500 mV at 10 mA | ~116 mV at our load; 734 mV available from a 3.234 V worst-case rail |
| stable C_L | **0.1 to 10 µF** | **C10's 4.7 µF is already inside the range** |
| V_IN | up to 12 V (2.55 V min for the 2.5 V part) | could even run off +12V_SW if ever wanted |
| package | SOT-23-6, 2.90 x 1.60 mm | |
| stock | LCSC **C187836**, `REF3425IDBVR`, 8012 in stock (checked 2026-09-12) | |

Total bias error under **±1 mV** against a ±10 mV window - **20x better than the
AZ431BN's ±4.8 mV**, on a part that costs 2.5 mA less to run.

REF3430 (3.0 V) and REF3433 (3.3 V) are the same die in the same package, so the
rail voltage stays a one-character decision if the CE gate moves it.

**Trap for a future reviewer: tie EN to V_IN.** The DBV part has an enable pin,
and `POWER-BUDGET.md` complains that no rail on Rev A is MCU-gateable. Do not fix
that here. Gating this rail drops the cell bias and restarts
`O2P_SETTLE_SECONDS` = 900. (`REF3425T` is the no-EN variant but LCSC stocks 8.)

### Unverified, flagged

`ref34.pdf` specifies line regulation (2 typ / 15 ppm/V max) but **no AC PSRR** -
a reference is not characterised as a supply. Using it as the analog rail leaves
the AFE's rejection of buck ripple unquantified. This is the same bench
measurement already queued at `DESIGN.md:704-706` and it now gates §2 rather than
merely informing it. If the CE gate sends us to the §4 fallback, the REF3425 is
still the right part - it just feeds the reference node only, and the analog
supply comes off the 3.3 V rail directly.

## 7. "Why not take a 1.5 % part and calibrate?" (Fab, 2026-09-12)

Because the reference sets **two** quantities and calibration reaches only one.

### The gain term: already solved, and not by calibration

`I = VREF x (0.67 - code) / R_TIA`, so a wrong VREF scales the reading. But
`finish_vref` (`main.c:709`) already **measures** VREF every cycle against the
ADS1119's internal 2.048 V reference (±0.25 %, SBAS925 p.329) and uses the
measured value. A ±1.5 % part would be read back to ±0.25 % and used correctly.
**For the gain term the part's tolerance genuinely does not matter.**

### The bias term: not calibratable, by construction

The bias is a *physical potential on an electrode* - 600 mV x whatever the
reference actually is. No stored constant moves it. The probe can KNOW it
(`CELL_BIAS_MV` is telemetry) but knowing is not compliance. Nor can it be
trimmed: the LMP91000 ladder steps in 2 % of VREF = 50 mV, five times coarser
than the whole ±10 mV window.

### And DS-0637 gives no basis for judging how much that costs

Checked 2026-09-12, DS-0637 Issue 2, the complete text on bias:

> Bias Voltage    -600 ± 10 mV

No sensitivity curve, no plateau width, no dI/dV_bias. So:

- if the cell sits well inside its plateau, ±9 mV probably does nothing and no
  calibration is needed either;
- if it sits near the edge, the bias error shifts sensitivity **and its
  temperature dependence** - and ±1.5 % is specified over line, load AND
  temperature, so the error moves with pile temperature (20-75 °C). A one-point
  air calibration taken at bench temperature cannot absorb a temperature-varying
  error, and it would land in the term the firmware models separately as cell
  TEMPCO/DIL_ALPHA, corrupting the correction model rather than the raw number.

Nobody has measured which case this cell is in. A ±1.5 % part converts a
datasheet compliance into a bet on an uncharacterised curve.

### The trade buys nothing anyway

Both candidates are one SOT-23. The LDO's only edge is quiescent current -
6.5 µA (TPS7A20) against the REF3425's 95 µA. That is 88 µA, ~0.3 mW at 12 V,
against a 123 mW heater: **0.2 % of the power budget**, for zero parts saved.

### Retiring the question properly

The LMP91000's bias is software-settable, so the plateau can simply be measured:
step BIAS through its codes around -600 mV and record the cell current at each.
Flat plateau -> the ±1.5 % part is fine and this whole section is moot. Sloped ->
REF3425 was mandatory. Same bench session as the `CE_MV` gate (§3), same
prerequisite: the U8 replacement and the `VREF_TRIM` repair.

### ADP160/ADP161/ADP162/ADP163 - the unread source, closed

Fab supplied the datasheet directly on 2026-09-12 after analog.com refused rungs
1-3 (HTTP/2 reset; HTTP/1.1 with Sec-Fetch headers timed out; Mouser's mirror
returned a 13.9 kB non-PDF interstitial). It does not rescue the LDO class - it
is the worst of the four:

| condition | accuracy |
|---|---|
| I_OUT = 10 mA, 25 °C | ±1 % |
| 0 µA to 150 mA, V_IN = V_OUT + 0.5 V to 5.5 V | ±2 % |
| **same, T_J = −40 to +125 °C** | **±3.5 %** |

±3.5 % is **±21 mV of bias** against a ±10 mV window. Also note V_IN =
V_OUT + 0.5 V in every accuracy row, which a 3.3 V rail cannot give a 3.0 V
output - the same headroom failure as §2.1. Its PSRR is genuinely good (65 dB at
100 Hz, 50 dB at 1 kHz, p.192) but irrelevant once the accuracy is out.

## 8. Codex xhigh review, 2026-09-12 — what it refuted

Independent `codex exec -c model_reasoning_effort=xhigh`, network on, Playwright
over a hidden Chrome on 127.0.0.1:61964. Access proven and checked: it returned
`<title>REF34 data sheet, product information and support | TI.com</title>` and
the same 1,809,474-byte `ref34.pdf` fetched here, plus live `git log` SHAs. Log
at `~/codex-reviews/o2probe-revb-supply/review.log` (4134 lines, rc=0), grepped
clean for `no connected browsers` and `node_repl/js (failed)`.

Every finding below was re-verified against the primary source before being
written here. **Findings are hypotheses; these are the ones that survived.**

### 8.1 KILLED: a 2.500 V analog rail is below the AFE's minimum supply

**SNAS506I gives VS = (VDD − AGND) = 2.7 V min, 5.25 V max** (`lmp91000.pdf`
electrical table, "Supply Voltage VS"). Verified directly 2026-09-12.

Section 2 proposed a 2.500 V combined supply+reference. **That is illegal on the
LMP91000 and no CE measurement can rescue it.** The error was mine: the 2.7 V
floor was known earlier in the same session and never applied to the proposal.

It also fails a second, independent way: `faults.h:76` sets
`O2P_VA_LOW_MV = 3130`, and `main.c:322` raises `O2P_F_VA_LOW` **and restarts
settling** whenever the analog rail reads below it. A 2.5 V rail — or a 3.0 V one
— would trip that continuously. So section 2.1's "costs nothing in firmware" is
false regardless of voltage.

A **3.000 V** combined rail survives the 2.7 V floor (REF3430 is the same die),
and its bias is marginally better: `VOS_RW` is ±1650 µV at ±20 % VREF against
±1750 µV at ±24 %. It still needs the `O2P_VA_LOW_MV` constant changed and still
carries the headroom and CE questions, so it is not the recommendation.

### 8.2 The bias budget was wrong: the potentiostat's own offset dominates

The §2.2 algebra survives — the reference contribution really is
`600 mV x tolerance` for both 2.5 V @ 24 % and 3.0 V @ 20 %. But §6's "total bias
error under ±1 mV" and "20x better than the AZ431" **do not**:

- **`VOS_RW`, WE voltage offset referred to RE, is ±1750 µV at ±24 % VREF over
  −40…80 °C** (`lmp91000.pdf`, POTENTIOSTAT table, verified). That single term
  exceeds the claimed total before any reference error. Do not add `TcVOS_RW` on
  top — the −40…80 °C condition already covers temperature.
- **Box method, not a local slope.** REF34's 6 ppm/°C max is specified over the
  −40…125 °C box (§8.3.2), permitting **990 ppm total span** = 0.594 mV of bias,
  not the 0.36 mV claimed for a 100 K interval. With ±0.05 % initial (0.300 mV)
  the reference contributes ~0.9 mV.
- **TPS7A20 at 2.5 V is ±40 mV = ±9.6 mV of bias**, not ±9.0 mV; adding `VOS_RW`
  gives **±11.35 mV** against a ±10 mV window. Its accuracy rows also start at
  **I_OUT = 1 mA**, above this board's ~0.4 mA analog load. The rejection stands;
  the arithmetic supporting it was loose.

Net: REF3425 still has comfortable bias margin. The honest claim is "reference
contributes ~0.9 mV into a budget whose floor is the LMP91000's ±1.75 mV", not
"±0.3 mV, 20x better".

### 8.3 The CE gate was overstated — and the generator already said so

`gen_sch.py:808-810`, written before this proposal:

> `SNAS506I 6.5's 0.3..VS-0.3 V window is an open-loop-gain characterisation
> condition, not a hard compliance limit.`

Confirmed at `lmp91000.pdf`: `300 mV <= VCE <= Vs-300 mV` is the test condition
for `AOL_A1`. Section 3 promoted it to a ceiling. **I should have read the
generator's own note before writing the gate.**

The physical concern survives — lowering VS does cut A1's output swing — but the
acceptance criterion must be maintained electrode bias and settling across load,
temperature and startup, not a single room-temperature `CE_MV` number. And any
Rev A measurement must be corrected for Rev B's **R42 = 1 kΩ in the CE path,
which drops up to 132.2 mV at 130 µA** (`gen_sch.py:806`).

### 8.4 Section 7's metrology claims were too strong

`finish_vref` removes the *reference amplitude* from the reported current, but
not everything:

- The **divider ratio survives**: R34/R35 at 0.1 % permit ±0.1 % of ratio error.
- ADS1119 internal-reference drift is **5 ppm/°C typical, 30 ppm/°C maximum** —
  §2 quoted the typical.
- `main.c:710` truncates the half-divider reading to **millivolts before
  doubling**, so `vref_mv` advances in 2 mV steps: up to ~0.08 % downward scale
  error near 2.5 V.
- The accepted band is **2380–2620 mV**, not the trim band: the code adds 100 mV
  slack to each 2480/2520 endpoint.

Initial reference-plus-divider is therefore ~0.35 % worst case, not ±0.25 %.
The nominal-seed worry does **not** produce a false current: `main.c:1099`
requires `vref_measured` before raw current is published.

### 8.5 Smaller corrections

- **REF34xx does publish AC PSRR** — SBAS804G Figure 6-5, typical curves. §6's
  "no AC PSRR" is wrong; the correct statement is that there is no *guaranteed
  minimum*.
- **Do not feed REF3425 from `+12V_SW`.** §6 floated it; the board's input is
  specified to **15 V** and REF34's recommended input maximum is **12 V**.
- The oxygen channel runs at **gain 1, 76.3 µV/LSB** (`ads1119.c:24`). Gain 4
  would give ±625 mV full scale, below the 1.675 V zero, and saturate.
- **3.234 V is not an established AP63203 minimum.** It was borrowed from the
  TPS7A20-based worst case at `DESIGN.md:54`. The AP63203 table specifies
  3.27–3.33 V in CCM; PFM ripple, transients and the R32 drop need their own
  allowance before any headroom claim is made.
- §5's noise wording ("never reaches the analog domain") overstates finite
  rejection. For Path A, R32=10 R with C7=10 µF is f_c ≈ 1.59 kHz — **0.017 dB
  at 100 Hz**. It is not a filter against PFM burst content.

### 8.6 What survived

- **No hidden 5 V consumer.** Exhaustive re-enumeration of `gen_sch.py` confirms
  U2, U3 and R41 (plus buck feedback/output parts and power flags). This is the
  load-bearing premise of the whole proposal and it holds.
- **The reference-error algebra** of §2.2.
- **REF3425 as a reference-only part**: headroom from 3.3 V, ample current, and
  C10's 4.7 µF inside its specified range.
- **DS-0637's +60 °C limit** against a 60–75 °C pile. Neither topology changes it.

### 8.7 Revised recommendation

**Path A, and now for a stronger reason than BOM count:** buck to 3.3 V, delete
both LDOs, REF3425 as *reference only*, AFE supply off the 3.3 V rail through
R32/C7. It is the only variant that keeps the LMP91000 above its 2.7 V floor
without a second regulator, leaves `O2P_VA_LOW_MV` valid, and needs no CE gate at
all.

The release gate moves accordingly. It is no longer "measure `CE_MV`" — it is
**qualify Path A's analog rail**, exercising RS-485 traffic, heater duty, input
voltage and sampling phase, and measuring **mean error as well as noise**, since
the consequential mechanisms (sampling-correlated load steps, reference
modulation) produce repeatable offsets rather than visible noise. `main.c:1571`
acquires VREF *before* the oxygen sample and against a different reference, so
fast reference disturbances are not guaranteed to cancel.

## 9. Path D: raise the pre-regulator, keep an LDO in front of the AFE

Fab, 2026-09-12: *"we could operate the buck and STM32 at 3.6 V"*. The point is to
buy back the LDO that Path A deletes — the only thing standing between the AFE
and the buck's PFM burst content — without going back to two LDOs and a 5 V rail.

It works, but not at 3.6 V, and the analog rail should be 3.0 V rather than 3.3 V.

### 9.1 3.6 V is a ceiling, so the nominal is ~3.5 V

| part | rail | limit | source |
|---|---|---|---|
| STM32G071 | 3V3D | VDD **1.7 to 3.6 V** | DS12232, "require a 1.7 V to 3.6 V operating supply voltage" |
| SHT45 (U12) | 3V3D | VDD 1.08 / 3.3 / **3.6 V max** | SHT4x DS V7.3 supply-voltage row |

3.6 V is the **maximum**, not a target. An adjustable buck carries ~±2 % (0.8 V
±1 % internal reference plus divider resistors), so a 3.6 V nominal reaches
3.67 V and puts both parts outside their recommended range. **Nominal 3.5 V**
(3.43-3.57 V) is the usable target.

### 9.2 It forces the adjustable buck

The AP632xx family offers **only two fixed outputs: 3.3 V (AP63203) and 5.0 V
(AP63205)** (`ap632.txt` Features, verified 2026-09-12). Any other rail needs the
adjustable **AP63200** plus a feedback divider — **+2 resistors**, and the
divider is where most of the ±2 % comes from.

Noted while checking: **AP63201 is forced-PWM regardless of load**; PFM is listed
for AP63200/63203/63205 only. That removes the burst mechanism at its source, but
constant switching at a ~3 mA load is the opposite of what a season on 10 Ah
wants. Recorded as an option, not a recommendation.

### 9.3 The unlock: the LDO's accuracy stops mattering

Once REF3425 owns the reference, the LDO is **only a filter**. Its ±1.5 %
tolerance is irrelevant, and section 2.1's rejection of a 3.0 V LDO on the
`VIN = VOUT(NOM) + 0.3 V` accuracy condition **does not apply here** — that
condition was binding only while the LDO *was* the reference.

### 9.4 But PSRR is conditioned the same way, and PSRR is the whole point

TPS7A20's entire electrical table, **including the PSRR row (65 dB at 100 Hz,
92 dB at 1 kHz, 75 dB at 10 kHz), is taken at `VIN = VOUT + 0.3 V` and
`IOUT = 300 mA`** (SBVS338H §5.5). TI publishes *PSRR vs Frequency and VIN*
(Figure 5-61/5-62) and *vs IOUT* (5-63) precisely because it degrades away from
those conditions.

A 3.3 V analog rail from a 3.43 V worst-case source leaves **130 mV** — the
filter would run outside the conditions its filtering is specified at, which
means buying it and being unable to size it.

**So take the analog rail to 3.0 V.** Legal now that the floor is known to be
2.7 V (§8.1): 3.43 − 3.0 = **430 mV**, inside spec. Costs:

- `O2P_VA_LOW_MV` (`faults.h:76`) must drop from 3130 — a constant, but it is the
  guard that restarts settling, so re-derive it rather than nudging it.
- 300 mV of A1 output swing. The CE question returns, correctly framed this time
  as available swing, **not** the hard ceiling §3 wrongly claimed (§8.3).
- ADS1119 AVDD 3.0 V ≥ VREF 2.5 V, so the reference still fits.

### 9.5 The cross-domain detail Path D introduces

R10/R11 pull I2C to `3V3D` (`gen_sch.py:730-731`). With digital at 3.5 V and the
LMP91000 at 3.0 V, the bus idles above the AFE's rail. That is inside absolute
max — SNAS506I §6.1 is "Voltage between any two pins, 6.0 V", not VDD+0.3 — but
the free fix is to **move R10/R11 to the analog rail**: the STM32's VIH is
0.7 x VDD = 2.45 V, so 3.3 V-class logic into a 3.5 V MCU reads correctly.
Today's design never raises this question because both rails are 3.3 V.

### 9.6 A against D

| | parts | AFE rail | noise posture |
|---|---|---|---|
| today | 19 | 3.3 V, two LDOs off 5 V | LDO-filtered, never measured |
| **Path A** | 11 (**−8**) | 3.3 V straight off the buck | `unverified` — must be qualified on hardware |
| **Path D** | 14 (**−5**) | 3.0 V behind an in-spec LDO | sized from datasheet numbers before fab |

**+3 parts to buy the filter back**, two of them the adjustable buck's divider.

That is a genuine trade, not an obvious loss. Path A is the bigger BOM cut but
carries its noise performance as an open hardware qualification; Path D is
smaller but can be argued from datasheets before anything is fabricated. Neither
is blocked on a bench measurement the damaged Rev A board cannot currently give.

## 10. Answers owed to `2026-09-12-revb-proposals-from-the-afe-failure.md`

That document defers two numbers here rather than asserting its own. Both come
out of `ref34.pdf` (REF3425, the part selected in section 6).

### 10.1 P2 — can the reference carry a 4.7k/4.7k sense divider? YES, easily

| | |
|---|---|
| divider current at 47k/47k | 27 µA |
| divider current at **4.7k/4.7k** | **266 µA** |
| REF3425 output capability | **±10 mA** |
| so the new divider costs | **2.7 % of capability** |

The accuracy cost is the load-regulation term, and it is nothing:
0.266 mA x 70 ppm/mA (max, sinking) = **18.6 ppm**, i.e. 0.047 mV on 2.500 V,
i.e. **0.011 mV of cell bias** against a ±10 mV window.

Total analog draw becomes ~400 µA (AFE) + 266 µA (divider) = **~0.67 mA**, still
6.7 % of the part's rating, and dropout at that current is far inside the 734 mV
available from a 3.234 V worst-case rail. **P2 is affordable. Take 4.7k/4.7k.**

Note this only holds for the SERIES reference. On the retired AZ431 shunt the
same divider would have been a 10 % perturbation of its bias current.

### 10.2 P0 — can the reference drive the STM32's VREF+? Yes on current; read 10.3

DS12232 gives `IDDV(ADC)`, the current drawn FROM VREF+, as **26 µA at
fs = 1 MSps**. This board samples far slower, so the average is smaller still —
**0.26 % of the REF3425's capability**. The switched-capacitor transients are
absorbed by C10, and 4.7 µF is inside SBAS804G's 0.1-10 µF stable range.

Two hard constraints that P0 must respect, both from the datasheets:

- **VREF+ must be between 2 V and VDDA** (DS12232: "When VDDA >= 2 V, VREF+
  must be between 2 V and VDDA"). VREF_TRIM = 2.500 V into VDDA = 3.3 V is
  legal, with 0.5 V of margin above the floor.
- **The MCU's ADC full scale becomes 2.500 V, not 3.3 V.** P0 already flags the
  rescaling; for the record the existing taps still fit — VA_MON reads ~1.65 V
  from 3V3A and VIN_MON ~1.42 V at 13.1 V through the fitted 82k/10k.

### 10.3 The objection P0 does not raise: a new digital-to-bias coupling path

Driving VREF+ from `/VREF_TRIM` puts a **switched-capacitor load, clocked by the
MCU, directly onto the node that sets the cell's electrochemical bias.** Today
that node feeds only the LMP91000's reference input and the ADS's REFP, both
quiet. Afterwards, every MCU conversion injects a charge pulse into it.

The energy is small and C10 is a large local reservoir, so this is not an
argument against P0 — it is an argument that P0 inherits the SAME open gate as
Path A, and for the same reason: the analog domain loses an isolating element
and gains a digital neighbour. If both land, the rail-noise qualification must
be run with the MCU's ADC converting at its real duty, and must measure MEAN
error on the O2 channel, not just noise — a bias shift correlated with
conversion timing would look exactly like a slow O2 drift.

### 10.4 Sequencing, so the two documents do not collide

P0 deletes U8, C28-C31, R33, R36-R38 and the `/ADC_*` family. Those are
precisely the nets that were re-captured as wired blocks on 2026-09-12 (the ADC
anti-alias filters and the VREF divider, sections 8-9 of this document and the
capture work in `gen_sch.py`). **Decide P0 before spending more effort on that
part of the sheet** — the capture is cheap to redo and the measurement that
settles P0 is not.

One consequence worth stating plainly: P0 removes the ADS1119, and with it the
**internal 2.048 V reference that `finish_vref()` currently uses to measure
VREF_TRIM absolutely** (section 8.4). P0's replacement is VREFINT, which is
correct in principle — but VREFINT is specified to roughly ±1 %, against the
ADS's ±0.25 %. That is still far better than the cell's ~1000 ppm/K, so it does
not change P0's conclusion; it should just be stated rather than inherited
silently.

### 10.5 P0 in full — deleting the ADS1119

P0's stated blocker 2 is **overstated by ~7x**. DS12232 Table 51 gives input
leakage for the **TT_xx** pins — the three-volt analog-capable class the ADC
channels use — as **±150 nA max**, not the ±1 µA quoted. (600 nA is the FT_xx
class and 2-3 µA the FT_c class; those are 5 V-tolerant pins and are the wrong
row for an analog input. Note 4's 10 µA is a whole-device total, not per pin.)

What ±150 nA actually costs, per node:

| node | source impedance | offset |
|---|---|---|
| AFE_VOUT through R33 | 1 kΩ | 0.15 mV = **0.0045 %O2** |
| VREF tap at 47k/47k | 23.5 kΩ | 3.5 mV on 1250 mV = **0.28 %** |
| VREF tap at **4.7k/4.7k** (P2) | 2.35 kΩ | 0.35 mV = **0.028 %** |

So the leakage argument does not block P0 — **provided P2 lands with it**, which
is exactly what P0 already says ("P2 becomes mandatory rather than optional").
Still 30x the ADS's ±5 nA, so it constrains every node the MCU ADC touches; it
just is not fatal.

**Where P0 is strong:** resolution is ample (12-bit raw is 0.018 %O2 against a
33.2 mV/%O2 span), the cell's ~1000 ppm/K dwarfs any converter term, and it
deletes ~10 parts plus the I2C path and the stuck-mux failure mode.

**Two reservations, neither fatal, both about timing rather than merit:**

1. **It does not address the root cause.** The incident was a conductive film
   bridging a HIGH-IMPEDANCE node. What fixes that is P2 (impedance), P5 (pad
   clearance) and assembly/coating discipline. The ADS1119 was the victim, not
   the mechanism — and the replacement tolerates 30x LESS leakage, so the same
   film on an MCU ADC pin is worse, not better. P0 should be argued on BOM and
   simplicity, which are good arguments, rather than on "it deletes the network
   that failed".
2. **It moves the measurement into the digital die at the same moment Path A
   removes the analog LDO.** The ADS1119 sits on 3V3A behind its own AVDD with
   85 dB PSRR; the MCU's ADC shares silicon with the RS-485 UART, the heater PWM
   and I2C. Landing both changes at once removes two isolating elements in one
   revision, with the rail-noise qualification still open (section 8.7).

**Recommendation: P2, P3 and P4 now; ADS stays in Rev B; P0 gated on the bench
comparison P0 itself asks for.** P3 and P4 are firmware-only and would have
turned this incident from a fourteen-hour blackout into a degraded-but-reporting
state — they are worth more than the BOM saving and cost nothing. If P0 later
lands, it deletes the ADC-filter capture done on 2026-09-12, which is cheap to
redo; the measurement that settles P0 is not.
