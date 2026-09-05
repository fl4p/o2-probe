# The farm cable: sourcing decision

Closes the cable half of `POTTING.md` §5 item 4, "Specify the cable and the gland
by part number". The gland is still open and waits on a measured OD.

**Ordered 2026-09-05: LAPP UNITRONIC SENSOR FD Lif9Y11Y 4x0,25, article
7038890**, from automation24.de (their art. 103793, EAN 4044777472314), €1,70/m
net, Meterware. §0 records why the recommendation moved.

The prior recommendation, and still the answer if chemistry outranks size: LAPP
ÖLFLEX ROBUST 215 C 4X0,5, article 0022704. Fallback if the pile ever measures
above ~75 °C: ÖLFLEX HEAT 125 C MC 4X0,75, article 1024482. Both carry a caveat
that §4 states plainly.

Research date 2026-09-04; independently reviewed and corrected 2026-09-05
(`review/CODEX-REVIEW-2026-09-04.md`). Method: `online-research` skill,
decision-grade tier.

---

## 0. What was ordered, and why it is not §3's winner

Fab added a constraint after §3 was written — **10 m, under €100, OD < 5 mm** —
and that last figure eliminates every candidate in §3. ROBUST 215 C is 6,6 mm,
ROBUST 210 is 5,8 mm, HEAT 125 C MC is 8,4 mm. The gland in a 32 mm end cap is
happier with a thin cable, so the constraint is real, not arbitrary.

| | LAPP 7038890 |
|---|---|
| construction | 4 x 0,25 mm², **unshielded**, PP core insulation |
| **OD** | **3,80 mm** |
| jacket | **PUR**, black, halogen-free, flame-retardant |
| temperature | **−40…+80 °C fixed, −25…+80 °C flexed** |
| rated | UV-resistant, oil-resistant, drag-chain (class 6), 300 V |
| price | €1,70/m net (~€2,02 gross); 10 m ≈ €17 net + shipping |

Verified 2026-09-05 on the automation24 product page's own technical-data table,
which is where the temperature and OD figures above come from — not from a search
snippet.

**Why it is a good answer.** 3,80 mm OD, 4 x 0,25 mm², PUR jacket is
*dimensionally identical to Truebner's TrueFlex*, the cable Truebner themselves
bury with the SMT100s already in this windrow. TrueFlex's blocker in §3 was that
Truebner publish **no temperature rating** for it; 7038890 is the same cable
geometry **with a published −40…+80 °C**. PUR is also the jacket `POTTING.md` §5
wants, because it bonds to a PU pot once abraded, unlike a fluoropolymer.

Note that its **flexed** rating is +80 °C, where LiYY's was +70 °C. That removes
§2's sharpest objection — this cable is inside its rating at 72,1 °C in either
installation condition, not just fixed.

**What it costs, stated plainly, because §4's caveats do not all carry over:**

1. **No compost or ammonia language.** ROBUST 215 C's one real advantage was that
   LAPP name composting plants and claim ammonia resistance. LAPP claim nothing
   of the kind for 7038890. PUR is generally well-regarded against ammonia and is
   what Truebner bury — but that is inference from a neighbouring product, not a
   vendor statement about this one. **This is the trade that was made:** vendor
   chemistry language was exchanged for OD, and it should be revisited if a
   jacket is ever recovered degraded.
2. **Unshielded, and no defined A/B twisted pair.** See §1's revised shield
   discussion, and treat the standing measurement action there as binding if the
   heater is enabled.
3. **No burial approval** — but no candidate had one, and the run goes in conduit
   regardless (§4 item 1).
4. **8 K of thermal margin**, with everything §4 item 2 says about what a jacket
   rating does and does not prove.
5. **Not returnable** — cut to length. Order the length you want, plus slack.

The 0,25 mm² conductors are electrically ample: 10 m gives ~63 mV on the ground
line and ~126 mV round the supply loop at 91 mA, against ~5 V of headroom. Even
at 30 m it would be ~380 mV loop.

Siblings, if the ordered part turns out wrong: **7038865** is the same family at
4 x 0,34, OD 4,7 mm. A shielded small-OD option exists — **UNITRONIC PUR CP
4x0,25, article 0032802**, OD 5,0 mm, PUR plus braid, −40…+80 °C fixed — but it
is sold in 100/500/1000 m rings, so it fails the 10 m constraint.

**A boundary worth recording: below 5 mm OD, +80 °C is the ceiling.** Every
surveyed cable that beats 80 °C leaves the PUR/TPE class entirely and lands at
8,4 mm or above. Thermal margin and small OD cannot both be bought here.

---

## 1. The envelope

Hard constraints, each traced to the repo or to a site measurement:

| constraint | value | source |
|---|---|---|
| conductors | 4 (+12 V, GND, RS-485 A, RS-485 B) | `DESIGN.md` J1 |
| supply window | 7–15 V, ~91 mA worst case (86 mA heater + 5 mA board) | `DESIGN.md`, `POWER.md` §1 |
| continuous temperature | **72.1 °C measured** at 30 cm in the windrow | `journal/COMPOST-JOURNAL-2026-08.md` (21.08 peak 72.1 °C, 25.08 recovery 71.7 °C) |
| chemistry | saturated, ammoniacal, organic-acid, microbially active | the application |
| UV / outdoor | the above-ground run is on an exposed site | `memory: steingrubenhof_site_wind` |
| jacket–potting bond | PU pot grips the abraded jacket | `POTTING.md` §5 |
| water path | water-blocked, **or** every conductor tinned through its stripped length | `POTTING.md` §5 |
| OD | must suit a gland in the end cap of a 32 mm tube | `POTTING.md` §5, `PLAN.md` |

