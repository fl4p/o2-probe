# O2 probe design record

## Status and source of truth

`gen_sch.py` is the source of truth for the schematic. Do not hand-edit the
generated `o2-probe.kicad_sch`; change the generator and regenerate it.

The root PCB records the fabricated Rev A article. The current schematic is
Rev B: RV1 is absent; U15 supplies the fixed reference. The latest routed
Rev B candidate is [routing/revb-interfaces](routing/revb-interfaces/README.md),
with the independent PC7 receiver-enable route, R45, 1k CE resistor and corrected
D7 pinout. It is not a fabrication release. See the
[completion and qualification record](docs/2026-09-09-revb-protection.md) and
[archived plan index](docs/archive/2026-09-09-pcb-plans/README.md).

Regenerate and verify with:

```sh
python3 gen_sch.py
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc \
  --exit-code-violations -o erc.rpt o2-probe.kicad_sch
python3 audit_schematic.py
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch export pdf \
  -o o2-probe-schematic.pdf o2-probe.kicad_sch
```

Current generated result: 101 components, 308 assigned package pins, 85 nets,
KiCad ERC 0 violations, and `schematic-audit.rpt` PASS.

## Electrical architecture

- J1 is the fixed four-wire farm cable. Its individual solder lands are J101
  through J104 and are labelled as J1.1 brown +12 V, J1.2 white GND, J1.3 green
  RS-485 A, and J1.4 yellow RS-485 B.
- The 7–15 V input uses a resettable fuse, input TVS, reverse-polarity P-FET,
  AP63205 fixed 5 V buck, and separate TPS7A2033 digital and analog 3.3 V rails.
  The analog LDO input is isolated from `+5V` by fitted R32=10 ohm and bypassed
  locally by C7=10 uF 25 V plus C27=100 nF on `+5V_ANALOG`. R32 uses an 0603
  option footprint that may take 0 ohm or a characterized bead after testing
  (0603 beads are as available as 0805 — Murata BLM18, TDK MPZ1608 — so the
  2026-09-05 package change did not cost the option, and took the last 0805
  resistor land off the board; C7 took the last 0805 capacitor land with it by
  becoming the same 1206 part as C1);
  a bead is not the default because its low-frequency inductance can resonate
  near the ADS1119 256 kHz modulator frequency.
- The O2 signal chain is SGX three-electrode cell -> LMP91000 -> ADS1119. U15,
  an **AZ431B wired as a two-terminal 2.5 V shunt** (REF strapped to the
  cathode), establishes `VREF_SHUNT`, and R31 feeds `VREF_TRIM` from it; that
  net keeps its name only because firmware keys off it, and **there is no
  trimmer**. `POTTING.md` §1.2 (in `../../../ha/farming/compostlab/o2-probe/`)
  removed it: the cell must be swappable with the board potted, so no adjustable
  part may sit on the potted side.
  - R41 biases the shunt from `+5V_ANALOG`, **not** 3V3A. The part needs
    I_KA ≥ 1.0 mA, and 3V3A leaves only 3.234 − 2.510 = 0.724 V of worst-case
    headroom — about 6 % over that floor — where +5V_ANALOG leaves 2.5 V and
    gives 1.67 mA.
  - C9 is deliberately only **1 nF on the cathode**, with the bulk capacitance
    (C10) held off it by R31. AZ431-A Figure 15 puts the lower stable region
    below roughly 10 nF at this cathode current. **That is a chart reading, not
    a specified number — confirm on the bench before release.** The same R31
    would have been *wrong* for a series reference like the REF33xx, which
    requires 0.1–10 µF **on** its output pin.
  - The AZ431's SOT-23 map (1 REF, 2 CATHODE, 3 ANODE) matches **no** KiCad
    TL431 variant, so the symbol borrows the TL431DBZ graphic with pin numbers
    remapped. Strapped as it is, the difference is electrically inert; it bites
    the moment REF is divided to make the part adjustable.
  - **The error the trimmer removed was overstated.** SNAS506I's ±2 % is the
    bias programming *resolution* — the ladder's step spacing — not an accuracy.
    Guaranteed WE-to-RE accuracy is `VOS_RW`: ±1750 µV max at the ±24 % setting
    over −40…80 °C, i.e. *inside* the SGX's ±10 mV window. The trimmer deletion
    stands on the potting requirement regardless, but the ±50 mV figure that
    justified the bias-telemetry channel does not survive the datasheet.
    `PLAN.md`'s AFE bias verdict is where it originates.
- Both OPA2333 halves are unity-gain electrometer followers on the cell nodes:
  U4A buffers WE, U4B buffers RE. U4B's output drives the guard through R40 and
  the bias telemetry through R38, so the guard tracks the **real** electrode
  instead of the old open-loop 0.91×VREF replica, which is both strictly better
  guarding and the ADC channel that makes the bias measurable. `GUARD_REPLICA`
  keeps its name because `repair_guard_fill.py`, `route_thermal_barrier.py` and
  `audit_pcb.py` key off it; it is no longer a replica of anything.
  No femtoampere part is needed: RE already carries the LMP91000's own ±900 pA
  max IRE (SNAS518, −40..80 °C), so the OPA333's ±200 pA max at 25 °C raises the
  worst case by about 20 %, where an ADA4530-1 at 20 fA would leave it at 900 pA.
- ADS1119 AIN2/AIN3 are wired to `WE_BUF`/`RE_BUF` for a **differential** cell-bias
  reading. **This is specified but NOT IMPLEMENTED — nothing reads AIN2 or AIN3
  today.** Until 2026-09-05 firmware sampled AIN3 single-ended and reported it as
  the input rail; that is fixed, and what remains is that the bias telemetry the
  next sentence describes has no code behind it.
  SBAS925 allows the ~2.27 V common mode at gain 1 and 4 alike, giving ±625 mV
  full scale at gain 4. The two rail monitors this displaced, `VA_MON` and
  `VIN_MON`, are now both on the MCU's own ADC (PA7/IN7 and PA6/IN6).
- The processor is STM32G071CBT7. USART1 on PA9/PA10 drives the THVD1410 farm
  RS-485 port. USART2 on PA2/PA3 lands on J105/J106 and is the bench-bridge
  tap, not a connector — see the J2 entry below.
- PC6 drives `RS485_DE` and **PC7 drives `RS485_RE`**, placing both
  direction-control GPIOs beside the USART1 TX/RX pins, and PA7/ADC_IN7
  measures `VA_MON`. These pin choices are generator-owned because they make
  the compact right-side MCU placement routable without changing the electrical
  functions.
