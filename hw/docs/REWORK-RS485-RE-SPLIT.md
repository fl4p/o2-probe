# Rev A rework: split /RE off DE

**Status: specified and verified against the as-built netlist, NOT performed.**
Nothing on the bench article has been cut, wired or fitted. This is the
procedure and its acceptance test; the iron is Fab's.

## What it buys, and what it does not

`POWER-BUDGET.md` (2026-09-07) split the THVD1410's `/RE` onto its own MCU pin
in `gen_sch.py` and in firmware, and said so plainly: *"No PCB work has been
done, so on copper `U5.2` is still shorted to `U5.3`."* That is still true. The
board on the bench cannot reach the transceiver's low-power state, so its
receiver draws **700 µA forever — 24 % of the whole board's idle budget**.

The rework recovers **630 µA** of that 700 µA. Not 700: commanding standby
means driving `/RE` high against a 47 k pull-down, so the floor is
3.3 V / 47 k = 70.3 µA rather than the part's 0.1 µA. The full table, and why
no larger resistor is in spec, is in `POWER-BUDGET.md`.

**It does not by itself save anything.** `o2p_modbus_rx_standby()` exists and
*nothing calls it* — entering standby means going deaf, which is only safe once
there is another way to be woken (USART1 wake-on-address out of Stop 1, still
unbuilt). So the rework makes the saving *available*; a later firmware change
takes it. Doing the copper first is still worth it, because it is the half that
cannot be done after potting.

## As-built facts this procedure depends on

Read out of the fabricated board, `16b5a606:ee/hw/o2-probe/o2-probe.kicad_pcb`
— the netlist whose gerbers were manufactured, pinned and SHA-256-verified by
`firmware/tools/gen_hw_caps.py`. Coordinates are that file's global mm.

| item | value |
|---|---|
| `U5` | THVD1410, SOIC-8, 1.27 mm pitch, **F.Cu**, origin (103.8, 92) rot 90° |
| `U5.2` (`/RE`) | **(103.165, 94.475)** — net `/RS485_DE` |
| `U5.3` (`DE`) | **(104.435, 94.475)** — net `/RS485_DE` (the same net) |
| `U5.5` (`GND`) | (105.705, 89.525) |
| the short | one **F.Cu** segment, `(104.45, 94.5) → (103.15, 94.5)`, **width 0.09 mm**, plus a ~0.02 mm stub at each pad |
| `U6.30` (PC6, `DE`) | (110.3375, 94.25) — the `/RS485_DE` run lands here |
| `U6.31` (PC7) | **(110.3375, 94.75)** — `unconnected-(U6-PC7-Pad31)`: no track, no via, no test pad |
| `U6` | LQFP-48, **0.5 mm pitch, 0.3 mm pad width**, origin (114.5, 94.5) rot 180° |
| `R7` | 47 k, 0603, **B.Cu**, pad 1 (102.325, 96) → `/RS485_DE`, pad 2 (100.675, 96) → `/GND` |
| `R45` | **does not exist on this board.** It is a Rev B part |

Two consequences of that table are the whole reason this document is longer
than three lines.

**R7 is on the `U5.2` side of the short.** The copper runs `U5.2` → (102.9,
94.75) → (102.65, 94.75) → In1.Cu → B.Cu → `R7.1`. `U5.3` is the side that runs
to PC6. So **cutting the link between the two pads leaves the existing
pull-down on `/RE` and leaves `DE` with none** — and an undriven `DE` is the one
that matters: `main.c` (the bus-jam backstop) leans on R7 holding the *driver*
off through MCU reset, because an undriven `DE` can jam the shared cable and
silence both SMT100s. A cut without a replacement pull-down is a regression, not
a partial improvement.

**PC7 has no copper on it at all.** There is no via or test pad to tap; the wire
has to land on the package pin, 0.3 mm wide on 0.5 mm pitch, with the live `DE`
track terminating on the immediately adjacent pad 30.

## Procedure

Target topology, identical to Rev B: `U5.2` on a net of its own, that net
reaching PC7, and **each enable with its own 47 k pull-down to GND**.

1. **Cut** the F.Cu segment between `U5.2` and `U5.3` — the 0.09 mm trace
   running along the pad row at y ≈ 94.5, between x = 103.165 and x = 104.435.
   Cut near mid-span (x ≈ 103.8) rather than at either pad.
2. **Fit a 47 k** from `U5.3` (DE, (104.435, 94.475)) to `U5.5` (GND, (105.705,
   89.525)) — 5.11 mm, both on the same package, both on F.Cu. This is R7's job
   moving to the DE side; see the nomenclature warning below.
3. **Wire `U5.2` to `U6.31`** (PC7) — 7.18 mm. 34–36 AWG enamelled wire, tacked
   at both ends, restrained so it cannot lift the LQFP pad.
