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
 *      file, i.e. the ~1.0 mm build PLACEMENT.md specifies. The enclosure is cut
 *      for board_t = 1.6, which Fab confirmed on 2026-09-05 is the correct Rev A
 *      thickness. So this picture shows the board as the FAB DATA describes it,
 *      inside a body sized for the board that Rev A actually IS. The gap is real,
 *      and it is the board file that is wrong; see PRINTING-BODY-TUBE.md.
 *
 * Preview only -- never exported, and never rendered with --render: the board
 * mesh is 215k facets and CGAL would take the rest of the day. OpenCSG does the
 * section on the GPU in a second.
 *
 *   make board-in-body
 */

$fn = 96;

// xray     see-through body, whole board -- nice to spin, alpha caveats below
// section  half the body cut away -- PRE-CUT, see below
// whole    everything solid
// cutbody  the sectioned body ALONE, for export; not a viewing mode
part = "section";     // xray, section, whole, cutbody

// WHY THE SECTION IS PRE-CUT AND NOT A LIVE difference().
//
// It used to be `difference(assembly(), a 120 mm cube)`, and that is fine until
// you reach for View > Thrown Together (F12) to work out why a surface has
// vanished. Thrown Together does NOT evaluate CSG -- it draws every object
// including the ones being subtracted -- so the cutting block appears as a
// giant slab over the model and the mode that exists to diagnose the problem
// becomes unusable.
//
// So the cut is baked once, by CGAL, into exports/body-monobody-section.stl
// (`make body-section`), and this file imports the result. The preview then
// contains no CSG at all: F12 is usable, F5 is fast, and nothing is hiding
// behind a cutter. The cost is that the section STL has to be rebuilt when the
// body changes, which the Makefile handles.
show_cap = true;

// CONVEXITY, first, because it is the one that looks like a graphics driver bug.
// OpenSCAD's PREVIEW renders CSG by depth-peeling a fixed number of layers, and
// that number is `convexity` -- the most surfaces any single ray crosses. It
// defaults to 1 on import(), which is right for a solid blob and wrong for
// everything here: a ray through this tube crosses four walls before it reaches
// the board, more once a difference() is cutting it. Below the true value,
// surfaces DISAPPEAR AT SOME VIEW ANGLES AND NOT OTHERS, which reads as a
// rendering bug rather than a missing parameter. Every import() below carries
// convexity=10. It costs nothing but preview time and only affects preview --
// F6/CGAL is exact regardless.
//
// TRANSPARENCY, second, because it has two traps of its own and both bite
// silently.
//
//   1. Alpha works in PREVIEW ONLY (F5 / OpenCSG). Render (F6 / CGAL) throws it
//      away and hands back opaque geometry -- the same reason the exploded
//      drawing must not use --render, which discards colour altogether.
//   2. ORDER MATTERS. OpenSCAD does not depth-sort transparent surfaces, so a
//      transparent object drawn BEFORE an opaque one hides it. Anything you
//      want to see through must come LAST in the source. That is why xray()
//      below draws the board first and the body afterwards, which reads
//      backwards and is correct.
//
// The other route needs no alpha at all: prefix any object with `%` and it
// becomes a background object -- transparent grey, and excluded from the
// geometry, so it cannot affect a difference() or an export. `#` is the same
// idea in debug pink, but it STAYS in the geometry. `%` is the honest choice
// for a thing you only want to look through.
body_alpha = 0.22;
// "alpha"      color(c, a) -- honours the colour, but see the ordering trap.
// "background" the % modifier -- OpenCSG draws background objects in their own
//              pass, so they cannot hide anything whatever the view angle. The
//              cost is the colour: they always come out grey.
xray_mode = "alpha";

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
body_tube_len = 124.0;      // monolithic (was 113 while socket_len was 14)
board_len     = 107.0;
tube_id       = 27.2;
cable_bore_d  = 27.3;
cap_engage    = 18.0;       // o2_probe_body_tube.scad, cap_engage

// Monobody frame: the cable end face is at z = -body_tube_len, the head's own
// z=0 is the joint. So board local y maps to z = y + tail_len - body_tube_len.
board_z0 = tail_len - body_tube_len;

