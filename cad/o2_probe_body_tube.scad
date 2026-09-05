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
// 3.0, tracking o2_probe_head_end.scad's socket_len, which is now
// `monolithic ? 3.0 : 14.0`. THIS IS NOT COSMETIC: tube_len subtracts it, so
// leaving it at 14 would have ended the tube 11 mm short of the head and put
// the board's tip 11 mm past the cavity. The overall probe length does not
// change -- 11 mm of Ø40 head simply becomes 11 mm of Ø32 tube.
head_socket_len = 3.0;      // o2_probe_head_end.scad, socket_len (monolithic)
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
// 1.6, on Fab's instruction 2026-09-05, NOT the 1.0 in PLACEMENT.md. That file
// still specifies "20.0 x 107.0 mm ... 1.0 mm, 4 layers", so the two disagree
// and the board file is the one that would have to change. PLAN.md gates a
// thickness change on "the tube chord/assembled-height check" -- done here: the
// swept diagonal goes 21.93 -> 22.19 against a 27.2 bore and the head's 25.19,
// so it clears both. The slot heights and the dam reliefs follow automatically.
board_t   = 1.6;
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

// CABLE GLAND -- TWO PARTS, and which one is fitted is a variant, not a
// preference. Fab, 2026-09-05: M8 brass for prototype 1's bench work and first
// fit, 316L for anything that goes in the ground.
//
//   "m8_brass"  Lumonic M8 x 1.0, nickel-plated brass, NBR seal, clamp 2-5 mm,
//               -40..+100 C, max panel 3 mm, hex nut supplied. IN HAND.
//   "m12_inox"  LAPP SKINTOP INOX-R M12x1,5, art. 53806749: 316L body, silicone
//               seal and O-ring, clamp 3,0-5,0 mm, thread 6,5 mm, SW16.
//               Specified in CABLE-SOURCING.md / POTTING.md, commit bb29a1d.
//
// WHY THERE ARE TWO, and it is not fit -- both clamp the ordered cable's 3,80 mm
// (UNITRONIC SENSOR FD Li9Y11Y 4x0,25, art. 7038890) comfortably. It is
// chemistry. Ammonia is the classic stress-corrosion-cracking agent for brass,
// worse in vapour than in liquid, and the canonical example in the literature is
// ammonia vapour from decaying organic matter. A gland is a PRE-STRESSED brass
// part and a windrow is an ammonia vapour generator: that is the whole SCC triad
// with nothing missing. So nothing brass goes in the pile. On the bench, where
// prototype 1 is fitted and handled first, it is fine and it is the part we have.
gland = "m8_brass";         // "m8_brass" (bench) or "m12_inox" (burial)
assert(gland == "m8_brass" || gland == "m12_inox",
       str("unknown gland '", gland, "'"));

// NOT TAPPED. This was tapped M8 x 1.0 into the ASA until POTTING.md's sourcing
// pass pointed out what it is: "Do not tap the gland thread directly into the
// plastic cap. MEMBRANE.md's rule against sustained strain in plastic at 75 C
// applies exactly here: the cap would creep and the seal relax." That is the
// same rule this file already cites against a preloaded printed thread on the
// bayonet -- and the gland thread was breaking it three lines away from the
// argument. A clearance hole and the gland's own nut put the load path
// metal-to-metal and the plastic merely between two steel faces.
gland_thread_d = (gland == "m8_brass") ? 8.0 : 12.0;
gland_hole_d   = (gland == "m8_brass") ? 8.5 : 12.5;   // clearance, not tap drill
// Each part's own limit on how much plastic can sit between flange and nut.
// m8: the vendor's rated 3 mm panel. m12: 6,5 mm of thread less a 2,8 mm
// stainless locknut = 3,7 mm, the arithmetic POTTING.md worked out and asked
// whoever edits this file to respect.
gland_wall_max = (gland == "m8_brass") ? 3.0 : 3.7;
cap_end_t    = 3.0;         // fits both; see the assert below

