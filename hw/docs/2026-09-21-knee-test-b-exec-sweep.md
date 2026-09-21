# Test B: the knee law EXECUTING on the probe, at room temperature

2026-09-21, ~22:00-23:30 CEST. Fab: "do 3 now", on Test B of
`2026-09-20-testing-the-knee-above-36C.md`.

**Result: PASS.** The compiled law matched an independent host oracle at every
point from 15 to 90 C, worst |firmware - oracle| **3.776e-08** against a 5e-06
tolerance. No heat was applied and none was needed.

## What this adds to Test A

Test A read the CONSTANTS out of the image by disassembly. It cannot show the
code running, and a knee is a branch: the two anchors can be correct while the
comparison that selects between them is not. This uploads 40 bytes of Thumb
that calls the probe's own `o2p_cell_t_lnf()` at a list of temperatures and
leaves the float bits in SRAM, then reads them back with the wide peek.

**The temperatures are ARGUMENTS, not states of the probe.** The cell sat at
~21 C throughout. This is why the test is free: the law is a pure function of
an int16, and nothing about evaluating it requires the probe to be hot.

## The instruments

* `firmware/tools/exec_stubs/cell_t_lnf_sweep.s` - 40 bytes, position
  independent (`adr`, PC-relative literals), so it does not care where
  `execute_arbitrary_code()` copies it. It RETURNS its own results address
  rather than the host computing one from a .bss symbol.
* `farming/tech/chirpstack/o2p_exec_sweep.py` - the driver, over the LoRaWAN
  CTRL path (the keeper is down and the node is out of farmgw's BLE range).

Both exist only because `O2P_DEBUG_ENABLE=1`, the same debug bit that a guard
of mine nearly rejected the image over on 2026-09-20.

## Three guards, and the two that fired

**PROVENANCE, which fired and was right.** Before a single instruction is
uploaded the flash at `o2p_cell_t_lnf` is wide-peeked off the live probe and
compared with the local ELF. First run: probe `0x9B00D048`, ELF `0x0004B510`,
REFUSED. Not a law problem - a peer had reflashed the probe to **FW 0x002C**
(commit 9c5e15c) at 19:42 and the function had moved 0x10C. Without the check
the stub would have called whatever now lives at 0x0800B7E4 and its return
value would have been reported as the temperature law. It also caught a stale
claim of mine: `2026-09-21-dil-alpha-written.md` named FW 0x0028, which was
not live at any point that day (0x0029 at 15:27, 0x002B at 16:42, 0x002C from
19:42). Corrected in 05f543f.

`o2.c` and `o2.h` are byte-identical from 2b7ed0a through 9c5e15c, so the LAW
never moved - only its address did. The driver now patches the stub's call
target from the same `--symbol-addr` the guard verifies, so the address checked
and the address called cannot drift apart again.

**KNOWN-BAD CALIBRATION.** Fed the pre-knee 0.75 law, the comparison must
fail. It does, but only above the knee:

| T | knee law | 0.75 law | gain error |
|---|---|---|---|
| 30.00 C | 0.022833 | 0.022833 | **+0.00 %** |
| 36.00 C | 0.037532 | 0.037532 | **+0.00 %** |
| 45.00 C | 0.038630 | 0.059054 | +2.06 % |
| 55.00 C | 0.038591 | 0.082265 | +4.46 % |
| 75.81 C | 0.038514 | 0.128380 | +9.40 % |

Exactly 0.000e+00 below 36 C. That is the third independent demonstration that
**no bench test under 36 C can see any of this**, after the bit-for-bit
comparison and the 50-sample run of 2026-09-20.

**ORACLE CALIBRATION.** The host oracle is a bracket-and-lerp over a node
list where the firmware is a cascade of early returns - a transcription would
reproduce a transcription error faithfully and agree. Checked against the
firmware's own function compiled for the host over 1429 points: worst
disagreement **5.8e-08**, i.e. float32 noise. The measured tolerance floor,
not a guessed one.

## The sweep

```
   T (C)    firmware lnf      oracle lnf       diff      gain
   15.00    -0.015227012    -0.015226988   -2.46e-08   0.984888
   20.00    -0.002324559    -0.002324554   -5.24e-09   0.997678
   25.00     0.010359678     0.010359666   +1.29e-08   1.010414
   30.00     0.022832915     0.022832928   -1.31e-08   1.023096
   35.00     0.035102099     0.035102137   -3.78e-08   1.035725
   40.00     0.038362138     0.038362139   -1.11e-09   1.039107
   45.00     0.038629644     0.038629643   +2.22e-10   1.039385
   50.00     0.038610134     0.038610134   -1.20e-10   1.039365
   55.00     0.038590927     0.038590925   +1.74e-09   1.039345
   60.00     0.038572006     0.038572006   -5.26e-11   1.039326
   65.00     0.038553368     0.038553369   -5.55e-10   1.039306
   70.00     0.038535006     0.038535005   +1.05e-09   1.039287
   75.00     0.038516905     0.038516907   -2.22e-09   1.039268
   80.00     0.038513999     0.038514000   -5.68e-10   1.039265
   85.00     0.038513999     0.038514000   -5.68e-10   1.039265
   90.00     0.038513999     0.038514000   -5.68e-10   1.039265
```

Three properties of the running probe, observed rather than argued:

* **The plateau is real.** 45 -> 75 C moves the gain 1.039385 -> 1.039268,
  **0.011 % across 30 K**. The old law moves 6.8 % over the same span.
* **The hold above 75.81 C holds.** 80, 85 and 90 C return bit-identical
  `0.038513999` - `O2P_CELL_T_TOP_LNF` exactly, not an extrapolation that
  happens to look flat.
* **Below the knee it is the 0.75 law**, so the 2026-09-13 outdoor fit is
  preserved in the running image and not merely in the source.

The stub reported its results at `0x2000056C`, which is
`s_exec_code_aligned` (0x20000544) + 40 from the link map - the self-reported
address and the ELF agree without either being told the other.

## Four bugs found, all mine, none silent

1. Hardcoded Modbus slave **address 1**; the probe answers on **3**. A frame
   to a nonexistent slave is not refused, it is SILENCE, which reads as a dead
   link. Found by a stray reply from address 3. Now `P.DEFAULT_ADDR`.
2. `objcopy -O binary` starts at the image's lowest **LMA, 0x08004000**, not
   the 0x08000000 a flash map suggests - and at the LMA, not the VMA, because
   `.data` has a flash LMA and an SRAM VMA. Now read from the ELF.
3. `PEEK_OK` was 0; regmap.h says **NONE is 0 and OK is 1**. A successful peek
   was reported as a refusal, and the same assumption would have turned "never
   triggered" into "fine".
4. `--resend-s 75` against a node uplinking every **~128 s** (14 in 30 min,
   DR3): every exchange queued a second request and the link ran permanently
   one reply behind, answering each question with the previous question's
   answer - the failure `o2p_lorawan_cmd.py`'s own docstring records from
   2026-09-19/20. 200 s works.

## WHAT THIS DOES NOT ESTABLISH

The law computes what it is designed to compute, everywhere, including where
no bench can reach it. **Whether the two anchors are PHYSICALLY right between
41.37 and 75.81 C is untouched** - that span is still one straight line through
two measured points. Test C, the oven, is unchanged and is the only test that
can settle it.
