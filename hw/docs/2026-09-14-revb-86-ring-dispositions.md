# Rev B 86 mm ring board — accepted-risk dispositions, 2026-09-14

Dispositions for the findings of the 2026-09-13 independent review
(`2026-09-13-revb-86-ring-codex-review.md`) that are **accepted rather than
fixed**. Each says what was measured, who decided, and what would refute it.
None of these is a qualification: no board has been built.

## 1. I2C runs at minimum clearance past the analog front end — ACCEPTED (Fab, 2026-09-14)

**Measured.** J107's flying-lead I2C pads are routed at the board minimum
0.100 mm from two analog nets:

| new J107 copper | beside | gap | parallel length | gap on accepted revb-86 |
|---|---|---|---|---|
| SCL, B.Cu, X 101.1..101.2, Y 100.0..113.85 | `/GUARD_REPLICA` (X 101.5, 0.25 mm wide) | 0.100 mm | ~9 mm | 0.625 mm |
| SDA, F.Cu, X 118.35..118.95, Y 96.6..102.4 | `/VREF_TRIM` (0.15 mm wide) | 0.100 mm | ~6 mm | not adjacent |

DRC is silent because 0.100 mm *is* the rule. The concern is coupling, which no
clearance rule expresses.

**Not fixable by routing — measured, not assumed.** Flood-fill reachability over
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

**Decision.** Fab, 2026-09-14, presented with all three options (drop SDA/SCL,
accept, drop J107 entirely): **accept the coupling and fab as routed.**

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
as AFE_VOUT moving with bus activity. If that appears, the fix is a layer count
or a J107 without I2C, not a reroute; this page records that a reroute was
already proven impossible.

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
