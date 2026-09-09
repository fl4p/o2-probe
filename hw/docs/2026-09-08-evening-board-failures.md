# The evening of 2026-09-08: a short, a railed AFE, a dead reset pull-up, and a dead MCU

Bench session on the Rev A first article, roughly 20:40 to 23:50. It ends with the
STM32G071 (U2) not responding to SWD and the board out of service. This is the
record of what was measured, in order, and what each step actually proved — written
because three of the four faults were diagnosed wrongly at least once before they
were diagnosed correctly.

## Timeline of the hardware state

| time | state |
|---|---|
| ~17:39 | AFE collapses. `afe_mv` 958 → 24 mV, `ADC_RANGE` latches |
| ~20:50 | U7 pin 10 (`LMP_C1`) — pin 11 (`VREF_TRIM`) bridge found and cleared by Fab |
| 21:07 | cell OUT: `afe_mv` 1675, pad WE 1680 — INT_Z restored, A2 holds virtual ground |
| 21:13 | cell IN: `afe_mv` rails to 2495; pads CE 17 / RE 391 / WE 836 |
| 21:45 | second, different cell fitted — identical 2495 mV rail |
| 22:12 | `rawmask` firmware installed, runs correctly |
| 22:48:59 | last Modbus reply from the probe, ever |
| 23:0x | probe power-cycled — still silent |
| ~23:30 | NRST pull-up (R8) found damaged by Fab, repaired; NRST measures 3.3 V |
| 23:44 | 40 SWD attempts, `Error connecting DP: cannot read IDR` every time |
| ~23:50 | SWCLK/SWDIO/GND continuity and 3V3 confirmed good. MCU presumed dead |

## The four faults, and what each one is

**1. The pin 10–11 bridge (repaired).** `LMP_C1`–`VREF_TRIM`. Held `CELL_WE` at
2485 mV instead of the internal zero of 1662 mV, for hours, with the AFE powered.
Cleared cleanly: with no cell fitted the AFE returned to a textbook 1675 mV.

**2. The AFE rail (real, undiagnosed).** With *either* of two different cells fitted,
`afe_mv` sits at 2495 mV against a VREF of 2496 — the positive rail — and CE sits at
17 mV. `AFE-BRING-UP-POSTMORTEM.md` records the healthy signature as CE 2875 /
RE 2275 / WE 1678, and the A1 that died on 2026-09-04 sat at **130 mV**. SNAS506
specifies A1's drive only over `300 mV <= VCE <= VS - 300 mV`, so both the previous
failure and this one sit *below the specified floor*.

Two cells behaving identically rules out the cell. It does **not** distinguish a dead
A1 from a healthy A1 correctly railing into a loop that cannot close — and the
lead-crossing question (`PIN-IDENTITY-POSTMORTEM.md:445-450`, W and R must be
crossed on this board) was never resolved. **The 10 kOhm dummy test that separates
these was never run.** It still hasn't been. Size it at 10k: the same postmortem
records that 470R demands 1.27 mA against a 750 uA spec and saturates a healthy A1.

**3. The NRST pull-up (repaired).** R8, 10k 0603, `NRST` → `3V3D`, at 108.0, 102.5 on
`B.Cu`, 2.80 mm from C15 (100n, same net). Found damaged by Fab. Repaired; NRST then
measured 3.3 V. This did **not** restore the probe.

**4. The MCU (fatal).** U2 at 104.5, 86.0 on `F.Cu`. Powered, NRST high, SWD wiring
confirmed, and `cannot read IDR` on every attempt at every speed. Reading DPIDR needs
only the SWD interface and the debug power domain — not the core clock, not running
firmware — so an unreadable DP with good wiring and good power means the debug port
itself is gone.

## What the sequence suggests about cause

The probe answered every Modbus poll from 22:12 to 22:48:59 and then stopped
mid-operation, not at a boot. Whatever killed U2 happened while it was running.

Three components on one board are damaged or suspect in a single evening: U7's A1
(suspect), R8 (a passive, damaged), and U2 (dead). **A damaged passive is the
signal worth taking seriously** — ESD and logic-level overstress do not usually
destroy a 10k resistor. Mechanical or thermal damage does, and so does a
substantial overcurrent.

The leading hypothesis is therefore an **electrical overstress event during rework**,
not a subtle design margin: VIN is 10.4 V on this board, and a momentary contact
between VIN and a 3V3 node during probing or soldering would take out parts on both
the digital and analog rails at once. That is consistent with U2 and U7 both being
affected while the 3V3 rail itself still measures 3.3 V afterwards.

**This is a hypothesis, not a finding.** Nobody observed such a contact. The
alternative — that these are three independent failures on one evening — is less
likely but not excluded.

### The input stage is good, and that is itself a diagnostic result

Checked 2026-09-09 in response to "does the probe have reverse polarity
protection?". It has three independent input defences, from `J1.1 BROWN +12V`:

| part | value | role | `gen_sch.py` |
|---|---|---|---|
| F1 | 0.75 A PTC, Bel Fuse 0ZCJ 1206 (IH 0.75 A, IT 1.5 A, Vmax 16 Vdc) | overcurrent | 430 |
| D1 | SMBJ15A-13-F, `+12V_FUSED` → GND | overvoltage, 15 V standoff | 435 |
| Q1 | DMP3130L PMOS, drain to input, source to load | **reverse polarity** | 436 |
| DZ1 | 10 V Zener, `+12V_SW` → `VIN_GATE` | Q1 VGS clamp — mandatory, DMP3130L VGSS is only +/-12 V | 441 |
| D2 | SM712-02HTG, cable-side of R2/R3 | RS-485 transients | 604 |

So the following are **excluded** as causes of tonight's failures: a reversed
supply at the connector, a supply overvoltage below the PTC trip, and an RS-485
cable transient. All three are defended.

What is **not** defended is the hypothesis above. Every element in that table sits
between the connector and `+12V_SW`; they protect against energy arriving from
outside. A probe tip, slipped iron or stray wire shorting `+12V_SW` to a 3V3 node
is downstream of all of them — the PTC, the TVS and the PMOS see nothing, and
10.4 V lands on a rail whose absolute maximum is 3.6 V, exposing every part on it
at once. `+12V_SW` is distributed rather than cornered: R26 (VIN_MON divider),
RH1/RH2 (the 280R heater resistors), F3 and U1 all carry it.

The quality of the input stage therefore *narrows* the hypothesis rather than
weakening it. Two checks that would move it from hypothesis to finding:

- **Measure across F1.** Near 0 Ohm cold when healthy. A genuine rail-to-rail
  short would likely have drawn enough to trip it; a PTC that has tripped and
  recovered, or a board that browns out under load, is evidence that real current
  flowed.
- **Check D1 and Q1.** If a fault reached `+12V_SW` they may have been stressed
  too, and a degraded Q1 or a shorted TVS would compromise whatever is built on
  this board next.

## Before fitting replacement parts

1. **Verify the regulator under load before powering anything new.** If the 3V3
   supply is what went out of spec, new parts die the same way. Measured 3.3 V
   unloaded is not sufficient evidence.
2. **Fit the two Rev B items that were written up after the FIRST A1 death and never
   implemented** (`AFE-BRING-UP-POSTMORTEM.md` 3.1 and 3.2): a **CE series resistor,
   100R to 1k**, and **cell-connector ESD protection**. The CE resistor sits inside
   the feedback loop so accuracy is unaffected, and it caps what A1 can drive into a
   fault. Without it, a third LMP91000 buys a third failure.
3. **Power the board down before swapping cells.** Every cell swap this evening was
   done live, hot-plugging a charged electrochemical source into unprotected inputs.
4. **Stock is not known.** InvenTree part 511 (`LMP91000SDX/NOPB`) reports
   `in_stock 0`, `ordering 0`, zero stock items — but PO-0010 ordered 5 on
   2026-08-24 with `--no-receive` and was then auto-completed on 2026-08-31 with
   every line still at `received: 0`, so the receipt was never booked. The true
   figure is probably 5 minus what has been used, and must be counted physically.
   The same gap applies to any STM32G071 stock figure.

## Diagnostic method notes, from the errors made tonight

- **`nRESET = 0` in OpenOCD's pin report means nothing on this bench.** The Debug
  Mate attaches with SWDIO/SWCLK/GND only, no nRESET lead (`platformio.ini:87-88`),
  so that pin always reads 0. It was cited during this session as independent
  confirmation that the reset line was held low. It was not evidence of anything.
- **A fault that survives a reset at both ends is a connection or a dead part**,
  never a firmware state. Firmware re-runs from scratch on reset. Two hours went
  into firmware and relay hypotheses that a single reset had already excluded.
- **Measuring "the 3.3 V rail" somewhere is not measuring it at the part's pins.**
- **A probe in its bootloader answers only the update block**, so `--status` and not
  a normal register read is the query that distinguishes "in the loader" from
  "dead". Both were tried here; both returned nothing.

## Still open

- The AFE rail (fault 2) is undiagnosed, and now untestable until the board runs.
- `firmware-2280c31-rawalways.bin` was never installed. The probe holds `rawmask`.
- The first of two high-severity review findings against the always-publish change
  is **fixed 2026-09-09**: `finish_o2()` now leaves `O2_RAW` at its sentinel when the
  converter saturated or VREF was never measured, and `AFE_VOUT_MV` (`0x0013`) carries
  the bench diagnostic instead. This is not the fault mask withholding a value it
  distrusts — those two conditions mean the microamps have no input to be computed
  from. The measurement that made the case is now a test
  (`test_a_railed_conversion_encodes_as_a_believable_air_current`): at the VREF of
  2496 mV measured that evening, a positive-rail conversion encodes as **−117.5 uA**,
  inside the SGX cell's 70–130 uA air band with a flipped sign. The negative rail
  overflows to the sentinel on its own, because INT_Z sits at 67 % of VREF and is two
  thirds of full scale away from it — an asymmetry, not a guard, and the harmless half.
  247 native tests pass; `o2probe` builds.
- The second finding is **unfixed**: `vm_ingest.py:422/436` and `oxygen.json:678`
  publish and plot `gas_cell_ua` with no `gas_faults` predicate. The fault word is in
  the same frame, so this is a consumer-side change only. Review log at
  `~/codex-reviews/serial-path-and-raw-publish/`.
