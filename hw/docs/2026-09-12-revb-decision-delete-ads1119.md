# Rev B decision: delete the ADS1119 (U8)

**Decided 2026-09-12 by Fab.** Supersedes P0 of
[`2026-09-12-revb-proposals-from-the-afe-failure.md`](2026-09-12-revb-proposals-from-the-afe-failure.md),
which recorded this as a proposal. Extends
[`2026-09-12-revb-decision-vref-monitor.md`](2026-09-12-revb-decision-vref-monitor.md),
whose deferred item is resolved here as **rejected**, not adopted.

Every analog channel moves to the STM32G071CBT7's own ADC. U8 comes off the BOM.

> **RE-TAKEN AND ADOPTED — Fab, 2026-09-12: "del u8".** U8 is deleted, in the
> **REF3425 form**, which is what this document's own recommendation and both
> reviews converged on. The binding specification is the "Final specification as
> adopted" section at the foot of this file; where the body below disagrees with
> it, the foot wins — the body is kept as the record of how the decision was
> reached, including the parts of it that were wrong.
>
> **CONTESTED 2026-09-12, same day — the body below was not settled.** A Codex review
> at xhigh returned **VERDICT: NO**, and I verified four of its five findings
> against the datasheets, the firmware and the working tree; all four hold. See
> [`2026-09-12-revb-codex-review-of-the-u8-decision.md`](2026-09-12-revb-codex-review-of-the-u8-decision.md).
> In short: the error budget below priced ONE conversion where oxygen uses
> THREE (corrected worst case ~0.20 %O2, not 0.073 — a ~2x margin over the cell,
> not 5-18x); `EO` should not have been removed, because DS12232 Table 60
> footnote 2 says the DC accuracy figures are already measured AFTER internal
> calibration; the "resolution never reached anyone" argument is FALSE, since
> `main.c:1179` publishes `o2_raw` at 10 nA/count = 70 uV = the ADS's LSB; and
> the supply premise changed underneath this document — **3V3D now comes
> straight off the AP63203 buck, both TPS7A20 LDOs deleted** (`gen_sch.py:905`),
> so the rejection of the `VREF+` move was decided against a topology that no
> longer exists and is **overturned**. The resolution and leakage conclusions
> survive. Recommendation: keep U8's footprint on Rev B until the corrected
> budget and a measured comparison pass. Fab's call to re-take.

> **IMPLEMENTED in the schematic the same day** by the Rev B session —
> `docs/2026-09-12-revb-ads1119-removal-implemented.md`. 82 components (was 89),
> ERC 0/0. The firmware sampler port is deliberately NOT done and
> `o2probe_revb` is out of `default_envs` until it lands. Their report also
> corrected two things in this document; both are marked below.

## The architecture: `VREF+` stays on VDDA, and the reference is MEASURED

This is the part that took two wrong turns to reach, so it is stated plainly.

```
VREF+ (pin 5)      = VDDA = 3V3D = 3.3 V     <- UNCHANGED
/VREF_TRIM         -> MCU ADC channel, direct, no divider   (2.5 V < FSR)
/AFE_VOUT          -> MCU ADC channel, via R33/C28          (982..1675 mV)
/WE_BUF, /RE_BUF   -> MCU ADC channels, via R37/C30, R38/C31

I = VDDA/FS x (0.67 x code_REF - code_AFE) / R_TIA,  VDDA from VREFINT
```

**The reference's drift cancels exactly, because it is measured on the same
converter, in the same units, in the same cycle.** That is the same
cancellation the ADS1119 gets from sharing `/VREF_TRIM` as its full scale —
performed by arithmetic instead of by wiring, and without requiring the
reference to BE the full scale. Rev A already relies on the measured value
rather than a nominal one: `ads_ext_scale_mv()` (`main.c:636`) returns
`g_cyc.vref_mv`.

### Why moving `VREF+` to `/VREF_TRIM` is REJECTED, not deferred

It was proposed under P0 as the mechanism for ratiometry. It is not needed for
it, and it costs four things the arithmetic form does not:

1. **Accuracy becomes uncharacterized.** Every row of DS12232 Rev 5 Table 60
   (`ET`, `EO`, `EG`, `ED`, `EL`, `ENOB`) is specified at `VDDA = VREF+`.
   Operation with VREF+ < VDDA is permitted (p.809-817) but ST publishes no
   accuracy figure for it. Keeping VREF+ = VDDA keeps the whole budget below
   inside its specified conditions.
