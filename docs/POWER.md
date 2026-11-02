# Power: what the probe costs, and what has to feed it

**Status: a budget, not a measurement.** Exactly one term in it has been
measured, and it is not the one that matters. Read §1 before using any number
below to buy anything.

The probe cannot share the LoRaWAN node's supply. `tech/RS485-LS-SMT100.md`
§"Power: not from this node" settles that: the Dragino's `+5V` output is gated
by `AT+5VT` and power-cycles the sensors before every sample, while the cell
restarts a 15-minute settling timer whenever its bias drops. Under `AT+5VT`
pulsing the oxygen channel would never leave `SETTLING`. So the probe gets a
**dedicated always-on 7–15 V supply**, and shares only A/B and a common ground
with the node. This document sizes that supply as a solar island.

## 1. The one number that decides everything is unmeasured

| term | value | provenance |
|---|---:|---|
| membrane heater, full on | **1.03 W** (86 mA at 12 V) | 140 Ω ring, `RING-PCB.md` §1 / `DESIGN.md`. Arithmetic: 12²/140. |
| board electronics | ~40 mW at 12 V (3.3 mA) | **estimate, never measured** — see §2 |
| charge-controller idle | 0.12 W (10 mA at 12 V) | Victron SmartSolar MPPT 75/10 datasheet, *load output off* |
| **heater duty cycle** | **unknown** | — |

The heater is 26× the rest of the board. Every panel and battery figure in §3 is
therefore a function of a duty cycle nobody has measured, and the spread across
plausible duties is a factor of seven in daily energy.

What is actually known about the duty:

- `CONDENSATION-MODEL.md` fixes the *target*, not the power: the Apogee SO-431
  precedent heats its Teflon membrane ~2 K above ambient, and Buck-1996 puts a
  surface 2 K warm at ~90 % local RH in saturated 40–60 °C gas, 4 K at ~82 %.
  That document is explicit that the SO-431 figure "is a precedent, not proof
  that 2 K is sufficient for this probe".
- `HEATED-SPREADER.md` §1 shows the entire coupling question turns on the
  membrane-side heat-transfer coefficient `h`, which is unmeasured. Below
  h ≈ 7 W/m²K the existing dry-side heater already reaches η ≥ 0.5; above
  h ≈ 25 nothing works without a spreader. The duty needed to hold 2 K is on
  the far side of that same measurement.
- Firmware v0 ships the heater **hard-disabled** (`HEATER_MAX_DUTY` = 0), pending
  the TMP117 alert fault test. So the duty today is 0 %, and `README.md` says
  do not bury a v0 probe precisely because of that.

**Consequence for procurement: do not buy a panel against a guessed duty.** The
1.03 W is a *ceiling* set by the ring resistance; the loop will modulate below
it. §3 brackets the answer instead of picking one.

## 2. The board estimate, and how to retire it

Summing datasheet typicals for the parts on the 3V3 and +5V rails — STM32G071
running Modbus, ADS1119 in continuous conversion, TMP117, THVD1410 receiving,
I²C pull-ups, and the AZ431 shunt's 1.67 mA bias from `+5V_ANALOG` — gives about
7 mA on 3V3 and 1.67 mA on +5V, so ~31 mW out of the regulators.

**That 31 mW is not what the buck sees.** The 3V3 rail is fed by TPS7A2033 LDOs
*from the 5 V rail*, and an LDO passes its load current at the input voltage: the
7 mA of 3V3 load draws 7 mA at 5 V, not at 3.3 V. The buck's output is therefore

    5 V x (7 + 1.67) mA = 43.4 mW at 8.67 mA

and the 3.3 V drop is burned in the LDOs, by design. At that output current the
AP63205 curve (DS41326) is ~88 % for 12 V -> 5 V; taking 80 % as the conservative
figure and adding quiescent gives

    ~50 mW at 12 V, i.e. 4.1 mA

An earlier revision of this document said ~40 mW, having summed the rails without
charging the 3V3 load to the 5 V rail. The corrected figure is ~25 % higher. It
does not move any panel or battery size in Sec. 3 (the heater and the MPPT's own
idle both dominate it), but it is the number to compare a measurement against.

