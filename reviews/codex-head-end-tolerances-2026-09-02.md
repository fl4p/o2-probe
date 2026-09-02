# Codex xhigh review — head-end O-ring/tolerance/gates (2026-09-02)

Source: `codex exec -s workspace-write -c model_reasoning_effort=xhigh`, brief in scratchpad/codex2.txt.
Targets: squeeze-points algebra, whole O-ring chain, whether the declared tolerances need a machinist, the cavity clip, staggered epsilons, six screws, brief consistency, free hunt.

## FINDINGS

1. **(c) The ≤5.0 cm³ requirement is still not gated on the measured mesh.**

   The only volume assertion is the analytic `cav_net` check at `compostlab/o2-probe/cad/o2_probe_head_end.scad:351` (o2_probe_head_end.scad:351). The Makefile checks CGAL solid counts but never computes STL volume: `compostlab/o2-probe/cad/Makefile:83` (Makefile:83).

   Concrete counterexample: `cell_axial_len=14.0` reports 4.85162 cm³ analytically, passes every assertion, renders one closed solid, but its cavity STL measures **5022.171 mm³**. This directly violates the stated rule that the measured mesh is the gate.

2. **(c) The membrane dry-face spacing is 0.75 mm under the file’s own diffusion-resistance definition, not ≤0.25 mm.**

   `gasket_gap = 1.0 × (1−0.25) = 0.75 mm` at `compostlab/o2-probe/cad/membrane_cartridge_common.scad:46` (membrane_cartridge_common.scad:46). The flare ends at the pocket floor while the membrane dry face is one compressed gasket thickness above it. The assert checks only `straight_web=0`: `compostlab/o2-probe/cad/membrane_cartridge_common.scad:29` (membrane_cartridge_common.scad:29), `compostlab/o2-probe/cad/membrane_cartridge_common.scad:52` (membrane_cartridge_common.scad:52).

   Thus the Ø16 gasket aperture is a 0.75 mm straight channel—the exact series-resistance geometry the comments say must be limited. The assert passes while the stated 0.25 mm constraint fails by 3×.

3. **(c) The O-ring tolerance chain omits larger first-order contributors than the default ±0.05 mm machining stack.**

   The calculations at `compostlab/o2-probe/cad/o2_probe_head_end.scad:204` (o2_probe_head_end.scad:204) and `compostlab/o2-probe/cad/o2_probe_head_end.scad:278` (o2_probe_head_end.scad:278) include bore diameter and groove-root diameter only. They omit:

   - O-ring cord and ID tolerances;
   - groove-width tolerance;
   - bore/groove roundness, runout, and coaxiality;
   - spigot-OD tolerance and carrier eccentricity;
   - thermal expansion, chemical swell, compression set, and hot plastic creep.

   The nominal 0.30 mm diametral spigot clearance at `compostlab/o2-probe/cad/o2_probe_head_end.scad:128` (o2_probe_head_end.scad:128) permits 0.15 mm eccentricity unless the O-ring reliably self-centres the carrier. At that eccentricity, nominal squeeze varies locally from approximately **12.1% to 32.6%**, already outside both asserted limits. Self-centring before the flange is locked is an unstated assumption.

   Even using only the declared ±0.05 dimensions, proper volumetric fill rises from 77.49% nominal to **81.04%** at the minimum gland; the code continues to assert on 76.15% nominal fill. The selected O-ring’s actual dimensional tolerances remain unverified.

   Thermal scale is also non-negligible: the visually verified Röchling PP-H TDS gives a typical CTE of 120–190 µm/(m·K). A free Ø25.02 root changes by **0.177–0.281 mm** from 20 to 79 °C. The actual gland change depends on ASA expansion and constraint, which are not modelled.

4. **(c) “PP survives on the seal” does not follow; material and manufacturing process have been conflated.**

   `carrier_material=="pp"` automatically means ±0.05, while every other material automatically means ±0.20: `compostlab/o2-probe/cad/o2_probe_head_end.scad:151` (o2_probe_head_end.scad:151). Machining—not PP—produces the tighter dimension. ASA can be machined; PP can be printed.

   The conclusion flips with modest changes to the unmeasured declarations:

   - reamed well ±0.05 + printed root ±0.15: approximately 15.8–28.9%, passes;
   - printed well ±0.15 + machined root ±0.05: approximately 15.6–29.1%, passes;
   - both surfaces ±0.10: approximately 15.7–29.0%, passes;
   - the declared mixed ±0.05/±0.20 cases fail.

   Therefore a machinist is **not yet proven necessary**. The honest release criterion is a measured multi-azimuth bore/root/runout envelope, preferably with matching or finish-cutting. PP still has the welding and chemical rationale in `compostlab/o2-probe/MEMBRANE.md:328` (MEMBRANE.md:328); the seal establishes process capability, not carrier material.