2. **Every MCU ADC channel's full scale would drop to 2.5 V**, costing the rail
   monitors their over-range headroom. 3V3A excursing to 5 V would put the VA
   tap at exactly full scale and clip above it. That is not hypothetical: the
   14-day over-voltage sweep that dated this failure is precisely that
   measurement.
3. ~~**The ADC scale would depend on trimpot RV1** instead of an LDO.~~
   **STRUCK 2026-09-12** — wrong for Rev B. There is no trimpot: Rev B's
   `/VREF_TRIM` is U15, a **REF3425IDBVR** series reference, Kelvin-sensed
   (`gen_sch.py:930`, `:945`, `:1499`), with C10 4.7 uF. The RV1/OPA2333
   divider is Rev A's topology and I carried it across by mistake.
4. ~~**A switched-cap load would land on `/VREF_TRIM`**~~ **WEAK** — the
   REF3425 sources +/-10 mA (SBAS804G Table, `IL`) into a 0.1-10 uF stable
   load range. 0.26 uA of `IDDV(ADC)` is not a load it notices.

**And one reason pointed the other way, which is worth stating rather than
quietly dropping.** With `VREF+` = VDDA the scale factor is VREFINT at 50
ppm/degC max; with `VREF+` = the REF3425 it would be **6 ppm/degC max**
(SBAS804G, 2.5 typ), an 8x better tempco. Over a 20 K swing that is 120 ppm
against 1000 ppm — 0.0025 %O2 against 0.021 %O2.

**The decision stands, on reasons 1 and 2 alone.** Both remaining terms are
18x to 150x under the cell's own 0.38 %O2 over the same swing, so the
better tempco buys nothing measurable, while reason 1 (uncharacterized
accuracy outside `VDDA = VREF+`) and reason 2 (the rail monitors' over-range
headroom) are real and unmitigated. But it rests on two reasons, not four.

## Error budget, entirely from datasheets — no bench measurement required

DS12232 Rev 5 Table 60 (12-bit, `TA` = entire range) and section 5.3.4.
O2 span 33.2 mV/%O2; FSR 3.3 V gives 806 uV/LSB.

| term | spec | -> %O2 |
|---|---|---|
| integral linearity `EL`, max | +/-3 LSB = +/-2.42 mV | +/-0.073 |
| LSB at 3.3 V FSR | 806 uV | 0.024 |
| `VREFINT` tempco, max 50 ppm/degC over 20 K | 1000 ppm | 0.021 (gain) |
| `VREFINT` long-term, max | 1000 ppm / 1000 h | 0.021 (gain) |
| `Ilkg` +/-70 nA into 1 kOhm (R33) | 70 uV | 0.002 |
| offset `EO` | removed by `ADCAL` | — |
| gain `EG` | absorbed by the air calibration | — |
| **cell drift, ~900 ppm/K over 20 K** | **12.5 mV** | **0.38** |

Every term is 5x to 18x under the cell's own drift. The converter is not the
limiting element under any of them, which was the whole question.

Supporting, from the telemetry rather than the datasheets
(`CELL-AFE-DEBUG.md`, 2026-09-12 14:00): the firmware publishes the O2 channel
as `uv / 1000` — whole millivolts (`main.c:1066`) — while the ADS resolves
76 uV/LSB, so **13x of its resolution was already being discarded before
transmission**, and the measured in-situ chain noise of 0.43 mV rms sits below
that 1 mV grid. 806 uV/LSB is still finer than the number anyone receives.

## BOM: what goes, and what stays

**Deleted:** U8 and its local decoupling; R34, R35, R36, C29 and the nets
`/VREF_MON_RAW` and `/ADC_VREF_MON` (per the VREF-monitor decision); the I2C
traffic to U8 and its failure modes; `ADC_DRDY`, freeing PB1.

**KEPT — correcting P0, which listed these as deletions:** R33/C28, R37/C30,
R38/C31 (1k + 100n, `gen_sch.py:1332-1352`). A SAR needs them *more* than a
delta-sigma does. The 100 nF sources the charge kick of the ADC's 5 pF sample
capacitor (`CADC`, Table 58) so the op-amp does not, and 1 kOhm is far inside
the 50 kOhm `RAIN` limit. Deleting them would have been a real error.

I2C pull-ups also stay — the bus is shared with the other sensors.

## Pins — as allocated by the Rev B session, verified here

