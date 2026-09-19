# Power budget on a 12 V 10 Ah battery

Written 2026-09-07, when the supply changed from the farm cable to a battery.

`firmware/src/main.c:1-7` still says:

> *"No sleep modes: the probe is PSU powered through the farm cable and the cell bias must
> run continuously, so there is no power budget to optimise and every low-power mode is a
> way to accidentally interrupt the bias."*

The first clause is now false. The second is true but does **not** imply the first — see
"The stated rationale is two claims, and only one holds" below.

## Device currents

Every figure below is from a datasheet fetched 2026-09-07, not estimated. Reproduce the
arithmetic with `power_budget.py`.

| device | condition | typ | max | source |
|---|---|---|---|---|
| STM32G071CB | Run, 16 MHz, flash, Range 1, 25 °C | 1.8 mA | 2.1 mA | DS12232 Rev 1 Table 24 |
| STM32G071CB | Stop 1, flash off, RTC on, 3 V, 25 °C | 4.0 µA | 16 µA | DS12232 Rev 1 Table 29 |
| STM32G071CB | Stop 1, same, **85 °C** | 33 µA | 140 µA | DS12232 Rev 1 Table 29 |
| THVD1410 | driver disabled, **receiver enabled**, no load | 700 µA | 960 µA | THVD14xx DS |
| ADS1119 | conversion mode, internal ref (AVDD) | 250 µA | — | ADS1119 DS |
| ADS1119 | conversion mode (DVDD) | 65 µA | 100 µA | ADS1119 DS |
| ADS1119 | power-down (AVDD/DVDD) | 0.1 / 0.3 µA | 3 / 5 µA | ADS1119 DS |
| LMP91000 | MODECN = 0x03, 3-lead amperometric | 10 µA | 13.5 µA (15 to 80 °C) | LMP91000 DS |
| LMP91000 | deep sleep, MODECN = 0x00 | 0.6 µA | 0.85 µA | LMP91000 DS |
| TMP117 | 1 Hz duty, 8-averaging | 16 µA | 22 µA | TMP117 DS |
| TMP117 | shutdown | 0.15 µA | 0.5 µA | TMP117 DS |
| SHT45 | avg, 1 meas/s low repeatability | 0.4 µA | — | SHT4x DS |
| SHT45 | idle | 80 nA | — | SHT4x DS |
| TPS7A2033 ×2 | IGND, IOUT = 0 | 6.5 µA ea | 8.5 µA (15 to 125 °C) | TPS7A20 DS |
| AP63205 | quiescent, non-switching, no load | 22 µA @12 V | — | DS41326 Rev 3-2 |
| heater | 140 Ω at 12 V | 85.7 mA / 1.029 W | — | README.md:59 |

The firmware programs the TMP117 for a 500 ms cycle with 8-sample averaging
(`firmware/src/tmp117.c:9`), so the table's 1 Hz figure is doubled to ~32 µA below.

## The budget

12 V × 10 Ah = 120 Wh gross. Buck efficiency taken as 0.85 at our few-mA load (DS41326
claims up to 88 % at 5 mA). The 5→3.3 V LDOs pass current straight through, so 3V3 load
current is also 5 V load current.

| | as built | duty-cycled |
|---|---|---|
| total @3V3 | **2.87 mA** | **28.6 µA** |
| at 12 V | 17.2 mW (1.43 mA) | 0.43 mW (0.036 mA) |
| LiFePO4, 80 % usable | **233 d** | self-discharge limited |
| SLA, 50 % usable | **146 d** | self-discharge limited |

With the heater, from the as-built floor:

| heater duty | total | LiFePO4 80 % | SLA 50 % |
|---|---|---|---|
| 100 % | 1046 mW | 3.8 d | 2.4 d |
| 12 % (`heater_ctl.h:112` ceiling) | 141 mW | 28 d | 18 d |
| 4 % | 58 mW | 69 d | 43 d |
| 0 % (v0 today) | 17 mW | 233 d | 146 d |

## What this says

