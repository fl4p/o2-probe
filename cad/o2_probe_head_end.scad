/*
 * O2 probe — buried head, END-WINDOW variant (printed ASA)
 * Units: millimetres. Z runs from the tube joint toward the tip.
 *
 * The alternative to o2_probe_head.scad, built so the two can be compared on
 * numbers instead of argument. The gas window is on the END face, so nothing has
 * to be found in the radial budget -- which is what forces the radial variant to
 * 46 mm and 11.2 cm3.
 *
 * IT NO LONGER COMMITS A CELL ORIENTATION, and that changed on 2026-09-05. This
 * file was built around PLAN.md's option C -- cell past the board end, axis along
 * the tube, sitting in a necked bore -- and Fab returned the design to option A,
 * the cell STANDING on the board like any other THT part, gas face radial. The
 * end window is orthogonal to that choice: see cell_mount, which defaults to
 * "standing" and keeps "past-end" so the two can still be compared.
 *
 * THE SEALING STACK, compost inward (MEMBRANE.md, decision 2026-09-02):
 *
 *     debris cap          replaceable, solid front, side slots only
 *     drainage gap        no liquid pocket against the membrane
 *   --------------------  ------------------------------------------------
 *     PMV15T coupon       the barrier; WEP 265 mbar min / 370 typ
 *     PP carrier          coupon FUSED in (ultrasonic or thermal weld)
 *     O-ring (radial)     carrier-to-head seal, squeezed by the FIT
 *     ASA head            this file
 *     bonded socket       head-to-tube, continuous circumferential bond
 *
 * No adhesive is load-bearing on the wet side, which MEMBRANE.md forbids until
 * a named adhesive has passed hot-condensate ageing.
 *
 * Three jobs are deliberately separated. The O-RING seals, and its squeeze comes
 * from the interference fit, so no fastener is in the seal load path and PP
 * creep at 75 C cannot bleed it off. The RETAINER only holds the carrier down.
 * The CAP is only a debris guard, independently replaceable as MEMBRANE.md
 * requires, and its open band is sized so the guard never out-restricts the
 * membrane it protects.
 *
 * MEASURED INPUTS ARE REFUSED, NOT GUESSED.  Preview: make head-end-provisional
 */

include <membrane_cartridge_common.scad>

$fn = 96;
heps = 0.02;
view_rot = 0;               // render-only: lay the stack over for a wider image

part = "assembly";   // assembly, head, carrier, retainer, cap, cap-asm, cavity

// Retainer fastening. "vascrew" is the default and is DECIDED, not provisional:
// Fab, 2026-09-05, "VA metric screw M2" and then, choosing off the printed
// fastener coupon, "use that hole / the 3rd one". Station 3 of that coupon is a
// Ø1.60 pilot with a Ø2.10 x 1.00 counterbore, driven directly into the printed
// ASA boss by a plain A2 stainless M2 machine screw. No PT screw -- there are
// none in the building -- and no insert.
//
// Why it works here at all, when driving a 60-degree ISO flank into plastic is
// normally the thing you talk somebody out of: the radial O-ring took the seal
// load off these screws, so the worst case is ~6 N, order 0.1 MPa in the thread.
// This joint is a retainer clamp, not a pressure boundary.
//
// The insert route is KEPT, and it costs 6 mm of head diameter -- RE-MEASURED at
// M2 on 2026-09-05, because the M2 insert is a smaller part and the penalty
// looked like it should have shrunk with it. It did not: head OD 38 on vascrew
// against 44 on insert, bolt circle Ø30.2 against Ø33.93. The bore got 0.76 mm
// smaller and the wall did not, because insert_seal_wall (2.3, set by
// heat-setting next to the O-ring seat) and pt_seal_wall (1.2, the boss rule)
// are what actually separate the two routes -- not the hole.
//
// What DID change on that route is the sourcing objection: the M2.5 part was
// E-Z LOK's, a sole-source US import that every EU specialist made special-order.
// The M2 part is PEM IUTFC-M2, a catalogue item with ordinary distribution. If
// the insert is ever needed -- a boss that strips in service, a joint that starts
// carrying load -- it is no longer blocked on procurement.
fastening = "vascrew";      // "vascrew" or "insert"
assert(fastening != "ptscrew",
       str("fastening=\"ptscrew\" was renamed to \"vascrew\" on 2026-09-05. It is ",
           "not a rename for tidiness: the screw is an A2 machine screw cutting an ",
           "ISO metric thread, not a PT screw forming its own non-ISO one, and the ",
           "pilot is justified differently (see pt_pilot_d)."));
assert(fastening == "vascrew" || fastening == "insert",
       str("unknown fastening '", fastening, "'"));
exploded = false;
// Draw the prototype-1 body below the head as well: the printed ASA tube, its
// bayonet cable cap and the dam. OFF by default, because those parts belong to
// o2_probe_body_tube.scad and this file must not grow a dependency on them --
// they come in as the STLs that model already exports, positioned, never as
// geometry. Nothing here is exported; it is a drawing aid for `make
// prototype-exploded`, which is the only view that shows the whole probe.
show_body = false;

// HOW THIS HEAD MEETS THE BODY.
//   "bonded"      the production joint, and the default: a Ø(tube+0.4) socket
//                 14 mm deep, filled with adhesive. Two parts.
//   "monolithic"  prototype 1: there is no joint, because the printed body tube
//                 is the same piece of plastic. The socket goes away, the bore
//                 runs to z=0, and an outward cone carries Ø32 up to Ø40.
//
// Monolithic exists for a sourcing reason, not an aesthetic one. The bonded
// joint is structural AND sealing, on the wet side, at ~75 C in ammoniacal
// condensate -- and MEMBRANE.md forbids a load-bearing adhesive there until a
// named one has passed hot-condensate ageing. None is sourced. Printing through
// the joint deletes the requirement instead of guessing at it.
joint = "bonded";
assert(joint == "bonded" || joint == "monolithic",
       str("unknown joint '", joint, "'"));
monolithic = (joint == "monolithic");
tube_od_nominal = 32.0;     // what the printed tube is DRAWN at, not measured
body_dir = "exports";       // where those STLs live, relative to the build cwd
// Interfaces to the body model. These are the SAME two numbers that file names
// as tracking this one (head_socket_len, cap_engage); if either moves, the body
// slides in this picture and the picture is the thing that would show it.
// Both of these are DUPLICATED from o2_probe_body_tube.scad, and both had
// already drifted by 2026-09-05: cap_engage moved 12 -> 18 there when the radial
// seal pushed the lock boss past the reamer, and this file kept 12, so the
// prototype drawing placed the cap 6 mm into the tube. Nothing complained.
// tools/interface_check.py now compares them and the Makefile runs it.
//
// body_tube_len depends on the joint, because the monolithic tube stops where
// the head begins: 113 against the bonded 127. The old single value happened to
// place BOTH correctly -- socket_len - 127 = -113 = -113 -- which is exactly the
// kind of coincidence that survives until one of the two numbers moves.
// BACK TO 124.0 / 127.0. These track the head's own cav_board_len, which is now
// SOLVED (see its note) rather than chosen: the board length is fixed, so every
// millimetre of bore the head gains has to come out of the tube or the board tip
// overshoots the well floor. Both numbers moved to 121.3 / 124.3 on 2026-09-05
// while cav_board_len solved to 4.7 under an 8.0 mm screw, and moved back when
// the fastener went to M2 and it returned to its 2.0 floor. Overall probe length
// never changed. tools/interface_check.py compares these against the body model
// and caught the drift both times -- run it after ANY fastener change.
body_tube_len = monolithic ? 124.0 : 127.0;   // o2_probe_body_tube.scad, tube_len
// The tube's BORE, and it is load-bearing here rather than decorative: with the
// cell standing on the board, this is the hole the can has to go down, and the
// assert that says so lives in this file because cell_seated_h does. Ø27.2 =
// tube_od 32 - 2*wall 2.4. Duplicated, so interface_check.py compares it.
body_tube_id = 27.2;        // o2_probe_body_tube.scad, tube_id
body_cap_engage = 18.0;     // o2_probe_body_tube.scad, cap_engage
body_seal_id   = 24.0;      // o2_probe_body_tube.scad, seal_id  (ORS116787)
body_seal_cord = 1.5;       // o2_probe_body_tube.scad, seal_cord
body_groove_root = 25.0299; // o2_probe_body_tube.scad, groove_root

// ------------------------------------------------- MEASURE THESE

tube_od_meas = undef;      // MEASURE: actual OD of the tube stock, incl. ovality
board_env_front = undef;   // MEASURE: populated swept envelope above the board
board_env_back = undef;    // MEASURE: populated swept envelope below the board
cell_seated_h = undef;     // MEASURE: can top above the board plane, real cell in
                           //          a real socket. PLAN.md option A computes
                           //          8.3 (can) + 0.51 (Cambion flange) = 8.8, and
                           //          that is arithmetic on a datasheet, not a
                           //          seated part. It is also board_env_front in
                           //          the tip region, so a wrong value moves the
                           //          bore and the head OD, not just a drawing.
// cell_axial_len IS GONE, and it is not a rename. It measured "how far the cell
// and its socket project past the board END", which is a dimension that only
// exists in cell-orientation option C -- the cell lying on the probe axis beyond
// the board tip. Fab, 2026-09-05: the design is back to option A, the cell
// STANDING on the board like any other THT part, axis normal to the copper, gas
// face radial. Nothing projects past the board end any more, so the quantity is
// not zero-because-unmeasured, it is zero because the feature does not exist,
// and the 13 mm of necked bore it bought is dead volume with nothing in it.
// See cell_mount below. HANDOFF-2026-09-05.md and RING-PCB.md are the two
// documents written against option C.
// M2, not M2.5. Fab, 2026-09-05: "for the o2-probe head i want the screw holes to
// receive M2 metric screws." Only the insert route actually receives a metric
// screw -- a thread-forming screw cuts its own non-ISO thread -- so both routes
// were resized to nominal 2.0 and the sourcing redone at that size.
//
// SOURCED 2026-09-05, ../reviews/M2-FASTENING-2026-09-05.md: PennEngineering SI
// IUTFC-M2, 300-series stainless, flanged straight-wall thru-threaded. Stainless
// because brass suffers ammonia stress-corrosion cracking and these sit outside
// the seal in NH3 condensate. Replaces E-Z LOK FL-M25-HI-CR, which was the M2.5
// part and is a sole-source US import.
// All four numbers below are from one table, PEM SI-7 (sidata.pdf, 06/2022),
// metric block, read off the RENDERED page -- the PDF's text layer scrambles
// these columns and must not be trusted for them.
insert_bore_d = 3.23;      // "Hole Dia." +0.08/-0.00. Was 3.99 for the M2.5 part.
insert_bore_h = 4.76;      // PUBLISHED "Min. Hole Depth", no longer inferred: PEM
                           // states it, and it agrees with SPIROL's length + 2
                           // pitches rule (3.99 + 0.8 = 4.79) to 0.03 mm.
insert_head_d = 4.75;      // flange dia E; flanged only -- needs a counterbore or
insert_head_t = 0.46;      // it holds the retainer off the face. T, same table.
// Filler correction, SPIROL design guide p.5: open the hole +0.08 at >=15% filler
// and +0.15 at >=35%, interpolating between. Unfilled ASA needs neither, so this
// is 0 -- set it if the print material changes to a filled grade.
insert_filler_add = 0.0;

// A2 stainless MACHINE screw, M2 x 0.4, driven straight into the printed boss.
// The `pt_` prefix is kept because the geometry is unchanged and it is threaded
// through a dozen expressions below; read it as "plastic thread", not "PT screw".
//
// THE PILOT HAS TWO INDEPENDENT DERIVATIONS AND THEY LAND ON THE SAME NUMBER,
// which is the only reason it is trusted at this size:
//   1.60 = d - P = 2.0 - 0.4, the ISO metric tap-drill for M2 x 0.4 (~75%
//          thread engagement) -- the right number for a CUT ISO thread.
//   1.60 = 0.8 x d1, EJOT/ATF's core-hole rule for direct fastening into
//          thermoplastic (DELTA PT design recommendations, 2017) -- the right
//          number for a FORMED thread at nominal 2.
// A machine screw in printed ASA does some of each, so a pilot that both rules
// agree on is the defensible one. Do NOT "split the difference" upward if this
// ever moves: 75% engagement is already aggressive for a 60-degree flank in
// plastic, and the far more likely correction is a LARGER pilot (~1.70-1.75) if
// bosses split in service.
//
// CHOSEN ON A PRINTED COUPON, not on the arithmetic: part="fastener-coupon"
// carries this hole with and without the counterbore, in real ASA at the real
// depth and the real print orientation, and Fab picked the counterbored one.
pt_nominal = 2.0;
pt_pilot_d = 1.60;
// Boss OD >= 2 x screw nominal, EJOT/ATF, same page. It is hoop stress that sets
// this, not heat -- which is why this wall is smaller than the insert's.
pt_seal_wall = (2*pt_nominal - pt_pilot_d)/2;
// STRUCTURAL, not a chamfer, and the reason station 3 beat station 4: EJOT gives
// the counterbore as edge-stress relief that prevents the boss cracking as the
// thread forms, plus lead-in for the first turn. dC = 1.05 x d1, depth 0.5 x d1.
// It is also the WIDEST cut at the bolt circle (2.10 against a 1.60 pilot), so
// bolt_r is derived from it -- see bolt_cut_max. Cut in head().
pt_cbore_d = 1.05 * pt_nominal;   // 2.10
pt_cbore_h = 0.5 * pt_nominal;    // 1.00

assert(!is_undef(tube_od_meas),
       "UNMEASURED: tube_od_meas -- measure the tube OD and its ovality");
assert(!is_undef(board_env_front),
       "UNMEASURED: board_env_front -- tallest component above the board plane");
assert(!is_undef(board_env_back),
       "UNMEASURED: board_env_back -- tallest component below the board plane");
assert(!is_undef(cell_seated_h),
       "UNMEASURED: cell_seated_h -- seat a real cell in a real socket and measure how far the can top stands off the board");
echo(str("FASTENING: ", fastening, use_insert
         ? str(" -- PEM IUTFC-M2, 300-series stainless; hole ", insert_bore_d,
               " +0.08 x ", insert_bore_h, " deep (PEM-published minimum)")
         : str(" -- A2 stainless M2 machine screw direct into the printed boss;",
               " pilot ", pt_pilot_d, " (= M2 tap drill d-P, = 0.8 x d1),",
               " counterbore ", pt_cbore_d, " x ", pt_cbore_h,
               " deep, engagement ", 2*pt_nominal)));

// ------------------------------------------------- design parameters

board_w = 20.0;             // KiCad Edge.Cuts, controlled
// CONFIRMED 2026-09-05 (Fab): "board_t = 1.6 is correct for Rev A". This is no
// longer an assumption to be reconciled -- it is the built thickness, and the
// fab data is what disagrees with it: o2-probe.kicad_pcb's stackup is a 0.910 mm
// dielectric and PLACEMENT.md still specifies "1.0 mm, 4 layers". Those are the
// files that need correcting, not this one.
// It is NOT cosmetic here: board_t feeds board_swept -> board_diag -> bore_d, so
// it moves the cavity the 5.0 cm3 budget is measured on. See the volume gate.
board_t = 1.6;              // Rev A, confirmed
// MEASURED 2026-09-04 (Fab): 14.62 mm on a real can, against DS-0637 Iss. 2's
// 14.4 nominal -- +0.22 on diameter. A measured interface dimension supersedes a
// datasheet nominal, so this is the number the geometry is cut to. CAUTION: it is
// ONE sample, so it is a value, not a tolerance band; the clearances below have
// no statistical margin behind them yet.
// neck_d is DERIVED from this (neck_d = cell_d + 2*neck_margin), so the finger
// annulus of RING-PCB.md holds at 1.0 mm automatically instead of being eaten.
cell_d = 14.62;             // MEASURED; DS-0637 Iss. 2 says 14.4 nominal
cell_h = 8.3;               // DS-0637 Iss. 2 -- NOT re-measured
bore_margin = 1.5;

// Window sized to match the radial variant's TWO 10x10 coupons, so the
// comparison isolates architecture rather than area.
//
// REDUCED 16.0 -> 15.2 on 2026-09-05, and the 0.8 is not arbitrary: it is the
// growth of face_wall_min from one-and-a-third beads to two, taken out of the
// WINDOW rather than added to the groove. face_groove_id = window_d +
// 2*face_wall_min, so the two moves cancel exactly and the groove ID stays at
// 17.6 -- install stretch on the 17.0 ring is unchanged at 3.53%. Growing the
// groove instead would have put it at 18.4 and stretch at 8.24%, past the 5%
// install limit, on a ring that was ALREADY climbing out of its groove. Area is
// the thing being spent here: 181 mm2, under the 200 mm2 two-coupon benchmark
// this number was originally chosen to beat. Fab took that trade knowingly.
window_d = 15.2;            // -> 181 mm2 (was 16.0 -> 201 mm2)