// THE GLAND'S OWN SEAL, and where it sits. An annular NOTCH in the cap's OUTER
// face, concentric with the hole, so the gland's ring drops into it instead of
// being squeezed out sideways on a flat face.
//
// WHY A GROOVE AND NOT A COUNTERBORE: a counterbore would sink the whole hole
// mouth and spend its depth out of the wall the gland clamps, on a wall that is
// only 3 mm to begin with. An annulus that starts OUTSIDE the thread's clearance
// hole takes its depth out of material the gland does not bear on, so the
// clamped thickness stays the full cap_end_t. gland_notch_id is asserted clear
// of the hole below.
//
// MEASURE THESE. They are the dimensions of a real ring on a real part and the
// project's rule is not to guess those. The values are provisional, and they
// only LOCATE the seal -- the sealing force comes from the gland's flange.
// Reference edges: the free ring off the gland, ID and OD across the ring, cord
// by micrometer.
// These provisionals are not free choices: the ring sits AROUND the clearance
// hole, so its ID is necessarily larger than the hole, and the notch that holds
// it has to start outside the hole too. 8.0 was the first value here and the
// assert below rejected it -- an 8.0 ID ring cannot surround an 8.5 hole. The
// numbers are the smallest physically coherent ones, which is the right place
// for a provisional to sit until the real ring is measured.
gland_seal_id   = (gland == "m8_brass") ? 8.6 : 12.6;   // MEASURE: free ring ID
gland_seal_cord = 1.5;      // MEASURE: cord diameter
gland_seal_squeeze = 0.25;  // design point; the flange sets the real value  // design point; the flange sets the real value
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

// HOW THE CAP'S GROOVE IS MADE, and it is the second sealing surface -- the
// bore is reamed and this one is not, so it is now the loose end of the chain.
//   "printed"   as it comes off the printer, +/-0.09 (seven readings on printed
//               ASA carriers, o2_probe_head_end.scad carrier_tol)
//   "machined"  turned to size, +/-0.05
cap_fab = "printed";
// MICROMETER-SORT THE RINGS. Not a preference: on catalogue cord the chain does
// not close (see the band assert below), which the 2026-09-05 Codex review found
// and this file's prose had wrong at 12.18 of 15. It is the same ring as the
// carrier, so one sorting pass covers the whole probe.
oring_sorting = "sorted";   // "sorted" or "catalogue"