The allocation is theirs, and it applies the leakage argument further than this
document did: `Ilkg` differs by pad type (DS12232 Table 51), so the three
1k-sourced signals take the quieter `FT_a` pads and the reference — driven by
U15's output, where even 150 nA is negligible — takes the `TT_a` one.

| pin | port | channel | pad | net |
|---|---|---|---|---|
| 11 | PA0 | ADC_IN0 | FT_a, +/-70 nA | `/ADC_WE_BUF` |
| 12 | PA1 | ADC_IN1 | FT_a, +/-70 nA | `/ADC_RE_BUF` |
| 16 | PA5 | ADC_IN5 | **TT_a, +/-150 nA** | `/VREF_TRIM`, undivided |
| 20 | PB1 | **ADC_IN9** | FT_a, +/-70 nA | `/ADC_AFE_VOUT` |

Verified against DS12232 Rev 5 on 2026-09-12: the pad types are exactly as
claimed, and **PB0 is ADC_IN8 while PB1 is ADC_IN9** — their correction to my
handover message, which had the channel numbering wrong. `ADC_IN17`/`IN18` are
not on any LQFP48 port pin. Whoever writes `mcu_adc.c` needs IN9, not IN17.

Putting WE and RE on adjacent pins of identical structure is deliberate: their
leakage common-modes out of the WE-RE difference, which is the quantity the
bias check actually uses.

## Design work this creates — tasks, not open questions

1. **The signal now crosses domains.** The LMP91000 and OPA2333 sit in 3V3A;
   the converter sits in the digital domain, which is part of why 3V3A/3V3D are
   split at all. This is the real work of the change and it must be coordinated
   with `2026-09-12-revb-single-rail-supply.md`, not decided independently.
2. **`ADCAL` after every power-up** becomes a firmware requirement, not an
   option — DS12232: *"It is recommended to perform a calibration after each
   power-up."* It is what removes `EO`.
3. Rescale the retained dividers for the channels' operating ranges, and choose
   a long sampling time (160.5 cycles allows 50 kOhm `RAIN`).
4. Re-derive the VREF gate at `main.c:700` / `main.c:869` from an MCU channel.
   **Partly done** — the Rev B session moved the divider constant out of the
   generated contract and into the per-revision caps headers as
   `O2P_HW_DIV_VREF_MON_NUM/DEN` (A: 47000/94000, B: 1/1), which had to happen
   first: `hw_contract.h` is GENERATED from `gen_sch.py`, so deleting R34/R35
   would have rescaled the constant that `main.c:770` applies to the **Rev A
   bench board**, which really does read a halved copy. Rev A would have
   published 1250 mV and tripped its own VREF gate. Caught by them, not by me.
5. Oversampling is available and not required. Do not spend it to chase the
   ADS's 76 uV — the `uv / 1000` publication grid throws that away. If the
   register format is ever widened, revisit.

## Retracted

My own claim that this decision needed measurements on Rev B hardware. It did
not. The blocker was self-inflicted: U8's deletion had been welded to the
`VREF+` move, and only the `VREF+` move hits an uncharacterized condition.
Fab: *"why can't we answer the ADS-out question from the datasheets?"* — it
can be, and the answer is above.

**One thing still not answerable from a datasheet**, recorded so it is not
mistaken for settled: whether the MCU's conversions pick up noise from its own
digital activity, the RS-485 traffic and the LoRa duty cycle. Table 60's
`ENOB` comes from ST's evaluation conditions, not from a probe with a radio.
This is a layout and sampling-timing concern with standard mitigations, and the
margin above would have to be wrong by ~5x for it to matter — but it is the
one term that Rev B itself will have to confirm.

---

# Final specification as adopted (Fab, 2026-09-12)

Binding. Supersedes every conflicting statement above and in
`2026-09-12-revb-decision-vref-monitor.md`. Derived from this document plus
[`2026-09-12-revb-codex-review-of-the-u8-decision.md`](2026-09-12-revb-codex-review-of-the-u8-decision.md)
and [`2026-09-12-revb-claude-review-of-the-u8-deletion.md`](2026-09-12-revb-claude-review-of-the-u8-deletion.md).

## Hardware