bond_gap = 0.20;
// TWO DIFFERENT JOBS UNDER ONE NAME, and they parted company when the joint did.
//
// BONDED: this is the real socket depth over the tube end -- the bonded area, so
// 14 mm is a design figure and must not be cut.
//
// MONOLITHIC: there is no socket (head() does not cut it, see below), so this is
// only the z at which the cavity stack starts. It was still 14, which left the
// head's first 14 mm as a plain Ø25.18 bore inside a Ø40 body -- a 7.4 mm wall
// doing a job the tube does at 2.4, for a stretch that holds nothing but board.
// The board is Ø22.18 swept and the tube's own ID is 27.2, so that length has no
// reason to be in the head at all. 3.0 on Fab's instruction 2026-09-05: not 0,
// so the join cone still lands on parallel bore rather than on the cavity mouth.
//
// IT DOES NOT SHORTEN THE PROBE, which was my first claim and it was wrong. The
// board still needs the same length of bore, so the joint simply moves: 11 mm of
// Ø40 head becomes 11 mm of Ø32 tube and the assembly is still 146.6 mm. What it
// buys is ~5.9 cm3 of ASA (a Ø40/Ø25.18 annulus replaced by a Ø32/Ø27.2 one) and
// ~0.9 cm3 more connected gas, which is nothing against the 75 cm3 the unpotted
// tube already contributes.
//
// It also takes 5.6 cm3 off the monolithic cavity that cavity_raw() below now
// measures honestly: 11.9 -> 6.3 cm3. Still over the 5.0 budget, because that
// budget describes the POTTED production build; the Makefile gates the bonded
// variant, which measures 4.917.
//
// TWO OTHER FILES CARRY THIS NUMBER and both had to move with it:
// o2_probe_body_tube.scad's head_socket_len (subtracted from tube_len, so
// leaving it at 14 ends the tube 11 mm short) and body_tube_len above.
socket_len = monolithic ? 3.0 : 14.0;
wall_min = 2.4;

// Carrier: a PP top-hat. The spigot enters the well and squeezes the gasket
// against the well floor; the flange sits on the head's end face and is what
// the retainer presses on. The seal therefore lives INSIDE the bolt circle and
// no fastener ever penetrates it.
// The seal is a RADIAL O-ring on the spigot, not a face gasket. Two reasons,
// and the second is the important one:
//   - a face groove needs a land either side, which pushes this head to 48 mm,
//     worse than the radial variant it is competing with;
//   - a radial squeeze comes from the interference fit, NOT from the screws, so
//     the screws stop being part of the seal load path. Polypropylene creep at
//     75 C then bleeds off retention instead of bleeding off the seal.
// Spigot length is DERIVED from what the groove needs, not chosen: every extra
// millimetre of it is Ø17.5 of connected gas, and the 5 cm3 budget is now the
// binding constraint on this variant.
spigot_bore = 18.0;         // gas path through the spigot; >= window + margin

// Spigot wall, formerly `land` -- and that sharing was a conflation, not a
// saving. `land` sizes the MEMBRANE disc and the ledge its rim is clamped on
// (see membrane_cartridge_common.scad); this sizes the wall that carries the
// RADIAL O-ring groove, three parts away. Nothing ties them together, and while
// they were one number the membrane disc could not be widened without growing
// the head, nor the head shrunk without narrowing the membrane disc.
//
// It is also measured off the wrong feature. The groove root sits over the
// spigot BORE (Ø18), not over the flare mouth (Ø22) that `mouth_d + 2*land`
// referenced -- the mouth is a counterbore in the flange, above the spigot
// entirely. The assert beside the other seal checks now measures the real wall.
//
// Why 2.4 exactly: head_od takes ceil() of the bolt circle, so the diameter
// moves in 2 mm steps and 2.4 is the LOOSEST value that still lands on 40 mm
// (42 before). Anything from 2.125 to 2.4 gives the same head, so this keeps the
// most wall the size allows. Below 2.125 the sourced Ø24.0 ring stops gripping
// its groove -- see the echo for what a smaller head would cost.
spigot_land = 2.4;
flange_margin = 4.0;
carrier_fit = 0.3;
// flange_t is DEFINED BELOW, after mem_seal: which bed is fitted decides whether
// it is free at all. A forward reference to mem_clamped here would read undef
// with a warning, which is the trap join_cone already documents.

// WHICH MEMBRANE BED. Two are kept, and they are not variants of a preference:
//   "cone"     the legacy bed -- O-ring 17.0 x 1.0 (ORS116731) in a groove cut
//              into the CARRIER's wet face, bounded inward by the flare cone.
//              Correct on paper and SOURCED, but it does not print: see the
//              long note at the head of the CLAMPED FACE SEAL section in
//              membrane_cartridge_common.scad, and the photograph of a real
//              carrier with filament strung across the aperture.
//   "clamped"  the printable bed -- O-ring 17.0 x 2.5 in a groove cut into the
//              RETAINER's underside, over a flat carrier land. Same seal,
//              mirrored, so that every surface that sets squeeze is printed
//              onto solid material instead of over air.
// The default is "clamped" because the carriers being printed now are ASA and
// the legacy bed is the one that failed on the bench, not in the model.
mem_seal = "clamped";
assert(mem_seal == "cone" || mem_seal == "clamped",
       str("unknown mem_seal '", mem_seal, "'"));
mem_clamped = (mem_seal == "clamped");

// ---- carrier flange thickness = HALF THE CELL-TO-MEMBRANE PATH --------------
//
// It was `flange_t = cart_t`, and on the CONE bed it has to be: that bed's
// sealing core is cut by the shared cartridge geometry in
// membrane_cartridge_common.scad, which measures everything down from cart_t, so
// a flange thicker or thinner than cart_t either seals the membrane off or leaves
// the core hanging in air. The assert further down still says exactly that.
//
// The CLAMPED bed does not inherit that. Its core is ONE frustum cut by
// clamped_core_cuts(window_d, spigot_bore, flange_t, ...) -- parametric on
// flange_t, referred to nothing in the common file -- so on this bed the two
// numbers were only ever equal by history.
//
// Why it is worth separating. PROTOTYPE-RESPONSE.md's build candidate calls for
// a CELL-TO-MEMBRANE PATH of 5-10 mm, and that path is exactly
// spigot_len + flange_t: the cell's sensing face sits at the well floor
// -- PAST-END, where cell_z + cell_h == well_z by construction. STANDING it is
// not: the can lies on the board cell_setback back from the tip, its top face at
// cell_z + cell_h nowhere near well_z, and the gas turns a corner to reach it. The
// GAS PATH echo says which case it is reporting.
// At cart_t = 5.0 the path is 9.6 mm, at the top of the band, and it goes OVER
// 10 mm with any ring that widens the spigot groove. The flange is also the
// widest gas column in the head: the frustum is 217 mm3/mm, so 2 mm off it is
// 0.45 cm3 measured on the mesh -- ~10% of the 5.0 cm3 budget, for nothing but
// a thinner disc.
//
// 3.0 and not 2.0: the >= 2.0 anti-dishing floor below is the hard limit, and
// this keeps a millimetre over it because the flange is also what the retainer
// clamps the membrane against. The aperture opens downward as a
// atan(1.4/flange_t) = 25 degree cone at 3.0 (15.6 at 5.0), which the carrier
// still prints wet-face-down -- the printability echo reports the real angle.
flange_t = mem_clamped ? 3.0 : cart_t;

// SOURCED 2026-09-02, ../../tech/PROBE-CARRIER-SOURCING.md: o-ring-stocks.eu
// ORS116787, EPDM 70 Shore A peroxide-cured, 24.0 x 1.5 DIN 3771. NOT a derived
// size -- 24.5 x 1.5 does not exist in EPDM at all; it is FKM/FFKM only, and FKM
// is excluded because ammonia attacks fluoroelastomers.
// WHICH RADIAL RING. The sourced one, or a size that is physically in the
// drawer -- because a bench test that waits on a delivery is a bench test that
// does not happen.
//
//   "ors116787"    24.0 x 1.5, o-ring-stocks.eu, EPDM 70 peroxide, WITH the
//                  compound test report the ammonia argument rests on. The
//                  design of record.
//   "onhand-22x2"  22 x 2, on hand, UNCATALOGUED -- material, cure system and
//                  cord tolerance all assumed. TEMPORARY, for a squeeze and
//                  leak test on a part that can be printed today. This is the
//                  substitution to use: it is the only on-hand size that keeps
//                  a full-thickness wall under the groove.
//   "onhand-20x2"  20 x 2, likewise on hand, and it costs the wall: 0.99 mm
//                  under the groove root against 2.39 for the 22. Kept because
//                  it is what shrinks the spigot furthest, if that is ever the
//                  question being asked.
//
// The ring SIZES THE SPIGOT, which is why this is not a one-line substitution.
// Install stretch has to stay inside 1-5%, so the groove root is pinned near
// 1.035 x the ring ID, and the spigot diameter follows from the root plus two
// compressed cords. Ø24 -> Ø26.8 spigot, Ø22 -> Ø25.8, Ø20 -> Ø23.0. Since the
// clamped bed deleted the Ø22 heater counterbore, nothing else in the part needs
// that diameter any more, so this is now a free parameter of the ring.
//
// 14 x 2.5 and 17 x 2.5 are NOT offered and cannot be: their roots (14.5 / 17.6)
// are at or under the Ø18 spigot bore the cell has to pass through, so there is
// no wall at all. Only the 20 and the 22 are geometrically possible.
//
// A NOTE ON THE Ø22 AND THE 2.4 mm WALL, because it is 14 microns from being a
// lie. Both constraints move together and stay exactly well_bias (0.0105) apart:
//     wall >= 2.4   needs  spigot_d >= 26.8 - 4*squeeze
//     stretch <= 5% needs  spigot_d <= 26.7895 - 4*squeeze
// so no squeeze value satisfies both, for any Ø22 ring, ever. At the Ø25.8
// spigot the stretch is 4.93% and the wall is 2.387. Rather than pretend, the
// wall minimum for this variant is stated as 2.38 -- and that is the whole
// concession, not a rounded-down 2.4.
// ---- the ring is TWO NUMBERS, not a name --------------------------------
//
// Fab, 2026-09-05: "make this a parameter, so its easy to adjust, depending on
// which o-ring is available". The three-way enum this replaces could only offer
// the three sizes someone had written a branch for; the fourth ring out of the
// drawer needed a code change. Now the ring is its DIMENSIONS, the presets are
// DATA, and the spigot is SOLVED from whatever ring is named.
//
// To use a ring that is not in the table, set two numbers and nothing else:
//
//     openscad -D ring_id=19 -D ring_cord=2.5 ...
//
// The presets stay because PROVENANCE IS NOT A DIMENSION: which ring has a
// compound test report behind it is a fact about a part number, not about
// "24 x 1.5", and that report is what the whole ammonia argument rests on.
//
//   name            id    cord  d1tol  spigot_d  wall_min  provenance
//   "ors116787"     24.0  1.5   0.25   undef     undef     SOURCED: EPDM 70
//                                                          peroxide, material
//                                                          127019011, WITH the
//                                                          compound test report
//   "onhand-22x2"   22.0  2.0   0.22   25.8      2.38      on hand, UNCATALOGUED
//   "onhand-20x2"   20.0  2.0   0.22   23.0      0.95      on hand, UNCATALOGUED
//
// undef in a preset means "derive it", which is what a custom ring always does.
// The two spigot literals are NOT undef on purpose: they are already-verified
// solved values, kept verbatim so this refactor cannot move a checked part by a
// rounding step. The assert below proves the derivation reproduces them, which
// is what stops the tabulated and solved forms drifting apart in silence.
// The stretch column is the correction that made this table honest. My first
// version pinned a spigot DIAMETER per preset and cross-checked it against one
// shared 3.5% target -- and the check fired on the Ø20, which pins 23.0 where a
// 3.5% solve gives 23.4163. The preset was not wrong; MY ASSUMPTION WAS. Each of
// these rings was solved at its own stretch, deliberately, trading stretch
// against the wall left under the groove: 3.50% on the Ø24, 4.93% on the Ø22,
// 1.42% on the Ø20. One shared target cannot express that and should not try.
//
// So the table carries STRETCH, not diameter, and the spigot is always solved.
// There is now exactly one source of truth for the geometry, which is why the
// literal-vs-derivation assert that caught this could be deleted rather than
// tuned: it existed only to police a second one.
radial_ring_presets = [
//   name             id    cord  d1tol  stretch     wall_min
    ["ors116787",     24.0, 1.5,  0.25,  0.0350167,  undef],
    ["onhand-22x2",   22.0, 2.0,  0.22,  0.0492595,  2.38 ],
//  BROKEN AND KEPT AS A RECORD, not as an option: at 20.2837 the groove root
//  leaves 1.1419 mm over the Ø18 spigot bore, under the hard 1.2 floor, so
//  selecting it FAILS TO RENDER. Verified to fail identically on HEAD before
//  this refactor, so it is inherited, not introduced. It cannot be fixed by
//  moving the stretch either: more stretch lifts the root but breaks the 5%
//  rule before it clears 1.2. The Ø20 needs a narrower spigot bore, i.e. a cell
//  that no longer has to pass through it -- a different decision entirely.
    ["onhand-20x2",   20.0, 2.0,  0.22,  0.0141850,  0.95 ],
];
// DEFAULT = the ring Fab actually has. ors116787 (24 x 1.5) is sourced but not
// on the bench, so defaulting to it made every hand render and the viewer show
// a ring nobody can fit, while only the Makefile's override kept the printed
// plates honest. The default is what an unqualified render gets, so it has to
// be the buildable one.
radial_ring = "onhand-22x2";
// Direct overrides. ring_id + ring_cord are all a new ring needs; the rest fall
// back to the DIN band and to the derivation.
ring_id       = undef;
ring_cord     = undef;
ring_id_tol   = undef;
ring_spigot_d = undef;
ring_wall_min = undef;
// Override the preset's own solved stretch, or set one for a custom ring that
// needs to trade stretch against wall the way the presets do.
ring_stretch_override = undef;
// The install stretch the spigot is solved TO when it is not given. 3.5% is
// where the sourced ring already sits and is near the middle of the 1-5% window,
// so a custom ring lands with margin at both ends instead of on a limit.
ring_stretch_target = 0.035;

function ring_row(n) = let (m = [for (r = radial_ring_presets) if (r[0] == n) r])
                       len(m) > 0 ? m[0] : undef;
_ring = ring_row(radial_ring);
// A named ring must exist; a nameless one must be fully dimensioned. Either is
// fine; half of each is the state where a typo silently selects a preset.
custom_ring = !is_undef(ring_id) || !is_undef(ring_cord);
assert(custom_ring || !is_undef(_ring),
       str("unknown radial_ring '", radial_ring, "', and no ring_id/ring_cord ",
           "given. Name one of ", [for (r = radial_ring_presets) r[0]],
           ", or set ring_id and ring_cord to the ring you actually have"));
assert(!custom_ring || (!is_undef(ring_id) && !is_undef(ring_cord)),
       "a custom ring needs BOTH ring_id and ring_cord; one alone is half a ring");

oring_id_ordered = is_undef(ring_id)   ? _ring[1] : ring_id;
oring_cord       = is_undef(ring_cord) ? _ring[2] : ring_cord;
// DIN ISO 3601 d1 rows: +/-0.25 at 24, +/-0.22 at 20 and 22. Only moves stretch.
// A custom ring gets the WIDER band: guessing the narrower one is the direction
// that flatters the tolerance chain.
oring_id_tol = !is_undef(ring_id_tol) ? ring_id_tol
             : (custom_ring || is_undef(_ring[3])) ? 0.25 : _ring[3];
// Wall left under the groove root, over the spigot bore. wall_min (2.4) is what
// the sourced ring affords and what the head is designed to; see the note above
// for why the Ø22 lands at 2.38 and cannot be made to land at 2.4.
//
// A CUSTOM RING DOES NOT GET TO LOWER THIS BAR. The preset concessions are
// declared, argued, and attached to one specific ring. An automatic concession
// would let any ring redefine the minimum to whatever it happened to afford, and
// the assert reading it would then be measuring itself rather than the part. So
// a custom ring is held to wall_min and fails loudly with the shortfall named --
// set ring_wall_min explicitly to accept a thinner wall, and own the decision.
spigot_groove_wall_min = !is_undef(ring_wall_min) ? ring_wall_min
                       : (custom_ring || is_undef(_ring[5])) ? wall_min : _ring[5];
onhand_ring = (radial_ring != "ors116787") || custom_ring;
// Static radial squeeze, fraction of cord. 0.24 is not a handbook preference --
// it is the value that CENTRES the printed well's tolerance band. At the obvious
// 0.20 the band is -0.34/+0.10, and a printed bore errs oversize, which is the
// direction that loses the seal. See the well_tol asserts below.
// Re-centred against the FULL band (bore + groove + cord), which moved when the
// ring's own +/-0.08 entered the chain: 0.24 left 0.80 points of margin at the
// 15% end and 1.76 at the 30%, and the low end is the one that leaks. 0.2433
// puts the worst case at 16.14-28.54% and lands the groove root on a round
// 25.03. Not a handbook preference -- it is where the band sits squarest.
oring_squeeze = 0.2433;
// The radial seal is made between TWO surfaces, and both have tolerance: the
// head's well bore and the carrier's groove root. Counting only the well -- as
// this model did until now -- assumes the carrier is perfect and understates the
// band by whatever the carrier contributes.
//
//   carrier_material  "pp"  machined PP-H, weldable, the production route
//                     "asa" printed like the rest of the head; no weld possible,
//                           compression only, and a much looser groove
//   well_finish       "reamed"  the printed bore is finish-cut to size
//                     "printed" as it comes off the printer
//   carrier_fab       "machined" turned to size, EITHER material
//                     "printed"  as it comes off the printer
//
// Material and PROCESS are separate, and conflating them was a real error: the
// tolerance comes from machining, not from PP. ASA can be turned; PP can be
// printed. carrier_material still decides the weld and the chemistry.
carrier_material = "pp";
carrier_fab = "machined";
well_finish = "reamed";
// The ring is bought, not made, so its cord is a MEASURABLE outside dimension.
//   "catalogue" take the vendor's published tolerance for any ring in the bag
//   "sorted"    micrometer every ring on receipt and use the ones that fit
oring_sorting = "catalogue";

