/*
 * o2_probe_gas_shell.scad -- the wall between the sensor chamber and the
 * electronics chamber, for a probe that is COATED rather than POTTED.
 *
 * WHY THIS PART EXISTS
 *
 * The cell rides the board (standing mount, PLACEMENT.md datum (10, 93.5)) and
 * the board comes out the CABLE end. o2_probe_head_end.scad echoes that itself:
 *
 *     CELL SERVICE: standing mount -- the cell rides the board and comes out
 *     the CABLE end. No extraction through the head [...]
 *
 * So the cell is already field-replaceable, by exactly one route: pop the cap,
 * pull the board. POTTING.md pours 50 cm3 of PU down that route. Fab, 2026-09-06:
 * coat the board instead and leave the tube full of air -- which restores the
 * service path and costs the one thing the pot actually bought, a place where
 * water cannot condense.
 *
 * But the air is not free, and the reason is RESPONSE TIME, not moisture.
 * o2_probe_body_tube.scad measures it:
 *
 *     GAS VOLUME, unpotted: head cavity 4.3671 cm3 + tube 57.6522
 *     + tail 12.7835 = 74.8029 cm3, 14.9606x the 5.0 cm3 budget.
 *
 * The pot was holding that number down by filling the tube. Take it out and
 * something else has to. This part is that something else.
 *
 * WHAT IT IS NOT
 *
 * It is NOT the `dam` in o2_probe_body_tube.scad. That part is honest about
 * itself -- "a loose split disc, not a seal: 204 mm2 of a 581 mm2 bore stays
 * open, so at equilibrium the tail is still connected". A restrictor splits one
 * time constant into two. It removes no volume.
 *
 * It is also NOT a bulkhead at the y=82 potting datum. A plain wall there leaves
 * the whole tube bore from 82 to the head socket inside the gas chamber, and the
 * can itself spans board y 86.19..100.81, so a wall behind it cannot go further
 * forward than ~85.5 anyway. Bore area is 581 mm2: every millimetre of open bore
 * left on the gas side costs 0.58 cm3, and the budget is 5.0 TOTAL.
 *
 * So a wall is necessary and nowhere near sufficient. What closes the number is
 * FILLING -- occupying the bore around the can and leaving a defined gas gap. The
 * separator and the filler are the same part, and that is this one.
 *
 * WHAT IS STILL OPEN, AND IT IS THE WHOLE DESIGN
 *
 * The shell has to reach board y~93 through the cable end, so it must pass the
 * Ø25.7 collar (o2_probe_body_tube.scad, cable_bore_d). That caps its OD at 25.2,
 * inside a 27.2 bore -- an annulus 1.0 mm deep that is a wide-open bypass duct
 * around the whole part. Closing it is the open question and `shell_seal` is
 * where the three answers live. Nothing here decides it; the model MEASURES what
 * each one costs. See CELL-SERVICE-AND-THE-WALL.md.
 *
 * FRAME. z = board y minus shell_y0. x = across the board (board centreline at
 * x=0; KiCad's x=10 is here x=0). y = board normal, +y toward the component
 * front, which is the side the cell stands on.
 */

$fn = 96;
e = 0.01;

part = "shell";

// ------------------------------------------------- mirrors
//
// Every number in this block belongs to another file. They are restated because
// the three models cannot include one another (see tools/interface_check.py's
// docstring for why), and restated numbers drift -- so interface_check.py
// compares these against their sources. Do not hand-edit one without running it.

board_w   = 20.0;           // o2_probe_body_tube.scad, board_w
board_t   = 1.6;            // o2_probe_body_tube.scad, board_t
board_len = 107.0;          // o2_probe_body_tube.scad, board_len
tube_id   = 27.2;           // o2_probe_body_tube.scad, tube_id
collar_bore = 25.7;         // o2_probe_body_tube.scad, cable_bore_d