| | |
|---|---|
| **U8 (ADS1119)** | **DELETED**, with its local decoupling, its I2C traffic and `ADC_DRDY` |
| **`VREF+` (pin 5)** | driven from **`/VREF_TRIM`** — U15 REF3425, Kelvin-sensed. NOT 3V3D. |
| R34, R35, R36, C29 | DELETED, with nets `/VREF_MON_RAW` and `/ADC_VREF_MON` |
| **R25** | **47k -> 27k** — rescales `VA_MON` for the 2.5 V full scale; ceiling 6.85 V, *better* than today's 6.60, source impedance 23.5k -> 17.2k |
| **new: 100 nF at `VREF+`** | local decoupling. Pin 5 leaves 3V3D, and its only capacitor would otherwise be C10 at U15. DS12232 Table 63 note 4; inside the REF3425's 0.1-10 uF stable range |
| **new: Schottky, PA6 -> AGND** | Table 50 rates PA6 at **0 mA** negative injection and it is the only analog channel with a path to the external supply cable (R26 91k from `+12V_SW`) |
| **NO VDDA divider** | `VA_MON` already reads 3V3D to within 1-2 mV through R32's 10 Ohm, better than a divider's own 1.65 mV leakage error — and a divider's 10 us aperture cannot see the buck anyway |
| R33/C28, R37/C30, R38/C31 | **KEPT**. A SAR needs them more than a delta-sigma does |
| `VIN_MON` (91k/10k), `CE_MON` (91k/91k) | unchanged; both already fit a 2.5 V full scale |
| U8 footprint | **open sub-question, see below** |

## Channels

| pin | port | ch | pad | net |
|---|---|---|---|---|
| 11 | PA0 | IN0 | FT_a | `/ADC_WE_BUF` |
| 12 | PA1 | IN1 | FT_a | `/ADC_RE_BUF` |
| 20 | PB1 | **IN9** | FT_a | `/ADC_AFE_VOUT` |
| 16 | PA5 | IN5 | TT_a | **returns to the pool** |

`PA5` is freed: with `VREF+` = `/VREF_TRIM`, converting the reference against
itself saturates at 4095 and carries no information. Reference health is
**VREFINT against the 2.5 V full scale** — and note what that is: a **collapse
detector, not a drift monitor.** VREFINT's own tempco (50 ppm/degC) and `ACoeff`
(1000 ppm/1000 h) are 8x and 40x worse than the reference it watches. Do not
document it as a drift monitor.

## Firmware

**The oxygen equation. There is no `code_REF` term.**

```
I = V_REF x (0.67 - code_AFE / 4095) / R_TIA      V_REF a COMPILE-TIME CONSTANT
```

The three-conversion form carried in the body above is the **VDDA-architecture**
equation and must not be ported. It would read a saturated channel — leaving
0.06 %O2 of zero error at `EG` = -5 LSB that no air-point calibration removes,
and violating the rule every other guard here enforces
(`ads1119.h:126`, `main.c:1176`).

- `ADCAL` after **every** power-up. Not optional: DS12232 Table 60 footnote 2
  says the DC accuracy figures are measured *after* internal calibration, so it
  is a precondition of the spec and `EO` stays in the budget regardless.
- **Publish `ADC_CALFACT`** per boot. It is a per-part proxy for converter offset
  and its drift, and the functional replacement for the ADS's lost shorted-input
  self-check — a register read against P4's whole `PH_OFFSET` phase and a MUX
  write per cycle.
- **Use the two exact ratiometric constants** the 2.5 V full scale creates:
  `V_WE` = 0.67 x FS (code 2744) and `V_RE` = 0.91 x FS (code 3727), both to the
  LMP's +/-0.04 %. `WE_BUF` is then an independent measurement of the very
  pedestal the oxygen subtraction uses, on a different pin, and a per-channel
  leak breaks a known constant instead of hiding in a signal.
- Re-derive the VREF gate at `main.c:700` / `:869` from the MCU path; drop the
  `O2P_HW_*_ON_ADS` flags; regenerate `hw_caps_rev_b.h`.
- Keep `VREF_MON_MV` (0x0010) and its units — the telemetry history is the only
  record of the 09-11 failure and must stay comparable.

## How this budget is to be written from now on

Both reviews rejected the old framing and they were right.

- **State the budget in mV at the TIA output.** Quote %O2 only *at a named cell
  output*, with a `CAL_AIR_NA`-scaled derating note: DS-0637 is 0.1 +/- 0.03 mA,
  so a legal replacement cell inflates every %O2 figure by up to 1.4x and an
  aged one by more.
- **Judge against the application requirement, not the cell tempco.** Compost
  aeration decisions are taken at whole-percent thresholds; the budget is
  0.14-0.20 %O2. The old "~5x to 18x under the cell" comparison was
  mis-attributed (it is the whole signal, on a *board* temperature), circular (it
  contained the ADS path's own tempco) and a category error (the cell's tempco is
  corrected in firmware; INL is not).