carrier_is_pp = (carrier_material == "pp");
// Half-widths on DIAMETER. These are read from standards now, not declared:
//   reamed 27.3 H7 = +0.021/0 (ISO 286-2, 18-30 mm band), designed to mid-band,
//   so +/-0.0105 -- FIVE TIMES tighter than the 0.05 this used to guess.
//   Printed is now MEASURED rather than guessed, but on a thin sample -- see below.
well_tol    = (well_finish == "reamed") ? 0.0105 : 0.20;   // ISO 286-2 H7
// The printed half-width was +/-0.15 mm, and that figure was my own guess with no
// measurement behind it. It now has three readings of the groove root, normalised
// by the diameter each part was actually cut at, because the two parts were cut
// differently:
//     carrier 1, cut 25.0404 -> 24.800   factor 0.99040
//     carrier 2, cut 25.2831 -> 24.980   factor 0.98801   (position A)
//     carrier 2, cut 25.2831 -> 25.000   factor 0.98880   (position B)
// Half-range 0.0012 on the factor = +/-0.030 mm on a 25.3 mm root.
//
// That was under ARACHNE and gave +/-0.06. The settled process is classic, and it
// now has seven angular readings on one carrier: sd 0.0393, so 2 sd = +/-0.079 for
// the ovality term. Combined in RSS with the arachne between-part figure of
// +/-0.025 gives +/-0.083, taken as +/-0.09.
//
// WHICH SPREAD DOMINATES FLIPPED at the process change, and it decides what to
// measure next. Under arachne the variation was part-to-part (0.050 mm) and not
// out-of-round (0.020 mm), so more parts were informative. Under classic ovality
// is 0.100 mm and dominates, so more POSITIONS on one part is what pays -- which
// is how this number got from a sample of two to a sample of seven without another
// print. Do not carry the old advice across the process change.
//
// THE CATALOGUE-RING ROUTE SITS EXACTLY ON THE LIMIT and must not be relied on:
// 14.45 of 15 points at +/-0.08, 15.14 at +/-0.09. A sourcing decision resting on
// 0.55 points of a 15-point budget is not a margin. Micrometer-sorted rings pass
// at 7.88, roughly half the budget, and that is the route to use. The seal-pair
// term runs at 68.1 squeeze points per mm, making this the chain's costliest axis.
carrier_tol = (carrier_fab == "machined") ? 0.05 : 0.09;   // printed, classic: 7 readings
seal_tol = well_tol + carrier_tol;   // the gland varies by half this, each way
// The ring's OWN cord tolerance, which this model ignored entirely until now.
// It is the LARGEST term in the chain -- bigger than the bore and the groove
// together -- because +/-0.08 on a 1.5 mm cord is +/-5% of the sealing element.
// Techniparts / o-ring-stocks.eu "O-ring Tolerances", DIN 3771 / DIN ISO 3601:
// d2 <= 1.8 -> +/-0.08. (d1 = 24 -> +/-0.24..0.25, which only moves stretch and
// is second order.) Sorting collapses it: a micrometer on a part in your hand.
oring_cord_tol = (oring_sorting == "sorted") ? 0.01 : 0.08;
// 1.40, not 1.30. The fill gate below used to check the NOMINAL ring in the
// NOMINAL gland and read 76%; at the worst corner -- bore at its H7 minimum,
// root at its machined maximum, cord and ID both at catalogue maximum -- the
// same 1.30 groove fills to 87.5% and the ring hydraulically locks. Widening
// the groove is the cheap axis: it costs 0.15 mm of spigot length and nothing
// else, where a narrower cord would cost squeeze.
groove_w_factor = 1.40;     // groove width as a multiple of cord
lead_chamfer = 1.0;         // so the O-ring is not shaved on assembly

// The clamped retainer carries the O-ring groove, so it loses face_seat_depth
// plus the groove depth out of its underside and what is left is the web that
// reacts the ring. At 3.0 that web is 1.0 mm and bows, which would bleed squeeze
// off exactly where it is being set, so 2.0 is the target.
//
// DERIVED, not declared, and quantized to the BUILD: whichever face is up, a
// total height that is not first_layer + n*layer puts a seal plane wherever the
// slicer's last layer happens to land.  NOTE the datum MOVES with
// face_groove_up: printed groove-up the seal plane is the top face, printed
// groove-down it is the FIRST LAYER and the groove ROOF is what has to land on a
// layer boundary instead.  See the depth assert -- it is the thing that checks
// this, and it is orientation-aware for exactly that reason.
// 0.2 + 32 x 0.12 = 4.04, web exactly 2.0. It costs 1.04 mm of probe length
// through cap_stack.
retainer_t = mem_clamped
    ? face_first_layer_h
      + ceil(((face_seat_depth + face_groove_depth(window_d) + 2.0)
              - face_first_layer_h) / face_layer_h) * face_layer_h
    : 3.0;
// SIX, not four. The four-screw choice was made when the radial O-ring was
// thought to have taken all seal load off these screws; a review found that is
// only true of the carrier-to-head joint -- the retainer still compresses the
// membrane's perimeter gasket, so bolt spacing governs how evenly that gasket is
// squeezed. Four on this circle is 25.4 mm of arc between screws against a 21 mm
// gasket; six is 16.9 mm. It costs nothing: head_od is set by the bolt RADIUS,
// not the count, so 4 and 6 both land on 42 mm.
bolt_n = 6;
// Wall between the INSERT bore and the well bore. Sized against thermal
// distortion, not strength: heat-setting at 200+ C within a millimetre of the
// O-ring's sealing surface will bulge it, and the leak test would fail with no
// visible cause. This is what sets the head diameter -- see the echo.
// 2.3 = SPIROL's boss rule (boss OD 2-3x insert dia, design guide p.5) on the
// PEM part's 3.73 mm knurl: 2 x 3.73 = 7.46 boss OD around a 3.23 hole is a
// 2.115 mm wall, and this keeps a little over it. Held at 2.3 rather than
// relaxed to 2.115 when the part changed from the M2.5 E-Z LOK, because the
// binding reason for this wall is thermal, not structural, and 200+ C a
// millimetre from the O-ring's sealing surface does not care which insert it is.
insert_seal_wall = 2.3;

// The stand-off is ALSO the breathing band, so it is sized by open area, not by
// how much clearance looks tidy. A guard more restrictive than the membrane
// sets the response time itself and corrupts the D_eff being measured.
guard_gap = 8.0;            // stand-off / open band height
guard_open_factor = 4.0;    // required open area, as a multiple of the window
rib_n = 6;                  // cage ribs across the band
rib_w = 3.0;
cap_wall = 2.5;
cap_front_t = 2.5;          // solid plowing face
cap_grip = 10.0;            // how far the cap reaches down the head's OD
cap_screw_n = 2;
// BLIND: must never reach the bore -- see the cap_screw_void_r assert.
//
// STAYS AT 4.0, and the counterbore added on 2026-09-05 comes OUT OF THE THREAD
// rather than being added to the depth. Engagement is therefore 3.0 = 1.5 x
// nominal, under EJOT's di = 2 x d1. That is a deliberate derate, on the one
// joint in the head that can afford it: these screws only hold the plow cap on
// and carry no seal load, which is the same reason they are self-tapping at all.
//
// It is not a free choice. 5.0 was tried first, to keep 2 x d1 of thread, and
// the cap_screw_void_r assert REFUSED it -- by 0.05 mm: the hole reaches r=14
// and the void behind it runs out to r=13.05, needing 14.05. Deepening these
// holes to keep the thread rule would have opened an outside-to-gas leak path
// through the head wall to save a cap screw. Wrong trade, and the guard is what
// made it visible rather than a comment.
cap_screw_depth = 4.0;      // 1.0 counterbore + 3.0 thread
selftap_cap = pt_pilot_d;   // cap screws carry no seal load, so self-tap is fine.
                            // Same M2 pilot as the retainer screws, and tied to
                            // it rather than restated: one screw size in the head
                            // (was 2.1, which was the M2.5 pilot).
nose_taper = 4.0;

// Seal-land thermometry: REMOVED 2026-09-04, deliberately -- "let's try without
// first" (Fab). Added 2026-09-03 to supply the WARM END of the eta measurement
// PROTOTYPE-RESPONSE.md needs (design point: 2 K membrane rise on no more than
// 4 K of block rise, i.e. coupling eta >= 0.5, which
// o2-condensation-model-research.md records as UNMEASURED). It was a 1.2 mm
// blind pocket in the heater ledge, from the days when the heater was assumed to
// live in this carrier.
//
// SUPERSEDED, not merely disabled. RING-PCB.md moves the heater onto a small PCB
// carried on the main board's fork, so the heat SOURCE now carries its own
// reflow-soldered sensor on two of the fork's four conductors. A second sensor
// buried in a printed pocket, needing its own lead through the same bore, buys
// nothing -- and it cost an interface dimension nobody could source: the 1.2 mm
// was a declared placeholder bounded by the 2.0 mm heater ledge, never a part.
//
// cartridge_tsense_axial(), tsense_axial_r() and tsense_axial_top() remain in
// membrane_cartridge_common.scad. To restore: re-add `tsense`/`tsense_bore`, the
// bolt-circle clearance assert beside bolt_cut_max, and the call in carrier().
// Note it never saw the membrane's CENTRE cold spot in any case -- that sits over
// the flare cone with nothing to bore into, so eta always also needed a
// temporary sensor on the membrane face.

// ------------------------------------------------- derived

board_swept = board_env_front + board_t + board_env_back;
board_diag = sqrt(pow(board_w, 2) + pow(board_swept, 2));
bore_d = max(board_diag + 2*bore_margin, cell_d + 2*bore_margin);

mouth_d = window_d + flare_extra;        // the flare's mouth, in the flange
// Ø23.0 for the on-hand ring: solved from the root it needs (20.0 x 1.035 =
// 20.7 -- see radial_ring above) plus two compressed cords, less carrier_fit.
// The sourced ring's 26.8 is left as the literal expression it has always been,
// so this substitution cannot move the design of record by a rounding step.
// Solved from the root each ring needs (ID x ~1.035) plus two compressed cords,
// less carrier_fit. The sourced ring's 26.8 is left as the literal expression it
// has always been, so this substitution cannot move the design of record by a
// rounding step.
// H7 is +0.021/0, not +/-0.0105: a reamed bore is centred half a band ABOVE
// nominal, never below it. The seal math must use the middle of the distribution
// the shop actually produces, or every squeeze figure is biased loose by 0.0105.
// The geometry is still cut at the call-out; only the seal arithmetic shifts.
//
// MOVED ABOVE spigot_d, which now derives from it. Left below, OpenSCAD reads it
// before its assignment and the solved spigot silently loses 10.5 microns.
well_bias = (well_finish == "reamed") ? 0.0105 : 0;

// THE RING SIZES THE SPIGOT, which is why a substitution is not a one-liner.
// Install stretch has to stay in 1-5%, so the groove root is pinned near
// ID x (1 + stretch), and the spigot follows from that root plus two COMPRESSED
// cords, less the carrier fit and the well's H7 bias. Inverting groove_root_d
// below gives exactly:
//
//   spigot_d = ID x (1+stretch) + 2 x cord x (1-squeeze) - carrier_fit - well_bias
//
// Solved rather than tabulated, so ANY ring works instead of only the three that
// had a branch written for them.
// QUANTIZED TO 1 MICRON, and that is not cosmetic -- it is the whole reason this
// derivation is safe to substitute for the literal it replaced.
//
// Measured the moment the literal went away: the Ø24 solves to 26.800000799...,
// 0.8 nanometres-worth of nothing above 26.8, because the stretch constant in
// the table is a rounded decimal. head_od then does
//   2 * ceil(max(..., bolt_r + fast_hole_d/2 + wall_min) + 0.5)
// and that expression lands EXACTLY on 20.0 for this part -- so 0.8 µm of
// overshoot became ceil(20.0000004) = 21 and the head grew 40 -> 42 mm, the cap
// 45 -> 47, silently, with every input printing unchanged. r7s0 had guarded
// against precisely this by keeping the sourced ring's 26.8 as a literal; I
// removed that guard, so the derivation has to be exact instead of nearly exact.
// A spigot diameter is not meaningful past a micron in any case -- it is turned
// or printed, and carrier_tol alone is ±0.09 mm.
function spigot_d_for(id, cord, stretch) =
    round(1000 * (id*(1 + stretch) + 2*cord*(1 - oring_squeeze)
                  - carrier_fit - well_bias)) / 1000;
ring_stretch = !is_undef(ring_stretch_override) ? ring_stretch_override
             : custom_ring ? ring_stretch_target : _ring[4];
spigot_d_derived = spigot_d_for(oring_id_ordered, oring_cord, ring_stretch);
spigot_d = !is_undef(ring_spigot_d) ? ring_spigot_d : spigot_d_derived;
// Solved, every time, for every ring: the spigot IS the derivation. Nothing to
// cross-check, because there is no second value to disagree with.
well_d = spigot_d + carrier_fit;         // the DRAWN bore, i.e. the call-out
well_d_made = well_d + well_bias;

// Radial O-ring groove, cut into the spigot's outside diameter. Seated OD must
// exceed the well bore by the squeeze; groove root follows from that.
groove_root_d = well_d_made - 2*oring_cord + oring_cord*oring_squeeze*2;

// SHRINKAGE COMPENSATION, printed carriers only. Two carriers measured on the
// P1P, 2026-09-03. Only the ROOT is compensated, because only the root moves the
// seal: squeeze is (well - root)/2 and the well is BORED to size, so it does not
// shrink with the carrier. That asymmetry is the whole problem -- a printed
// carrier in a PRINTED well would self-compensate and need none of this.
//
// Shrinkage is NOT one number. On the first carrier, against the drawing:
//     flange OD   39.1000 -> 38.870   -0.588%   mean of two: 38.90, 38.84
//     spigot OD   27.0000 -> 26.830   -0.630%   one reading
//     groove root 25.0404 -> 24.800   -0.960%   <-- the one that seals
// The thin wall under the groove pulls harder than the flange rim does, so a
// single XY scale in the slicer cannot fix this part: the factor that corrects
// the root over-sizes the rim by the same stroke.
//
// THE COMPENSATION IS NOW CONFIRMED ON A PRINTED PART, which is what this block
// used to be waiting for. Uncompensated, the printed root came out at 24.800 and
// squeezed 14.90% against a 15% floor -- genuinely out. The compensated carrier
// was cut at 25.2831 and printed at 24.99, squeezing 21.02%, with install stretch
// still inside the 5% rule at 4.13%.
//
// Under-compensating fails SAFE: too little correction leaves the root small, the
// gland wide and the squeeze HIGH, not low. The residual here is -0.04 mm and it
// cost nothing.
carrier_is_printed = (carrier_fab == "printed");

// The raw readings, as named parameters rather than prose, so the factor is
// derived from them and cannot drift out of step with its own comment.
//
// Each reading is a (cut, printed) PAIR, because the two carriers were cut at
// different diameters -- the second was already compensated. A bare list of
// printed sizes would be meaningless: the factor is a ratio, and its denominator
// differs per part. This also removes the need to pin groove_root_d, which the
// earlier single-value form had to assert against.
carrier_meas_flange = [38.90, 38.84];       // first carrier, two readings
carrier_meas_spigot = [26.83];              // first carrier, one reading
// ARACHNE-process pairs only. wall_generator changes the achieved diameter, so a
// classic reading cannot be pooled with these -- see carrier_root_classic below.
carrier_root_pairs  = [[25.0404, 24.800],   // carrier 1, uncompensated, arachne
                       [25.2831, 24.990]];  // carrier 2, compensated, arachne
carrier_root_ovality = [24.98, 25.00];      // carrier 2, two angular positions

// CARRIER 3, the settled classic process, same cut and same flow as carrier 2:
carrier_root_classic = [25.00, 25.10, 25.06, 25.00, 25.03, 25.08, 25.02];
// SEVEN angular positions. Mean 25.0414 against a 25.0404 target -- one micron.
// Squeeze at the mean is 22.69% against the drawn 22.65%, and every position lands
// between 21.34% and 24.59%, all inside the 15-30% window. The compensation is
// validated far better than the first two-position reading suggested.
//
// The 25.10 is the earliest of these readings and sits 2.1 sd above the other six.
// It is KEPT: 2.1 sd in a sample of seven is not an outlier, and discarding it
// would tighten carrier_tol, which is the direction that flatters this model. Note
// what dropping it would do -- mean 25.0317, sd 0.0325 instead of 0.0393 -- so the
// decision is visible rather than buried.
// Mean 25.050 against 24.990 on arachne -- wall_generator moved the root +0.060 mm
// (factor 0.99078 against 0.98940), confirming the process dependence recorded
// below is real and not theoretical.
//
// The factor is NOT re-tuned to it. Correcting for classic would move the cut by
// -0.0097 mm, ten times smaller than this part's own 0.100 mm ovality; tuning to
// that is false precision. The arachne-derived cut happens to land classic at
// 22.97% squeeze against a 22.65% target, which is better centred than arachne
// managed, so there is nothing to gain.
//
// What DID change is the scatter, and it went the wrong way: ovality 0.100 mm on
// this carrier against 0.020 mm on the arachne one, a 5x regression. Suspected
// mechanism, and it is a suspicion: classic fills residue with gap infill, whose
// volume varies around the loop, where arachne redistributes bead width smoothly.
// That would make the achieved diameter angle-dependent. Unverified.
function vmean(v, i=0) = i >= len(v) ? 0 : v[i]/len(v) + vmean(v, i+1);
function ratios(v, i=0) = i >= len(v) ? [] : concat([v[i][1]/v[i][0]], ratios(v, i+1));

// OVALITY IS NOT THE PROBLEM, which was the open question. The compensated root
// reads 24.98 and 25.00 at two angular positions -- 0.020 mm out of round, worth
// 0.65 squeeze points. The between-PART spread is 0.199 points, 2.5x larger than
// the within-part ovality, so the uncertainty lives in the factor and not in the
// geometry. That is the useful direction: another part improves the estimate,
// another position on the same part does not.
carrier_shrink_root = vmean(ratios(carrier_root_pairs));   // 0.98940, -1.060%

