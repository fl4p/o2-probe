# Printing the body tube — ASA, prototype 1

Model: [`o2_probe_body_tube.scad`](o2_probe_body_tube.scad). Build:

    make body-tube

which writes `exports/body-tube.stl`, `body-cap.stl`, `body-dam.stl` and a
preview, gates `tube` and `cap` as single closed solids, and runs
[`tools/bayonet_check.py`](tools/bayonet_check.py) — a kinematic check on the
cap, not a mesh check. See "The bayonet" below for why that exists.

## What this is for

A **printed** body so the Rev-A board — the revision already at the fab,
unmodified, with **no heater ring** and **not potted** — can be buried now
instead of after the bought-tube-plus-potting route is qualified.

**No heater ring is not the same as no heater, and the difference matters here.**
The board carries **RH1/RH2, CRCW2512280RFKEG 280 R 1 W, two of them on the back
at (5, 96.5)** — 140 Ω effective, so **≈1.03 W at 12 V**, which is the full
heater budget `PLAN.md` sizes. What is missing is J5's ring, the dry-side metal
carrier that was supposed to take that heat to the membrane, and which
`HEATED-SPREADER.md` §0 records as orphaned by the end-window head.

So prototype 1 puts about a watt into the head cavity with **nothing to aim it**.
It warms the gas, the board and the cell rather than the membrane face — which
is the one surface `CONDENSATION-MODEL.md` says has to stay above the dew point.
Treat the heater in this build as a chamber warmer and a source of measurement
data (`RING-PCB.md` §4: v1's first job is to measure `h` and η *in situ*), not as
the condensation control the design eventually needs.

`MEMBRANE.md`, *Enclosure material: printed ASA* (2026-09-02), decided a bought
tube for the production body and allowed exactly this in the same breath: *"A
fully printed body is permitted for prototypes."* So this is sanctioned, not a
departure — but the same section attaches a release gate to it, and this part
does **not** pass that gate and is not offered as passing it.

It is dimensionally the production body: **Ø32 OD**, the section `PLAN.md` names
and the section `o2_probe_head_end.scad`'s socket was cut for. The head does not
change. That is deliberate — the prototype and the production body are the same
joint, so nothing learned here has to be re-learned.

## The three things it gives up, with numbers

**1. Gas volume — this is the big one.** The head cavity is held to ≤ 5.0 cm³
because that budget is what makes the response measurement mean anything
(`PROTOTYPE-RESPONSE.md`). Potting is what stops the rest of the tube joining it.
Unpotted:

| | connected volume | vs the 5.0 cm³ budget |
|---|---:|---:|
| head cavity alone | 4.92 cm³ | 0.98× |
| **+ open tube, no dam** | **75.4 cm³** | **15.1×** |
| + tube with the dam fitted | 18.1 cm³ | 3.6× |

(The head cavity is measured off the `cavity` mesh; the tube figures are the
model's own echo, 57.7 cm³ alongside the board plus 12.8 cm³ of cable tail. The
table read 4.84 / 63.8 / 18.3 while the board was 1.0 mm and the tail was not
counted — both are fixed, and the open-tube number got *worse*, not better.)

Without the dam, the step response you measure is the **tube's** time constant,
not the membrane's. The dam is a two-piece printed disc that clamps around the
board and drops the open bore from 581 mm² to 184 mm² of slit; it is a
restrictor, not a seal, and the table above credits it with nothing more.

**2. The wall is not gastight, and here that is a measurement error.**
`~/dev/ee/p1p/doc/gastight-and-watertight.md` is unambiguous: *"Watertight is a
settings problem. Gastight is not."* Every published FDM leak rate lands in the
leaky class — at 6 mm walls, at 0.09 mm layers, with epoxy infusion. For a probe
whose entire output is a gas concentration, whatever the wall passes is **air**,
and air reads 20.9 % O₂.

So: **treat this prototype's absolute O₂ number as biased high by an unknown
amount.** Its value is in *changes* — the shape of the diurnal curve, the
response to a turn, the agreement in direction with the Apogee reference — not in
the reading itself. If an absolute number is needed, that is what the bought tube
and the potting are for.

**3. Surface leakage on the AFE.** Potting is what keeps the sub-µA nodes out of
condensate; buried in 100 %RH pore gas without it, they are not. Expect offset
drift on CELL_RE. Put a silica sachet in the cable tail and check its colour on
recovery — that reading is the diagnosis for anything odd in the data.

## The board is 1.6 mm here, and PLACEMENT.md still says 1.0

Fab, 2026-09-05: *"assume 1.6mm pcb thickness."* The KiCad board file and
`PLACEMENT.md` both still specify **1.0 mm, 4 layers**, so the two disagree and
the board file is the one that would have to move. Recorded rather than
reconciled, because that is not this model's call.

It is not a cosmetic number. `PLAN.md` gates a thickness change on "the tube
chord/assembled-height check", so here it is:

| | 1.0 mm | **1.6 mm** | against |
|---|---:|---:|---|
| swept diagonal | 21.93 | **22.19** | Ø27.2 tube bore, Ø25.18 head bore — both clear |
| head bore `bore_d` | 24.93 | **25.18** | head OD unchanged at Ø40 |
| trimmer worst corner | r 11.19 | **r 11.34** | Ø27.2 bore — 2.26 mm spare |
| **cavity mesh** | 4849 mm³ | **4917 mm³** | 5000 mm³ budget — **1.7 % margin, was 3.0 %** |

That last row is the one to watch. The gas-volume gate now passes by 83 mm³. It
is still a pass, and the mesh is measured rather than modelled, but there is no
longer room to spend on anything else inside the cavity.

## The head and the tube are ONE part

`make monobody` → `exports/body-monobody.stl`, **146.6 mm tall**, head and tube in
a single piece of plastic. The bonded socket is gone; Ø32 opens out to the head's
Ø40 on a 45° cone, which is why the whole thing prints cable-end-down with no
support anywhere.

**The reason is sourcing, not elegance.** The bonded joint is structural *and*
sealing, on the wet side, at ~75 °C in ammoniacal condensate — and `MEMBRANE.md`
forbids a load-bearing adhesive there until a named one has passed hot-condensate
ageing. **No such adhesive is sourced**, and "epoxy for the prototype" is a guess,
not a part number. Printing through the joint deletes the requirement instead of
guessing at it.

What it costs: a failed print loses the whole body, and any change to the head
reprints the whole 146.6 mm with it.

**`socket_len` is 3.0 in the monolithic head, not 14.0** (Fab, 2026-09-05). The
14 mm was the depth of the *bonded* socket — the glued area — and in a head with
no socket it had become nothing but the coordinate the cavity stack sits on,
leaving the head's first 14 mm as a plain Ø25.18 bore inside a Ø40 body: a
7.4 mm wall doing a job the tube does at 2.4 mm, over a length that holds
nothing but board. **The overall length does not change** — 11 mm of Ø40 head
becomes 11 mm of Ø32 tube, so `tube_len` goes 113 → 124 and the probe is still
146.6 mm. What it buys is about **5.9 cm³ of ASA** and a shorter, fatter section
turned into a longer, thinner one. It costs ~0.9 cm³ of extra connected gas
(Ø27.2 bore instead of Ø25.18 over those 11 mm), which is noise against the
75 cm³ the unpotted tube already contributes.

Two files carry a copy of that number and both had to move with it, which is the
trap: `o2_probe_body_tube.scad`'s `head_socket_len` (it is subtracted from
`tube_len`, so leaving it at 14 would have ended the tube 11 mm short) and
`o2_probe_head_end.scad`'s `body_tube_len`. The guide rail at station B now gets
*longer*, not shorter — the tube reaches board y=102, so 81.3–102 of that clear
band is on this part and only the last 5 mm is located by the head's bore alone.

