# o2-probe Rev A firmware — v0

Modbus RTU slave for the SGX-OX-ROHS-Mini oxygen probe. STM32G071CBT7,
PlatformIO + STM32Cube (HAL headers, direct CMSIS register code).

`gen_sch.py` in the parent directory is the source of truth for the hardware.
`src/hw_contract.h` is **generated** from it and checked on every build; do not
edit it by hand.

```sh
pio test -e native      # portable logic, 23 cases
pio run  -e o2probe     # cross build
pio run  -e o2probe -t upload
python3 tools/gen_hw_contract.py            # regenerate after a schematic change
python3 tools/gen_hw_contract.py --check    # what the build runs
```

## What v0 does and does not do

Does: all four I²C devices, the oxygen conversion with air-point calibration,
the Modbus RTU slave and the full register map, bias supervision with the
15-minute settling rule, the condensation-margin channel, flash-backed
configuration, and an independent watchdog.

**Does not: drive the membrane heater.** `DESIGN.md:47-51` and
`FAB-READINESS.md:61` both state the TMP117 ALERT path "is not credited as an
autonomous overtemperature cutoff until firmware configures and fault-tests the
TMP117". Until that bench test is run and recorded, nothing may put 1 W into
the membrane carrier. The heater is off at three independent levels: an
`#error` behind `O2P_HEATER_ENABLE`, PA8 held as a plain output driven low and
never switched to alternate function, and TIM1's clock left off entirely.

**The cost of that, stated plainly:** the SGX cell is rated 15–90 %RH
*continuous, non-condensing*, and the heater is the only thing keeping the
membrane above the dew point of saturated pore gas. **v0 is a bench and
short-deployment build.** A v0 probe left in a pile for weeks will wet its
membrane. `DEW_MARGIN` and the `DEW_SUSPECT` fault exist so that is observed
rather than discovered afterwards.

Also absent: the **RS-485 application bootloader**. `SCHEMATIC-REVIEW.md` M2 is
emphatic that it must be installed *before potting*, because J3 is not exposed
through the enclosure and the STM32 ROM bootloader is not proven to work
through the half-duplex DE line. **Do not pot a probe running v0.**

## Bus settings

9600 8E1, matching the Truebner SMT100s already on this cable
(`tech/RS485-LS-SMT100.md:277`). Default slave address **3** — 1 and 2 are the
two SMT100s. Address **253** is answered as a discovery alias, the same
convention the SMT100 uses; that is only safe with a single device connected,
because two responders collide.

The Dragino master reads with literal pre-programmed frames:

```
AT+COMMAND3=03 03 00 00 00 08,1     # this probe, primary block, 8 registers
```

## Register map

Everything is exposed through **FC03** (holding registers); FC04 mirrors it.
Writes use FC06/FC16 and only reach the config block.

**Undefined addresses raise exception 02 rather than reading as zero.** A read
spanning the gap between blocks is refused for the same reason: `0x0000` in the
oxygen register decodes as a perfectly plausible 0.00 %vol, which is exactly
what an anaerobic pile produces. A mistyped `AT+COMMAND` must look like a
fault, not like anoxia.

### Primary block — `0x0000`, 8 registers (16 bytes, one uplink block)

| Reg | Name | Type | Scale | Invalid |
|---|---|---|---|---|
| 0 | `O2_COMP` | u16 | %vol × 100 | `0xFFFF` |
| 1 | `O2_RAW` | i16 | cell µA × 100 | `0x8000` |
| 2 | `T_TIP` | i16 | 0.01 °C (TMP117) | `0x8000` |
| 3 | `T_CHAMBER` | i16 | 0.01 °C (SHT45) | `0x8000` |
| 4 | `RH_CHAMBER` | u16 | 0.01 %RH | `0xFFFF` |
| 5 | `HEATER_DUTY` | u16 | 0.01 % (always 0 in v0) | — |
| 6 | `FAULTS` | u16 | bitfield | — |
| 7 | `SETTLE_S` | u16 | seconds remaining, 0 = settled | — |