// The guide rails. The shell has to pass station A on its way in and cannot,
// unless it carries channels the rails run through -- the rail reaches from
// x=9.0 (board_w/2 - guide_engage) out to 14.8, over 7.0 mm of board normal, so
// a Ø25.2 disc fouls it by 3.6 mm on each side. This is not a detail; it is why
// the shell is not a plain disc.
guide_engage = 1.0;         // o2_probe_body_tube.scad, guide_engage
guide_body   = 7.0;         // o2_probe_body_tube.scad, guide_body

// The cell, standing. cell_seated_h is measured from the board SURFACE, which is
// how o2_probe_head_end.scad uses it (cell_stand_r adds board_t/2 to it).
cell_d = 14.62;             // o2_probe_head_end.scad, cell_d (MEASURED)
cell_h = 8.3;               // o2_probe_head_end.scad, cell_h (DS-0637 Iss. 2)
cell_seated_h = 8.8;        // Makefile HEAD_END_PROV -- PROVISIONAL, see below
cell_y = 93.5;              // PLACEMENT.md controlled datum, board y of the axis

// ------------------------------------------------- span
//
// The cable-side face. It cannot go forward of 85.5 -- the can's own back edge
// is at cell_y - cell_d/2 = 86.19 -- and it should not go back of 81.3, which is
// where o2_probe_body_tube.scad's edge scan says both board edges stop being
// clear. 82.0 is the potting datum's own line, which is not a coincidence: it is
// the one plane on this board that the layout has already been told to keep free.
shell_y0 = 82.0;
// The forward face: where the tube ends and the head's bore takes over. This is
// the MONOLITHIC number (tube_len 124 less tail_len 22). Bonded, the tube runs to
// 105 and the shell could be longer; it is not, because the same part has to fit
// both joints.
shell_y1 = 102.0;
shell_len = shell_y1 - shell_y0;

// OD. Set by the collar, not by the bore it runs in.
shell_pass_clr = 0.5;       // diametral, shell OD under the collar bore
shell_od = collar_bore - shell_pass_clr;

// Fits. The shell is bonded to the board (it leaves with the board and is part
// of that assembly), so these are bond gaps, not sliding fits.
board_slot_w = board_w + 0.30;
board_slot_t = board_t + 0.20;
rail_clr     = 0.35;        // on the rail channel, all round
cell_gap_r   = 0.60;        // gas gap around the can's rim
cell_gap_t   = 0.80;        // gas gap over the can's sensing face
wall_min     = 1.20;        // thinnest wall this part is allowed anywhere

// The seal to the tube bore. THIS IS THE OPEN DECISION, not a setting with a
// right answer, and each branch is a different probe:
//
//   "none"   the annulus stays open. The shell displaces volume and restricts
//            flow; it does not divide the probe into two chambers. Honest, and
//            what a first article should be built as, because it is the only
//            branch that needs nothing decided.
//   "lip"    a printed conical skirt, thin enough to deflect through the Ø25.7
//            collar and spring back in the Ø27.2 bore. Costs nothing to try and
//            needs a coupon before it is believed -- an ASA lip at pile
//            temperature for a season is not a spring.
//   "oring"  a real radial seal at Ø27.2. Genuinely two chambers, and it CANNOT
//            PASS THE COLLAR: a 2.0 cord on the ~Ø24 root it needs relaxes to
//            ~Ø28, and driving that through Ø25.7 is 57 % squeeze at the lip.
//            This branch requires the cable end to go back to a full Ø27.2 bore,
//            i.e. giving up the 22 x 2 cap ring. The assert below says so rather
//            than letting the geometry render as though it were free.
shell_seal = "none";
assert(shell_seal == "none" || shell_seal == "lip" || shell_seal == "oring",
       str("unknown shell_seal '", shell_seal, "'"));

// Does station B's rail run the length of the shell? It does not today --
// o2_probe_body_tube.scad has station_b = [82, 90] for the monolithic joint,
// sized when head_socket_len was 14 and the tube stopped at board y=91. It is 3
// now and the tube runs to 102, so that limit is stale and the rail could cover
// the whole shell. That matters here for one reason: a rail inside the channel
// PLUGS it, and the channels are the second-largest gas term in the part. This
// flag is what lets the model weigh the difference instead of arguing it.
rails_in_span = false;

