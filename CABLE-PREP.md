# Cable preparation: stripping the farm cable

Companion to [`CABLE-SOURCING.md`](CABLE-SOURCING.md), which picked the cable.
This picks the tool that opens it.

**Decision: JOKARI Abisolierzange Sensor Mini, Art.-Nr. 20310** — working range
**3,20–4,40 mm**, built for PUR/PVC sensor-cable sheaths, self-adjusting to the
diameter. The measured cable (3,65 mm) sits in the middle of that range. UVP
€116,00; street price from about €59.

Research date 2026-09-13. Every tool range below is taken from the JOKARI
**product datasheet** (`jokari.de/ptg/Datasheet/source/Datenblatt <Art>-v24.pdf`),
not from the shop blurbs, which omit the lower bounds and the cable-type limits.

### Revision history (same day)

1. First version chose the **Fibre Strip DC** (30700) against the catalogue OD
   of 3,8 mm, as the only tool whose published range seemed to contain it.
2. Its Amazon reviews reported the fixed-blade under-cut failure that version
   had flagged as a risk, so the choice moved to the **Kabelmesser No. 16 SECURA**
   (10160), used below its 4 mm minimum.
3. Fab **measured the cable at 3,65 mm**, and the datasheets were read. That put
   No. 16 SECURA 0,35 mm out of range, and a catalogue-wide scan by *diameter*
   rather than by tool category found the **Sensor Mini**. Versions 1 and 2 had
   searched only JOKARI's "Entmanteler" and "Kabelmesser" categories. The Sensor
   Mini is filed under "Abisolierzangen", although it is a sheath stripper.

---

## 1. What has to be opened

`CABLE-SOURCING.md` §0, ordered 2026-09-05: **LAPP UNITRONIC SENSOR FD
Lif9Y11Y 4x0,25, article 7038890**.

| | |
|---|---|
| **outer diameter, measured** | **3,65 mm** (Fab, 2026-09-13; method and number of points not recorded) |
| outer diameter, catalogue | 3,8 mm (automation24 technical-data table) |
| jacket | PUR, black, halogen-free, flame-retardant |
| cores | 4 x 0,25 mm², **unshielded**, PP insulation |
| rated | 300 V, drag-chain class 6, −40…80 °C fixed / −25…80 °C flexed |

The cable is 0,15 mm under its catalogue figure. That is enough to change the
answer: it moves the cable **out of** the No. 16 SECURA's range and further
**into** the Sensor Mini's.

PUR stretches rather than snapping after a circumferential score, so
score-and-flex techniques that work on NYM or PVC do not transfer.

## 2. Survey at the measured OD, from the datasheets

| tool | datasheet capacity | cable types named | verdict at 3,65 mm |
|---|---|---|---|
| **Sensor Mini**, 20310 | **Ø 3,20–4,40 mm** | **PUR halogen-free sensor/actuator cables**, TPE-U, control cables (e.g. ÖLFLEX), PUR/PVC, shielded and unshielded | **in range, right cable class — chosen** |
| CAN-Strip, 30013 | Ø **3,30–3,50 mm** | shielded data-bus twisted pair with micro-thin PTFE sheath, **wall 0,18–0,38 mm** | 0,15 mm too thick, wrong jacket |
| Fibre Strip DC, 30700 | Ø ≤ 5,9 mm | fibre cables **with reinforcement elements inside the sheath**, e.g. DAC | in range, wrong cable class |
| Kabelmesser No. 16 SECURA, 10160 | Ø 4–16 mm | round cables, fixed and flexible installation | 0,35 mm below minimum |
| Allrounder / Strip No. 14 | from 4 mm | — | below minimum |
| Sensor Special | Ø 4,40–7 mm | sensor cables | below minimum |
| KNIPEX ErgoStrip 16 95 01 SB | 8–13 mm (coax 4,8–7,5) | — | no |

