# Cable preparation: stripping the farm cable

Companion to [`CABLE-SOURCING.md`](CABLE-SOURCING.md), which picked the cable.
This picks the tools that open it. It exists because the cable that was actually
ordered is **thinner than the working range of every common jacket stripper**,
and that is not obvious until you check the numbers.

**Decision: JOKARI Kabelmesser No. 16 SECURA, Art.-Nr. 10160, €19,00 UVP**,
used 0,2 mm below its published 4 mm minimum, because its inner-blade depth is
adjustable by hand.

**Superseded 2026-09-13, same day: the first version of this note chose the
Fibre Strip DC (Art. 30700)** on the grounds that it was the only tool whose
published range contains 3,8 mm. §3 records why the field evidence reversed
that — its fixed cut depth fails in exactly the way §3.1 predicted it might.

Research date 2026-09-13. Tool ranges taken from `jokari.de` product pages and
`knipex.de`, cable figures from the automation24 technical-data table for the
ordered article. Not yet validated against the physical cable.

---

## 1. What has to be opened

From `CABLE-SOURCING.md` §0, ordered 2026-09-05: **LAPP UNITRONIC SENSOR FD
Lif9Y11Y 4x0,25, article 7038890**.

| | |
|---|---|
| **outer diameter** | **3,8 mm** |
| jacket | PUR, black, halogen-free, flame-retardant |
| cores | 4 x 0,25 mm², **unshielded** |
| core insulation | PP |
| rated | 300 V, drag-chain class 6, −40…80 °C fixed / −25…80 °C flexed |