lip_t     = 0.45;           // printed skirt wall
lip_over  = 0.10;           // how far past the bore it stands, diametral
lip_len   = 2.5;

// The `oring` branch needs the collar gone. Nothing in this file can remove it,
// so it refuses to draw a seal that cannot be installed -- the failure mode this
// guards against is a model that renders a perfectly good ring into a bore no
// ring can reach, and gates that all pass because none of them simulate assembly.
cable_end_bore_is_full = false;   // set true ONLY when the collar is deleted
assert(shell_seal != "oring" || cable_end_bore_is_full,
       str("shell_seal=oring seals at Ø", tube_id, ", which needs a groove root near Ø24 ",
           "and a ring that relaxes to about Ø28. It has to be pushed through the Ø",
           collar_bore, " collar to get there -- ", 100*((28 - collar_bore)/2)/2,
           " % squeeze at the lip, which rolls or shaves the ring. Either delete ",
           "the collar (and with it the 22 x 2 cap seal) and set ",
           "cable_end_bore_is_full=true, or use shell_seal=\"lip\"/\"none\"."));

// ------------------------------------------------- derived and gated

cell_z    = cell_y - shell_y0;              // the can's axis, in shell z
pocket_d  = cell_d + 2*cell_gap_r;
pocket_y0 = board_t/2;                      // board front surface
pocket_y1 = board_t/2 + cell_seated_h + cell_gap_t;
rail_x0   = board_w/2 - guide_engage;       // 9.0, the rail's inner face

assert(cell_y - cell_d/2 > shell_y0 + wall_min,
       str("the can's back edge is at board y ", cell_y - cell_d/2,
           " and the shell's back face at ", shell_y0,
           ": less than ", wall_min, " mm of wall between them"));
assert(cell_y + cell_d/2 < shell_y1,
       str("the can's front edge is at board y ", cell_y + cell_d/2,
           " and the shell ends at ", shell_y1, ": the can is not inside the shell"));
assert(shell_y0 >= 81.3 && shell_y1 <= 103.6,
       str("the shell spans board y ", shell_y0, "..", shell_y1,
           ", outside the 81.3..103.6 band where o2_probe_body_tube.scad's edge ",
           "scan says BOTH board edges are clear. It would sit on a pad."));
assert(shell_od <= collar_bore - shell_pass_clr + 1e-9,
       str("shell OD ", shell_od, " does not pass the Ø", collar_bore, " collar"));
// The wall over the can's sensing face. This is the thinnest place in the part
// and it is the one that has to hold the gas gap open, so it is checked rather
// than eyeballed off the render.
cap_wall = shell_od/2 - pocket_y1;
assert(cap_wall >= wall_min,
       str("only ", cap_wall, " mm of shell over the can's face (pocket top at y=",
           pocket_y1, ", OD ", shell_od, "): below ", wall_min,
           " it prints as two lines and collapses into the gas gap"));
// The rail channel eats the part from x=9.0 outward. What is left holding the
// two halves together across the board is the material between the board slot
// and the channel, and at guide_engage=1.0 that is nothing at all -- the channel
// starts exactly where the slot's engagement ends. Say so.
web = rail_x0 - rail_clr - board_slot_w/2;
assert(web <= 0 || web >= wall_min,
       str("the web between the board slot and the rail channel is ", web,
           " mm -- either make it >= ", wall_min, " or accept 0 and bond across it"));