1. **The heater is the entire question.** At any duty above a few percent it is
   90–98 % of the budget. Every other item on this page is a rounding error beside it.
   Whether the probe survives a season on 10 Ah is decided by the dew-margin policy in
   `heater_ctl.h`, not by firmware efficiency.

2. **v0 as it stands already lasts a season without the heater** — 233 d on LiFePO4,
   146 d on SLA. That was not obvious before the numbers were fetched, and it means no
   firmware change is *required* to deploy on battery today.

3. **The two big always-on loads are the MCU (1.8 mA, 63 %) and the RS-485 receiver
   (700 µA, 24 %).** Together they are 87 % of the as-built draw.

4. **Duty-cycling collapses the load by 100×**, at which point the floor is set by the
   AP63205's own 22 µA quiescent — 264 µW, or 61 % of the remaining 0.43 mW — plus the
   two LDOs' 13 µA, plus the LMP91000's 10 µA. Beyond that the battery's self-discharge
   dominates and further firmware work buys nothing.

## The stated rationale is two claims, and only one holds

`main.c:1-7` refuses sleep because "the cell bias must run continuously". That is true:
DS-0637 Note 1 costs 15 minutes of settling per interruption, encoded as
`O2P_SETTLE_SECONDS 900` at `main.c:44-48`.

But the bias is held by the **LMP91000's potentiostat**, not by the MCU. With 3V3A up,
MODECN = 0x03 holds the cell at bias while drawing 10 µA, whatever the CPU is doing. The
ADS1119 only *reads* the TIA output; powering it down does not unbias the cell.

So "the cell bias must run continuously" does **not** imply "the MCU must run
continuously." Stop 1 with 3V3A alive preserves the bias exactly. The conflation of the
two is the reason the sleep question was never examined.

Caveat worth carrying: Stop-1 leakage is strongly temperature-dependent — 4 µA at 25 °C
but 33 µA typ / 140 µA max at 85 °C. In a pile at 60–75 °C, assume the 85 °C column.
It is still far below the buck's quiescent, so it does not change the conclusion.

## Rev A blocks the cheap win

No rail is MCU-gateable as built:

- buck EN tied to `+12V_SW` — `gen_sch.py:458`
- analog LDO EN tied to its own input: `ASSIGNED[("U3","1")] == ASSIGNED[("U3","3")] == "+5V_ANALOG"` — `gen_sch.py:1165`
- `MCU_NETS` (`gen_sch.py:621`) contains no regulator-enable net

So on Rev A the only firmware-reachable savings are MCU sleep states and putting the
ADS1119 and TMP117 into their power-down modes between samples. The transceiver's 700 µA
can be cut only by disabling its receiver (RE = VCC), which deafens the probe to the bus.

## Recommendations, in order of value

> **UPDATED 2026-09-07: the heater IS needed** (Fab, this session). That settles the
> ranking below and demotes every MCU-side item on this page. With the heater running at
> a plausible duty, the entire firmware programme -- clock-down, Stop 1, the RE/DE
> standby split -- is worth **under 7 %** (28.4 -> 30.3 d at 12 % duty), because 1500 uA
> at 3V3 is 8.8 mW against a 123 mW heater. Treat items 2-4 as over-optimisation until
> item 1 is measured. See "What the heater actually costs" immediately below.

### What the heater actually costs, and what it demands of the battery

What a 10 Ah pack (120 Wh gross, 96 Wh usable) buys:

| heater duty | total | days |
|---|---|---|
| 2 % | 37.7 mW | 106 |
| 4 % | 58.3 mW | 69 |
| 8 % | 99.5 mW | 40 |
| 12 % | 140.6 mW | 28 |
| 20 % | 223 mW | 18 |
| 100 % | 1046 mW | 3.8 |

Inverted -- the most duty a 10 Ah pack sustains for a given run length:

| target | budget | max heater duty |
|---|---|---|
| 42 d (6 weeks) | 95 mW | **7.6 %** |
| 70 d (10 weeks) | 57 mW | **3.9 %** |
| 120 d | 33 mW | **1.6 %** |

