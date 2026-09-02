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

part = "assembly";   // assembly, head, carrier, retainer, cap, cavity
exploded = false;

// ------------------------------------------------- MEASURE THESE

tube_od_meas = undef;      // MEASURE: actual OD of the tube stock, incl. ovality
board_env_front = undef;   // MEASURE: populated swept envelope above the board
board_env_back = undef;    // MEASURE: populated swept envelope below the board
cell_axial_len = undef;    // MEASURE: how far the cell + its socket project past
                           //          the board end, real cell in a real socket
insert_bore_d = undef;     // MEASURE: your heat-set insert's bore, from ITS
insert_bore_h = undef;     //          datasheet -- brand-specific, do not assume

assert(!is_undef(tube_od_meas),
       "UNMEASURED: tube_od_meas -- measure the tube OD and its ovality");
assert(!is_undef(board_env_front),
       "UNMEASURED: board_env_front -- tallest component above the board plane");
assert(!is_undef(board_env_back),
       "UNMEASURED: board_env_back -- tallest component below the board plane");
assert(!is_undef(cell_axial_len),
       "UNMEASURED: cell_axial_len -- seat a real cell in a real socket and measure");
assert(!is_undef(insert_bore_d) && !is_undef(insert_bore_h),
       "UNMEASURED: insert_bore_d / insert_bore_h -- from the insert's own sheet");

// ------------------------------------------------- design parameters

board_w = 20.0;             // KiCad Edge.Cuts, controlled
board_t = 1.0;              // KiCad, controlled
cell_d = 14.4;              // DS-0637 Iss. 2
cell_h = 8.3;               // DS-0637 Iss. 2
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
flange_margin = 4.0;
// The sealing core lives entirely in the flange, so the flange IS the core.
flange_t = cart_t;
carrier_fit = 0.3;

oring_cord = 1.5;           // CONFIRM this size exists in EPDM or silicone
oring_squeeze = 0.20;       // static radial squeeze, fraction of cord
groove_w_factor = 1.30;     // groove width as a multiple of cord
lead_chamfer = 1.0;         // so the O-ring is not shaved on assembly

retainer_t = 3.0;
bolt_n = 4;                 // retention only now, but 4 keeps it even
bolt_clear_gap = 1.5;       // between well wall and screw hole edge

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

// ------------------------------------------------- derived

board_swept = board_env_front + board_t + board_env_back;
board_diag = sqrt(pow(board_w, 2) + pow(board_swept, 2));
bore_d = max(board_diag + 2*bore_margin, cell_d + 2*bore_margin);

mouth_d = window_d + flare_extra;        // the flare's mouth, in the flange
spigot_d = mouth_d + 2*land;             // wall thick enough to hold a groove
well_d = spigot_d + carrier_fit;         // the bore the spigot seals against
flange_d = spigot_d + 2*flange_margin;

// Radial O-ring groove, cut into the spigot's outside diameter. Seated OD must
// exceed the well bore by the squeeze; groove root follows from that.
groove_root_d = well_d - 2*oring_cord + oring_cord*oring_squeeze*2;
groove_w = groove_w_factor * oring_cord;
spigot_len = groove_w + lead_chamfer + 1.5;   // the assert below, solved
oring_free_id = groove_root_d - 0.4;     // slight stretch onto the groove
bolt_r = spigot_d/2 + bolt_clear_gap + m25_clear/2;

// Head OD: the bore, or the bolt circle plus material around it. NOT a facet at
// a radius, which is the whole point of this variant.
head_od = 2 * ceil(max(bore_d/2 + wall_min, bolt_r + m25_clear/2 + 2.0) + 0.5);
cap_od = head_od + 2*cap_wall;

// Volume, and the structural advantage of putting the cell past the board end:
// BEYOND THE BOARD THERE IS NO BOARD TO CLEAR, so the bore necks to the cell.
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

// The cap must SWALLOW the whole clamped stack, not just the drainage gap. It
// clears the carrier flange and the retainer, then leaves the stand-off in
// front of the membrane, then the solid plowing face.
cap_stack = flange_t + retainer_t;
band_z0 = cap_grip + cap_stack;          // start of the open breathing band
band_z1 = band_z0 + guard_gap;
cap_len = band_z1 + cap_front_t;
window_area = PI * pow(window_d/2, 2);
guard_open = (PI*cap_od - rib_n*rib_w) * guard_gap;

// ------------------------------------------------- gates

assert(bore_d >= cell_d + 2*bore_margin, "bore does not clear the cell can");
assert((spigot_d - spigot_bore)/2 - oring_cord + oring_cord*oring_squeeze >= 1.2,
       "spigot wall too thin under the O-ring groove: it will collapse inward and lose squeeze");
assert(spigot_len >= groove_w + lead_chamfer + 1.5,
       "spigot too short to carry the groove plus its lead-in chamfer");
assert(spigot_bore >= window_d + 2.0,
       "spigot bore constricts the window");
assert(bolt_r - m25_clear/2 > spigot_d/2,
       "bolt circle cuts into the well: fasteners would penetrate the seal");