The two-part bonded variant is still in the model — `joint="bonded"` — and is
committed as fd50a98 if it is ever wanted back.

## What gets printed

| part | solid volume | bbox | orientation | support |
|---|---:|---|---|---|
| **monobody** (head + tube) | 54.3 cm³ | Ø40 × 146.6 | upright, **cable end down** | none |
| cap | 12.1 cm³ | Ø37.2 × 26.5 | upright, **mouth up** | none |
| dam (2 halves) | 1.5 cm³ | 27.2 × 30 × 4 | flat | none |

≈ 67.9 cm³ of solid across the three, so roughly **73 g** of ASA at
1.07 g/cm³. Print them **one at a time**, not three to a plate; see the table
below. The cap
prints mouth up so its 8 mm sealing end is the first layer and the bayonet slots
are cut into a vertical skirt. Nothing in either part bridges.

## Print settings

Every number in the sealing column comes from
`~/dev/ee/p1p/doc/gastight-and-watertight.md`, whose own caveat applies here in
full: **no study in it tested ASA.** The settings are transferred, not measured.

| | value | why |
|---|---|---|
| orientation | **upright, cable end DOWN** | every feature — guide slots, lugs, seal land — is then a vertical extrusion. No overhang, no support, anywhere |
| objects per plate | **one** | identical parts: 0 mTorr singly, 18 mTorr nine-up |
| layer height | 0.10–0.15 mm | 0.2 mm cost ~31× leakage and ±90 % scatter |
| wall loops | **4** | and the wall is 2.4 mm = exactly 4 × 0.60, so there is no gap fill in it. The model asserts this |
| wall line width | **0.60 mm** | ≥ 0.64 sealed in test; 0.40 never did. Do not let the slicer choose |
| flow ratio | 1.00–1.02 | 0.95 is deliberate under-extrusion; 85–90 % always leaked |
| top/bottom shells | ≥ 5 | closures leak, walls do not |
| seam | aligned, painted onto the cable-end face | a placed seam is inspectable; random did not save the reference parts |
| nozzle / bed | 270 °C / 100 °C, textured PEI, brim | ASA on this machine |
| fan | 10 % min, 30–40 % max | layer welding beats surface finish here |