And PILE-THERMAL-TEST.md §2 maps that duty to the one unmeasured physical quantity,
theta, the tip-to-medium thermal resistance: 98 K/W (bench, still air) -> 3.0 % duty and
an 8 Ah pack; 50 -> 5.9 % and 10 Ah; 20 -> 14.7 % and 15 Ah; 10 -> 29.4 % and 20 Ah.
**A 10 Ah pack implicitly assumes theta ~ 50 K/W**, i.e. that wet compost couples no
better than half of still air. Still air is the *best* case for the heater -- worst
coupling, least power for a given rise -- so the real value is expected to be lower and
the duty higher. Nothing measured supports 50 yet.

1. **Measure theta in the pile.** PILE-THERMAL-TEST.md, about an hour, executable today
   via `firmware/tools/o2p_thermal.py` over the Modbus cable, method already proven on
   the bench 2026-09-04. It is worth **up to 4x on the pack size**, against <7 % for
   everything else on this page. This is the only lever that matters while the heater
   runs.
2. **Decide the heater duty policy.** It is the whole budget. If dew control needs more
   than ~12 % duty, a 10 Ah battery is the wrong battery, not the firmware's problem.
3. **Clock down to Range 2 / 2 MHz, or Low-power run.** One constant (`mcu.h:25`), one
   I2C clock-source line, and a bench test. 233 d -> 480-509 d **with the heater off** --
   but only 28.4 -> 30.3 d at 12 % duty. Worth doing only if the heater turns out to be
   cheap, or if the build ships with it disabled. See the addendum for the three costs
   and why an earlier draft of this file wrongly dismissed it outright.
4. **If the probe is moving to LoRaWAN anyway** (the Chirpstack migration), the Modbus
   slave model goes with the cable. A scheduled wake → sample → transmit → Stop 1 node
   drops the MCU and the transceiver together, which is 87 % of the as-built draw. This
   is an architecture change, not an optimisation.
5. **Sample cadence.** 1 Hz is meaningless for compost O2, which moves over hours. Every
   sample interval longer than ~5 min converts the ADS1119's 315 µA into a rounding error.
6. **Rev B:** bring the digital LDO's EN and the transceiver's supply to GPIO; keep 3V3A
   ungated for the bias. Consider a buck with single-µA quiescent if the deep-sleep floor
   ever matters.
7. **Not worth doing:** replacing the 12→5→3.3 chain with a single 12→3.3 buck. It wastes
   2.87 mA × 1.7 V = 4.9 mW, 29 % of the as-built draw but only 0.5 % of a heated one.

## Unverified

Everything above is datasheet-typical at 25 °C unless stated. **Nothing here has been
measured on the board.** A series shunt on the 12 V feed, read at heater 0 % and at 12 %,
would settle it in five minutes and is worth doing before committing to a battery size.

---

# Addendum: can the RS-485 receiver be turned off, and can the MCU be clocked down?

## The transceiver: the part says yes, Rev A says no

THVD1410 has a true standby, and it is excellent:

| RE | DE | state | ICC typ | ICC max |
|---|---|---|---|---|
| 0 V | VCC | driver + receiver enabled | 2.4 mA | 3 mA |
| VCC | VCC | driver enabled, receiver disabled | 2 mA | 2.5 mA |
| 0 V | 0 V | **driver disabled, receiver enabled — today's idle** | **700 µA** | 960 µA |
| VCC | 0 V, D open | **driver and receiver disabled** | **0.1 µA** | 1 µA |

7000× down. But that state is **physically unreachable on Rev A**:

```
gen_sch.py:592  {1:"RS485_RX", 2:"RS485_DE", 3:"RS485_DE", 4:"RS485_TX", ...}
```

Pin 2 is `RE` (receiver enable, **active low**, 2 MΩ internal pull-up) and pin 3 is `DE`
(driver enable, **active high**, 2 MΩ internal pull-down) — per the THVD14xx Pin Functions
table. Rev A ties both to the single net `RS485_DE` (PC6), with R7 47k to GND. So:

- `RS485_DE` low → RE=0, DE=0 → receiver on, driver off → **700 µA** (the idle state)
- `RS485_DE` high → RE=1, DE=1 → receiver off, driver on → **2 mA, and driving the bus**

