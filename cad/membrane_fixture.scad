/*
 * O2 probe — membrane coupon cartridge and step-1 bench chamber
 * Units: millimetres.
 *
 * The cartridge is the SHARED part: the same seal land, aperture and dry-side
 * relief go into the bench chamber now and into the printed ASA probe head
 * later, so the D_eff that qualification step 1 measures transfers to the probe
 * instead of carrying an unstated transfer assumption.
 *
 * Sourced dimensions (do not "improve" without re-reading the source):
 *   - SGX-OX-ROHS-Mini can 14.4 x 8.3 mm, pins Ø0.64, 3 in a row at 2.54 pitch,
 *     row offset 2.50 mm from the body centre  -- DS-0637 Iss. 2, via PLAN.md.
 *   - PMV15T thickness 0.18 +/- 0.03 mm  -- Porex CON-002454 Ver. 5 [S14].
 *   - Target connected gas volume <= 5.0 cm3  -- RESPONSE-CANDIDATE-VOLUME.md.
 *
 * NOT released geometry. Clearances come from an UNMEASURED printer profile
 * (profile_measured = false); the first print is the measurement.
 */

$fn = 96;
eps = 0.02;

part = "assembly";   // assembly, cartridge, retainer, chamber, lid, plenum, die, plug, cavity
exploded = false;

// ---------------------------------------------------------------- parameters

// Gas window. NOT frozen: step 1 pins D_eff, and window area trades directly
// against it. Vary this, not the rest of the fixture.
window = 10.0;              // square aperture seen by the gas
land = 2.5;                 // seal land width around the aperture
coupon = window + 2*land;   // 15.0 mm cut coupon -> 126 per A5 sheet

membrane_t = 0.18;          // PMV15T datasheet nominal
gasket_t = 1.0;             // uncompressed elastomer sheet; SEE NOTE below
gasket_squeeze = 0.25;      // fraction compressed by the retainer

// Dry-side access. The membrane's dry face must see the cavity almost
// immediately: a straight channel behind it is a series diffusion resistance,
// and 5.8 mm of it is what failed the outer-cartridge concept.
straight_web = 0.0;         // unflared depth below the coupon
flare_depth = 3.0;          // 45-degree relief opening into the cavity
flare_inner = 12.0;         // aperture width where the flare meets the shelf
flare_extra = 6.0;          // mouth width = window + this

// Dry-side carrier heater, mirroring the probe: the heat goes into the carrier
// at the land, not into the bulk gas. The seat sits INSIDE the seat gasket's
// window, so the heater and its leads cross no sealing surface -- a channel
// across the seal band would be exactly the bypass leak this fixture exists to
// detect. Leads drop into the cavity and leave through the potted feedthrough.
heater_shelf_t = 1.0;

// Membrane-side thermometry. A blind bore in from the cartridge EDGE, stopping
// short of the seal land: it touches neither face, so again no seal is crossed,
// and it reads the carrier cold spot the condensation model asks for rather
// than an average. Oversized on purpose -- set it to your actual sensor
// carrier, bare WSON-6 or a small breakout.
tsense_bore = 3.2;
tsense_standoff = 1.0;      // material left between bore end and the land

// Wet-side plenum. Sweeps the outer membrane face so the O2 step is applied
// where it belongs. Small on purpose: its own time constant must stay far
// below the membrane's, and -- more important -- it must be IDENTICAL across
// all four step-1 arms so that it cancels in the comparison.
plen_t = 7.5;
plen_cav = 12.5;
plen_h = 5.0;               // must exceed the port bore, or the bore breaks out
plen_tube_id = 3.0;         // smaller than the chamber's: it has to fit in plen_h

// Cartridge frame.
cart_t = 5.0;               // body thickness
cart_margin = 7.0;          // frame material outside the coupon
cart_w = coupon + 2*cart_margin;
retainer_t = 3.0;
m25_clear = 2.8;            // M2.5 clearance hole (declared default)
screw_inset = 4.0;
// Retainer screws self-tap into the lid boss. That is acceptable HERE and not
// in the probe: this fixture runs at <=55 C and is serviced on a bench, while
// the buried head must carry no sustained strain in plastic at 75 C and gets
// nuts or heat-set inserts instead.
selftap_pilot = 2.1;        // M2.5 self-tapping pilot in ASA (declared default)