- The THVD1410's two enables are on **separate** nets and separate GPIOs, and
  each has its own 47 k pull-down: R7 on `RS485_DE` (driver off by default —
  the bus-jam release path `main.c` relies on) and **R45 on `RS485_RE`**
  (receiver *on* by default, since `/RE` is active low and floats high on a
  2 MΩ internal pull-up, and a probe in the bootloader must still hear the
  bus). Rev A shorted the two together, which made the transceiver's 0.1 µA
  standby state uncommandable; see `POWER-BUDGET.md` for what the split buys
  and what R45 costs. **The PCB has not been reworked for this yet.**
- One TMP117 measures the warm tip near the membrane carrier. Its open-drain
  ALERT is wired directly to the MOSFET gate so a correctly configured active
  alarm can pull the heater off while MCU PWM drives through R28; R29 provides
  the passive default-off state. This is not credited as an autonomous
  overtemperature cutoff until firmware configures and fault-tests the TMP117.
  SHT45 is the chamber RH/dew-point channel. BMP390 remains an explicitly DNP
  pressure option at address 0x76.
- **The heat source stays on this board.** RH1/RH2 (2 × 280 Ω 2512, ~1 W at
  12 V) bridge `+12V_SW` to `HEATER_LOW` above Q2, as they always have. An
  earlier pass in this revision deleted them and moved the heat to the ring PCB;
  Fab reversed that on 2026-09-04 — *"the heater stays where it is"*. The
  geometry that motivated the delete is real and unchanged: `HEATED-SPREADER.md`
  §0 measured 18.6 mm from the old J5 lands to the cartridge heater shelf, with
  the cell filling the bore for 8.3 mm of it, and `RING-PCB.md` §1 puts the
  fork's conduction at 4.3 mW/K — so heat made here does **not** efficiently
  reach the membrane. But that is an argument about where heat must *arrive*,
  not a licence to remove the only heat source the board has. The delete would
  have cost a validated subsystem: the bench run recorded in `FAB-READINESS.md`
  ("Heater bench results, 2026-09-04") exercised the PWM, the TMP117 interlock
  with the core halted, the rail monitor and detect-and-recover **against
  RH1/RH2 as the load**, and none of it could be re-run on a board whose heater
  lives on an unbuilt ring behind an unmeasured neck bore. A ring PCB, when it
  exists, **parallels** these elements through J5; it does not replace them.
- **J5 is now a fork tip rather than two edge castellations.** J5's two edge
  castellations are deleted, for the reach reason above. J5 is now two solder lands at the
  tips of a tuning-fork board end, taking switched `HEATER_LOW` and fused
  `+12V_HTR` 13 mm forward to a perpendicular ring PCB that carries the heater
  itself. One finger per net, both layers of a finger paralleled. Fab dropped
  the ring's temperature sensor from this revision, so only 2 of the 4 available
  conductors are used and the second layer of each finger stays free for a v2
  ring — which needs no main-board change. The footprint is explicitly DRAFT:
  `RING-PCB.md` §5.1 forbids freezing the 0.6 mm finger width before the printed
  ASA neck bore is measured on a real part.
- **F3 is a FITTED 0 Ω link reserving a position against a fault path the fork
  created.** It is deliberately *not* a DNP placeholder: it sits in series in the
  only supply path to the ring, so leaving it unpopulated would open the heater
  feed to the ring entirely. RH1/RH2 sit in the main-board branch and **not** in
  the fork feed, so nothing limits the fork itself: a short between fork fingers
  — which run at 0.20 mm clearance to a metal cell can — puts
  +12V_SW across Q2 unlimited, and possibly 12 V onto the cell. Do not fit it as
  drawn: a PPTC derates badly at pile temperature (F1's own note records 0.36 A
  at 85 °C for a 0.75 A part), so one holding the heater's 83 mA would nuisance-
  trip. Size it once the ring's resistance is fixed, or protect at the ring.
- **J2 is DELETED**, with F2, R12-R16 and D4/D5/D6 — fourteen never-fitted
  parts, 2026-09-05, `docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md` §3. It was the sealed-side expansion
  connector for a future external CO2 head (switched 12 V, fused 3.3 V, I2C,
  interrupt, spare UART) and was never the programming connector. It was also
  224.8 mm² of courtyard — 14 % of every courtyard on the board — plus two
  Ø2.41 mm NPTH holes, at local y 60.5…73.5, immediately before the AFE band
  the two-layer work is fighting. On two layers an NPTH is a hole through both.
  What was lost: the 2x04 pad field for a daughterboard and its separately
  fused `EXP_3V3`. J2 was DNP on every board ever built, so no built board had
  either.
- **R15/R16 were not deletable, and J105/J106 replace them.** `board_pins.h`
  and `bridge_main.c` both took the bench bridge's host lead off the MCU-side
  pads of R15/R16, so those two DNP parts were load-bearing lands. USART2 now
  ends on two solder-wire lands, J105 `BRIDGE TX` (PA2) and J106 `BRIDGE RX`
  (PA3) — a better tap at two footprints instead of five, and no BOM line.
  3.3 V logic only: PA2/PA3 are not 5 V tolerant.
- J3 is the sole pre-pot programming/recovery interface: VTREF, SWDIO, NRST,
  SWCLK/BOOT0, GND, and SWO. Post-pot firmware updates must use the RS-485
  application bootloader; the enclosure does not expose J3.

## Address map

| Device | Address / selection |
|---|---|
| SHT45 | `0x44` fixed |
| LMP91000 | `0x48` fixed |
| TMP117 cell | `0x49`, ADD0 to V+ |
| ADS1119 | `0x40`, A1=A0=GND |
| BMP390 DNP | `0x76`, SDO=GND and CSB=VDDIO |

## Modbus register map

The probe is a Modbus RTU slave, **9600 8E1, address 3**, on the shared farm
RS-485 bus (1 and 2 are the Truebner SMT100s; 253 is answered as a discovery
alias, which is only safe with a single device connected). `firmware/src/regmap.h`
is the implementation and this table is the design record; `firmware/FIRMWARE.md`
carries the working copy with the fault semantics. Everything is exposed through
FC03; FC04 mirrors it; FC06/FC16 reach the config block and the firmware
updater's two blocks.

The layout is dictated by the master. A Dragino RS485-LS reads with literal
pre-programmed frames over a contiguous block — `AT+COMMAND3=03 03 00 00 00 08,1`
— and its uplink is a LoRaWAN payload. So every channel that must survive each
cycle is packed into ONE eight-register block at address zero: 16 bytes, one
`AT+COMMAND`, alongside the two SMT100 blocks already on the bus. Diagnostics and
configuration sit further out, where a field technician can reach them but the
routine uplink never pays for them.

