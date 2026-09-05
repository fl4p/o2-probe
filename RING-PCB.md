# The heater ring as PCB — geometry study

> **STATUS 2026-09-05: the geometry this study is built on is GONE.** Fab
> returned the cell to a **standing** THT mount (PLAN.md option A), so nothing
> projects past the board tip, `cell_axial_len` is deleted, and with it the
> **Ø16.62 × 13.0 mm neck** — the 1.00 mm annulus this whole study routes
> through. §1's tuning fork has nothing to cross: the board tip now lands on the
> well floor (z = 16.0) and the well is Ø26.1, not a Ø16.62 tunnel.
>
> What survives, and is worth re-reading before the ring is re-sited: §2's ring
> in the carrier's Ø18 spigot bore (that bore is unchanged), §3's cost of a
> head-side permanent mount, §5.3's finish question, and the 4.3 mW/K back-leak
> arithmetic (the conductor length changes, the method does not). What does not
> survive: §1's finger envelope, §5.1's "measure the printed neck bore", and
> every dimension quoted off the neck.
>
> **The heater's route to the ring is therefore reopened.** With the cell
> standing on the board 13.5 mm back from the tip, the ring is no longer reached
> by fingers running past the cell — decide it against the new bore before any
> schematic edit.

**2026-09-04.** Written before any schematic edit, against the actual bore geometry
in `cad/o2_probe_head_end.scad` (end-window head, `cell_axial_len = 13.0`
placeholder). Nothing here is drawn yet.

Two prior decisions bound this:

- **The end-window head wins**, and it is no longer close. Measured from the two
  models: the radial head reports **10.6 cm³ of connected volume against a 5.0 cm³
  budget** (2.1× over), a 46 mm head / 57 mm guard, and 100 mm² of window; the
  end-window head is **4.81 cm³**, 40 / 45 mm, 201 mm². So J5's ring at the board
  tip is orphaned (`HEATED-SPREADER.md` §0) and the heater's home is forward.
- **Fab chose a head-side, permanent mount** (2026-09-04) over a carrier-side one,
  so the heater is never consumed with a membrane change. §3 prices that choice —
  it is more expensive than it looked.

---

## 1. The ring needs no wires

The first framing of this had the ring as a separate part reached by a harness.
That was an assumption, not a constraint, and Fab rejected it. The geometry says
why:

```
neck Ø16.62 → r 8.31
cell Ø14.62 → r 7.31      1.00 mm free annulus, all the way round
board tip   z = 16.0
well floor  z = 29.0      13.0 mm to cross
```

**Cell diameter measured 2026-09-04 (Fab): Ø14.62**, against DS-0637 Iss. 2's
Ø14.4 nominal — +0.22 mm. It cost nothing here, because `neck_d` is *derived*
(`neck_d = cell_d + 2*neck_margin`), so the neck opened with the cell and the
annulus held at 1.00 mm instead of being eaten down to 0.89. What it did cost is
gas volume — see §5.2.

A 1.0 mm annulus is hostile to a connector and roomy for **the board itself**.
Route the main board's gas end as a **tuning fork**: full 20 mm width to the
present tip, then two narrow fingers running 13 mm forward past the cell, ending
in a small PCB carried perpendicular on their ends — a soldered T-joint, the way
any right-angle daughterboard mounts.

That removes, in one move: the harness, the hand-made joint in the cavity, the
assembly step through an Ø18 bore, and a corrosion site 12 mm from CELL_RE.

**Conductor count comes free.** Two fingers × 2 layers = **4 conductors** — heater
pair *and* sensor pair, which was the whole reason a connector was being
considered.

### Finger envelope

| | |
|---|---:|
| radial band available | r 7.31 (cell) → r 8.31 (neck) = **1.00 mm** |
| finger width 0.6 mm → clearance per side | **0.20 mm** |
| finger Y extent (board thickness) vs neck at r 7.8 | ±0.5 mm against ±2.85 mm — ample |

**One bound is now measured, the other is not.** The cell can is **Ø14.62,
measured** — but from *one sample*, so it is a value and not a tolerance band.
The neck is a **printed ASA bore** and has never been measured at all. 0.20 mm
per side, with no statistical margin on one side and no data on the other, is
thin. **Do not freeze the finger width before the printed bore is measured on a
real part.**

Because `neck_d` is derived from `cell_d`, a further cell revision opens the neck
automatically and preserves the annulus — but each 0.1 mm of cell diameter costs
roughly 34 mm³ of cavity margin (§5.2), so the annulus is not free forever.

### Heat leaked back down the fingers

Two 1.0 mm × 2 oz copper paths, 13 mm long: `k·A/L` = **4.3 mW/K**, so ~**86 mW**
at a 20 K rise out of a ~1 W budget — about 9 %, and reducible by necking the
copper in the fingers. Acceptable, and worth keeping in the budget rather than
discovering later.

## 2. The ring itself

Head-side, the ring lives inside the carrier's Ø18 spigot bore, and **the cell
must still pass through it** — the cell is a consumable and its only exit is
axial (`cad/o2_probe_head_end.scad`, `CELL SERVICE` echo). So:

| | |
|---|---:|
| OD ≤ spigot bore Ø18 → use | **17.4** |
| ID ≥ measured cell Ø14.62 + clearance → use | **15.2** |
| clearance to the can, per side | 0.29 mm |
| annulus width | 1.1 mm |
| **face area** | **56.3 mm²** |
| z, back face | 29.5 (0.5 clear of the cell top at 29.0) |
| z, front face at 0.8 mm thick | 30.3 |