Soft / not constraints:

- **A shield is desirable, not required — but the argument is weaker than an
  earlier revision of this document made it.** The only in-cable aggressor is the
  heater's 1 kHz PWM (`firmware/src/regmap.c:23`, `heater_pwm_hz = 1000`) sharing
  the jacket with A/B. That earlier revision reasoned that the coupling is
  substantially common-mode and therefore rejected by the THVD1410 "over
  −7…+12 V". **That is a category error and is withdrawn.** A common-mode
  *operating range* is not a crosstalk-rejection specification: it says the part
  keeps working with the whole bus offset, not that a disturbance arriving on the
  pair is cancelled. Unequal mutual capacitance and inductance from the power
  cores to A versus B, stranding lay, and the connector breakout all convert the
  heater's switching edge into genuinely **differential** voltage, and RS-485
  receiver thresholds are tens to a couple hundred millivolts — not volts. Note
  also that an overall shield does little against an aggressor *inside the same
  jacket*; what actually helps is a **defined twisted A/B pair**, which neither
  the ordered cable nor the ROBUST candidates have.

  Two things keep this from being a blocker. The heater ships disabled
  (`HEATER_MAX_DUTY` = 0), so today there is no aggressor at all; and Truebner run
  the SMT100 bus unshielded to 300–400 m at the same 9600 baud, though with no
  comparable PWM source in the cable. **Standing action:** if the heater is ever
  enabled, scope A−B at the master with the heater at worst-case duty and count
  Modbus CRC errors over a day before trusting the link. Do not treat the
  unshielded choice as qualified until that measurement exists.
- **Conductor CSA is not a constraint.** At 91 mA over 30 m, one conductor of
  0.5 mm² is ~1.05 Ω at 20 °C, so **~96 mV on the ground line and ~190 mV round
  the supply loop**; 0.34 mm² gives ~140 mV and ~280 mV; the ordered 0.25 mm² at
  10 m gives ~63 mV and ~126 mV. At 72 °C add ~20 %. Against ~5 V of headroom
  above the 7 V floor, all of these are ample — pick CSA for handling. (An earlier
  revision labelled the ~0.2 V figure a "ground-line drop"; it is the loop drop,
  and the ground line carries half of it.)

## 2. Why the €1.50/m LiYY was rejected

Fab proposed an eBay 4×0,34 mm² LiYY (`ebay.de/itm/274834113899`, IT-Tronics,
from €1.50/m). Its attraction is real and worth recording: 4-core LiYY is coded
to **DIN 47100**, whose first four colours are weiß, braun, grün, gelb — exactly
`DESIGN.md`'s J1 map, which the project inherited from Truebner's SMT100
convention. Electrically it is ample.

It fails on the environment:

- **Temperature.** LAPP UNITRONIC LiYY is **−40…+80 °C fixed, −5…+70 °C flexed**.
  The site measured **72.1 °C**. A flexed LiYY is *over* its rating in a working
  windrow and a fixed one has 8 K of margin at the jacket's ceiling, continuously,
  for years.
- **Not water-blocked**, so `POTTING.md` §5's fallback (tinning every conductor)
  becomes the only barrier rather than the second one.
- **No burial approval.** No candidate here has one; LiYY is not special in this.

Two disqualifiers an earlier revision listed are **withdrawn as unfounded**: "not
UV-stabilised, not rated for outdoor" and "no stated oil or chemical resistance".
LAPP's current UNITRONIC LiYY BK catalogue page does describe UV/outdoor
suitability and some oil resistance. The rejection therefore rests on temperature
and the unverified burial/chemistry record alone — which is still sufficient, but
it is one reason, not four.

**The article number was also wrong.** An earlier revision cited LAPP **1030240**
as the 4×0,34; 1030240 is the **5×0,34** (OD 5,5 mm). The 4×0,34 is **1030239**
(OD 4,0 mm) — verified 2026-09-05 across three distributors. Note separately that
the eBay listing is a **Lumonic / IT-Tronics** cable, not LAPP: applying LAPP's
datasheet to it was never valid in the first place, and rejecting it for having
no verified burial, chemistry or temperature record of its own remains the sound
call.

The rejection is environmental, not electrical. LiYY remains a perfectly good
**bench and short-trial** cable, which is all v0 needs — `README.md` forbids
burying a v0 probe anyway, because the heater ships hard-disabled.

## 3. Candidates

