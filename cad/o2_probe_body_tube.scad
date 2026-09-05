/*
 * O2 probe — PRINTED ASA BODY TUBE, prototype 1 (buried)
 * Units: millimetres. Z runs from the CABLE end toward the head.
 *
 * MEMBRANE.md, "Enclosure material: printed ASA" (2026-09-02) decided a BOUGHT
 * tube for the potted body and a printed head, and in the same breath allowed
 * this: "A fully printed body is permitted for prototypes." This is that part.
 * It exists so the Rev-A board -- the revision already at the fab, unmodified,
 * with no heater RING and NOT POTTED -- can be buried and can start returning
 * numbers, months before the bought-tube/potting route is qualified.
 *
 * No heater ring is NOT no heater. The board carries RH1/RH2 (CRCW2512280RFKEG,
 * 280 R 1 W, two on the back at (5, 96.5)) = 140 ohm, ~1.03 W at 12 V, the whole
 * budget PLAN.md sizes. What is missing is J5's ring, which was to carry that
 * heat to the membrane; HEATED-SPREADER.md section 0 records it as orphaned by
 * the end-window head. So this build puts a watt into the head cavity with
 * nothing to aim it: it warms gas, board and cell, not the membrane face.
 *
 * WHAT IT IS NOT. It is not the production body and it must not be released as
 * one. An unpotted board in an open tube gives up two things the production
 * design is built around, and both are quantified in the echoes below:
 *
 *   1. GAS VOLUME. The head's cavity is held to <= 5.0 cm3 because that budget
 *      is what makes the response time meaningful (PROTOTYPE-RESPONSE.md). An
 *      unpotted tube adds its whole bore to that cavity through the board bore
 *      in the head, which is roughly 60 cm3 -- an order of magnitude over. The
 *      optional `dam` part below cuts most of it back; nothing here can remove
 *      it, and if the dam is not fitted the prototype's step response is a
 *      TUBE measurement, not a membrane measurement. Read the echo.
 *   2. SURFACE LEAKAGE. Potting is what keeps the sub-uA AFE nodes out of
 *      condensate. Buried, unpotted, in 100 %RH pore gas, they are not. Expect
 *      offset drift on CELL_RE and treat a plausible-looking low reading as
 *      suspect until the desiccant charge is checked on recovery.
 *
 * The three things it DOES buy: the tube's own OD becomes a MEASURED number
 * that closes `tube_od_meas` in o2_probe_head_end.scad; the printed wall gets a
 * real burial-season exposure against MEMBRANE.md's two named risks (bead-void
 * permeability, ESC in NH3 condensate); and the board comes back out, because
 * the cable end is a bayonet cap and nothing is bonded to the board.
 *
 * ORIENTATION FOR PRINTING: upright, CABLE END DOWN on the plate.  Every
 * internal feature here (guide slots, bayonet lugs, the seal land) is then a
 * vertical extrusion with no overhang and no support. The wall is FOUR 0.60 mm
 * loops and nothing else -- there is no infill anywhere in it, by construction
 * (see `wall`). Do not reduce the loop count to save time and do not let the
 * slicer pick its own line width: bead-to-bead voids are the leak path
 * MEMBRANE.md names, and 0.40 mm lines leaked in every study in
 * ~/dev/ee/p1p/doc/gastight-and-watertight.md.
 *
 * AND EVEN THEN THE WALL IS NOT GASTIGHT. That document's bottom line is that no
 * FDM part in the literature reaches the "tight" leak class -- not at 6 mm
 * walls, not at 0.09 mm layers, not with epoxy infusion. For a probe whose whole
 * output is a gas concentration, that is a MEASUREMENT path, not just a water
 * risk: whatever the wall passes is air, and air reads as 20.9 % O2. Treat this
 * prototype's absolute reading as biased high by an unknown amount, and take its
 * value from CHANGES over time rather than from the number itself.
 *
 * Preview: make body-tube
 */

$fn = 128;
e = 0.02;

part = "tube";       // tube, cap, dam, assembly
exploded = false;

// ------------------------------------------------- the interfaces

// Head. These three MUST track o2_probe_head_end.scad or the board lands in the
// wrong place: `socket_len` is how far the head swallows this tube, and
// `cav_board_len` is how far the board's tip stands proud of the tube end face
// inside the cavity. They are duplicated rather than included because that file
// asserts on four unmeasured inputs and refuses to load without them.
head_socket_len = 14.0;     // o2_probe_head_end.scad, socket_len
cav_board_len   = 2.0;      // o2_probe_head_end.scad, cav_board_len