Two datasheet details that the web pages do not show, and that settle the
rejected tools on their own:

- **CAN-Strip** is a *range*, not just a ceiling: 3,30–3,50 mm, calibrated for a
  0,18–0,38 mm PTFE wall. It is a single-cable-class tool.
- **Fibre Strip DC** is specified for cable **with strength members in the
  sheath**. Our cable has none: four stranded cores in soft PUR, which will
  deform in a fixed-blade tool that expects a stiff jacket. This is a second,
  mechanical reason for its rejection, independent of the reviews in §4.

## 3. The chosen tool

**JOKARI Abisolierzange Sensor Mini, Art.-Nr. 20310**, EAN 4011391203105,
152 g, 172 x 98 x 30 mm, glass-fibre-reinforced PA body with TPE grip, hardened
special-steel blades in a replaceable cassette, TÜV/GS tested.

From the datasheet:

> *"Die automatische Abisolierzange Sensor Mini entfernt PVC / PUR-
> Kabelummantelungen mit Durchmessern von 3,20 mm – 4,4 mm präzise, ohne die
> inneren Leiter oder das Schirmgeflecht zu beschädigen. Dabei stellt sich das
> automatische Abtastsystem der Zangen vollautomatisch auf die unterschiedlichen
> Kabeldurchmesser ein."*

It answers every concern the earlier versions had to argue around:

- **In range with margin.** 3,65 mm is 0,45 mm above the floor and 0,75 mm below
  the ceiling. A caliper reading that slightly compresses the PUR does not
  change that, and neither does the 3,8 mm catalogue figure.
- **Right jacket material, stated by the vendor.** PUR halogen-free sensor cable
  is the first cable type the datasheet names. LAPP UNITRONIC SENSOR FD is exactly
  that product class.
- **Not a fixed cut depth.** It senses the diameter, so the uncharacterised
  jacket wall that made the Fibre Strip DC a gamble does not matter here.
- Strip length is freely selectable.

**Price.** JOKARI UVP €116,00. Street prices seen 2026-09-13: idealo from
€58,68 (€65,58 incl. shipping), stex24 €74,99, Geizhals from €69,62. Stocked by
Conrad (1216154), Reichelt and Amazon.de (B0FL2DRBL4). Spare blade cassette:
**EM-Set Sensor Mini, Art.-Nr. 29310**, UVP €67,00.

**Datasheet slip, so it does not mislead a later reader:** the English half of
the 20310 datasheet says *"The Wire Stripper Sensor Special is tightly
focussed…"* and names the spare part *"EM-Set Sensor Special – 29310"*. The
German half, the heading, the capacity (3,20–4,40 mm) and the article numbers
all say Sensor Mini. The Sensor Special is the separate 4,40–7 mm tool.

**Still sacrifice 20 cm first.** At €1,70/m it costs about 34 cents. Strip the
offcut and inspect all four PP core insulations under magnification before
using the tool on a real termination. It is a new tool on a cable it has not
yet been tried on.

## 4. Why the earlier choices were dropped

**Fibre Strip DC (30700).** Amazon.de B00KZE9KI4, read 2026-09-13: 3,2 of 5
stars, n = 8, no reviews from Germany. The one review with legible text
(France, 2021-03, verified, style "Fibre optic cables") says *"Il fonctionne
bien mais il ne permet de dénuder entièrement le cable"*: it does not strip
the cable fully, which is the under-cut mode of a fixed blade. The pattern holds
across JOKARI's range. Fixed-depth tools score 2,7–3,5 (AS-Interface Strip 2,7/3,
Fibre Strip LC 3,5/7, LC-PUR 3,1/12), while adjustable ones score 4,5–4,8 on far
larger samples (Secura Super No. 15 4,8/4 098, Super 4 Plus 4,7/30 548). The
datasheet's "reinforcement elements inside the sheath" (§2) now gives the
mechanical reason. Amazon ratings are weak evidence on their own; here they
agree with the datasheet.