| | ÖLFLEX ROBUST 215 C 4X0,5 | ÖLFLEX HEAT 125 C MC 4X0,75 | TRUEBNER TrueFlex |
|---|---|---|---|
| article | **0022704** | **1024482** | no MPN published |
| temp, fixed | −50…+80 °C | **−55…+125 °C** | **not published** |
| jacket | TPE | e-beam cross-linked polyolefin | **PUR** |
| shield | tinned Cu braid | braid | **none** |
| cores | 4 × 0,5 mm², numbered black | 4 × 0,75 mm², numbered black | 4 × 0,25 mm², DIN 47100 colours |
| OD | **6,6 mm** | 8,4 mm | **3,8 mm** |
| UV / outdoor | yes, EN 50396 / HD 605 S2, plus UV-C | yes | yes |
| **direct burial** | **not claimed** | not claimed | **yes, explicitly** |
| compost | **named application; ammonia and bio-gas resistance claimed** | not stated | microbe-resistant |
| price | ~€4,49/m net + Cu surcharge (Letronic) | not priced here | quote only |

### 3.1 Why ROBUST 215 C wins

Because the hard problem here is chemistry, and ROBUST 215 C is the only candidate
whose vendor names this application *at all*. LAPP's 2017 product information
reads:

> "shielded control cable, weather-resistant, bio-oil-resistant,
> detergent-resistant and hot-water-resistant for use in the food industry **and
> in composting plants**"

and, under Benefits, "**Good resistance to ammonia compounds and bio-gases**".
The application list names *composting plants* and *sewage works* outright.

**Read that as application guidance, not qualification.** An earlier revision of
this document said "LAPP qualified this exact cable for this exact application"
and called it "a qualification no general-purpose cable carries". That is
stronger than the source: LAPP give **no concentration, immersion duration,
temperature, test method or service life** behind "good resistance", and the
*current* LAPP product page for 0022704 omits the composting-plant language
altogether — it survives only on a 2017 information sheet. What is true, and
still decisive between candidates, is that every other option is silent on the
medium while this one at least names it.

It is also the smaller of the two LAPP options at 6,6 mm OD, which matters where
the cable has to pass a gland in the end cap of a 32 mm tube, and it is the only
candidate with a published price. **TrueFlex beats it on that axis** — 3,8 mm —
and that is one more reason to make the phone call in §3.2 before ordering.

### 3.2 Why TrueFlex is the honourable mention, not the pick

Truebner's own cable is genuinely well-suited on paper and is already on this
bus — the SMT100s' 10 m tails are TrueFlex, and the colour convention in
`DESIGN.md` came from it. Truebner state it is "for Erdverlegung ausgelegt"
(designed for direct burial) and that the jacket is "Polyurethanmantel, der
wasserdicht, mikrobenbeständig und für Erdverlegung geeignet ist" — watertight,
**microbe-resistant**, burial-rated. PUR also bonds well to a PU pot, which is
exactly what `POTTING.md` §5 asks of the jacket.

It loses on one thing: **Truebner publish no temperature rating for the cable**.
The SMT100 manual's spec table gives "Cable specification 4 x 0.25 mm²" and
"Cable jacket material: very robust polyurethane (PUR)"; the cable-extension
guide adds the OD, "ca. 3,8 mm". Neither states a temperature. The
−20…+85 °C in the manual is the sensor's *measurement* range, not a cable
rating, and must not be read as one. Against a measured 72 °C that gap is
disqualifying for a load-bearing choice — but it is a phone call, not a dead end.
**If Truebner will state a jacket temperature rating ≥ 90 °C, TrueFlex becomes
the better answer than ROBUST 215 C**, because it adds burial approval, microbe
resistance and PU-compatible chemistry, and keeps the DIN 47100 colours.
Contact: `info@truebner.de`, +49 6321 8579050.

## 4. What is wrong with the recommendation

Stated plainly, because both items are real.

**1. Nobody claims direct-burial approval for ROBUST 215 C.** Lapp says "für den
Außenbereich geeignet" — suitable for outdoor use. That is not *Erdverlegung*,
and I found no source that upgrades it (see §6 for the search bound). The probe
end is buried in compost and the run crosses open ground.

**Mitigation, which is also Truebner's own advice for their burial-rated cable:**
run it in conduit. The SMT100 manual says "sometimes it can make sense to protect
the cable against animal bites by using an additional ductwork". Conduit closes
the burial-approval gap and the animal-bite hazard in one move.

**2. Eighty degrees is only 8 K above what the site already measured.** This is
the same objection that disqualified LiYY, and intellectual honesty requires
noting that ROBUST 215 C does not escape it — it merely sits on the right side
of the line where LiYY's flexed rating sits on the wrong one. It is a continuous
rating and the cable carries 91 mA in 0,5 mm², so self-heating is genuinely nil
(91 mA in ~2,1 Ω of supply loop is **~21 mW spread over the whole 30 m**); the
margin is entirely against the pile.

Be clear about what that margin is worth: **a jacket temperature rating is an
operating limit for the specified installation condition, not evidence of
multi-year life in hot wet compost.** And 72,1 °C is one measured peak from one
season — it bounds neither future seasons, nor depth gradients, nor sensor error.
Treating 8 K as adequate is an accepted risk, not a demonstrated result. Either
accept it explicitly, or buy the 125 °C option and stop thinking about it. **If a future season measures above ~75 °C
at probe depth, switch to ÖLFLEX HEAT 125 C MC 4X0,75 (1024482)**, which buys
53 K of margin at the cost of a larger 8,4 mm OD and no stated compost
qualification.