The two opposite-polarity enables share one GPIO, so standby (RE=1, DE=0) cannot be
commanded. Reaching 0.1 µA needs a Rev B net cut and one more GPIO. This tie is the same
one `main.c:869` relies on for the bus-jam watchdog argument, so splitting it must be
done deliberately, not incidentally.

## The protocol objections to unsolicited transmission

1. **The bus is multi-drop.** It carries two SMT100s (`main.c:866-872`). Modbus RTU is
   strictly master-solicited; a slave transmitting on its own timer will collide.
   At 9600 8E1 (1.146 ms/char) a 16-register FC03 response is 42.4 ms and a master
   transaction ~24 ms, so each unsolicited frame has a ~67 ms vulnerable window. Against
   a 60 s master poll that is 0.11 % per transmit — about **0.3 collisions/day** *if the
   phases were random*.

2. **The phases are not random, and that is the real hazard.** A 300 s probe period
   against a 60 s master poll is exactly harmonic: 300 = 5 × 60. The probe therefore
   transmits at the *same phase* relative to the master's poll every single time. Either
   it never collides, or it collides on **every** transmit — a total blackout — decided by
   the power-on phase and drifting with clock temperature. Any fix must jitter the
   interval (e.g. 300 s ± 5 s) to decorrelate the two.

3. **It costs the RS-485 field updater.** `update.c` / `loader_main.c` exist so a potted
   probe can be reflashed over the farm cable (SCHEMATIC-REVIEW.md M2). A 200 ms receive
   window every 300 s passes ~170 bytes per window; a 52 KiB image would take **~25 hours**.
   That path is effectively lost.

A hybrid avoids most of this: stay fully attached while the master is talking, and drop
to standby + unsolicited only after N minutes of bus silence. To regain control the master
polls continuously for longer than one probe period. That preserves the updater and the
Modbus semantics whenever anyone is actually listening.

## But there is a better lever on Rev A, in firmware alone

**USART1 can wake the MCU from Stop mode.** DS12232 Rev 1 Table 9 gives USART1/USART2
"Dual clock domain and wakeup from Stop mode", and §3.20 lists the wakeup events:

> • start bit detection • any received data frame • **a specific programmed data frame**

The third is the Modbus slave address. And the wake is fast enough to be invisible:

| | typ | max |
|---|---|---|
| Stop 1 → Run, flash not powered, HCLK = HSI16 | **9.0 µs** | 11.2 µs |
| one character at 9600 8E1 | 1146 µs | |

128× margin, so no byte and no framing is lost. This keeps Modbus RTU exactly as it is,
needs no hardware change, and saves **1800 µA — 2.6× more than the 700 µA that disabling
the receiver targets.** The receiver has to stay on for wake-on-receive to work at all, so
the two ideas are alternatives, not additions, until Rev B splits DE from RE.

| configuration | @3V3 | at 12 V | LiFePO4 80 % |
|---|---|---|---|
| as built | 2870 µA | 17.1 mW | 233 d |
| **Stop 1 + wake-on-address + ADC/TMP power-down (Rev A, firmware only)**, 25 °C | **728 µA** | 4.5 mW | **880 d** |
| same, 85 °C leakage | 757 µA | 4.7 mW | 848 d |
| + transceiver standby (needs Rev B) | 58 µA | 0.6 mW | self-discharge limited |

## Clocking down: worth a doubling, and available today

DS12232 Rev 1 Table 25, fetching from flash, typ at 25 °C:

| mode | current |
|---|---|
| Range 1, 16 MHz — **what runs today** (`mcu.c:36-46`) | 1.8 mA |
| **Range 2, 16 MHz** | **1.4 mA** |
| Range 2, 8 MHz | 0.8 mA |
| Range 2, 2 MHz | 0.3 mA |
| Low-power run, 2 MHz | 220 µA |
| Low-power run, 1 MHz | 105 µA |
| Low-power run, 32 kHz | 17 µA |
| **Stop 1, 25 °C / 85 °C** | **4 µA / 33 µA** |

Two things follow:

- **Range 2 at 16 MHz is a free 22 %** - same clock, just voltage scaling. Caveat: the
  flash wait states change with the range, and `mcu.c:44-46` deliberately asserts
  `LATENCY = 0` with a comment scoped to *"range 1"*. Switching to Range 2 requires
  re-reading the wait-state table in RM0444 (not in the datasheet) and setting latency
  **before** the switch.
- **Clocking right down is worth about a doubling, and is available today.**

| run mode | MCU | total @3V3 | at 12 V | LiFePO4 80 % |
|---|---|---|---|---|
| Range 1, 16 MHz (as built) | 1800 µA | 2870 µA | 17.15 mW | 233 d |
| Range 2, 16 MHz | 1400 µA | 2470 µA | 14.80 mW | 270 d |
| Range 2, 8 MHz | 800 µA | 1870 µA | 11.27 mW | 355 d |
| Range 2, 4 MHz | 500 µA | 1570 µA | 9.50 mW | 421 d |
| **Range 2, 2 MHz** | 300 µA | 1370 µA | 8.33 mW | **480 d** |
| **Low-power run, 2 MHz** | 220 µA | 1290 µA | 7.85 mW | **509 d** |
| Low-power run, 1 MHz | 105 µA | 1175 µA | 7.18 mW | 557 d |
| Stop 1 @25 °C + ADC/TMP power-down | 4 µA | 728 µA | 4.54 mW | 880 d |
| Stop 1 @85 °C + ADC/TMP power-down | 33 µA | 757 µA | 4.71 mW | 848 d |

### Correction to an earlier draft of this document

An earlier version of this section said clocking down "attacks the 0.1 %" because the MCU
is "idle >99.9 % of the time", and advised against going below 16 MHz. **That was wrong,
and wrong in the same way `main.c:1-7` is wrong.**

The probe has no sleep states: `main.c:806` is a spin loop that busy-polls Modbus and the
sampler. The MCU is therefore in Run mode **100 % of the time**, not idle 99.9 % of it.
"Not doing useful work" and "not drawing run current" are different things, and conflating
them is exactly the error this document was written to correct elsewhere. Under the
firmware as it stands, a clock reduction is fully effective on every microamp.

### What clocking down actually costs

The firmware is already parameterised for it: `O2P_SYSCLK_HZ` (`mcu.h:25`) is a single
constant that already feeds the USART BRR (`modbus_rtu.c:98`, `loader_uart.c:62`,
`bridge_uart.c:34`), SysTick (`mcu.c:56`) and the heater PWM prescaler (`heater.c:77`).

Three concrete consequences, none architectural:

1. **I2C breaks and must be re-clocked.** `i2c1.c:6-9` sets
   `O2P_I2C_TIMINGR 0x30420F13`, explicitly *"from the RM0444 I2C_TIMINGR examples for a
   16 MHz peripheral clock"*, giving 100 kHz standard mode. At 2 MHz PCLK that same
   constant yields ~12.5 kHz and violates the setup/hold timings. The clean fix is **not**
   to re-derive it: I2C1 has an independent clock source (DS12232 Table 8 - I2C1 yes,
   I2C2 no), so point I2C1SEL at HSI16. HSI16 is already running because SYSCLK is derived
   from it through HSIDIV, so this costs nothing and keeps the validated TIMINGR constant.
2. **Heater PWM duty resolution coarsens 8x.** `heater.c:77` derives ARR from
   `O2P_SYSCLK_HZ`; at 2 MHz and 1 kHz PWM, ARR is 2000, so granularity is 0.05 %. The
   `duty_x100` 0.01 % unit becomes partly notional. Not a blocker at the duties in play.
3. **Baud accuracy is unaffected.** BRR at 2 MHz is 208, giving 9615 Bd (+0.16 %). That is
   swamped by HSI16's own drift of ±1 % over 0-85 °C (DS12232 Table 41), which is identical
   at any HSIDIV setting. No margin is lost by dividing.

The sample cycle does not slow materially either: it is I/O-bound on the ADS1119, eight
conversions at 50 ms for the oxygen channel (`main.c:8-15`), during which the CPU waits.