// HOW THE HEAD JOINS.
//   "bonded"      the production joint: this tube slides 14 mm into the head's
//                 socket on a 0.2 mm radial adhesive gap. Two parts.
//   "monolithic"  the prototype joint: there ISN'T one. The head is printed in
//                 the same piece, so the tube stops where the head begins and
//                 o2_probe_head_end.scad's part="monobody" unions the two.
//
// Monolithic is the default for prototype 1 and the reason is sourcing, not
// elegance: the bonded joint is structural AND sealing, on the wet side, at
// ~75 C in ammoniacal condensate -- and MEMBRANE.md forbids a load-bearing
// adhesive there until a named one has passed hot-condensate ageing. No such
// adhesive is sourced. Printing through the joint deletes the requirement
// instead of guessing at it.
//
// What it costs: a failed print loses the whole body, and any change to the
// head reprints 147 mm of tube with it.
joint = "monolithic";       // "monolithic" or "bonded"
assert(joint == "monolithic" || joint == "bonded",
       str("unknown joint '", joint, "'"));

// Board. Controlled by KiCad Edge.Cuts (PLACEMENT.md).
board_w   = 20.0;
board_t   = 1.0;
board_len = 107.0;

// Component envelope. DECLARED, NOT MEASURED -- and the distinction matters,
// because the head's own model refuses to run without these measured.
//
// WHICH FACE: checked in o2-probe.kicad_pcb, not assumed. RV1 -- the 5 mm
// trimmer Fab named -- is a Bourns 3224W on **B.Cu**, i.e. the BACK, at board
// (2.5, 73.0) with pads spanning x 0.25..4.75. This file had it on the front
// until 2026-09-04; nothing broke, because the tube is round and has room on
// both faces, but the number was against the wrong surface.
//   front  3.0  L1, SRN6028C-4R7M, footprint L_6.3x6.3_H3. The tallest thing
//               on F.Cu: J3 is a Tag-Connect pogo land with no part fitted and
//               J2 is DNP.
//   back   5.0  RV1, the VREF trimmer. Fab, 2026-09-04: "mind the trimmer: its
//               5mm high". Also on this face, further gasward, is the cell
//               socket barrel -- PLAN.md "cell-orientation option A": "~2.6 mm
//               of socket protrudes out the back of a 1.0 mm board" -- so the
//               trimmer governs.
// Neither is a caliper reading on a populated assembly. They are used here only
// for CLEARANCE. Do NOT copy them into the head file, where the same numbers set
// a bore that a real assembly has to pass through.
board_env_front = 3.0;
board_env_back  = 5.0;

// Tube stock the printed part is imitating: PLAN.md's 32 OD / 28 ID target.
// Keeping the printed prototype ON that section is the whole point -- the head,
// its bore, its socket and the volume gate were all sized for it, so the
// prototype and the production body are dimensionally the same part.
tube_od = 32.0;
// 2.4, not the 2.0 that 32/28 implies, and the reason is the slicer rather than
// strength. ~/dev/ee/p1p/doc/gastight-and-watertight.md: 0.40 mm extrusion width
// leaked in every test, 0.64 mm sealed, so the wall is printed at 0.60 mm width
// -- and 2.0 mm is 3.33 of those, which fills the remaining third with gap-fill,
// a discontinuous bead and exactly the defect the wide line was chosen to avoid.
// 2.4 is FOUR whole 0.60 loops, no gap fill, no infill anywhere in the wall.
// The 0.8 mm of bore it costs is free: the board's swept diagonal is 21.8 mm.
wall    = 2.4;
tube_id = tube_od - 2*wall;
wall_line_w = 0.60;         // what the wall count above assumes
wall_loops = wall / wall_line_w;

// ------------------------------------------------- cable end

// M12 x 1.5 cable gland, TAPPED not printed. A printed thread at this pitch is
// a coin toss on a 0.4 mm nozzle and this joint is the only thing between the
// pile and an unpotted board; a hand tap in ASA is fifteen seconds and gives a
// real thread. 10.5 is the ISO tap drill for M12 x 1.5.
// The gland is the STRAIN RELIEF. Nothing else in this part anchors the cable,
// deliberately -- a printed internal tie post would have to bridge the bore.
// Leave a service loop in the tail and let the gland clamp the jacket.
// NOT SOURCED: the gland's clamp range has to match the cable OD, which has not
// been measured. That is a gland selection, not a geometry change -- M12 x 1.5
// is the same thread whatever it clamps.
gland_tap_d  = 10.5;
cap_end_t    = 8.0;         // 5.3 turns of M12 x 1.5
cap_wall     = 2.4;         // four 0.60 loops, same reason as the tube wall
cap_fit      = 0.4;         // diametral, cap bore over tube OD

// Cable tail inside the tube, measured from the board's cable end to the cap's
// inner face. Holds the four soldered wires, their service loop and a silica
// sachet. The cap adds its own depth on top of this.
tail_len = 22.0;