**3. Neither is water-blocked.** `POTTING.md` §5's fallback is therefore not a
fallback but the plan: tin every conductor through its full stripped length, keep
the jacket cut and the tinned length inside the pot, and anchor the jacket
mechanically.

**4. The colour convention breaks.** Both LAPP candidates identify cores by
**numbers on black**, not by DIN 47100 colours. `DESIGN.md`'s J1 map — brown
+12 V, white GND, green A, yellow B — no longer describes the physical cable.
Whichever is bought, the number→function map has to be recorded in `DESIGN.md`
and printed on the probe label, or a field repair will be a coin toss. Avoid the
`4G` variants (0022703, 1024409): the G forces a green-yellow core, and using a
protective-conductor colour for signal is a trap for whoever opens it next.

## 5. Buy list

For one probe with a 30 m run:

| item | article | qty | note |
|---|---|---|---|
| ÖLFLEX ROBUST 215 C 4X0,5 | LAPP 0022704 | 30 m | Letronic ~€4,49/m net + Cu surcharge; €15 cutting fee below 100 m and a €25 handling fee below €150, so a 30 m cut lands near €175 net. Compare Conrad/Voelkner, who sell Meterware without the cut fee. |
| cable gland | — | 1 | **open** — pick for the *measured* OD (nominal 6,6 mm), not the nominal range; `POTTING.md` §5. M16 with a 4,5–10 mm range is the likely size. |
| conduit for the buried and traversed sections | — | 30 m | §4 item 1 |

### 5.1 Splicing — corrected

An earlier draft of this section said "do not splice in the ground, order the
full run in one piece". **That was too strong.** Truebner publish a sanctioned
extension procedure, and the project already has its own answer to the same
question in [`tech/CONNECTORS.md`](../../tech/CONNECTORS.md), which selects a
field-terminable connector pair for the 4-pin Modbus run. Both routes are open;
only *improvised* joints are forbidden.

**But keep the joint out of the soil.** Truebner's own FAQ
(`truebner.de/de/faq_sensor.php`) states that the extension contact point must
never be in soil. The extension guide requires the outer adhesive sleeve to be
soil-suitable, which reads like a licence to bury — and an earlier revision of
this section took it as one. **Truebner never withdraw the FAQ prohibition, so
that reconciliation is my inference, not their approval.** Until Truebner confirm
buried use in writing, terminate above grade or in an accessible hand-hole. This
costs nothing: the run is being laid in conduit anyway (§4 item 1), so siting the
joint at a conduit end is free.

**Truebner's method** (`truebner.de/de/anleitung_kabelverlaengerung.php`, English
at `/en/manual_cable_extension.php`) is a soldered, double-shrunk butt joint,
explicitly "dauerhaft, robust und bei korrekter Ausführung wasserdicht":

1. Strip ~5 cm of jacket from both ends; **stagger the core lengths** so the
   four solder joints do not sit side by side.
2. **Solder only.** Truebner are categorical: "Klemm-, Quetsch- und
   Schraubverbindungen sind nicht geeignet" — clamp, crimp and screw joints are
   unsuitable, and only a clean solder joint stays corrosion-resistant long term.
3. One 1–1,5 cm **adhesive-lined** shrink sleeve per core, slid on *before*
   soldering.
4. One **25 cm** adhesive-lined sleeve over the whole joint — the length is
   specified for longitudinal tensile strength as well as water tightness, and
   the sleeve must be rated for use in the ground.
5. Heat evenly until the adhesive flows, within the sleeve maker's temperature
   limit.

**The orderable part Truebner name for step 4:** adhesive-lined heat-shrink,
8 mm before / 2 mm after, = **CellPack SRH2 8/2 black**, Voelkner Art.-Nr.
**X774691**, €8,21, EAN 4010311009223.

**Two cautions before ordering that part.**

- **It is sized for TrueFlex, not for the recommended cable.** An 8 mm sleeve
  shrinking to 2 mm suits TrueFlex's 3,8 mm OD. It will not pass over ÖLFLEX
  ROBUST 215 C at **6,6 mm**, let alone HEAT 125 C MC at 8,4 mm. For those,
  size up — roughly 19/6 for the outer sleeve — and keep the adhesive lining and
  the 25 cm length, which are the parts that do the work.
- **Truebner's FAQ and their own guide read as if they disagree**, and the
  reconciliation matters. The FAQ says "Keinesfalls darf die Kontaktstelle im
  Erdboden sein" and that tape and non-adhesive shrink give insufficient
  protection; the guide requires a sleeve "für den Einsatz im Erdreich
  geeignet". The FAQ is warning against *improper* joints in soil, not
  prohibiting the sanctioned one. Read together: a taped or plain-shrink joint
  must never be buried; a correctly executed adhesive-lined soldered joint is
  what Truebner sell the method for.

Then order the run in as few pieces as the site allows anyway — every joint is a
water path, and `POTTING.md` §5 already treats the cable as the leak path of
record.

## 5.2 The gland

Closes the other half of `POTTING.md` §5 item 4. Researched 2026-09-05, same
method and browser as the cable work; sources in §8.

**Recommendation: LAPP SKINTOP INOX-R M12x1,5, article 53806749.**

