# Heated 12 V packs in the 20–30 Ah class, and the DIY heating route

Research date **2026-09-05**. Commissioned to test `POWER.md` §3.5's bounded
absence claim — *"No heated 12 V 20 Ah pack exists in this class — LIONTRON's
self-heating Arctic line starts at 100 Ah / €978"* — which was bounded to
LIONTRON's own catalogue and Offgridtec on 2026-09-04 at medium confidence.

**That claim is now falsified in its strong form, and the finding does not move
the recommendation.** Two heated packs below 100 Ah exist and one is EU-stocked.
But the arithmetic in §3 shows that heating a battery is unaffordable at this
site's December energy budget *at any pack size*, which is a stronger argument
for AGM than the sourcing gap ever was.

## 1. What exists

### 1.1 LiTime 12 V 30 Ah "Ice Fishing" — the only genuine 20–30 Ah heated pack found

`litime.com/products/12v-30ah-lithium-ice-fishing-battery-with-bluetooth`,
inspected 2026-09-05. Direct evidence, vendor specification, from the product
page's own spec table:

| parameter | value |
|---|---|
| capacity / energy | 30 Ah / 384 Wh, 12.8 V, 4S |
| weight | 2.8 kg (6.17 lb) |
| ingress | IP65, ABYC E-13, CE / RoHS / UN38.3 / FCC |
| BMS | 20 A; 20 A max continuous charge and discharge |
| charge temperature | **−20 °C to 50 °C** (i.e. with heating) |
| discharge temperature | −20 °C to 60 °C |
| automatic charge off | < 0 °C · recovery ≥ 5 °C |
| heating range | charge: −20 °C to 5 °C |
| heating time | 40–60 min from −10 °C; 60–80 min from −20 °C |
| **required minimum charge current for heating** | **5 A** |
| Bluetooth | yes, LiTime app; dual-mode (Regular / Energy-Saving) heating |
| price | $209.99 (from $299.99), listed 49 in stock |

**The 5 A row is the disqualifier, and it is the vendor's own number** — see §3.2.
The heater is powered from the charger, not from the pack, so it arms only when
an external source can deliver ≥ 5 A.

**Not EU-sourceable as of 2026-09-05.** Searched litime.de's own catalogue: it
returns a 12 V 20 Ah *Basic* (no heating, out of stock, €115,99) and a 12 V 50 Ah
*Low-Temp* (cut-off, not heating, €205,99). The DE self-heating line starts at
12 V 100 Ah. The 30 Ah model appears on litime.com, ca.litime.com, amazon.com,
amazon.ca and walmart.com only.

### 1.2 EPEVER 12.8 V 50 Ah with charging-heating — the smallest EU-stocked heated pack

`solarv.de`, SolarV GmbH, Schwalbach am Taunus; SKU 4912064-EPEVER, MPN
**LFP0.64KWH12.8V-P65L2GT40**, EAN 4260558576235. **€142,82 at 0 % USt §12 Abs. 3
UStG / €169,95 incl. 19 %**, listed *available immediately*. 640 Wh, 4S1P, 7.6 kg,
260 × 168 × 210 mm, IP65, Bluetooth, ≥4000 cycles @ 80 % DoD, 3-year warranty.

**The heating function is unquantified in the primary, and that is a finding.**
The datasheet (2 pages, image-only PDF, read as rendered pages 2026-09-05) lists
*"Charging Heating Technique"* as a bullet feature and nothing more: no heater
power, no trigger condition, no minimum charge current, no lower ambient bound.
Its temperature row still reads **`Charge: 0 °C~+50 °C`**. The manual (text-layer
PDF, grepped) mentions heat only in safety warnings. The only description of what
the heater does is the shop's own prose — *"integrated self-heating keeps the
battery temperature above 0 °C at all times during charging"* — which is a
retailer claim, not a manufacturer specification.

So this pack cannot be compared to the LiTime on the axis that matters. **Its
published charge window is no better than the LIONTRON's 0 °C floor that §3.4
rejected.** Buying it would mean trusting an unspecified heater to extend a
specification the datasheet does not extend.