5. **(a) `oring_band <= 0.15` is exact only with a fixed fitted cord; it is not strictly a necessary condition in the implemented model.**

   With bore \(B\), root \(R\), fitted cord \(c_f\), and radial gland height \(h=(B-R)/2\),

   \[
   s=1-\frac{B-R}{2c_f}.
   \]

   If \(c_f\) is fixed and `well_tol`/`carrier_tol` are diametral half-widths, the code is correct:

   - worst-case gland height varies by ±\((t_B+t_R)/2\);
   - `oring_squeeze_min/max` correctly contain the radial factor 2;
   - the full squeeze span is \((t_B+t_R)/c_f\), so `oring_band` correctly has no additional factor 2.

   But `c_f` changes with root diameter through stretch. Correct endpoints require \(c_f(R_0-t_R)\) and \(c_f(R_0+t_R)\), not one nominal denominator. Recalculation using the code’s own thinning approximation gives:

   | Bore/root tolerances | Code band | Recalculated squeeze |
   |---|---:|---:|
   | ±0.05 / ±0.05 | 6.81 points | 19.03–25.68% |
   | ±0.05 / ±0.20 | 17.03 points | 14.20–30.57% |
   | ±0.20 / ±0.05 | 17.03 points | 13.93–30.79% |
   | ±0.20 / ±0.20 | 27.25 points | 9.11–35.70% |

   So all four pass/fail classifications survive, but the claimed universal proof does not. Changing `oring_squeeze` changes the root, stretch, denominator, and band slightly.

   Linear addition is correct for guaranteed worst-case bilateral limits and arbitrary pairing. RSS would be appropriate only for characterized statistical distributions and an accepted yield; for the mixed case it gives 0.206 mm rather than 0.250 mm and reverses the simple band verdict. Measurement and matching are more honest for low-volume production.

6. **(a) The cavity clip removes 11.142 mm³, not the stated 3.8 mm³, and the two volume models contain cancelling errors.**

   `cavity_raw()` independently measures **4822.2235 mm³**, bbox top 38.49 mm. The clipped STL is **4811.0812 mm³**, bbox top 38.45 mm, so the clip removes **11.1423 mm³**. The 3.8 mm³ claim at `compostlab/o2-probe/cad/o2_probe_head_end.scad:502` (o2_probe_head_end.scad:502) counts only the extra Ø16×0.02 flare overshoot; it omits the Ø21.3×0.02 pocket overshoot.

   More importantly, `cavity()` unions the entire coupon-pocket cutter at `compostlab/o2-probe/cad/o2_probe_head_end.scad:520` (o2_probe_head_end.scad:520), including space occupied by the gasket and membrane. Subtracting the modelled gasket and membrane removes **171.196 mm³**.

   Meanwhile `core_gas` uses `mouth_d=22` as the flare endpoint at `compostlab/o2-probe/cad/o2_probe_head_end.scad:243` (o2_probe_head_end.scad:243), although the built flare starts at `inner_d=18`; it also omits the 0.75 mm gasket-window channel. Those errors nearly cancel, explaining why `cav_net=4640.376` happens to lie within 0.5 mm³ of the gasket/membrane-subtracted model. That agreement is not validation.

7. **(a) The staggered lower flare edit moves the carrier surface.**

   The upper extension does stay above `cart_t=5`. The lower change does not remain local to material already removed by the mouth: moving the Ø18 hull cylinder from z=1.00…1.02 to z=0.98…1.00 also moves the hull’s sloping boundary throughout z=1.00…4.07. Maximum radial shift is about **0.0065 mm**.

   Committed carrier evidence:

   - before: 5600.662434 mm³, canonical `3a953d287e4d8ace398e98c8da0592c00ff9e9137395b5f9c17e9d590bf707f1`;
   - after: 5600.868506 mm³, canonical `a81c4082a016ea5a5eb99d814cf50bb70cb8448baa0681b29fa5bbe066621a15`.

   Bbox is unchanged, but volume rises 0.206072 mm³ and the canonical geometry differs. “No surface moved” at `compostlab/o2-probe/cad/membrane_cartridge_common.scad:109` (membrane_cartridge_common.scad:109) is false. The change is tiny and benign, but real.