This is a paper number. It has never been measured, and it is the kind of number
that is routinely wrong by 2× in either direction — LDO quiescent, pull-up
choices and whether the MCU actually sleeps between Modbus frames are all
unverified here.

**It is measurable now**, on the bare-board first article, with a bench supply
and a current meter on the 12 V input: one reading with the MCU idle, one during
a Modbus exchange. Do that before ordering, and replace this section with the
measurement. At the heater-off duty the board and the charge controller are the
*whole* load, so a 2× error here is a 2× error in the panel.

## 3. Sizing

### 3.1 Site irradiation

Steingrubenhof windrow site — 48.01475 N, 8.03294 E, 715 m (`memory:
steingrubenhof_site_wind`). PVGIS v5.3, SARAH3, 2005–2023, DEM-calculated
horizon (so terrain shading is included), plane azimuth south.

Tilt sweep, to pick the angle. December is the binding month and the annual
optimum (38°) is the wrong angle for it:

| tilt | Dec mean | Dec worst yr | Nov–Jan mean | annual |
|---:|---:|---:|---:|---:|
| 40° | 52.4 | 28.4 | 58.6 | 1387 |
| 50° | 55.9 | 29.6 | 62.1 | 1365 |
| 60° | 58.1 | 30.0 | 64.0 | 1313 |
| **70°** | **58.8** | 29.8 | **64.4** | 1232 |
| 80° | 57.9 | 29.0 | 63.1 | 1125 |
| 90° | 55.6 | 27.5 | 60.3 | 993 |

kWh/m²/month, except annual (kWh/m²/yr). **Use 70° south.** It is the December
optimum, it is flat across 60–80° so mounting tolerance is irrelevant, and the
steep angle sheds snow — which the table cannot price but which is the difference
between a working and a dead panel on an exposed Black Forest site in January.

Design irradiation at 70°:

| month | worst year (19 y) | mean |
|---|---:|---:|
| November | 0.97 kWh/m²/d (2023) | 2.33 |
| **December** | **0.96 kWh/m²/d (2011)** | 1.90 |
| January | 1.29 kWh/m²/d (2023) | 2.08 |

Reproduce with:

```sh
curl -sS -G https://re.jrc.ec.europa.eu/api/v5_3/MRcalc \
  -d lat=48.01475 -d lon=8.03294 -d selectrad=1 -d angle=70 \
  -d outputformat=json -d startyear=2005 -d endyear=2023
```

`H(i)_m` is the monthly in-plane total in kWh/m². `use_horizon` defaults true.

### 3.2 The table

Daily energy includes the controller's 2.9 Wh/d idle. Panel figures are
break-even against the **worst** December of nineteen, times 2.5 — the multiplier
covers snow, soiling, and actually refilling a depleted battery rather than
merely holding station. Break-even Wp is `E / (H x 0.70)`, where `H` is the
worst-December daily in-plane irradiation from the table above and **0.70 is an
end-to-end harvest factor** — module derating from STC, MPPT conversion loss,
charge acceptance and wiring. It is **not** a tilt correction: PVGIS's `H(i)_m`
already reports energy in the 70° plane, so applying a tilt derate on top would
double-count. An earlier revision described 0.70 as an "MPPT/tilt" figure, which
was wrong in name though not in value.

A note on whether 0.70 and 2.5 double-count each other: they do not, but they
are close. With a 2.5x panel the nominal daily surplus is `1.5E`, so the 7-day
`7E` deficit the battery column defends against refills in about **4.7 clear
design-average days**. That implicit recovery target is what makes 2.5 coherent.
What the two factors cannot do is each absorb the full margin simultaneously —
snow, soiling and post-outage recharge are competing claims on the same surplus,
not independent ones. Battery is 7-day autonomy, AGM at 50 % DoD with a 0.7
cold-capacity derate.

| heater duty | load | energy/day | break-even Wp | x2.5 | panel bought | actual x | battery |
|---|---:|---:|---:|---:|---:|---:|---:|
| **0 %** — what v0 ships | 50 mW | 4.1 Wh | 6.1 | 15.2 | ~15 Wp | 2.5 | 12 V 7 Ah |
| 25 % | 307 mW | 10.3 Wh | 15.3 | 38.1 | ~40 Wp | 2.6 | 12 V 20 Ah |
| **50 %** | 564 mW | 16.4 Wh | 24.4 | 61.1 | **~60 Wp** | **2.45** | **12 V 30 Ah** |
| 100 % | 1078 mW | 28.8 Wh | 42.8 | 107.0 | ~100 Wp | 2.34 | 12 V 50 Ah |