### 1.3 Everything else starts at 100 Ah

Checked catalogues on 2026-09-05: LiTime (US and DE), Redodo, Power Queen,
Vatrer, Renogy, Enjoybot, Battle Born, Eco-Worthy, Ultimatron, Supervolt,
Bulltron, LiThink, LIONTRON. Every self-heating line found begins at 12 V 100 Ah;
Supervolt's heated JUMBO is 520 Ah, Battle Born's heated kits are 100 Ah,
Vatrer's start at 100 Ah and run to 600 Ah. Below 100 Ah the feature offered is
**low-temperature cut-off**, not heating — Enjoybot and LiTime both file a 12 V
30 Ah under "cold weather" while the feature is cut-off only. The two terms are
routinely conflated in listing copy; check the spec table, not the badge.

## 2. The DIY route

This is the more interesting branch, because it decouples the heater from the
pack and puts the trigger condition under our control.

### 2.1 BMS with a heating port

**JK BMS (Jikong).** Vendor guide `shop.jkbms.com/jkbms-heating-function-setup-guide/`,
inspected 2026-09-05, last updated 2026-09-04. A heating film connects between the
board's **HT−** wire and pack **P+**. For **4–8S: max 20 A at 32 V, <15 A
recommended** — ample for a 12 V pack.

Its trigger logic is materially better than the LiTime's. Heating needs a
mandatory temperature trigger (below the "Heating Start" setting on ≥V19.05, or
below the charge low-temperature protection limit on older firmware) **plus at
least one** of:

- charger output voltage higher than battery voltage — *an MPPT satisfies this
  whenever the sun is up, with no current floor*;
- 12 V auxiliary power detected;
- charging current present (V19.05+);
- **discharge heating** (V19.05+, app-enabled): heats from the pack itself when
  discharge current exceeds the sampled heating current.

Vendor safety instruction, worth honouring on an unattended outdoor box: put a
**45–65 °C normally-closed thermal switch in series** with the heating circuit as
a second layer against a stuck-on failure.

**JBD (Jiabaida).** 4S LiFePO4 200 A BMS with integrated heating module exists
(e.g. srikobatteries.com listing, metadata only — not inspected). JBD is the
protocol `POWER.md` §3.4 already identified as decoded by `BMS_BLE-HA`, so this
route would deliver the BLE telemetry requirement natively rather than through
the Smart Battery Sense.

### 2.2 Heating elements, EU

- **Hawco (UK)**, `hawco.co.uk` — 12 V silicone rubber heater mats, adhesive
  backed, **1.25 W to 80 W**, 25–400 mm, ~5 working days. This is the right power
  granularity for a 30 Ah pack; the 100 W pads that ship inside RV batteries are
  sized for 100 Ah.
- **Mi-Heat carbon film**, `infrarot-fussboden.de` (DE) — 12 V AC/DC, **130 W/m²
  ±10 %**, only **0.366 mm** thick, 98 % conversion. 50 cm wide: €34,90/m
  (= 65 W), up to €104,70 for 3 m (195 W), incl. 19 % USt, in stock. Also a 30 cm
  / 220 W/m² width and a 14 cm width separable every 3.5 cm. Vendor names
  *"Temperierung für Akkukoffer, Wohnmobil-Batterie, Lithium-Akkus im KFZ"* as an
  intended use.
- **Embro** (DE, `embro-tech.com`) — OEM lithium battery heating mats, made in
  Germany. Metadata only; OEM channel, likely no small quantities.

### 2.3 Controller

Either the BMS heating port (§2.1, no separate controller and the temperature
sensor is already in the pack), or a standalone 12 V DC thermostat — Mi-Heat M3,
€59,90 at infrarot-fussboden.de. The BMS port is the better shape here: one fewer
box, and the trip point is the same sensor the charge protection uses.

## 3. Why none of it is bought — the energy arithmetic

All figures below are **calculated** by me from `POWER.md` §3.1–3.2 inputs and the
vendor specifications above; assumptions are named where they are mine.

### 3.1 What the panel actually delivers in the worst December