Verified 2026-09-13 on automation24's own technical-data table (`Außendurchmesser
Mantel 3,8 mm`, `Werkstoff Mantel PUR`, `Aderisolation PP`). `lapp.com` itself
returns HTTP 403 to a plain-Chrome-UA curl; automation24 and letronic both serve
the data unprotected.

Two properties drive everything below:

- **3,8 mm is very thin for a 4-core jacket.** It is the same geometry as
  Truebner's TrueFlex, which is why `CABLE-SOURCING.md` §0 accepted it.
- **PUR is tough and elastic.** It does not snap after a circumferential score
  the way PVC does. Techniques that work on NYM do not transfer.

## 2. The survey: 3,8 mm falls in a gap

Every tool named in the first pass of this question is out, in one direction or
the other. Ranges as published by the makers, checked 2026-09-13:

| tool | published range | verdict at 3,8 mm |
|---|---|---|
| JOKARI **CAN-Strip**, Art. 30013 | PTFE jackets, **max. Ø 3,5 mm** | **too thick** — 3,8 > 3,5 |
| JOKARI **Fibre Strip DC**, Art. 30700 | round cable **up to 5,9 mm**, no lower bound published | in range, **rejected in §3** |
| JOKARI Allrounder | 4–15 mm round / to 15 mm flat | 0,2 mm below minimum |
| JOKARI Strip No. 14 | 4–13 mm | 0,2 mm below minimum |
| JOKARI **Kabelmesser No. 16 SECURA**, Art. 10160 | 4–16 mm | 0,2 mm below minimum — **chosen, §4** |
| JOKARI PC-CAT | 4,5–10 mm | no |
| JOKARI Top Coax Plus | 4,8–7,5 mm | no |
| JOKARI PC-Strip | 5–13 mm | no |
| JOKARI SECURA No. 15 | 8–13 mm | no |
| KNIPEX ErgoStrip 16 95 01 SB | 8–13 mm round, 4,8–7,5 mm coax | no |
| KNIPEX STX60 16 45 220 | 30–60 mm | no |

So the usable window is a 0,4 mm slot between the CAN-Strip's 3,5 mm ceiling and
the 4 mm floor of the general-purpose tools.

**The CAN-Strip is doubly excluded**, which is worth stating because its name
invites the guess. JOKARI describe it as an *"Entmanteler zum Abmanteln von
geschirmten Data Bus Twisted Pair Leitungen mit einer hoch temperaturbeständigen,
mikrodünnen PTFE Ummantelung"* — wrong jacket material *and* 0,3 mm too small,
for €112.

## 3. Why the fixed-depth tool was rejected

The first version of this note chose **JOKARI Entmanteler Fibre Strip DC,
Art.-Nr. 30700** (EAN 4011391307001, €26,00 UVP, listed on amazon.de at €16.95),
because it is the only surveyed tool whose published range contains 3,8 mm. It
is no longer the recommendation.

### 3.1 The concern, stated before the evidence was looked for

The tool carries one property that was flagged as needing respect rather than
assumption:

> *"Eine Einstellung der Klingen auf die Schnitttiefe ist nicht erforderlich."*

**The cut depth is fixed, not adjustable.** That works only because the blade
geometry is calibrated for one jacket class — and the class JOKARI name is not
ours: *"Access Kabel … z.B. DAC-Direct Access Cable aus der Serie der LWL-Kabel
Single mode"*. A fibre access cable's jacket is typically LSZH or PVC; ours is
PUR, tougher and more elastic at the same wall thickness. Two opposite failure
modes follow — **under-cut**, where the blade scores the PUR without severing it
so the jacket stretches instead of parting, and **over-cut**, where a thinner
wall than a DAC's at the same OD lets the fixed depth reach the PP core
insulation. LAPP publish no jacket wall thickness for 7038890, so neither could
be settled on paper.

### 3.2 The field evidence says under-cut, on the tool's own intended cable

Amazon.de listing B00KZE9KI4 (read 2026-09-13 through a headless browser; curl
returns a 3,8 kB block page): **3,2 out of 5 stars, n = 8, zero reviews from
Germany.** The one review with legible body text — Damien D., France,
20 March 2021, 3 stars, verified purchase:

> *"Il fonctionne bien mais il ne permet de dénuder entièrement le cable."*

It works, but it does not strip the cable completely. **That is §3.1's under-cut
mode, reported by a user on the tool's intended cable class.** Our PUR is the
harder case, not the easier one.

**The rating pattern across JOKARI's own range is one-directional**, and that is
what lifts this above an n = 8 anecdote. From the same listing's comparison and
recommendation strips:

| fixed cut depth | rating (n) | | adjustable | rating (n) |
|---|---|---|---|---|
| AS-Interface Strip | 2,7 (3) | | Secura Super No. 15, T30120 | 4,8 (4 098) |
| **Fibre Strip DC** | **3,2 (8)** | | Super 4 Plus, T20050 | 4,7 (30 548) |
| Fibre Strip LC | 3,5 (7) | | Coaxi No. 1, 30600 | 4,7 (779) |
| Fibre Strip LC-PUR | 3,1 (12) | | T30140 flat cable | 4,7 (856) |
| | | | 30150 FP | 4,5 (2 428) |
| | | | COAX T30010 | 4,7 (1 082) |

Every no-adjustment tool sits at 2,7–3,5. Every adjustable tool sits at 4,5–4,8,
on sample sizes two to three orders of magnitude larger. The mechanism and the
distribution agree.

**Weigh the evidence honestly.** n = 8 is small, one legible review body is
thin, and Amazon ratings conflate "wrong tool for my cable" with "bad tool". On
its own that would not overturn a datasheet-based choice. What makes it decisive
here is that the reported failure is *the specific one predicted from the
datasheet*, and that the family-wide split falls exactly along the
adjustable/fixed line.

**The LC-PUR variant does not rescue this.** JOKARI do ship a PUR-named tool in
the family — Fibre Strip LC-PUR, Art.-Nr. 30810 — but its range is **LWL-Kabel
ab Ø 6 mm**, well above our 3,8 mm, and it rates 3,1 (12).

## 4. The chosen tool, and its compromise

**JOKARI Kabelmesser No. 16 SECURA, Art.-Nr. 10160**, EAN 4011391101609,
€19,00 UVP, published range 4–16 mm, 132x29x35 mm, 74 g, spare TiN blade
included, polyamide housing.

Its decisive property, from JOKARI's own description:

> *"Die Schnitttiefe des Innenmessers ist durch eine Einstellschraube am
> Griffende einstellbar"*

**Adjustable cut depth**, with circumferential/longitudinal selection automatic.
That is precisely what §3 shows a fixed-depth tool cannot offer against an
uncharacterised jacket wall, and it puts the tool in the 4,5–4,8 half of §3.2's
table.

**State the compromise plainly: 3,8 mm is 0,2 mm below its published 4 mm
minimum.** The 4 mm figure bounds the guide body; the blade depth is set by
hand. This is expected to work and JOKARI do not sanction it. The trade is
deliberate — being marginally under a *guide* dimension with a blade you control
is a smaller risk than being on the wrong jacket material with a blade you do
not.

**Still sacrifice 20 cm.** The cable is €1,70/m Meterware and the run is 10 m
with a small number of ends; an offcut costs about 34 cents. Set the depth on
the offcut, strip it, and inspect all four PP core insulations under
magnification for score marks before the tool touches a real termination. With
an adjustable tool this is a calibration step rather than a gamble.

**Do not reach for a scalpel.** For a handful of ends that would normally be
defensible, but PUR is the worst jacket for score-and-flex: it stretches rather
than snapping, so the cut turns into sawing, and sawing over 0,25 mm² cores is
how a strand gets nicked. A nicked strand on a buried probe is a fault that
appears months later.


## 5. Core stripping — a separate tool

0,25 mm² cores in **PP** insulation: thin, slippery, and easy to stretch. The
jacket tool does not address them.

| option | range | UVP | note |
|---|---|---|---|
| JOKARI **SECURA 2K**, Art. 20100 | 0,2–6,0 mm² / AWG 24–10 | €46,00 | specified by **cross-section**, so 0,25 mm² is unambiguous |
| KNIPEX ErgoStrip 16 95 01 SB | 0,2–4,0 mm² | ~€25 | already covers it; its jacket function is useless here, its core function is not |
| JOKARI **PWS-PLUS 002**, Art. 40025 | conductor 0,25–0,80 mm Ø / AWG 30–20 | €36,00 | precision option; steps 0,25/0,30/0,40/0,50/0,60/0,80 mm, length stop 1,5–22 mm |

Two caveats on the PWS-PLUS 002, which is otherwise the nicest tool of the three:

- Its range is stated as a **conductor diameter**, not a cross-section.
  0,25 mm² stranded is about 0,55–0,6 mm bare (AWG 24), which lands inside
  0,25–0,80 mm — but that is a derivation, not a JOKARI statement about this
  cable, so confirm the setting on the offcut alongside the jacket test.
- JOKARI list it as ideal for PVC, TEFLON, KYNAR, TEFZEL and MYLAR. **PP is not
  on that list.** Probably immaterial, but it is an absence, not an endorsement.

For a soldered field joint the cores are stripped ~5 cm back and staggered —
see `CABLE-SOURCING.md` §5.1, which takes the procedure from Truebner.

## 6. An unplanned consequence of the OD change

`CABLE-SOURCING.md` §5.1 names **CellPack SRH2 8/2** (Voelkner X774691, €8,21,
EAN 4010311009223) as the adhesive-lined outer sleeve for Truebner's splice
method, and then warns that it is *"sized for TrueFlex, not for the recommended
cable"* — an 8 mm sleeve shrinking to 2 mm suits TrueFlex's 3,8 mm OD but will
not pass over ÖLFLEX ROBUST 215 C at 6,6 mm.

That warning was written against the §3 recommendation. **What was actually
ordered is 3,8 mm**, the TrueFlex geometry — so SRH2 8/2 is the correctly sized
part after all, and the caution in §5.1 no longer applies to the cable on order.
Anyone reading §5.1 in isolation will size the sleeve up unnecessarily.

## 7. Buy list

| item | article | qty | UVP |
|---|---|---|---|
| JOKARI Kabelmesser No. 16 SECURA | 10160 | 1 | €19,00 |
| core stripper — SECURA 2K, or nothing if an ErgoStrip is already on the bench | 20100 | 0–1 | €46,00 |
| ~~JOKARI Entmanteler Fibre Strip DC~~ | ~~30700~~ | 0 | rejected, §3 |

## 8. Open

- **Measure the delivered OD with calipers at two or three points before
  ordering any tool.** Every table above turns on the catalogue figure of
  3,8 mm. If the cable measures 4,0 mm or more, the Kabelmesser No. 16 SECURA
  comes into specification outright and §4's compromise disappears — as do the
  Allrounder and Strip No. 14 as alternatives. This is the same measurement
  `CABLE-SOURCING.md` §5 already holds the cable gland on — one caliper reading
  closes both.
- Jacket wall thickness is unpublished for 7038890. The offcut calibration in §4
  is the substitute; if a wall figure is ever obtained from LAPP, record it here.
- **§3.2's evidence is Amazon ratings, not a measurement.** If the No. 16 SECURA
  turns out not to close on 3,8 mm at all, the Fibre Strip DC is still in range
  and costs €16.95 — reopen it rather than treating §3 as settled forever.
- Nothing in this note has been validated against physical cable.