// CABLE-END SEAL -- RADIAL, on a spigot the cap carries into the tube's bore.
// It was a 28 x 2 FACE seal squeezed by the cap, and that was the wrong joint
// twice over. It needed a second ring size, and -- the part that actually
// decided it -- its squeeze was set by the bayonet's detent depth, a printed
// feature whose tolerance was never budgeted. Radial squeeze is set by a bore
// and a groove root, which is the one seal geometry this project has a
// validated tolerance model for (o2_probe_head_end.scad, the carrier ring).
//
// SAME RING AS THE CARRIER: o-ring-stocks.eu ORS116787, EPDM 70 Shore A
// peroxide-cured, 24.0 x 1.5 DIN 3771, house compound 127019011. One size, one
// compound, one test report, one micrometer-sorting pass for the whole probe.
// EPDM because ammonia attacks fluoroelastomers.
seal_id   = 24.0;
seal_cord = 1.5;
// The same 0.2433 the head uses, and for the same reason: it is where the
// tolerance band sits squarest, not a handbook preference.
seal_squeeze = 0.2433;
carrier_fit = 0.3;          // spigot to bore, diametral

// The cable end is REAMED, and it has to be: as-printed, the bore's +/-0.20
// spends 19.75 of the 15 available squeeze points on its own. Reamed it spends
// 0.72. Ø27.3 H7 is the SAME call-out and the SAME reamer as the head's well,
// which is the only reason this is one extra setup rather than one extra tool.
// Drawn at the finished size: a printed bore comes out UNDER, so the reamer has
// stock without the model having to carry a separate pre-ream diameter.
cable_bore_finish = "reamed";
cable_bore_d   = 27.3;      // H7, +0.021/0, ISO 286-2 18-30 band
cable_bore_len = 12.0;      // reamed depth
spigot_len = 8.5;
spigot_id  = 20.0;          // cable passage; sized by the wall under the groove

// Bayonet. Chosen over a thread or screws because MEMBRANE.md's rule for this
// enclosure is "no part of the enclosure may carry sustained strain at
// temperature ... retention is by positive features plus a compliant elastomer
// seal that supplies the sealing force". A bayonet lug is a positive feature
// and the O-ring is the spring; a printed thread preloaded at 75 C is the
// creeping-polymer case that rule exists to forbid.
lug_n      = 2;
lug_h      = 3.0;           // axial
lug_r      = 1.6;           // radial projection
lug_arc    = 22;            // degrees
lug_z      = 5.0;           // centre, from the tube's cable end face
slot_slack = 0.35;
// Angular slack at the ENTRY, in degrees. It is the window you have to find by
// feel with the tube in one hand: 3 deg was correct and unusable, 10 deg is a
// tenth of a turn of hunting. It costs nothing but arc.
entry_slack = 10;
twist_deg  = 30;            // lock rotation
// Back-lock depth, so vibration cannot walk the cap open. It is NOT free: to
// enter the pocket the lug must first be pushed PAST it, which compresses the
// O-ring by this much again. At 0.3 the transient squeeze is 40 % against a
// 25 % locked squeeze, which an EPDM cord takes; at the 0.7 first tried, the
// locked gap exceeded the cord and there was no seal at all.
detent     = 0.3;
// 18, not the 12 the face seal needed. The lock screw has to reach its pilot
// THROUGH the skirt, and the pilot has to sit clear of the reamer that cuts the
// sealing bore -- so the boss moved past cable_bore_len, and the skirt had to
// grow to still cover it. Asserted below rather than left to be noticed.
cap_engage = 18.0;          // tube end face depth in the cap AT LOCK
// The pocket runs PAST the end of the twist, not back toward the entry. A hand
// twist overshoots, and a pocket only as wide as the lug would mean feeling for
// an exact stop. Extending it the OTHER way would be worse than useless: it
// would reach back toward the entry slot and let the lug drop into the pocket
// without ever being twisted, which is a cap that falls off.
pocket_extra = 8;           // degrees of overshoot room past the twist

// LOCK SCREW. The bayonet's own retention is a 0.3 mm detent held by the
// O-ring's preload, and that is not something to bury for a season: the preload
// is tens of newtons and unmeasured, EPDM takes compression set at pile
// temperature, and the gland clamps the cable to the CAP, so every tug on the
// cable runs cable -> gland -> cap -> bayonet -> tube. One screw makes the lock
// positive and leaves the O-ring doing only the job it is good at.
//
// IT MUST NOT REACH THE BORE. A hole through the tube wall at this height opens
// the sealed volume to the outside, below the seal plane -- so the wall is
// thickened locally on the INSIDE, where at z=6 there is nothing but cable, and
// the pilot is blind with 1.0 mm left.
lock_screw = true;
lock_a_tube = 90;           // degrees in the TUBE frame, between the lugs
lock_pilot_d = 2.5;         // M3 thread-forming in ASA
lock_z = 17.0;              // clear of the reamed bore, still under the skirt
lock_boss_r = 9.5;          // inner face of the local wall thickening
lock_boss_arc = 22;         // degrees, centred on lock_a_tube
lock_boss_h = 6.0;
lock_pilot_floor = 12.5;    // radius the pilot bottoms at -> 1.75 mm of boss left
lock_slot_arc = 10;         // half-width of the cap's clearance slot, degrees

