# Rev B proposals from the 2026-09-10 bench session

**Status: PROPOSALS, none implemented.** Written for the next agent to evaluate and, where
Fab agrees, carry into `gen_sch.py` and the routed candidate. Rev B is not ordered
(`fab/o2-probe-rev-b-*/REVB-FAB.md`: `order_ready: false`).

Already in Rev B and not repeated here: R42 CE series resistor (1k) plus TPD2E2U06 ESD,
driven RE guard (R40 → `GUARD_REPLICA`), WE/RE followers (U4), fixed reference, CE
monitor, THVD1410 /RE split from DE (`docs/2026-09-09-revb-protection.md`,
`docs/REVB-SCOPE.md`).

Session record, with telemetry, timings and the firmware changes made that day:
`~/dev/ha/farming/docs/2026-09-10-o2-probe-handoff.md`.

## What the bench showed (probe 3, Rev A, unpotted and reworked)

These are measured unless marked otherwise.

1. **The I2C bus died twice, and all four parts went with it** (LMP91000 U7, ADS1119 U8,
   TMP117 U10, SHT45 U12).
   - **First failure, 11:14:10 UTC,** in an 80 °C water bath with chamber RH 97 % and dew
     margin 0.47 K. SDA was held at 0.3 V against 4.7 kΩ, which puts the sink at about
     470 Ω. The sink was a powered part other than the MCU: SDA stayed low with NRST held,
     and read over 100 kΩ to GND unpowered. It survived reboots and 23 minutes unpowered,
     and was freed by briefly pulling SDA up through 330 Ω.
   - **Second failure:** after a heater run that took the tip to 76 °C. It survived a
     reset and came back by itself about 40 minutes later.
   - **Cause not proven.** Moisture or flux residue is the leading hypothesis.
2. **The AFE output sat on its low rail again and again** (18–126 mV, cell current
   unpublishable), both after boots and mid-run. Pad voltages measured in one episode:
   - CE 2950 / RE 2250 / WE 2050 mV. Healthy is CE 2875 / RE 2275 / WE 1678.
   - RE was held at its target, so the control loop and the cell leads were fine.
   - WE was about 380 mV high with the TIA saturated, which is about 290 µA pushed into WE.
   - **Candidates:** a leak from VREF (U7 pin 11) into C1 (pin 10) or WE (pin 12), at
     0.5 mm pitch with 0.25 mm gaps. Pins 10–11 were bridged at assembly on 09-08 and
     reworked. Or CE→WE on the board, the socket or the cell.
3. **Losing the bus blinded every heater interlock that needs a sensor.** TMP117 tip,
   SHT45 chamber and humidity all went at once, and the TMP117 ALERT cutoff only exists
   once firmware has configured it over I2C. Firmware now has an open-loop "blind" fallback
   (50 %, die below 40 °C) as a workaround. That is exactly the case hardware should make
   unnecessary.
4. **Power-on reset (cause 12) at about 16:02:35 while heating at 50 %** (~0.4 W into
   140 Ω). Cause unknown. `VIN_MON` read invalid (65535) from at least 15:42, so supply
   sag was not observable. Earlier measurement: 3.9–6.0 Ω source impedance, so continuous
   full-on heating should sag about 0.30–0.46 V, not collapse a rail (inference).

## Proposals, in priority order

### P1. A tip temperature that does not depend on I2C

Add an NTC (0402/0603, on the heated island next to U10) as a divider into a spare MCU
ADC input.

- **Why:** the heater can then regulate on a real temperature, and enforce a tip limit,
  with the I2C bus dead.
- **Firmware:** would use it as `tip_valid` whenever the TMP117 is unavailable, and as a
  cross-check whenever it is available.
- **Open:** confirm a free ADC-capable pin on the G071. `MCU_NETS` in `gen_sch.py` ~682
  lists what's used. Choose the NTC β and divider for 0–100 °C resolution; place it
  thermally on the tip island, not across the barrier.

### P2. A hardware over-temperature cutoff that needs no configuration

A fixed-trip or resistor-set thermal switch on the heater gate node, alongside the
TMP117 ALERT (which sits open-drain on that node, `heater_ctl.c` update_runaway comment).

- **Candidates, unverified:** TI TMP302 (factory trip options), TI TMP390 (resistor-set).
  Check trip accuracy, hysteresis, output type (it must be able to hold the AO3400A gate
  low through R28), supply range, and whether its trip survives a dead 3V3D.
- **Why:** the TMP117 cutoff is armed only after an I2C write, so a board that boots with
  a wet or wedged bus has no hardware limit at all.

