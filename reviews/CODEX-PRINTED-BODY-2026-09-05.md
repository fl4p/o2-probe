# Codex adversarial review — printed body, prototype 1

**2026-09-05.** Range `fd50a98..4a25bd2` (six commits): the printed ASA body tube,
the bayonet cable cap, the monolithic head+tube, the radial cable seal, the lock
screw, and the KiCad board-mesh clearance check.

## How this run was set up, and what was actually available

Launched detached (`codex exec -s workspace-write`, own PGID) with
`sandbox_workspace_write.network_access=true` and a headed Chrome on a scratch
profile at 127.0.0.1:9334 for it to attach to over CDP.

**The browser did not connect and the reviewer said so rather than pretending.**
Verified independently rather than taken on trust: Chrome's `/json/list` shows it
never left `about:blank`, so nothing was fetched through it. Its NETWORK did
work — the Serper search returned a live ISO 286 source. So exactly one claim in
this review is void, the `o-ring-stocks.eu` title, and the reviewer marked that
one `unverified` itself. Everything else was reached inside the repository and
stands on its own.

The MCP server never started; cause not chased. If this is re-run, check that
`npx -y @playwright/mcp@latest` comes up before trusting a browser rung.

---

## ACCESS

- **o-ring-stocks.eu `<title>`: unverified.** The browser connection reported no available browser, including after its recovery check. I did not substitute an offline guess.
- **Live search result:** Google via Serper returned Engineers Edge, “[ISO Tolerances For Bolt Fastener and Holes Table Chart ISO 286](https://www.engineersedge.com/iso_tolerance.htm),” naming a source for the 18–30 mm ISO 286 H7 band.
- Repository inspection remained read-only; the pre-existing out-of-scope working-tree changes are unchanged.

## FINDINGS

1. **(a) The stated 24.33% squeeze is the unthinned value.** The radial-gland relation itself is correct: gland depth is `(bore − root)/2`, hence `root = bore − 2·cord·(1−squeeze)`. It must, however, use the fitted cord. The committed numbers give root `25.0299 mm`, stretch `(25.0299−24)/24 = 4.291%`, and material under the root `(25.0299−20)/2 = 2.515 mm`; those three survive. Constant-volume thinning gives `d_fitted = 1.5/√1.0429125 = 1.4688 mm`, making squeeze **22.72%** at the H7 lower limit, **22.37%** at mid-band, and **22.01%** at the upper limit—not 24.33%. The head already applies essentially this correction; the body does not. Consequence: nominal squeeze is overstated by about 1.6–2.3 points. `cad/o2_probe_body_tube.scad:342`, `cad/o2_probe_head_end.scad:465`

2. **(a) The cable-seal tolerance budget does not reproduce.** The transferred sensitivity is not universal, but happens to be close because both seals use nearly the same fitted 1.5 mm cord: this gland gives **68.13 squeeze-points/mm**. A printed-bore `±0.20 mm` alone costs **13.63 points**, not 19.75; **19.76** is the combined printed-bore `±0.20` plus printed-root `±0.09` term. The H7 bore alone correctly costs about **0.72**. With H7, root `±0.09`, cord `±0.08`, and the head’s linear thinning convention, the full span is **15.14 points**, not 12.18. Exact constant-volume thinning gives 14.89 points if ring-ID tolerance is omitted, but **15.70 points** when the catalogue ID tolerance is included: approximately **14.08–29.78%**, breaching the 15% floor. Consequence: catalogue rings plus an unmeasured printed cap do not close the claimed 15-point window. `cad/PRINTING-BODY-TUBE.md:242`, `cad/o2_probe_head_end.scad:594`

3. **(c) The printed cap’s sealing root has neither qualified process capability nor shrink compensation.** The premise that `±0.09` came from machined PP is incorrect—it came from printed ASA carriers—but that still does not qualify this cap: those carriers used 0.95 flow, 0.20 mm layers and 0.45 mm lines, whereas the cap prescription is 1.00–1.02 flow, 0.10–0.15 mm layers and 0.60 mm lines. The head compensates the measured `−1.06%` root bias; the cap emits `groove_root` directly. If that measured bias repeated, the root would print near **24.765 mm** and nominal mid-H7 squeeze would fall to about **13.8%**. The printed root is also one of the two sealing surfaces, yet only the bore is finish-machined. Consequence: leakage is plausible even with a dimensionally correct reamed bore. `cad/o2_probe_head_end.scad:437`, `cad/PRINTING-BODY-TUBE.md:142`, `cad/o2_probe_body_tube.scad:613`

4. **(c) The assembly procedure still instructs installation of the obsolete face seal.** It says “O-ring on the tube end face” and that lug drop confirms squeeze; the ring now belongs in the cap-spigot groove, and a lug can drop with the radial ring absent or ineffective. The same section still describes the ring as the bayonet’s axial spring, contradicting the later correct statement that it provides no axial preload. Consequence: following the committed procedure can produce an apparently locked but completely unsealed probe. `cad/PRINTING-BODY-TUBE.md:186`, `cad/PRINTING-BODY-TUBE.md:202`, `cad/PRINTING-BODY-TUBE.md:253`

5. **(c) The bayonet gate can pass defects between samples and imposes no usable-window width.** Discovery samples every 3°, twist travel every 2°, and axial entry at only six depths. A sub-2° obstruction between twist samples passes; conversely, a single sampled clear angle is accepted as a lock window even if its real width is effectively unassemblable. `TOUCH=10⁻³ mm³` is defensible against the documented `10⁻¹³ mm³` coincident-face noise. `BLOCK=1 mm³` is conservative for detecting a collision but has no demonstrated relationship to mechanical retention—a paper-thin tongue exceeding 1 mm³ qualifies. Consequence: the test proves selected ideal-mesh poses, not continuous kinematics or strength. `cad/tools/bayonet_check.py:117`, `cad/tools/bayonet_check.py:203`, `cad/tools/bayonet_check.py:235`

6. **(c) The pilot “solid floor” test explicitly permits a leak-sized through-channel.** Its expected rod is Ø2.4 × 2.8 mm, volume **12.67 mm³**, and it passes with 90% present. A coaxial **Ø0.75 mm through-channel** removes only 1.24 mm³, leaving 90.2% and therefore passes while directly connecting compost to the bore. Pulling the good model into a collision is a useful fixture check, and deleting the entire boss is a gross negative control; neither calibrates sensitivity to a leak path. Consequence: the mesh check can certify a geometrically flooded enclosure. `cad/tools/bayonet_check.py:305`, `cad/tools/bayonet_check.py:313`

7. **(c) “Volumes: 2” proves connectivity, not positive fusion or correct placement, and the duplicated body interfaces have already drifted.** A read-only OpenSCAD control gave `Volumes: 2` for two cylinders merely sharing a face, `3` with a 0.001 mm gap, and `2` with 0.001 mm overlap. The current tube and head likewise meet at exactly one plane. `body_tube_len` remains 127 although the imported tube is 113; `socket_len − 127 = −113` only happens to align it. A longer stale tube would overlap and still pass. Separately, `body_cap_engage` remains **12 mm** after the body changed to **18 mm**, so the prototype view already places the cap 6 mm incorrectly. Consequence: the gate cannot detect one-sided interface drift, and the visual assembly check is presently false. `cad/Makefile:200`, `cad/o2_probe_head_end.scad:80`, `cad/o2_probe_head_end.scad:1216`, `cad/o2_probe_head_end.scad:1264`, `cad/o2_probe_body_tube.scad:305`

8. **(c) The 4917 mm³ gate measures a mesh of a hand-written void model, not the void of the rendered head.** The checked STL does measure **4916.6 mm³**, leaving 83.4 mm³ or 1.67%; that arithmetic survives. But `cavity_raw()` independently recreates the cutters and always starts at `socket_len`, while the monolithic `head()` opens the bore from `z=0`. The omitted Ø25.185 × 14 mm monolithic section, less the 1.6 mm board, is about **6526 mm³**; therefore the monolithic head’s connected void is roughly **11.44 cm³** before adding the tube. Consequence: the gate protects the bonded-head analytical model, not the actual monobody connected volume. `cad/Makefile:119`, `cad/o2_probe_head_end.scad:1046`, `cad/o2_probe_head_end.scad:1060`, `cad/o2_probe_head_end.scad:892`

9. **(b) The board transform and the quoted clearance numbers happen to hold for the checked committed board.** The PCB places Bourns 3224W RV1 on B.Cu at page `(102.5,123)`, hence local `(2.5,73)`, with pad extent `x=0.25…4.75`; `sqrt(9.75²+5.8²)=11.345 mm` is correct. The transform has determinant +1, maps KiCad’s negative page-y along the probe, and maps B.Cu below the board—not to the wrong face. The 22.185 mm swept diagonal, 25.185 mm head bore, guide-slot height, and dam reliefs all follow `board_t=1.6`; no residual 1.0 mm assumption remains in the changed head file. L1, U8, U12 and J101–104 are missing from the installed 3D library, but their board positions and envelopes are safely inside the bore and outside the 1 mm rail strips. `COPPER=0.15` could hide only a body wholly within 0.15 mm of a face; none of these parts is such a body. Consequence: no present board collision was found, though this does not cure the stale-mesh defect below. `/Users/fab/dev/ee/hw/o2-probe/o2-probe.kicad_pcb@HEAD:13801`, `cad/tools/board_clearance.py:47`, `cad/o2_probe_board_in_body.scad:70`

10. **(c) `board-in-body` can silently validate a stale, gitignored board mesh.** `board-mesh` exists but is not a prerequisite of `board-in-body`; that target depends only on `monobody` and then reads whatever `o2-probe-board-bin.stl` happens to exist. Neither a PCB timestamp nor a source hash is checked. The script also moves only hand-added RV1 outward for a hypothetical 1.6 mm board; every exported component remains positioned on the 0.910 mm mesh, although current margins make that harmless. Consequence: a future component or placement change can pass because the tested mesh predates it. `cad/Makefile:228`, `cad/Makefile:236`, `cad/tools/board_clearance.py:99`

11. **(c) The thermal argument cannot support rejecting insulation.** “0–4 K from 0–1 W” is a requested operating range, not a measured steady-state `Rθ=4 K/W`; the repository explicitly calls membrane coupling unmeasured. The estimated 78 K/W cylindrical radial wall is not in series with a 4 K/W system—it is one of many parallel, distributed paths through the tube, cap, cable, board, gas, membrane stack and wet compost. Even accepting both numbers, removing a 78 K/W parallel branch changes 4 K/W to approximately 4.22 K/W, **5.4%**, not 4%. The cylindrical estimate also assumes uniform isothermal cylinders, while the head is a cone plus several changing bores and local heat sources. Consequence: it says nothing reliable about membrane temperature or condensation; local thermal simulation or measurement is required before dismissing hollowing. `cad/o2_probe_body_tube.scad:12`, `cad/o2_probe_head_end.scad:316`, `cad/o2_probe_head_end.scad:871`

12. **(a) The published gas-volume numbers were not updated for the 1.6 mm board or the 4916.6 mm³ cavity.** The committed formula now gives **57.652 cm³**, not 58.9; with the measured cavity the simplified total is **62.569 cm³ = 12.514×** the budget. Its dam-side term is **13.178 cm³**, giving **18.094 cm³ = 3.619×**, not 3.66–3.7×. The echo still hardcodes the old 4840 mm³ cavity while the same document reports 4917. Consequence: the table and generated diagnostic disagree with the current geometry. `cad/o2_probe_body_tube.scad:393`, `cad/o2_probe_body_tube.scad:463`, `cad/PRINTING-BODY-TUBE.md:50`

13. **(c) More importantly, neither gas-volume formula represents the sealed assembly.** `tube_gas` uses the 105 mm board length and omits the 22 mm cable tail, despite that tail being open gas around the service loop and silica. Allowing for the cap’s Ø20 passage, the omitted tail is roughly 10.5 cm³ before cable/silica displacement. With the dam, `dam_gas` counts only the 24 mm gas-side stub; a loose split disc does not disconnect the tail, so the entire volume remains connected at equilibrium. It changes conductance and creates a multi-time-constant system, not an 18.1 cm³ sealed cavity. Consequence: the dam cannot restore the 5 cm³ response model, and its benefit requires a measured transient/leak conductance rather than a volume ratio. `cad/o2_probe_body_tube.scad:164`, `cad/o2_probe_body_tube.scad:396`, `cad/o2_probe_body_tube.scad:644`, `cad/PRINTING-BODY-TUBE.md:56`

## SURVIVED

3. No additional geometric breach was found: bayonet slots and grip scallops remain outside the radial seal, guide slots subtract only additive rails, the Ø27.3 counterbore retains 2.35 mm radial wall, the dam is openly non-sealing, the monolithic join is a single manifold mesh, and the head’s radial cap pilots stop at r=16 mm against a maximum void radius of 13.65 mm; the M12 passage is the explicitly intended—but still unsourced—gland interface.

---

## Disposition — 2026-09-05, later the same day

Every finding is answered below. Where a fix landed, the mechanism that would
have caught it is named, because several of these were things a human noticed by
eye and that is not a control.

| # | tag | disposition |
|---|---|---|
| 1 | (a) | **Fixed.** The echo now separates the two: 24.33 % is the sizing basis, 22.67 % is what the ring delivers after 4.29 % stretch thins the cord. |
| 2 | (a) | **Fixed, and the conclusion changed.** `PRINTING-BODY-TUBE.md` now states catalogue cord at **15.1–15.7 points — over budget**, sorted at ~7.5. The finding is the reason the doc says sorted rings "are not the better option, they are the only one". |
| 3 | (c) | **Fixed.** The cap's groove root is emitted with shrink compensation — `25.0299 target (CUT 25.3057, shrink 0.9891)`. The provenance error was also corrected: ±0.09 came from printed ASA carriers, not machined PP, and the doc said the wrong thing. |
| 4 | (c) | **Fixed.** Assembly steps 5–7 fit the radial ring into the cap's spigot groove and say plainly that the lug drop confirms the lock and nothing about the seal. |
| 5 | (c) | **Fixed.** Twist sweeps and window walks now run at 1°, the entry ladder samples every millimetre instead of six chosen depths, and both windows must exceed a stated usable width. The retention test no longer rests on `BLOCK`: it is weighed against the lug's own swept section, with a 0.3 mm tongue built as the known-bad and required to fail. Measured: the tongue gives 7.4 mm³ at a 2 mm pull, seven times `BLOCK`, and is not a lock. |
| 6 | (c) | **Fixed.** Threshold 0.90 → 0.97, calibrated (sound part 99.2 %, Ø0.75 channel 90.2 %), plus a coaxial thin-rod probe for channels too narrow for the main rod. |
| 7 | (c) | **Fixed.** New `tools/interface_check.py`, run from `make monobody`. It compares every number the two files duplicate — six pairs — and weighs the union against its parts, since fusion conserves volume and overlap does not. It caught a stale monobody on its first run. `body_cap_engage` and `body_tube_len` are both correct now and are no longer trusted to stay that way. |
| 8 | (c) | **Fixed** (by a parallel session, in `cavity_raw()`). Compounded by `socket_len` going 14 → 3 in the monolithic head: the monolithic cavity measures **6.31 cm³**, down from 11.9. Still over the 5.0 cm³ budget, which is a production figure — the Makefile gates the bonded variant, at 4.917. |
| 9 | (b) | No action; it survived. |
| 10 | (c) | **Fixed** for the stale-mesh half — `board-mesh` is a prerequisite of `board-in-body`. The source-hash half is **open**: nothing yet ties the exported mesh to a revision of `o2-probe.kicad_pcb`. |
| 11 | (c) | **WITHDRAWN, not fixed — the claim was never in the repository.** The argument against hollowing the head (~78 K/W radial wall against a ~4 K/W system, so insulating it changes little) was made in conversation and never committed, which is why no file cites it. It does not hold: "0–4 K from 0–1 W" is a requested operating range and not a measured Rθ, and the wall is one of many parallel distributed paths rather than a series element. Nothing in the design rests on it. **If hollowing the head is reconsidered, it needs a measurement or a local simulation, and this argument must not be reused.** |
| 12 | (a) | **Fixed.** 4.92 / 75.4 / 18.1 cm³, measured cavity, cable tail counted. |
| 13 | (c) | **Fixed.** The echo states outright that the dam is a loose split disc, that 204 mm² of a 581 mm² bore stays open, and that its worth needs a measured transient rather than a volume ratio. |

**Open after this pass:** finding 10's provenance half (bind the board mesh to a
board revision), and the two sourcing items that are not CAD — the gland's NBR
seal against hot wet ammoniacal service, and whether the cable's PUR sheath is a
hydrolysis-resistant grade.

**What this review cost and returned.** Thirteen findings, eleven of them real
enough to change code or prose, one withdrawn as an argument that should never
have been made, one clean pass. Three of the fixes are new controls rather than
new numbers, which is the part worth keeping: the pilot threshold, the retention
floor and the interface check each now fail on a deliberately built bad part.