The **actual x** column is there because the last two rows do not quite reach the
2.5 the paragraph above claims: rounding to catalogue sizes lands at 2.45 and
2.34. That is disclosed rather than hidden by inflating the panel, because 2.5
is itself a judgement, not a derived requirement — but do not read the 100 % row
as carrying the full stated margin. If you want a true 2.5 at 100 % duty, buy
110 Wp.

**Recommendation: 60 Wp at 70° south, 12 V 30 Ah AGM, Victron SmartSolar MPPT
75/10.** That covers 50 % duty against the worst December *total* in the record
and 100 % duty against a typical one. It is a deliberate over-buy against Sec. 1's
ignorance, and it is cheap insurance: the difference between the 40 Wp and the
60 Wp panel is smaller than one wasted winter of missing data.

**What a monthly total cannot tell you.** `H(i)_m` is a month's energy. It
contains no day-to-day sequence and no snow-cover outage, so "carries through the
worst December" means *the month's energy balance closes*, not *the probe never
browns out*. A December can hold adequate total energy and still contain a
week-long dark or snow-covered run that empties the battery. The 7-day autonomy
column is what is actually defending against that, and it has never been checked
against a daily series. To make the uninterrupted-operation claim properly, run
PVGIS `seriescalc` at daily resolution over the same 19 years and count the
worst run of consecutive sub-load days. Until then, treat winter continuity as
argued, not demonstrated.

### 3.3 Three decisions inside that recommendation

**Decision history, because it turned twice.** Fab first overrode the AGM
recommendation for LiFePO4, then reconsidered ("maybe LiFePO4 without heater is
not the best choice") and asked for the alternatives. **§3.4 is where that lands
and supersedes this paragraph's conclusion** — AGM, but for a different and
better reason than the one below, and with the battery telemetry Fab wanted
obtained a different way.

**The original argument for AGM — the charging floor, not the chemistry.** A 4S
LiFePO4 pack sits nicely inside the probe's 7–15 V window (10.0 V cutoff to
14.6 V absorption), is lighter, and cycles better. But its BMS will refuse to
*charge* below 0 °C, and at 715 m in the Black Forest that lockout lands on
exactly the weeks with the least sun and the most need for margin — the failure
mode is a pack that is both cold and empty and will not accept the little charge
that is available. AGM accepts charge to −20 °C with no lockout; the price is
capacity derate (already in the 0.7 factor above) and a shorter service life
(§3.6, which is where the numbers actually come from). Revisit
only if the battery box ends up buried below the frost line, or the pack has a
self-heating BMS.

**Take the load off the battery, not off the controller's load output.** The
Victron 75/10's self-consumption is 10 mA with the load output off and 19 mA with
it on. That 9 mA delta is 2.7× the entire board draw. The load output's
low-voltage disconnect is not worth it here — and disconnecting the probe to save
the battery would restart the cell's 15-minute settling timer anyway, which is
the same reason §0 rejected the Dragino's `+5V` rail.

**Wire up VE.Direct — but it will not retire the load estimate.** It puts battery
voltage and charge current into Home Assistant, which is worth having. What it
does *not* give you is this probe's consumption: the paragraph above deliberately
wires the load **directly to the battery**, bypassing the controller's load
output, and the 75/10 can only report current through its own terminals. A load
hung on the battery is invisible to it. An earlier revision of this section
claimed the load current would fall out of VE.Direct and retire Sec. 1 and Sec. 2's
estimates; that was wrong, and the two claims contradicted each other.

To actually measure the draw, pick one:

- a **Victron SmartShunt 500 A** in the battery negative (~€120) — BLE and
  VE.Direct, reads the true load including the heater's duty, and is the only
  option that also gives real state-of-charge on an AGM;
- run the probe **through the controller's load output** after all, paying the
  9 mA and accepting the low-voltage disconnect;
- a **bench session** with a current meter, which costs nothing and answers Sec. 2
  in an afternoon.