// Bench chamber. A cylinder above a flush-mounted cell keeps the connected
// volume a single auditable number instead of a sum of pockets.
// Diameter is set by the cartridge bolt circle, not by taste: the retainer
// screws must land in lid material OUTSIDE the cavity or they breach the gas
// volume. Height then buys back the 5 cm3.
cav_d = 18.0;
cav_h = 9.8;                // sized so the CONNECTED volume, not the cavity
                            // alone, lands under the 5.0 cm3 probe target
wall = 3.0;
floor_t = 3.0;
cell_d = 14.4;              // DS-0637 Iss. 2
cell_h = 8.3;               // DS-0637 Iss. 2
cell_fit = 0.4;             // radial slip allowance, UNMEASURED profile
pin_d = 1.2;
pin_pitch = 2.54;           // DS-0637 Iss. 2
pin_row_offset = 2.50;      // DS-0637 Iss. 2
wire_recess_d = 12.0;
wire_recess_h = 4.0;
feed_bore = 4.0;            // potted feedthrough for heater + sensor leads
feed_cup_d = 8.0;
feed_cup_h = 3.0;
plug_fit = 0.25;            // pin undersize, UNMEASURED profile

// Gas ports: printed barbs for soft tubing, so the fixture depends on no
// fitting vendor. Blanking plugs turn the same ports into the leak test.
tube_id = 4.0;
barb_len = 12.0;
barb_wall = 1.2;

m3_clear = 3.4;
m3_nut_af = 5.5;            // DIN 934 M3 across-flats
m3_nut_t = 2.4;
lid_t = 4.0;
seat_t = 3.0;
lid_screws = 4;

// Known-bad calibration part. Cuts a deliberate bypass across the seal land so
// step 1 can demonstrate that the test CATCHES a perimeter leak rather than
// assuming it would.
bypass = false;
bypass_w = 0.4;

// ---------------------------------------------------------------- derived

gasket_gap = gasket_t * (1 - gasket_squeeze);
pocket_depth = membrane_t + gasket_gap;          // retainer closes onto this
aperture_far = window + flare_extra;
cav_volume_mm3 = PI * pow(cav_d/2, 2) * cav_h;
// The connected volume is the cavity PLUS everything above it up to the
// membrane's dry face. Asserting on the cavity alone missed 2.4 cm3 of
// aperture stack -- half as much again as the whole budget allows.
flare_h = cart_t - pocket_depth - straight_web - heater_shelf_t;
flare_vol = flare_h/3 * (pow(flare_inner,2) + pow(window,2)
                         + sqrt(pow(flare_inner,2) * pow(window,2)));
conn_volume_mm3 = cav_volume_mm3
                + pow(aperture_far,2) * (lid_t + seat_t + heater_shelf_t)
                + flare_vol
                + pow(window,2) * straight_web;
cart_bolt_r = (cart_w/2 - screw_inset) * sqrt(2);   // corner screws, so diagonal
lid_bolt_r = cart_bolt_r + 6.0;
body_d = 2*lid_bolt_r + 8.0;
body_h = floor_t + cell_h + cav_h;
grip = body_h + lid_t + seat_t;                     // M3 lid screw length needed
heater_ledge = (aperture_far - flare_inner) / 2;    // ledge width for the heater
tsense_depth = cart_w/2 - coupon/2 - tsense_standoff;
plen_volume_mm3 = plen_cav * plen_cav * plen_h;
cart_stack = plen_t + gasket_t + retainer_t + cart_t;   // M2.5 screw grip
plug_len = body_d/2 + barb_len - cav_d/2;           // bore length to the cavity
// A teardrop's apex reaches d/2*sqrt(2) above its centre; that, not the bore
// radius, is what has to stay under the top face.
port_apex_z = floor_t + cell_h + cav_h*0.60 + tube_id/2*sqrt(2);
port_dead_mm3 = PI * pow(tube_id/2, 2) * plug_len;  // per port, if capped outside

