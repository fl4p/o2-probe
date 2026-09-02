/*
 * O2 probe — buried head, printed ASA
 * Units: millimetres. Z runs from the tube joint toward the tip.
 *
 * Scope: the parts of the head that do NOT depend on D_eff. Window area stays
 * parametric because step 1 has not run, and PLAN.md forbids freezing it before
 * it does. What is designed here is the tube joint, the internal cavity and its
 * volume budget, the two cartridge wells with their seat land and drain, the
 * retainer, the stand-off guard, and the tip nose.
 *
 * Architecture follows the 2026-09-02 enclosure decision in MEMBRANE.md:
 * bought tube for the potted body, printed ASA head bonded onto its end, PP
 * cartridge sealed to the ASA by elastomer compression, no sustained strain in
 * plastic at temperature -- so the head uses captive nuts, never a self-tapped
 * thread (that shortcut is allowed only in the <=55 C bench fixture).
 *
 * MEASURED INPUTS ARE REFUSED, NOT GUESSED. The four `undef` values below are
 * the ones cad/README.md already says to measure before printing a functional
 * enclosure. Render provisionally with, e.g.:
 *   make head-provisional
 */

include <membrane_cartridge_common.scad>

$fn = 96;
heps = 0.02;

part = "assembly";   // assembly, head, retainer, guard, cavity
exploded = false;

// ------------------------------------------------- MEASURE THESE

tube_od_meas = undef;      // MEASURE: actual OD of the tube stock, incl. ovality
board_env_front = undef;   // MEASURE: populated swept envelope above the board
board_env_back = undef;    // MEASURE: populated swept envelope below the board
cell_seated_h = undef;     // MEASURE: can top above board top, real cell in a
                           //          real socket (PLAN.md risk 11 -- the plan's
                           //          own ~8.8 mm is computed, not measured)

assert(!is_undef(tube_od_meas),
       "UNMEASURED: tube_od_meas -- measure the tube OD and its ovality");
assert(!is_undef(board_env_front),
       "UNMEASURED: board_env_front -- tallest component above the board plane");
assert(!is_undef(board_env_back),
       "UNMEASURED: board_env_back -- tallest component below the board plane");
assert(!is_undef(cell_seated_h),
       "UNMEASURED: cell_seated_h -- seat a real cell in a real socket and measure");

// ------------------------------------------------- design parameters

board_w = 20.0;             // KiCad Edge.Cuts, controlled
board_t = 1.0;              // KiCad, controlled
cell_d = 14.4;              // DS-0637 Iss. 2
bore_margin = 1.5;          // radial clearance around the board swept envelope

bond_gap = 0.20;            // radial adhesive gap on the tube joint
socket_len = 14.0;          // bonded overlap; also the continuous seal band
wall_min = 2.4;             // minimum printed wall anywhere on the head

// Cartridge well. The flange is narrower than the bench cartridge's square one:
// a 42 mm head cannot host two square flanges 90 degrees apart. The SEALING
// CORE is identical (see membrane_cartridge_common.scad); only the outline and
// bolt pattern differ, which is what the D_eff transfer argument actually needs.
cart_w = coupon + 2*3.0;    // 21.0 circumferential
cart_l = coupon + 2*4.0;    // 23.0 axial
well_land = 2.5;            // seat gasket land around the mouth
screw_inset = 4.0;
m25_nut_af = 5.0;           // DIN 934 M2.5 across-flats -- captive, not self-tap
m25_nut_t = 2.0;

port_angles = [45, 315];    // both in the lower quadrants; -Y is DOWN
guard_gap = 3.5;            // stand-off between guard and membrane
guard_wall = 2.0;
guard_ramp = 6.0;           // lead-in and lead-out so it does not catch on
                            // insertion or withdrawal

nose_len = 12.0;            // bullet nose, eases insertion into the pile
drain_w = 3.0;              // drain notch at the low edge of each well

// ------------------------------------------------- derived

board_swept = board_env_front + board_t + board_env_back;
board_diag = sqrt(pow(board_w, 2) + pow(board_swept, 2));
bore_d = max(board_diag + 2*bore_margin, cell_d + 2*bore_margin);

// The head OD is not a style choice: it is forced. A flat facet wide enough for
// the cartridge sits at f = sqrt(R^2 - (cart_w/2)^2) from the axis, and the
// cartridge plus its seat land must fit between that facet and the bore.
facet_need = cart_t + well_land_floor();
function well_land_floor() = wall_min;      // material under the seat land
head_r_min = sqrt(pow(bore_d/2 + facet_need, 2) + pow(cart_w/2, 2));
head_od = 2 * ceil(head_r_min + 0.5);
facet_dist = sqrt(pow(head_od/2, 2) - pow(cart_w/2, 2));