// ------------------------------------------------- board guides

// TWO STATIONS, and their positions are not free. The guide has to trap the
// board's EDGES, so it sits on top of whatever copper and parts are there --
// and this board has pads 0.25 mm from the edge (RV1 at y=73, R7 at y=46,
// R38 at y=70). Measured off o2-probe.kicad_pcb on 2026-09-04, the bands where
// BOTH edges are clear by >= 1.5 mm over a run of 5 mm or more are:
//
//     board y   0.0 .. 28.6      cable lands, protection, power
//              47.8 .. 55.7
//              58.3 .. 64.6
//              81.3 .. 103.6     gasward of the pot line
//
// The two long ones are used, which also puts the stations as far apart as the
// board allows. Engagement is 1.0 mm of board width per side against a 1.5 mm
// clear band, so there is 0.5 mm in hand -- and that margin is for PAD
// clearance only. Pads were what could be measured from the board file; a
// component BODY overhanging its own pads is not covered. Look along the edge
// of the populated board before the first insertion.
//
// IF THE BOARD REVISION CHANGES, RE-RUN THAT SCAN. These four numbers are the
// only thing tying this part to that board.
guide_engage = 1.0;
guide_slack  = 0.3;         // on board thickness
guide_body   = 7.0;         // rail width across the board plane
guide_r_max  = 14.8;        // how far the rail buries itself in the wall (bore is 13.6)
station_a = [ 4.0, 24.0];   // board y
// Station B is SHORTER in the monolithic joint, and not by choice. Bonded, the
// tube runs to board y=105 and the rail can use the whole 81.3..103.6 clear
// band. Monolithic, the tube stops where the head begins -- board y=91 -- so
// the rail has to end there, and only 81.3..91 of that band is on this part.
// Nothing carries the board over the last 16 mm in that case except the head's
// own bore, which is 24.93 against a 21.93 mm swept diagonal: it locates the
// board loosely, and it is the only thing that does.
station_b = (joint == "monolithic") ? [82.0, 90.0] : [86.0, 102.0];

// Optional dam, see the header. Sits just gasward of the pot line, in the same
// clear band as station B.
dam_y = 81.0;               // board y of its cable-side face
dam_t = 4.0;
dam_fit = 0.4;              // diametral, in the bore

// ------------------------------------------------- derived

board_in_tube = board_len - cav_board_len;      // 105.0
// Bonded, this part runs to where the board's tip section starts (board y=105)
// and its top 14 mm live inside the head's socket. Monolithic, the head's own
// z=0 face IS that plane minus the socket, so the tube ends there instead and
// the head carries on from it.
tube_len = board_in_tube + tail_len
         - ((joint == "monolithic") ? head_socket_len : 0);
board_y0_z = tail_len;                          // board y=0 sits here
function zy(y) = board_y0_z + y;                // board y -> tube z

// THE LOCK ROTATION, derived rather than measured off the checker.
// Work it in the LAB frame, where the tube stands +z up and the cap arrives
// from below. Placing the cap is rotate([180,0,0]), which maps (x,y,z) to
// (x,-y,-z) -- so a cap-frame angle phi appears at lab angle -phi, and the
// handedness of every cap angle flips. That flip is the single thing that made
// the first three attempts at this disagree with each other.
//   entry slot, cap [0, entry_arc]          -> lab [-entry_arc, 0]
//   pocket,     cap [pocket_a0, pocket_a1]  -> lab [-pocket_a1, -pocket_a0]
// A lug is modelled at tube angle [0, lug_arc] and the tube is turned by psi,
// so the lug sits at lab [psi, psi + lug_arc] and has to fit inside those.
entry_arc  = lug_arc + entry_slack;
pocket_arc = lug_arc + pocket_extra;
pocket_a0  = -twist_deg - pocket_extra;
pocket_a1  = pocket_a0 + pocket_arc;
psi_entry  = (-entry_arc + (-lug_arc))/2;               // -27
psi_lock   = (-pocket_a1 + (-pocket_a0 - lug_arc))/2;   // +12
// The pilot is at lock_a_tube in the TUBE, so at lock it stands at this lab
// angle, and the cap's clearance slot has to be at MINUS that in its own frame.
lock_a_lab = lock_a_tube + psi_lock;
lock_a_cap = -lock_a_lab;

// Bayonet angles, in the CAP's frame. The entry slot starts at 0 and the pocket
// sits `twist_deg` back from it; `pocket_a1 < 0` below is what guarantees the
// two never touch, i.e. that the cap cannot be pushed straight into its locked
// position without being twisted.
// Bayonet, in the CAP's frame (z from the cap mouth inward).
face_clear = 0.5;                               // tube end face to cap inner face
cap_bore_depth = cap_engage + face_clear;       // mouth to the cap's inner face
pocket_z  = cap_engage - lug_z - lug_h/2;       // pocket floor = the lock stop
chan_top  = pocket_z + detent + lug_h + slot_slack;
cap_h     = cap_bore_depth + cap_end_t;

