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

### 2026-09-10 evening: the net itself collapsed — the mirror image of the §2 trap

§2's trap was an open package pin on a healthy net: the monitor read 2.5 V
while the die was attached to nothing. On 2026-09-10 the net itself went
down, and the two together are the reason a meter is mandatory on both
sides of the buffer.

Measured on Probe 3 (Rev A, unpotted, after the day's 80 °C bath and heater
runs), 16:45–17:00 UTC:

| node | value | source |
|---|---|---|
| `/VREF_TRIM` (U7.11 = ADS1119 REF U8.7 = R34/R35 tap) | **233 mV** | meter at the pin; `ADC_VREF_MON` 232 mV — same net, they agree |
| `/VREF_WIPER` | 2.344 V | meter |
| `/VREF_TOP` | 2.68 V | meter |

The feed is healthy, so the fault is between the wiper and the net: the
buffer (U4 — `AFE-BRING-UP-POSTMORTEM.md` puts RV1 "upstream of U4") or
the net itself. With the net down, measured: `O2_RAW`, `WE_BUF`, `RE_BUF`,
`CELL_BIAS`, `T_AFE` all invalid, `afe_vout` 9–16 mV and still sinking,
while `i2c_errs` 0, `lmp_readback` 0x0CCD, `ads_fail_count` 0 and `VA_MON`
3.29 V. **Every digital check green, every analog quantity dead** — that
is the reference-net signature. It is not an I²C failure, and swapping the
LMP91000 or the ADS1119 will not fix it (§2 already cost one AFE to a
cousin of that assumption).

Two follow-ups, in order:

1. 2344 mV ÷ 10 = 234 mV. If the exact tenth is not a coincidence,
   something bridges WIPER to TRIM through a 9:1 path and the net is
   UNDRIVEN, not leaking. Power off, ohms TRIM→GND, read against the
   R34/R35 schematic values: a driven net at 233 mV means a leak — start at
   the U7 pins 10–13 edge, which owns four prior faults (09-08 bridge,
   09-09 open pin 11, 09-09 R–W short, 09-09 reference collapse) and was
   soaked today; an undriven net means U4 or its trace.
2. Once VREF is back (~2.496 V; WE ≈ 0.67 × VREF ≈ 1672 mV; no cell fitted,
   `afe_vout` ≈ 1675 mV textbook), run the 10 kΩ dummy-cell test that has
   never been run.

**Update, same evening: the leak is quantified — U4 is exonerated, hunt the
net.** Meter at U4.1 (`/VREF_BUF`, the follower output, isolated from the
net by R31 = 47 Ω per SCHEMATIC-REVIEW.md "H1" — C10 = 4.7 µF and all
LMP91000/ADS1119/guard loads sit ON `/VREF_TRIM`): **431 mV**, while the
net holds 233 mV. Arithmetic across R31: (431 − 233) mV / 47 Ω =
**4.2 mA flowing into the net**, which sits at 233 mV → the net leaks
through ≈ **55 Ω to ground**. Self-check: 431 × 55.3/(55.3 + 47) =
232.9 mV — three readings agreeing to three digits, so they are
simultaneous and real. The follower is alive and in current limit: holding
2.344 V into 47 + 55 Ω needs ~23 mA, a 17 µA-IQ chopper delivers ~4 mA and
collapses to 431 mV. The fault is ON the net, not upstream of R31.

Prime suspect: **C10, the 4.7 µF MLCC on `/VREF_TRIM`** — the only bulk
part on the net. A cracked MLCC leaks ohms-to-kΩ, drifts with temperature
and voltage, and can "heal" and re-fail, which fits the whole history:
the 09-09 collapse that "cleared", today's re-collapse after the 80 °C
bath + heater runs, and the monitor drifting 232 → 226 → 228 mV while
idle. Confirm power-off: ohms across C10's pads — every parallel path is
≥ 47 Ω + 93 kΩ, so a ~55 Ω reading is C10 itself. If C10 reads open, fall
back to the U7 pins 10–13 edge (the 09-08 bridge site), U8.7's neighbors,
R34/R35, then the net vias, in that order. Flex or warm the C10 area
gently while watching `ADC_VREF_MON` (the keeper reads it in ~2 s) — a
cracked cap jumps. The 2344/10 numerology above is dead: the net voltage
is the amp's current limit intersecting the leak, nothing to do with the
wiper ratio.

**Confirmed, same evening: C10 is the leak.** Power off, ohms directly
across C10's pads: **~60 Ω** (predicted ~55 from the live arithmetic; every
parallel path on those pads is ≥ 93 kΩ). Replace C10 — 1–4.7 µF X7R is
fine, it is reference decoupling behind R31, not a timing part, but this
board heat-cycles by design so prefer a smaller case or flexible
terminations over another large rigid MLCC there. Post-removal checks:
the board's C10 pads should read ~93 kΩ (the divider alone); the lifted
part should still read tens of Ω on the bench — if it reads healthy out
of circuit, the 60 Ω lived in the pad/solder joints instead (same fix,
different root cause, worth knowing). Then: power up, watch for the
recovery signature (VREF ~2496 mV, T_AFE and WE_BUF/RE_BUF valid,
afe_vout ≈ 1675 mV no-cell, O2_RAW valid only after the up-to-15-min
settle window, §4), re-arm the heater, and run the never-run 10 kΩ
dummy-cell test.

**Correction, same evening: C10 was NOT the leak — the 60 Ω attribution
was circular.** "60 Ω across C10" was pads-to-ground through the
footprint, i.e. the whole net's leak; treating it as C10's own resistance
assumed away the very leak being hunted. C10 removed and the board
repowered: `/VREF_TRIM` still collapsed (monitor 240 → 246 mV, empty
footprint 250 mV live, `afe_vout` 33 mV still dead). The fabricated Rev A
netlist (`git show 16b5a606` + `firmware/tools/pcb_netlist.py`) puts the
net's membership at: R31.2 (feed), R34.1 (divider → `VREF_MON_RAW` → R35
→ GND), U7.11, U8.7, C10.1 (now empty). Suspects, in test order:

1. **Chip-input protection, power off, ohms at the pins:** U7.11 → U7.1
   (GND; U7 GND pads are 1, 7, 15) and U8.7 → U8.2 (GND; U8 GND pads are
   2, 3, 6, 15, 16, 17). ~60 Ω either way = that chip's input protection
   is leaking internally → replace the chip. The U7 pins 10–13 edge
   (LMP_C1, VREF_TRIM, CELL_WE, CELL_RE — no adjacent GND pin) has four
   prior rework faults; U7 internal damage is credible.
2. **Surface contamination:** the net drifted UP as the board dried
   (226 → 234 → 240 → 246 mV over ~15 min), the board was soaked and
   boiled today, and the 09-09 collapse "cleared" (probably a cleaning).
   IPA + brush the whole AFE region, dry, re-ohm the empty footprint →
   GND. A spontaneous full recovery while drying is the contamination
   verdict delivered by the data (the keeper watches `ADC_VREF_MON`
   every 60 s).
3. Copper/via last: a cracked via partially shorting to a ground via is
   exotic but not impossible.

Close C10's file separately: ohms on the lifted part alone — tens of Ω
= it was also guilty; charging/open = innocent (likely, given the above).

**Collapse timestamp pinned (VictoriaMetrics, same evening):** the
ADS1119's last valid conversions landed at **15:01** — `AFE_VOUT` blipped
963 → 1026 mV on its way down — and from **15:02** every overrange
channel reads 0xFFFF (`gas_vin_mv`, `gas_afe_mv`, the lot). The reference
collapsed at **~15:01, in the wet/heating afternoon, eight minutes
before the first of the five resets** (15:10). Note the asymmetry:
channels above the collapsed reference go invalid; channels below it
still convert to garbage (AFE_VOUT has read ~10 mV all evening). Last
valid `VIN_MON` readings: 10.57–10.79 V (14:48–15:01); earlier
bench-era eras read 9.65–9.79 V (stuck at exactly 9.74 V for hours
overnight) and ~11.1 V three days ago — absolute trust in these is low
(§6). Observability lesson: **the fault blinded the board's only remote
supply monitor** — VIN is ADS1119-converted, so once VREF collapses,
only a bench meter can see the rail under load.

**RECOVERED, same evening ~18:02 — bake-dried contamination is the
leading explanation.** After the IPA surface clean (no change) and a
~20-minute bake (heater to 80 °C setpoint), `/VREF_TRIM` stepped
302 → 2488 mV at 18:02 **while hot** and has held 2494–2496 mV through
heater duty swings to 92–100 %. The thermal-ionic signature was confirmed
before it died: 174 mV with local heat, 322 mV plateau cold outdoors,
climbing while cooling — a resistance that halves in minutes with
temperature is contamination, not silicon; U7/U8 internal damage is
exonerated without lifting anything. Recovery timing coincided with the
duty throttle 100 % → 2 % (a confound), but VREF later held at high duty
and `VIN_MON` showed no sag under load — supply coupling is weakened,
not proven dead. AFE woke with it: `faults` dropped 2560 → 512 (18:12),
`AFE_VOUT` settling ~952 mV, `T_AFE` valid (40–41 °C), `O2_RAW`
converting; settle window §4 restarted at recovery.

**Edding 751 paint applied ~18:13 by Fab around U7, U8 and U4 — AFTER
the recovery, so it is insurance, not the cause.** Documented risks:
it seals residue in, not out (works until the film fails); a thick
paint-marker film is not rated for this board's thermal cycling — expect
micro-cracking over days-to-weeks, and cracked film + humidity holds
water against the pins; the U7 pins 10–13 edge (four prior faults) is
now uninspectable without solvent; the ink is not a qualified conformal
coating and was applied wet with the board powered. Durable fix remains:
strip, clean under the packages, thin qualified conformal coat. The
paint's verdict comes from days of thermal cycles and the next humid
exposure, not from tonight.

**Rule addition: `VA_MON` valid and `i2c_errs` zero prove nothing about the
reference.** The only measurement that splits this is WIPER vs TRIM, and it
needs a meter.

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

## 2026-09-10 ~23:00 — WE_BUF/RE_BUF 0xFFFF closed as a NON-QUESTION on Rev A; VOUT 975 mV is open-input

- **Correction of the standing premise.** Earlier notes treated
  `WE_BUF/RE_BUF` (`0x0025`/`0x0026`) reading `0xFFFF` as "either residual AFE
  trouble or honest floating-electrode overrange, to be settled by the
  dummy-cell test." Wrong on this board: `hw_caps_rev_a.h:36` sets
  `O2P_HW_BIAS_ADC_REACHES_ELECTRODES 0` — AIN2/AIN3 are wired to
  `/ADC_VA_MON` and `/ADC_VIN_MON` (hw_caps_rev_a.h:12-13), so those two
  registers have **no measurement behind them at all on Rev A** and read the
  sentinel in every cycle, whatever is connected to the cell pads
  (main.c:finish_electrode only writes them under the Rev B caps). The rail
  data reaches `va_mv`/`vin_mv` instead. They come alive on Rev B. The
  dummy-cell test cannot move them on this board — drop that expectation.
- **What the dummy-cell test CAN answer on Rev A** (all via the O2 chain):
  `O2_RAW` (a 10 kΩ across WE/RE gives a definite µA), `AFE_VOUT`
  (`0x0013`), `CE_MV` (`0x002D`), and the bias verdict.
- **AFE_VOUT ≈ 975 mV explained as open-input, not an anomaly to chase.**
  VOUT is the converter's own output, published unconditionally as a rail
  diagnostic (main.c:977: "24 mV named the pin 10-11 bridge and 2495 mV named
  the collapsed A1"). With no cell attached the TIA input floats and the
  output parks mid-scale; the ~1675 mV expectation (0.67 × VREF 2494) assumed
  a cell load holding the input at the LMP internal zero. One dummy cell
  answers it. Post-0x0010 reboot: VOUT 975, VREF 2494, O2_RAW 98.97 µA (air
  band, cal point 99.16).

## 2026-09-10 ~22:20 — the sustained 80 °C soak: VREF falls with tip
temperature again; the heater disarm has two arms

The evening recovery (§2, 18:02) held VREF 2494–2496 mV through
minutes-scale heater duty swings. The sustained soak is a different
regime, and it re-activated the contamination. Heater armed at 80.00 °C
setpoint, 100 % duty cap (0x0049=8000, consent 0x004A), ~94 % duty at
steady state:

| tip temp | VREF | notes |
|---|---|---|
| 63 °C | 2416 mV | falling |
| ~75 °C | 2304 mV | |
| 79.7 °C | **2258 mV** | ~94 % duty, steady soak |
| duty backed off | 2404 mV | recovering as it cooled |

That is the second temperature-reversal of the same resistance (first:
the 18:02 bake-dry recovery) — reversibility with temperature keeps
pointing at ionic contamination, not silicon. And the Edding paint
(applied 18:13, after recovery) did **not** prevent the fall under soak:
first data point for the paint verdict, and it is not in the paint's
favour.

The AFE during the soak: stuck in SETTLING, 12 settle restarts, ~10
missed ADS conversions; `O2_RAW`, `T_AFE`, `VIN` invalid;
`AFE_VOUT` ~10 mV — that is firmware honesty ("no cell current"), the
same signature as the collapsed-net era, not a new fault.

Supply at full duty: `VIN_MON` sagged to **10.2 V**, `VA_MON` 3.16 V,
and the probe rebooted ~20:49 local (uptime regs 0x0016/0x0017; reset
counter 0x001A read 12). With VREF down, VIN is ADS1119-converted and
therefore blind (§3/§6) — trust the sag only as a lower bound. The
firmware TIP_LIMIT 82/77 °C backstop held throughout: tip never
exceeded ~79.8 °C into an 80 °C setpoint.

**Operational lesson — the heater has two independent arms, and disarming
one does nothing to the other:**

- `0x0060` = volatile bench override (test arm; the firmware's own disarm
  command writes 0 here)
- `0x004A` = persistent tip-temp consent — **committed to flash it
  survives reboots**

Tonight: the dashboard's disarm cleared only 0x0060 and reported
success; the probe rebooted after the OTA flash, restored the committed
consent from NVM, and the heater re-armed itself at 80 °C while the UI
said DISARMED. The keeper's atomic write+readback caught the honest
failure shape (`0x0060 readback 1 != written 36519` — the register
reflects the combined arm state). Kill sequence, verified: write
`0x004A=0`, then `0x0060=0`, confirm both read back 0, then commit
(`0x003E=0x5AC1`) so the next reboot restores DISARMED. Dashboard fixed
accordingly (web-ble `1ffa508`: both arms, consent first, readback
verified or it throws).

Probe left disarmed and committed at ~22:10 local; output register 0,
tip cooling 79.8 → 44.5 °C over ~10 min. The bench verdict on sustained
high-temperature operation is Fab's call, but the data says: at 80 °C
soak the reference collapses, the AFE stops converting, and the supply
sags to a reboot — while the firmware's own backstop never flinched.

### Addendum ~23:30 — CONFIG_OFF: the heater refused at any RH, and why that was correct

With the arms cleared the dashboard read "Blocked 0.0 %, Reasons:
CONFIG_OFF". That flag is not a fault: `O2P_HB_CONFIG_OFF` means
**`HEATER_MAX_DUTY` (0x0035) is zero** — one of the hard refusals
(heater_ctl.c:466), a ceiling that caps every loop, the consented RH
regulation included. The RH loop itself was fully armed the whole time:
consent 0x0048 = 0x9C07, setpoint 0x0033 = 85.00 %, tip setpoint at the
0x8000 sentinel — flag 15 (`TIP_DISARMED`), whose own comment reads
"the RH loop is the configured law".

The ceiling reads 0 because the fail-safe is allowed to fail in only one
direction: HEATER_MAX_DUTY **defaults to 0, lives in flash**, and an
upgrade never carries heat authority across — "a probe whose stored
HEATER_MAX_DUTY was nonzero now declines to heat until consent is
written" (regmap.h). Tonight's OTA plus the disarm/commit left it at 0,
so a probe in the pile would have sat unprotected at RH > 90 % while
the dashboard's old "consent updated" message claimed the loop was
authorized. **A consented loop with a zero ceiling is indistinguishable
from a commissioned one on every read except 0x0035/0x002E.**

Fix, both halves:

- **Tooling** (web-ble `317f992`): *Set RH* is now the commissioning
  triple — setpoint 0x0033 + ceiling 0x0035 + consent 0x0048, each
  readback-verified, ceiling field in the UI, default 12 % (the
  POWER-BUDGET.md value the 28-day pile math is built on; at 12 % duty
  the whole heater question is the budget, per that file). Interlock
  names 13–15 (BLIND, IDLE, TIP_DISARMED) added so the card cannot
  render an undefined reason again.
- **This probe**: `0x0035=1200` + commit, once the bus returns from the
  parallel session's flash (claims were refused mid-OTA; the write
  bounces until the node finishes its reboot).