- **Carry `ACoeff`.** VREFINT is 1000 ppm max per 1000 **hours** and a buried
  probe runs continuously: 0.183 %O2 at a year, the same size as the entire
  static budget. This is a large part of why the REF3425 form won — it is
  25 ppm/1000 h.
- **Drop `VDDCoeff`.** 0.0015 %O2 across the rail's own range. Both earlier
  passes over-weighted it.

## Why the REF3425 form and not the VDDA form

With `VREF+` = VDDA the three conversions happen at different times on a rail
with no LDO, so the cancellation fails: the worst pair at zero oxygen couples
0.718 mV/mV, i.e. **4.63 mV of supply variation costs 0.1 %O2**, on a 3V3D that
is now a bare AP63203 buck output. With `VREF+` = the REF3425 that coupling is
not reduced, it is **zero** — VDDA appears nowhere in the derivation. Residuals
are the LMP's PSRR at RE (80 dB min) and the TIA's unspecified supply
sensitivity, both behind R32/C7. **~1000x on the term that dominates.**

## Open, and deliberately not closed by this decision

1. ~~**Keep U8's footprint, or reclaim the area?**~~ **CLOSED 2026-09-12 —
   DROPPED**, by revB, on a better argument than the one I offered. I had
   recommended keeping it if area allowed, treating it as a PCB-area question.
   It is not: on a generated board a footprint can only be retained by keeping
   U8 in the netlist as a DNP, and a DNP U8 puts U8's pads back into `ASSIGNED`,
   which makes `gen_hw_caps.py` derive `O2P_HW_HAS_ADS1119 = 1` and emit channel
   macros for a part that is not fitted. **That is precisely the failure the
   per-revision capability split exists to prevent**, and the one that cost a
   healthy probe every oxygen reading on 09-09. A hedge that makes firmware
   assert hardware the board does not have is not a hedge. If the digital-noise
   term does bite, the remedy is shielding, a sampling change or a different
   converter — not a resurrected ADS1119 whose three dead inputs are the reason
   for this document.
2. **The single-rail buck ripple** remains the release gate of
   `2026-09-12-revb-single-rail-supply.md` §8.7/§9. This decision makes the
   oxygen channel insensitive to it; it does not measure it. That gate needs a
   scope or a deliberate peak detector — **an ADC channel cannot answer it**, the
   10 us aperture nulls at 99.7 kHz.
3. **The cell/AFE tempco split** is still unmeasured. Only the dummy-cell run in
   `2026-09-09-afe-tempco-plan.md` (6.04 kOhm in the socket + ring heater) closes
   it. No longer gates this decision, since the acceptance criterion is re-based.
4. ~~**STM32G0 `CHSELR`/`CCRDY` errata** — unverified, the errata sheet is not
   archived.~~ **CLOSED 2026-09-12 — no such erratum exists**, ES0418 Rev 5 is
   archived, and the fetch turned up a different erratum that does apply:
   **2.6.7, `EO` out of specification below `VREF+` = 3.0 V.** See the ES0418
   section at the foot of this document. No hardware change; firmware gains a
   `CALFACT` fault bit and a workaround path, and PA5 is no longer free.

## Implemented 2026-09-12 — revB, `~/dev/ee` commit `68e6bde` (unpushed)

83 components / 292 pins, `kicad-cli sch erc` 0/0, `audit_schematic` PASS
(72 nets), `audit_layout` PASS, `pio run -e o2probe` SUCCESS, 360/360 native.
Every hardware line above is in, plus `C26` 100 n relocated onto `/VREF_TRIM` at
pin 5 and `D8` BAT54 on PA6.

**Verified independently here, not relayed:** regenerating both caps headers
from the current netlist reproduces revB's committed files **byte-identically**,
so the emitted capability set is what the netlist actually implies.

Two defects they found by reading the *emitted header* rather than trusting the
restructure — **both silent, neither would have failed a build, both would have
lied to a firmware guard**:

1. `O2P_HW_VREF_NET_SHARED_WITH_AFE` inverted to **0** on Rev B. The
   `has_ads` branch read PA5 as "the converter's reference", true only while the
   reference was a measured channel; once `VREF+` became the reference, PA5 went
   to `(NC)` and the flag flipped — while the true answer is emphatically yes.
   Now derived from U6.5.
