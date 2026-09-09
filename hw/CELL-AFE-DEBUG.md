# Debugging the cell + AFE: expected voltages, rails, and settling

General procedure, not an incident record. Written 2026-09-09 after three
separate sessions each rediscovered the same numbers from scratch. Incident
records live in `AFE-BRING-UP-POSTMORTEM.md` (2026-09-04, A1 failure),
`PIN-IDENTITY-POSTMORTEM.md`, `docs/2026-09-08-evening-board-failures.md` and
`docs/2026-09-09-afe-rework-debug.md`.

Applies to the LMP91000 (U7) driving an SGX-OX-ROHS-Mini cell, as configured by
`firmware/src/lmp91000.h`.

---

## 1. The numbers everything else is measured against

Configuration, from `O2P_LMP_TIACN_INTENDED` / `O2P_LMP_REFCN_INTENDED`:

| parameter | value | source |
|---|---|---|
| TIA gain | 7 kΩ | `TIACN` TIA_GAIN 011 |
| internal zero | **0.67 × VREF** | `REFCN` INT_Z 10 = 67 % |
| commanded bias | **24 % of VREF** | `REFCN` BIAS 1101; ~599 mV at VREF 2496 |
| bias polarity | **RE above WE** | BIAS_SIGN 0 = (V_WE − V_RE) < 0 |

Do not carry the bias around as a fixed millivolt figure. It is a *percentage
of the measured reference*, so it moves with VREF: 599.0 mV at 2496, 595.2 mV
at the 2480 spec floor, 600.0 mV at the 2500 target. Firmware derives it with
`o2p_lmp_commanded_bias_mv()` from `O2P_LMP_REFCN_INTENDED` for exactly this
reason — two hand-copied literals agree today and go stale together.

**The polarity is the one to get right.** `BIAS_SIGN 0` means
(V_WE − V_RE) < 0, so **RE sits ~599 mV ABOVE WE**. An earlier version of this
document said "RE below WE" in prose while its own table said WE + 598 — the
table was right. A sign slip here makes the guard fire on every healthy probe
instead of no broken one.

With a healthy VREF of 2496 mV:

| node | expected | how obtained |
|---|---|---|
| internal zero | **1672 mV** | derived, 0.67 × 2496 |
| **WE** (U7.12) | **1672 mV** | derived; virtual ground held by A2 |
| **RE** (U7.13) | **2271 mV** | derived, WE + 599 |
| **R − W** | **599 mV** | derived; *the* regulation check |
| **CE** (U7.14) | no expected value | see below |
| VOUT, cell out | ~1650 mV | measured 2026-09-09, ~2.5 µA |
| VOUT, cell in air | 900–1000 mV | measured 2026-09-09, 100 µA region |

**Every "expected" above is DERIVED, not measured**, and that distinction is
load-bearing. An earlier version of this table listed 1678 / 2275 / 2875 as
expectations; those are single measurements from `AFE-BRING-UP-POSTMORTEM.md`
§1, taken on a different board state with a symmetric 1 MΩ/1 MΩ dummy in place
of the cell and a different reference voltage. They are consistent with the
derivation, but they are not a specification, and a couple of millivolts of
disagreement with them means nothing.

**CE has no expected value at all.** A1 drives CE to whatever the particular
cell's compliance requires; it is an output, not a setpoint. What CE tells you
is a *direction*, not a number:

| CE reads | meaning |
|---|---|
| at either rail | A1 saturated — the loop cannot close |
| at the internal zero | A1 idle or dead |
| between, and stable | healthy, whatever the value |

The one hard limit is the specified drive window: SNAS506 characterises A1 only
over `300 mV ≤ V_CE ≤ VS − 300 mV`, which `hw_contract.h` puts at 300–2934 mV
for this board's worst-case rail. Outside that the amplifier is not specified,
so treat it as a fault rather than a reading.

Current from VOUT:

```
I = (0.67 × VREF_at_U7_pin_11  −  VOUT) / 7 kΩ
```

