# Accepted routing provenance

The routed upstream board remains derived from bounded per-net
KiCadRoutingTools passes. The earlier base used commit
`81a3c1930892cf9170fd15f8d9e61327d8420596`; the dense MCU-cluster pass used
commit `1dd393eaaa895fd83d3acb40e603969f36542e0e`. The heated-ring revision is a
deterministic local migration and route owned by `adopt_heated_ring_tip.py` and
`route_heated_ring_tip.py`; `gen_pcb.py` owns final placement and outline while
`gen_sch.py` owns the MCU pin map. `thermal_design.py` owns all four thermal
slots, the all-layer pour gap, heated-island spreader, and minimal GND bridge.
`route_thermal_barrier.py` owns the local crossings. `repair_guard_fill.py`
owns the four guard stitch vias and ten short In1/B.Cu links added after the
routed board exists. `adopt_tip_reposition.py` owns the later U10/C23 compaction,
six local U10 fan-outs, and the SGX-aperture/heater-feed shift.
`adopt_testpoint_silk.py` applies `gen_pcb.py`'s test-point labels to the routed
board; it touches silkscreen only, adds no copper and no DRC finding, and shares
`gen_pcb.TESTPOINT_LABELS` with the generator rather than restating it.

The release uses a 0.09 mm track floor, 0.15 mm clearance, 0.20 mm copper-to-
edge clearance, and 0.25/0.15 mm advanced vias. Tip routing is separated by
function:

- `HEATER_LOW` uses at least 0.80 mm B.Cu from RH1/RH2 and Q2 to the ring, plus
  a solid B.Cu spreader covering the gas-side island.
- J5's two through-plated castellated slots join every copper layer and are
  connected by 0.80 mm B.Cu, so the metal ring is not an electrical jumper.
- The HEATER_PWM In1 tail is held inboard of the right J5 castellation; ordinary
  tracks retain the global board-edge clearance and enter J5 from inside its
  pads.
- I²C lateral fanout uses separated In1 corridors with short F.Cu escapes.
- U10 is centred at local `(10,102.525)`; its old-row 3V3D/SDA fragments are
  removed so no routed copper enters the moved exposed-pad land.
- The heater PWM follows the right edge and crosses below the sensor routes.
- The 0.40 mm In1 `+12V_SW` feed detours at absolute y=148.80 mm around the
  gas-side end of U11's shifted NPTH slot. It may not return to the former
  y=142.50 mm cross-slot route.
- A full-width, all-four-layer rule area prevents zone fill across absolute
  y=133…135 mm. In2 GND therefore fills as two regions and remains electrically
  continuous only through one exact 0.15 mm three-segment jog in the left edge
  web; ground dogbones keep process vias out of fitted U10/U12 pads.
- The expanded slots leave a 5.0 mm centre neck. The accepted KiCad shove
  result reroutes `/I2C_SCL`, `/I2C_SDA`, `CELL_WE`, `3V3D`, `HEATER_PWM`,
  `VA_MON`, `+12V_SW`, and the guard stitch through the reduced corridors.
  Exact contour DRC, not a coarse rectangular bounding-box estimate, is the
  clearance oracle.
- The two 0.8 × 16.0 mm side slots at absolute x=101.2/118.8 mm have no track,
  via, or pad crossings. Their former edge-lane routes move into the central
  island, and the B.Cu heater-spreader fill preserves both routed voids.
- The exact F.Cu `GUARD_REPLICA` source zone spans the centre neck around
  CELL_RE, as the quad `(109.25,131.75) (112.15,131.75) (114.00,141.65)
  (111.10,141.65)`. The bottom edge follows CELL_RE east to the corrected RE
  land and stays clear of the WE land at `(110.00,141.00)`, whose 1.6 mm
  circular pad plus 0.15 mm clearance reaches x=110.95. Because CELL_RE and
  nearby signals fragment the pour, the release retains three physically
  connected saved fill regions using four guard vias and ten short In1/B.Cu
  links. The barrier audit locks actual filled copper
  together with the two In2 fill regions, B.Cu heater spreader, 14 crossing
  track segments, two crossing vias, zero pads, and zero copper graphics. The
  side-slot inventory separately locks zero track, via, and pad crossings.
