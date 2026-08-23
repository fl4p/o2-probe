# PCB capture experience and reusable lessons

## Outcome

The Rev-A PCB is a schematic-linked, electrically complete four-layer KiCad
board released for bare-board first articles. The accepted 109-footprint
schematic transfers without parity errors. KiCad reports 0 errors, 0
unconnected items, and 0 parity issues; all placed/library mismatches are gone.
The 28 courtyard pairs are locked manual-assembly exceptions and silkscreen is
not exported. `audit_pcb.py --calibrate` rejects 6/6 known-bad variants.

## 2026-08-23 fabrication corrective pass

- Move U7 to the potted side immediately behind the dam. CELL_RE is now one
  9.652 mm F.Cu segment with no via or test point.
- Extend the low-impedance guard-replica net into a continuous F.Cu enclosure
  around the long CELL_RE run.
- Split In2 GND across the 3.5 mm potting transition and reconnect it with one
  deliberate 0.25 mm bridge at the board edge.
- Replace the illustration-derived round SGX pilot with a 3 × 6 mm gasward
  first-article NPTH slot while retaining the official Issue 2 body/pin geometry.
- Resynchronise all 109 placed footprints from authoritative libraries and
  enable every KiCad DRC category. Route endpoint and dangling-stub warnings
  were corrected, not suppressed.
- Generate and independently inspect the Gerber/Excellon ZIP with `make_fab.py`.

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
- KRT may add a redundant same-net loop that boxes an adjacent pad. At U13,
  removing a three-segment redundant SDA loop freed the centre 3V3D dogbone;
  the exposed-pad return was locally doglegged, then KRT rejoined the two SDA
  islands. This avoided an unreliable via-in-pad on a 0.30 mm TMP117 pad.

## Lessons worth reusing

- Treat schematic-to-board parity as an exact string-and-instance contract.
  KiCad's generated root-sheet net names include the leading `/`; removing it
  made every connected pad look wrong even though the logical names looked the
  same.  Footprint `KIID_PATH`, DNP flags, BOM flags, and custom symbol fields
  also participate in parity.
- Do not model routed slots as helper footprints in the final board.  They show
  up as extra schematic parts under `--schematic-parity`.  Closed Edge.Cuts
  capsules are the correct board-native representation and can be audited by
  count and datum.
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
- Do not force a local DRC fix when the corridor is globally occupied.  Moving
  the four slot-adjacent traces by only tens of micrometres created real shorts
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
- Keep the mechanical source deterministic.  The outer 20 x 125 mm R2 outline,
  pot datum, cell centre, aperture, and six slots are assertions in
  `audit_pcb.py`, so a future electrical rearrangement cannot silently move a
  controlled enclosure interface.
- Ground planes help connectivity but are not a substitute for deliberate
  return design.  The final routing pass still needs a manual buck hot-loop,
  cable-entry surge return, heater return, quiet analogue return, and via-stitch
  review.  Plane fill should be repeated only after those current paths are
  deliberately shaped.
- A driven guard is a topology, not decorative copper. Audit the low-impedance
  source, its connected route/via, the guard zone, the enclosed sensitive run,
  and the absence of vias or test-mask openings on the sensitive node.
- Keep fabrication gates visible in the same status record as DRC.  Zero parity
  does not validate the SGX sample footprint/rear port, connector tube chord,
  potting dam, slot thermal neck, exact passive stress ratings, or VREF stability.

## Reproduction sequence

```sh
python3 make_fab.py
```

That command applies/verifies project rules, runs ERC and both audits, records
error and warning DRC JSON, plots the exact layer set, validates Gerber X2
functions and outline dimensions, validates routed NPTH Excellon data, writes
checksums, and builds `fab/o2-probe-rev-a-fab.zip`.
