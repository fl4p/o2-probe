# PCB capture experience and reusable lessons

## Outcome

The Rev-A PCB is a schematic-linked, electrically complete four-layer KiCad
board released for bare-board first articles. The accepted 106-footprint
schematic transfers without parity errors. KiCad reports 0 errors, 0
unconnected items, and 0 parity issues. The 29 courtyard pairs are locked
manual-assembly exceptions and silkscreen is not exported.
`audit_pcb.py --calibrate` rejects 22/22 known-bad variants.

## 2026-08-23 fabrication corrective pass

- Move U7 to the potted side immediately behind the dam. CELL_RE is now one
  9.652 mm F.Cu segment with no via or test point.
- Extend the low-impedance guard-replica net into a continuous F.Cu enclosure
  around the long CELL_RE run.
- Reject the entire two-TMP117 thermal-barrier concept. The original horizontal
  slots did not isolate the sensor from the heater in the claimed gradient,
  and a remote gas-reference sensor did not measure membrane temperature.
- Remove U13/C22/R30/TP7 and the obsolete sensor-isolation slot concept. This
  was initially applied too broadly by also removing the transverse boundary
  slots; the 2026-08-24 correction below restores those two distinct features.
- Shorten the board to 20 × 107 mm and move the membrane heater to J5: four
  paste-free front/back lands for a hand-soldered metal carrier ring. Join all
  lands in PCB copper so the ring is not an electrical jumper.
- Put the one fitted TMP117 at local `(10,102)` near the ring, keep the SHT45
  for RH/dew-point estimation, and retain BMP390/C23/C24 only as a DNP option.
- Route `HEATER_LOW` with ≥0.80 mm B.Cu; segregate I²C/gate/PWM corridors and
  keep open vias out of fitted U10/U12 pads.
- Replace the illustration-derived round SGX pilot with a 3 × 6 mm gasward
  first-article NPTH slot while retaining the official Issue 2 body/pin geometry.
- Resynchronise placed footprints from authoritative libraries and
  enable every KiCad DRC category. Route endpoint and dangling-stub warnings
  were corrected, not suppressed.
- Generate and independently inspect the Gerber/Excellon ZIP with `make_fab.py`.
- Audit the exact outer contour, one continuous GND zone, all four J5 lands,
  two stitch vias, wide heater copper, and absence of obsolete nets.

## 2026-08-24 thermal-break slot correction

- “Remove the slots” was interpreted too broadly. The rejected geometry was
  the old second-sensor isolation concept; it did not authorize deleting the
  two transverse boundary slots. Record slot function, axis, datum, finished
  size, residual webs/neck, and which thermal regions it separates as separate
  requirements so one shorthand instruction cannot collapse them together.
- Restore two horizontal 5.5 × 1.0 mm capsules at absolute y=134.0 mm, centred
  at x=103.75 and x=116.25 mm. They leave 1.0 mm side-edge webs and a 7.0 mm
  centre neck. They are a partial axial thermal break between potted body and
  gas-side tip, not an isolated heated island and not a second-sensor feature.
- A coarse rectangular collision estimate falsely marked the original
  diagonal `/I2C_SCL` route as conflicting. The exact capsule contours show
  that it clears through the centre neck. Use exact routed-contour geometry
  plus KiCad DRC before ripping up accepted copper near slots.
- Lock the two closed contours in the board audit and independently parse the
  Edge.Cuts Gerber in the fabrication builder. The fab note must explicitly
  require both internal contours to be routed; a clean outer profile alone is
  insufficient release evidence.
- Inventory every track, via, pad, and plane crossing at the barrier datum.
  This board deliberately retains 12 track segments, two vias, no footprint
  pads, and the clipped In2 GND region. The audit rejects added crossings so
  later routing cannot silently erase the thermal intent.

## 2026-08-23 density and MCU-cluster pass

- Treat user-authored footprint moves as design input, then snap them to exact
  generator coordinates before routing. A plausible interactive drag is not a
  reproducible placement.
