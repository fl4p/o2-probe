# o2-probe Rev A firmware — v1

> **DEPLOYMENT PROHIBITED.** v0 is a bench and short-trial build. It has no
> membrane heater, and its RS-485 updater — which now exists, engine and
> bootloader both — has never run on silicon. Do not bury a probe running it,
> and do not pot one until a full update cycle has been performed on the bench
> and recorded. The reasons are in "What v0 does and does not do" below, and
> neither is a matter of polish.

Modbus RTU slave for the SGX-OX-ROHS-Mini oxygen probe. STM32G071CBT7,
PlatformIO + STM32Cube (HAL headers, direct CMSIS register code).

`gen_sch.py` in the parent directory is the source of truth for the hardware.
`src/hw_contract.h` is **generated** from it and checked on every build; do not
edit it by hand.

```sh
pio test -e native      # portable logic, 223 cases
pio run  -e o2probe     # cross build: the application, linked at 0x08004000
pio run  -e loader      # cross build: the RS-485 bootloader, at 0x08000000
pio run  -e loader  -t upload    # flash the bootloader FIRST, once
pio run  -e o2probe -t upload    # then the application
pio run  -e bridge              # a spare board as the RS-485 adapter
python3 tools/gen_hw_contract.py            # regenerate after a schematic change
python3 tools/gen_hw_contract.py --check    # what the build runs
python3 tools/check_flash_map.py            # linker scripts vs src/flash_map.h
python3 tools/check_update_tool.py          # field tool vs update.h + regmap.h
python3 tools/test_swd_link.py              # the bridge's SWD transport, host-side
python3 tools/test_resume.py                # the updater's resume decision, host-side
python3 tools/test_baud.py                  # the updater's baud fallback, host-side
python3 tools/test_serial_capture.py        # SerialLink against measured and late replies, host-side
python3 tools/test_verify_install.py        # --boot proves the install or exits non-zero, host-side
python3 tools/test_fallback_identity.py     # finding a probe whose loader fell back
python3 tools/test_tempco.py                # the AFE-tempco fit recovers a planted slope and refuses a flat run
python3 tools/o2p_update.py --port /dev/tty.usbserial-X --status
python3 tools/o2p_update.py --swd --status  # ... or through a bridge over SWD
python3 tools/o2p_capture.py --once         # one live snapshot over SWD, to stdout
python3 tools/o2p_tempco.py --csv run.csv --mode dummy   # AFE tempco from a heater run; docs/2026-09-09-afe-tempco-plan.md
python3 tools/o2p_capture.py bench-logs/x.csv --count 1441 --interval 30   # 12 h
```

A bench board needs **both** images. The core fetches its reset vector from
`0x08000000`, which is the bootloader's; flashing only the application leaves
that erased.

## What v0 does and does not do