### So why still prefer sleep, eventually

Because at 2 MHz you are still spending 300 µA continuously to wait on an ADC. Stop 1
turns that waiting into 4-33 µA. The gap between the best clock-down (LPRUN 1 MHz, 557 d)
and Stop 1 (880 d) is ~320 days.

But the two do **not** stack. If Stop 1 lands, run-mode current stops mattering because
run time collapses toward zero - so this is choose-one-first, not a sum. And Stop 1 is the
more invasive change: `main.c:884-889` feeds the IWDG only when a cycle completed *and*
the DE line is not stuck, and a sleeping main loop changes what "completing cycles" means.
That watchdog invariant is a safety property for the shared bus and must be redesigned
deliberately, not incidentally.

**Recommendation: clock down now, sleep later.** Range 2 at 2 MHz (or Low-power run) is a
constant, an I2C clock-source line, and a bench test - available today, worth a doubling.
Stop 1 with USART1 wake-on-address is the 3.8x, and needs the watchdog rethink.

One consequence worth seeing: at 2 MHz the THVD1410's 700 µA becomes **51 % of the whole
budget**. Clocking down is what makes the Rev B standby split worth doing.

---

# Implemented, 2026-09-07: the RE/DE split (schematic + firmware only)

The blocker described above — "Reaching 0.1 µA needs a Rev B net cut and one
more GPIO" — is now cut in `gen_sch.py`. **No PCB work has been done**, so on
copper `U5.2` is still shorted to `U5.3`; this is a change to the source of
truth and to firmware, not to a fabricable board.

> **Still true on 2026-09-09.** The bench article is unreworked. Since that
> date the firmware *knows* it: `gen_hw_caps.py` derives
> `O2P_HW_RS485_RE_ON_ITS_OWN_PIN` from each revision's own netlist — 0 for the
> fabricated Rev A, 1 for the Rev B schematic — and
> `o2p_modbus_rx_standby(true)` **refuses** where it is 0 rather than writing a
> pin that goes nowhere and reporting a 630 µA saving the copper cannot make.
> The procedure and its acceptance test are in
> [`docs/REWORK-RS485-RE-SPLIT.md`](docs/REWORK-RS485-RE-SPLIT.md), including
> the trap this section does not mention: **R7 sits on the `U5.2` side of the
> short**, so a bare cut leaves `/RE` with the pull-down and `DE` with none —
> and `DE` is the one whose passive default keeps a reset probe off the shared
> cable.

- `U5` pin 2 (`/RE`) moves from `RS485_DE` to a new net **`RS485_RE`**.
- `MCU_NETS` gains **pin 31 = PC7**. Verified against DS12232 Rev 1 Table 12
  ("Pin assignment and description"), LQFP48/UFQFPN48 column: PC6 = 30,
  PC7 = 31, and PC7's *Additional functions* cell is empty, so no ADC channel
  is lost and `mcu_adc.c` cannot collide with it.
- **`R45`, 47 k `RS485_RE` → GND.** `/RE` is active low and floats *high* on
  the part's 2 MΩ internal pull-up; MCU GPIOs are high-impedance out of reset.
  Without R45 a probe that reset into the RS-485 bootloader would be **deaf**,
  and a potted one unrecoverable. Sized against the **guaranteed** spec rather
  than the 2 MΩ typical: SLLSEY3E gives `IIN = ±6.2 µA` max for D/DE/RE, and
  `V_IL` max 0.8 V, so worst case `6.2 µA × 47k = 291 mV` — a **2.75× margin**.
- **R7 is untouched.** DE keeps its own 47 k pull-down, so `main.c:857-880`'s
  argument — reset plus R7 releases the bus with no code running — is unchanged.
  R45 is the same idea applied to the other enable.

## Correction to the table above: the win is 630 µA, not ~700 µA

The row `RE=VCC, DE=0 V, D open → 0.1 µA` is the *part's* number. **This board
cannot reach it**, because commanding standby means driving `/RE` high against
R45: `3.3 V / 47 k = 70.2 µA`. So:

| | receiver on | standby, as implemented | standby, part's floor |
|---|---|---|---|
| transceiver + its pull-down | 700 µA | **70.3 µA** | 0.1 µA |

A 10× cut, not 7000×. That is enough to matter against today's 2.87 mA total,
but note where it lands in the duty-cycled column: at a **28.6 µA** total,
R45 alone would be the largest single load on the board.

The largest pull-down that still *guarantees* a low is `0.8 V / 6.2 µA = 129 kΩ`,
so no resistor can better ~26 µA. The weaker alternatives are not a gentle trade —
they are out of spec:

| R45 | V(/RE) worst case | vs 0.8 V V_IL | standby current |
|---|---|---|---|
| **47 k (fitted)** | 291 mV | **2.75×** | 70 µA |
| 100 k | 620 mV | 1.29× | 33 µA |
| 129 k | 800 mV | 1.00× — at the limit | 26 µA |
| 220 k | 1.36 V | **fails** | 15 µA |
| 470 k | 2.91 V | **fails** | 7 µA |

A resistor structurally cannot reach the 0.1 µA the split was made for. Only
omitting R45 and having the loader drive `/RE` low in early init can, and that
trades a sub-millisecond deaf window between reset and the first GPIO write.

Note the asymmetry with R7: **R7 on DE is a bus-safety part** — an undriven DE
could jam the shared cable and silence both SMT100s, which is why `main.c:857-880`
leans on it. R45 is not: an undriven `/RE` makes only *this* probe deaf, and only
while it is in reset, when it cannot answer anyway.

**Fab chose 47 k on 2026-09-07** — robust, passive, no init-order dependency, and
630 µA of the available 700 µA.

## Firmware