- Move U6 from `(12.5,49)` to the right-side lane at `(14.5,44.5)` and rotate
  it 180 degrees. This puts it beside U5, faces its RS-485 side toward the
  transceiver, and opens the centre-left lane for SWD and low-speed fanout.
- Move C8 to `(18,37.5)` so the compact U6 courtyard does not overlap the
  analog-LDO output bypass. Density is bounded by courtyard and rework access,
  not by drawing component bodies until they almost touch.
- Do not move a routed fine-pitch IC on top of old copper. First prove the new
  placement has no courtyard/edge conflict, remove every track or via entering
  its new routing envelope, lock accepted copper outside that envelope, and
  reroute only the disturbed connectivity.
- An endpoint-only rectangle test is insufficient: a long segment can cross
  the moved footprint while both endpoints remain outside. Use segment
  bounding-box intersection for the first cut, then require a copper-clean seed
  DRC before invoking a router.
- The first compact-routing experiment was rejected before promotion: U6 was
  still too far left, old 3V3A fragments crossed the new courtyard, and an
  over-threaded exploratory router run consumed excessive memory. Re-cut the
  complete envelope and use a bounded low-thread run instead.
- Preserve the guarded CELL_RE path, analog placement, continuous GND plane,
  and completed heated-ring tip as locked scaffolding. Compaction never grants
  a router permission to rewrite those accepted structures.
- When package-edge congestion comes from arbitrary GPIO choices, revisit the
  pin map before forcing long routes. Moving `RS485_DE` from PA1 to PC6 grouped
  the transceiver controls, while moving `VA_MON` from PA0 to ADC-capable PA7
  removed two trapped right-edge routes. Treat the schematic, firmware pin
  map, and PCB pad nets as one atomic change.
- The accepted density pass used KRT commit
  `1dd393eaaa895fd83d3acb40e603969f36542e0e`. Withdraw the complete digital
  cluster envelope, lock everything outside it, route power plus RS-485 A/B at
  0.18 mm with 0.45/0.20 mm vias, then route signals at 0.09 mm with
  0.25/0.15 mm vias. This two-stage run closed 69 disconnected pads without
  disturbing the guarded AFE or heated tip.
- Copy the matching `.kicad_pro` beside a candidate *before* invoking pcbnew's
  zone filler. A same-stem project copied only after filling caused the In2
  plane to ignore the 0.25 mm copper-to-edge rule and created nine false
  hole-clearance errors around NPTHs.
- A KRT “zero disconnected pads” result can still import one-grid-cell gaps,
  dangling tail chains, off-centre via endpoints, and exact same-net duplicate
  segments. Refill with the matching project, run KiCad DRC, recenter endpoints,
  prune the full dead branch rather than only its first segment, and explicitly
  inventory duplicate segment/via geometry.
- A bounded Freerouting attempt was stopped after it stalled on the compact
  bundle. Preserve the clean seed and switch tools instead of letting a long
  run monopolize memory without a completed session artifact.

## 2026-08-22 KiCadRoutingTools completion pass

- Run KiCadRoutingTools (KRT) before falling back to a general Specctra
  autorouter. KRT understood KiCad's four-layer board and exact filled-zone
  geometry, and its per-net targeting made controlled rip-up possible.
- Treat KiCad's final DRC as authoritative. KRT's internal “connected” score
  is a search result, not an acceptance gate. Every candidate was copied next
  to a matching `o2-probe.kicad_pro`, zones were refilled, and KiCad recomputed
  connectivity, clearance, holes, and schematic parity.
- A candidate must have the same basename as its `.kicad_pro` during CLI DRC.
  Grading `candidate.kicad_pcb` beside `o2-probe.kicad_pro` silently uses
  different defaults and produces false design-rule conclusions.
- Reserve escape channels during placement. Opposite-side passives around U7
  boxed the fine-pitch 3V3A pad. Moving R33/C28 and escaping the pad along its
  axis before the via made the route solvable.