The tension is worth saying out loud: **the settings that seal a part are the
settings Bambu names as ASA warping causes.** A 127 mm tall Ø32 tube in ASA is a
warp candidate; use the brim and the enclosure.

**The printer was not reachable when this was written** (2026-09-04):
`~/dev/ee/p1p/bin/p1p-status` returned *"Connection Refused: not authorised"* on
every frame and then *"no full status frame received (printer off, or LAN Only
Mode not active)"*. That is a credentials-or-LAN-mode problem, not a print
problem — but nothing here has been sliced or sent, and the plate-clear check is
a human one that nobody has made. Bring the printer up before slicing.

**MC fan.** `~/dev/ee/p1p/doc/machine-state.md` still has the MC-fan row open as
of 2026-09-04, and it gates high-temperature filament inside the enclosure.
Resolve it (look at the board — there is no telemetry field) before a print this
long, or accept the risk knowingly. The machine has run ASA at 260/100 with that
row open, which is not evidence that it is fine.

## Assembly order

The cable end is a **bayonet cap**, so the board goes in and comes back out with
the head already bonded on. That is the point of the cap: nothing is bonded to
the board and the prototype is recoverable.

1. **Tap the cap.** M8 × 1.0 through the 3 mm end, Ø7.0 pilot as printed.
   Printed, not tapped, threads at this pitch are a coin toss and this joint is
   the only thing between the pile and an unpotted board.
   **Do not tap deeper than the wall** and do not counterbore the hole mouth:
   3 mm is only 3 turns, and it is the whole strain relief. The annular notch in
   the outer face is for the gland's own NBR ring and deliberately starts
   *outside* the thread's major diameter, so it costs no thread — a counterbore
   would have spent its depth out of the tapped length.
2. **Nothing to bond.** The head is already the same part. Ream the Ø27.3 H7
   well — it is now at the top of a 146.6 mm part, so fixture accordingly.
3. Solder the cable, thread it through the cap, fit the gland.
4. Slide the board in from the cable end, tip first, through both guide
   stations. Fit the dam halves around the board as it passes y = 81.
5. **O-ring into the cap's spigot groove**, not onto the tube's end face. It is
   a radial seal now: it rolls onto the Ø25.03 groove root at 4.3 % stretch and
   seals against the reamed Ø27.3 bore as the spigot enters.
6. Cap on, push and twist. The lugs drop into their pockets after about 35°,
   and then **keep turning** — the last 22° runs the lug up a ramp that
   converges on it, and the cap comes up against a positive wall at **57°**
   total. It should feel progressively tighter and then stop dead; if it stops
   spongily, it has bound on the ramp and the M3 screw will not find its pilot.
   **Neither the drop nor the wedge says anything about the seal.** A radial
   seal gives no axial preload, so the lug drops and the wedge tightens just as
   convincingly with the ring missing, rolled, or nicked — the wedge is
   plastic-on-plastic and would feel identical with no O-ring in the probe at
   all. Check the ring is on the spigot before the cap goes near the tube; you
   cannot check it afterwards.
7. **Fit the M3 lock screw**, radial, through the cap's slot into the tube's
   blind pilot, *after* twisting home. With a radial seal the screw is the whole
   of the retention — see *The lock screw* below.

