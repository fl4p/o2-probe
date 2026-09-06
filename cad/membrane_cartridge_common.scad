/*
 * O2 probe — shared membrane sealing core
 * Units: millimetres.
 *
 * This file owns the geometry that MUST be identical between the step-1 bench
 * fixture and the buried probe head: the window, the seal land, the dry-side
 * relief, the coupon pocket and the assembly key. `D_eff` measured on the bench
 * only transfers to the probe because these are one definition and not two
 * copies that drift.
 *
 * What is deliberately NOT shared is the flange outline and the bolt pattern:
 * the bench lid has room for a square 4-screw flange, a 38 mm head at two
 * angular positions does not. The transfer argument rests on the gas path and
 * the seal cross-section, not on the screw count.
 *
 * Convention: the cartridge occupies z = 0..cart_t with the WET face at +Z.
 */

// --- shared sealing geometry ------------------------------------------------

window = 10.0;              // square aperture; NOT frozen until step 1 pins D_eff
land = 2.5;                 // seal land width around the aperture
coupon = window + 2*land;   // 15.0 mm cut coupon

membrane_t = 0.18;          // PMV15T datasheet nominal [S14]
gasket_t = 1.0;             // uncompressed elastomer: sheet thickness for the
                            // SQUARE fixture, O-ring CORD for the round head
gasket_squeeze = 0.25;      // fraction compressed by the retainer

// --- membrane perimeter seal: an O-ring, not a cut washer -------------------
//
// Rev-A uses a standard O-ring face seal in the round head. See MEMBRANE.md,
// "Membrane perimeter gasket sourced". Three reasons it beats a die-cut washer:
//
//  1. A flat washer in the old Ø(coupon_d + 0.3) pocket could not work. Rubber
//     is incompressible; at 25% the washer had to shed 29.8 mm3 with only
//     7.5 mm3 of room outward, so 22.4 mm3 went INWARD and closed its own bore
//     from 17.0 to 15.84 -- inside the Ø16 window. Max squeeze was 7.7%.
//     A torus in a groove has void by construction, so the problem disappears.
//  2. o-ring-stocks.eu ORS116731 (17.0 x 1.0) is material 127019011 -- the SAME
//     compound as the carrier's radial ring ORS116787. One compound test report
//     covers both seals, from one supplier, off the shelf at ~EUR 0.22.
//  3. cord 1.0 at 25% squeeze compresses to 0.750 -- exactly the gasket_gap the
//     1.0 mm sheet gave -- so pocket_depth, the gas path and the 5.0 cm3 budget
//     are all UNCHANGED. This is a drop-in in gas-path terms.
//
// UNVERIFIED, and the reason to test rather than assume: an O-ring loads the
// 0.18 mm porous sintered-PTFE membrane in LINE contact where the washer spread
// it over a 2 mm band. PTFE cold-flows under concentrated stress at temperature,
// so the ring may emboss the membrane and then relax. That risk is absent in the
// production route, where the membrane is welded into a PP cartridge and this
// joint becomes PP-against-ASA, rigid on rigid.
mem_oring_cs = gasket_t;        // cord = the free gasket thickness, by definition
mem_oring_fill = 0.80;          // SIZING BASIS for groove_od() only -- the fill
                                // the ring would see if the groove had an inner
                                // wall at gasket_id. It has none, so the ACHIEVED
                                // fill is lower; ask mem_fill_real() for that.

// Dry-side access. A straight channel behind the membrane is a series
// diffusion resistance; 5.8 mm of it is what failed the outer-cartridge
// concept in RESPONSE-CANDIDATE-VOLUME.md.
straight_web = 0.0;         // unflared depth below the coupon
flare_depth = 3.0;          // 45-degree relief opening into the cavity
flare_inner = 12.0;         // aperture width where the flare meets the shelf
flare_extra = 6.0;          // mouth width = window + this
heater_shelf_t = 1.0;       // dry-side heater seat, inside the seat gasket window

cart_t = 5.0;               // cartridge body thickness
key = 3.0;                  // corner key size

// Clearance holes, "mittel" (medium) row. SOURCED 2026-09-05 and then CONFIRMED
// AGAINST THE PRIMARY the same day: Fab supplied the clause-2 "Maße" table of
// DIN EN 20273 (the German adoption of ISO 273), which reads d=2 -> 2,2 / 2,4 /
// 2,6 and d=2,5 -> 2,7 / 2,9 / 3,1 under Durchgangsloch d_h, Reihe fein/mittel/
// grob. This started as a second-hand distributor chart because ISO paywalls
// clause 2 and the free previews stop before it; it is no longer second-hand.
// The H12/H13/H14 grade names are from that chart, NOT from the DIN page, which
// labels the columns fein/mittel/grob only.
// See ../reviews/M2-FASTENING-2026-09-05.md.
m2_clear = 2.4;             // M2 mittel (fein 2.2 / mittel 2.4 / grob 2.6)
m25_clear = 2.8;            // M2.5. CONFIRMED NOT a DIN EN 20273 value: the row
                            // is 2.7 / 2.9 / 3.1, and 2.8 sits between fein and
                            // mittel. Left as found because o2_probe_head.scad's
                            // captive-nut ports are dimensioned around it; only
                            // the head-end variant moved to M2.
selftap_pilot = 2.1;        // M2.5 self-tapping pilot in ASA (declared default)

// --- derived ----------------------------------------------------------------

gasket_gap = gasket_t * (1 - gasket_squeeze);
pocket_depth = membrane_t + gasket_gap;
aperture_far = window + flare_extra;

// --- gates ------------------------------------------------------------------