Commissioning after ANY firmware flash is now a standing step, by
design: the fail-safe guarantees the ceiling is 0 after an upgrade, and
only the explicit triple (plus commit) restores pile protection.

## 2026-09-11 ~01:40 — commissioning landed; the SUPPLY block is real;
## a retraction; the node woke via LoRaWAN

**Commissioning complete in config.** After the parallel session's
22:01 OTA left the bench node hung, it recovered without a bench visit:
the keeper's chirpstack path sent SESSION_OPEN (fPort 13, opcode 0x01,
flags `CTRL_F_BLE_OTA`) against the node's invitation; BLE link
authenticated 01:08:41. That downlink is the standing remote-wake lever
— the node parses nothing, but the CTRL header is the one exception,
and `+BLE_OTA` opens the radio without a button press.

The triple, all readback-verified through the keeper (~01:35):
`0x0033=8500` (armed all along), `0x0035=1200` (this write,
readback 1200), `0x0048=0x9C07` (armed all along), commit
`0x003E=23233` (readback 0 — edge-register echo, by design).
`0x0049=8000` sentinel re-read: the RH loop is the configured law.
`HEATER_BLOCK=0x0200` — SUPPLY only; CONFIG_OFF, NO_CONSENT and
TIP_DISARMED are all clear. The config side of pile protection is done.