The SmartShunt is the honest recommendation if the heater is ever enabled, since
duty is the one number Sec. 1 says decides the whole system.

### 3.4 Chemistry and battery telemetry

Fab added a requirement partway through sourcing: the battery should expose a
**BLE BMS speaking a protocol that is already decoded**, so its state reaches
Home Assistant. That requirement turns out to be satisfiable on *any* chemistry,
which is what breaks the deadlock.

**The decoded-protocol landscape**, from the `BMS_BLE-HA` integration's supported
list (`github.com/patman15/BMS_BLE-HA`, read 2026-09-04):

- **JBD / Jiabaida / Xiaoxiang** is the de-facto standard in cheap drop-in packs,
  and the integration names **LIONTRON, Ultimatron, accurat, ECO-WORTHY, CHINS,
  Eleksol, LANPWR** and a dozen more as JBD-protocol batteries. Note what this
  does and does not establish: those *named* families are supported. It is not
  evidence that an arbitrary "smart" LiFePO4 in this class will work — discovery
  in that integration keys off BLE name patterns, and vendors change BMS supplier
  and firmware without changing the model name. **Check the exact pack model
  against the supported list before ordering**, and do not treat "it's JBD
  inside" as a specification you can rely on unless the vendor states it.
- **JK / Jikong** (HW ≥ 6), **Daly**, **Seplos**, **Renogy**, **Redodo**,
  **Ective**, **Offgridtec LiFePo4 Smart Pro** (`SmartBat-A…`/`-B…`) are
  separately supported.
- **Victron's own BLE** ("Instant Readout") is a different and better-documented
  route, read in HA by the `victron_ble` integration, and it is **chemistry-
  agnostic** — a Victron **Smart Battery Sense** bolts onto a lead-acid battery
  and publishes voltage *and temperature* over BLE.

That last point is the one that matters, because it decouples the telemetry
requirement from the chemistry requirement.

**The comparison, at this system's actual load:**

| | cold charging | BLE, decoded | cost | verdict |
|---|---|---|---|---|
| **AGM + Victron Smart Battery Sense** | **to −20 °C, no lockout** | Victron Instant Readout, `victron_ble` | **~€107** | **recommended** |
| LiFePO4, no BLE (Offgridtec 12/30, LIONTRON LX) | −5 °C (LIONTRON) | none | €65–275 | fails the new requirement |
| LiFePO4 + JBD BLE (LIONTRON Smart, Ultimatron, accurat) | −5 °C typ. | JBD, `BMS_BLE-HA` | ~€250+ | works; cold floor remains |
| LiFePO4, self-heating (LIONTRON Arctic) | full | yes | €978 @ 100 Ah | right answer, wrong size |
| **NMC / NCM** | **0 °C, and the failure is plating** | varies | — | **reject, see below** |
| LTO | to −30 °C | rare | niche | the actually-correct cold chemistry, not sourced |

**Why AGM wins here, having argued against it in §3.3.** The objection to AGM
was cycle life at depth. At this load that objection evaporates: a 25 Ah AGM
holds 300 Wh, and 16,4 Wh/day is **5,5 % depth of discharge per day**. Victron's
current Super Cycle datasheet rates it at **>=300 cycles @ 100 % DoD, >=700 @ 60 %,
>=1000 @ 40 %** (verified in the datasheet 2026-09-05). An earlier revision of
this document cited "300 @ 80 % and 2500 @ 20 %" — **neither figure appears in the
source**; they were invented. The datasheet's shallowest published point is 40 %,
and this system reaches 40 % nominal DoD only after 7.3 no-sun days at 25 % duty.
The conclusion survives the correction and is in fact better supported: the
published curve never descends to the depths that would make cycle life the
binding constraint here. The lithium advantage is
priced for a duty cycle this system does not have — while the lithium
*disadvantage*, a charge lockout in the coldest weeks, lands exactly where the
margin is thinnest.

And AGM gains something lithium does not offer here: the Smart Battery Sense
feeds battery temperature to the SmartSolar over VE.Smart Networking, so the
charge voltage is **temperature-compensated** — which is precisely what a
lead-acid battery living outdoors wants, and worth real capacity and life.

