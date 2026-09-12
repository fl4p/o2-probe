# Implemented: the ADS1119 is out of the Rev B netlist

Implementation record for
[`2026-09-12-revb-decision-delete-ads1119.md`](2026-09-12-revb-decision-delete-ads1119.md)
and [`2026-09-12-revb-decision-vref-monitor.md`](2026-09-12-revb-decision-vref-monitor.md).
Those two are the decisions; this is what landed and what did not.


> ## ADOPTED — Fab, 2026-09-12: *"del u8"*
>
> Deleted **in the REF3425 form**: `VREF+` moves off VDDA. Binding spec is the
> "Final specification as adopted" section at the foot of
> [`2026-09-12-revb-decision-delete-ads1119.md`](2026-09-12-revb-decision-delete-ads1119.md);
> where it and anything else disagree, the foot wins.
>
> This document was written before the decision and describes the **VDDA form**.
> It is kept as the record of what was built and why, and amended below where
> the adopted form differs. The differences are small in parts and total in
> reasoning: the decisive argument, which nobody had computed while this was
> being written, is that with `VREF+` = VDDA the three conversions happen at
> different times on a rail with no LDO, so the worst pair couples 0.718 mV/mV
> at zero oxygen — and with `VREF+` = the reference that coupling is not
> reduced, it is **zero**.
>
> **What changed from what is described below:**
>
> - `VREF+` (pin 5) is driven from `/VREF_TRIM`, **not 3V3D**.
> - **PA5 returns to the pool.** Converting the reference against itself
>   saturates at 4095. Reference health is `VREFINT` against the 2.5 V full
>   scale, and that is a **collapse detector, not a drift monitor**.
> - `R25` 47k → **27k**, rescaling `VA_MON`; the ceiling *rises* to 6.85 V.
> - `C26` becomes **100 nF on `/VREF_TRIM`**, following pin 5 rather than
>   staying on 3V3D.
> - **`D8`**, a Schottky clamp from PA6 to AGND.
> - **No VDDA divider** — the cost I argued for hardest and got wrong.
> - The oxygen equation has **no `code_REF` term**:
>   `I = V_REF × (0.67 − code_AFE/4095) / R_TIA`, `V_REF` a compile-time
>   constant. The three-conversion form below must not be ported.
>
> Full costing and the corrections behind each line:
> [`2026-09-12-revb-cost-of-moving-vref-to-the-ref3425.md`](2026-09-12-revb-cost-of-moving-vref-to-the-ref3425.md).

## Schematic — done

`gen_sch.py` regenerates clean. **82 components** (was 89), **ERC 0/0**,
connectivity audit PASS, layout audit **0 collisions**, BOM audit unchanged
except for the parts that left.

Deleted: **U8**, its `ADS1119` library symbol, **R19** (the `ADC_DRDY` pull-up),
**C18/C19** (U8's local 3V3A and 3V3D decoupling), **R34/R35/R36/C29** (the VREF
divider and its filter), and the nets `/ADC_DRDY`, `/VREF_MON_RAW`,
`/ADC_VREF_MON`.

Kept, per the decision's correction to P0: **R33/C28, R37/C30, R38/C31**. A SAR
needs them more than a delta-sigma does.

### The pins, and why these four

Identities from **DS12232 Rev 5 Table 12**, the pin table — not the pinout
figure, per `PIN-IDENTITY-POSTMORTEM.md`. One correction worth recording
because it is an easy misread: on this package **PB0 is ADC_IN8 and PB1 is
ADC_IN9**. The `ADC_IN17`/`ADC_IN18` rows in the same table belong to the larger
packages' columns.

| net | pin | channel | I/O structure | source Z |
|---|---|---|---|---|
| `/ADC_WE_BUF` | 11, PA0 | ADC_IN0 | FT_a | 1 k (R37) |
| `/ADC_RE_BUF` | 12, PA1 | ADC_IN1 | FT_a | 1 k (R38) |
| `/VREF_TRIM` | 16, PA5 | ADC_IN5 | TT_a | U15 REF3425 output |
| `/ADC_AFE_VOUT` | 20, PB1 | ADC_IN9 | FT_a | 1 k (R33) |