VOUT swings from the internal zero toward ground, so the arithmetic runs out at
about **239 µA** (1672 mV / 7 kΩ). Treat that as a nominal bound, not a
threshold: it assumes the TIA output reaches exactly 0 V and R_TIA is at its
nominal 7 kΩ (5 % gain accuracy, and SNAS506 does not specify a guaranteed
output-low swing). It is where the number stops meaning anything, which is all
you need it for.

152 µA is *not* the ceiling — it is the design point at 30 % O₂
(`lmp91000.h:41-43`), chosen so 30 % fits inside range.

Expected cell current in room air, **DS-0637 Issue 2**:
**0.1 ± 0.03 mA = 70–130 µA**.

> Issue 1 said 0.07 ± 0.03 mA = 40–100 µA and is superseded. Both PDFs are in
> `compostlab-literature/datasheets/`; read Issue 2. The first version of this
> document quoted Issue 1, which made a perfectly nominal 99.9 µA look like it
> was at the top of spec. `PIN-IDENTITY-POSTMORTEM.md:416` already had this
> right.

---

## 2. The trap that has cost two AFEs

**A current computed while the chip has no reference is not a current.**

If U7 pin 11 (`VREF_TRIM`) is open or sagging, the internal zero is 0, so the
TIA parks VOUT at ground for reasons unrelated to current. Substituting the
*board's* `ADC_VREF_MON` into the formula above then yields **≈ 238 µA** — just
above the DS-0637 air spec, just at the clip point, and entirely fictitious.

That number was quoted as measured at least four times across 2026-09-08 and
2026-09-09 and led to an AFE replacement. The chip was healthy.

**Why no converter catches this.** On the fabricated Rev A board, U7 pin 11 and
the ADS1119's own reference pin U8.7 are the **same net**, `/VREF_TRIM`, and the
monitor divider R34/R35 taps that same net. So `ADC_VREF_MON` is reading the
right node — and it still cannot see the fault, because **the open is at the
package pin**. The net stays at 2.5 V, the monitor reads it happily, and the die
is attached to nothing. Measured 2026-09-09: `vref` reported 2490 mV while the
AFE's internal zero was 0 V.

> An earlier version of this section said the trimmer sat between the monitor
> and pin 11. It does not: RV1 is on `/VREF_TOP` → `/VREF_WIPER`, upstream of
> the buffer. (Rev A has that trimmer; Rev B has none — `hw_contract.h` says
> "There is no trimmer", which is a Rev B statement.) The conclusion is
> unchanged and in fact stronger: **monitoring the reference harder cannot
> detect this**, so do not propose a guard built on it.

**Rule: VOUT at either rail invalidates the derived current.** Do not quote a
current until the chip's reference is independently established.

### What does and does not prove the reference is present

**WE ≈ 0.67 × VREF is the test.** WE at 0 V is the unmistakable signature of a
lost reference, because the internal zero is 0.67 × 0. On Rev A this needs a
meter on U7.12; on Rev B, `we_buf` is a real ADC channel and firmware can make
this check itself — which is the actual answer to "how do we detect a lost
reference", and it comes free with `AFE-BRING-UP-POSTMORTEM.md` §3.3.

**`t_afe` being valid does NOT prove it.** An earlier version of this document
said the die sensor is referred to the same rail, so a plausible temperature
meant pin 11 had its voltage. That is wrong: **SNAS506I §7.3.1.5 specifies the
temperature output as ground-referred**, and OP_MODE 111 merely routes it to
VOUT. The 2026-09-09 timeline is its own counterexample — `t_afe` went valid at
12:57, five minutes *before* the open pin 11 was found. A valid `t_afe` proves
the I²C path, the mode switch and the ADC chain. It says nothing about VREF.

---

## 3. Reading the rails

| VOUT | means |
|---|---|
| **~0 mV**, WE also 0 V | no reference at pin 11. **Not** an overcurrent |
| **~0 mV**, WE at 1672 mV, VREF confirmed | current is large — but see below |
| **~0 mV**, WE *above* 1672 mV | so much current that A2 lost the virtual ground |
| **positive rail** (~VREF) | *not* zero current — the formula gives ≈ −118 µA, i.e. current flowing the wrong way. Check cell orientation and the C-R-W order |
| frozen to the LSB across a swap | **interconnect fault, not a device fault** — see §5 |

