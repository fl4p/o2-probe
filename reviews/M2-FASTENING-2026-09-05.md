# M2 fastening for the head-end: sourcing and design rules

2026-09-05. Written because Fab asked for the head's screw holes to receive **M2
metric screws**, and the file's M2.5 numbers were a mix of one sourced part
(E-Z LOK), one inferred number (the insert hole depth) and one placeholder with
its rationale explicitly disowned in the comment (`pt_pilot_d`).

The sizes below are now cited from `cad/o2_probe_head_end.scad` and
`cad/membrane_cartridge_common.scad`.

## What "M2" can mean here, and which one this is

Only the **insert** route actually receives an ISO metric M2 screw. A
thread-forming screw cuts its own thread, and that thread is not ISO metric: EJOT's
DELTA PT flank is 20°/30° with a 140° root transition, deliberately unlike the 60°
ISO profile, because the plastic female thread has to spread the stress. Tapping a
real M2 thread into a printed boss is supported by none of the design guides read
here and is not offered as a route.

Both routes were resized to nominal 2.0 anyway, so the choice stays open.

## Route A — heat-set insert (receives a true M2 screw)

**PennEngineering SI, IUTFC-M2, 300-series stainless**, flanged, straight wall,
thru-threaded. Stainless for the same reason the M2.5 part was: brass suffers
ammonia stress-corrosion cracking, and these sit outside the seal in NH₃
condensate.

| | IUTFC-M2 (chosen) | IUTC-M2 (unflanged) | E-Z LOK FL-M25 (previous, M2.5) |
|---|---|---|---|
| hole Ø in plastic | **3.23** +0.08/−0.00 | 3.23 +0.08/−0.00 | 3.99 |
| min hole depth | **4.76** (published) | 3.94 / 4.76 | *none published* — 6.7 was inferred |
| length A | 3.99 ±0.13 | 3.18 or 4.0 ±0.13 | 5.74 |
| flange / knurl Ø | **4.75** | 3.73 | 5.54 |
| flange thickness | **0.46** | — | 0.61 |

Three things improved at once:

1. The bore dropped 3.99 → 3.23 and the flange 5.54 → 4.75.
2. **The hole depth is published.** `insert_bore_h` was a cross-manufacturer
   inference (SPIROL's rule applied to an E-Z LOK body) carrying a "verify on a
   coupon" caveat. PEM states 4.76 outright, and SPIROL's rule independently gives
   3.99 + 2×0.4 = 4.79 — agreement to 0.03 mm, which is what makes the published
   number believable rather than merely authoritative.
3. The sourcing objection went away. E-Z LOK is a sole-source US import that every
   EU specialist made special-order; IUTFC-M2 and IUTC-M2 are catalogue items.

SPIROL's design guide also supplies two things the model now carries:

- boss OD 2–3× insert diameter (2 × 3.73 = 7.46 around a 3.23 hole → 2.115 mm
  wall). `insert_seal_wall` stays at **2.3**, above that: its binding constraint is
  thermal, not structural — 200 °C+ a millimetre from the O-ring's sealing surface
  bulges the seat, and that does not care which insert it is.
- filler correction: open the hole +0.08 at ≥15 % filler, +0.15 at ≥35 %,
  interpolating between. `insert_filler_add` is 0 for unfilled ASA and exists so a
  filled grade is a one-line change rather than a recalculation.

## Route B — thread-forming (nominal 2.0)

**EJOT DELTA PT size 20**, nominal Ø2.0 +0.08, A2, or an equivalent Plastite/PT.
From EJOT/ATF's design-recommendations page, with d1 = 2.0:

| rule | value |
|---|---|
| core hole `db = 0.8 × d1` (± screw tolerance) | **1.60** |
| — for filled or higher-strength material, up to `0.88 × d1` | 1.76 |
| boss OD `dO = 2 × d1` | 4.00 |
| counterbore `dC = 1.05 × d1`, depth `0.5 × d1` | **2.10 × 1.00** |
| installation depth `di = 2 × d1` | 4.00 |
| core-hole draft | ≤ 0.5° per side |

Two corrections to the file:

- `pt_pilot_d` was 2.1 against a 2.5 nominal. The comment correctly called
  "0.75 × nominal" false arithmetic — but the real rule is **0.8**, and 2.1/2.5 =
  0.84 sits inside EJOT's 0.80–0.88 band. The old value was defensible for a
  reason nobody had.
- **The counterbore was missing, and it is structural.** EJOT: it relieves edge
  stress and is what prevents boss cracking as the thread forms, as well as acting
  as the lead-in. It is now cut on the thread-forming route too, and because
  2.10 > 1.60 the counterbore — not the pilot — is the widest cut at the bolt
  circle. `bolt_cut_max` was moved above `bolt_r` so the circle is *derived* from
  the widest cut instead of being checked against it afterwards.

## Clearance holes

**Reihe "mittel"** (medium): **M2 → 2.4** (fein 2.2, grob 2.6). `m2_clear = 2.4`
replaces `m25_clear` throughout the head-end model.

`m25_clear = 2.8` is left in place for `o2_probe_head.scad`'s captive-nut ports,
with a note that it matches **no** row of the standard (M2.5 is 2.7 / 2.9 / 3.1)
and sits between fein and mittel.

**Primary, since 2026-09-05.** This row was written second-hand — ISO paywalls
clause 2, its OBP entry serves only the foreword and scope, and the ANSI preview
PDF stops before the table — from a distributor chart naming the standard. Fab
then supplied the clause-2 *Maße* table of **DIN EN 20273**, the German adoption
of ISO 273, and it agrees exactly:

| d | fein | mittel | grob |
|---|---|---|---|
| 1.6 | 1.7 | 1.8 | 2 |
| **2** | 2.2 | **2.4** | 2.6 |
| 2.5 | 2.7 | 2.9 | 3.1 |
| 3 | 3.2 | 3.4 | 3.6 |

Two notes on what that page does and does not say. It labels the columns
**fein / mittel / grob** only — the H12/H13/H14 grade names used elsewhere in this
document come from the distributor chart, not from the DIN table, and are carried
as attribution rather than as something read in the standard. And the page is
licensed material: it is cited here, not copied into the repo
(sha256 `641967a7…3e3a8a` of the supplied scan, for provenance only).

## What it costs — measured, not assumed

Rendered both routes (cone bed, provisional measured-ins):

| | ptscrew | insert |
|---|---|---|
| head OD | **38** | **44** |
| bolt circle Ø | 30.2 | 33.93 |
| wall to sealing bore | 1.2 | 2.3 |

The M2 insert is a smaller part, so the 6 mm diameter penalty in the
`fastening` comment looked like it should have shrunk. **It did not.** What
separates the routes is the wall — `insert_seal_wall` 2.3 (thermal) against
`pt_seal_wall` 1.2 (EJOT's boss rule) — not the hole, and the hole is the only
thing that got smaller. So `ptscrew` stays the default, and the "6 mm" figure in
that comment is now a measured number at M2 rather than an inherited one.

## Open — the coupon

Every number above comes from a vendor design guide, and all of those guides are
written for **moulded** bosses. Nothing has been put in printed ASA yet, where the
boss is layered, anisotropic, and weakest exactly where the thread-forming hoop
stress acts.

`part="fastener-coupon"` builds a 35.9 × 12.4 × 6.5 mm test block from the head's
own parameters, printed the same way up as the head (holes entering the top face,
because the head prints cable-end-down). Four stations:

| # | hole | question |
|---|---|---|
| 0 | insert 3.23 + flange counterbore | does an IUTFC-M2 heat-set square and flush? |
| 1 | insert 3.13 — deliberately 0.1 tight | which side of +0.08/−0.00 does a printed hole land on? |
| 2 | PT pilot 1.60 + 2.10 × 1.00 counterbore | does a DELTA PT 20 form a thread without splitting the boss? |
| 3 | PT pilot 1.60, **no** counterbore | control for EJOT's claim that the counterbore is what stops the cracking |

Sliced on the ASA sealing profile — deliberately, since the point is how a boss
behaves in the process the part is printed in — and it passes `seal_check.sh`.
13 m 22 s, 2.68 cm³.

    make -C cad head-end-provisional   # or: openscad -D 'part="fastener-coupon"' ...
    ./print.sh slice fastener-coupon
    ./print.sh upload fastener-coupon
    ./print.sh start  fastener-coupon

## Sources

| source | state | route | notes |
|---|---|---|---|
| EJOT/ATF, *DELTA PT — predictable performance improvement for thermoplastics*, 2017 — `ejot-atf.com/wp-content/uploads/2017/02/ATFDELTAPT2017HighRes.pdf` | inspected: design-recommendations page, tolerance table p.16 | text layer | 200, 11.5 MB |
| PennEngineering, *SI Inserts For Plastics*, pp. SI-6, SI-7 — `pemnet.com/wp-content/uploads/sites/2/2022/06/sidata.pdf` | inspected: metric tables | **re-read from 170 dpi page renders** | the PDF's text layer scrambles these columns and must not be used for them |
| SPIROL, *Inserts for Plastics Design Guide*, pp. 4–5 — `spirol.com/assets/files/ins-threaded-inserts-design-guide-us.pdf` | partial: plastic-component guidelines | text layer | boss OD, hole depth rule, filler correction |
| ISO 273:1979 — `iso.org/standard/4183.html`, OBP `#!iso:std:4183:en` | **metadata only** — identity and edition confirmed (1st ed. 1979-06-01, corrected 1992-07); clause 2 paywalled | DOM / text | ANSI preview: curl rung 1 → 403 Cloudflare; rung 2 (Sec-Fetch + referer) → 200, 4 pages, ends before the table |
| **DIN EN 20273**, clause 2 *Maße*, Durchgangsloch d_h table | **inspected** — the clearance row's primary; supplied by Fab as a page scan, 2026-09-05 | rendered page | licensed, not archived here; sha256 `641967a7552a634d8793b400570e8addf26a7047d868c0933169a80f863e3a8a` |
| Albany County Fasteners clearance-hole chart, citing ISO 273 | inspected: metric table | text layer | was the sole numeric source; now corroborating, and the source of the H12/H13/H14 grade names the DIN page does not carry |
| PEM product pages `IUTC-M2`, `IUTFC-M2` | metadata only — existence and description | text layer | both are catalogue items |

Distributor stock and price for IUTFC-M2 were **not** verified. That is the next
sourcing action if the insert route is ever chosen.
