# Codex xhigh review #2 — tolerance chain, dry-side gate, volume gate (2026-09-02)

Run with a headless Chrome attached over CDP (port 9311, scratch profile) so the ISO/DIN claims could be checked against primary sources. 81 browser calls; iso.org and roymech reached.

## FINDINGS

1. **(c) Critical — the default catalogue route violates its own gland-fill limit.** The `compostlab/o2-probe/cad/o2_probe_head_end.scad:341` (fill gate) checks nominal fitted cord only: 76.451%. With H7 bore minimum, machined root maximum, 1.58 mm cord, and 24.25 mm ID, fill is **87.506%**. Therefore the current H7 + machined carrier + catalogue-ring configuration is not a PASS.

2. **(a) High — `oring_squeeze_min/max` are not extrema over the documented tolerance box.** They omit ID tolerance and freeze stretch thinning despite root tolerance `compostlab/o2-probe/cad/o2_probe_head_end.scad:305` (at lines 305–315). The claimed 16.14–28.54% becomes 15.38–28.52% under the stated H7 interpretation.

3. **(a) High — H7 is centered on the wrong datum.** A one-sided `+0.021/0` bore was converted to ±0.0105 without moving the CAD center from 27.300 to 27.3105 `compostlab/o2-probe/cad/o2_probe_head_end.scad:171` (at lines 171–175).

4. **(a) Medium — ID tolerance is first-order, not second-order.** The contrary claim appears in `tech/PROBE-CARRIER-SOURCING.md:177` (the sourcing document) and `compostlab/o2-probe/cad/o2_probe_head_end.scad:181` (CAD comments). Its omission costs about 0.7 squeeze point.

5. **(b) Medium — the published band formula relies on unstated tolerance conventions.** It works approximately only when `T_bore`, `T_root`, and `T_cord` are full widths and cord width has been stretch-thinned. The adjoining tables publish ± half-widths, making the formula unsafe to reuse literally.

6. **(c) Critical — the 5 cm³ gate does not establish true connected volume.** `carrier_fit=5.0`, `oring_id_ordered=28.5` builds no groove yet passes all asserts, topology gates, and the 4811.1 mm³ cavity gate. True connected volume is approximately **5805.6 mm³**.

7. **(c) High — the dry-side gate can false-pass a channel over 0.25 mm.** Its binary 0/0.75 model ignores partial intersection of the gasket bore and flare; `flare_inner=15.7` yields a real 0.261 mm restriction while reporting zero `compostlab/o2-probe/cad/membrane_cartridge_common.scad:70` (at lines 70–84).

8. **(c) Medium — the gate and built cone can use different epsilon values.** The gate retains its default `eps=0.02`, while the module accepts another `eps`; moreover, the overshoot changes the physical hull slope despite comments asserting that the rendered solid is unchanged `compostlab/o2-probe/cad/membrane_cartridge_common.scad:143` (at lines 143–155).

9. **(b) Medium — “straight_web never has geometric effect” depends on `inner_d >= window_d`.** That holds now but is neither asserted nor universal. `flare_inner=8` breaks the claim while passing all common-file asserts `compostlab/o2-probe/cad/membrane_cartridge_common.scad:56` (at lines 56–68).

10. **(c) Medium — the land gate measures the parameter, not actual sealing land.** Current effective land is exactly 2.0 mm, not 2.5 mm. Setting `land=2.0` would still pass while leaving only 1.5 mm after the fixed 1 mm bore enlargement.

11. **(c) Medium — install stretch has no lower-bound gate.** `compostlab/o2-probe/cad/o2_probe_head_end.scad:300` (The assertion) rejects only stretch above 5%; a slack, negative-stretch ring can pass.

12. **(c) High — the claimed shared bench/probe sealing source is not actually shared.** The probe includes `membrane_cartridge_common.scad`, but `membrane_fixture.scad` retains its own copied parameters and modules and never includes it. This directly contradicts `compostlab/o2-probe/cad/README.md:52` (the README transfer claim) and has already allowed the Ø17 gasket change to affect only the probe path.

13. **(c) Medium — catalogue tolerance applicability to the selected EPDM compound is release-unverified.** The vendor warns that compound shrinkage can change tolerances; no product-specific primary declaration was recovered.

14. **(a) Low — decision documents contain stale geometry.** `compostlab/o2-probe/cad/README.md:267` (README:267) says Ø25.02 and 22.35%; current values are Ø25.0299 and 22.6708%. `tech/PROBE-CARRIER-SOURCING.md:135` (PROBE-CARRIER-SOURCING.md:135) still says a 24.5 mm root and about 2% stretch; current stretch is 4.291%.

15. **(b) Low — several “gates” are derivation identities, not independent checks.** The bore-clearance assert follows directly from `max()` `compostlab/o2-probe/cad/o2_probe_head_end.scad:293` (at line 293), spigot length is assigned to its asserted minimum `compostlab/o2-probe/cad/o2_probe_head_end.scad:296` (at line 296), and flange coverage is guaranteed by the defining `max()` `compostlab/o2-probe/cad/o2_probe_head_end.scad:369` (at line 369). They are refactor tripwires, not present-geometry evidence.

## SURVIVED

- The vendor PDF really does specify **±0.08 mm** for `d2 ≤ 1.8`; only the d1 interpretation needed correction to **±0.25 mm**.
- Worst-case independent tolerances do occur at corners, and least squeeze does pair the widest gland with the thinnest cord—plus minimum ID and minimum root.
- Cord tolerance is correctly multiplied by the stretch-thinning factor when stretch is fixed; cord diameter should not itself alter root diameter or stretch.
- Linear absolute-sensitivity addition is appropriate as a first-order worst-case method for arbitrary independent pairing.
- Under the assumed tolerance boxes, current squeeze still narrowly remains within 15–30%; **gland fill**, not squeeze, invalidates the default route.
- For current `inner_d=18 > window_d=16`, `straight_web=0` and `0.25` truly produce identical geometry.
- For current `eps=0.02`, the dry-face interpolation matches the cone actually constructed and gives Ø16.1089.
- The current Ø17 gasket bore clears the complete current flare through the compressed gasket thickness; it leaves 2.0 mm land and the membrane remains geometrically clamped.
- `stlvol.py` correctly computes signed tetrahedral mesh volume, rejects empty ASCII STL input, and enforces `≤5000` using `>` as the failure condition `compostlab/o2-probe/cad/tools/stlvol.py:25` (at lines 25–55).
- The default cavity mesh is a valid closed 4811.1 mm³ solid. The present gasket omission alone is conservative, but that does not rescue the missing-seal bypass.
