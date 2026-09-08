# o2-probe

A buried oxygen probe for compost windrows: an electrochemical cell, its
potentiostat, a heated membrane, and an STM32 that speaks Modbus RTU, on one
elongated PCB that is potted at one end and breathing at the other.

It exists because measuring O₂ in a pile is not a sensor problem, it is a
condensation problem. Pore gas is saturated, a buried probe conducts heat
outward, and every surface therefore sits below the dew point — while the cell
is rated 15–90 %RH *non-condensing*. So the board carries a heated membrane
ring, and the firmware's job is as much keeping the membrane dry as reading
the cell.

Hardware and firmware live together here because they are one contract: the
firmware's scale factors are **generated** from the schematic (see
[The hardware contract](#the-hardware-contract)).

## Status

**Bare-board first article. Not qualified, not deployed, not potted.**

| | |
|---|---|
| Schematic / PCB | released for a bare-board first article; ERC and DRC clean |
| Firmware v0 | builds, 74 host tests pass — **has never run on hardware** |
| Firmware v1 heater loop | implemented and **shipped disabled**, pending the TMP117 alert fault test |
| Cell fit, enclosure fit, potting | unqualified; physical sample gates open |
| RS-485 bootloader | **does not exist** |

Two consequences worth stating plainly:

- **Do not pot a probe.** J3 is not exposed through the enclosure and there is
  no application bootloader yet, so a potted board cannot be updated or
  recovered. `SCHEMATIC-REVIEW.md` M2 has the detail.
- **Do not bury one running v0.** v0 ships the membrane heater hard-disabled,
  pending a fault test of the TMP117 alert cutoff — which means nothing is
  holding the membrane above the dew point. It is a bench and short-trial
  build. `firmware/FIRMWARE.md` says so in more detail.

## The signal chain

```
SGX-OX-ROHS-Mini ──▶ LMP91000 ──▶ ADS1119 ──▶ STM32G071CBT7 ──▶ THVD1410 ──▶ RS-485
 biased 3-electrode  potentiostat  16-bit ADC   Cortex-M0+,        half duplex
 cell, −600 mV,      7 kΩ TIA,     ratiometric  Modbus RTU slave
 0.10 mA in air      67 % zero     to VREF      9600 8E1
```

Alongside: a TMP117 at the warm tip whose alert pin is wired straight to the
heater MOSFET gate as a hardware cutoff, an SHT45 as the condensation-margin
channel, and two 280 Ω resistors driving a soldered membrane-carrier ring
(140 Ω, 1.03 W at 12 V).

One four-wire farm cable does everything — brown +12 V, white GND, green A,
yellow B — over a 7–15 V input. The bus is shared with two Truebner SMT100
soil probes and a Dragino RS485-LS acting as LoRaWAN master.

The board is 20.0 × 107.0 mm, four layers on a 1.0 mm stack, split by a potting
datum at y = 82 mm with a thermal break beyond it so the gas-side tip can be
heated without heating the whole probe.

## How well it can read

`O2-CORRECTION-MODEL-BUDGET.md` propagates the part datasheets through the law
the firmware actually implements. Three results decide how the probe is
calibrated and what may be claimed for it:

- **The digitiser is nowhere near the limit.** One ADS1119 LSB is 10.9 nA =
  0.002 %O₂, and an averaged sample is 3.2 nA. The cell's own datasheet zero
  signal — `< 0.4 %vol O₂`, DS-0637 — is 1706 nA, 150× that and 12× the
  LMP91000's ±0.04 % internal-zero error. Multiplicative chain errors (5 % TIA
  gain accuracy, ±0.01 % ADC gain) cancel exactly, because the reading depends
  only on `S/K` and `K` comes from an air point through the same chain.
- **The tempco is the whole game.** With an air point alone — what ships today
  — the error at 55 °C is ~1.3 %O₂ in air and 0.3–0.5 %O₂ in the 2–5 % range
  where the compost decision lives — those are the **55 °C** figures, and they
  keep rising (1.47 %O₂ at 60 °C). Any temperature sweep collapses that below
  0.03 %O₂. **DS-0637 Issue 2 does publish an output-versus-temperature curve**
  (≈ +0.2 %/K, eyeballed, not yet digitised); it is the cell alone, from another
  population, without our electronics, so a per-probe fit is still the plan.
  The curve also looks **visibly non-linear above 40 °C**, which would mean one
  linear coefficient cannot close the model — recorded as unverified until
  `dsdig` digitises it, because a chart read by eye is not a sourced number.