**The allocation is by leakage, because leakage is the failure this revision
exists to answer.** Table 51 bounds FT_a at **±70 nA** and TT_a at **±150 nA** —
which is the opposite of the intuition that the "true analog" TT pins are the
quiet ones. So the three 1 kΩ-sourced signals take the three FT_a pins (70 µV of
offset each, 0.002 %O2), and `/VREF_TRIM` takes the one TT_a pin, because it is
the signal that cannot care: it is U15's **Kelvin-sensed REF3425 output** with
C10's 4.7 µF on the node and ±10 mA of drive (SBAS804G). 150 nA of pad leakage
and a 5 pF sample-cap kick are both nothing against that.

> **Corrected 2026-09-12 by the peer session, who caught it in my comment.** The
> first version of this reasoning said "47 Ω". That is **R31 — a Rev A part**,
> the series resistor out of the OPA2333 buffering trimpot RV1, and Rev B has
> neither. The conclusion is unchanged and in fact stronger; the stated reason
> was wrong. A vestigial `R31` exemption in `verify()`'s "no resistor on
> `VREF_TRIM`" assertion went with it — an exemption for a part that cannot
> exist is a hole with no floor.

WE and RE are additionally on **adjacent pins of identical structure**, so their
leakage largely common-modes out of the difference. That difference is the
−600 mV bias; it is the quantity, not a by-product.

### ERC: the analog MCU pins are now declared `input`

Landing `/VREF_TRIM` on PA5 raised a genuine Power-output-to-Bidirectional
violation against the REF3425's OUT_F. The fix is in the symbol, not in an
exclusion: pins 11, 12, 15, 16, 17, 18 and 20 are ADC inputs and are now typed
as inputs. An exclusion would also have muted a real GPIO driving into a rail.
(Pin 12 was in `MCU_OUTPUTS`; it was never an output, only unassigned.)

## Firmware — the headers moved, the sampler did not

### One landmine found and closed

`O2P_HW_DIV_VREF_NUM/DEN` was derived from **R34/R35 in the live schematic** and
used at `main.c:770`. Deleting those parts would have made the contract say 1:1
— and the **Rev A board on the bench**, which really does read a 47k/47k halved
copy, would have reported **1250 mV instead of 2500** and tripped its own VREF
gate. Same shape as the 2026-09-09 channel-map failure.

It moved to the per-revision caps header as `O2P_HW_DIV_VREF_MON_NUM/DEN`
(Rev A 47000/94000, Rev B 1/1). A fabricated board's scale factor is a property
of the copper, not of the drawing.

### Capability headers

`gen_hw_caps.py` **refused to emit** when U8 vanished — its `_required()` guard
working exactly as designed, and incidentally the known-bad calibration that
guard never had. Restructured rather than defaulted:

- New `O2P_HW_HAS_ADS1119`. When 0 the `O2P_HW_ADC_AIN*_NET` macros **do not
  exist**, deliberately: there is no honest net name for a channel on a chip
  that is not fitted, and an empty string would compare unequal to everything
  and read as "wired somewhere else".
- New `O2P_HW_MCU_PA0/PA1/PA5/PB1_NET`, `O2P_HW_AFE_VOUT_ON_MCU`,
  `O2P_HW_VREF_MON_DIRECT_ON_MCU`.
- `bias_ok` now reads whichever converter the revision uses. Rev B:
  **`O2P_HW_BIAS_ADC_REACHES_ELECTRODES` = 1** via PA0/PA1.
- Rev A's generated header is **unchanged in every pre-existing macro** — only
  additions. Checked line by line, because that header describes a board that
  cannot change.

`hw_contract.h`: `ADC_DRDY` left `REQUIRED_NETS`; the four analog nets joined it,
so `board_pins.h` has to bind each one to the pin the schematic assigns. The
ADS1119 address-strap check is now presence-gated rather than deleted — a future
revision that puts an ADS back must re-check its strapping, not inherit a pass.

### What does NOT exist: Rev B firmware

`ads1119.c` `#error`s on a board with no ADS1119, and `O2P_ADC_DRDY_PORT/PIN`
are gated behind `O2P_HW_HAS_ADS1119`. This is deliberate and is the opposite of
a mute: on Rev B, **PB1 is the AFE_VOUT analog input**, so a driver that
configures it as a GPIO would be configuring the oxygen channel's own pin. A red
build that names the owed work beats a green build doing that.