// VALID ONLY AT THESE PROCESS CONDITIONS, and nothing recorded them before.
// Both carriers printed at filament_flow_ratio 0.95 (the ASA profile's deliberate
// 5% under-extrusion), wall_generator arachne, 0.2 mm layers, 0.45 mm line width,
// nozzle 270 with a 280 initial layer. Flow especially matters: it is a bead-width
// multiplier, so raising it to 1.05 would grow diameters by roughly 0.047 mm --
// about 1.6 squeeze points, which is the same order as the whole correction. A
// change to any of these invalidates the factor rather than merely perturbing it.
carrier_shrink_flow = 0.95;
assert(carrier_shrink_root > 0.97 && carrier_shrink_root < 1.0,
       str("shrink factor ", carrier_shrink_root, " is outside anything plausible ",
           "for ASA -- check the (cut, printed) pairs, one is probably transposed"));
// The compensated cut is EXPECTED TO PRINT at groove_root_d, which is why every
// seal calculation below still uses the drawn value and the machined drawing stays
// at 25.0404. Confirmed: cut 25.2831 printed 24.99 against a 25.0404 target.
groove_root_cut = carrier_is_printed ? groove_root_d / carrier_shrink_root
                                     : groove_root_d;
// Compensating the root UP makes the groove shallower, so the wall under it
// gets thicker, not thinner -- the risk is at the other end: a root that
// approaches the spigot OD stops being a groove at all.
assert((groove_root_cut - spigot_bore)/2 >= 1.2,
       str("compensated groove root ", groove_root_cut, " leaves only ",
           (groove_root_cut - spigot_bore)/2, " mm of wall over the bore"));
assert(spigot_d - groove_root_cut >= 2*0.5,
       str("compensated groove root ", groove_root_cut, " is only ",
           (spigot_d - groove_root_cut)/2, " mm below the spigot OD ", spigot_d,
           " -- too shallow to retain the ring"));
groove_w = groove_w_factor * oring_cord;
spigot_len = groove_w + lead_chamfer + 1.5;   // the assert below, solved
oring_stretch = groove_root_d/oring_id_ordered - 1;   // install stretch onto the groove
// Stretching thins the cord by roughly half the stretch, which eats squeeze.
oring_cord_fitted = oring_cord * (1 - oring_stretch/2);
oring_squeeze_real = (oring_cord_fitted - (well_d_made - groove_root_d)/2) / oring_cord_fitted;
// Derived from the INSERT bore, not the screw's clearance hole: the insert is
// the larger feature and the one installed hot next to the sealing surface.
use_insert = (fastening == "insert");
fast_hole_d = use_insert ? insert_bore_d + insert_filler_add : pt_pilot_d;
// The insert's depth is now a PUBLISHED minimum, so it is used as one: the hole
// is cut to it, not to a round number that happened to exceed it.
fast_hole_h = use_insert ? insert_bore_h : 2 * pt_nominal + pt_cbore_h;
fast_seal_wall = use_insert ? insert_seal_wall : pt_seal_wall;
// The widest thing actually cut at the bolt circle. On EITHER route that is the
// counterbore, not the hole -- and this is NOT an identity, because
// insert_head_d and pt_cbore_d are independent sourced inputs that no derivation
// ties to bolt_r. The thread-forming counterbore was added 2026-09-05 and is
// 2.10 against a 1.60 pilot, so on that route the widest cut is now the
// counterbore too. Defined here rather than beside its assert because bolt_r has
// to be derived from it: sizing the circle off the hole and checking the
// counterbore afterwards is how the check ends up failing something the geometry
// could simply have avoided.
bolt_cut_max = use_insert ? max(insert_bore_d + insert_filler_add, insert_head_d + 0.3)
                          : max(fast_hole_d, pt_cbore_d);
// Minimum wall from the WIDEST cut to the sealing well. Distinct from
// fast_seal_wall, which is the boss rule at the thread; this one is the floor
// the mouth of the counterbore must still respect.
cut_seal_wall_min = 1.0;

// The bore the fastener must stay clear of is the WELL the spigot seals into --
// well_d = spigot_d + carrier_fit -- not the spigot itself. Using spigot_d here
// overstated every quoted wall by carrier_fit/2.
// TWO things push the bolt circle out, and until 2026-09-05 only one of them was
// counted: the sealing bore (a fastener must not be drilled into the well's
// wall) and, since the bed moved into the retainer, THE MEMBRANE SEAT (a bolt
// hole must not break into the disc pocket). With the sourced Ø24 ring the well
// term wins and this changes nothing; substituting the on-hand Ø20 ring shrinks
// the well by 4 mm, and without the second term the circle followed it down to
// Ø28.3 and cut straight through a Ø27.25 seat. The assert below caught it,
// which is the correct outcome -- but the answer is to derive the circle from
// both constraints, not to shrink the membrane.
bolt_r = max(well_d/2 + fast_seal_wall + fast_hole_d/2,
             // THIRD constraint, added 2026-09-05 with the thread-forming
             // counterbore: the mouth of the widest cut must also keep its wall.
             well_d/2 + cut_seal_wall_min + bolt_cut_max/2,
             // m2_clear, not fast_hole_d: through the FLANGE the screw needs
             // its clearance hole, and that is the bigger of the two features
             // -- sizing this off the pilot leaves the assert 0.95 mm short.
             mem_clamped ? (face_disc_d(window_d) + 0.4)/2 + 0.8 + m2_clear/2
                         : 0);

// The flange must reach the bolt circle, which the insert now sets -- with the
// real 3.99 bore the circle grew past a flange sized from the spigot alone.
// The trailing constant IS the rim outboard of the screw holes: this term makes
// flange_d = 2*bolt_r + m2_clear + K, so the rim is K/2 whatever else moves.
// K was 4.0 -> a 2.0 mm rim -> 3.33 beads at 0.6, and the classic generator
// gap-filled the 0.58 leftover so badly the flange printed with voids you could
// see through (observed 2026-09-05). K = 8*face_line_w makes the rim four whole
// beads. Rounder rather than thinner on purpose: this rim is what the six
// screws pull against.
flange_d = max(spigot_d + 2*flange_margin, 2*bolt_r + m2_clear + 8*face_line_w);

// Head OD: the bore, or the bolt circle plus material around it. NOT a facet at
// a radius, which is the whole point of this variant.
// The -1e-6 is a float guard, not a design allowance. ceil() here amplifies any
// sub-micron overshoot into a 2 mm step of head diameter, and this expression
// sits exactly on an integer (20.0) for the part as drawn -- the worst possible
// place to be. Anything within a micron of the boundary is the boundary; a ring
// whose solved spigot lands a nanometre over must not cost 2 mm of probe.
head_od = 2 * ceil(max(bore_d/2 + wall_min,
                       bolt_r + fast_hole_d/2 + wall_min) + 0.5 - 1e-6);
cap_od = head_od + 2*cap_wall;

// Volume, and the structural advantage of putting the cell past the board end:
// BEYOND THE BOARD THERE IS NO BOARD TO CLEAR, so the bore necks to the cell.
// The cone that carries the tube's OD out to the head's, when they are one
// part. 45 degrees, so the monolithic body prints cable-end-down with no
// support anywhere -- which is the whole reason it is printed that way up.
// Defined here and not beside `joint`, because head_od is derived below it and
// a forward reference makes OpenSCAD substitute undef with only a warning.
join_cone = (head_od - tube_od_nominal)/2;
assert(!monolithic || join_cone > 0,
       "the head is not wider than the tube; there is nothing to cone out to");

// WHERE THE CELL SITS. This is the one decision the whole cavity length rides on.
//
//   "standing"  option A, and what Rev A was actually built as: the cell is a THT
//               part on the board, axis normal to the copper, gas face radial,
//               centre 13.5 mm back from the board tip (PLACEMENT.md, "SGX O2
//               cell centre (10.0, 93.5)" on a board whose gas end is y=107.0).
//               NOTHING is past the board tip, so the board runs right up to the
//               well floor and there is no necked bore at all.
//   "past-end"  option C: cell beyond the board end on the probe axis, sitting in
//               a Ø(cell+2) neck. Kept because the two orientations are still
//               being compared on numbers, not because either is provisional --
//               but it now needs cell_axial_len supplied explicitly, since the
//               measured-input block no longer carries one.
cell_mount = "standing";
assert(cell_mount == "standing" || cell_mount == "past-end",
       str("unknown cell_mount '", cell_mount, "'"));
cell_standing = (cell_mount == "standing");
cell_axial_len = cell_standing ? 0 : undef;
assert(cell_standing || !is_undef(cell_axial_len),
       "cell_mount=past-end needs cell_axial_len -- seat a real cell in a real socket");

// PLACEMENT.md, controlled datum: cell centre (10.0, 93.5) on a 20.0 x 107.0
// board with the square gas end at y=107.0. DRAWING ONLY -- the head has no
// feature at this z; it is here so the picture says where the gas has to get to.
cell_setback = 13.5;        // board tip to cell axis, standing mount

neck_margin = 1.0;
neck_d = cell_d + 2*neck_margin;
cell_disp = PI * pow(cell_d/2, 2) * cell_h;
// How far the board tip stands inside the cavity, and it is NO LONGER a free
// 2.0. Deleting the neck moved the binding constraint onto the RETAINER SCREWS:
// they enter from the end face and go fast_hole_h deep, at a bolt radius that
// overlaps the bonded socket, so they cannot be allowed to reach z = socket_len
// or they open an outside-to-gas leak path through the bond. The material behind
// the end face is exactly cav_board_len + cav_clear_len + spigot_len, and the
// assert further down wants fast_hole_h + 2 of it. With the neck gone that sum
// fell to 7.3 against 10.0 and the head stopped rendering -- correctly.
//
// So it is SOLVED rather than chosen, and 2.0 stays as the floor for when the
// fastener is not the binding constraint. It is the most expensive millimetre in
// the probe: Ø25.18 less the board is 466 mm3/mm, against 254 for the spigot
// bore and 217 for the flange core. Anything that lets fast_hole_h down -- a
// shorter screw, the monolithic joint where there is no socket to break into --
// buys cavity here first.
// The necked length past the board tip. ZERO on the standing mount: the neck was
// only ever the pocket the axial cell sat in, and with the cell on the board
// there is nothing to pocket. 13.0 mm of Ø16.62 bore and 1.43 cm3 of connected
// gas leave with it, and the head gets 13 mm shorter.
cav_clear_len = cell_axial_len;          // guard_gap is OUTSIDE the membrane
has_neck = cav_clear_len > 0;
cav_board_len = max(2.0, fast_hole_h + 2.0 - cav_clear_len - spigot_len);
// Now counts the spigot bore and the flare stack as well, because a bore-only
// figure understates: it passed at 2.68 cm3 while the mesh measured 5.81.
// The clamped core is ONE frustum through the whole flange, spigot bore to
// window -- no Ø22 heater counterbore (RING-PCB.md put the heater in the spigot
// bore instead) and no groove on this side of the membrane. It is 1136 mm3
// against the legacy 1258 + 21, so the bed change BUYS cavity budget rather
// than spending it.
core_gas = mem_clamped
    ? PI*flange_t/12 * (pow(spigot_bore,2) + spigot_bore*window_d + pow(window_d,2))
    : PI*pow(mouth_d/2,2)*heater_shelf_t
      + PI*(cart_t - pocket_depth - heater_shelf_t)/12
        * (pow(mouth_d,2) + mouth_d*window_d + pow(window_d,2));
// THE CAN'S DISPLACEMENT IS COUNTED ONLY WHERE ITS SHAPE IS ACTUALLY MODELLED,
// and standing it is not -- so standing, it is never subtracted.
//
// This was a boolean, `cell_in_head`, that switched the WHOLE 1393 mm3 can in as
// soon as any part of it crossed into the head. Codex review 2026-09-05 broke it
// in one step: at cav_board_len = 6.6 only 0.41 mm of the can has entered, worth
// ~11 mm3 of circular segment, yet both gates dropped 1393 and reported 3.68 cm3
// against a real ~5.07 cm3. Worse, they AGREED -- because cavity() cut the same
// wrong solid, an AXIAL cylinder at the board tip, which is where the can sits in
// the PAST-END mount and nowhere near where it sits standing (radial, on the
// board, cell_setback back from the tip). Two checks that share a wrong model are
// one check.
//
// So the standing branch counts the can as GAS. That over-states the cavity by at
// most the can's own volume, and over-stating is the only safe direction for a
// gate that must never read low. If the can's real displacement is ever wanted
// here, model the radial can -- do not reintroduce a threshold.
//
// The past-end branch is unchanged: there the axial cylinder IS the can.
cell_disp_counted = has_neck ? cell_disp : 0;
cav_net = PI*pow(bore_d/2,2)*cav_board_len - board_w*board_t*cav_board_len
        + PI*pow(neck_d/2,2)*cav_clear_len - cell_disp_counted
        + PI*pow(spigot_bore/2,2)*spigot_len + core_gas;

well_z = socket_len + cav_board_len + cav_clear_len;   // well floor
end_z = well_z + spigot_len;                           // head end face
head_len = end_z;

// The PCB tip and the cell it carries. REPRESENTATIVE -- drawn, never exported.
// This geometry belongs to the KiCad board, not to this file; it is here for one
// reason, which is that the exploded view showed the head without showing what
// the head is FOR, so nothing in the picture said where the gas has to get to.
//
// Controlled: board_w / board_t are the Edge.Cuts numbers, cell_d / cell_h are
// DS-0637 Iss. 2. NOT sourced: the socket. Its stand-off is DERIVED as
// cav_clear_len - cell_h -- i.e. it inherits the unmeasured cell_axial_len -- and
// the real Cambion 450-3703 is three separate receptacles, not the solid pillar
// drawn. The pillar is a position marker; gas flows around it.
//
// Note the deliberate inconsistency: cav_net subtracts cell_disp and NEVER the
// socket, so the volume model counts the socket's own solid as gas. That errs
// toward a larger cavity, which is the safe direction for a <= 5.0 cm3 budget,
// so it stays -- but it is why this drawing shows solid where the gate assumes
// void.
board_tip_z = socket_len + cav_board_len;   // the board's end face
socket_standoff = cav_clear_len - cell_h;   // past-end only; meaningless standing
// STANDING: the can's axis is radial, cell_setback back from the tip, and it is
// lifted off the copper by whatever the socket gives -- cell_seated_h is measured
// to the can TOP, so the can's near face is cell_seated_h - cell_h off the board.
cell_stand_off = cell_seated_h - cell_h;
cell_z = cell_standing ? board_tip_z - cell_setback   // the can's AXIS
                       : board_tip_z + socket_standoff;  // underside of the can
board_stub = cell_standing ? cell_setback + cell_d/2 + 6.0 : 16.0;   // drawing only

// The cap must SWALLOW the whole clamped stack, not just the drainage gap. It
// clears the carrier flange and the retainer, then leaves the stand-off in
// front of the membrane, then the solid plowing face.
cap_stack = flange_t + retainer_t;
band_z0 = cap_grip + cap_stack;          // start of the open breathing band
band_z1 = band_z0 + guard_gap;
cap_len = band_z1 + cap_front_t;
// cap_len is the length that has to CONTAIN the stack, so it deliberately stops
// at the plowing face. The nose taper still exists in the world, so anything
// placing or measuring the whole part needs the overall length instead.
cap_oal = cap_len + nose_taper;
window_area = PI * pow(window_d/2, 2);
guard_open = (PI*cap_od - rib_n*rib_w) * guard_gap;

// ------------------------------------------------- gates

// STANDING, the head bore never has to pass the can: the board is inserted from
// the CABLE end, down the tube, so the can's clearance is the tube's ID and the
// board's own swept envelope -- which is what bore_d is derived from anyway.
assert(!has_neck || bore_d >= cell_d + 2*bore_margin,
       "bore does not clear the cell can");
// STANDING, the can never passes the head bore -- the board is inserted from the
// CABLE end, down the tube -- so what has to clear it is the TUBE's ID. That was
// asserted nowhere until the 2026-09-05 Codex review pointed out that
// cell_seated_h was a required input constraining absolutely nothing: a render
// with cell_seated_h = 20 passed every gate while the can needed a 22.05 mm
// radius inside a 13.6 mm bore. The swept radius is the can's far top corner.
cell_stand_r = sqrt(pow(cell_d/2, 2) + pow(board_t/2 + cell_seated_h, 2));
assert(!cell_standing || cell_stand_r <= body_tube_id/2 - 0.5,
       str("the standing cell sweeps r=", cell_stand_r, " and the tube bore is r=",
           body_tube_id/2, ": the can does not go down the tube. cell_seated_h ",
           cell_seated_h, " is what drives this."));
echo(str("STANDING CELL: sweeps r=", cell_stand_r, " in a r=", body_tube_id/2,
         " tube bore -- ", body_tube_id/2 - cell_stand_r, " mm spare."));

// SERVICEABILITY.
//
// STANDING: the cell is soldered-or-socketed to the board and the board comes out
// the CABLE end, so there is no extraction through the head and nothing here to
// check. That is a real improvement over what this block used to have to say.
//
// PAST-END: the head is BONDED to the tube (see the sealing stack at the top of
// this file), so the head never comes off and the ONLY path a cell can ever take
// is axially OUT through the carrier well -- up the neck first, then through the
// spigot bore. "The cell is replaceable" is a claim the geometry has to earn, so
// it is checked rather than asserted in prose.
cell_pull_neck   = (neck_d - cell_d)/2;
cell_pull_spigot = (spigot_bore - cell_d)/2;
cell_pull_travel = cell_h + socket_standoff + spigot_len;
assert(cell_standing || (cell_pull_neck > 0 && cell_pull_spigot > 0),
       str("cell cannot be withdrawn: neck clearance ", cell_pull_neck,
           " mm, spigot-bore clearance ", cell_pull_spigot,
           " mm. With the head bonded to the tube there is no second path."));