- Passive orientation is routing data. C9 initially faced its GND pad toward
  R21's wiper pad; rotating it 180 degrees turned an impossible crossing into
  a short direct bottom-layer connection.
- Limit rip-up authority to named blockers. The successful closure fixed
  `/3V3A` and `/VREF_WIPER`, then withdrew only `/I2C_SCL`, `/I2C_SDA`,
  `/VIN_MON`, `/AFE_VOUT`, and `/ADC_VREF_MON`. KRT rerouted those five nets
  while every unrelated completed net remained protected.
- Reject router regressions with an improvement gate. KRT's reconciliation and
  multi-point phase can reopen previously connected nets; preserve accepted
  checkpoints and compare gained/lost connectivity before promotion.
- Route signal escapes before repairing planes. Router-created GND fragments
  were stripped, signals were closed, then `repair_planes.py` rebuilt GND taps.
- Plane repair's in-memory oracle can be newer than its first saved output.
  Reopen the written board, refill zones, and save again before DRC; otherwise
  stale fill appears to short every new through-via to the plane.
- Use an explicit advanced-fabrication floor consistently. This board permits
  0.09 mm minimum tracks, 0.25/0.15 mm vias, and 0.05 mm annular rings. These
  limits must be quoted to the fabricator, never inferred from emergency router
  geometry.
- Treat an enlarged NPTH or slot as a copper change. Introducing the SGX rear
  flow slot invalidated nearby `/I2C_SDA` and `/3V3D` routes
  even though the footprint pads did not move. Query KiCad DRC for every item
  intersecting the new hole-clearance envelope, withdraw only those nets, and
  reroute them before promotion.
- Do not infer an undimensioned gas-port diameter from a drawing. Preserve the
  official pin/body geometry, use a clearly labelled first-article flow/fit
  feature, and require a physical sample before production qualification.
- KRT may add a redundant same-net loop that boxes an adjacent pad. Remove the
  loop and reroute the interacting bundle; do not solve a fine-pitch escape by
  placing an unqualified open via inside a 0.30 mm sensor pad.
- KRT can also leave a microscopic same-net segment on an internal plane. KiCad
  correctly reports no connectivity or clearance error for that redundant
  copper, so the release audit must independently reject routed GND segments on
  the dedicated In2 plane and exact duplicate tracks/vias. The compact pass left
  one 0.0158 mm In2 `/GND` remnant; deleting it preserved 0/0/0 DRC and restored
  the intended zone-only plane.
- A generic process-width check does not protect current paths. KRT left one
  0.778 mm diagonal on `/+12V_SW` at the 0.09 mm signal floor between two
  0.18 mm power segments. KiCad DRC was correctly clean, but that diagonal was
  the series bottleneck. Widen it and calibrate an explicit per-net 0.18 mm
  switched-supply floor rather than relying on the board-wide minimum.
- Treat the KiCad CLI parity section as corroboration, not the sole oracle.
  KiCad 10.0.5 can report zero parity findings after a footprint is deleted.
  Export the schematic XML fresh, compare its complete reference set and every
  numbered pad net against the PCB, and calibrate both a footprint deletion and
  a pad-net mutation so that the independent contract is proven to fail closed.

## Lessons worth reusing

- Treat schematic-to-board parity as an exact string-and-instance contract.
  KiCad's generated root-sheet net names include the leading `/`; removing it
  made every connected pad look wrong even though the logical names looked the
  same.  Footprint `KIID_PATH`, DNP flags, BOM flags, and custom symbol fields
  also participate in parity.
- If a future revision genuinely needs a routed slot, do not model it as a
  helper footprint. Closed Edge.Cuts contours are the board-native form and
  must be audited by exact primitive and datum. This revision has two.
- A thermal slot is load-bearing only when it interrupts the actual heat-flow
  path. Lock its orientation, residual neck/web widths, sensor/heater sides,
  and every copper-plane crossing. A slot parallel to the gradient, or a solid
  plane spanning the intended barrier, is decorative geometry.
