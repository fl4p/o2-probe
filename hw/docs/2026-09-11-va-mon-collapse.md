# VA_MON collapsed overnight and took the oxygen channel with it — 2026-09-11

**RESOLVED 09:15 CEST**: a surface leak on the VA_MON divider, cleaned off by
Fab with an air gun; `va_mv` recovered 1338 -> 3282 mV in one frame and the rail
was never at fault. Oxygen resumed 09:30:58 after the settle window ran out.
Diagnosis in 2, confirmation in 2.1, recovery in 2.2. Outage 7 h 54 min.

Probe 3 (Rev A, `hw_rev` 10). Window examined: 2026-09-10 02:37 → 2026-09-11 08:36
CEST, one VictoriaMetrics export, `{__name__=~"gas_.*",probe="3"}`. 1356 frames.

**Headline: the probe has published no oxygen at all since 01:37 CEST — 7 h.**
`gas_pct_vol` and `gas_o2_dry_pct` are absent in **0 of 326** frames since then,
while `gas_cell_ua` is present in all 326. The fault word is `0x0241` =
`SETTLING | VA_LOW | TEMP_OVER`. `O2P_F_VA_LOW` is in `O2P_FAULTS_INVALIDATE_O2`
(`faults.h:133`), so this is the guard working exactly as designed — on an input
that is almost certainly false.

## 1. What the rails did — measured

`O2P_VA_LOW_MV` is 3130 (`faults.h:76`).

| time (CEST) | VIN mV | **VA mV** | VREF mV | cell µA | tip °C | duty % |
|---|--:|--:|--:|--:|--:|--:|
| 09-10 22:06 | 10567 | 3286 | 2496 | 98.6 | 80.0 | 51 |
| 09-11 01:01 | 10552 | 3242 | 2462 | 88.0 | 60.6 | 0 |
| 09-11 01:07 | 10620 | **2850** | 2484 | 79.7 | 66.9 | 0 |
| 09-11 01:20 | 10650 | 2670 | 2494 | 95.3 | 51.3 | 0 |
| 09-11 01:42 | 10560 | 2320 | 2494 | 99.5 | 66.5 | 50 |
| 09-11 02:36 | 10485 | 2164 | 2490 | 101.5 | 80.0 | 84 |
| 09-11 05:34 | 10492 | 2086 | 2490 | 102.9 | 80.0 | 82 |
| 09-11 08:17 | 10500 | **2012** | 2492 | 103.6 | 80.0 | 79 |

- **VA_LOW first raised 01:07:01**, bounced between 2188 and 3098 mV until 01:36,
  then settled low and decayed smoothly to 2008 mV by 07:17. Asserted in 347 frames.
- **VIN never moved**: 10.49–10.50 V for the whole night. No upstream brownout.
- **VREF never moved**: 2490 ± 2 mV. `i2c_errs` 0, `ads_fail_count` 0,
  `lmp_readback` 0x0CCD, `gas_simulated` 0 throughout.

## 2. Why the 3V3A rail is probably FINE and VA_MON is the broken thing

Two independent instruments disagree in a way that has no physical solution.

- **VA_MON** is converted by the ADS1119 against **VREF_TRIM as its external
  reference** (`main.c:829`, `g_cyc.vref_mv`), through a 10k/10k divider,
  ×2 (`hw_caps_rev_a.h:95-96`: NUM 10000, DEN 20000). On Rev A this channel is on
  the ADS, not the MCU (`hw_caps_rev_a.h:92`, `O2P_HW_VA_MON_ON_ADS 1`).
- **VREF_MON** is converted by the ADS against its **own internal 2.048 V
  reference** (`main.c:664`, `O2P_ADS_INTERNAL_REF_MV`, `ads1119.h:50`). Different
  reference, so a genuinely separate measurement.

VREF_TRIM is the output of **U4A, a follower** (`SCHEMATIC-REVIEW.md:304`) fed from
the RV1 trimmer on `/VREF_TOP` → `/VREF_WIPER` (`AFE-BRING-UP-POSTMORTEM.md:254`),
and `/VREF_TOP` metered **2.68 V** with the rail at 3.29 V (`CELL-AFE-DEBUG.md:159`)
— a resistive tap off the analog rail. So:

> A follower cannot output 2490 mV from a 2008 mV supply. If 3V3A had really fallen
> to 2.008 V, `/VREF_TOP` would scale to 2.68 × 2.008/3.286 ≈ 1.64 V, VREF_TRIM
> would follow to ~1.5 V, and `finish_vref()` would raise `O2P_F_ADC_RANGE` for
> leaving the trim band. It did exactly that on 09-10 17:46–19:47, when VREF_MON
> read 192–336 mV and the fault word carried `0x0800`. **Overnight it did not.**

