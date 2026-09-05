/*
 * The REAL board, from KiCad, inside the printed body.
 *
 * Not a representative rectangle: this imports the mesh KiCad 10 exports from
 * o2-probe.kicad_pcb, with its populated 3D models, and drops it into the
 * monolithic body at the position the enclosure model actually assumes. It
 * exists to answer one question by looking rather than by arithmetic -- does
 * everything on that board clear a Ø27.2 bore -- and to catch the class of
 * error a swept-envelope number cannot: one tall part in the wrong place.
 *
 * TWO THINGS THE MESH DOES NOT SHOW, and both matter here:
 *
 *   1. RV1 IS NOT IN IT. KiCad ships no 3D model for
 *      Potentiometer_SMD:Potentiometer_Bourns_3224W_Vertical -- the library has
 *      3314G and 3314J and nothing else -- so the export silently omits the
 *      TALLEST part on the board, which is the one the clearance question is
 *      about. It is drawn here by hand from its footprint (pads x 0.25..4.75,
 *      y 71.10..74.90 in board coordinates, B.Cu) at the 5 mm Fab measured.
 *      Also missing, and NOT redrawn because none of them is near the envelope:
 *      L1 (SRN6028C, 3.0 mm), U8, U12, and the four J101-104 solder-wire pads.
 *   2. THE MESH IS A 0.91 mm BOARD. That is the dielectric stack in the board
 *      file, i.e. the ~1.0 mm build PLACEMENT.md specifies. The enclosure model
 *      is cut for board_t = 1.6 on Fab's 2026-09-05 instruction. So this picture
 *      shows the board that EXISTS in the fab data, inside a body sized for the
 *      board that was ASKED FOR. The gap is real and it is the board file that
 *      would have to move; see PRINTING-BODY-TUBE.md.
 *
 * Preview only -- never exported, and never rendered with --render: the board
 * mesh is 215k facets and CGAL would take the rest of the day. OpenCSG does the
 * section on the GPU in a second.
 *
 *   make board-in-body
 */

$fn = 96;

part = "section";     // section, whole
show_cap = true;

// ------------------------------------------------- the KiCad export

// kicad-cli pcb export stl --no-dnp --subst-models --include-tracks --include-pads
// Its frame, measured off the export rather than assumed:
//   x   = page x, 100.00 .. 120.00   -> board local x = x - 100
//   y   = MINUS page y, -157 .. -50  -> board local y = -y - 50   (0 = cable end)
//   z   = 0 at the board's bottom face, 0.910 at its top
board_stl   = "exports/o2-probe-board-bin.stl";
kicad_x0    = 100.0;
kicad_y0    = -50.0;
kicad_t     = 0.910;        // the mesh's own board thickness, NOT board_t

// ------------------------------------------------- where the body puts it

// These must track o2_probe_body_tube.scad and o2_probe_head_end.scad.
tail_len      = 22.0;       // board y=0 sits this far up the tube
body_tube_len = 113.0;      // monolithic
board_len     = 107.0;
tube_id       = 27.2;
cable_bore_d  = 27.3;

// Monobody frame: the cable end face is at z = -body_tube_len, the head's own
// z=0 is the joint. So board local y maps to z = y + tail_len - body_tube_len.
board_z0 = tail_len - body_tube_len;

// RV1, redrawn because KiCad has no model for it.
rv1_x0 = 0.25;  rv1_x1 = 4.75;      // board local x, from the pad extents
rv1_y0 = 71.10; rv1_y1 = 74.90;     // board local y
rv1_h  = 5.0;                       // Fab, 2026-09-04, measured

// ONE matrix, and it is worth writing out rather than chaining rotates -- the
// first attempt chained translate/rotate/multmatrix and put the board flat on
// the floor outside the tube, which at least was obvious.
//
//   bodyX = kx - 110                 board local x 0..20, centred on the bore
//   bodyY = kz - kicad_t/2           the export's z is the board's thickness
//   bodyZ = -ky - 50 + board_z0      the export's y is NEGATED page y
//
// Determinant of the 3x3 is +1, so this is a rotation and not a mirror: a
// mirrored board would look almost right and be wrong about which face RV1 is
// on, which is the entire question this drawing exists to answer.
module board() {
    multmatrix([[1,  0, 0, -110],
                [0,  0, 1, -kicad_t/2],
                [0, -1, 0, -50 + board_z0],
                [0,  0, 0, 1]])
        import(board_stl);
}

module rv1() {
    // B.Cu, so it hangs BELOW the board plane
    translate([rv1_x0 - 10, -kicad_t/2 - rv1_h, board_z0 + rv1_y0])
        cube([rv1_x1 - rv1_x0, rv1_h, rv1_y1 - rv1_y0]);
}

module assembly() {
    color("Sienna") import("exports/body-monobody.stl");
    if (show_cap)
        color("DarkOrange")
            translate([0, 0, -body_tube_len + 12.0])
                mirror([0, 0, 1]) import("exports/body-cap.stl");
    color("DarkGreen") board();
    color("Crimson") rv1();
}

if (part == "whole") assembly();
else difference() {
    assembly();
    // Half section, taken on the side the trimmer is on so it is the thing you
    // see. The board is at x -10..+10 and RV1 at x -9.75..-5.25.
    translate([-60, 0, -200]) cube([120, 60, 400]);
}