2. The pad normaliser prefixed the `(NC)` marker into `/(NC)`, which reads as a
   net named `NC`.

**The architecture is now locked in the caps, not just documented.**
`O2P_HW_VREF_IS_ADC_REFERENCE`, derived from one pad: when 1,
`O2P_HW_DIV_VREF_MON_*` **do not exist** and `O2P_HW_VREF_MV` 2500u does; when
0, the reverse. Asking for the wrong one is a compile error. And `board_pins.h`
asserts `/VREF_TRIM` lands on pin 5 via a new `O2P_LQFP48_VREFP`, so **putting
pin 5 back on 3V3D stops the build** rather than quietly re-admitting VDDA at
0.718 mV/mV. That is the right shape: the thing that must not silently regress
now cannot.

### D8 selection gate, and its deliberate limit

`Ir <= 1 uA at 1.2 V reverse, 85 C`, taken from the **curve**, not the headline.
The catalogue 2 uA at 25 V would be 18 mV on `VIN_MON` through the divider's
9.0k — tolerable only because nothing scales by that reading. revB recorded in
the schematic that this reasoning **does not license a clamp on an oxygen-path
channel**: 2 uA into R33's 1 k is 0.06 %O2 on the measurement itself. Correct,
and it is the distinction that makes footnote 3's mitigation safe to fit.

**Procurement gap:** `BAT54-7-F` is on no purchase order and `audit_bom` flags
it. Checked against stock on hand — **nothing suitable**: the five Schottkys
held are all power rectifiers (1 A to 40 A, 40-100 V), whose reverse leakage at
85 C is orders of magnitude outside the 1 uA gate. D8 must be bought.

## ES0418 fetched 2026-09-12 — open item 4 answered, and it found a bigger one

Archived: `~/dev/ee/datasheets/ST-STM32G071-ES0418-Rev5-errata.pdf`,
**Rev 5, November 2023** — the current revision. Provenance matters here: a
mirror served Rev 4 (Oct 2022) while st.com hung on every curl rung, and Rev 4
is materially different at exactly the erratum below. Rev 5 came through a
headless browser `fetch()`. Do not re-derive this from the Rev 4 text.

**Open item 4 is answered, as a clean negative: there is no `CHSELR`/`CCRDY`
erratum.** Zero occurrences of either string in Rev 5 (or Rev 4). The ADC
errata are 2.6.1-2.6.7 and the channel-selection handshake is not among them.
The sampler port may rely on it.

### 2.6.7 — `EO` may be out of specification when `VREF+` < 3.0 V

Nobody costed this, and the adopted architecture is the reason it applies.

> "When the `VREF+` voltage is lower than 3.0 V, the ADC hardware calibration
> may not fully compensate for the offset error caused by the diffusion process
> variation. When this occurs, the `CALFACT` register value is either 0x00 or
> 0x7F and the `EO` parameter is out of the maximum stated in the device data
> sheet."

`VREF+` = `/VREF_TRIM` = **2.500 V**. That is the whole point of the adopted
form, and it puts the part inside this erratum's stated condition.

At our `fADC` = 16 MHz (HSI16, `mcu.c:99`), the substituted specification:

| | DS12232 Table 60 | ES0418 Rev 5 2.6.7 | |
|---|---|---|---|
| `EO` typ | 1.5 LSB | 1.5 LSB | **unchanged** |
| `EO` max | 4.5 LSB | **50 LSB** | 11x |
| `ET` max | 6.5 LSB | **52 LSB** | 8x |

At 2.500 V full scale one LSB is 610.4 uV, so 50 LSB = **30.5 mV** = 4.36 uA
through the 7 kOhm TIA. Stated the way this document now requires — mV at the
TIA output, %O2 only at a named cell output — that is 30.5 mV, and at
DS-0637's 99 uA air point **0.92 %O2** raw.

**What the air calibration does and does not remove.** A converter offset is a
constant current error, so the air point absorbs it there and nowhere else.
With `d` = 4.36 uA on a 99 uA air point, the normalised fraction at zero oxygen
reads `d/(I_air+d)` = 4.2 % of the air fraction, i.e. **0.88 %O2 of error at
0 %O2, falling linearly to zero at the air point**. The error is largest at the
low-oxygen end, which is the end compost aeration decisions are taken at. It is
4-6x the whole 0.14-0.20 %O2 static budget.

**Three things make it much less alarming than that, and one makes it worse.**