The datasheet makes that stronger than a preference. Victron specify
**−24 mV/°C for a 12 V battery, centred on 25 °C**, and state that temperature
compensation **is required** when the battery is below 10 °C or above 30 °C for
long periods. This install is below 10 °C for months at a time, so the Smart
Battery Sense is not an optional refinement bought for telemetry — it is the
datasheet's own condition for reaching the published life.

**Why NMC/NCM is rejected, on arithmetic rather than taste.** NMC cells charge to
4,2 V. A 4S pack is therefore **16,8 V fully charged, above the probe's 15 V
input ceiling** (`DESIGN.md`, 7–15 V) — a hard fail, not a derating. A 3S pack
(12,6 V full, ~9 V empty) does fit the window, but no standard solar controller
carries a 3S Li-ion profile, so it would need a hand-built one. And NMC's charge
floor is **0 °C — worse than the LiFePO4 it would be replacing** — with lithium
plating and a thermal-runaway path as the consequence, rather than LFP's merely
lost capacity. It is worse on every axis that matters here.

### 3.5 The buy list, by part number

Sourced 2026-09-04, all from **offgridtec.com** except where noted, so it is one
basket and one shipment. German solar hardware is 0 % USt under §12 Abs. 3 UStG;
where the vendor showed both figures, both are given.

| item | part | price | notes |
|---|---|---|---|
| panel | **Offgridtec MONO 100W V2 Black Frame**, MPN 3-01-018385 | €63,02 incl. / **€52,96** | Pmax 100 W, Vmp 23,9 V, **Voc 28 V**, Isc 4,4 A, 925 × 590 × 35 mm, 6,22 kg, MC4 leads |
| controller | **Victron SmartSolar MPPT 75/10**, SCC075010060R | €63,72 / **€53,55** | Bluetooth + VE.Direct |
| battery | **Victron AGM 12V 25Ah Super Cycle M5**, BAT412025081 | €64,74 / **€54,40** | 300 Wh; >=300 cyc @100 % DoD, >=700 @60 %, >=1000 @40 % — see the autonomy note below |
| battery telemetry | **Victron Smart Battery Sense Long Range**, SBS050150200 | **€42,48** | BLE V + T; VE.Smart Networking to the MPPT for temperature-compensated charging; `victron_ble` in HA |
| PV cable | Offgridtec 5 m 4 mm² MC4 → controller | €12,55 | |

≈ **€247 incl. VAT**, or ≈ €205 at 0 % USt. Free shipping over €100.

**The 25 Ah battery does not meet Sec. 3.2's 50 %-duty row, and that is a
deliberate, now-explicit choice.** The sizing formula asks for 27,4 Ah at 50 %
duty; the basket buys 25 Ah. Derated for cold and 50 % DoD it holds
`25 x 12 x 0.5 x 0.7 = 105 Wh`, which is:

| duty | Wh/day | autonomy on 105 Wh |
|---|---:|---:|
| 0 % (what v0 ships) | 4,1 | **26 days** |
| 25 % | 10,3 | **10,2 days** |
| 50 % | 16,4 | **6,4 days** — short of the 7-day target |

So the basket is sized for the **0–25 % duty band**, which is where the probe
actually is: firmware v0 ships `HEATER_MAX_DUTY = 0`. If the heater is enabled at
50 % or above, step up to the **Victron Super Cycle 12 V 38 Ah** (the next size in
the range) before burying anything. Earlier revisions of this document quietly
carried the 30 Ah requirement in the table and the 25 Ah part in the buy list
without reconciling them.

Alternates priced on the same day, if the decision moves:

| | part | price |
|---|---|---|
| bigger AGM | Offgridtec AGM 32Ah 20HR 12V, MPN 2-01-001480 | €58,43 / €49,10 |
| smaller AGM | Offgridtec AGM 17Ah 20HR 12V | €28,45 / €23,91 |
| cheapest LiFePO4 | Offgridtec LiFePo4 12/30, 12,8V 30Ah, MPN 020675 | €65,39 / €54,95 — no BLE |
| LiFePO4 with BLE | LIONTRON LiFePO4 12,8V 20Ah LX **Smart**, JBD protocol | ~€250+, shop.liontron.com |
| LiFePO4, no BLE | LIONTRON LI1220LX: 256 Wh, >=3000 cyc @90 % DoD, charge **0…+45 °C**, discharge −20…+60 °C, storage −40…+60 °C, **IP65**, 2,9 kg, 7-yr warranty | €274,99 Liontron / €229,95 pro-akkus |