// SHRINK COMPENSATION ON THE PRINTED ROOT. The head records three readings of a
// root cut oversize and measured after printing -- factors 0.99040, 0.98801 and
// 0.98880, mean 0.9891 -- and the cap emitted its root with no correction at
// all, so a printed root would land near 24.77 against a 25.03 target and take
// nominal squeeze down to about 14 %. Drawn oversize by 1/factor so the PRINTED
// root lands on target.
//
// PROVENANCE IS NOT AIRTIGHT: those readings are on the carrier, and the print
// prescription here is different (1.00-1.02 flow, 0.10-0.15 layers, 0.60 lines
// against 0.95 / 0.20 / 0.45). MEASURE THE ROOT ON THE FIRST CAP before trusting
// the seal, and correct this factor from that measurement.
cap_root_shrink = (cap_fab == "printed") ? 0.9891 : 1.0;

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
//
// THE WEDGE RAMP. The pocket used to be a flat slot 0.65 mm taller than the lug,
// so once the lug dropped in it rattled over that 0.65 and turning further did
// nothing. Now the pocket's DEEP wall closes on the lug over the last stretch of
// travel: keep turning and the cap wedges tight.
//
// WHAT THIS IS NOT. It does not tighten the SEAL. The cable seal is radial --
// squeeze is set by the bore and the groove root -- so no amount of twist
// changes it, and that is the point rather than a limitation. A ramp that
// compressed a FACE seal would be sizing an elastomer by hand torque, i.e. a
// sustained strain on ASA at pile temperature, which is what MEMBRANE.md's rule
// forbids. This ramp loads a plastic-on-plastic wedge and nothing else.
//
// WHICH WALL, and it matters for printing: the cap prints MOUTH UP, so the
// pocket's deep wall is an UPWARD-facing surface. Ramping it costs nothing in
// overhang. The mouth-side wall -- the one that carries pull-out load -- is the
// printed roof and is left flat and at pocket_z, so the retention face is
// unchanged from the version that was checked.
ramp = true;
ramp_free = 6;              // deg of pocket the lug drops into before it bites
ramp_deg  = 16;             // deg over which the deep wall closes
// HOW MUCH CLEARANCE IS LEFT AT THE FAR WALL, and this number is the whole
// difference between a wedge that works and one that fights the lock screw.
//
// The first version closed PAST the lug -- 0.15 mm of designed interference, a
// friction wedge, self-locking at 9.6 deg. It measured beautifully and it was
// wrong, and the mesh check is what said so. A friction wedge has no defined
// stop: it stops where hand force balances elastic deformation. The check drove
// the cap to 30 deg (0.2 mm3 of interference) while the model declared its lock
// at 27, and the lock screw cannot live with that. The tube pilot is a 2.5 mm
// hole at r=14, so ONE degree of scatter is 0.24 mm of lateral offset and three
// degrees is 0.73 mm -- the screw simply misses.
//
// So the far wall is the stop, positively, and the ramp only takes up the play
// on the way to it. 0.20 mm is left at the wall: the pocket still converges 0.45
// of its 0.65 mm of rattle, a 3.3x improvement, while a pocket that prints
// 0.1 mm short still REACHES the wall instead of binding 4 deg early and putting
// the pilot out of the screw's reach.
//
// WHAT WAS TRADED AWAY, plainly: there is no interference fit any more and so no
// friction hold. Retention was already the M3 screw -- the assert below has
// refused to build without it since the seal went radial -- so nothing
// load-bearing has been given up. What is gained is a lock angle the screw can
// find.
ramp_clear = 0.20;
// A staircase, because rotate_extrude sweeps a CONSTANT profile and cannot vary
// z with angle. 16 steps puts each riser at 0.05 mm, a quarter of a layer, so
// the slicer cannot resolve them and the printed surface is the ramp.
ramp_steps = 16;
pocket_extra = ramp ? ramp_free + ramp_deg : 8;

// LOCK SCREW. The bayonet's own retention is a 0.3 mm detent plus the wedge
// ramp above -- a friction hold, and friction is not something to bury for a
// season: the ramp's grip depends on a coefficient nobody here has measured, on
// ASA that creeps at pile temperature, and the gland clamps the cable to the
// CAP, so every tug on the cable runs cable -> gland -> cap -> bayonet -> tube.
// One screw makes the lock positive and leaves the wedge doing only what it is
// good at, which is taking the rattle out.
//
// (This paragraph used to credit "the O-ring's preload" for holding the detent.
// That was the 28 x 2 FACE seal, gone since 7fd21c0. A radial seal pushes
// outward, not along the axis, and supplies no preload at all -- which is why
// the assert further down refuses to build without this screw.)
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
// The lug travels toward DECREASING cap angle, so it enters the pocket at the
// pocket_a1 end and runs out toward pocket_a0. In psi that is +8 (just dropped
// in) to +30 (leading edge on the far wall).
psi_seated = -pocket_a1;                    // +8, the moment it drops in
psi_hard   = -pocket_a0 - lug_arc;          // +30, leading edge on the far wall
// The ramp starts once the LEADING edge passes ramp_a, and closes linearly to
// the far wall. The lug stops where the closure equals the interference, which
// is ramp_interf short of the hard end -- so the lock angle is derived from the
// ramp, not from the middle of a slot.
ramp_a     = pocket_a0 + ramp_deg;                      // cap angle, -36
ramp_close = detent + slot_slack - ramp_clear;          // 0.45 mm of closure
// Guarded: the bayonet check's known-bad control builds this same cap with
// -D ramp_close=0, and an unguarded divide made that control render as nothing
// at all -- a calibration that fails to build is not a calibration.
// The stop is the FAR WALL, so the lock angle is psi_hard and nothing is derived
// from how hard the cap happened to be turned.
psi_lock   = ramp ? psi_hard                            // +30
                  : (-pocket_a1 + (-pocket_a0 - lug_arc))/2;
