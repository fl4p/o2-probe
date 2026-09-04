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

## What gets printed

| part | solid volume | bbox | orientation | support |
|---|---:|---|---|---|
| tube | 30.1 cm³ | Ø35.2 × 127 | upright, **cable end down** | none |
| cap | 11.1 cm³ | Ø37.2 × 21.5 | upright, **mouth up** | none |
| dam (2 halves) | 1.5 cm³ | 27.2 × 30 × 4 | flat | none |

≈ 42.8 cm³ of solid, so roughly **46 g** of ASA at 1.07 g/cm³ — and for the tube
that figure is real rather than an upper bound, because its wall is four
perimeters and nothing else. Print them **one at a time**, not three to a plate;
see the table below.

The cap prints mouth up so its 8 mm sealing end is the first layer and the
bayonet slots are cut into a vertical skirt. Nothing in either part bridges.

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
2. **Bond the tube into the head.** Ø32 into the head's socket, 14 mm of
   engagement, 0.2 mm radial adhesive gap. Epoxy for the prototype. *Not*
   solvent weld: acetone/MEK is the chemistry ASA is weakest against and
   `MEMBRANE.md` flags environmental stress cracking as one of the two named
   risks for this enclosure.
3. **Measure the tube OD first**, at several angles, before bonding — see below.
4. Solder the cable, thread it through the cap, fit the gland.
5. Slide the board in from the cable end, tip first, through both guide
   stations. Fit the dam halves around the board as it passes y = 81.
6. O-ring on the tube end face, cap on, push and twist 30° until the lugs drop
   into their pockets. The drop is the confirmation — if it has not dropped, the
   ring is not squeezed.

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
2. **The cable-end O-ring.** 28 × 2.0 is a stock metric size but has *not* been
   checked against the vendor already used for the head's ring
   (o-ring-stocks.eu, EPDM 70 peroxide-cured, `../tech/PROBE-CARRIER-SOURCING.md`).
   EPDM for the same reason as there: ammonia attacks FKM.
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
