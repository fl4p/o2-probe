# o2-probe Modbus Debugging Architecture & Friction Reduction Plan (Consolidated Final)

**Date:** 2026-09-09  
**Status:** Approved Architecture (Post Dual-Review: Codex gpt-5.6-sol & Claude opus)  
**Target Hardware:** o2-probe Rev A (STM32G071CBT7, 128 KiB Flash, 36 KiB SRAM)  
**Target Path:** `ee/hw/o2-probe/firmware`  
**Review Citations:** `codex-reviews/o2p-modbus-debug/review-last.md`, `claude-reviews/o2p-modbus-debug/review.log`

---

## 1. Problem Statement & Historical Context

The o2-probe is an RS-485 Modbus RTU slave on a multi-drop cable alongside Truebner SMT100 soil sensors. Once potted in polyurethane or epoxy, **J3 (SWD) is permanently inaccessible**. The only physical communications link is the 4-wire cable (RS-485 A/B, V+, GND).

Past bring-up incidents demonstrated the high friction of debugging over the wire:
1. **Trapped Heater Interlocks (`tools/o2p_thermal.py:27`):** The heater control loop evaluates 13 distinct interlocks (`O2P_HB_*` in `src/heater_ctl.h:44-67`). When `HEATER_DUTY` reads 0, host tools cannot diagnose why because the bitmask is computed in firmware but omitted from `regmap.h`.
2. **Black-Box AFE Silicon vs Software Configuration (`AFE-BRING-UP-POSTMORTEM.md`):** When U7's (LMP91000) control amp A1 failed on 2026-09-04, diagnosing whether the fault was software configuration (`TIACN`, `REFCN`, `MODECN`) vs dead silicon required hours of physical DMM probing on fine-pitch leads because AFE registers could not be queried or exercised over Modbus.
3. **Dead DRDY False Alarms (`PIN-IDENTITY-POSTMORTEM.md`):** An ADS1119 DRDY pin configuration defect caused an unnecessary ADC desolder/replacement because timeout states were unobservable over the bus.
4. **Crash Blindness:** When the probe resets unexpectedly or the Independent Watchdog (IWDG) triggers, `RESET_CAUSE` (`0x001A`) only reports "IWDG" or "SOFT". The program counter (`PC`), link register (`LR`), and crash site are lost.
5. **Tooling Gaps:** Tooling is rigid and specialized (`o2p_poll.py` for fixed tables, `o2p_thermal.py` for thermal steps, `o2p_update.py` for flashing). There is no interactive CLI to inspect, write, or stream arbitrary registers with symbolic names and unit conversions.

### 1.1 Scope Boundary: Digital vs Analog Fault Domains
This architecture addresses **digital, configuration, bus, and crash observability**. It does **not** and cannot replace analog board-level observability:
- As demonstrated during bench bring-up (`CELL-AFE-DEBUG.md` and `AFE-BRING-UP-POSTMORTEM.md:3.7`), analog interconnect defects (such as an open joint on U7 pin 11 `VREF_TRIM`, bridged electrodes, or crossed flying harness leads) leave digital I²C readback reporting healthy `0x0CCD` while a missing reference causes a railed VOUT to be miscalculated as a phantom ~238 µA overcurrent.
- Diagnosing analog interconnect faults requires physical probing (`CELL-AFE-DEBUG.md`) and PCB routing revisions (Rev B asks 3.7 and 3.9: monitoring `VREF_TRIM` and dedicated buffered electrode channels). The Modbus debug architecture provides the software tools to isolate digital and configuration causes before picking up the soldering iron.

---

## 2. System Architecture & Register Layout

All debug and diagnostic blocks are placed strictly in the free ground between the heater test block (`0x0060..0x0064`) and the update data window (`0x0080` in `src/update.h:90`). This 27-register window (`0x0065..0x007F`) is partitioned into volatile debug mailboxes:

```
   0x0010..0x002F : Diagnostic Block (expanded 30 -> 32 registers; adds HEATER_BLOCK, TIMING)
   0x0030..0x004A : Configuration Block (flash-backed)
   0x0050..0x005F : Firmware Update Control Block
   0x0060..0x0064 : Volatile Heater Test Block
   0x0065..0x006F : Memory Peek Mailbox (Burst window of 1-4 requested words, 11 registers)
   0x0070..0x0076 : Typed Sensor Diagnostic Mailbox (7 registers)
   0x0077..0x007F : Crash Context & Retention Mailbox (backed by TAMP->BKP0R..4R, 9 registers)
   0x0080..0x00FA : Firmware Update Data Window (123 registers)
   0x00FB..0x00FF : unassigned guard gap (exception 02)
   0x0100..0x0140 : Wide Peek Block (1-30 words per trigger, snapshotted, 65 registers) - added 2026-09-10, FW_VERSION 0x000D, see 3.4
```