Does: all four I²C devices, the oxygen conversion with air-point calibration,
the Modbus RTU slave and the full register map, bias supervision with the
15-minute settling rule, the condensation-margin channel, flash-backed
configuration, and an independent watchdog (IWDG, /64 prescaler, reload 2047 — 4.096 s
nominal, roughly 2.7–6.5 s over the LSI's spread). The watchdog is fed only
while the sampler is completing cycles **and** the RS-485 driver is not stuck
enabled; nothing else in the firmware feeds it, because a safety interlock with
a second, unconditional key is not one.

v1 adds the **membrane-heater control loop**. It shipped **switched off**; as
of 2026-09-08 the compile flag is `1` and the ring is reachable, with the
flash-backed duty maximum the remaining switch.

`DESIGN.md:47-51` and `FAB-READINESS.md:61` both state the TMP117 ALERT path
"is not credited as an autonomous overtemperature cutoff until firmware
configures and fault-tests the TMP117". Firmware now *configures* it, and
`o2p_tmp117_safety_armed()` latches whether that took. It has **not been
fault-tested** — the injected-fault test (lower `THIGH` below ambient, command
duty, watch `HEATER_LOW` go high) has never been run, so the 85 °C cutoff is
*configured and read back*, not proven.

That test was previously stated as a precondition for putting 1 W into the
membrane carrier. It no longer is: as of 2026-09-08 the flag is `1` and the
override exists specifically to drive the ring for the 80 °C
harsh-environment characterisation, with degradation expected. The live limits
are therefore the firmware tip clamp at 80.00 °C, which fails if firmware
fails, and an unproven hardware cutoff behind it. Treat the ring as attended
equipment until the injected-fault test is recorded.

The heater was off at **two independent switches**, and enabling it is never
a single edit:

| Switch | Where | Default |
|---|---|---|
| `O2P_HEATER_ENABLE` | compile flag in `platformio.ini` | **`1` since 2026-09-08.** Was `0`, which gated TIM1's clock off and held PA8 as a plain output |
| `HEATER_MAX_DUTY` `0x0035` | flash-backed configuration | `0` — the loop refuses with `CONFIG_OFF` |

The full enable procedure and its bench prerequisites are at the top of
`src/heater.h` and in [The heater loop](#the-heater-loop-v1) below.

**The cost of that, stated plainly:** the SGX cell is rated 15–90 %RH
*continuous, non-condensing*, and the heater is the only thing keeping the
membrane above the dew point of saturated pore gas. **With the heater switched
off this is a bench and short-trial build.** A probe left in a pile for weeks
with the loop disabled will wet its membrane. `DEW_MARGIN` and the `DEW_SUSPECT` fault exist so that is observed
rather than discovered afterwards.

The **RS-485 updater** is no longer absent. `SCHEMATIC-REVIEW.md` M2 requires
it to be installed *before potting*, because J3 is not exposed through the
enclosure and the STM32 ROM bootloader cannot work through the software-driven
DE line. It is now built: `src/update.c` is the engine and register block,
`src/loader_main.c` is the 16 KiB bootloader that installs what it receives.
See [Field updates](#field-updates-how-a-buried-probe-gets-new-firmware).

**The gate has moved, not lifted.** None of it has executed on silicon. What
must be true before epoxy touches a probe is now a bench result — one complete
transfer, install and restart, plus one deliberate power-cut mid-transfer — not
the existence of the code. **Do not pot a probe whose update cycle has not been
demonstrated.**

## Field updates: why the v2 bootloader is wired

The question this settles, because it will be asked again: once a probe is
potted and buried, can it be reflashed through infrastructure that is already
there — the Dragino's LoRaWAN link, or its BLE console — instead of a wired
bootloader that has to be installed *before* the epoxy goes on?

No, and the reason is narrower than "there is no wireless path". There is one.
It is 40 bytes wide, it takes about **90 hours**, and it cannot create the
thing it would need to talk to.

**Every number below is proportional to the image and moves with it.** They
are stated for a measured build rather than left as a formula because a
transport estimate nobody can check is not an estimate — but the build is
named, and `tools/check_transport_math.py` verifies that the chain is
internally consistent, which is the part that has silently rotted twice.

Measured at `5662aaa` + this commit: `firmware.bin` is **25,964 bytes**,
48.8 % of the **53,248-byte run slot** — not of the part, which the
application no longer owns. The updater pads to the next doubleword before
sending, so **25,968 bytes** go over the wire. (PlatformIO's banner counts `text`+`data`
and not the inter-section padding that a flash image still has to carry. Use
the `.bin` size, not the banner, for any transport estimate; and re-run these
numbers when the image changes, because every one of them is proportional
to it.) A differential scheme would
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
| whole 16-bit registers | 30 B per downlink |
| less this engine's 8-byte image alignment (`src/update.h`) | **24 B** of image per downlink |
| less the block sequence number, which shares the frame | 12 payload registers |
| downlinks for 25,968 bytes | **1,082** |
| at `AT+TDC` = 300 s | **90.2 h** |

Nearly three days, and that is the *floor*: no retries, no erase waits, no
handshake. (Whether the 40 bytes counts the CRC the node appends when `MM=1`
is not spelled out; if it does not, the budget is 32 bytes of image and the
figure gets worse, not better.)

**The radio is not the binding constraint, the command is.** An `A8` frame is
4 + 40 = 44 application bytes, which fits even DR0/SF12's 51-byte maximum, so
data rate never enters into it. For reference: EU868 allows 51 application
bytes at DR0 and 242 at DR5 — the 242 assuming no repeater and empty `FOpts`,
222 otherwise — but no data rate lets one downlink carry more than 40 bytes of
CFGDEV. Airtime is likewise not the limit: 785 SF12 downlinks of 57 PHY bytes
is 2,630 ms each, 2,064 s of transmitter time (0.57 h), which under continuous
10 % duty-cycle pacing on the 869.4–869.65 MHz band is about 5.7 h elapsed —
well inside the 65 h the cadence already costs.

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

### Wired RS-485, which is what the updater actually uses

The cable that carries Modbus carries the image at line rate. At 9600 8E1 a
byte is 11 bit times, so 872.7 B/s and **29.8 s** for the whole image; at
38400, **7.4 s**. Line time only — framing, page-erase waits and per-block
acks are on top. Concretely, at the 240-byte block the register window allows,
a 25,968-byte image is 109 blocks; each block frame is 251 bytes and its
response 8, so about 0.30 s per block on the wire and **under a minute** in
practice at 9600, plus the staging-slot erase — 26 pages at this part's 22 ms
typical and 40 ms maximum, so **0.57 s typical and 1.04 s worst case** of
flash-busy time, and more than that in wall time because the application
interleaves a sampler step between pages. A transport with that much
headroom can acknowledge and retry every block, and it is reachable from the
same A/B pair a technician already has to touch.

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

## Field updates: how a buried probe gets new firmware

### The flash map

`src/flash_map.h` is the source of truth; `tools/check_flash_map.py` runs on
every build and fails it if the linker scripts or `platformio.ini` drift from
it. 128 KiB, 64 pages of 2 KiB:

| Pages | Address | Size | Contents |
|---|---|---|---|
| 0–7 | `0x08000000` | 16 KiB | bootloader — never rewritten in the field |
| 8–33 | `0x08004000` | 52 KiB | run slot — the application (5.6 KiB and 25.7 KiB used today) |
| 34–59 | `0x08011000` | 52 KiB | staging slot — the image being received |
| 60–61 | `0x0801E000` | 4 KiB | boot descriptor, A/B |
| 62–63 | `0x0801F000` | 4 KiB | configuration, A/B (unchanged) |

The application is therefore **linked at 0x08004000** and a bench board needs
both images: `pio run -e loader -t upload` once, then `pio run -t upload` for
the application. Flashing only the application leaves the reset vector the core
actually fetches — the one at `0x08000000` — erased.

Downloading into a slot beside the running image rather than over it is the
whole point: the farm supply is a shared 12 V feed and a brownout during a
transfer is an ordinary event, not an exotic one. The cost is that there is no
room for a second full-size slot, so **there is no automatic rollback** — see
[Known limitations](#known-limitations).

### The protocol

Plain Modbus: FC03 to read, FC06/FC16 to write, nothing else. Every step fits
in 40 bytes, so the same sequence works over a laptop's USB-RS-485 dongle and
over the Dragino's `A8` downlink, differing only in how long it takes.

1. Read `0x0050` `UPD_STATUS` and `0x0051` `UPD_BLOCK_MAX`.
2. Write the image length and CRC-32, and `BEGIN` — one FC16 of five registers
   from `0x0054` does all of it. The engine applies the command *after* the
   numbers in the same frame regardless of address order, which is what makes
   the single-frame form possible at all.
3. Poll `0x0050` until the state is `READY`: the staging slot is erased one
   page per main-loop pass, so the probe keeps answering throughout.
4. Write blocks to `0x0080`: `[sequence, payload…]`, payload a whole number of
   64-bit doublewords, at most 120 registers. The FC16 response **is** the
   acknowledgement.
5. Write `COMMIT`, poll until `STAGED` — the probe CRCs the whole slot in
   1 KiB slices and checks the image's vector table.
6. Write `BOOT`. The probe resets, the bootloader installs the staged image
   into the run slot, verifies it, and starts it.

Blocks carry their own sequence number rather than streaming, because on the
`A8` path a lost reply is routine: a repeat of the block just accepted is
acknowledged and not reprogrammed, and anything else is refused with
`ERR_SEQUENCE` so the master can read `0x005B` `UPD_NEXT_SEQ` and resume.
A refused frame never ends the transfer — only a flash error or a failed
verification does.

`tools/o2p_update.py` performs all of it over a serial port.

### Raising the baud for a transfer

The cable is 9600 8E1 because the SMT100s on it are, and 9600 is what makes a
30 KiB image take about four minutes. `BAUD_CODE` `0x0031` is a writable
register, so `tools/o2p_update.py` moves the probe to the fastest rate its
firmware offers for the duration of a push and puts it back afterwards. That
was **38400** — the same image in about a minute; a probe running `a901947` or
later also offers 115200, and the tool goes there. `--no-speedup` turns it off.

**Not through the node.** When `--port` is the node's USB console (the
`src/serbus.h` relay in node-prototype), the host's line rate never reaches the
cable: the ESP32-S3 USB Serial/JTAG ignores the host line coding, so the probe
would move alone and stay stranded until its probation reverts. Pass
`--no-speedup` there; the tool does not yet refuse on its own. (ESP32-S3 TRM
reading by another session, 2026-09-10 — not measured here.)

Three properties make that defensible, and all three are load-bearing:

1. **It is never committed.** The new rate lives in the RAM config only. Every
   way the tool can lose control — a crash, a killed terminal, a pulled lead —
   is ended by the probe's next reset, which reloads the flash config and puts
   it back on the bus rate. `--boot` resets, so the bootloader and the newly
   installed application both come up at the stored rate no matter what the
   tool did.
2. **The switch is deferred at both ends.** The probe applies a serial change
   only once its reply is off the wire (`src/main.c`, the deferred-work block,
   via `serial_reconfig_pending`), so the acknowledgement is the last frame at
   the old rate. The tool waits, retimes, and only then speaks.
3. **It is confirmed by content, not by silence.** The tool reads `BAUD_CODE`
   back five times at the new rate and requires the value it asked for. One
   lucky frame is not evidence for a four-minute transfer, and a link that
   merely *seems* alive would spend the time twice.

It declines outright, and says which of these it hit, when a bench bridge is in
the path (`O2P_BRIDGE_BUS_BAUD` is compiled in, so the bridge cannot follow the
probe anywhere), over `--swd` for the same reason, when the probe will not
report a baud code this tool has a rate for, and when it is already at the
fastest code. Declining costs four minutes; guessing costs a probe.

**The case the tool cannot recover from on its own** is a cable that carries
9600 and not 38400. The probe accepts the write, and then neither the
retraction nor anything else reaches it, because it cannot hear the rate it is
being spoken to at. No amount of retrying at this end helps; the tool detects
it, puts its own line back on 9600 and says so. That is why the probe closes it
from the other side — see *Reachability is on probation*. Against a probe older
than 2026-09-08 the remedy is still a reset, which is safe precisely because
the write was never committed.

`tools/test_baud.py` exercises the fallback on the host, against a fake line
that drops frames whose rate does not match the probe's and applies a baud
change only after the reply — including the unrecoverable case above, which it
asserts ends the way described rather than the way one would prefer. As of
2026-09-10 its fixtures still assume 38400 is the top rate, and 30 of its checks
fail against HEAD for exactly that reason; they have not been reconciled with
`a901947`.

### Late replies, and a `--boot` that proves the install

Modbus RTU has no transaction id: a reply that arrives after its exchange gave
up is indistinguishable from the next exchange's. So `SerialLink` drains the
line until it has been silent for `--late-reply-s` (default 8 s, `LATE_REPLY_S`)
after any exchange that did not end with a frame (including one that raised
mid-read), and before the first exchange of every run, in case a previous process left a request queued in the node. 8 s is
derived from the node's stall path — a relayed request waiting while the node
is inside a LoRaWAN uplink — not measured; a longer stall is not covered, and
`tools/test_serial_capture.py` pins that limit. After a real host rate change
on a dongle the drain is 0.3 s, so it cannot outlast the probe's 10 s probation;
a same-rate call, or a link that is the node's USB Serial/JTAG (recognised by
VID/PID), keeps the full drain because nothing became undecodable.

`--boot` used to exit 0 once the BOOT write was acknowledged, which happens
before the reset and so proves nothing about the install. It now waits up to
`--verify-timeout` (180 s) for the application and exits **0** only if
`UPD_INSTALLS` advanced by exactly one — and `BUILD_ID` equals
`--expect-build-id` when given; **1** when the probe contradicts that; **2**
when it cannot be shown (no answer, a saturated counter, an unreadable count).
A matching `BUILD_ID` alone is never enough: the image may already have been
running, and every dirty build of a commit carries the same stamp.
Before sending BOOT the tool also confirms the probe is STAGED with this image's
length and CRC-32 (`UPD_LEN_*`, `UPD_CRC_*`) and refuses to boot otherwise
(exit 1): an advancing count proves an install, not whose. Between that read and
BOOT the tool must be the only master on the probe.
`--no-verify` restores the old behaviour and says so. The farming repo's BLE
and LoRaWAN push tools call the same check.

### The bootloader

`src/loader_main.c`, 16 KiB, flashed over SWD before potting and never
rewritten afterwards. On every reset it:

1. reads the boot descriptor, and if an image is staged **re-verifies it**
   before erasing anything, then copies it into the run slot, verifies the
   copy, and records it as installed;
2. checks the run slot — against the descriptor's CRC when there is one, and
   against the vector table when there is not, so a probe whose application was
   flashed over SWD still starts;
3. listens for **one second** for a knock: a write of `STAY` to `0x0054`
   `UPD_CMD`. Nothing else is acted on during the window, and anything else is
   answered with silence.
4. Otherwise it starts the application.

The knock window is the recovery path, and it is why the loader is a separate
image. An application that boots but has stopped answering — stalled sampler,
jammed DE, wrong address — cannot update itself, and a potted probe has no J3
and no BOOT0. One second of start-up delay on an instrument that already
spends fifteen minutes settling its cell is a cheap price for the only
remaining door. In service mode the loader answers the same update registers,
with bit 15 of `UPD_STATUS` set so a master can tell it is not talking to a
probe that is measuring; after ten minutes of silence it starts the
application anyway rather than leave a buried probe unbiased.

### How the loader knows where the probe is on the bus

The knock window is only a door if the master knocks at the right address and
the right baud, so the loader has to read the probe's transport settings out
of flash. That is harder than it looks, and it was **wrong until 2026-09-08**.

The loader read them from the application's configuration record and accepted
only an exact `CONFIG_LAYOUT_VERSION` match. But it is the one image never
rewritten in the field, so it is frozen at whatever layout was current the day
it was flashed, while the application's record marches on — version 7 landed
on 2026-09-08, version 8 hours later. The moment the application's layout
moved past the loader's, the loader could no longer read the record and fell
back to **address 3 / 9600 / even parity**, silently, on precisely the probe
whose application was already broken enough to need the loader. A probe an
operator had moved off the default transport was then unreachable through its
only remaining door.

The exact-match rule was not the bug — it is arithmetic. The record's CRC sits
immediately *after* the configuration struct, so growing that struct **moves
the checksum**, and a loader that does not know the new size cannot find the
bytes that would tell it whether the record is trustworthy. Reading an address
out of a record you cannot verify is worse than defaulting.

So the three transport bytes are written a **second time**, into their own
16-byte record at a fixed offset in the same config page, with its own magic,
its own version and its own CRC at a fixed position (`src/transport_record.h`,
programmed by `o2p_config_store()` in the same erase as the configuration).
The loader reads that and never needs to know what the configuration looks
like. **That layout is frozen, not merely stable**: a future firmware that
needs to hand the loader something else adds a *second* block at a different
fixed offset — there are ~2 KiB spare in the page — and leaves this one
untouched. Growing it, reordering it or moving its CRC would recreate exactly
the bug it exists to fix, in images that cannot be told.

The configuration record remains a fallback for records written before the
block existed, and outranks the block only when it is demonstrably newer (a
higher sequence) — which covers a downgrade leaving a valid but stale block on
the other page. Neither path runs `o2p_config_valid()`: a probe with silly
heater limits is still a probe that answers at address 7, and the recovery
loader may not be made unreachable for a reason that has nothing to do with
reaching it. The three codes are range-checked on every path regardless, since
a CRC proves the bytes are the ones written, not that this build knows what
baud code 4 means.

**Recovery on a probe potted before this change.** Its loader has no idea the
block exists and will still fall back to the default identity. That is not a
loss of access, but it does mean a recovery host must try **two identities**,
in this order:

1. the configured one, from the probe's commissioning record;
2. **address 3, 9600 8E1** — the loader's fallback.

The knock is harmless at both: a wrong address is answered with silence.
`tools/o2p_update.py` sweeps both — `find_at_fallback_identity()`, reached when
the configured address is silent at every rate — and says loudly which identity
answered, because an operator whose probe has fallen back needs to be told
rather than quietly rescued. It refuses to conclude anything from a well-formed
reply alone: address 3 on a farm cable may be somebody else's instrument, so
the update block's own fields must be in range before the device is treated as
a probe (`looks_like_o2p()`). The sweep asks the **update block**, not the
config registers: the loader refuses everything outside its update window, so a
probe sitting in its bootloader is silent on `BAUD_CODE` at exactly the right
rate — which meant `find_probe()` used to walk away from a bootloader it was
already talking to, at the correct address. It now asks the update block before
concluding anything about the rate. `tools/test_fallback_identity.py` covers
both directions on the host: the fallen-back probe is found, and a stranger at
address 3 with a different register map is not adopted.

Once a probe has been updated to firmware that
writes the block *and* has had its loader reflashed over SWD — which only
happens before potting — identity 2 stops being necessary for it.

### Guard review, in writing

Against the checklist in `~/.claude/CLAUDE.md`, because everything here is a
guard on an operation that cannot be undone from the surface:

1. **Unevaluable input.** A transfer that is short, misaligned, out of order,
   or whose CRC does not match never reaches `STAGED`; a descriptor that fails
   its own CRC reads as "nothing staged", not as a staged image of unknown
   length. `commit_staged(0, 0)` is called *before* the staging slot is erased,
   so an interrupted transfer cannot leave a record claiming a verified image.
2. **Monotonicity.** Worse input never reads better: a truncated image is
   refused by length before its CRC is computed, and an image whose CRC matches
   is still refused if its vector table is not one for the run slot.
3. **Preconditions.** The engine reaches flash only through
   `update_target.c`, which refuses every address outside the staging slot.
   The bootloader's install path is separately bounded to the run slot.
4. **Source of truth.** The declared CRC covers the image; the vector-table
   check covers *which slot* the image was linked for. Measured against the
   real artifacts rather than fixtures: today's `o2probe` image has
   `MSP = 0x20009000`, reset vector `0x0800A06D` — inside the run slot, so it
   passes — and today's `loader` image has reset vector `0x0800161D`, which
   the same check refuses as an application. A CRC alone cannot
   distinguish the application from the bootloader's own binary — which is the
   mistake this catches, and it is tested.
5. **Persistence.** The staged flag is written only after a verify that read
   the bytes back out of flash, and it is cleared by the bootloader only after
   the copy into the run slot has itself been verified. A power loss mid-copy
   leaves both the staged image and the flag intact, and the next boot repeats
   the install.
6. **Provenance.** `UPD_STATUS` reports the state and the last error
   separately, and bit 15 says whether the bootloader or the application is
   answering. `UPD_INSTALLS` counts installs actually completed.
7. **Known-bad calibration.** `test/test_update/` builds each failure — wrong
   CRC, wrong slot, non-Thumb reset vector, truncation, misalignment, overrun,
   duplicate block, out-of-order block, flash failure, descriptor-write failure
   — and observes the refusal. The fake flash refuses a second write to an
   unerased doubleword exactly as the part does, so "acknowledged a duplicate"
   cannot be confused with "programmed it twice".
8. **Fix vs mute.** The engine has no path that clears an error without the
   underlying condition changing: `ERROR` is left only by `BEGIN` or `ABORT`,
   both of which discard the transfer.

### The bench bridge: a spare probe as the RS-485 adapter

Everything above needs a Modbus master on the farm cable, and the usual one is
a USB-RS485 dongle. `pio run -e bridge -t upload` makes one out of a spare,
**unpotted** board instead. The probe already carries the whole adapter: a
THVD1410 on USART1, the direction pin on PC6, and A/B on J1.3/J1.4. What it
does not carry is a way to reach a laptop — so the bridge uses USART2, the
expansion UART, and carries frames between the two verbatim.

The host lead does **not** go to J2. R15 and R16, the 33R series parts between
`UART2_TX`/`UART2_RX` and J2's `EXP_TX`/`EXP_RX`, are DNP (`gen_sch.py:511`),
and so is J2. On an assembled board those two nets stop at the R15/R16 pads,
and those 0603 pads — not the LQFP's 0.5 mm pins — are where the lead goes:

| Lead | Board |
|---|---|
| USB-TTL **RX** | R15 pad, **MCU side** (`UART2_TX`, PA2, LQFP48 pin 13) |
| USB-TTL **TX** | R16 pad, **MCU side** (`UART2_RX`, PA3, LQFP48 pin 14) |
| USB-TTL GND | any GND — J1.2 is the easiest |
| — | J1.3/J1.4 to the probe's A/B, and 12 V to both boards |

**3.3 V logic only.** PA2/PA3 are not five-volt tolerant on this part, so a
5 V FTDI lead damages the bridge board rather than failing visibly.

Then everything that speaks Modbus works unchanged:

```sh
python3 tools/o2p_update.py --port /dev/tty.usbserial-X --bridge   # is it alive?
python3 tools/o2p_update.py --port /dev/tty.usbserial-X --status   # is IT alive?
python3 tools/o2p_update.py --port /dev/tty.usbserial-X .pio/build/o2probe/firmware.bin --boot
```

`--bridge` is the reason the bridge is not purely a wire. A bridge that only
forwarded would be untestable: silence on the port could be the adapter, the
baud rate, the parity, the wiring or the probe, and there would be no way to
tell them apart. So it answers FC03/FC04 for itself at **address 250** with
eight registers — an identity word, the two frame counters, the two drop
counters, and the line settings it was built with. An answer there proves the
whole host half of the chain before any probe is blamed.

What it deliberately is not: a Modbus master, an implementation of the update
protocol, or anything that retries. Every decision stays in
`tools/o2p_update.py`, which is where the diagnostics are. The bridge links
neither the application nor the bootloader — no register map, no drivers, no
update engine, and no flash writes of any kind — so it cannot damage the probe
on the far end of the cable.

Three constraints, all of them checked or asserted somewhere:

* **One master at a time.** The Dragino masters the farm cable. Stretch its
  `AT+TDC` or power it down for the transfer; two masters collide.
* **Nothing may transmit at the bridge while the bridge is transmitting.**
  It is store-and-forward and both sends block, so the traffic model it needs
  is the ordinary Modbus one: a single master that waits for each reply before
  asking the next question. Pipelined requests, or a second master, can arrive
  during a send. A send now drains the *other* port's receiver as it waits
  (`o2p_buart_accumulate`), which closes the window for everything except the
  bus while DE is asserted — there the transceiver's receiver is off, so the
  bytes are gone and the drop counters cannot see them either.

  An earlier version asserted at compile time that the host link was at least
  as fast as the bus, on the reasoning that a slower host could not drain a
  reply as it arrived. That was wrong twice over: the reply is complete and
  buffered before the host send starts, so nothing is drained in real time,
  and a line rate cannot establish a traffic model. The assertion is gone.
  What is asserted instead is that a full 256-byte ADU fits inside the 500 ms
  transmit timeout, which puts a floor of 5,632 baud on either side — below
  it, frames would be truncated mid-send, silently.
* **A bridge board is no longer a probe.** The image takes the whole 128 KiB
  and leaves nothing at `0x08004000`. Making it a probe again is `-e loader`
  then `-e o2probe`, over SWD, exactly like a new board.

### The bridge's second transport: SWD, no lead at all

The serial side above needs a 3.3 V USB-TTL lead and two soldered pads. The
bridge board also has SWD on it already — that is how it got flashed — and the
debug port can read and write SRAM while the core runs. So the same image
carries a second host transport: a 544-byte mailbox at **`0x20000000`** that a
debugger writes frames into and reads replies out of.

```sh
python3 tools/o2p_update.py --swd --bridge      # is the mailbox alive?
python3 tools/o2p_update.py --swd --status
python3 tools/o2p_update.py --swd .pio/build/o2probe/firmware.bin --boot
```

The tool launches OpenOCD itself, with the same invocation that already reads
this board's sensor globals — `interface/cmsis-dap.cfg`, `transport select
swd`, `target/stm32g0x.cfg` — and talks to its TCL RPC port. `--swd-attach`
uses an OpenOCD you started yourself; `--swd-tcl` moves the port. `--baud` and
`--parity` describe the cable, and over SWD the cable settings are the ones
the bridge was compiled with, so the tool says so rather than pretending.

`--swd --bridge` is the cheapest first test of a new bridge board: it proves
the debugger, the mailbox and the frame handling without a single byte
reaching the cable.

**Two rules, and both are about a debugger's freedom to stop the core.**

- **Never halt to read this.** `read_memory`/`write_memory` reach SRAM through
  the MEM-AP with the core running. The sensor-readout recipe halts, for a
  coherent snapshot, and that is right there and wrong here: PC6 is a plain
  GPIO, so a core stopped between `de_assert()` and `de_release()` leaves the
  THVD1410 driving the cable — muting every other node on it, the two SMT100s
  included — until the debugger resumes.
- **The address is pinned, not linked.** The host types `0x20000000`; there is
  no symbol lookup at the far end of a debugger. The mailbox therefore lives in
  its own `NOLOAD` section at the bottom of SRAM, and
  `tools/pio_image_check.py` reads `g_o2p_mailbox` out of the ELF and fails the
  build if it is anywhere else.

The handshake is two sequence words, and the ordering is the whole protocol:
the host fills `tx[]` and `tx_len` and writes `host_seq` **last**; the bridge
sees it change, transmits, collects a reply, sets `rx_len` and `status`, and
writes `target_seq` **last**. Neither side can observe a half-written buffer,
so there is no torn state to reason about — only a transaction that has or has
not been published.

Two things make that claim true rather than merely likely:

- **A data barrier before each publishing store.** `volatile` constrains the
  compiler, not the memory system, and the ordering here has to hold for the
  debug MEM-AP rather than for a second thread. `__DMB()` before `target_seq`
  and before the boot magic is one instruction and removes the assumption.
- **A torn frame is abandoned rather than sent.** Nothing stops a debugger
  writing the mailbox while the bridge copies out of it — a second host, or
  the same tool restarted after a timeout it believed was fatal. So the bridge
  re-reads `host_seq` after the copy, and publishes nothing if it moved; and
  `SwdLink` refuses to connect at all if `target_seq != host_seq`, because
  that means someone else's transaction is already in flight.

| Offset | Field | |
|---|---|---|
| `+0x00` | `magic` | `0x4F324D42`, stamped by the firmware at boot |
| `+0x04` | `version` | |
| `+0x08` | `host_seq` | host writes this last |
| `+0x0C` | `target_seq` | bridge writes this last |
| `+0x10` | `tx_len` | 4..256, or the frame is refused untransmitted |
| `+0x14` | `rx_len` | 0 means nothing answered |
| `+0x18` | `status` | IDLE / REPLIED / SILENT / LOCAL / REJECTED |
| `+0x1C` | `reply_ms` | how long to wait; 0 means the 1 s default, capped at 5 s |
| `+0x20` | `tx[256]` | |
| `+0x120` | `rx[256]` | |

`tools/test_swd_link.py` stands a real TCL RPC server up on a socket in front
of a fake bridge and asserts the ordering, because "written last" is a claim
about what a debugger observes and reading the source cannot establish it. It
runs on every build.

### Guard review, in writing — the bridge's one interception

Address 250 is the only way this image can eat a frame meant for something
else, so the checklist applies to it.

1. **Unevaluable input.** A frame too short to hold a CRC, or one whose CRC
   fails, produces *silence* — not a reply, and not a forward. Its address byte
   is not trustworthy either, so it is not established that it was ever meant
   for the bridge; and a Modbus master is built to survive a timeout.
2. **Monotonicity.** `test_reads_off_the_end_are_refused_and_stay_refused`
   walks the request further and further past the block, including
   `first = 0xFFFF, count = 0xFFFF` where a bound written as `first + count`
   wraps back inside. The verdict never returns to data.
3. **Preconditions.** The address is constrained at compile time to 0 (no
   interception at all) or the reserved 248..255 the specification keeps for
   this, minus 253, which this firmware already uses as its discovery alias.
   Anything in 1..247 would make the bridge swallow frames addressed to a real
   slave, and `_Static_assert` in `bridge_main.c` refuses to build it.
4. **Source of truth.** `tools/check_update_tool.py` now also compares the
   tool's `BRIDGE_ADDR`, `BRIDGE_IDENT` and register count against
   `src/bridge_main.c`. A `--bridge` that asked the wrong address would report
   "no bridge" on a working one, and send someone to look at the probe.
5. **Persistence.** There is none: the counters are RAM, reset with the board,
   and nothing here writes flash.
6. **Provenance.** The identity register is checked by the tool, so "a bridge
   answered" is distinguished from "something answered at 250".
7. **Known-bad calibration.** The drift check was run against a deliberately
   wrong `BRIDGE_ADDR` and a deliberately wrong field count, and reported both.
8. **Fix vs mute.** The dropped-frame counters exist because the bridge
   discards frames with parity/framing/noise/overrun errors rather than
   forwarding bytes already known to be wrong. Discarding them is the mute;
   counting them is what stops it from being one.

The eleven cases in `test/test_bridge/` cover the reply arithmetic — byte
order, CRC placement, partial reads, and every refusal above.

The SWD mailbox adds three guards of its own, on the same terms:

1. **Unevaluable input.** `tx_len` arrives from a debugger writing raw SRAM;
   there is no framing to catch a wrong one. Anything outside 4..256 is
   refused as `REJECTED` and nothing is transmitted — tested at both edges and
   at `0xFFFFFFFF`, where a length that wrapped or was never written must not
   come back to a pass.
2. **Unset is not zero.** `reply_ms = 0` means "the host never wrote this", so
   it becomes the 1 s default rather than "do not wait", which would make
   every transaction report silence. It is capped at 5 s at the other end,
   because the wait holds the bridge and therefore the cable.
3. **Stale state cannot fire a transmission.** The section is `NOLOAD`, so it
   comes up holding whatever the last session or a power-on pattern left.
   `o2p_mailbox_init()` zeroes it before the bus is touched and stamps the
   magic last, so a host that finds the magic has found a mailbox that is
   fully set up — and a `host_seq` left over from a previous session cannot
   look like a new request.
4. **Source of truth.** The layout is pinned to the struct with `offsetof`,
   not described in comments. An adversarial review broke the earlier check in
   one move: swapping two declarations while leaving their comments in place
   passed the layout check, the build, and would have pointed the host at the
   wrong word. The same mutation now fails to compile. The division is that
   the compiler owns struct-to-constant, and `check_update_tool.py` owns
   constant-to-Python; neither can cover for the other.


## Bus settings

9600 8E1, matching the Truebner SMT100s already on this cable
(`tech/RS485-LS-SMT100.md:277`). Default slave address **3** — 1 and 2 are the two SMT100s.

### Reachability is on probation

`SLAVE_ADDR`, `BAUD_CODE` and `PARITY_CODE` are not like the rest of the config
block. Every other register is wrong-answer-shaped when it is set wrong: a bad
RH setpoint makes a bad heater, and you can see it and fix it. These three are
different in kind — set one to something the master cannot follow and **the
master cannot follow**, so there is no channel left to notice the mistake
through, let alone undo it. On a potted probe at the end of a lead with no way
to cut its supply, that is a dig.

So a change to any of the three is applied **on probation** (`src/serial_probation.h`):

- The new settings go live immediately — that is what was asked for.
- If they are not **proven both ways** within **10 s**, the transport is put back.
- Proof is a **two-way exchange**, since firmware version 0x001D.
  When the new settings go live the probe publishes a fresh nonce in
  `PROBATION_NONCE` (`0x000C`) and keeps them only once the master writes that
  value back to `PROBATION_ACK` (`0x000D`), which it can do only if it read the
  nonce, i.e. only if the probe's replies reach it. The echo must arrive at the
  probe's **own unicast address**: a broadcast proves nothing about this probe,
  and the 253 alias is answered at any address.
- Until then, one frame *arriving* at the new settings was the proof, and on
  2026-09-13 that stranded probe 3. A retime to 115200 over the BLE keeper
  delivered the master's confirmation read while every reply was lost; the
  probe confirmed, the master put its end back to 9600, and the probe answered
  nothing until it was power-cycled. A link that works in one direction is the
  link this mechanism exists to undo. `tools/o2p_update.py` therefore refuses
  to retime a probe whose nonce register answers exception 02.
- It reverts to the settings **in flash**, not to the ones the config held a
  moment earlier. A master that raises the baud for a transfer and then puts it
  back performs *two* changes, and under a previous-value rule the second one's
  fallback would be the first one's new value — reverting *away* from the
  master. The stored settings are also where a reset lands, so the timer and
  the reset agree on one recovery state instead of racing between two.
- Only the three fields revert. Anything else the same frame set was accepted
  on its own terms; one mistyped baud code must not silently discard a batch of
  deliberate settings.
- Writing one of the three **its own current value is a no-op** and arms
  nothing. A master rewriting its whole config block touches all three every
  time, and treating that as a change would put a `COMMIT` in the same frame
  behind proof that a five-minute Dragino poll never delivers — so that commit
  could only ever report `FAILED`.

A timer rather than "provisional until `COMMIT`", because the commit would have
to arrive over the very link whose viability is in question — a master that
*cannot* reach the probe could never retract either. The timer is the only
mechanism here that does not depend on the link working.

**`COMMIT` is gated on it.** A commit taken while a serial change is unproven
would put the unreachable settings in flash; the timer would then restore the
RAM config and leave the probe answering at the old rate while flash held the
new — so its very next reset would strand it permanently. `BAUD_CODE` and
`COMMIT` in one frame therefore returns `CMD_RESULT` = `PENDING`, and becomes
`OK` when the new settings are proven or `FAILED` when they are not — and a
revert fails an outstanding commit in *either* queue, including one riding a
calibration, because `finish_o2()` can run after the probation has already
resolved and would otherwise report `OK` for a configuration whose serial
change was undone.

That `FAILED` is byte-identical to the one a worn flash page produces. The
fault word has no spare bit and a new diagnostic register would move the block
the ChirpStack decoder parses, so the two are not distinguishable on the bus
today; what separates them in practice is that this one is read at the *old*
settings. A distinct `CMD_RESULT` code would fix it and is a register-semantics
change, so it is Fab's call rather than a silent one. Whoever
reads that result is by construction talking to the probe at the settings that
work, so the `FAILED` is reachable. The two-frame procedure needs nothing
special: the `COMMIT` frame arrives at the new settings and *is* the proof.

There is no register and no fault bit for a revert — the fault word has no
spare bits and adding a diagnostic register would move the block the ChirpStack
decoder parses. It is observable as `CONFIG_CRC` `0x003F` changing, and as the
probe answering at the old settings.

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
Writes use FC06/FC16 and reach the config block and the updater's two blocks.

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
| 5 | `HEATER_DUTY` | u16 | 0.01 %, **60 s trailing mean** of the duty actually applied (FW v0.36; the last 1 Hz decision before) | — |
| 6 | `FAULTS` | u16 | bitfield | — |
| 7 | `SETTLE_S` | u16 | seconds remaining, 0 = settled | — |

**`HEATER_DUTY` is a 60 s trailing mean since FW v0.36 (`FW_VERSION` 0x25).** The loop decides once a
second, and until 0x0025 this register carried only the last decision; the farm
node reads it every 60 s, so the telemetry was a 1-in-60 snapshot that aliased
(seen live: 0 / 8.5 / 0 / 1.9 %). The format is unchanged. Definition: once per
elapsed second of uptime the firmware samples the duty the hardware layer holds
(`o2p_heater_duty_x100()`, after the stale cut has had its chance), and publishes
the mean of the last 60 samples, rounded half up, clamped to 0..10000. Refused,
stale-cut and forced-off seconds count as the zeros the ring got; a slow cycle
counts as the duty held through it. Under 60 s of uptime the mean covers the
seconds that exist — shorter, never zero-padded; before the first second it is
the instantaneous duty. The window is time-based and nothing a master does
resets it, because several masters share the register. The instantaneous duty
is `HEATER_DUTY_NOW` (`0x0009`) in the heater-law block.

`O2_RAW` is **signed** on purpose: `SCHEMATIC-REVIEW.md` M4 leaves the SGX sign
convention as an open release gate, and the bench air-versus-nitrogen pair is
what settles it. Firmware that took an absolute value would hide the answer.

### Heater-law block — `0x0008`, 2 registers, read-only

This block arrived with firmware version 0x0018.
`HEATER_LAW` says which control law produced this cycle's duty,
because `HEATER_BLOCK` cannot say: its bit 15 is identical for the RH and dew
laws and is omitted on refusing and blind cycles. A separate block rather than
a ninth primary register, so the primary read is byte-for-byte unchanged.

| Reg | Name | Type | Scale | Invalid |
|---|---|---|---|---|
| 8 | `HEATER_LAW` | u16 | law in command (low byte) and flags (high byte) | `0xFFFF` until the heater has been stepped |
| 9 | `HEATER_DUTY_NOW` | u16 | 0.01 %, the duty applied at this cycle's publish (FW v0.36) | `0xFFFF` before the first cycle publishes |

`HEATER_DUTY_NOW` (`0x0009`) is what `HEATER_DUTY` (`0x0005`) meant before FW v0.36. Read it
when the question is "is the ring driven right now" or a tip-loop step response;
`HEATER_BLOCK` is instantaneous too, and pairing it with the 60 s mean would call a
real block "operating" for up to a minute. A read of `0x0008` count 2 is exception
02 on 0x0024 and earlier.

Low byte: 0 RH, 1 OPEN (bench override, open loop), 2 TIP (bench override,
tip loop), 3 TIP_AUTO (stored tip setpoint), 4 DEW (dew margin, high-selected
with the gradient floor - 2 K until FW 0x002D, 4 K since), 5 BLIND (the fallback, not a law), 6 REFUSED (no
law, no drive). High byte bit 8: the dew law has declared its margin
unreachable - margin short with the tip pinned at the dew law's ceiling for
600 s (FW 0x0019) - and the gradient floor is holding the tip.
High byte bit 9 (FW 0x001B): the dew law is configured but has no dew point
this cycle - humidity lost, typically during the SHT45 de-creep - so its own
demand is withheld and only the gradient floor is regulating.
High byte bit 10 (FW 0x001F): a runaway latch is in force while the tip and
cell still read, so the dew law's demand is withheld and only the gradient
floor runs - a false latch set by environmental heat no longer ends
anti-condensation heat. Since FW 0x001A
that ceiling is the lower of 79 C and the cell side plus the envelope, so on a
bench probe the verdict usually lands a few kelvin above the cell, not at 79 C.

### Probation block — `0x000C`, 2 registers

This block arrived with firmware version 0x001D.
It carries the two-way proof a serial-settings change needs before the probe
keeps it; see *Reachability is on probation*.

| Reg | Name | Access | Meaning |
|---|---|---|---|
| 12 | `PROBATION_NONCE` | R | nonce of the running probation; 0 when none is running |
| 13 | `PROBATION_ACK` | W | write the nonce back at the new settings; reads 1 while the proof is held |

A write of any other value, or any write while no probation is running, is
refused with exception 03 and confirms nothing; the nonce register itself is
read-only. Reading the acknowledgement back is how a master resolves an echo
whose reply was lost.

### Diagnostic block — `0x0010`, 32 registers, read-only

`VREF_MON_MV`, `VA_MON_MV`, `VIN_MON_MV`, `AFE_VOUT_MV`, `DEW_MARGIN` (i16,
0.01 K), `PRESSURE_HPA` (0 — BMP390 is DNP), `UPTIME_HI/LO`, `FW_VERSION`,
`HW_REV`, `RESET_CAUSE`, `LMP_READBACK` (TIACN<<8 | REFCN as actually read),
`MB_CRC_ERRS`, `MB_FRAME_ERRS`, `I2C_ERRS`, `EXP_DATA` (`0xFFFF` if absent; external TMP117 on ext I2C in 0.01 C),
`SETTLE_RESTARTS` (`0x0020`), `SAMPLE_SEQ` (`0x0021`), `T_DIE` (`0x0022`),
`FAULTS_EVER` (`0x0023`), `ADS_FAIL_COUNT` (`0x0024`), `WE_BUF_MV` (`0x0025`),
`RE_BUF_MV` (`0x0026`), `CELL_BIAS_MV` (`0x0027`), `BUILD_ID_HI/LO` (`0x0028`/`0x0029`),
`CMD_RESULT` (`0x002A`), `CAL_STATE` (`0x002B`), `T_AFE` (`0x002C`), `CE_MV` (`0x002D`),
`HEATER_BLOCK` (`0x002E`), `SAMPLER_TIMING_MS` (`0x002F`).

Two of those deserve their own notes:

- `RESET_CAUSE` (`0x001A`) is `(RCC_CSR >> 24) & 0xFF`, a **bitfield**, not an
  enumeration — two causes can be set at once. `0x14` = PIN|SFT is a software
  reset with the NRST pulse riding along (observed 2026-09-10 on a deliberate
  update BOOT); `0x0C` = PIN|PWR is an ordinary power-cycle. Bits: 1 OBL,
  2 PIN, 3 PWR, 4 SFT, 5 IWDG, 6 WWDG, 7 LPWR (`mcu.h:27`). `0xFFFF` is the
  sentinel for an application under a bootloader that cleared CSR without
  parking it.
- `WE_BUF_MV`/`RE_BUF_MV` (`0x0025`/`0x0026`) read their `0xFFFF` sentinel
  **always on Rev A**: `O2P_HW_BIAS_ADC_REACHES_ELECTRODES` is 0 there — AIN2
  and AIN3 are wired to `/ADC_VA_MON` and `/ADC_VIN_MON` instead, so those
  registers have no measurement behind them on this board at all (the rail
  data reaches `va_mv`/`vin_mv`). They come alive only on Rev B. Reading them
  for a verdict on a Rev A probe is reading a compiled-out path — noted
  2026-09-10 after two nights of bench notes treated `0xFFFF` there as
  residual AFE trouble.
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
- `T_DIE` `0x0022` — MCU die temperature, i16 0.01 °C, `0x8000` invalid. Not
  an ambient reading and not part of the oxygen path: it is the silicon,
  self-heating included, specified to about ±5 °C. It is published because it
  is the only temperature on the board that does not come over I²C1. `T_TIP`
  and `T_CHAMBER` share a bus; this does not. When they disagree with it, or
  vanish while it survives, the fault is the bus rather than the weather.
- `FAULTS_EVER` `0x0023` — every fault bit seen since power-up, never cleared.
  `FAULTS` says what is wrong *now*; that is the right thing to act on and the
  wrong thing to diagnose from, because a probe that glitched once last month
  and one glitching every hour both read clean between events. This register is
  the difference between them.
- `ADS_FAIL_COUNT` `0x0024` — cycles in which the ADS1119 delivered no
  conversion at all, saturating at `0xFFFF`. The latch on `FAULTS` guarantees
  such an event is *seen*; this is how often. A rate is what separates a one-off
  from a failing part, and since the latch self-clears the count would otherwise
  be lost.

- `WE_BUF_MV` `0x0025`, `RE_BUF_MV` `0x0026`, `CELL_BIAS_MV` `0x0027` — the
  buffered cell electrodes on ADS1119 AIN2/AIN3, in millivolts at the pin, and
  the bias between them (`WE - RE`, i16, `0x8000` invalid). This is the
  differential cell-bias telemetry DESIGN.md has always specified and nothing
  implemented. It is the channel that separates *the cell changed* from *the
  measurement changed*: a potentiostat whose counter electrode runs out of
  headroom walks its working point off target while every other register stays
  plausible. Sampled **after** the oxygen channel, deliberately — putting them
  before it would change which channel the mux leaves when it converts AIN0,
  and that is the leading suspect for the 0.51 % step in `O2_RAW` across the
  2026-09-07 install. Telemetry that exists to explain a number must not be
  able to move it.

- `CMD_RESULT` `0x002A` — command outcomes, one byte each: the high byte for
  the last calibration trigger, the low byte for the last commit.
  `0` none, `1` pending, `2` OK, `3` failed.

  A successful Modbus write only means the *request* was accepted. A
  calibration is still refused if the cell is settling or the gas temperature
  is missing, and a flash store can fail; all three used to look identical to
  the master, and a power cycle before the next conversion took the
  calibration with it. Commissioning is therefore: write `CAL_TRIGGER`
  (and `COMMIT` in the same frame to persist), poll `CMD_RESULT` until neither
  byte reads `1`, and require `2` in both before treating the probe as
  calibrated. Each byte latches until that command is issued again.

  It sits at `0x002A` rather than beside the other status registers because
  `0x0022`..`0x0029` are a published contract the ChirpStack decoder already
  parses — a status word inside that range would decode as a die temperature.
- `T_AFE` `0x002C` — LMP91000 die temperature, i16 0.01 °C, `0x8000` invalid.
  The AFE's own silicon, and the only register that reports it. `T_DIE`
  (`0x0022`) is the MCU, at the other end of the board: on 2026-09-08, with
  the ring heater holding `T_TIP` at 78.00 °C, the MCU die sat at 49 °C — a
  29 K gradient across one PCB — so neither `T_TIP` nor `T_DIE` is the AFE's
  temperature.

  It matters because the published cell current is
  `(0.67·VREF − VOUT)/R_TIA` with `R_TIA` a hardcoded 7000 Ω, and SNAS506I
  specifies that resistor's **accuracy** (5 %) while publishing no temperature
  coefficient for it and no gain-versus-temperature curve — checked against
  Rev I, whose 35 figures contain neither. Every other term in the chain is
  bounded and small: the ADS1119 contributes at most 2 ppm/K of gain drift
  (SBAS925A), `TcVOS_RW` is 8 µV/K at the configured 24 % bias, and VREF cancels because
  the internal zero and the ADC reference are the same rail. `R_TIA` is the
  single uncharacterised term, and it drifts with *this* temperature. A
  tempco fitted against `T_TIP` therefore contains the AFE's drift scaled by
  whatever fraction of the tip's excursion the AFE actually saw; this
  register is what measures that fraction.

  Sampled in its own phase after the electrodes, with the part in `OP_MODE`
  111 — temperature on VOUT, TIA still powered, so the cell is never unbiased
  and the DS-0637 settling penalty is never incurred. Both the entry and the
  exit verify the `MODECN` readback, because the oxygen channel's own swing
  (930–970 mV) decodes as a plausible 72–77 °C: no value check can tell a
  failed mode switch from a real reading, only the readback can.
- `CE_MV` `0x002D` — `CELL_CE_DRV` in mV, u16, `0xFFFF` invalid. The
  potentiostat's **control effort**, and the register that names which hardware
  fault you have.

  A1 drives the counter electrode until the reference electrode sits at the
  commanded bias, and that loop closes *through the cell*. If the cell is
  absent, high-impedance or on bad leads — or if A1 is dead, as it was on
  2026-09-04 — A1 has no feedback and CE rests against a rail while
  `TIACN`/`REFCN`/`MODECN` still read back exactly as written. `LMP_READBACK`
  cannot see that. `CELL_BIAS_MV` shows the symptom; this shows the cause.

  SNAS506I 6.5 characterises A1's drive only over 300 mV ≤ V(CE) ≤ VS−300 mV,
  so outside `O2P_HW_CE_COMPLIANCE_MIN/MAX_MV` the amplifier is not specified
  and the reading raises `AFE_CONFIG_MISMATCH` rather than being published as a
  measurement.

  Not in the node's poll window, deliberately, for the reason `CMD_RESULT` and
  `CAL_STATE` are not: at 96 bytes that frame has 4 bytes of DR3 headroom left,
  and this is a bench question answered by a laptop on the bus in the same
  session that asks it. The fault reaches the radio; the millivolts do not need
  to.
- `CAL_STATE` `0x002B` — calibration completeness, a bitfield: bit 0 the air
  point is the datasheet nominal rather than a measurement, bit 1 no zero
  point has ever been taken. A register rather than two fault bits because the
  16-bit fault word is full, and because these are commissioning state, not
  faults: a probe with no zero point is unfinished, not broken, and it still
  measures.
- `BUILD_ID_HI` `0x0028`, `BUILD_ID_LO` `0x0029` — which binary is running.
  Bit 31 the working tree was dirty at build time, bit 30 a debug build
  (`O2P_DEBUG_ENABLE=1`, set by `src/regmap.c`; clear on `env:o2probe_nodebug`),
  bits 29..28 reserved, bits 27..0 the 7-hex-digit commit prefix. `FW_VERSION` cannot do this job: it is a
  hand-edited constant that read v0.1 on every probe ever built, through
  every install, which is why the 0.51 % step in `O2_RAW` across the 2026-09-07
  install could not be attributed to an image. `tools/pio_build_id.py` stamps it
  from `git rev-parse --short=7 HEAD` and **fails the build** if git cannot
  answer, rather than defaulting to zero: an unidentifiable image on a potted
  probe is exactly what this register exists to prevent. Zero means *no stamp*,
  which after this commit is only the host test build, and is never reported as
  a commit. `FW_VERSION` is now bumped only when the wire contract changes, and
  is `0x000A` for this 27-register block.

### Config block — `0x0030`, 29 registers, read/write, flash-backed

- `CAL_ZERO_NA_HI` `0x0046`, `CAL_ZERO_NA_LO` `0x0047` — cell dark current,
  i32 nanoamps, **signed**. Subtracted from every measured current *and* from
  the air point before `K` is derived, because the cell law is
  `I = I0 + K·ln(…)`: `I0` is an offset, and folding it into `K` turns it into
  a slope error. DS-0637 rates the zero at `< 0.4 %vol O₂`, which is roughly
  2 % relative at the air point but about 8 % at 5 %vol — where compost
  control acts. `0` is both a legitimate measured zero and the never-measured
  default; `CAL_STATE` bit 1 is what separates them.
- `HEATER_STORAGE` `0x004C` (FW `0x002B`) — **permission for the dry-air idle
  gate**, and the last byte of the config record. **Since FW `0x002C` the probe
  clears this itself once it has been in a pile** — cell ≥ 50.00 °C **OR**
  chamber RH ≥ 95.00 %, whichever comes first, written to flash so a human must
  grant it again. OR and not AND: above 37.00 °C the pile lockout has already
  released the gate, so the floor is running and the heater has collapsed the
  RH the sensor reports (measured under 90 % for 238 of 270 samples in the
  2026-09-17 windrow), and an AND could not fire where it is needed. Only the magic `0x5A` lets
  the gate withhold the gradient floor; `0` — the default, and the result of
  every layout migration — forbids it, and the probe heats exactly as it did
  before FW `0x0027`. Anything else is refused on the wire, and a stored record
  holding neither value is rejected **whole** rather than read as field mode.
  It is commanded rather than inferred because the gate's own conditions cannot
  tell dry gas from a wetted SHT45 reading low, and the `35.00 °C` cell lockout
  added in `0x002A` separates the probe from a **hot** pile only — a curing heap
  sits near ambient. **No layout bump:** it takes v8's last reserved byte at
  offset 47, so the CRC does not move and no migration runs. That also means a
  same-layout reflash KEEPS the flag — `config_migrate.c` is only on the path
  when `layout_version` differs, so the operator clears this, not the installer.
- `VIN_DIV_X1000` `0x004B` (FW `0x0014`) — the board's **own** input-rail
  divider ratio × 1000, flash-backed (write, then `COMMIT`). `0` = the generated
  netlist divider (Rev A R26/R27 130k/20k = ×7.5, Rev B 91k/10k = ×10.1);
  `2000..20000` scales `VIN_MON_MV` by that ratio on either revision; anything
  else is refused. It exists because Probe 3 (Rev A) carries 82k/10k (×9.2) and
  published its metered 13.11 V input as 10.71 V (2026-09-11,
  `CELL-AFE-DEBUG.md`) — a per-board fact, so it lives in the board's flash and
  not in the generated `hw_caps_rev_a.h`. **No layout bump:** the value sits in
  two formerly reserved bytes (offsets 31 and 35) that every older record holds
  as zero, so a reflash keeps the heater consents, the O₂ calibration and the
  transport. A stored value outside the window does not fail the record (that
  would reset the address); it scales by the netlist and reads back as stored.

`SLAVE_ADDR`, `BAUD_CODE`, `PARITY_CODE`, `RH_SETPOINT`, `DT_MAX_K`,
`HEATER_MAX_DUTY`, `HEATER_PWM_HZ`, `CAL_AIR_NA_HI/LO`, `CAL_TEMP_C100`,
`TEMPCO_PPM_K`, `SHT_PULSE_H`, `SHT_PULSE_TRIG`, `CAL_TRIGGER`, `COMMIT`,
`CONFIG_CRC` (read-only), plus the two PI gains, both in 0.01 units:

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
an absolute temperature, unattended.

**Consent is enduring, and the sentinel does not revoke it.** Writing `0x8000`
to `TIP_SETPOINT` stops the loop, but `HEATER_TIP_CONSENT` keeps its magic
across that write and across a reset — so a later setpoint write alone restarts
an unattended loop. **To revoke, write `0` to `0x004A`.** The two registers are
independent on purpose: consent answers "may this probe ever hold a temperature
by itself", which is an operator's standing decision, while the setpoint answers
"which temperature, now". Coupling them would mean every routine setpoint change
silently re-asked a question that had already been answered. Found by review
2026-09-08, where the earlier wording here promised revocation the code does not
perform.
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

Keeping `NO_CHAMBER` live has a consequence that had to be handled separately.
`cycle_begin()` invalidates the chamber **and** the humidity, and the scheduled
SHT45 de-creep pulse then masks both for `O2P_SHT_RECOVERY_MS`. Without help the
persistent loop would therefore stop for the whole mask, on a schedule, several
times a day — a loop that refuses intermittently for a reason invisible from
outside, which is worse than one that refuses consistently. `main.c` bridges the
**chamber temperature only** from the same cache the oxygen path uses, bounded by
its own bound, `O2P_HEATER_CHAMBER_MAX_AGE_S` (45 s). Past that bound the reading
stays invalid and `NO_CHAMBER` fires again, so a genuinely dead SHT45 still
blocks the heater.

**That is a separate constant as of 2026-09-09, and briefly it was not.** The
mask went from a guessed 30 s to a measured 350 s
(`SHT-DECREEP-MASK-IS-TOO-SHORT.md`), and the oxygen cache bound was raised
45 → 400 s to cover it — which silently extended this thermal interlock's
reference to ~3.6 τ of the chamber's ~110 s time constant. A clamp compares a
fresh measurement against its reference, so staleness there does not add noise,
it *moves the trip point*: a cached 60 °C against an actual 55 °C turns a real
+4 K excursion into a computed −1 K and the clamp does not fire. Both bounds are
back to 45 s, under separate names so an oxygen data-age policy can never again
move a heater interlock. The cost is that the tip loop now stands down for the
remainder of each mask alongside the RH loop; that is the accepted side of the
trade, and on Rev A this block is measured inert anyway.

The operational consequence is the honest one to state: **the RH loop now
stands down for 350 s after every scheduled pulse, not 25 s** — about 1.2 % of
the time at the default 8 h interval. It is visible on the bus as `NO_RH` in
`HEATER_BLOCK` (0x002E), the tip loop keeps running throughout on the bridged
chamber temperature, and refusing remains the right answer rather than merely
the cautious one: the pulse drives measured RH *low*, so a loop regulating on it
would read the chamber as drier than it is and under-heat — the direction that
condenses.

The humidity is deliberately **not** bridged. Chamber temperature moves on
minutes and is an *input to a clamp*; relative humidity is the RH loop's
*controlled quantity* and is the very thing the pulse perturbs. Substituting a
cached value for a clamp's reference is not the same act as substituting one for
the quantity you are regulating, so the RH loop keeps refusing exactly as before.
Found by review 2026-09-08.

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


| Reg | | |
|---|---|---|
| `0x0040` | `HEATER_KP` | proportional gain |
| `0x0041` | `HEATER_KI` | integral gain, per second |

…the water-vapour and pressure fields, and the cell's dilution efficacy:

| Reg | | |
|---|---|---|
| `0x0042` | `ASSUMED_P_HPA` | total pressure now, hPa (no barometer on Rev A) |
| `0x0043` | `CAL_AIR_FRAC` | O₂ fraction present at the air point, %vol × 1000 |
| `0x0044` | `CAL_P_HPA` | total pressure then, hPa; 0 = unknown |
| `0x0045` | `DIL_ALPHA` | dilution efficacy × 1000; 1000 = full gas law |

`DIL_ALPHA` is the fraction of the modelled water-vapour dilution the cell's
current actually shows, so the factor applied is
`f_eff = 1 − α·(1 − (P−p_w)/P)` rather than `(P−p_w)/P`. The 2026-09-07 sweep
measured `α = 0.453 ± 0.052` on this cell against a separately identified
tempco of `+0.284 ± 0.014 %/K` (`O2-HUMIDITY-CORRECTION.md` §15). The same α
appears in the air point's fraction and in the measurement — K is fixed against
the first, so if the two sides disagreed the difference would land on every
reading as gain error. Default 1000, which is the plain gas law and is
bit-for-bit what earlier firmware did; **not** 453, because that is one cell's
coefficient and a default is a claim about every cell.

Writing it **restates** `CAL_AIR_FRAC` under the new α rather than discarding
it. The stored fraction is `C_air · f_eff(α_old)` and K is fixed against it, so
leaving it alone would rescale every later reading by the ratio — but nothing
has to be re-measured, because `f_eff = 1 − α·(1−f)` inverts exactly:

```
α_old·(1−f) = 1 − air_frac_old / C_AIR
air_frac_new = C_AIR · (1 − (α_new/α_old)·(1−f)·α_old)
```

So **no recalibration is needed**, and the register is safe to write in any
order — including inside a whole-block FC16, where `0x0043` is applied before
`0x0045` and a zeroing implementation would have silently dropped the
calibration the same frame supplied. The one uninvertible case is `α_old = 0`:
at α 0 the stored fraction is `C_AIR` whatever the humidity was, so `(1−f)` is
gone and the field falls back to 0, "unknown". Identifying α still takes two
disjoint bench legs and cannot be derived from anything a buried probe sees.

The gains are registers on purpose. The plant is unmeasured — the thermal path
is an engineering bound, not a measurement — so they will need tuning against a
real pile, and the alternative to a register write is a full firmware transfer
through the updater and a reset. Bounded at 100.00 each: `kp` of
100 already saturates the duty clamp on a 1 %RH error, and a 1 W heater against
a membrane is not the place to discover a fat-fingered write. Zero is legal —
`kp = 0` with `ki > 0` is a pure integrator, reasonable on a slow thermal
plant, and both zero simply means the loop never asks for heat.

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

### Heater test block — `0x0060`, 5 registers, read/write, volatile

Open-loop bench override for the membrane ring. Exists because the RH loop
refuses to drive without a humidity signal and clamps to `DT_MAX_K`, and
characterising the thermal plant needs neither.

| Reg | Name | Access | Meaning |
|---|---|---|---|
| `0x0060` | `HEATER_TEST_ARM` | rw | write `0x8EA7` to arm; any other value disarms; reads `1`/`0` |
| `0x0061` | `HEATER_TEST_DUTY` | rw | duty when no target is set, 0.01 %, clamped to the configured maximum |
| `0x0062` | `HEATER_TEST_TIP_SP` | rw | tip setpoint, i16 0.01 °C; `0x8000` = none → open loop. Max 79.00 °C |
| `0x0063` | `HEATER_TEST_KP` | rw | tip-loop proportional gain, 0.01 units (default 50.00) |
| `0x0064` | `HEATER_TEST_KI` | rw | tip-loop integral gain, 0.01 units/s (default 0.50) |

Volatile: not in flash, not covered by `CONFIG_CRC`, not reachable by
`COMMIT`, cleared by reset and brownout.

Suppresses `NO_RH`, `NO_CHAMBER` and `DT_LIMIT` only. Still enforced: the
TMP117 therm-mode cutoff, a valid tip reading, the 80.00 °C absolute tip clamp
(release 75.00 °C), rail faults, the runaway latch, the PA7 pin-integrity
assertion, and the configured duty maximum — zero there still means off.
Runaway accumulation pauses while armed so that an external heat source cannot
latch it mid-run; the latch is never cleared by this mode.

**Procedure — hold the tip at a temperature (preferred).**

1. Write a nonzero duty maximum to `0x0035` (defaults to zero, and zero
   disables the heater outright). Do **not** `COMMIT` unless the probe should
   keep it.
2. Write `0x0062` = setpoint in 0.01 °C, e.g. `7800` for 78.00 °C. The maximum
   accepted is 79.00 °C, a kelvin below the absolute clamp.
3. Write `0x0060` = `0x8EA7`.
4. Watch `T_TIP` (`0x0002`) and `HEATER_DUTY_NOW` (`0x0009`; `HEATER_DUTY` `0x0005` is its 60 s mean since FW v0.36). Duty should ride high,
   then taper as the tip approaches the setpoint and settle at whatever holds
   it. `T_TIP` reaching 80.00 °C means the loop failed — the clamp is a
   backstop here, not the mechanism.
5. Disarm by writing anything else to `0x0060`, or by power-cycling.

Retune with `0x0063`/`0x0064` while armed; the gains are provisional because
the plant has never been measured. Slow approach → raise `0x0063`. Standing
offset below setpoint → raise `0x0064`. Overshoot or hunting → lower both.

**Procedure — fixed duty, no temperature target.** As above, but write `0x0062`
= `0x8000` (or leave it, that is the reset value) and set `0x0061` to the duty.
The tip then runs to the 80.00 °C clamp and oscillates down to 75.00 °C. Use
this to measure what the ring can do, not to hold a temperature.

If `HEATER_DUTY_NOW` stays zero, read `HEATER_BLOCK` in the diagnostic block for
the reason — it reports every interlock at once rather than the first.

### Debug blocks — debug builds only

Compiled in with `O2P_DEBUG_ENABLE=1` (`env:o2probe`, `env:o2probe_revb`).
`env:o2probe_nodebug` compiles all four out, and every address in them then
raises exception 02 like any other undefined register; `BUILD_ID` bit 30 says
which kind of image is answering. Design, and the Cortex-M0+ rules the peeks
obey: `doc/PLAN-MODBUS-DEBUG.md`.

| Block | Declared as | Purpose |
|---|---|---|
| Memory peek mailbox | `0x0065`, 11 registers, read/write, volatile | 1..4 words per trigger |
| Sensor diagnostic mailbox | `0x0070`, 7 registers, read/write, volatile | typed AFE/ADC/sensor register reads; MCU pin state (opcode 8, see below) |
| Crash context | `0x0077`, 9 registers, read/write, retained | last HardFault, assert or IWDG record |
| Wide peek block | `0x0100`, 65 registers, read/write, volatile | 1..30 words per trigger, snapshotted |
| Arbitrary code execution mailbox | `0x0150`, 72 registers, read/write, volatile | Thumb-2 execution in SRAM with watchdog and fault interceptor |
| Memory poke mailbox | `0x0198`, 12 registers, read/write, volatile | 1..4 words per trigger, payload in the trigger frame — the WRITE counterpart of the peek |
| Wide poke block | `0x01B0`, 65 registers, read/write, volatile | 1..30 words per trigger, payload in the trigger frame |

Both peeks read only SRAM `0x20000000`–`0x20008FFC`, flash
`0x08000000`–`0x08010FFC`, the three UID words at `0x1FFF7590`–`0x1FFF7598`
and the flash-size word at `0x1FFF75E0`, on 4-byte boundaries, and a burst must
lie wholly inside the region it starts in. Anything else is refused with a
status and is never dereferenced: on this core a bad load is a HardFault.

The flash window is the loader and run slot only (pages 0–33), **not** the
whole 128 KiB, from firmware `0x000F`. The staging slot, the boot descriptor
and the config pages are written at run time, and a doubleword left
half-programmed by a power loss raises an ECC NMI when read that the default
handler does not survive (RM0444 Rev 6 §3.3.3/§3.3.6). A peek of those pages
answers `ERR_RANGE`; the running image's own pages are intact by definition.
It is a mitigation, not a proof — see `doc/PLAN-MODBUS-DEBUG.md` §3.6, and §11
for the boot-path reads that carry the same risk and are not fixed. On `0x000E`
and earlier the window was the whole 128 KiB.

The snapshot copy is overlap-safe from `0x000F`: a peek that names the SRAM the
copy writes into (`g_rm`'s own buffer) used to come back corrupt with status
OK, and now copies in the safe direction (review N1).

From firmware `0x000F`, if the part's `RAM_PARITY_CHECK` option bit is enabled
(`FLASH_OPTR` bit 22 reads 0), an SRAM burst must also lie inside `.data` or
`.bss`. Anything else answers status 4, ERR_PARITY, unread, because with parity
on, reading SRAM nothing has written since power-on can raise NMI and a
HardFault (RM0444 Rev 6 §2.3). The bit is disabled from the factory, and
nothing in this firmware changes it, so on these probes every peek answers as
it did under `0x000E`. Rule and reasoning: `doc/PLAN-MODBUS-DEBUG.md` §3.5.

#### Wide peek block — `0x0100`

One FC16 of exactly three registers at `0x0100` — address high, address low,
word count 1..30 — takes the whole burst in one go, with interrupts masked for
the copy, and holds it. One FC03 of 65 registers then returns all of it: a
135-byte reply. Because the words are a snapshot, a transport too narrow for
that reads the same snapshot in several pieces, and nothing the sampler
publishes in between can tear it.

| Reg | Name | Access | Meaning |
|---|---|---|---|
| `0x0100` | `PEEKW_ADDR_HI` | rw | trigger: target address, high word; reads the address held |
| `0x0101` | `PEEKW_ADDR_LO` | rw | low word |
| `0x0102` | `PEEKW_WORDS` | rw | trigger: words, 1..30; reads the count held |
| `0x0103` | `PEEKW_STATUS` | ro | 0 none, 1 OK, 2 out of range, 3 misaligned, 4 SRAM not provably written on a part with RAM parity checking enabled (firmware `0x000F`+; see below) |
| `0x0104` | `PEEKW_SEQ` | ro | triggers executed; skips 0 on wrap, so 0 means never |
| `0x0105` | `PEEKW_DATA` | ro | word 0 high, word 0 low, word 1 high, … up to `0x0140` |

- Any other write touching the block, and a count of 0 or above 30, is
  **exception 03 and changes nothing** — address, count, status, sequence and
  data still describe the previous trigger.
- A well-formed trigger always replaces the result: with the data, or with a
  status saying why there is none. Data past the requested count, and all of
  it when the status is not OK, reads `0xFFFF`.
- A reader that needs more than one FC03 reads the sequence register with its
  first piece and again after its last. If it moved, another master peeked in
  between and the pieces do not belong together.

How much of the block one read carries, by the largest reply ADU on each path
(read from the code 2026-09-10, not measured on a cable):

| Path | Largest reply | One FC03 carries |
|---|---|---|
| USB-RS485 dongle, SWD bridge mailbox, node USB serial relay | 255 B | everything |
| Node LoRaWAN relay, reply uplinked at DR4/DR5 | 227 B | everything |
| … at DR3 | 100 B | header + 21 words |
| … at DR0–DR2 | 36 B | header + 5 words |
| Dragino RS485-LS `A8` (46-byte uplink data, unverified) | 46 B | header + 7 words |

The radio rows are EU868's 242/115/51 application bytes (RadioLib 7.7.1
`payloadLenMax`) less 15. The node uplinks the reply ADU as it is, and
RadioLib's `getMaxPayloadLen()` subtracts whatever MAC answers are pending in
`FOpts`, up to 15 bytes. A master cannot see those, so it plans for the full
15. This table said 242/115/51 until an independent review on 2026-09-10.

The trigger itself is 15 bytes, inside the `A8` ceiling. The radio drops an
oversized reply rather than truncating it: the node logs `PACKET_TOO_LONG`
and never sends it. So `--max-adu` in `tools/o2p_cli.py peek` is a ceiling to
respect, not a hint.

`tools/o2p_cli.py peek SYMBOL` uses this block when `FW_VERSION` (`0x0018`)
reads `0x000D` or later, and the 4-word mailbox when it is older. If the block
answers exception 02 anyway, the tool says so and tries the mailbox. That
serves an image without the wide block, but not a nodebug build: there
`0x0065` answers exception 02 as well, and the tool reports **debug blocks
compiled out** and exits 1. It reads the ELF symbol's size by default
(`--bytes`/`--count` override), and refuses a name that several objects share
(file-local statics in two source files; it lists their addresses to peek
instead). It rounds an unaligned symbol out to whole words, splits the reads
to fit `--max-adu` (`auto`, `dongle`, `swd`, `node`, `lorawan-dr4`,
`lorawan-dr3`, `lorawan-dr0`, `a8`, or a number), plans them before it sends
the trigger, and refuses the result if the sequence register moved between
pieces.
`tools/test_o2p_cli_peek.py` checks all of that host-side, against
`src/regmap.c` and `src/modbus_pdu.c` compiled into `tools/peek_oracle.c`
rather than against a Python imitation of them. Nothing in it has run against
a probe.

On the narrow path it also sizes the burst to `--max-adu`: the 4-word mailbox
reply cannot be split, so a low ceiling caps how many words one trigger asks
for (two under `--max-adu 19`), and a ceiling too small for even one word is
refused before any trigger goes out.

**The 4-word mailbox at `0x0065` assumes sole ownership for the trigger/read
pair.** It echoes the target address but not the word count, so a shorter peer
peek at the same address, arriving between another master's trigger and its
read, returns `0xFFFFFFFF` unused-slot padding that the reader cannot tell from
memory (and `0xFFFFFFFF` is also erased flash, so value cannot tell). There is
no in-contract fix that closes this: re-reading the mailbox header carries no
count either. The wide block at `0x0100` echoes both the word count and a
sequence number and is used instead whenever `FW_VERSION` allows; when the tool
must fall back to the mailbox it prints that the result assumes no other
master. On a shared bus, prefer the wide block.

#### ADS1119 internal-reference override — opcode 9 (`OP_ADS_INTERNAL_REF`)

Firmware `0x0015` and later, debug builds only, **volatile** (every reset
clears it). Added 2026-09-11 on Fab's order: "let it use the internal ref for
all channels now, for debugging. the external ref is down".

Normally only VREF_MON converts against the ADS1119's internal 2.048 V
reference; AFE_VOUT, T_AFE and AIN2/AIN3 (VA_MON/VIN_MON on Rev A, WE/RE on
Rev B) convert against the external `/VREF_TRIM` and are scaled by the
measured VREF, so they go invalid whenever that reference collapses. With the
override set, every conversion uses the internal reference and is scaled by
2048 mV, and the rail and die-temperature channels no longer wait for a
measured VREF. `O2_RAW` still requires one: the LMP91000's internal zero is
0.67 × the analog reference, so in this mode the current is **not
ratiometric** and a VREF error lands in it instead of cancelling. Full scale is
2048 mV; a clipped conversion still refuses.

One FC16 of two registers:
`DIAG_CMD` (`0x0070`) = `0x5A09`, and
`DIAG_PARAM` (`0x0071`) = 1 (override on) or 0 (normal). Served inside the write: status
2 OK, `DIAG_RDATA0` echoes the value now in force. Any other PARAM, or a
one-register write, is exception 03 with `DIAG_STATUS` = 3 and changes nothing.
`main.c` latches the flag at the start of the next measurement cycle. Through
the farmgw keeper: `diag 9:1` / `diag 9:0`. The flag itself is
`o2p_regmap_t.ads_internal_ref`, a `uint32_t` in `.bss`, so the poke mailbox
can write it as well.

#### Pin state — opcode 8 (`OP_READ_GPIO`) in the sensor diagnostic mailbox

Firmware `0x000E` and later, debug builds only. It reads what one MCU pin is
really doing: its mode, pull, output type, alternate function, output latch and
level, plus its whole port's input and output registers. It is strictly
read-only: no mode, pull, output or clock register is written. It exists
because PB1, the ADS1119's DRDY input, once sat unconfigured in analog mode,
read 0 whatever the pin did, and got a healthy ADC replaced
(`../PIN-IDENTITY-POSTMORTEM.md`).

One FC16 of two registers:
`DIAG_CMD` (`0x0070`) = `0x5A08`, and
`DIAG_PARAM` (`0x0071`) = port × 256 + pin,
where port A = 0, B = 1, C = 2, D = 3, F = 5 (there is no port E). Then read
`DIAG_STATUS` (`0x0072`) through `DIAG_CRC_STATUS` (`0x0076`). The result is
ready when the write is acknowledged; this opcode never reports PENDING.

While an I²C opcode (1–7) is queued, every well-formed write to the mailbox,
this one included, is refused with **exception 06** (busy) and changes
nothing: the queued command's `DIAG_STATUS` stays PENDING until it has run.
Retry. Firmware `0x000E` and earlier refused with exception 03 and wrote
`DIAG_STATUS` = 6 ERR_BUSY over the queued command's PENDING. A master polling
such a probe must not take 6 as its own command's result, and
`tools/o2p_cli.py` does not.

PF2 is the NRST pad. Its GPIO registers describe that pad only when the
`NRST_MODE` option bits select GPIO (RM0444 Rev 6 §7.3.17). The factory
setting is reset I/O, and nothing in this firmware writes option bytes, so a
PF2 answer describes a GPIO cell that is not connected to the pin. Port F is
unclocked today anyway, so PF0–PF2 all answer 8.

| Status | Meaning |
|---|---|
| 2 OK | level sampled; every field is real |
| 7 GPIO_NOT_SAMPLED | the pin is in **analog mode**, so it has no level. RM0444 Rev 6 §7.3.13: IDR reads 0 in analog mode whatever the voltage. Mode, pull and AF are still reported. **Not a LOW.** |
| 8 ERR_GPIO_UNCLOCKED | the port's clock is off. The firmware clocks A, B and C only; nothing on the port was read and no clock was enabled |
| 9 ERR_GPIO_NO_PIN | not a pin on this LQFP48, per DS12232 Rev 5 Table 12: PA0–15, PB0–15, PC6/7/13/14/15, PD0–3, PF0–2. Nothing was read |

| Register | Meaning |
|---|---|
| RDATA0 | bits 1..0 mode (0 input, 1 output, 2 AF, 3 analog) · bits 3..2 pull (0 none, 1 up, 2 down) · bit 4 open-drain · bit 5 output latch (ODR) · bit 6 level (IDR) · bits 11..8 AF number · bit 14 level valid · bit 15 configuration valid |
| RDATA1 | the port's IDR, bits 15..0 |
| RDATA2 | the port's ODR, bits 15..0 |
| CRC_STATUS | for this opcode, the port's analog-pin mask: those pins' IDR bits are 0 by construction |

With `tools/o2p_cli.py`:

```sh
python3 tools/o2p_cli.py --port /dev/cu.usbserial-X diag gpio ADC_DRDY   # or PB1
python3 tools/o2p_cli.py --port /dev/cu.usbserial-X diag gpio --port B   # every bonded pin
```

A pin takes a `PB3`-style name or a `src/board_pins.h` signal name. The tool
prints HIGH or LOW only for status OK with the level-valid bit. Otherwise it
prints NOT SAMPLED with the reason, or the refusal. An output-mode pin whose
latch and level disagree is flagged "driven level not reached - overloaded or
shorted?".

The opcode is served inside the write, with interrupts masked for its seven
register loads (the reasoning is in `src/regmap.c` and
`doc/PLAN-MODBUS-DEBUG.md` 5.4). It costs 568 bytes of flash on a debug build.
`test/test_logic` `test_gpio_*` and `tools/test_o2p_cli_gpio.py` (against
`tools/gpio_oracle.c`) check it host-side. **Nothing of it has run on a
probe.**

#### Memory poke mailbox — `0x0198` and wide poke — `0x01B0` (2026-09-11)

The WRITE counterpart of the two peek blocks (Fab's order, 2026-09-11):
SRAM variable patching from the bench, under the same debug gate. The full
cortex-M0+ reasoning is `doc/PLAN-MODBUS-DEBUG.md` §3.7; the operator rules:

- One FC16 starting exactly at the block base, of exactly `3 + 2*words`
  registers: `[addr_hi, addr_lo, words, w0_hi, w0_lo, …]`. `words` is 1..4 at
  `0x0198` (accepted counts 5, 7, 9, 11) and 1..30 at `0x01B0` (accepted
  counts 5..63). Any other in-block write is **exception 03 and changes
  nothing**; a frame running off the block's end is exception 02 like any
  off-map frame.
- Writes land only in the `.data`/`.bss` span — the same span the SRAM parity
  gate admits for reads — so anything poked is peekable back for verification.
  Flash, peripherals (SCB AIRCR included), the UID, SHARED, the stack and the
  `.data`/`.bss` gap are all status 2 (out of range), deliberately. Misaligned
  targets are status 3.
- Every register reads back what the last trigger HELD: address, word count,
  payload, status — and for `0x01B0`, a sequence number that skips 0 on wrap.
  A REFUSED poke still holds the payload, so the readback shows what was
  attempted while the status says it never landed.

| Reg | Name | Access | Meaning |
|---|---|---|---|
| `0x0198` | `POKE_ADDR_HI` | rw | trigger: target address, high word; reads the address held |
| `0x0199` | `POKE_ADDR_LO` | rw | low word |
| `0x019A` | `POKE_WORDS` | rw | trigger: words, 1..4; reads the count held |
| `0x019B` | `POKE_W0_HI` | rw | trigger: payload word 0, high; reads the payload held (to `0x01A2`) |
| `0x01A3` | `POKE_STATUS` | ro | 0 none, 1 OK, 2 out of range, 3 misaligned |

| Reg | Name | Access | Meaning |
|---|---|---|---|
| `0x01B0` | `POKEW_ADDR_HI` | rw | trigger: target address, high word; reads the address held |
| `0x01B1` | `POKEW_ADDR_LO` | rw | low word |
| `0x01B2` | `POKEW_WORDS` | rw | trigger: words, 1..30; reads the count held |
| `0x01B3` | `POKEW_DATA` | rw | trigger: payload word 0 high, word 0 low, … (60 registers, to `0x01EE`); reads the payload held |
| `0x01EF` | `POKEW_STATUS` | ro | 0 none, 1 OK, 2 out of range, 3 misaligned |
| `0x01F0` | `POKEW_SEQ` | ro | triggers executed; skips 0 on wrap, so 0 means never |

**Nothing of this has run on a probe** — host-tested only
(`test/test_peek_write`, 17 cases: every refusal proven by status AND a
store count of zero, the poke-then-peek roundtrip, both overlap directions).

#### Arbitrary code execution mailbox — `0x0150`

Allows loading and executing small ARMv6-M Thumb payloads (functions matching `uint32_t (*fn)(uint32_t arg)`) in SRAM during the `PH_IDLE` phase between measurement cycles. Protected by a SysTick execution timeout and Thread-mode HardFault interception, plus hardware IWDG backstop (~4.1 s) and automatic RS-485 transceiver DE (`PC6`) deassertion and heater shutdown.

| Reg | Name | Access | Meaning |
|---|---|---|---|
| `0x0150` | `EXEC_CMD` | rw | `0x5A01` = RUN, `0x5A00` = ABORT; reads held command |
| `0x0151` | `EXEC_LEN` | rw | code byte length (2..128, even) |
| `0x0152` | `EXEC_PARAM_HI` | rw | 32-bit input argument in R0, high word |
| `0x0153` | `EXEC_PARAM_LO` | rw | low word |
| `0x0154` | `EXEC_TIMEOUT_MS` | rw | timeout in ms (1..1000, 0 defaults to 50 ms) |
| `0x0155` | `EXEC_STATUS` | ro | 0 none, 1 pending, 2 OK, 3 bad opcode/magic, 4 bad length, 5 fault intercepted, 6 timeout expired |
| `0x0156` | `EXEC_RESULT_HI` | ro | 32-bit return value from R0, high word |
| `0x0157` | `EXEC_RESULT_LO` | ro | low word |
| `0x0158` | `EXEC_CODE_START` | rw | code payload registers (64 halfwords = 128 bytes, up to `0x0197`) |

##### Execution protocol and register access rules

1. **Payload upload:** Write 16-bit Thumb instruction halfwords to `EXEC_CODE_START` (`0x0158..`, count 1..64).
   * **Byte, register, and wire mapping:**
     Modbus holding registers store 16-bit halfword values. On Cortex-M0+ (little-endian), a 16-bit Thumb instruction halfword like `movs r0, #42` (`0x202A`) is stored in flash/memory as bytes `2A 20`. Over Modbus FC16, register `0x0158` transmits MSB first (`20 2A`):

     | Representation | Value for `movs r0, #42; bx lr` |
     |---|---|
     | Binary file (`.bin`) / SRAM bytes | `2A 20 70 47` |
     | Register values (16-bit halfwords) | `0x202A`, `0x4770` |
     | CLI continuous hex input | `202a4770` |
     | Modbus FC16 wire bytes | `20 2A 70 47` |

     Note: do not paste raw byte dumps (`xxd -p payload.bin` -> `2a207047`) into the CLI as register values; use the `.bin` path directly or specify halfwords.
2. **Trigger write:** Write 5 registers to `0x0150..0x0154` using FC16: `[0x5A01, LEN, PARAM_HI, PARAM_LO, TIMEOUT_MS]`.
   * **Span warning & precedence:** Registers `0x0155..0x0157` (`STATUS`, `RESULT_HI/LO`) are read-only. Any write command overlapping them is rejected with Modbus Exception 03 (`ILLEGAL_DATA_VALUE`), *except* that an `ABORT` write (`0x5A00` at `0x0150`) is accepted before the overlap check, and an already pending execution returns Exception 06 (`DEVICE_BUSY`) before the overlap check. Always write payload words to `0x0158+` and trigger words to `0x0150..0x0154` separately.
3. **Execution & polling:** When `0x5A01` is accepted, `EXEC_STATUS` becomes `PENDING` (1). During the next `PH_IDLE` phase in the main loop, the MCU copies the payload into an aligned SRAM buffer, fills unused words with `BKPT 0` (`0xBE00`) traps, releases RS-485 DE, turns off the heater, and calls the entry point. Poll `0x0155` until it is no longer 1:
   * `2` = `OK`: execution succeeded; 32-bit return value available in `0x0156:0x0157`.
   * `5` = `FAULT_INTERCEPTED`: payload raised HardFault in Thread mode; intercepted by trampoline, returning without immediate chip reset. (Note: state changes or peripheral mutations made before the fault survive; stack corruption or handler-mode faults fall back to normal reset).
   * `6` = `TIMEOUT_EXPIRED`: execution exceeded `EXEC_TIMEOUT_MS`; terminated by SysTick trampoline. (Note: if interrupts are masked via `cpsid i`, SysTick cannot fire and hardware IWDG resets the MCU at ~4.1 s).
4. **Abort:** Writing `0x5A00` to `0x0150` cancels a pending execution before it runs.

##### Calling convention & ABI constraints (ARMv6-M Cortex-M0+)
* **Architecture:** Target is strictly ARMv6-M (Cortex-M0+), not generic Thumb-2. Compile with `-mcpu=cortex-m0plus -mthumb`. Instructions not supported on ARMv6-M (e.g. `movw`, `movt`, `cbz`, `it`, 32-bit arithmetic) will trigger a HardFault.
* **Signature:** `uint32_t fn(uint32_t arg);`
* **Calling convention:** AAPCS for ARMv6-M (Thumb).
  * Input argument `arg` in `R0`.
  * Return value in `R0`.
  * Caller-saved (scratch): `R0`–`R3`, `R12`.
  * Callee-saved: `R4`–`R7` and high registers `R8`–`R11`. On ARMv6-M, high registers cannot be pushed/popped directly (e.g. `push {r8}` is illegal); they must be moved to low registers before push/pop.
  * Stack pointer (`SP`): Must remain 4-byte aligned throughout execution, and 8-byte aligned at external call boundaries.
  * Return address: Passed in `LR`. The function returns via `bx lr` or `pop {..., pc}`.
  * The Thumb bit (bit 0 of entry point address) is set automatically by the firmware before calling.

##### CLI usage

Using `tools/o2p_cli.py exec`:

```sh
# Execute snippet returning 42 (movs r0, #42 [0x202A]; bx lr [0x4770]):
python3 tools/o2p_cli.py --port /dev/cu.usbserial-X exec "202a 4770"

# Execute snippet adding 5 to the parameter (adds r0, #5 [0x3005]; bx lr [0x4770]):
python3 tools/o2p_cli.py --port /dev/cu.usbserial-X exec "3005 4770" --param 37 --timeout-ms 100

# Execute from a compiled binary file (compiled with -mcpu=cortex-m0plus -mthumb):
python3 tools/o2p_cli.py --port /dev/cu.usbserial-X exec payload.bin --param 0x12345678

# Abort any currently pending execution:
python3 tools/o2p_cli.py --port /dev/cu.usbserial-X exec --abort
```


#### Through the node's USB console

`peek` and `diag gpio` can also reach a probe through a farm node, whose USB
console relays Modbus RTU onto its RS-485 pair. `nodecon.py` holds the node's
port and hands the wrapped command a pty as `{port}`. Run from
`~/dev/ha/farming`:

```sh
tech/node-prototype/tools/nodecon.py -n farm-node-01 -- \
    python3 ~/dev/ee/hw/o2-probe/firmware/tools/o2p_cli.py \
    --port {port} --addr 3 --timeout 3 peek <symbol>
tech/node-prototype/tools/nodecon.py -n farm-node-01 -- \
    python3 ~/dev/ee/hw/o2-probe/firmware/tools/o2p_cli.py \
    --port {port} --addr 3 --timeout 3 diag gpio PB3
```

How the relay treats these frames (node-prototype `src/serbus.h`, read
2026-09-10):

- **There is no envelope.** A request is recognised by its structure: a
  non-zero unit address, function code 03 or 16 and nothing else, and a valid
  CRC over the exact length that code implies. Console log text cannot pass
  that test. Everything `peek` and `diag gpio` send is FC03 or FC16.
- **The ADU ceiling is 256 bytes** (`SERBUS_MAX_ADU`). `o2p_cli.py`'s `node`
  preset uses 255, the probe's own FC03 limit. The largest reply these
  commands ask for is the wide block's 135 bytes.
- **Each accepted frame claims the pair for 30 s** (`SERBUS_HOLD_MS`), renewed
  by the next frame. The node's own poller stays off the bus meanwhile, and a
  crashed tool holds it off for at most that long.
- **While that claim is held, only `bus` and `ble` act on the USB console.**
  Other typed verbs are ignored, because relayed bytes can complete a typed
  line (node-prototype `README.md`, console table).

**The node must be awake.** In deep sleep its USB-Serial-JTAG peripheral is
powered down and the port disappears (node README, "A sleeping node is not
reachable over USB at all"). Since node-prototype `ce20225` it stays awake
while a USB host is present.

`--timeout` (default 1 s) is the per-read serial timeout, and 3 s follows the
node README's relayed `o2p_update.py` example. The committed
`SerialLink.exchange()` in `tools/o2p_update.py` also keeps reading for
max(2 s, 3 × timeout) after a read that held no frame. So the default already
waits about 4 s for a relayed reply, and `--timeout 3` about 12 s.

**This path is UNVERIFIED.** On 2026-09-10 a wrapped `o2p_update.py --status`
crossed the relay end to end and released its locks, but no probe reply came
back (node README). farming `docs/2026-09-10-rs485-lost-replies.md` traced it
to the node, not the probe: the RS-485 turnaround byte committed the node's
`read_frame()` to its 20 ms inter-frame gap, so it stopped listening before
the probe answered. Node-prototype `ce20225` fixed that. No relayed exchange
has been recorded as succeeding since, and neither command here has been run
through the node.

### Update block — `0x0050`, 16 registers

The firmware updater's control registers. Answered by the application and, with
bit 15 of `UPD_STATUS` set, by the bootloader. Full protocol in
[Field updates](#field-updates-how-a-buried-probe-gets-new-firmware).

| Reg | Name | Access | Meaning |
|---|---|---|---|
| `0x0050` | `UPD_STATUS` | ro | state << 8 \| error; bit 15 set = the bootloader is answering |
| `0x0051` | `UPD_BLOCK_MAX` | ro | largest payload register count in one block (120) |
| `0x0052` | `UPD_SLOT_HI` | ro | staging slot size in bytes, high word |
| `0x0053` | `UPD_SLOT_LO` | ro | low word |
| `0x0054` | `UPD_CMD` | wo | command magic, below; reads as 0 |
| `0x0055` | `UPD_LEN_HI` | rw | declared image length, latched by `BEGIN` |
| `0x0056` | `UPD_LEN_LO` | rw | |
| `0x0057` | `UPD_CRC_HI` | rw | declared CRC-32 (zlib) of the image |
| `0x0058` | `UPD_CRC_LO` | rw | |
| `0x0059` | `UPD_RECV_HI` | ro | bytes accepted into the staging slot |
| `0x005A` | `UPD_RECV_LO` | ro | |
| `0x005B` | `UPD_NEXT_SEQ` | ro | block sequence expected next — how a master resyncs |
| `0x005C` | `UPD_LOADER_VER` | ro | bootloader version; 0 when the application answers |
| `0x005D` | `UPD_IMAGE_VER` | ro | version of the image now running |
| `0x005E` | `UPD_INSTALLS` | ro | installs this probe has completed |
| `0x005F` | `UPD_RESERVED` | ro | 0 |

Commands, all magics for the same reason `COMMIT` and `CAL_TRIGGER` are — each
one erases tens of kilobytes or reboots a settled cell:

| Magic | Command | Effect |
|---|---|---|
| `0xB001` | `BEGIN` | latch length and CRC, erase the staging slot |
| `0xB002` | `COMMIT` | verify what was received |
| `0xB003` | `BOOT` | reset into the bootloader, which installs it |
| `0xB004` | `ABORT` | discard the transfer, retract any staged image |
| `0xB005` | `STAY` | end up in the bootloader with the application stopped |

States are `IDLE`, `ERASING`, `READY`, `RECEIVING`, `VERIFYING`, `STAGED`,
`ERROR`; errors are `STATE`, `LENGTH`, `SEQUENCE`, `ALIGN`, `FLASH`, `CRC`,
`IMAGE`, `NOIMAGE`. A refused frame sets the error and leaves the state alone;
only a flash error or a failed verification ends a transfer.

### Update data window — `0x0080`, 123 registers, write-only

`UPD_DATA` at `0x0080`. One FC16 write is one block: the first register is the
block sequence number, the rest is image payload, high byte of each register
first. The payload must be a whole number of 64-bit doublewords, which caps a
block at 120 payload registers — 240 bytes, the largest FC16 that fits a
256-byte ADU. Over the Dragino's 40-byte `A8` ceiling the same protocol runs at
12 payload registers. Reads return zero; the window is not a way to read the
staging slot back.

## Fault bits and the validity rule

| Bit | Name | Invalidates O₂? |
|---|---|---|
| 0 | `SETTLING` | **`O2_COMP` only — see below** |
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
| 13 | `ADS_DRDY_STUCK` | **yes** — see below |
| 14 | `ADS_CONFIG_LOST` | **yes** — see below |
| 15 | `HEATER_DISABLED` | no — set whenever the loop is not driving, for any reason |

**Bits 13 and 14 changed meaning on 2026-09-04.** They were `EXP_PRESENT` and
`EXP_FAIL`, reserved for the J2 expansion header, which is DNP on Rev A and
was written by no firmware.

*"No firmware writes it" did not mean "nothing reads it."*
`tech/chirpstack/rs485-ls-decoder.js` in the `ha/farming` repo holds a
**positional** copy of this enum and names every set bit for ChirpStack and
Home Assistant, so between the rename and its update a stuck DRDY line was
reported to the operator as `exp_present`. The decoder and the Grafana panel
description have been corrected. **If this enum is renumbered again, those two
must move with it** — they are in a different repository, which is exactly why
they were missed.

Bit 13 reports a DRDY pin that does not match the converter. It is raised when
the pin will not release a stale result, and when the STATUS register says a
result is ready but the pin never fell. It is NOT raised for a timeout in
which the device reports no result either — that is a device fault and stays on
`I2C_FAIL_ADS`, because "no valid ready was observed" does not by itself
implicate the pin.

Bit 13 reports a DRDY line that will not release — a *pin* failure, deliberately
separate from `I2C_FAIL_ADS`, because the bus can be perfectly healthy while
this pin is not. Reporting the one as the other is what sent a healthy
ADS1119 back as scrap; the fault word said "I²C" and the board was believed.

Bit 14 reports that the ADS1119's config register did not read back as
written: the bus worked, the device disagreed. It is separate from
`I2C_FAIL_ADS` (one NACK) and from `AFE_CONFIG_MISMATCH` (the LMP91000's).

Test the mask `O2P_FAULTS_ADS_NO_CONVERSION`, never any bit alone, when
asking "did the converter deliver this phase?" — splitting the bit broke three
call sites that tested the single bit and would otherwise have computed a
plausible reading from a zeroed accumulator.

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

`SETTLING` splits the two channels the same way, and until 2026-09-08 it did
not. Warmup means the cell has not reached equilibrium, so no %vol derived from
it can be trusted — but the current is still a real measurement of what the
cell is doing, and during warmup it is the *only* record of the cell recovering.
Blanking `O2_RAW` destroyed exactly the evidence the settle window exists to
bound: after two power cycles on 2026-09-08 the probe published a full fault
word, a counting-down `SETTLE_S`, uptime, temperatures and humidity — and
`0x8000` for cell current, for 900 s each time. The 101.04 → 100.60 µA recovery
transient across that window was recorded by nothing, on any transport,
including a Modbus master standing at the probe.

`SETTLING` is *stated* on the compensated mask rather than merely removed from
the raw one, because `O2P_FAULTS_INVALIDATE_O2_COMP` is defined in terms of
`O2P_FAULTS_INVALIDATE_O2`; deleting the bit without restating it would
silently strip the warmup gate from the oxygen verdict as well. Both directions
are pinned by `_Static_assert` in `faults.c`.

Consumers that used the gap in `O2_RAW` to spot a reset must read `SETTLE_S`
(`0x0007`) or bit 0 instead. Both were already in every frame throughout.

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

### The update cycle, which is the gate on potting

Nothing below has been performed. This is the procedure that has to be run and
recorded before a probe is potted, because after that these are the only
mechanisms that exist:

0. Have a master. A USB-RS485 dongle, or a second board flashed with
   `pio run -e bridge -t upload` — reached either by a USB-TTL lead on the
   R15/R16 pads or, with no lead at all, by `--swd` through its mailbox. If it
   is the bridge, `--bridge` must answer before step 1 means anything.
1. `pio run -e loader -t upload`, then `pio run -e o2probe -t upload`. Confirm
   the probe answers a primary-block read at all — that is the jump from the
   bootloader working.
2. `python3 tools/o2p_update.py --port … --status`. Expect `IDLE`, answered by
   the application, loader v1.
3. Push the same image back to it: `… o2p_update.py --port … firmware.bin`.
   Expect `STAGED`, and confirm the probe kept answering Modbus throughout the
   erase and the transfer.
4. `--boot --expect-build-id <the image's stamp>`. The tool now waits for the
   application and checks that `UPD_INSTALLS` advanced and that the running
   `BUILD_ID` is the one you sent: exit 0 proven, 1 contradicted, 2 not shown.
   Read its lines, not just its exit code.
5. **Pull the power mid-transfer.** Restore it, and confirm the probe comes
   back with the *old* application running and no staged image — this is the
   claim the whole staging-slot design rests on, and it is not proven by
   reasoning about it.
6. Pull the power **during the install** (between `--boot` and the probe
   answering again). Confirm it retries the install and ends up running the new
   image.
7. Knock: `--stay`, confirm the loader answers with bit 15 set and the probe is
   not sampling, then power-cycle and confirm it starts the application again.

Only then does the epoxy come out.

### Flashing

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

1. **There is nothing to trim. Read the bias instead.** RV1 is deleted
   (`POTTING.md` §1.2): the cell must be swappable with the board potted, and a
   trimmer on the potted side is unreachable after cure — every cell change
   would have needed a trim nobody can perform. U15, an AZ431B 2.5 V shunt, sets
   `VREF_TRIM` = 2.500 V, and `VREF_MON_MV` verifies it against the window in
   `hw_contract.h` (2489–2511 mV, the reference's own guaranteed spec including
   30 ppm/°C over 100 °C).

   **Trimming VREF was never the right lever anyway.** The error being
   compensated is the LMP91000's *internal* bias step tolerance — `PLAN.md:174`
   records ±2 % of VREF, i.e. ±50 mV, five times the cell's ±10 mV window — and
   moving VREF compensates an internal percentage error by shifting its input.
   VREF is not where the ±2 % lives, so measuring VREF cannot substitute either.
   The only node carrying the real information is the differential
   **V(WE) − V(RE)**, and it is now a measured channel: U4A and U4B buffer the
   two electrodes into ADS1119 AIN2/AIN3, read differentially at gain 4
   (±625 mV full scale, ~19 µV/LSB). Report it; do not try to correct it.

   What makes measuring sufficient is the *plateau*: on the diffusion-limited
   part of the O₂ reduction wave sensitivity is flat, so an in-situ gas
   calibration absorbs whatever bias the board actually has. **That plateau is
   still ungated** — `POTTING.md` §1.4 wants a bias sweep in air at 20 °C and
   again at 75 °C. If the plateau is narrower than ±50 mV the exit is the
   discrete potentiostat, not a trimmer. Note `CELL_RE` still has no test point
   or via (it is a guarded trace), so a probe-based cross-check is taken at the
   cell pins; the buffered copy is available at the ADC without disturbing it.
2. I²C scan → exactly `0x40`, `0x44`, `0x48`, `0x49`.
3. `VREF_MON_MV` should read ≈2500. It is measured on AIN1 against the
   ADS1119's *internal* 2.048 V reference, because a converter referenced to
   the thing it is checking cannot detect that thing drifting.
4. `VA_MON_MV` (MCU ADC1_IN7) and `VIN_MON_MV` (MCU ADC1_IN6) are **both** on
   the MCU's own ADC now — the ADS1119 channels they used to occupy were taken
   by the bias telemetry, so the old cross-check against AIN2 no longer exists.
   Each source impedance (5 kΩ and 8.9 kΩ) needs the longest sampling time;
   C33 and C32 are the reservoirs that make that work.
5. Air point after ≥15 minutes settled: expect 0.1 ± 0.03 mA, i.e. ~700 mV
   across the 7 kΩ TIA. That is DS-0637 **Issue 2**; Issue 1's 0.07 mA is
   superseded, and a cell measured against it looks 43 % hot. Write `0xCA11`
   to `CAL_TRIGGER`, then `0x5AC1` to `COMMIT`.
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

### Bench capture: a time series, not a reading

Most of the interesting bring-up failures are *shapes*. Cell polarisation takes
tens of minutes, a saturated converter looks exactly like a steady one in a
single sample, and a rail that is collapsing reports plausible numbers all the
way down. `tools/o2p_capture.py` reads the live snapshot out of `g_rm` over SWD
and appends one CSV row per sample, with no firmware support and nothing
written to the board.

```sh
python3 tools/o2p_capture.py --once                    # one row, to stdout
python3 tools/o2p_capture.py bench-logs/run.csv --count 1441 --interval 30
```

Captures land in `bench-logs/`, which is **not** ignored — a run that is worth
taking is worth committing, and the 2026-09-04 session lost a series twice by
logging into a scratch directory that vanished. `bench-logs/plot_capture.py`
turns one into a PNG.

It refuses to write a number it cannot justify: the regmap address comes from
the ELF symbol rather than a constant, sentinel readings become empty cells so
a plot shows a hole rather than 65535, `afe_rail` marks any converter within
50 mV of a supply, and a failed probe writes an explicit `status=failed` row —
never a gap, never a stale value carried forward.

Two things to set before a long run:

- **Pick the probe.** With two CMSIS-DAP adapters on the bench OpenOCD takes
  whichever enumerates first, and reading the wrong board is how you get a
  clean-looking file full of someone else's numbers. `--adapter-serial` (or
  `O2P_ADAPTER_SERIAL`) binds it; the Debug Mate publishes no serial, so with
  that one the only answer is to unplug the other. The all-zero-regmap check
  catches the wrong-board case rather than decoding it.
- **Detach it.** Each sample spawns its own OpenOCD; anything past ten minutes
  outlives a foreground agent call. Give it its own process group
  (`nohup python3 -c "import os,subprocess;os.setsid();…" &` — `setsid` does
  not exist on macOS) and take the bench lock for the duration.

If it reports `live index N not 0/1`, the ELF is newer than the image on the
board: the symbol resolved fine, against a build that is not running. Flash the
board, or pass `--addr` with the running build's `g_rm`.


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
clamp, not as a setpoint. It bounds the tip against the chamber (the
`DT_LIMIT` interlock, inert on Rev A) and, for the dew law and its gradient
floor, against the cell side - see **The gradient ceiling** below.

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
| `NOT_COMPILED` | built with `O2P_HEATER_ENABLE=0` — **not** this build, which compiles the heater in |
| `CONFIG_OFF` | `HEATER_MAX_DUTY` is zero — true on a fresh config, and the switch that still stands between this build and any current |
| `SAFETY` | `o2p_tmp117_safety_armed()` false: the therm-mode alert is not programmed |
| `NO_RH` | no fresh SHT45 humidity — **including during the de-creep pulse mask** |
| `NO_TIP` | no fresh TMP117 reading |
| `NO_CHAMBER` | no chamber temperature, so the ΔT clamp cannot be enforced |
| `TIP_LIMIT` | tip ≥ 82.00 °C (firmware absolute limit, releases at 77.00 °C) — the *setpoint* guard refuses above 80.00 °C separately |
| `DT_LIMIT` | tip − chamber ≥ `DT_MAX_K` (releases 0.5 K below) — **inert on Rev A**, where the chamber sensor is the SHT45 and the clamp's premise does not hold |
| `RUNAWAY` | latched: heat with no command — **releases on clear evidence since 2026-09-10**, see below |
| `SUPPLY` | `VA_LOW` or `VIN_LOW` — heating adds ~86 mA to a rail already out of tolerance |
| `PIN_INTEGRITY` | `TIM1.CCER.CC1NE` set, or PA7 no longer analog |
| `STALE` | no duty command within 2 s (`O2P_HEATER_STALE_MS` 2000, 0x0010; was 5000, outrun by the IWDG on a slow LSI tail — review 2026-09-10); the drive is cut and the bit latches for the cycle |
| `NO_CONSENT` | the consent registers (`0x0048` RH, `0x004A` tip) do not carry their magics |
| `BLIND` | the sensor-less fallback is driving at `O2P_HEATER_BLIND_DUTY_X100` because tip/die readings are missing or the die is above `O2P_HEATER_BLIND_DIE_MAX_C100` |
| `IDLE` | **annotation, not a refusal, since 0x0010**: a loop is in command and simply has no demand — duty 0 with the loop healthy |
| `TIP_DISARMED` | **annotation, not a refusal, since 0x0010**: the stored tip setpoint is at the `0x8000` sentinel — the RH loop is the configured law (since 0x0013: the dew-margin law while the cell-side reading is valid, the RH loop otherwise — see "Dew-margin law" below) |

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

**It holds while its evidence persists — and until 2026-09-10 it latched until
reset.** The argument was that a FET conducting unasked is a hardware failure,
that the firmware which just found it should not decide the fault has cleared,
and that auto-clearing would re-arm 1 W every time the tip cooled.

**The premise was refuted on the bench.** About 80 °C water poured into the jar
with the RH loop running heated the tip 20 K in six minutes — starting two
minutes *before* any duty was commanded — while the die lagged across the
thermal barrier. Tip − die crossed 10 K and the latch set at 11:07 UTC with no
sign of the FET conducting: VIN held its 10710 mV baseline through the
uncommanded rise, where continuous conduction would have sagged it by an
estimated 0.30–0.46 V, and the chamber ran up to 0.8 K *ahead* of the tip, which
ring heat never does on this board. That excludes continuous conduction, **not a
small leak** — published VIN resolves only 7.5 mV — so it is corroboration of an
external source, not proof of a healthy FET. Any environment that heats the tip end faster than the die end produces
the signature, and a probe pushed into a hot pile is exactly that.

So the latch still sets on the same evidence and still holds for as long as that
evidence persists, which is what a stuck FET does. It releases only after
`O2P_HEATER_RUNAWAY_WINDOW_S` of evidence that is valid on **every** reference
and below both thresholds by `O2P_HEATER_RUNAWAY_RELEASE_HYST_K100`. Requiring
every reference matters because on Rev A the chamber tracks the tip whatever the
FET does, so a lost die reading falls back to latched-until-reset instead of
releasing. A chamber temperature bridged from the cache does not count toward
release, a sample with the tip or both references invalid restarts the window
rather than being credited as observed time, and arming the bench override
discards banked release evidence (it only *freezes* accumulation). All three were
found by review of `eae463f`. No register write clears the latch, and
`FAULTS_EVER` keeps the event. What is given up: a
firmware-side fault that forcing duty to zero *does* stop now cycles instead of
stopping for good. The TMP117's open-drain alert can hold the gate low against
the MCU's drive through R28, but only at its 85 °C trip point, with overshoot
unmeasured and the alert path never fault-injected; the 82 °C firmware clamp
helps only if the faulty path still obeys a zero command. The full
argument is at `update_runaway()` in `heater_ctl.c`; the real event is replayed
at 1 Hz by `test_the_80c_bath_of_2026_09_10_latches_and_then_releases`.

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

As of 2026-09-08 step 1 is still outstanding and the flag is nevertheless set
to 1, deliberately, for the 80 °C harsh-environment characterisation — see
`src/heater.h`. What still stands between the build and any current is a
non-zero `HEATER_MAX_DUTY`, which no fresh configuration has.

`pio run -e o2probe_heater_disabled` exists purely to prove the compiled-out
path still compiles; it is never flashed. It was called
`o2probe_heater_enabled` until the shipped polarity flipped.

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
4. **Source of truth.** The duty published in `0x0009`, and averaged into
   `0x0005`, is read back from
   `o2p_heater_duty_x100()` — what the hardware layer actually applied — not
   the controller's request. If `heater.c` refuses a command, the register
   shows the refusal.
5. **Persistence.** The runaway latch holds while its evidence persists and is
   never cleared by a register write or a brief healthy interval — only by a full
   window of evidence that is valid and clear on every reference (see above). The integrator is **zeroed** on any
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
     and `HEATER_DUTY_NOW` `0x0009` reads back what you asked for.
   - Write `TLOW` then `THIGH` on the TMP117 (`0x0003`, `0x0002`) to a limit
     **below** the present tip temperature, over the same I²C bus.
   - **Expect: `HEATER_GATE` pulled low by the open-drain ALERT within one
     TMP117 conversion, and `HEATER_LOW` at +12 V — heater off — while the MCU
     is still commanding PWM.** That contention is bounded to ~0.33 mA by R28
     per `SCHEMATIC-REVIEW.md` H3's closure; confirm on the gate trace that it
     is held below the AO3400A's threshold.
   - **Firmware will notice too, and that is deliberate.** `phase_temps()`
     re-verifies `CONFIG`, `THIGH` and `TLOW` against what `o2p_tmp117_init()`
     programmed, so writing `THIGH` from the bench disarms
     `o2p_tmp117_safety_armed()` and raises `I2C_FAIL_TMP` — in v1 that is
     itself an interlock which drops duty to zero. The re-verification runs
     only every tenth cycle (~10 s) precisely so this cannot be confused with
     the hardware cutoff, which acts within one TMP117 conversion (500 ms).
     **The gate edge you are looking for is the FIRST one, ~20x earlier than
     the firmware's reaction.** If the two are not clearly separated on the
     trace, the measurement has not shown what it claims to.
   - Restore `THIGH` and confirm the heater resumes only after the tip falls
     below the hysteresis point — and that `I2C_FAIL_TMP` clears within 10 s.
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

### From the independent review of the updater, still open

An adversarial Codex review of the updater commit raised fifteen findings. Ten
are fixed in the tree (the loader's two-base vector check, the never-stamped
response deadline, the stale descriptor copy, the side-effecting rejected
control frame, the wrapping flash bound, the unchecked install result, the
knock-window parser, the idle timer, the flash-map B pages, and the transport
arithmetic below). These are the ones that are **not**, each with what would
close it:

- **The updater authenticates nothing.** Verification is a CRC-32 the sender
  supplies, plus a vector-table plausibility check. That catches a corrupted
  transfer and a wrong-slot image; it does not distinguish this product from
  another, a current image from an older known-bad one, or a friendly image
  from a hostile one. Anyone who can put frames on the cable can install code,
  and once installed that code can erase the bootloader — `o2p_flash_program`
  is generic and the boot pages are not write-protected. The closing moves, in
  order of cost: flash write-protection (WRP) on pages 0–7, a product and
  hardware-revision word inside the image that the loader checks, an
  anti-rollback version counter, and a signature. **None of this is a reason to
  delay potting** — the alternative to a weakly authenticated updater is no
  updater — but it should be decided before probes are buried somewhere a
  stranger can reach the cable.
- **A loader potted before 2026-09-08 cannot read the transport block.** The
  fix above is forward-looking by construction: it makes every *future* layout
  change survivable, and can do nothing for an image already under epoxy. Such
  a loader still falls back to address 3 / 9600 8E1 whenever the application's
  configuration layout has moved past its own, so the recovery host must knock
  at both identities — see "How the loader knows where the probe is on the
  bus" — which `o2p_update.py` now does automatically. That sweep is the whole
  mitigation available: a device-side scheme cannot be installed on a probe
  that is already buried, which is to say it is not a closing move at all. No
  probe is potted as of this writing, so every board on the bench can simply
  have its loader reflashed over SWD and be done with it.

- **Update commands are executed when broadcast.** A broadcast (address 0)
  FC16 to the command register reaches every probe at once: one frame can put
  the whole cable into `ERASING`, or reboot all of it. The dispatcher does not
  tell the register handlers that a frame was a broadcast; it should, and the
  update block should refuse them.
- **A page erase can lose a request that arrives during it.** `main()` checks
  only that no response is transmitting before erasing. Reception is
  interrupt-driven with no DMA or FIFO, so a frame that begins arriving during
  the 22–40 ms erase can overrun and vanish. The master sees a timeout and
  retries, which is survivable — but `tools/o2p_update.py` does not retry
  transient errors while polling for the erase to finish, so it gives up
  early. Fix the tool first; it is the cheaper half.
- **`flash_wait()`'s timeout cannot fire during the stall it is meant to
  catch.** It measures 200 ms with `o2p_millis()`, which SysTick advances —
  and a flash operation that stalls instruction fetch stalls SysTick's handler
  too. The application's IWDG is the real backstop; the loader has no
  watchdog at all, deliberately, and that is the trade to revisit if a bench
  board ever hangs mid-install.
- **The boot-request word is not gated on the reset cause.** Two SRAM words
  holding a value and its complement will not survive a power cycle as a
  matched pair in any realistic pattern, but "realistic" is doing work there:
  the loader does not additionally require that the reset was the software
  reset that follows a request. `RCC_CSR`'s `SFTRSTF` is already latched by
  `o2p_clock_init()`; checking it would make this deterministic instead of
  probabilistic.
- **The config read-back now compares the reserved tail.** The shared
  `o2p_flash_program` verifies all 64 bytes, while the config CRC deliberately
  excludes the reserved bytes. A read-back difference confined to those bytes
  makes `o2p_config_store()` report failure even though the record it wrote is
  semantically valid and will win after a reset. Rare, and it fails safe; it
  is a behaviour change from the pre-refactor driver all the same.


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
- **The heater gains are compile-time constants, and they should not be.** The
  plant gain cannot be known until the loop runs on hardware, and once a probe
  is potted there is no SWD to reflash it through — so tuning has to happen
  over the bus or it cannot happen at all. Two holding registers
  (`HEATER_KP`, `HEATER_KI`) would fix this. They were implemented and then
  **reverted**: adding them changes the register map, whose prose copy lives in
  `../DESIGN.md`, outside the boundary this work was scoped to. It is one
  commit of `regmap.h` plus a `DESIGN.md` table row, and it should be done
  before anyone tunes a loop on a board they intend to pot.
- **The refusal reason is published since FW 0x000F** as `HEATER_BLOCK` (`0x002E`), the table above. This paragraph originally said the reason was
  not published and named "twelve interlocks"; the register went live and the
  word gained `NO_CONSENT`, `BLIND` (0x000F-era) and the `IDLE`/
  `TIP_DISARMED` annotations (0x0010), so it is kept as history, corrected:
  diagnosing a refusal from a buried probe is now a register read, with the
  caveat that bits 14/15 are annotations, not refusals, and the word is full —
  a future "why" needs a mode field in a spare diagnostic register.
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
  the chamber channels read invalid for **350 s** afterwards. That window was a
  conservative 30 s guess until it was **measured on 2026-09-07** against the
  chamber's own drying curve: recovery to within 0.10 %RH takes 325 s, and at
  t+40 s — ten seconds after the old mask expired — the published RH was
  1.63 %RH low. The old value published, three times a day, exactly the
  artefact the mask exists to prevent. Derivation and both bench logs:
  `SHT-DECREEP-MASK-IS-TOO-SHORT.md`; constants and the assertion tying them
  together: `o2.h`. Still open from that run: 0.05 %RH was **not** reached
  inside the observation window, and the slow-recovery signature has not been
  turned into the `DEW_SUSPECT` classifier `PLAN.md:312` asks for.
- **A masked cycle raises no fault.** It used to raise `I2C_FAIL_SHT`, which
  made a maintenance action this firmware ordered indistinguishable from a dead
  humidity sensor — while `I2C_ERRS` stayed at 0, so the counter and the bit
  disagreed and neither settled it. A consumer now reads a mask as *chamber
  sentinels with no fault* and a failure as *chamber sentinels with
  `I2C_FAIL_SHT`*. The absence of the bit is the discriminator, and there is no
  room in the 16-bit fault word or in the 0x0010–0x002F diagnostic block for a
  positive one. `o2p_sht_masked()` / `o2p_sht_phase_faults()` in
  `sampler_logic.h` are the two halves of the rule, called from `phase_sht()`
  and covered on the host.
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
- ~~`BAUD_CODE` has no revert-on-silence~~ — built, `src/serial_probation.h`.
  A `SLAVE_ADDR`/`BAUD_CODE`/`PARITY_CODE` change now applies on probation and
  reverts to the STORED settings after ten seconds without a valid frame at the
  new ones. It also makes a mistyped slave address recoverable, which it was
  not.

Still open:

- **The node has never been configured.** `AT+COMMAND3` / `AT+DATACUT3` /
  `AT+CMDDL3` / `AT+PAYVER=3` are written down in
  `tech/RS485-LS-SMT100.md` ("Adding the o2-probe") but not sent. Deploy the
  codec first and set `AT+PAYVER` last, so the codec is never behind the node.
- A dedicated always-on 12 V supply on the probe cable.

### HEATER_BLOCK correction, 2026-09-11 ~01:50 — the supply veto is removed (Fab's order)

`O2P_HB_SUPPLY` no longer vetoes any heating path. Old rule: a rail fault
(VA < 3130 mV or VIN < 9000 mV) forced duty 0 everywhere, "heating adds
~86 mA, a rail out of tolerance is not the place for more load" — while
`blind_duty()` simultaneously drove 50 % through the *same* fault with no
sensors at all. Working sensors earned less heating than none: backwards.
The heater is <1 W and cannot start a fire, and heat is exactly what a wet
board needs. New rule: the bit is an **annotation** — duty runs, and
HEATER_BLOCK says the rail was out of tolerance while it did. Removed from
the loop interlocks (`heater_ctl.c` `interlocks()`, dated comment) and from
the override's do-not-bypass list (`regmap.h`, dated correction);
`main.c`'s `supply_ok` feeds the annotation only. Tests:
`test_supply_fault_annotates_but_does_not_veto` pins that identical inputs
give identical duty regardless of `supply_ok`, with the bit reported;
"supply" removed from both forces-zero tables.

Correction to the correction, 2026-09-11 ~01:58 (codex-xhigh audit, finding 9):
the runaway-latch-this-cycle branch in `o2p_heater_ctl_step` used to overwrite
HEATER_BLOCK with `O2P_HB_RUNAWAY` alone, dropping the supply annotation on
exactly the cycle the register most needs to tell the whole truth. It now
ORs the latch in (`|=`), so a wet-rail cycle that also latches runaway reads
`RUNAWAY | SUPPLY`. Gap acknowledged, not yet closed in tests: no test
covers supply-fault + same-cycle runaway latch (the 60 s accumulation makes
it tedious to construct); the latch-cycle path with a healthy rail is
covered and unchanged.

### Dew-margin law, 2026-09-11 (FW 0x0013) — Fab's order

Trigger, measured 2026-09-11 15:18 UTC with the probe in a steam bath (FW
0x0011, keeper register read): tip 77.7 °C, cell side (`T_EXT`) 74.9 °C, gas
dew point ≈ 76.2 °C from the SHT45. The cell side sat **below** the dew point
while the published tip-referenced margin (tip − Td) read ≈ +1.5 K. The heater
was off with block word 0x1004 = `NO_CONSENT` + `SAFETY` (the RH consent
register read 0), and for the RH
law SAFETY blinds, which the die gate (die 73.6 °C ≥ 40 °C) then closes — so
consent alone would not have heated either. Order: *"fix it so it keeps a
reasonable dew-margin"*; answers: reference = cell-side `T_EXT`, margin 4 K,
"margin, up to the 80 °C tip cap", implement + test + flash + arm.

**The law.** `margin = T_cell − Td(T_chamber, RH)`; error =
`min(4.00 K − margin, 79.00 °C − T_tip)` in 0.01 K, PI with kp 5 / ki 0.05
(duty 0.01 % per 0.01 K), `O2P_HEATER_MODE_DEW`. The dew point is a property
of the gas and survives the island's self-heating, so the SHT45 still supplies
it; what changes is the surface it is compared with. **That holds only while
the SHT45 is responsive to the gas**: liquid water on its surface makes it
unresponsive to air RH (Sensirion SHT4x datasheet v7.3), and a successful I2C
read plus a Magnus-valid input cannot tell. Whether it held in the 15:18 steam
bath is unverified. The `min` holds the tip
at 79 °C when the margin cannot be met — which saturated gas near 76 °C
guarantees, since the cell side gains only ~0.4 K per K of tip — so the
80.00 °C clamp stays a backstop. Above the cell's 60 °C rating the margin
still wins, per the answer. Constants and reasoning: `heater_ctl.h`
`O2P_HEATER_DEW_*`.

**The gradient ceiling.** Introduced in FW 0x001A, on Fab's "fix it, flash it"
of 2026-09-13.
The 79.00 °C in the error above is now `min(79.00 °C, T_cell + DT_MAX_K)`,
one function (`dew_ceiling_c100()`) shared by the dew law's error, the
gradient floor's setpoint clamp and the unreachable-margin detector. Why:
that morning, with the tip setpoint disarmed, this law ran probe 3's tip
22 → 69 °C at 100 % duty in a wet enclosure with the cell fitted; nothing
bounded it in kelvin short of 79 °C, and how far 1.2 W gets depends on θ, which
is 68 K/W in still air and unmeasured buried. A gradient is bounded whatever
the plant. The envelope register already existed and is stored, so the
bound is tunable without a reflash and the record layout is unchanged. The
trade: a margin that needs a steeper tip-to-cell gradient than the envelope
is unreachable by construction, and after the 600 s dwell the floor holds its
gradient (2 K until FW 0x002D, 4 K since). Since 0x002D the floor equals the
ceiling whenever `DT_MAX_K` is the stored 4.00 K, so the dew law has no room
above the floor until `DT_MAX_K` is raised. Pinned by `test_dew_gradient_ceiling_bounds_the_wet_enclosure_excursion`,
which first reproduces the excursion with the envelope out of reach.

**When it is in command.** The RH law's slot (no override, stored tip
setpoint at the sentinel, RH consent `0x0048`) **and** a cell-side reading no
older than 10 s (`O2P_HEATER_CELL_MAX_AGE_S`, bridging the ext glitch
filter). Without one, the RH law runs exactly as before. Precedence is now
override > stored tip > dew > RH; the mode tag restarts the integrator on
every hand-over. No register was added: `HEATER_BLOCK` has no free bit, and
**the law in command cannot be read off `T_EXT` in either direction**. A
withheld or failed sample publishes the sentinel while the heater's private
bridge keeps the dew law for up to 10 s (Codex review of `4fe6b36`, finding
5); and since `b3f7711` a responsive part whose conversions froze keeps
publishing a valid `T_EXT` while the bridge, which needs `Data_Ready`, expires
to the RH law (Codex review of `b3f7711`, finding 2). An observable mode needs
a spare diagnostic register.

**Its interlocks, per the per-law blind rule.** `NO_RH`, `NO_CHAMBER` and
`NO_TIP` blind it (die-gated, as for every law) — the dew point is its control
quantity and the tip its only bound; a humidity the Magnus form rejects
(≤ 0 or > 100 %RH) raises `NO_RH`. `SAFETY` annotates, and `TIP_LIMIT` is
80.00 °C under this law unconditionally (release 77.00 °C).

**Limits, stated.** The gains are provisional on an unmeasured plant. Magnus
is fit to ~60 °C; 75 °C is extrapolation. `4fe6b36` (the image installed
2026-09-11 17:53) had no conversion-freshness check on the ext TMP117, so a
frozen conversion held a constant margin forever — a warm frozen reading keeps
a drowning cell cold, which the tip ceiling does not bound; `b3f7711` ages the
bridge from `Data_Ready` instead (diagnostic-mailbox reads of the ext part
consume that flag — see the restriction in `main.c`). `4fe6b36` also let the
shared integral drive past the 79 °C ceiling (57 % at 79.50 °C); `b3f7711`
back-calculates it so duty is 0 above the ceiling, proven over 249 480 cases
by the second review. That is a bound, not regulation: on a hypothetical
first-order plant the re-entry cycled ~77.6–79.0 °C, and actual stability at
the ceiling is unverified. In the bath the 4 K margin is physically
unreachable under the cap; the law then runs the tip up to the ceiling and
the cell side as close as that allows.
Published `DEW_MARGIN` (0x0014) is unchanged and still tip-referenced. Tests: `test_dew_law_*` in `test/test_logic`.