**Undefined addresses raise exception 02 rather than reading as zero, and a read
spanning the gap between blocks is refused.** `0x0000` in the oxygen register
decodes as a perfectly plausible 0.00 %vol, which is exactly what an anaerobic
pile produces; a mistyped `AT+COMMAND` must look like a fault, not like anoxia.

### Primary block, `0x0000`, 8 registers

| Reg | Name | Encoding | Invalid |
|---|---|---|---|
| 0 | `O2_COMP` | u16, %vol x 100, **dry basis** | `0xFFFF` |
| 1 | `O2_RAW` | i16, cell uA x 100 | `0x8000` |
| 2 | `T_TIP` | i16, 0.01 C (TMP117) | `0x8000` |
| 3 | `T_CHAMBER` | i16, 0.01 C (SHT45) | `0x8000` |
| 4 | `RH_CHAMBER` | u16, 0.01 %RH | `0xFFFF` |
| 5 | `HEATER_DUTY` | u16, 0.01 % (always 0 in v0) | - |
| 6 | `FAULTS` | u16 bitfield (`firmware/src/faults.h`) | - |
| 7 | `SETTLE_S` | u16 seconds remaining, 0 = settled | - |

`O2_RAW` is signed deliberately: the SGX sign convention is an open release gate
(`SCHEMATIC-REVIEW.md` M4) and the bench air-versus-nitrogen pair settles it.
Firmware that took an absolute value would hide the answer.

**`O2_COMP` is dry basis** - oxygen as a fraction of the water-free gas - and
`O2_RAW` is the uncorrected cell current. Water vapour is a gas and it displaces
everything else pro rata, so a wet-basis number falls as the pile gets hotter and
wetter even when aeration has not changed: in a 60 C pile at 100 %RH, fully
aerated air is 16.815 %vol wet against 20.946 dry, a 19.7 % error in the
direction that reads as anoxia. Dry basis is what the compost literature, a
Draeger tube and a lab instrument all report, and the only basis on which a trend
means respiration rather than weather. The correction is
`C_dry = C_wet * P / (P - p_w)` with `p_w = RH/100 * p_sat(T_chamber)`, and the
air point is corrected the same way when it is taken, because a current measured
in moist air attributed to dry 20.946 % mis-scales K by 1-2 % permanently. When
RH, chamber temperature or `P` is unavailable the correction cannot be evaluated
and `O2_COMP` publishes `0xFFFF`; it never falls back to the wet-basis number
under the corrected name.

The criterion for "unavailable" is the **age of the chamber reading**, not the
`I2C_FAIL_SHT` bit. That bit was briefly used for it, on 2026-09-06, and it is
the wrong instrument: the same bit was then raised for the SHT45's own scheduled
de-creep pulse, whose recovery mask blanked the primary oxygen channel
three times a day and labelled firmware-ordered maintenance a bus failure. The
sampler instead keeps the last measured `(RH, T_chamber)` pair and bridges a gap
of up to `O2P_RH_MAX_AGE_S` = 45 s with it - 30 s of mask plus the 1.1 s blocking
pulse plus a second of 1 Hz sample quantisation is 32.1 s worst case, so 45 s is
that with 40 % margin. **The mask is now 350 s and the bound deliberately does
not cover it**: the recovery was measured on 2026-09-07
(`SHT-DECREEP-MASK-IS-TOO-SHORT.md`) and the mask lengthened, but a staleness
budget is set by how fast the bridged quantity goes wrong, not by the length of
the gap being papered over. The cache carries chamber *temperature* as well as
humidity, and through `p_sat(T)` a 5 K stale temperature is a 6.3 % error at
60 °C and 10.8 % at 70 °C - so `O2_COMP` takes its sentinel for the remainder of
each mask instead. `O2_RAW` needs no SHT45 and publishes throughout.
Since 2026-09-09 the mask also raises **no fault at all**, so a masked chamber
and a dead one are told apart by the presence of `I2C_FAIL_SHT` rather than
being identical. Past the cap the value is unevaluable and
`O2_COMP` takes its sentinel, so a genuinely dead SHT45 still reports as one; and
an air-point calibration is never bridged, because a permanent constant gets a
humidity measured in its own cycle or none at all. Full argument, bench evidence
and test vectors: `O2-HUMIDITY-CORRECTION.md`.

### Diagnostic block, `0x0010`, 32 registers, read-only

`VREF_MON_MV`, `VA_MON_MV`, `VIN_MON_MV`, `AFE_VOUT_MV`, `DEW_MARGIN` (i16,
0.01 K), `PRESSURE_HPA` (0 - the BMP390 option is deleted), `UPTIME_HI/LO`, `FW_VERSION`,
`HW_REV`, `RESET_CAUSE`, `LMP_READBACK` (TIACN<<8 | REFCN as actually read),
`MB_CRC_ERRS`, `MB_FRAME_ERRS`, `I2C_ERRS`, `EXP_DATA` (`0xFFFF` - J2 is deleted),
`SETTLE_RESTARTS` (`0x0020`), `SAMPLE_SEQ` (`0x0021`), `HEATER_BLOCK` (`0x002E`),
`SAMPLER_TIMING_MS` (`0x002F`).

`CAL_STATE` (`0x002B`) reports calibration completeness: bit 0 the air point is
the datasheet nominal, bit 1 no zero point taken. A register and not two fault
bits, because the 16-bit fault word is full and because these are commissioning
state rather than faults.

`CAL_ZERO_NA_HI/LO` (`0x0046`/`0x0047`) hold the cell dark current, i32 signed
nanoamps, subtracted from every current and from the air point before K.

`CMD_RESULT` (`0x002A`) reports the outcome of the last calibration trigger in
its high byte and the last flash store in its low byte: 0 none, 1 pending,
2 OK, 3 failed. An acknowledged Modbus write means the REQUEST was accepted,
never that the calibration was taken or that it reached flash; this register is
what separates those. Each byte latches until its own command is issued again.


`CE_MV` (`0x002D`) is CELL_CE_DRV in mV, u16, `0xFFFF` invalid - the
potentiostat's control effort, and the register that names which hardware fault
you have. A1 drives the counter electrode until the reference electrode sits at
the commanded bias, and the loop closes THROUGH THE CELL, so an absent,
high-impedance or badly-led cell - or a dead A1, as on 2026-09-04 - leaves A1
without feedback and CE against a rail while the register image still reads back
as written. `LMP_READBACK` cannot see that; `CELL_BIAS_MV` shows the symptom,
this shows the cause. Outside the compliance window SNAS506I 6.5 characterises
A1 over, it raises `AFE_CONFIG_MISMATCH`. Not polled by the node: the frame has
4 bytes of DR3 headroom and this is a bench question.