echo(cell_standing
     ? str("CELL SERVICE: standing mount -- the cell rides the board and comes ",
           "out the CABLE end. No extraction through the head, no reach down the ",
           spigot_bore, " mm spigot bore.")
     : str("CELL SERVICE: withdraws axially, travel ", cell_pull_travel,
           " mm; radial clearance ", cell_pull_neck, " mm in the neck then ",
           cell_pull_spigot, " mm in the spigot bore. Blind reach from the head end face to the can top ",
           end_z - well_z, " mm through a ", spigot_bore,
           " mm bore -- NO EXTRACTION TOOL EXISTS and fingers do not fit."));
assert((spigot_d - spigot_bore)/2 - oring_cord + oring_cord*oring_squeeze
       >= spigot_groove_wall_min - 1e-6,
       str("spigot wall under the O-ring groove is ",
           (spigot_d - spigot_bore)/2 - oring_cord*(1 - oring_squeeze),
           " mm against ", spigot_groove_wall_min,
           " required: it collapses inward and loses squeeze"));
assert(spigot_len >= groove_w + lead_chamfer + 1.5,
       "spigot too short to carry the groove plus its lead-in chamfer");
assert(spigot_bore >= window_d + 2.0,
       "spigot bore constricts the window");
assert(oring_stretch <= 0.05,
       str("O-ring install stretch ", oring_stretch*100, "% exceeds the 5% rule"));
// And a lower bound, which was missing: a ring that is not stretched onto its
// groove is loose on it. It slips out of the groove during assembly, sits
// crooked, or rolls -- and every squeeze figure here assumes it is seated.
assert(oring_stretch >= 0.01,
       str("O-ring install stretch is only ", oring_stretch*100,
           "%; below 1% the ring does not grip its groove and will not stay ",
           "seated during assembly"));
assert(oring_squeeze_real >= 0.15,
       str("squeeze after stretch-thinning is only ", oring_squeeze_real*100,
           "%; a static radial seal wants 15% or more"));
// The nominal squeeze is not the seal. THREE things vary, not two: the well
// bore, the carrier's groove root, and the cord of the ring itself. Squeeze is
// 1 - gland/cord, so the worst cases pair the extremes -- least squeeze is the
// widest gland on the thinnest cord, most is the narrowest gland on the fattest.
oring_cord_thin = 1 - oring_stretch/2;                 // stretch-thinning factor
oring_cord_min = (oring_cord - oring_cord_tol) * oring_cord_thin;
oring_cord_max = (oring_cord + oring_cord_tol) * oring_cord_thin;
oring_gland_min = ((well_d_made - groove_root_d) - seal_tol)/2;
oring_gland_max = ((well_d_made - groove_root_d) + seal_tol)/2;
oring_squeeze_max = (oring_cord_max - oring_gland_min) / oring_cord_max;
oring_squeeze_min = (oring_cord_min - oring_gland_max) / oring_cord_min;
// Feasibility BEFORE centring: the band the tolerances alone impose, in squeeze
// points, against the 15 the 15-30% window allows. If this fails, no value of
// oring_squeeze can rescue it -- the answer is a tighter bore, a tighter groove,
// sorted rings, or a fatter cord.
oring_band = oring_squeeze_max - oring_squeeze_min;
// What each contributor spends, so a failure says which one to attack.
oring_band_pair = seal_tol / oring_cord_fitted;
oring_band_cord = oring_band - oring_band_pair;
assert(oring_band <= 0.15,
       str("tolerance alone spans ", oring_band*100, " squeeze points -- ",
           oring_band_pair*100, " from the seal pair (well +/-", well_tol,
           ", carrier +/-", carrier_tol, ") and ", oring_band_cord*100,
           " from the cord itself (+/-", oring_cord_tol,
           ") -- against the 15 the 15-30% window allows. No squeeze value ",
           "satisfies both ends. Ream the well, machine the groove, sort the ",
           "rings by cord, or use a fatter cord"));
assert(oring_squeeze_min >= 0.15,
       str("at the loose end of the seal pair (gland +", seal_tol/2,
           ") squeeze falls to ", oring_squeeze_min*100,
           "%; below 15% this leaks. Raise oring_squeeze or hold a tighter bore"));
assert(oring_squeeze_max <= 0.30,
       str("at the tight end (gland -", seal_tol/2, ") squeeze reaches ",
           oring_squeeze_max*100,
           "%; above 30% a static O-ring takes compression set and the carrier ",
           "may not press in"));
// Groove fill. An overfilled gland hydraulically locks and extrudes the ring;
// nothing checked this before, because there was no gland to check.
oring_fill = (PI/4 * pow(oring_cord_fitted, 2))
             / (groove_w * (well_d_made - groove_root_d)/2);
// The nominal ring in the nominal gland is not the case that locks. The worst
// corner is the FATTEST ring in the SMALLEST gland: bore at its H7 minimum, root
// at its machined maximum, cord at catalogue maximum, and ID at catalogue maximum
// too -- a big ID stretches least, so it thins least and stays fattest.
oring_id_max = oring_id_ordered + oring_id_tol;   // DIN ISO 3601 d1 row
oring_root_max = groove_root_d + carrier_tol;
oring_stretch_min = oring_root_max/oring_id_max - 1;
oring_cord_fat = (oring_cord + oring_cord_tol) * (1 - oring_stretch_min/2);
oring_gland_tight = (well_d - oring_root_max)/2;   // H7 minimum IS the call-out
oring_fill_max = (PI/4 * pow(oring_cord_fat, 2)) / (groove_w * oring_gland_tight);
assert(oring_fill_max <= 0.85,
       str("worst-corner groove fill is ", oring_fill_max*100,
           "% (cord ", oring_cord_fat, " in a ", oring_gland_tight,
           " gland): the ring has nowhere to go, hydraulically locks and ",
           "extrudes past the land. Widen the groove or take a thinner cord"));
assert(oring_fill <= 0.85,
       str("groove is ", oring_fill*100,
           "% full; over 85% the ring has nowhere to go when squeezed"));

// What the spigot wall actually is, now that it has its own parameter: the
// material between the GAS BORE and the groove ROOT, which is where the section
// is thinnest and what a shrinking head eats into first. The old
// `mouth_d + 2*land` measured off a counterbore in the flange instead, so this
// number was never checked -- it happened to be 3.52 mm, comfortably over
// wall_min, and nothing would have said so had it not been.
spigot_groove_wall = (groove_root_d - spigot_bore)/2;
assert(spigot_groove_wall >= spigot_groove_wall_min - 1e-6,
       str("only ", spigot_groove_wall, " mm of spigot left under the O-ring ",
           "groove root (Ø", groove_root_d, " over a Ø", spigot_bore,
           " bore), against a ", spigot_groove_wall_min, " mm minimum. Raise ",
           "spigot_land, take a larger-ID ring, or accept a thinner section on ",
           "the part that carries the seal"));

// ---- membrane perimeter seal ------------------------------------------------
// The radial ring above gets six checks. This one had one -- the ledge, inside
// cartridge_core_cuts_round -- and it is the ring whose squeeze band is WORSE,
// because the cord tolerance is an absolute +/-0.08 in both cases and this cord
// is 1.0 rather than 1.5. Cord 1.0 is still the right call (it keeps gasket_gap
// at 0.750 and the 5 cm3 budget at its 3.0% margin, where cord 1.5 would cut
// that to 1.3%); the point is that the cost lands on tolerance and nothing said so.
mem_floor = 0.15;                    // same gas-sealing floor as the radial ring
mem_dtol_max = mem_depth_tol_max(mem_oring_cs, mem_floor);
// Feasibility BEFORE any process claim: if the cord band alone breaks the floor,
// a PERFECT groove cannot rescue it and the answer is a fatter cord or sorting.
assert(mem_clamped || mem_dtol_max > 0,
       str("cord tolerance alone (+/-", mem_cord_tol, " on a ", mem_oring_cs,
           " cord) puts squeeze at ", mem_squeeze_min(mem_oring_cs, 0)*100,
           "% before the groove depth errs at all, against a ", mem_floor*100,
           "% floor. No groove tolerance can satisfy this: take a fatter cord, ",
           "sort the rings by cord, or cut a deeper groove"));
// Worst corner for fill is the fattest cord in the shallowest groove the line
// above still permits -- against the REAL cavity, not the nominal annulus that
// groove_od() was sized from. On the sizing basis this same corner reads 100.4%
// and would fire a copied `oring_fill_max` assert spuriously.
mem_fill_worst = mem_fill_real(window_d, mem_oring_cs + mem_cord_tol,
                               gasket_gap - mem_dtol_max, heps);
assert(mem_clamped || mem_fill_worst <= 0.85,
       str("worst-corner membrane-groove fill is ", mem_fill_worst*100,
           "% (cord ", mem_oring_cs + mem_cord_tol, " in a ",
           gasket_gap - mem_dtol_max, " deep groove): the ring hydraulically ",
           "locks and extrudes into the flare cone"));
// Tripwire, not a discovery: with the cone defined from window_d outward this
// reduces to an identity, and it is kept so that a hand-set flare_inner or a
// moved pocket cannot quietly let the ring slide over the gas path -- which is
// exactly the failure the cut washer had. window_d is ALSO the retainer bore,
// so this is what guarantees the retainer still backs the ring where it lands.
mem_ring_inner_d = flare_d_at(cart_t - pocket_depth, window_d, heps);
assert(mem_clamped || mem_ring_inner_d >= window_d,
       str("the flare cone reaches ", mem_ring_inner_d, " at the groove floor, ",
           "inside the ", window_d, " window and the retainer bore: the ring ",
           "can slide over the gas path with nothing above it"));

// ---- membrane perimeter seal, CLAMPED BED -----------------------------------
// The bed in the retainer. Same six questions the radial ring answers, asked of
// a ring that is IN THE DRAWER rather than in a catalogue -- so the first thing
// to say about it is that its dimensions are nominal until someone puts a
// micrometer on one.
//
// Sorting is the lever this bed leans on, and unlike the radial ring's it costs
// nothing to pull: the rings are here, and the cord band is what sets both
// tolerance ends below.
// SORTING IS NOT OPTIONAL ON THIS BED and the model now says so by failing.
// With the 20% floor, the catalogue cord band alone (+/-0.09 on a 2.5 cord)
// leaves no groove depth on the 0.12 mm layer grid that holds 20-30% across the
// corners -- 1.80 is too shallow at the fat corner and the next step down, 1.68,
// reaches 33%. Micrometering the rings on receipt collapses the band to +/-0.01
// and the depth closes with room to spare. The Makefile's ASA target sets this;
// the default stays "catalogue" so that anyone who has NOT sorted gets the
// failure rather than the part.
face_sorting = "catalogue";      // "catalogue" | "sorted" (micrometered on receipt)
face_cord_tol_eff = (face_sorting == "sorted") ? 0.01 : face_cord_tol;
// 0.20, not 0.15. Parker ORD 5700 Design Chart 4-3, p. 4-18, gives 20-30% for
// the nearest FACE-SEAL cross-section (0.103 in / 2.62 mm). The 15% floor this
// carried is the RADIAL rule, copied across from the carrier-to-head ring, and a
// face seal is not a radial one: it has no gland-fill-driven energisation to
// fall back on. Raised on the ORD-5700 review, 2026-09-05. It is the change that
// makes the catalogue-ring build fail, which is the point -- it was already
// failing, silently.
face_floor = 0.20;
face_ceiling = 0.30;             // takes compression set above it
face_dtol_max = face_depth_tol_max(window_d, face_floor, face_cord_tol_eff);
face_dtol_min = face_depth_tol_min(window_d, face_ceiling, face_cord_tol_eff);
face_gap_nom = face_gap(window_d);
face_cord_fit = face_cord_fitted(window_d);
face_sq_nom = face_squeeze(window_d, face_cord_fit, face_gap_nom);

// Feasibility BEFORE any process claim, exactly as the legacy bed asks it: if
// the cord band alone breaks a limit, a perfect groove cannot rescue it.
assert(!mem_clamped || face_dtol_max > 0,
       str("cord tolerance alone (+/-", face_cord_tol_eff, " on a ",
           face_ring_cord, " cord) puts squeeze under the ", face_floor*100,
           "% floor before the groove depth errs at all. Sort the rings, or ",
           "cut the groove one layer shallower"));
assert(!mem_clamped || face_dtol_min > 0,
       str("cord tolerance alone (+/-", face_cord_tol_eff, ") puts squeeze over ",
           face_ceiling*100, "% before the groove depth errs at all: the ring ",
           "takes compression set. Sort the rings, or cut one layer deeper"));

// Install stretch, at both ends of the ring's OWN ID band -- the nominal cannot
// fail, and it is the thin-ID ring that overstretches.
face_stretch_nom = face_stretch(window_d);
face_stretch_max = face_groove_id(window_d)/(face_ring_id - face_id_tol) - 1;
assert(!mem_clamped || face_stretch_max <= 0.05,
       str("install stretch reaches ", face_stretch_max*100, "% on a ",
           face_ring_id - face_id_tol, " ID ring (DIN band +/-", face_id_tol,
           "), against the 5% rule. Narrow the inner wall, or take a larger ID"));

// Worst corner for fill: fattest cord in the shallowest groove the ceiling
// still permits. A locked ring cannot be squeezed the last few points and the
// retainer then stops bottoming, which is what makes squeeze geometric.
face_fill_worst = face_fill(window_d,
                            face_cord_fitted(window_d, face_ring_cord + face_cord_tol_eff),
                            face_gap_nom - face_dtol_min);
assert(!mem_clamped || face_fill_worst <= 0.85,
       str("worst-corner bed fill is ", face_fill_worst*100,
           "%: the ring hydraulically locks. Raise face_groove_w_factor"));

// The membrane disc has to fit between the groove and the bolt circle, and this
// is the dimension that killed the Ø20 x 2 alternative -- its disc lands at
// Ø28.0 against a bolt-hole inner edge at Ø29.3.
face_disc_edge = bolt_r - m2_clear/2 - (face_disc_d(window_d) + 0.4)/2;
assert(!mem_clamped || face_disc_edge >= 0.8,
       str("the Ø", face_disc_d(window_d) + 0.4, " membrane seat leaves only ",
           face_disc_edge, " mm to the bolt holes on a Ø", 2*bolt_r,
           " circle. Reduce face_disc_ledge or face_groove_w_factor, or take a ",
           "smaller-ID ring"));

// What is left of the retainer over the groove. This is why retainer_t moved to
// 4.0: the web reacts the ring, and a web that bows gives squeeze back.
face_web = retainer_t - face_seat_depth - face_groove_depth(window_d);
assert(!mem_clamped
       || abs((retainer_t - face_first_layer_h)/face_layer_h
              - round((retainer_t - face_first_layer_h)/face_layer_h)) < 1e-9,
       str("retainer height ", retainer_t, " is not first_layer + n x ",
           face_layer_h, ": its TOP FACE is the bed's reference plane, and an ",
           "unquantized height leaves the slicer to place it"));
assert(!mem_clamped || face_web >= 1.6,
       str("only ", face_web, " mm of retainer over the bed groove: it bows ",
           "under the ring and bleeds off the squeeze the groove depth sets"));

// Tripwires. Both reduce to identities as written, and both are kept because a
// hand-set depth or a re-sliced layer height is exactly how this bed goes back
// to being unprintable without anything complaining.
// The ladder is measured FROM THE PLATE, so the datum moves with the flip:
// subtract it before asking whether the depth is a whole number of layers.
// Checking bare multiples of face_layer_h was right only for groove-up, and
// would reject the correct groove-down depth while accepting a wrong one.
assert(!mem_clamped
       || abs((face_groove_depth(window_d) - face_depth_datum())/face_layer_h
              - round((face_groove_depth(window_d) - face_depth_datum())/face_layer_h)) < 1e-9,
       str("groove depth ", face_groove_depth(window_d), " is not ",
           face_depth_datum(), " + an integer ",
           "number of ", face_layer_h, " mm layers, so the SLICER picks the ",
           "depth and the slicer does not know it is a seal dimension"));
// 1e-9 slack because face_groove_id is DERIVED from window_d + 2*face_wall_min:
// the check is a round trip through binary floats, and 15.2 + 2.4 - 15.2 is not
// exactly 2.4. Without the slack this fires on the very value it is checking.
// It still earns its keep -- it catches an OVERRIDDEN face_groove_id.
assert(!mem_clamped ||
       (face_groove_id(window_d) - window_d)/2 >= face_wall_min - 1e-9,
       str("the bed's inner wall is ", (face_groove_id(window_d) - window_d)/2,
           " mm: under ", face_wall_min, " it is a sliver, not ",
           face_wall_min/face_line_w, " beads"));

// ---- seal-land thermometry --------------------------------------------------
//
// The ledge and seal-groove clearances are the module's own; it owns the
// geometry that decides them.
cbore_wall = bolt_r - bolt_cut_max/2 - well_d/2;
assert(cbore_wall >= cut_seal_wall_min - 1e-6,
       str("the widest bolt-circle cut (", bolt_cut_max,
           " mm) leaves only ", cbore_wall,
           " mm to the sealing well; a change to insert_head_d or ",
           "insert_seal_wall can walk it into the O-ring seat with every other ",
           "assert still passing"));
// Tripwire only: with bolt_r derived this reduces to an identity, and it is kept
// so a hand-set bolt_r cannot quietly move the load-bearing hole inward.
assert(bolt_r - fast_hole_d/2 - well_d/2 >= fast_seal_wall - 1e-6,
       str("only ", bolt_r - fast_hole_d/2 - well_d/2,
           " mm of wall between the fastener hole and the O-ring's sealing bore; ",
           use_insert ? "heat-setting there will distort the seat"
                     : "thread-forming hoop stress there will deform the seat"));
assert(fast_hole_h <= head_len - socket_len - 2.0,
       "insert bore deeper than the material behind the end face");
assert(2*bolt_r + m2_clear + 2.0 <= flange_d,
       "bolt circle falls outside the carrier flange: the retainer would clamp nothing");
assert(bolt_r - m2_clear/2 >= spigot_d/2,
       str("the screw clearance hole through the carrier flange would break into ",
           "the spigot bore: bolt circle radius ", bolt_r, " minus half a ",
           m2_clear, " hole lands inside the ", spigot_d/2, " mm spigot"));
