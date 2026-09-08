# o2-probe Rev A firmware — v1

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
pio test -e native      # portable logic, 91 cases
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

v1 adds the **membrane-heater control loop** — but ships it **switched off**.

`DESIGN.md:47-51` and `FAB-READINESS.md:61` both state the TMP117 ALERT path
"is not credited as an autonomous overtemperature cutoff until firmware
configures and fault-tests the TMP117". Firmware now *configures* it, and
`o2p_tmp117_safety_armed()` latches whether that took. It has **not been
fault-tested**, because nothing in this firmware has ever executed on silicon.
Until that bench test is run and recorded, nothing may put 1 W into the
membrane carrier.

So the heater is off at **two independent switches**, and enabling it is never
a single edit:

| Switch | Where | Default |
|---|---|---|
| `O2P_HEATER_ENABLE` | compile flag in `platformio.ini` | `0` — TIM1's clock stays gated off, PA8 is a plain output held low |
| `HEATER_MAX_DUTY` `0x0035` | flash-backed configuration | `0` — the loop refuses with `CONFIG_OFF` |

The full enable procedure and its bench prerequisites are at the top of
`src/heater.h` and in [The heater loop](#the-heater-loop-v1) below.

**The cost of that, stated plainly:** the SGX cell is rated 15–90 %RH
*continuous, non-condensing*, and the heater is the only thing keeping the
membrane above the dew point of saturated pore gas. **With the heater switched
off this is a bench and short-trial build.** A probe left in a pile for weeks
with the loop disabled will wet its membrane. `DEW_MARGIN` and the `DEW_SUSPECT` fault exist so that is observed
rather than discovered afterwards.

Also absent: the **RS-485 application bootloader**. `SCHEMATIC-REVIEW.md` M2 is
emphatic that it must be installed *before potting*, because J3 is not exposed
through the enclosure and the STM32 ROM bootloader is not proven to work
through the half-duplex DE line. **Do not pot a probe running this firmware.**

## Field updates: why the v2 bootloader is wired

The question this settles, because it will be asked again: once a probe is
potted and buried, can it be reflashed through infrastructure that is already
there — the Dragino's LoRaWAN link, or its BLE console — instead of a wired
bootloader that has to be installed *before* the epoxy goes on?

No, and the reason is narrower than "there is no wireless path". There is one.
It is 40 bytes wide, it takes about **65 hours**, and it cannot create the
thing it would need to talk to.

The arithmetic below is for this image: `firmware.bin` is **23,916 bytes**,
18.8 % of the 126,976-byte application space. (PlatformIO's banner reports the
same percentage on a different quantity: it counts 23,912 bytes of
`text`+`data` and not the inter-section padding that a flash image still has to
carry over the wire. Use the image size, not the banner, for any transport
estimate.) A differential scheme would
do better, but not by the order of magnitude that would change the answer.

### The wireless path that does exist: `A8`, and its 40-byte ceiling

`AT+CFGDEV` puts one arbitrary RS-485 frame on the bus from the AT console
(`tech/RS485-LS-SMT100.md:254`), and it **does** have a documented downlink
equivalent — [Dragino's RS485-LB/LS manual §3.3.2][cfgdev], which is this
node's own model:

    A8 MM NN XX XX .. XX YY
      MM  1 = node appends CRC-16/MODBUS, 0 = no CRC
      NN  length of the RS-485 command
      XX  the RS-485 command, NN bytes
      YY  how many bytes of the reply to uplink; 0 = execute, send nothing

So a downlink *can* reach this probe's Modbus parser, and `YY` even gives a
return path — the reply comes back on the next uplink, which means a block
could genuinely be acknowledged rather than fired blind. An earlier version of
this section said no such channel was established to exist and that the probe
would have no way to NAK a bad page. Both were wrong.

What kills it is the ceiling. The same section caps `AT+CFGDEV` at **40 bytes**:

| | |
|---|---|
| CFGDEV command budget | 40 B |
| less FC16 framing (addr, FC, start, count, byte count, CRC) | −9 B |
| whole 16-bit registers | 30 B of image per downlink |
| downlinks for 23,916 bytes | **798** |
| at `AT+TDC` = 300 s | **66.5 h** |

Nearly three days, and that is the *floor*: no retries, no erase waits, no
handshake. (Whether the 40 bytes counts the CRC the node appends when `MM=1`
is not spelled out; if it does not, the budget is 32 bytes of image and the
figure gets worse, not better.)

**The radio is not the binding constraint, the command is.** An `A8` frame is
4 + 40 = 44 application bytes, which fits even DR0/SF12's 51-byte maximum, so
data rate never enters into it. For reference: EU868 allows 51 application
bytes at DR0 and 242 at DR5 — the 242 assuming no repeater and empty `FOpts`,
222 otherwise — but no data rate lets one downlink carry more than 40 bytes of
CFGDEV. Airtime is likewise not the limit: 798 SF12 downlinks of 57 PHY bytes
is 2,630 ms each, 2,099 s of transmitter time (0.58 h), which under continuous
10 % duty-cycle pacing on the 869.4–869.65 MHz band is about 5.8 h elapsed —
well inside the 66 h the cadence already costs.

That cadence is the other half. A Class A node opens receive windows only
after its own uplink, and RX1 and RX2 are two windows of **one** opportunity —
the server picks one, so RX2 is an alternate scheduling slot (869.525 MHz,
DR0 by default), *not* an automatic retry when RX1 is missed. One downlink per
uplink therefore means one per `AT+TDC`, here 300 s, unless `FPending` makes
the node uplink again sooner; whether RS485-LS v1.3.1 acts on `FPending` is
**unverified** — Dragino's manual documents no behaviour for it.

[cfgdev]: https://wiki.dragino.com/docs/LoRaWAN-End-Node/io-controllers-sensor-nodes/rs485-lb/#332-rs485-debug-command-atcfgdev

### BLE reaches the bus too, and still is not an answer

BLE is the Dragino's AT console (`tech/dragino/DRAGINO.md:93`), and
`AT+CFGDEV` is available from it, so BLE can put frames on the RS-485 cable
just as the downlink can. The categorical claim that it "never crosses the
cable to this MCU", in an earlier version of this section, was wrong.

It fails on access rather than on principle. BLE is only advertised after a
power-on, reset, or button press (`tech/dragino/DRAGINO.md:108`) — all of
which want hands on a node that is, by assumption, buried; and the console has
one unexplained command rejection correlated with radio activity, whose
truncation mechanism was conjectured and never isolated
(`tech/dragino/DRAGINO.md:131`). Dragino's own "OTA over BLE"
(`tech/dragino/DRAGINO.md:350`) updates the *node's* firmware, not anything
across the RS-485 cable.

### Wired RS-485, which is what v2 will use

The cable that carries Modbus carries the image at line rate. At 9600 8E1 a
byte is 11 bit times, so 872.7 B/s and **27.0 s** for the whole image; at
38400, **6.7 s**. Line time only — framing, page-erase waits and per-block
acks are on top. But a transport with that much headroom can acknowledge and
retry every block, and it is reachable from the same A/B pair a technician
already has to touch.

### Why the gate is at potting

Not because wireless is slow. **Because none of these paths can install a
bootloader that is not already there.** `A8` and the BLE console both deliver
bytes to whatever is listening on the probe's RS-485 port; if the firmware in
flash has no self-programming code, there is nothing to receive an image, and
an STM32G071 cannot be made to write its own flash by a Modbus frame it does
not implement. The ROM bootloader is the only alternative, and it is not
proven to work through the half-duplex DE line.

So `SCHEMATIC-REVIEW.md` M2's deadline stands, on a corrected premise: wireless
is a plausible transport *to an existing updater*, at about three days per
image, and no transport at all *to a probe that never got one*. J3 is not
exposed through the enclosure. An application bootloader missing when the epoxy
goes on cannot be added afterwards.

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
| 5 | `HEATER_DUTY` | u16 | 0.01 %, the duty actually applied | — |
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

### Config block — `0x0030`, 20 registers, read/write, flash-backed

`SLAVE_ADDR`, `BAUD_CODE`, `PARITY_CODE`, `RH_SETPOINT`, `DT_MAX_K`,
`HEATER_MAX_DUTY`, `HEATER_PWM_HZ`, `CAL_AIR_NA_HI/LO`, `CAL_TEMP_C100`,
`TEMPCO_PPM_K`, `SHT_PULSE_H`, `SHT_PULSE_TRIG`, `CAL_TRIGGER`, `COMMIT`,
`CONFIG_CRC` (read-only), plus four appended registers:

| Reg | | |
|---|---|---|
| `0x0040` | `HEATER_KP` | proportional gain, 0.01 units |
| `0x0041` | `HEATER_KI` | integral gain, 0.01 units per second |
| `0x0042` | `CAL_ZERO_NA_HI` | cell zero current, i32 nA, **signed**, default 0 |
| `0x0043` | `CAL_ZERO_NA_LO` | |

`CAL_ZERO_NA` is appended rather than placed beside `CAL_AIR_NA` at
`0x0037/0x0038` where it belongs logically. **No existing address moved**, and
none may: `AT+COMMAND` frames name literal addresses, and a renumbered map is a
node that reads the wrong register without saying so.

Write it as one FC16 of both words. A single-word write cannot pass the bound
(below), which is the mechanism that forces `HI` and `LO` to arrive together —
the same trick `CAL_AIR_NA` uses. Both are covered by `CONFIG_CRC`, so a master
can confirm the probe is running the calibration it wrote.

The gains are registers on purpose. The plant is unmeasured — the thermal path
is an engineering bound, not a measurement — so they will need tuning against a
real pile, and the alternative to a register write is a full firmware transfer
through a bootloader that does not exist yet. Bounded at 100.00 each: `kp` of
100 already saturates the duty clamp on a 1 %RH error, and a 1 W heater against
a membrane is not the place to discover a fat-fingered write. Zero is legal —
`kp = 0` with `ki > 0` is a pure integrator, reasonable on a slow thermal
plant, and both zero simply means the loop never asks for heat.

A multi-register write is validated against a copy and committed all-or-nothing
— a frame that sets a legal address and an illegal baud rate changes neither.
Serial changes take effect only after the response has left the wire.

### Calibration: what the three constants mean

The cell is logarithmic, not linear (`DS-0637` Issue 1):

```
S = I0 + K * (1 + alpha*(T - T0)) * ln( 1 / (1 - C) )
```

| Constant | Register | How it is obtained |
|---|---|---|
| `K` | derived from `CAL_AIR_NA` **net of** `CAL_ZERO_NA` | air point, `CAL_TRIGGER` or written directly |
| `I0` | `CAL_ZERO_NA` `0x0042/0x0043` | nitrogen point, fitted on the bench and written |
| `alpha` | `TEMPCO_PPM_K` `0x003A` | temperature sweep; **0 = no compensation**, which is what ships |
| `T0` | `CAL_TEMP_C100` `0x0039` | the temperature the air point was taken at |

Three things about that law are easy to get wrong, and the firmware is explicit
about each.

**The zero is not a rounding term.** DS-0637 rates the zero signal at
`< 0.4 %vol O2 (20 C)` — **1706 nA** at Issue 2's nominal 100 µA cell and
**2218 nA** at the top of the population, which is 8× the
LMP91000's internal-zero error and 100× a converter LSB. Folded into the air
point instead of subtracted it stops being an offset and becomes a *slope*
error across the whole low-O₂ range, which is precisely where the compost
decision lives: 0.37 vs 0.20 %O₂ at the 2 %O₂ point.

**The tempco scales `K`, not the measured current.** Those are the same
operation only while `I0` is zero. With a zero present, applying the gain to
`S` hands the zero a temperature dependence nobody has measured — worth
0.54 %O₂ at the 2 % point for a worst-case in-window zero under the
membrane-regime `alpha`. Pinned by
`test_tempco_scales_k_and_not_the_measured_current`.

**The zero itself is not temperature-corrected.** DS-0637 publishes no
zero-vs-temperature figure and no sweep has measured one, so it is a constant.
An invented coefficient would be worse than none, because the number coming out
would look compensated. Same reasoning as `TEMPCO_PPM_K`'s default of 0.

`CAL_ZERO_NA` is **signed**, and deliberately so in both directions:
`SCHEMATIC-REVIEW.md` M4 leaves the SGX polarity convention open, and the
electronic offsets it competes with have no fixed sign either. It is bounded to
**±5000 nA** — 2.9× the nominal cell's zero and 2.25× the worst in-spec one, so an aged part is still
calibratable, while an air point mistakenly written into the zero registers, or
a byte-swapped word, is refused rather than stored. An out-of-window value
returns exception 03 and changes nothing; a zero at or above the air point can
only be reached by bypassing that bound, and the conversion returns
`UNEVALUABLE` rather than a number if it ever is.

### The honest accuracy claim

Numbers from [`../O2-CORRECTION-MODEL-BUDGET.md`](../O2-CORRECTION-MODEL-BUDGET.md),
which propagates part datasheets through this exact law. They are an estimate,
not a measurement — **no calibration data exists yet.**

| Calibration actually performed | at air | at 2–5 %O₂ |
|---|---|---|
| Air point only, `alpha` = 0 — **what ships today** | **±1.3 %O₂** | **±0.3–0.5 %O₂** |
| N₂ + air at 5 temperatures, fit weighted by reference uncertainty | ±0.05 %O₂ (1σ) | ±0.05 %O₂ (1σ) |

**Read the first row as "at 55 °C", not as a bound.** It is a point on a curve
that keeps rising: the same model gives **+1.47 %O₂ at 60 °C**, and the 2–5 %
figure reaches 0.58 %O₂ at 65 °C — outside the stated 0.3–0.5. Quote these with
the temperature attached or not at all. The second row is **predicted parameter
uncertainty under the assumptions of §3**, not a measured accuracy, and it
excludes model closure — including the fact that the vendor curve behind
`alpha` is visibly not a straight line (§5). Neither row is a specification.

The 1.3 %O₂ is not resolution and it is not the converter — the digitiser is
two orders of magnitude away from mattering. It is the uncompensated tempco at
55 °C. A temperature sweep is the single change that collapses it, and until
one is run, `TEMPCO_PPM_K = 0` is correctly labelled *no compensation applied*
rather than a compensation.

**A fitted `alpha` is a LUMPED cell + AFE coefficient.** The LMP91000 datasheet
(`SNAS506I`) specifies no TIA-gain tempco and no internal-zero-divider drift —
only `TcVOS_RW`, which moves the bias and not the gain. So an isothermal
whole-probe sweep fits `alpha_cell + alpha_AFE` and cannot separate them. For a
probe whose cell and AFE sit on one board that lumped number is the *right* one
to use in the field — **except when the heater is running**, which is exactly
the condition that splits the two temperatures. Do not tune the heater loop
around an assumed `alpha`, and if the measured `alpha` is large enough for
heater gradients to matter, the split-temperature pass in §5 of the budget doc
is a prerequisite to enabling the loop.

On top of calibration uncertainty, and larger than it, sit four terms no O₂-only
calibration can see: wet- versus dry-basis definition (up to 3.5 %O₂ at 55 °C if
confused), barometric weather (±0.45 %O₂ at air — `PRESSURE_HPA` reads 0 because
the BMP390 is DNP, so this is uncorrectable on-board), CO₂ enhancement
(+0.2–0.3 %O₂ at compost concentrations) and cell ageing (±1 %O₂ at air over
life, re-spanned by the field air point). Decide wet or dry basis *before* the
calibration: the tempco fit and a vapour correction both key off temperature and
will otherwise absorb each other.

### Guard review, in writing — the zero bound and the corrected law

The checklist every guard in this repository has to answer, for `CAL_ZERO_NA`
and for `o2p_fraction_from_current()`.

1. **Unevaluable input.** There is no path from a constant that cannot be
   trusted to a number. `cal_air_na <= 0` is `UNEVALUABLE` as before; a net air
   point outside the window two plausible constants can reach is `UNEVALUABLE`;
   the tempco-gain window is unchanged and still `UNEVALUABLE` outside it; the
   `isfinite` checks stand. `UNEVALUABLE` writes **no** value to `*out_c`, and
   `o2p_encode_percent()` maps everything but `OK` to `0xFFFF`. The specific
   trap here is a *tiny* K rather than a negative one: at a net of 1 nA every
   real current saturates the `exp()` and `C` comes out as exactly 1.0000 —
   finite, positive, and encodable. That is why the floor is a floor and not a
   sign test.
2. **Monotonicity.** `test_zero_bound_rejects_the_far_tail_not_just_near_misses`
   checks both edges, both signs, a swapped-halves value 10⁴ out, and
   `INT32_MIN`/`INT32_MAX`, then sweeps outward geometrically — the verdict
   never comes back to PASS. `test_monotonic_across_the_whole_range_with_a_zero`
   re-runs the current sweep with the zero and a tempco live, down past the zero
   into the negative-fraction region, and ends below zero rather than folding
   back into a plausible mid-range reading.
3. **Preconditions.** The zero is a *precondition of the air point*, not an
   unrelated register: K is `(air − zero)`, so `o2p_calibrate_air()` checks the
   stored zero as well as its own reading and refuses the calibration outright
   if the zero is out of window. The conversion re-derives the net from the
   struct it was handed rather than trusting that it came through a checked
   path. `_Static_assert` in `o2.h` proves that widening the zero bound to reach
   the air-point floor fails the build instead of the field.
4. **Source of truth.** `src/regmap.h` is the map; `tools/check_regmap_docs.py`
   fails the build if this document disagrees with it. The bound itself is
   derived from DS-0637's `< 0.4 %vol O2` and stated as such at its definition;
   `O2P_NET_AIR_MIN/MAX_NA` are *derived from the two bounds*, not a third magic
   number, so they cannot drift out of agreement with them.
5. **Persistence.** A refused zero leaves the previous value standing — it is
   validated against a copy of the config and committed all-or-nothing, so a
   half-written 32-bit value cannot be stored. A refused air point likewise
   leaves the old constants in place. Nothing caches a "verified" flag: the
   bounds are re-evaluated on every write and the net is re-derived on every
   conversion.
6. **Provenance.** An accepted calibration write takes effect on the *next
   conversion*, not at `COMMIT`: `cal_from_config()` builds the constants fresh
   every cycle. Until 2026-09-07 a cached copy was refreshed only at boot and
   after `COMMIT`, so a master could verify a new calibration by `CONFIG_CRC`
   and still be reading numbers produced by the old one — the worst shape a
   provenance bug can take, since the check meant to catch it reported success.
   Found by the 2026-09-07 Codex review. `CONFIG_CRC` covers `cal_zero_na`, so
   a master can tell *which configuration the probe holds*
   (`test_zero_point_is_covered_by_the_config_crc`).

   **What `CONFIG_CRC` does not tell it is which configuration produced the
   sample sitting beside it.** The 2026-09-08 review showed the sample carries
   no config identity: `CONFIG_CRC` is computed live at read time, so a
   configuration write landing between `PH_O2` and `PH_PUBLISH` publishes a
   value converted under the old constants next to a CRC describing the new
   ones. Two of the three ways in were closed —
   the self-inflicted one, where `finish_o2()` converted the sample and *then*
   applied a requested air point (the air point is now taken **before** the
   conversion, so the published value and the readback agree), and a combined
   `CAL_TRIGGER`+`COMMIT` frame that used to persist the pre-calibration image
   (the commit now waits for the calibration). The remaining window is an
   asynchronous Modbus write inside one cycle, and it is **open**: closing it
   needs a config CRC or epoch latched into the sample, which costs a
   diagnostic register. Do not read a matching `CONFIG_CRC` as proof that the
   adjacent `O2_COMP` was produced under it.

   `COMMIT` still does what it says — persist to flash — with one caveat the
   same review raised: `o2p_config_store()`'s return is discarded in `main.c`,
   so a *failed* flash write is silent. The fault word has no bit left to
   report it (all 16 are allocated), so this needs a decision, not a patch. `CAL_DEFAULT` still marks a
   substituted air point, and **`CAL_ZERO_DEFAULT` (bit 13) now marks a missing
   zero point**, so a probe running on air alone says so on every uplink instead
   of publishing `O2_COMP` with a clean fault word. It invalidates nothing — the
   error it announces is bounded at 0.4 %O₂, see the fault-word section. Expect
   it set fleet-wide until a zero point exists; that is the honest state, not a
   defect in the flag.

   **What is still not reported, and cannot be from this file:** the raise
   condition lives in `main.c`'s sampler, which is *not* in the native build's
   `build_src_filter`, so no host test observes the bit being set — only its
   semantics are covered (`test_missing_zero_point_flags_without_invalidating`,
   `test_zero_fault_bit_does_not_collide_with_its_neighbours`). That gap is
   structural and predates this change: no sampler logic is host-tested.
7. **Known-bad calibration.** Constructed and observed, not argued.
   `test_written_zero_point_must_also_be_plausible` writes the byte-swapped
   −1200 nA (−77 856 769 nA) and an air point into the zero registers and
   watches both bounce with exception 03 and no state change.
   `test_zero_at_or_above_the_air_point_is_unevaluable` builds nets of 0, −20000
   and **1 nA** and watches each refuse. For the tempco move,
   `test_tempco_scales_k_and_not_the_measured_current` was run against a
   deliberately re-broken `o2.c` carrying the old placement, which returned
   1.4566 %O₂ for a true 2.0000 % and failed the assertion — the test pins the
   semantics rather than describing them.
8. **Fix versus mute.** Neither change silences anything. The zero term alters
   the published number by up to 0.4 %O₂ at the low end; moving the tempco to K
   alters it by up to 0.54 %O₂ at 2 %O₂ under the membrane-regime `alpha`. The
   accuracy statement above got *worse*, not better: `±1.3 %O₂ at air` is now
   written down where it was previously not stated at all.

**Runtime cost.** One extra 64-bit subtract, two compares and one float
multiply per 1 Hz conversion on a Cortex-M0+; the `int64` subtraction is a
two-instruction sequence, not a library call. Measured, by building `HEAD` and
this change side by side: `firmware.bin` 23,516 → 23,916 bytes, **+400**, which
is 0.3 % of the application space and adds ~1.1 h to the wireless-transport
estimate above. Nothing is in the Modbus path.

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
| 8 | `HEATER_RUNAWAY` | no — latched, see below |
| 9 | `TEMP_OVER` | **no — see below** |
| 10 | `DEW_SUSPECT` | no |
| 11 | `ADC_RANGE` | **yes** |
| 12 | `CAL_DEFAULT` | **`O2_COMP` only — see below** |
| 13 | `CAL_ZERO_DEFAULT` | **no — see below** |
| 14 | `EXP_FAIL` | no |
| 15 | `HEATER_DISABLED` | no — set whenever the loop is not driving, for any reason |

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
  the datasheet nominal spans 0.07–0.13 mA, so a substituted value can be 30 %
  out, and 15.2 %vol against a true 21 %vol is indistinguishable from a real and
  alarming result. That is not lower-confidence data, it is an unknown scale
  factor wearing the units of a measurement.

- **`CAL_ZERO_DEFAULT` invalidates nothing.** It has the shape of `TEMP_OVER`,
  not of `CAL_DEFAULT`, and the difference is quantitative. A missing *air*
  point leaves the scale factor unknown to ±30 %; a missing *zero* point leaves
  a bounded offset — DS-0637's `Zero Signal (20 °C) < 0.4 %vol O₂` — so the
  reading is wrong by at most 0.4 %O₂, and least where the pile is most
  interesting. Flag it, do not discard it. Making it invalidate would blank the
  compensated channel on every probe built so far, since none has a zero point
  and there is no bench yet to take one on — which is how a guard gets switched
  off rather than satisfied. `../O2-CORRECTION-MODEL-BUDGET.md` has the
  propagation.

  **A stored `CAL_ZERO_NA` of 0 is read as "never taken", not as "measured as
  zero".** The register cannot distinguish them, and this is the direction the
  ambiguity must fail in: a bench that genuinely measures 0 nA gets a flag it
  can explain, whereas the other choice silently certifies every uncalibrated
  probe. One ADC LSB is 10.9 nA, so a bench holding a real zero point has a
  value to write.

  **Bit 13 was `EXP_PRESENT`.** J2 is DNP on Rev A, no firmware ever wrote the
  bit, and the presence answer is already published in `EXP_DATA`
  (`0xFFFF` = absent), so it carried nothing. The fault word is otherwise full.
  Note that `tech/chirpstack/codec/_o2_regs.js` independently retired bits
  13/14 on 2026-09-04 and named them `ads_drdy_stuck` / `ads_config_lost` —
  names no firmware implements. The decoder's bit 13 now matches this file;
  **bit 14's disagreement is unresolved** and belongs to whoever lands the ADS
  supervision.

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

Flash over SWD with any ST-LINK. Power the probe from its own 12 V feed, bench
PSU current-limited to ~300 mA.

**Not from the Nucleo-H503RB.** That board is MB1814 with an STLINK-V3EC, and
UM3121 §8.1 offers exactly two options, *both* aimed at the board's own STM32:
the embedded STLINK-V3EC (JP1 off, the default), or an external debug tool on
the CN4 STDC14/MIPI10 connector (JP1 fitted [1-2], which puts the STLINK-V3EC
into reset so it "no longer drives the embedded STM32"). There is no documented
mode in which the embedded ST-LINK programs an *external* target: the classic
Nucleo-64 arrangement of pulling two CN2 jumpers and using CN4 as an ST-LINK
output does not exist here, and JP1 is a single jumper pointing the other way.

CN4 is not a usable substitute either — UM3121 Table 6 describes its pins as
*target* SWDIO/SWCLK/NRST, i.e. the same net the on-board STM32H503 sits on.
Hanging a second target off it puts two debug ports on one SWD bus, which has
no addressing to separate them.

So use a standalone probe. Two that work:

- **Seeed XIAO Debug Mate** (ESP32-S3 DAPLink, CMSIS-DAP). Set
  `upload_protocol = cmsis-dap` and `debug_tool = cmsis-dap`; the board JSON
  already lists that protocol and `openocd_target` is `stm32g0x`.
- **Any ST-LINK/V2 clone**, which needs no configuration change at all.

**Debug Mate pin identification.** Its silkscreen legend has two rows per
header: the GREEN label is the Debug Mate's own signal, the BLUE label is the
XIAO socket name for that same physical pin. The debug group is therefore
scattered across both headers, and the two SWD signals are on *different* ones:

Identify pins by the BLUE label, never by counting positions: the front and
back legends mirror each other, so "third from the left" means different pins
depending on which face you are reading.

| Debug Mate (green) | same pin, blue label | header | to J3 pad |
|---|---|---|---|
| `SWDIO` | `D4` (`SDA`) | lower | **2** |
| `SWDCLK` | `D9` (`MISO`) | upper | **4** |
| `GND` | `D8` (`SCK`) | upper | **5** |
| `RST/EN` | `D5` (`SCL`) | lower | **3** |

The two SWD signals are on different headers, so the bundle splits.

Use the GREEN `GND` beside `SWDCLK`, not the blue one in the power group - it is
the debug connector's own return, adjacent to the clock.

**Leave `3V3` and `5V` alone.** Those are in the blue row: the XIAO socket's
power rails, not a `VTref` sense input, so neither belongs on the probe, which
runs from its own 12 V feed. The two are not symmetric, per Seeed's schematic
sheet 6: `5V` is `XIAO_5V+`, switched from `VBUS_5V` and genuinely driven,
while blue `3V3` is `X_3V3` — the rail a *plugged-in XIAO* would supply, which
an empty socket does not drive. So connecting `3V3` would not in fact fight the
probe's LDO, as an earlier version of this section claimed; it is simply
pointless, and it is one solder joint away from `5V`, which would. Both boards
are 3.3 V logic, so nothing is lost by omitting both.

`RST/EN` sits inside the green debug group alongside `SWDIO`/`SWDCLK`/`MTMS`/
`MTCK`, which is what identifies it as the DAPLink *target* reset rather than
the ESP32-S3's own enable. Wiring it gives connect-under-reset. If an attach
ever fails without it, the manual equivalent is to ground J3 pad 3 by hand,
start the upload, and release.

### Getting SWD onto J3 without a Tag-Connect cable

There is no TC2030-IDC-NL-6 cable here, so **solder leads to the J3 pads**.
That is a reasonable permanent choice rather than a compromise: no probe can be
potted until the RS-485 bootloader exists, so the first article is a bench mule
either way.

The footprint is six **0.787 mm circular pads on a uniform 1.27 mm grid**, with
0.48 mm of bare laminate between pad edges — comfortable with 30 AWG Kynar
wire-wrap wire. Five of the six are worth wiring:

| Pad | Net | |
|---|---|---|
| 1 | `3V3D` | VTREF — the ST-LINK's level sense |
| 2 | `SWDIO` | |
| 3 | `NRST` | for connect-under-reset |
| 4 | `SWCLK` / BOOT0 | |
| 5 | `GND` | |
| 6 | "SWO" (PB3) | **skip it** — Cortex-M0+ has no ITM, so there is no trace to carry |

Three things that are easy to get wrong:

- **Use an alignment hole as strain relief.** The three 0.99 mm NPTH holes at
  ±2.54 mm are the only mechanical anchor available: these are `-NL` pads, with
  no legs. Thread the bundle through one. A 0.787 mm pad lifts easily, and
  lifting SWDIO or SWCLK removes the only programming interface the board has.
- **VTREF is a sense input, not a supply.** Power the board from 12 V and let
  the debugger read 3.3 V through pad 1. Do not back-feed the probe.
- **Keep the SWCLK lead short.** It is the same net as BOOT0 with only a 100 kΩ
  pull-down, so a long dangling wire is an antenna on a boot-mode strap.

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
5. Air point after ≥15 minutes settled: expect 0.1 ± 0.03 mA (DS-0637 Issue 2),
   i.e. ~700 mV across the 7 kΩ TIA — 490 mV was Issue 1's 0.07 mA. Internal
   zero sits at 1.675 V, so the output swings down to ~0.98 V, and the 30 %
   overload point (152 µA, 1.06 V) still clears ground with margin. Write
   `0xCA11` to `CAL_TRIGGER`, then `0x5AC1` to `COMMIT`.
6. Nitrogen zero: < 0.4 %vol per DS-0637 — with the Issue 2 nominal that is up
   to 1706 nA. Write the measured value to `CAL_ZERO_NA_HI/LO` (FC16, both
   halves in one frame) to clear `CAL_ZERO_DEFAULT`.
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


## The heater loop (v1)

### What is controlled, and why it is not a temperature

`PLAN.md:294-297`, verbatim: *"primary loop regulates measured chamber RH
(SHT45, hold ~85-90 % — the actual controlled quantity: condensation margin +
the cell's 90 % continuous-RH spec)."*

Regulating humidity rather than a fixed temperature rise is the whole design.
`PLAN.md:300-302`: *"+2 K gives only ~90-91 % RH on saturated gas; 85 % needs
~3.1-3.7 K at 40-65 °C — design the thermal path for a 0-4 K ΔT range, not a
fixed 2 K."* A fixed offset that is right at 40 °C is wrong at 65 °C, and the
pile spans both. `DT_MAX_K` (`0x0034`, default 4.00 K) is that envelope as a
clamp, not as a setpoint.

Heating dries the chamber at constant absolute humidity, so the loop is
positive-acting: measured RH above setpoint asks for more duty. A sign error
here would drive the loop away from its target, so the direction is pinned by
`test_duty_is_monotonic_in_humidity`.

Structure: ~1 Hz PI with conditional-integration anti-windup and a duty clamp,
~1 kHz PWM on TIM1_CH1, exactly as `PLAN.md:311` specifies. The control law
lives in `src/heater_ctl.c` with no registers and no CMSIS, so it is
host-tested; `src/heater.c` owns the timer.

### Interlocks

Every one is independent and independently tested. **Any** of them means duty
zero for that cycle.

| Interlock | Fires when |
|---|---|
| `NOT_COMPILED` | built with `O2P_HEATER_ENABLE=0` — this build |
| `CONFIG_OFF` | `HEATER_MAX_DUTY` is zero — this build |
| `SAFETY` | `o2p_tmp117_safety_armed()` false: the therm-mode alert is not programmed |
| `NO_RH` | no fresh SHT45 humidity — **including during the de-creep pulse mask** |
| `NO_TIP` | no fresh TMP117 reading |
| `NO_CHAMBER` | no chamber temperature, so the ΔT clamp cannot be enforced |
| `TIP_LIMIT` | tip ≥ 80.00 °C (firmware limit, releases at 75.00 °C) |
| `DT_LIMIT` | tip − chamber ≥ `DT_MAX_K` (releases 0.5 K below) |
| `RUNAWAY` | latched: heat with no command |
| `SUPPLY` | `VA_LOW` or `VIN_LOW` — heating adds ~86 mA to a rail already out of tolerance |
| `PIN_INTEGRITY` | `TIM1.CCER.CC1NE` set, or PA7 no longer analog |
| `STALE` | no duty command within 5 s — the sampler stalled |

Two of these deserve their reasoning spelled out.

**The firmware tip limit is 80 °C while the TMP117's therm-mode alert is at
85 °C.** Deliberately different: firmware backs off first and the hardware
clamp is the backstop for the case where firmware is the thing that failed.
Two mechanisms at the same threshold would be one mechanism.

**`SETTLING` and the O₂-chain faults do NOT block heating**, and that is a
judgement worth disagreeing with. The 15-minute settle is about the cell's
electrochemical bias; the heater's job is keeping the membrane dry. Blocking
the loop on `SETTLING` would leave the membrane unprotected for 15 minutes
after every reset — the one thing v0's disabled heater already does badly. Only
the *supply* faults block, because heat is a load. If a reviewer prefers the
stricter reading, the change is one line in `main.c`'s `supply_ok`.

### Runaway detection

Fault bit 8 was defined in v0 and never set. It now latches when the tip runs
hotter than the loop is ever allowed to make it **while duty is commanded
zero**, sustained for 60 s: `dT > DT_MAX_K + 2.00 K`.

It cannot false-positive on a cold start, because at power-on tip and chamber
are the same temperature. The margin is measured above `DT_MAX_K` rather than
above zero because a small standing ΔT is expected by design —
`PLAN.md:304-307` warns that *"U10 measures PCB copper, but the 5 g ABS cell
couples via three pins and gas"*, so the two sensors disagree normally.

**It latches until reset.** A FET conducting unasked is a hardware failure, and
the firmware that has just discovered it cannot control the heater is not what
should decide the fault has cleared. Auto-clearing would re-arm 1 W against the
membrane every time the tip cooled. The cost is that a false positive disables
heating until the next reset.

Detection is skipped entirely when `O2P_HEATER_ENABLE=0`: PA8 is then a plain
output held low, so a hot tip says something about the environment or the
sensors, not about a stuck FET — and a fault bit nobody can act on is noise.

### Tuning parameters

| Parameter | Register | Default | Status |
|---|---|---|---|
| RH setpoint | `RH_SETPOINT` `0x0033` | 85.00 %RH | from `PLAN.md:294-296` |
| ΔT clamp | `DT_MAX_K` `0x0034` | 4.00 K | from `PLAN.md:300-302` |
| Duty ceiling | `HEATER_MAX_DUTY` `0x0035` | **0** (off) | second enable switch |
| PWM frequency | `HEATER_PWM_HZ` `0x0036` | 1000 Hz | `PLAN.md:311`; **edge unverified** |
| Proportional gain | *compile-time* `O2P_HEATER_KP_X100_DEFAULT` | 2.00 | **unverified** |
| Integral gain | *compile-time* `O2P_HEATER_KI_X100_DEFAULT` | 0.10 /s | **unverified** |

**The gains are placeholders, not design values.** The plant gain is unknown:
`THERMAL-BARRIER.md:5-9` gives 98 K/W (interval 91–102, engineering bound
90–110 K/W) for the *bare-PCB transverse* path, and `:18` says plainly that the
estimate *"is for PCB conduction only. It is not the ring-to-ambient"* path —
which is the one that actually sets how many kelvin a watt buys in wet pore
gas. Nothing here is derived from a measured plant. They are deliberately slow:
a loop that cannot be tuned before it is potted should err towards sluggish
rather than towards overshooting into a cell rated to 60 °C.

They are **compile-time constants, and they should not be.** See
[Known limitations](#known-limitations) — this is the one follow-up that
matters.

### Enabling it

Every prerequisite is bench work on a real board. None has been done.

1. **TMP117 alert fault test.** The whole hardware-cutoff argument is this one
   measurement — see the known-bad calibration in the guard checklist below.
2. **Gate edge and PWM frequency.** `SCHEMATIC-REVIEW.md` H3's closure makes
   this *"a firmware and thermal bench requirement"*: R28 is 10 kΩ into the
   AO3400A gate against R29's 100 kΩ pulldown, so Vgs reaches only ~3.0 V and
   the edge is tens of microseconds — at 1 kHz roughly 3 % of the period.
   Scope the gate, and check FET dissipation at **intermediate duty**, not only
   0 % and 100 %.
3. **Ring and resistors safe at 100 % duty at the 15 V worst case** — 1.61 W,
   not the 1.03 W of the 12 V nominal case.
4. **Tune the gains** against the real thermal path.
5. **Controlled dew-point crossings**, per `FAB-READINESS.md`'s open gates.

Then: set `-DO2P_HEATER_ENABLE=1`, and write a non-zero `HEATER_MAX_DUTY`.
`pio run -e o2probe_heater_enabled` exists purely to prove that path still
compiles; it is never flashed.

### Guard review, in writing

The checklist every guard in this repository has to answer, for this loop.

1. **Unevaluable input.** Missing RH, missing tip, missing chamber, an
   unarmed TMP117, a failed pin-integrity check and a stale command are each
   an interlock, not a default. There is no path from "cannot evaluate" to a
   non-zero duty. `test_unevaluable_input_is_off_not_midrange` sweeps every
   combination of missing sensor.
2. **Monotonicity.** As the chamber gets wetter — the input worsening — the
   demanded duty never falls, and at or below setpoint it is exactly zero, not
   a residual. `test_duty_is_monotonic_in_humidity` walks 0–100 %RH.
3. **Preconditions.** The loop is invoked from `cycle_publish()`, after every
   phase has run, so it sees the rail, AFE, temperature and humidity results
   together. A loop running earlier could command heat into a supply already
   known to be sagging. `o2p_heater_apply()` re-checks pin integrity itself
   rather than trusting its caller.
4. **Source of truth.** The duty published in `0x0005` is read back from
   `o2p_heater_duty_x100()` — what the hardware layer actually applied — not
   the controller's request. If `heater.c` refuses a command, the register
   shows the refusal.
5. **Persistence.** The runaway latch survives until reset and is never
   cleared by a subsequent healthy cycle. The integrator is **zeroed** on any
   interlock rather than frozen, so a cleared fault restarts from
   proportional-only instead of slamming to whatever it had wound up to.
6. **Provenance.** `HEATER_DISABLED` (bit 15) is set whenever the loop is not
   driving, for any reason. Every number in the tuning table above is marked
   measured or unverified; the gains and the PWM edge are unverified.
7. **Known-bad calibration — the bench procedure.** Construct the failure and
   watch the guard fire:
   - Power the board from its 12 V feed, current-limited to ~300 mA. Scope
     probe on `HEATER_LOW` (the RH1/RH2–Q2 junction, reachable at the
     2512 pads); second channel on `HEATER_GATE` at R28.
   - Enable the heater and command a mid duty. Confirm `HEATER_LOW` switches
     and `HEATER_DUTY` `0x0005` reads back what you asked for.
   - Write `TLOW` then `THIGH` on the TMP117 (`0x0003`, `0x0002`) to a limit
     **below** the present tip temperature, over the same I²C bus.
   - **Expect: `HEATER_GATE` pulled low by the open-drain ALERT within one
     TMP117 conversion, and `HEATER_LOW` at +12 V — heater off — while the MCU
     is still commanding PWM.** That contention is bounded to ~0.33 mA by R28
     per `SCHEMATIC-REVIEW.md` H3's closure; confirm on the gate trace that it
     is held below the AO3400A's threshold.
   - Restore `THIGH` and confirm the heater resumes only after the tip falls
     below the hysteresis point.
   - Record the result in `FAB-READINESS.md`. Until this passes,
     `O2P_HEATER_ENABLE` stays 0.
8. **Fix versus mute.** Every interlock changes the commanded duty; none
   merely suppresses a report. `HEATER_RUNAWAY` and `HEATER_DISABLED` reach
   the uplink, so a probe that refuses to heat says so rather than looking
   healthy and cold.

**Runtime cost.** One float PI evaluation per second on a 16 MHz Cortex-M0+ with
no FPU — soft-float, microseconds, once per 1 Hz cycle. The interlock
evaluation is integer comparisons. Nothing here is in the Modbus path, and no
phase became blocking: the decision runs inside the existing publish step.

## Known limitations

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
- **A v2 board reflashed to v3 loses its entire stored configuration.**
  `CONFIG_LAYOUT_VERSION` **has** been bumped (2 → 3) for `cal_zero_na`, so an
  older record is refused rather than mis-parsed — the right call, and the
  defaults it falls back to put `HEATER_MAX_DUTY` at 0, the only direction a
  layout change may fail in. But the fallback is total: air calibration, slave
  address, baud and parity all revert together, so **a probe that had been
  re-addressed stops answering the poll it was configured for and presents as a
  dead probe rather than a reset one.** No migration path was written. This is
  acceptable only while no v2 unit is deployed; write the migration, or plan to
  re-provision every probe on the bench, before the first field unit ships.
  (An earlier revision of this bullet said the bump was still outstanding and
  that the CRC would catch an old record "with probability 65535/65536". The
  bump is done, and that CRC claim was wrong — see `config_flash.c`.)
- **`../DESIGN.md` still documents the config block as 18 registers.**
  `tools/check_regmap_docs.py` fails the `o2probe` build on this, deliberately:
  the map is a wire contract and a stale prose copy is how someone writes an
  `AT+COMMAND` against an address that moved. `DESIGN.md` was outside this
  change's file boundary, so **the target build does not currently pass from a
  clean tree** — it needs one heading edit (`0x0030`, 20 registers) and the two
  `CAL_ZERO_NA` rows. The compile itself is clean; verified by running the build
  with the checker temporarily narrowed to `FIRMWARE.md`.
- **There is no `ZERO_TRIGGER` to match `CAL_TRIGGER`.** The air point can be
  taken by the probe itself because it can be told it is in air; nothing on the
  probe can tell nitrogen from a dead cell, an unplugged cell, or a collapsed
  bias, and an automatic zero would happily store any of them. The fitted `I0`
  is written to `0x0042/0x0043` by whoever ran the bench. If a trigger is ever
  added it needs a plausibility test the air point does not: "the reading is
  small" is exactly what a broken cell also looks like.
- **The zero has no temperature coefficient**, because none has been measured.
  The 5-temperature N₂ + air campaign in `../O2-CORRECTION-MODEL-BUDGET.md` §7
  produces one for free; until it is run, `I0` is a constant and the firmware
  says so rather than extrapolating.
- **The heater gains are compile-time constants, and they should not be.** The
  plant gain cannot be known until the loop runs on hardware, and once a probe
  is potted there is no SWD to reflash it through — so tuning has to happen
  over the bus or it cannot happen at all. Two holding registers
  (`HEATER_KP`, `HEATER_KI`) would fix this. They were implemented and then
  **reverted**: adding them changes the register map, whose prose copy lives in
  `../DESIGN.md`, outside the boundary this work was scoped to. It is one
  commit of `regmap.h` plus a `DESIGN.md` table row, and it should be done
  before anyone tunes a loop on a board they intend to pot.
- **The refusal reason is not published.** `HEATER_DISABLED` says the loop is
  not driving; it does not say which of the twelve interlocks fired. That mask
  exists in firmware (`O2P_HB_*`) and a `HEATER_BLOCK` diagnostic register
  would surface it, but it is the same map change as above. Until then,
  diagnosing a refusal from a buried probe means reasoning from the other
  fault bits.
- **The PWM edge is unverified.** `SCHEMATIC-REVIEW.md` H3's closure makes
  gate-edge and frequency verification an explicit firmware and thermal bench
  requirement, and no scope has been near this board. 1000 Hz is
  `PLAN.md:311`'s figure, not a measured choice.
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