`T_AFE` (`0x002C`) is the LMP91000's own die temperature, i16 0.01 C, `0x8000`
invalid - the only register that reports the AFE's silicon. It is not `T_DIE`
and not `T_TIP`: on 2026-09-08, with the ring heater holding `T_TIP` at
78.00 C, the MCU die sat at 49 C, a 29 K gradient across one board. The
published cell current is `(0.67*VREF - VOUT)/R_TIA` with `R_TIA` hardcoded at
7000 ohm, and SNAS506I gives that resistor an accuracy but no tempco and no
gain-versus-temperature curve, so it is the one uncharacterised term in the
chain - and it drifts with this temperature, not with the tip's. Sampled in
`OP_MODE` 111, which keeps the TIA powered so the cell is never unbiased;
entry and exit both verify the `MODECN` readback, because the oxygen swing
decodes as a plausible 72-77 C and no value check could tell them apart.

`T_DIE` (`0x0022`) is the MCU die temperature, i16 0.01 C, `0x8000` invalid.
Not ambient and not part of the oxygen path - it is the silicon, self-heating
included, at about +/-5 C. It is here because it is the only temperature on
the board that does not arrive over I2C1, so it separates a dead bus from a
real excursion.

`FAULTS_EVER` (`0x0023`) is every fault bit seen since power-up, never cleared,
and `ADS_FAIL_COUNT` (`0x0024`) counts cycles in which the ADS1119 delivered no
conversion, saturating at `0xFFFF`. Both exist because `FAULTS` is rebuilt from
zero every second while a buried probe is polled every five minutes: a
one-cycle converter fault is published for one second in three hundred. The
fault word carries a bounded latch so such an event survives to the next poll
(`O2P_FAULT_LATCH_S`, 330 s - one nominal poll interval plus 10 %), but the
latch self-clears, so the rate would be lost without a counter. A probe that
glitches once and one that glitches hourly read identically between events
otherwise.

`WE_BUF_MV` (`0x0025`), `RE_BUF_MV` (`0x0026`) and `CELL_BIAS_MV` (`0x0027`) are
the buffered cell electrodes on ADS1119 AIN2/AIN3 and the bias between them
(`WE - RE`, i16, `0x8000` invalid). Specified here from the start and not
implemented until 2026-09-08: AIN3 was meanwhile sampled and published as
`vin_mv` until `e31d5ac` removed it. Cell bias is what fails silently — the
working point walks off target while every other register stays plausible — and
it is the only channel that distinguishes a cell that changed from a measurement
that changed. Sampled after the oxygen channel so that adding it cannot alter
which channel precedes AIN0.

`BUILD_ID_HI` (`0x0028`) and `BUILD_ID_LO` (`0x0029`) answer *which binary is
this*. `FW_VERSION` cannot: it is a hand-edited constant, and it read v0.1 on every
probe ever built, through every install, so when `O2_RAW` stepped 0.51
%vol across the 2026-09-07 install nothing on the wire named the image on either
side of the step. `BUILD_ID` is bit 31 the working tree was dirty at build time,
bits 30..28 reserved, bits 27..0 the 7-hex-digit prefix of the commit the image
was built from. `tools/pio_build_id.py` stamps it and **fails the build** if git
cannot answer — an unidentifiable image is the condition the register exists to
prevent, and the probe is potted. Zero means *built without the stamp* (only the
host test build after 2026-09-08) and is never reported as a commit.


### Config block, `0x0030`, 27 registers, read/write, flash-backed

`SLAVE_ADDR`, `BAUD_CODE`, `PARITY_CODE`, `RH_SETPOINT`, `DT_MAX_K`,
`HEATER_MAX_DUTY`, `HEATER_PWM_HZ`, `CAL_AIR_NA_HI/LO`, `CAL_TEMP_C100`,
`TEMPCO_PPM_K`, `SHT_PULSE_H`, `SHT_PULSE_TRIG`, `CAL_TRIGGER`, `COMMIT`,
`CONFIG_CRC` (read-only), then the two PI gains:
`HEATER_KP` at `0x0040` and
`HEATER_KI` at `0x0041`, both in 0.01 units, and the three water-vapour and
pressure fields: `ASSUMED_P_HPA` at `0x0042`, `CAL_AIR_FRAC` at `0x0043` and
`CAL_P_HPA` at `0x0044`.
The cell's dilution efficacy `DIL_ALPHA` sits at `0x0045`.
`HEATER_RH_CONSENT` sits at `0x0048`.
`TIP_SETPOINT` sits at `0x0049` and `HEATER_TIP_CONSENT` at `0x004A`.

`HEATER_RH_CONSENT` (`0x0048`) is consent to **autonomous** heating: only the
magic `0x9C07` lets the RH loop drive the ring, and anything else — zero
included — raises `NO_CONSENT` and holds duty at zero. It does not gate the
bench override, which carries its own magic, is volatile, and is used with an
operator present.

`TIP_SETPOINT` (`0x0049`) and `HEATER_TIP_CONSENT` (`0x004A`) are the
**persistent tip-temperature loop** — the flash-backed counterpart of the
volatile bench override at `0x0060`.

Until this block existed, nothing in the firmware regulated a *temperature*:
the only loop was on chamber RH, and the one way to hold a tip temperature was
to arm the override, which needs an operator and which every reset clears. That
is correct for a characterisation run and useless for anything that must
survive a power cycle — a reflash on 2026-09-08 ended a bath comparison
mid-experiment for exactly this reason.

`TIP_SETPOINT` is an i16 in 0.01 °C. `0x8000` is the sentinel and means the
mode is off; anything else must lie in `0..8000` (0.00–80.00 °C), the same
envelope and the same sentinel as the override's `0x0062`, so an operator who
learned one has learned both. A negative that is not the sentinel is refused
rather than quietly meaning "never heat".

`HEATER_TIP_CONSENT` takes the magic `0x71C0` — a **third** token, distinct
from both `0x8EA7` (bench arm) and `0x9C07` (RH consent). The three authorise
different things, and this one is the largest permission of the three: holding
an absolute temperature, unattended, until someone writes the sentinel back.
Reusing the RH magic would let consent given for a loop that sits a few kelvin
above ambient silently authorise one that sits tens of kelvin above it. A
stored setpoint whose consent is missing **refuses** — it raises `NO_CONSENT`
and holds duty at zero rather than falling through to the RH loop, because
silently running a different control law than the one configured is worse than
not running at all.