assert(flange_d <= head_od,
       str("carrier flange ", flange_d, " overhangs a ", head_od, " mm head"));
// The cap screws are RADIAL, so what they must clear is whatever void sits at
// THEIR height -- not the narrowest void in the head. Checking neck_d was wrong:
// the neck ends at well_z, well below them. They sit cap_grip/2 down from the
// end face, which is inside the Ø27.3 well, and cap_screw_depth=8 breaks into
// it while every assert passes and CGAL still reports one closed solid.
cap_screw_z0 = head_len - cap_grip/2 - selftap_cap/2;
cap_screw_z1 = head_len - cap_grip/2 + selftap_cap/2;
function spans(a0, a1, b0, b1) = (a0 < b1 && b0 < a1);
cap_screw_void_r = max(
    spans(cap_screw_z0, cap_screw_z1, 0, socket_len)
        ? (tube_od_meas + 2*bond_gap)/2 : 0,
    spans(cap_screw_z0, cap_screw_z1, socket_len, socket_len + cav_board_len)
        ? bore_d/2 : 0,
    spans(cap_screw_z0, cap_screw_z1, socket_len + cav_board_len, well_z)
        ? neck_d/2 : 0,
    spans(cap_screw_z0, cap_screw_z1, well_z, head_len)
        ? well_d/2 : 0,
    spans(cap_screw_z0, cap_screw_z1, head_len - lead_chamfer, head_len)
        ? well_d/2 + lead_chamfer : 0);
assert(head_od/2 - cap_screw_depth > cap_screw_void_r + 1.0,
       str("blind cap screw reaches r=", head_od/2 - cap_screw_depth,
           " but the void at z=", cap_screw_z0, "..", cap_screw_z1,
           " runs out to r=", cap_screw_void_r, ": outside-to-gas leak path"));
// CONE BED ONLY. That bed's core comes out of membrane_cartridge_common.scad,
// which measures every feature down from cart_t, so a flange that is not cart_t
// thick either seals the membrane off or leaves the core hanging in air. The
// clamped bed cuts its own frustum from flange_t and is free of this -- see the
// note where flange_t is defined.
assert(mem_clamped || abs(flange_t - cart_t) < 0.001,
       "flange must equal cart_t on the cone bed, else the sealing core does not reach the flange's gas face and the membrane is sealed off");
assert(flange_t >= 2.0,
       "carrier flange under 2 mm: too thin to clamp without dishing");
assert(cap_len - cap_grip - cap_front_t >= flange_t + retainer_t + 2.0,
       "cap pocket too shallow: its front face would land on the retainer and crush the clamped stack");
assert(guard_open >= guard_open_factor * window_area,
       str("guard open area ", guard_open, " mm2 is under ", guard_open_factor,
           "x the window's ", window_area,
           " mm2 -- the guard, not the membrane, would set the response time"));
assert(cav_net <= 5000,
       str("connected volume ", cav_net/1000, " cm3 exceeds the 5.0 cm3 target"));

echo(str("MEASURED IN: tube OD ", tube_od_meas, ", board swept ", board_swept,
         ", cell seated ", cell_seated_h, " (mount ", cell_mount,
         cell_standing ? "" : str(", axial ", cell_axial_len), ")"));
echo(str("GAS PATH membrane -> cell face: ", flange_t, " (flange core) + ",
         spigot_len, " (spigot bore) = ", flange_t + spigot_len, " mm axial",
         cell_standing
         ? str(", then ", cell_setback, " mm back down the bore to a RADIAL gas ",
               "face -- the cell stands on the board, so the path turns. ",
               "PROTOTYPE-RESPONSE.md's 5-10 mm cell-to-membrane figure was ",
               "written for the axial mount and does not describe this one.")
         : " straight onto the cell face."));
// MACHINE-READ, by tools/board_tip.py, which has to place the KiCad board mesh
// in head coordinates and must not keep its own copy of this arithmetic. It kept
// one -- a literal -152 in its matrix, right for the monolithic joint -- and the
// head-end viewer drew the PCB 11 mm too deep for as long as that scene existed.
// board_tip_z is no longer regex-readable out of this file anyway: socket_len is
// a ternary and cav_board_len is a max(), so the value has to come from a render.
// KEEP THE SPELLING STABLE -- the parser matches on it.
echo(str("INTERFACE board_tip_z ", board_tip_z, " head_len ", head_len,
         " well_z ", well_z, " cav_board_len ", cav_board_len,
         " socket_len ", socket_len, " joint ", joint));
echo(str("bore ", bore_d, "; head OD ", head_od, "; cap OD ", cap_od,
         " mm -- widest point of the probe"));
echo(str("window dia ", window_d, " -> ", PI*pow(window_d/2,2), " mm2 free area"));
echo(str("PP carrier: spigot dia ", spigot_d, " x ", spigot_len,
         ", bore ", spigot_bore, "; flange dia ", flange_d, " x ", flange_t));
echo(str("head OD is set by the fastening: bolt circle dia ", 2*bolt_r,
         " from a ", fast_hole_d, " hole with ", fast_seal_wall,
         " mm to the sealing bore"));
echo(str("SIZE: head ", head_od, " / cap ", cap_od, " mm. The electronics want ",
         "only ", 2*(bore_d/2 + wall_min), " -- the rest is the bolt circle, so ",
         "this head is as wide as it is because of HOW THE MEMBRANE IS CLAMPED, ",
         "not what is inside it. spigot_land ", spigot_land, " (split out of ",
         "land ", land, ") leaves ", spigot_groove_wall, " mm under the groove ",
         "root against a ", wall_min, " minimum. NEXT STEP DOWN is not CAD: at ",
         "spigot_land 2.125 the sourced Ø", oring_id_ordered,
         " ring stops gripping, so a narrower spigot needs a smaller-ID ring ",
         "(~Ø22 x ", oring_cord, ", EPDM 70 peroxide) -- a sourcing action. ",
         "Deleting the bolt circle outright, now that the O-ring sets squeeze ",
         "by GEOMETRY and the screws carry no seal load, would reach ",
         2*(bore_d/2 + wall_min), " mm."));
echo(str("RADIAL O-RING ", onhand_ring
         ? "ON HAND, UNCATALOGUED -- material, cure system and cord band all ASSUMED; the ORS116787 compound test report does NOT cover it. TEMPORARY"
         : "ORS116787, EPDM 70 peroxide", ", ", oring_id_ordered, " x ", oring_cord,
         " on a ", groove_root_d, " x ", groove_w, " groove: ", oring_stretch*100,
         "% install stretch, ", oring_squeeze_real*100, "% squeeze after thinning; ",
         oring_squeeze_min*100, "-", oring_squeeze_max*100, "% worst case; groove ",
         oring_fill*100, "% full"));
echo(str("TOLERANCE BUDGET: ", oring_band*100, " of 15 squeeze points -- ",
         oring_band_pair*100, " seal pair (well ", well_finish, " +/-", well_tol,
         " [ISO 286-2 H7], carrier ", carrier_fab, " +/-", carrier_tol, "), ",
         oring_band_cord*100, " cord (", oring_sorting, " +/-", oring_cord_tol,
         " [DIN ISO 3601, d2<=1.8])"));
echo(str("CARRIER: ", carrier_material, carrier_is_pp
         ? " -- machined PP-H, membrane WELDABLE into it (production route)"
         : str(" -- printed like the head. NO weld is possible to ASA, so the ",
               "membrane is compression-only, and a styrenic under sustained ",
               "gasket load in NH3 is an environmental-stress-cracking risk")));
if (!mem_clamped) {
    echo(str("MEMBRANE SEAL: O-ring ", gasket_id(window_d), " x ", mem_oring_cs,
             " -- o-ring-stocks.eu ORS116731, EPDM 70 Shore A peroxide, material ",
             "127019011 (the SAME compound as the carrier ring ORS116787, so one ",
             "test report covers both). Groove Ø", groove_od(window_d), " x ",
             gasket_gap, " deep, bounded inward NOT by a wall but by the flare cone ",
             "at Ø", mem_ring_inner_d, ": achieved fill ",
             mem_fill_real(window_d, mem_oring_cs, gasket_gap, heps)*100, "%, which ",
             "is NOT the ", mem_oring_fill*100, "% sizing basis groove_od() solved ",
             "against a nominal annulus from Ø", gasket_id(window_d),
             ". Membrane ledge ", membrane_ledge(window_d), " mm. Bore clears ",
             "the flare (", flare_d_at((cart_t - membrane_t)
                                       - gasket_t*(1 - gasket_squeeze),
                                       window_d, heps),
             " at the ring's far end, where the cone is widest), so it seals beside ",
             "the gas path, not in front of it."));
    echo(str("MEMBRANE SEAL squeeze is set by GEOMETRY, not screw torque -- the ",
             "retainer bottoms on the ledge -- nominal ",
             (1 - gasket_gap/mem_oring_cs)*100, "%. REQUIREMENT: hold the groove ",
             "depth to +/-", mem_dtol_max, " mm, or squeeze falls under ",
             mem_floor*100, "%. Cord tolerance alone (+/-", mem_cord_tol,
             ", DIN ISO 3601 d2<=1.8) already spans ",
             mem_squeeze_min(mem_oring_cs, 0)*100, "-",
             mem_squeeze_max(mem_oring_cs, 0)*100, "% = ",
             (mem_squeeze_max(mem_oring_cs, 0)
              - mem_squeeze_min(mem_oring_cs, 0))*100, " points on CATALOGUE cord. ",
             "The radial ring spends ", oring_band_cord*100, " (", oring_sorting,
             ") on a 1.5 cord; sorting is open to both rings and is the same lever ",
             "here. ",
             "Worst-corner fill ", mem_fill_worst*100, "%."));
} else {
    echo(str("MEMBRANE BED (clamped, printable): O-ring ", face_ring_id, " x ",
             face_ring_cord, " -- ON HAND, uncatalogued, dimensions NOMINAL ",
             "until micrometered. Groove Ø", face_groove_id(window_d), "/Ø",
             face_groove_od(window_d), " x ", face_groove_depth(window_d),
             " deep = ", face_groove_depth(window_d)/face_layer_h, " layers of ",
             face_layer_h, ", cut into the RETAINER underside over a flat ",
             "carrier land. Inner wall ", (face_groove_id(window_d) - window_d)/2,
             " mm on the Ø", window_d, " bore -- the legacy bed had none. ",
             "Membrane disc Ø", face_disc_d(window_d), " in a Ø",
             face_disc_d(window_d) + 0.4, " seat, ", face_disc_edge,
             " mm clear of the bolt holes."));
    echo(str("MEMBRANE BED squeeze is set by GEOMETRY -- the retainer bottoms on ",
             "the carrier face outside the seat -- nominal ", face_sq_nom*100,
             "% on a cord thinned to ", face_cord_fit, " by ",
             face_stretch_nom*100, "% install stretch (", face_stretch_max*100,
             "% on a thin-ID ring). REQUIREMENT: hold the assembled gap ",
             face_gap_nom, " to +", face_dtol_max, "/-", face_dtol_min,
             " mm, or squeeze leaves ", face_floor*100, "-", face_ceiling*100,
             "%. The tighter end is the ",
             (face_dtol_max < face_dtol_min) ? "FLOOR, and that is the one that leaks"
                                             : "CEILING, the benign one -- compression set over years against a leak now",
             ". Cord band ",
             "+/-", face_cord_tol_eff, " (", face_sorting, ") = ",
             (face_squeeze(window_d, face_cord_fitted(window_d, face_ring_cord - face_cord_tol_eff), face_gap_nom)
              - face_squeeze(window_d, face_cord_fitted(window_d, face_ring_cord + face_cord_tol_eff), face_gap_nom))*-100,
             " squeeze points; the same absolute +/-0.08..0.09 costs 12.1 points ",
             "on the legacy 1.0 cord, which is the whole case for the fat ring. ",
             "Worst-corner fill ", face_fill_worst*100, "%."));
    echo(str("MEMBRANE BED printability: no feature under one layer. The carrier ",
             "keeps its wet face DOWN on the plate (the flange overhangs the ",
             "spigot by ", (flange_d - spigot_d)/2, " mm, so it cannot print the ",
             "other way up) and its aperture opens downward as a ",
             atan(((spigot_bore - window_d)/2)/flange_t), " degree cone. The ",
             "retainer prints ",
             face_groove_up
               ? str("GROOVE UP: nothing bridges, and the groove depth is laid ",
                     "on solid material. Its sealing face is a TOP surface.")
               : str("GROOVE DOWN: its sealing face is the FIRST LAYER against ",
                     "the plate, and the groove roof BRIDGES ",
                     face_groove_w(), " mm anchored on both walls. That roof is ",
                     "what the O-ring bottoms on, so droop there moves squeeze."),
             " Slice at ", face_layer_h, " mm layers or re-derive the depth."));
}
echo(str("MEMBRANE SEAL preload: UNVERIFIED. Sized on geometry only. The washer ",
         "bracket (38-115 N/screw) does NOT transfer -- an O-ring seals on a ",
         "line at far lower load. Measure it. RISK: line contact on 0.18 mm ",
         "porous PTFE may cold-flow and relax; absent if the membrane is welded ",
         "into a PP cartridge and this joint becomes PP-on-ASA."));
echo(str("CUT LIST: PMV15T disc dia ",
         mem_clamped ? face_disc_d(window_d) : window_d + 2*land,
         carrier_is_pp && !mem_clamped ? " mm, welded into the carrier"
                                       : " mm, clamped between retainer and carrier"));
// Sizes come from the parameters, not from a literal: this echo said "M2.5" for
// a day after the fasteners were M2 because both were typed in by hand.
echo(str("fasteners: ", bolt_n, "x ",
         use_insert ? "M2 into PEM IUTFC-M2 heat-set inserts"
                    : "M2 A2 machine screws direct into printed bosses",
         " on a dia ",
         2*bolt_r, " bolt circle; ", cap_screw_n,
         "x M2 self-tapping for the cap, counterbored, ",
         cap_screw_depth - pt_cbore_h, " mm engagement (no seal load)"));
// Bore sections only -- UNDERSTATES, the aperture stack is connected gas too.
// Build `cavity` and measure the mesh; that is the number that governs.
echo(str("connected volume ", cav_net/1000,
         " cm3 (bore sections only -- measure the `cavity` mesh)"));
echo(str("head length ", head_len, " mm"));

// ------------------------------------------------- head

module bolt_positions() {
    for (i = [0:bolt_n-1]) rotate([0, 0, i*360/bolt_n]) translate([bolt_r, 0, 0])
        children();
}

module cap_screw_positions() {
    // Local to whichever body calls it: children are placed on the +X radius at
    // the caller's own z. The earlier version baked in the head's absolute z and
    // silently missed the cap entirely.
    for (i = [0:cap_screw_n-1])
        rotate([0, 0, 90 + i*360/cap_screw_n]) rotate([0, 90, 0]) children();
}

module head() {
    difference() {
        if (monolithic) {
            // Ø32 at z=0, opening out to the head's Ø40 on a 45 deg cone. Below
            // z=0 the printed tube continues in the same plastic.
            union() {
                cylinder(d1=tube_od_nominal, d2=head_od, h=join_cone);
                translate([0, 0, join_cone])
                    cylinder(d=head_od, h=head_len - join_cone);
            }
        } else {
            cylinder(d=head_od, h=head_len);
        }

        // Bonded socket over the tube end. Absent when monolithic: there is no
        // tube end to socket, and leaving it would put a 0.2 mm annular void
        // inside the solid.
        if (!monolithic)
            translate([0, 0, -heps])
                cylinder(d=tube_od_meas + 2*bond_gap, h=socket_len + heps);

        // Cavity: full bore only where the board is, then necked to the cell.
        // Monolithic, the bore starts at z=0 instead of at the socket floor --
        // otherwise the board could not reach the cavity at all.
        translate([0, 0, monolithic ? -heps : socket_len])
            cylinder(d=bore_d, h=(monolithic ? socket_len + heps : 0) + cav_board_len);
        // Only the past-end mount has a neck. A zero-height cylinder is not a
        // no-op in CGAL, it is a degenerate solid, so this is a branch and not
        // an h=0.
        if (has_neck)
            translate([0, 0, socket_len + cav_board_len])
                cylinder(d=neck_d, h=cav_clear_len + heps);

        // The well the spigot seals into. Its bore IS the sealing surface, so it
        // wants to be printed cleanly -- it is the one feature here whose
        // surface finish is functional.
        translate([0, 0, well_z]) cylinder(d=well_d, h=head_len);
        // Lead-in, so the O-ring is not shaved on assembly.
        translate([0, 0, head_len - lead_chamfer])
            cylinder(d1=well_d, d2=well_d + 2*lead_chamfer, h=lead_chamfer + heps);

        // Fastener holes on the bolt circle, blind from the end face. BOTH
        // routes get a counterbore, for different reasons.
        bolt_positions() {
            translate([0, 0, head_len - fast_hole_h])
                cylinder(d=fast_hole_d, h=fast_hole_h + heps);
            // Insert: it is made flanged only, and a proud flange would hold the
            // retainer off the face.
            if (use_insert)
                translate([0, 0, head_len - insert_head_t - 0.1])
                    cylinder(d=insert_head_d + 0.3, h=insert_head_t + 0.2);
            // Thread-forming: EJOT's counterbore is STRUCTURAL, not cosmetic --
            // it relieves edge stress at the mouth of the boss, which is where
            // the boss cracks as the thread forms, and it guides the screw in
            // for the first turn. Omitting it was a real defect, not a
            // simplification.
            else
                translate([0, 0, head_len - pt_cbore_h])
                    cylinder(d=pt_cbore_d, h=pt_cbore_h + heps);
        }

        // Cap retention: BLIND radial holes that stop well short of the bore.
        //
        // COUNTERBORED SINCE 2026-09-05, and this was a real defect, not a
        // refinement. These holes were a bare selftap_cap cylinder -- which is
        // station 4 of the fastener coupon exactly, the one Fab drove and found
        // TOO SMALL, against station 3 (same pilot, counterbored) which he chose
        // for the retainer. The retainer screws got the counterbore in the same
        // pass and these did not, so the head would have shipped with two holes
        // built to the geometry the coupon had just rejected.
        //
        // The lead-in is what the screw needs to START; a 60-degree ISO flank
        // entering bare printed plastic has nothing to centre on and nowhere for
        // the first displaced material to go. That is worse here than on the
        // retainer face, because these are RADIAL, so the screw starts on a
        // CURVED surface and the counterbore is also what gives it a flat.
        translate([0, 0, head_len - cap_grip/2])
            cap_screw_positions()
                translate([0, 0, head_od/2 - cap_screw_depth]) {
                    cylinder(d=selftap_cap, h=cap_screw_depth + heps);
                    translate([0, 0, cap_screw_depth - pt_cbore_h])
                        cylinder(d=pt_cbore_d, h=pt_cbore_h + heps);
                }
    }
}

