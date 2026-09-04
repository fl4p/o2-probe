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
| head cavity alone | 4.84 cm³ | 0.97× |
| **+ open tube, no dam** | **63.8 cm³** | **12.8×** |
| + tube with the dam fitted | 18.3 cm³ | 3.7× |

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

What it costs: a failed print loses the whole body, any change to the head
reprints the whole 146.6 mm with it, and the guide rail at station B gets shorter
(the tube now stops at board y=91, so only 81.3–91 of that clear band is on this
part). Over the last 16 mm the board is located by the head's Ø24.93 bore alone.

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

1. **Tap the cap.** M12 × 1.5 through the 8 mm end, Ø10.5 pilot as printed.
   Printed, not tapped, threads at this pitch are a coin toss and this joint is
   the only thing between the pile and an unpotted board.
2. **Nothing to bond.** The head is already the same part. Ream the Ø27.3 H7
   well — it is now at the top of a 146.6 mm part, so fixture accordingly.
3. Solder the cable, thread it through the cap, fit the gland.
4. Slide the board in from the cable end, tip first, through both guide
   stations. Fit the dam halves around the board as it passes y = 81.
5. O-ring on the tube end face, cap on, push and twist 30° until the lugs drop
   into their pockets. The drop is the confirmation — if it has not dropped, the
   ring is not squeezed.
6. **Fit the M3 lock screw.** Radial, through the cap's slot into the tube's
   blind pilot, *after* twisting home. See below.

## Measure the OD — it closes an open input

`o2_probe_head_end.scad` refuses to run without `tube_od_meas` and has done since
it was written. A printed tube makes that number available for the first time:
measure the print, at several angles for ovality, and feed the **measured**
figure in. Do not feed 32.0 back in — the part shrinks, and this project already
has three readings of ASA shrink on the carrier (−0.588 % to −0.960 %).

## The bayonet, and why there is a test for it

The cap locks with two lugs into two L-slots, and the O-ring on the tube's end
face is the spring — `MEMBRANE.md`'s rule for this enclosure is *"no part of the
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

**The bore must be reamed.** As-printed, its ±0.20 spends **19.75 of the 15
available squeeze points** on its own; reamed it spends 0.72. With the printed
cap groove (±0.09) and catalogue cord it comes to 12.18 of 15 — it closes, but
micrometer-sorted rings take it to 7.51 and that is the route to use, exactly as
the head's own note concludes.

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

Three separate mistakes lived in that one subtraction, and **every one of them
rendered as a perfectly clean closed solid**: the rotation sent the hole out at
`lock_a_tube + 180` through plain wall with the boss left untouched; the rotate
leaves the axis at the origin's height, so the hole was cut at z = 0 with half of
it hanging off the end face; and it sat in its own `difference()` with the boss,
so it never reached the wall it has to pass through first — a tube with no pilot
at all. `bayonet_check.py` now drives a rod down the screw's path and requires it
clear at the model's own stated angle and blocked ±45° off it.

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

1. **The gland — and M12 is tight for the cable now recommended.** A parallel
   sourcing pass in `../CABLE-SOURCING.md` (2026-09-04, another session's
   uncommitted work) recommends **LAPP ÖLFLEX ROBUST 215 C 4×0,5, OD 6,6 mm**.
   A great many M12 × 1.5 glands clamp **3–6,5 mm**, which 6,6 misses. Wider
   M12 glands exist (4–7 mm), so this is a gland *selection* problem, not a
   geometry problem — but **check the clamp range against 6,6 mm before
   ordering**, and if no M12 covers it, the cap's boss goes to M16 and only that
   one dimension changes. Do not assume M12 fits because the hole says M12.
2. ~~The cable-end O-ring.~~ **Closed.** It is the **same ring as the carrier** —
   ORS116787, 24 × 1.5 EPDM 70 peroxide, house compound 127019011,
   o-ring-stocks.eu (`../tech/PROBE-CARRIER-SOURCING.md`). One size, one
   compound, one test report and one sorting pass for the whole probe. See
   *The cable seal* below for why it changed.
3. **The M12 × 1.5 tap.**
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