Compatibility, checked rather than assumed:

- Voc 28 V against the controller's 75 V PV limit. Crystalline Voc rises as it
  cools at roughly −0,3 %/K, so a −20 °C morning puts it near 31 V — still under
  half the limit.
- Isc 4,4 A sits under the 75/10's **13 A maximum PV short-circuit current**, and
  100 W under its 145 W nominal PV power at 12 V.
- **Correction: 100 W is not this controller's panel ceiling.** An earlier
  revision rejected the €70,86 150 W module by dividing 150 W by 12,8 V to get
  11,7 A and calling it over the 10 A limit. That arithmetic is wrong in kind:
  10 A is the *battery charge* current, and Victron explicitly limit excess
  connected PV power rather than failing on it. The real PV-side limits are 75 V
  Voc and 13 A Isc. A 150 W module is disqualified only if it breaches those. It
  would clip on the brightest days, which at this load is irrelevant, and it
  would harvest more in December, which is not. If the 150 W module's cold Voc
  and Isc check out, it is a legitimate — arguably better — buy.
- The panel is 100 W where §3.2 asked for 60 Wp, because at €53 it costs less
  than most dedicated 60 W modules and the surplus lands exactly where the
  December worst case needs it.
- AGM absorption 14,4 V / float 13,5 V sits inside the probe's 7–15 V window, so
  the probe hangs directly on the battery as §3.3 requires.

**If a LiFePO4 is bought instead**, three things to get right: check its actual
ingress rating rather than assuming a bare-terminal pack (the LIONTRON LX is
**IP65**, not the IP20 an earlier revision of this document claimed, so the
enclosure argument is weaker than stated — but its **0 °C charge floor**, also
corrected upward from a claimed −5 °C, is a stronger objection than stated, and
the two corrections both push toward AGM); set the controller to LiFePO4 (absorption
14,2–14,4 V, float ~13,5 V, **equalisation off**) *before* connecting it; and
establish whether the BMS is common-port, because a common-port pack that opens
one MOSFET pair for both directions would cut the *probe* on a cold morning, not
just the charge — restarting the cell's 15-minute settling timer, which is the
exact failure §0 rejected the Dragino rail for.

**Correction, 2026-09-05: a heated pack in this class does exist, and it changes
nothing.** An earlier revision said *"No heated 12 V 20 Ah pack exists in this
class — LIONTRON's self-heating Arctic line starts at 100 Ah / €978"*, bounded to
LIONTRON and Offgridtec. Widening the search to eleven further brands falsified
it: **LiTime sells a 12 V 30 Ah self-heating pack** (384 Wh, 2.8 kg, IP65, BLE,
charge to −20 °C, $209.99) — US/CA only, not in litime.de's catalogue. The
smallest EU-stocked pack claiming integrated heating is the **EPEVER 12.8 V 50 Ah**
(€142,82 at 0 % USt, solarv.de), whose datasheet still specifies `Charge:
0 °C~+50 °C` and publishes **no** heater power, trigger, or ambient bound.

**But the sourcing gap was never the real objection — the energy budget is.** The
LiTime heater requires **≥ 5 A charge current** to arm; a 100 Wp array in the worst
December of §3.1 averages ~0.65 A, so the heater would never turn on in the month
it exists for. And one preheat from −10 °C costs ≥ 43 Wh against a worst-December
harvest of 67 Wh/d and a probe load of 4,1 Wh/d. Holding a pack warm continuously
in a 30 mm-insulated box costs 2,7–4,2 W, i.e. 66–102 Wh/d — the entire harvest,
sustained for weeks. Heat is a bigger load than everything else on this system
combined, at every pack size and insulation thickness checked. AGM's −20 °C charge
acceptance costs 0 W. The DIY route (JK BMS heating port, whose trigger is far
better matched — charger V > battery V, no current floor) is documented but fails
the same arithmetic.

Full survey, vendor-by-vendor, with the arithmetic and the source access log:
`HEATED-BATTERY-SURVEY.md`.