// The PP part. Printed here as a FIT MODEL only: the real one is polypropylene,
// with the PMV15T coupon fused into it. A printed disc is not a membrane.
// An outward-facing cut: everything from `root_d` out to beyond the spigot,
// over height h. Subtracting a centred solid instead is the defect this exists
// to prevent -- it removes the bore, which is inboard of every external feature.
module ring_cut(root_d, h) {
    difference() {
        cylinder(d=spigot_d + 2, h=h);
        translate([0, 0, -heps]) cylinder(d=root_d, h=h + 2*heps);
    }
}

module carrier() {
    difference() {
        union() {
            cylinder(d=spigot_d, h=spigot_len);
            translate([0, 0, spigot_len]) cylinder(d=flange_d, h=flange_t);
        }
        // Gas path straight through the spigot into the flare above it.
        translate([0, 0, -heps]) cylinder(d=spigot_bore, h=spigot_len + 2*heps);
        // Radial O-ring groove. This is the seal. It must be cut as an ANNULUS
        // off the spigot's OUTSIDE: a centred cylinder here bores the gas path
        // out to the groove root instead, which is silently a bigger cavity and
        // no groove at all.
        translate([0, 0, lead_chamfer + 0.75]) ring_cut(groove_root_cut, groove_w);
        // Lead-in chamfer on the spigot's leading edge -- annular for the same
        // reason: a centred cone opens the bore rather than breaking the edge.
        translate([0, 0, -heps])
            difference() {
                cylinder(d=spigot_d + 2, h=lead_chamfer + heps);
                translate([0, 0, -heps])
                    cylinder(d1=spigot_d - 2*lead_chamfer, d2=spigot_d,
                             h=lead_chamfer + 3*heps);
            }
        // The sealing core, in the flange, wet face at +Z. Under the clamped
        // bed there is no core to speak of: the bed moved into the retainer and
        // what is left is ONE tapered aperture, landing exactly on the spigot
        // bore so the part contains no ledge, no sub-layer step and no bridge.
        translate([0, 0, spigot_len])
            if (mem_clamped) clamped_core_cuts(window_d, spigot_bore, flange_t, heps);
            else cartridge_core_cuts_round(window_d, heps);
        // The flange sits between the retainer and the head's end face, so the
        // clamping screws pass THROUGH it. Without these it is 5 mm of solid PP
        // in front of every boss and nothing can be assembled.
        translate([0, 0, spigot_len - heps])
            bolt_positions() cylinder(d=m2_clear, h=flange_t + 2*heps);
    }
}

// z = 0 is the UNDERSIDE, the face that meets the carrier -- which is where the
// clamped bed lives. retainer_printed() flips it, so the groove is cut downward
// into solid material on the plate rather than bridged over air.
module retainer() {
    difference() {
        cylinder(d=flange_d, h=retainer_t);
        translate([0, 0, -heps]) cylinder(d=window_d, h=retainer_t + 2*heps);
        if (mem_clamped) clamped_bed_cuts(window_d, heps);
        translate([0, 0, -heps])
            bolt_positions() cylinder(d=m2_clear, h=retainer_t + 2*heps);
    }
}

// VOID COUPON -- one bolt hole and about 1 cm2 of the flange around it.
//
// Three hypotheses for the voids around the bolt holes have now died: that six
// perimeters cannot fit the rim (rim fill is BETTER at six), that the top surface
// pattern causes it (monotonic on top voided anyway), and that thin-wall slivers
// go unfilled (the slice emits no gap infill at all). Each cost a 25-minute plate
// to reject. This coupon costs minutes, so settings can be swept instead of
// guessed.
//
// It is built from the real parameters, not redrawn, so it cannot drift from the
// part. What must be preserved is not the hole but the RIM OUTBOARD OF IT: the
// hole edge sits 2.0 mm from the flange OD, and that is the constrained dimension
// every dead hypothesis was about. The true arc is kept for the same reason -- a
// straight outer edge changes how the perimeters pack.
coupon_sweep = 50;                  // degrees, sized for ~1 cm2 of face

// The artificial inner edge has to be FAR ENOUGH IN, and the first version was not.
// Measured on the first coupon: its whole cross-section came out as perimeters, with
// ZERO bottom-surface infill, against 564 bottom-surface moves on the real part's
// first layer. The perimeter field from the free inner edge had collided with the
// hole's own, so the hole sat in colliding Arachne beads instead of the solid infill
// it sits in on the flange -- a different structure, and one that generates its own
// four-fold artifacts around a round hole. The coupon was measuring itself.
//
// So the inner edge is now placed so that wall_loops of the WIDEST line width we
// might slice at still cannot reach the hole, and it is asserted rather than trusted.
coupon_wall_reach = 6 * 0.70;       // wall_loops x widest line width considered
coupon_r_in  = bolt_r - m2_clear/2 - coupon_wall_reach - 1.5;
// DECOUPLED FROM flange_d ON 2026-09-05. This coupon is a CONTROL SPECIMEN: its
// job is to keep reproducing the 2.0 mm rim the voids appear in, so that the
// fix can be judged against it. Once the flange rim was corrected to 2.4 (four
// whole beads) a coupon derived from flange_d stopped reproducing the defect
// and the assert below said so, correctly. Sweep it to compare: the interesting
// pair is 2.0 (3.33 beads, defect) against 2.4 (4.00 beads, fix).
coupon_rim   = 2.0;
coupon_od    = 2*(bolt_r + m2_clear/2 + coupon_rim);
assert(coupon_r_in + coupon_wall_reach < bolt_r - m2_clear/2,
       str("coupon inner edge r=", coupon_r_in, " is too close: its perimeter field ",
           "reaches r=", coupon_r_in + coupon_wall_reach, " and the hole starts at r=",
           bolt_r - m2_clear/2, " -- the coupon would measure its own free edge"));
assert(coupon_r_in > 0, str("coupon inner radius went negative: ", coupon_r_in));
// The rim is now an input rather than a consequence, so the check that matters
// is that it is a REAL width to print, not that it equals 2.0 -- pinning 2.0
// would forbid the very comparison this coupon exists to make.
assert(coupon_rim >= face_line_w,
       str("coupon rim ", coupon_rim, " mm is under one ", face_line_w,
           " bead: there is no wall left to void"));
echo(str("VOID COUPON: hole dia ", m2_clear, " at r ", bolt_r,
         ", rim outboard ", coupon_rim, " mm, face area ",
         (coupon_sweep/360)*PI*(pow(coupon_od/2,2)-pow(coupon_r_in,2)), " mm2",
         "; rim = ", coupon_rim/face_line_w, " beads at ", face_line_w));

module void_coupon(t) {
    intersection() {
        difference() {
            cylinder(d=coupon_od, h=t);
            translate([0, 0, -heps]) cylinder(d=2*coupon_r_in, h=t + 2*heps);
            translate([bolt_r, 0, -heps]) cylinder(d=m2_clear, h=t + 2*heps);
        }
        rotate([0, 0, -coupon_sweep/2])
            linear_extrude(t + 2*heps)
                polygon([[0, 0], [coupon_od, 0],
                         [coupon_od*cos(coupon_sweep), coupon_od*sin(coupon_sweep)]]);
    }
}

// Both thicknesses that showed the defect: the retainer voided on BOTH faces, the
// carrier flange only on the face the bed did not press flat. Same plate, so a
// settings change is judged against both at once.
module coupon_plate() {
    translate([0, 0, 0])  void_coupon(retainer_t);
    translate([0, 14, 0]) void_coupon(cart_t);
}

// ---- FASTENER COUPON -------------------------------------------------------
//
// A different coupon from void_coupon above, testing a different thing. That one
// is about how the SLICER fills a rim; this one is about whether the fastener
// geometry works in the material: whether a PEM IUTFC-M2 heat-sets square and
// flush into a 3.23 hole, whether a DELTA PT 20 forms a thread in a 1.60 pilot
// without splitting the boss, and how much torque either takes before it strips.
// It exists because both routes are now dimensioned from vendor design guides
// and NOTHING has been put in ASA yet -- the guides are written for moulded
// bosses, and a printed boss is layered, anisotropic and weakest exactly where
// the hoop stress is.
//
// Built from the head's own parameters, like every other coupon here, so it
// cannot drift from the part.
//
// PRINTED THE SAME WAY UP AS THE HEAD. The head prints cable-end-down, so its end
// face -- the face these holes enter -- is the TOP of the print. A coupon printed
// the other way up would test thread-forming against a different layer structure
// than the part has, and would pass or fail for the wrong reason.
fcoup_wall   = 2.3;                 // to the free edge: insert_seal_wall, the
                                    // bigger of the two routes' walls, so one
                                    // coupon carries both
fcoup_floor  = 1.5;                 // material under the deepest blind hole
fcoup_t      = max(insert_bore_h, 2*pt_nominal + pt_cbore_h) + fcoup_floor;
fcoup_pitch  = 2*(insert_bore_d/2 + fcoup_wall);   // hole spacing, walls touching
// Four stations, left to right, all at full depth:
//   0  insert hole, 3.23 + counterbore for the flange   -- heat-set one in
//   1  insert hole DELIBERATELY 0.1 TIGHT (3.13)        -- the bracket, to find
//      out which side of the +0.08/-0.00 tolerance a printed hole lands on
//   2  thread-forming pilot 1.60 + 2.10 x 1.00 counterbore
//   3  thread-forming pilot with NO counterbore         -- the control for
//      EJOT's claim that the counterbore is what stops the boss cracking
fcoup_n = 4;
fcoup_len = fcoup_n*fcoup_pitch + 2*fcoup_wall;
echo(str("FASTENER COUPON: ", fcoup_len, " x ", fcoup_pitch + 2*fcoup_wall,
         " x ", fcoup_t, " mm; stations insert ", insert_bore_d, ", insert ",
         insert_bore_d - 0.1, " (tight), PT ", pt_pilot_d, " + cbore, PT ",
         pt_pilot_d, " bare; wall to free edge ", fcoup_wall));

module fastener_coupon() {
    w = fcoup_pitch + 2*fcoup_wall;
    difference() {
        translate([0, -w/2, 0]) cube([fcoup_len, w, fcoup_t]);
        for (i = [0:fcoup_n-1]) {
            x = fcoup_wall + fcoup_pitch/2 + i*fcoup_pitch;
            translate([x, 0, 0]) {
                if (i < 2) {
                    d = insert_bore_d - (i == 1 ? 0.1 : 0) + insert_filler_add;
                    translate([0, 0, fcoup_t - insert_bore_h])
                        cylinder(d=d, h=insert_bore_h + heps);
                    translate([0, 0, fcoup_t - insert_head_t - 0.1])
                        cylinder(d=insert_head_d + 0.3, h=insert_head_t + 0.2);
                } else {
                    translate([0, 0, fcoup_t - 2*pt_nominal - pt_cbore_h])
                        cylinder(d=pt_pilot_d, h=2*pt_nominal + pt_cbore_h + heps);
                    if (i == 2)
                        translate([0, 0, fcoup_t - pt_cbore_h])
                            cylinder(d=pt_cbore_d, h=pt_cbore_h + heps);
                }
            }
        }
    }
}

// Connected gas volume as a solid, for mesh measurement. A bore-only figure is
// not the connected volume -- that error let the bench fixture's first gate pass
// at 5.02 cm3 against a real 7.44.
module cavity() {
    // Clipped at the real wet face. The core cutters deliberately overshoot the
    // blank so the preview does not depth-fight, and without this clip that
    // overshoot is counted as gas volume -- a gate that measures its own
    // modelling epsilon. Worth 3.8 mm3 here, and it would grow silently with eps.
    intersection() {
        cavity_raw();
        cylinder(d = 2*head_od, h = end_z + flange_t);
    }
}

module cavity_raw() {
    difference() {
        union() {
            // MONOLITHIC OPENS THE BORE FROM z=0, and this module used to start
            // at socket_len regardless -- so the gate measured a void the
            // monolithic part does not have and MISSED 14 mm of Ø25.19 that it
            // does. About 6.5 cm3, more than the whole 5.0 cm3 budget, and no
            // gate saw it because the gate is built from this same module.
            // Found by the 2026-09-05 Codex review.
            //
            // The 5.0 cm3 budget is a PRODUCTION figure -- it presumes the
            // bonded joint and a potted board, where the tube contributes
            // nothing. Prototype 1 is 15x over it whatever this section does
            // (see o2_probe_body_tube.scad's gas echo), so the number that has
            // to stay honest is the BONDED one. It is now measured on the
            // geometry it claims to describe rather than on a fixed z.
            translate([0, 0, socket_len]) cylinder(d=bore_d, h=cav_board_len);
            // The monolithic section, as its OWN cylinder rather than as a
            // conditional start height -- the conditional form silently
            // truncated the cavity's top instead of extending its bottom.
            if (monolithic)
                translate([0, 0, -heps]) cylinder(d=bore_d, h=socket_len + heps);
            if (has_neck)
                translate([0, 0, socket_len + cav_board_len])
                    cylinder(d=neck_d, h=cav_clear_len);
            translate([0, 0, well_z - heps])
                cylinder(d=spigot_bore, h=spigot_len + heps);
            translate([0, 0, end_z])
                if (mem_clamped) clamped_core_cuts(window_d, spigot_bore, flange_t, heps);
                else cartridge_core_cuts_round(window_d, heps);
        }
        // The board runs through the whole of it, so the slot has to as well.
        cav_board_z0 = monolithic ? -heps : socket_len - heps;
        translate([-board_w/2, -board_t/2, cav_board_z0])
            cube([board_w, board_t, socket_len + cav_board_len + 2*heps - cav_board_z0]);
        // OPEN, 2026-09-04: the can is cut at the BOARD END, but the socket
        // stands it off by socket_standoff (4.7 mm at the placeholder
        // cell_axial_len), so in service its sensing face sits that much CLOSER
        // to the membrane. Volume-neutral -- cav_net subtracts cell_disp
        // analytically and the neck is prismatic -- which is why no gate ever
        // caught it. NOT neutral for the axial diffusion path in model/.
        //
        // Deliberately NOT fixed here. Seating the can on its stand-off makes it
        // an ISLAND in the gas, so the void becomes a legitimately enclosed
        // second shell and the cavity renders "Volumes: 3". That is correct
        // geometry, not a defect -- but it costs this part its Volumes: 2 gate,
        // and the alternative (modelling the socket as a solid) puts an
        // UNSOURCED diameter inside a release gate: a 6 mm stem would eat
        // ~133 mm3 of a ~190 mm3 budget margin. Decide it with the Cambion
        // footprint in hand, not before. The assembly drawing already shows the
        // can in its true seated position.
        // PAST-END ONLY. This cylinder IS the can in that mount. It is NOT the
        // can in the standing mount -- there the can lies radially on the board,
        // cell_setback back from the tip -- so cutting it here would remove a
        // solid that is not in the cavity, and it did: the boolean this replaces
        // let it switch on the moment any part of the standing can crossed into
        // the head, deleting all 1393 mm3 for 11 mm3 of real overlap. cav_net's
        // cell_disp_counted is gated on the SAME has_neck, so the two models
        // measure one solid, not two. Standing, the can is counted as gas --
        // over-stating, which is the only safe direction for this gate.
        if (has_neck)
            translate([0, 0, socket_len + cav_board_len])
                cylinder(d=cell_d, h=cell_h);
    }
}

// Debris cap: SOLID front face, because this is the face that plows into the
// pile. Everything enters from the sides, so material is never driven straight
// onto the membrane. Modelled in ITS OWN frame, z = 0 at its open end.
module cap() {
    difference() {
        union() {
            // Lower shell: grip plus clearance over the clamped stack.
            cylinder(d=cap_od, h=band_z0);
            // Cage ribs. Everything between them is open: this band is the
            // probe's entire gas inlet, so it is sized by open area.
            for (i = [0:rib_n-1])
                rotate([0, 0, i*360/rib_n])
                    translate([flange_d/2 + 0.5, -rib_w/2, band_z0])
                        cube([cap_od/2 - flange_d/2 - 0.5, rib_w, guard_gap]);
            // Solid plowing face, plus a taper so it does not catch on the way
            // in or out.
            translate([0, 0, band_z1]) cylinder(d=cap_od, h=cap_front_t);
            translate([0, 0, band_z1 + cap_front_t])
                cylinder(d1=cap_od, d2=cap_od - 2*nose_taper, h=nose_taper);
        }
        // Grip: slips over the head's OD.
        translate([0, 0, -heps]) cylinder(d=head_od + 0.4, h=cap_grip + heps);
        // Clearance for the clamped stack.
        translate([0, 0, cap_grip]) cylinder(d=flange_d + 1.0, h=cap_stack + heps);
        // Retention screws, in the grip, clear of everything sealed.
        translate([0, 0, cap_grip/2])
            cap_screw_positions()
                translate([0, 0, head_od/2 - heps])
                    cylinder(d=m2_clear, h=cap_wall + 2*heps);
    }
}