Precedence is **override > persistent tip > RH**: an armed override means an
operator is at the bench now, and their intent outranks anything a previous
session committed to flash.

The persistent mode suppresses exactly **one** interlock, `NO_RH` — a
temperature loop has no use for humidity. `NO_CHAMBER` and `DT_LIMIT` stay
live, unlike under the override, which suppresses them because exceeding the
0–4 K envelope *is* the experiment and an operator owns that. Here nobody is
present, so the envelope keeps its meaning. On Rev A this costs nothing (the dT
clamp is structurally inert — tip and chamber are one thermal node), but on a
revision with a thermally separated sensor it is the difference between a loop
that holds 80 °C in a pile and one that refuses to. Refusing is correct.

Neither consent is **ever** carried across a config migration, and the setpoint
always lands on the sentinel: an upgrade leaves both autonomous loops off,
whatever the old record said.

There is **no persistent gain pair**. The flash record is fixed at 64 bytes, of
which 14 are header and CRC, so the config may not exceed 50 and only six bytes
were free — four went to the setpoint and its consent. Both tip loops therefore
share the volatile gains at `0x0063`/`0x0064` and a reset restores the
conservative defaults. That is the right thing to lose: gains are tuning, and a
probe resuming after a power cycle on saturate-early/integrate-slowly defaults
is safer than one resuming on somebody's aggressive bench tuning. What had to
survive a reset is the target and the authorisation to pursue it.

It is a separate field from the duty maximum on purpose. While the heater was
compiled out, `NOT_COMPILED` refused every path whatever the stored config
said; compiling the ring in removed that guarantee and left a nonzero stored
duty maximum sufficient, by itself, to start an unvalidated control loop on a
buried probe with nobody present — and migrations carry that maximum forward
by design. The maximum answers *how hard*, a tuning question; consent answers
*at all*. One field cannot be both. `config_migrate.c` never carries consent,
so every upgrade lands with autonomous heating off.

`DIL_ALPHA` (`0x0045`, alpha x 1000, default 1000) is how much of the
water-vapour dilution the cell's current actually shows. The gas law says the
correction is `P/(P-p_w)`; the 2026-09-07 sweep says this cell moves only
`alpha = 0.453 +/- 0.052` of it, so the factor applied is
`f_eff = 1 - alpha*(1 - (P-p_w)/P)` — on both sides, the air point's fraction
and the measurement, because it describes the cell rather than the gas. The
default of 1000 is the plain gas law and reproduces every earlier firmware
exactly; it is deliberately not 453, because that is one cell's measured
coefficient and a default is a claim about all of them. Writing this register
restates `CAL_AIR_FRAC` under the new alpha — the stored fraction was computed
with the old one and `K` is fixed against it — which inverts exactly, so no
recalibration is required and the write is order-independent. See
`O2-HUMIDITY-CORRECTION.md` §15.

The two heater gains are registers rather than compile-time constants because
the plant they tune can only be characterised in a real pile:
`THERMAL-BARRIER.md` bounds the PCB conduction path, not ring-to-gas. The
alternative was reflashing to change a number, which post-pot means the RS-485
updater and a full image transfer. Adding them moved the config block from
16 to 18 registers and took the flash record's layout version to 2. A version-1
record still falls back to defaults - version 1 predates any deployed probe and
has no decoder - and the defaults hold `HEATER_MAX_DUTY` at 0, so a layout
change fails towards no heat.

`ASSUMED_P_HPA` (`0x0042`) is the total pressure the water-vapour correction
uses, in hPa, bounded 500-1100 and defaulting to 930 - the 715 m Steingrubenhof
site. It exists because the BMP390 option is deleted and `PRESSURE_HPA` reads 0,
so without it the correction has no `P` at all.

**What a wrong `ASSUMED_P_HPA` actually costs, corrected 2026-09-06.** This
section used to say "sea level is 8 % away", which is the difference in
absolute pressure and not the error in the published number. `P` appears
twice - once in the air point's own oxygen fraction and once in the
measurement's dilution factor - and the two uses partially cancel. Leaving the
930 default in place while calibrating *and* deploying at sea level gives about
**+2.10 % relative** at a 25 C / 50 %RH air point read out at 60 C / 100 %RH,
not +8 %. The residual depends on both conditions, so it is a range rather than
a constant, and it is still worth getting right - but 2 % is the number to
quote.

What does *not* cancel is the weather. `P` moving +/-3.5 % after the air point
was taken produces about **-4.17 % / +4.14 % relative** on the published value
at that same 60 C / 100 %RH operating point - four times the size of the
in-situ altitude residual above, and the largest uncorrected term left in the
oxygen channel. **It is not correctable without a barometer**, and Rev A has
none. With one, `CAL_P_HPA` below is what corrects it.

`CAL_AIR_FRAC` (`0x0043`) is the oxygen fraction actually present when the air
point was taken, %vol x 1000, and it is written by the `CAL_TRIGGER` routine
together with `CAL_AIR_NA`. The air point is taken in moist room air, so the
recorded current belongs to the wet fraction (0.2070 at the 23.4 C / 42.3 %RH
point this bench used, not 0.20946); attributing it to dry air makes K 1.4 %
high for the life of the probe, and a probe calibrated in a damp shed and one
calibrated in a dry lab then genuinely disagree. Zero means "unknown" and
`O2_COMP` stays invalid. `CAL_AIR_NA` still holds exactly what the ADC read, so
it remains comparable with `O2_RAW` in air.

`CAL_P_HPA` (`0x0044`) is the total pressure in force when the air point was
taken, in hPa, `0` meaning unknown. It is not a duplicate of `ASSUMED_P_HPA`:
that one is the pressure *now* and this one is the pressure *then*. The cell
answers to `pO2 = C * P`, so its current at a given fraction is proportional to
total pressure, and `K` is fixed once at the air point and therefore carries
that pressure inside it. A measurement made at a different `P` has its current
normalised by `P_cal / P_meas` before the inverse; without that step, correcting
the vapour dilution against a real barometer reading would still leave about
-3.2 % / +3.2 % of the weather term on the answer - the correction would be
half-applied. With no barometer fitted, `P_meas` is `ASSUMED_P_HPA` and `P_cal`
was the same register, the ratio is exactly `1`, and this changes no published
number on Rev A. It is the structure that makes populating the BMP390 an actual
fix rather than a partial one. A stored `0` is read as `P_cal == P_meas`, i.e.
no normalisation - never as an assumed atmosphere.

