## FINDINGS

1. **(c) Blocker — the carrier’s O-ring groove and lead-in chamfer are inverted cuts. The modeled cavity is at least 5.549 cm³, not 4.818 cm³, and the radial seal cannot be assembled as drawn.**

   Both features subtract centered solids:

   - The “groove” subtracts a Ø24.9 cylinder from a spigot already bored Ø18. It therefore enlarges the *gas bore* to Ø24.9 over 1.95 mm instead of cutting an external circumferential groove.
   - The “lead-in chamfer” subtracts a Ø25→Ø27 cone from the center. It enlarges the gas opening and leaves an annular skirt whose wall tapers to zero at `z=1.0`.

   [cad/o2_probe_head_end.scad:364–371](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:364)

   This diagnoses the non-manifold output: both the parent and current carrier meshes have exactly 96 four-incidence edges at `z=1.0`, radius 13.5 mm. The lower skirt and main spigot meet only on that zero-thickness ring. It is not a benign CGAL coplanar-face artifact and can slice as two bodies with no positive-area bond. `plate` merely inherits the invalid carrier.

   More seriously, `cavity()` models only the intended Ø18 spigot bore and therefore omits both accidental internal volumes. [cad/o2_probe_head_end.scad:391–407](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:391)

   A valid closed mesh reconstructed from the exported cavity plus the two actual connected cutter volumes measured:

   - Exported gate: `4.818409 cm³`
   - Internal “groove” addition: `0.453024 cm³`
   - Internal “chamfer” addition: `0.277315 cm³`
   - Actual modeled connected void: **`5.548747 cm³`**, 10.97% over the 5.0 cm³ limit.

   The same mistake also means there is no external O-ring groove. The drawn O-ring intersects the spigot material rather than occupying a seat, so the claimed radial carrier/head seal is physically unrealizable. This defect predates `0ebb5bf`, but it invalidates the commit’s unchanged-volume and closed-cavity evidence.

2. **(c) The retainer screws carry membrane-seal preload under the modeled Rev-A compression construction; “not a seal load” and “worst case ≈6 N” are not valid bounds.**

   The common core defines a 1.0 mm gasket compressed by 25%, makes the pocket depth equal to membrane thickness plus the 0.75 mm compressed gasket, and cuts that pocket into the carrier’s wet face. [cad/membrane_cartridge_common.scad:25–27](../../compostlab/o2-probe/cad/membrane_cartridge_common.scad:25), [cad/membrane_cartridge_common.scad:46–47](../../compostlab/o2-probe/cad/membrane_cartridge_common.scad:46), [cad/membrane_cartridge_common.scad:97–112](../../compostlab/o2-probe/cad/membrane_cartridge_common.scad:97)

   The retainer lies directly over that pocket, so its screws establish gasket compression. [cad/o2_probe_head_end.scad:382–388](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:382) `MEMBRANE.md` also says Rev-A starts with compression coupons. [MEMBRANE.md:328–351](../../compostlab/o2-probe/MEMBRANE.md:328)

   The radial O-ring removes screw preload only from the *carrier-to-head* seal; it does not remove preload from the membrane-perimeter gasket. The ≈6 N appears to be only pressure force: 265 mbar across a Ø16 window is 5.33 N, while 370 mbar is 7.44 N. Neither includes gasket compression. Required preload is **unverified** because gasket material, hardness, compression force and minimum residual load are absent.

   A fully fused membrane with no gasket could make the no-seal-load claim true, but that is inconsistent with the current shared-core geometry and Rev-A compression instruction. The sourcing brief currently assumes the low-load interpretation without resolving this contradiction. [PROBE-SCREW-SOURCING-BRIEF.md:56–63](../../tech/PROBE-SCREW-SOURCING-BRIEF.md:56)

