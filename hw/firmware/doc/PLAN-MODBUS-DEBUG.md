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
   0x0065..0x006F : Memory Peek Mailbox (Burst window up to 4 words, 11 registers)
   0x0070..0x0076 : Typed Sensor Diagnostic Mailbox (7 registers)
   0x0077..0x007F : Crash Context & Retention Mailbox (backed by TAMP->BKP0R..4R, 9 registers)
   0x0080..       : Firmware Update Data Window
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
4. **Burst Throughput (Resolving A-4):** Rather than 1 word per 2 Modbus round-trips (~25s to dump `g_rm`), the mailbox accepts a count of 1 to 4 words (up to 16 bytes), returning them into 8 contiguous read registers (`0x0068..0x006F`).

### 3.2 Register Layout (`0x0065..0x006F`)

| Reg Address | Name | Type | Description |
|---|---|---|---|
| `0x0065` | `O2P_REG_PEEK_ADDR_HI` | R/W | Target physical address [31:16] |
| `0x0066` | `O2P_REG_PEEK_ADDR_LO` | R/W | Target physical address [15:0]; FC16 writes trigger execution |
| `0x0067` | `O2P_REG_PEEK_STATUS` | RO | `0`=NONE, `1`=OK, `2`=ERR_RANGE, `3`=ERR_ALIGN |
| `0x0068` | `O2P_REG_PEEK_W0_HI` | RO | Word 0 [31:16]; `0xFFFF` if unexecuted |
| `0x0069` | `O2P_REG_PEEK_W0_LO` | RO | Word 0 [15:0]; `0xFFFF` if unexecuted |
| `0x006A` | `O2P_REG_PEEK_W1_HI` | RO | Word 1 [31:16] |
| `0x006B` | `O2P_REG_PEEK_W1_LO` | RO | Word 1 [15:0] |
| `0x006C` | `O2P_REG_PEEK_W2_HI` | RO | Word 2 [31:16] |
| `0x006D` | `O2P_REG_PEEK_W2_LO` | RO | Word 2 [15:0] |
| `0x006E` | `O2P_REG_PEEK_W3_HI` | RO | Word 3 [31:16] |
| `0x006F` | `O2P_REG_PEEK_W3_LO` | RO | Word 3 [15:0] |

### 3.3 Atomic Trigger & Dispatch Semantics
- **Atomic FC16 Requirement (Resolving A-1):** The write callback receives `(addr, count, in)`. Single-register writes to `0x0066` are rejected: if `addr == O2P_REG_PEEK_ADDR_HI && count == 2`, the write is accepted and executed; any other write length or offset touching `0x0065..0x0066` returns Modbus Exception `0x03` (`ILLEGAL_DATA_VALUE`).
- **Initialization (Resolving A-2):** In `o2p_regmap_init()`, all `PEEK_W*_HI/LO` registers are explicitly initialized to `0xFFFF` and `PEEK_STATUS` to `0` (`NONE`), avoiding deceptive zero-readbacks.

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
| `0x0072` | `O2P_REG_DIAG_STATUS` | RO | `0`=NONE, `1`=PENDING, `2`=OK, `3`=ERR_OPCODE, `4`=ERR_NACK, `5`=ERR_TIMEOUT, `6`=ERR_BUSY |
| `0x0073` | `O2P_REG_DIAG_RDATA0` | RO | Result data byte 0/1 [31:16] |
| `0x0074` | `O2P_REG_DIAG_RDATA1` | RO | Result data byte 2/3 [15:0] |
| `0x0075` | `O2P_REG_DIAG_RDATA2` | RO | Result data byte 4/5 (for 6-byte SHT45 readouts) |
| `0x0076` | `O2P_REG_DIAG_CRC_STATUS` | RO | CRC validity mask for multi-byte sensors |

### 5.3 Supported Opcodes (Resolving C-2, C-3, C-4)
- `0x01`: `OP_READ_LMP_REG` — Read LMP91000 register (param = `0x00` STATUS, `0x01` LOCK, `0x10` TIACN, `0x11` REFCN, `0x12` MODECN).
- `0x02`: `OP_TRIM_LMP_TIACN` — Volatile bench trim of TIACN (temporarily suspends supervisor for 60s; raises `O2P_F_AFE_OVERRIDE`).
- `0x03`: `OP_READ_ADS_STATUS` — Read ADS1119 status byte (DRDY bit, conversion state).
- `0x04`: `OP_READ_ADS_CONFIG` — Read ADS1119 configuration register.
- `0x05`: `OP_READ_TMP_REG` — Read TMP117 register (param = `0x00`..`0x08`, plus `0x0F` DEVICE_ID).
- `0x06`: `OP_READ_SHT_SERIAL` — Read SHT45 32-bit electronic serial number into RDATA0/1.
- `0x07`: `OP_READ_SHT_SAMPLE` — Read single-shot SHT45 conversion; returns 16-bit T in RDATA0, 16-bit RH in RDATA1, CRC flags in `CRC_STATUS`.

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
   - All volatile debug mailboxes (`0x0065..0x007F`: peek, sensor diagnostics, crash context) are live.
   - Used for bench characterization, thermal step tests, sensor validation, and prototype field deployments where live wire debugging is required.

2. **Production Field Deployment (`env:o2probe_nodebug`):**
   - Explicit target in `platformio.ini`.
   - Compiles with `-DO2P_DEBUG_ENABLE=0`.
   - All debug mailboxes are compiled out; any read/write to `0x0065..0x007F` returns Modbus Exception `0x02` (`ILLEGAL_DATA_ADDRESS`).
   - HardFault handler falls back to a minimal `NVIC_SystemReset()`.
   - Saves 1,492 bytes of Flash and 64 bytes of RAM.
   - Mandatory target before potting production probes destined for unmonitored permanent burial.