`POWER.md` §3.1: worst December of 19 years at 70° tilt, St. Peter (48.01475 N,
8.03294 E), PVGIS v5.3 = **0.96 kWh/m²/d**; end-to-end harvest factor **0.70**;
panel bought **100 Wp**.

    100 W / 1000 W/m² × 0.96 kWh/m²/d × 0.70 = 67 Wh/d

Mean December (1.90 kWh/m²/d) gives 133 Wh/d. Probe load at the shipping heater
duty (`HEATER_MAX_DUTY = 0`) is **4.1 Wh/d**.

### 3.2 The LiTime pack's heater cannot arm on this system

Its precondition is **≥ 5 A charge current**. A 67 Wh day spread over ~8 h of
usable winter daylight averages ~8 W ≈ **0.65 A** at 13 V. Sustaining 5 A means
65 W out of a 100 Wp module — about 65 % of STC — which does not happen on a
0.96 kWh/m²/d day. Even the mean-December day averages ~1.3 A.

So on the darkest, coldest days, the days the heater exists for, **the heater
never turns on**, and the pack degrades to a plain low-temperature-cut-off
battery. This is not a marginal call: the trigger is off by roughly an order of
magnitude at the design point.

### 3.3 And a heating cycle costs a whole December day

Sensible heat to bring the 2.8 kg LiTime pack from −10 °C to +5 °C, assuming
c ≈ 1.0 J/(g·K) for a packaged LFP cell (typical published range 0.9–1.1 — **my
assumption, not a vendor figure**), zero loss to ambient:

    2.8 kg × 1000 g/kg × 1.0 J/(g·K) × 15 K = 42 kJ = 11.7 Wh

The vendor's own numbers put the real draw far higher: ≥5 A at ~13 V for 40–60 min
from −10 °C is **≥ 43 Wh**, and that is a floor — minimum current at minimum time.
The implied efficiency (11.7/43 ≈ 27 %) is what an uninsulated ABS case in moving
air would give, so the number is self-consistent.

**One preheat ≈ 43–65 Wh against a worst-December harvest of 67 Wh/d, and against
a probe load of 4.1 Wh/d.** A single heating event costs about ten days of probe
operation, or one entire bad December day of production.

### 3.4 Holding the pack warm is worse, insulation included

The DIY alternative to preheating is to hold the pack above 0 °C continuously in
an insulated box. Take 30 mm PU (λ ≈ 0.025 W/m·K → U ≈ 0.83 W/m²K) around the
30 Ah pack, mean wall area ~0.22 m², holding +5 °C against −10 °C ambient:

    0.83 W/m²K × 0.22 m² × 15 K = 2.7 W = 66 Wh/d, sustained

That is the entire worst-December harvest, before the probe draws anything.
Doubling to 60 mm PU halves it to ~33 Wh/d — still half the harvest, for weeks on
end. Around the larger 7.6 kg EPEVER (mean area ~0.34 m² at 30 mm) it is 4.2 W =
**102 Wh/d**, more than a bad day produces.

The conclusion is insensitive to pack size, insulation thickness, and which
vendor's heater: **at 715 m in December, heat is a bigger load than everything
else on this system combined.** The 0.70/×2.5 margin structure in §3.2 was built
for snow and soiling; a heater eats it whole.

### 3.5 AGM's cold-charge acceptance costs 0 W

This is the point. §3.4 of `POWER.md` chose AGM because its charge floor is
−20 °C with no lockout. The survey above shows the lithium workaround exists but
is powered by a budget this site does not have in the month it is needed. The
sourcing gap was never the real objection — **the energy budget is**, and that
objection does not expire when a 30 Ah heated pack comes to market.

## 4. What would change this

- **Mains reachable at the windrow.** `POWER.md` §4 already flags this; it moots
  the whole document, heater included.
- **A much larger array.** A heater needs its own energy budget, roughly a
  doubling of installed Wp, not a margin taken out of the existing one.
- **The battery box below the frost line.** Already named in `POWER.md` §3.3 —
  it removes the need for a heater rather than paying for one.
