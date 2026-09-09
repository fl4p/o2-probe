# Archived PCB plans and routing studies

Archived 2026-09-09 after inspecting hardware-repository HEAD `9e93c0e`.
These documents are retained unchanged as historical records. Their old
“not applied”, “board is behind”, and routing-failure statements describe the
state when written; they are not the current implementation checklist.
Bare file paths in the archived text are relative to the o2-probe project root.
Older review records retain the original filenames; the table below locates them.

| Record | Reason for archiving | Implementation / successor |
|---|---|---|
| [BOM-REDUCTION.md](BOM-REDUCTION.md) | Approved reductions implemented, with the corrections recorded in the document. Further proposed cuts were rejected or deferred. | `ae019ee`; [schematic generator](../../../gen_sch.py); reduced BOM incorporated into the [two-layer candidate](../../../routing/2layer-bom39/README.md). The 100-part count describes that candidate, before the later R45 addition. |
| [BOM-CUT-ROUTING.md](BOM-CUT-ROUTING.md) | Completed routing experiments and collision-fix record, superseded by the routed candidate. | `907ac4c`; [candidate provenance](../../../routing/2layer-bom39/PROVENANCE.md), including its later J105/J106 footprint changes. |
| [TWO-LAYER-REFLOORPLAN.md](TWO-LAYER-REFLOORPLAN.md) | Earlier floorplan brief superseded by the completed routing attempt; this does not mean every proposed floorplan change was implemented. | [Routing handoff](../../../routing/2layer-bom39/README.md) and [independent regrade](../../../routing/2layer-bom39/PROVENANCE.md), merged in `027e693`. |

## Work that is not closed by this archive

- The fixed reference, WE/RE followers, RE-driven guard and CE monitor are
  already in the HEAD schematic and two-layer candidate. Their bench
  qualification remains separate from schematic implementation.
- The later RS-485 `/RE` split is now completed in the
  [Rev B interface candidate](../../../routing/revb-interfaces/README.md),
  including R45, PC7 routing and generator placement. The original BOM39
  candidate remains unchanged as historical input.
- The new candidate resolves U6 pad 21 and stale symbol fields, and both saved
  and CLI-refilled copper have zero opens. Five inherited footprint-parity
  findings, assembly warnings, thermal verification and fabrication exports
  remain release work. See its [validation record](../../../routing/revb-interfaces/README.md)
  and [FAB-READINESS.md](../../../FAB-READINESS.md).
- CE series resistance, D7 pinout/MPN and CE routing are implemented; physical
  compliance, leakage and ESD qualification remain open. The heater interface,
  F3 and input-stage protection also remain open. See [DESIGN.md](../../../DESIGN.md) and
  [AFE decision review](../../../REVIEW-2026-09-04-AFE-DECISIONS.md).
- Unselected alternatives and sourcing questions in the BOM record are not
  approved changes: retain the VREF monitor; deleting the AZ431 requires the
  proposed noise study; capacitor MPN selection remains a sourcing task.

The AFE postmortem, power study, design record, and fabrication-readiness
record remain at the project root because they contain outstanding work.
The enclosure-side heater, coating and potting plans also remain active in
`ha/farming/compostlab/o2-probe`.
