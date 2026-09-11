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