// EVERY part KiCad could not place, redrawn. The export names them and then
// omits them, which is the worst possible failure for a clearance drawing: the
// picture looks complete. Each row is [name, x0, x1, y0, y1, height, back?]
// in BOARD-LOCAL coordinates, taken from the footprint's pad extents in
// o2-probe.kicad_pcb, with the height from the source named beside it.
//
// HEIGHTS ARE PACKAGE NOMINALS, NOT MEASURED, except RV1 which Fab measured.
// They are good enough to answer "does it foul the bore" with millimetres to
// spare; they are not good enough to answer a question about tenths.
missing = [
    // RV1: the tallest thing on the board, and the whole reason to look.
    // Bourns 3224W on B.Cu. Library has 3314G and 3314J and nothing else.
    ["RV1  trimmer",   0.25,  4.75, 71.10, 74.90, 5.0, true ],
    // L_6.3x6.3_H3 -- the footprint name carries the height.
    ["L1   inductor",  7.00, 14.00, 26.30, 28.70, 3.0, false],
    // WQFN-16 3x3, package nominal.
    ["U8   WQFN-16",  13.62, 17.38, 75.12, 78.88, 0.8, false],
    // SHT4x DFN-4 1.5x1.5, package nominal.
    ["U12  SHT45",     2.55,  4.45,100.95,102.05, 0.5, false],
    // J101-104 are solder-wire lands, so what projects is the CABLE, not a
    // component: 0.25 sqmm wire, 1.7 mm insulated OD, lying along the land.
    ["J101 wire",      1.90,  4.10,  3.58, 15.80, 1.7, false],
    ["J102 wire",      6.60,  8.80,  3.58, 15.80, 1.7, false],
    ["J103 wire",     11.20, 13.40,  3.58, 15.80, 1.7, false],
    ["J104 wire",     15.90, 18.10,  3.58, 15.80, 1.7, false],
];
// NOT drawn, deliberately, and neither is a part in service:
//   J3  Tag-Connect TC2030-IDC-NL -- "NL" is no-legs, so the pogo adapter is
//       present only while programming, never in the tube.
//   J5  Ring_Fork_Tip_DRAFT -- solder lands for the heater ring that
//       HEATED-SPREADER.md section 0 records as orphaned. No part fitted.

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
        import(board_stl, convexity=10);
}

module missing_parts() {
    for (m = missing) {
        x0 = m[1]; x1 = m[2]; y0 = m[3]; y1 = m[4]; h = m[5]; back = m[6];
        translate([x0 - 10,
                   back ? -kicad_t/2 - h : kicad_t/2,
                   board_z0 + y0])
            cube([x1 - x0, h, y1 - y0]);
    }
}

module assembly() {
    color("Sienna") import("exports/body-monobody.stl", convexity=10);
    if (show_cap)
        color("DarkOrange")
            translate([0, 0, -body_tube_len + cap_engage])
                mirror([0, 0, 1]) import("exports/body-cap.stl", convexity=10);
    color("DarkGreen") board();
    // Crimson so they read as "added by hand", not as exported geometry.
    color("Crimson") missing_parts();
}

// See-through body, whole board. Opaque things FIRST -- see the note at the top.
module xray() {
    color("DarkGreen") board();
    color("Crimson") missing_parts();
    if (xray_mode == "background") {
        %import("exports/body-monobody.stl", convexity=10);
        if (show_cap)
            %translate([0, 0, -body_tube_len + cap_engage])
                mirror([0, 0, 1]) import("exports/body-cap.stl", convexity=10);
    } else {
        color("Sienna", body_alpha) import("exports/body-monobody.stl", convexity=10);
        if (show_cap)
            color("DarkOrange", body_alpha)
                translate([0, 0, -body_tube_len + cap_engage])
                    mirror([0, 0, 1]) import("exports/body-cap.stl", convexity=10);
    }
}

// The cutter. It removes the -Y half, which is the side OpenSCAD's default view
// looks from, so the model opens toward you the moment you load it. That is not
// a detail: only the BODY is pre-cut now, so with the cut facing away the
// remaining half simply hides the board and the section looks like the whole
// part. RV1 lives on the board's -Y face (B.Cu) and is therefore the first
// thing in view, which is the point of the drawing.
module half_space() { translate([-60, -60, -200]) cube([120, 60, 400]); }

// Emitted for export only -- `make body-section` renders this through CGAL.
module cutbody() {
    difference() {
        import("exports/body-monobody.stl", convexity=10);
        half_space();
    }
}

module section() {
    color("Sienna") import("exports/body-monobody-section.stl", convexity=10);
    if (show_cap)
        color("DarkOrange")
            translate([0, 0, -body_tube_len + cap_engage])
                mirror([0, 0, 1]) import("exports/body-cap.stl", convexity=10);
    color("DarkGreen") board();
    color("Crimson") missing_parts();
}

if (part == "xray") xray();
else if (part == "whole") assembly();
else if (part == "cutbody") cutbody();
else section();