---

## 3. Component A: Memory Peek Mailbox (`0x0065..0x006F`)

### 3.1 Design Principles & Cortex-M0+ Safety Constraints
1. **No Configurable BusFault:** On Cortex-M0+, any unaligned load (`addr & 3 != 0`) or read of an unmapped address or unclocked peripheral escalates immediately to a fatal `HardFault`.
2. **Destructive Reads Banned:** Reading peripheral registers like `ADC_DR` clears `EOC` (silently stealing conversions from the active sampler) and reading `USART_RDR`/`I2C_RXDR` clears FIFOs.
3. **Strict Memory Boundary:** `peek` is restricted **strictly to SRAM and Flash memory**, plus exact system constants:
   - **SRAM:** `0x20000000 .. 0x20008FFC` (36 KiB; `0x20008FFC` is the exact last 4-byte aligned word).
   - **Flash:** `0x08000000 .. 0x0801FFFC` (128 KiB; `0x0801FFFC` is the exact last 4-byte aligned word).
   - **Device Constants:** STM32G071 96-bit Unique Device ID (`0x1FFF7590`, `0x1FFF7594`, `0x1FFF7598`) and Flash Size Register (`0x1FFF75E0`). Unmapped option-byte holes are completely excluded.
4. **Burst Throughput (Resolving A-4):** Rather than 1 word per 2 Modbus round-trips (~25s to dump `g_rm`), the mailbox accepts a count of 1 to 4 words (up to 16 bytes), returning them into 8 contiguous read registers (`0x0068..0x006F`). The count is a **third register of the trigger write**, so the firmware validates it; a client that merely limits how many already-fetched words it prints has validated nothing. A burst must lie wholly inside the region it starts in, which is why the count is load-bearing rather than cosmetic: the UID is three words and the flash-size register is one, so neither is reachable by a fixed four-word burst.

### 3.2 Register Layout (`0x0065..0x006F`)

| Reg Address | Name | Type | Description |
|---|---|---|---|
| `0x0065` | `O2P_REG_PEEK_ADDR_HI` | R/W | Target physical address [31:16] |
| `0x0066` | `O2P_REG_PEEK_ADDR_LO` | R/W | Target physical address [15:0]; FC16 writes trigger execution |
| `0x0067` | `O2P_REG_PEEK_STATUS` | R/W | **R:** `0`=NONE, `1`=OK, `2`=ERR_RANGE, `3`=ERR_ALIGN. **W:** as the third register of a trigger write, the requested burst length, 1..4 |
| `0x0068` | `O2P_REG_PEEK_W0_HI` | RO | Word 0 [31:16]; `0xFFFF` if unexecuted |
| `0x0069` | `O2P_REG_PEEK_W0_LO` | RO | Word 0 [15:0]; `0xFFFF` if unexecuted |
| `0x006A` | `O2P_REG_PEEK_W1_HI` | RO | Word 1 [31:16] |
| `0x006B` | `O2P_REG_PEEK_W1_LO` | RO | Word 1 [15:0] |
| `0x006C` | `O2P_REG_PEEK_W2_HI` | RO | Word 2 [31:16] |
| `0x006D` | `O2P_REG_PEEK_W2_LO` | RO | Word 2 [15:0] |
| `0x006E` | `O2P_REG_PEEK_W3_HI` | RO | Word 3 [31:16] |
| `0x006F` | `O2P_REG_PEEK_W3_LO` | RO | Word 3 [15:0] |

### 3.3 Atomic Trigger & Dispatch Semantics
- **Atomic FC16 Requirement (Resolving A-1):** The write callback receives `(addr, count, in)`. Single-register writes to `0x0066` are rejected: the write is accepted and executed only if `addr == O2P_REG_PEEK_ADDR_HI` and `count` is 2 (address only, burst defaults to 4 words) or 3 (address plus a burst length of 1..4). Any other write length or offset touching the block, and any burst length outside 1..4, returns Modbus Exception `0x03` (`ILLEGAL_DATA_VALUE`). A refused trigger leaves the previous address, words and status untouched, so a malformed request cannot half-overwrite a result the operator is still reading.
- **Initialization (Resolving A-2):** In `o2p_regmap_init()`, all `PEEK_W*_HI/LO` registers are explicitly initialized to `0xFFFF` and `PEEK_STATUS` to `0` (`NONE`), avoiding deceptive zero-readbacks.

