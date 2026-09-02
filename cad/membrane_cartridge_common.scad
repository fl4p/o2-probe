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
gasket_t = 1.0;             // uncompressed elastomer sheet
gasket_squeeze = 0.25;      // fraction compressed by the retainer

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

m25_clear = 2.8;            // M2.5 clearance (declared default, UNMEASURED profile)
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
assert(land >= 2.0,
       "seal land under 2 mm: not enough width to close a compression seal");

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

    translate([0, 0, cart_t - pocket_depth])
        cylinder(d=coupon_d + 0.3, h=pocket_depth + eps);

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

// Membrane-side thermometry, bored in from an edge at `edge_dist` from centre.
// Touches neither face, so it crosses no seal.
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