| | |
|---|---|
| body | stainless **V4A, 1.4404 / 316L** |
| seal / O-ring | **silicone** / silicone (insert: polyamide) |
| clamping range | **3,0 - 5,0 mm** — the ordered cable's 3,80 mm sits at 40 % of the band |
| temperature | **−40 ... +100 °C** |
| ingress | **IP68 (10 bar), IP69**, NEMA 4X / 6 |
| thread | M12x1,5, **thread length 6,5 mm**, SW 16, overall length 29,3 mm |
| pack | 5 pieces (~€19-21 each incl. VAT, several German distributors) |

### Why the material question dominates this choice

The default cable gland is **nickel-plated brass**, and brass is the wrong alloy
family for this specific environment — not marginally, but by a named failure
mechanism. Ammonia is *the* classic stress-corrosion-cracking agent for brass,
and the canonical description of the hazard is a description of this site:

> "brasses stored in a dry and clean atmosphere, although carrying high internal
> strains, cracked only after a long time; while a damp atmosphere was especially
> active in producing such cracking, particularly if it carried **ammonia vapor
> from decaying organic matter**"
>
> — Davalos-Monteiro et al., *Mat. Res.* 22(1), 2019,
> [doi:10.1590/1980-5373-MR-2018-0077](https://doi.org/10.1590/1980-5373-MR-2018-0077),
> §1, which also finds SCC "most severely in ammonia **vapour**"

A cable gland is a pre-stressed brass part (the compression nut holds the body in
tension) sitting in warm, saturated, ammonia-bearing vapour. That is the complete
SCC triad — susceptible alloy, sustained tensile stress, specific agent — so
**every nickel-plated brass gland is rejected here**, including PFLITSCH's own
brass blueglobe and LAPP's SKINDICHT/SKINTOP MS range. This is a chemistry
rejection, not a preference.

Note the mechanism prefers **vapour** to immersion, so "it will be sealed in
conduit" is not mitigation — a conduit is exactly where humid ammonia vapour
collects.

### Why not the obvious hygienic-grade part

**LAPP SKINTOP HYGIENIC-R M12x1,5 (53105200) is rejected**, despite being the
best geometric fit found (3,0 - 4,5 mm brackets 3,80 mm almost dead centre) and
316L bodied. Its datasheet gives **FKM** seals, and FKM is the one common
elastomer family with a documented ammonia exception — the standard resistance
summary lists its weaknesses as "hot water and steam, for standard
bisphenol-cured grades ... **ammonia and certain strong bases**". Hot, wet and
ammoniac is all three of FKM's weaknesses at once, and it is the entire
description of a windrow.

Silicone (INOX-R) and TPE (PFLITSCH) are both ordinary choices for ammonia
service. That is the whole reason INOX-R wins over the part that fits better.

### Alternatives, and the one number that separates them

| | LAPP INOX-R M12 **53806749** | PFLITSCH **bg 212V4A** | PFLITSCH **bg 212VA** |
|---|---|---|---|
| body | 1.4404 / 316L | 1.4571 (V4A) | **1.4305** |
| seal | silicone | TPE | TPE |
| temperature | −40…+100 °C | **−40…+130 °C** | −40…+130 °C |
| range at 3,80 mm | 3,0–5,0 (40 %) | 2,0–5,0 w/ inlet (60 %) | 2,0–5,0 w/ inlet |
| ingress | IP68 10 bar | **IP68 15 bar** | IP68 15 bar |
| thread length | 6,5 mm | 5,0 mm | 5,0 mm |
| orderable | 5-pack, several DE distributors | **price on request, catalogue PU 50** | **single**, €15,50 net (automation24 art. 103588) |

PFLITSCH's **bg 212V4A** is on paper the better part — 1.4571, a TPE insert good
to +130 °C where INOX-R's silicone stops at +100 °C, and IP68 to 15 bar. It loses
on procurement only: price-on-request against a catalogue pack of 50.

**Do not substitute the in-stock bg 212VA for it.** PFLITSCH's own table gives the
plain-VA body as **1.4305**, a free-machining grade whose sulphur is deliberately
present as manganese-sulphide inclusions; those inclusions are established pitting
initiation sites, and the grade carries a **PREN of about 17–21 against 316L's
~24**. For a part that is permanently buried, permanently wet, warm and in contact
with chloride-bearing leachate, that is the wrong end of the stainless range. The
€15,50 single-unit convenience is buying a machining grade for a corrosion job.

**If the pile ever measures above ~85 °C**, INOX-R's +100 °C stops being
comfortable and the answer is bg 212V4A (or its silicone-insert option, −55 …
+200 °C) bought as a pack — the same escalation `POTTING.md` §5.1 already defines
for the cable.

### The mounting constraint this exposes

INOX-R's thread is **6,5 mm long**, and a stainless M12x1,5 locknut is **2,8 mm**
tall (PFLITSCH 212/5stv). Through-hole mounting therefore allows a cap wall of at
most **6,5 − 2,8 ≈ 3,7 mm**, and less once you want thread engaged past the nut.

That collides with an existing project rule. `MEMBRANE.md` forbids **sustained
strain in plastic at 75 °C**, and a gland torqued into a tapped ASA or PVC-U boss
is precisely sustained strain in plastic at temperature — the cap would creep and
the seal would relax over exactly the timescale this probe is meant to survive.
So the two mounting routes are:

1. **Thin cap wall (≤ 3,5 mm) + stainless locknut** — the load path is
   metal-to-metal through the nut, and the plastic is only in compression. This
   is the route consistent with the existing rule.
2. **A stainless M12x1,5 threaded insert** moulded or bonded into the cap, if the
   cap has to be thicker.

**Tapping the plastic directly is not an option**, and this is worth stating
because it is the obvious thing to do with a printed ASA head. Resolve the cap
wall thickness before ordering; it is a `PLAN.md` enclosure decision, not a
sourcing one.

### Open

- **Measure the cable's actual OD before committing.** 3,80 mm is LAPP's nominal.
  Jacket OD tolerance is typically ±0,15 mm or so, which stays inside 3,0–5,0 —
  but the measurement is free and the whole point of §5.1's warning.
- **The expansion port** (`PLAN.md`, second gland or M12 connector) needs either a
  second gland or a **stainless blanking plug**; PFLITSCH list a
  "Blindstopfen Sechskant – metrisch – Edelstahl" and LAPP an equivalent. Not
  priced here, because whether the port exists at all is still open in `PLAN.md`.
- **Silicone is the most gas-permeable common elastomer.** It is the right choice
  against ammonia, but §5's claim that the gland is a *moisture barrier* is a
  claim about liquid water at the clamping interface, not about vapour transport
  through the seal cross-section. Nobody has bounded the vapour path, and the
  soak test is what would.
- Neither the +100 °C nor the +130 °C rating is a **service-life** figure at
  72 °C in ammoniac wet — the same caveat §4 item 2 records for the cable applies
  unchanged to the gland's elastomer.

## 6. Search record for the absence claims

Two absence claims are load-bearing and both are **bounded**, not strong.

*"No source claims direct-burial approval for ÖLFLEX ROBUST 215 C."* Searched
2026-09-04: Lapp's own German shop page for 0022704 and 0022700 (live DOM, all
accordions expanded), Lapp's 2017 product-information PDF via Farnell, the Lapp
online catalogue entry, and distributor spec tables (Letronic, Conrad, Voelkner,
elektro4000, elektroland24, industry-electronics). German query set around
*Erdverlegung / erdverlegt / eingraben / nicht geeignet*. Every source that
states an installation environment says "für den Außenbereich geeignet" and none
says Erdverlegung. Stopped on saturation across vendor and distributor copy.
**Confidence in absence: medium** — Lapp's catalogue is close to a closed corpus
for its own product, but I did not reach a Lapp technical datasheet PDF for
0022704 specifically (the shop's Downloads tab exposes only category landing
pages), so a burial statement could exist in a document I did not open.