3. **(a) The head-side sealing-wall arithmetic uses `spigot_d`, but the actual sealing bore is the larger `well_d`; both quoted wall margins are overstated by 0.15 mm.**

   `well_d = spigot_d + carrier_fit = 27.3 mm`, but `bolt_r` and the wall assertion reference Ø27.0 `spigot_d`. [cad/o2_probe_head_end.scad:169–171](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:169), [cad/o2_probe_head_end.scad:189](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:189)

   Actual minimum head material to the well is:

   - PT route: `16 − 2.1/2 − 27.3/2 = 1.30 mm`, not 1.45 mm.
   - Insert bore: `17.795 − 3.99/2 − 27.3/2 = 2.15 mm`, not 2.30 mm.
   - Insert counterbore: `17.795 − 5.84/2 − 27.3/2 = 1.225 mm`.

   The existing wall assertion is an identity because substituting the definition of `bolt_r` makes its left side exactly `fast_seal_wall`; it cannot detect this error. [cad/o2_probe_head_end.scad:244–248](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:244)

4. **(c) The insert counterbore has no geometric guard. An input change can break it into the well while every assertion passes.**

   The new assertion correctly checks the actual Ø2.8 carrier hole, but it does not cover the insert counterbore, whose actual cut diameter is `insert_head_d + 0.3 = 5.84 mm`. [cad/o2_probe_head_end.scad:253–256](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:253), [cad/o2_probe_head_end.scad:335–346](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:335)

   For example, overriding the sourced input to `insert_head_d=8.0` makes the counterbore Ø8.3 and its inner edge `17.795 − 4.15 = 13.645 mm`, inside the Ø27.3 well radius of 13.650 mm. OpenSCAD rendered it with every assertion passing. Likewise, reducing `insert_seal_wall` to 1.0 passes but moves the existing Ø5.84 counterbore into the well.

   Current Ø5.84 geometry does not intersect the well, flare or cavity, but its 1.225 mm radial ligament is neither asserted nor the claimed 2.3 mm.

5. **(b) The insert branch happens to clear at current values, but the normal build never exercises it.**

   `make head-end-provisional` does not override or iterate `fastening`, so every exported part uses the default PT route. [cad/Makefile:73–86](../../compostlab/o2-probe/cad/Makefile:73) The variant selector also treats every value other than the exact string `"insert"` as PT rather than rejecting invalid input. [cad/o2_probe_head_end.scad:48](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:48), [cad/o2_probe_head_end.scad:182–187](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:182)

   The manually rendered current insert route is clear, but that result depends on an unautomated invocation and therefore fails the checklist’s precondition coverage for future changes.

6. **(a) The sourcing brief contains two pilot-hole arithmetic errors.**

   First, `2.1 / 2.5 = 0.84`, not `0.75`; 0.75 × 2.5 would be 1.875 mm. Both CAD and brief attach the wrong rationale to the placeholder. [cad/o2_probe_head_end.scad:69–77](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:69), [PROBE-SCREW-SOURCING-BRIEF.md:22–26](../../tech/PROBE-SCREW-SOURCING-BRIEF.md:22)

   Second, the brief says a different pilot moves both `bolt_r` and `head_od`. Algebraically:

   `bolt_r = spigot_d/2 + (2N−p)/2 + p/2 = spigot_d/2 + N`

   so the pilot cancels exactly. Changing `pt_pilot_d` from 2.10 to 2.25 left the bolt circle at Ø32; it changed the rounded head diameter from Ø40 to Ø42. [cad/o2_probe_head_end.scad:77](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:77), [cad/o2_probe_head_end.scad:189–197](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:189)

7. **(c) The screw brief lacks enough information to select lengths and omits the retained insert-route machine screw.**

   For the retainer screw, the CAD gives:

   `under-head length = 3.0 + 5.0 + required engagement = 8.0 + E`

   The 8.0 mm blind pilot means the geometrically available range is `8 < L < 16 mm`; a 16 mm screw using the full nominal depth would bottom unless extra point/bottom allowance were added. The exact `E`, thread-forming lead length, bottom clearance and installation torque are not requested, so actual required length remains **unverified**. The 8 mm stack plus 8 mm hole is physically satisfiable; the defect is missing selection criteria, not an impossible stack. [PROBE-SCREW-SOURCING-BRIEF.md:58–63](../../tech/PROBE-SCREW-SOURCING-BRIEF.md:58), [PROBE-SCREW-SOURCING-BRIEF.md:96–104](../../tech/PROBE-SCREW-SOURCING-BRIEF.md:96)

   For the cap screw, the brief gives only the 4.0 mm head pilot and omits the 2.5 mm cap wall/grip, so its length cannot be calculated from the brief. [cad/o2_probe_head_end.scad:155–160](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:155), [cad/o2_probe_head_end.scad:430–438](../../compostlab/o2-probe/cad/o2_probe_head_end.scad:430), [PROBE-SCREW-SOURCING-BRIEF.md:72–84](../../tech/PROBE-SCREW-SOURCING-BRIEF.md:72)

   Finally, `fastening="insert"` still needs an M2.5 machine screw through the same 8 mm stack, but the brief specifies only thread-forming screws into printed ASA. The prior sourcing pass identified the insert, not its mating screw. Also, Ø2.8 clearance must be confirmed against the screw’s shank/major diameter and printed-hole tolerance; “against the head profile” is the wrong interface. [PROBE-SCREW-SOURCING-BRIEF.md:86–88](../../tech/PROBE-SCREW-SOURCING-BRIEF.md:86)