- CELL_RE provenance. The run is fixed by the SGX land pattern, which was
  corrected on 2026-09-01: DS-0637 Issue 2 (PDF page 2, the sheet numbered
  Page 1/1) shows a BOTTOM view whose leaders land Counter on the left pin,
  Working on the CENTRE pin and Reference on the right pin. Issue 1 carries the
  same figure and agrees. The page 1 prose "Counter, Reference and Working" is
  not the pin order and was the original defect. With Working central and the
  180-degree insertion the footprint uses, CELL_RE reaches the east land, so
  `adopt_cell_pinout_fix.py` re-aims the single F.Cu segment, moves the CELL_WE
  In1 tail onto the centre land (it no longer passes under CELL_RE; nearest
  approach 2.327 mm), and re-tapers the guard. Two conflicts had to move rather
  than be routed around, because CELL_RE is locked to one straight via-free
  segment: `/I2C_SDA` and the `/+12V_SW` In1-to-B.Cu via at `(111.30,132.30)`.
  Both were shorts, not near misses. The CELL_RE centreline reaches x=111.50 at
  y=134.52, inside SDA's old 133.50-135.00 leg, and x=111.80 at y=136.39,
  inside its old 135.30-139.50 leg; at y=135.30, where the two are merely
  close, the edge-to-edge gap is 0.054 mm against a 0.15 mm rule. SDA now crosses the barrier
  on In1 at x=112.15 and descends the east side; its closest approach to
  CELL_RE is 0.350 mm in plane on the adjacent layer, across the 0.1 mm
  prepreg. The +12V_SW via slid along its own 45-degree line to
  `(112.10,131.50)`, leaving the point where that net crosses under CELL_RE
  unchanged. Nearest foreign copper to CELL_RE is now the `/HEATER_PWM` F.Cu
  turn at 0.252 mm, which is legal but is the closest a switching net comes to
  the reference node and sits in the ungurded pour gap.
- U10's exposed pad terminates at TP6 through a via inside the large test land.

The compact MCU pass treats the right-side U6/C8 placement as generator-owned.
All copper disturbed by that move is withdrawn as a complete net set before
rerouting; the AFE, CELL_RE guard, and heated-ring tip remain protected. A
partial-fragment reroute is forbidden because it produced normalization loops
and stranded same-net fragments during the exploratory pass.

The accepted compact pass first routes power and RS-485 A/B at 0.18 mm with
0.45/0.20 mm vias, then signals at 0.09 mm with 0.25/0.15 mm vias. It remaps
`RS485_DE` to PC6 and `VA_MON` to PA7/ADC_IN7, and strips every dangling
fragment and exact same-net duplicate. The subsequent thermal revision
intentionally splits the In2 GND pour at the barrier and reconnects it with one
narrow track.

Generated routing is never acceptance evidence. Every saved board is refilled
and checked by KiCad DRC, `audit_pcb.py --calibrate`, and `make_fab.py`.

## Rev B, four layers — superseded

The four-layer Rev-B route below closed 61/61 nets and is kept for its
findings, not as a target. Fab moved the board to **two layers** on 2026-09-05
and everything after this section describes that board.

## Rev B: the regenerated board, routed 2026-09-05

Rev A above is history. The Rev-B placement is a different board -- the cell
moved into the gas island as U11, U7 turned, the fork tip replaced the
castellated ring -- so none of the `adopt_*` migrations above apply to it, and
their absolute coordinates describe copper that no longer exists.

Rev B splits ownership three ways instead of by migration script:

- **`gen_pcb.py`** owns placement, outline, mechanical features and, through
  `thermal_design.py`, the barrier rule area, the B.Cu heater spreader and the
  GND bridge.
- **`critical_routes.py`** (new) owns the In2 ground plane, the CELL_RE via
  keepout, and the copper a router is not allowed to invent: CELL_RE, CELL_WE's
  U7 leg, the RH1/RH2 -> Q2 -> J5 heater path at 0.80 mm, and the fork-tip layer
  joins. Everything it emits is emitted **locked**, so KRT routes around it.
- **KiCadRoutingTools** owns the remaining 59 nets.

`repair_krt_endpoints.py` (new) replaces `repair_route_endpoints.py`, which was
keyed by track UUID against one accepted Rev-A route and cannot survive a
re-route. The new one is driven by the DRC report and keyed by geometry.

### The accepted pass

    python3 py_router/route.py <board> --overwrite \
      --track-width 0.18 --clearance 0.15 --via-size 0.45 --via-drill 0.25 \
      --fab-overrides krt_fab_floor.txt --no-fix-drc-settings \
      --rip-existing-nets '*' \
      --power-nets HEATER_LOW +12V_HTR +12V_SW +12V_FUSED +12V_RAW +5V 3V3D GND \
      --power-nets-widths 0.8 0.8 0.5 0.5 0.5 0.4 0.4 0.5

Result: **61/61 nets, 0 unconnected items**, 197 vias, 1793 track segments,
minimum track width 0.09 mm, minimum clearance 0.15 mm. In2 GND pours
1806.5 mm2; the B.Cu heater spreader pours 311.2 mm2. CELL_RE is a single
F.Cu net with **no via on it anywhere**.

