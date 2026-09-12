# Schematic ownership handoff — o2-probe Rev B

**Date:** 2026-09-12
**From:** Claude session `revb-ee` (~/dev, schematic + firmware)
**To:** Codex session `codex-farming-h7ln` (PCB, worktree `~/dev-worktrees/o2-revb-current`)
**Authority:** Fab, 2026-09-12, "handoff schematics to them"

Until today the split was: I owned `gen_sch.py`, `audit_schematic.py`, the
generated `.kicad_sch` and the firmware; the Codex session owned the PCB. Fab has
handed the schematic over as well. This document is the handoff.

Everything below is state as of commit **`77654f4`** in `~/dev` (repo root is
`~/dev`, *not* `~/dev/ee`). **Nothing is pushed, in any tree.**

---

## 1. The one invariant that breaks everything if missed

**`o2-probe.kicad_sch` is generated output. `gen_sch.py` is the design.**

`python3 gen_sch.py` rewrites the entire sheet — components, placement, wires,
labels — from the Python source. A hand edit in the KiCad GUI survives exactly
until the next generate, and leaves no trace when it dies. This applies inside an
isolated worktree too.

Corollary: there is no merge story for the `.kicad_sch`. Two sessions editing it
is two sessions editing a build artifact. Change the generator.

Watch for `_autosave-o2-probe.kicad_sch` in the directory — it means someone had
the sheet open in KiCad with unsaved edits, and those edits are already gone.

## 2. Verification block — run all of it

```sh
cd ~/dev/ee/hw/o2-probe
python3 gen_sch.py
kicad-cli sch erc --exit-code-violations o2-probe.kicad_sch
kicad-cli sch export netlist -o /tmp/o2.net o2-probe.kicad_sch
python3 audit_schematic.py /tmp/o2.net
python3 audit_layout.py
python3 audit_mpn_package.py
python3 audit_bom.py
cd firmware && pio run -e o2probe && pio test -e native
```

Current expected results: ERC 0/0 · `audit_schematic` PASS, 72 nets ·
`audit_layout` PASS, 0 collisions · `audit_mpn_package` FAIL with 4 known errors
(D3/U15/U16 unmapped footprints, U11 unstated) · `audit_bom` FAIL with 11 errors
(10 pre-existing, plus D8 on no purchase order) · `pio run` SUCCESS ·
`pio test` 360/360.

`pio run -e o2probe_revb` **fails on purpose** — a hard `#error` in `ads1119.c`,
because Rev B has no ADS1119 and building it would drive PB1, the oxygen
channel's analog input, as a GPIO. `o2probe_revb` is out of `default_envs` until
the sampler port lands. Do not "fix" either by muting.

### `audit_mpn_package.py` is the one that is easy to skip, and it is the one that matters

It is the only check that compares an MPN against its footprint using
**distributor parametrics** rather than the author's memory, so it is the only
one that can catch a package error. D8 shipped in the wrong package yesterday
purely because I did not run it. It is cached; the repeat cost is ~2 s.

**Run it whenever an MPN or a footprint changes.**

## 3. Guard discipline in this tree

Two rules, both learned the hard way here, both worth keeping:

1. **Write assertions from the design statement, not from the code.** D8's
   polarity assertion was transcribed from the `add_passive()` call, so it
   asserted the bug and passed. Assertions now name *roles* — cathode, anode —
   not net order.
2. **Calibrate every guard by constructing its target failure and watching it
   fail.** Both guards added in `77654f4` were calibrated this way. A guard that
   has only ever been seen to pass has not been tested.

Related live example: `audit_schematic.py`'s comments claimed exact net
membership while the loop computed only `wanted - actual`, so extra pins passed
silently — the precise failure the comment claimed to catch. There is now an
`EXACT` set (8 nets) checked in both directions. Other nets remain subset-checked
and say so.

`authoritative_symbol()` exists so that no schematic symbol is hand-drawn: every
symbol is validated against the installed KiCad library. Preserve this. It is why
D8 became a Vishay SOD-123 part rather than a SOT-23 one — a SOT-23 single
Schottky has no authoritative KiCad symbol, and inventing one would have put a
hand-authored symbol in a generator built to forbid them.

## 4. Recent design decisions you are inheriting

- **U8 (ADS1119) is deleted.** All four analog channels convert on the STM32G071
  SAR. `docs/2026-09-12-revb-decision-delete-ads1119.md`.