// RESPONSE-CANDIDATE-VOLUME.md, "Access-path constraint": the membrane's dry
// face must be within 0.25 mm of the local cavity -- a response-critical gas
// path, not an assembly clearance.
//
// This gated straight_web alone, which could not fail: it gates a variable
// assigned 0 on the line above, and MEASUREMENT SHOWS IT HAS NO GEOMETRIC
// EFFECT EITHER. hull() of the window cylinder with the inner_d disc always
// tapers to the cylinder's TOP rim, so the cutter is one continuous cone and no
// straight section is ever built -- rendering the hull at two straight_web
// values gives identical meshes (922.5 mm3, 572 tris, both).
//
// The real constrictor is the GASKET, which sits on the dry side with its bore
// in front of the membrane. The check therefore lives in the cut modules, where
// the window diameter is actually known; see dry_side_gap().
assert(straight_web <= 0.25,
       str("straight_web exceeds the 0.25 mm dry-side access limit (note: it ",
           "also has no geometric effect -- see the comment above)"));

// Gasket bore for a given window. Opening it past the flare cone puts the gasket
// BESIDE the gas path instead of in front of it; it still seals on the land,
// which runs out to window_d + 2*land.
function gasket_id(window_d) = window_d + 1.0;
// The flare cone's diameter where the membrane's dry face sits, from the hull's
// own geometry: apex at cart_t (plus its overshoot), base inner_d at the shelf.
// Cone diameter at height z. The apex sits at cart_t + 2*eps because that is
// where the hull's top cylinder actually ends -- the overshoot is not cosmetic
// here, it sets the cone's SLOPE -- so eps must be passed in rather than
// defaulted, or the gate measures a different cone than the one built.
function flare_d_at(z, window_d, eps) =
    window_d + (flare_inner - window)
             * ((cart_t + 2*eps) - z) / ((cart_t + 2*eps) - heater_shelf_t);
// Straight channel the gasket puts in series with the membrane: one compressed
// gasket thickness if its bore is inside the cone, otherwise nothing.
// The cone WIDENS with depth, so the binding check is at the gasket's far end,
// not at the dry face: checking the dry face tests the narrowest cone and passes
// a gasket that constricts everywhere below it. What is returned is the depth
// over which the gasket bore is actually the smaller of the two.
function dry_side_gap(window_d, eps) =
    let (gap = gasket_t * (1 - gasket_squeeze),
         d_far = flare_d_at((cart_t - membrane_t) - gap, window_d, eps),
         d_near = flare_d_at(cart_t - membrane_t, window_d, eps),
         g = gasket_id(window_d))
    (g >= d_far)  ? 0                                     // clears everywhere
  : (g <= d_near) ? gap                                   // constricts throughout
  : gap * (d_far - g) / (d_far - d_near);                 // constricts partway
// `land` no longer sets a compression-seal band in the round head -- the O-ring
// seals on a line. It now sizes the membrane disc (coupon_d = window_d + 2*land)
// and, with the groove below it, the ledge that disc is supported on.
assert(land >= 2.0,
       str("seal land under 2 mm: too little membrane disc outside the groove ",
           "to support its rim and close a seal"));

// --- O-ring groove ----------------------------------------------------------
//
// The groove's INNER wall is the flare cone, which at this depth is only
// ~Ø16.5: too thin to print as a retaining wall. Retention is therefore on the
// OUTER wall, sized for a target fill so the ring cannot migrate radially
// during assembly. The old Ø21.3 pocket left it at 46% fill -- free to roll.
function oring_vol(window_d) =
    (PI/4 * mem_oring_cs*mem_oring_cs) * PI * (gasket_id(window_d) + mem_oring_cs);
function groove_od(window_d) =
    sqrt(gasket_id(window_d)*gasket_id(window_d)
         + 4*(oring_vol(window_d) / (gasket_gap * mem_oring_fill)) / PI);
// Membrane rim ledge left between the groove wall and the disc pocket.
function membrane_ledge(window_d) =
    ((window_d + 2*land + 0.3) - groove_od(window_d)) / 2;

// --- what the ring actually sees, as opposed to what sized the groove --------
//
// `mem_oring_fill` is a SIZING BASIS, not an achieved fill. groove_od() solves
// it against a nominal annulus running outward from gasket_id, as if there were
// an inner groove wall at Ø17. There is not: cartridge_core_cuts_round() cuts a
// FULL cylinder and the flare cone is the inner boundary, so the real cavity is
// larger and the real fill is lower -- 64% against the 80% asked for, at Ø16.0.
// Report the real one. A fill that is true by construction cannot detect
// anything, and the 80% figure understates the ring's radial float by 16 points
// while overstating how close the worst corner is to hydraulic lock.
mem_cord_tol = 0.08;        // DIN ISO 3601-1, d2 <= 1.8 -- the SAME class the
                            // carrier's radial ring uses. It is an ABSOLUTE
                            // band, so a thinner cord spends MORE squeeze points
                            // on it: 12.1 points at cord 1.0 against 8.0 at 1.5.

function mem_ring_vol(window_d, cord) =
    (PI/4 * cord*cord) * PI * (gasket_id(window_d) + cord);
// The cavity the ring is really in: the groove cylinder less the flare-cone
// frustum bounding it inward, over `depth` below the membrane seat.
function mem_cavity_vol(window_d, depth, eps) =
    let (d_roof  = flare_d_at(cart_t - membrane_t, window_d, eps),
         d_floor = flare_d_at(cart_t - membrane_t - depth, window_d, eps),
         od = groove_od(window_d))
    PI/4*od*od*depth
    - (PI*depth/12)*(d_floor*d_floor + d_floor*d_roof + d_roof*d_roof);
function mem_fill_real(window_d, cord, depth, eps) =
    mem_ring_vol(window_d, cord) / mem_cavity_vol(window_d, depth, eps);

// Squeeze here is set by GEOMETRY, not by screw torque: the retainer bottoms on
// the membrane ledge, so squeeze = 1 - groove_depth/cord and the screws only
// hold the joint shut. That is the whole reason this beats a screw-loaded
// washer -- but it also means the groove DEPTH is now a seal dimension.
function mem_squeeze_min(cord, depth_tol) =
    ((cord - mem_cord_tol) - (gasket_gap + depth_tol)) / (cord - mem_cord_tol);
function mem_squeeze_max(cord, depth_tol) =
    ((cord + mem_cord_tol) - (gasket_gap - depth_tol)) / (cord + mem_cord_tol);
