# Rev B 86 mm ring board — accepted-risk dispositions, 2026-09-14

Dispositions for the findings of the 2026-09-13 independent review
(`2026-09-13-revb-86-ring-codex-review.md`) that are **accepted rather than
fixed**. Each says what was measured, who decided, and what would refute it.
None of these is a qualification: no board has been built.

## 1. I2C at minimum clearance past the analog front end — FIXED, not accepted

**Closed 2026-09-14 by moving the pads.** Fab, asked to choose between keeping
J107's I2C lands at the cable end at 0.100 mm from `/GUARD_REPLICA` and
`/VREF_TRIM` and relocating them: *"i dont care where the pads are"*. They moved.

### What was wrong

| J107 copper, as accepted | beside | gap | parallel length | gap on accepted revb-86 |
|---|---|---|---|---|
| SCL, B.Cu, X 101.1..101.2, Y 100.0..113.85 | `/GUARD_REPLICA` (X 101.5, 0.25 mm wide) | 0.100 mm | ~9 mm | 0.625 mm |
| SDA, F.Cu, X 118.35..118.95, Y 96.6..102.4 | `/VREF_TRIM` (0.15 mm wide) | 0.100 mm | ~6 mm | not adjacent |

0.100 mm *is* the board rule, so DRC was silent. The concern was coupling, which
no clearance rule expresses.

**The earlier impossibility claim was wrong in scope, and is withdrawn.** It was
measured with J107's pads held where they were, then written as if it held for
any placement. A second independent review disproved it by relocating individual
pads. Fab's 2026-09-14 acceptance had rested on that claim, so the acceptance
does not stand — and it is now moot.

### What was done

`tools/relocate_j107_i2c.py` moves pads 3 and 4 to the bus side of the AFE and
deletes the legs that fed them; `tools/reroute_net.py` (SENS_EXTRA=0.3) routes
the one new track.

| pad | from | to | new copper |
|---|---|---|---|
| 3 `/I2C_SDA` | (108.70, 61.50) | **(104.10, 125.95)** | none — the land sits on existing B.Cu SDA copper |
| 4 `/I2C_SCL` | (111.30, 61.50) | **(118.85, 100.00)** | 7.54 mm B.Cu + 1 via to U6 pin 45 |

**107.68 mm of track and 5 vias removed, 7.54 mm and 1 via added.** The freed
copper went back to the pour: F.Cu GND 946.91 → 972.58 mm², B.Cu GND 828.88 →
875.17 mm².

Measured clearances of the new lands, against every other net's copper on B.Cu:

| land | nearest copper of any net | nearest analog / ADC net |
|---|---|---|
| SDA (104.10, 125.95) | `/HEATER_PWM` 0.250 mm | `/CELL_CE` **1.551 mm** |
| SCL (118.85, 100.00) | `/AFE_MENB` 0.279 mm | `/CE_MON` **1.657 mm** |

Against 0.100 mm before: **15x** on the quantity that mattered. The two nearest
neighbours that remain are digital — `/HEATER_PWM` is the MCU's gate drive and
`/AFE_MENB` the LMP91000 module-enable, a static line.

DRC after the change is identical to the accepted baseline: **12 warnings, 0
errors, 0 unconnected, 0 parity.** No firmware quiet-bus rule is owed any more;
the one proposed under the withdrawn disposition is not needed and was never
implemented.

### The sensitive-net set was too narrow, and that is part of this finding

The reviewer's own counterexample placed SCL 0.119 mm from `/CE_MON` and SDA
0.150 mm from `/3V3A`. `/CE_MON` is a 91k/91k tap off `/CELL_CE_DRV` into U6 pin
15; `/VA_MON` and `/VIN_MON` are the same shape; `/ADC_WE_BUF`, `/ADC_RE_BUF`
and `/ADC_AFE_VOUT` are the buffered cell measurements. All are ADC inputs behind
tens of k of source impedance, and none of them was in `reroute_net.SENSITIVE`.
They are now. Every number above is measured against the widened set.

### What this costs, stated plainly

**J107 is no longer one block — it is no longer even one part.** Its 3V3D, GND
and UART lands stay in the row at the cable end as J107; the I2C pair is up the
board, and since later on 2026-09-14 they are two separate components, **J108**
(SDA) and **J109** (SCL). A lead for an external TMP117 therefore lands its power
pair and its signal pair in two places, inside the potting, instead of leaving
with the cable. Part count 85 -> 87.