KiCad DRC after `repair_krt_endpoints.py`: **zero** clearance, shorting,
track-width, hole-clearance, copper-edge and unconnected findings. What remains
is 20 allowlisted courtyard overlaps (`ASSEMBLY-EXCEPTIONS.md`), 27 pre-existing
silkscreen findings, 6 `lib_footprint_issues` that are a library-path
configuration message rather than a board defect, 14
`track_not_centered_on_via` and 1 `track_dangling` that the repair deliberately
declines to touch.

### Two things the router had to be stopped from doing

**Routing below the board's own floor.** Invoked with `--clearance 0.15`, KRT
still emitted 46 segments at 0.0889 mm on `/3V3D`, `/I2C_SDA` and `/LMP_C2`,
**and then rewrote the project's Board Setup to match** -- `min_track_width`
0.09 -> 0.0889, `min_clearance` 0.15 -> 0.10 -- along with turning
`solder_mask_bridge`, `lib_footprint_issues`, `annular_width` and four other
severities to `ignore`. Every checker, KiCad's DRC included, then grades the
copper against the router's floor instead of the fab's. `krt_fab_floor.txt` plus
`--no-fix-drc-settings` pins it. Even so KRT still rewrote one key
(`min_hole_clearance` 0.20 -> 0.15), so **restore the project file from the
repository before running DRC on any KRT output**; the numbers above were
measured that way.

**Putting a via barrel in the reference node.** With CELL_RE authored and
locked but its U4 leg left to the router, KRT dropped a through via at
(11.00, 82.00) -- in the middle of the protected run -- took the leg down to
B.Cu, snaked it under U7 and brought it back up at (4.00, 76.00). Two barrels
through the laminate in the electrometer input, and no rule on the board scores
it, because no rule scores leakage. `CELL_RE_VIA_KEEPOUT` forbids vias on every
layer in a corridor 0.4 mm either side of the run; with it in place the router
finds an all-F.Cu path for the leg and the board still closes completely.

### Still open

- **The `GUARD_REPLICA` driven guard does not exist on this revision.** On Rev A
  it was a separate migration because the barrier rule area and CELL_RE itself
  split the pour into four regions that each need their own feed, and every feed
  competes for In1 in the same 5 mm neck the signals cross. CELL_RE is presently
  an unguarded run, and `GUARD_REPLICA` is a two-pad net driving nothing.
- **U4 is in the wrong place.** The RE follower and guard buffer sits at
  (3.0, 77.0), about 16 mm from the cell and on the far side of U7, so both
  electrometer nodes make a long run past a congested pad row to reach it. The
  via keepout makes the result legal; it does not make the placement right.
  Moving U4 next to U11 is a floorplan change and Fab's call.
- The fork finger width is still frozen pending the printed-neck-bore
  measurement (`RING-PCB.md` 5.1).
- `audit_pcb.py` still encodes Rev-A absolute coordinates and does not describe
  this board.


## Rev B on two layers — 2026-09-05

**Status: not routed. 244 of 265 pad-pairs connected; 21 links open across 15
nets.** No clearance, shorting, track-width, hole-to-hole or copper-edge
violations; all 57 authored critical items present and locked; both ground
pours stitched and connected. The board is in the session scratch, not
promoted: an incomplete route is not a better tracked artefact than the
four-layer one it would replace, and the repository is deliberately left with
the generators describing two layers and `o2-probe.kicad_pcb` still holding the
four-layer route. That inconsistency is recorded rather than hidden.

### What changed for two layers

- Layer count is a board property nothing restates: `thermal_design.copper_layers()`
  derives it, and the barrier rule area, CELL_RE keepout and ground pours all
  follow. The literal `(F_Cu, In1_Cu, In2_Cu, B_Cu)` tuples that were there
  before would have kept writing onto layers that no longer exist, silently,
  because an `LSET` accepts a disabled layer id.
- Ground was one In2 plane; it is now poured on F.Cu and B.Cu, solid-connected,
  yielding to the heater spreader by zone priority. **22 stitch vias** tie the
  two pours together — without them KiCad reported them as unconnected zones on
  a fully routed board, a ground plane in name only. Cable side only: gas-side
  B.Cu is the spreader, so ground on the island lives on F.Cu alone and reaches
  the cable side through the barrier bridge.
- The stack is 1.0 mm, 1 oz outer, 0.93 mm FR-4 core, ENIG — and it is
  *written* now, which it never was. `gen_pcb.py` emitted no stackup at all;
  Rev A only had one because it was set once in the GUI and never regenerated.