- **A LiTime 30 Ah with a lower heating trigger.** If LiTime ever publishes a
  minimum charge current in the 1 A class, or the discharge-heating mode of a JK
  BMS build is used instead, §3.2 changes but §3.3–3.4 do not.

## 5. Source access log

All rows attempted 2026-09-05. Browser: Playwright 1.x driving **real Chrome**
(`channel="chrome"`), headless, plain-Chrome UA override, de-DE locale.
Control proven by `about:blank` navigation + DOM read before any fetch. (The
Playwright MCP profile was held by a concurrent session; routed around with an
own-process browser rather than contending for it.)

| # | source | evidence state | attempt history | route | validation | load-bearing |
|---|---|---|---|---|---|---|
| 1 | `https://www.litime.com/products/12v-30ah-lithium-ice-fishing-battery-with-bluetooth` | **inspected** (full spec table incl. TEMPERATURE and SELF-HEATING blocks) | headless real-Chrome + plain UA, 200, 20 027 chars | raw text (DOM) | validated (DOM self-validating) | **yes** — §1.1, §3.2, §3.3 |
| 2 | `https://www.litime.com/collections/self-heating-batteries` | inspected (collection listing + filter facets) | as above, 200 | raw text (DOM) | validated | yes — §1.1 |
| 3 | `https://www.litime.de/search?type=product&q=eisangeln+30Ah` | inspected (5 results, full facets) | rung 0 correction: composed URL `/collections/selbstheizende-lifepo4-batterien` returned a genuine 404, replaced with the site's own search endpoint, 200 | raw text (DOM) | validated | yes — §1.1 EU-availability negative |
| 4 | `https://solarv.de/EPEVER-LiFePO4-Batteries-128V-50Ah-205Ah-integrated-BMS-Self-heating-function-under-0C-A-Grade-LiFePO4-Cells` | **inspected** (description, variant list, spec table, PDF link list) | headless real-Chrome, 200, two passes (second for link extraction) | raw text (DOM) | validated | **yes** — §1.2 |
| 5 | `https://solarv.de/Datenblatt/2024/10/EPEVER/4912/LFP0.64KWH12.8V-P65L2GT40_Datasheet_EN.pdf` (rev undated, SolarV © 2024) | **inspected** (both pages) | curl + plain-Chrome UA, 200, `%PDF` magic confirmed, 596.8 KB; `pdftotext -layout` yielded 2 bytes → **image-only PDF**; recovered by rendered-page read | OCR / rendered-page vision | validated (rendered pages read directly; the `Charge: 0 °C~+50 °C` row and the "Charging Heating Technique" bullet both read off the page image) | **yes** — §1.2 |
| 6 | `https://solarv.de/Datenblatt/2024/10/EPEVER/4912/LFP0.64KWH12.8V-P65L2GT40-Manual-EN-V1.0.pdf` V1.0 | **partial** — searched for heating/temperature content; found only safety-warning mentions | curl + plain-Chrome UA, 200, text layer present (6 452 chars) | raw text | validated | yes — supports the "unquantified heater" finding in §1.2 |
| 7 | `https://www.shop.jkbms.com/jkbms-heating-function-setup-guide/` (last updated 2026-09-04) | **inspected** | headless real-Chrome, 200 | raw text (DOM) | validated | **yes** — §2.1 |
| 8 | `https://infrarot-fussboden.de/12V-Heizfolie-50cm-130W` (Art. 626, Mi-Heat) | **inspected** (variants, prices, description) | headless real-Chrome, 200 | raw text (DOM) | validated | yes — §2.2 |
| 9 | `https://www.hawco.co.uk/industrial/process-heating/silicone-rubber-heater-mats/12v-silicone-rubber-heater-mats/` | **partial** — category page: power range and size range read; individual part numbers not opened | headless real-Chrome, 200 | raw text (DOM) | validated | yes — §2.2 |
| 10 | `https://srikobatteries.com/product/jiabaidajbd-smart-bms-lifepo4-4s-200a-bms-with-bluetooth-integrated-heating-module/` | **metadata only** — search-result title/description | not fetched | route: none | n/a | no — §2.1 names it as an existence pointer only |
| 11 | `https://embro-tech.com/batterieheizung-lithium-ionen-akkus/` | **metadata only** | not fetched | route: none | n/a | no |
| 12 | Vendor catalogues surveyed for §1.3 (Redodo, Power Queen, Vatrer, Renogy, Enjoybot, Battle Born, Eco-Worthy, Ultimatron, Supervolt, Bulltron, LiThink) | **metadata only** — collection titles and listing copy via search results; no product page opened | not fetched individually | route: none | n/a | yes, jointly — bounds §1.3; see the confidence statement below |
| 13 | `POWER.md` §3.1–3.2 (this repository) | inspected | local read | raw text | validated | **yes** — every input to §3 |