`o2p_modbus_rx_standby(bool)` in `modbus_rtu.c` enters and leaves the state.
**Nothing calls it.** Default runtime behaviour is byte-for-byte what Rev A did:
`/RE` is driven high exactly where the old shared net went high (transmit) and
low again on every exit path, including the timeout backstops. `loader_uart.c`
and `bridge_uart.c` do the same, for echo suppression only — with `/RE` left
low during their own transmissions the loader would parse its own reply as a
request (it carries this probe's address and a valid CRC), which is why "just
don't drive the pin in the loader" is *not* the safe simplification it looks
like.

Wiring standby into the sampler remains blocked on the protocol question in
"The protocol objections to unsolicited transmission" above, and on this page's
own conclusion that **USART1 wake-from-Stop saves 1800 µA and needs the
receiver on** — the two levers are still alternatives, and Stop-1 remains the
bigger one.

---

# Physical layer: is RS-485 the right choice on a battery?

Asked 2026-09-07, prompted by Truebner shipping a low-voltage UART variant of the SMT100.

## What Truebner actually ships

From truebner.de/en/smt100.php, fetched 2026-09-07: RS-485 (TBUS/ASCII or Modbus),
SDI-12, analog 0-10 V (0-1/0-3/0-5 V on request), 4-20 mA, and **"Low voltage UART
(especially for IoT radio modules)"**. They did not pick a winner; they shipped the trade.

Application Note AN007 (02/2022) describes the SMT100 LV: 3.1-15 V supply, 3 V UART
levels, UART lines protected by 1 kOhm series resistors, internal 3 V rail behind an
ultra-low-dropout regulator, aimed explicitly at lithium primary cells. And:

> "The UART interface is typically used for **point-to-point** communication with a
> **single sensor** (master - slave configuration)."

That parenthetical on the product page - *especially for IoT radio modules* - is the whole
point. The LV variant exists for a sensor wired to one radio node, not for a bus.

## The ordering that matters

**The physical layer is the second-order question. Who initiates is first-order.**

A slave must listen, and listening is what costs. If this probe stays a polled Modbus
slave, swapping RS-485 for UART saves the transceiver's 700 uA but leaves the MCU's
**1800 uA** awake to catch the poll - 24 % of the problem, paid for in noise immunity.
Fix initiation instead (USART1 wake-on-address, or scheduled transmit) and RS-485 drops to
the ~70 uA standby that R45 allows, at which point the physical layer stops mattering.

So the order of work is: **initiation, then clock, then physical layer.** The first two are
worth 2-4x between them. The third is worth 630 uA already recovered by the RE/DE split.

## What RS-485 buys in this deployment specifically

The probe is potted with the cell *and* the STM32 in the pile, at the end of a long cable.
That is the case RS-485 exists for:

- **+/-15 V common-mode range.** THVD1410 receiver thresholds are specified over a +/-15 V
  common-mode range (SLLSEY3E electrical table), and the driver survives -7 V to +12 V.
  The probe shares a ground with a heater switching 86 mA down a long wet cable; ground
  offset between probe and logger is not hypothetical.
- **Differential signalling**, so common-mode pickup cancels.
- **A protected front end**: transceiver plus the SM712 TVS. The LV variant's protection is
  1 kOhm series resistors - reasonable for a sealed sensor the vendor replaces, thin for a
  potted one-off that cannot be opened.
- **Multi-drop.** The cable already carries two SMT100s. UART is point-to-point; each
  sensor would need its own pair.
- **The field updater.** loader_main.c reflashes a potted probe over that same pair.

## When LV/UART would genuinely be right

If the electronics moved *out* of the pile into a dry enclosure beside the radio, with only
a short lead to the cell. Then RS-485 is overhead. That is a mechanical redesign, and the
tip is in the pile by construction, so it is not today's board.

The more interesting alternative is **SDI-12**, not plain UART: the agriculture standard for
battery soil probes, addressable and multi-drop on one wire, built around sensors that
sleep between measurements, and available on the SMT100. But it is 1200 baud and would mean
replacing the Modbus stack *including the RS-485 updater*. Large rewrite, working bus - not
recommended.

## Conclusion

**Keep RS-485.** The RE/DE split removes the power objection. Spend the effort on
initiation and the clock-down.

## The system-level caveat, unmeasured

If the probe is polled by an ESP32 node (the Chirpstack migration), that node has to be
awake to poll, and its budget is not in this document. Do not assume it is small and do not
assume it is large: a bare ESP32 module in deep sleep is tens of microamps, while a
development board carrying an LDO and a USB-UART bridge is milliamps, and for infrequent
reporting the radio's per-uplink energy usually dominates both. **Measure the actual node
board before optimising this probe further** - the answer may change whether the probe
should be polled at all, which is the first-order question above.

## Update 2026-09-19 — the heater now idles in dry air (FW 0x0027)

Written when the dry-air idle gate landed; the numbers above are unchanged, this is
about which row of the heater table a probe *sits in* when it is not in a pile.

Point 1 above ("the heater is the entire question") was still true as written, but
incomplete in one direction: since FW 0x0016 the **gradient floor** demands
`T_tip = T_cell + 2.00 K` on every dew-law cycle and has no humidity input by design, so
a probe on the bench or in transit held that gradient continuously. On this plant that
is a large fraction of full duty, i.e. the 3.8 d / 2.4 d row, for heat nobody needed.

FW 0x0027 withholds the floor's demand while **RH < 90 % and the cell-side dew margin is
at least 6.00 K** — roughly "22 °C room air at 65 %RH or drier". The dew law asks for
nothing in that regime already, so the probe lands on the 0 % row: **233 d on LiFePO4,
146 d on SLA**, the as-built floor of 2.87 mA.

Three things this does *not* change, stated so nobody reads a season into it:

- **In the pile nothing changes.** Pore gas is saturated, the margin is small or
  negative, and both laws run exactly as before. The buried-probe budget is still the
  dew-margin policy's, not this gate's.
- **It is not free of risk.** The floor exists because a wetted-then-drying SHT45 reads
  low RH; the margin condition blocks the common form of that lie (warming the gas
  raises Td in step) but not all of it. The gate is therefore bounded, not latched:
  120 s of floor every 1800 s regardless of humidity — about 6 % of the floor's demand,
  which is why the saving is "the 0 % row plus a premium", not literally zero.
- **Duty-cycling the MCU is still not implemented.** The 28.6 µA column remains
  hypothetical (`main.c:3`, "No sleep modes").