- **The terms calibration cannot touch are larger than calibration error.**
  Water-vapour dilution of saturated pore gas is −0.18 %O₂ per K at 55 °C;
  barometric weather is ±0.45 %O₂ at air and is uncorrectable because the
  BMP390 is DNP; CO₂ enhancement (0.3 % of signal per 1 %CO₂, 4-series figure,
  unverified on the Mini) is +0.23 %O₂ at 5 %O₂ in pile gas.

Counter-intuitively, **an unweighted fit gets worse as dilution points are
added** — up to 9× worse on `K` — because each blend injects its own 1–2 %
reference error into a fit whose best reference, air at ±0.005 %O₂ once RH and
pressure are logged, was already free. Weight each residual by its own
reference uncertainty and the same points neither help nor hurt. Either way the
dilution series earns its place on the zero and the log law, not on
sensitivity.

## Layout

```
*.kicad_sch  *.kicad_pcb   the KiCad project — GENERATED, see below
gen_sch.py   gen_pcb.py    the generators that are the actual source of truth
audit_*.py                 machine-enforced design rules, with --calibrate
DESIGN.md                  the design record: architecture, address map, gates
firmware/                  STM32G071 firmware, PlatformIO + STM32Cube
lib/                       project-local symbols and footprints
```

`gen_sch.py` is the source of truth for the schematic. **Do not hand-edit
`o2-probe.kicad_sch`** — change the generator and regenerate.

## Building the firmware

```sh
cd firmware
pio test -e native      # portable logic on the host
pio run  -e o2probe     # cross build
pio run  -e o2probe -t upload
```

Flashing is pre-pot only, over the J3 Tag-Connect footprint (TC2030-IDC-NL-6),
using any ST-LINK — including the one on a Nucleo board in external-target
mode. J3 pin 1 is VTREF, not a supply: power the board from its 12 V feed.

## Regenerating the hardware

```sh
python3 gen_sch.py
kicad-cli sch erc --exit-code-violations -o erc.rpt o2-probe.kicad_sch
python3 audit_schematic.py
```

`DESIGN.md` carries the full sequence including the PCB side.

## The hardware contract

The firmware converts ADC codes with divider ratios that live in the
schematic. Those have already moved once — the input-voltage divider went from
130k/20k to 82k/10k — and nothing but a comment connected the two.

So `firmware/tools/gen_hw_contract.py` imports `gen_sch.py`, extracts every
value the firmware converts with, and writes `firmware/src/hw_contract.h`. A
PlatformIO pre-build action regenerates and diffs it, and `board_pins.h`
static-asserts each GPIO binding against the generated pin map. A schematic
change that rescales a divider or moves a pin now **breaks the build** instead
of silently rescaling every reported value.

```sh
cd firmware
python3 tools/gen_hw_contract.py          # regenerate after a schematic change
python3 tools/gen_hw_contract.py --check  # what the build runs
python3 tools/check_regmap_docs.py        # prose register map vs regmap.h
```


## Further reading

| | |
|---|---|
| `DESIGN.md` | architecture, I²C address map, register map, release gates |
| `firmware/FIRMWARE.md` | register map, fault semantics, bring-up procedure |
| `O2-CORRECTION-MODEL-BUDGET.md` | what a dilution + tempco calibration can and cannot buy |
| `SCHEMATIC-REVIEW.md` | review findings M1–M4 and their closures |
| `FAB-READINESS.md` | what must pass before fabrication and assembly |
| `THERMAL-BARRIER.md` | the ~98 K/W tip isolation, the heater's plant model |
| `PLACEMENT.md`, `ROUTING.md` | layout constraints and their rationale |

Selection rationale, the condensation model and the membrane study live in the
separate compostlab `o2-probe` planning repository.
