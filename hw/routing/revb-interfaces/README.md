# Rev B receiver-enable and CE interfaces

The current two-layer Rev B candidate completes the RS-485 `/RE` split and
CE resistor/clamp layout. It has **99 components**, including R45, with no
RV1. The root PCB remains the Rev A article; this directory is the candidate.

**Reproducible engineering-review export.** `python3 make_fab.py` now builds
this two-layer Rev B design by default. Saved-fill and CLI-refilled DRC have
zero copper errors, opens, parity findings and silkscreen warnings. The remaining
15 courtyard warnings have individual manual-assembly dispositions; they are
visible, not disabled. The package is not order-ready: procurement
and physical qualification remain open; J5/F3 are deferred to optional Rev C.

See [build/export instructions](../../docs/REVB-FAB.md),
[assembly dispositions](../../docs/REVB-ASSEMBLY.md), and the
[current removal validation and review record](../../docs/2026-09-09-revb-ring-removal.md).
The [current BOM reconciliation](../../docs/REVB-BOM-RECONCILIATION.md) records
exact capacitor choices, refreshed order coverage, current stock and remaining gates.

Read the [implementation, source evidence and qualification record](../../docs/2026-09-09-revb-protection.md).
The previous [BOM39 candidate](../2layer-bom39/PROVENANCE.md) is unchanged.

## Changes

- U5.2 `/RE` reaches PC7/U6.31 independently of DE/PC6; R45 = 47k defaults
  reception on. The existing firmware and loader already support this split.
- R42 = 1k 1%, with an explicit internal-rail fault-current and compliance
  budget. D7 uses the complete TPD2E2U06QDBZRQ1 order code and correct DBZ
  pinout: 1 CE, 2 unused, 3 GND. The CE route passes through the clamp land.
- Ground stitches connect R45's formerly empty fill regions and make the
  existing thermal-web ground strap's main-plane connection explicit.
- A short 3V3D detour permits the receiver escape without drilling SMD lands.
  U6.21 is explicit PB2 NC; symbol fields match the current generator.

## Reproduce and verify

From the project root (KiCad 10.0.5):

```sh
python3 make_fab.py --revision rev-b
```

The exporter copies all source dependencies into staging, generates the schematic,
replays `adopt_revb_interfaces.py` and `finish_revb_layout.py`, compares the rebuilt
board with this accepted candidate, then runs all checks before packaging it.
The historical BOM39 route and root Rev A PCB remain unchanged. `gen_pcb.py`
supplies placement only; it does not reproduce the routed copper.

The finishing step moves R17 above U4 and connects it to the existing MENB trunk,
removing the obsolete resistor-only branch. It moves conflicting wire/cell
outlines and process notes onto the assembly drawing. The optional ring branch
J5/F3 and its supply/return spurs are removed; the accepted wire lands are explicit in the schematic and project library.

## Evidence

- [Saved-fill DRC](drc-saved-fill.json), [CLI-refilled DRC](drc-refill.json)
- [Schematic ERC](erc.json), [physical pin/value check](interface-check.txt)
- [51-item critical-route check](critical-check.txt)
- [Artifact and tool-source hashes](validation-manifest.json)

The original interface implementation record is historical evidence. Current
build/export status is in the links above and this directory's refreshed reports.

The deferred design is discoverable in [PCB plans](../../plans/README.md) and
[the Rev C heated-ring recovery plan](../../plans/REVC-HEATED-RING.md).