assert(flange_d <= head_od,
       str("carrier flange ", flange_d, " overhangs a ", head_od, " mm head"));
assert(head_od/2 - cap_screw_depth > neck_d/2 + 1.0,
       "blind cap screw would break into the gas bore");
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
echo(str("O-RING: cord ", oring_cord, ", free ID approx ", oring_free_id,
         "; groove root dia ", groove_root_d, " x ", groove_w,
         " wide; radial squeeze ", oring_squeeze*100, "% -- EPDM or silicone, NOT FKM"));
echo(str("CUT LIST: PMV15T disc dia ", window_d + 2*land,
         " mm, welded into the carrier"));
echo(str("fasteners: ", bolt_n, "x M2.5 into heat-set inserts on a dia ",
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
        cylinder(d=head_od, h=head_len);

        // Bonded socket over the tube end.
        translate([0, 0, -heps])
            cylinder(d=tube_od_meas + 2*bond_gap, h=socket_len + heps);

        // Cavity: full bore only where the board is, then necked to the cell.
        translate([0, 0, socket_len]) cylinder(d=bore_d, h=cav_board_len);
        translate([0, 0, socket_len + cav_board_len])
            cylinder(d=neck_d, h=cav_clear_len + heps);

        // The well the spigot seals into. Its bore IS the sealing surface, so it
        // wants to be printed cleanly -- it is the one feature here whose
        // surface finish is functional.
        translate([0, 0, well_z]) cylinder(d=well_d, h=head_len);
        // Lead-in, so the O-ring is not shaved on assembly.
        translate([0, 0, head_len - lead_chamfer])
            cylinder(d1=well_d, d2=well_d + 2*lead_chamfer, h=lead_chamfer + heps);

        // Heat-set inserts on the bolt circle, blind from the end face.
        translate([0, 0, head_len - insert_bore_h])
            bolt_positions() cylinder(d=insert_bore_d, h=insert_bore_h + heps);

        // Cap retention: BLIND radial holes that stop well short of the bore.
        translate([0, 0, head_len - cap_grip/2])
            cap_screw_positions()
                translate([0, 0, head_od/2 - cap_screw_depth])
                    cylinder(d=selftap_cap, h=cap_screw_depth + heps);
    }
}

// The PP part. Printed here as a FIT MODEL only: the real one is polypropylene,
// with the PMV15T coupon fused into it. A printed disc is not a membrane.
module carrier() {
    difference() {
        union() {
            cylinder(d=spigot_d, h=spigot_len);
            translate([0, 0, spigot_len]) cylinder(d=flange_d, h=flange_t);
        }
        // Gas path straight through the spigot into the flare above it.
        translate([0, 0, -heps]) cylinder(d=spigot_bore, h=spigot_len + 2*heps);
        // Radial O-ring groove. This is the seal.
        translate([0, 0, lead_chamfer + 0.75])
            cylinder(d=groove_root_d, h=groove_w);
        // Lead-in chamfer on the spigot's leading edge.
        translate([0, 0, -heps])
            cylinder(d1=spigot_d - 2*lead_chamfer, d2=spigot_d, h=lead_chamfer + heps);
        // The sealing core, in the flange, wet face at +Z.
        translate([0, 0, spigot_len]) cartridge_core_cuts_round(window_d, heps);
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

// Connected gas volume as a solid, for mesh measurement. A bore-only figure is
// not the connected volume -- that error let the bench fixture's first gate pass
// at 5.02 cm3 against a real 7.44.
module cavity() {
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

module assembly() {
    e = exploded ? 12 : 0;
    color("Tan") head();
    // Gasket drawn at its COMPRESSED height, which is how it sits in service.
    color("DimGray")
        translate([0, 0, well_z + lead_chamfer + 0.75 + groove_w/2 + 1.0*e])
            rotate_extrude() translate([groove_root_d/2 + oring_cord/2, 0])
                circle(d=oring_cord);
    color("Khaki") translate([0, 0, well_z + 2.0*e]) carrier();
    color("LightSteelBlue") translate([0, 0, end_z + flange_t + 3.0*e]) retainer();
    // The cap is a shell that swallows the rest, so it has to travel furthest
    // before an exploded view shows anything.
    color("DimGray") translate([0, 0, head_len - cap_grip + 4.5*e]) cap();
}

// Every printable part, laid out flat and print-oriented, as ONE file. Handing
// a slicer four separate STLs loses a race with its own launch; one file does
// not. The carrier is included as a FIT MODEL -- the real one is PP.
module plate() {
    pitch = head_od + 8;
    color("Tan") head();
    // Flange down: as modelled the flange overhangs the spigot, which is a
    // 90-degree overhang all the way round.
    color("Khaki") translate([pitch, 0, spigot_len + flange_t])
        mirror([0, 0, 1]) carrier();
    color("LightSteelBlue") translate([0, pitch, 0]) retainer();
    color("DimGray") translate([pitch, pitch, 0]) cap();
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
else if (part == "assembly") assembly();
else if (part == "head") head();
else if (part == "carrier") carrier();
else if (part == "retainer") retainer();
else if (part == "cap") cap();
else if (part == "cavity") cavity();
else assert(false, "unknown part");
