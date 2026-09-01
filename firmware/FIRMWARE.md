# o2-probe Rev A firmware — v0

> **DEPLOYMENT PROHIBITED.** v0 is a bench and short-trial build. It has no
> membrane heater and no RS-485 bootloader. Do not bury a probe running it, and
> do not pot one. The reasons are in "What v0 does and does not do" below, and
> neither is a matter of polish.

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
configuration, and an independent watchdog (IWDG, /64 prescaler, reload 2047 — 4.096 s
nominal, roughly 2.7–6.5 s over the LSI's spread). The watchdog is fed only
while the sampler is completing cycles **and** the RS-485 driver is not stuck
enabled; nothing else in the firmware feeds it, because a safety interlock with
a second, unconditional key is not one.

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
(`tech/RS485-LS-SMT100.md:277`). Default slave address **3** — 1 and 2 are the two SMT100s.

Address **253** is answered as a discovery alias, the same convention the
SMT100 uses — but **reads only**. The SMT100 procedure re-addresses through 253
(`AT+CFGDEV=FD 06 00 04 00 01,1`), and that is exactly the operation that
writes to *every* device answering the alias if more than one is connected.
Reading a probe's own `SLAVE_ADDR` through 253 recovers the address just as
well, after which the write goes to the real unicast address: same capability,
no way to reconfigure the wrong device. A write to 253 returns exception 01.

### Provisioning the master

Three settings, and they are one unit — set and read back together.

```
AT+COMMAND3=03 03 00 00 00 08,1     # this probe, primary block, 8 registers
AT+DATACUT3=21,2,4~19               # keep ONLY the 16 data bytes
```

`AT+DATACUT3` is not optional. The FC03 reply is
`1 addr + 1 func + 1 bytecount + 16 data + 2 CRC = 21 bytes`, and without a
command-specific cut the node retains a range that shifts every following field
in the decoder (`DRAGINO.md:252`). The syntax is
`AT+DATACUTn=<len>,<mode>,<range>`, bytes numbered from 1.

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

### Diagnostic block — `0x0010`, 18 registers, read-only

`VREF_MON_MV`, `VA_MON_MV`, `VIN_MON_MV`, `AFE_VOUT_MV`, `DEW_MARGIN` (i16,
0.01 K), `PRESSURE_HPA` (0 — BMP390 is DNP), `UPTIME_HI/LO`, `FW_VERSION`,
`HW_REV`, `RESET_CAUSE`, `LMP_READBACK` (TIACN<<8 | REFCN as actually read),
`MB_CRC_ERRS`, `MB_FRAME_ERRS`, `I2C_ERRS`, `EXP_DATA` (`0xFFFF` — J2 is DNP),
then two that exist because supervision here is *sampled*, not continuous:

- `SETTLE_RESTARTS` `0x0020` — how many times the 15-minute settling timer has
  been restarted. The rail and AFE checks run once a second, so a 3V3A
  excursion that begins and recovers between samples is missed entirely: the
  readback afterwards is correct and the rail reads normal, while the cell in
  fact needs another 15 minutes. A counter climbing without a matching fault
  ever appearing in an uplink is the signature of exactly that.
- `SAMPLE_SEQ` `0x0021` — increments on every published cycle. Frozen across
  two polls means the sampler has stalled, even though every other register
  still holds a plausible value.

### Config block — `0x0030`, 16 registers, read/write, flash-backed

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
| `CAL_TRIGGER` `0x003D` | `0xCA11` | take an air-point calibration this cycle |
| `COMMIT` `0x003E` | `0x5AC1` | erase and rewrite the config flash page |

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
| 12 | `CAL_DEFAULT` | **`O2_COMP` only — see below** |
| 13/14 | `EXP_PRESENT` / `EXP_FAIL` | no |
| 15 | `HEATER_DISABLED` | no (always set in v0) |

Two exceptions that are easy to "tidy" into wrongness, so they are also
enforced by `_Static_assert` in `src/faults.c`:

- **`TEMP_OVER` does not invalidate.** `PLAN.md:211-228` (decision 2026-08-27)
  deliberately runs the cell above its 60 °C rating because the thermophilic
  phase is the phase the probe exists to observe. Above 60 °C the reading is an
  *extrapolation* and is flagged as one. This overrides
  `compostlab/research/COMPOST-O2.md` §6.
- **`CAL_DEFAULT` invalidates `O2_COMP` but not `O2_RAW`.** The two channels
  fail for different reasons. `O2_RAW` is a physical measurement — microamps
  through a known transimpedance — and is meaningful with no calibration at
  all; it is also the channel the bench uses to resolve the open sign-convention
  gate. `O2_COMP` is that current divided by a constant nobody has measured:
  the datasheet nominal spans 0.04–0.10 mA, so a substituted value can be 43 %
  out, and 12 %vol against a true 21 %vol is indistinguishable from a real and
  alarming result. That is not lower-confidence data, it is an unknown scale
  factor wearing the units of a measurement.

A related rule with the same shape: if a non-zero temperature coefficient is
configured but no temperature is available, `O2_COMP` is invalid rather than
silently computed with a zero correction and presented as compensated.

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

1. **Trim RV1 to `VREF_TRIM` = 2.500 V at TP4** — then **measure the actual
   bias.** The LMP91000's 24 % step is the top one it offers, so nominally
   0.24 × 2.500 V = 600.0 mV, and the SGX's ±10 mV window implies VREF within
   about ±42 mV. 2.500 V sits at roughly 60 % of RV1's travel. **Firmware
   cannot do this** — it can only verify VREF via `VREF_MON_MV`.

   **But trimming TP4 does not prove the cell sees −600 ± 10 mV.** The
   LMP91000's bias programming carries its own error — `PLAN.md:174` records
   ±2 % of VREF, i.e. ±50 mV, which alone is five times the cell's window — so
   the nominal product of two nominal numbers is not an acceptance test.
   Measure the real V(WE) − V(RE) at the fitted cell and adjust RV1 against
   *that*, over supply and temperature. Note `CELL_RE` deliberately has no test
   point or via (it is a guarded trace), so this measurement is taken at the
   cell pins. An overbiased cell drifts or degrades, and no firmware can undo
   it once the probe is potted.
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

## Known limitations of v0

- **Bias supervision is sampled, not continuous.** The rail and AFE checks run
  at 1 Hz, so a short 3V3A excursion between samples is missed. `SETTLE_RESTARTS`
  makes the sampled-ness visible; a continuous analog watchdog on PA7, or an
  external supervisor, is the real fix and is v1 work.
- **No `t1.5` inter-character check.** Framing uses only the hardware receiver
  timeout for the 3.5-character inter-frame silence. A malformed frame with an
  internal 1.5–3.5 character gap is accepted at the framing layer and rejected
  only if the CRC happens to fail. With a single well-behaved Dragino master
  this is low risk; it is a deviation from the RTU specification all the same,
  and it is counted in `MB_CRC_ERRS` when it bites.
- **BOR level and option bytes are not configured by firmware, deliberately.**
  A slow brownout above an unsuitable BOR threshold can corrupt a flash commit,
  so the level must be *chosen and audited* before deployment — but programming
  option bytes from application firmware is permanent enough that it belongs in
  a deliberate production step, not a boot path. Keep RDP at level 0 through
  first-article and bootloader validation; **never RDP 2**, which would remove
  every recovery path from a device whose SWD connector is already inside the
  potting.
- **Every reset costs 15 minutes of settling.** An earlier version skipped the
  wait when the reset was not a power-cycle and the LMP91000's registers read
  back intact. That inference does not hold: the readback proves the AFE's
  *digital* configuration survived, not that `VREF_TRIM` stayed present. An EMI
  event that resets the MCU can equally collapse the reference buffer for a few
  milliseconds, with VREF back long before the readback runs. Fifteen minutes
  of honest invalidity, at most once per reset, beats an unknown interval of
  confident wrong numbers from a buried instrument.
- **The unsigned diagnostic channels use `0xFFFF` for "not measured", not 0.**
  Zero is a possible real reading for every one of them — 0 mV on a collapsed
  rail, an all-zero LMP91000 register image after a reset. `PRESSURE_HPA` is
  the deliberate exception: its 0 states that the BMP390 footprint is not
  populated, which is a fact about the board rather than a failed measurement.
- **A request older than 400 ms is dropped rather than answered.** The master's
  Modbus timeout is about 1 s, and a reply sent after it has given up does not
  merely go unheard — it lands on top of whatever transaction the master
  started next and corrupts another slave's answer. One lost poll is cheaper
  than a frame injected into someone else's exchange.
- **The SHT45 de-creep pulse is scheduled and its readings are masked.** The
  pulse runs on the configured interval (default 8 h) as well as on demand, and
  the chamber channels read invalid for 30 s afterwards. That window is a
  conservative guess, not a measurement: **it is unverified on this part in
  this chamber**, and the bench run that establishes it is the same one that
  would turn the slow-recovery signature into the `DEW_SUSPECT` classifier
  `PLAN.md:312` asks for.
- **The TMP117's safety configuration is latched and re-verified.** A part
  whose therm-mode alert failed to program still answers temperature reads
  perfectly, so nothing else would notice the hardware heater cutoff was not
  armed. `o2p_tmp117_safety_armed()` is the gate **v1's heater loop must
  refuse to energise without**.

## Downstream work this creates

Done, in `~/dev/ha/farming/tech`:

- ~~`smt100-2probe-decoder.js` breaks on a 31-byte payload~~ — replaced by
  `chirpstack/rs485-ls-decoder.js`, which selects its layout from the node's
  `AT+PAYVER` and then checks the length exactly. `AT+PAYVER=3` means
  SMT100@1 + SMT100@2 + o2-probe@3. Exact-length checking is the point: a node
  that loses `AT+COMMAND3` emits 15 bytes, which the old inferred-N rule would
  have decoded as a healthy two-probe frame with the oxygen channel simply
  absent. `chirpstack/test_rs485_ls_decoder.js` covers that case and the
  no-reply case.
- ~~`provision.py`~~ — points at the new codec. The profile *name* is its lookup
  key and was deliberately not changed; renaming it would orphan the existing
  profile. `uplink_interval` already matches the node's `AT+TDC=300000`.
- ~~`vm_ingest.py`~~ — `o2_<slave>_*` fields route to a `gas` measurement rather
  than joining the SMT100s under `soil`; they are a gas instrument on the same
  bus, not a third soil probe.
- ~~Copy this register map into `../DESIGN.md`~~ — done, under "Modbus register
  map".

Still open:

- **The node has never been configured.** `AT+COMMAND3` / `AT+DATACUT3` /
  `AT+CMDDL3` / `AT+PAYVER=3` are written down in
  `tech/RS485-LS-SMT100.md` ("Adding the o2-probe") but not sent. Deploy the
  codec first and set `AT+PAYVER` last, so the codec is never behind the node.
- A dedicated always-on 12 V supply on the probe cable.
