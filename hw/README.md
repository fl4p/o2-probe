# o2-probe

Current Rev B PCB work is in
[`routing/revb-current/o2-probe.kicad_pcb`](routing/revb-current/o2-probe.kicad_pcb).
It uses the current 83-component schematic: AP63203 supplies 3.3 V, R32 filters
the analog rail, REF3425 supplies the reference, and the STM32 ADC replaces
ADS1119. The outline is 20 × 89 mm on two copper layers with a 1.6 mm nominal
board target. J5 and the external heated ring remain
[deferred Rev C work](plans/REVC-HEATED-RING.md).

The PCB is complete and [independently reviewed](docs/2026-09-12-current-pcb-independent-review.md): native 0 errors, 0 unconnected items and 0 schematic mismatches, with 195 vias. The ten assembly courtyard and two intentional guard-endpoint warnings remain visible and individually documented.

[Fabrication package](fab/o2-probe-revb-current-8eef4aa26e24a6cb/o2-probe-revb-current.zip) · [artifact review](docs/2026-09-12-current-artifact-review.md) · [archived implementation plan](docs/archive/2026-09-12-pcb-plans/REVB-AISLER.md). This uses the user-overridden 0.10 mm trace/spacing and 0.20 mm via-drill profile; it is not a standard-Aisler-compliance claim. Procurement and first-article electrical, thermal and mechanical qualification remain open.

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

## Rev A status snapshot, 2026-09-05

**Bare-board first article. Not qualified, not deployed, not potted.**

| | |
|---|---|
| Schematic / PCB | released for a bare-board first article; ERC and DRC clean |
| Firmware v0 | builds, 49 host tests pass — **has never run on hardware** |
| Firmware v1 image | **runs on hardware** (2026-09-05): answers Modbus FC03, publishes T/RH and the diagnostic block |
| Firmware v1 heater loop | implemented and **shipped disabled**, pending the TMP117 alert fault test |
| Cell fit, enclosure fit, potting | unqualified; physical sample gates open. Two new SGX cells arrived 2026-09-05, so the air/nitrogen pair and the bias-plateau sweep are runnable again |
| RS-485 bootloader | **exists and is demonstrated** (2026-09-05): two images staged, CRC-verified and installed over the bus, `UPD_INSTALLS` 0 → 2 |

Two consequences worth stating plainly:

- **Do not pot a probe** — but the reason has narrowed. The application
  bootloader now works: on 2026-09-05 a 26,664-byte image was staged and
  installed over RS-485 twice, and the probe came back answering. What remains
  is recovery, not update: J3 is not exposed through the enclosure, so a potted
  board whose *bootloader* is the thing that breaks has no way back. Today's
  session is the standing argument for caring — the bench bridge spent the
  evening in its ROM bootloader because SWCLK doubles as BOOT0, and SWD was the
  only way out (`~/dev/kb/tooling/probe-swclk-pullup-straps-stm32-boot0.md`).
  `SCHEMATIC-REVIEW.md` M2 has the rest of the detail.
- **Do not bury one running v0.** v0 ships the membrane heater hard-disabled,
  pending a fault test of the TMP117 alert cutoff — which means nothing is
  holding the membrane above the dew point. It is a bench and short-trial
  build. `firmware/FIRMWARE.md` says so in more detail.

## Rev A signal chain

```
SGX-OX-ROHS-Mini ──▶ LMP91000 ──▶ ADS1119 ──▶ STM32G071CBT7 ──▶ THVD1410 ──▶ RS-485
 biased 3-electrode  potentiostat  16-bit ADC   Cortex-M0+,        half duplex
 cell, −600 mV,      7 kΩ TIA,     ratiometric  Modbus RTU slave
 0.1 mA in air       67 % zero     to VREF      9600 8E1
```

Alongside: a TMP117 at the warm tip whose alert pin is wired straight to the
heater MOSFET gate as a hardware cutoff, an SHT45 as the condensation-margin
channel, and two 280 Ω resistors driving a soldered membrane-carrier ring
(140 Ω, 1.03 W at 12 V).

One four-wire farm cable does everything — brown +12 V, white GND, green A,
yellow B — over a 7–15 V input. The bus is shared with two Truebner SMT100
soil probes and a Dragino RS485-LS acting as LoRaWAN master.

The board is 20.0 × 107.0 mm, two layers on a 1.0 mm stack, split by a potting
datum at y = 82 mm with a thermal break beyond it so the gas-side tip can be
heated without heating the whole probe.

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
| `SCHEMATIC-REVIEW.md` | review findings M1–M4 and their closures |
| `FAB-READINESS.md` | what must pass before fabrication and assembly |
| `THERMAL-BARRIER.md` | the ~98 K/W tip isolation, the heater's plant model |
| `PLACEMENT.md`, `ROUTING.md` | layout constraints and their rationale |

Selection rationale, the condensation model and the membrane study live in the
separate compostlab `o2-probe` planning repository.