// The groove-depth tolerance at which the thin end of the cord band lands
// exactly on `floor`. DERIVED, so that no invented process capability can mute
// it: nobody has measured what depth this carrier actually holds, and asserting
// against a guessed +/-0.05 would be asserting against a guess.
function mem_depth_tol_max(cord, floor) =
    (cord - mem_cord_tol) * (1 - floor) - gasket_gap;

// --- shared modules ---------------------------------------------------------

// Asymmetric key: one corner chamfered so coupon, gasket and retainer can only
// assemble one way. If the oleophobic treatment is one-sided, this is what
// keeps the wet face the wet face.
module keyed_rect(w, h, k) {
    difference() {
        square([w, h], center=true);
        translate([w/2, h/2]) rotate(45) square([k*1.42, k*1.42], center=true);
    }
}

// Everything subtracted from a cartridge blank, whatever its outline.
// EXTRACTED VERBATIM from membrane_fixture.scad as of 2026-09-02 so that
// pointing the fixture at this file is a no-op refactor, not a redesign.
module cartridge_core_cuts(eps=0.02) {
    // Coupon + gasket pocket, opening on the wet (+Z) face.
    translate([0, 0, cart_t - pocket_depth])
        linear_extrude(pocket_depth + eps) keyed_rect(coupon + 0.3, coupon + 0.3, key - 0.4);

    // Aperture, then an immediate 45-degree relief. The straight section under
    // the coupon is straight_web, nothing more.
    translate([0, 0, heater_shelf_t])
        hull() {
            translate([0, 0, cart_t - pocket_depth - straight_web - heater_shelf_t])
                linear_extrude(straight_web + pocket_depth + eps)
                    square([window, window], center=true);
            linear_extrude(eps) square([flare_inner, flare_inner], center=true);
        }

    // Heater seat: a flat ledge facing the cavity, entirely inside the seat
    // gasket's window, so heater leads cross no sealing surface.
    translate([0, 0, -eps])
        linear_extrude(heater_shelf_t + eps)
            square([aperture_far, aperture_far], center=true);
}

// Round variant of the same core, for an end-face window where a disc carrier
// is natural. Same land width, same 45-degree relief, same heater shelf, same
// zero straight web -- only the outline changes.
module cartridge_core_cuts_round(window_d, eps=0.02) {
    assert(dry_side_gap(window_d, eps) <= 0.25,
           str("the dry-side gasket bore is ", gasket_id(window_d),
               " but the flare reaches ",
               flare_d_at((cart_t - membrane_t) - gasket_t*(1 - gasket_squeeze),
                          window_d, eps),
               " behind the membrane, so the gasket constricts the path for ",
               dry_side_gap(window_d, eps),
               " mm against the 0.25 mm access-path limit. Open the gasket ",
               "bore, or use a thinner gasket"));
    coupon_d = window_d + 2*land;
    mouth_d = window_d + flare_extra;
    inner_d = window_d + (flare_inner - window);

    assert(membrane_ledge(window_d) >= 0.5,
           str("O-ring groove Ø", groove_od(window_d), " leaves only ",
               membrane_ledge(window_d), " mm of ledge inside the Ø",
               coupon_d + 0.3, " disc pocket, so the membrane rim is ",
               "unsupported over the groove. Reduce mem_oring_cs, raise land, ",
               "or raise mem_oring_fill"));

    // Membrane disc seat: the TOP membrane_t of the pocket, full coupon width.
    translate([0, 0, cart_t - membrane_t])
        cylinder(d=coupon_d + 0.3, h=membrane_t + eps);

    // O-ring groove below it. Its floor is the carrier, its roof is the
    // membrane, its outer wall retains the ring; inward it opens into the flare
    // cone, which the hull below removes anyway. Overshoots UP into the disc
    // seat rather than stopping on the shared plane -- same coincident-face
    // rule as the staggered cutters below.
    translate([0, 0, cart_t - pocket_depth])
        cylinder(d=groove_od(window_d), h=gasket_gap + eps);

    // Overshoots are deliberately STAGGERED. Every cutter used to stop on exactly
    // the same two planes as its neighbour -- the pocket and the flare both at
    // cart_t + eps, the mouth and the flare both at heater_shelf_t -- and CGAL
    // resolves coincident faces exactly while the OpenCSG preview depth-fights
    // them into speckle. Both changes stay in material the other cutter already
    // removes, so the rendered solid is unchanged: the flare's extra reach is
    // above cart_t, outside the blank, and its lowered base is at inner_d, inside
    // the wider mouth bore.
    translate([0, 0, heater_shelf_t])
        hull() {
            translate([0, 0, cart_t - pocket_depth - straight_web - heater_shelf_t])
                cylinder(d=window_d, h=straight_web + pocket_depth + 2*eps);
            translate([0, 0, -eps]) cylinder(d=inner_d, h=eps);
        }

    translate([0, 0, -eps]) cylinder(d=mouth_d, h=heater_shelf_t + eps);
}