- **`VREF+` (pin 5) is driven from `/VREF_TRIM`, the REF3425 — not VDDA.** The
  VDDA form was proposed and rejected. The reason is load-bearing and easy to
  re-propose by accident: arithmetic cancellation of rail drift *fails*, because
  the two conversions happen at different instants on a moving rail (3V3D couples
  at 0.718 mV/mV at zero O₂; 4.63 mV RMS is 0.1 %O₂). Only wiring the LMP91000
  ladder and the SAR full scale to the same node cancels it.
- **PA5 (pin 16) is `nc()` and RESERVED — not free.** *(Corrected 2026-09-12;
  this bullet originally read "converting the reference against itself saturates
  at 4095", offered as the reason PA5 returned to the pool. ES0418 §2.6.7's own
  workaround makes that saturation the measurement — see the addendum. Every
  hardware remedy for that erratum claims PA5, as a pin to `/VREF_TRIM` or as
  `DAC_OUT2`. Do not spend it.)*
- **U8's footprint was dropped, not kept as DNP** — a DNP U8 would put its pads
  back in the netlist and make `gen_hw_caps` emit `O2P_HW_HAS_ADS1119 = 1`.
- **Bias-leg headroom, stated honestly:** V_WE = 1.675 V = 0.67 × FS (code 2744),
  V_RE = 2.275 V = 0.91 × FS (code 3727) against 2.500 V. Nothing clips, but V_RE
  has 225 mV, not "a volt of room" as an older note claimed. Both codes are known
  constants, so drift off them is a free per-channel leak detector.

## 5. Open items handed over with the schematic

| item | state |
|---|---|
| **D8 leakage gate** | **RETIRED by Fab, 2026-09-12** — "relax the gate, record the number". The `Ir ≤ 1 µA at 1.2 V, 85 °C` gate came from an 18 mV budget that was picked rather than required; VIN_MON is health telemetry with 7/15 V thresholds. *(This row previously said Fig. 3 plots −40/25/125 °C and cited "Vishay 86409". Both wrong: the document is **85885 Rev 1.1**, and −40/25/125 °C is Fig. 1, the forward curve — Fig. 3 plots 25/50/75/100/125 °C.)* Digitized typical value 8.662 µA at 85 °C, 1.331 V → 78 mV, in `datasheets/BAT54W-G-leakage-digitized/`, **pending human overlay verification** and not a worst case. |
| **D8 procurement** | `BAT54W-G3-08`, Vishay, SOD-123, €0.42, 29.5k at Mouser DE. On no purchase order. Fab's call. |
| **PCB** | Still carries U8, R19, C18/C19, R34/R35/R36/C29; no routes for the MCU analog channels; no D8; no R25/C26 changes. Yours already. |
| **Sampler port** | `ads1119.c` → `mcu_adc.c`; `ADCAL` after every power-up; re-derive the VREF gate at `main.c:700`/`:869`; restore `o2probe_revb` to `default_envs` in the same commit. Mine unless Fab moves it. |
| **STM32G0 CHSELR/CCRDY errata** | **CLOSED 2026-09-12, clean negative.** Zero occurrences of `CCRDY` or `CHSELR` in ES0418 Rev 5 or Rev 4; the ADC errata are §2.6.1–2.6.7 and the channel-selection handshake is not among them. Grepped in the archived PDF, not relayed. The sampler port may rely on that handshake. |
| **ES0418 §2.6.7, ADC offset** | **OPEN, and it lands on the reference architecture committed today.** See the section below. |
| **Buck-ripple release gate** | Open — `docs/2026-09-12-revb-single-rail-supply.md` §8.7/§9. |
| **Cell/AFE tempco split** | Needs the dummy-cell run, `2026-09-09-afe-tempco-plan.md`. |
| **Pre-existing audit errors** | 10 BOM errors + 4 `audit_mpn_package` errors, all predating today. Listed in §2. |

## 6. Two hazards in the working tree

- **The frozen Rev A fab archive is dirty.**
  `fab/o2-probe-rev-a-source/source/o2-probe.kicad_pro` and `.kicad_prl` are
  modified (+362 lines) because someone opened KiCad. That archive is pinned by
  commit and verified by SHA-256. I left both **unstaged** — neither committed
  nor reverted — because I do not know which session did it. Check the pinned
  hash still resolves before touching it.
- **Several agent sessions share these worktrees.** Stage explicit paths. Never
  `git add -A` or `git commit -a`. Read `git diff --cached --name-only` before
  every commit; the index may already hold another session's files.

## 7. What I still hold

Firmware (`firmware/`), including `gen_hw_caps.py`, `gen_hw_contract.py`,
`hw_caps.h`, `board_pins.h` and the sampler port — unless Fab says otherwise.