**The I2C pair ended up adjacent after all.** Fab placed J108 himself once it was
its own part: (104.10, 125.95) -> **(118.82, 101.97)**, 1.97 mm from J109, and
routed it — 5.32 mm and 2 vias. That is the adjacency this document earlier
recorded as unreachable *with the lands as pads of one footprint*, and it is
reachable now for exactly that reason. The cost is measured and on record in
`routing/revb-86-ring/README.md`: the new SDA run passes 0.235 mm from
`/CE_MON` over ~0.6 mm, against 1.551 mm at the tip site it left. Legal against
the 0.100 mm rule, tighter than the 0.50 mm margin the router holds itself to,
and a corner rather than a parallel run.

The split is what makes the lands placeable. Pads inside a footprint cannot be
dragged in pcbnew except in Pad Edit Mode, and a footprint edited that way no
longer matches its library — `lib_footprint_mismatch`. Fab asked to ungroup them
so he could place them himself, tried it, and reported the pads still moved
together; three parts is the only real ungroup. `tools/split_j107_i2c.py` does
it deterministically and moves no copper: J108 and J109 land exactly where pads
3 and 4 were, keeping the measured silk offsets, so DRC stays at the accepted
12 / 0 / 0 / 0. Each gets a courtyard the size of its own pad and no larger —
at pad-plus-0.15 the SDA land collides with RH1's courtyard, and a footprint
with none at all is a `missing_courtyard` error.

That is forced, not chosen. A search over the whole board for a site holding a
complete four-land block (3V3D, GND, SDA, SCL as 1.6 x 1.2 lands, every land
0.30 mm from all copper and 2.00 mm from every analog net, inside the outline and
clear of the slots and of every back courtyard) found **zero** sites, at any
pitch and either orientation; a three-land group exists only at x 116.4,
Y 120.5..125.7, which still splits the lead. The board is 20 x 86 mm and the AFE
spans its width.

The lands are labelled `SDA` and `SCL` on B.SilkS where they are, and the Design
Notes on J107, J108 and J109 each name the other two, so nobody has to infer the
split from the board.

## 2. New tip ground-return dependencies — ACCEPTED, with the numbers

The tip re-route left two F.Cu ground pockets that are now reached over
dependent paths rather than by plane:

- **U10.2 and C20.2**: a 14.63 mm² F.Cu component reached through four 0.15 mm
  tracks totalling 6.373 mm and three vias, with the transitions at
  (106.1, 132.35) and (103.35, 132.15) each individually indispensable.
- **U12.4**: a 0.832 mm² pocket depending on the single 0.4/0.2 via at
  (102.3, 135.9).

Measured annular contact is ~95–100 %, so these are real connections, not
slivers, and the reviewer confirmed every GND component reaches input ground.
U10 is the cell-side TMP117 and U12 the humidity sensor — both low-current
digital parts, so the inductance of a 6.4 mm return is not load-bearing for
them. Accepted as documented, not as ideal.

## 3. Spreader thermal corridor is 0.68 mm — CONNECTIVITY ONLY

`HEATED_ISLAND_SPREADER` refills as one 215.13 mm² island holding both back J5
lands, RH1.2, RH2.2 and Q2.3. The neck feeding the **left** land measures
**0.6796 mm** at its narrowest (around X 108.825, Y 138.02..138.70), confirmed
independently by polygon erosion.

That establishes **connection, not conductance.** The θ = 68 K/W figure measured
on Rev A (`aa6133d`) was taken on a different tip geometry and is **not**
transferred to this board. Whether 0.68 mm of 1 oz copper spreads enough heat
into the left half of the ring is unmeasured and must be measured on a built
board before any thermal claim is made.

## 4. Hand-solder lands carry no paste — RESOLVED, not accepted

J5 and J107 emitted 2.8 × 2.0 mm and 1.6 × 1.2 mm paste apertures. Fab,
2026-09-14: hand solder only, no pre-tinning. Paste layers removed from both
footprints in `lib/o2-probe.pretty/` and from the board, so library and board
agree; the verifier now pins the paste-free pad layer sets. This is a fix, and
is listed here only so the review's finding 5 has a visible outcome.
