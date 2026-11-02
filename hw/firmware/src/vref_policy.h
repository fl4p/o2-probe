/* What the ADC's reference IS on each revision, and what may be done with a
 * measurement of it.
 *
 * These are two different questions, and conflating them is how the VDDA
 * architecture nearly shipped. Kept pure and in a header so the host can
 * exercise both revisions.
 *
 * REV A: RATIOMETRY BY ARITHMETIC. The ADS1119's full scale is the external
 * /VREF_TRIM, and the firmware also measures /VREF_TRIM through the R34/R35
 * sense tap. Oxygen is scaled by the MEASURED value, so reference drift
 * cancels in the division. The measurement is load-bearing: without it there
 * is no scale, which is why finish_o2() refuses when vref_measured is false.
 *
 * REV B: RATIOMETRY BY WIRING. VREF+ IS the REF3425. The LMP91000's ladder and
 * the SAR's full scale are the same node, so the ratio is fixed in copper and
 * there is nothing to cancel arithmetically. The scale is therefore the
 * CONSTANT O2P_HW_VREF_MV, not a measurement.
 *
 * AND THAT DISTINCTION IS THE WHOLE POINT, so it is worth being blunt about
 * what would happen if Rev B scaled by a measurement instead. The only thing
 * on Rev B that can measure VREF+ is VREFINT, whose tempco is 50 ppm/degC and
 * whose ageing is 1000 ppm/1000 h - 8x and 40x worse than the REF3425 it would
 * be measuring. Dividing oxygen by that number would inject VREFINT's drift
 * into every reading and call it a correction: the probe would be *less*
 * accurate than reading the constant, while looking more rigorous.
 *
 * So on Rev B the VREFINT-derived reading has exactly one job: detect that the
 * reference has COLLAPSED - shorted, unpowered, or grossly wrong. It is a
 * collapse detector, not a drift monitor, and the band below is sized for that
 * and no more.
 */
#ifndef O2P_VREF_POLICY_H
#define O2P_VREF_POLICY_H

#include <stdbool.h>
#include <stdint.h>

#include "hw_caps.h"

/* Millivolts to scale a conversion by, given whatever the board was able to
 * measure of its own reference this cycle. */
static inline uint32_t o2p_vref_scale_mv(uint32_t measured_mv)
{
#if O2P_HW_VREF_IS_ADC_REFERENCE
    /* Rev B. The measurement is deliberately DISCARDED here - see above. If a
     * future change makes this return measured_mv, it will look like an
     * improvement and will quietly make the probe worse. */
    (void)measured_mv;
    return (uint32_t)O2P_HW_VREF_MV;
#else
    /* Rev A. The measurement IS the scale; that is the ratiometry. */
    return measured_mv;
#endif
}

/* True when the scale above is a constant rather than a measurement, i.e. when
 * a failed reference reading does NOT cost the board its oxygen scale. Callers
 * that refuse to report oxygen without vref_measured must consult this, or Rev
 * B would refuse for the absence of a channel it does not have. */
static inline bool o2p_vref_scale_is_constant(void)
{
#if O2P_HW_VREF_IS_ADC_REFERENCE
    return true;
#else
    return false;
#endif
}

/* Collapse band, in millivolts, for a VREFINT-derived reading of VREF+.
 *
 * +/-10 % of nominal, and deliberately that loose. The error of the MEASURING
 * instrument sets the floor: VREFINT's factory calibration, its 50 ppm/degC
 * tempco over the probe's range and its 1000 ppm/1000 h ageing together are on
 * the order of 1-2 %, so a band tighter than a few percent would report the
 * measurement's own error as a reference fault. The upper bound on usefulness
 * is that a 2.500 V reference which has moved 10 % has not drifted - it has
 * broken. Between those two is the only honest window.
 *
 * Do NOT tighten this into a trim check. A REF3425 is 6 ppm/degC and 25 ppm/
 * 1000 h; nothing here can resolve its real drift, and a band that pretends to
 * would fire on VREFINT's wander and be "fixed" by widening it back. */
/* REV B ONLY. Rev A does not define O2P_HW_VREF_MV at all, and that is
 * correct rather than an omission: Rev A has no nominal to compare against
 * because its reference is MEASURED, and its equivalent check is the trim band
 * O2P_HW_VREF_MIN_MV..MAX_MV applied to that measurement in finish_vref().
 * Defining a collapse band there would be inventing a second, looser opinion
 * about a quantity Rev A already judges properly. */
#if O2P_HW_VREF_IS_ADC_REFERENCE

#define O2P_VREF_COLLAPSE_LO_MV ((uint32_t)O2P_HW_VREF_MV - \
                                 (uint32_t)O2P_HW_VREF_MV / 10u)
#define O2P_VREF_COLLAPSE_HI_MV ((uint32_t)O2P_HW_VREF_MV + \
                                 (uint32_t)O2P_HW_VREF_MV / 10u)

static inline bool o2p_vref_collapsed(uint32_t measured_mv)
{
    return measured_mv < O2P_VREF_COLLAPSE_LO_MV ||
           measured_mv > O2P_VREF_COLLAPSE_HI_MV;
}

#endif /* O2P_HW_VREF_IS_ADC_REFERENCE */

#endif /* O2P_VREF_POLICY_H */