// SELF-LOCKING, which is the whole reason the ramp is shallow and long rather
// than short and steep. A wedge holds only while its slope is under the
// coefficient of friction; above that it springs back out as soon as the hand
// comes off. ASA on ASA is ~0.35-0.45 dry, so 0.20 is the limit with margin for
// a wet, warm, ammoniacal joint.
ramp_r    = tube_od/2 + (lug_r + slot_slack)/2;         // mean contact radius
ramp_run  = ramp_r * ramp_deg * PI/180;
ramp_slope = ramp_close/ramp_run;
// The ramp must not close past the lug, or the lug stops on the RAMP instead of
// on the wall and the lock angle becomes force- and tolerance-dependent -- which
// is the defect this parameterisation exists to prevent, so it is asserted and
// not merely commented.
assert(!ramp || ramp_clear > 0,
       "the ramp closes onto the lug: the cap would stop on the ramp rather than on the far wall, and the lock screw pilot moves with however hard it was turned");
// Shallow enough that the lug is guided rather than jammed. This is no longer a
// self-locking criterion -- there is no interference to lock -- but a steep ramp
// on a printed staircase would be a step the lug climbs, not a surface it slides on.
assert(!ramp || ramp_slope <= 0.20,
       str("ramp slope ", ramp_slope, " (", atan(ramp_slope),
           " deg) is too steep for the lug to slide up. Lengthen ramp_deg."));
// The lug has to be able to DROP INTO the pocket before the ramp touches it,
// otherwise there is no seated state and the cap jams on the way in.
assert(!ramp || ramp_free >= 2,
       "no free pocket before the ramp: the lug would meet the closing wall before it has dropped off the detent step");
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

// THE GLAND'S SEAL NOTCH, derived. Mean diameter on the ring's own centreline,
// width 1.2x cord so the ring can spread as it is squeezed, depth cord minus
// the squeeze so the gland's flange still lands on the face and does the
// compressing -- a groove deeper than the cord would hold the flange off and
// seal nothing.
gland_notch_mean  = gland_seal_id + gland_seal_cord;
gland_notch_w     = 1.20 * gland_seal_cord;
gland_notch_id    = gland_notch_mean - gland_notch_w/2;
gland_notch_od    = gland_notch_mean + gland_notch_w/2;
gland_notch_depth = gland_seal_cord * (1 - gland_seal_squeeze);

// The notch must not eat the thread. This is the assert that makes the 3 mm
// wall work at all: if the groove's inner wall fell inside the thread's major
// diameter it would take its depth out of the tapped length, and 3 mm is
// already only 3 turns of M8 x 1.0.
assert(gland_notch_id >= gland_hole_d + 0.4,
       str("the gland seal notch runs to dia ", gland_notch_id,
           ", inside the ", gland_hole_d,
           " mm clearance hole -- it would break into the hole instead of ",
           "sitting on the face the gland bears on"));
// And it must leave a floor. 1.5 mm is two 0.6 mm walls plus a skin, on a face
// that carries the whole cable pull through the gland's flange.
assert(cap_end_t - gland_notch_depth >= 1.5,
       str("only ", cap_end_t - gland_notch_depth,
           " mm of cap end left under the seal notch"));
assert(gland_notch_od + 2*cap_wall <= tube_od + cap_fit + 2*cap_wall,
       "the gland seal notch runs out past the cap's rim");
// The plastic sits between the gland's flange and its nut, so the wall cannot
// exceed what the thread has left after the nut takes its share.
assert(cap_end_t <= gland_wall_max + 1e-9,
       str("cap end ", cap_end_t, " mm exceeds the ", gland_wall_max,
           " mm this gland can clamp; the nut would run out of thread before it seated"));

// The radial gland, mirroring o2_probe_head_end.scad's carrier seal exactly --
// including the parts this file used to skip.
spigot_od   = cable_bore_d - carrier_fit;
// seal_squeeze is the SIZING BASIS, not the achieved squeeze. It sets the root;
// what the ring then delivers is seal_squeeze_real below, and they are not the
// same number because stretching the ring thins its cord.
groove_root = cable_bore_d - 2*seal_cord*(1 - seal_squeeze);
groove_root_drawn = groove_root / cap_root_shrink;   // what the model cuts
groove_w    = 1.40 * seal_cord;                 // 1.40: the head's fill gate
seal_stretch = (groove_root - seal_id)/seal_id;
groove_wall = (groove_root - spigot_id)/2;      // material under the groove root
lead_chamfer = 1.0;