*"No independent literature on TPE cable-jacket life in compost."* One English
challenge query on TPE jacket degradation / ammonia / hydrolysis / buried
failure returned only general cable-ageing work (XLPE in soil and seawater,
polymer insulation ageing) and vendor marketing. **Confidence in absence: low**
— one query on one axis, and the claim it guards (Lapp's own ammonia and
bio-gas resistance) rests on the manufacturer's assertion, uncorroborated.

## 7. What would discriminate

| open question | what settles it | which way it cuts |
|---|---|---|
| TrueFlex jacket temperature rating | ask Truebner (`info@truebner.de`) | ≥ 90 °C makes TrueFlex the pick over ROBUST 215 C |
| Is ROBUST 215 C approved for Erdverlegung? | ask LAPP for the 0022704 datasheet | approval removes the conduit requirement |
| Real windrow temperature at probe depth over a season | the SMT100s already log it | > 75 °C forces HEAT 125 C MC |
| Joint or one-piece run | site survey of the actual route | a serviceable joint pulls in `tech/CONNECTORS.md`'s connector pair instead of a soldered splice |
| **Does the windrow get turned with the probe in it?** | the deployment plan | if yes, no jacket survives and the answer is a removable probe, not a better cable |

That last row is not a cable question and it dominates all of them.

## 8. Source access log