### 3.4 Wide Peek Block (`0x0100..0x0140`) — added 2026-09-10, `O2P_FW_VERSION` `0x000D`

**Why.** The mailbox above returns 16 bytes per trigger + read pair. Dumping a 68-byte `o2p_snapshot_t` took five pairs, and the sampler could publish between any two of them, so the struct that came back had never existed as a whole. The wide block serves up to 30 words (120 bytes) per trigger and **snapshots the burst at trigger time**, so one struct comes back consistent however many FC03s carry it home. The 4-word mailbox is unchanged on the wire and keeps working.

**Placement.** `0x0065..0x007F` is full and `0x0080..0x00FA` is the update data window (`src/update.h`). `0x00FB..0x00FF` is left empty as a guard, so an FC16 running off the end of an update block lands in nothing. Verified free on 2026-09-10 against `src/regmap.h`, `src/update.h`, the `o2p_regmap_read/write` dispatch, the bootloader's handlers (update blocks only) and `tools/check_regmap_docs.py`.

| Reg Address | Name | Type | Description |
|---|---|---|---|
| `0x0100` | `O2P_REG_PEEKW_ADDR_HI` | R/W | Trigger: target [31:16]. Reads the address held |
| `0x0101` | `O2P_REG_PEEKW_ADDR_LO` | R/W | Trigger: target [15:0] |
| `0x0102` | `O2P_REG_PEEKW_WORDS` | R/W | Trigger: burst length 1..30. Reads the length held |
| `0x0103` | `O2P_REG_PEEKW_STATUS` | RO | `0`=NONE, `1`=OK, `2`=ERR_RANGE, `3`=ERR_ALIGN (same codes and region rules as 3.1) |
| `0x0104` | `O2P_REG_PEEKW_SEQ` | RO | Executed triggers; skips 0 on wrap, so 0 = never triggered |
| `0x0105` | `O2P_REG_PEEKW_DATA` | RO | Word 0 [31:16], word 0 [15:0], word 1 [31:16] … through `0x0140`; `0xFFFF` if unexecuted |

**Semantics.**
- The trigger is exactly one FC16 of exactly 3 registers at `0x0100`. There is no 2-register form: no legacy master needs one, and a default length is a length the firmware never checked. Every other write touching the block, and a burst length of 0 or above 30, is exception `0x03` and changes nothing — address, length, status, sequence and data still describe the previous trigger, and no memory is dereferenced.
- A well-formed trigger always replaces the result, with the data or with `ERR_ALIGN`/`ERR_RANGE`. Words not filled read `0xFFFF`, including every word of a refused burst.
- The fit test counts the words left in the region (`(last - target) / 4`), so it cannot wrap for any target, including `0xFFFFFFFC`.
- The copy runs with `PRIMASK` saved, set and restored around the copy loop only. The trigger is served from the main loop, so what the mask adds is SysTick and USART1. USART1 runs without its FIFO, so the masked window must stay inside one character time: 95 µs at 115200 8E1. In the 2026-09-10 `env:o2probe` build, `peek_copy` masks for 15 instructions per word, two of them taken branches, so about 17 clock cycles. At 16 MHz with zero flash wait states (`src/mcu.c`) a 30-word copy is about 32 µs, roughly a third of a character. That is an **estimate from the disassembly, not measured on the board**, and it is also why the ceiling is not 60 words.
- A reader needing several FC03s reads `SEQ` with its first piece and again after its last. If it moved, the pieces came from different triggers.