- **Typ is unchanged.** This is not a continuous degradation, it is a
  population effect: an affected part saturates `CALFACT` to 0x00 or 0x7F.
- **It is detectable per part at boot, and the detector is already specified
  above** — "Publish `ADC_CALFACT` per boot". That line was written as a proxy
  for offset drift; it is now also the erratum's own trigger condition. Make it
  a fault bit, not just telemetry.
- **Two independent absolute checks already exist**: `WE_BUF` should read code
  2744 (0.67 x FS) and `RE_BUF` code 3727 (0.91 x FS), both to the LMP's
  +/-0.04 % = ~1.6 LSB. A 50 LSB offset is 30x that, so it cannot hide.
- **Worse:** it is silicon-revision dependent, and *we do not know which
  silicon we have.* ES0418 Table 3: marking **B** (`REV_ID` 0x2000) = present
  with workaround; marking **Y** (0x2002) = **absent**. `DBGMCU_IDCODE` is not
  in the firmware's peek allowlist (`regmap.c:1199-1211` admits SRAM, the boot
  and app slots, the UID and the flash-size word — peripheral space is
  excluded), so this needs one SWD read or the package marking on U6. Not worth
  disturbing a settled bench measurement for; do it next time the board is on
  the debugger.

### The workaround is free on the board as designed — but only in Rev 5

Rev 4's third workaround required `VREF+` and `VSSA` **on ADC GPIO inputs**,
which the adopted spec had just deleted the means to do: PA5 is `nc()`
(`gen_sch.py:1117`) precisely because converting the reference against itself
saturates. Rev 5 adds four words — "**or internally through the DAC output**" —
and that changes the answer from "one more pin and a route" to **firmware
only**:

- DAC channel 2 is on PA5, which is already `nc` and already free.
- DAC full scale is `VREF+` and DAC zero is `VSSA`, giving both `CALFACT`
  branches, with the pad isolated.
- So **no schematic change, no part, no pin.** `68e6bde` stands as committed.

Two caveats, both firmware-side:

1. **Reserve PA5.** It is documented above as "returns to the pool"; it is now
   the erratum's workaround channel (DAC_OUT2 / ADC_IN5). Do not hand it to
   anything else. DAC_OUT1 is on **PA4 = pin 15 = `CE_MON`** and is therefore
   unavailable, so channel 2 is the only one.