// The radial gland, mirroring o2_probe_head_end.scad's carrier seal exactly.
spigot_od   = cable_bore_d - carrier_fit;
groove_root = cable_bore_d - 2*seal_cord*(1 - seal_squeeze);
groove_w    = 1.40 * seal_cord;                 // 1.40: the head's fill gate
seal_stretch = (groove_root - seal_id)/seal_id;
groove_wall = (groove_root - spigot_id)/2;      // material under the groove root
lead_chamfer = 1.0;

// THE AXIAL PRELOAD IS GONE, and that is a real consequence, not a footnote.
// A face seal pushed the tube back out and held the bayonet lug in its detent;
// a radial seal pushes outward, not along the axis, so nothing springs the lock
// any more. The M3 screw is now the whole of the retention -- which is what it
// was added for, so this costs nothing that was not already paid, but the
// bayonet on its own is no longer a lock and must not be treated as one.
assert(lock_screw,
       "a radial cable seal supplies no axial preload, so the bayonet has no spring: the lock screw is not optional with this seal");
assert(seal_stretch <= 0.05,
       str("install stretch ", seal_stretch*100, "% exceeds the 5% rule"));
assert(seal_stretch > 0,
       "the groove root is under the ring ID; it would not stay on the spigot");
assert(groove_wall >= 2.4,
       str("only ", groove_wall, " mm under the groove root, against 2.4 min"));
assert(cable_bore_d > tube_id,
       "the sealing counterbore is not larger than the tube bore; there is nothing to ream");
assert(board_diag <= cable_bore_d - 0.5,
       "the board does not pass the cable-end sealing bore");
assert(!lock_screw || lock_pilot_floor - lock_pilot_d/2 > lock_boss_r + 0.5,
       str("lock pilot breaks into the bore: floor r=",
           lock_pilot_floor - lock_pilot_d/2, " against boss r=", lock_boss_r,
           " -- that hole would vent the sealed volume past the O-ring"));
assert(!lock_screw || lock_boss_r > board_diag/2 + 0.5 || lock_z + lock_boss_h/2 < board_y0_z,
       "the lock boss is in the board's way");
assert(!lock_screw || lock_z - lock_boss_h/2 > cable_bore_len,
       str("the lock boss starts at z=", lock_z - lock_boss_h/2,
           ", inside the ", cable_bore_len,
           " mm reamed bore -- the reamer would machine it away"));
assert(!lock_screw || lock_z < cap_engage,
       str("the lock pilot at z=", lock_z, " is past the skirt's ", cap_engage,
           " mm of cover; the screw could not reach it"));
assert(pocket_a1 < -4,
       str("pocket reaches ", pocket_a1, " deg, into the entry slot -- the lug ",
           "could drop into the lock without being twisted, and the cap would ",
           "come off in the hole"));
assert(pocket_z > 1.5,
       "bayonet pocket breaks out of the cap mouth -- lug_z is too large");
assert(chan_top + 2.0 <= cap_bore_depth,
       "bayonet channel runs into the cap's inner face");

board_swept = board_env_front + board_t + board_env_back;
board_diag  = sqrt(pow(board_w, 2) + pow(board_swept, 2));

// Free gas the unpotted tube adds to the head cavity, board displacement out.
tube_gas = PI*pow(tube_id/2, 2) * board_in_tube
         - board_w*board_t*board_in_tube;
// With the dam fitted, only the tail and the short gasward stub remain
// connected -- and the dam's own board aperture is a slit, not a seal.
dam_blocked = PI*pow(tube_id/2, 2) - board_w*(board_swept + 2*guide_slack);
dam_gas = PI*pow(tube_id/2, 2) * (board_in_tube - dam_y)
        - board_w*board_t*(board_in_tube - dam_y);

// The rail's far CORNER, not its face, is what has to stay inside the wall.
guide_corner_r = sqrt(pow(guide_r_max, 2) + pow(guide_body/2, 2));
assert(guide_corner_r <= tube_od/2 - 0.6,
       str("guide rail corner reaches r=", guide_corner_r,
           " and breaks out of the ", tube_od/2, " wall"));
// The cap must not meet a rail. Nothing in the bayonet check would see this:
// it probes the cap against the tube, and a rail that fouls it would read as a
// bayonet failure with no clue where it came from.
assert(zy(station_a[0]) > cap_engage + 2.0,
       "station A rail reaches into the cap's bore");
assert(wall_loops == floor(wall_loops),
       str("wall ", wall, " is not a whole number of ", wall_line_w,
           " mm loops -- the remainder prints as gap fill, which leaks"));
assert(cap_wall / wall_line_w == floor(cap_wall / wall_line_w),
       "cap wall is not a whole number of extrusion widths");
