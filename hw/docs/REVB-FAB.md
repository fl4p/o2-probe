# Rev B build and fabrication review

Run from the project root:

```sh
python3 make_fab.py
# Equivalent explicit selection:
python3 make_fab.py --revision rev-b
```

The default is now the **two-layer Rev B engineering-review package**. The
historical root PCB and Rev A exporter remain accessible with `--revision rev-a`.
Rev B does not call Rev A's four-layer board audit or apply its castellation
assumptions to this two-layer board.

The command creates a private staging tree, generates the live schematic and
library, migrates the pinned BOM39 route, applies the reviewed assembly/legend
changes and ring-branch retirement, and compares the result with the accepted Rev B candidate. Comparison
ignores fresh item IDs, serialization ordering and exact collinear interior
vertices while retaining geometry,
polygon vertex order, electrical properties, text and fabrication settings.
The root source PCB and historical route are never rewritten by this command.

KiCad 10.0.5 is required at the recorded macOS installation paths. Both saved-fill
and freshly refilled DRC run with all severities and schematic parity. The exact
15 individually dispositioned courtyard pairs are retained; any other warning,
error, missing report field, excluded/ignored check, open or parity finding
fails the build. The reviewed project/rule-file hashes are pinned. ERC, schematic
netlist audit, all 299 package pins/99 values and MPNs, and 51 locked critical
route items are checked on the staged design.

The package contains two copper layers, front/back mask, front/back paste,
front/back silkscreen, Edge.Cuts, separate PTH/NPTH drills, drill maps, assembly
PDFs (front and mirrored back), BOM, current audit reports and a self-contained KiCad source snapshot.
Checks validate the X2 layer identities, exact 20 × 107 mm outline and four
thermal slots, absence of zone fill across the thermal gap, and every emitted
drill hit/slot against KiCad's actual board inventory. Positions match one-to-one
within half the 0.001 mm metric-decimal export quantum. Tool diameters use
the same quantum; plating and multiplicity must match exactly. Rev B has no J5 ring lands or plated ring slots. Paste is emitted from the
remaining footprint apertures. The retired J5/F3 branch is preserved as optional
Rev C work in [the scope record](REVB-SCOPE.md).

Successful packages live in immutable `fab/o2-probe-rev-b-<ZIP-hash>/` directories.
`fab/rev-b-latest.json` identifies the newest successful package. Failed builds
exit nonzero and retain their staging logs; they do not update that pointer.
Every packaged file is checksummed, and every ZIP member is read back and checked.
`fab-manifest.json` fingerprints input and derivation scripts, libraries, rules,
board, command results and elapsed time. Rebuilds have the same normalized board;
fresh IDs, timestamps, logs and ZIP bytes are intentionally not byte-identical.

## Open release gates

The manifest explicitly says `order_ready: false`. This is a reproducible CAD
review artifact, not authorization to order boards or assemble a production run.
Main-board heater/input-protection qualification and exact procurement
decisions remain open. J5 and the external ring belong to optional Rev C. The BOM audit runs on the generated netlist
and records its real PASS/FAIL and procurement errors. A failed BOM never becomes
a clean parts basket merely because the geometry/export checks passed.

Use [REVB-ASSEMBLY.md](REVB-ASSEMBLY.md) for the individual manual-assembly
dispositions. Physical fit, wire dressing, cell compliance, leakage, ESD and
thermal behavior must be qualified separately. Prior Rev A manufacturing notes
are not copied into this package because their four-layer/castellation details
do not describe this board.