`o2probe_revb` is therefore **out of `default_envs`**. The env still exists and
still fails with the reason; what it no longer does is break the default build
for work that has not started. **Put it back in the same commit that lands the
port.**

Still owed, and none of it is started:

1. Port the sampler from `ads1119.c` onto `mcu_adc.c` — four new channels, and
   the −600 mV pedestal subtracted in firmware instead of arriving pre-subtracted.
2. `ADCAL` after every power-up. Not optional on Rev B: it is what removes `EO`.
3. Re-derive the VREF gate (`main.c:700`, `main.c:869`) from an MCU channel.
4. **P3 and P4, implemented earlier today, are ADS1119-specific and do not carry
   over.** The reference fallback targets the ADS's internal 2.048 V reference
   and the stuck-mux detector targets its MUX register. They remain correct and
   useful for the Rev A bench board; Rev B needs its own equivalents, and the
   MCU's SAR has different failure modes.
5. Long sampling time (160.5 cycles) on every analog channel.

## Verified

```
gen_sch.py         82 components, 289 pins
kicad-cli sch erc  0 errors, 0 warnings
audit_schematic    PASS (71 nets)
audit_layout       PASS (0 collisions, 421 items)
pio run -e o2probe SUCCESS, flash 85.8% (45684 / 53248)
pio test -e native 360/360 PASSED
pio run -e o2probe_revb   #error, by design
```

## U8's footprint: DROPPED — the one sub-question left to me

Fab left this open and recommended keeping it if board area allows, as a hedge
against the one term no datasheet settles: whether the MCU's conversions pick up
noise from its own digital activity, RS-485 and the LoRa duty cycle.

**I am dropping it, because keeping it costs the thing it hedges.** A footprint
on this board cannot be kept without keeping U8 in the schematic as a DNP — the
PCB is generated from the netlist, and a PCB-only footprint is something every
subsequent sync tries to delete. But a DNP U8 puts U8 pads back in `ASSIGNED`,
which makes `gen_hw_caps.py` derive `O2P_HW_HAS_ADS1119 = 1` and emit
`O2P_HW_ADC_AIN*_NET` for a part that is not fitted. That is precisely the
failure the per-revision capability split exists to prevent, and it is the one
that cost a healthy probe every oxygen reading on 2026-09-09.

A hedge that makes the firmware assert hardware the board does not have is not a
hedge. If the noise term turns out to matter, the answer is a shield, a sampling
change, or a different converter — not a resurrected ADS1119 whose three dead
inputs are why this revision exists.

## Not touched, and stale because of this change

**The PCB.** `o2-probe.kicad_pcb` still has U8, R19, C18, C19, R34, R35, R36 and
C29 on it, and does not have the four MCU analog routes. It was already stale
from the single-rail supply work; this widens the gap.

## Flagged, not decided

### Schottky clamps on the electrode inputs — NEW, and it belongs to this change

**DS12232 Table 60 footnote 3**, verified directly in the archived datasheet:

> *"Injecting negative current on any analog input pin significantly reduces the
> accuracy of A-to-D conversion of signal on **another** analog input. It is
> recommended to add a Schottky diode (pin to ground) to analog pins susceptible
> to receive negative current."*

This is a **cross-channel** effect, and it is created by the consolidation: with
all four channels on one converter and an electrochemical cell on long buried
leads, a negative excursion on `/ADC_WE_BUF` or `/ADC_RE_BUF` corrupts the
**oxygen** reading. The ADS1119 isolated that by being a separate part. If the
deletion proceeds, the two electrode inputs want Schottky clamps to AGND.
Pencilled in here rather than discovered later; not added, because the deletion
itself is contested.

### R32 / the U3 EN strap — VOID for Rev B, and the correction matters

Raised by the peer session against `/+5V` → `/+5V_ANALOG` with U3's `EN` tied to
its own `IN`. **Checked against the generator: U3 does not exist on Rev B.**
`R32` is now 10 Ω from `3V3D` to `3V3A` — buck output to AFE, with no regulator
on either side and therefore no `EN` pin to strap. The hypothesis cannot apply
to this netlist.

It may still explain the **Rev A bench board's** intermittent 3V3A, which does
have U3. That is a bench question, and it needs Fab and a measurement.