`O2_RAW` is **signed** on purpose: `SCHEMATIC-REVIEW.md` M4 leaves the SGX sign
convention as an open release gate, and the bench air-versus-nitrogen pair is
what settles it. Firmware that took an absolute value would hide the answer.

### Diagnostic block — `0x0010`, 16 registers, read-only

`VREF_MON_MV`, `VA_MON_MV`, `VIN_MON_MV`, `AFE_VOUT_MV`, `DEW_MARGIN` (i16,
0.01 K), `PRESSURE_HPA` (0 — BMP390 is DNP), `UPTIME_HI/LO`, `FW_VERSION`,
`HW_REV`, `RESET_CAUSE`, `LMP_READBACK` (TIACN<<8 | REFCN as actually read),
`MB_CRC_ERRS`, `MB_FRAME_ERRS`, `I2C_ERRS`, `EXP_DATA` (`0xFFFF` — J2 is DNP).

### Config block — `0x0020`, 16 registers, read/write, flash-backed

`SLAVE_ADDR`, `BAUD_CODE`, `PARITY_CODE`, `RH_SETPOINT`, `DT_MAX_K`,
`HEATER_MAX_DUTY`, `HEATER_PWM_HZ`, `CAL_AIR_NA_HI/LO`, `CAL_TEMP_C100`,
`TEMPCO_PPM_K`, `SHT_PULSE_H`, `SHT_PULSE_TRIG`, `CAL_TRIGGER`, `COMMIT`,
`CONFIG_CRC` (read-only).

A multi-register write is validated against a copy and committed all-or-nothing
— a frame that sets a legal address and an illegal baud rate changes neither.
Serial changes take effect only after the response has left the wire.

Two actions need a magic value, not a `1`:

| Register | Magic | Effect |
|---|---|---|
| `CAL_TRIGGER` `0x002D` | `0xCA11` | take an air-point calibration this cycle |
| `COMMIT` `0x002E` | `0x5AC1` | erase and rewrite the config flash page |

Both are destructive — one overwrites the calibration, the other spends one of
roughly 10 000 flash cycles and stalls the CPU for tens of milliseconds. A
16-bit token makes an accident on a noisy line implausible.

## Fault bits and the validity rule

| Bit | Name | Invalidates O₂? |
|---|---|---|
| 0 | `SETTLING` | **yes** |
| 1 | `I2C_FAIL_LMP` | **yes** |
| 2 | `I2C_FAIL_ADS` | **yes** |
| 3 | `I2C_FAIL_TMP` | no (tip temperature only) |
| 4 | `I2C_FAIL_SHT` | no (chamber channels only) |
| 5 | `AFE_CONFIG_MISMATCH` | **yes** |
| 6 | `VA_LOW` | **yes** |
| 7 | `VIN_LOW` | no |
| 8 | `HEATER_RUNAWAY` | no |
| 9 | `TEMP_OVER` | **no — see below** |
| 10 | `DEW_SUSPECT` | no |
| 11 | `ADC_RANGE` | **yes** |
| 12 | `CAL_DEFAULT` | **no — see below** |
| 13/14 | `EXP_PRESENT` / `EXP_FAIL` | no |
| 15 | `HEATER_DISABLED` | no (always set in v0) |

Two exceptions that are easy to "tidy" into wrongness, so they are also
enforced by `_Static_assert` in `src/faults.c`:

- **`TEMP_OVER` does not invalidate.** `PLAN.md:211-228` (decision 2026-08-27)
  deliberately runs the cell above its 60 °C rating because the thermophilic
  phase is the phase the probe exists to observe. Above 60 °C the reading is an
  *extrapolation* and is flagged as one. This overrides
  `compostlab/research/COMPOST-O2.md` §6.
- **`CAL_DEFAULT` does not invalidate.** An uncalibrated cell is 0.07 ± 0.03 mA
  in air — data of known-poor accuracy, not absent data.

Before the first sample completes, every channel reads its invalid sentinel and
`SETTLING` is set. A freshly booted probe that never converts must not publish
0.00 %vol at 0.00 °C with a clear fault word.

## Two hardware facts the firmware is shaped by

