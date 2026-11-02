# o2-probe Rev A first article — bench session 2026-09-04

Board: Rev A (== git HEAD). New ADS1119 (U8) and new SGX-OX-ROHS-Mini cell fitted at
session start; **LMP91000 (U7) replaced during the session** — see Outcome.

Readings taken over SWD (CMSIS-DAP / XIAO Debug Mate) unless marked DMM.
Internal zero = 0.67 x VREF. TIA = 7 kOhm unless stated.

## Outcome

U7's A1 control amplifier had failed: it could not servo even to a 0 % bias setpoint
into 1 MOhm (0.6 uA demanded against a 750 uA spec), sitting at ~130 mV. Replacing U7
restored the board. The cell and the replacement ADC were both fine.

The firmware's only complaint while A1 was dead was `O2P_F_ADC_RANGE` (bit 11,
"converter saturated or out of window") — pointing at the ADC, which was healthy.

## TIA gain sweep — proves A2 healthy and current real

`TIACN` stepped over SWD with the CPU halted; AFE_VOUT read directly from the ADS1119
against the external 2.494 V reference. A real current scales with R_TIA; an amplifier
offset would not.

| R_TIA | VOUT-INTZ | implied current | note |
|---|---|---|---|
| 2.75 k | +168.6 mV | 61.31 uA | |
| 3.5 k  | +218.4 mV | 62.39 uA | |
| 7 k    | +431.9 mV | 61.71 uA | |
| 14 k   | +822.9 mV | — | ADC clipped at full scale 2493.9 mV |
| 35 k   | +822.9 mV | — | ADC clipped |

Three valid points across a 2.5x gain range agree to 1.8 % (mean 61.8 uA). That current
was later shown to be the 470 Ohm bench dummy conducting, not a board fault.

## Pad voltages (DMM, left = CE / middle = RE / right = WE)

| condition | CE | RE | WE |
|---|---|---|---|
| cell fitted, A1 dead | 1695 / 1726 / 1717 | 1660 / 1626 / 1607 | 1678 |
| cell removed | 0 | 43 | 1678 |
| 470 Ohm dummy, A1 dead | 1673-1674 | 1673-1674 | 1678 |
| 1 MOhm dummy, A1 dead | 207 -> 130 | 214 -> 140 | 1678 |
| 1 MOhm dummy, bias sign flipped (REFCN 0xdd) | 177 | 197 | 1678 |
| 1 MOhm dummy, bias 0 % (REFCN 0xc0) | 130 | 140 | 1678 |
| **1 MOhm dummy, NEW U7** | **2875** | **2275** | **1678** |

New-U7 check against prediction: RE-WE = 597 mV vs 598.56 mV commanded (0.3 %);
CE-RE = 600 mV; CE-WE = 1197 mV = 2 x 598.5. Series chain confirmed.

## Cell, after U7 replacement

| uptime | AFE_VOUT | cell current | flags |
|---|---|---|---|
| 199 s | 21 mV | >= 239 uA (railed at 7 k) | 0x9801 |
| 382 s | 19 mV | >= 607 uA (railed at 2.75 k too) | 0x9801 |
| 1135 s | 974 mV | 99.6 uA | — |
| 1188 s | 969 mV | **100.28 uA**, `SETTLING` cleared, O2_RAW valid | 0x9000 |

Spec is 0.1 +/- 0.03 mA (70-130 uA) in air. The long rail period was initial
polarisation, not a fault — the output was above full scale at every gain, so a
decaying current was indistinguishable from a flat one.

## Register state (stable throughout, both old and new U7)

`STATUS 0x01, LOCK 0x00, TIACN 0x0c, REFCN 0xcd, MODECN 0x03`, readback `0x0ccd`.
Decode: internal 7 kOhm TIA / 10 Ohm RLOAD; external reference, 67 % internal zero,
negative bias polarity, 24 % = 598.56 mV; 3-lead amperometric, shorting FET off.
Verified bit-for-bit against SNAS506I sections 7.6.1-7.6.5.

## Other findings not yet closed

- `AFE_VOUT` reads ~77 mV lower at the ADC than a DMM at U7 pin 8. R33 is 1 k, R39 is
  DNP, and the ADS1119 draws +/-5 nA, so the expected drop is ~5 uV. Unexplained.
- AIN2 (`ADC_VA_MON`, U8 pin 5) reads 366 mV where the divider implies 1643 mV.
- `VREF_MON` is a divided copy of `VREF_TRIM` measured *against* `VREF_TRIM` as the ADC
  reference, so the firmware's "VREF = 2494 mV" is partly ratiometric. TP4 gives an
  absolute check.