// Representative fastener, for the exploded view only. Never exported: these are
// bought parts, and the pilot they thread into is still unsourced.
// Drawn HANGING from its own origin: the head sits at z=0..head_t and the shank
// runs DOWN to -length. So the origin is placed on the surface the screw enters
// and no flip is needed -- flipping it was what put the heads on the inside.
module screw(nominal, length, head_d, head_t) {
    color("Silver") {
        translate([0, 0, -length]) cylinder(d=nominal, h=length);
        cylinder(d=head_d, h=head_t);
    }
}

// The cap in the ASSEMBLY's frame rather than its own. part="cap" renders the
// cap with z=0 at its open end, which is what a printer or a caliper wants; a
// viewer drawing the stack needs it where it actually sits, cap_grip down the
// head's OD from the end face. Exposed as its own part so no consumer has to
// carry that offset as a literal -- one that would silently go stale the next
// time head_len or cap_grip moves. assembly() calls this too, so the two frames
// cannot drift apart.
module cap_assembled(e = 0) {
    translate([0, 0, head_len - cap_grip + 13.0*e]) cap();
}

module assembly() {
    e = exploded ? 12 : 0;
    color("Tan") head();

    // ---- what the head is FOR -------------------------------------------
    // The board arrives from the TUBE side, so it explodes DOWN. Drawing it up
    // with the sealing stack would say it assembles through the membrane, which
    // is the one direction it cannot: the head is bonded to the tube.
    // The cell is separated from its own socket because it is the only
    // SCHEDULED CONSUMABLE in this picture (PLAN.md risk 11 -- electrolyte loss
    // at 75 C sets a replacement interval), and a drawing that buries it in the
    // board hides the service problem instead of showing it.
    color("ForestGreen")
        translate([-board_w/2, -board_t/2, board_tip_z - board_stub - 4.4*e])
            cube([board_w, board_t, board_stub]);
    // The cell. STANDING it is a THT part: axis normal to the copper, sitting
    // cell_setback back from the board tip, lifted cell_stand_off off the board
    // by the socket, gas face RADIAL -- which is why the gas has to come down the
    // spigot bore and then turn. The socket is the same position marker it always
    // was, now under the can rather than in front of it.
    if (cell_standing) {
        color("Goldenrod")
            translate([0, 0, cell_z - 3.4*e])
                rotate([-90, 0, 0]) translate([0, 0, board_t/2])
                    cylinder(d=cell_d - 2.0, h=cell_stand_off);
        color("DarkSlateGray")
            translate([0, 0, cell_z - 3.4*e])
                rotate([-90, 0, 0]) translate([0, 0, board_t/2 + cell_stand_off])
                    cylinder(d=cell_d, h=cell_h);
    } else {
        color("Goldenrod")
            translate([0, 0, board_tip_z - 4.4*e])
                cylinder(d=6.0, h=socket_standoff);
        color("DarkSlateGray")
            translate([0, 0, cell_z - 3.4*e]) cylinder(d=cell_d, h=cell_h);
    }
    // Gasket drawn at its COMPRESSED height, which is how it sits in service.
    color("DimGray") translate([0, 0, 1.6*e]) radial_ring();
    color("Khaki") translate([0, 0, well_z + 3.4*e]) carrier();
    // The consumable stack the retainer clamps, in the carrier's wet-face pocket:
    // the O-ring at its COMPRESSED height, then the membrane coupon on top.
    // These are what the six screws actually preload. The ring's bore is wider
    // than the window: at window_d it would sit inside the flare cone and put one
    // compressed cord thickness of straight channel in front of the membrane.
    // Drawn as a squashed torus -- the free cord is mem_oring_cs, so at gasket_gap
    // the section is an ellipse, which is what a seated ring actually looks like.
    coupon_d = mem_clamped ? face_disc_d(window_d) : window_d + 2*land;
    // The clamped bed is the same two parts the other way up: the membrane lies
    // ON the carrier's flat face and the ring comes down onto it from the
    // retainer's groove, so the ring is drawn ABOVE the membrane, not below it.
    if (mem_clamped)
        color("IndianRed")
            translate([0, 0, end_z + flange_t + membrane_t + face_gap_nom/2 + 6.4*e])
                rotate_extrude()
                    translate([(face_groove_id(window_d) + face_cord_fit)/2, 0])
                        scale([1, face_gap_nom/face_cord_fit]) circle(d=face_cord_fit);
    else
        color("IndianRed")
            translate([0, 0, end_z + flange_t - pocket_depth + gasket_gap/2 + 5.6*e])
                rotate_extrude()
                    translate([(gasket_id(window_d) + mem_oring_cs)/2, 0])
                        scale([1, gasket_gap/mem_oring_cs]) circle(d=mem_oring_cs);
    color("GhostWhite")
        translate([0, 0, end_z + flange_t
                         + (mem_clamped ? 0 : -membrane_t) + 5.6*e])
            cylinder(d=coupon_d, h=membrane_t);

    color("LightSteelBlue") translate([0, 0, end_z + flange_t + 8.8*e]) retainer();

    // Fasteners. Retainer screws run down the bolt circle into the head's bosses;
    // cap screws come in radially. Drawn at the length the stack actually needs.
    // Entered from OUTSIDE the retainer, running down through retainer and flange
    // into the head's bosses -- so the origin sits on the retainer's outer face.
    translate([0, 0, end_z + flange_t + retainer_t + 10.8*e])
        bolt_positions()
            screw(pt_nominal, flange_t + retainer_t + 4.0, m2_clear + 1.6, 1.6);
    // The cap screws go in radially, so they explode radially -- pushing them up
    // the Z axis with everything else would misrepresent how they assemble.
    translate([0, 0, head_len - cap_grip/2 + 13.0*e])
        cap_screw_positions()
            translate([0, 0, head_od/2 + cap_wall + 3.0*e])
                screw(selftap_cap, cap_wall + cap_screw_depth,
                      selftap_cap + 1.6, 1.4);
    // The cap is a shell that swallows the rest, so it has to travel furthest
    // before an exploded view shows anything.
    color("DimGray") cap_assembled(e);

    if (show_body) body_stack(e);
}

// PROTOTYPE 1's WHOLE BODY, as one printed solid: this head with the printed
// tube fused to it. The tube arrives as the STL o2_probe_body_tube.scad exports
// -- the producer's own output, not a re-modelled copy -- so the two can only
// disagree by being rebuilt out of order, which the Makefile prevents.
//
// Both models must be on the same joint. Nothing downstream would notice if
// they were not: a bonded tube unioned to a monolithic head leaves a 14 mm
// Ø32.4 void where the socket was, and it still exports as a closed solid.
module monobody() {
    // Keep this message free of escaped quotes. OpenSCAD 2021.01 refuses a
    // backslash-quote inside a string here, and reports it at a line number PAST
    // the end of the file, which points nowhere near the actual text.
    // THE PAREN. This read `import(str(body_dir, "/body-tube.stl",
    // convexity=10))` -- convexity inside str() -- so the path came out
    // "exports/body-tube.stl10", import() found no such file, and the monobody
    // was THE HEAD ALONE. OpenSCAD says "ERROR: Unsupported file format" and
    // then exits 0; the head by itself is a perfectly good closed solid, so
    // CGAL reported `Volumes: 2` and the Makefile gate passed. Every exported
    // monobody was 22.6 mm of head. Found by tools/interface_check.py weighing
    // the union against its parts, which is the whole reason that check exists.
    assert(monolithic,
           "monobody needs joint=monolithic -- with the socket still cut, the union leaves a 14 mm annular void inside the part");
    union() {
        head();
        // monolithic, so the tube's top face IS this head's z=0
        translate([0, 0, -body_tube_len])
            import(str(body_dir, "/body-tube.stl"), convexity=10);
    }
}

// The prototype-1 body, imported from the STLs o2_probe_body_tube.scad exports.
//
// EVERYTHING BELOW THE HEAD EXPLODES DOWNWARD, for the same reason the board
// does: it all assembles from the tube side. The head is bonded to the tube, so
// nothing in this half can be shown arriving through the membrane.
//
// Frames. The body model's z=0 is the tube's CABLE end and its top face is at
// z=body_tube_len; that face seats at head z=socket_len. So a body-frame point
// maps to head z = socket_len - (body_tube_len - z_body). The cap is mirrored:
// its own z runs from its mouth inward, and its mouth sits body_cap_engage above
// the tube's cable end face when locked.
module body_stack(e) {
    // Explosion offsets are chosen so nothing hides inside the tube. The board
    // is drawn by assembly() at -4.4*e and is 16 mm long, so its cable end
    // reaches -4.4*e - 16; the tube's top face has to clear that or the whole
    // gas end of the picture disappears up the bore -- which is exactly what
    // the first render did.
    tube_drop = 8.25*e;
    dam_drop  = 5.9*e;
    cap_drop  = 10.6*e;
    // Where the tube's TOP face sits with nothing exploded: at the socket floor
    // when bonded, at the head's own z=0 when the head continues from it.
    tube_seat_z = monolithic ? 0 : socket_len;
    tube_top_z  = tube_seat_z - tube_drop;              // head frame
    tube_base_z = tube_top_z - body_tube_len;
    color("Sienna") translate([0, 0, tube_base_z]) import(str(body_dir, "/body-tube.stl"), convexity=10);
    // The dam clamps round the board at body y=81; drawn between board and tube,
    // which is also the order it is fitted in.
    color("MediumPurple")
        translate([0, 0, tube_seat_z - dam_drop]) import(str(body_dir, "/body-dam.stl", convexity=10));
    // The cable-end seal: the SAME ORS116787 24 x 1.5 EPDM as the carrier's
    // ring, now RADIAL on the cap's spigot rather than a 28 x 2 face seal. It
    // is drawn on the groove root, not on the tube's end face, because that is
    // where it sits -- and the change is not cosmetic: a radial seal supplies
    // no axial preload, so it is no longer the spring that holds the bayonet
    // lug in its detent. The M3 lock screw is.
    // Drawn Crimson rather than black because label-prototype.py separates the
    // greys by row band, and a fourth grey at the bottom of the stack would be
    // taken for the carrier's ring.
    color("Crimson")
        translate([0, 0, tube_base_z - 0.67*e])
            rotate_extrude()
                translate([body_groove_root/2 + body_seal_cord/2, 0])
                    circle(d=body_seal_cord);
    // Cap: mirrored, because its own z runs from its mouth inward and the mouth
    // faces the tube. Locked, its mouth sits body_cap_engage above the tube's
    // cable end face.
    color("DarkOrange")
        translate([0, 0, tube_seat_z - body_tube_len - cap_drop + body_cap_engage])
            mirror([0, 0, 1]) import(str(body_dir, "/body-cap.stl", convexity=10));
}

// Every printable part, laid out flat and print-oriented, as ONE file. Handing
// a slicer four separate STLs loses a race with its own launch; one file does
// not. The carrier is included as a FIT MODEL -- the real one is PP.
// Which parts the plate carries.
//   "all"    every printable part
//   "pair"   carrier + retainer only, for a reprint of just those two
//   "ready"  drops the head. The head's length rides on cell_axial_len, which is
//            still an unmeasured placeholder: 13.0 -> 14.0 moves it 28416 ->
//            29590 mm3, so it is a part we expect to reprint. The other three
//            come out byte-identical across that same sweep, which is what makes
//            them printable NOW and the head not.
plate_set = "all";
assert(plate_set == "all" || plate_set == "ready" || plate_set == "pair",
       str("plate_set must be all, ready or pair, not: ", plate_set));

// The two print-orientation flips are defined HERE and nowhere else. Both are
// load-bearing, and a plate and a single-part export that each carry their own
// copy of a flip are two chances to get it wrong; this way there is one.

// Flange DOWN: as modelled the flange overhangs the spigot, which is a
// 90-degree overhang all the way round.
module carrier_printed() {
    translate([0, 0, spigot_len + flange_t]) mirror([0, 0, 1]) carrier();
}
// Nose DOWN. As modelled the cap's solid plowing face sits on top of the open
// cage band, so printing it nose-up asks the slicer to start a full dia-47 disc
// in mid-air on six 3 mm ribs -- a ~39 mm island, not a bridge. Inverted, the
// nose is the first layer and the lower shell arrives last as a 3.45 mm wide
// annulus bridging rib to rib, anchored at both ends.
module cap_printed() {
    translate([0, 0, cap_oal]) mirror([0, 0, 1]) cap();
}
// WHICH FACE GOES ON THE PLATE, and it is a real trade, not a default.
//
// GROOVE UP (true) keeps the groove roof out of the air: nothing bridges, and
// the groove depth -- which sets squeeze -- is laid down layer by layer on solid
// material. The cost is that the sealing face is then a TOP surface.
//
// GROOVE DOWN (false) puts the sealing face on the plate. Fab, 2026-09-05, from
// the printed parts and said twice: "the bed-surface is much cleaner". That is a
// measurement and it outranks the argument that a top surface ought to be fine.
// The cost is that the groove roof spans face_groove_w() over air. Note what
// that is and is not: it is a bridge ANCHORED ON BOTH WALLS, not the
// one-sided unsupported overhang that ruined the legacy carrier bed -- those are
// different failure modes and FDM handles the first far better. The real risk is
// narrower: that roof is the surface the O-ring bottoms on, so any droop moves a
// dimension whose whole window is +0.054/-0.093 mm.
//
// The 1.2 mm inner rim is what makes this orientation viable at all. Printed
// groove-down it is a free-standing annular wall face_groove_depth tall; at the
// old 0.8 (one bead plus a 0.2 sliver) that wall was fragile. Two whole beads is
// a wall. The rim fix and the flip are independent changes that happen to help
// each other -- neither is a substitute for the other.

module retainer_printed() {
    if (mem_clamped && face_groove_up)
        translate([0, 0, retainer_t]) mirror([0, 0, 1]) retainer();
    else retainer();
}

module plate() {
    pitch = head_od + 8;
    if (plate_set == "all") color("Tan") head();
    color("Khaki") translate([pitch, 0, 0]) carrier_printed();
    color("LightSteelBlue") translate([0, pitch, 0]) retainer_printed();
    if (plate_set != "pair") color("DimGray") translate([pitch, pitch, 0]) cap_printed();
}

// Assembled and cut on the axis, which is the only view that shows the sealing
// stack in place: an exploded view hides the carrier inside the cap.
module section() {
    intersection() {
        assembly();
        translate([-head_len, 0, -head_len])
            cube([2*head_len, 2*head_len, 3*head_len]);
    }
}

// The CARRIER-TO-HEAD radial seal, at its assembly coordinate. Defined once
// because it was drawn in exactly one place -- inline in assembly() -- and so
// the viewer had no way to show it. A seal that is not drawn reads as a seal
// that is not there, which is the one thing this viewer exists to prevent.
//
// Drawn SQUEEZED, like the bed ring: the gland is (well_d_made - groove_root_d)/2
// per side, i.e. one compressed cord, and the section bulges axially to keep its
// area. The old inline copy drew a free circle at the free cord, which is 1.5
// where the seated ring is 1.13 x 1.98 -- it looked like a ring resting in a
// groove rather than one filling it.
module radial_ring() {
    gland = (well_d_made - groove_root_d) / 2;
    translate([0, 0, well_z + lead_chamfer + 0.75 + groove_w/2])
        rotate_extrude()
            translate([groove_root_d/2 + gland/2, 0])
                scale([gland/oring_cord, oring_cord/gland]) circle(d=oring_cord);
}

// ---------------------------------------------------------------- viewer
// The sealing stack, element by element, IN ASSEMBLY COORDINATES. The three.js
// viewer loads these with identity matrices, so it does no arithmetic of its
// own and cannot place a part by a number copied out of this file -- the same
// rule tools/make_viewer_parts.py enforces for the body.
module bed_element(which) {
    if (which == "carrier") translate([0, 0, well_z]) carrier();
    else if (which == "retainer") translate([0, 0, end_z + flange_t]) retainer();
    else if (which == "membrane")
        translate([0, 0, end_z + flange_t])
            cylinder(d=mem_clamped ? face_disc_d(window_d) : window_d + 2*land,
                     h=membrane_t);
    else if (which == "ring")
        translate([0, 0, end_z + flange_t
                         + (mem_clamped ? membrane_t + face_gap_nom/2
                                        : -pocket_depth + gasket_gap/2)])
            rotate_extrude()
                translate([(mem_clamped ? face_groove_id(window_d) + face_cord_fit
                                        : gasket_id(window_d) + mem_oring_cs)/2, 0])
                    scale([1, mem_clamped ? face_gap_nom/face_cord_fit
                                          : gasket_gap/mem_oring_cs])
                        circle(d=mem_clamped ? face_cord_fit : mem_oring_cs);
    else if (which == "radial-ring") radial_ring();
    else assert(false, str("unknown bed element '", which, "'"));
}

if (part == "section") section();
else if (part == "plate") plate();
else if (part == "assembly") rotate([0, view_rot, 0]) assembly();
else if (part == "head") head();
else if (part == "carrier") carrier();
else if (part == "retainer") retainer();
else if (part == "cap") cap();
else if (part == "cap-asm") cap_assembled();
else if (part == "monobody") monobody();
else if (part == "cavity") cavity();
else if (part == "void-coupon") coupon_plate();
else if (part == "fastener-coupon") fastener_coupon();
else if (part == "bed-carrier") bed_element("carrier");
else if (part == "bed-retainer") bed_element("retainer");
else if (part == "bed-membrane") bed_element("membrane");
else if (part == "bed-ring") bed_element("ring");
else if (part == "bed-radial-ring") bed_element("radial-ring");
// Print-oriented single-part exports, for a slicer that takes STLs as-exported
// and cannot be trusted to re-derive the flips.
else if (part == "carrier-print") carrier_printed();
else if (part == "retainer-print") retainer_printed();
else if (part == "cap-print") cap_printed();
else assert(false, "unknown part");