// ---------------------------------------------------------------- gates

assert(straight_web <= 0.25,
       "straight_web exceeds the 0.25 mm dry-side access limit");
assert(land >= 2.0,
       "seal land under 2 mm: not enough width to close a compression seal");
assert(cart_margin >= m25_clear/2 + 2.0,
       "frame margin too thin for the retainer screws");
assert(cav_d > cell_d + 2*cell_fit + 2.0,
       "cavity narrower than the cell can plus its fit: no floor ledge left");
assert(cart_bolt_r > cav_d/2 + 2.0,
       "cartridge retainer screws land inside the gas cavity and would breach it");
assert(lid_bolt_r > cart_bolt_r + 3.0,
       "lid bolt circle collides with the cartridge screws");
assert(port_apex_z <= body_h - 1.0,
       "upper port teardrop breaks through the chamber's sealing face");
assert(conn_volume_mm3 <= 5000,
       "connected gas volume exceeds the 5.0 cm3 probe target");
assert(flare_inner > window && flare_inner < aperture_far,
       "heater shelf needs the flare to stop between the window and the mouth");
assert(heater_ledge >= 1.5,
       "heater ledge under 1.5 mm: nothing will sit on it");
assert(tsense_depth > 3.0,
       "sensor bore too shallow to reach the seal land");
assert(plen_cav > window + 2.0 && plen_cav < coupon,
       "plenum cavity must clear the window and stay inside the coupon land");
assert(plen_volume_mm3 < 1000,
       "plenum volume over 1 cm3: its sweep lag stops being negligible");
assert((plen_h - plen_tube_id)/2 >= 0.8,
       "plenum port bore breaks out of the sealing face: raise plen_h or shrink the bore");

echo(str("coupon ", coupon, " x ", coupon, " mm; window ", window, " x ", window,
         " mm; gross free area ", window*window, " mm2"));
echo(str("connected gas volume ", conn_volume_mm3/1000, " cm3 = cavity ",
         cav_volume_mm3/1000, " + aperture stack ",
         (conn_volume_mm3 - cav_volume_mm3)/1000,
         " -- NOMINAL: the fit uses the MEASURED volume"));
echo(str("membrane-to-cell face distance ", cav_h, " mm"));
echo(str("chamber body ", body_d, " dia x ", body_h, " mm"));
echo(str("fasteners: 4x M2.5 self-tapping, >= ",
         ceil((cart_stack + 4)/5)*5, " mm long; 4x M3 x ",
         ceil(grip/5)*5 + 5, " mm through the body into bottom nut traps"));
echo(str("plenum swept volume ", plen_volume_mm3/1000, " cm3; at 200 mL/min its ",
         "sweep lag is ~", plen_volume_mm3/(200000/60), " s -- keep it IDENTICAL ",
         "across all four step-1 arms so it cancels"));
echo(str("heater ledge ", heater_ledge, " mm wide; sensor bore ", tsense_bore,
         " mm x ", tsense_depth, " mm deep from the -Y edge"));
echo(str("port dead volume if capped at the barb tip: ", port_dead_mm3/1000,
         " cm3 PER PORT -- use the full-depth plug pin instead"));
echo(str("seat gasket to cut: ", cart_w, " x ", cart_w, " mm outer, ",
         aperture_far, " x ", aperture_far, " mm window"));

// ---------------------------------------------------------------- cartridge

// Asymmetric key: one corner chamfered, so coupon, gasket and retainer can only
// assemble one way. If the oleophobic treatment is one-sided, this is what keeps
// the wet face the wet face.
module key_profile(w, key) {
    difference() {
        square([w, w], center=true);
        translate([w/2, w/2]) rotate(45) square([key*1.42, key*1.42], center=true);
    }
}

module screw_positions() {
    for (sx=[-1,1], sy=[-1,1])
        translate([sx*(cart_w/2 - screw_inset), sy*(cart_w/2 - screw_inset), 0])
            children();
}