// Dry-side thermometry for the ROUND head.
//
// DO NOT use cartridge_tsense_cut() below for the probe. It enters through the
// flange EDGE, which is right on a bench fixture and wrong when buried: the
// probe carrier's O-ring seals radially on the SPIGOT, so the whole flange OD
// sits on the WET side of that seal. A bore there opens a blind pocket into
// compost about a millimetre from the membrane seat and forces its own lead to
// cross the seal. It also mis-computes its depth for a round window -- it
// subtracts the SQUARE `coupon`, and at the head's Ø21 disc that lands the bore
// tip inside the flare cone, venting the gas path.
//
// This one enters from the DRY face, inside the sealed cavity where the board
// already is, and stops short of the wet face.
//
// WHAT IT MEASURES: the carrier land beside the membrane rim -- the seal-land
// boundary temperature, which is the warm end of the gradient and the number the
// thermal model has never had.
// WHAT IT DOES NOT MEASURE: the membrane's centre cold spot. That point sits
// over the flare cone with no material to bore into, so NO fixed sensor can
// reach it. Getting eta still needs a temporary sensor on the membrane face
// during qualification; this bore is the other half of that pair.
// WHERE IT CAN GO, which is one place. The carrier is a top-hat and almost none
// of it faces the sealed cavity: the flange OD and the flange underside outboard
// of the spigot are on the WET side of the spigot's radial O-ring, and the
// spigot WALL cannot be bored through because the seal groove is in it. What is
// left is the heater-shelf counterbore, which is open to the cavity through the
// spigot bore -- so the sensor pocket rises from the HEATER LEDGE itself, beside
// the heater, under the membrane's clamped rim.
//
// Bored from anywhere else this is not merely worse, it is a blind pocket with
// no path to the cavity: an earlier placement outboard of the disc rendered as a
// SECOND CLOSED VOLUME and the Makefile's `Volumes: 2` gate is what caught it.
// NOT CURRENTLY CALLED (2026-09-04). o2_probe_head_end.scad dropped its seal-land
// pocket -- "let's try without first" -- because RING-PCB.md puts the heater, and
// therefore its own sensor, on a PCB carried forward on the main board's fork.
// Kept because the geometry and its clearance checks are correct and the pocket
// is cheap to restore; see the note at the top of the head-end file.
module cartridge_tsense_axial(window_d, bore=1.2, clear=0.2, ledge_min=0.3,
                              eps=0.02) {
    inner_d = window_d + (flare_inner - window);   // cone dia at the shelf
    mouth_d = window_d + flare_extra;              // heater counterbore
    r_c = (inner_d + mouth_d) / 4;                 // centre of the heater ledge
    top = cart_t - pocket_depth - clear;           // stop under the O-ring groove
    ledge_in  = r_c - bore/2 - inner_d/2;
    ledge_out = mouth_d/2 - (r_c + bore/2);
    assert(min(ledge_in, ledge_out) >= ledge_min,
           str("a ", bore, " mm sensor pocket leaves ", ledge_in, "/", ledge_out,
               " mm on the ", (mouth_d - inner_d)/2, " mm heater ledge, against ",
               ledge_min, " required. The LEDGE WIDTH is what limits sensor ",
               "size here, not the plate thickness -- 1.6 mm does not fit"));
    assert(top > heater_shelf_t + 1.0,
           str("sensor pocket top ", top, " leaves under 1 mm above the ",
               heater_shelf_t, " mm heater shelf: nothing to bore into"));
    // -Y, i.e. 270 degrees -- the mid-gap of an even bolt circle started at 0.
    translate([0, -r_c, heater_shelf_t - eps])
        cylinder(d=bore, h=top - heater_shelf_t + eps);
}
function tsense_axial_r(window_d) =
    ((window_d + (flare_inner - window)) + (window_d + flare_extra)) / 4;
function tsense_axial_top(clear=0.2) = cart_t - pocket_depth - clear;

// Membrane-side thermometry, bored in from an edge at `edge_dist` from centre.
// Touches neither face, so it crosses no seal. SQUARE BENCH FIXTURE ONLY -- see
// cartridge_tsense_axial() above for why this must not be used on the probe.
module cartridge_tsense_cut(edge_dist, bore=3.2, standoff=1.0, eps=0.02) {
    depth = edge_dist - coupon/2 - standoff;
    assert(depth > 3.0, "sensor bore too shallow to reach the seal land");
    translate([0, -edge_dist - eps, cart_t/2])
        rotate([-90, 0, 0]) cylinder(d=bore, h=depth + eps);
}

// The consumables this core implies, for the cut list.
module echo_consumables(seat_w, seat_h) {
    echo(str("coupon ", coupon, " x ", coupon, " mm keyed; window ", window,
             " x ", window, " mm; gross free area ", window*window, " mm2"));
    echo(str("membrane gasket ", coupon, " x ", coupon, " outer, ", window,
             " x ", window, " window; seat gasket ", seat_w, " x ", seat_h,
             " outer, ", aperture_far, " x ", aperture_far, " window"));
}

// ============================================================================
// CLAMPED FACE SEAL -- the printable bed
// ============================================================================
//
// WHY THIS EXISTS. The bed above (`cartridge_core_cuts_round`) does not print.
// Photographed 2026-09-05 on a real carrier: a web of filament strung right
// across the aperture, ragged slivers on the flange face, and a groove of
// visibly uneven depth. That is not a slicer setting, it is the geometry, and
// the mechanism is exact.
//
// The carrier prints WET FACE DOWN (`carrier_printed()` mirrors it), because
// the flange is 6 mm wider than the spigot and any other orientation puts that
// step in mid-air. Wet face down turns every wet-side feature upside down:
//
//   1. The membrane seat is `membrane_t` = 0.18 deep -- LESS THAN ONE LAYER.
//      There is no way to print a 0.18 mm step; the slicer either drops it or
//      places it a whole layer out, and the 0.862 mm ledge that survives is a
//      single free-floating bead 0.18 mm above the plate. Those are the slivers.
//   2. The O-ring groove, inverted, becomes a CEILING. Its floor -- the surface
//      that sets squeeze -- is an annulus from the flare cone (Ø16.48) out to
//      Ø19.58, printed over air, and its inner boundary is the OPEN APERTURE.
//      An annular ledge with no inner anchor is bridged straight across the
//      hole: those are the strands in the photograph.
//   3. Nothing is a multiple of anything. Groove 0.75 deep (3.75 layers) and
//      1.55 wide (~3.9 beads), so the floor is one bridged layer plus gap fill.
//      That is the uneven groove, and since squeeze = 1 - depth/cord, an uneven
//      groove IS an uneven seal.
//
// THE FIX IS TO MOVE THE BED, not to tune it. The groove goes into the
// RETAINER, which is a flat ring and prints groove-up on solid material; the
// carrier's wet face becomes a plain flat land with one tapered aperture. The
// seal is unchanged in kind -- the membrane is still nipped between an O-ring
// on one side and a flat land on the other -- it is merely mirrored, so that
// every surface that matters is printed onto something instead of over nothing.
//
// Consequences, all of them wanted:
//   - the carrier has NO feature under one layer and NO bridge (the aperture
//     opens downward as a cone, so each layer's hole is wider than the one
//     below it);
//   - the groove now has a REAL inner wall, so the ring cannot migrate over
//     the gas path -- the failure `mem_ring_inner_d` above only tripwires;
//   - the groove is on the WET side of the membrane, so it stops counting
//     against the 5.0 cm3 connected-volume budget;
//   - the vestigial Ø22 heater shelf goes with it (RING-PCB.md moved the heater
//     into the spigot bore, head-side), which removes 380 mm3 of cavity.
//
// SIZED FOR THE RING IN THE DRAWER: 17.0 x 2.5, against the 17.0 x 1.0 the
// legacy bed uses. The fat cord is not a compromise, it is the second half of
// the fix: the DIN cord tolerance is an ABSOLUTE band, so it costs 3.6 squeeze
// points on a 2.5 cord where it cost 12.1 on a 1.0, and the groove depth may
// then err by tenths instead of hundredths. Ø20 x 2 was the alternative and
// does not fit: its groove would put the membrane disc at Ø28, which collides
// with the Ø32.1 bolt circle. Ø14 x 2.5 is bore-inside-the-window, dead on
// sight.