Adding these three took the config block to 21 registers and the flash record's
layout version to **4** (version 3 existed for one commit and never reached a
board). **An older record is now migrated rather than discarded**, and the
difference is not cosmetic: discarding it defaulted the whole structure,
including `SLAVE_ADDR`, `BAUD_CODE` and `PARITY_CODE`, so a probe an operator
had moved off the default transport stopped answering its master the moment it
took a firmware update - unrecoverably, on hardware that is potted and buried.
The migration carries transport, heater tuning, pulse interval, tempco and
`CAL_TEMP_C100` forward, and zeroes `CAL_AIR_NA`, `CAL_AIR_FRAC` and
`CAL_P_HPA` and nothing else, because the air point is the only thing whose
meaning changed: a version-2 `CAL_AIR_NA` was taken against an assumed dry
atmosphere at a humidity nobody recorded. A migration that fails validation
still falls back to full defaults. **Recalibration is therefore still required
after this update:** `CAL_DEFAULT` is raised and `O2_COMP` publishes the
sentinel until a fresh air point is taken. What is no longer required is a trip
to the pile.

A multi-register write is validated against a copy and committed all-or-nothing,
so a frame setting a legal address and an illegal baud rate changes neither.
Serial parameter changes take effect only after the response has left the wire.

Two actions require a magic value rather than a `1`, because both are
destructive and one stray bit in a frame that happened to pass CRC is otherwise
enough: `CAL_TRIGGER` (`0x003D`) takes an air-point calibration on `0xCA11`, and
`COMMIT` (`0x003E`) erases and rewrites the config flash page on `0x5AC1`.

### Heater test block, `0x0060`, 5 registers, read/write, **volatile**

The bench override. It drives the membrane ring open-loop at a chosen duty,
at any humidity and without the `DT_MAX_K` clamp, so the thermal plant can be
characterised — the RH loop's gains describe a plant nobody has measured, and
the loop refuses to run without the humidity signal that characterisation does
not need.

| Reg | Name | Meaning |
|---|---|---|
| `0x0060` | `HEATER_TEST_ARM` | write `0x8EA7` to arm, anything else disarms; reads back `1`/`0` |
| `0x0061` | `HEATER_TEST_DUTY` | duty when no target is set, 0.01 %, clamped to the configured maximum |
| `0x0062` | `HEATER_TEST_TIP_SP` | tip setpoint, i16 0.01 °C; `0x8000` = none, so the override runs open loop |
| `0x0063` | `HEATER_TEST_KP` | tip-loop proportional gain, 0.01 units |
| `0x0064` | `HEATER_TEST_KI` | tip-loop integral gain, 0.01 units per second |

**Two modes.** With no setpoint the override commands a fixed duty. With one,
it closes a PI loop on tip temperature — which is the only temperature control
anywhere in this firmware; the shipped loop regulates chamber humidity and
never a temperature.

That distinction matters more than it looks. Driving open loop toward 80 °C
does not hold 80 °C: full duty runs until the absolute clamp cuts at 80.00 and
releases at 75.00, giving a mean near 77.5 °C with ±2.5 K of sawtooth, produced
by bouncing a *protection* device off its limits once per thermal time
constant. A clamp that fires every cycle in normal use has stopped being a
clamp. A setpoint is bounded a kelvin below it, so the clamp firing at all
means the loop failed.

The tip loop carries its own gains rather than reusing `HEATER_KP`/`HEATER_KI`
at `0x0040`/`0x0041`: those are in %RH and do not transfer to an error in
kelvin, and overwriting a probe's humidity tuning as a side effect of a bench
test is not a trade worth making. Switching modes zeroes the integrator, since
an integral wound up in 0.01 %RH means nothing in 0.01 K.

**Not in the config block and not in flash.** Arming is lost on reset and on
brownout, it is not covered by `CONFIG_CRC`, and `COMMIT` cannot persist it. A
test mode that survives a power cycle is one that gets left armed in a potted
probe two metres down a pile.

It suppresses exactly three interlocks — `NO_RH`, `NO_CHAMBER` and `DT_LIMIT` —
which are the ones protecting the *controlled quantity*. Every interlock
answering to the hardware stays live: the TMP117 therm-mode cutoff (`SAFETY`),
a missing tip temperature (`NO_TIP`), the absolute tip clamp at 80.00 °C
(`TIP_LIMIT`, release 75.00 °C), the rail fault, the runaway latch, the PA7
pin-integrity assertion, and `HEATER_MAX_DUTY`, which still caps the commanded
duty and still means *off* at zero. With `TIP_LIMIT` left in place an armed
override is a bang-bang thermostat between 75 °C and 80 °C, which is the
mechanism for "drive the tip to 80 °C" rather than an obstacle to it.

Runaway *accumulation* is suspended while armed, because external heat — a
water bath — produces the die-referenced runaway signature at zero commanded
duty and would latch mid-run. The latch itself is never cleared by this mode.

### Update block, `0x0050`, 16 registers

The RS-485 firmware updater's control registers, implemented in
`firmware/src/update.c` and answered by the application and the bootloader
alike.

| Reg | Name | Meaning |
|---|---|---|
| `0x0050` | `UPD_STATUS` | state and last error; bit 15 = the bootloader is answering |
| `0x0051` | `UPD_BLOCK_MAX` | payload registers accepted in one block (120) |
| `0x0052` | `UPD_SLOT_HI` | staging slot size, high word |
| `0x0053` | `UPD_SLOT_LO` | low word |
| `0x0054` | `UPD_CMD` | command magic: begin `0xB001`, commit `0xB002`, boot `0xB003`, abort `0xB004`, stay `0xB005` |
| `0x0055` | `UPD_LEN_HI` | declared image length, high word |
| `0x0056` | `UPD_LEN_LO` | low word |
| `0x0057` | `UPD_CRC_HI` | declared CRC-32 (zlib), high word |
| `0x0058` | `UPD_CRC_LO` | low word |
| `0x0059` | `UPD_RECV_HI` | bytes accepted, high word |
| `0x005A` | `UPD_RECV_LO` | low word |
| `0x005B` | `UPD_NEXT_SEQ` | block expected next - how a master resynchronises |
| `0x005C` | `UPD_LOADER_VER` | bootloader version, 0 when the application answers |
| `0x005D` | `UPD_IMAGE_VER` | version of the running image |
| `0x005E` | `UPD_INSTALLS` | installs completed |
| `0x005F` | `UPD_RESERVED` | 0 |