// ------------------------------------------------- volume, MEASURED not modelled
//
// These are the analytic numbers, and they are here to be CONTRADICTED. The gate
// is `part="gas"` weighed on the mesh, because every volume model in this project
// that was not weighed has been wrong at least once. cav_net in the head file was
// out by 3.1 cm3; head_cavity in the body file was quoting the bonded head while
// the file defaulted to monolithic.
bore_area   = PI*pow(tube_id/2, 2);
annulus_vol = (bore_area - PI*pow(shell_od/2, 2)) * shell_len;
rail_vol    = rails_in_span ? 0
            : 2 * (shell_od/2 - rail_x0 + rail_clr) * (guide_body + 2*rail_clr) * shell_len;
pocket_vol  = PI*pow(pocket_d/2, 2)*(pocket_y1 - pocket_y0) - PI*pow(cell_d/2, 2)*cell_h;

echo(str("GAS SHELL: board y ", shell_y0, "..", shell_y1, " (", shell_len,
         " mm), OD ", shell_od, " in a ", tube_id, " bore, seal \"", shell_seal, "\"."));
echo(str("GAS SHELL model (weigh part=\"gas\" instead): annulus ", annulus_vol/1000,
         " + rail channels ", rail_vol/1000, " + cell pocket ", pocket_vol/1000,
         " = ", (annulus_vol + rail_vol + pocket_vol)/1000, " cm3."));
// What is actually left for it. The head spends most of the budget by itself and
// the monolithic head spends nearly all of it -- which is a statement about the
// JOINT, not about this part, and it is the single most useful number here.
echo(str("BUDGET: the 5.0 cm3 gate less the head's own cavity leaves 2.0715 cm3 ",
         "bonded and 0.6329 cm3 monolithic (meshes, tools/interface_check.py). ",
         "The annulus alone is ", annulus_vol/1000,
         " cm3. THE MONOBODY CANNOT MEET THE BUDGET WHATEVER THIS PART DOES."));
echo(str("UNMEASURED: cell_seated_h ", cell_seated_h,
         " is the Makefile's provisional value, and it sets the gas gap over the ",
         "sensing face directly. Seat a real cell in a real socket before printing."));

// ------------------------------------------------- geometry

// The rail channels, as a cutter. Full length, both edges, with the board slot's
// own clearance folded in -- the rail is a U straddling the board and the shell
// has to clear both prongs.
module rail_channels() {
    for (sx = [1, -1])
        scale([sx, 1, 1])
            translate([rail_x0 - rail_clr, -(guide_body/2 + rail_clr), -e])
                cube([shell_od, guide_body + 2*rail_clr, shell_len + 2*e]);
}

// The gas pocket around the can, opening FORWARD into the head's bore. It has to
// open somewhere or it is a sealed bubble with the cell inside it, and forward is
// the only direction with a head on the other end. The forward cut runs to the
// face rather than stopping short: at pocket_d 15.82 the can's front edge is
// 0.59 mm from the face anyway, so a "duct" here would be a fiction.
module gas_pocket() {
    translate([0, pocket_y0, cell_z]) rotate([-90, 0, 0])
        cylinder(d=pocket_d, h=pocket_y1 - pocket_y0);
    // the forward opening
    translate([-pocket_d/2, pocket_y0, cell_z])
        cube([pocket_d, pocket_y1 - pocket_y0, shell_len - cell_z + e]);
}

// The guide rail's own solid, copied from o2_probe_body_tube.scad's guide(): a
// block from the board's engaged edge out to guide_r_max, guide_body wide across
// the board plane, with the board slot cut through it. Drawn ONLY to be
// subtracted from the gas -- this file does not own the rail and must not export
// one. Clipped to the tube bore, which is where the shell's channel ends anyway.
module rails() {
    for (sx = [1, -1])
        scale([sx, 1, 1])
            difference() {
                intersection() {
                    translate([rail_x0, -guide_body/2, -e])
                        cube([tube_id, guide_body, shell_len + 2*e]);
                    cylinder(d=tube_id, h=shell_len + 2*e, center=false);
                }
                translate([-tube_id, -board_slot_t/2, -2*e])
                    cube([2*tube_id, board_slot_t, shell_len + 4*e]);
            }
}

