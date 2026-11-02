/* MCU ADC1 rail monitors: PA7 (ADC1_IN7) = 3V3A, PA6 (ADC1_IN6) = +12V_SW.
 *
 * BOTH rails are read here and NEITHER is on the ADS1119 any more. The
 * ADS1119's AIN2/AIN3 carry the buffered cell electrodes (WE_BUF/RE_BUF), not
 * rails - an older revision had 3V3A/2 and +12V_SW/12 there, and stale
 * comments describing that map outlived it by a revision. See board_pins.h's
 * VIN_MON note for what that cost.
 *
 * 3V3A must be witnessed off-converter because the ADS1119's own AVDD IS
 * 3V3A: a converter cannot report its own supply collapsing. PA7 exists so a
 * 3V3A brownout - which silently drops the LMP91000's volatile configuration
 * and therefore the cell bias, with the MCU still happily running
 * (PLAN.md:273-280) - is detectable at all.
 *
 * This ADC's reference is VREF+ = 3V3D, a different rail, so absolute volts
 * come from the factory VREFINT calibration rather than an assumed 3.3 V.
 */
#ifndef O2P_MCU_ADC_H
#define O2P_MCU_ADC_H

#include <stdbool.h>
#include <stdint.h>

/* NOT optional, and not merely for convenience. The Rev B block at the bottom
 * of this header is gated on `#if !O2P_HW_HAS_ADS1119`, and an UNDEFINED macro
 * evaluates to 0 in a preprocessor conditional -- so a translation unit that
 * reached this header without hw_caps.h would silently declare the Rev B
 * oxygen channels on a Rev A board, while mcu_adc.c (which does get the caps
 * via board_pins.h) would not define them. Declaration and definition would
 * disagree about which hardware exists. hw_caps.h #errors when the generated
 * header is missing, so including it here converts that whole class of
 * mismatch into a build failure. */
#include "hw_caps.h"

void o2p_mcu_adc_init(void);

/* Millivolts on the 3V3A rail, undoing the R24/R25 divider. Returns false if
 * the conversion or the VREFINT reference read failed - never a default. */
bool o2p_mcu_adc_read_va_mv(uint16_t *out_mv);

/* Millivolts on the +12V_SW input rail, undoing the R26/R27 divider - or the
 * board's stored ratio, VIN_DIV_X1000 (0x004B), when div_x1000 is one a write
 * would have accepted. Same contract: false on any failure, never a
 * substituted default. The caller must treat false as "supply not OK", because
 * a rail that cannot be read is not a rail that is known good - see
 * phase_rails() in main.c. */
bool o2p_mcu_adc_read_vin_mv(uint16_t div_x1000, uint16_t *out_mv);

/* VDDA/VREF+ in millivolts, derived from VREFINT. Exposed for bring-up. */
bool o2p_mcu_adc_read_vdda_mv(uint16_t *out_mv);

/* CELL_CE_DRV, the LMP91000's counter-electrode drive, undivided by R43/R44.
 *
 * This is the potentiostat's control effort. A1 moves CE until the reference
 * electrode sits at the commanded bias, so CE resting against a rail means the
 * loop is OPEN - a disconnected or high-impedance cell, or a dead A1 - while
 * the register image still reads back perfectly. It is the measurement that
 * separates "the AFE is misconfigured" from "the AFE is configured and the
 * cell is not there". */
bool o2p_mcu_adc_read_ce_mv(uint16_t *out_mv);

/* MCU die temperature in 0.01 C, from the two factory calibration points.
 *
 * This is NOT an ambient measurement and nothing in the oxygen path may
 * depend on it: it is the die, it includes the MCU's own self-heating, and
 * the part is specified to about +/-5 C. What it is good for is a second
 * opinion with no failure mode in common with the TMP117 and the SHT45 -
 * those are both on I2C1, this is on the MCU's own ADC. A tip sensor
 * reporting 80 C while the die sits at 25 C is one of them lying, and today
 * the firmware has no way to notice.
 *
 * Returns false - never a substituted default - if the calibration words are
 * implausible or either conversion fails. */
bool o2p_mcu_adc_read_die_c100(int16_t *out_c100);

/* ------------------------------------- the bias pedestal, as a leak detector
 *
 * Deliberately OUTSIDE the revision gate below, and deliberately pure. These
 * are statements about the LMP91000's ladder, not about any converter, so they
 * hold on both revisions and can be exercised on the host where the
 * register-level code cannot.
 *
 * With REFCN = 0xCD the LMP91000's internal zero is 67 % of VREF and the bias
 * step 24 %, so the two buffered legs sit at FIXED FRACTIONS of the ADC's full
 * scale by design: V_WE at 0.67 and V_RE at 0.91. Against a 12-bit converter
 * that is code 2744 and code 3727, and they are constants - not measurements.
 *
 * That makes them free evidence. A leg that walks off its constant is a leak
 * or an open on THAT pin, identified without calibration and without comparing
 * against another channel. The Rev A bench board could not do this: when three
 * of U8's four inputs died on 2026-09-11 it took five hours to see, because
 * every channel was only interpretable relative to the others and the one
 * channel still trusted was the one lying. */