Third corroboration: the cell-current channel uses the **same converter and the
same reference** as VA_MON (`main.c:1017`, `o2p_cell_na_from_code(code,
g_cyc.vref_mv)`) and returned a smooth, physical 100.5 → 103.65 µA across six
hours. A displaced reference or a sick ADS would move that too.

**Conclusion: the ADS's VA_MON input node reads ~1004 mV where it should read
~1643 mV. The rail is not what moved.** Candidate mechanisms, in order of fit to
the board's history — **mechanism 1 was confirmed at 09:15, see 2.1**:

1. **A resistive leak from the divider midpoint to ground**, ~**7.9 kΩ**, reproduces
   1004 mV exactly (10k ∥ 7.9k = 4.40 k; 4.40/(10+4.40) = 0.3055 × 3286 = 1004).
   The same *class* of failure as the `/VREF_TRIM` ionic leak already on record for
   this board, on a different node.
2. **R24 (the top 10 k) risen to ~22.7 kΩ** gives the same ratio. A damaged part,
   but it would not drift smoothly.
3. **ADS1119 AIN2 loading the node.** Not excluded here; `ads1119-inputs-not-dead`
   covered AIN1/AIN3, not AIN2.

Mechanism 1 is favoured by the shape (smooth monotone decay, bouncing during the
first 30 min) and by the timing: the chamber sat at **RH 100.0 %, dew margin
0.20 K** at 09-10 20:47–21:17, then was freezer-soaked to −21 °C (23:21–00:39) and
brought back to 60 °C within 20 minutes. Condensation history immediately precedes
the onset. **Note this is after the conformal coating** (which went on ~20:00 on
09-10, between the VREF collapse and its 20:17 recovery), so the coating did not
prevent it — on this node.

### 2.1 CONFIRMED by cleaning — 2026-09-11 09:15 CEST

Fab air-gunned and cleaned the board. **`va_mv` jumped 1338 -> 3282 mV in a single
frame at 09:15:17**, and has held 3280-3284 mV since.

| time | va_mv | vref_mv | cell µA | faults |
|---|--:|--:|--:|---|
| 09:12:16 | 1684 | 2492 | 95.9 | `0x8841` SETTLING\|VA_LOW\|ADC_RANGE\|HEATER_DISABLED |
| 09:13:16 | 1398 | 2494 | 97.0 | `0x8841` |
| 09:14:17 | 1338 | 2490 | 99.8 | `0x8841` |
| **09:15:17** | **3282** | 2494 | 105.4 | `0x8801` — **VA_LOW cleared** |
| 09:16:18 | 3282 | 2494 | 97.2 | `0x8001` SETTLING\|HEATER_DISABLED |
| 09:23:21 | 3280 | 2492 | 100.1 | `0x8001` |

This settles the diagnosis, and it settles it in the strong direction:

- **The rail was never low.** A cleaning cannot raise an LDO's output, and VIN,
  VREF and the cell current never moved through any of it.
- **Mechanism 1 (a surface leak on the divider midpoint) is confirmed;
  mechanisms 2 and 3 are eliminated.** A drifted R24 and a damaged ADS AIN2
  channel are both unaffected by cleaning. The node returned to *exactly* its
  pre-fault value (3282 vs 3282-3286 before 01:07), which a partly-repaired part
  would not do.
- **It was surface contamination, not absorbed moisture.** An air gun and a wipe
  removed it in minutes; a leak inside the laminate would need a bake, as the
  `/VREF_TRIM` one did. ~7.9 kOhm across a 10k/10k divider is a substantial
  conductive bridge, which fits residue plus condensate over absorption.
- The `ADC_RANGE` bit in 09:11-09:15 is the cleaning itself, and it cleared with
  everything else at 09:16. VA dipping further to 1338 mV first is consistent with
  a wet wipe briefly bridging harder before it was blown dry.

**The double-mute of 3 is confirmed too, by its absence.** With `VA_LOW` gone,
`settle_s` immediately began counting DOWN — 898, 838, 777, ... 414 at 09:23 —
instead of sitting at 900. That is direct evidence that the pin was
`phase_rails()` calling `restart_settling()` on every false low reading, not a
stalled timer.

### 2.2 Oxygen returned at 09:30:58, on schedule

The settle window opened at 09:15:17 when `VA_LOW` cleared and expired 15 min
later. `gas_pct_vol` reappeared in the **first frame after it expired**:

```
09:30:24  pct_vol 21.47  cell 99.57 uA  t_chamber 22.77 C  RH 32.12 %
          va 3280  vref 2492   faults 0x8000  HEATER_DISABLED only
```

The fault word is now clean apart from `HEATER_DISABLED` (bit 15, expected — the
heater was committed OFF at 08:50). Total outage: **01:37 -> 09:30, 7 h 54 min**,
of which the last 15 min was the legitimate settle window and the rest was the
false `VA_LOW`.

That 21.47 %vol **is** the dry basis and so is directly comparable to the 20.946
truth: `gas_pct_vol` carries `O2P_REG_O2_COMP` (0x0000), which is dry basis by
construction (`regmap.h:47`) — confirmed through the codec by
`tech/mp-node/test_payload_roundtrip.py:107,149` (`comp=1847` → `pct_vol 18.47`).
`gas_o2_dry_pct` is the separate host-side backfill and was absent from this frame.

So the first post-recovery frame reads **+0.52 %vol high**. Do not quote that as a
model error yet, for one reason that has nothing to do with the rail:

- **The O2 config is at firmware defaults.** `fw_version` went 11 -> 15 -> 16 -> 17
  across 09-10/09-11 with four distinct `build_id`s, and nothing in the fault word
  says the config reverted (`o2probe-o2-config-lost-on-reflash`). Any model-error
  number taken from the frames after 09:30 must have `0x0037:16` read back first,
  or it is a measurement of the defaults, not of the commissioned probe. One frame
  is also not a spread, which is the quantity §2 of that document actually tests.

**It is not the reflash.** FW 0x11 (`build_id` 3265401358) installed at 02:18,
*after* the 01:07 onset. `fw_version` went 11 → 15 → 16 → 17 across the window,
which does mean the O2 config reverted to defaults again — see
`o2probe-o2-config-lost-on-reflash`.

## 3. One false VA_LOW mutes oxygen TWICE

Worth recording as a design coupling, because removing the bit from one mask would
not restore the channel:

1. `O2P_F_VA_LOW` ∈ `O2P_FAULTS_INVALIDATE_O2` → `pct_vol`/`o2_dry` withheld.
2. `phase_rails()` calls `restart_settling()` on every low reading
   (`main.c:313-317`, "Assume the bias went too"). So `settle_s` is pinned at
   **exactly 900 in all 326 frames** — the deadline advances with uptime forever.
   `settle_restarts` stays at 1 because `o2p_settle_restart()` only increments on a
   already-expired deadline (`sampler_logic.h:93`), so the counter does **not**
   reveal that this is happening. `settle_s` constant at its maximum is the tell.

Both are correct fail-closed behaviour. The defect is upstream, in the measurement.

## 4. The discriminating test — moot here, still worth having

**Superseded for this event by 2.1**: cleaning localized the fault without it. Kept
because the next occurrence deserves a cheaper answer than an air gun and a guess,
and because the asymmetry below is a standing waste.

### 4.1 One line of firmware, no meter needed

`phase_rails()` **already reads the same physical node with the MCU's own ADC**
(`main.c:310-312`, PA7/ADC_IN7, `board_pins.h:139-141`) and uses it only to raise
the fault; `main.c:838` then overwrites `s->va_mv` with the ADS value, so the MCU's
number is computed and thrown away. Publishing it in a spare register separates the
two hypotheses immediately:

- both converters read ~1.0 V at the node → the node really is low (leak or R24),
- MCU reads ~1.64 V, ADS reads ~1.0 V → the ADS AIN2 channel is the fault.

Bench alternative: meter `/ADC_VA_MON` and `/3V3A` directly. `/3V3A` at 3.3 V with
the node at ~1.0 V confirms the leak and localizes it to R24/R25.

## 5. Also in this window

- **`HEATER_RUNAWAY` (bit 8) re-fired at 08:29:08**, after the plateau ended: duty
  went 0 at 08:28 (tip falling 80 → 57.8) then 50 % at 08:29 with tip climbing
  57.8 → 61.9. Not new — 62 frames since 09-10 13:07 — and it is a pure annotation
  since FW 0x11. Recorded, not diagnosed; what ended the plateau at ~08:25 is not
  in the telemetry.
- **The heater ran 79–85 % duty for six hours with `VA_LOW` asserted.** Intended:
  the supply veto was removed in FW 0x11 by standing order
  (`o2probe-heater-supply-veto-removed`). Noting it so the combination is not later
  mistaken for a regression.