### P3. Separate the heater's safety sensor from the analog I2C parts

Put the TMP117 (and possibly the SHT45) on the G071's second I2C, and keep the LMP91000
and ADS1119 on the first.

- **Why:** one wedged or leaking part took down the sensor the heater's safety depends on.
- **Open:** pin availability and remapping (bootloader and SWD pins must stay); the
  firmware driver change; a second pull-up pair.

### P4. I2C pull-ups R10/R11: 4.7 kΩ → 2.2 kΩ

`gen_sch.py` ~694–695.

- **Leak tolerance** to a low node, for SDA to stay above V_IH = 0.7 × 3.3 V:
  - 4.7 kΩ tolerates a leak down to 11 kΩ;
  - 2.2 kΩ down to 5.1 kΩ;
  - 1.0 kΩ down to 2.3 kΩ.
- **Sink current at 2.2 kΩ** is 1.5 mA. That is inside the LMP91000's 5 mA absolute
  maximum, the STM32G071 FT_f pins' 20 mA, and the I2C standard-mode 3 mA VOL spec.
- **What it does not fix:** a ~470 Ω sink like the one measured. This is margin against
  thin damp films, not the remedy; P6 is the remedy.

### P5. U7 (LMP91000, WSON-14 P0.5) footprint and assembly hardening

- **Solder mask:** confirm dams between every U7 signal pad, especially 10/11/12, at the
  chosen fab's minimum dam width.
- **Paste:** reduce apertures on the signal pads, and use a window-pane pattern on the
  exposed pad so solder isn't pushed into bridges. Pins 10–11 bridged on Rev A.
- **Routing:** VREF_TRIM leaves pin 11 on the side away from WE/C1 traces where possible.
  The adjacency at the pins is fixed by the package and cannot be guarded, so P6 matters.

### P6. Cleaning and coating as written process requirements

- **Assembly notes:** remove all no-clean flux residue (IPA or ultrasonic, then bake dry),
  mandatory after any rework of U7 or U8.
- **Unpotted bench articles:** conformal coat them. Keep-outs: the SHT45 membrane
  (never coat), the cell socket contacts, test points and connectors.
  - Production probes are potted (`POTTING.md`). The point is that the bench board
    behaves like the product.

### P7. Test points for today's blind spots

Rev A has TP1 CELL_WE, TP3 CELL_CE, TP4 VREF_TRIM and TP5 GUARD, but no CELL_RE. Add:
- `CELL_RE`;
- `LMP_C1`;
- `I2C_SDA` and `I2C_SCL`;
- a `3V3D` and GND pair near the AFE.

Today's pad measurements were taken on bare component pins.

### P8. Put NRST out of reach of 3V3D on J3

J3 pads 1 (3V3D), 3 (NRST) and 5 (GND) sit in one row at 1.27 mm. A manual reset means
shorting pad 3 to pad 5, one slip from shorting 3V3D.

- **Fix:** move NRST away from 3V3D, or add a dedicated, spaced reset pad pair (or a
  tactile switch footprint, DNP).

## Diagnose before committing PCB changes

- **The 16:02:35 power-on reset under 50 % heater.** Scope 12V_SW, 3V3D and 3V3A at the
  probe while stepping duty 0 → 50 → 100 %, with the node's supply in circuit.
  - If a rail dips: add bulk capacitance on `+12V_SW` near RH1/RH2 and review BOR/supervisor
    thresholds.
  - If nothing dips: the cause is elsewhere, possibly node-side.
- **`VIN_MON` reading 65535.** The probe was running a working-tree build that included
  other sessions' uncommitted firmware changes (`regmap`, `gpio_diag`), so rule out
  firmware before suspecting the divider or ADC channel.
- **The trailing 0x00 on relayed Modbus replies**, measured on FC16 (`03 10 00 35 00 01 10 25 00`)
  and attributed to RS-485 turnaround. Rev B's /RE split may remove it; check on the first
  Rev B board before keeping the host and firmware trims.

## Guard review notes for whoever implements P1–P3

- **Unevaluable input:** an NTC reading outside the plausible range (open or short) must
  count as `tip_valid = false`, never a temperature.
- **Monotonicity:** a hotter NTC or thermal-switch reading must never re-enable drive.
- **Known-bad calibration:** fault-inject the hardware cutoff (heat the tip past its trip
  with the MCU commanding full duty, and observe the gate fall). The TMP117 ALERT path has
  still never been fault-injected (`heater.h` header).