### 3.6 How long the battery lasts, and what actually ends it

**Victron publish no design life for the Super Cycle range.** The AGM Super
Cycle datasheet (fetched 2026-09-05) carries cycle life only — the three figures
quoted in §3.4 — and **no design life in years, no float life, no
self-discharge rate, and no temperature-vs-life table.** An earlier revision of
this document asserted "a 4–6 year life" with no source; that figure is
withdrawn. It is the same class of defect as the invented cycle numbers §3.4
already corrects, and it is recorded in the kb as
`~/dev/kb/power/victron-super-cycle-has-no-published-design-life.md`.

The nearest sourced comparator is Victron's **other** AGM line, in
`Datasheet-GEL-and-AGM-Batteries-EN.pdf`, Table 2, *design service life under
float service*:

| average temperature | AGM "Deep Cycle" | Gel "Deep Cycle" |
|---|---:|---:|
| 20 °C | 7–10 y | 12 y |
| 30 °C | 4 y | 6 y |
| 40 °C | 2 y | 3 y |

**That is a different battery**, and the table is an indicator rather than this
part's spec: the Super Cycle uses a carbon-additive chemistry, and the two lines
differ in cycle-life value *and* test method (Super Cycle 300/700/1000 at
100/60/40 % DoD; Deep Cycle AGM 400/600/1500 at 80/50/30 %). Borrowing the years
figure across the line would be an unattributed substitution, and the direction
of the error is not known.

**Cycling is not the constraint at this load.** At v0's `HEATER_MAX_DUTY = 0`,
4,1 Wh/day on 300 Wh is **1,4 % DoD/day**; at 25 % duty, 3,4 %. That is roughly
an order of magnitude shallower than the datasheet's shallowest published point,
so **calendar life, not cycle count, binds** — which is precisely the number the
datasheet does not give.

**Temperature works in our favour here, unusually.** Victron's table only
extends *upward* from 20 °C, and every step up roughly halves the life. St. Peter
at 715 m has a mean annual air temperature around 7–8 °C, so the box lives
permanently on the cold side of the reference point rather than the usual
solar-battery failure mode of a black enclosure baking at 40 °C.

**What will actually end it — two failure modes that appear in no cycle-life
figure:**

1. **Sulfation from chronic undercharge.** The 100 W panel against a 4,1 Wh/day
   load is enormously oversized, so any clear day fully recharges the pack, and
   §3.2's `7E` deficit refills in ~4,7 clear days. The exposure is a multi-week
   snow-covered or shaded run that leaves the pack sitting at low state of
   charge — and an *uncompensated* fixed absorption voltage all winter produces
   the same condition without any weather at all, which is the paragraph above.
2. **Electrolyte freezing when discharged.** Fully charged lead-acid electrolyte
   freezes near −60 °C; near 50 % SoC around −25 °C; near-flat around −8 °C. A
   snow-covered panel and a cold snap are a *correlated* pair, so the state that
   reaches the dangerous end is the one the site actually produces. A frozen
   plate assembly is destroyed, not discharged.

**Working expectation: 5–8 years**, bounded below by the sibling line's 20 °C
figure being unreachable in practice and above by the cold mean temperature, and
conditional on the temperature compensation of §3.4 actually being wired. Treat
it as an estimate with a named basis, not a spec.

## 4. What this document does not cover

- The Dragino RS485-LS has its own solar panel and 3000 mAh Li-ion
  (`tech/RS485-LS-SMT100.md`). It is not on this budget.
- The two SMT100s draw ~5 mA each and are powered from the node's gated `+5V`,
  not from this supply.
- Mains. If a mains outlet turns out to be reachable from the windrow, a sealed
  12 V PSU is cheaper, smaller and more reliable than everything above, and this
  document becomes moot. Check before buying a panel.
- The cable and gland. `POTTING.md` §5 owns those.

## 5. Open

1. **Measure the board's 12 V input current** on the first article, idle and
   during a Modbus exchange. Retires §2.
2. **Measure the heater duty needed to hold 2 K** once `h` is known
   (`HEATED-SPREADER.md` §7). Retires §1 and fixes the panel size.
3. Confirm no mains is reachable, per §4.