Every command is a 16-bit magic for the same reason `COMMIT` and `CAL_TRIGGER`
are: each erases tens of kilobytes of flash or reboots a settled cell, and one
stray bit in a frame that happened to pass CRC must not be enough.

### Update data window, `0x0080`, 123 registers, write-only

`UPD_DATA` (`0x0080`). One FC16 write is one block — first register the block
sequence number, the rest image payload, high byte first — capped at 120
payload registers so a block is a whole number of the 64-bit doublewords this
part programs. That is 240 bytes on a laptop's dongle and, over the Dragino's
40-byte `A8` downlink ceiling, 24 bytes on the same protocol.

**The flash map this implies is in `firmware/src/flash_map.h`**: a 16 KiB
bootloader at `0x08000000`, a 52 KiB run slot at `0x08004000` that the
application is linked into, a 52 KiB staging slot at `0x08011000`, and A/B
descriptor pages. `firmware/tools/check_flash_map.py` fails the build if the
linker scripts or `platformio.ini` disagree with it. There is one staging slot
and therefore **no automatic rollback**; the bootloader's one-second knock
window is the recovery path.

**This section is checked mechanically.** `firmware/tools/check_regmap_docs.py`
parses `src/regmap.h` and fails if the block bases, the block sizes, the primary
register names or the exception-02 rule stated here have drifted from it. The
diagnostic block grew from 16 to 18 registers and the config block moved from
`0x0020` to `0x0030` within a day of this map first being written down, so the
check is not hypothetical.

## Controlled mechanical datums

- Board: 20.0 x 107.0 mm, R2.0 cable-end corners, square gas end, initially
  1.0 mm FR-4.
- Potting datum: y=82.0 mm; ordinary-component exclusion y=80–86 mm.
- Cell centre: (10.0, 93.5) mm; unrelated-part courtyard diameter 15.0 mm.
- Rear-flow aperture: a 3.0 × 6.0 mm vertical NPTH routed slot centred 1.8 mm
  gasward of the cell axis. Its nearest edge is 0.50 mm from the pad-2 copper
  edge. It spans the axis and provides a first-article
  airflow/fit window without inventing a rear-port diameter that DS-0637 Issue
  2 does not specify. Physical sample fit remains required for production.
- No mounting holes. Two exact 6.75 × 1.5 mm horizontal Edge.Cuts slots at
  absolute y=134 mm form a partial thermal break between the potted body and
  gas-side tip while retaining 0.75 mm edge webs and a 5 mm centre neck. Two
  additional 0.8 × 16 mm vertical side slots centred at `(101.2,145.0)` and
  `(118.8,145.0)` mm remove lateral coupling over y=137–153 mm. Their upper
  caps are 2.25 mm gasward of the transverse-slot edge, so they are not a
  16 mm series barrier to the body. A named rule area excludes zone fill on
  every copper layer across y=133–135 mm; the crossing inventory is re-derived
  from the routed board rather than fixed at Rev A's 14 segments and two vias. The gas-side B.Cu island has a solid
  `/HEATER_LOW` thermal-spreader zone with voids for both side slots. Cable
  strain relief, expansion-connector chord clearance, ring/membrane carrier,
  and gas volume require the tube/fixture fit check in `PLACEMENT.md`.

## Release gates and provisional choices

- Fit a physical SGX-OX-ROHS-Mini sample before production qualification. The
  released first-article footprint is `SGX-OX-ROHS-Mini_ISS2`; the elongated
  aperture is deliberately a prototype fit feature, not a datasheet dimension.
- ~~Independently recheck the BMP390 bottom-view numbering and land geometry.~~
  **Closed by deletion, 2026-09-05.** U14/C23/C24 are gone and
  `o2-probe:BMP390_LGA10_DRAFT` leaves the project library with them: an
  unverified land on a released board was the risk, and never fitting it was
  not a mitigation. I²C `0x76` is free for a future pressure channel.
- D2 is one Littelfuse `SM712-02HTG` asymmetric RS-485 array in SOT-23:
  pin 1=A, pin 2=B, pin 3=GND, cable-side of R2/R3. It replaces the invalid
  earlier interpretation of SM712 as two independent SMA diodes.
- U1's package mapping is locked by generator and exported-net assertions to
  AP63205 DS41326: 1=FB, 2=EN, 3=VIN, 4=GND, 5=SW, 6=BST.
- U4A feeds the 4.7 uF reference node through 47 ohm isolation with unity-gain
  feedback taken directly at the op-amp output. Stability/startup/noise still
  require bench verification, but the PCB no longer hard-wires a 4.7 uF load
  directly onto OPA2333.
- Derive the worst-case `3V3A` current budget and verify U3 input headroom with
  R32 tolerance and temperature. Compare 0 ohm, 10 ohm, and any proposed bead
  by measuring the `+5V_ANALOG` spectrum around 256 kHz, 1.1 MHz, and PFM burst
  components, plus ADS1119 mean/offset at heater 0%, intermediate, and 100%
  duty. Do not qualify this filter using RMS noise alone.
- ~~J2 may become a sealed pad field if the Micro-Fit swept envelope does not
  fit the actual tube.~~ **Closed by deletion, 2026-09-05** — the swept-envelope
  question cannot be asked of a connector that is not there. A future revision
  wanting a daughterboard lands a pad field, which is what this gate always
  permitted.
- Confirm every exact MPN/package pin map, MCU alternate-function assignment,
  input protection rating, heater steady-state temperature, and component
  ambient rating in the independent review before PCB transfer.
- Bare-board first articles may be ordered after schematic/PCB parity, DRC,
  exact outline/SGX-aperture validation, and ring-land review pass. A 1:1
  board/ring/tube coupon, real cell fit, and potting-fixture interface review
  remain mandatory before production or automated assembly.

## Source access log

Research date: 2026-08-21. A standalone Playwright 1.55 session drove installed
Google Chrome and validated the rendered TI product pages and their current
datasheet links. PDF load-bearing pin tables were also rendered and visually
checked after download.

