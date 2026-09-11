
## 2026-09-10 ~22:30 — 0x0010 flashed, verified, bake re-armed (install #4)

- **FW_VERSION 0x0010 running** (`0x0018` reads 16), install count 4, uptime
  fresh. BUILD_ID `0xC48390AA` = commit 48390aa (tree HEAD at build) + bit 31
  dirty (uncommitted 0x0010 changeset) + bit 30 debug build.
- Transfer: 41,856 B / 175 blocks in **99.8 s** over BLE (MTU 517), CRC
  0A7B1F6A, probe verify passed → STAGED. First push attempt died at
  CMD_BEGIN, third at CMD_COMMIT, both on `FC16 reply is 9 bytes, expected 8`
  — both writes **landed**; the exception is host-side parse noise. Pattern:
  only state-transition writes to `0x0054` hit it; ~180 data writes echoed
  clean. Root cause NOT yet proven; suspect class = a late-reordered status
  read reply (9 = FC03 reply, 2 words) gluing to the write reply through the
  node's queue. The canonical updater's suspect-drain covers session opens
  only. **Open issue.**
- Two other failure modes tonight, both mine, both retired: ghost ACL from
  `kill -9` (node holds the dead peer, never advertises — v1/v3; fix = clean
  TERM + explicit `bluetoothctl disconnect` + verified clear), and the
  farmgw toolchain being stale (Sep-8 `o2p_update.py`, old runner — deployed
  canonical copies; md5 now matches repo).
- **BOOT landed despite "bus silence"** — the reply raced the reset; probe
  rebooted and installed on its own. Don't re-send BOOT on that error; read
  the update block first.
- Post-boot: node's disconnect-disarm had fired during BLE churn
  (`0x0049=32768 0x004A=0`, cap 500). Re-armed deliberately:
  `0x0035=10000 0x0048=39943 0x0049=8000 0x004A=29120`, all read back.
- **Runaway latch fired from bake residue** (fresh boot, duty 0, tip ~55 °C
  over the references → latched) and **self-released in ~90 s** as the board
  equilibrated — the release-on-clear-evidence change (heater_ctl.c, refuted
  2026-09-10 latch-until-reset premise) proven live. Event kept in
  FAULTS_EVER (`0x0023` = 0x8301; bits 0/9 unidentified, decode pending).
- Bake confirmed: tip ~79-80 °C modulating, block 0, VREF 2494, O2_RAW
  98.97 µA (air band, cal point 99.16), T_AFE valid. WE_BUF/RE_BUF still
  0xFFFF (no cell) — dummy-cell test still pending.

## 2026-09-10 ~23:40 — the 9-byte FC16 reply: root-caused with byte evidence

Two instrumented repro pushes (same image, no install — ABORT after capture)
nailed it. Both crashes returned the **write's own correct 8-byte echo plus
one trailing 0x00**:

- CMD_BEGIN: `031000540005403800` = echo(`03 10 0054 0005`, CRC 4038) + `00`
- CMD_COMMIT: `03100054000141fb00` = echo(`03 10 0054 0001`, CRC 41fb) + `00`

Both writes **landed** — after each crash the probe was found in the expected
state (run 1: READY, erase done; run 2: STAGED, verify passed). The tool's
strict exact-length check refused a frame that was 8/9ths correct; the
workaround is simply to re-run and read the update block — never re-send BOOT
blind.

**Mechanism** (evidence + the node's own measured comments, main.cpp
read_frame_wait): a turnaround `0x00` artifact lands "about 0.5 ms after our
own last stop bit on essentially every exchange". On reads the probe's answer
latency is ~85 ms (ADS conversion), so the artifact leads the reply and the
node's resync strips it. On BEGIN/COMMIT — the only two update commands whose
handlers do no inline flash work — the echo returns in ~1-3 ms and the
artifact can land **behind** it; nothing strips a trailing byte, so the node
gap-collector frames 9 bytes and the host's CRC check passes (both parses
validate; the probe's code can only build 8). Data writes (inline flash
programming) and reads never hit it. It is a sub-millisecond race, which is
why the keeper's fast FC06 writes usually win it.

**Fix belongs in the node** (`read_frame_wait`): trim a single trailing 0x00
that arrives within the gap window after a CRC-valid frame — the same
judgment it already applies to leading fragments. Node flash is Fab's call;
not done tonight. A scope on the pair would say which end's driver-enable
edge produces the byte, but the trim fixes it either way.

The instrumented `o2p_update.py` (hex in every shape error) is deployed to
farmgw and in the repo; md5s agree.

## 2026-09-10 ~23:55 — bake ended by Fab's call

`0x004A=0 0x0049=32768 0x0035=0`, all read back. Duty 0, block = CONFIG_OFF,
tip ~79 °C cooling passively. Probe runs 0x0010 (install #4); keeper up on
farmgw with the current code; night's work complete.