The listing's style selector groups three ASINs: B007K52EQ6 "Data/Control
Lines", B01AG2KTFM "CAN-BUS LINES" and B00KZE9KI4 "Fibre optic cables". The
3,2/8 headline may pool reviews across those variants. The quoted review is on
the fibre variant.

**Kabelmesser No. 16 SECURA (10160).** An adjustable-depth cable knife and a
good tool, but its datasheet capacity starts at 4 mm. At the catalogue 3,8 mm it
was a 0,2 mm compromise. At the measured 3,65 mm it is 0,35 mm out of range, and
an in-range tool built for this cable class exists.

**Scalpel.** PUR stretches instead of breaking cleanly after scoring, so the cut
becomes sawing, and sawing over 0,25 mm² cores is how a strand gets nicked. On a
buried probe, a nicked strand is a fault that shows up months later.

## 5. Core stripping: a separate tool

The Sensor Mini removes the sheath only. The 0,25 mm² cores in thin, slippery PP
insulation need their own tool.

| option | range | UVP | note |
|---|---|---|---|
| JOKARI **SECURA 2K**, 20100 | 0,2–6,0 mm² / AWG 24–10 | €46,00 | specified by cross-section, so 0,25 mm² is unambiguous |
| KNIPEX ErgoStrip 16 95 01 SB | 0,2–4,0 mm² | ~€25–32 | if one is already on the bench, no purchase needed |
| JOKARI **PWS-PLUS 002**, 40025 | conductor 0,25–0,80 mm Ø / AWG 30–20 | €36,00 | precision steps 0,25/0,30/0,40/0,50/0,60/0,80 mm, length stop 1,5–22 mm |

PWS-PLUS 002 caveats: its range is a *conductor diameter*, and 0,25 mm²
stranded is about 0,55–0,6 mm bare, inside the range by derivation rather than
by a JOKARI statement. JOKARI list it as ideal for PVC, TEFLON, KYNAR, TEFZEL
and MYLAR, and **PP is not listed**. Confirm on the offcut.

For a soldered field joint, the cores are stripped ~5 cm back and staggered, per
Truebner's procedure in `CABLE-SOURCING.md` §5.1.

## 6. Consequence for the splice sleeve

`CABLE-SOURCING.md` §5.1 names **CellPack SRH2 8/2** (Voelkner X774691, €8,21)
as the adhesive-lined outer sleeve and warned that it was too small for the
superseded ÖLFLEX ROBUST 215 C (6,6 mm). That warning is marked void there. At a
measured 3,65 mm, an 8 mm sleeve passes over easily, and its 2 mm recovered
diameter leaves the adhesive room to seal. The part is correctly sized as
published.

## 7. Buy list

| item | article | qty | UVP | street |
|---|---|---|---|---|
| JOKARI Abisolierzange Sensor Mini | 20310 | 1 | €116,00 | from ~€59 |
| core stripper: SECURA 2K, or nothing if an ErgoStrip is on the bench | 20100 | 0–1 | €46,00 | — |
| spare blade cassette, only when worn | 29310 | 0 | €67,00 | — |
| ~~Fibre Strip DC~~ | ~~30700~~ | 0 | — | rejected, §4 |
| ~~Kabelmesser No. 16 SECURA~~ | ~~10160~~ | 0 | — | out of range at 3,65 mm, §4 |

## 8. Open

- **Record how 3,65 mm was measured**: instrument, number of points, and
  whether the jaws compressed the jacket. The tool choice has margin either way,
  but `CABLE-SOURCING.md` §5 sizes the **cable gland** on this same figure, and a
  gland has much less tolerance than this tool.
- Validate the Sensor Mini on the 20 cm offcut (§3), including a magnified check
  of the PP core insulation, and record the result here.
- Jacket wall thickness for 7038890 is still unpublished. It no longer matters
  for this tool, but it would for any future fixed-depth one.