## SURVIVED

- The newly added Ø2.8 carrier holes themselves are correctly positioned at current derived values:

  | Route | `bolt_r` | Hole inner edge | Gap to Ø27 spigot | Gap to Ø22 flare mouth | Outer flange wall |
  |---|---:|---:|---:|---:|---:|
  | PT | 16.000 | 14.600 | 1.100 | 3.600 | 2.000 |
  | Insert | 17.795 | 16.395 | 2.895 | 5.395 | 2.000 |

  The coupon pocket and window are smaller still. The O-ring groove ends 0.75 mm below the flange; the hole cutter begins 0.02 mm below the flange, leaving 0.73 mm axial separation.

- An explicit known-bad calibration works: `pt_nominal=1.0` with Ø2.8 moves the inner edge to 13.1 mm and the new assertion fails. `m25_clear=5.1` also fails. Therefore the new assertion is not a mute button. In the PT branch it reduces to `pt_nominal >= m25_clear/2`; unlike the older wall and flange assertions, that relation is not guaranteed by the derivation.

- `m25_clear` is the right diameter for the new carrier hole and the retainer hole. The PT head pilot correctly uses `pt_pilot_d`; the insert head bore uses `insert_bore_d`. The missing diameter is specifically the larger insert counterbore guard.

- Off-flange drift cannot occur through normal derived inputs: `flange_d` is always at least `2*bolt_r + m25_clear + 4`, giving 2.0 mm radial material. The existing off-edge assertion is redundant but the geometry holds.

- Ignoring the malformed O-ring/chamfer defect, neither current fastening variant has a direct screw-hole-to-cavity intersection. The PT pilot is blind and 1.30 mm outside the well; the insert bore is 2.15 mm outside it, and the current counterbore is 1.225 mm outside it.

- The exported `cavity` meshes from the parent, current commit, PT route and insert route have identical normalized facets and all measure `4.818409 cm³`. Thus the narrow claim that the *new four clearance cuts* add no volume survives. What fails is using that incomplete cavity module as the physical volume gate.

- The new assertion fails closed on undefined `m25_clear`, is monotone as clearance worsens, is top-level and therefore invoked on rendered parts, and uses the same `bolt_r`, `m25_clear` and `spigot_d` as the carrier cut. Its scope is nominal CAD intersection only; the file correctly labels Ø2.8 as unsourced.

- The brief’s quoted 3.0, 5.0, 8.0, 4.0, Ø32, Ø40, Ø2.8 and 2.1 values match the current provisional CAD. Ø32 and Ø40 are derived current results, not invariants. The only numerical rationale that fails is “2.1 = 0.75 × nominal.”

- Both default screw positions thread into printed ASA: the retainer’s axial pilot and the cap’s radial pilot are both cut in `head()`. The insert variant is the stated exception.

- The previous carrier sourcing pass covered the insert, O-ring and PP rod, not screws; the new brief does not duplicate an already-completed screw selection.

- The membrane dry-side straight web remains `0.0 mm`, satisfying the ≤0.25 mm constraint. [cad/membrane_cartridge_common.scad:29–35](../../compostlab/o2-probe/cad/membrane_cartridge_common.scad:29), [cad/membrane_cartridge_common.scad:52–53](../../compostlab/o2-probe/cad/membrane_cartridge_common.scad:52)