face_ring_id   = 17.0;      // ON HAND, uncatalogued: measure before trusting
face_ring_cord = 2.5;
// DIN ISO 3601-1 / DIN 3771 tolerance rows, same table as mem_cord_tol above,
// one band up: 1.8 < d2 <= 2.65.
face_cord_tol  = 0.09;
// 0.21, not 0.22. The supplier's own table rows are d1 <= 18 -> +/-0.21 and
// d1 <= 20 -> +/-0.22; 17 is in the FIRST row and this had taken the second.
// Corrected from the ORD-5700/supplier-table review, 2026-09-05.
face_id_tol    = 0.21;
// The membrane is part of the gland stack, so its tolerance is part of the
// squeeze band -- and it was missing entirely. PMV15T is 0.18 +/- 0.03, so it
// spends 0.06 mm of gap band, which is COMPARABLE TO THE WHOLE DEPTH ALLOWANCE
// and bigger than a sorted cord's contribution. Leaving it out was the single
// largest omission in the band.
membrane_t_tol = 0.03;
// Inner groove wall. 0.8 mm, and at this profile's 0.6 line width that is ONE
// bead plus a third -- not the two beads the first version of this comment
// claimed. It cannot be widened: the wall stands between the Ø16 window and the
// groove ID, and the groove ID is pinned near the ring's own ID because a face
// ring whose bore is smaller than the inner wall has to be STRETCHED over it.
// At Ø17 nominal, 0.8 already costs 3.5% stretch; 1.2 (two real beads) would
// cost 8.2% and break the 5% rule.
//
// It is retention, not sealing: the wall stops the ring migrating over the
// window during assembly and carries no load once the retainer is down. A
// single 0.6 bead 1.8 mm tall is a real wall. If that proves not to be true on
// the part, the ways out are a Ø15 window (176.7 mm2, under the 180 floor), a
// Ø20 bed ring (head grows to Ø42), or a narrower line width for this part --
// all three are sourcing or profile decisions, not CAD ones.
// The same profile's wall line width. The inner groove wall was specified as
// "two 0.4 beads" -- that was a 0.4-nozzle assumption, and this process prints
// 0.6-wide walls with the classic generator. See face_wall_min below.
face_line_w    = 0.6;
// DEFINED ABOVE face_wall_min ON PURPOSE: face_wall_min is derived from it, and
// OpenSCAD does not resolve forward references at top level -- it silently
// yields undef and every dimension downstream goes with it.
//
// MEASURED ON THE PRINTED PART, 2026-09-05: 0.8 was 1.33 beads at the 0.6 line
// width, so the classic generator laid one bead and gap-filled a 0.2 sliver.
// The result was a ridge rough enough to damage the PTFE membrane clamped
// against it. Narrow lands here must be an INTEGER number of beads; 1.2 is
// exactly two. The window shrinks to hold face_groove_id -- see window_d --
// because growing the groove instead would raise install stretch to 8.24%.
face_wall_min  = 2 * face_line_w;
// Groove width as a multiple of cord. 1.45 optimised the worst-corner FILL and
// ignored RETENTION, which is the failure that actually happened: 1.45 * 2.5 =
// 3.625 radial on a 2.456 thinned cord leaves the ring 1.125 mm of radial
// freedom, so a stretched ring is not captured and climbs the inner wall out
// of the groove during assembly (observed 2026-09-05). Parker ORD 5700 Design
// Chart 4-3 gas/vacuum row for a 2.5 cord is 3.175 mm, which is this factor:
// slop drops to 0.36 mm and fill rises into the upper half of the 60-85% band
// rather than sitting near its floor. Fill is asserted below, so a cord that
// does not fit this width fails the build instead of jamming the groove.
// Parker's exact 3.175 FAILS the hydraulic-lock assert at 85.11% worst-corner
// fill, and that is not a rounding problem: their row assumes their groove
// depth, ours is set by the squeeze target and quantized to 0.12 layers, so the
// same width sits fuller. 3.25 is the nearest width that clears 85% with margin
// (83.1%). Honest about what it buys: radial slop 0.585 -> 0.397 mm, a real but
// MODEST improvement. If the ring still climbs out on the printed part, the
// remedy is a retaining lip on the inner wall, not more narrowing -- there is no
// more width left to give before the ring locks.
//
// 3.25 -> 3.18 on Fab's ask 2026-09-06, which is ALL the assert allows: 3.175 --
// Parker's exact gas/vacuum figure -- still fails at 85.1078% worst-corner fill,
// the same number this note already recorded, so removing the membrane seat
// bought no room here.
//
// DO NOT "CORRECT" THIS TO THE ISO 3601 WIDTH. That table's flange-seal row for
// a 2.5 cord is 3.90 x 1.90, and its neighbours (2.00 -> 3.40, 2.62 -> 4.00,
// 3.00 -> 4.60) all sit at 61-67% fill, so 3.90 is genuinely what the standard
// says and it is tempting: it would put this gland at 69.3% worst-corner fill
// instead of 84.97%. It was proposed on 2026-09-06 and is WRONG FOR THIS PART
// on two counts, both already known above:
//   1. ISO 3601's flange row is the GENERAL-PURPOSE one. This is a gas seal,
//      and Parker ORD 5700 Chart 4-3's gas/vacuum row is 3.175 for a 2.5 cord.
//   2. The wide groove is the configuration where the stretched ring CLIMBED THE
//      INNER WALL AND CAME OUT during assembly, observed 2026-09-05. Widening
//      walks straight back into a measured failure.
// It also costs 2 mm of head diameter (38 -> 40, cap 43 -> 45), because the
// bolt circle follows the groove OD.
face_groove_w_factor = 3.18 / 2.5;
// THE BUILD LAYER THIS BED IS QUANTIZED TO, and it is READ OFF THE PROFILE, not
// chosen: cad/profiles/process_asa_seal.json slices this part at 0.12 with a
// 0.2 first layer. It was 0.2 here for a day and that was simply wrong -- a
// groove depth that is not an integer number of layers is a depth the SLICER
// picks, and squeeze is 1 - gap/cord, so the slicer would be picking a seal
// dimension. tools/profile_check.py compares these two numbers and the Makefile
// runs it, because a constant that has to track a JSON file three directories
// away will otherwise drift the first time either moves.
face_layer_h   = 0.12;
face_first_layer_h = 0.2;
// Membrane counterbore in the retainer's underside. Was 2 * face_layer_h: two
// layers, so the disc is located without asking the slicer to print a fraction
// of one, and the retainer bottoms on the carrier flange OUTSIDE it, which is
// what made squeeze geometric rather than a function of screw torque.
//
// ZERO ON FAB'S INSTRUCTION 2026-09-06: "i dont think we need that membran
// seat, i just cut a square out of the PTFE and throw it there."
//
// KNOW WHAT THIS GIVES UP, because it is not just a located disc. A square
// cannot both fit the seat and reach the groove -- the largest square the
// O26.5 seat took was 18.74 across, and the smallest that covers the groove OD
// plus its rim is 26.10 -- so a hand-cut square was never sitting in the seat
// anyway. It lands on the SEALING FACE, holds the joint open by the membrane
// thickness, and takes the gap from 1.82 to 2.00, i.e. squeeze from 25.89% to
// 18.56%, BELOW the 20% floor. That is the looseness Fab could feel, and
// removing the seat makes it the permanent design rather than a fit error.
//
// What replaces the lost datum: nothing here. The joint now bottoms wherever
// the membrane happens not to be, so the assembled gap depends on where a
// hand-cut square lands and on how much 0.18 mm PTFE creeps under six M2.5
// screws. face_gap() below still reports the geometric number and it is now an
// ESTIMATE, not a datum. MEASURE THE ASSEMBLED GAP before trusting a squeeze
// figure off this build.
//
// The alternative that was NOT taken, recorded so it does not have to be
// rediscovered: enlarge the seat instead of deleting it, out past the largest
// square anyone would cut, and keep a narrow bottoming land outboard of it.
// That keeps squeeze geometric AND swallows a rough square. It costs a thinner
// land (the bolt circle at r 15.25 ends up inside the pocket) and was not
// modelled.
face_seat_depth = 0;
face_disc_ledge = 1.0;      // membrane rim outboard of the groove
face_squeeze_target = 0.25;

