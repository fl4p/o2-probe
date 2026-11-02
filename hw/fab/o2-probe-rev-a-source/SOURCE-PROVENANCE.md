# o2-probe Rev A — design source as released for fabrication

The KiCad source of the board that `o2-probe-rev-a-fab.zip` was exported from.
The fab package itself carries only Gerbers, drills and reports; it pins its
input by hash in `fab-manifest.json` but never contained the board. This zip
was assembled afterwards, on 2026-09-10, to close that gap.

## Provenance

- Source commit: `16b5a6062bc36eecad4c589553d5fdd65bc0a0bd` in the `~/dev` monorepo (`ee/hw/o2-probe/`),
  2026-08-24 13:49:04 +0200, "o2-probe: restore heated-island side slots".
  The same files are at `1774fac` in `slopmylife/o2-probe`; blobs identical.
- `o2-probe.kicad_pcb` SHA-256 `983681ce…6d230` and `o2-probe.kicad_sch`
  SHA-256 `dcba8c14…d932` equal `input.sha256` and `schematic.sha256` in the
  Rev A `fab-manifest.json` (generated 2026-08-24T11:48:20Z, kicad-cli 10.0.5).
- `lib/tmp117-probe.pretty/` is `ee/hw/tmp117-probe/lib/tmp117-probe.pretty`
  at the same commit.

## The one edited file

`fp-lib-table`: the `tmp117-probe` URI was
`${KIPRJMOD}/../tmp117-probe/lib/tmp117-probe.pretty` and now points at the
bundled `${KIPRJMOD}/lib/tmp117-probe.pretty`, as in the Rev B packages.
Every other file is byte-identical to the commit; see `SHA256SUMS`.

## Reading it as fabricated

- Silkscreen was **not** exported (`silkscreen_exported: false`). The fab house
  received F.Cu, In1.Cu, In2.Cu, B.Cu, F.Mask, B.Mask, Edge.Cuts and drills.
- The Gerbers came from the zone fills saved in this board. Do not refill
  zones before comparing against the Gerbers.
- The link to the physical order runs through the release package. No record
  from the fab house of the uploaded file was found in either repository.