// Connected volume budget. Length is the free variable and it is tightly
// bounded: a 20 mm board in a round bore spends volume fast.
cell_disp = PI * pow(cell_d/2, 2) * cell_seated_h;
cav_per_mm = PI * pow(bore_d/2, 2) - board_w * board_t;   // net volume per mm
cav_len_max = (5000 + cell_disp) / cav_per_mm;            // what 5.0 cm3 buys
cav_len = 15.0;
cav_gross = PI * pow(bore_d/2, 2) * cav_len;
cav_board = board_w * board_t * cav_len;
// Each port adds the duct through the head wall plus the cartridge's own core.
// Counting the bore ALONE is what let this file pass at 4.99 cm3 while the
// measured mesh was 11.21 -- the same defect the bench fixture had.
port_duct = pow(aperture_far, 2) * (facet_dist - bore_d/2);
port_core = pow(aperture_far, 2) * heater_shelf_t
          + (cart_t - pocket_depth - heater_shelf_t)/6
            * (pow(flare_inner,2) + 4*pow((flare_inner+window)/2,2) + pow(window,2));
cav_net = cav_gross - cav_board - cell_disp
        + len(port_angles) * (port_duct + port_core);

head_len = socket_len + cav_len + nose_len;
cart_stack = cart_t + gasket_t;             // into the well, before the retainer
retainer_t = 3.0;

// ------------------------------------------------- gates

assert(bore_d >= cell_d + 2*bore_margin,
       "bore does not clear the cell can");
assert(facet_dist - cart_t >= bore_d/2 + wall_min,
       "cartridge well would break into the bore: no seat land left");
// ARCHITECTURE WRITTEN OFF 2026-09-02 (see cad/README.md, "Buried head").
// A facet wide enough for a cartridge forces a thick wall, and every mm of that
// wall is a 16x16 duct of dead gas behind the window. This is not tunable.
accept_written_off = false;
assert(cav_net <= 5000 || accept_written_off,
       str("connected volume ", cav_net/1000,
           " cm3 exceeds the 5.0 cm3 target. This architecture is WRITTEN OFF -- ",
           "use o2_probe_head_end.scad. Set -D accept_written_off=true only to ",
           "regenerate the comparison renders."));
assert(cart_l < cav_len + 2*wall_min + 4,
       "cartridge flange longer than the cavity plus its end material");

echo(str("MEASURED IN: tube OD ", tube_od_meas, ", board swept ", board_swept,
         ", cell seated ", cell_seated_h));
echo(str("bore ", bore_d, " mm (board diagonal ", board_diag, ")"));
echo(str("head OD ", head_od, " mm -- FORCED by board + cartridge core, not chosen"));
echo(str("guard OD ", head_od + 2*(guard_gap + guard_wall), " mm at the two ports"));
echo(str("connected volume ", cav_net/1000, " cm3 nominal of a 5.0 cm3 budget",
         " (gross ", cav_gross/1000, ", board -", cav_board/1000,
         ", cell -", cell_disp/1000, ")"));
echo(str("cavity length ceiling ", cav_len_max,
         " mm -- 5.0 cm3 divided by ", cav_per_mm, " mm3 per mm of bore"));
echo(str("head length ", head_len, " mm; fasteners 4x M2.5 captive nuts per port"));
echo_consumables(cart_w, cart_l);

// ------------------------------------------------- head body

module port_screw_positions() {
    for (sx=[-1,1], sy=[-1,1])
        translate([sx*(cart_w/2 - screw_inset), sy*(cart_l/2 - screw_inset), 0])
            children();
}

// One cartridge well, cut into the facet at the given angle. Local frame: +Z
// points radially outward, +Y along the tube toward the tip.
module at_port(angle) {
    rotate([0, 0, angle]) translate([facet_dist, 0, socket_len + cav_len/2])
        rotate([0, 90, 0]) rotate([0, 0, -90]) children();
}

// The gas that a port adds to the connected volume: the channel from the bore
// out to the well floor, plus the cartridge's own core cuts once it is seated.
// NOT the well itself -- the cartridge body fills that.
module port_gas() {
    translate([0, 0, -(facet_dist - bore_d/2) - heps])
        linear_extrude(facet_dist - bore_d/2 + heps)
            square([aperture_far, aperture_far], center=true);
    cartridge_core_cuts(heps);
}

module well_cuts() {
    // Flat facet, so the seat gasket closes on a plane rather than a curve.
    translate([0, 0, -heps])
        linear_extrude(cart_t + heps)
            keyed_rect(cart_w + 0.3, cart_l + 0.3, key);

