/* STM32G0 die-temperature conversion, as pure arithmetic.
 *
 * Separated from mcu_adc.c so the calibration guard can be tested against
 * DELIBERATELY BAD calibration words. On the target that is impossible: the
 * TS_CAL words live in read-only factory OTP, so the only die this guard ever
 * sees is a good one, and a guard that has never been shown to reject
 * anything is not a guard. Everything here is integer maths over values the
 * caller has already read - no registers, no CMSIS - so env:native can hand it
 * blank OTP, an inverted slope, and the far tails.
 *
 * All limits below are from the STM32G071x8/xB datasheet DS12232 Rev 5,
 * Table 65 "TS characteristics" (p.100), read 2026-09-04.
 */
#ifndef O2P_DIE_TEMP_H
#define O2P_DIE_TEMP_H

#include <stdbool.h>
#include <stdint.h>

/* The two factory points, in 0.01 C. */
#define O2P_TS_CAL1_C100 3000
#define O2P_TS_CAL2_C100 13000

/* The calibration voltage both TS_CAL words and VREFINT_CAL were taken at. */
#define O2P_TS_CAL_VDDA_MV 3000u

/* Plausibility bounds on the factory calibration.
 *
 * 12 bits against 3.0 V is 3000/4096 = 0.7324 mV per count, so:
 *
 *   V30 = 0.742 .. 0.785 V          ->  TS_CAL1        = 1013 .. 1072 counts
 *   Avg_Slope = 2.3 .. 2.7 mV/C     ->  cal2 - cal1    =  314 ..  369 counts
 *                                       (100 K between the two points)
 *
 * The bands below are those limits with margin, because neither figure is a
 * hard production screen: Avg_Slope carries datasheet note 2, "based on
 * characterization results, not tested in production", and V30 carries note 3,
 * "measured at VDDA = 3.0 V +/-10 mV" - a tolerance worth about +/-3.5 counts
 * on TS_CAL1 by itself. So the job here is to reject OTP that is CORRUPT, not
 * to enforce datasheet compliance on a part that is merely at the edge.
 *
 * cal2 needs no band of its own: these two together already confine it to
 * 1250..1535, against a legitimate 1327..1441. */
#define O2P_TS_CAL1_MIN 950
#define O2P_TS_CAL1_MAX 1150
#define O2P_TS_SLOPE_MIN 300
#define O2P_TS_SLOPE_MAX 385

/* Die temperature in 0.01 C from the raw conversion and the two factory
 * points. Returns false - never a substituted default - if any input is
 * implausible or the result cannot be a temperature.
 *
 * cal1, cal2 : the factory TS_CAL1/TS_CAL2 words (30 C and 130 C at 3.0 V)
 * raw        : this conversion's 12-bit result
 * vdda_mv    : the supply this conversion actually ran at, from VREFINT
 */
static inline bool o2p_die_c100_from_cal(uint16_t cal1, uint16_t cal2,
                                         uint16_t raw, uint16_t vdda_mv,
                                         int16_t *out_c100)
{
    if (out_c100 == 0) {
        return false;
    }

    /* Guard the SLOPE, not just the two values. Bounding each endpoint
     * separately admits almost any scale factor - a correct cal1 with a
     * corrupted cal2 anywhere above it passes, and a 30 C die still reads
     * about 30 C while a 60 C die reads 40, or 140. The difference is the
     * quantity that scales the answer. Blank OTP fails this too: all-ones and
     * all-zeros both give a slope far outside the band. */
    int32_t slope = (int32_t)cal2 - (int32_t)cal1;
    if (cal1 < O2P_TS_CAL1_MIN || cal1 > O2P_TS_CAL1_MAX ||
        slope < O2P_TS_SLOPE_MIN || slope > O2P_TS_SLOPE_MAX) {
        return false;
    }

    /* A 12-bit right-aligned result cannot exceed 4095, and VDDA outside the
     * part's own operating range means the VREFINT read that produced it was
     * wrong - either way the scaling below would be meaningless. */
    if (raw > 4095u || vdda_mv < 1600u || vdda_mv > 3600u) {
        return false;
    }

    /* The calibration points were taken at 3.0 V and this converter runs at
     * VDDA, so scale the raw count into calibration volts before
     * interpolating between the two points. */
    int32_t scaled = ((int32_t)raw * (int32_t)vdda_mv) /
                     (int32_t)O2P_TS_CAL_VDDA_MV;
    int32_t span_c100 = O2P_TS_CAL2_C100 - O2P_TS_CAL1_C100;
    int32_t t_c100 = ((span_c100 * (scaled - (int32_t)cal1)) / slope)
                     + O2P_TS_CAL1_C100;

    /* Reject only what cannot be a temperature at all. The bounds sit OUTSIDE
     * the part's limits on purpose: TA min is -40 C and TJ max is 130 C, but
     * the error budget here is the +/-5 C tolerance on the calibration
     * temperature itself (DS12232 Table 65 note 3) plus +/-2 C max linearity,
     * so a die genuinely at -40 C may legitimately read -47 C. Clipping at the
     * rated limit would throw away good readings at the cold end. Anything
     * past these is a failed conversion, not weather. */
    if (t_c100 < -5000 || t_c100 > 14000) {
        return false;
    }
    *out_c100 = (int16_t)t_c100;
    return true;
}

#endif /* O2P_DIE_TEMP_H */