**PC6 has no `USART1_DE` alternate function** on the STM32G071 — only
`TIM2_CH3` (AF2) and `TIM3_CH1` (AF1). USART1's hardware driver-enable exists
only on PA12 and PB3, neither of which reaches the THVD1410. `PLAN.md:261`
assumed "USART+DE"; the board cannot do it, so DE is asserted in software and
released in the transmission-complete interrupt, with a backstop timer so a
lost TC cannot leave the transceiver driving a shared bus.

**PA7 is `TIM1_CH1N`, the complement of PA8's `TIM1_CH1`.** PA7 is the 3V3A
rail monitor. If TIM1 is ever used for heater PWM, `CCER.CC1NE` must stay clear
or the timer will drive an analog input. v0 keeps TIM1's clock off entirely.

## Power: the probe needs its own supply

The Dragino RS485-LS gates its sensor rail — `+5V` is "only powered up before
each sampling" (`DRAGINO.md:194`, `AT+5VT=3000`). **The o2-probe must not be
powered from it.** The cell bias must never drop (15 minutes of settling every
time it does) and the heater will draw ~86 mA continuously in v1. Give the
probe a dedicated always-on 12 V supply and share only A/B and a common ground
with the node. This closes `PLAN.md:424` in the "dedicated PSU" direction.

## Bring-up

Flash from the **Nucleo-H503RB's** on-board ST-LINK in external-target mode
(remove the ST-LINK jumpers, use CN4) through a **TC2030-IDC-NL-6** cable to
J3. J3.1 is VTREF, not a supply — power the board from its 12 V feed with the
bench PSU current-limited to ~300 mA.

1. **Trim RV1 to `VREF_TRIM` = 2.500 V at TP4.** The LMP91000's 24 % bias step
   is the top step it offers, so 0.24 × 2.500 V = 600.0 mV exactly, and the
   SGX's ±10 mV window means VREF must land within about ±42 mV. 2.500 V sits
   at roughly 60 % of RV1's travel. **Firmware cannot do this** — it can only
   verify it, via `VREF_MON_MV`.
2. I²C scan → exactly `0x40`, `0x44`, `0x48`, `0x49`.
3. `VREF_MON_MV` should read ≈2500. It is measured on AIN1 against the
   ADS1119's *internal* 2.048 V reference, because a converter referenced to
   the thing it is checking cannot detect that thing drifting.
4. Cross-check `VA_MON_MV` (MCU ADC1_IN7 via VREFINT) against the ADS1119's
   AIN2 reading of the same node. They must agree.
5. Air point after ≥15 minutes settled: expect 0.07 ± 0.03 mA, i.e. ~490 mV
   across the 7 kΩ TIA. Write `0xCA11` to `CAL_TRIGGER`, then `0x5AC1` to
   `COMMIT`.
6. Nitrogen zero: < 0.4 %vol per DS-0637.
7. **Resolve the cell sign convention** from the air/N₂ pair — this closes
   `SCHEMATIC-REVIEW.md` M4.
8. Modbus at 9600 8E1: FC03 of `0x0000`+8; illegal-address and
   illegal-function exceptions; bad-CRC silence; broadcast; and DE turnaround
   on a scope at the transceiver pins.
9. End to end: set `AT+COMMAND3` on the Dragino node and confirm the block
   reaches ChirpStack.
10. **Known-bad calibration for the bias supervisor:** dip 3V3A momentarily
    with the MCU alive and confirm the firmware raises
    `AFE_CONFIG_MISMATCH`/`VA_LOW`, rewrites the AFE, and *restarts the
    settling timer*.

## Downstream work this creates

- **`tech/chirpstack/smt100-2probe-decoder.js` breaks.** It requires
  `(len − 3) % 6 == 0`; adding an 8-register block makes the payload 31 bytes
  and the whole uplink — including both SMT100s — fails to decode. It needs a
  layout-driven decoder, or the o2-probe needs its own node.
- `provision.py`: new device profile, codec, and an `uplink_interval` matching
  the node's real `AT+TDC`.
- `vm_ingest.py`: its `NODE_FIELDS` / `PROBE_RE` normalisation assumes the
  SMT100 and D23 shapes.
- Copy this register map into `../DESIGN.md`, which `PLAN.md:283` already
  claims holds it.