**A bottom-rail VOUT does not identify where the current comes from.** It says
the TIA summing node is being fed faster than it can sink; it does not say the
*cell* is doing it. On 2026-09-09 the actual cause was A1 pushing current
through an R–W short — the electrodes were fine, and so were both chips. Treat a
railed VOUT as "excess current into WE, source unknown" and use §5 to find it.

`R − W` is the single most informative measurement on the board:

| R − W | means |
|---|---|
| **~599 mV** (24 % of VREF) | loop in regulation. Trust the current |
| **0 mV** | RE and WE shorted. A1 cannot converge, rails, dumps current into WE |
| **small, and C − W ≈ 599 mV** | **RE not sensing.** Bias landed on CE-to-WE instead |
| climbing over minutes | the cell is polarising — wait, see §4 |

A floating RE input was observed at **~2.27 V** on 2026-09-09, matching the
guard replica measured at U4 pins 5/6/7. That is one observation on one board,
not a specification — a high-impedance input picks up whatever is adjacent, and
the guard replica is what happens to be adjacent here. Useful as corroboration,
never as the sole evidence for an open RE; confirm with continuity from U7.13.

---

## 4. Settling: what is normal and what is stuck

DS-0637 Note 1 allows **up to 15 minutes** for the cell to settle after a bias
is applied. The firmware enforces its own settle window and reports
`o2raw = -32768` (invalid) until it expires — that is correct behaviour, not a
fault.

Normal recovery after a bias is restored, measured 2026-09-09:

```
R−W  155 → 285 → 320 mV over ~4 min      (loop closing, looks like a plateau)
R−W  600 mV                              (regulation reached, abruptly)
VOUT   17 → 796 → 908 → 944 mV           (comes off the rail within one sample)
I     236 → 125 → 109 → 104 µA           (decays for several more minutes)
```

**Do not extrapolate a settling curve from three samples.** Steps of +130 then
+35 mV predicted an asymptote at ~335 mV and "the loop will never converge". It
reached 600 mV two minutes later. Those points were the middle of an S-curve.

Anything that unbiases the cell restarts the 15-minute clock: power cycle, an
SWD attach that resets the MCU, OP_MODE 000 / 010 / **110**. Mode 110 is
temperature-with-TIA-*off* and must never be used here; 111 gives the same
reading with the TIA still on (`lmp91000.h:68-74`).

A current that is **frozen to the LSB** is not settling. A real cell dithers in
the low bits; a polarising one ramps.

---

## 5. Decision procedure

Work top to bottom. Each step is cheap and rules out a whole class.

1. **Is the AFE on the bus?** `lmp_readback` should be `0x0CCD`, `i2c_errs` 0.
   `0x0000` with a climbing error count = I²C fault; check MENB (U7.2) and
   joints on pins 3/4/6. **R17 is a 100 kΩ pull-DOWN to GND** (`gen_sch.py:740`,
   asserted at `:1189`), and MENB is active-low, so MENB *should* read low and
   continuity from U7.2 to ground through 100 kΩ is correct. An earlier version
   of this document called R17 a pull-up, which would send you to rework a good
   joint. This is independent of every analog fault.

2. **Does the chip have its reference?** **WE ≈ 1672 mV (0.67 × VREF)** — this
   is the test, and on Rev A it needs a meter on U7.12. `t_afe` does NOT answer
   this (see §2). If WE is 0 V, measure **U7 pin 11 — expect ~2.5 V**. If pin 11
   is low, check **U4 pin 1** before concluding pin 11 is shorted: pin 11 may
   simply be following a dead source. U4 pin 8 = 3.3 V, pin 3 = 2.5 V in,
   pin 1 = 2.5 V out, pin 7 = 2.27 V guard replica.
   **Until this passes, no current reading means anything.**

3. **Cell out / cell in.** The fastest board-vs-cell split, and it needs no
   meter. Cell out should give VOUT ≈ 1650 mV, ~2.5 µA. Clean with the cell out
   and pinned with it in ⇒ the current enters through the connector.