module cartridge() {
    difference() {
        linear_extrude(cart_t) key_profile(cart_w, 3.0);

        // Coupon + gasket pocket, opening on the wet (outer, +Z) face.
        translate([0, 0, cart_t - pocket_depth])
            linear_extrude(pocket_depth + eps) key_profile(coupon + 0.3, 2.6);

        // Aperture, then an immediate 45-degree relief into the cavity. The
        // straight section under the coupon is straight_web, nothing more.
        translate([0, 0, heater_shelf_t])
            hull() {
                translate([0, 0, cart_t - pocket_depth - straight_web - heater_shelf_t])
                    linear_extrude(straight_web + pocket_depth + eps)
                        square([window, window], center=true);
                linear_extrude(eps) square([flare_inner, flare_inner], center=true);
            }

        // Heater seat: the mouth steps out over the last heater_shelf_t, giving
        // a flat ledge facing the cavity, entirely inside the seat gasket's
        // window. A wire ring or small chip resistors bond into it.
        translate([0, 0, -eps])
            linear_extrude(heater_shelf_t + eps)
                square([aperture_far, aperture_far], center=true);

        // Sensor bore, in from the -Y edge at mid-thickness, stopping short of
        // the land. Crosses no sealing face.
        translate([0, -cart_w/2 - eps, cart_t/2])
            rotate([-90, 0, 0]) cylinder(d=tsense_bore, h=tsense_depth + eps);

        // Retainer screws pass straight through and self-tap into the lid boss.
        screw_positions()
            translate([0, 0, -eps]) cylinder(d=m25_clear, h=cart_t + 2*eps);

        if (bypass)
            translate([0, coupon/2, cart_t - pocket_depth - bypass_w/2])
                cube([bypass_w, cart_w, bypass_w], center=true);
    }

    // Deep engraving, because at 15 mm the bypass part is otherwise
    // indistinguishable from a good one on the bench.
    if (bypass)
        translate([0, -cart_w/2 + 3.0, cart_t - 0.6])
            linear_extrude(0.61) text("BYPASS", size=3, halign="center", valign="center");
}

module retainer() {
    difference() {
        linear_extrude(retainer_t) key_profile(cart_w, 3.0);
        translate([0, 0, -eps])
            linear_extrude(retainer_t + 2*eps) square([window, window], center=true);
        screw_positions()
            translate([0, 0, -eps]) cylinder(d=m25_clear, h=retainer_t + 2*eps);
    }
}

// ---------------------------------------------------------------- ports

// Teardrop bore: printed horizontally, a plain round hole's roof has nothing to
// bridge to and droops into the gas path. The gas path is the one place a
// collapsed roof is not cosmetic.
module teardrop(d, len) {
    // rotate([0,90,0]) maps profile -X onto world +Z, so the apex must point
    // -X in the profile to end up pointing up in the print.
    rotate([0, 90, 0]) linear_extrude(len)
        union() {
            circle(d=d);
            rotate(135) square([d/2, d/2]);
        }
}

// r0 is the radius at which the part's own wall stands. Everything is drawn
// from there OUTWARD -- draw it from the origin instead and the root cone
// becomes a blob in the middle of the gas cavity, which no arithmetic volume
// check can see.
module barb(r0, len, id=tube_id) {
    od = id + 2*barb_wall;
    rotate([0, 90, 0]) translate([0, 0, r0]) {
        cylinder(d=od, h=len - r0);
        // 45-degree root fillet: the cantilever's support.
        cylinder(d1=od + 2*4.0, d2=od, h=4.0);
        for (i=[1:3])
            translate([0, 0, len - r0 - i*3.0])
                cylinder(d1=od + 1.0, d2=od, h=1.6);
    }
}

// ---------------------------------------------------------------- chamber