## Measure the OD — it closes an open input

`o2_probe_head_end.scad` refuses to run without `tube_od_meas` and has done since
it was written. A printed tube makes that number available for the first time:
measure the print, at several angles for ovality, and feed the **measured**
figure in. Do not feed 32.0 back in — the part shrinks, and this project already
has three readings of ASA shrink on the carrier (−0.588 % to −0.960 %).

## The bayonet, and why there is a test for it

The cap locks with two lugs into two L-slots. **It no longer has a spring** —
that sentence used to say the O-ring on the tube's end face supplied one, and it
was true of the face seal this design replaced. The M3 screw is what holds the
lock now.

**The ramp is not a spring either, and it is not a seal.** The pocket's deep
wall converges 0.45 mm over the last 16° of travel, so the cap tightens as it is
turned instead of rattling over the 0.65 mm the flat pocket left it. Residual
play once home is **0.20 mm**, down from 0.65. That is all it does. It cannot
tighten the seal, because the cable seal is radial and its squeeze is set by the
reamed bore and the groove root — turn as hard as you like and the squeeze is
the same 22.7 %. A ramp that *did* compress a face seal would be sizing an
elastomer by hand torque, i.e. exactly the sustained strain on ASA at 75 °C that
`MEMBRANE.md`'s rule forbids.

**It stops on a wall, not on friction, and that was not the first design.** The
first version closed 0.80 mm — *past* the lug — giving a true interference
wedge, self-locking at 9.6° against a dry ASA-on-ASA coefficient of ~0.35–0.45.
It measured beautifully and it was wrong, and `tools/bayonet_check.py` is what
caught it. **A friction wedge has no defined stop**: it stops wherever hand
force balances elastic deformation. The check drove the cap to 30° with 0.2 mm³
of interference while the model declared its lock at 27°, and the lock screw
cannot live with that — the tube's pilot is a Ø2.5 hole at r = 14, so **1° of
scatter is 0.24 mm of lateral offset and 3° is 0.73 mm**, and the screw simply
misses its hole.

So the far wall is the stop. The ramp leaves 0.20 mm of clearance at it, which
is sized against the printed tolerance rather than for feel: a pocket that comes
out 0.1 mm short still *reaches* the wall instead of binding 4° early and
putting the pilot out of reach. What that trades away is the friction hold —
there is no interference any more — and that costs nothing that was load
bearing, because retention has been the M3 screw since the seal went radial and
the model has refused to build without it ever since.

Total twist is now **57°**, entry to home: about 35° to drop the lugs into their
pockets, then 22° more converging onto the wall. `MEMBRANE.md`'s rule for this enclosure is *"no part of the
enclosure may carry sustained strain at temperature ... retention is by positive
features plus a compliant elastomer seal that supplies the sealing force"*. A
printed thread held under preload at 75 °C is the creeping-polymer case that rule
exists to forbid; a bayonet lug is a positive feature.

That geometry can be **wrong while every part renders as a perfect closed
solid** — a lug that never reaches its pocket, or a pocket so deep the ring is
never squeezed, looks exactly like a working one in a mesh gate and in a picture.
It was in fact wrong on the first cut: the detent was 0.7 mm against a 1.5 mm
locked gap and a 2.0 mm cord, so entering the pocket left the ring **uncompressed
and the joint unsealed**. Nothing in the render said so.

`tools/bayonet_check.py` therefore measures the mechanism: it intersects the two
solids at a scan of positions and requires zero overlap sliding in, zero through
the twist, zero at the locked depth — and **positive overlap when pulled from the
lock**, which is the known-bad calibration. Without that last case the check
would happily pass a cap with no lugs at all.

## The cable seal — radial, and the same ring as the carrier

It started as a 28 × 2 **face** seal squeezed by the cap, and that was the wrong
joint twice over. It needed a second ring size, and — the part that actually
decided it — **its squeeze was set by the bayonet's detent depth**, a printed
feature whose tolerance was never budgeted. Every piece of validated seal work in
this project is on *radial* seals.

A 24 × 1.5 cannot be a face seal here at all: ring OD 27.0 against a Ø27.2 bore,
so it drops straight through. As a radial seal on a spigot the cap carries into
the bore, it lands almost exactly where the carrier's ring already sits:

| | value | carrier ring, for comparison |
|---|---:|---|
| bore | Ø27.3 H7, **reamed**, 12 mm deep | Ø27.3 H7 reamed — *the same reamer* |
| groove root | 25.030 × 2.10 wide | 24.840 × 2.10 |
| install stretch | 4.29 % | 3.50 % |
| squeeze | 24.33 % | 22.98 % |
| material under the root | 2.51 mm | 3.42 mm (2.4 min) |

**The bore must be reamed**, and even reamed the chain does NOT close on
catalogue rings. Both numbers below were wrong when first written and are
corrected from the 2026-09-05 Codex review (`../reviews/`):

| | squeeze points, of 15 |
|---|---:|
| printed bore ±0.20 alone | **13.63** (not 19.75 — that figure was bore *and* root together) |
| reamed H7 bore alone | 0.72 |
| reamed bore + printed root ±0.09 + **catalogue** cord | **15.1–15.7 — over budget** |
| reamed bore + printed root + **sorted** cord | ~7.5 |

So micrometer-sorted rings are **not the better option, they are the only one**.
The head's own note reaches the same conclusion for the carrier ring; one sorting
pass covers both, since it is the same ring.

`±0.09` is the **printed** figure, from seven readings on printed ASA carriers —
an earlier draft of this file called it a machined-PP number, which was simply
wrong (`o2_probe_head_end.scad`, `carrier_tol`).

**Two things moved to make room for the reamer**, and both are asserted rather
than left to be noticed: the lock boss went from z 6 to **z 17**, clear of the
12 mm reamed depth, and the cap's skirt grew from 12 to **18 mm** of engagement
so the screw can still reach it.

**And the bayonet lost its spring.** A face seal pushed the tube back out and
held the lug in its detent; a radial seal pushes outward, not along the axis. The
M3 lock screw is now the whole of the retention — which is what it was added for,
so nothing new is owed, but the bayonet on its own is no longer a lock and the
model refuses to build without the screw.

### The lock screw

The bayonet's own retention is a 0.3 mm detent held by the O-ring's preload, and
that is not something to bury for a season: the preload is tens of newtons and
unmeasured, EPDM takes compression set at pile temperature, and **the gland
clamps the cable to the cap**, so every tug on the cable runs cable → gland →
cap → bayonet → tube. One M3 thread-forming screw makes the lock positive and
leaves the O-ring doing only the job it is good at.

It is **blind**, and that is the whole design of it: a hole through the tube wall
at that height would vent the sealed volume past the seal plane. The wall is
thickened on the *inside* at z = 6, where nothing but cable passes, so the pilot
gets 3.5 mm of engagement and still leaves 1.75 mm of material to the bore. The
cap's clearance is an arc ±10° wide, so the screw finds its pilot anywhere in the
pocket's own play.

**Four** separate mistakes lived in that one subtraction, and **every one of them
rendered as a perfectly clean closed solid**: the rotation sent the hole out at
`lock_a_tube + 180` through plain wall with the boss left untouched; the rotate
leaves the axis at the origin's height, so the hole was cut at z = 0 with half of
it hanging off the end face; and it sat in its own `difference()` with the boss,
so it never reached the wall it has to pass through first — a tube with no pilot
at all; and then, fixing that, the boss went into the *outer* union where **the
bore subtraction ate it**, leaving a 3.5 mm pilot in a 2.4 mm wall — a through
hole from the compost straight into the sealed volume, below the seal plane.

That last one shipped. It was found by slicing the exported STL, not by any
assert — and the assert beside `lock_pilot_floor` passed the whole time, because
it compares two numbers the model was *told* rather than two things it *built*.

`bayonet_check.py` now does both jobs on the mesh: it drives a rod down the
screw's path and requires it clear at the model's own stated angle and blocked
±45° off it, and it weighs the material inboard of the pilot floor, which must be
solid boss. The second test is calibrated against its own known-bad — delete the
boss and it fails with 0.0 of 12.7 mm³.

Locked squeeze is 25 % of the cord; passing the detent takes it transiently to
40 %, which an EPDM cord takes. As built, the check reports an **entry window of
about 7°** and a **lock window of about 7°, 30–39° apart** — the entry slack was
raised from 3° to 10° for exactly this reason: 3° was geometrically correct and
unusable, because it is a window you have to find by feel with the tube in one
hand.

Two more things it caught, both in the check rather than the part, and both
worth knowing before writing another one:

