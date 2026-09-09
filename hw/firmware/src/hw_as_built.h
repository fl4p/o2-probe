/* Where the FABRICATED board differs from the schematic. Added 2026-09-09.
 *
 * hw_contract.h is generated from ../gen_sch.py, so it is the schematic's
 * INTENT. That is the right source of truth for anything the schematic still
 * governs - move a divider and the build fails. But it cannot describe a board
 * that was fabricated from an earlier revision of that schematic and is now on
 * the bench, and it will not warn you, because from its point of view nothing
 * is wrong.
 *
 * This file is the difference, and it is hand-maintained ON PURPOSE: every
 * entry has to be checked against an as-built netlist by a human, because the
 * whole failure mode is trusting a generator that only ever saw the drawing.
 *
 * VERIFY, DO NOT ASSUME. Extract the netlist of the board in your hand:
 *     git show 16b5a606:ee/hw/o2-probe/o2-probe.kicad_pcb > /tmp/bench.kicad_pcb
 * and read the pads. Do not set any flag here from the schematic, from
 * gen_sch.py, or from a Rev B plan.
 */
#ifndef O2P_HW_AS_BUILT_H
#define O2P_HW_AS_BUILT_H

/* ---- ADS1119 AIN2/AIN3: electrode buffers, or rail monitors? ----
 *
 * hw_contract.h says AIN2 = WE_BUF and AIN3 = RE_BUF, and gen_sch.py does now
 * assign ADC_WE_BUF / ADC_RE_BUF to U8 pins 5 and 4 - that is the Rev B change
 * argued for in AFE-BRING-UP-POSTMORTEM.md 3.3.
 *
 * It has never been fabricated. On the board that exists - netlist at commit
 * 16b5a606 - those two pads carry:
 *
 *     U8 pad 5 (AIN2) -> /ADC_VA_MON     the 3V3A rail
 *     U8 pad 4 (AIN3) -> /ADC_VIN_MON    the input rail
 *
 * The nets WE_BUF, RE_BUF, ADC_WE_BUF and ADC_RE_BUF occur ZERO times in that
 * file. So `cell_bias_mv` is the difference of two rails and has never
 * measured the cell on any probe built to date. Measured 2026-09-09:
 * we_buf_mv 1638 against va_mv/2 = 1643.
 *
 * WHY THIS BECAME A BUILD FLAG RATHER THAN A COMMENT. The bias existence check
 * added 2026-09-08 judges that difference against the commanded bias and
 * raises AFE_CONFIG_MISMATCH, which is in O2P_FAULTS_INVALIDATE_O2. On
 * 2026-09-09 a fully healthy probe - loop in regulation at 598 mV, cell at
 * 99.9 uA in room air against DS-0637's 40-100 uA, all confirmed with a DMM -
 * withheld every single oxygen reading on that bit alone, because the guard
 * was judging two power rails.
 *
 * That is the guard checklist's first rule inverted: unevaluable input must
 * not silently mean OK, and it must not mean FAULT either. Both invent a
 * verdict from no evidence. The third state is what is missing, and the guard
 * already has it - BIAS_UNKNOWN, which bias_verified_recently() refuses, so
 * calibration stays gated exactly as before.
 *
 * Set to 1 only when the electrodes genuinely reach AIN2/AIN3 on the board
 * being flashed, verified against ITS netlist. Overridable per environment
 * from platformio.ini so a Rev B build does not need this file edited. */
#ifndef O2P_HW_BIAS_ADC_REACHES_ELECTRODES
#define O2P_HW_BIAS_ADC_REACHES_ELECTRODES 0
#endif

#endif /* O2P_HW_AS_BUILT_H */
