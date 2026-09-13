# Cable preparation: stripping the farm cable

Companion to [`CABLE-SOURCING.md`](CABLE-SOURCING.md), which picked the cable.
This picks the tools that open it. It exists because the cable that was actually
ordered is **thinner than the working range of every common jacket stripper**,
and that is not obvious until you check the numbers.

**Decision: JOKARI Entmanteler Fibre Strip DC, Art.-Nr. 30700, €26,00 UVP** —
the only surveyed tool whose range contains 3,8 mm. **Test it on an offcut
before the first real end**; §3 says why that is not optional.

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
| JOKARI **Fibre Strip DC**, Art. 30700 | round cable **up to 5,9 mm**, no lower bound published | **only candidate** |
| JOKARI Allrounder | 4–15 mm round / to 15 mm flat | 0,2 mm below minimum |
| JOKARI Strip No. 14 | 4–13 mm | 0,2 mm below minimum |
| JOKARI **Kabelmesser No. 16 SECURA**, Art. 10160 | 4–16 mm | 0,2 mm below minimum |
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

## 3. The chosen tool, and the reason for the offcut test

**JOKARI Entmanteler Fibre Strip DC, Art.-Nr. 30700**, EAN 4011391307001,
€26,00 UVP, 23 g, 100x18x18 mm, polyamide housing, TiN-coated blades.

It is the only tool whose published range contains 3,8 mm. It carries one
property that must be respected rather than assumed away:

> *"Eine Einstellung der Klingen auf die Schnitttiefe ist nicht erforderlich."*

**The cut depth is fixed, not adjustable.** That is workable only because the
blade geometry is calibrated for one jacket class — and the class JOKARI name is
not ours: *"Access Kabel … z.B. DAC-Direct Access Cable aus der Serie der
LWL-Kabel Single mode"*. A fibre access cable's jacket is typically LSZH or PVC;
ours is PUR, which is tougher and more elastic at the same wall thickness.

Two failure modes follow, and they are opposite:

- **Under-cut** — the blade scores the PUR without severing it, the jacket
  stretches instead of parting, and you end up worrying it off.
- **Over-cut** — if our jacket wall is thinner than a DAC's at the same OD, the
  fixed depth reaches the PP core insulation. LAPP publish no jacket wall
  thickness for 7038890, so this cannot be settled on paper.

**Therefore: sacrifice 20 cm.** The cable is €1,70/m Meterware and the run is
10 m with a small number of ends; an offcut costs about 34 cents. Strip it,
then inspect all four PP core insulations under magnification for score marks
before the tool touches a real termination.

## 4. Fallback if it will not bite PUR

**JOKARI Kabelmesser No. 16 SECURA, Art.-Nr. 10160**, EAN 4011391101609,
€19,00 UVP, 4–16 mm, spare TiN blade included.

Its decisive property, from JOKARI's own description: *"Die Schnitttiefe des
Innenmessers ist durch eine Einstellschraube am Griffende einstellbar"* —
**adjustable cut depth**, with circumferential/longitudinal selection automatic.
Depth adjustment is exactly what a fixed-depth tool cannot offer on an
uncharacterised jacket wall.

**State the compromise honestly: 3,8 mm is below its published 4 mm minimum.**
The 4 mm figure bounds the guide body, and the blade depth is set by hand — so
this is expected to work, but it is out of specification and JOKARI do not
sanction it. It is a fallback, not the recommendation.

**Do not reach for a scalpel here.** For a handful of ends that would normally be
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
| JOKARI Entmanteler Fibre Strip DC | 30700 | 1 | €26,00 |
| JOKARI Kabelmesser No. 16 SECURA — fallback, order only if §3's test fails | 10160 | 0–1 | €19,00 |
| core stripper — SECURA 2K, or nothing if an ErgoStrip is already on the bench | 20100 | 0–1 | €46,00 |

## 8. Open

- **Measure the delivered OD with calipers at two or three points before
  ordering any tool.** Every table above turns on the catalogue figure of
  3,8 mm. If the cable measures 4,0 mm or more, the Allrounder, Strip No. 14 and
  Kabelmesser No. 16 SECURA all come into specification and the awkward
  fixed-depth compromise of §3 disappears. This is the same measurement
  `CABLE-SOURCING.md` §5 already holds the cable gland on — one caliper reading
  closes both.
- Jacket wall thickness is unpublished for 7038890. The offcut test in §3 is the
  substitute; if a wall figure is ever obtained from LAPP, record it here.
- Nothing in this note has been validated against physical cable.