| Source | Access result | Use |
|---|---|---|
| TI LMP91000 product page, <https://www.ti.com/product/LMP91000> and current Rev I PDF <https://www.ti.com/lit/gpn/LMP91000> | Clean rendered DOM in Playwright; PDF retrieved and rendered | WSON-14 pin table, DAP to AGND, fixed I2C address |
| TI ADS1119 product page, <https://www.ti.com/product/ADS1119> | Clean rendered DOM in Playwright; current Rev A PDF retrieved and rendered | RTE WQFN pin table and address straps |
| TI THVD1410 product page, <https://www.ti.com/product/THVD1410> | Clean rendered DOM in Playwright; current Rev E PDF retrieved and rendered | SOIC-8 pin table and half-duplex interface |
| ST STM32G071CB product page, <https://www.st.com/en/microcontrollers-microprocessors/stm32g071cb.html> | Non-clean: Chrome returned `ERR_HTTP2_PROTOCOL_ERROR`; curl also failed. Current ST product identity was recovered through indexed ST search results; ST DS12232 Rev 1 was obtained through DigiKey and its LQFP48 pin figure was rendered | MCU identity and preliminary LQFP48 map. Exact suffix-7 temperature/rating and current revision remain reviewer checks |
| Bosch BMP390 DS002, <https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp390-ds002.pdf> | Direct official PDF retrieved; pin table and package drawing rendered | DNP I2C wiring, 0x76 strap, provisional LGA-10 footprint |
| Diodes AP63205 family DS41326 Rev. 3-2, <https://www.diodes.com/assets/Datasheets/AP63200-AP63201-AP63203-AP63205.pdf> | Direct official PDF retrieved and pin/application page rendered during independent review | Corrected and asserted TSOT-23-6 pin map |
| Littelfuse SM712 series, <https://www.littelfuse.com/assetdocs/tvs-diode-array-spa-sm712-datasheet?assetguid=8313a28c-8802-4d47-a2a7-e30b5b1f67d8> | Official indexed datasheet result; exact `SM712-02HTG` topology selected | RS-485 cable-side TVS pin map and footprint |
| Diodes SMBJ series, <https://www.diodes.com/assets/Datasheets/ds19002.pdf> | Official indexed datasheet result; exact `SMBJ15A-13-F` selected | Input TVS value and SMB/DO-214AA footprint |
| SGX Sensortech `SGX-OX-ROHS-Mini`, DS-0637 Issue 2, 28-May-2026, <https://sgxsensortech.com/uploads/f_note/DS-0637-SGX-OX-ROHS-Mini_iss2.pdf> | Official product page rendered in Playwright and its exact manufacturer PDF retrieved; product drawing visually validated at 300 dpi | Body Ø14.40 mm, height 8.30 mm, three Ø0.64 mm pins at 2.54 mm pitch, pin-row offset 2.50 mm, general tolerance ±0.15 mm. The drawing does not dimension the rear gas port; the first article uses a gasward-offset 3 × 6 mm fit/flow slot. |

The retrieved PDFs were used as working evidence in `/tmp/o2-datasheets` and
were not silently promoted into the repository as a permanent literature
archive.

## PCB capture status

PCB first-article release date: 2026-08-24. `o2-probe.kicad_pcb` is linked to
the 106-footprint schematic and preserves the exact 20 × 107 mm outline with
R2 cable-end corners and a square gas end, local y=82 pot line, and SGX centre
`(10,93.5)`. The stack is two layers on 1.0 mm, nominal ENIG, 1 oz outer
copper on a 0.93 mm FR-4 core (Fab, 2026-09-05 — it was four layers with 0.5 oz
inner copper through Rev A). 1.0 mm is not a default: the tube fit, the potting
fixture and `RING-PCB.md`'s finger envelope all budget the board's own
thickness, so the layer count changed and the thickness did not.

The tip has no second TMP117. Two horizontal thermal-break slots are centred at
local y=84.0, immediately gasward of the potting datum; two vertical side slots
are centred at local x=1.2/18.8, y=95.0. They are not a sensor-isolation
feature. The calculated transverse bare-PCB resistance is about 98 K/W, with a
90–110 K/W engineering bound pending first-article measurement; the side-slot
length is not added in series. See `THERMAL-BARRIER.md`. RH1/RH2, Q2, U10,
U12, and the DNP pressure option are aligned behind J5. J5 provides two exact
2.0 × 3.0 mm PTH pads at local x=0/20, y=105.5. Their 1.0 × 2.0 mm plated
slots are centred on the left/right profile and explicitly marked as
castellated; wide B.Cu joins them independently of the hand-soldered ring. The
cell centre is 13.5 mm from the board end and U10 is 2.975 mm from the
ring-contact centreline.

The dense digital cluster places U6 at local `(14.5,44.5)`, rotated 180° in
the right-side lane beside U5. C8 moves to `(18,37.5)` to preserve a clean U6
courtyard without separating the analog-LDO output bypass from U3.

CELL_RE remains one 9.723 mm F.Cu segment with no via/test point and a driven
guard. It runs `(111.00,131.40)` to `(112.54,141.00)`: on 2026-09-01 the
SGX-OX-ROHS-Mini land pattern was corrected against DS-0637 (Issue 2, with
Issue 1 agreeing), which places Working on the CENTRE pin, so the RE land moved
from x=110.00 to x=112.54 and the segment lengthened from 9.652 mm. U7.13 to
U11.2 is 9.723 mm, still inside the 10 mm budget. `repair_guard_fill.py`
physically stitches three saved F.Cu fill regions on both sides of the trace;
the source outline alone is not credited as guard copper. The all-layer thermal rule area divides the In2 GND pour into two saved
regions, joined only by one explicit 0.15 mm three-segment jog through the left
web. The heated tip has a solid B.Cu `/HEATER_LOW` spreader immediately gasward of the
barrier.
KiCad 10.0.5 reports 0 DRC errors and 0 unconnected items, and the calibrated
audit rejects 33/33 known-bad variants. Six schematic-parity findings are
outstanding and are not from the layout: the footprint Value fields for DZ1,
Q1, R20, R21, R26 and R27 lag symbol values changed by a separate, in-progress
schematic edit. They must be back to zero before release.
**AND THE BOARD IS NOW BEHIND THE SCHEMATIC BY MORE THAN THAT.** The 2026-09-05
BOM pass (`docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md`) is schematic-side ONLY: `gen_pcb.py` was
deliberately NOT run, because the working tree holds another session's
in-progress two-layer layout work in `o2-probe.kicad_pcb`. The board still
carries J2, U14, C23/C24, R5/R6, R12-R16 and D4/D5/D6, still has R32/C7 in
0805, and has no J105/J106. Every DRC/parity number in this section predates
the change. Regenerate and re-measure deliberately, once, when that session
lands. The
27 exact courtyard pairs are
manual-assembly exceptions and legend layers are not exported. See
`FAB-READINESS.md`, `ASSEMBLY-EXCEPTIONS.md`, and `FAB-NOTES.md` for release
scope and remaining qualification work.