8. **(c) The same coincident-plane defect remains, and the claimed shared bench geometry is not actually shared.**

   The untouched rectangular module still ends both pocket and flare at `cart_t+eps` and meets mouth/flare at `heater_shelf_t`: `compostlab/o2-probe/cad/membrane_cartridge_common.scad:72` (membrane_cartridge_common.scad:72). The head/cavity bore and neck also meet exactly at z=16: `compostlab/o2-probe/cad/o2_probe_head_end.scad:411` (o2_probe_head_end.scad:411), `compostlab/o2-probe/cad/o2_probe_head_end.scad:515` (o2_probe_head_end.scad:515).

   Worse, despite the “shared part” claim in `compostlab/o2-probe/cad/README.md:52` (cad/README.md:52), `membrane_fixture.scad` neither imports nor calls `cartridge_core_cuts()`. It contains a duplicated implementation at `compostlab/o2-probe/cad/membrane_fixture.scad:226` (membrane_fixture.scad:226), including the same coincidences. The bench-to-probe transfer geometry can therefore drift.

9. **(c) Six screws are dimensionally free, but sufficiency is completely unverified.**

   No assert relates `bolt_n`, gasket stiffness/preload, plate modulus, or permissible retainer deflection. A pathological `bolt_n=1, retainer_t=0.1` still passes every assert and renders `Volumes: 2`. The only “dishing” check applies to the 5 mm carrier flange, not the 3 mm ASA retainer: `compostlab/o2-probe/cad/o2_probe_head_end.scad:341` (o2_probe_head_end.scad:341).

   Six improves angular pitch from 90° to 60°, but comparing a 16.9 mm bolt-circle arc with a 21 mm gasket diameter at `compostlab/o2-probe/cad/o2_probe_head_end.scad:161` (o2_probe_head_end.scad:161) is not a stiffness or sealing criterion. Without gasket compression-force data, six cannot be called sufficient.

10. **(c) The blind cap-screw gate checks the wrong bore and can pass a real leak.**

    The radial cap holes overlap the axial range where the Ø27.3 well begins, but the assert compares their depth only with the smaller Ø16.4 neck: `compostlab/o2-probe/cad/o2_probe_head_end.scad:339` (o2_probe_head_end.scad:339), versus the actual cuts at `compostlab/o2-probe/cad/o2_probe_head_end.scad:437` (o2_probe_head_end.scad:437).

    `cap_screw_depth=8.0` passes every assertion and renders one closed solid, yet the radial hole intersects the well between z≈29 and 29.5, creating an outside-to-gas path. The hand-built cavity mesh remains unchanged and would not reveal it.

11. **(c) The insert route currently has one solid per part, but the Makefile does not gate that property.**

    The default loop parses `Volumes`; the insert loop merely tests process exit status and discards all output: `compostlab/o2-probe/cad/Makefile:98` (Makefile:98). A valid multi-body insert render would return success. My explicit insert renders all reported `Volumes: 2`, so current geometry survives, but the regression gate does not.

12. **(a) Documentation and sourcing quantities are materially stale.**

    - `compostlab/o2-probe/MEMBRANE.md:630` (MEMBRANE.md:630) still says four screws; `compostlab/o2-probe/MEMBRANE.md:641` (MEMBRANE.md:641) says the default returns the head to Ø40; and `compostlab/o2-probe/MEMBRANE.md:652` (MEMBRANE.md:652) quotes Ø24.9, 3.75%, and 18.5%. Current values are six screws, Ø42, Ø25.02, 4.25%, and 22.35%.
    - `compostlab/o2-probe/cad/README.md:266` (cad/README.md:266) describes the former printed-well-only tolerance calculation, and `compostlab/o2-probe/cad/README.md:279` (cad/README.md:279) still specifies four inserts and the invalid ≈6 N load basis.
    - The sourcing brief correctly says six at `tech/PROBE-SCREW-SOURCING-BRIEF.md:55` (PROBE-SCREW-SOURCING-BRIEF.md:55), but calls them “these four screws” at line 75 and retains “4 off” in the insert-route heading at `tech/PROBE-SCREW-SOURCING-BRIEF.md:105` (PROBE-SCREW-SOURCING-BRIEF.md:105).

13. **(b) The handbook limits are unsourced within the reviewed evidence and are being treated too categorically.**

    The code asserts that below 15% “this leaks,” above 30% causes compression set, and above 85% necessarily leaves nowhere for the ring: `compostlab/o2-probe/cad/o2_probe_head_end.scad:273` (o2_probe_head_end.scad:273). Those are recognizable screening rules, but their applicability to this exact 1.5 mm EPDM static male gland, low gas pressure, hot condensate, surface finish, and years-long service is `unverified`.

    Independently of the precise authoritative limits, their implementation is not release-grade because stretch and fill are checked only nominally. Nominal 4.25% stretch is already close to a 5% ceiling; the declared machined root maximum gives 4.46%, and a printed ±0.20 root gives 5.08% while the nominal stretch assert still passes.