- `CELL_RE` has a driven guard for the first time: two F.Cu rails 0.275 mm
  either side, tied under the run on B.Cu at both ends, fed once from R40. A
  rule area blocks zone *fill*, not tracks, so rails are immune to the
  fragmentation that made Rev A's pour need a whole migration script.

### Standing rule for every KiCadRoutingTools entry point

**Pass `--fab-overrides krt_fab_floor.txt` and `--no-fix-drc-settings` to every
tool that writes a board, and restore `o2-probe.kicad_pro` from the repository
before running DRC on the output.** This is not per-tool advice; three separate
entry points did it during this session:

- `route.py`, invoked with `--clearance 0.15`, emitted 46 segments at 0.0889 mm
  and rewrote Board Setup to match — `min_track_width` 0.09 → 0.0889,
  `min_clearance` 0.15 → 0.10 — plus seven DRC severities set to `ignore`.
- `route.py` again, even with `--no-fix-drc-settings`, rewrote
  `min_hole_clearance` 0.20 → 0.15.
- `repair_planes.py` ignored `--clearance 0.25` outright, used 0.127 mm, and
  rewrote `net_class[CELL_RE].clearance` 0.15 → 0.127.

Every checker, KiCad's own DRC included, then grades the copper against the
router's floor instead of the fab's.

### The custom rule the board needs, and why 0.15 mm is not enough

`o2-probe.kicad_dru` requires 0.25 mm from `CELL_RE` to any other track. The
board's ordinary clearance is a *manufacturing* number: it says two conductors
will not bridge and says nothing about current creeping between them across the
mask, and nothing in KiCad's default rules scores leakage. On the best route
before this rule existed, `/3V3D` sat 0.17 mm from the reference node,
`/CELL_CE_DRV` 0.185 mm and `/3V3A` 0.215 mm — **eight violations of a rule
that did not exist, on a board with zero clearance violations**, against a node
budgeted for the LMP91000's ±900 pA.

Track-to-track only. CELL_RE arrives at U7 pin 13 on a 0.5 mm-pitch row where
the gap to pins 12 and 14 is 0.255 mm; a pad-inclusive rule at 0.25 would pass
by 5 µm today and fail on any library revision. The scope also matches the
subset KRT parses, so the **router** honours it — its log prices the net — and
first-pass intrusions went from eight to one.

### What is still open, and what it is not

The 21 links are concentrated in the AFE band, y≈64–85: `/+12V_SW`,
`/ADC_AFE_VOUT`, `/ADC_DRDY`, `/ADC_VREF_MON`, `/AFE_MENB`, `/AFE_VOUT`,
`/LMP_C1`, `/LMP_C2`, `/VREF_SHUNT`, `/VREF_TRIM`, `/WE_BUF`, `/CE_MON`, plus
four I²C links at the tip and one ground stitch. The 30 dangling vias are the
stranded ends of those same links, not a separate defect.

It is **not** a router-effort problem and it is not a track-width problem:

- Six independent configurations plateaued between 18 and 21.
- 0.12 mm tracks with 0.35/0.15 vias were *worse* (33 open) than 0.18/0.45.
- Routing GND as an ordinary net with no pours was far worse (108 open); the
  pours are carrying ground, not obstructing.
- A rescue pass routing only the open nets, with every other routine net
  rippable, moved nothing.

Two of the plateau's causes were found and fixed, and both were self-inflicted,
which is the reason to be cautious about calling the remainder structural:

- CELL_WE's westward run sat under U7's gas-side pad row. U7's body is one
  large exposed pad, so pins 8–11 cannot cross the package; their only route is
  a via south of the row then north underneath on B.Cu — straight through that
  run. Four nets were open on that alone.
- U8 is a `Texas_RTE0016D` WQFN-16 on 0.5 mm pitch. Every signal pad must fan
  out sideways on F.Cu, and CELL_RE's leg at x=13.00 left its west pad row
  0.495 mm to escape into. Nine of the then-fifteen failing nets were U8 pads.
  Moving the leg to x=12.40 opened it to 1.095 mm.

### Open questions for the next pass

1. Whether the remaining 21 are a third self-inflicted wall or genuinely need
   re-floorplanning of the AFE block. The honest answer is that this has not
   been established — every previous plateau looked structural until the
   specific obstruction was found.
2. `make_fab.py` and `audit_pcb.py` both encode Rev-A geometry and layer lists
   and do not describe this board. `make_fab.py` additionally carries another
   session's uncommitted work.
3. The barrier conductance must be re-derived once routing closes
   (`thermal_barrier_conductance.py`); `THERMAL-BARRIER.md` carries a STALE
   marker until then.
4. The fork finger width is still frozen pending the printed-neck-bore
   measurement (`RING-PCB.md` §5.1).