// SQUEEZE AFTER STRETCH-THINNING. Stretching a cord onto a groove root makes it
// thinner, and that eats squeeze -- the head has always done this and this file
// reported the unthinned number, overstating squeeze by about 1.7 points.
// Linear thinning (1 - stretch/2), the head's convention; constant volume
// (1/sqrt(1+stretch)) differs by 0.001 mm here and is not worth the divergence.
seal_gland      = (cable_bore_d - groove_root)/2;
seal_cord_thin  = 1 - seal_stretch/2;
seal_cord_fit   = seal_cord * seal_cord_thin;
seal_squeeze_real = (seal_cord_fit - seal_gland)/seal_cord_fit;

// THE WORST CORNER, which is what decides whether this seals at all. Three
// things vary, not one: the reamed bore, the cap's groove root, and the cord of
// the ring itself. Least squeeze is the widest gland on the thinnest cord.
bore_tol  = (cable_bore_finish == "reamed") ? 0.0105 : 0.20;  // ISO 286-2 H7
root_tol  = (cap_fab == "machined") ? 0.05 : 0.09;
cord_tol  = (oring_sorting == "sorted") ? 0.01 : 0.08;        // DIN ISO 3601
seal_pair_tol = bore_tol + root_tol;
cord_min = (seal_cord - cord_tol) * seal_cord_thin;
cord_max = (seal_cord + cord_tol) * seal_cord_thin;
gland_min = ((cable_bore_d - groove_root) - seal_pair_tol)/2;
gland_max = ((cable_bore_d - groove_root) + seal_pair_tol)/2;
squeeze_max = (cord_max - gland_min)/cord_max;
squeeze_min = (cord_min - gland_max)/cord_min;
seal_band      = squeeze_max - squeeze_min;
seal_band_pair = seal_pair_tol / seal_cord_fit;
seal_band_cord = seal_band - seal_band_pair;

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
assert(seal_stretch >= 0.01,
       str("install stretch is only ", seal_stretch*100,
           "%; the ring would not stay seated on the spigot"));
assert(seal_squeeze_real >= 0.15,
       str("squeeze after stretch-thinning is only ", seal_squeeze_real*100,
           "%; a static radial seal wants 15% or more"));
// The 15-30% window is 15 points wide, so tolerance alone must not span it.
// THIS IS THE ASSERT THAT FAILS ON CATALOGUE RINGS, and the prose in
// PRINTING-BODY-TUBE.md claimed 12.18 of 15 when the real figure is over 15.
assert(seal_band <= 0.15,
       str("tolerance alone spans ", seal_band*100, " squeeze points -- ",
           seal_band_pair*100, " from the seal pair (bore +/-", bore_tol,
           ", root +/-", root_tol, ") and ", seal_band_cord*100,
           " from the cord (+/-", cord_tol,
           "). Sort the rings, machine the cap's groove, or use a fatter cord."));
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

// THE CONNECTED GAS VOLUME. The previous version got two things wrong, both
// found by the 2026-09-05 Codex review:
//
//   1. It counted board_in_tube (105 mm) and so OMITTED THE CABLE TAIL -- 22 mm
//      of open bore around a service loop and a silica sachet, connected to
//      everything else and not small.
//   2. The head cavity was hardcoded at 4840 mm3, from before the board went to
//      1.6 mm. The measured cavity mesh is 4917.
//
// Still a MODEL, not a measurement: it ignores the board's components, the
// cable, the sachet and the guide rails, all of which displace gas, so it errs
// LARGE. That is the safe direction for a budget.
head_cavity = 4917;         // mm3, MEASURED off the cavity mesh
tube_bore_area = PI*pow(tube_id/2, 2);
tube_gas_board = tube_bore_area * board_in_tube - board_w*board_t*board_in_tube;
tube_gas_tail  = tube_bore_area * tail_len;
tube_gas = tube_gas_board + tube_gas_tail;