// --- derived ---------------------------------------------------------------

// The groove's inner wall stands on the retainer bore, which is the window.
// PRECONDITIONS, because everything below is a derivation and a derivation
// cannot police its own inputs. Measured 2026-09-05: with face_layer_h = -0.12
// the model exported successfully, two closed volumes, announcing a groove
// "2.28 deep = -19 layers" -- every downstream assert passed, because each was
// retesting a value round() or ceil() had just produced. Nonsense in, nonsense
// out, silently, all the way to an STL. These are the only checks here that
// test an INPUT rather than an output.
assert(face_layer_h > 0 && face_first_layer_h > 0 && face_line_w > 0,
       str("build parameters must be positive: layer ", face_layer_h,
           ", first layer ", face_first_layer_h, ", line width ", face_line_w));
assert(face_ring_id > 0 && face_ring_cord > 0,
       str("the ring must have positive dimensions: ", face_ring_id, " x ",
           face_ring_cord));
assert(face_wall_min > 0 && face_disc_ledge > 0 && face_groove_w_factor > 0,
       "wall, ledge and groove-width factor must be positive");
assert(face_squeeze_target > 0 && face_squeeze_target < 1,
       str("squeeze target ", face_squeeze_target, " is not a fraction"));
assert(membrane_t > 0 && membrane_t_tol >= 0 && membrane_t_tol < membrane_t,
       "membrane thickness and its tolerance are not physical");

function face_groove_id(window_d) = window_d + 2*face_wall_min;
// The ring is stretched onto that wall. Same 5% rule as the radial ring.
function face_stretch(window_d) = face_groove_id(window_d)/face_ring_id - 1;
function face_cord_fitted(window_d, cord=face_ring_cord) =
    cord * (1 - face_stretch(window_d)/2);
