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
- **PA5 (pin 16) is `nc()`.** Converting the reference against itself saturates
  at 4095. The reference is not measured at all any more.
- **U8's footprint was dropped, not kept as DNP** — a DNP U8 would put its pads
  back in the netlist and make `gen_hw_caps` emit `O2P_HW_HAS_ADS1119 = 1`.
- **Bias-leg headroom, stated honestly:** V_WE = 1.675 V = 0.67 × FS (code 2744),
  V_RE = 2.275 V = 0.91 × FS (code 3727) against 2.500 V. Nothing clips, but V_RE
  has 225 mV, not "a volt of room" as an older note claimed. Both codes are known
  constants, so drift off them is a free per-channel leak detector.

## 5. Open items handed over with the schematic

| item | state |
|---|---|
| **D8 leakage gate** | **OPEN.** `Ir ≤ 1 µA at 1.2 V reverse, 85 °C`. Vishay 86409 Fig. 3 plots −40/25/125 °C only, so 85 °C is an interpolation, not a spec. Digitize with `dsdig` (`~/dev/pv/ee/datasheet-chart-digitizer`), never by eye. Not met today. |
| **D8 procurement** | `BAT54W-G3-08`, Vishay, SOD-123, €0.42, 29.5k at Mouser DE. On no purchase order. Fab's call. |
| **PCB** | Still carries U8, R19, C18/C19, R34/R35/R36/C29; no routes for the MCU analog channels; no D8; no R25/C26 changes. Yours already. |
| **Sampler port** | `ads1119.c` → `mcu_adc.c`; `ADCAL` after every power-up; re-derive the VREF gate at `main.c:700`/`:869`; restore `o2probe_revb` to `default_envs` in the same commit. Mine unless Fab moves it. |
| **STM32G0 CHSELR/CCRDY errata** | Unverified. Worth one fetch before the port relies on that handshake. |
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