// THE DAM IS A RESTRICTOR, NOT A BULKHEAD, and the number this used to print
// implied otherwise -- it reported a "with the dam" volume as though the tail
// had been disconnected. It is a loose split disc. It does not seal, so at
// equilibrium the whole tube is still one connected volume and NO volume is
// removed. What it changes is the CONDUCTANCE between head cavity and tail,
// turning one time constant into two, and how much that is worth cannot be got
// from a volume ratio -- it needs a measured transient.
dam_blocked   = tube_bore_area - board_w*(board_swept + 2*guide_slack);
dam_open      = tube_bore_area - dam_blocked;
dam_near_side = tube_bore_area * (board_in_tube - dam_y)
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
         ", twist ", psi_lock - psi_entry, " deg total (entry psi ", psi_entry,
         " -> lock psi ", psi_lock,
         "). NO axial preload: a radial seal supplies none, so the M3 screw ",
         "is the retention and the detent only resists back-rotation."));
if (ramp) echo(str("WEDGE RAMP: the pocket's deep wall closes ", ramp_close,
         " mm over ", ramp_deg, " deg (slope ", ramp_slope, " = ", atan(ramp_slope),
         " deg), leaving ", ramp_clear, " mm at the wall. Lug drops in at psi ",
         psi_seated, ", starts converging at psi ", psi_seated + ramp_free,
         ", and STOPS ON THE FAR WALL at psi ", psi_hard,
         " -- a positive stop, not a friction wedge, so the lock screw's pilot is ",
         "at a repeatable angle. Rattle once home: ", ramp_clear, " mm, down from ",
         detent + slot_slack, ". IT DOES NOT TIGHTEN THE SEAL -- the cable seal is ",
         "radial and its squeeze is set by the bore and the groove root. Turning ",
         "harder takes up play, nothing else."));
echo(str("CABLE SEAL: ORS116787 24 x 1.5 EPDM, the SAME ring as the carrier. ",
         "Bore ", cable_bore_d, " ", cable_bore_finish, " x ", cable_bore_len,
         " deep; groove root ", groove_root, " target (CUT ", groove_root_drawn,
         ", ", cap_fab, ", shrink ", cap_root_shrink, ") x ", groove_w,
         " wide on a ", spigot_od, " spigot, ", groove_wall,
         " mm under the root."));
echo(str("CABLE SEAL squeeze: ", seal_squeeze*100, "% is the SIZING BASIS; ",
         "after ", seal_stretch*100, "% stretch thins the cord the ring ",
         "actually delivers ", seal_squeeze_real*100, "%."));
echo(str("CABLE SEAL tolerance: ", seal_band*100, " of 15 squeeze points -- ",
         seal_band_pair*100, " seal pair (bore ", cable_bore_finish, " +/-",
         bore_tol, ", root ", cap_fab, " +/-", root_tol, "), ",
         seal_band_cord*100, " cord (", oring_sorting, " +/-", cord_tol,
         "). Worst case ", squeeze_min*100, "-", squeeze_max*100, "%."));
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
echo(str("GAS VOLUME, unpotted: head cavity ", head_cavity/1000,
         " cm3 (MEASURED off the cavity mesh) + tube ", tube_gas_board/1000,
         " + tail ", tube_gas_tail/1000, " = ", (head_cavity + tube_gas)/1000,
         " cm3, ", (head_cavity + tube_gas)/5000, "x the 5.0 cm3 budget."));
