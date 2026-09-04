/*
 * O2 probe — buried head, END-WINDOW variant (printed ASA)
 * Units: millimetres. Z runs from the tube joint toward the tip.
 *
 * The alternative to o2_probe_head.scad, built so the two can be compared on
 * numbers instead of argument. The gas window is on the END face, following
 * PLAN.md's cell-orientation option C -- cell past the board end, axis along the
 * tube. Nothing has to be found in the radial budget, which is what forces the
 * radial variant to 46 mm and 11.2 cm3.
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

part = "assembly";   // assembly, head, carrier, retainer, cap, cavity

// Retainer fastening. Both routes are kept; "ptscrew" is the default because
// the reason for metal threads went away when the radial O-ring took the seal
// load off the screws. Worst case is now ~6 N, order 0.1 MPa in the thread, so
// creep is a non-issue -- and the insert route costs 6 mm of head diameter, a
// sole-source US-only part, a flange counterbore, and a heat-setting step 2.3 mm
// from the O-ring's sealing bore.
fastening = "ptscrew";      // "ptscrew" or "insert"
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
body_tube_len = 127.0;      // o2_probe_body_tube.scad, tube_len
body_cap_engage = 12.0;     // o2_probe_body_tube.scad, cap_engage
seal_cord_body = 2.0;       // o2_probe_body_tube.scad, seal_cord

// ------------------------------------------------- MEASURE THESE

tube_od_meas = undef;      // MEASURE: actual OD of the tube stock, incl. ovality
board_env_front = undef;   // MEASURE: populated swept envelope above the board
board_env_back = undef;    // MEASURE: populated swept envelope below the board
cell_axial_len = undef;    // MEASURE: how far the cell + its socket project past
                           //          the board end, real cell in a real socket
// SOURCED 2026-09-02, ../../tech/PROBE-CARRIER-SOURCING.md: E-Z LOK FL-M25-HI-CR,
// stainless E-Z Sonic. Stainless because brass suffers ammonia stress-corrosion
// cracking and these sit outside the seal in NH3 condensate. Every EU specialist
// checked makes stainless special-order only.
insert_bore_d = 3.99;      // E-Z LOK dimensional drawing D-S.113 Rev1, 11/01/2024
insert_bore_h = 6.7;       // INFERRED, not an E-Z LOK number: SPIROL's design-guide
                           // rule (length + 2 pitches) applied to E-Z LOK's 5.74 mm
                           // body. E-Z LOK publishes no hole depth anywhere.
insert_head_d = 5.54;      // flanged only -- needs a counterbore or it holds the
insert_head_t = 0.61;      // retainer off the face. Same drawing.

// Thread-forming screw for thermoplastics (Delta PT / EJOT PT / Plastite), A2,
// nominal 2.5. NOT YET SOURCED: the pilot is brand-specific and belongs in the
// next sourcing pass. 2.1 is a bare placeholder -- it was commented here as the
// usual "0.75 x nominal", which is false arithmetic (2.1/2.5 = 0.84), so it has
// no rationale at all and must not be treated as an anchor.
pt_nominal = 2.5;
pt_pilot_d = 2.1;
// Boss OD >= 2x screw nominal is the standard rule for thread-forming in
// plastic, and it is the hoop stress that sets it, not heat -- which is why
// this wall is smaller than the insert's.
pt_seal_wall = (2*pt_nominal - pt_pilot_d)/2;

assert(!is_undef(tube_od_meas),
       "UNMEASURED: tube_od_meas -- measure the tube OD and its ovality");
assert(!is_undef(board_env_front),
       "UNMEASURED: board_env_front -- tallest component above the board plane");
assert(!is_undef(board_env_back),
       "UNMEASURED: board_env_back -- tallest component below the board plane");
assert(!is_undef(cell_axial_len),
       "UNMEASURED: cell_axial_len -- seat a real cell in a real socket and measure");
echo(str("FASTENING: ", fastening, use_insert
         ? " -- E-Z LOK FL-M25-HI-CR; NOTE insert_bore_h is cross-manufacturer inference, verify on a coupon"
         : " -- thread-forming screw, A2, nominal 2.5; NOTE pt_pilot_d is NOT YET SOURCED"));

// ------------------------------------------------- design parameters

board_w = 20.0;             // KiCad Edge.Cuts, controlled
board_t = 1.0;              // KiCad, controlled
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
window_d = 16.0;            // -> 201 mm2, against 200 mm2 for two square coupons

bond_gap = 0.20;
socket_len = 14.0;
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
// The sealing core lives entirely in the flange, so the flange IS the core.
flange_t = cart_t;
carrier_fit = 0.3;

// SOURCED 2026-09-02, ../../tech/PROBE-CARRIER-SOURCING.md: o-ring-stocks.eu
// ORS116787, EPDM 70 Shore A peroxide-cured, 24.0 x 1.5 DIN 3771. NOT a derived
// size -- 24.5 x 1.5 does not exist in EPDM at all; it is FKM/FFKM only, and FKM
// is excluded because ammonia attacks fluoroelastomers.
oring_cord = 1.5;
oring_id_ordered = 24.0;    // the part that actually exists
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

retainer_t = 3.0;
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
// 2.3 = SPIROL's boss rule (boss OD >= 2x knurl dia) on E-Z LOK's 4.60 mm body.
// Inserco allows 1.6 for its M2.5; SPIROL is the conservative one and this wall
// also protects the O-ring seat from the heat of installation.
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
cap_screw_depth = 4.0;      // BLIND: must never reach the bore
selftap_cap = 2.1;          // cap screws carry no seal load, so self-tap is fine
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
spigot_d = mouth_d + 2*spigot_land;      // wall thick enough to hold a groove
well_d = spigot_d + carrier_fit;         // the DRAWN bore, i.e. the call-out
// H7 is +0.021/0, not +/-0.0105: a reamed bore is centred half a band ABOVE
// nominal, never below it. The seal math must use the middle of the distribution
// the shop actually produces, or every squeeze figure is biased loose by 0.0105.
// The geometry is still cut at the call-out; only the seal arithmetic shifts.
well_bias = (well_finish == "reamed") ? 0.0105 : 0;
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
fast_hole_d = use_insert ? insert_bore_d : pt_pilot_d;
fast_hole_h = use_insert ? insert_bore_h : 8.0;
fast_seal_wall = use_insert ? insert_seal_wall : pt_seal_wall;

// The bore the fastener must stay clear of is the WELL the spigot seals into --
// well_d = spigot_d + carrier_fit -- not the spigot itself. Using spigot_d here
// overstated every quoted wall by carrier_fit/2.
bolt_r = well_d/2 + fast_seal_wall + fast_hole_d/2;

// The flange must reach the bolt circle, which the insert now sets -- with the
// real 3.99 bore the circle grew past a flange sized from the spigot alone.
flange_d = max(spigot_d + 2*flange_margin, 2*bolt_r + m25_clear + 4.0);

// Head OD: the bore, or the bolt circle plus material around it. NOT a facet at
// a radius, which is the whole point of this variant.
head_od = 2 * ceil(max(bore_d/2 + wall_min, bolt_r + fast_hole_d/2 + wall_min) + 0.5);
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

neck_margin = 1.0;
neck_d = cell_d + 2*neck_margin;
cell_disp = PI * pow(cell_d/2, 2) * cell_h;
cav_board_len = 2.0;   // board tip inside the cavity; volume is tight
cav_clear_len = cell_axial_len;          // guard_gap is OUTSIDE the membrane
// Now counts the spigot bore and the flare stack as well, because a bore-only
// figure understates: it passed at 2.68 cm3 while the mesh measured 5.81.
core_gas = PI*pow(mouth_d/2,2)*heater_shelf_t
         + PI*(cart_t - pocket_depth - heater_shelf_t)/12
           * (pow(mouth_d,2) + mouth_d*window_d + pow(window_d,2));
cav_net = PI*pow(bore_d/2,2)*cav_board_len - board_w*board_t*cav_board_len
        + PI*pow(neck_d/2,2)*cav_clear_len - cell_disp
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
socket_standoff = cav_clear_len - cell_h;   // derived, NOT a Cambion dimension
cell_z = board_tip_z + socket_standoff;     // underside of the can
board_stub = 16.0;                          // drawing length only

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

assert(bore_d >= cell_d + 2*bore_margin, "bore does not clear the cell can");

// SERVICEABILITY. The head is BONDED to the tube (see the sealing stack at the
// top of this file), so the head never comes off and the ONLY path a cell can
// ever take is axially OUT through the carrier well -- up the neck first, then
// through the spigot bore. "The cell is replaceable" is a claim the geometry has
// to earn, so it is checked rather than asserted in prose.
cell_pull_neck   = (neck_d - cell_d)/2;
cell_pull_spigot = (spigot_bore - cell_d)/2;
cell_pull_travel = cell_h + socket_standoff + spigot_len;
assert(cell_pull_neck > 0 && cell_pull_spigot > 0,
       str("cell cannot be withdrawn: neck clearance ", cell_pull_neck,
           " mm, spigot-bore clearance ", cell_pull_spigot,
           " mm. With the head bonded to the tube there is no second path."));
echo(str("CELL SERVICE: withdraws axially, travel ", cell_pull_travel,
         " mm; radial clearance ", cell_pull_neck, " mm in the neck then ",
         cell_pull_spigot, " mm in the spigot bore. Blind reach from the head end face to the can top ",
         end_z - well_z, " mm through a ", spigot_bore,
         " mm bore -- NO EXTRACTION TOOL EXISTS and fingers do not fit."));
assert((spigot_d - spigot_bore)/2 - oring_cord + oring_cord*oring_squeeze >= 1.2,
       "spigot wall too thin under the O-ring groove: it will collapse inward and lose squeeze");
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
oring_id_max = oring_id_ordered + 0.25;      // DIN ISO 3601 d1 row for 24 mm
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
assert(spigot_groove_wall >= wall_min - 1e-6,
       str("only ", spigot_groove_wall, " mm of spigot left under the O-ring ",
           "groove root (Ø", groove_root_d, " over a Ø", spigot_bore,
           " bore), against a ", wall_min, " mm minimum. Raise spigot_land, or ",
           "accept a thinner section on the part that carries the seal"));

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
assert(mem_dtol_max > 0,
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
assert(mem_fill_worst <= 0.85,
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
assert(mem_ring_inner_d >= window_d,
       str("the flare cone reaches ", mem_ring_inner_d, " at the groove floor, ",
           "inside the ", window_d, " window and the retainer bore: the ring ",
           "can slide over the gas path with nothing above it"));

// ---- seal-land thermometry --------------------------------------------------
//
// The ledge and seal-groove clearances are the module's own; it owns the
// geometry that decides them.
// The widest thing actually cut at the bolt circle. On the insert route that is
// the flange counterbore, not the insert bore -- and unlike the wall check below
// this one is NOT an identity, because insert_head_d is an independent sourced
// input that no derivation ties to bolt_r.
bolt_cut_max = use_insert ? max(insert_bore_d, insert_head_d + 0.3) : fast_hole_d;
cbore_wall = bolt_r - bolt_cut_max/2 - well_d/2;
assert(cbore_wall >= 1.0 - 1e-6,
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
assert(2*bolt_r + m25_clear + 2.0 <= flange_d,
       "bolt circle falls outside the carrier flange: the retainer would clamp nothing");
assert(bolt_r - m25_clear/2 >= spigot_d/2,
       str("the screw clearance hole through the carrier flange would break into ",
           "the spigot bore: bolt circle radius ", bolt_r, " minus half a ",
           m25_clear, " hole lands inside the ", spigot_d/2, " mm spigot"));
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
assert(abs(flange_t - cart_t) < 0.001,
       "flange must equal cart_t, else the sealing core does not reach the flange's gas face and the membrane is sealed off");
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
         ", cell axial ", cell_axial_len));
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
echo(str("O-RING ORS116787, EPDM 70 peroxide, ", oring_id_ordered, " x ", oring_cord,
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
echo(str("MEMBRANE SEAL preload: UNVERIFIED. Sized on geometry only. The washer ",
         "bracket (38-115 N/screw) does NOT transfer -- an O-ring seals on a ",
         "line at far lower load. Measure it. RISK: line contact on 0.18 mm ",
         "porous PTFE may cold-flow and relax; absent if the membrane is welded ",
         "into a PP cartridge and this joint becomes PP-on-ASA."));
echo(str("CUT LIST: PMV15T disc dia ", window_d + 2*land,
         carrier_is_pp ? " mm, welded into the carrier" : " mm, clamped in the carrier"));
echo(str("fasteners: ", bolt_n, "x ", use_insert ? "M2.5 into heat-set inserts"
         : "thread-forming, nominal 2.5, into printed bosses", " on a dia ",
         2*bolt_r, " bolt circle; ", cap_screw_n,
         "x M2.5 self-tapping for the cap (no seal load)"));
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
        translate([0, 0, socket_len + cav_board_len])
            cylinder(d=neck_d, h=cav_clear_len + heps);

        // The well the spigot seals into. Its bore IS the sealing surface, so it
        // wants to be printed cleanly -- it is the one feature here whose
        // surface finish is functional.
        translate([0, 0, well_z]) cylinder(d=well_d, h=head_len);
        // Lead-in, so the O-ring is not shaved on assembly.
        translate([0, 0, head_len - lead_chamfer])
            cylinder(d1=well_d, d2=well_d + 2*lead_chamfer, h=lead_chamfer + heps);

        // Heat-set inserts on the bolt circle, blind from the end face, each
        // with a counterbore for its flange -- the stainless E-Z Sonic is only
        // made flanged, and a proud flange holds the retainer off the face.
        bolt_positions() {
            translate([0, 0, head_len - fast_hole_h])
                cylinder(d=fast_hole_d, h=fast_hole_h + heps);
            // Counterbore only for the insert: it is made flanged only, and a
            // proud flange holds the retainer off the face.
            if (use_insert)
                translate([0, 0, head_len - insert_head_t - 0.1])
                    cylinder(d=insert_head_d + 0.3, h=insert_head_t + 0.2);
        }

        // Cap retention: BLIND radial holes that stop well short of the bore.
        translate([0, 0, head_len - cap_grip/2])
            cap_screw_positions()
                translate([0, 0, head_od/2 - cap_screw_depth])
                    cylinder(d=selftap_cap, h=cap_screw_depth + heps);
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
        // The sealing core, in the flange, wet face at +Z.
        translate([0, 0, spigot_len]) cartridge_core_cuts_round(window_d, heps);
        // The flange sits between the retainer and the head's end face, so the
        // clamping screws pass THROUGH it. Without these it is 5 mm of solid PP
        // in front of every boss and nothing can be assembled.
        translate([0, 0, spigot_len - heps])
            bolt_positions() cylinder(d=m25_clear, h=flange_t + 2*heps);
    }
}

module retainer() {
    difference() {
        cylinder(d=flange_d, h=retainer_t);
        translate([0, 0, -heps]) cylinder(d=window_d, h=retainer_t + 2*heps);
        translate([0, 0, -heps])
            bolt_positions() cylinder(d=m25_clear, h=retainer_t + 2*heps);
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
coupon_r_in  = bolt_r - m25_clear/2 - coupon_wall_reach - 1.5;
coupon_rim   = flange_d/2 - (bolt_r + m25_clear/2);
assert(coupon_r_in + coupon_wall_reach < bolt_r - m25_clear/2,
       str("coupon inner edge r=", coupon_r_in, " is too close: its perimeter field ",
           "reaches r=", coupon_r_in + coupon_wall_reach, " and the hole starts at r=",
           bolt_r - m25_clear/2, " -- the coupon would measure its own free edge"));
assert(coupon_r_in > 0, str("coupon inner radius went negative: ", coupon_r_in));
assert(abs(coupon_rim - 2.0) < 0.15,
       str("coupon rim is ", coupon_rim, " mm, not the 2.0 the voids appear in -- ",
           "the bolt circle or flange OD moved, so this coupon no longer reproduces ",
           "the defect it was built for"));
echo(str("VOID COUPON: hole dia ", m25_clear, " at r ", bolt_r,
         ", rim outboard ", coupon_rim, " mm, face area ",
         (coupon_sweep/360)*PI*(pow(flange_d/2,2)-pow(coupon_r_in,2)), " mm2"));

module void_coupon(t) {
    intersection() {
        difference() {
            cylinder(d=flange_d, h=t);
            translate([0, 0, -heps]) cylinder(d=2*coupon_r_in, h=t + 2*heps);
            translate([bolt_r, 0, -heps]) cylinder(d=m25_clear, h=t + 2*heps);
        }
        rotate([0, 0, -coupon_sweep/2])
            linear_extrude(t + 2*heps)
                polygon([[0, 0], [flange_d, 0],
                         [flange_d*cos(coupon_sweep), flange_d*sin(coupon_sweep)]]);
    }
}

// Both thicknesses that showed the defect: the retainer voided on BOTH faces, the
// carrier flange only on the face the bed did not press flat. Same plate, so a
// settings change is judged against both at once.
module coupon_plate() {
    translate([0, 0, 0])  void_coupon(retainer_t);
    translate([0, 14, 0]) void_coupon(cart_t);
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
            translate([0, 0, socket_len]) cylinder(d=bore_d, h=cav_board_len);
            translate([0, 0, socket_len + cav_board_len])
                cylinder(d=neck_d, h=cav_clear_len);
            translate([0, 0, well_z - heps])
                cylinder(d=spigot_bore, h=spigot_len + heps);
            translate([0, 0, end_z]) cartridge_core_cuts_round(window_d, heps);
        }
        translate([-board_w/2, -board_t/2, socket_len - heps])
            cube([board_w, board_t, cav_board_len + 2*heps]);
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
        translate([0, 0, socket_len + cav_board_len]) cylinder(d=cell_d, h=cell_h);
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
                    cylinder(d=m25_clear, h=cap_wall + 2*heps);
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
    color("Goldenrod")
        translate([0, 0, board_tip_z - 4.4*e])
            cylinder(d=6.0, h=socket_standoff);
    color("DarkSlateGray")
        translate([0, 0, cell_z - 3.4*e]) cylinder(d=cell_d, h=cell_h);
    // Gasket drawn at its COMPRESSED height, which is how it sits in service.
    color("DimGray")
        translate([0, 0, well_z + lead_chamfer + 0.75 + groove_w/2 + 1.6*e])
            rotate_extrude() translate([groove_root_d/2 + oring_cord/2, 0])
                circle(d=oring_cord);
    color("Khaki") translate([0, 0, well_z + 3.4*e]) carrier();
    // The consumable stack the retainer clamps, in the carrier's wet-face pocket:
    // the O-ring at its COMPRESSED height, then the membrane coupon on top.
    // These are what the six screws actually preload. The ring's bore is wider
    // than the window: at window_d it would sit inside the flare cone and put one
    // compressed cord thickness of straight channel in front of the membrane.
    // Drawn as a squashed torus -- the free cord is mem_oring_cs, so at gasket_gap
    // the section is an ellipse, which is what a seated ring actually looks like.
    coupon_d = window_d + 2*land;
    color("IndianRed")
        translate([0, 0, end_z + flange_t - pocket_depth + gasket_gap/2 + 5.6*e])
            rotate_extrude()
                translate([(gasket_id(window_d) + mem_oring_cs)/2, 0])
                    scale([1, gasket_gap/mem_oring_cs]) circle(d=mem_oring_cs);
    color("GhostWhite")
        translate([0, 0, end_z + flange_t - membrane_t + 7.2*e])
            cylinder(d=coupon_d, h=membrane_t);

    color("LightSteelBlue") translate([0, 0, end_z + flange_t + 8.8*e]) retainer();

    // Fasteners. Retainer screws run down the bolt circle into the head's bosses;
    // cap screws come in radially. Drawn at the length the stack actually needs.
    // Entered from OUTSIDE the retainer, running down through retainer and flange
    // into the head's bosses -- so the origin sits on the retainer's outer face.
    translate([0, 0, end_z + flange_t + retainer_t + 10.8*e])
        bolt_positions()
            screw(pt_nominal, flange_t + retainer_t + 4.0, m25_clear + 1.6, 1.6);
    // The cap screws go in radially, so they explode radially -- pushing them up
    // the Z axis with everything else would misrepresent how they assemble.
    translate([0, 0, head_len - cap_grip/2 + 13.0*e])
        cap_screw_positions()
            translate([0, 0, head_od/2 + cap_wall + 3.0*e])
                screw(selftap_cap, cap_wall + cap_screw_depth,
                      selftap_cap + 1.6, 1.4);
    // The cap is a shell that swallows the rest, so it has to travel furthest
    // before an exploded view shows anything.
    color("DimGray") translate([0, 0, head_len - cap_grip + 13.0*e]) cap();

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
    assert(monolithic,
           "monobody needs joint=monolithic -- with the socket still cut, the union leaves a 14 mm annular void inside the part");
    union() {
        head();
        translate([0, 0, socket_len - body_tube_len])
            import(str(body_dir, "/body-tube.stl"));
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
    tube_top_z  = socket_len - tube_drop;               // head frame
    tube_base_z = tube_top_z - body_tube_len;
    color("Sienna") translate([0, 0, tube_base_z]) import(str(body_dir, "/body-tube.stl"));
    // The dam clamps round the board at body y=81; drawn between board and tube,
    // which is also the order it is fitted in.
    color("MediumPurple")
        translate([0, 0, socket_len - dam_drop]) import(str(body_dir, "/body-dam.stl"));
    // The cable-end seal, 28 x 2 EPDM, sitting on the tube's cable end face and
    // squeezed by the cap. It was missing from this drawing until 2026-09-04,
    // which mattered: it is not just a seal, it is the SPRING that pushes the
    // tube back out and drops the bayonet lug into its detent pocket. A drawing
    // without it shows a cap that cannot lock.
    // Drawn Crimson rather than black because label-prototype.py separates the
    // greys by row band, and a fourth grey at the bottom of the stack would be
    // taken for the carrier's ring.
    color("Crimson")
        translate([0, 0, tube_base_z - 0.67*e])
            rotate_extrude() translate([28/2 + seal_cord_body/2, 0])
                circle(d=seal_cord_body);
    // Cap: mirrored, because its own z runs from its mouth inward and the mouth
    // faces the tube. Locked, its mouth sits body_cap_engage above the tube's
    // cable end face.
    color("DarkOrange")
        translate([0, 0, socket_len - body_tube_len - cap_drop + body_cap_engage])
            mirror([0, 0, 1]) import(str(body_dir, "/body-cap.stl"));
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
// The retainer is a flat disc and needs no flip; it exists here only so the
// three print-oriented exports read as one set.
module retainer_printed() { retainer(); }

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

if (part == "section") section();
else if (part == "plate") plate();
else if (part == "assembly") rotate([0, view_rot, 0]) assembly();
else if (part == "head") head();
else if (part == "carrier") carrier();
else if (part == "retainer") retainer();
else if (part == "cap") cap();
else if (part == "monobody") monobody();
else if (part == "cavity") cavity();
else if (part == "void-coupon") coupon_plate();
// Print-oriented single-part exports, for a slicer that takes STLs as-exported
// and cannot be trusted to re-derive the flips.
else if (part == "carrier-print") carrier_printed();
else if (part == "retainer-print") retainer_printed();
else if (part == "cap-print") cap_printed();
else assert(false, "unknown part");
