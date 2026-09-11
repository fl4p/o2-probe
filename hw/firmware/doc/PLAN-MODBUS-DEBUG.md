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
   - **SRAM:** `0x20000000 .. 0x20008FFC` (36 KiB; `0x20008FFC` is the exact last 4-byte aligned word). See §3.5 for the SRAM parity gate that narrows this further when the option bit is set.
   - **Flash:** `0x08000000 .. 0x08010FFC` — the loader (pages 0–7) and the run slot (pages 8–33) only, **not** the whole 128 KiB. §3.6 is why. `0x08010FFC` is `O2P_APP_BASE + O2P_APP_BYTES - 4`, the run slot's last aligned word.
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
| `0x0103` | `O2P_REG_PEEKW_STATUS` | RO | `0`=NONE, `1`=OK, `2`=ERR_RANGE, `3`=ERR_ALIGN, `4`=ERR_PARITY (same codes and region rules as 3.1; `4` since `0x000F`, see 3.5) |
| `0x0104` | `O2P_REG_PEEKW_SEQ` | RO | Executed triggers; skips 0 on wrap, so 0 = never triggered |
| `0x0105` | `O2P_REG_PEEKW_DATA` | RO | Word 0 [31:16], word 0 [15:0], word 1 [31:16] … through `0x0140`; `0xFFFF` if unexecuted |

**Semantics.**
- The trigger is exactly one FC16 of exactly 3 registers at `0x0100`. There is no 2-register form: no legacy master needs one, and a default length is a length the firmware never checked. Every other write touching the block, and a burst length of 0 or above 30, is exception `0x03` and changes nothing — address, length, status, sequence and data still describe the previous trigger, and no memory is dereferenced.
- A well-formed trigger always replaces the result, with the data or with `ERR_ALIGN`/`ERR_RANGE`. Words not filled read `0xFFFF`, including every word of a refused burst.
- The fit test counts the words left in the region (`(last - target) / 4`), so it cannot wrap for any target, including `0xFFFFFFFC`.
- The copy runs with `PRIMASK` saved, set and restored around the copy loop only. The trigger is served from the main loop, so what the mask adds is SysTick and USART1. USART1 runs without its FIFO, so the masked window must stay inside one character time: 95 µs at 115200 8E1. In the 2026-09-10 `env:o2probe` build, `peek_copy` masks for 15 instructions per word, two of them taken branches, so about 17 clock cycles. At 16 MHz with zero flash wait states (`src/mcu.c`) a 30-word copy is about 32 µs, roughly a third of a character. That is an **estimate from the disassembly, not measured on the board**, and it is also why the ceiling is not 60 words.
- A reader needing several FC03s reads `SEQ` with its first piece and again after its last. If it moved, the pieces came from different triggers.

