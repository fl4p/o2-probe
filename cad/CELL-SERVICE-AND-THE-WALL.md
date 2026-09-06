# Replacing the cell in a potted probe, and the wall that a coated one needs

**Status:** design analysis, 2026-09-06, prompted by Fab: *"did we ever consider
how to replace the cell when this is potted? just coat the board and leave an air
chamber in the tube around the sealed board? then we need a wall between that and
our sensor chamber. how to put the separators?"*

Every number below is measured off a mesh unless it says otherwise. Reproduce
with `make gas-shell`.

---

## 1. Yes it was considered, and the answer on file is stale

`POTTING.md` §1 opens with the requirement — *"the cell is replaceable with the
PCB already potted"*, set by Fab 2026-09-04 — and §1.5 concludes it is unsolved:
head bonded, cell withdrawn axially through the Ø18 spigot bore, 17.6 mm of
travel, *"no extraction tool exists and fingers do not fit."*

**That was written for the past-end cell mount.** The design moved to the
standing mount, and `o2_probe_head_end.scad` now echoes the consequence itself:

```
CELL SERVICE: standing mount -- the cell rides the board and comes out the
CABLE end. No extraction through the head, no reach down the 18 mm spigot bore.
```

So the service route already exists and is a good one: release the lock screw,
twist the bayonet, pull the cap, withdraw the board, swap the cell on the bench.
`POTTING.md` §1.5's whole "swappability is a tooling problem" passage should be
replaced with *swappability is solved, and the pot is the only thing that breaks
it.* Fab's instinct is right; this is the live question, not a settled one.

## 2. What dropping the pot actually costs

`POTTING.md` §2 gives the pot three separable jobs. Two of them transfer:

| job | without the pot |
|---|---|
| cable strain relief | the SKINTOP INOX-R M12 is a strain-relief gland, already ordered; §5 says the pot never carried this alone anyway, it needed a mechanical anchor |
| creepage across wet surfaces | conformal coat plus the driven guard. §2 already states the pot was never the moisture *barrier* — the tube, end seal and gland are |
| **removing the condensing air volume over the AFE** | **does not transfer** |

The third is the real cost, and it is not small. §2's acceptance criterion for
the whole potting process is *void-freedom over the AFE*, because `PLAN.md`'s own
arithmetic says ~1.8 MΩ of wet contaminated surface across 600 mV already fakes
0.1 % O₂ (≈335 nA), and a 1 mm bubble against the guard ring is that resistance
class. An air chamber is not a 1 mm bubble; it is ~58 cm³ of one.

**So the air chamber is viable only if it is deliberately dry.** Desiccant in the
cable tail (the body model already reserves room for a silica sachet in
`tail_len`), or a dry backfill, plus an enclosure that genuinely seals. That is
ordinary and buildable, but it has to be designed, not assumed.

Two consequences to carry:

- **`POTTING.md` §7 flips.** Potting couples the AFE to the tube wall at
  ~0.2 W/m·K against still air at 0.026. Unpotted, part of the LMP91000's 6 K
  budget goes back onto self-heating and heater proximity.
- **§6's outgassing hazard goes away.** No 50 g of curing PU inside the tube
  means the SHT45 contamination risk and the post-potting recondition bake both
  disappear. That is a real saving, not a consolation.

## 3. Why the wall — and the number that reframes everything

The wall's job is **response time**, not moisture. `o2_probe_body_tube.scad`
measures the unpotted probe:

```
GAS VOLUME, unpotted: head cavity 4.3671 cm3 (MEASURED off the cavity mesh)
+ tube 57.6522 + tail 12.7835 = 74.8029 cm3, 14.9606x the 5.0 cm3 budget.
```

The obvious reading is "the pot was holding that down, so replacing it costs a
wall." **That reading is wrong, and this is the most useful finding in the
document.**

`PLAN.md` pots `y = 0…82` and leaves `y = 86…107` as the gas zone. **The cell is
at y = 93.5.** So the pot never filled the bore the cell actually breathes. The
potted production build — the one the 5.0 cm³ budget is said to describe —
measures:

| | connected gas | vs 5.0 cm³ |
|---|---:|---:|
| potted to y=82, monolithic head | 15.35 cm³ | **3.07×** |
| potted to y=82, bonded head | 15.56 cm³ | **3.11×** |

Bore area is 581 mm². Every millimetre of open bore left on the gas side costs
0.58 cm³, and there are 20 of them between the pot line and the head.

**The wall is not the price of giving up the pot. It is work the pot was never
doing.** Whatever is decided about potting, this part is needed.

## 4. What a wall alone cannot do, and what the eliminations are

A plain bulkhead cannot go forward of board y ≈ 85.5: the can spans y
86.19…100.81 and has to stay on the gas side. That leaves ~16 mm of open bore in
front of it — about 9.3 cm³ — so **a wall by itself lands near 13.7 cm³ and
misses the budget by 2.7×.** What closes the number is *filling*: occupying the
bore around the can and leaving a defined gas gap. The separator and the filler
are the same part.

Three other architectures were considered and die:

- **Board pulls through a wall fixed to the tube.** Dead. The can rides on the
  board, so it must pass the wall too — that is a Ø15 hole, not a board slot.
- **Wall bonded to both board and tube.** Dead. That is potting with less resin;
  the board never comes out and the service route is gone again.
- **`o2_probe_response_candidate.scad`'s Ø23 shroud.** It seals to nothing and so
  passes the cable end freely, which is exactly right — but it was drawn for a
  smaller cell footprint. The standing can sweeps r = 12.07 and a Ø23 shroud is
  r = 11.5. It does not fit this mount.

## 5. The part: `o2_probe_gas_shell.scad`

A two-piece clamshell, split on the board plane like the existing `dam`, closing
around the board and the can over board y 82…102, bonded to the PCB so it leaves
with the board as one serviceable unit. A pocket around the can gives a 0.6 mm
rim gap and a 0.8 mm gap over the sensing face, opening forward into the head's
bore. Both halves render as closed solids (`Volumes: 2`) in all four
configurations.

Previews: `exports/gas-shell-assembly.png` (the pair on the board, tube ghosted)
and `exports/gas-shell-section.png` (one half cut open on the board plane, which
is the only way to see the pocket at all).

Three constraints shaped it, and two are non-obvious:

- **It must pass the Ø25.7 collar.** The board goes in tip-first from the cable
  end, so the shell travels the whole tube. That caps its OD at 25.2 inside a
  27.2 bore — an annulus 1.0 mm deep, which is a wide-open bypass duct around
  the entire part. This is the collar we added on 2026-09-06 to seal the cap with
  the on-hand 22 × 2 ring, and it is now load-bearing in a second place.
- **It must pass the guide rails.** `guide()` reaches from x = 9.0 out to 14.8
  over 7.0 mm of board normal, so a Ø25.2 disc fouls station A by 3.6 mm each
  side. The shell therefore carries full-length rail channels — which are
  themselves the second-largest gas term in the part.
- **Board y 81.3…103.6 is the only band where both board edges are clear.** The
  model asserts on it; asking for y1 = 105 fails with the reason.

### Measured, `make gas-shell`

```
                                       shell   +mono head   +bonded head
POTTED to y=82, no shell (reference)     --    15349 3.07x   15557 3.11x
collar kept, station B short (as drawn) 3595    7962 1.59x    8171 1.63x
collar kept, station B extended         2681    7048 1.41x    7257 1.45x
collar deleted, station B short         2406    6773 1.35x    6982 1.40x
collar deleted, station B extended      1492    5859 1.17x    6068 1.21x
```

(mm³, against the 5.0 cm³ budget.) **The shell takes the probe from 74.8 cm³ to
5.9, a 12.8× improvement, and beats the potted build by 2.6×.**

## 6. The two open decisions the table prices

