# How to test the knee model above 36 C

FW 0x0028 is live on probe 3. Below 36.00 C the knee model returns the 0.75
law bit for bit, so bench air cannot test it - measured over all 50 samples
either side of the flash, the two laws differ by **0.000e+00**. Three tests
exist, at three different scopes. Only the third is about the physics.

## A. Is the right law COMPILED? - done 2026-09-20, no bench needed

Disassembled `o2p_cell_t_lnf` out of a build of the flashed source
(`o2.c`/`o2.h` verified identical to 2b7ed0a) and read the constants back:

| word | value | is |
|---|---|---|
| `0x3D1E492C` | 0.0386440009 | **MID_LNF, the 41.37 C anchor** |
| `0x3D1DC0DB` | 0.0385139994 | **TOP_LNF, the 75.81 C anchor** |
| `0x439307AE` | 294.06 | T_ref, 20.91 C |
| `0x00001029` | 4137 | MID_C100 |
| in-code `225<<4` | 3600 | KNEE_C100, 36.00 C |
| in-code `253<<22` | 0.75 | O2P_CELL_T_EXPONENT |

The compiler also pre-folded every segment slope, and all four reproduce by
hand: `x_knee` 0.0500427, `lnf_knee` 0.0375320 (= 0.75 x 0.0500427),
`MID_LNF - lnf_knee` 0.00111195, `x_mid - x_knee` 0.0172210,
`TOP_LNF - MID_LNF` -0.000130001, `x_top - x_mid` 0.1039096. The `>= TOP`
test compiled to `> 7580`, which is the same thing on integers.

**Proves:** the anchors and the arithmetic in the image are the measured ones.
**Does not prove:** that it executes correctly, or that the model is right.

## B. Does the flashed law EXECUTE correctly above 36 C? - possible today, no heat

The EXEC mailbox (`0x0150`-`0x0197`) uploads up to 128 bytes of Thumb code,
takes a 32-bit argument in R0, runs it under a timeout with a fault
trampoline, and returns 32 bits. A stub that unpacks `t_c100` and
`t_cal_c100` from R0, calls `o2p_cell_t_law_gain`, and returns the float bits
would let us sweep the law from 30 to 80 C **on the running image, with the
probe at room temperature**, and compare against the host curve point by point.

This facility exists only because `O2P_DEBUG_ENABLE=1` - the debug bit I
nearly rejected the image over is what makes the image testable.

Needs: the symbol address from the build that was actually flashed, and Fab's
word, because it executes uploaded code on a potted probe.

**Proves:** the law as it runs on the MCU matches the law as designed.
**Does not prove:** that the model is physically right.

## C. Is the model PHYSICALLY right in the gap? - the only real test

41.37 to 75.81 C is two anchors and a straight line in ln T. The probe's whole
service band (66-77 C in the pile) sits inside it. Nothing short of a
measurement at a known oxygen fraction and a settled elevated cell temperature
tests it.

### Two things that will NOT work

**The tip heater cannot do it.** It heats the TIP relative to the cell, not the
cell. Measured at the highest drive in the record - 38.5 % duty - the tip was
**3.05 K** above the cell. A 90 C tip ladder raises the ceiling on the tip and
leaves the cell near ambient. The 55-60 C hold needs the OVEN.

**The existing soak data cannot do it.** The 2026-09-19 run has only 9 samples
with the cell between 50 and 65 C, every one moving at **2.09 to 3.96 K/min**
against a hold criterion of 0.05. It ramped straight through the gap and
descended straight back through it.

### The run

Probe in AIR - air is the whole point, because 20.946 %vol dry is the only
oxygen fraction we know. Oven to put the CELL at a settled point in the gap.

- One hold anywhere in 45-70 C tests the straight line. **Two** (say 50 and
  65 C) test it for curvature, which one cannot.
- Hold criteria as the soak plan: >= 30 min, |dT/dt| < 0.05 K/min, settle_s 0,
  COMP_OK, faults in {0, 512}.
- Air bracket before and after at ambient, each a re-takeable window.
- An isothermal DRYING window at the hold temperature, as at the 09-19 top
  hold: that is what breaks the n/alpha degeneracy, and alpha above 40 C still
  rests on a single such window.
- Restartable, not merely watched: judge each hold on its own settled window,
  accumulate nothing across the run, keep the settle_s/COMP_OK gating.

### How sharp it is

The two laws are far apart in the gap, and a settled hold measures to ~0.07 %:

| cell T | knee predicts | old law | separation | vs noise |
|---|---|---|---|---|
| 45 C | 1.039385 | 1.060833 | 2.02 % | 29 : 1 |
| 55 C | 1.039345 | 1.085744 | 4.27 % | 61 : 1 |
| 65 C | 1.039306 | 1.110466 | 6.41 % | 92 : 1 |

So the test is not marginal. **What would falsify the model** is a measured
gain at the hold that is neither the knee's ~1.0393 nor the old law's value,
but something between - that would mean real structure in the gap that a
straight line in ln T does not capture, and the fix would be a third anchor
rather than a different exponent.

### The one hazard to write into the run log first

The dry-basis conversion REFUSES above `O2P_VAPOUR_T_MAX_C` = 80.0 C
(`o2.h:101`, enforced `o2.c:23`) and refuses by publishing the SENTINEL with
no distinguishing fault bit, because the fault word has none spare. A 45-70 C
cell is comfortably clear of it. A 90 C tip is not.