**The ceiling, 30 words.** The whole block is one 65-register FC03, a 135-byte reply. Largest reply ADU per path, read from the code on 2026-09-10 (not measured on a cable): USB-RS485 dongle, SWD bridge mailbox and node USB serial relay 255 B; node LoRaWAN relay 242 B at DR4/DR5, 115 B at DR3, 51 B at DR0-DR2; Dragino `A8` about 46 B (manual's uplink figure, unverified). With 30 words the block is one read on every wired path and on the radio at DR4/DR5. A 60-word ceiling, the most a 125-register FC03 holds, would be one read on the wired paths only, and the radio drops an oversized reply rather than truncating it. 30 words also covers every struct worth dumping except `g_rm` itself, and it costs 120 bytes of SRAM.

**Compiled out** with the other debug blocks when `O2P_DEBUG_ENABLE=0`: every read and write at `0x0100..0x0140` is then exception `0x02`. A nodebug build reports the same `FW_VERSION`, so a master confirms the block exists from `BUILD_ID` bit 30 or from the exception, not from the version.

**Tests.** `test/test_logic/test_main.c` `test_peekw_*` drive the block against a fake memory that counts every dereference, so each refusal is checked by status and by zero dereferences. They cover every region's far tail at every burst length, monotonicity in burst length, address wrap, malformed triggers, the snapshot property and SEQ.

---

## 4. Component B: Exposing Trapped Telemetry in Regmap

### 4.1 Telemetry Exposure
- `0x002E`: `O2P_REG_HEATER_BLOCK` (u16 bitmask of `O2P_HB_*` from `src/heater_ctl.h:44-67`).
- `0x002F`: `O2P_REG_SAMPLER_TIMING_MS` (u16 cycle execution duration in ms).
- Expands `O2P_REG_DIAG_COUNT` from 30 to 32 registers (`0x0010..0x002F`).
- Bumps wire contract version `O2P_FW_VERSION` from `0x000A` to `0x000B`.
- `o2p_snapshot_t` in `src/regmap.h` grows 64 → 68 bytes (alignment 4, no padding).
- **Snapshot Sentinel Reset (Resolving B-2):** `o2p_snapshot_reset()` in `src/regmap.c` resets `heater_block` to `0xFFFF` (undefined/unmeasured) and `sampler_timing_ms` to `0xFFFF` to prevent publishing plausible 0s before the first measurement cycle runs.
- In `src/main.c:1192`, `hout.block` and the measured cycle execution time are copied into `g_rm.buf[next]`.

### 4.2 Comprehensive Lockstep Updates (Resolving B-1)
All of the following must be updated simultaneously in Phase 1:
1. `src/regmap.h`: Define `O2P_REG_HEATER_BLOCK = 0x002E`, `O2P_REG_SAMPLER_TIMING_MS = 0x002F`, `O2P_REG_DIAG_COUNT = 32u`, `O2P_FW_VERSION = 0x000Bu`.
2. `src/regmap.c`: Add cases to `read_diag()`, initialize in `o2p_snapshot_reset()`.
3. `src/main.c`: Publish `heater_block` and timing into live snapshot.
4. `tools/o2p_poll.py:53`: Update `DIAG_COUNT = 32`.
5. `tools/o2p_thermal.py:77`: Update `DIAG_COUNT = 32`.
6. `test/test_logic/test_main.c:5460,5466`: Update `O2P_FW_VERSION` test to `0x000Bu`, update `O2P_REG_DIAG_COUNT` test to `32u`, append v0.11 entry to wire changelog.
7. `FIRMWARE.md:807` & `../DESIGN.md`: Update declaration to "`0x0010`, 32 registers, read-only" so `tools/check_regmap_docs.py:76-84` passes.

### 4.3 LoRaWAN Network Polling Boundary (Resolving B-3)
- The farm node (`tech/node-prototype/src/poll.h:106,205`) polls 29 registers (0x0010..0x002C, up to `O2P_REG_T_AFE`), consuming 63 bytes of its 64-byte Modbus buffer.
- `0x002E` and `0x002F` (as well as `CE_MV` at `0x002D`) are **direct-bus / bench diagnostics only**. The farm node's poll count remains 29, keeping radio uplinks untouched and avoiding buffer overflow.

---

## 5. Component C: Typed Sensor Diagnostic Mailbox (`0x0070..0x0076`)

### 5.1 Architecture & Safety Guards
Generic raw register writes are rejected. A typed, non-blocking diagnostic interface operates during the idle window of the main cooperative loop between 1 Hz sampler cycles:
- **No Supervisor Collisions (Resolving C-1):** `phase_afe()` in `src/main.c:367-379` checks `o2p_lmp91000_verify()`. If an operator commands `OP_TRIM_LMP_TIACN`, the command automatically arms a volatile `afe_supervisor_override` (with a 60-second self-clearing timeout and a dedicated fault bit) so the supervisor does not immediately revert the register and trigger a 900 s settle restart.
- **Timing Budget & Watchdog Safety (Resolving C-6):** `i2c1.c:15` enforces a hard `O2P_I2C_TIMEOUT_MS = 25 ms` per transaction. The total execution time of any diagnostic command is bounded <30 ms, safely below the 2.7 s minimum IWDG margin.
- **Status Reporting (Resolving C-7):** Accurately distinguish `NACK` (part present, command refused) from `TIMEOUT` (bus lines dead/stuck).

### 5.2 Register Layout (`0x0070..0x0076`)

| Reg Address | Name | Type | Description |
|---|---|---|---|
| `0x0070` | `O2P_REG_DIAG_CMD` | R/W | Magic + Opcode: `0x5A00 | OPCODE` |
| `0x0071` | `O2P_REG_DIAG_PARAM` | R/W | Parameter (register address, channel, or trimmed value) |
| `0x0072` | `O2P_REG_DIAG_STATUS` | RO | `0`=NONE, `1`=PENDING, `2`=OK, `3`=ERR_OPCODE, `4`=ERR_NACK, `5`=ERR_TIMEOUT, `6`=ERR_BUSY, `7`=GPIO_NOT_SAMPLED, `8`=ERR_GPIO_UNCLOCKED, `9`=ERR_GPIO_NO_PIN (7..9 for `OP_READ_GPIO` only, `O2P_FW_VERSION` `0x000E`, see 5.4) |
| `0x0073` | `O2P_REG_DIAG_RDATA0` | RO | Result data byte 0/1 [31:16] |
| `0x0074` | `O2P_REG_DIAG_RDATA1` | RO | Result data byte 2/3 [15:0] |
| `0x0075` | `O2P_REG_DIAG_RDATA2` | RO | Result data byte 4/5 (for 6-byte SHT45 readouts) |
| `0x0076` | `O2P_REG_DIAG_CRC_STATUS` | RO | CRC validity mask for multi-byte sensors; for `OP_READ_GPIO`, the port's analog-pin mask instead (5.4) |

### 5.3 Supported Opcodes (Resolving C-2, C-3, C-4)
- `0x01`: `OP_READ_LMP_REG` — Read LMP91000 register (param = `0x00` STATUS, `0x01` LOCK, `0x10` TIACN, `0x11` REFCN, `0x12` MODECN).
- `0x02`: `OP_TRIM_LMP_TIACN` — Volatile bench trim of TIACN (temporarily suspends supervisor for 60s; raises `O2P_F_AFE_OVERRIDE`).
- `0x03`: `OP_READ_ADS_STATUS` — Read ADS1119 status byte (DRDY bit, conversion state).
- `0x04`: `OP_READ_ADS_CONFIG` — Read ADS1119 configuration register.
- `0x05`: `OP_READ_TMP_REG` — Read TMP117 register (param = `0x00`..`0x08`, plus `0x0F` DEVICE_ID).
- `0x06`: `OP_READ_SHT_SERIAL` — Read SHT45 32-bit electronic serial number into RDATA0/1.
- `0x07`: `OP_READ_SHT_SAMPLE` — Read single-shot SHT45 conversion; returns 16-bit T in RDATA0, 16-bit RH in RDATA1, CRC flags in `CRC_STATUS`.
- `0x08`: `OP_READ_GPIO` — Read-only snapshot of one MCU pin: mode, pull, output type, AF, output latch and level, plus its port's IDR, ODR and analog-pin mask (param = `port << 8 | pin`). Never reports a level for an analog-mode pin. Added 2026-09-10, `O2P_FW_VERSION` `0x000E`; see 5.4.

### 5.4 `OP_READ_GPIO` (`0x08`) — added 2026-09-10, `O2P_FW_VERSION` `0x000E`

**Why.** `../PIN-IDENTITY-POSTMORTEM.md`: PB1, the ADS1119 DRDY input, was never configured and sat in analog mode. IDR read 0 whatever the pin did, the conversion wait fell straight through, every channel read as the one before it, and a healthy ADC was replaced. One read of PB1's mode register would have said so. On a potted probe the bus is the only way to take that read.

**Strictly read-only, and not a generic register read.** The opcode loads `RCC_IOPENR` and, for the one validated port, `GPIOx_MODER`, `OTYPER`, `PUPDR`, `IDR`, `ODR` and the relevant `AFRL`/`AFRH`. It writes nothing and never enables a clock. The register seam (`src/gpio_hal.h`) has no write function to call, which is what keeps 5.1's rejection of generic writes intact.

**Parameter.** Port is 0 = A, 1 = B, 2 = C, 3 = D, 5 = F. 4 is where E would be, and the G071 has none: CMSIS `stm32g071xx.h` defines no `GPIOE`. Pin is 0..15. A one-register write with no parameter gets `ERR_OPCODE` and exception `0x03`, as `0x01` and `0x05` do.

| Status | Meaning | What was loaded | Data |
|---|---|---|---|
| `2` OK | the level was sampled | IOPENR + 6 port registers | everything below |
| `7` GPIO_NOT_SAMPLED | analog mode. ST RM0444 Rev 6, 7.3.13: "Read access to the input data register gets the value '0'", so there is no level | IOPENR + 6 port registers | configuration and port words real; `LEVEL` and `LEVEL_VALID` 0 |
| `8` ERR_GPIO_UNCLOCKED | the port's `RCC_IOPENR` bit is clear. `src/mcu.c` enables A, B and C only | IOPENR only | all 0 |
| `9` ERR_GPIO_NO_PIN | no such bonded pin: port 4 or above 5, pin above 15, or a pad not on the LQFP48 | nothing, RCC included | all 0 |

These are new codes rather than `ERR_NACK`/`ERR_TIMEOUT`, which mean something specific about an I²C part. `ERR_BUSY` still applies while an I²C opcode is queued, because that opcode owns the result registers until it runs.

**Packing.** `RDATA0`: bits 1..0 mode (MODER: 0 input, 1 output, 2 AF, 3 analog); bits 3..2 pull (PUPDR: 0 none, 1 up, 2 down, 3 reserved); bit 4 open-drain (OTYPER); bit 5 ODR, the latch; bit 6 LEVEL, the IDR bit; bits 11..8 AF number; bit 14 `LEVEL_VALID`, set only with OK; bit 15 `CONFIG_VALID`, set with OK or NOT_SAMPLED; other bits 0. Encodings are from RM0444 Rev 6 7.5.1, 7.5.2 and 7.5.4. `RDATA1` holds the port's IDR[15:0], `RDATA2` the port's ODR[15:0], and `CRC_STATUS` the port's analog mask (bit n = pin n in analog mode, so bit n of `RDATA1` is not a sample). A refusal leaves `RDATA0` at 0, not `0xFFFF`: `0xFFFF` would carry both VALID bits to a reader that ignored the status.

**Bonded pins.** PA0–PA15, PB0–PB15, PC6, PC7, PC13–PC15, PD0–PD3 and PF0–PF2, 44 in all. Source: ST DS12232 Rev 5 (June 2025), Table 12 "Pin assignment and description", LQFP48 column, read 2026-09-10. The local KiCad 10.0.5 library has no STM32G071CBTx symbol, so it was not used. Caveat, from note 5 of that table and RM0444 8.1.1: `SYSCFG_CFGR1` PA11_RMP/PA12_RMP can put PA9/PA10 on pins 33/34. This firmware never writes SYSCFG, so those pads are PA11/PA12.

**Where it executes: inside the FC16 handler, not deferred to `main.c`.** Opcodes `0x01..0x07` are I²C transactions of up to 25 ms on a bus the sampler owns between phases. `0x08` is seven register loads, the same class of work as the peek triggers, which are also served in the write. The consistency property that could argue for deferring already holds here. Every pin-mode writer is main-loop code that runs to completion before returning: I²C bus recovery re-runs `o2p_i2c1_init()` before it returns, and heater, ADC, AFE and RS-485 setup happen inside their own calls. The handler is reached from `o2p_modbus_poll()` in that same loop. No interrupt changes a pin mode. The one ISR that touches a pin at all, USART1 TC releasing DE and /RE through BSRR, is excluded by masking PRIMASK around the IOPENR check and the six loads. Serving it in the write also means the status is never PENDING: a port walk is 16 request pairs, not 16 sampler cycles. And the path a host test drives through `o2p_mb_dispatch()` is the whole path.

**Cost.** +568 B of flash on `env:o2probe` and `env:o2probe_revb`, 0 on `env:o2probe_nodebug` and `env:loader`. Measured 2026-09-10 by building the same tree with and without the change. Compiled out with the rest of the mailbox at `O2P_DEBUG_ENABLE=0`.

**Tests, host only.**
- `test/test_logic/test_main.c` `test_gpio_*` run against `src/gpio_hal_host.c`, a GPIO/RCC fake that counts every load and every load made outside the mask. Each refusal is checked by status and by loads not made, and all 65536 parameters are classified.
- `tools/test_o2p_cli_gpio.py` drives `o2p_cli.py diag gpio` through its real argument parser against `tools/gpio_oracle.c`, which is the real regmap, PDU layer and opcode.
- Every guard was broken deliberately in a scratch copy and caught: analog check, clock gate, bonded table (bypassed, one extra bit, port E admitted), level and ODR bit indices, dispatch range, the immediate branch, the interrupt mask, stale result registers. On the CLI side: level taken from the port IDR word or without `LEVEL_VALID`, drive warning, walk mask, read-back ownership.
- **Nothing has run on a probe.**

---

## 6. Component D: Crash Context & Retention Mailbox (`0x0077..0x007F`)

### 6.1 Hardware Realities on STM32G071
1. **IWDG Reset:** No early warning interrupt exists. On expiration, IWDG asserts a hard system reset.
   - *Strategy:* The 1 Hz sampler updates a cyclic breadcrumb (sampler phase, sequence number) in `TAMP->BKP3R` once per cycle. On boot, `mcu.c` identifies IWDG via `RCC_CSR.IWDGRSTF`, reporting reason `3` (IWDG) alongside the last breadcrumb.
2. **HardFault & Assert Capture:**
   - Stack Frame: ARMv6-M pushes 8 words: `R0`, `R1`, `R2`, `R3`, `R12`, `LR` (+0x14), `PC` (+0x18), `xPSR` (+0x1C).
   - Naked assembly shim checks `EXC_RETURN` bit 2 using branches (`MOV r0, lr; MOVS r1, #4; TST r0, r1; BEQ use_msp; MRS r0, psp; B check; use_msp: MRS r0, msp`).
   - Verifies `SP & 0x03 == 0` and `0x20000000 <= SP <= 0x20008FE0`.

### 6.2 5-Register Packing in `TAMP->BKP0R..4R` (Resolving D-2, D-3, D-4)
STM32G071 has exactly 5 32-bit backup registers. Packed allocation:
- `TAMP->BKP0R`: Magic Signature `0xC8A54001`.
- `TAMP->BKP1R`: Faulting Program Counter `PC` (32-bit).
- `TAMP->BKP2R`: Link Register `LR` return candidate (32-bit).
- `TAMP->BKP3R`: Low byte: Reason (`1`=HardFault, `2`=Assert, `3`=IWDG). High 24 bits: Assert line number or IWDG breadcrumb.
- `TAMP->BKP4R`: Exact `BUILD_ID` of the crashed firmware image (32-bit).

### 6.3 Atomicity & Reflash Safety (Resolving D-1, D-2)
- **Atomic Latch Sequence:**
  1. Write `0x00000000` to `TAMP->BKP0R` (invalidates any existing record).
  2. Write `PC` to `BKP1R`, `LR` to `BKP2R`, Reason/Breadcrumb to `BKP3R`, `O2P_BUILD_ID` to `BKP4R`.
  3. Write `0xC8A54001` to `TAMP->BKP0R` **last**.
  4. Trigger `NVIC_SystemReset()`.
- **Reflash Provenance Protection:** When `o2p_cli crash` runs, it compares `BKP4R` (the crashed build's ID) against the ELF file, preventing cross-build symbol misdecoding after a firmware update.
- **Record Clearing:** Writing `0` to `O2P_REG_CRASH_CLEAR` (`0x007F`) clears `TAMP->BKP0R`, acknowledging the crash record.

### 6.4 Register Layout (`0x0077..0x007F`)

| Reg Address | Name | Type | Description |
|---|---|---|---|
| `0x0077` | `O2P_REG_CRASH_REASON` | RO | `0`=None, `1`=HardFault, `2`=Assert, `3`=IWDG |
| `0x0078` | `O2P_REG_CRASH_PC_HI` | RO | Program Counter [31:16] |
| `0x0079` | `O2P_REG_CRASH_PC_LO` | RO | Program Counter [15:0] |
| `0x007A` | `O2P_REG_CRASH_LR_HI` | RO | Link Register [31:16] |
| `0x007B` | `O2P_REG_CRASH_LR_LO` | RO | Link Register [15:0] |
| `0x007C` | `O2P_REG_CRASH_DETAIL_HI` | RO | Assert line or IWDG breadcrumb [31:16] |
| `0x007D` | `O2P_REG_CRASH_DETAIL_LO` | RO | Assert line or IWDG breadcrumb [15:0] |
| `0x007E` | `O2P_REG_CRASH_BUILD_ID_HI` | RO | Crashed image BUILD_ID [31:16] |
| `0x007F` | `O2P_REG_CRASH_BUILD_ID_LO` | RO | Crashed image BUILD_ID [15:0] (Writing 0 clears record) |

---

## 7. Component E: Interactive Debugger CLI (`tools/o2p_cli.py`)

A unified Python debugger CLI built on the proven `Bus` and `SerialLink` infrastructure from `tools/o2p_update.py:396-458` (Resolving E-5):

```bash
# Read registers symbolically with units
python3 tools/o2p_cli.py --port /dev/cu.usbserial-0001 read O2_COMP T_TIP HEATER_BLOCK

# Write block atomically (protecting against the 1-cycle arming hazard, Resolving E-2)
python3 tools/o2p_cli.py --port ... htest --arm --duty 20.0 --sp 45.0

# Write persistent config and verify flash commit outcome (Resolving E-3)
python3 tools/o2p_cli.py --port ... config TIP_SETPOINT 45.0 --commit

# Burst memory peek with ELF symbol resolution and dirty-build warning (Resolving E-1)
python3 tools/o2p_cli.py --port ... peek g_rm --count 4

# Sensor diagnostics
python3 tools/o2p_cli.py --port ... diag lmp-read 0x10
python3 tools/o2p_cli.py --port ... diag tmp-read 0x0F

# Crash decode with addr2line (provenance matched against BKP4R, Resolving D-2)
python3 tools/o2p_cli.py --port ... crash
```

### 7.1 Multi-Drop Bus Collision Policy (Resolving E-4)
Because the Dragino node polls the bus periodically, `o2p_cli.py` enforces:
- A mandatory bus silence check before transmitting.
- Interactive commands use single-shot transactions with exponential backoff on frame collisions.
- Continuous streaming/watch modes require explicit confirmation (`--force-bus-master`) or pausing the node.

---

## 8. Implementation Roadmap

1. **Phase 1: Diagnostic Telemetry & Tooling Synchronization**
   - Update `src/regmap.h`, `src/regmap.c`, and `src/main.c` (expose `0x002E` and `0x002F`, bump to 32 registers, `O2P_FW_VERSION = 0x000Bu`, update `o2p_snapshot_reset()`).
   - Update `tools/o2p_poll.py:53`, `tools/o2p_thermal.py:77`.
   - Update `test/test_logic/test_main.c:5460,5466`.
   - Update `FIRMWARE.md` and `DESIGN.md` documentation lines.
   - Implement base `tools/o2p_cli.py` supporting symbolic read/write via `tools/o2p_update.py`'s `Bus` class.

2. **Phase 2: Crash Context Retention (`TAMP_BKPxR`)**
   - Pre-initialize `PWR_CR1.DBP` and `RTCAPBEN` in `src/mcu.c`.
   - Implement assembly/C `HardFault_Handler` with stack bounds checking, atomic magic invalidation, and 5-register packing.
   - Expose `0x0077..0x007F` crash registers in `src/regmap.c`.
   - Add `o2p_cli crash` decode command with `addr2line` and `BUILD_ID` verification.

3. **Phase 3: Burst Memory Peek Mailbox**
   - Implement `0x0065..0x006F` mailbox in `src/regmap.c` enforcing SRAM/Flash bounds and 4-byte alignment.
   - Implement atomic 2-register FC16 trigger check.
   - Add `o2p_cli peek <symbol>` with dynamic ELF parsing via `pyelftools`.

4. **Phase 4: Typed Sensor Diagnostic Mailbox**
   - Implement `0x0070..0x0076` mailbox and deferred execution in `src/main.c`.
   - Implement opcodes `OP_READ_LMP_REG`, `OP_TRIM_LMP_TIACN`, `OP_READ_ADS_STATUS`, `OP_READ_TMP_REG`, `OP_READ_SHT_*`.
   - Add `o2p_cli diag` subcommands.

---

## 9. Bench vs Field Deployment Policy (`O2P_DEBUG_ENABLE`)

Because memory peek is an unauthenticated read primitive on a shared multi-drop RS-485 bus, and once potted in polyurethane the firmware on J3 cannot be updated over SWD, the deployment policy is explicitly structured:

1. **Bench Bring-Up & Active Testing (`env:o2probe`):**
   - Default environment in `platformio.ini`.
   - Compiles with `-DO2P_DEBUG_ENABLE=1`.
   - All volatile debug mailboxes (`0x0065..0x007F`: peek, sensor diagnostics, crash context; and since 2026-09-10 the wide peek block `0x0100..0x0140`) are live.
   - Used for bench characterization, thermal step tests, sensor validation, and prototype field deployments where live wire debugging is required.

2. **Production Field Deployment (`env:o2probe_nodebug`):**
   - Explicit target in `platformio.ini`.
   - Compiles with `-DO2P_DEBUG_ENABLE=0`.
   - All debug mailboxes are compiled out; any read/write to `0x0065..0x007F` or `0x0100..0x0140` returns Modbus Exception `0x02` (`ILLEGAL_DATA_ADDRESS`).
   - HardFault handler falls back to a minimal `NVIC_SystemReset()`.
   - Saves 1,492 bytes of Flash and 64 bytes of RAM.
   - Mandatory target before potting production probes destined for unmonitored permanent burial.