module chamber() {
    // One full-diameter puck rather than a body plus a top flange: a flange at
    // the top is a 90-degree overhang all the way round, and the extra material
    // buys thermal mass, which the 40 and 55 C repeats want anyway.
    difference() {
        union() {
            cylinder(d=body_d, h=body_h);
            // Inlet and outlet, diametrically opposed and at opposite ends of
            // the cavity height, so a purge sweeps it instead of short-cutting.
            for (a=[0, 180])
                rotate([0, 0, a])
                    translate([0, 0, floor_t + cell_h + cav_h*(a == 0 ? 0.30 : 0.60)])
                        barb(body_d/2, body_d/2 + barb_len);
        }

        // Gas cavity.
        translate([0, 0, floor_t + cell_h])
            cylinder(d=cav_d, h=cav_h + eps);

        // Cell pocket: the can sits with its gas face flush to the cavity floor,
        // so the cavity is one clean cylinder and the volume arithmetic has no
        // hidden stagnant pockets.
        translate([0, 0, floor_t])
            cylinder(d=cell_d + cell_fit, h=cell_h + 0.2);

        // Three pin holes, straight row, and a recess for the flying leads.
        for (i=[-1, 0, 1])
            translate([i*pin_pitch, -pin_row_offset, -eps])
                cylinder(d=pin_d, h=floor_t + 2*eps);
        translate([0, 0, -eps]) cylinder(d=wire_recess_d, h=wire_recess_h);

        // Port bores.
        for (a=[0, 180])
            rotate([0, 0, a])
                translate([-eps, 0, floor_t + cell_h + cav_h*(a == 0 ? 0.30 : 0.60)])
                    teardrop(tube_id, body_d/2 + barb_len + 2*eps);

        // Potted feedthrough for the heater and sensor leads. Everything
        // electrical lives on the dry side and leaves through one sealed hole,
        // which is exactly what the probe does; the outer cup holds the potting.
        rotate([0, 0, 90])
            translate([-eps, 0, floor_t + cell_h + cav_h/2]) {
                teardrop(feed_bore, body_d/2 + 2*eps);
                translate([body_d/2 - feed_cup_h, 0, 0])
                    rotate([0, 90, 0]) cylinder(d=feed_cup_d, h=feed_cup_h + eps);
            }

        // Lid fasteners: clearance right through the body, hex nut captured in
        // the bottom face, screw entered from above through the lid.
        for (i=[0:lid_screws-1])
            rotate([0, 0, i*360/lid_screws])
                translate([lid_bolt_r, 0, -eps]) {
                    cylinder(d=m3_clear, h=body_h + 2*eps);
                    cylinder(d=m3_nut_af/cos(30), h=m3_nut_t + eps, $fn=6);
                }
    }
}

module lid() {
    difference() {
        union() {
            cylinder(d=body_d, h=lid_t);
            // Cartridge seat, raised so the cartridge and its seat gasket can
            // be swapped without disturbing the lid gasket underneath.
            translate([0, 0, lid_t]) linear_extrude(seat_t) key_profile(cart_w, 3.0);
        }
        // Cartridge aperture through the lid, opening into the cavity.
        translate([0, 0, -eps])
            linear_extrude(lid_t + seat_t + 2*eps)
                square([aperture_far, aperture_far], center=true);
        // Blind pilots for the self-tapping retainer screws. Blind, so the
        // lid's sealing face is never broken by a fastener.
        screw_positions()
            translate([0, 0, lid_t + seat_t + eps])
                mirror([0, 0, 1]) cylinder(d=selftap_pilot, h=lid_t + seat_t - 1.0);
        for (i=[0:lid_screws-1])
            rotate([0, 0, i*360/lid_screws])
                translate([lid_bolt_r, 0, -eps])
                    cylinder(d=m3_clear, h=lid_t + 2*eps);
    }
}

// ---------------------------------------------------------------- plenum

// Applies the O2 step to the WET face. Without it the fixture can only step the
// gas behind the membrane, which is the one path the measurement must not use.
// It also stands in for the probe's guard stand-off gap.
module plenum() {
    difference() {
        union() {
            linear_extrude(plen_t) key_profile(cart_w, 3.0);
            // Ports enter at opposite ends so the sweep crosses the window
            // rather than short-circuiting corner to corner.
            for (a=[0, 180])
                rotate([0, 0, a])
                    translate([0, 0, plen_h/2]) barb(cart_w/2, cart_w/2 + barb_len, plen_tube_id);
        }
        // Swept cavity, open downward onto the retainer.
        translate([0, 0, -eps])
            linear_extrude(plen_h + eps) square([plen_cav, plen_cav], center=true);
        for (a=[0, 180])
            rotate([0, 0, a])
                translate([-eps, 0, plen_h/2])
                    teardrop(plen_tube_id, cart_w/2 + barb_len + 2*eps);
        screw_positions()
            translate([0, 0, -eps]) cylinder(d=m25_clear, h=plen_t + 2*eps);
    }
}