// Depth, quantized to the build layer. Solved so that the ASSEMBLED gap --
// groove depth plus the seat's 0.02 mm of slack over the membrane -- lands as
// close to face_squeeze_target as an integer layer count allows.
// WHERE THE LAYER BOUNDARIES ARE, measured from the plate, and that depends on
// which face is down. Printed with the groove UP the groove floor is cut from
// above into a part whose own height is already first_layer + n*layer, so a
// depth that is a whole multiple of face_layer_h lands on a boundary: datum 0.
// Printed with the groove DOWN the roof is built up FROM the plate, where the
// ladder is first_layer + n*layer -- and 1.80 is not on that ladder at all
// (0.2+13*0.12 = 1.76, 0.2+14*0.12 = 1.88). Quantizing to the wrong datum does
// not fail loudly; the slicer just picks a neighbouring layer and moves a seal
// dimension whose entire window is 0.15 mm.
// WHICH FACE OF THE RETAINER GOES ON THE PLATE. It lives HERE, not in the
// consumer, and that is not a style choice: a consumer that re-assigns a
// variable declared in an included file has that assignment HOISTED to the
// include site, where its own locals do not exist yet. OpenSCAD then warns
// about a variable defined two lines above and silently evaluates the
// expression with undef -- measured 2026-09-05, `b = a ? 1 : 2` gives 1 alone
// and 2 behind an include. A seal dimension must never be decided that way.
//
// ============================================================================
// ORIENTATION IS FAB'S DECISION, IN EITHER DIRECTION. DO NOT CHANGE IT ALONE.
// ============================================================================
// true  = groove UP   = sealing face is a TOP surface. THE CURRENT DEFAULT,
//                       chosen by Fab on 2026-09-06.
// false = groove DOWN = sealing face is a BED surface. The original objective.
//
// GETTING THE GLAND ONTO THE PLATE WAS THE GOAL, and it was pursued properly
// before being given up. Four plates, all on the machine, all 0.12 ASA:
//
//   1  groove-down, seat, 3.25   spaghetti out of the empty middle
//   2  groove-down, seat, 3.25   held; groove roof full of voids, unusable
//   3  groove-down, seat, 3.25, bridge fan 100   detached at ~layer 12
//   4  groove-down, NO seat, 3.18  printed clean, no spaghetti at all --
//      Fab's fix: dropping the seat put the O15.2-17.6 inner wall ON THE PLATE
//      instead of starting 61.8 mm2 of it in mid-air at z=0.24. Verdict off the
//      plate: "that worked, but i probably wouldn't use it. the groove/bridge
//      is not very clean."
//
// So the bed-side route reaches a part that prints reliably and a SEALING
// SURFACE THAT IS NOT GOOD ENOUGH. What remains is not a slicer setting:
//   - machine the groove after printing (clean, no size cost, needs a lathe)
//   - trapezoidal groove with self-supporting flanks -- but the gland is
//     volume-constrained at 79% fill, so a chamfer that removes volume LOCKS
//     the ring (roof 1.8 on the same mouth = 101% full). Self-support has to be
//     bought by widening the mouth 3.18 -> ~4.96, which grows the head ~3.5 mm.
//   - bridge_flow > 1, the last cheap lever, low expectation
// Fab chose the fourth option instead: accept a top-surface sealing face.
//
// WHAT THAT COSTS, so it is not forgotten: the seal is now made on layer lines
// instead of on glass-flat PEI. Nobody has measured what that does to this
// joint. If the assembled seal leaks, THIS is the first suspect, and the list
// above is what to go back to -- not another fan or speed experiment.
//
// The waiver still cannot be set from a consumer (the hoist above), so going
// back to the bed side means passing -D on the command line, where it shows up
// in the build invocation. An agent
// flipped this flag twice in one session without being asked -- once silently,
// inside a commit doing two unrelated things Fab had requested. Fab: "the whole
// point of all this is to get the groove on the bed-side. you just cheated."
// Whichever way it points, it is a design decision and it is Fab's.
face_groove_up = true;           // Fab, 2026-09-06 -- see the four plates above
// Named for the direction it actually guards. A single "waiver" set true in this
// file to make groove-up the default would have waived BOTH directions and left
// the assert unable to fire at all -- written that way first, caught by testing
// it, which is the only reason it is not still like that.
face_groove_down_waiver = false;
assert(face_groove_up || face_groove_down_waiver,
       str("face_groove_up = false puts the sealing face back on the BED. That ",
           "is the original objective and it is not forbidden -- but it was ",
           "retired on evidence (four plates, GLAND-ON-THE-BED.md), and the ",
           "clean-printing version of it produced a groove roof Fab rejected. ",
           "Going back to it is a decision, not a default: pass ",
           "-D face_groove_down_waiver=true and say why in the commit."));

// A FUNCTION, not a variable, so it is resolved lazily and cannot be caught by
// the same hoist.
function face_depth_datum() = face_groove_up ? 0 : face_first_layer_h;

// DOES THE MEMBRANE FIT INSIDE THE SEAT, or does it hold the joint open?
// This is the whole difference between the two designs and it was implicit
// before, which made it wrong the moment face_seat_depth went to 0.
//
//  seat >= membrane_t  the disc is recessed, the retainer's face bottoms on the
//                      CARRIER, and the ring is squeezed to (seat+depth) - t.
//  seat <  membrane_t  the membrane stands proud of the recess by (t - seat), so
//                      the FACE bottoms on the MEMBRANE and rides that much
//                      higher. Working it through: the roof ends up depth + t
//                      above the carrier and the membrane top is t above it, so
//                      the gap is just `depth` -- the seat and the membrane
//                      thickness cancel out of the answer entirely.
//
// Fab, 2026-09-06: "the o-ring is thick enough to stand out of the groove and
// touch the membrane first." True -- it stands 0.696 mm proud -- but what SETS
// squeeze is where the joint stops, not what touches first, and without a seat
// the stop is the membrane.
function face_seat_offset() =
    face_seat_depth >= membrane_t ? face_seat_depth - membrane_t : 0;
function face_groove_depth(window_d) =
    face_depth_datum()
    + round((face_cord_fitted(window_d)*(1 - face_squeeze_target)
             - face_seat_offset() - face_depth_datum()) / face_layer_h)
      * face_layer_h;
// What the ring is actually squeezed to.
//
// THE OLD FORM WAS `depth + face_seat_depth - membrane_t`, which silently
// assumed the disc was always recessed. At face_seat_depth = 0 that under-reports
// the gap by a whole membrane thickness: it would have derived depth 2.04 and
// reported gap 1.86 / squeeze 24.26%, where the assembled joint actually holds
// 2.04 and squeezes 16.9% -- BELOW the 20% floor, reported as comfortably inside
// it. 0.18 mm is 7.4 squeeze points on this cord; the whole budget is 15.
function face_gap(window_d) =
    face_groove_depth(window_d) + face_seat_offset();