    // Mouth through into the cavity.
    translate([0, 0, -(facet_dist - bore_d/2) - heps])
        linear_extrude(facet_dist - bore_d/2 + heps)
            square([aperture_far, aperture_far], center=true);

    // Captive nuts, loaded from the cavity side so nothing is self-tapped.
    port_screw_positions() {
        translate([0, 0, -(facet_dist - bore_d/2) - heps])
            cylinder(d=m25_clear, h=facet_dist - bore_d/2 + cart_t + 2*heps);
        translate([0, 0, -(facet_dist - bore_d/2) - heps])
            cylinder(d=m25_nut_af/cos(30), h=m25_nut_t + heps, $fn=6);
    }

    // Drain notch at the well's low edge. No upward-facing pocket is allowed to
    // hold condensate against the membrane.
    translate([0, -cart_l/2, 0])
        rotate([45, 0, 0]) cube([drain_w, drain_w, drain_w], center=true);
}

module head() {
    difference() {
        union() {
            cylinder(d=head_od, h=socket_len + cav_len);
            // Bullet nose.
            translate([0, 0, socket_len + cav_len])
                cylinder(d1=head_od, d2=head_od*0.45, h=nose_len);
        }

        // Bonded socket over the tube end.
        translate([0, 0, -heps])
            cylinder(d=tube_od_meas + 2*bond_gap, h=socket_len + heps);

        // Gas cavity.
        translate([0, 0, socket_len])
            cylinder(d=bore_d, h=cav_len);

        // No separate board pass-through: the socket bore already clears the
        // tube, and `bore_d` is derived from the board's swept diagonal, so the
        // cavity clears the board by construction. An extra slot here would
        // only add volume to a budget that has none to spare.

        for (a = port_angles) at_port(a) well_cuts();
    }
}

// The connected gas volume as a printable-looking solid. NOT a part: build it
// and measure the mesh. The analytic figure below counts the bore only, and a
// bore-only gate is exactly what let the bench fixture pass at 5.02 cm3 while
// its real connected volume was 7.44.
module cavity() {
    difference() {
        union() {
            translate([0, 0, socket_len]) cylinder(d=bore_d, h=cav_len);
            for (a = port_angles) at_port(a) port_gas();
        }
        // Displaced by the board and by the cell can.
        translate([-board_w/2, -board_t/2, socket_len - heps])
            cube([board_w, board_t, cav_len + 2*heps]);
        translate([0, 0, socket_len + cav_len - cell_seated_h])
            cylinder(d=cell_d, h=cell_seated_h);
    }
}

module retainer() {
    difference() {
        linear_extrude(retainer_t) keyed_rect(cart_w, cart_l, key);
        translate([0, 0, -heps])
            linear_extrude(retainer_t + 2*heps) square([window, window], center=true);
        port_screw_positions()
            translate([0, 0, -heps]) cylinder(d=m25_clear, h=retainer_t + 2*heps);
    }
}

// Independently replaceable coarse guard: it must come off without disturbing
// the cartridge, and its lowest edge stays open so the stand-off gap drains.
module guard() {
    ow = cart_w + 2*guard_wall;
    ol = cart_l + 2*guard_wall;
    oh = guard_gap + guard_wall;
    difference() {
        hull() {
            translate([0, 0, oh - guard_wall/2])
                cube([ow, ol, guard_wall], center=true);
            translate([0, 0, 0])
                cube([ow + 2*guard_ramp*0.4, ol + 2*guard_ramp, 0.1], center=true);
        }
        // Inner stand-off volume.
        translate([0, 0, -heps])
            cube([cart_w, cart_l, 2*guard_gap], center=true);
        // Open the low edge completely: this is the drain.
        translate([0, -ol/2 - guard_ramp, guard_gap/2])
            cube([cart_w, 2*guard_ramp, guard_gap + 2*heps], center=true);
        // Side slots, facing sideways and down, never up.
        for (s = [-1, 1], i = [0:2])
            translate([s*(ow/2), -ol/4 + i*ol/5, guard_gap/2])
                cube([2*guard_wall + 2*heps, 2.5, guard_gap*0.7], center=true);
    }
}

// ------------------------------------------------- assembly

module assembly() {
    e = exploded ? 14 : 0;
    color("Tan") head();
    for (a = port_angles) {
        at_port(a) translate([0, 0, e]) color("LightSteelBlue") retainer();
        at_port(a) translate([0, 0, cart_t + 2.2*e]) color("DimGray") guard();
    }
}

if (part == "assembly") assembly();
else if (part == "head") head();
else if (part == "retainer") retainer();
else if (part == "guard") guard();
else if (part == "cavity") cavity();
else assert(false, "unknown part");