4. **Do not remove or repurpose R7.** After the cut it is the `/RE` pull-down,
   which is exactly the passive default `R45` exists to provide on Rev B: the
   part's `/RE` floats *high* (deaf) on its ~2 MΩ internal pull-up, and every MCU
   GPIO is high-impedance out of reset, so without a pull-down a probe in its
   RS-485 bootloader is unreachable.

### Nomenclature warning, and the alternative

After step 2 the board is electrically Rev B **with R7 and R45's roles
swapped**: the fitted R7 is the `/RE` pull-down and the added resistor is the
`DE` one. Anyone reading `main.c`'s "R7 (47k) already holds the transceiver's
DRIVER off through MCU reset" against a reworked board will find it false as
written — it is the *added* resistor doing that. Mark the board.

**An earlier draft of this document offered a two-cut alternative that would
have left the board with no DE pull-down at all, and it is recorded here rather
than deleted because the reasoning error is the interesting part.** The idea was
to also cut the `U5.2` → R7 stub at (103.15, 94.5) → (102.9, 94.75), "leaving R7
on `DE` where the drawing puts it". It does not: trace the copper and R7 reaches
the transceiver *through* the junction at (103.15, 94.5), which is on the
`U5.2` side. Both cuts therefore isolate R7 from **both** enables — it ends up
hanging off dead copper, `/RE` loses the pull-down it had just been given, and
`DE` still has none. Restoring the designators would need a third wire from R7
back to `U5.3`, which is strictly worse than living with the swapped labels.

The single-cut procedure above is the only one recommended. Caught by an
independent review of 2ac1712, 2026-09-09.

## Acceptance test

**The failure mode to hunt is a solder bridge between `U6.30` and `U6.31`.**
They are adjacent 0.3 mm pads on 0.5 mm pitch, and pad 30 is `DE`. A bridge
re-creates the exact short being removed, 7 mm away from where anyone would look
for it — and, worse, the firmware would then believe it had a split and report a
standby that puts the driver on the bus. Steps 1–3 do not count as done until
step B below has passed.

- **A. Continuity, unpowered.** `U5.2`–`U5.3` open. `U5.2`–`U6.31` short.
  `U5.2`–GND ≈ 47 k (through R7). `U5.3`–GND ≈ 47 k (through the new part).
  `U6.30`–`U6.31` **open** — this is the bridge check and it is the one that
  matters.
- **B. Independence, powered, before trusting anything.** Drive PC6 and PC7 to
  *opposite* levels over SWD and read both pins back, then swap. Two pads that
  are bridged will not disagree. A continuity check on a powered board through
  two GPIO drivers can be misread; this cannot.
- **C. The bus still works.** Full Modbus poll at 9600 8E1, then at 115200 —
  echo suppression is `/RE`'s other job (`loader_uart.c` parses its own reply
  as a request without it), and a `/RE` that no longer follows `DE` during
  transmit shows up here and nowhere else.
- **D. The reachability property.** Hold the MCU in reset and confirm the probe
  still *hears*: `/RE` must sit low on the pull-down alone with no code running.
  This is the field-reflash path of `SCHEMATIC-REVIEW.md` M2 and the reason
  step 4 says do not remove R7.
- **E. The saving is real.** Board idle current before and after
  `o2p_modbus_rx_standby(true)`, expected ≈ 630 µA apart. Measure it rather than
  quoting this document: the number above is derived from SLLSEY3E and a 47 k
  resistor, not from this article.

## Firmware, after the rework

The firmware already knows the difference and currently answers "no". Rev A's
generated capability header says:

```c
#define O2P_HW_RS485_RE_ON_ITS_OWN_PIN 0
#define O2P_HW_RS485_RE_PASSIVE_PULLDOWN 0
```

so `o2p_modbus_rx_standby(true)` **refuses** on this board rather than writing a
pin that goes nowhere and reporting a standby the copper cannot hold. That is
the current, correct state, and it is pinned by
`test_this_board_cannot_be_commanded_transceiver_deaf` in the host suite.

Turning it on is deliberately not a one-line edit. `gen_hw_caps.py` derives Rev
A's capabilities from **the fabricated netlist pinned at `16b5a606` and verified
by SHA-256**, and its header says why: *"A fabricated article's wiring cannot
legitimately change, so it is pinned by commit AND verified by content."* A
rework makes that sentence false for one article — the copper changed, on
purpose, and the pinned commit is still the honest record of what was
manufactured. So do **not** edit the hash or re-point `REV_A_COMMIT`. Introduce
the reworked board as its own revision (`A_MOD`, with its own pinned netlist and
its own `hw_caps_rev_a_mod.h`), and build for it explicitly — the same argument
`hw_caps.h` already makes for refusing a default revision. Then the host test
above is edited, and its comment says so.

That is more ceremony than a bench hack wants, and it is the point: the failure
this whole capability split was built after was firmware asserting a wiring the
board did not have.