2. **The exact register path is unverified** — RM0444 is not archived and the
   "connected to on-chip peripheral" DAC mode needs reading before the sampler
   port relies on it. ES0418 sanctions the method; it does not give the
   sequence. Also check erratum 2.3.1 ("GPIO assigned to DAC cannot be used in
   output mode when the DAC output is connected to on-chip peripheral") — PA5
   is an input-only `nc` pin here, so it should not bite, but confirm.

### A firmware option that removes the term entirely, not decided here

`I = V_REF x (code_WE - code_AFE) / 4096 / R_TIA`, using the **measured**
`WE_BUF` code in place of the compile-time 0.67 constant, cancels a common
converter offset exactly — both channels are FT_a pins on the same converter,
and `EO` subtracts out. This is **not** the rejected three-conversion form:
that one reads `/VREF_TRIM` itself and saturates. `WE_BUF` sits at 67 % of full
scale and converts normally.

It is a real trade, not a free win, and it is Fab's and revB's call:

- **For:** removes `EO` (erratum or not) and the LMP's own internal-zero ratio
  error from the oxygen term.
- **Against:** adds a second conversion's noise, and it spends the independent
  check. Today a leak on PA0 breaks a *known constant* and is caught; if
  `code_WE` becomes part of the measurement, that same leak corrupts oxygen
  silently. That is the failure mode this whole revision exists to prevent.

The conservative shape: keep the constant form as primary, publish both, and
switch only when `CALFACT` says the erratum has bitten on this part.

### Other ADC errata checked against the sampler port

| | applies? |
|---|---|
| 2.6.1 `OVR` not set if `EOC` clear coincides with conversion end | only if the port polls `EOC` and can overrun |
| 2.6.2 writing `ADC_CFGR1` while `ADEN` set resets `RES[1:0]` to 00 | **yes, a real trap** — a 12-bit config silently becomes 6-bit. Disable, configure, re-enable |
| 2.6.3 AWD1 misses out-of-threshold in Single mode past the first channel | only if an analog watchdog is used on a sequence; none is today |
| 2.6.4 sampling time one cycle longer | **no** — 1.5/3.5 cycles only; we use 160.5 |
| 2.6.5 / 2.6.6 | documentation errata, trigger latency |

### RM0444 Rev 6 + DS12232 Table 62 — the DAC path is real but not exact

Archived: `~/dev/ee/datasheets/ST-STM32G0x1-RM0444.pdf`, **Rev 6**, 17 180 597 B,
byte-count verified against st.com. Reached the same way as ES0418 Rev 5.

**Correction to the section above.** I wrote that the Rev 5 workaround is "free
on the board as designed". That is right for one of the two `CALFACT` branches
and too strong for the other. The register path exists and needs no pin:

- `DAC_MCR MODE2 = 011` — "DAC is connected to on-chip peripherals", output
  buffer **disabled**, `DACx_OUTy` disconnected from the pad (RM0444 §16.4.2,
  and the MODE encoding). PA5 stays physically `nc`.
- The internal destination is **not** `ADC_IN5`. `ADC_CCR` bit 24: "0: VBAT
  channel disabled, **DAC_OUT2 connected to ADC channel 14**". So the reading is
  taken on internal channel 14, with `VBATEN` cleared, writable only while
  `ADSTART = 0`.
- `ADC_CCR` bit 23 does the same for `DAC_OUT1` → **channel 12**, but that one is
  gated on `TSEN = 0`, i.e. it costs the internal die-temperature sensor, which
  is in use. **Channel 2 / channel 14 is the only free path** — and DAC_OUT2 is
  on PA5. The alignment is luck, not design.

**What limits it: the DAC's own error, in the same LSBs.** DS12232 Table 62,
buffer OFF, `CL <= 50 pF, no RL` — which is exactly the on-chip-peripheral case:

| | buffer OFF |
|---|---|
| `Offset1` at code 0x001 | ±5 LSB |
| `Offset` at code 0x800 | ±8 LSB |
| `INL` | ±4 LSB |
| `Gain` | **±0.5 %** = ±20 LSB at full scale |
| `TUE` | ±12 LSB |

A DAC LSB and an ADC LSB are the same 610 uV here — both are 12-bit off the same
`VREF+` — so these numbers land directly on the correction:

- **`CALFACT` = 0x7F (the `VSSA` branch): the DAC is good.** Code 0x001 carries
  ±5 LSB, so a 50 LSB offset is corrected to about ±5. Free, firmware only.
- **`CALFACT` = 0x00 (the `VREF+` branch): the DAC is weak.** The reading is near
  full scale, where the DAC's ±0.5 % gain error is **±20 LSB** and masquerades as
  ADC offset. Correcting a 50 LSB unknown with a ±20 LSB ruler is an improvement,
  not a fix.

So the earlier "no schematic change" holds only if the part turns out to be
0x7F, and we will not know that until a part is measured. `68e6bde` is still
correct as committed — nothing here is a defect in it — but the remedy set needs
ranking, and the ranking is Fab's and revB's call, not mine:

1. **The differential form, `code_WE - code_AFE`** (the option above). Cancels
   `EO` **exactly**, for both branches, with no pin and no part — it is ST's own
   second workaround bullet, "use the ADC for measuring a difference between two
   DC voltages". Cost: one conversion's noise, and it spends `WE_BUF` as an
   independent check.
2. **Wire PA5 to `/VREF_TRIM` after all.** One route, zero parts, and it gives
   the 0x00 branch an exact reference instead of a ±20 LSB one. This also
   **retracts a claim made above and in `gen_sch.py:1100`**: converting the
   reference against itself does not "carry no information" — the erratum's whole
   method is that it reads 4096 *minus the offset*, so the saturation is the
   measurement. That reasoning was sound for the VDDA architecture and is wrong
   for this one.
3. **DAC2 internal** as specified above: free, sufficient for 0x7F, partial for
   0x00.
4. **Detect and reject.** Publish `CALFACT`, and treat 0x00/0x7F as a
   production-test failure for that MCU. Viable precisely because typ is
   unchanged, so affected parts should be a minority.

Whatever is chosen, **PA5 must stop being advertised as free** — every remedy
except (1) and (4) claims it, as a pin or as DAC_OUT2.

Still open, and cheap: **which silicon revision we have.** `REV_ID` 0x2000
(marking B) has the erratum, 0x2002 (marking Y) does not. One SWD read of
`DBGMCU_IDCODE`, or the marking on U6. If it is Y, all of this is moot for the
parts on hand — and it must then become a **purchasing constraint**, because the
next reel can be either.