The firmware derives its hardware contract *from the schematic*, so a generator
change can break a firmware guard without breaking a build. `gen_hw_caps.py`
refuses to emit rather than guess when it cannot resolve a pad; that refusal is
correct behaviour, not a bug to route around. If you change a net or a pin
identity, run `pio run -e o2probe` and read the emitted `hw_caps_rev_b.h` — one
capability silently inverted during the U8 removal and was caught only by reading
the header, not by any build failing.

---

## Addendum, 2026-09-12: ES0418 §2.6.7 and two retracted claims

Added at the Codex session's request, so these survive outside a generator
comment while the 86 mm fabrication artifacts are frozen. Source: ST **ES0418
Rev 5**, archived at `~/dev/ee/datasheets/ST-STM32G071-ES0418-Rev5-errata.pdf`
(commits `40e914a`, `3fe1466`). Fetched by a peer session; every claim below was
re-verified against the PDF here rather than relayed.

### The erratum

**§2.6.7 "ADC offset may be out of specification".** When `VREF+` is below
3.0 V the ADC's hardware calibration may not fully compensate the offset caused
by diffusion-process variation. `CALFACT` then reads `0x00` or `0x7F`, and the
datasheet's `EO` is replaced by:

| condition | typ | max |
|---|---|---|
| `1.65 V < VDDA = VREF+ < 3 V`, fADC = 16 MHz, fs ≤ 1.1 Msps | 1.5 | **50 LSB** |

Silicon-dependent: status **A** on rev B, **"–"** on rev Y.

Rev B of this board drives `VREF+` from the REF3425 at 2.500 V, so it is inside
the erratum's description. 50 LSB × 610 µV = 30.5 mV ≈ 4.36 µA against a ~99 µA
air point: the air calibration absorbs it *at the air point*, leaving roughly
**0.9 %O₂ at zero oxygen** — worst precisely at the low-oxygen end this probe
exists to measure. Typ is unchanged, so it is a per-part effect.

**Applicability is ambiguous and must not be written down as settled.** The
substituted table is characterised at `VDDA = VREF+`. This board's rails are
split — VDDA 3.3 V, `VREF+` 2.500 V — so it matches the erratum's *description*
(which keys on `VREF+` alone) but not the condition its numbers were taken
under. 50 LSB is therefore neither clearly applicable nor clearly excluded.

### Two claims in `gen_sch.py` that are now wrong

Both are at the PA5 block (~line 1098–1100) and both were inherited wording.
**Not corrected in the generator** — that file is the Codex session's and its
artifacts are frozen; agreed as a separate reviewed follow-up.

1. *"Converting `/VREF_TRIM` against itself saturates at 4095 and carries no
   information."* **False in this architecture.** The erratum's own workaround
   for the `CALFACT = 0x00` branch is to measure `VREF+` on an ADC GPIO or DAC
   channel and subtract the result from 4096 to obtain the offset. The
   saturation *is* the measurement.
2. *"PA5 (pin 16) therefore RETURNS TO THE POOL."* **Premature.** Every hardware
   remedy claims PA5 — as a pin to `/VREF_TRIM`, or as `DAC_OUT2`. **Treat PA5
   as RESERVED**, still `nc()`, and do not spend it.

### Two details worth not losing

- **The `0x7F` branch measures VSSA, not `VREF+`,** and *subtracts*. A remedy
  that only brings `VREF+` to a channel covers one branch of two; the other
  needs a path to ground.
- `mcu_adc.c:73` already runs `ADCAL`, but **nothing reads `CALFACT`.** Reading
  and publishing it is the cheapest possible answer to "does this erratum bite
  our parts": `0x00` or `0x7F` is the erratum firing, anything else is not. It
  cannot be exercised on the Rev A bench board, whose `VREF+` is 3V3D at 3.3 V
  (`O2P_HW_VREF_IS_ADC_REFERENCE 0`), so it only becomes measurable on Rev B
  hardware.

### Decisions that are Fab's, not mine

- **Which silicon.** Rev Y does not have this erratum. `DBGMCU_IDCODE` is not in
  the firmware peek allowlist, so it needs one SWD read or the marking on U6.
  If the parts on hand are Y this is moot for them — and becomes a *purchasing*
  constraint, since the next reel can be either.
- **The remedy.** The software-only form — `I = V_REF × (code_WE − code_AFE) /
  4096 / R_TIA`, using the measured WE_BUF code instead of the compile-time
  0.67 — is ST's own second workaround bullet ("use the ADC for measuring a
  difference between two DC voltages") and needs no hardware. Its cost is that
  it spends WE_BUF as an *independent* check: a PA0 leak would then corrupt
  oxygen instead of breaking a known constant, which is the failure mode this
  revision exists to prevent.