**Does the collar stay?** Keeping it costs 1.65 cm³ of open annulus and means the
shell can never carry a real radial seal — a 2.0 cord on the ~Ø24 root it would
need relaxes to ~Ø28, and driving that through Ø25.7 is 57 % squeeze at the lip,
which rolls or shaves the ring. The model refuses to draw that seal unless
`cable_end_bore_is_full` is set, rather than rendering a ring that cannot be
installed. Giving up the collar means going back to a 24 × 1.5 cap ring, which we
do not have on hand.

The middle option is `shell_seal="lip"`: a 0.45 mm printed conical skirt that
deflects through the collar and springs back in the bore. It costs nothing to try
and needs a coupon before it is believed — ASA at pile temperature for a season
is not a spring.

**Does station B's rail run the length of the shell?** Today
`station_b = [82, 90]` for the monolithic joint. That limit is **stale**: it was
sized when `head_socket_len` was 14 and the tube stopped at board y = 91. It is 3
now and the tube runs to 102, so the rail can cover the whole shell — and a rail
inside the channel plugs it, worth 0.91 cm³. This is a change to the tube, which
is why it has not been made while one is on the printer.

## 7. What the shell still cannot fix

Even at its best the probe is 5.86 cm³ against a 5.0 budget, and **the remaining
0.86 is not in the shell.** The head's spigot bore is Ø18 × 8.5 = 2163 mm³, 43 %
of the entire budget on its own; the monolithic joint costs another 1438 mm³ over
the bonded one by opening the head's bore from z = 0.

So the honest ranking of what to attack next is: the spigot bore, then the joint,
then the collar, then the rails. Nothing on that list is this part.

`RESPONSE-CANDIDATE-VOLUME.md` also says the 5.0 figure is
communication-model arithmetic and that release needs *"a measured connected
effective volume"* and a measured transient. A budget that no variant of the
design has ever met, potted or not, is worth re-deriving before more geometry is
bent to it.

## 8. What changed in the repo

- **`o2_probe_gas_shell.scad`** — new. The clamshell, its gas Boolean, and the
  three seal branches.
- **`tools/shell_volume.py`** — new. Weighs the connected gas on the mesh. It is
  a ratchet plus a report, not a threshold: a `<= 5000` assert would fail on
  every commit and be switched off, and a `<= what it measures today` assert is a
  mute button. Unevaluable input (missing mesh, failed render, empty solid)
  raises. Calibrated against three known-bads.
- **`tools/interface_check.py`** — the shell's 15 mirrored dimensions are now
  compared against their sources, and `head_cavity` is re-rendered and weighed
  instead of trusted. Both calibrated against a known-bad.
- **`o2_probe_body_tube.scad`** — `head_cavity` was `2929`, correct for the
  **bonded** head, in a file that defaults to `joint = "monolithic"`. The
  monolithic cavity is 4367. It is now a ternary and it is checked. Its old
  comment ended *"NOTHING CHECKS THIS COPY"*, which turned out to be the whole
  problem.
- **`o2_probe_head_end.scad`** — `body_groove_root` 22.4732 → 22.6732, following
  the collar bore to 25.7.
- **`Makefile`** — `make gas-shell`.

## 9. Open, in priority order

1. **Decide the collar.** It is now load-bearing in two places and the table
   prices both answers.
2. **Measure `cell_seated_h` on a real cell in a real socket.** It sets the gas
   gap over the sensing face directly, and 8.8 is the Makefile's provisional
   value.
3. **Print one shell and a lip coupon.** The lip is the only branch that gets
   two chambers without giving up the collar, and it is a five-gram test.
4. **Attack the spigot bore**, then reconsider the monolithic joint. That is
   where the residual 0.86 cm³ lives.
5. **Extend station B to [82, 102]** once the tube is off the printer.
6. **Specify the dry chamber** — desiccant sachet size and placement, or a dry
   backfill — and re-run `POTTING.md` §2's void argument against a chamber
   instead of a bubble.
7. **Re-derive the 5.0 cm³ budget**, or measure a transient. No variant of this
   design has ever met it.
