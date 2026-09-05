#include "o2.h"
#include "faults.h"

#include <math.h>
#include <stddef.h>

bool o2p_calibrate_air(o2p_cal_t *cal, int32_t cell_na, int16_t temp_c100)
{
    /* A bad calibration must never overwrite a good one, so an implausible
     * air point is rejected rather than stored. */
    if (!o2p_cal_air_plausible(cell_na)) {
        return false;
    }
    cal->cal_air_na = cell_na;
    cal->cal_temp_c100 = temp_c100;
    return true;
}

o2p_status_t o2p_fraction_from_current(const o2p_cal_t *cal,
                                       int32_t cell_na,
                                       int16_t temp_c100,
                                       float *out_c)
{
    if (cal == NULL || out_c == NULL) {
        return O2P_UNEVALUABLE;
    }
    /* No calibration constant at all -> nothing to divide by. The caller
     * substitutes O2P_CAL_AIR_NOMINAL_NA and raises CAL_DEFAULT; reaching here
     * with a non-positive value means even that did not happen. */
    if (cal->cal_air_na <= 0) {
        return O2P_UNEVALUABLE;
    }

    float s = (float)cell_na;

    /* Temperature correction, referenced to the calibration temperature.
     * Guard the denominator: a tempco register written badly enough to drive
     * it through zero must not produce an infinity that later compares as a
     * plausible fraction. */
    float dt = ((float)temp_c100 - (float)cal->cal_temp_c100) * 0.01f;
    float gain = 1.0f + cal->tempco_per_k * dt;
    if (!(gain > 0.05f) || !(gain < 20.0f)) {
        return O2P_UNEVALUABLE;
    }
    s /= gain;

    float k = (float)cal->cal_air_na / O2P_LN_AIR;
    /* k is positive by construction (cal_air_na > 0), so no divide guard is
     * needed beyond the check above. */

    float ratio = s / k;
    if (!isfinite(ratio)) {
        return O2P_UNEVALUABLE;
    }

    /* C = 1 - exp(-S/K). Below zero current this yields a negative fraction,
     * which is physically impossible but diagnostically meaningful: it means
     * the cell polarity is inverted relative to the assumed sign convention -
     * the very thing SCHEMATIC-REVIEW.md M4 leaves open. Report it as RANGE
     * rather than clamping it silently to zero, so the bench sees it. */
    float c = 1.0f - expf(-ratio);
    if (!isfinite(c)) {
        return O2P_UNEVALUABLE;
    }
    *out_c = c;

    if (c < 0.0f || c > O2P_C_MAX) {
        return O2P_RANGE;
    }
    return O2P_OK;
}

uint16_t o2p_encode_percent(o2p_status_t st, float c)
{
    /* RANGE is deliberately encoded as invalid, not clamped. A cell reading
     * 45 % O2 in a compost pile is a fault, and clamping it to 30.00 would
     * publish a number that looks like a real, if high, measurement. */
    if (st != O2P_OK) {
        return O2P_U16_INVALID;
    }
    float pct100 = c * 10000.0f;
    if (!(pct100 >= 0.0f)) {          /* also catches NaN */
        return O2P_U16_INVALID;
    }
    if (pct100 > (float)(O2P_U16_INVALID - 1u)) {
        return O2P_U16_INVALID;
    }
    return (uint16_t)(pct100 + 0.5f);
}