**The SUPPLY block is new data for §contamination.** `VA_MON`
2904 → 2852 mV over seconds, unloaded, at tip 48.2 °C; `VIN_MON`
10.65 V (no VIN fault); VREF 2494 mV — healthy, so ADS-converted
rail readings are trustworthy again (§3/§6 blindness does not apply).
Compare the soak era: VA 3.16 V *under ~94 % duty*. The 3V3A domain is
now further down unloaded and cool than it was loaded and hot. The
interlock is right to refuse the 86 mA (main.c: "a rail already out of
tolerance is not the place to put more load"); the RH loop will engage
the moment the rail recovers — nothing further to commission.

Also from this read: RH 97.7 % (chamber saturated post-soak),
`O2_COMP` 0xFFFF (the wet-basis guard, correct — never a number
instead), `FAULTS_EVER 0x8F41` (RUNAWAY/TEMP_OVER/DEW_SUSPECT/
ADC_RANGE seen historically tonight; live word only HEATER_DISABLED,
VA_LOW, +bit0), `SETTLE_RESTARTS=2` — VA sags restart settling
(main.c phase_rails), so the 900 s settle clock is the rail's, not ours.

**Retraction — the "wrong-base cross-wire" was never in the keeper.**
At 01:13 the keeper was dead (killed externally, see below); `curl -s`
swallowed the connection refusals and `-o` wrote nothing, so `cat
/tmp/v1.json` resurrected hours-old files from the disarm turn —
`{"base": 73, "regs": [8000, 0]}` is exactly the 0x0049:2 arm read.
The keeper's per-line address check (o2p_ble_keeper.py /read handler)
was right all along; my instrument was wrong. Lesson recorded: always
print the status code and never cat a file curl may not have written.
Defense in depth shipped anyway (web-ble d67c010): the client now
refuses a wrong-block reply by base mismatch before count.

**Keeper wars, fourth round.** The supervisor tree was killed three
more times tonight (last at 01:10, no exit line — external pkill
signature) and a duplicate instance spawned at 01:15 that could not
bind 8923 and ran its BLE loop bare — likely the dangling CTRL session
that refused every claim until its expiry. Standing rule for the two
sessions: don't pkill the keeper, ask; one bus owner at a time.

## 2026-09-11 morning — VA_MON: a false rail, cleaned off

**`va_mv` is not a rail measurement you can trust on this board.** From 01:07 it
fell 3282 → 2008 mV and latched `VA_LOW` for 7 h 54 min, muting oxygen entirely
(`VA_LOW` ∈ `O2P_FAULTS_INVALIDATE_O2`). The rail was fine. Fab air-gunned and
cleaned the board at 09:15 and it recovered **1338 → 3282 mV in a single frame**,
back to its exact pre-fault value.

Numbers for this file's purpose:

| quantity | during the fault | after cleaning |
|---|--:|--:|
| `va_mv` (ADS AIN2, ÷2, ext. ref) | 2008–2168 | 3280–3284 |
| `vin_mv` | 10485–10500 | 10642–10672 |
| `vref_mv` (ADS, **internal** 2.048 V ref) | 2490 ± 2 | 2492 ± 2 |
| `cell_ua` (ADS, same ext. ref as VA) | 100.5 → 103.65, smooth | 97–105 |
| `afe_mv` | 944–990 | 933–990 |
| `i2c_errs` / `ads_fail_count` | 0 / 0 | 0 / 0 |
| `lmp_readback` | 0x0CCD | 0x0CCD |

The arithmetic: a **~7.9 kΩ** leak from the 10k/10k divider midpoint
(`hw_caps_rev_a.h:95-96`, ÷2) to ground puts the node at 1004 mV instead of
1643 mV — 10k ∥ 7.9k = 4.40 k, 4.40/14.40 × 3282 = 1004. Cleanable without a bake,
so surface contamination, unlike the `/VREF_TRIM` leak this file already records.

**The rule this adds to the one at line 296.** That rule says `VA_MON` valid and
`i2c_errs` zero prove nothing about the cell. The converse now also holds:
**`VA_MON` invalid proves nothing about the rail.** VA_MON and the cell current
share the ADS *and* the external VREF_TRIM reference (`main.c:829` and
`main.c:1017`), while VREF_MON is converted against the ADS's internal 2.048 V
reference (`main.c:664`, `ads1119.h:50`) — so VREF_MON healthy plus a physical
cell current localizes any VA_MON excursion to the VA_MON *input node* alone.
U4A is a follower off a tap on 3V3A (`SCHEMATIC-REVIEW.md:304`,
`AFE-BRING-UP-POSTMORTEM.md:254`, `/VREF_TOP` metered 2.68 V at line 159), so it
cannot output 2.49 V from a 2.01 V rail: that inequality is the whole diagnosis and
it was available 8 h before the cleaning confirmed it.

Full write-up, including the double-mute (`phase_rails()` re-arms settling every
cycle, pinning `settle_s` at 900 while `settle_restarts` stays at 1 and hides it):
`docs/2026-09-11-va-mon-collapse.md`.

## 2026-09-11 evening — steam bath: VREF collapsed 18:48–19:37, came back *under* an 80 °C soak

Source: VictoriaMetrics `gas_*{probe="3"}` (2-min step unless noted), keeper
register reads. Probe in a steam bath from ~17:07 (die 25.6 → 78.8 °C,
17:05–17:14).

| time | `vref_mv` | context |
|---|--:|---|
| 14:30 | 2492 | in window (2489–2511) |
| 17:12 | 2460 | bath going in |
| 17:28–18:28 | 65535 in stretches | invalid; I2C errors climbing from 17:22 (FW 0x0011) |
| 18:28 | 2494 | after the 18:25 power-on reset (reset cause 12) |
| **18:48** | **606** | collapsed |
| 19:33–19:36 (1-min) | 428 → 440 → 538 | still collapsed |
| **19:37** (1-min) | **2496** | back in window, and stayed |

At recovery the stored tip loop (0x0049 = 80.00 °C, committed 19:04) held the
tip at 80.0 °C, chamber 80.0 °C at **6.5 %RH**, die 80.3 °C, cell side 78–79 °C,
duty 0–6 % (the surroundings were at the setpoint).

AFE consequence: `settle_restarts` 1 → 2 at 19:38, `settle_s` 848 (settled
~19:52); `FAULTS` gained `SETTLING` (with no reset — uptime continuous, reset
cause 20). `cell_ua` read **235.7 µA** while VREF was collapsed and **84.7 µA**
at 19:41, settling. Treat O₂ from 18:48 until the settle ends as invalid.

**Contrast with 2026-09-10 ~22:20** (the 80 °C soak above): there the reference
*fell* with tip temperature on a board that had been baked dry. Today it had
collapsed for an hour at moderate temperature on a steam-wet board and
*recovered* after ~30 min at 80 °C and single-digit RH. Reversible in both
directions again — still consistent with ionic/moisture contamination on
`/VREF_TRIM` rather than silicon. **Inference, not measured**: nothing isolates
the node's resistance directly.

Two readings that are **not** supply findings: `VIN_LOW` appeared alongside
`SETTLING` at 19:38, and `vin_mv` read 0/1132/2220/65535 through the evening.
On Rev A VIN_MON is not on the MCU ADC but **is** ADS1119-converted
(`hw_caps_rev_a.h:90-91`, R26/R27 130k/20k), i.e. against the same external
reference that was collapsed — blind while VREF is out of window, as the
2026-09-10 ~22:20 entry already says (65535 through 19:36). (A read-only
reviewer's "Rev A has no real VIN measurement" was half right and is corrected
here.) **But it is not blind now:** since VREF came back (19:38, 2496–2498 mV)
`vin_mv` reads a steady **0**, and it read 0 at 18:27 next to an in-window VREF
too. `main.c:853-874` publishes the scaled conversion as-is (a negative code
returns early, so 0 is a measured ~0 mV at the divider tap), and the probe is
running and heating, so the 12 V feed is present. **Inference:** the VIN_MON
input path (R26/R27 130k/20k tap) is faulted — an open R26 or a leak from the
tap to ground, the VA_MON failure shape of this morning on the other divider —
not the rail. Not metered; `VIN_LOW` will stay latched until it is.

**Correction, 21:12 — the tap-fault inference above does not survive.** VIN_MON
(`0x0012`) read **10710 mV** at 21:10, after the heater was disarmed (writes at
21:06:40/21:07:25), with the same reference. VictoriaMetrics `gas_vin_mv` at
10-min steps: 10650 (17:10) / 10717 (17:20) with the heater idle; 0 at 18:30
(dew law driving) and 0 from 19:40 through 21:00 (stored tip loop armed, duty
0–100 %, across the 20:45 and 21:00:35 power-on resets); 10710 at 21:10. So
the zero follows the heater being armed or driving, not a static open/leak —
mechanism unidentified (ADS mux/timing under heater PWM is one candidate, not
checked). Separately, Fab metered **VIN = 13.11 V at ~21:08** against the
published 10710 mV at duty 0: the published value is 18 % low (ratio 1.224) —
divider/scaling check in progress (farming-f7), not concluded here.

**Correction to the correction, 21:25 — the zero does not follow the heater
either.** The 21:12 claim came from 10-min VictoriaMetrics steps, which skipped
the counter-examples. At 1-min steps (`gas_vin_mv` vs `gas_heater_duty_pct`):

| time | `vin_mv` | duty % | note |
|---|--:|--:|---|
| 18:27 | 0 | 33 | first zero after the 18:25 power-on reset |
| 18:37 | 1740 | 100 | a near-zero-scale value, not the rail |
| 19:38–20:45 | 0 (7, 52 once each) | 0–2.6 | heater idle, stored loop armed |
| 20:48 | 0 | 100 | after the 20:45 power-on reset |
| **21:03** | **10560** | **100** | valid while driving (farming-f7: also 21:02:15/21:03:16, and 10552 at 21:05:54) |
| 21:08 | 10710 | 0 | six reads 21:08:25–21:08:49, VREF 2498, VA 3288 |

So the zero spans ~18:27–20:48 at every duty and recovered somewhere between
20:48 and 21:03 — a window containing the 21:00:35 power-on reset and the board
cooling after its 80 °C soak. **Mechanism unidentified.** A tap-to-ground leak
that dried out is consistent with the timing; nothing measured isolates it.

**The 18 % low reading is a separate, stable effect** (numbers: farming-f7).
Fab metered 13.11 V at ~21:08 (measurement point not yet stated); the published
10710 mV gives ratio 1.2241, i.e. a tap of 1428 mV against the design 1748 mV
(13.11 V × 20k/150k). Equivalent hardware: R26 ≈ 163.6 k instead of 130 k, or an
effective R27 ≈ 15.9 k (≈ 77 k tap-to-GND ∥ 20 k). ADC loading is excluded (ADS1119
input current ±5 nA ≈ 0.1 mV across the 18.3 k source). A reference running 18 %
high is excluded by VA_MON on the same external reference reading 3288 mV — true
3V3A would be ~4.0 V. The valid readings on 09-10/09-11 all sit at 10.49–10.79 V,
ratios 1.215–1.250 against 13.11 V: a stable gain error rather than a varying
leak, **if** the supply is constant — which is unverified. And the 18:04–18:26 bus
silence ended in a power-on reset (`gas_link_ok` 0 → 1 at 18:27, uptime
restarted ~18:25) — firmware 0x0013 ruled out by a read-only review; board
damage/power loss or a hand on the bench are the candidates, unresolved.

**Resolved, 2026-09-11 evening — the 18 % is the fitted VIN divider (Fab).**
Fab: the 13.11 V was metered **at the probe's input terminals**, and the board
carries a **10 k / 82 k** divider, not the Rev A netlist's R26/R27 130 k / 20 k.
Orientation inferred, not stated: 82 k top / 10 k bottom (×9.2) — the reverse
would put ~11.7 V on AIN3. Check: 13.11 V × 10/92 = 1.425 V tap × 7.5 (the
firmware's netlist scale) = **10.69 V predicted vs 10.71 V published**; ratio
9.2/7.5 = 1.2267 predicted vs 1.2241 measured (−0.2 %, inside 1 % part
tolerance). The "equivalent hardware" line above is superseded. Hardware
history: this bench board deviates from its netlist at R26/R27 (when and why
unrecorded).

Fix, per Fab ("this calibration constants belongs in the stm non-volatile
storage"): flash-backed config register `VIN_DIV_X1000` `0x004B`, FW 0x0014
(`firmware/FIRMWARE.md`), no layout bump, so a reflash keeps heater consents
and O₂ calibration. Candidate values were 9200 (nominal parts; 13.14 V from the
1428 mV tap) or 9181 (fit to the 21:08 meter pair; 13.11 V).

**Installed and written, 2026-09-11 21:47–21:48 (Fab: "flash it", "write
0x004B").** FW 0x0014 via keeper `/update`, install #7 → #8, running BUILD_ID
`CD8DD459` (dirty tree on d8dd459 — names the commit, not the binary; image md5
`9e8f2f25…`). Across the boot `CONFIG_CRC` stayed 47343, O₂ calibration
(0x0037/38, 0x0043–0x0045) and the committed heater-OFF record unchanged, so no
layout migration ran. Then `0x004B=9181`, COMMIT result 2 (OK), CRC 47343 →
24106; `VIN_MON_MV` 10717 → **13119 / 13110 mV** against the metered 13.11 V.
The commit has not been proven by a reset yet. The ~18:27–20:48 zero above is a
separate effect and still unexplained.

## 2026-09-11 late — coating, then hot air: the 3V3A-supplied AFE went silent

**Hardware history (Fab, stated afterwards):** coating applied to the board at
about the time VREF collapsed; roughly half an hour later, a hot air gun. Times
below are telemetry, not his.

VictoriaMetrics `gas_*{probe="3"}`, 1-min steps, change points:

| time | uptime / reset cause | FAULTS | `vref_mv` | `va_mv` | `afe_mv` | tip °C |
|---|---|---|--:|--:|--:|--:|
| 22:03 | 953 s / 20 | 0x8041 | 2496 | 3076 | 980 | 22.9 |
| 22:24 | 2178 s / 20 | 0x8805 | **78** | **4432** | 43 | 28.3 |
| 22:26 | 2299 s / 20 | 0x8805 | 76 | **5054** | 38 | 40.6 |
| 22:30 | 2540 s / 20 | 0x8805 | 70 | 5034 | 35 | 25.8 |
| **22:37** | **32 s / 12** | **0x8047** | 65535 | **12** | 65535 | 23.5 |
| 22:43 | 394 s / 12 | 0x8247 | 65535 | 12 | 65535 | 63.1 (hot air) |
| 23:03–23:17 | — | 0x8247 | 65535 | 8–12 | 65535 | 81.6–81.8, die 82.3–82.9 |

- **22:03 → 22:24 (coating):** VREF_MON — converted against the ADS1119's
  INTERNAL reference, so a real measurement — fell 2496 → 70–94 mV, and
  I2C_FAIL_ADS began appearing while conversions still landed. `va_mv` in that
  window is the MCU's PA7 read (the ADS path does not publish without a
  measured VREF): 4432–5054 mV, i.e. the `/VA_MON` tap at 2.2–2.5 V. A driven
  3V3A or a corrupt reading; **unverified**. The 22:24–22:26 tip rise with the
  heater off is unattributed.
- **22:36:30, power-on/brownout reset** (cause 12). The farmgw keeper log shows
  no write, update, nodeflash, diag or restart between 22:20 and 22:39, so it was
  not a tool.
- **Since that reset the two 3V3A-supplied parts NACK and the 3V3D-only parts
  answer.** Rev A netlist: U7 LMP91000 VDD = `/3V3A` (pad 6); U8 ADS1119 AVDD =
  `/3V3A` (pad 10), DVDD = `/3V3D` (pad 11); U10 TMP117, U12 SHT45 and U6 STM32 on
  `/3V3D`; all on one `/I2C_SCL`/`/I2C_SDA`. Diag mailbox 23:13: `READ_ADS_STATUS`,
  `READ_ADS_CONFIG`, `READ_LMP_REG` all **ERR_NACK**; tip and chamber still read.
  PA7 puts the 3V3A ÷ 2 tap at 8–12 mV. **Inference:** 3V3A is down — one fault
  explains both NACKs; two parts failing independently in the same minute does
  not. Whether an ADS1119 NACKs with DVDD present and AVDD absent is not checked
  against SBAS925. **Not metered.**
- The hot air (from ~22:41) held tip/die at ~82–83 °C; the probe went bus-silent
  again from ~23:18.

FW 0x0015 (`d10091c`, diag opcode 9, internal-reference override —
`firmware/FIRMWARE.md`) was installed 23:13:11 and the override set 23:13:40
(volatile). It cannot show anything while the ADS NACKs.

**Open:** coating type and cure schedule (a wet solvent film bridging the
high-impedance VREF_TRIM and VA_MON nodes would fit the 22:24 readings — not
established); meter 3V3A and U8 pad 11 with the board cool; if 3V3A is absent,
the regulator and a short/film on that rail before U7/U8.

## 2026-09-12 09:10–09:24 — nothing is dead; the 2.5 V shunt reference is the fault

Fab metered 3V3A: **fine**. That refutes the 2026-09-11 inference above
("3V3A is down — one fault explains both NACKs"). Keep the inference on
record; it was the best reading of a NACKing bus, and it was wrong.

Every I2C device on the board answers, over the keeper's diag mailbox
(probe uptime 779 s, i.e. it rebooted ~09:00; FW 0x0015 `CD10091C`):

| diag op | device / register | reply |
|---|---|---|
| `1:0x00` | LMP91000 STATUS | OK, `0x01` — ready |
| `1:0x10` | LMP91000 TIACN | OK, `0x0C` |
| `1:0x11` | LMP91000 REFCN | OK, `0xCD` |
| `1:0x12` | LMP91000 MODECN | OK, `0x03` — 3-lead amperometric |
| `3` | ADS1119 STATUS | OK, `0x70` |
| `4` | ADS1119 CONFIG | OK, `0x65` |
| `5:0x0000` | TMP117 #0 TEMP | OK, `0x0B30` = 22.38 °C |
| `5:0x0100` | TMP117 #1 TEMP | OK, `0x0C08` = 24.06 °C |
| `7` | SHT45 sample | OK, `0x6234` / `0x5325` |
| `6` | SHT45 serial | ERR_NACK, twice — the only NACK left, and the part samples fine, so it is that command, not the device |

The LMP91000 registers are the **configured** values, not reset defaults, so
it did not merely survive — it kept its state.

**The fault is `/VREF_TRIM`: 70 mV where it should be 2.500 V.** VREF_MON is
converted on AIN1 against the ADS1119's *internal* 2.048 V reference, so that
70 mV is a real measurement, not a reference-scaled artefact. Rev A feeds it
`+5V` → R32 10R → `/+5V_ANALOG` → R41 1k → `/VREF_SHUNT` (U15 shunt reference,
C9 1n) → R31 47R → `/VREF_TRIM` → U7.11, U8.7 (REFP), C10 4.7 µF, R34 47k.

One collapsed node explains every symptom at once:

- **ADS1119**: CONFIG `0x65` has VREF = 1 (external), so every AIN0/AIN2/AIN3
  channel is converted against 70 mV and clips. FAULTS bit 11 ADC_RANGE is
  exactly that.
- **LMP91000**: REFCN `0xCD` has REF_SOURCE = 1 (external) and INT_Z = 67 %, so
  its internal zero is 0.67 × 70 mV ≈ 47 mV. AFE_VOUT measures **34 mV**. The
  cell is biased against a 47 mV zero — O2_RAW cannot mean anything.

**The silicon is proven good by forcing the internal reference.** Diag `9:1`
(volatile, cleared by the ~09:00 reset) was re-sent 09:16:

| register | ext ref (70 mV) | internal ref 2.048 V |
|---|--:|--:|
| `VREF_MV` 0x0010 | 70 | 70 |
| `VA_MV` 0x0011 | 5188 (garbage) | **0** |
| `VIN_MV` 0x0012 | 65535 invalid | **13128** |
| `AFE_VOUT_MV` 0x0013 | 35 | 34 |

VIN 13.128 V is a correct reading through the fitted 82k/10k divider. **The
ADS1119 converts correctly the moment it is given a valid reference.**

**Second, independent fault: `/VA_MON` is at ground.** R24 47k from 3V3A,
R25 47k to GND, C33 100n — with 3V3A good the tap must be ~1.64 V. It reads
0 mV on the ADS (AIN2, internal ref) and 8–18 mV on the MCU's PA7. Both agree,
so it is the node, not either ADC. A 47k-fed node shorted to ground draws
~70 µA, which is why 3V3A meters fine. FAULTS bit 6 VA_LOW is real and is
**not** a rail problem. This net already had one surface leak, cleaned 09-11
09:15 (`o2-probe-afe-postmortem`).

So: two high-impedance analog nodes pulled to ground, both in the region that
got coating and then hot air, and no semiconductor implicated yet.

FAULTS 0x8844 = I2C_FAIL_ADS · VA_LOW · ADC_RANGE · HEATER_DISABLED.
`ADS_FAIL_COUNT` (0x0024) held at 141 and `I2C_ERRORS` (0x001E) moved 1132 →
1133 over four minutes — the bus is essentially clean now; those counters are
the history of the 22:37–23:18 outage.

### Measurements that would close this (powered, board cool)

1. **TP4 (`/VREF_TRIM`) to GND** — expect 2.500 V, we predict ~0.07 V.
2. **`/+5V_ANALOG`** (C7 or C27 pad) — expect ~4.9 V. This splits the two
   cases: 4.9 V present means U15 or C10 is shorted (~4.9 mA through R41
   would leave the node at exactly the 70 mV seen); low means the feed
   through R32 is gone, and 3V3A being fine argues against that, since U3
   makes 3V3A from `/+5V_ANALOG`.
3. **R24/R25 junction (or C33)** — expect 1.64 V, we predict ~0.
4. **Unpowered, after C10 discharges:** `/VREF_TRIM`–GND and `/VA_MON`–GND
   ohms. VA_MON–GND should read ~23.5 k (R25 ∥ R24+rail). Single-digit ohms on
   either is a short; a few hundred k to a few M is a leakage film.

Suspects, in order: coating/flux residue bridging the two nodes (fits both,
and fits the timing); C10 4.7 µF shorted; U15 shunt reference failed short.
Note that a residue film explaining `/VA_MON` at 0 mV must be **well under
47 k**, which is a lot more than a damp film — check for a solder bridge or
displaced part from the hot air before assuming contamination.

### 09:40 correction — TP4 = 2484 mV. The reference is GOOD; three ADS inputs are not

Fab metered TP4 (`/VREF_TRIM`): **2484 mV**, right on the 2500 mV trim target.
That refutes the section above, which is left standing as written. Two errors
in it, one of consequence:

1. **Wrong board.** I read `gen_sch.py`, which is Rev B. The bench board is
   Rev A (`fab/o2-probe-rev-a-source/source/o2-probe.kicad_pro`), and its
   reference is not a shunt at all: `3V3A` → R20 1.91k → `/VREF_TOP` → RV1 2k
   10-turn → `/VREF_WIPER` → U4 OPA2333 buffer → `/VREF_BUF` → R31 47R →
   `/VREF_TRIM`. There is no U15, no R41, and `/+5V_ANALOG` is not in the path.
   Ignore measurement 2 of the previous section.
2. **`VREF_MON` is a measurement of the SENSE TAP, not of the reference.**
   `/VREF_TRIM` → R34 47k → `/VREF_MON_RAW` → R35 47k → GND, and R36 1k →
   `/ADC_VREF_MON` (C29 100n) → U8 pin 8. `finish_vref()` (main.c:700) converts
   that pin against the internal 2.048 V reference and doubles it
   (`O2P_HW_DIV_VREF_NUM/DEN` = 47000/94000). Reported 70 mV therefore means
   **the pin is at 35 mV**, where half of 2484 = 1242 mV is due.

So the reference is fine and the firmware cannot see it. Everything downstream
follows from that one blind spot, without any reference fault:

- 70 mV is outside the trim band, so `finish_vref` raises ADC_RANGE and
  **refuses to update `g_cyc.vref_mv`**, leaving `vref_measured` false. Every
  ADS channel that needs a measured reference is then suppressed — that is why
  `VIN_MV` published 0xFFFF, not because VIN was unreadable.
- With `vref_measured` false the ADS VA path returns early, so `VA_MV` under
  the external reference is the **MCU's PA7** value, not the ADS's.

Rev A ADS1119 channel map (`hw_caps_rev_a.h:10-13`) and what each reads now:

| pin | AIN | net | measured | due |
|---|---|---|--:|--:|
| 4 | AIN3 | `/ADC_VIN_MON` | **13128 mV** reconstructed — sane | — |
| 5 | AIN2 | `/ADC_VA_MON` | **0 mV** | 1650 |
| 7 | — | `/VREF_TRIM` (REFP) | 2484 at TP4 | 2500 |
| 8 | AIN1 | `/ADC_VREF_MON` | **35 mV** | 1242 |
| 9 | AIN0 | `/ADC_AFE_VOUT` | **34 mV** | ~1660 (0.67 × 2484) |

**Three of the four analog inputs are pinned near ground; the fourth is
correct.** AIN3 reading 13.128 V proves the converter, the internal reference
and the I2C path. Pins 5, 8 and 9 sit on one side of the WQFN, around the GND
at pin 6.

**The two ADCs contradict each other on `/VA_MON`, across 1 kΩ:** PA7 reads the
node at **2594 mV** (`va_mv` 5188 = tap × 2, `O2P_HW_DIV_VA_NUM/DEN`), while the
ADS reads `/ADC_VA_MON` — the same node through R37 1k — at **0 mV**. Both
cannot be true, and neither is the 1650 mV a 10k/10k divider off a good 3V3A
owes. (PA7 read this node at 6–9 mV during last night's outage, so it has
moved.) One of the two front ends is lying and a meter settles it in one touch.

Note the 22:24 collapse of VREF_MON preceded the hot air (22:41) and followed
the coating — so whatever pinned the sense tap arrived with the coating, and
the AFE_VOUT and VA inputs joined later.

#### Probe list, powered

| # | point | expect | meaning if it differs |
|---|---|--:|---|
| 1 | R34/R35 junction (= R36 pad 1), `/VREF_MON_RAW` | **1242 mV** | 0 here ⇒ R34 open or the tap is shorted; 1242 here ⇒ the fault is at the ADS pin |
| 2 | U8 pin 8 or C29, `/ADC_VREF_MON` | 1242 mV | 35 mV with #1 at 1242 ⇒ C29 shorted or AIN1 dead |
| 3 | R24/R25 junction (= R37 pad 1, U6 pin 18), `/VA_MON` | **1650 mV** | settles PA7 (2594) vs ADS (0) |
| 4 | U8 pin 7, REFP | 2484 mV | proves the PIN, not just TP4 |
| 5 | U7 pin 8 (= R33 pad 1), `/AFE_VOUT` | ~1660 mV | 0 ⇒ the LMP output is genuinely down; 1660 ⇒ AIN0 is the fault |

If #1, #3 and #5 all read correctly while the ADS reports 35/0/34 mV, the board
is fine and the ADS1119's input mux is damaged on three of four channels — and
the part gets replaced rather than debugged further.

### 10:15 — `/VREF_TRIM` is OPEN. TP4 2484 mV, R34.1 34 mV, same net

Fab's meter, bottom side, powered:

| point | net | reads | due |
|---|---|--:|--:|
| TP4 (F.Cu 119.0, 123.5) | `/VREF_TRIM` | **2484** | 2500 |
| R34.1 (B.Cu 107.625, 120.8) | `/VREF_TRIM` | **34** | 2484 |
| R34.2 (B.Cu 105.975, 120.8) | `/VREF_MON_RAW` | 90 | 1242 |

TP4 and R34.1 are the **same net**. 2.45 V across what should be continuous
copper is an open circuit — not a component, not contamination, not the ADS.

**Retracted:** the 09:55 reading of this — "49 µA flows into the ADS stub,
implying an ~840 Ω shunt at AIN1, so C29 is shorted or U8's input mux is
damaged" — assumed 2484 mV at R34.1. It is 34 mV. Both ends of R34 are within
a meter's noise of ground, so the sense divider is simply **unpowered** and
nothing about AIN1 is implicated. Do not ohm C29 or replace U8 on that basis.
The 0 / 90 / 34 mV spread across these three points is bench noise at the
bottom of the range, not a signal.

Net topology from the Rev A PCB (4-layer; `/VREF_TRIM` = C10.1, R22.1, R31.2,
R34.1, TP4.1, U7.11, U8.7). The driven end is **R31.2** (OPA2333 buffer
through the 47R). Two arms leave it:

- **R34 arm (dead):** R34.1 → B.Cu → **via (107.15, 121.4)** → In1.Cu →
  **via (109.7, 123.45)** → F.Cu run y=123.45, x=109.7→113.15 →
  **via (113.25, 123.35)** → B.Cu → R31.2.
- **TP4 arm (live):** R31.2 ← B.Cu ← via (113.25, 123.35) … and TP4 →
  **via (118.5, 124.5)** → In1.Cu → (116.35, 126.65) → (116.35, 127.55) →
  **via (114.6, 129.3)** → F.Cu → **U8.7**. C10.1 hangs off the same
  (118.5, 124.5) via.

So the break lies between R34.1 and the junction at (113.25, 123.35): three
vias and one 3.45 mm top-side trace. Three buried vias on a board that took a
hot-air gun for ~30 minutes is the obvious suspect; an In1.Cu break is not
visible.

**U8.7 (the ADS's REFP) reaches the live TP4 arm through the (114.6, 129.3)
via, so it most likely still HAS the reference.** If that holds, the ADS was
converting against a good 2.484 V the whole time and the firmware refused to
publish only because the *sense tap* is orphaned — `finish_vref` sees 70 mV,
raises ADC_RANGE and leaves `vref_measured` false. The probe would then be one
wire away from working.

#### Next, powered

1. **Bisect: the F.Cu trace at ~(111.5, 123.45).** 2484 ⇒ break is between
   there and R34 (via 107.15,121.4 / via 109.7,123.45 / the In1 run). ~0 ⇒
   break is at via (113.25, 123.35) or the B.Cu run to R31.2.
2. **U8 pin 7** — expect 2484. Confirms the ADS kept its reference.
3. **U7 pin 11** — expect 2484. If ~0, the LMP lost its reference, its internal
   zero collapses to ~0, and **AFE_VOUT at 34 mV is genuine**, explained by the
   same open rather than by a second fault.
4. **R24/R25 junction (106.83–108.38, y=130.2), `/VA_MON`** — still expect
   1650; PA7 says 2594 and the ADS says 0 across R37 1k, and that is untouched
   by any of this.

#### Repair, once the break is located

A fine wire from **TP4 or C10.1 (118.3, 124.775)** to **R34.1 (107.625,
120.8)** restores the sense tap without disturbing the live arm. That alone
would clear ADC_RANGE and let every externally-referenced channel publish
again.

### 10:35 — RETRACTION of the open-net finding. The ADS1119's inputs are damaged

**R34.1 = 2484 mV**, re-measured. The 10:15 section above is wrong and is
retracted in full: `/VREF_TRIM` is NOT open, the via chain is fine, and no
jumper is needed. It was written on a reported R34.1 = 34 mV; that reading did
not stand. (Two retractions in one morning, both from building a topology
story on a single low reading. A sub-100 mV reading on a high-impedance node
is not evidence until the node's expected value has been confirmed at its
source pad.)

With R34.1 = 2484 mV and R37.1/R37.2 in hand, all four channels resolve
quantitatively. Meter, powered, bottom side:

| channel | node (before the 1k) | ADS pin side (after) | current | direction |
|---|--:|--:|--:|---|
| AIN1 `/ADC_VREF_MON` (U8.8) | R34.2 / R36.1 = **90 mV** | ≈41 mV (fw reports 35) | **49 µA IN** | sinks to GND, ≈840 Ω |
| AIN2 `/ADC_VA_MON` (U8.5) | R37.1 = **2.590 V** | R37.2 = **2.788 V** | **198 µA OUT** | sources from AVDD, ≈2.6 kΩ |
| AIN3 `/ADC_VIN_MON` (U8.4) | — | — | — | **correct**, 13.128 V |

Working:

- AIN1: I(R34) = (2484−90)/47k = 50.9 µA; I(R35) = 90/47k = 1.9 µA; the
  difference, 49 µA, can only go into R36 → 49 mV across the 1 k → pin at
  41 mV. `finish_vref` reports 70 mV = pin × 2 = 35 mV. Agreement within the
  meter's resolution at this level.
- AIN2: the pin is 198 mV ABOVE the node it is fed from, so it is a source.
  Injecting 198 µA into the divider's Thévenin (1.65 V, 5 kΩ) predicts 2.64 V
  at `/VA_MON`; measured 2.590 V. This also disposes of the PA7-vs-ADS
  contradiction: **PA7 was right all along** (2594 mV), the node really is
  pulled up, and R24/R25 are good. The ADS's own 0 mV on AIN2 is an overrange
  artefact — 2.788 V exceeds the 2.048 V internal reference forced by
  `diag 9:1` at 09:16.

**Two adjacent inputs leaking in opposite directions — one clamped toward
AVDD, one toward GND — cannot be an external short, contamination or a
coating film.** Those give one polarity. This is damaged input structure
inside the ADS1119.

Everything else is exonerated by these same numbers: the 2.5 V reference and
its buffer, `/VREF_TRIM` end to end, R24, R25, R34, R35, R36, R37, and the
whole via chain. **U8 is replaced; nothing else is.**

Open: AIN0 `/ADC_AFE_VOUT` (U8.9) not yet metered — R33.1 (106.83, 114.0) vs
R33.2 (105.18, 114.0) makes it three of four and separates a genuinely dead
LMP output from one being dragged by the ADS. And what damaged three inputs
while sparing AIN3 is unexplained; all four are fed through equal 1 k series
resistors.

### 10:50 — discriminator run: `/VREF_MON_RAW` = 90 mV. AIN1 is damaged, confirmed

The 10:35 section's AIN1 half was briefly in doubt: a 34 mV reading at R36.1
would have meant the node and the ADS pin sat at the same voltage, hence no
current across R36 and an innocent AIN1 with a ~680 Ω leak on the board node
instead. The two hypotheses predicted different node voltages — 90 mV if the
ADS sinks, 35 mV if the board leaks — so one careful re-probe settles it.

**Measured 90 mV at R34.2, R35.1 and R36.1 alike.** The 34 mV was a bad
contact. The board-leak hypothesis is refuted; **AIN1 sinks.**

Solving exactly, with R34.1 = 2484 mV and the firmware's pin estimate of
35 mV (VREF_MON 70 / 2) as the constraint:

    (2484 - V)/47k = V/47k + (V - 35)/1k   ->   V = 84.3 mV

against 90 mV measured — a 6 mV agreement on a node whose expected value is
1242 mV. The implied pin shunt is **35 mV / 49.3 µA ≈ 710 Ω**.

So both diagnoses in the 10:35 section stand, each independently derived and
each cross-checked against a measurement that was not used to build it:

| pin | channel | leak | direction | cross-check |
|---|---|--:|---|---|
| U8.8 | AIN1 | ≈710 Ω to GND, 49 µA in | **down** | node predicted 84.3 mV, measured 90 |
| U8.5 | AIN2 | ≈2.6 kΩ to AVDD, 198 µA out | **up** | `/VA_MON` predicted 2.64 V, measured 2.59 |
| U8.4 | AIN3 | none | — | VIN 13.128 V, correct |

Opposite polarities on adjacent pins, both quantitatively consistent with an
internal clamp to the respective supply rail. **Replace U8.** The reference,
`/VREF_TRIM`, R24, R25, R34, R35, R36, R37 and the via chain are all exonerated
by the same two calculations.

Still open: AIN0 `/ADC_AFE_VOUT` (R33.1 106.83,114.0 vs R33.2 105.18,114.0),
and why AIN3 survived when all four inputs sit behind identical 1 kΩ series
resistors.

### 11:05 — HOLD: the pad readings were misattributed by one part. Sections above are unproven

Fab, at the bench: *"during all my pad measurements i measured C29 instead of
R36, R36 instead of R35, R35 instead of R34."* Every reported designator in
the 09:40–10:50 sections is one position to the LEFT of the part actually
probed. R34, R35, R36 and C29 sit in a 3 mm-pitch row at y = 120.8 on B.Cu,
which is how the miscount happened.

His own ohmmeter proves it: he measured "R35 pad-to-pad" and got **exactly
1 k**. R35 is 47k 0.1%; **R36 is the 1 k part**. So the probe was on R36, and
R36 reads its design value.

**Therefore the following are withdrawn pending re-measurement, and must not
be acted on:**

- 10:35 / 10:50 (`e3e256d`, `5d967a0`): "AIN1 sinks 49 µA through ≈710 Ω",
  "AIN2 sources 198 µA through ≈2.6 kΩ", "replace U8". Both rest on
  designator-labelled pad voltages. **Do not order or fit a new ADS1119 on
  this basis.**
- 10:15 (`935ca72`) was already retracted for an unrelated reason and stays
  retracted.
- 09:40 (`90a7cf2`): the channel map and the `finish_vref` mechanism are read
  from source and the netlist, not from pads, and stand. Its pad-derived
  numbers do not.

**What survives, because it does not depend on a designator:**

- **TP4 = 2484 mV.** A named testpoint, unambiguous.
- **`/ADC_VREF_MON` = 34 mV.** Reported as "R36.1", so actually C29.1 — which
  is on `/ADC_VREF_MON`, the ADS's AIN1 pin. The firmware independently puts
  that pin at 35 mV (VREF_MON 70 / 2). Two instruments, one number: **the ADS
  converts its own AIN1 pin correctly, and the pin really is at ~34 mV.** That
  is worth more than anything derived this morning.
- Every register reading taken over the wire.

**Lesson, and the fix.** Three wrong conclusions today, each built by fitting a
network model to one or two designator-labelled readings. A 3 mm-pitch row of
four two-pad parts cannot be indexed by counting. The row is self-locating if
read as a sequence, because it contains landmarks:

| x (B.Cu, y=120.8 unless noted) | pad | net |
|--:|---|---|
| 103.52 (y=120.0) | C31.2 | GND |
| 104.48 (y=120.0) | C31.1 | `/ADC_VIN_MON` |
| 105.98 | R34.2 | `/VREF_MON_RAW` |
| 107.63 | R34.1 | `/VREF_TRIM` — **the only 2484 mV pad in the row** |
| 108.98 | R35.2 | **GND** |
| 110.63 | R35.1 | `/VREF_MON_RAW` |
| 111.98 | R36.2 | `/ADC_VREF_MON` |
| 113.63 | R36.1 | `/VREF_MON_RAW` |
| 115.32 | C29.2 | **GND** |
| 116.28 | C29.1 | `/ADC_VREF_MON` |
| 117.80 (y=120.02) | C30.1 | `/ADC_VA_MON` |
| 117.80 (y=120.98) | C30.2 | GND |

Two GND pads and one 2484 mV pad inside the group fix the alignment from the
readings themselves. `/VREF_MON_RAW` appears at three pads and
`/ADC_VREF_MON` at two, so each net is cross-checked against itself, and the
diagnosis reduces to one question: is there a voltage difference across R36?
Equal ⇒ the ADS input is innocent and the leak is on the board node. Lower on
the `/ADC_VREF_MON` side ⇒ current into the pin ⇒ AIN1 damaged.

C30.1 gives the AIN2 pin in the same row, so the VA channel can be re-tested
without R37, which is in a different row and was not covered by Fab's stated
offset.

Also unexplained and now urgent: `/VA_MON` was 2.590 V at ~10:20 and 35 mV at
~10:55. 35 mV is not reachable through R37 from a 10k/10k divider on a live
3V3A, so either R24 is open or **3V3A has gone**. If 3V3A dropped, TP4 = 2484
is stale too, since the reference is derived from it. Meter 3V3A and TP4 again
before anything else.

### 11:25 — 3V3A IS DOWN. It is intermittent, and everything this morning was downstream of it

The self-locating sweep worked. Fab read the row left-to-right **as seen from
the bottom side**, which is decreasing x in board coordinates, so the sequence
arrived reversed — and the landmarks caught it: his zeros fell at positions 2
and 6, exactly the reversed pattern. Decoded:

| # | pad | net | mV |
|---|---|---|--:|
| 1 | C29.1 | `/ADC_VREF_MON` | 425 |
| 2 | C29.2 | GND | 0 |
| 3 | R36.1 | `/VREF_MON_RAW` | 416 |
| 4 | R36.2 | `/ADC_VREF_MON` | 425 |
| 5 | R35.1 | `/VREF_MON_RAW` | 416 |
| 6 | R35.2 | GND | 0 |
| 7 | R34.1 | `/VREF_TRIM` | **500** |
| 8 | R34.2 | `/VREF_MON_RAW` | 416 |

Both `/ADC_VREF_MON` pads agree at 425, all three `/VREF_MON_RAW` pads agree
at 416, both grounds are 0, and TP4 — a different point on `/VREF_TRIM`,
metered separately — also reads 500. Every net is internally consistent and
cross-checked. **This is the first pad measurement today that can be trusted,
and the technique is why: read a row as a SEQUENCE with known landmarks in it,
never by counting to a designator.**

C30.1 (`/ADC_VA_MON`) = 36 mV.

Over the wire at the same moment (probe uptime 328 s):

    diag 3      ADS1119 STATUS  -> ERR_NACK
    diag 1:0x00 LMP91000 STATUS -> ERR_NACK
    diag 5      TMP117          -> ERR_TIMEOUT
    VA_MV 48    VREF/VIN/AFE_VOUT all invalid

**`3V3A` is at ~48 mV.** PA7 puts the 10k/10k tap at 24 mV. Both 3V3A-powered
parts NACK. `/VREF_TRIM` collapsed to 500 mV because U4, the OPA2333 that
buffers the reference, is itself powered from 3V3A (U4.8).

At 09:10 those same two parts ANSWERED and AIN3 returned a correct 13.128 V,
and TP4 read 2484 mV. **So 3V3A is intermittent, not dead.** That is also what
moved `/VA_MON` from 2.590 V to 35 mV between 10:20 and 10:55: the rail went
away underneath it. It is the same signature as last night's 22:37 event,
where the 3V3A parts NACKed and the 3V3D parts answered.

**Every pad-level conclusion this morning was measuring a symptom of this.**
The AIN1/AIN2 leak models are not merely unproven, they were fitted to a
network whose supply was coming and going during the measurements.

Rev A analog rail: `+5V` → R32 10R → `/+5V_ANALOG` (C7 10u, C27 100n) → U3
TPS7A2033PDBVR (pin 1 IN, pin 3 IN/EN, pin 5 OUT) → `/3V3A` (C8 1u, C16, C18,
C25 100n) → U4.8, U7.6, U8.10, R20, R24. All on F.Cu around y = 83–88 except
the decoupling.

#### Next, powered, top side

| point | x, y | expect |
|---|---|--:|
| U3.5 `3V3A` | 114.14, 85.05 | 3.3 V — predict ~0.05 |
| U3.1 / U3.3 `/+5V_ANALOG` | 111.86, 85.05 / 86.95 | ~4.9 V |
| across R32 (`+5V` 110.00, 83.59 → `/+5V_ANALOG` 110.00, 85.41) | | the analog rail's whole current, 1 mV = 100 µA |

- +5V_ANALOG good, 3V3A ~0, R32 drop < 10 mV ⇒ nothing is drawing; U3 has
  stopped conducting. A cracked joint on a SOT-23-5 after coating and 30 min
  of hot air is the obvious intermittent.
- Large R32 drop ⇒ 3V3A is shorted and U3 is in current limit; then ohm 3V3A
  to GND unpowered and work through C8, C16, C18, C25, U7, U8.
- +5V_ANALOG also low ⇒ upstream, R32 or the +5 V buck.

#### Bench-measurement rule adopted today

Three wrong conclusions came from single designator-labelled pad readings on a
3 mm-pitch row. From now on, for any dense row: give the pads as a **sequence
with landmarks** (grounds, and one pad at a known distinctive voltage), have
every net appear at **two or more pads**, and state that a bottom-side view
mirrors left-to-right against board coordinates. Fit no network model to a
reading until the sequence has decoded itself.

### 11:55 — external 3V3A restores the AFE. Fault 2 isolated: ~50 µA sinking into the AIN1 stub

Fab injected an external 3.3 V onto `/3V3A`, drawing no visible current (the
honest load is only ~1–1.5 mA, and note a shutdown TPS7A20 would have pulled
22 mA through its internal 150 Ω OUT pulldown — so the LDO is not simply in
shutdown, or the injection point is isolated from U3.5).

**Both AFE parts came straight back:** ADS1119 STATUS 0x70 / CONFIG 0x65,
LMP91000 STATUS 0x01 / REFCN 0xCD. So U7 and U8 survive, and **fault 1 is the
3V3A rail alone.**

With the rail held steady by the bench supply, fault 2 stands still and the
landmarked sweep resolves it. Sequence as read (bottom side, so reversed;
zeros at 2 and 6 decoded it):

| # | pad | net | mV | due |
|---|---|---|--:|--:|
| 1 | C29.1 | `/ADC_VREF_MON` | 36 | 1250 |
| 2 | C29.2 | GND | 0 | 0 |
| 3 | R36.1 | `/VREF_MON_RAW` | 86 | 1250 |
| 4 | R36.2 | `/ADC_VREF_MON` | 36 | 1250 |
| 5 | R35.1 | `/VREF_MON_RAW` | 86 | 1250 |
| 6 | R35.2 | GND | 0 | 0 |
| 7 | R34.1 | `/VREF_TRIM` | **2500** | 2500 |
| 8 | R34.2 | `/VREF_MON_RAW` | 86 | 1250 |

Two pads agree on `/ADC_VREF_MON`, three on `/VREF_MON_RAW`, both grounds are
0, and the reference is exactly on its trim target. **The node currents close
to 0.4 µA:**

    in  through R34: (2500 - 86)/47k = 51.4 µA
    out through R35:  86/47k         =  1.8 µA
    out through R36: (86 - 36)/1k    = 50.0 µA

So R34, R35 and R36 are all intact at their design values, and **~50 µA sinks
into the `/ADC_VREF_MON` stub, which sits at 36 mV — a ≈720 Ω path to ground.**
The meter reads that pin at 36 mV and the ADS reports 35 mV, so the converter
reads its own pin correctly: the pin really is dragged down. Only **C29 (100n)
and U8 pin 8** live on that stub.

This reproduces the 09:55 conclusion, but this time on a self-validating
measurement (two- and three-pad agreement, ground landmarks, an exact current
balance, and the reference at nominal) taken on a stable rail. The earlier
version happened to be right and was not proven; the difference is the method,
not the luck.

**Reading the state with the internal reference forced (`diag 9:1`, re-set
after the reboot): VREF_MON 70, VIN 13138 (correct), AFE_VOUT 34, VA 0.**
Identical to the 09:10 good state, so fault 2 is stable and rail-independent.

#### The non-destructive discriminator: sweep the AFE_VOUT row

`/AFE_VOUT` should idle at 0.67 × 2500 ≈ 1675 mV (REFCN INT_Z 67 %, reference
healthy), and AIN0 reads 34 mV — the same shape as AIN1. Four pads, B.Cu,
y = 114.0, self-locating on one GND with `/ADC_AFE_VOUT` twice:

| x | pad | net | healthy |
|--:|---|---|--:|
| 105.17 | R33.2 | `/ADC_AFE_VOUT` | 1675 |
| 106.83 | R33.1 | `/AFE_VOUT` | 1675 |
| 108.52 | C28.2 | GND | 0 |
| 109.48 | C28.1 | `/ADC_AFE_VOUT` | 1675 |

- `/AFE_VOUT` ≈ 1675 with `/ADC_AFE_VOUT` ≈ 34 ⇒ a second stub sinking through
  its own 1 k. Two leaking stubs would need C28 **and** C29 both soft-shorted
  near 700 Ω; one chip with two damaged inputs is far likelier ⇒ **replace U8.**
- Both ≈ 34 ⇒ the LMP's output is genuinely down, AIN0 is innocent, and the
  LMP becomes a separate question.

Fallback, destructive but definitive: lift one end of C29 (116.28 / 115.32,
y = 120.8) and re-read VREF_MON over the wire. ~2500 ⇒ C29. Still 70 ⇒ the ADS.
**Do not ohm across C29 in place** — that measures the net, not the part; the
same trap cost a day on 2026-09-10 when C10 was removed and the leak persisted.

#### Open: the rail may not be 3.3 V

Before the internal-reference override, PA7 published `VA_MV` 5224, i.e. a
divider tap of 2612 mV. Through the ÷2 that R24/R25 are supposed to be, that
implies **3V3A ≈ 5.2 V**. Either the bench supply is set above 3.3 V, or
R24/R25 are not ÷2 as fitted and the firmware's scale factor is wrong — and
fitted-vs-designed divergence has precedent here, the VIN divider being 82k/10k
rather than the designed 130k/20k (reg 0x004B). This is also what made `/VA_MON`
look wrong all morning. One meter touch on the rail and the R24/R25 junction
settles it.

### 12:20 — U8 is the fault. AIN1 leaks, AIN0's mux does not connect, the board is clean

The AFE_VOUT row, swept the same way (single GND landmark at position 2 decoded
the reversal):

| # | pad | net | mV | due |
|---|---|---|--:|--:|
| 1 | C28.1 | `/ADC_AFE_VOUT` | 1650 | 1675 |
| 2 | C28.2 | GND | 0 | 0 |
| 3 | R33.1 | `/AFE_VOUT` | **1673** | 1675 |
| 4 | R33.2 | `/ADC_AFE_VOUT` | 1650 | 1675 |

`/AFE_VOUT` = 1673 mV is 0.67 × 2500 to within 2 mV. **The LMP91000 is working
correctly** — right reference, right INT_Z, right output. R33 and C28 are fine.

**And U8 pin 9 sits at 1650 mV while the ADS reports AFE_VOUT as 34 mV.**

That is a different failure from AIN1, where meter and ADS agreed (36 vs 35) and
the pin was genuinely dragged. Here the pin is correct and the converter is
wrong — and 34 mV is precisely what AIN1 produced. Checked in source before
concluding:

- Mux codes match SBAS925A (`ads1119.h:33-44`): AIN0-AGND = 011, AIN1 = 100.
  Each phase passes the right one (`main.c:1571,1580`). No channel mix-up.
- **PH_VREF (AIN1) runs immediately before PH_O2 (AIN0)** — consecutive states
  in the phase machine (`main.c:1567-1588`).
- `afe_vout_mv` is the raw AIN0 pin voltage, `uv / 1000`, unscaled
  (`main.c:1066`).
- A stale-read/DRDY bug would shift EVERY channel by one phase. It does not:
  PH_RE (AIN3) publishes VIN at 13138 mV, consistent with AIN3's own divider
  tap (~1752 mV × 7.5). No global shift, so AIN0 alone is broken.

**Conclusion: AIN0's mux switch is not connecting, and the converter retains
the preceding channel's sample.**

#### Both defects, and the board exonerated

| pin | channel | defect | evidence |
|---|---|---|---|
| U8.8 | AIN1 | input leaks ≈720 Ω to GND | 50 µA measured into the stub; node currents balance to 0.4 µA |
| U8.9 | AIN0 | mux does not connect | pin 1650 mV, converts as 34 mV = the preceding AIN1 sample |
| U8.4 | AIN3 | **works** | VIN 13138 mV, correct |

Why AIN1's node collapses and AIN0's does not, despite both inputs leaking:
source impedance. AIN1 is fed from 47k∥47k + 1k ≈ 24.5 kΩ, so a 720 Ω shunt
gives 1250 × 720/25220 = **35.7 mV** — the 36 mV measured. AIN0 is fed from
1 kΩ, and its milder ≈72 kΩ leak (23 µA across R33's 23 mV drop) barely moves
it. One high-impedance node is the only reason this was visible at all.

Proven healthy and NOT to be touched: the 2.5 V reference and its OPA2333
buffer (2500 mV on target), `/VREF_TRIM` end to end, R34, R35, R36, R33, C28,
R24, R25, and the LMP91000 with its whole bias chain.

**U8 (ADS1119IRTER, WQFN-16) is replaced. Nothing else.**

#### Fix the rail FIRST

3V3A is still intermittent and is currently substituted by a bench supply. Do
not fit the new ADS1119 until the rail is repaired: with AVDD absent and DVDD
present, `/ADC_VIN_MON` stays near 1.75 V off the VIN divider — which is NOT
on 3V3A — and forward-biases that input's ESD path into a dead AVDD. Every
3V3A dropout has been running that condition. A new part fitted under the same
rail fault is a candidate to fail the same way.

Outstanding on the rail: U3 pin 3 (EN, 111.86/86.95) against pin 1 (IN,
111.86/85.05) — an open EN joint lets the internal 500 kΩ pulldown shut the
regulator off; and U3 pin 5 (114.14/85.05) against the injection point, since a
break there would explain both the dead rail and the supply seeing no current.

### 12:35 — correction to 12:20: "replace U8" is not yet earned

Fab: *"are you sure?"* No. The 12:20 section states two conclusions more
strongly than the evidence carries. The measurements in it stand; the
attribution to silicon does not.

**1. "AIN1's input leaks ≈720 Ω."** The `/ADC_VREF_MON` stub is **C29 ∥ U8.8**,
and C29 was never excluded. The argument offered for the chip — two leaking
stubs beats two coincidentally shorted caps — **collapsed in the same section**
that made it: the AFE_VOUT sweep showed AIN0's stub is NOT strongly leaking.
Only one stub leaks, so a single soft-shorted C29 explains it completely. The
lift-C29 discriminator was proposed at 11:55 and never run.

**2. "AIN0's mux does not connect."** An **open solder joint on pin 9** is
indistinguishable from an open mux switch by this symptom: in both cases the
sampling capacitor is never connected to anything external and retains the
previous channel's charge. One is a reflow, the other a replacement. On a QFN
that took 30 minutes of hot air, the joint is the likelier of the two.

One datum leans against the open joint but does not settle it:
`/AFE_VOUT` 1673 − `/ADC_AFE_VOUT` 1650 = 23 mV across R33 1 k, so ~23 µA flows
INTO pin 9, and an open lead cannot draw current. That current could equally be
a leaky C28 (72 kΩ at 1650 mV). Leaning is not proving.

**Tests, in order, before any part is ordered:**

| | test | result ⇒ conclusion |
|---|---|---|
| A | lift one end of C29 (116.28 / 115.32, y=120.8), re-read `VREF_MON` | ~2500 ⇒ C29 was the leak, AIN1 healthy. Still 70 ⇒ the leak is U8.8 |
| B | reflow U8 with flux, minimum heat, re-read `AFE_VOUT` | ~1650 ⇒ it was a joint, no replacement. Still 34 ⇒ internal path broken, replace U8 |

A before B, so the reflow does not disturb the cap under test. The 3V3A repair
is independent and comes first regardless.

What survives 12:20 untouched: every pad voltage, the current balances, the
LMP91000's clean bill of health, `/VREF_TRIM` at 2500, and the exoneration of
R33, R34, R35, R36, R24, R25 and the reference chain.

### 13:00 — the leak is SUPPLY-DEPENDENT. U8 is damaged; every passive cause is excluded

Two experiments closed it.

**C29 removed** (Fab): `VREF_MON` unchanged at 70 mV across three reads,
`/VREF_MON_RAW` still 86 mV. C29 excluded as a component. This also proved pin
8 is not an open joint — current is flowing into that stub, and an open lead
draws none.

**3 kΩ pull-up to 3.3 V on `/ADC_VREF_MON`** (Fab): node rose to 765 mV,
`/VREF_MON_RAW` to 783 mV. Solving:

    in  from pull-up:  (3300 - 765)/3k     = 845 uA
    in  through R36:   (783 - 765)/1k      =  18 uA   (predicted 20)
    at node A: in (2500-783)/47k = 36.5 uA, out 783/47k + 18 = 34.7 uA
                                            -> balance 1.8 uA
    leak: 863 uA at 765 mV                  = 887 ohm

against 720 Ω at the unpulled operating point (36 mV / 50 µA). **Ohmic across
a 17× current range** — not a junction, which would conduct nanoamps at 36 mV
and get steeply less resistive at 765 mV. R34/R35/R36 confirmed intact a third
time.

**Then the falsifier: ohm `/ADC_VREF_MON` to GND with the board unpowered.**
Fab measured **36 kΩ**. R36 1 k + R35 47 k with a partial path through R34
puts a clean board between 24 k and 48 k, so 36 kΩ IS the passive network —
and it is 40× the 885 Ω the powered measurement requires.

That reading self-validates the conditions too: with the external 3.3 V still
injected it would have read ~866 Ω, and with the 3 k pull-up still on a
low-impedance source, ~3 kΩ. Neither happened.

**The leak exists only when the chip is powered**, which excludes every
passive cause simultaneously:

| candidate | verdict |
|---|---|
| surface residue / coating film on the net | **excluded** — would conduct unpowered |
| residue across the empty C29 footprint | **excluded** — same |
| solder/metal bridge to the pad under U8 | **excluded** — same |
| C29 soft-shorted | excluded by removal |
| supply-dependent conduction inside U8 | **only survivor** |

A conduction path that appears with AVDD and vanishes without it is a damaged
input clamp or a latched parasitic — consistent with the ohmic behaviour.

**U8 (ADS1119IRTER) is damaged and is replaced.** Unlike the 12:20 call, the
falsifying experiment was run and came back clean. The AIN0 misreport (pin at
1650 mV, converts as 34 mV, = the preceding AIN1 sample) is a second defect in
the same part and no longer needs separating from a joint.

Still exonerated, and not to be touched: the 2.5 V reference and its OPA2333
buffer, `/VREF_TRIM`, R24, R25, R33, R34, R35, R36, C28, and the LMP91000 —
whose output at 1673 mV is 0.67 × 2500 to within 2 mV.

#### Likely cause, and the sequencing that follows from it

Every 3V3A dropout ran the ADS in an abusive state: DVDD present, AVDD at
zero, and `/ADC_VIN_MON` still held near 1.75 V by the VIN divider, **which is
not fed from 3V3A**. That injects into a dead supply through the input clamp,
repeatedly, across at least the 22:37 and the 09-12 morning events.

**Repair 3V3A before fitting the replacement**, or the new part is a candidate
to fail the same way. Rail work outstanding: U3 pin 3 (EN, 111.86/86.95) vs
pin 1 (IN, 111.86/85.05) — an open EN joint lets the internal 500 kΩ pulldown
shut the regulator off; and U3 pin 5 (114.14/85.05) vs the injection point.

**Open, asked three times:** what the bench supply is set to. PA7 keeps putting
the 3V3A tap at 2612 mV, i.e. a **5.2 V** rail through the ÷2 R24/R25 are
supposed to be — inside the ADS1119's range but at the LMP91000's 5.25 V
ceiling. Either the supply is set high, or R24/R25 as fitted are not ÷2 and the
firmware's scale factor is wrong. Fitted-vs-designed divergence has precedent
here (the VIN divider is 82k/10k, not the designed 130k/20k, reg 0x004B).

### 13:15 — bench supply is 3.3 V, which closes AIN2 too. Three inputs damaged, one good

With the rail confirmed at **3.3 V**, `/VA_MON` owes 1650 mV and PA7 reports
2612. Solving with R24/R25 at their design 10k/10k:

    in  through R24: (3300 - 2612)/10k = 69 uA
    out through R25:  2612/10k         = 261 uA
    deficit                            = 192 uA arriving from elsewhere

The only other path into that node is R37's 1 kΩ, which requires
`/ADC_VA_MON` about 192 mV higher — and Fab's morning readings were
**R37.1 = 2.590 V, R37.2 = 2.788 V**, a 198 mV drop for **198 µA**. Two
independent routes to the same current, one from the divider arithmetic and
one from a direct measurement taken hours earlier.

So **AIN2 sources ~195 µA from AVDD through ≈2.6 kΩ** — the same
supply-dependent conduction as AIN1, clamping up instead of down. Forward
check: inject 195 µA into the divider's Thévenin (1650 mV, 5 kΩ) → 2625 mV
predicted against 2612 measured.

This independently reinstates the AIN2 half of the 10:35 section, which was
withdrawn at 11:05 for resting on possibly-shifted designators. It was right;
it is now derived from R24/R25 and a known 3.3 V rail instead.

**Also confirmed: R24 and R25 are the ÷2 they are drawn as, and the firmware's
`O2P_HW_DIV_VA_NUM/DEN` scale is correct.** The VA anomaly was never a
divider problem.

#### Final state of U8

| pin | channel | defect | symptom |
|---|---|---|---|
| U8.9 | AIN0 | mux does not connect | AFE_VOUT = 34 mV, the preceding AIN1 sample |
| U8.8 | AIN1 | ≈885 Ω to GND, powered only | 24.5 kΩ source dragged to 36 mV → VREF_MON 70 → ADC_RANGE → `vref_measured` false → every ext-ref channel suppressed |
| U8.5 | AIN2 | ≈2.6 kΩ to AVDD, powered only | `/VA_MON` lifted 1650 → 2612, VA_MV 5224, VA_LOW trips |
| U8.4 | AIN3 | **good** | VIN 13138 mV |

Every symptom chased since 2026-09-11 22:24 reduces to this one part. Board
exonerated by balanced measurements: the 2.5 V reference and its OPA2333
buffer, `/VREF_TRIM`, R24, R25, R33, R34, R35, R36, C28, and the LMP91000
(output 1673 mV = 0.67 × 2500 within 2 mV).

#### Cause: NOT established

The "AVDD absent, DVDD present, `/ADC_VIN_MON` held near 1.75 V by a divider
not on 3V3A, injecting into a dead rail through the input clamp" theory from
12:20 **does not fit the damage pattern.** AIN3 is exactly the input whose
source stays alive through a 3V3A dropout and would carry that injection
current — and AIN3 is the only undamaged channel. Withdrawn as an explanation.

Repair 3V3A before fitting the replacement anyway, on general grounds: an
intermittent analog rail under a fresh part is not a state to commission in.
Rail work outstanding: U3 pin 3 (EN, 111.86/86.95) vs pin 1 (IN,
111.86/85.05), and U3 pin 5 (114.14/85.05) vs the injection point.

### 13:40 — live confirmation of BOTH defects: AIN1 tracks, AIN0 returns AIN1's sample

Fab asked whether the firmware ever reported the pulled-up node. It had not
been read — the 13:00 analysis worked only from meter values, missing a free
cross-check. With the 3 kΩ refitted and the meter on `/ADC_VREF_MON` at
775 mV, the registers say:

    VREF_MON = 1484 mV  ->  AIN1 pin = 742 mV     (was 70 -> 35)
    AFE_VOUT =  740 mV                             (was 34)

**AIN1's converter and mux are GOOD.** VREF_MON moved 70 → 1484 with the
pull-up, so AIN1 reads its own pin and the pin is genuinely dragged by the
leak. A channel broken the way AIN0 is would not have tracked. This removes
the last alternative reading of the AIN1 evidence.

**AIN0 returns AIN1's sample — conclusive.** AFE_VOUT was 34 mV while AIN1 sat
at 35; it is now **740 mV while AIN1 sits at 742**. It followed a pull-up
applied to a *different net*, while `/AFE_VOUT` itself has not moved from
1673 mV. This was a stated prediction (12:20, refined 13:00) before the
resistor went back on, not a fit after the fact.

Leak recomputes at the third operating point: (3300−775)/3k = 842 µA, plus
~18 µA through R36 → ~860 µA at 775 mV → **901 Ω**, against 885 and 887
earlier. Stable and ohmic across ~20× in current.

VIN stays 0xFFFF because 1484 mV is still outside the trim band, so
`finish_vref` keeps ADC_RANGE set and `vref_measured` false — the suppression
path behaving exactly as designed.

#### Note for the replacement: the ADS reads ~3–4 % low

Meter vs ADS on the same pin, both operating points: 36 → 35, and 775 → 742.
Same direction, same magnitude — a gain error, most plausibly the internal
2.048 V reference. R34/R35 are 0.1 % parts, so the ×2 reconstruction is not
the source. Not actionable while the part is being replaced, but it would bias
O2, so **check the internal-reference gain against a meter on the new U8**
before trusting a calibration.

### 14:05 — DOWNGRADE of 13:00: the unpowered 36 kΩ is confounded by temperature

Fab: *"are we sure now its the ADC leaking? how can that happen?"* Not sure.
The 13:00 section's central argument — "36 kΩ unpowered versus 885 Ω powered,
therefore every passive cause is excluded" — **has a confound I should have
caught: the board was powered down AND cooling at the same time.**

This file already documents thermally-activated ionic leakage on this board
(2026-09-10): `/VREF_TRIM` at 174 mV hot, climbing monotonically to a ~320 mV
plateau cold, with the explicit note that *"silicon ESD damage doesn't halve
its resistance in minutes with temperature; ionic contamination does."* So a
36 kΩ reading taken while cooling is not evidence of a de-energized leak.

What still stands: the leak is **ohmic and stable at ~890 Ω** across three
operating points (720 Ω at 36 mV, 887 Ω at 765 mV, 901 Ω at 775 mV), C29 is
excluded by removal, and both AIN0 and AIN1 behaviours are confirmed live.

#### If it IS supply-dependent, the mechanism is latch-up

A parasitic SCR fits every observed property and nothing else does: ohmic,
hundreds of ohms to a few kΩ, conducts only while the supply sustains its
holding current, vanishes on power-down, and requires a trigger. Contamination
and a shorted junction both conduct unpowered.

**And this board supplies a trigger on every power-up.** VIN is upstream of
everything (VIN → U1 buck → +5V → R32 → +5V_ANALOG → U3 → 3V3A), but
`/ADC_VIN_MON` is fed from the VIN divider directly — R26/R27, fitted 82k/10k,
so ~1.42 V at 13.1 V in — through R38 1 kΩ. That input is biased to 1.4 V
**before AVDD has risen at all**, which is 1.1 V beyond SBAS925A §6.1's
`AVDD + 0.3 V` limit for AIN0–3/REFP/REFN.

Two qualifications, stated so this is not oversold:

- R38 limits the clamp current to ~700 µA, **14× under** the ±10 mA continuous
  input-current abs-max (same table). So it is an abs-max VOLTAGE violation,
  not an evident destruction mechanism.
- But it is a credible latch-up trigger; it occurs on every power-up; and it
  occurs on every 3V3A dropout, because **AIN3 is the only input that stays
  biased when 3V3A dies** — every other input's source (the reference via the
  OPA2333, the LMP output, the 3V3A divider) is itself 3V3A-derived. This also
  explains why AIN3 is the one undamaged channel: it is the injector, not the
  victim. (It rescues, in better form, the cause theory withdrawn at 13:15 —
  under latch-up the injecting pin need not be the affected one.)

**Consequence: do not fit a replacement U8 yet.** If this is latch-up, the part
is not damaged and a new one would be commissioned into the same trigger.

#### Tests, cheapest first

1. **Ohm `/ADC_VREF_MON` to GND within seconds of power-off, board still warm;
   repeat after five minutes.** ~900 Ω warm and 36 kΩ cold ⇒ thermally
   activated contamination, and 13:00 is wrong. 36 kΩ in both ⇒ genuinely
   supply-dependent.
2. If supply-dependent: **bring 3V3A up BEFORE VIN**, or power with VIN absent,
   and read `VREF_MON`. Near 2500 ⇒ latch-up from VIN-before-AVDD, U8 is fine,
   and the defect is rail sequencing.
3. **Warm the board while powered** and watch `VREF_MON` over the wire. A
   strong negative tempco on the leak indicts contamination independently of
   test 1. Using the probe's own heater for this needs Fab's explicit word
   (standing hands-off order).

#### Design note regardless of outcome

`/ADC_VIN_MON` being biased from a rail that is upstream of AVDD is a
sequencing hazard in the Rev A design, independent of whether it caused this
failure. A series resistor large enough to hold the clamp current to a few
tens of µA, or a divider referenced to a rail that comes up with AVDD, would
remove it. Carry this into any Rev B review.

### 14:25 — the leak is NOT supply-dependent. Temperature is the variable: contamination

Test run in the cleanest available configuration — VIN on, 3V3A off, board
warm and running, Fab's 3 kΩ pull-up to an external 3.3 V still fitted, so no
cooling confound. Predictions were ~2940 mV for "leak needs AVDD" and ~730 mV
for "leak present anyway".

**Measured `/ADC_VREF_MON` = 1.1 V.** Solving:

    in  from 3k pull-up: (3300 - 1100)/3k     = 733 uA
    out through R36 + collapsed divider (24.5k): 1100/24.5k = 45 uA
    leak: 688 uA at 1100 mV                   = 1.6 kohm

**The leak conducts with AVDD at zero.** Latch-up is excluded, and the 13:00
conclusion is wrong.

All three operating points together:

| condition | board | AVDD | leak |
|---|---|---|--:|
| powered, running | **warm** | 3.3 V | ~890 Ω |
| VIN on, 3V3A off | **warm** | 0 | ~1.6 kΩ |
| fully off, ohmmeter minutes later | **cold** | 0 | 36 kΩ |

Removing AVDD moves it **1.8×**. Cooling moves it **22×**. Temperature
dominates by an order of magnitude — the 2026-09-10 signature in this file
("silicon ESD damage doesn't halve its resistance in minutes with temperature;
ionic contamination does"). The 36 kΩ reading was **cold**, not
de-energized; that was the confound, and it is now measured rather than
suspected.

**Working conclusion: the AIN1 leak is thermally-activated ionic contamination
on `/ADC_VREF_MON`.** Candidate fix is the 09-10 recovery — IPA clean plus a
bake, which took `/VREF_TRIM` from 302 mV to 2488 mV that day. The net's
surface extent is small: R36.2's pad, a short trace, the now-empty C29
footprint (its GND pad 0.96 mm away), and the copper at U8 pin 8. A bake also
reaches under the package, which a wipe does not.

**AIN0 remains a separate defect and is not cleanable.** A channel returning
the PRECEDING channel's sample is a switching fault, not a resistive one, and
contamination bridging AIN0 to AIN1 is excluded because their pins do not
equalise: 1650 mV against 36 mV across source impedances of 1 kΩ and 24.5 kΩ.
Confirmed live at 13:40, where AFE_VOUT tracked AIN1 from 34→740 while
`/AFE_VOUT` itself stayed at 1673.

So the board may need **only a clean and bake for AIN1**, with U8's
replacement decided afterwards on AIN0 alone — and judged on a board whose
high-impedance net is no longer poisoned.

**To confirm before acting:** 1.1 V is also the value reported for
`/ADC_VIN_MON` minutes earlier. Two different nets reading the same value is
possible but, after this morning's designator offset, is worth one explicit
re-check that the probe landed on two distinct pads.

### 14:45 — retractions: the 1.1 V readings were both `/ADC_VREF_MON`, and unpowered data cannot answer this

Fab: *"i always injected the 3.3V/3k at `/ADC_VREF_MON`"*, and the 1.1 V was
taken with **3V3A = 0 and 3V3D = 0**. Two consequences, both retractions.

**1. The AIN3 injection analysis (14:05) is withdrawn.** "The injection reads
1.1 V" was read as `/ADC_VIN_MON` and turned into "33 µA into AIN3's clamp with
AVDD at zero, confirming the abs-max violation is actually happening."
`/ADC_VIN_MON` was never measured. That number does not exist.

What survives is only the schematic observation, unmeasured: `/ADC_VIN_MON` is
fed from the VIN divider (R26/R27, R38) and VIN is upstream of AVDD
(VIN → U1 → +5V → R32 → +5V_ANALOG → U3 → 3V3A), so that input is biased
before AVDD rises on every power-up, beyond SBAS925A §6.1's `AVDD + 0.3 V`.
Keep it as a **Rev B design note**, not as a quantified trigger for this
failure.

**2. The 14:25 contamination conclusion is withdrawn, and so is the 13:00
supply-dependence conclusion.** Both rested on unpowered measurements of a CMOS
input. With AVDD and DVDD at 0, the input protection is a diode to a 0 V rail —
exactly what the abs-max table describes — so conduction above roughly half a
volt is expected of an undamaged part, and behaviour below it depends on where
the floating rails settle. **Unpowered readings on this pin cannot separate
damage from contamination in either direction.** That disqualifies the 36 kΩ
ohmmeter reading (offered at 13:00 as the decisive falsifier) and the 1.6 kΩ
derived at 14:25 alike.

(For the record, 1.1 V at 688 µA is also a poor fit for a single forward ESD
diode, which would sit near 0.65 V at that current. Whether that means a
series element, a non-diode clamp, or a floating AVDD being lifted by the
injected current is unresolved — and is another reason not to build on it.)

#### The one durable measurement

    Powered, AVDD = 3.3 V: AIN1's pin sits at 36 mV with 50 uA flowing into it.

No healthy structure conducts 50 µA at 36 mV; protection is nanoamps there. It
scales ohmically to ~860 µA at 775 mV, a 21× voltage range. **That resistive
path of ~800 Ω is real, and it is the whole of the AIN1 case.** Everything
else measured today about AIN1 either supports it (the meter and ADS agreeing
on the pin; the divider currents balancing to under 2 µA three times; AIN1
tracking the pull-up to 1484) or is uninformative (all unpowered data).

#### Remaining test — must be POWERED

Board running, vary only temperature, poll `VREF_MON` over the wire:

- cools → climbs from 70 toward 2500 ⇒ contamination, cleanable
- warms → drops below 70 ⇒ contamination
- unmoved ⇒ fixed defect in the die ⇒ U8 damaged

Supporting but not decisive: `VREF_MON` has read exactly 70 mV on every read
across five hours and several reboots, with no drift — though the board's
temperature was stable throughout, so that is not itself a test.

AIN0's defect (returns the preceding channel's sample, confirmed live at 13:40)
is untouched by any of this and remains a genuine ADS fault.

### 12:10 — powered temperature sweep: the leak rises with heat. Contamination EXCLUDED

The test the 14:45 retraction called for, run with `tech/bench/o2p_reg_watch.py`
(farming `ee65122`) polling the leak and the probe's own temperatures together.
Fab heated the bottom-side row at R36/C30 — directly over `/ADC_VREF_MON`'s
copper and the empty C29 footprint — then let it cool.

| chamber °C | AIN1 pin mV | leak Ω |
|--:|--:|--:|
| 22.24 | 36 | 727 |
| **30.93** | **39** | **789** |
| 28.00 | 37 | 747 |
| 26.51 | 36 | 727 |
| 24.70 | 36 | 727 |
| **33.29** | **44** | **894** |

Monotonic above ~27 C, an 8 LSB excursion in all.

**The pin rose with heat and retraced on cooling.** Contamination does the
opposite: an ionic film conducts harder when warm, which would pull the pin
DOWN. On 2026-09-10 that is exactly what this board showed on `/VREF_TRIM` —
174 mV hot climbing to a 320 mV plateau cold.

**No tempco is quoted, deliberately.** The whole excursion is 3 LSB of the pin
(36→39→37→36), and it is back at baseline by 26.5 °C — 4.3 K above the
starting temperature. That is thermal lag, not curvature: the heat went into
the board beside U8 while the reference thermometer is the SHT45 elsewhere, so
die and chamber are not the same temperature during a transient. Extracting
%/K from this would be false precision. A real tempco needs soak-and-hold at
two temperatures. **It is not needed — direction alone settles the question.**

**Both contamination mechanisms are excluded by this one trace**, for two
different reasons:

1. *Instantaneous ionic conduction* is thermally activated, so resistance
   **falls** when warm. Ours rises. This is the 09-10 signature on
   `/VREF_TRIM` (174 mV hot, 320 mV cold).
2. *Drying out* — sustained heat driving off moisture — raises resistance, and
   that is what the 09-10 bake achieved (302 -> 2488 mV). It would fit the
   heating half of our trace. But **drying is irreversible and ours retraced**
   (789 -> 747 -> 727 as it cooled). Excluded.

Confound checked and dismissed: for `/VREF_TRIM`'s own drift to raise the pin
8.3 %, the reference would have to climb 104 mV over 8.7 K, ~4800 ppm/K on a
divider of 0.1 % resistors and a cermet trimpot. Not possible.

What remains is either the leak's resistance rising with temperature or the
ADS's offset drifting up (~350 µV/K — at 36 mV we are reading 1.8 % of full
scale, and a damaged part may drift freely). **Both are inside the die.** They
cannot be separated by these numbers and do not need to be: neither is on the
board.

**VERDICT: the fault is the part, not the board. No clean, no bake. Replace
U8.** This agrees with AIN0 (stuck mux) and AIN2 (leak to AVDD), neither of
which was ever cleanable, so all three defects point one way.

Earlier in this session a "+975 ppm/K" figure was quoted and an argument built
on it that a MOS channel specifically fit. That was an arithmetic error of 10×
(8.5 % over 8.69 K is ~9800 ppm/K) and, corrected, the magnitude sits at the
steep edge of a mux channel rather than inside it. With 3 LSB of signal the
magnitude carries no mechanism claim at all. Withdrawn; the "damaged input
multiplexer" picture remains an attractive single-fault story for AIN0/AIN1/
AIN2 but is not established by the tempco.

#### What is fixed and what is next

- Replace U8 (ADS1119, WQFN-16). Four are on hand: 3× IRTET confirmed in
  InvenTree plus 1× IRTER from PO-0010.
- **Repair 3V3A first** — still intermittent, still unexplained, and not
  something to commission a fresh part under.
- After fitting: check the internal-reference gain against a meter before any
  O2 calibration. The old part read 3–4 % low at two operating points and it
  is not known whether that was the chip.
- Rev B note, unmeasured but derivable: `/ADC_VIN_MON` is biased from the VIN
  divider while VIN is upstream of AVDD, so that input exceeds
  `AVDD + 0.3 V` on every power-up.

### 12:50 — Codex xhigh review: the U8 verdict is DOWNGRADED. Contamination is not excluded

Independent adversarial review (codex exec, network + headed Chrome over CDP;
log `~/codex-reviews/o2probe-afe-20260912/review.log`). Its ACCESS proof is
corroborated: the live keeper read it quoted, `VREF_MON 72` at uptime 1206 s,
matches this session's own watcher log (72 at uptime 1172 s). No
`no connected browsers` in the log.

**Its verdict: "U8 is a credible suspect, but 'contamination excluded; replace
U8' is not established."** Accepted. The 12:10 verdict and its "No clean, no
bake" instruction are withdrawn.

#### Findings that change the decision

1. **The powered temperature sweep does NOT exclude contamination.** The sign
   argument holds ionic mobility constant while varying temperature — but
   heating a coated board also changes the film's water content, and
   **hydration is reversible**, so "it retraced, therefore not drying" does not
   follow. Thermal movement of a cracked contact or a residue bridge is equally
   admissible. And the document's own data defeats a single-valued relationship
   with chamber temperature: **894 Ω at 33.29 °C versus 747 Ω at 32.61 °C**.
   The die-leading-chamber explanation is plausible but the copper, coating and
   joints can lead that sensor too; it cannot establish a die location.

2. **Current entering a PCB stub is not current entering the package.**
   Removing C29 excludes C29 as the *component*; it does not exclude residue
   across its now-vacant footprint, a bridge beneath U8, or another board path.
   So "current flows, therefore pin 8 is not open" is circular — it assumes the
   current's destination. Same for the 23 µA at R33 and pin 9. Also flagged:
   **R39, a DNP shunt footprint on `/ADC_AFE_VOUT`**, whose fitted state and
   surface condition were never established (Rev A netlist).

3. **The 36 kΩ unpowered reading was real evidence, wrongly discarded.** A
   fixed ~800 Ω ohmic shunt to ground should dominate an ordinary unpowered
   resistance measurement; parallel protection structures do not make it
   vanish. So 36 kΩ is evidence **against the fixed-ohmic-shunt model** — the
   14:45 blanket dismissal of all unpowered data was too broad. Conversely the
   1.1 V injection genuinely IS confounded, not only by protection but by
   **back-powering**: 688 µA through the clamp can partially raise AVDD. That
   rehabilitates supply-dependence as a live hypothesis. Net effect: whether
   the leak needs the supply is **unresolved**, and this session concluded both
   ways on inadequate grounds.

4. **AIN2 is not localized to U8.** The arithmetic survives conditionally, but
   "the only other path into `/VA_MON` is R37" omits **MCU PA7**, and the R37
   pair remains an unverified single-designator reading from the offset window
   (its different PCB row means the offset does not prove it wrong — but does
   not validate it either). Additionally, **`VA_MV = 0` is unexplained**: the
   claim that it is an overrange artifact contradicts main.c:869, where
   `g_acc_clipped` returns early and PRESERVES the earlier PA7 value (~5190).

5. **AIN0's cross-channel dependence survives; "open mux" is an attribution.**
   The reviewer found no accumulate/DRDY/reference-selection bug in source, and
   noted the firmware is stronger than this document credited — config readback
   with a discarded conversion, status-readiness gating, an eight-conversion
   average with the accumulator reset after PH_VREF, and diag-9 latched per
   cycle. R33/C28 settling is ~0.1 ms against ~50 ms per O2 conversion, so
   settling is not it either. But no runtime transaction trace exists, so an
   internal mux defect is not distinguished from every connection fault.

#### Arithmetic and sourcing errors confirmed against the primaries

| claim | published | correct |
|---|---|---|
| `/VREF_TRIM` tempco needed to fake the sign | 4800 ppm/K | **9590 ppm/K** — a half-node increment was divided by the full-node value |
| divider current closure | "balance 0.4 µA" | −0.47 µA, and **±0.5 mV rounding alone permits ±1.03 µA**, so it is consistency, not verification of three resistors |
| VIN scale in the AIN3 argument | ×7.5 (caps header) | **×9.18** (stored `VIN_DIV_X1000` 0x004B, fitted 82k/10k) |
| TPS7A20 ICL 360/520/730 mA | quoted as bounding U3 | that row is **`VOUT < 1.5 V` (DBV)**; the ≥1.5 V rows name YCJ/YCK and DQN, so it is **unverified** for a 3.3 V DBV part. ISC 160 mA typ is correct |
| "leak is ohmic" | 720→887→901 Ω | a ~25 % spread — broadly resistive loading, not a constant ohmic element |
| VREF_MON granularity | "2× the pin voltage" | 2 × floor(µV/1000): **2 mV register steps, and twice a TRUNCATED estimate** |
| `0xFFFF` in VREF_MON | "3V3A is down" | an invalid-snapshot sentinel that can also mean an I²C/readback/DRDY failure or abandoned acquisition |

#### What survived

- **The powered AIN1-stub load is real.** Landmarked multi-pad readings, ~50 µA
  inferred, persisting after C29 removal. SBAS925A §6.5 gives absolute input
  current as **±5 nA typical at VIN = 0** (no maximum in that row), so
  "protection is nanoamps at 36 mV" is stronger than the spec — but 50 µA is
  plainly inconsistent with healthy input loading. **An abnormal circuit
  condition is established; its physical location is not.**
- The watcher's formula: 24500 × V/(1250−V), 726.524 → 727 Ω at 36 mV. Correct.
- The mux map (011/100/101/110), the phase order, and the diag-9 override all
  match source. ADS specifies single-cycle settling.
- The PA7 ÷2 scaling discrepancy (contract 47k/94k vs fitted 10k/10k) is
  harmless for voltage reconstruction, and the AIN2 current calculation
  correctly used 10k.
- ADS absolute-maximum quotations are correct.

#### Standing position

U8 replacement is **a reasonable candidate intervention after rail repair, not
a proven necessary remedy.** Still unexcluded: board contamination, damaged or
intermittent joints, fitted-component deviations, PA7 error or loading, shared
supply/ground/reference faults, and runtime acquisition behaviour that source
review cannot reach. **An IPA clean and bake is cheap, non-destructive, and has
precedent on this exact board (09-10) — it should be tried before desoldering.**

### 13:10 — ROOT CAUSE from the VictoriaMetrics history: heat applied to dry the coating, 22:24

Fab asked whether the captured ADC telemetry had been examined for over-voltage.
It had not — five hours of live bench work had been done without querying the
historian. Three queries answered what the bench had not.

**There is no over-voltage anywhere in fourteen days.** Sentinels excluded:

| channel | max over 14 d | implied ADS input | AVDD |
|---|--:|--:|--:|
| `gas_vin_mv` | 13138 | AIN3 pin **1.43 V** (stored ÷9.18) | 3.3 V |
| `gas_afe_mv` | **2495 mV** | AIN0 | 3.3 V |
| `gas_vref_mv` | **2512 mV** | — | 3.3 V |
| `gas_va_mv` 5226 | `/VA_MON` tap **2.61 V** | AIN2 | 3.3 V |

No ADS input ever exceeded ~2.6 V against a 3.3 V supply, in any recorded
sample.

**Both defects were born in the same minute, 2026-09-11 22:24.** `gas_va_mv`
had been a steady 3080–3114 mV since **09-06**; minute-resolution trace:

    time    vref    va      vin     afe   faults   i2c_err  ads_fail  duty  chamber  die
    22:23   2496   3114   13119    980   0x8041         0         0   0.0     23.4   23.9
    22:24     78   4432   65535     43   0x8805        18         3   0.0     28.4   29.4
    22:26     76   5054   65535     38   0x8805        18         3   0.0     40.5   48.0
    22:35     70   5028   65535     35   0x8805        18         3   0.0     23.2   27.7
    22:37  65535     12   65535  65535   0x8047       227        32   0.0     23.8   26.2   <- reset, cause 12
    22:41+                                                                     33->68.8  72.2 <- the hot-air session

Heater duty is **0.0 throughout**, so the 22:24–22:26 excursion was external —
and it is a *separate, earlier* event from the 22:41 hot air. Chamber RH was
also climbing 34.6 % → 38.3 % across 22:03–22:23, consistent with coating
solvent outgassing after the ~22:03 application.

**Fab, asked: "i remember i applied some heat to dry the coating paint. this
was probably not a good idea."** That is the event, and it dates the failure to
the minute.

**Mechanism:** warm solvent wicks under a QFN by capillary action, carrying
dissolved no-clean flux with it, and leaves a conductive residue that persists
after cool-down. It accounts for two ADC channels failing in the same sample,
I²C errors appearing from zero at the same instant, and the fault surviving the
return to 23 °C.

**Crucially, the stress required for silicon damage is absent.** At 22:24 the
die reached 48 °C against an ADS1119 junction rating of 150 °C, with no
over-voltage on any input. There is no recorded stress capable of damaging the
part at the moment it broke.

#### Consequences

- **The 12:10 tempco argument against contamination is now worth almost
  nothing.** It assumed an aqueous ionic film, whose conduction rises with
  temperature. A paint-plus-flux residue is not that, and its tempco sign is
  not well defined. The Codex review had already flagged the argument as
  holding hydration constant; the paint identification removes what was left.
- **Do not desolder U8.** Clean first, then bake — the 09-10 recovery on this
  exact board (IPA surface clean plus a ~20 min bake, `/VREF_TRIM` stepping
  302 → 2488 mV while hot) is the precedent and the recipe.
- Sequence matters and is the whole lesson: baking a CLEANED board drives
  residue off; baking WET PAINT mobilizes it into the package. Clean, then bake.
- If cleaning does not reach it, the film is under the package. U8 then comes
  off **to clean underneath**, and may be refittable rather than scrapped.
- Open: which coating was used on 09-11. The 09-10 record names Edding 751
  around U7/U8/U4; if the same, it is an enamel marker and IPA may not shift it
  once set. The answer decides the solvent.
- `VREF_MON` will be watched over the wire throughout, with
  `tech/bench/o2p_reg_watch.py`; on 09-10 the recovery appeared as a step.

---

## 2026-09-12 14:00 — What the existing telemetry already settles (no bench time)

Fab, on being handed a list of three measurements as prerequisites for the
Rev B "delete the ADS1119" proposal: *"cant we answer this already from the
data we have?"* Yes — and the reason is a property of Rev A worth recording
here, because it turns 129 hours of ordinary telemetry into a converter
characterisation.

### Rev A wires BOTH converters to one node

`/ADC_VA_MON` — a 10k/10k divider off 3V3A, Thevenin 1650 mV / 5 kOhm — is
read by the ADS1119 on AIN2 (`hw_caps_rev_a.h:12`, `:92`) AND by the STM32 on
PA7 / ADC1_IN7 (`hw_contract.h:53`, `:60`). Both scale x2 into the same
register 0x0011 (`o2p_scale_va_ads`, `sampler_logic.h:119`, against
`read_divided_rail`, `mcu_adc.c:195`), so the published numbers are directly
comparable with no rescaling.

Which one publishes depends on the VREF gate: `phase_rails` writes PA7 first
(`main.c:319`), and `finish_electrode` overwrites it with AIN2 **only if the
external reference converted** (`main.c:869`). So the 22:24 failure on 09-11
is a changeover, not merely a fault — `gas_va_mv` is the ADS before it and the
STM32 after it.

**That cross-check is not usable on this board, and the reason is itself a
finding.** Post-22:24 the AIN2 fault (~2.6 kOhm to AVDD) pulls the shared
node up, so both converters read a corrupted node: `gas_va_mv` jumped
3114 → 4432, i.e. the tap at 2216 mV instead of 1650, which implies roughly
9.6 kOhm of injected path. **A defect inside the ADS1119 corrupted a node the
STM32 also measures** — the independent-witness role PA7 exists for
(`mcu_adc.h:10`) was defeated by sharing a net with the part it was meant to
witness. Carry that into Rev B: an independent monitor needs an independent
node, not just an independent converter. And the remaining post-failure window
is unusable for noise anyway — 09-12 was a bench day, die to 87.8 C, rail
pulled down, current injected, so its 450 mV of "noise" is Fab's hands.

### The O2 channel's real in-situ noise, and the grid it is published on

`tech/bench/o2p_adc_noise_from_vm.py` (farming) exports raw samples and takes
the stddev of **adjacent differences**, which removes anything slower than the
sample interval; plain stddev over days is dominated by drift, not noise.
Filtered to pairs where `gas_t_die_c` moved under 0.1 K, healthy era
2026-09-06 → 09-11 22:23, 4981 pairs on `gas_afe_mv` (AIN0, at the pin):

| adjacent-pair difference | share |
|---|---|
| 0 mV | 71.3 % |
| 1 mV | 28.2 % |
| 2 mV | 0.42 % |
| >= 3 mV | 0.06 % |

sd of differences 0.610 mV → **chain noise 0.43 mV rms**, i.e. 0.013 %O2 on
the 33.2 mV/%O2 span. The distribution is the point: a chain dithering between
two adjacent codes 71/28 is quieter than the grid it is reported on.

And the grid is coarse. `main.c:1066` stores `uv / 1000` — whole millivolts —
while `ads1119.h:124` resolves 2500/32768 = **76 uV/LSB**. The probe throws
away a factor of 13 of the ADS1119's resolution before transmitting. Nothing
downstream has ever seen it.

Consequence for the Rev B decision, in full in
`docs/2026-09-12-revb-proposals-from-the-afe-failure.md` P0: a bare STM32
12-bit conversion against a 2.5 V VREF+ is 0.610 mV/LSB — **finer than the
millivolt the probe publishes**, and the same size as 1 K of the cell's own
~900 ppm/K drift. Two datasheet items from DS12232 Rev 5 close the other two
objections: `Ilkg` for PA7's `FT_a` pad is **+/-70 nA max** (Table 51, p.81),
not the +/-1 uA I had asserted — a 14x error on my part, which demotes the
"lower the divider impedance" item from mandatory to desirable — and
`IDDV(ADC)`, the current VREF+ must supply, is **0.26 uA typ at 10 kSps**
(Table 58), far above the probe's rate. Datasheet archived at
`~/dev/ee/datasheets/ST-STM32G071-DS12232-Rev5.pdf`.

### Also fixed: this log's own watcher gave a sign-blind verdict

`tech/bench/o2p_reg_watch.py` reported the +57 K soak as *"thermally
activated, i.e. contamination"* when the leak resistance had **risen**
727 → 873 Ohm — the opposite of the ionic signature. The verdict branched on
`rhi / rlo`, a ratio of independently-taken extrema that is >= 1 by
construction, so the sign was never consulted. It now least-squares-fits R
against T over the paired samples and reports signed ppm/K: falling
resistance = ionic, rising = doped-silicon path, flat = fixed ohmic shunt, and
too few samples or too little span returns INCONCLUSIVE rather than any
physical verdict. Calibrated against the real trace (now +3202 ppm/K → "NOT
ionic; suspect the die") plus a synthetic ionic case, a fixed shunt, and both
unevaluable inputs.

### 16:30 — U8 replaced: ALL THREE defects gone. And U3 is the second failed part

**The new ADS1119 fixed the AFE completely.**

| register | before | after |
|---|--:|--:|
| `VREF_MON` | 70 | **2466 → 2464** (pin 1233, ideal 1250) |
| `VA_MV` | 5226 | **3246** — a real 3.3 V rail, the AIN2 injection gone |
| `VIN_MV` | 13138 | 13119 — unchanged, AIN3 was always good |
| `i2c_errs` | 1132 | **0** |
| `ads_fail_count` | 141 | **0** |
| `FAULTS_EVER` | 0x8867 (I2C_FAIL_LMP, I2C_FAIL_ADS) | **0x8801** — no I²C fault bits at all |

The AIN0 signature is gone too: `AFE_VOUT` no longer tracks `VREF_MON/2` (0 against
1233). And the pin held 1232–1233 mV across 5.4 K of cooling — **no leak, no
tempco**. So the old U8 was genuinely damaged on AIN1 and AIN2, and the core
diagnosis was right even though the route to it was not.

**`AFE_VOUT = 0` is expected, not a symptom: Fab reports the CELL IS NOT
CONNECTED.** With WE/RE/CE open the TIA input floats and the output rails, so
`O2_RAW` (236 µA) is garbage from a railed stage. `T_AFE` is unavailable for the
same reason — the LMP's die temperature is read out through that same pin.
**AIN0 therefore remains unproven**, and the test that does not need the cell is
`T_AFE` once the rail is stable, or a pull-up on `/ADC_AFE_VOUT`.

Calibration note carried forward: the new part reads `VREF_MON` 2464 against a
metered ~2500, i.e. **1.4 % low** (the old one was 3–4 %). Check against a meter
before trusting an O2 calibration.

#### 3V3A dropped again minutes later — and U3 is the fault

    up 37s   VREF 65535   i2c_errs 262   ads_fail 37   faults_ever 0x8047
    up 56s   VREF 65535   i2c_errs 395   ads_fail 56

0x8047 = SETTLING · I2C_FAIL_LMP · I2C_FAIL_ADS · **VA_LOW** · HEATER_DISABLED,
counters climbing ~130 per 20 s. The same signature as 09-11 22:37. **This is
pointed at the part just fitted**: every dropout runs the ADS with DVDD up and
AVDD at zero, which remains the leading candidate for what killed the old one.

Diagnosis of U3 (TPS7A2033PDBVR), by elimination against Fab's measurements:

| fact | excludes |
|---|---|
| kick-starting by injecting 3.3 V via 3 kΩ on OUT works, repeatedly | a short on 3V3A; and the 150 Ω shutdown discharge being active, which would clamp the injection to ~157 mV |
| it failed to start even with **U8 removed** | a load-driven start-up failure |
| **IN = 5 V** | a missing input; the part can regulate once started |
| **EN = 5 V** | the "open EN joint, held off by the internal 500 kΩ pulldown" hypothesis offered at 15:xx — **withdrawn** |
| **GND fine** | the "high-resistance ground joint starves the ~25 µA quiescent return" hypothesis offered at 16:xx — **withdrawn** |
| **VEN abs max 6.5 V** (SBVS338H §5.1), VIN max 6.5 V | anything external over-stressing U3 |

All three connections correct, part commanded on, will not regulate until the
output is pre-charged, then latches and runs. **U3 has failed. Replace it**
(one is on PO-0010).

**Before fitting: ohm C8** (1 µF output cap, 118.00, y=86.72/88.28, top side).
The LDO needs a minimum output capacitance for loop stability, and an open C8
would upset the replacement too. It is not shorted — a 1.1 mA injection lifted
the rail, which a short would have swallowed — but open is still possible and
costs one probe.

#### Still open

- **The removed U8 has not been ohmed.** pin 8 (AIN1) → pin 6 (GND) and pin 5
  (AIN2) → pin 10 (AVDD), both polarities. ~890 Ω and ~2.6 kΩ would confirm the
  leaks were silicon; open would mean the rework washed away board residue and
  the part was innocent. The board's recovery alone cannot separate these,
  because R36 was replaced in the same session.
- **R36's failure is unexplained and post-dates the injection test.** The node
  balance during that test closed to 1.8 µA using R36 = 1 kΩ, pinning it at
  1 kΩ ±15 %, and R36 carried only 18 µA of the 863 µA leak. So R36 was healthy
  then and failed later — most plausibly during the hot-air rework to remove U8.
- **AIN0 unproven** until the cell is back or `T_AFE` reads.

### 16:55 — U3 replaced: the rail is clean. Board repaired; three parts changed

Read from VictoriaMetrics over LoRaWAN (the node was refusing BLE claims on its
CTRL session budget, and the telemetry path does not need the claim):

    VREF_MON  2506 mV    (target 2500)
    VA_MV     3298 mV    (a real, regulated 3.3 V)
    VIN_MV   13119 mV
    i2c_errs     0       ads_fail  0
    FAULTS  0x8801  =  SETTLING . ADC_RANGE . HEATER_DISABLED
    FAULTS_EVER 0x8801   <- no VA_LOW and no I2C_FAIL_* since boot

**The intermittency is gone with U3.** `VA_LOW` never set this boot, and the
I²C counters have stayed at zero.

**Retraction of the 16:30 calibration note.** `VREF_MON` was 2464 on Fab's
bench injection and is **2506** on the new regulator — the reference tracks
3V3A through R20/RV1/U4, exactly as the Rev A topology says. So the "new ADS
reads 1.4 % low" observation was measuring the RAIL, not the converter. At 2506
against a 2500 trim target the new part's gain is fine, which also suggests the
old part's 3–4 % error was part of its damage rather than a board property.

#### Repair summary

| part | why |
|---|---|
| **U8** ADS1119 | AIN1 leaking ~730 Ω to ground and AIN2 ~2.6 kΩ to AVDD, both powered; AIN0 returning the preceding channel's sample. All three gone with the new part, and `i2c_errs` 1132 → 0, `ads_fail_count` 141 → 0 |
| **U3** TPS7A2033 | commanded on with IN, EN and GND all measured correct, and would not regulate until the output was pre-charged; then latched and ran. Intermittent 3V3A since 09-11 22:37 |
| **R36** 1 kΩ | measured faulty after the U8 removal. The 3 kΩ injection test had pinned it at 1 kΩ ±15 % earlier the same day (node balance closing to 1.8 µA), so it failed **during** the rework, not before |

**Root cause, from the telemetry history: heat applied to dry the coating at
2026-09-11 22:24.** No over-voltage in fourteen days on any channel; the die
reached only 48 °C against a 150 °C rating; and every defect appeared in that
one minute.

#### Still open

- **AIN0 unproven.** `AFE_VOUT` reads 0 with `SETTLE_S` 633 — expected while a
  freshly reconnected cell polarises and rails the TIA. When it rises to
  ~1650 mV, AIN0 is proven. Being watched.
- **The removed U8 has still not been ohmed** (pin 8 → pin 6, pin 5 → pin 10).
  It is the only way to separate "the silicon was damaged" from "the rework
  washed away board residue", since R36 was replaced in the same session. The
  board's recovery cannot decide it.
- Whether U3's failure was caused by the same 22:24 event, or is independent.

### 17:15 — cell reconnected after 12 h open-circuit: AFE_VOUT railed, and that is expected

`SETTLE_S` reached 0 and `FAULTS` dropped to 0x8800 (SETTLING cleared,
ADC_RANGE and HEATER_DISABLED remain), but `AFE_VOUT` is still 0.

**ADC_RANGE here means the O2 conversion is PINNED — and that is itself
evidence AIN0 is healthy.** The old chip's AIN0 fault made `AFE_VOUT` mirror
`VREF_MON/2` (1253 now); a pinned rail at 0 is the new part converting AIN0 and
finding a genuinely railed LMP output.

Numbers, with the gain read from source rather than assumed — **TIA_GAIN 011 =
7 kΩ** (`lmp91000.h:40-48`; the same comment records the sizing intent, ~152 µA
at 30 % O₂ giving a 1.06 V excursion from the 1.675 V internal zero):

| quantity | value |
|---|---|
| rail-to-zero threshold | 1679 mV / 7 kΩ = **240 µA** |
| datasheet output in air | **0.1 ± 0.03 mA** (DS-0637 Issue 2) |
| therefore expected VOUT in air | 1679 − 100 µA × 7 kΩ = **979 mV** |
| measured 09-11 21:50–22:23, pre-failure | **975–981 mV** — exactly nominal |

So the cell was in spec before the failure, and is now sourcing **>240 µA**,
over 2.4× nominal.

DS-0637 Note 1 names the mechanism: *"When bias is not applied to the sensor,
it will become saturated with oxygen gas which is consumed when the bias is
reapplied. This results in a settling time which can be as long as 15
minutes."* That 15-minute figure is the origin of the firmware's `SETTLE_S`
window and describes an ordinary bias interruption. **This cell sat
open-circuit for 12 h**, so it is saturated far more deeply and has a
correspondingly larger excess to consume; `SETTLE_S` expiring says nothing
about the chemistry being finished.

**Prediction to close on:** `AFE_VOUT` lifts off 0 once the current falls below
240 µA and settles toward **~979 mV**. Landing there confirms the cell, the
LMP91000 and AIN0 in a single number. Watched with
`tech/bench/o2p_vm_watch.py` (farming `611a66a`), which reads the telemetry
over LoRaWAN and so does not need a BLE claim.