/* Against 4096, NOT 4095. The SAR's LSB is VREF/4096 -- which is the same
 * 610 uV/LSB this project has used for the 2.500 V reference throughout -- so
 * the code for a voltage is V/VREF x 4096, and 4095 is merely the largest code
 * that mapping can produce. Using 4095 here instead shifts V_RE to 3726 and
 * V_WE not at all, which is exactly the kind of one-code disagreement that
 * looks like rounding noise and is actually the wrong transfer function. A
 * host test pins both numbers to this derivation. */
#define O2P_BIAS_CODE_WE 2744   /* round(0.67 x 4096) */
#define O2P_BIAS_CODE_RE 3727   /* round(0.91 x 4096) */

/* Tolerance, in codes, before a leg counts as off its pedestal.
 *
 * FALSE-POSITIVE-AVERSE ON PURPOSE. The legitimate spread is the LMP91000's
 * +/-2 % bias-step error (POTTING.md 1.1) plus the ADC's offset, which under
 * ES0418 2.6.7 can reach 50 LSB - about 1.2 % of full scale - on this board's
 * 2.500 V reference. That is ~3.2 % of budgeted error before anything is
 * wrong, so a tighter band would fire on healthy hardware. 5 % leaves margin.
 *
 * This is NOT a precision check and must not be repurposed as one: it is a
 * detector for the failure that actually happened, an input leaking hundreds
 * of codes, not a calibration gate. */
#define O2P_BIAS_CODE_TOL 205   /* 5 % of 4096 */

static inline bool o2p_bias_code_plausible(int32_t code, int32_t expected)
{
    int32_t delta = code - expected;
    if (delta < 0) {
        delta = -delta;
    }
    return delta <= O2P_BIAS_CODE_TOL;
}

/* CALFACT at either rail is ES0418 2.6.7 firing. Pure, so the host can test
 * the boundary; the register read that feeds it is below. */
static inline bool o2p_calfact_railed(uint8_t calfact)
{
    return calfact == 0x00u || calfact == 0x7Fu;
}

/* ------------------------------------------------------------------- Rev B
 *
 * The oxygen signal chain, on the MCU's own SAR because the ADS1119 is gone.
 * Compiled only where the board actually has these channels: on Rev A the same
 * nets are on U8 and PB1 is the ADS1119's DRDY, so building this there would
 * drive a converter's interrupt pin as an analog input.
 */
#if !O2P_HW_HAS_ADS1119

/* Raw 12-bit codes: no scaling, no averaging.
 *
 * RAW IS THE POINT for the two bias legs. With REFCN = 0xCD the LMP91000's
 * pedestal is fixed BY DESIGN at 67 % and 91 % of the REF3425 full scale, so
 * these read 2744 and 3727 as known constants. A leg that walks off its
 * constant is a leak or an open on that specific pin - detectable with no
 * calibration and no reference to the other channels, which is exactly the
 * per-channel evidence the Rev A bench board could not produce when three of
 * U8's four inputs died. Scaling to volts first would bury it.
 *
 * false on any conversion failure. Never a substituted default. */
bool o2p_mcu_adc_read_we_code(uint16_t *out_code);   /* PA0, ADC_IN0 */
bool o2p_mcu_adc_read_re_code(uint16_t *out_code);   /* PA1, ADC_IN1 */
bool o2p_mcu_adc_read_afe_code(uint16_t *out_code);  /* PB1, ADC_IN9 */

/* The ADC's calibration factor, as left by ADCAL at init.
 *
 * Published because it is the only way to find out whether ES0418 section
 * 2.6.7 fires on the part in hand. That erratum says that below VREF+ = 3.0 V
 * - and this board's VREF+ is the REF3425's 2.500 V - the hardware calibration
 * may fail to compensate the offset, in which case CALFACT saturates to 0x00
 * or 0x7F and EO(max) is substituted from 4.5 LSB to 50 LSB. 50 LSB is roughly
 * 0.9 %O2 at zero oxygen, worst exactly at the low-oxygen end this probe
 * exists to measure.
 *
 * So a CALFACT of 0x00 or 0x7F is the erratum firing on THIS die, and anything
 * between is the calibration having worked. That is a measurement costing one
 * register read, against the alternative of reading a silicon revision off a
 * package marking and trusting an errata table.
 *
 * Worth knowing why the register cannot be skipped: the erratum is marked
 * present on silicon rev B and absent on rev Y, AND its substituted numbers
 * are characterised at VDDA = VREF+, which this split-rail board (3.3 V and
 * 2.500 V) does not satisfy. Neither "it applies" nor "it does not" follows
 * from the datasheet. CALFACT settles it per part.
 *
 * false if the ADC is not enabled - i.e. if init's calibration timed out -
 * because a CALFACT read off a disabled ADC is not evidence of anything. */
bool o2p_mcu_adc_calfact(uint8_t *out_calfact);

/* True when CALFACT sits at a rail, i.e. ES0418 2.6.7 is firing on this die.
 * False also when CALFACT could not be read, so a caller that treats this as
 * "all clear" is wrong; pair it with o2p_mcu_adc_calfact() when the
 * distinction between "fine" and "unknown" matters. */
bool o2p_mcu_adc_offset_erratum_active(void);

#endif /* !O2P_HW_HAS_ADS1119 */

#endif /* O2P_MCU_ADC_H */