4. **Is the loop in regulation?** `R − W` ≈ 599 mV (24 % of VREF). If not, use the §3 table.

5. **Only now, read the current.** And give it the settle time from §4.

### Two tests that do not work

**An ohmmeter cannot exonerate the cell, and convicts it only grossly.** A cell
under bias is a current source set by oxygen diffusion, not an ohmic path: it
passes ~100 µA while reading megohms to a meter. So a *high* reading proves
nothing at all. A *low* reading — tens of kΩ or less between C and W — is
evidence of a gross short, but it is weaker evidence than it looks: a DMM in
resistance mode applies its own excitation with the third electrode
uncontrolled, so the reading depends on the meter, the polarity and how long
you hold the probes. Record which terminals, which polarity and which meter, or
the number is not reproducible. Dividing a measured C−W voltage by the TIA
current to get a "cell resistance" is invalid in every case — that reasoning
produced a spurious "≤1.7 kΩ" here, since the current used in it was itself
computed through a missing reference.

**Swapping the cell proves less than it seems.** Two different cells reading
identically does rule out the cell — but only if every other fault is stable
across the swap. On 2026-09-09 two cells and two AFEs all read 22 mV because an
R–W short dominated all four combinations.

---

## 6. Rev A observability gaps (read before trusting telemetry)

On the fabricated Rev A board — commit **`16b5a606`**, the one on the bench —
several telemetry fields do not measure what their names say:

| field | actually measures |
|---|---|
| `we_buf` | `ADC_VA_MON` — the VA rail (AIN2) |
| `re_buf` | `ADC_VIN_MON` — the VIN rail (AIN3) |
| `cell_bias_mv` | derived from the two above; **has never measured the cell** |
| `ce_mv` | scaling unverified — reported 1806 mV while CE measured 3280 mV |
| pin 11 (`VREF_TRIM`) | monitored as a *net* (AIN1), but see below |

`ADC_VREF_MON` (AIN1) does tap `/VREF_TRIM`, the same net as U7.11 — so the node
is monitored. What is *not* observable is an **open joint at the package pin**,
which leaves the net and the monitor perfectly healthy. No extra converter fixes
that; the detector is WE ≈ 0.67 × VREF, which needs `we_buf` to be a real
electrode channel.

Consequences on this board: the bias guard would raise `AFE_CONFIG_MISMATCH`
(`faults` bit 5) on a quantity unrelated to the cell, and a reference lost at
the pin is invisible to firmware. **Prefer the meter over these fields.**

Since `28b8a75` the firmware derives this per revision rather than assuming it:
`O2P_HW_BIAS_ADC_REACHES_ELECTRODES` is generated from each revision's own
netlist and is 0 for Rev A, so the guard reports `BIAS_UNKNOWN` instead of a
verdict. `src/hw_caps_rev_a.h` carries the channel names, so a diagnosis never
has to guess which board's map it is reading. Extract the fabricated netlist
with `git show 16b5a606` — or run `python3 tools/pcb_netlist.py` — earlier work
read a *different* PCB revision and sent Fab after U4 followers and R37/R38 that
do not exist on the bench board.

Rev B asks that follow from this: buffer WE and RE into real ADC channels
(which also gives firmware the WE ≈ 0.67 × VREF check), and fix the connector
pin order so the C-R-W crossing wires are no longer needed. See
`AFE-BRING-UP-POSTMORTEM.md` §3.3, §3.4 and §3.7.

---

## 7. Tooling notes

`/tmp/o2p_probe.py` reads the live snapshot over the OpenOCD TCL port (6666)
**without halting the target**, so it occasionally tears across a buffer flip
and returns a row with `lmp_readback = 0x0000`, `ce = 33`, `t_afe = 0`. One such
row looks exactly like the AFE dropping off the I²C bus. **Re-read before
reporting** — a torn row does not repeat.

Each SWD attach resets the MCU, which unbiases the cell and restarts the settle
window. Budget 15 minutes per attach.
