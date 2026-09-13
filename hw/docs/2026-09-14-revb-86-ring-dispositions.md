# Rev B 86 mm ring board — accepted-risk dispositions, 2026-09-14

Dispositions for the findings of the 2026-09-13 independent review
(`2026-09-13-revb-86-ring-codex-review.md`) that are **accepted rather than
fixed**. Each says what was measured, who decided, and what would refute it.
None of these is a qualification: no board has been built.

## 1. I2C runs at minimum clearance past the analog front end — DISPOSITION WITHDRAWN 2026-09-14

**Measured.** J107's flying-lead I2C pads are routed at the board minimum
0.100 mm from two analog nets:

| new J107 copper | beside | gap | parallel length | gap on accepted revb-86 |
|---|---|---|---|---|
| SCL, B.Cu, X 101.1..101.2, Y 100.0..113.85 | `/GUARD_REPLICA` (X 101.5, 0.25 mm wide) | 0.100 mm | ~9 mm | 0.625 mm |
| SDA, F.Cu, X 118.35..118.95, Y 96.6..102.4 | `/VREF_TRIM` (0.15 mm wide) | 0.100 mm | ~6 mm | not adjacent |

DRC is silent because 0.100 mm *is* the rule. The concern is coupling, which no
clearance rule expresses.

> **WITHDRAWN.** This section claimed the coupling was unavoidable. A second
> independent review disproved that, and the claim below is scoped wrongly: it was
> measured **with J107's pads where they are**, then written as if it held for any
> placement. Fab's 2026-09-14 acceptance was given on the strength of an
> impossibility that does not hold, so the acceptance does not stand on this text.
> See **1b** for what is actually true and what the real choice is.

**Not fixable by routing WITH J107'S PADS FIXED — measured, not assumed.** Flood-fill reachability over
the whole board, with every sensitive net (`/CELL_*`, `/GUARD_REPLICA`,
`/LMP_*`, `/TMP_CELL*`, `/VREF*`, `/AFE_VOUT`) inflated by only **0.1 mm** beyond
ordinary clearance, ripping the **entire** J107 I2C route and permitting a join
**anywhere** on the bus:

    /I2C_SCL   target reachable: False   closest approach 3.29 mm
    /I2C_SDA   target reachable: False   closest approach 3.02 mm

Leave-one-out identifies the wall: SCL is blocked by the `/CELL_*` nets, SDA by
`/VREF_TRIM`. On 20 mm of two-layer board the AFE spans the width; the only
corridor to the MCU's I2C is the one already taken, at minimum clearance. The
alternatives were therefore to drop the pads or to accept the coupling.

**Decision, now superseded.** Fab, 2026-09-14, presented with three options (drop
SDA/SCL, accept, drop J107 entirely): accept the coupling. That choice was made
without the fourth option in **1b**, which was not known at the time.

**What this costs, stated plainly.** `/GUARD_REPLICA` is a driven guard and
`/VREF_TRIM` a buffered reference with C10/C26 bypass, so both are low-impedance
victims rather than high-impedance ones — but `/VREF_TRIM` is the ADC reference,
and the cell-side TMP117 (U10, 0x49) is read over this same bus, so I2C traffic
does occur close in time to conversions. Coupling has **not** been measured or
simulated; any capacitance figure in this repo would be invented. It is an
accepted risk, not a quantified one.

**Standing mitigation, to be enforced in firmware.** Keep the bus quiet during
an ADC conversion: no I2C transaction may overlap a `/VREF_TRIM`-referenced
conversion. This is a firmware rule, not a board property, and it is **not yet
implemented** — treat it as owed work, not as a control already in place.

**What would refute this disposition.** A built board showing O2 or VREF noise
correlated with I2C traffic — visible as steps in `gas_*` at poll boundaries, or
as AFE_VOUT moving with bus activity. If that appears, the fix is the pad
relocation in 1b, a layer count, or a J107 without I2C.

## 1b. There IS a fourth option: move the two I2C pads off the cable-end row

The second independent review (2026-09-14) found, without using this repo's
router, that relocating **individual J107 pads** gives far better clearance:

| net | relocated pad centre (B.Cu) | joins bus at | new track | min gap to sensitive copper |
|---|---|---|---|---|
| SDA | (108.650, 106.200) | (110.650, 107.450) | 2.358 mm | **3.513 mm** |
| SCL | (113.800, 95.025) | (115.250, 95.800) | 1.644 mm | **3.700 mm** |

Same 1.6 x 1.2 mm pads, same 0.15 mm track, **no new vias**, spreader still one
island. That is a ~35x improvement on the 0.100 mm this board currently has, and
it makes the coupling risk go away rather than accepting it.

**What it costs, verified here.** Those two positions are **33.5 mm and 44.7 mm
away from the J107 row at Y 61.5**, in the dense middle of the board: the band
Y 93..108 carries **417** B.Cu segments against **6** in Y 55..62, and the
nearest neighbours are R11, R32, C33 and C7. So J107 stops being one six-pad
connector at the cable end. The I2C pair becomes two isolated lands mid-board,
which a flying lead can only reach by running back along the assembly rather
than leaving with the cable — the thing the connector was for
(Fab: *"add a smd solderpad connector: 3.3V, GND, SDC, SCL for an external
tmp117"*).

**Status: open. Fab's call, not decided here.** The trade is *pads where the
cable leaves, at 0.100 mm from the guard and the ADC reference* versus *3.5 mm
of clearance with the I2C pads in the middle of the board*. Until that is
decided, no gate may issue: `ACCEPTED_RISKS` still names
`i2c-at-minimum-clearance-from-guard-and-vref`, and that risk is no longer
supported by an impossibility argument.

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
