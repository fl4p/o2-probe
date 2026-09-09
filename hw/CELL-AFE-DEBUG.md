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
| commanded bias | **−598 mV** | 24 % of 2480 mV, BIAS_SIGN 0 |
| bias polarity | RE **below** WE | |

With a healthy VREF of 2496 mV:

| node | expected | meaning |
|---|---|---|
| internal zero | **1672 mV** | 0.67 × 2496 |
| **WE** (U7.12) | **1672–1678 mV** | virtual ground, held by A2 |
| **RE** (U7.13) | **2271–2275 mV** | WE + 598 mV |
| **CE** (U7.14) | 2870 mV typ. | whatever A1 needs; varies with the cell |
| **R − W** | **598 mV** | *the* regulation check |
| VOUT, cell out | ~1650 mV | ≈ internal zero, ~2.5 µA |
| VOUT, cell in air | 900–1000 mV | 100 µA region |

Current from VOUT:

```
I = (0.67 × VREF_at_U7_pin_11  −  VOUT) / 7 kΩ
```

VOUT swings from the internal zero down to ground, so the TIA clips at
**~239 µA** (1672 mV / 7 kΩ). Note 152 µA is *not* the ceiling — it is the
design point at 30 % O₂ (`lmp91000.h:41-43`), chosen so 30 % fits inside range.

Expected cell current in room air, DS-0637: **0.07 ± 0.03 mA = 40–100 µA**.

---

## 2. The trap that has cost two AFEs

**A current computed while the chip has no reference is not a current.**

If U7 pin 11 (`VREF_TRIM`) is open or sagging, the internal zero is 0, so the
TIA parks VOUT at ground for reasons unrelated to current. Substituting the
*board's* `ADC_VREF_MON` into the formula above then yields **≈ 238 µA** — just
above the DS-0637 air spec, just at the clip point, and entirely fictitious.

That number was quoted as measured at least four times across 2026-09-08 and
2026-09-09 and led to an AFE replacement. The chip was healthy.

`ADC_VREF_MON` watches the reference **network**; U7 pin 11 is fed from it
**through the trimmer**. They are different nodes and a fault between them shows
a healthy `vref` in telemetry while the chip has none. Rev A has no monitor on
pin 11 — see §6.

**Rule: VOUT at either rail invalidates the derived current.** Do not quote a
current until the chip's reference is independently established.

Cheapest positive evidence that the reference is present:

- **`t_afe` is valid and plausible.** The die sensor is referred to the same
  rail, so a sane temperature means pin 11 has its voltage. Invalid `t_afe`
  (−32768) alongside a railed VOUT means *suspect the reference first*.
- **WE measures ~1672 mV.** WE at 0 V is the unmistakable signature of a lost
  reference: internal zero = 0.67 × 0.

---

## 3. Reading the rails

| VOUT | means |
|---|---|
| **~0 mV**, WE also 0 V | no reference at pin 11. **Not** an overcurrent |
| **~0 mV**, WE at 1672 mV, `t_afe` valid | genuine overcurrent, >239 µA |
| **~0 mV**, WE *above* 1672 mV | overcurrent so large A2 lost the virtual ground |
| **positive rail** (~VREF) | current near zero or reversed; check cell orientation |
| frozen to the LSB across a swap | **interconnect fault, not a device fault** — see §5 |

`R − W` is the single most informative measurement on the board:

| R − W | means |
|---|---|
| **598 mV** | loop in regulation. Trust the current |
| **0 mV** | RE and WE shorted. A1 cannot converge, rails, dumps current into WE |
| **small, and C − W ≈ 598 mV** | **RE not sensing.** Bias landed on CE-to-WE instead |
| climbing over minutes | the cell is polarising — wait, see §4 |

A floating RE input sits at the **guard replica potential, ~2.27 V** (U4 pins
5/6/7). RE reading 2.27 V when the loop is out of regulation is a fingerprint of
an open reference electrode, not a coincidence.

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
   `0x0000` with a climbing error count = I²C fault; check MENB (U7.2, pull-up
   R17), and joints on pins 3/4/6. This is independent of every analog fault.

2. **Does the chip have its reference?** `t_afe` valid, and WE ≈ 1672 mV. If WE
   is 0 V, measure **U7 pin 11 — expect ~2.5 V**. If pin 11 is low, check U4
   (reference buffer) pin 1 before concluding pin 11 is shorted: pin 11 may
   simply be following a dead source. U4 pin 8 = 3.3 V, pin 3 = 2.5 V in,
   pin 1 = 2.5 V out, pin 7 = 2.27 V guard replica.
   **Until this passes, no current reading means anything.**

3. **Cell out / cell in.** The fastest board-vs-cell split, and it needs no
   meter. Cell out should give VOUT ≈ 1650 mV, ~2.5 µA. Clean with the cell out
   and pinned with it in ⇒ the current enters through the connector.

4. **Is the loop in regulation?** `R − W` = 598 mV. If not, use the §3 table.

5. **Only now, read the current.** And give it the settle time from §4.

### Two tests that do not work

**An ohmmeter cannot exonerate or convict the cell.** A cell under bias is a
current source set by oxygen diffusion, not an ohmic path: it passes ~100 µA
while reading >1 MΩ to a meter. A *low* reading proves a short; a high reading
proves nothing. Dividing the measured C−W voltage by the TIA current to get a
"cell resistance" is invalid — that reasoning produced a spurious "≤1.7 kΩ".

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
| pin 11 (`VREF_TRIM`) | **not monitored at all** |

Consequences: the bias guard raises `AFE_CONFIG_MISMATCH` (`faults` bit 5) on a
quantity unrelated to the cell, and a lost reference is invisible to firmware.
**Prefer the meter over these fields.** Extract the fabricated netlist with
`git show 16b5a606` — earlier work read a *different* PCB revision and sent Fab
after U4 followers and R37/R38 that do not exist on the bench board.

Rev B asks that follow from this: monitor pin 11 (or move `ADC_VREF_MON`'s tap
to the wiper side), buffer WE and RE into real ADC channels, and fix the
connector pin order so the C-R-W crossing wires are no longer needed. See
`AFE-BRING-UP-POSTMORTEM.md` §3.3 and §3.4.

---

## 7. Tooling notes

`/tmp/o2p_probe.py` reads the live snapshot over the OpenOCD TCL port (6666)
**without halting the target**, so it occasionally tears across a buffer flip
and returns a row with `lmp_readback = 0x0000`, `ce = 33`, `t_afe = 0`. One such
row looks exactly like the AFE dropping off the I²C bus. **Re-read before
reporting** — a torn row does not repeat.

Each SWD attach resets the MCU, which unbiases the cell and restarts the settle
window. Budget 15 minutes per attach.