assert(board_diag <= tube_id - 0.5,
       str("board diagonal ", board_diag, " does not pass the ", tube_id,
           " bore -- the swept envelope has outgrown the tube"));
assert(station_b[1] <= board_in_tube - 2.0,
       "station B runs past the end of the tube");
assert(guide_engage + 0.5 <= 1.5,
       "guide engagement exceeds the measured edge-clear band");
assert(lug_z + lug_h/2 < tube_len/2, "bayonet lugs are not at the cable end");

echo(str("BODY TUBE: ", tube_od, " OD x ", tube_id, " ID x ", tube_len,
         " long, wall ", wall, "; cap ", cap_h, " tall, adds ",
         cap_h - cap_engage, " mm past the tube; overall ",
         tube_len + cap_h - cap_engage, " mm to the head joint"));
if (lock_screw) echo(str("LOCK SCREW: M3 thread-forming, pilot ", lock_pilot_d,
         " blind at tube angle ", lock_a_tube, " deg, z=", lock_z,
         "; engages ", tube_od/2 - lock_pilot_floor, " mm of boss and leaves ",
         lock_pilot_floor - lock_pilot_d/2 - lock_boss_r,
         " mm to the bore. Cap slot at cap angle ", lock_a_cap,
         " deg, +/-", lock_slot_arc, ". Fit it AFTER twisting home."));
echo(str("BAYONET: lug at tube z=", lug_z, ", pocket floor at cap z=", pocket_z,
         ", twist ", twist_deg,
         " deg. NO axial preload: a radial seal supplies none, so the M3 screw ",
         "is the retention and the detent only resists back-rotation."));
echo(str("CABLE SEAL: ORS116787 24 x 1.5 EPDM, the SAME ring as the carrier. ",
         "Bore ", cable_bore_d, " ", cable_bore_finish, " x ", cable_bore_len,
         " deep; groove root ", groove_root, " x ", groove_w, " wide on a ",
         spigot_od, " spigot. Install stretch ", seal_stretch*100,
         "%, squeeze ", seal_squeeze*100, "%, ", groove_wall,
         " mm under the root."));
echo(str("BOARD: y=0 at z=", board_y0_z, ", tube end face at board y=",
         board_in_tube, ", tip ", cav_board_len, " proud into the cavity"));
// The trimmer sits at the board EDGE, so the flat "height above the board"
// figure is not the clearance -- the bore is round and the binding point is the
// component's outer top CORNER. RV1's outer pad edge is 0.25 mm in from the
// board edge, i.e. x = -9.75 in tube coordinates, 5.0 mm below the board plane.
rv1_corner_r = sqrt(pow(9.75, 2) + pow(board_t/2 + 5.0, 2));
assert(rv1_corner_r < tube_id/2 - 0.5,
       str("the trimmer's outer corner reaches r=", rv1_corner_r,
           " in a ", tube_id/2, " bore"));
echo(str("CLEARANCE: the trimmer's outer top CORNER sits at r=", rv1_corner_r,
         " in a ", tube_id/2, " bore -- ", tube_id/2 - rv1_corner_r,
         " mm spare. Its mid-face clearance of ", tube_id/2 - board_t/2 - 5.0,
         " mm is NOT the binding number; the part is at the board edge."));
echo(str("MEASURE ON THE PRINT: the OD, at several angles. It closes ",
         "tube_od_meas in o2_probe_head_end.scad, which currently refuses to ",
         "run without it. Print SHRINKS -- do not feed 32.0 back in."));
echo(str("GAS PENALTY, unpotted: the tube adds ", tube_gas/1000,
         " cm3 to the head's 4.84 cm3 cavity -- ",
         (tube_gas + 4840)/5000, "x the 5.0 cm3 budget. ",
         "With the dam at board y=", dam_y, ": ", dam_gas/1000, " cm3, ",
         (dam_gas + 4840)/5000, "x. The dam blocks ", dam_blocked,
         " mm2 of a ", PI*pow(tube_id/2,2), " mm2 bore."));

// ------------------------------------------------- modules

module bore_solid(z0, z1) {
    translate([0, 0, z0]) cylinder(d=tube_id, h=z1 - z0);
}