function face_groove_w() = face_groove_w_factor * face_ring_cord;
function face_groove_od(window_d) = face_groove_id(window_d) + 2*face_groove_w();
function face_disc_d(window_d) = face_groove_od(window_d) + 2*face_disc_ledge;
// Squeeze and fill, as functions of the corner being asked about rather than of
// the nominal -- the nominal is the one number that cannot fail.
function face_squeeze(window_d, cord, gap) = (cord - gap) / cord;
function face_fill(window_d, cord, gap) =
    (PI/4 * cord*cord) / (face_groove_w() * gap);
// The groove-depth error at which the thin end of the cord band reaches `floor`.
// DERIVED, exactly as mem_depth_tol_max() is: nobody has measured what depth a
// printed retainer holds, so this is stated as the REQUIREMENT it is.
// Two of them, because this bed is bounded at BOTH ends and by different rings.
// The floor (a leak, now) is reached by the THIN end of the cord band in a
// groove cut too deep; the ceiling (compression set, over years) by the FAT end
// in one cut too shallow. Quoting only the floor -- which is what the legacy bed
// did -- hides the tighter of the two.
// BOTH ENDS NOW CARRY THE WHOLE CHAIN, which they did not before: these used
// the NOMINAL-ID stretch in every case, so face_id_tol never reached squeeze,
// fill, or the quoted depth requirement at all -- it was declared, echoed, and
// inert. And membrane_t was treated as exact.
//
// The corners pair the extremes that hurt:
//   FLOOR   thinnest cord, least stretch-thinning (fat ID), thinnest membrane
//           (which OPENS the gap, because the seat is fixed and the membrane
//           fills part of it)
//   CEILING fattest cord, most thinning (thin ID), thickest membrane
function face_stretch_at(window_d, id) = face_groove_id(window_d)/id - 1;
function face_cord_at(window_d, cord, id) = cord * (1 - face_stretch_at(window_d, id)/2);
// WHICH ID GOES WITH WHICH CORD END, and I had it backwards in both. Stretch is
// groove_id/ring_id - 1, so a THIN ring stretches MORE and its cord thins MORE.
// The smallest fitted cord -- the floor corner -- is therefore the thin cord on
// the THIN ID, not on the fat one; and the fattest fitted cord is the fat cord on
// the FAT ID, which stretches least. Pairing them the other way flattered the
// floor by 0.3 squeeze points and turned a failing build into a passing one.
// Caught by the ORD-5700 review, which reproduced 2.35187 and 2.56065 where this
// model produced 2.3827 and 2.5607.
function face_depth_tol_max(window_d, floor, cord_tol=face_cord_tol) =
    face_cord_at(window_d, face_ring_cord - cord_tol, face_ring_id - face_id_tol)
      * (1 - floor)
    - (face_gap(window_d) + membrane_t_tol);
function face_depth_tol_min(window_d, ceiling, cord_tol=face_cord_tol) =
    (face_gap(window_d) - membrane_t_tol)
    - face_cord_at(window_d, face_ring_cord + cord_tol, face_ring_id + face_id_tol)
      * (1 - ceiling);

// --- modules ---------------------------------------------------------------

// The carrier's whole wet-side core, for the clamped bed: one tapered aperture
// and nothing else. `dry_d` is the spigot bore, so the cone lands exactly on it
// and there is no ledge anywhere in the part to bridge. Cut with the DRY face
// at z = 0 and the wet face at z = plate_t.
module clamped_core_cuts(window_d, dry_d, plate_t, eps=0.02) {
    assert(dry_d >= window_d,
           str("the dry side Ø", dry_d, " is narrower than the Ø", window_d,
               " window: the aperture would close going down, which is both a ",
               "constriction in front of the membrane and an overhang"));
    assert(atan(((dry_d - window_d)/2) / plate_t) <= 45,
           str("aperture taper is ", atan(((dry_d - window_d)/2)/plate_t),
               " degrees off vertical; over 45 it needs support"));
    // Overshoot ALONG THE CONE'S OWN SLOPE, not straight out. A cone extended
    // with its end diameters unchanged is a slightly different cone: it would
    // put the window at Ø(window_d + 2*eps*slope) and leave a four-micron ledge
    // where the aperture meets the spigot bore -- a coincident face turned into
    // a near-coincident one, which is the shape CGAL makes slivers out of.
    over = (dry_d - window_d) * eps / plate_t;
    translate([0, 0, -eps])
        cylinder(d1=dry_d + over, d2=window_d - over, h=plate_t + 2*eps);
}

// The bed itself, cut into the retainer's underside. Call with the underside at
// z = 0, cutting into +Z; the caller mirrors the part for printing.
module clamped_bed_cuts(window_d, eps=0.02) {
    depth = face_groove_depth(window_d);
    // Membrane seat, +0.4 on diameter so a hand-cut disc drops in. GUARDED:
    // face_seat_depth is 0 by default now (see its declaration), and an
    // unguarded cylinder of height eps here is a degenerate sliver that CGAL
    // will still union in -- a zero-depth "seat" that shows up as a facet ring
    // on the sealing face and would be invisible in every echoed dimension.
    if (face_seat_depth > 0)
        translate([0, 0, -eps])
            cylinder(d=face_disc_d(window_d) + 0.4, h=face_seat_depth + eps);
    // The groove, as an ANNULUS. A plain cylinder here would remove the inner
    // wall -- which is the entire point of this bed -- and would do it silently:
    // the part still renders as one solid and every dimension still echoes.
    // Overshoots staggered against the seat above for the same coincident-face
    // reason as the round core.
    translate([0, 0, -2*eps])
        difference() {
            cylinder(d=face_groove_od(window_d),
                     h=face_seat_depth + depth + 2*eps);
            translate([0, 0, -eps])
                cylinder(d=face_groove_id(window_d),
                         h=face_seat_depth + depth + 4*eps);
        }
}
