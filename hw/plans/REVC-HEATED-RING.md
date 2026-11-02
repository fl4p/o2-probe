# Optional Rev C heated ring — J5/F3 recovery plan

**Status: deferred, not approved.** Fab, 9 September 2026: “J5 will be in RevC
(if ever).” Rev B removes this branch and retains RH1/RH2 on the main board.
This plan preserves the idea; it is not a commitment to build it.

## Recover the complete pre-removal design

Last revision containing the reviewed branch: **`c8a5a592338edb5e29e4273032fa126c43c8c995`**, in the
`/Users/fab/dev` monorepo (PCB routing/firmware tree, not the enclosure submodule).
The routed board at that revision has SHA-256
`5d9a9c6494feb09f6400e51d1d91a478e9b74190de16a5d0963bfff5afe21781`.

From the monorepo root, recover it without replacing the current Rev B files:

```sh
git show c8a5a592338edb5e29e4273032fa126c43c8c995:ee/hw/o2-probe/gen_sch.py > /tmp/revc-ring-gen_sch.py
git show c8a5a592338edb5e29e4273032fa126c43c8c995:ee/hw/o2-probe/o2-probe.kicad_sch > /tmp/revc-ring-reference.kicad_sch
git show c8a5a592338edb5e29e4273032fa126c43c8c995:ee/hw/o2-probe/routing/revb-interfaces/o2-probe.kicad_pcb > /tmp/revc-ring-reference.kicad_pcb
```

Restore the matching `.kicad_pro`, `.kicad_dru` and local libraries from the same
revision before opening or checking a complete recovered project. Do not combine
its old netlist with the current Rev B board and call the result verified.
The older [BOM39 route](../routing/2layer-bom39/PROVENANCE.md) is also retained
unchanged, but predates the `/RE` split and CE fixes; it is not the preferred
starting point for future work.

The draft [fork footprint](../lib/o2-probe.pretty/Ring_Fork_Tip_DRAFT.kicad_mod)
remains in the library for reference. It is unused by the Rev B board.
The electrical/routing removal is explicit in
[retire_revb_ring.py](../retire_revb_ring.py), including every retired copper ID.

## What the branch did

- J5 was `RING PCB FORK TIP`: two electrical lands, each present on front and
  back copper, intended for a soldered perpendicular ring PCB.
- J5.1 was `+12V_HTR`, supplied from `+12V_SW` through F3. J5.2 was
  `HEATER_LOW`, switched by Q2; it was not ground.
- F3 was a draft 0603 series position labelled `0R FITTED`, but its own note
  said **DO NOT FIT AS DRAWN**. It had no approved protective-device MPN.
  That contradiction must not return as a manufacturing instruction.
- RH1/RH2 connect directly from `+12V_SW` to `HEATER_LOW`. The proposed ring
  was an additional parallel heater load, not a replacement for these parts.
- The retired routing comprised 13 track segments and 3 vias: the F3-only
  supply spur, all `+12V_HTR` copper, and the Q2-to-J5 low-side extension.

## Reopen only with an explicit Rev C decision

1. Define the ring's function and thermal target, then obtain actual interface
   measurements. The old fork/neck geometry is superseded (see below);
   no physical dimension is approved by this archived CAD.
2. Freeze the ring PCB/heater design, resistance range, temperature range,
   insulation, assembly joint and accessible-metal clearances. Confirm the
   membrane/cell/gas-path requirements against the current enclosure design.
3. Design and validate ring-feed fault protection at those conditions. Do not
   inherit the old 0Ω link, generic PPTC speculation or RH1/RH2 load assumptions
   as an approved ring protection choice.
4. Recheck Q2, supply/F1, wiring and total heater current for the additional load;
   review firmware/control and sensor placement if the thermal plant changes.
5. Revalidate routing, copper spreading, gas clearance, leakage and ESD, then
   qualify a physical assembly with open/short/stuck-on heater fault tests.

## Mechanical research: read its supersession notice first

The separate enclosure repository at
`/Users/fab/dev/ha/farming/compostlab/o2-probe`, commit
`6a0a7ba1a7a7a72ff33cbdd96ced9fbbd96a5361`, contains the tracked documents
`RING-PCB.md` and `HEATED-SPREADER.md` (both confirmed present on 9 September).

**RING-PCB.md's 2026-09-05 status notice explicitly invalidates the original
fork/neck geometry:** the cell returned to a standing THT mount and the former
neck was removed. Its finger envelope and “measure the printed neck bore” step
are superseded. The old schematic note had failed to carry that correction.
Recover the electrical concept and historical routing for reference; design any
Rev C ring connection against the then-current standing-cell enclosure, not by
restoring that obsolete fork. The study identifies which thermal/mounting topics
remain worth revisiting; those still require re-evaluation.

HEATED-SPREADER.md is an earlier design study and directs readers to its §0 and
the unmeasured thermal coefficient in §7. It does not authorize the old J5
geometry or supersede the later standing-cell decision.