- **Coincident contact is not collision.** A lug sliding along its channel floor
  touches it exactly, and CGAL returns that as a sliver mesh of ~1e-13 mm³
  rather than as nothing. Testing `== 0.0` read every contact as interference,
  and the check twice reported a working bayonet as broken. It judges against a
  threshold now.
- **"Clear at the sealing depth" is not "locked."** It is also true at the entry
  angle, because the entry slot is open to the mouth. The check now defines
  locked as *clear at the sealing depth **and** obstructed when pulled*, which is
  what the word means.

## Not sourced, and needed before burial

1. ~~The gland and the cable.~~ **Both bought, and they fit.** Recorded here
   because the pairing is the constraint, not either part on its own.

   | | part | the number that matters |
   |---|---|---|
   | gland | **Lumonic M8 × 1.0**, nickel-plated brass, NBR seal | clamp **2–5 mm**, panel **max 3 mm**, −40…+100 °C, hex nut supplied |
   | cable | **LAPP UNITRONIC SENSOR FD Li9Y11Y 4×0,25**, PUR/PP, art. 7038890 | **OD 3,8 mm**, −40…80 °C fixed, 300 V, 4 cores |

   3,8 mm sits mid-range in 2–5 mm, which is where a gland grips best, and the
   four cores match the board's four wire lands J101–J104 exactly. `cap_end_t`
   is cut to the gland's rated 3 mm and the tap is M8 × 1.0, Ø7,0 pilot.

   **Three things to accept knowingly.** None is a geometry problem and none is
   fixed by changing the cap:

   - **The cable is now the temperature-limiting part of the probe: 80 °C.**
     The gland is rated 100 °C and every seal here is EPDM good well past that.
     Against a pile that runs ~75 °C — with hot spots above it — that is about
     5 K of margin on the one component with the least.
   - **It is UNSHIELDED.** `Li9Y11Y` carries no screen (the shielded build would
     be `Li9YC11Y`), and the earlier candidate, ÖLFLEX ROBUST 215 **C**, was
     screened. This probe has a sub-µA analogue front end on an unpotted board
     with a heater switching on the same four cores' worth of harness. Whether
     that matters is a measurement, not an opinion — but take the noise floor
     early, on the bench, while it is still cheap to change.
   - **PUR and hydrolysis, unresolved.** Buried service here is 100 %RH at
     ~75 °C for a season, which is the exact condition that hydrolyses
     polyester-based PUR. LAPP publishes hydrolysis-resistant PUR grades; the
     product page does not say which this is. **Ask LAPP whether 7038890's
     sheath is hydrolysis-resistant** before committing a season to it.

   And one about the gland itself:

   - **NBR is the weakest elastomer in the probe.** Every seal this project
     chose is EPDM 70 peroxide, picked for hot wet ammoniacal service. NBR
     handles ammonia, but 100 °C is its ceiling and hot wet NBR is not a
     season-long part. It is a bought seal on a bought part.
   - **3 mm of ASA is 3 turns of M8 × 1.0, and it is the entire strain relief.**
     Nothing else in the probe anchors the cable. Leave a real service loop in
     the tail so the gland is never the thing taking a pull — the cable's own
     fixed-install bend radius is 5 × Ø = 19 mm, so a loop fits the tail easily.
2. ~~The cable-end O-ring.~~ **Closed.** It is the **same ring as the carrier** —
   ORS116787, 24 × 1.5 EPDM 70 peroxide, house compound 127019011,
   o-ring-stocks.eu (`../tech/PROBE-CARRIER-SOURCING.md`). One size, one
   compound, one test report and one sorting pass for the whole probe. See
   *The cable seal* below for why it changed.
3. **An M8 × 1.0 tap** (and a Ø7.0 drill, if the printed pilot needs cleaning up).
4. **Silica gel** for the tail.

## One thing to check by eye before the first insertion

The guide stations sit where the board's edges are clear, and the bands were
measured off `o2-probe.kicad_pcb` on 2026-09-04 — this board has **pads 0.25 mm
from the edge** (RV1 at y=73, R7 at y=46, R38 at y=70), so the placement is not
free. The clear bands are board y 0–28.6, 47.8–55.7, 58.3–64.6 and 81.3–103.6;
the two long ones are used, with 1.0 mm of engagement against a 1.5 mm band.

**Pads are what could be measured from the board file. A component body
overhanging its own pads is not covered by that scan.** Look along both edges of
the populated board once before it goes in. And if the board revision changes,
re-run the scan — those four bands are the only thing tying this part to that
board.