**Non-clean rows restated:** #5 is `OCR / rendered-page vision` (image-only PDF, no
text layer) — its two load-bearing readings are the charge-temperature row and the
absence of any heating specification. #6, #9 are `partial`. #10, #11, #12 are
`metadata only`; §1.3's claim rests on them and is bounded accordingly.

## 6. Search record for the absence claims (§3 of the skill)

**Claim A — "no self-heating 12 V pack exists in the 20–30 Ah class."**
**Refuted.** The LiTime 12 V 30 Ah (§1.1) is a counterexample with a published
heating specification. `POWER.md` §3.5's paragraph must be corrected.

**Claim B — "no self-heating 12 V pack in the 20–30 Ah class is EU-sourceable."**
Searched 2026-09-05 on Google via Serper, `country=DE`/`search_lang=de` for the
German axes and default US for the English ones. Query axes, chosen to be
independent: (a) feature vocabulary EN — *self-heating / heated / heating pad /
low temperature*; (b) feature vocabulary DE — *selbstheizend / Selbsterwärmung /
mit Heizung / Heizfunktion / Niedertemperatur / beheizt*; (c) capacity-anchored —
*12V 20Ah*, *12V 30Ah*, *12V 40Ah*, *12V 50Ah* crossed with (a) and (b);
(d) vendor-anchored — the eleven brands in row 12 plus LIONTRON, named explicitly;
(e) site-scoped — `site:litime.de`, plus litime.de's own product search;
(f) application-anchored — ice fishing, trolling motor, RV, off-grid.
Followed into vendor catalogues where a hit appeared. Stopped on saturation: axes
(a)–(f) converged on the same 100 Ah-and-up set plus the two exceptions in §1.
**Result:** no 20–30 Ah heated pack in EU distribution; the smallest EU-stocked
pack claiming integrated heating is the EPEVER 50 Ah (§1.2), and its heater is
unspecified in the manufacturer's own documents. **Confidence: medium**, limited
by row 12 — the eleven brand catalogues were read through search-result copy
rather than opened page by page, and grey-market EU importers were not enumerated.

**Challenge search (§2.1 of the skill).** The query run specifically to refute the
"nothing below 100 Ah in the EU" conclusion — `"self-heating" OR "mit Heizung"
LiFePO4 12V 50Ah OR 40Ah OR 30Ah Europe kaufen beheizte Batterie klein`, DE —
is what surfaced the EPEVER 50 Ah at solarv.de. The refutation query worked; it
found the counterexample the confirmatory queries had missed. That counterexample
is in §1.2, and inspecting its primary is what revealed the heater is
unquantified — which is a different and more useful finding than the shop copy.

## 7. What would discriminate

- **EPEVER's heating specification.** If EPEVER publishes heater power, trigger
  condition and lower ambient bound for LFP0.64KWH12.8V-P65L2GT40, §1.2 becomes
  comparable to §1.1 and can be judged on §3's arithmetic rather than dismissed
  for being unspecified. Ask SolarV or EPEVER directly — this is a vendor email,
  not a search.
- **A measured December harvest.** §3 rests on PVGIS worst-year modelling. One
  winter of VE.Direct or SmartShunt data from the installed array would replace
  the modelled 67 Wh/d with a measured one and settle whether any heating budget
  exists at all. If the measured worst week comes in above ~200 Wh/d, §3.4's
  hold-warm option reopens; below ~100 Wh/d it is permanently closed.