// One guide rail: fills the annulus between the board edge and the bore, with a
// slot the board edge slides into. Chamfered at BOTH ends -- the board goes in
// from the cable end, but the tube is printed and the head is bonded on before
// anyone finds out whether that is true.
// The rail is a plain CUBE, not the bore-arc intersection it started as. It runs
// radially past the bore and dies inside the wall, which is geometrically the
// same part after the union with the tube -- and it deletes four CGAL
// intersections against a 128-gon cylinder. That is not a micro-optimisation:
// with them, one probe in tools/bayonet_check.py cost 6.5 s and the check ran
// over five minutes.  `guide_r_max` is asserted to stay inside the wall.
module guide(sx, z0, z1) {
    lead = 1.5;
    slot_h = board_t + guide_slack;
    scale([sx, 1, 1]) {
        difference() {
            translate([board_w/2 - guide_engage, -guide_body/2, z0])
                cube([guide_r_max - board_w/2 + guide_engage, guide_body, z1 - z0]);
            // the slot, plus a lead-in taper at each end
            translate([board_w/2 - guide_engage - e, -slot_h/2, z0 - e])
                cube([tube_id, slot_h, z1 - z0 + 2*e]);
            for (zz = [[z0 - e, 1], [z1 + e, -1]])
                translate([board_w/2 - guide_engage - e, 0, zz[0]])
                    scale([1, 1, zz[1]])
                        linear_extrude(height=lead, scale=[1, slot_h/(slot_h + 2*lead)])
                            translate([0, -(slot_h/2 + lead)])
                                square([tube_id, slot_h + 2*lead]);
        }
    }
}

module bayonet_lug() {
    rotate_extrude(angle=lug_arc)
        translate([tube_od/2 - e, lug_z - lug_h/2])
            square([lug_r + e, lug_h]);
}

// The mating L-slot, as a solid to subtract from the cap skirt. Built in the
// CAP's frame, where z runs from the cap mouth inward.
//
// The lock position is set by the POCKET FLOOR, not by how far the cap can be
// pushed on: the O-ring pushes the tube back out until the lug's inner face
// lands on that floor, and where the floor sits is what fixes the squeeze.
// Everything else is derived from it, which is the only way the two constraints
// (25 % squeeze, and a pocket the lug has to be pushed past) stay consistent.
module bayonet_slot() {
    h = lug_h + slot_slack;
    r0 = tube_od/2 + cap_fit/2 - e;
    r1 = tube_od/2 + lug_r + slot_slack;
    // axial entry, open to the mouth
    rotate_extrude(angle=entry_arc)
        translate([r0, -e]) square([r1 - r0, chan_top + e]);
    // circumferential run, one detent deeper than the locked position
    rotate([0, 0, pocket_a0])
        rotate_extrude(angle=entry_arc - pocket_a0)
            translate([r0, pocket_z + detent]) square([r1 - r0, h]);
    // the pocket itself, at and past the end of the twist
    rotate([0, 0, pocket_a0])
        rotate_extrude(angle=pocket_arc)
            translate([r0, pocket_z]) square([r1 - r0, h + detent]);
}

// ------------------------------------------------- parts

module tube() {
    // THE NESTING MATTERS AND IT IS NOT OBVIOUS. The boss has to be unioned on
    // AFTER the bore is cut, because it stands inside the bore -- put it in the
    // outer union and the bore subtraction eats it whole. The pilot then has to
    // be cut LAST, so it passes through wall and boss together.
    //
    // It was written the wrong way round and shipped: the boss vanished, and
    // the pilot -- 3.5 mm deep into a 2.4 mm wall -- became a THROUGH HOLE from
    // the outside straight into the sealed volume, below the seal plane. The
    // assert beside lock_pilot_floor passed the whole time, because it compared
    // declared numbers with each other instead of measuring the mesh. There is
    // a mesh check for it now, in tools/bayonet_check.py.
    difference() {
        union() {
            difference() {
                union() {
                    cylinder(d=tube_od, h=tube_len);
                    for (i = [0:lug_n-1]) rotate([0, 0, i*360/lug_n]) bayonet_lug();
                }
                translate([0, 0, -e]) cylinder(d=tube_id, h=tube_len + 2*e);
                // The sealing counterbore, reamed. 0.05 mm larger than the bore
                // on radius so it is a real step the reamer can find, and 12 mm
                // deep -- which is what pushed the lock boss to z=17 and the
                // cap's skirt to 18: nothing internal may stand in its path.
                translate([0, 0, -e])
                    cylinder(d=cable_bore_d, h=cable_bore_len + e);
            }
            // Local wall thickening for the lock screw, standing INTO the bore
            // at a height where only cable passes.
            if (lock_screw)
                rotate([0, 0, lock_a_tube - lock_boss_arc/2])
                    rotate_extrude(angle=lock_boss_arc)
                        translate([lock_boss_r, lock_z - lock_boss_h/2])
                            square([tube_id/2 - lock_boss_r, lock_boss_h]);
        }
        // Blind pilot, from outside, stopping short of the bore. Two more traps
        // lived in this one expression and both rendered as clean closed solids:
        // rotate([0,-90,0]) sends local +z to -X, so the hole came out 180 deg
        // away through plain wall; and the rotate leaves the axis at the
        // ORIGIN's height, so without the outer translate it was cut at z=0,
        // half of it hanging off the end face.
        if (lock_screw)
            translate([0, 0, lock_z])
                rotate([0, 0, lock_a_tube]) rotate([0, 90, 0])
                    translate([0, 0, lock_pilot_floor])
                        cylinder(d=lock_pilot_d, h=tube_od, $fn=32);
    }
    for (s = [1, -1]) {
        guide(s, zy(station_a[0]), zy(station_a[1]));
        guide(s, zy(station_b[0]), zy(station_b[1]));
    }
}