- Preserve KiCad's one-pad `unconnected-(...)` pseudo-nets on the saved board
  for parity, but remove them only from the temporary Specctra export.  Older
  Freerouting versions attempt to route them and can dereference a nonexistent
  target shape.
- Bound autorouter work.  Freerouting 2.1 repeatedly threw geometry exceptions
  and did not write a session when interrupted.  Freerouting 2.3 from the
  packaged macOS runtime was stable enough to finish; `-mp 8` gave a deterministic
  2m19s run and wrote a usable session.  Interrupting a longer run lost the best
  in-memory solution, so use short completed runs and preserve each `.ses`.
- A low autorouter unrouted count is not a quality gate.  Import the session,
  refill zones, and let KiCad recompute clearance, shorts, thermal starvation,
  and schematic parity.  The router's eight internal violations became a more
  actionable KiCad report.
- Clear placement-origin copper errors before routing. The accepted seed had
  zero shorts, ordinary clearance, hole, edge, and mask violations. Courtyard
  overlaps remain a separate manual-assembly review item.
- A component grid is not functional placement.  In this board, C17 and the
  reference/RS-485 support parts landed tens of millimetres from the IC pins
  they serve.  The autorouter could make the picture look busy but could not
  create a legitimate via-free guarded AFE escape.  Cluster support components
  around their owning IC before the first route and assert maximum critical-net
  Manhattan distances in the generator.
- Do not force a local DRC fix when the corridor is globally occupied. Moving
  several mechanically constrained traces by only tens of micrometres created real shorts
  or clearance failures to the I2C bundle.  The correct fix is to rip up and
  reroute the whole interacting bundle; restoring the clean checkpoint is more
  honest than trading one named error for a less visible one.
- Re-exporting an already routed board to Specctra can change the router's view
  of connectivity.  This board re-opened as 92 unrouted items, and four bounded
  passes finished worse at 53--55.  Always compare the imported result with the
  preserved KiCad checkpoint and reject regressions.
- Solid zone attachment can be the correct thermal fix for reflowed SMT return
  pads on a narrow board.  It removed nine one-spoke islands here without
  changing parity or introducing copper errors.  Record that assembly/process
  rationale; do not merely lower the required spoke count.
- Dense narrow boards punish “logical” grid placement.  The cable-relief lands,
  Micro-Fit connector, Tag-Connect holes, 2512 heaters, and component courtyards
  consume more axial space than their pad centres imply.  Check courtyard and
  hole envelopes before routing, especially on both sides of through-hole parts.
- Keep the mechanical source deterministic. The 20 × 107 mm R2 outline, one
  continuous In2 zone, pot datum, cell/aperture, tip placement, and J5 geometry
  are exact assertions in `audit_pcb.py`, so electrical rearrangement cannot
  silently move an enclosure interface.
- Ground planes help connectivity but are not a substitute for deliberate
  return or thermal design. The final routing still needs a manual buck hot-loop,
  cable-entry surge return, heater return, quiet analogue return, and via-stitch
  review.  Plane fill should be repeated only after those current paths are
  deliberately shaped.
- A driven guard is a topology, not decorative copper. Audit the low-impedance
  source, its connected route/via, the guard zone, the enclosed sensitive run,
  and the absence of vias or test-mask openings on the sensitive node.
- Keep fabrication gates visible in the same status record as DRC.  Zero parity
  does not validate the SGX sample/rear port, connector tube chord, ring joint,
  membrane temperature, exact passive stress ratings, or VREF stability.

## Reproduction sequence

```sh
python3 make_fab.py
```

That command applies/verifies project rules, runs ERC and both audits, records
error and warning DRC JSON, plots the exact layer set, validates Gerber X2
functions, the exact R2 outer contour, both thermal-break slot contours, and
routed SGX NPTH Excellon data, writes checksums, and builds
`fab/o2-probe-rev-a-fab.zip`.