// ---------------------------------------------------------------- consumables

// Cutting template. A coupon cut freehand has a ragged land and a crushed edge,
// exactly where the compression seal has to close.
module die() {
    plate = coupon + 16;
    difference() {
        linear_extrude(4.0) square([plate, plate], center=true);
        translate([0, 0, -eps]) linear_extrude(4.0 + 2*eps) key_profile(coupon, 2.6);
        // Scribe line marking the window, so land width is visible before cutting.
        translate([0, 0, 4.0 - 0.4]) difference() {
            linear_extrude(0.41) square([window + 1.0, window + 1.0], center=true);
            linear_extrude(0.41) square([window, window], center=true);
        }
    }
}

// Blanking pin, NOT a stopper at the barb tip. Each port bore is 25.9 mm long;
// capping it at the outside would leave ~0.33 cm3 of dead gas per port hanging
// off a 5 cm3 budget. The pin fills the bore to the cavity wall instead.
// Wrap it in PTFE tape or grease it -- a printed pin is a fit, not a seal.
module plug() {
    cylinder(d=tube_id + 6, h=2.5);                 // handle flange
    translate([0, 0, 2.5]) cylinder(d=tube_id - plug_fit, h=plug_len);
}

// ---------------------------------------------------------------- volume audit

// The connected gas volume rendered as a SOLID, so it can be measured off the
// mesh instead of trusted from a cylinder formula. The arithmetic assert above
// could not see the barb root cone that was sitting inside the cavity.
module gas_volume() {
    translate([0, 0, floor_t + cell_h]) cylinder(d=cav_d, h=cav_h);
    translate([0, 0, body_h])
        linear_extrude(lid_t + seat_t) square([aperture_far, aperture_far], center=true);
    translate([0, 0, body_h + lid_t + seat_t]) {
        linear_extrude(heater_shelf_t) square([aperture_far, aperture_far], center=true);
        translate([0, 0, heater_shelf_t])
            hull() {
                linear_extrude(eps) square([flare_inner, flare_inner], center=true);
                translate([0, 0, cart_t - pocket_depth - straight_web - heater_shelf_t])
                    linear_extrude(straight_web + eps)
                        square([window, window], center=true);
            }
    }
}

// ---------------------------------------------------------------- assembly

module assembly() {
    e = exploded ? 20 : 0;
    seat_top = body_h + lid_t + seat_t;

    color("SlateGray") chamber();
    color("LightSteelBlue") translate([0, 0, body_h + e]) lid();
    color("Tan") translate([0, 0, seat_top + 1.6*e]) cartridge();
    // Coupon and gasket are visual only; a printed disc is not a membrane.
    color("White") translate([0, 0, seat_top + cart_t - pocket_depth + 2.0*e])
        linear_extrude(membrane_t) key_profile(coupon, 2.6);
    color("DimGray") translate([0, 0, seat_top + cart_t - gasket_gap + 2.2*e])
        linear_extrude(gasket_t) difference() {
            key_profile(coupon, 2.6);
            square([window, window], center=true);
        }
    color("LightSteelBlue") translate([0, 0, seat_top + cart_t + gasket_t + 2.6*e]) retainer();
    color("Tan") translate([0, 0, seat_top + cart_t + gasket_t + retainer_t + 3.2*e]) plenum();
}

if (part == "assembly") assembly();
else if (part == "cartridge") cartridge();
else if (part == "retainer") retainer();
else if (part == "chamber") chamber();
else if (part == "lid") lid();
else if (part == "die") die();
else if (part == "plug") plug();
else if (part == "plenum") plenum();
else if (part == "cavity") gas_volume();
else assert(false, "unknown part");