// The cuts are UNIONED and then subtracted once. OpenSCAD 2021.01 has no
// manifold backend (`--backend=manifold` is rejected), so this is on CGAL, and
// fourteen sequential differences against a 128-gon body cost 3.7 s where one
// costs a fraction of that. tools/bayonet_check.py runs this module ~50 times.
module cap() {
    difference() {
        union() {
            cylinder(d=tube_od + cap_fit + 2*cap_wall, h=cap_h);
            // The sealing spigot, reaching back out of the cap's inner face and
            // into the tube's reamed bore. Chamfered at its tip so the ring is
            // not shaved on assembly.
            translate([0, 0, cap_bore_depth - spigot_len])
                cylinder(d1=spigot_od - 2*lead_chamfer, d2=spigot_od,
                         h=lead_chamfer);
            translate([0, 0, cap_bore_depth - spigot_len + lead_chamfer])
                cylinder(d=spigot_od, h=spigot_len - lead_chamfer + e);
        }
        union() {
            // the tube's seat
            translate([0, 0, -e])
                cylinder(d=tube_od + cap_fit, h=cap_bore_depth + e);
            // the radial O-ring groove, in the spigot
            translate([0, 0, cap_bore_depth - spigot_len + lead_chamfer + 1.2])
                difference() {
                    cylinder(d=spigot_od + 2*e, h=groove_w);
                    translate([0, 0, -e])
                        cylinder(d=groove_root, h=groove_w + 2*e);
                }
            // the cable passage through the spigot
            translate([0, 0, cap_bore_depth - spigot_len - e])
                cylinder(d=spigot_id, h=spigot_len + 2*e);
            // tapped M12 x 1.5 for the gland
            translate([0, 0, cap_bore_depth - e])
                cylinder(d=gland_tap_d, h=cap_end_t + 2*e);
            for (i = [0:lug_n-1]) rotate([0, 0, i*360/lug_n]) bayonet_slot();
            // Lock-screw clearance. An ARC, not a hole: it is +/- lock_slot_arc
            // wide so the screw still finds its pilot anywhere in the pocket's
            // own play, which is what makes this assemblable by hand.
            if (lock_screw)
                rotate([0, 0, lock_a_cap - lock_slot_arc])
                    rotate_extrude(angle=2*lock_slot_arc)
                        translate([tube_od/2 - e,
                                   cap_engage - lock_z - (lock_pilot_d + 0.7)/2])
                            square([cap_wall + cap_fit + 2*e, lock_pilot_d + 0.7]);
            // grip scallops
            for (i = [0:5]) rotate([0, 0, i*60])
                translate([tube_od/2 + cap_fit/2 + cap_wall + 0.9, 0, -e])
                    cylinder(d=2.4, h=cap_h + 2*e, $fn=24);
        }
    }
}

// Split dam. Two halves that meet on the board plane, pushed into the bore
// against the board. It is a RESTRICTOR, not a seal -- see the echo for what it
// actually buys. Printed flat, both halves in one go.
module dam_half(env, sign) {
    difference() {
        intersection() {
            cylinder(d=tube_id - dam_fit, h=dam_t);
            translate([-tube_id, sign > 0 ? 0 : -tube_id, -e])
                cube([2*tube_id, tube_id, dam_t + 2*e]);
        }
        translate([-(board_w + 2*guide_slack)/2,
                   sign > 0 ? -e : -(env + board_t/2), -e])
            cube([board_w + 2*guide_slack, env + board_t/2 + e, dam_t + 2*e]);
    }
}

module dam() {
    translate([0, 2, 0]) dam_half(board_env_front + guide_slack,  1);
    translate([0, -2, 0]) dam_half(board_env_back + guide_slack, -1);
}

// Representative board, drawn only. Never exported.
module board_stub() {
    color("ForestGreen")
        translate([-board_w/2, -board_t/2, zy(0)])
            cube([board_w, board_t, board_len]);
    // RV1, the trimmer: BACK face, board x 0.25..4.75 -> tube x -9.75..-5.25.
    color("Crimson")
        translate([-9.75, -board_t/2 - 5.0, zy(71.1)]) cube([4.5, 5.0, 3.8]);
    color("DarkSlateGray")
        translate([0, 0, zy(board_len) + 1.0]) cylinder(d=14.62, h=8.3);
}

module assembly() {
    ex = exploded ? 1 : 0;
    color("Sienna") tube();
    color("Tan") translate([0, 0, -cap_bore_depth - ex*25]) cap();
    board_stub();
    color("SlateGray") translate([0, 0, zy(dam_y) + ex*12]) dam();
}

if (part == "tube") tube();
else if (part == "cap") cap();
else if (part == "dam") dam();
else if (part == "assembly") assembly();
else assert(false, str("unknown part '", part, "'"));