## SURVIVED

1. The default cavity STL independently measures **4811.0812 mm³**, canonical SHA-256 `cfd5af8aa1e38c4bd0d79ab2745aa3080288c215412af2a274981cfea51fd231`, bbox `[-11.9403,-11.9403,14]…[11.9403,11.9403,38.45]`. Margin to the specified mesh gate is **188.9188 mm³ = 0.188919 cm³ = 3.778%**.

2. The clip plane itself is correct: the physical carrier ends at `end_z+flange_t=38.45`, and no intended connected void lies above it. The membrane dry face is lower still, at 38.27. The clip removes modelling overshoot only; it does not remove a current nominal leak path.

3. The nominal O-ring geometry is built as declared: well Ø27.3, groove root Ø25.02, groove width 1.95, and gland height 1.14 mm. The STL groove root is Ø25.02 over z=1.75…3.70.

4. `cord × (1−stretch/2)` is a defensible first-order incompressible-thinning approximation. At 4.25% stretch it gives 1.46813 mm; simple exact area conservation gives about 1.46910 mm. Using the thinned cord in the squeeze denominator is correct and does not double-count thinning. It changes the nominal 24% construction target to about 22.35–22.54% actual squeeze.

5. The fill denominator uses the correct radial gland height from groove root to mating bore, not the 0.99 mm machined groove depth from the spigot OD. A full torus-volume calculation gives 77.49% rather than 76.15%; both nominal results are below 85%.

6. Worst-case bore and root tolerances add linearly if they are guaranteed diametral limits and arbitrary parts must mate. The diametral/radial factor of two is correct in both endpoint equations and the fixed-cord full-band equation.

7. The upper epsilon extension is wholly above `cart_t` and therefore does not move the carrier. The retainer is exactly unchanged across 7cd84f3: volume 2886.092074 mm³ and canonical hash `67b7b9b169d572fa3d51b51c491a6b81fce0b880147b2a30c47a618e6d435b9f`.

8. Four-to-six screws does not change `head_od`, flange dimensions, cap, or cavity. Four- and six-screw cavity and cap STLs have identical canonical hashes. Current minimum adjacent material is ample: 14.05 mm between head pilot edges and 13.35 mm between flange/retainer clearance-hole edges. The flange leaves 2.0 mm outside the holes and 1.25 mm between their inner edge and the spigot. The extra holes are vertical in the stated print orientations, so they introduce no new bridging.

9. The pilot cancellation is correct:

   \[
   bolt_r=\frac{well_d}{2}+\frac{2\,pt_{nominal}-p}{2}+\frac p2
         =\frac{well_d}{2}+pt_{nominal}=16.15.
   \]

   The `ceil` expression produces Ø42 for every `pt_pilot_d` from 1.95 through 3.90 mm inclusive. At 3.91 it becomes Ø44. Values above 3.0 are rejected separately by the wall assert, but the sourcing brief’s head-diameter algebra survives.

10. The sourcing brief’s substantive gasket correction survives: the retainer screws preload the membrane-perimeter gasket, not the radial carrier seal, and required gasket preload remains unknown: `tech/PROBE-SCREW-SOURCING-BRIEF.md:70` (PROBE-SCREW-SOURCING-BRIEF.md:70). Its PP-carrier wording is correct for the current default production route, though not for the new ASA switch.

11. The exact identity/tautological asserts are:

    - bore clearance, because `bore_d=max(...)`: `compostlab/o2-probe/cad/o2_probe_head_end.scad:266` (o2_probe_head_end.scad:266);
    - spigot length, because it is assigned exactly to the RHS: `compostlab/o2-probe/cad/o2_probe_head_end.scad:269` (o2_probe_head_end.scad:269);
    - fastener-to-well wall, because of the `bolt_r` definition: `compostlab/o2-probe/cad/o2_probe_head_end.scad:324` (o2_probe_head_end.scad:324);
    - bolt-circle flange coverage, because `flange_d=max(..., same expression + 4)`: `compostlab/o2-probe/cad/o2_probe_head_end.scad:331` (o2_probe_head_end.scad:331);
    - `flange_t==cart_t`, because it is directly assigned that way: `compostlab/o2-probe/cad/o2_probe_head_end.scad:341` (o2_probe_head_end.scad:341).

    They can fail only through command-line override or invalid numeric input; they do not independently validate derived geometry.