- The model-fit tool's guards refuse the whole 01:37-09:30 stretch on
  `settle_s != 0`, so it reports UNEVALUABLE rather than a number. Correct, and worth stating: the overnight
  run contributes **nothing** to the model-vs-truth test of
  `2026-09-11-o2-model-fit-vs-truth.md` §2, because there is no published oxygen to
  test. The cell-current analysis in that document's §10 is a separate use of the
  same rows and is conditional on §2 above.

## 6. Provenance

One export, `start=-30h`, taken 2026-09-11 08:37 CEST through the existing
`127.0.0.1:8428` tunnel. Scripts: `/tmp/ovn3.py` (windowing + regression),
`/tmp/rails.py` (rail trace). Every number above is from that export; nothing was
read from the probe and no register was written.

## 7. Fully coated — 2026-09-11, and the prediction it makes

**Fab: "the board analog circuitry is now fully coated."** Recorded as hardware
history; the coating material and its exact extent are his, not measured here.

**Dated from the telemetry at ~09:34**, 19 min after the cleaning. One frame shows
the signature of a wet intervention on the analog nodes and nothing else does:

| time | va_mv | vref_mv | afe_mv | cell µA | settle_s | faults |
|---|--:|--:|--:|--:|--:|---|
| 09:25:22 | 3280 | 2492 | 969 | 100.04 | **293** | `0x8001` SETTLING\|HEATER_DISABLED |
| **09:34:26** | **3182** | **2418** | 992 | 89.64 | **892** | `0x8a01` +TEMP_OVER+**ADC_RANGE** |
| 09:35:26 | 3284 | 2494 | 1011 | 94.14 | 893 | `0x8801` |
| 09:45:31 | 3280 | 2492 | 981 | 98.28 | 288 | `0x8001` |

VREF left its trim band for one minute, which raised `ADC_RANGE` and — on
re-entry — re-armed the settle window through the documented F6 path in
`finish_vref()` (`main.c:658-686`), throwing away the 293 s it had already
counted. That is the firmware behaving correctly on a real reference excursion.
The 09:34 timestamp is **inferred** from that signature, not stated by Fab.

### 7.1 The prediction, and what would falsify it

§2.1 concluded surface contamination on the VA_MON divider midpoint. That
conclusion now has a consequence that can be checked by waiting:

> **If the leak was surface contamination on a bare node, a fully coated analog
> section should not reproduce it.** A second VA_MON decay would falsify that
> reading and point at absorbed moisture in the laminate, or at the coating
> process itself.

The second branch is not hypothetical, and the timing is the thing to watch. The
**first** coating went on at ~20:00 on 09-10 (§7.2 of
`2026-09-11-o2-model-fit-vs-truth.md`), and VA_MON began decaying **5 h later at
01:07**. If a decay reappears roughly 5 h after 09:34 — call it ~14:30 — then the
common cause is the coating operation, not the bare copper: uncured solvent
conducting, or residue sealed *under* the coat where no air gun can reach it.
Nothing in the 09-10 data distinguishes those two, because that coating was
applied to an uncleaned board.

**One thing to confirm before trusting the prediction:** whether R24/R25 — the
10k/10k VA_MON divider, the actual suspect parts — are inside what "analog
circuitry" covers. The prediction is only as good as that extent. This is not
derivable from telemetry.

### 7.2 Post-coating baseline, for comparison against the next event

Clean, and the first quantitative read on the model since 09-08:

```
09:55:36  va 3280  vref 2492  afe 985  cell 97.70 uA  settle_s 0
          pct_vol 21.14  t_chamber 23.07 C  RH 36.69 %   faults 0x8000
```

- `va_mv` **3280-3284** across 09:15 -> 10:00, the pre-fault value, with only the
  09:34 dip. `vref_mv` 2492 +/- 2.
- Fault word is **`0x8000`, `HEATER_DISABLED` alone** — expected, heater committed
  OFF at 08:50. `settle_s` 0. Nothing is being withheld.
- `gas_pct_vol` n=11, **21.14..21.47 %vol, mean 21.315**, against the 20.946 truth:
  **+0.37 %vol mean error, 0.33 %vol spread** over ~25 min at 23 °C and RH 28-37 %.
- **That is the error of the DEFAULTS, not of the commissioned probe.** No reset or
  reflash in the window (`fw_version` 17 only, one `build_id` 3265401358, uptime
  monotone 21131 -> 27926 s), so the config is still whatever 02:18 left, and the
  tool's recovery on the 09-10/11 export returns alpha 1.000, tempco 0,
  K ~416554 nA — firmware defaults. A 25-minute room-temperature window is also
  far too narrow to test a model whose failure is across temperature; quote it as a
  baseline for the next comparison, not as a model result.