The carrier still withdraws: it moves forward, so only its spigot bore (Ø18)
passes over the ring, never its Ø16 throat. Carrier replaceability is preserved.

## 3. The cost of the head-side choice, quantified

This is the finding, and it was not visible when the choice was made.

Membrane dry face is at **z = 38.42**. A head-side ring front face at 30.3 is
therefore **8.12 mm** behind it, against **3.82 mm** for the carrier-side heater
counterbore. With `η = 1/(1 + h·L/k_air)`, k_air = 0.028 W/m·K:

| h (W/m²K) | head-side, 8.12 mm | carrier-side, 3.82 mm |
|---:|---:|---:|
| 5 | **0.408** | 0.594 |
| 10 | 0.256 | 0.423 |
| 25 | 0.121 | 0.227 |
| 50 | 0.065 | 0.128 |

**`HEATED-SPREADER.md` §7 sets the target at η ≥ 0.5. The head-side ring does not
reach it at any h in the plausible range** — its best case, at the most optimistic
h, is 0.408. The carrier-side position clears 0.5 at h ≲ 5.

And the area term makes it worse than the table says. The formula is a
parallel-plate model in which area cancels; the real geometry is a **56.3 mm²
annulus trying to warm a 201.1 mm² window** — 28 % of it — from 8.12 mm away.
Carrier-side would be 125.7 mm², still only 63 %.

So: **a plain annular ring, at either position, is not a sufficient heater.** That
is not a new conclusion — `HEATED-SPREADER.md` §1 already showed a rim ring warms
an annulus 1–3 mm wide against an 8 mm window radius — but this is the first time
it has been priced against the actual mounting positions.

## 4. What that means for what to build now

**Build the fork. Treat the first ring as the instrument, not the answer.**

The reasoning is about which decisions are expensive and which are cheap:

- **The fork is a main-board change** — new outline, new fab, a revision of the
  controlled 20 × 107 dimension to roughly 20 × 120, and it touches the tube fit
  and the potting fixture. Expensive to redo, so freeze it once.
- **The ring is a ~Ø17 two-layer coupon.** Nearly free, days to re-spin, and it
  changes nothing upstream.

So commit the platform and iterate the payload. The v1 ring carries the heater
and the temperature sensor, and its first job is to **measure `h` and η in situ**
— the measurement `HEATED-SPREADER.md` §7 says gates everything and that nobody
has made. It will also very likely under-heat, and §3 says so in advance rather
than discovering it in the field.

**The upgrade path is already open, and needs no board change.** The fork's ends
can equally carry a v2 ring that extends **forward on legs** into the flare cone
— the cone runs Ø18 → Ø16 over z 34.6 → 38.4, so legs at r ≈ 7.75 clear it — and
terminates in a **perforated spreader disc of up to Ø15.6** sitting just behind
the membrane. That disc is **191 mm² against the window's 201 mm²**, essentially
touching, and the carrier still withdraws because its Ø16 throat clears Ø15.6.

`HEATED-SPREADER.md` §2 already says 2 oz copper at 75 % open meets the h = 50
spreading requirement with 2.2× margin, where 316 needed 0.213 mm. What that
section did not have was a way to mount such a disc permanently. The fork is it.

Its open problem is unchanged and real: §4's membrane support. The membrane is
unsupported across Ø16 and a disc pressed against its dry face pushes it outward.
That is a v2 problem, and the v1 measurement is what decides whether it must be
solved at all.

## 5. Open before layout

1. ~~**Measure the printed neck bore on a real part.**~~ **VOID 2026-09-05 —
   there is no neck.** The standing cell deleted it, and with it the 0.20 mm
   finger clearance that made the bore load-bearing. The can is **Ø14.62,
   measured 2026-09-04**, one sample, and that still stands. `cell_axial_len` is
   deleted rather than measured; what is still unmeasured is **`cell_seated_h`**
   (can top above the board plane, placeholder 8.8) and `cell_h`, still the
   datasheet's 8.3 and not re-measured while the can was in hand.
2. ~~Decide the neck opening.~~ **Taken automatically.** `neck_d` is derived, so
   the measured cell carried the neck Ø16.4 → **Ø16.62** and held the annulus at
   1.00 mm. §5.2 records what that cost.
3. **Ring surface finish** — open since `CONTACT-CORROSION.md` §3 retracted the
   ENIG rationale. The ring is a ~Ø17 coupon, so ordering it in **two finishes is
   nearly free** and would give an in-situ comparison the literature cannot
   supply for this environment.
4. ~~The temperature sensor is unsourced.~~ **Closed 2026-09-04 — the pocket is
   gone.** Fab: "I don't think we need that additional sensor, let's try without
   first." `cartridge_tsense_axial()` is no longer called from the head; the
   heater's own PCB carries its sensor on two of the fork's four conductors. That
   turns an unsourceable 1.2 mm interface dimension into an ordinary board-level
   part choice. The module stays in `membrane_cartridge_common.scad`, uncalled and
   cheap to restore. **The ring's own sensor is still to be selected** — but it is
   now a normal component decision, not a geometry constraint.
5. **Do the AFE changes in the same board revision.** `POTTING.md` §1 needs the
   RE follower / guard buffer, a fixed VREF and bias telemetry; the fork needs a
   new outline. One respin, not two.
