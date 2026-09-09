# Rev B receiver-enable and CE interfaces

The current two-layer Rev B candidate completes the RS-485 `/RE` split and
CE resistor/clamp layout. It has **101 components**, including R45, with no
RV1. The root PCB remains the Rev A article; this directory is the candidate.

**Not a fabrication release.** Both saved-fill and CLI-refilled DRC have
zero copper errors and zero unconnected items, while 41 inherited non-copper
warnings and five inherited footprint-parity findings remain visible. Bench
compliance, leakage, ESD and thermal qualification are still required.

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
python3 gen_sch.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  adopt_revb_interfaces.py routing/revb-interfaces/o2-probe.kicad_pcb
python3 verify_revb_interfaces.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  routing/2layer-bom39/verify_critical.py \
  routing/revb-interfaces/o2-probe.kicad_pcb --essential-only --expect-locked
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc \
  --severity-all --schematic-parity --refill-zones --format json \
  -o /tmp/o2-revb-drc.json routing/revb-interfaces/o2-probe.kicad_pcb
```

The schematic and project library beside this board are copies of the root
outputs; refresh both when regenerating. The migration starts from the pinned
BOM39 route, authors the local changes, preserves the project constraints and
requires successful zone fill plus zero opens before saving. KiCad assigns
fresh IDs to added items: compare geometry/connectivity when reproducing.
`gen_pcb.py` supplies placement only and does not reproduce this routed copper.

## Evidence

- [Saved-fill DRC](drc-saved-fill.json), [CLI-refilled DRC](drc-refill.json)
- [Schematic ERC](erc.json), [physical pin/value check](interface-check.txt)
- [63-item critical-route check](critical-check.txt)
- [Artifact and tool-source hashes](validation-manifest.json)

The candidate retains the previously accepted J105/J106 no-relief footprints.
The five parity findings concern those substitutions/filters and F3's filter;
there is no remaining pin/net or value mismatch. The non-copper warnings and
open product qualification gates are not waived by these checks.