**The ceiling, 30 words.** The whole block is one 65-register FC03, a 135-byte reply. Largest reply ADU per path, read from the code on 2026-09-10 (not measured on a cable): USB-RS485 dongle, SWD bridge mailbox and node USB serial relay 255 B; node LoRaWAN relay 227 B at DR4/DR5, 100 B at DR3, 36 B at DR0-DR2; Dragino `A8` about 46 B (manual's uplink figure, unverified). The radio figures were first written as 242/115/51, which is RadioLib 7.7.1's EU868 `payloadLenMax` (`LoRaWANBands.cpp:25`). They are 15 B lower because the node uplinks the reply ADU raw (`reply_push()` in node-prototype `main.cpp` `relay()`), and RadioLib's `getMaxPayloadLen()` subtracts the FOpts the MAC layer has pending (`LoRaWAN.cpp:3785-3805`), up to `RADIOLIB_LORAWAN_FHDR_FOPTS_MAX_LEN` = 15 (`LoRaWAN.h:124`). An over-length reply is dropped for good (`PACKET_TOO_LONG` in `main.cpp`), and a master cannot see FOpts, so it plans against the ceiling that holds when FOpts is full. Corrected 2026-09-10 after independent review. With 30 words the block is one read on every wired path and on the radio at DR4/DR5. A 60-word ceiling, the most a 125-register FC03 holds, would be one read on the wired paths only, and the radio drops an oversized reply rather than truncating it. 30 words also covers every struct worth dumping except `g_rm` itself, and it costs 120 bytes of SRAM.

**Compiled out** with the other debug blocks when `O2P_DEBUG_ENABLE=0`: every read and write at `0x0100..0x0140` is then exception `0x02`. A nodebug build reports the same `FW_VERSION`, so a master confirms the block exists from `BUILD_ID` bit 30 or from the exception, not from the version.

**Tests.** `test/test_logic/test_main.c` `test_peekw_*` drive the block against a fake memory that counts every dereference, so each refusal is checked by status and by zero dereferences. They cover every region's far tail at every burst length, monotonicity in burst length, address wrap, malformed triggers, the snapshot property and SEQ.

### 3.5 SRAM parity gate — added 2026-09-10, `O2P_FW_VERSION` `0x000F`

**Why.** Independent review F1, reasoned rather than observed. ST RM0444 Rev 6 §2.3 (p. 67): with the `RAM_PARITY_CHECK` option bit enabled, parity is "computed and stored when writing into the SRAM" and checked on every read, and a failing bit raises an NMI plus a bus error, i.e. a HardFault. Its note advises initialising the whole SRAM at startup "to avoid getting parity errors when reading non-initialized locations". This firmware does not, and must not: the bottom 16 bytes are `SHARED`, the boot hand-off that has to survive a warm reset (`ldscript/o2probe_app.ld`). Both peek blocks could name all 36 KiB.

**Rule.** On every trigger `peek_check()` loads `FLASH_OPTR`. If bit 22 reads 0 (enabled; RM0444 §3.7.8, p. 102), an SRAM burst must lie wholly inside `.data`, inside `.bss`, or inside both when they abut, from the linker's `_sdata`/`_edata`/`_sbss`/`_ebss`. Anything else is status `4` ERR_PARITY, with nothing dereferenced. Startup writes every word of both sections (`CopyDataInit`/`FillZerobss` in `startup_stm32g071xx.s`, 4-byte stores between `ALIGN(4)` bounds). Flash, the UID and the flash-size word are not gated. Alignment and range errors keep their precedence. With the bit at 1, the factory value (Table 17, p. 83), every peek answers exactly as under `0x000E`.

**Deliberately not admitted:** `SHARED`, the heap gap and the stack. "SP up to `_estack`" is not proven written, because a frame reserves space with one `SUB` and writes only what the code assigns. Every symbol `peek` resolves from the ELF lives in `.data`, `.bss` or flash.

**Guard review.**
- **Unevaluable input** fails closed. An OPTR that reads 0, for example with the flash interface clock off, means enabled and restricts. FLASHEN resets to 1 (RM0444 §5.4.14, p. 193) and nothing in `src/` clears it.
- **Monotonicity:** a longer burst from the same target is never OK once a shorter one was refused, tested at `_ebss` for every length.
- **Precondition:** `FLASH_OPTR` holds the loaded option bytes. It would not after an OPTR write that had not yet been through `OBL_LAUNCH` (RM0444 §3.4.2, p. 84), and nothing in `src/` writes OPTR, OPTKEYR or `OBL_LAUNCH` (grepped 2026-09-10).
- **Known-bad calibration:** the test reads every refused SRAM target first with the factory bit and sees it read OK, so each refusal is the gate's doing.
- **Provenance:** a refusal is its own status, not ERR_RANGE, so an address that is in range is never reported as out of range.

**Reasoned, not measured: whether this image boots with the bit enabled at all.** RM0444 Table 7 (p. 66) gives the G071 32 KiB of SRAM with parity against 36 KiB without, and the linker places `_estack` at the top of 36 KiB. No probe has had the bit set, and none should. The gate is for the image that does run, and it costs one register load per trigger.

**Tests.** `test_peek_parity_on_*`, with every refusal checked by zero dereferences through both blocks. They cover known-bad calibration, bit-exact decoding, OPTR = 0, the far tail at `_ebss`, a gap between `.data` and `.bss`, unaligned bounds, and empty or inverted spans. `test_peek_the_first_word_of_every_region_is_readable` closes review mutant R2. Nothing of this has run on a probe.

### 3.6 Flash peek is the loader and run slot only — added 2026-09-10, `O2P_FW_VERSION` `0x000F`

**Why.** Independent review N4, reasoned rather than observed. Flash is programmed 64 bits at a time with 8 ECC bits per doubleword (RM0444 Rev 6 §3.3.3, p. 74). A program or erase interrupted by a power loss "might result in a corrupted flash memory data and/or ECC bits. The address concerned might trigger an ECC interrupt or an NMI when accessed later on" (§3.3.6, p. 77), and "when two errors are detected ... a NMI is generated" (§3.3.3). The NMI vector on this build is the default infinite loop (`NMI_Handler` shares the looping `Default_Handler` address in the ELF), so a peek of a torn doubleword hangs until the IWDG resets the probe.

**Why not an ECC-aware NMI handler.** On a Cortex-M0+ the read cannot be made recoverable. The NMI returns to the stacked PC — the faulting load — and ARMv6-M gives a handler no architected way to step past it without decoding the Thumb instruction to know its length; nothing in RM0444 licenses that. RM0444 §3.3.3 also warns that "a new read at the failing address may not generate an ECC error if the data is still present in the current buffer," so even a retry is not deterministic. A "peek in progress" flag plus an ECCD clear cannot yield a defined resume.

**The mitigation instead.** The three flash areas a power loss can tear are all written **at run time** — the staging slot during a push, the boot descriptor when a transfer verifies, the config pages A/B on `COMMIT` (`src/flash_map.h`). None is inside the loader (pages 0–7, never rewritten) or the run slot (pages 8–33, written only by the loader while the application is not running). So the flash peek region is confined to pages 0–33, `0x08000000 .. 0x08010FFC`; a peek of staging, the descriptor or config now answers `ERR_RANGE`. Where the running image lives is, by definition, intact enough to execute. This is a **mitigation, not a proof** the excluded pages would fault: no torn page was ever read on a probe. Ordinary flash *activity* — a read while a program/erase is in progress — is a different case that stalls then completes (§3.3.6) and is unaffected.

See §11 for the boot-path reads that share this exposure and are **not** fixed here.

### 3.7 Memory poke mailbox and wide poke — added 2026-09-11, `O2P_FW_VERSION` `0x0012`

**Why.** Fab's order 2026-09-11: "let an agent implement the equivalent write command of the peek", after a lost TMP117 threshold pair could only be repaired by an MCU reset because no runtime path could write memory. The peek blocks read; these two blocks write, under the same debug gate.

**Blocks.** Mailbox `0x0198..0x01A3` (12 registers) mirrors the 4-word peek mailbox; wide poke `0x01B0..0x01F0` (65 registers) mirrors the wide peek block. `0x01A4..0x01AF` is an empty guard on the `0x00FB..0x00FF` convention: a malformed FC16 that runs off the end of a block lands in nothing. Placement verified free against `src/regmap.h`, `src/update.h` and the `o2p_regmap_read/write` dispatch.

**Trigger shapes.** Each block takes ONE FC16 starting exactly at its base, of exactly `3 + 2*words` registers — the payload rides the trigger frame, `[addr_hi, addr_lo, words, w0_hi, w0_lo, ...]`, `words` 1..4 (mailbox) or 1..30 (wide), so accepted counts are 5..11 and 5..63, inside the 123-register FC16 ceiling (`src/modbus_pdu.c:73`). Any other in-block write is exception `03` and changes nothing; a frame that runs off the block's end leaves the map and is exception `02` like any off-map frame. A well-formed trigger always replaces the held state — address, count, payload and status — and the wide block's SEQ advances on every executed trigger, skipping 0 on wrap. On a REFUSED poke the payload is still held (unlike a refused peek's `0xFFFF` words): the readback shows exactly what was attempted while the status says it never landed, and a store counter in the host tests proves nothing was written.

**Write space, and every exclusion's reason.** The `.data`/`.bss` span the SRAM parity gate (§3.5) admits, and NOTHING else:

- The reasoning INVERTS from the read side. A peek admits that span because startup made those words' parity valid; a poke could safely write ANY SRAM word, because RM0444 §2.3 (p. 67) computes and stores parity "when writing into the SRAM" — a store cannot hit the never-written NMI a read can. The span is kept anyway, as POLICY: (1) SYMMETRY — whatever the poke may write, the peek can read back, so a poke's verification is a peek it already has; (2) THE SPAN IS THE LINKER'S PROMISE — ".data and .bss" are the words the image can NAME, "a variable", which is what a poke is for.
- SHARED (`0x20000000..0x2000000F`, below `_sdata`) is excluded: the boot hand-off that must survive a warm reset (`ldscript/o2probe_app.ld`).
- The stack and never-written SRAM above `_ebss`, and the heap gap between non-abutting `.data` and `.bss`, are excluded — a burst must lie wholly inside one section or the abutting union, exactly the read-side rule.
- FLASH is excluded — the write-side form of §3.6's N4 reasoning: a runtime flash write tears pages (bad ECC, NMI, a hung probe), and the only sanctioned runtime flash writer is the updater's.
- PERIPHERALS AND SYSTEM REGISTERS are excluded, SCB AIRCR (`0xE000ED0C`) included, on purpose: the peek reads no peripheral either (its regions are SRAM, the loader/run slot, the UID, the flash-size word), and a peripheral write is an arbitrary side effect. A bench-triggered MCU reset through AIRCR would be an undocumented reset path competing with the ones the firmware owns; if wanted, it is a new register with its own review, not an accident of this one.

**Status codes** mirror `O2P_PEEK_*` (0 none, 1 OK, 2 range, 3 align). There is deliberately no parity code: a store creates valid parity, so the read-side parity failure mode cannot happen on the write path.

**The store loop** mirrors `peek_copy()`: interrupts masked for the stores only (the torn-struct argument run the other way — an ISR must not read a struct half-poked, old and new plausible together), the same 95 µs character bound and ~17 cycles/word estimate, so 30 words ≈ 32 µs and the ceiling stays 30. Overlap is handled memmove-style with the ROLES REVERSED from `peek_copy` — the payload is the SOURCE and the target the DESTINATION — so the walk is high-to-low when the payload sits BELOW the target, low-to-high above it: the write-side image of N1, where an early store could clobber a payload word a later load still needs.

**Compiled out** with the other debug blocks when `O2P_DEBUG_ENABLE=0`: every read and write at both blocks is exception `02`.

**Tests.** `test/test_peek_write/test_peek_write.c` (its own suite, `pio test -e native -f test_peek_write`): every refusal is checked by status AND by a store count proving nothing was written; the accepted shapes are enumerated; SHARED, the stack, the gap, the span tail and the empty-span degenerate map are pinned; the regions a READ may touch but a WRITE may not (run slot, UID, flash-size, AIRCR) are pinned; the poke-then-peek roundtrip proves the symmetry; and both overlap directions prove the store order.

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

These are new codes rather than `ERR_NACK`/`ERR_TIMEOUT`, which mean something specific about an I²C part. A queued I²C opcode owns the result registers until it runs, so a request that arrives meanwhile is refused. Up to `0x000E` it was refused with exception `0x03` and `DIAG_STATUS` := `6` ERR_BUSY. That overwrote the queued command's PENDING, and the CLI, which polls for "not PENDING", took ERR_BUSY as that command's result (independent review F2, 2026-09-10, confirmed through `o2p_regmap_write`). From `0x000F` the refusal is exception `0x06` SERVER DEVICE BUSY and writes nothing; the shape check runs before it and the magic/opcode checks after it, so while busy nothing can write `DIAG_STATUS`. `o2p_cli.py` reports the 06, checks `DIAG_CMD`/`DIAG_PARAM` against its own command on every poll, and does not treat ERR_BUSY as final. Tests: `test_dmbox_a_busy_refusal_is_exception_06_and_writes_nothing` (through `o2p_mb_dispatch`) and the "queued I2C command" cases in `tools/test_o2p_cli_gpio.py`.

**PF2 is the NRST pad.** Its GPIO registers describe the pad only when the `NRST_MODE` option bits select GPIO (RM0444 Rev 6, 7.3.17, p. 237; 3.7.8, p. 102). The factory value is `11`, reset I/O (Table 17, p. 83), and nothing in `src/` writes option bytes. PF2 therefore describes an unconnected GPIO cell on these probes. No runtime effect today: `src/mcu.c` never clocks port F, so every PF pin answers `8` ERR_GPIO_UNCLOCKED before anything is loaded.

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
   - Saves 3,112 bytes of `firmware.bin` and 196 bytes of RAM as PlatformIO counts it, measured 2026-09-10 as `env:o2probe` minus `env:o2probe_nodebug` from the same tree at `O2P_FW_VERSION` `0x000F`. Given as the DELTA rather than an absolute pair: the difference is exactly the debug mailboxes and is independent of whatever else is linked, since both images carry it. This line said 1,492 bytes of Flash and 64 of RAM, and `platformio.ini` said about 1.8 KiB; both predate the wide peek block, the GPIO opcode and the 0x000F work.
   - Mandatory target before potting production probes destined for unmonitored permanent burial.

---

## 10. Executing uploaded code (0x0150 mailbox)

**Status: Implemented 2026-09-11 in commit `0b31cd9` under `O2P_DEBUG_ENABLE=1` at register base `0x0150`.**

Originally considered and deferred on 2026-09-10 due to safety and privilege concerns; subsequently implemented with software fault interception and hardware watchdog backstop:
- **Debug builds only**: compiled in only when `O2P_DEBUG_ENABLE=1`. In production/potting builds (`env:o2probe_nodebug`), the entire block (72 registers) is omitted and returns Modbus Exception 02.
- **Containment & Fault Interception (narrow scope)**:
  - Unused buffer space is filled with `BKPT 0` (`0xBE00`) trap instructions.
  - SysTick execution timeout watchdog (default 50 ms, configurable 1..1000 ms) uses a C trampoline to unwind via `setjmp`/`longjmp` back to Thread mode with `STATUS_TIMEOUT`. Note: if user code disables interrupts (`cpsid i`) and hangs, SysTick cannot fire; only the hardware IWDG (~4.1 s) will reset the MCU.
  - HardFault interception (`o2p_hardfault_c_handler`) traps instruction/bus/alignment errors in Thread mode and unwinds via `longjmp` back to Thread mode with `STATUS_FAULT`, returning control without an immediate chip reset or 15-minute cell settling cycle. State mutations made before the fault survive; stack-corruption or handler-mode faults fall back to the default reset.
  - Automatic heater cut-off (`o2p_heater_force_off()`) before and after invocation.
  - Automatic RS-485 DE line release (`o2p_modbus_de_release()`) before and after invocation so the bus transceiver is not left driven on return.
- **Execution model**:
  ARMv6-M (Cortex-M0+) Thumb functions matching `uint32_t (*fn)(uint32_t arg)` in SRAM, taking `R0` from `EXEC_PARAM_HI:LO` and returning `R0` into `EXEC_RESULT_HI:LO`. Runs during `PH_IDLE` between sampler cycles. Must be compiled specifically for Cortex-M0+ (`-mcpu=cortex-m0plus -mthumb`).

The original design rationale and hazard analysis from 2026-09-10 are retained below for provenance:


**Why it would work.** The pieces exist:
- An FC16 window to carry a blob. The update data window already takes 123 registers per frame (`src/update.h`).
- A trigger register holding the entry address.
- A blob linked with `--just-symbols=firmware.elf`, so it calls firmware functions by name.

Cortex-M0+ SRAM is executable when no MPU region says otherwise. That is the ARMv6-M default memory map, stated from knowledge of the architecture and not re-read for this note. This firmware never programs the MPU: on 2026-09-10, `grep MPU src/` matched only the word "COMPUTED" in two comments.

**Why it is worse than the existing updater.**
- **It bypasses the heater interlocks.** Every interlock in FIRMWARE.md "Interlocks" is main-loop code that decides TIM1's compare value (`src/heater.c`). A blob runs at the same privilege as that code, with nothing between it and TIM1. An install replaces the whole image, and the image that then runs carries its interlocks.
- **It can erase the loader or rewrite the option bytes.** The flash unlock keys are already in the image (`src/flash_hal.c` lines 39–40), so a blob linked against the ELF can erase any page. That includes pages 0–7, the bootloader that `src/flash_map.h` marks "NEVER rewritten". A blob can also unlock `OPTLOCK` (RM0444 Rev 6 §3.4.2, p. 84) and rewrite RDP, WRP or `NRST_MODE`. Nothing write-protects anything today. On 2026-09-10, `src/` was grepped for OPTR, OPTKEY, OPTSTRT, `OBL_LAUNCH`, WRP and RDP, and the only hit is `FLASH_SR_WRPERR` in `flash_hal.c`'s error mask. On a potted probe an erased loader is permanent.
- **It is unauthenticated code execution on a plaintext bus.** LoRaWAN reaches that bus through the node's fPort-10 relay (node-prototype `README.md`). farming `tech/IMAGE-AUTH.md`: "Status 2026-09-06: specification. Nothing in it is built." The updater is unauthenticated too, so this is not a new class of exposure. What an install still has is `update.c`'s length and CRC checks on the staged image, a loader outside the region it writes, and a reset into a whole image. A blob gets none of those, and runs mid-sampler inside live state, possibly with the heater on.
- **A hung blob is recovered only by the IWDG.** It is started in `src/mcu.c` and cannot be stopped (`IWDG->KR = 0xCCCC`), so a hang resets the probe within 4.096 s nominal (`mcu.c`, prescaler /64, reload 2047). A blob that refreshes the IWDG itself is not recovered, and nothing stops it doing so.

**Containment, if it were ever wanted.**
- **Debug builds only**, behind `O2P_DEBUG_ENABLE` with the peeks. `env:o2probe_nodebug`, the build §9 mandates before potting, would then have no path at all. This is the one option that holds against a deliberate blob, because the code is not there.
- **Locking `FLASH_CR` with a deliberately wrong key before the jump.** Verified in RM0444: a wrong sequence "locks the FLASH_CR register until the next system reset", and it also means "a bus error is detected and a Hard Fault interrupt is generated" (§3.3.6, p. 77; LOCK bit, §3.7.5, p. 98). The same holds for `OPTLOCK` (§3.4.2, p. 84). Setting LOCK by software instead contains nothing, because the blob can unlock again with the published keys. The wrong-key lock, though, arrives as a HardFault, and this firmware's `HardFault_Handler` records a crash and calls `NVIC_SystemReset()` (`src/mcu.c`), which clears the lock. So it contains a blob only if the handler learns to recognise that one fault and return from it, which on ARMv6-M means rewriting the stacked PC. **UNVERIFIED** that this is safe on this part. As the handler stands, it is not a containment.
- **MPU plus unprivileged execution.** `__MPU_PRESENT` is 1 in CMSIS `stm32g071xx.h` (line 50), and DS12232 Rev 5 §3.2 describes the MPU. A blob in unprivileged Thread mode, with regions that deny `FLASH`, `RCC` and the timers, could not undo its own confinement. On ARMv6-M a violation arrives as a HardFault, since there is no MemManage exception, so the handler again has to tell a blob's fault from a real one. **UNVERIFIED:** whether ST configured this Cortex-M0+ with unprivileged Thread mode. Neither DS12232 nor RM0444, as searched, says so.

**Pre-potting recommendation, independent of the above: a proposal, not adopted.** Write-protect the loader's pages before potting. RM0444 §3.5.3 (p. 90): a WRP area "cannot be erased or programmed", at 2 KiB page granularity, set in `FLASH_WRP1AR`. For pages 0–7 that is `WRP1A_STRT` = 0 and `WRP1A_END` = 7, and it applies at the next option-byte load. It guards against an **accidental** erase: a wrong page number, a stray `PER`. It does not guard against a **deliberate** privileged write, because WRP lives in the option bytes and any privileged code can clear it with the §3.4.2 sequence. Before adopting it, check two things: that no bench or loader-update path legitimately writes pages 0–7, and that the SWD flashing recipes in FIRMWARE.md "Flashing" still work, or say how to lift WRP first. RDP Level 2 is not proposed. It is irreversible and removes the debug port and the system bootloader (RM0444 §3.5.1, p. 86).

---

## 11. Considered, not built: flash ECC beyond the peek (report, 2026-09-10)

§3.6 confined the *peek* to the loader and run slot because a torn flash doubleword raises an NMI the default handler does not survive. That handler is shared by every read of mapped flash, not only the peek, so review finding N4(b) asked which boot-path reads carry the same exposure. This section is a **report and does not change any code** — above all it does not touch the loader.

**The handler.** `NMI_Handler` is a weak alias to `Default_Handler`, an infinite loop (`startup_stm32g071xx.s:190-191`, `:116-118`), and nothing in `src/` overrides either. So a double-ECC-error NMI (RM0444 Rev 6 §3.3.3, p. 74 — **sourced**) spins until the IWDG resets (`src/mcu.c`, ~4.096 s — sourced). If the read that faulted runs again on the next boot, the probe resets forever. That a plain `memcpy`/struct read of a torn doubleword raises this NMI is **reasoned** from §3.3.6 (p. 77, "might trigger an ECC interrupt or an NMI when accessed later on"); no torn page was read on a probe.

**Reads of run-time-programmed flash on the boot path:**

| Site | Reads | Pages | On whose boot |
|---|---|---|---|
| `src/config_flash.c:53-54` (`read_record`, from `o2p_config_load` `:111`) | both config records, always, to pick the newer | 62, 63 | application (`src/main.c:1741`) |
| `src/boot_desc.c:86` (`read_page`, from `o2p_desc_load` `:90`) | both descriptor records, always | 60, 61 | application via `o2p_update_target_init` (`src/main.c:1748` → `src/update_target.c:18`) **and the loader** (`src/loader_main.c:490`, and again at `:500`) |

Both readers touch **both** A/B pages unconditionally — validity is judged only after the bytes are read — so a single torn page faults the read regardless of which page is live. A config store writes the page that is *not* live (`config_select.h`, `o2p_config_other_page`), and the descriptor is A/B likewise, so the page a power loss tears is the non-live one, and the next boot reads it anyway.

**Consequences (reasoned):**
- A torn **config** page (power loss during `COMMIT`) faults `o2p_config_load` at application boot → NMI → IWDG reset → **the application boot-loops**. The config machinery's own A/B redundancy does not help, because the read that faults happens before any validity check.
- A torn **descriptor** page (power loss when the application writes the descriptor after a verified transfer, or when the loader rewrites it after an install) faults `o2p_desc_load`. The application reads it at boot, and **so does the loader at every reset** (`loader_main.c:490`). A descriptor tear that faults the loader is **permanent on a potted probe**: the loader cannot be reflashed once potted, and it never gets far enough to start the application.
- The **staging** slot is not read on the boot path (`update_target.c` initialises from descriptors only, and the peek no longer reaches it), so a staging tear alone does not boot-loop anything.

**Is the loader exposed?** Yes — `src/loader_main.c:490` and `:500`, through `o2p_desc_load`. This is the most serious case, and it is exactly the one this task must not change.

**What an ECC-aware NMI handler would need**, if this is ever taken up (reasoned, and the reason §3.6 chose restriction over recovery on the peek):
1. A real `NMI_Handler` replacing the weak default, that reads `FLASH_ECCR` (`ECCD`, `ADDR_ECC`, `SYSF_ECC`), clears `ECCD` by writing 1, and returns without re-executing the faulting load. On Cortex-M0+ that last step is the hard part: the NMI resumes at the stacked PC, and stepping past a load means decoding the Thumb instruction's length and rewriting the stacked PC — architecturally unsupported and fragile. RM0444 §3.3.3 also warns a re-read "may not generate an ECC error if the data is still present in the current buffer," so a retry is not deterministic.
2. For the boot path specifically, a handler cannot simply "return failure" the way a peek can, because the caller expects valid config/descriptor bytes. It would need a boot policy: on an ECC fault reading config, fall back to defaults; reading the descriptor, treat the slot as empty. That is design work spanning `config_flash.c`, `boot_desc.c`, `update_target.c` and `loader_main.c`, and it changes the loader — out of scope here.
3. ST **AN5342** ("ECC management on STM32…") was named in the brief as a source for whether a safe return is possible; it was **not fetched** for this pass (the task is host-only and no code depends on it), so the recoverability conclusion rests on RM0444 and the ARMv6-M architecture alone. Fetching AN5342 is the first step if recovery is ever pursued. **UNVERIFIED** until then.

**Recommendation:** treat the loader's descriptor read as the priority if this is taken up, since it is the only permanent-brick path; the application-side config and descriptor reads boot-loop but remain recoverable by a new install once the tear is understood. No change is made now.