| # | source | evidence state | attempt history | route | validation | load-bearing |
|---|---|---|---|---|---|---|
| S1 | https://www.truebner.de/de/faq_sensor.php | inspected (all FAQ answers, accordions expanded) | headed Chrome/CDP, first attempt 200 | raw text (live DOM) | validated (live DOM) | yes |
| S2 | https://www.truebner.de/assets/download/Manual_SMT100_V1.0.pdf (RS485 version, 11 pp.) | inspected (§2 technical data, §4 installation, §5 FAQ) | curl + plain-Chrome UA, 200, 1 239 692 B, `%PDF-1.5` | raw text (`pdftotext -layout`, text layer) | validated (layout table renders coherently; values cross-check the vendor FAQ) | yes |
| S3 | https://www.truebner.de/de/smt100.php | inspected (Spezifikationen block) | headed Chrome/CDP, accordions expanded, 200 | raw text (live DOM) | validated | no |
| S4 | https://www.truebner.de/de/datenkabel.php | inspected | headed Chrome/CDP, 200 | raw text (live DOM) | validated | no |
| S5 | https://www.farnell.com/datasheets/2547203.pdf — LAPP *Product Information ÖLFLEX ROBUST 215 C*, last update 16.07.2017, PN 0456 / 02_03.16 | inspected (Info, Benefits, Application range, Product make-up, Technical Data, article table) | curl + plain-Chrome UA, 200, 205 290 B, `%PDF-1.3` | raw text (`pdftotext -layout`) | validated (article table and temperature range agree with the live Lapp shop and with Letronic independently) | yes |
| S6 | https://www.lapp.com/de/de/oelflex-robust-215-c/p/0022704 | inspected (Nutzen, Anwendung, Hinweise; Downloads tab opened) | headed Chrome/CDP, 200; tab/accordion expansion | raw text (live DOM) | validated | yes |
| S7 | https://www.lapp.com/de/de/oelflex-robust-215-c/p/0022700 | partial (product header and feature list only) | headed Chrome/CDP, 200 | raw text (live DOM) | validated | no |
| S8 | https://www.letronic.de/de/produkte/lapp/olflex-robust-215-c/olflex-robust-215-c-4x05 | inspected (spec table and price table) | headed Chrome/CDP, 200 | raw text (live DOM) | validated | yes |
| S9 | https://www.lapp.com/de/de/oelflex-heat-125-c-mc/p/1024400 | inspected (feature list + complete 40-row article table, parsed from the DOM) | headed Chrome/CDP, 200; Artikeltabelle tab clicked | raw text (live DOM) | validated | yes |
| S10 | https://www.ebay.de/itm/274834113899 | inspected (title, item specifics, price, seller) | curl plain-Chrome UA → **403**; curl + full Sec-Fetch/sec-ch-ua → **403**; headless Chrome (channel=chrome, plain UA) → **403**; **headed Chrome, scratch profile, warmed on an eBay search page → 200** | raw text (live DOM) | validated | yes |
| S15 | https://www.truebner.de/de/anleitung_kabelverlaengerung.php — *Anleitung Kabelverlängerung* | inspected (all five steps, plus the cable-construction preamble) | headed Chrome/CDP, first attempt 200 | raw text (live DOM) | validated | yes |
| S16 | https://www.voelkner.de/products/1026046/… — CellPack SRH2 8/2, Voelkner Art.-Nr. X774691 | inspected (identity, dimensions, shrink ratio, price, EAN) | composed URL `voelkner.de/search/X774691` → **404, rung-0 wrong URL**; recovered by driving the site's own search box, which redirected to the product page → 200 | raw text (live DOM) | validated | yes |
| S11 | https://www.electricautomationnetwork.com/PDF/PIM/LAP/DE_1030240.pdf — LAPP *Produktinformation UNITRONIC LiYY BK* | **partial** — temperature range only, and taken from the search-result snippet, not the document | curl + plain-Chrome UA → **403** (server returned HTML, not PDF); not further climbed | intermediary (search index) | unvalidated extraction | **yes** — see the caveat below |
| S12 | https://www.helukabel.de/de/produkte/datentechnik-leitungen/pvc-datenleitungen/liyy.html | de-scoped | curl plain-Chrome UA → 404 (composed URL, rung-0 failure); superseded by S11 and not re-derived, because the LiYY rejection does not turn on it | route: none | n/a | no |
| S13 | https://www.victronenergy.com/upload/documents/Datasheet-SmartSolar-charge-controller-MPPT-75-10,-75-15,-100-15,-100-20-EN.pdf | partial (self-consumption rows) | curl + plain-Chrome UA, 200, 285 373 B, `%PDF-1.6` | raw text (`pdftotext`) | validated | yes — for `POWER.md`, not this document |
| S14 | PVGIS v5.3 MRcalc API, `re.jrc.ec.europa.eu`, SARAH3 / ERA5, 2005–2023 | inspected (monthly `H(i)_m` series, tilt sweep 40–90°) | curl, 200, JSON | raw text (JSON) | validated (inputs block echoes lat/lon/elevation/horizon as requested) | yes — for `POWER.md` |
| S15 | https://doi.org/10.1590/1980-5373-MR-2018-0077 — Davalos-Monteiro et al., *Observations of Corrosion Product Formation and Stress Corrosion Cracking on Brass Samples Exposed to Ammonia Environments*, Mat. Res. 22(1), 2019 | **partial** — abstract and §1 Introduction, which carry the quoted claims | headed Chrome over CDP, 200, article DOM read live | raw text (DOM) | validated (title, DOI and journal match) | **yes** — the brass rejection in §5.2 |
| S16 | https://www.pflitsch.de/de/kabelverschraubungen/standard-kabelverschraubungen/blueglobe/blueglobe-edelstahl-v4a/ and …/blueglobe-edelstahl/ | **inspected** — full ordering table plus the material/temperature header row | headed Chrome over CDP, 200 | raw text (DOM) | validated | yes — bg 212V4A vs bg 212VA body grades, TPE insert, clamping ranges |
| S17 | https://datasheet.octopart.com/53806743-Lapp-Group-datasheet-180552415.pdf — LAPP *Product Information SKINTOP INOX / INOX-R*, last update 11.12.2022 | **inspected** — technical-data block and full ordering table | curl + plain-Chrome UA, 200, 456 585 B, `%PDF-1.7` | raw text (`pdftotext -layout`) | validated | **yes** — the recommendation's body grade, seal, range and thread length |
| S18 | https://imager.lapp.com/e/lapp/FMNziTRKHY-Vh3MqiS4zWg~~/DB53105110EN.pdf — LAPP *SKINTOP HYGIENIC / HYGIENIC-R* data sheet | **partial** — material and temperature block, M12/M16 rows | curl + plain-Chrome UA, 200, 188 252 B, `%PDF-1.5` | raw text (`pdftotext -layout`) | validated | **yes** — the FKM seal that rejects HYGIENIC-R |
| S19 | https://oringhandbook.com/materials/fkm-viton/ | **partial** — the FKM limitations paragraph | headed Chrome over CDP, 200 | raw text (DOM) | validated | yes — FKM's ammonia/strong-base and hot-water exceptions. **Secondary source**, not Parker's own chemical table — see the caveat below |
| S20 | https://www.agst.de/4305?lang=en (PREN 17.0–20.7 for 1.4305), corroborated by two further stainless suppliers on the MnS-inclusion point | **partial** — the PREN figure and the pitting-initiation statement | search index + headed Chrome, 200 | raw text | validated across three independent vendors | yes — the bg 212VA rejection |
| S21 | https://www.pflitsch.de/de/kabelverschraubungen/zubehoer-din-artikel-werkzeuge/gegenmuttern/gegenmutter-metrisches-gewinde-edelstahl/ | **inspected** — full locknut ordering table | headed Chrome over CDP, 200 | raw text (DOM) | validated | yes — the 2,8 mm M12 locknut height |
| S22 | https://www.automation24.de/edelstahl-kabelverschraubungen-metrisch (both result pages) | **inspected** — all M12 rows with prices and stock state | headed Chrome over CDP, 200 | raw text (DOM) | validated | yes — bg 212VA single-unit price and availability |
| S23 | https://www.automation24.de/pur-sensorleitung-hochflexibel-lapp-unitronic-sensor-fd-lif9y11y-4x0-25-7038890 | **inspected** — full technical-data table | curl + plain-Chrome UA, 200, 1 124 466 B | raw text (parsed DOM) | validated | **yes** — §0's OD, temperature range and price for the ordered cable |