echo(str("THE DAM DOES NOT REDUCE THAT. It is a loose split disc, not a seal: ",
         dam_open, " mm2 of a ", tube_bore_area,
         " mm2 bore stays open, so at equilibrium the tail is still connected. ",
         "It puts ", dam_near_side/1000,
         " cm3 on the head side of a restriction and turns one time constant ",
         "into two. What that is worth needs a MEASURED transient, not a ",
         "volume ratio."));

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
// STALE PROSE REMOVED, and what it said is worth recording because it was the
// kind of wrong that reads as authoritative: "the O-ring pushes the tube back
// out until the lug's inner face lands on that floor, and where the floor sits
// is what fixes the squeeze". True of the 28 x 2 FACE seal this cap once had,
// false since 7fd21c0. The radial seal fixes squeeze by DIAMETER, and pocket_z
// no longer has anything to do with it.
//
// What pocket_z does now: it is the pull-out face, the surface the lug bears on
// when the cable is tugged. It sets cap_engage -- how deep the tube sits in the
// cap, hence how much skirt covers the lock screw's pilot -- and nothing else.
// The wedge that takes up the remaining play is the DEEP wall, ramped below.
module bayonet_slot() {
    h = lug_h + slot_slack;
    r0 = tube_od/2 + cap_fit/2 - e;
    r1 = tube_od/2 + lug_r + slot_slack;
    // Where the pocket stops being full height and starts closing. Without the
    // ramp both features run the whole pocket, exactly as before.
    a_ramp = ramp ? ramp_a : pocket_a0;
    // axial entry, open to the mouth
    rotate_extrude(angle=entry_arc)
        translate([r0, -e]) square([r1 - r0, chan_top + e]);
    // Circumferential run, one detent deeper than the locked position. It stops
    // at the ramp: past that the ceiling is BELOW the run's, and sweeping the
    // run through the ramp region would open the ceiling straight back up --
    // silently deleting the wedge while every part still rendered as a solid.
    rotate([0, 0, a_ramp])
        rotate_extrude(angle=entry_arc - a_ramp)
            translate([r0, pocket_z + detent]) square([r1 - r0, h]);
    // The free pocket: full depth and full height, so the lug can drop in.
    rotate([0, 0, a_ramp])
        rotate_extrude(angle=pocket_a1 - a_ramp)
            translate([r0, pocket_z]) square([r1 - r0, h + detent]);
    // The wedge. Floor stays at pocket_z -- the pull-out face is untouched --
    // and the deep wall walks down toward the lug over ramp_deg.
    if (ramp) {
        step = ramp_deg/ramp_steps;
        for (i = [0:ramp_steps-1]) {
            // i counts AWAY from the free pocket, toward pocket_a0. Height is
            // taken at the middle of each step, so the staircase straddles the
            // ideal ramp instead of sitting entirely above or below it.
            f = (i + 0.5)/ramp_steps;
            hgt = h + detent - ramp_close*f;
            // EACH STEP IS SWEPT TWO STEPS WIDE, backward into its taller
            // neighbour. A 0.02 deg overlap was tried first and CGAL threw
            // `e_below != SHalfedge_handle()` on the intersection -- at r=17 a
            // 0.02 deg overlap is 6 um, a sliver rather than a solid overlap.
            // The direction is the load-bearing part: extending BACKWARD is
            // free, because the union of the cutters takes the taller of the
            // two and the taller one is already there. Extending FORWARD would
            // hold the ceiling up into the next step and quietly flatten the
            // ramp while every part still rendered as a closed solid.
            rotate([0, 0, a_ramp - (i + 1)*step])
                rotate_extrude(angle=2*step)
                    translate([r0, pocket_z]) square([r1 - r0, hgt]);
        }
    }
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
                        cylinder(d=groove_root_drawn, h=groove_w + 2*e);
                }
            // the cable passage through the spigot
            translate([0, 0, cap_bore_depth - spigot_len - e])
                cylinder(d=spigot_id, h=spigot_len + 2*e);
            // clearance for the gland's thread; its nut lands on the inside
            translate([0, 0, cap_bore_depth - e])
                cylinder(d=gland_hole_d, h=cap_end_t + 2*e);
            // The gland's seal notch, in the OUTER face, cut inward. Sits
            // entirely outside the thread's major diameter, so the tapped
            // length stays the full cap_end_t.
            translate([0, 0, cap_h - gland_notch_depth])
                difference() {
                    cylinder(d=gland_notch_od, h=gland_notch_depth + e);
                    translate([0, 0, -e])
                        cylinder(d=gland_notch_id, h=gland_notch_depth + 3*e);
                }
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