module lip_skirt(z, dir) {
    // A cone standing proud of the bore, thin enough to fold through the collar.
    translate([0, 0, z])
        scale([1, 1, dir])
            difference() {
                cylinder(d1=shell_od, d2=tube_id + lip_over, h=lip_len);
                translate([0, 0, -e])
                    cylinder(d1=shell_od - 2*lip_t, d2=tube_id + lip_over - 2*lip_t,
                             h=lip_len + 2*e);
            }
}

module shell_solid() {
    difference() {
        union() {
            cylinder(d=shell_od, h=shell_len);
            if (shell_seal == "lip") {
                lip_skirt(1.0, 1);
                lip_skirt(shell_len - 1.0, -1);
            }
        }
        // the board, straight through
        translate([-board_slot_w/2, -board_slot_t/2, -e])
            cube([board_slot_w, board_slot_t, shell_len + 2*e]);
        gas_pocket();
        rail_channels();
        if (shell_seal == "oring") {
            // Root sized for 20 % squeeze on a 2.0 cord in the Ø27.2 bore. Only
            // reachable with the collar gone -- the assert above is the gate.
            groove_root = tube_id - 2*2.0*(1 - 0.20);
            translate([0, 0, shell_len/2 - 1.4])
                difference() {
                    cylinder(d=shell_od + 2*e, h=2.8);
                    cylinder(d=groove_root, h=2.8);
                }
        }
    }
}

// Two halves, split on the board plane, exactly as the dam is. Each half is
// bonded to the board; the board plus its shell is the serviceable unit.
module shell_half(sign) {
    intersection() {
        shell_solid();
        translate([-tube_id, sign > 0 ? board_slot_t/2 : -tube_id, -e])
            cube([2*tube_id, tube_id, shell_len + 2*e]);
    }
}

module shell() {
    translate([0,  2, 0]) shell_half( 1);
    translate([0, -2, 0]) shell_half(-1);
}

// The board and the can, for the preview and for the gas Boolean. Representative,
// never exported -- the board belongs to KiCad.
module board_and_cell(stub = false) {
    // The full board is what `gas()` has to cut with -- it runs the length of the
    // tube and the void has to be cut by all of it. `stub` is for the preview
    // only: 107 mm of board in a picture of a 20 mm part shows the part as a
    // speck. It changes nothing that is measured.
    z0 = stub ? -8 : -shell_y0;
    z1 = stub ? shell_len + 8 : board_len - shell_y0;
    translate([-board_w/2, -board_t/2, z0])
        cube([board_w, board_t, z1 - z0]);
    translate([0, board_t/2 + cell_seated_h - cell_h, cell_z]) rotate([-90, 0, 0])
        cylinder(d=cell_d, h=cell_h);
}

// THE GATE. The connected gas inside the shell's span: everything in the tube
// bore that is neither shell, nor board, nor can. It counts the annulus and the
// rail channels automatically, which is the point -- those are the two terms a
// hand-written model forgets, and they are the two largest.
module gas() {
    difference() {
        translate([0, 0, 0]) cylinder(d=tube_id, h=shell_len);
        shell_solid();
        board_and_cell();
        if (rails_in_span) rails();
    }
}

module assembly() {
    color("SlateGray", 0.9) shell();
    color("ForestGreen") board_and_cell(stub = true);
    %translate([0, 0, -8]) cylinder(d=tube_id, h=shell_len + 16);
}

// The half that carries the cell pocket, opened up so the gas gap is visible.
// The pocket is the whole point of the part and it is invisible from outside.
module section() {
    color("SlateGray") difference() {
        shell_half(1);
        translate([-tube_id, -e, -e]) cube([tube_id, tube_id, shell_len + 2*e]);
    }
    color("ForestGreen") board_and_cell(stub = true);
}

if (part == "shell") shell();
else if (part == "half-front") shell_half(1);
else if (part == "half-back") shell_half(-1);
else if (part == "gas") gas();
else if (part == "assembly") assembly();
else if (part == "section") section();
else assert(false, str("unknown part '", part, "'"));