**One row is not clean and the claim resting on it is load-bearing.** S11: the
LiYY temperature range **−5…+70 °C flexed / −40…+80 °C fixed** was read from a
Google result snippet quoting a LAPP product-information PDF that returned 403 to
a plain-Chrome-UA curl. I did not climb the ladder on it, because the LiYY
rejection in §2 does not depend on that figure alone. **Update 2026-09-05:** an
independent review established that two of those supposed independent
disqualifiers — "no UV rating" and "no chemical resistance" — are contradicted by
LAPP's current catalogue, and that S11's URL is for article 1030240, a **5×0,34**
cable, not the 4×0,34 in question. Both corrections are folded into §2. The
practical effect is that the LiYY rejection now leans harder on this one
unvalidated temperature figure than the paragraph below assumed.
But the specific "72.1 °C exceeds the flexed rating" sentence **rests on an
unvalidated intermediary extraction**, and should be reverified against the LAPP
document before it is quoted anywhere else.


**A second unclean row, disclosed for the same reason as S11.** S19 is a
seal-vendor handbook, not Parker's own chemical-compatibility table, and the
claim resting on it is load-bearing: it is the sole reason SKINTOP HYGIENIC-R —
otherwise the best geometric fit found — is rejected. FKM's incompatibility with
ammonia and amines is textbook and is not seriously in doubt, but the *specific*
claim that matters here is unquantified in a way this source cannot settle:
**nobody has established the NH₃ concentration in a windrow at 30 cm, nor FKM's
degradation rate at that concentration and 72 °C.** The rejection is therefore
argued as material-class risk avoidance — do not choose the one elastomer with a
named exception for the one chemical the environment is known to produce — and
**not** as a demonstrated failure. If HYGIENIC-R were the only orderable part,
this row would need Parker's own table and a windrow NH₃ measurement before it
could carry the decision. It is not, so the cheap move is to sidestep it.

Browser-control proof for the 2026-09-05 gland work (`online-research` §0):
headed Google Chrome 152.0.7977.77, scratch profile at `…/scratchpad/chrome-gland`,
own CDP port allocated from the ephemeral range and verified free before launch,
ownership confirmed against the launching PID's command line. Playwright over CDP;
`about:blank` navigated, `document.readyState` = `complete`,
`document.body.outerHTML` = `<body></body>` read from the live DOM,
`navigator.userAgent` = Chrome/152.0.0.0 with no `HeadlessChrome`.

Browser-control proof for the 2026-09-04 cable work: headed Google Chrome 152.0.7977.77,
scratch profile at `…/scratchpad/chrome-research`, own CDP port 54113 — port
verified free before launch and ownership confirmed against the launching PID's
command line. Playwright over CDP; `about:blank` navigated, `document.readyState`
= `complete`, `document.body.outerHTML` = `<body></body>` read from the live DOM,
`navigator.userAgent` = Chrome/152.0.0.0 with no `HeadlessChrome`.
