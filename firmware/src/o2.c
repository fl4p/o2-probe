#include "o2.h"
#include "faults.h"

#include <math.h>
#include <stddef.h>

bool o2p_calibrate_air(o2p_cal_t *cal, int32_t cell_na, int16_t temp_c100)
{
    if (cal == NULL) {
        return false;
    }
    /* A bad calibration must never overwrite a good one, so an implausible
     * air point is rejected rather than stored. Judged on the RAW reading:
     * the bound describes what a cell in air produces, and netting the zero
     * off first would let a large bogus zero pull an out-of-range air point
     * into the window. */
    if (!o2p_cal_air_plausible(cell_na)) {
        return false;
    }
    /* The zero is a precondition of this routine, not an unrelated register:
     * K comes out as (air - zero), so an implausible zero makes an air point
     * that passed its own check produce a wrong K. Both paths that can set a
     * calibration have to honour both bounds - the lesson the air point
     * already learned the hard way (see o2.h). */
    if (!o2p_cal_zero_plausible(cal->cal_zero_na)) {
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

    /* K is derived from the air point NET of the zero. In int64 because the
     * two constants are independent int32s: a caller that filled the struct
     * without going through the checked paths could otherwise overflow the
     * subtraction, which is undefined behaviour and not a rejection. */
    int64_t net_air_na = (int64_t)cal->cal_air_na - (int64_t)cal->cal_zero_na;
    /* Defence in depth against a struct that never passed a bound. A zero at
     * or above the air point makes K non-positive; a zero just below it makes
     * K tiny, which is worse - every real current then saturates the exp() and
     * comes out as a fraction near 1.0 rather than as an error. Both are
     * refused here, so neither can reach the encoder as a number.
     *
     * The window is the one two individually plausible constants can reach
     * (o2.h), not a fresh bound: anything outside it means a constant got in
     * through a path that did not check, which is exactly the case where this
     * function cannot trust its inputs. */
    if (net_air_na < O2P_NET_AIR_MIN_NA || net_air_na > O2P_NET_AIR_MAX_NA) {
        return O2P_UNEVALUABLE;
    }

    /* Temperature correction, referenced to the calibration temperature.
     * Guard the denominator: a tempco register written badly enough to drive
     * it through zero must not produce an infinity that later compares as a
     * plausible fraction. */
    float dt = ((float)temp_c100 - (float)cal->cal_temp_c100) * 0.01f;
    float gain = 1.0f + cal->tempco_per_k * dt;
    if (!(gain > 0.05f) || !(gain < 20.0f)) {
        return O2P_UNEVALUABLE;
    }

    /* The tempco scales K, NOT S. Dividing S by the gain - which is what this
     * did while there was no I0 - is algebraically the same thing only for a
     * pure gain tempco with no offset. With a zero point present it would
     * divide the zero by the gain too, i.e. hand the zero a temperature
     * dependence that nothing has measured and that the fitted alpha does not
     * describe (../O2-CORRECTION-MODEL-BUDGET.md S6).
     *
     * The zero is subtracted UNCORRECTED for the same reason it has no
     * coefficient in o2p_cal_t: there is no measured zero-vs-temperature
     * figure for this cell, and an invented one would look like a correction.
     */
    float k = ((float)net_air_na / O2P_LN_AIR) * gain;
    /* k is positive by construction: net_air_na >= O2P_NET_AIR_MIN_NA > 0 and
     * the gain guard above bounds it away from zero. */

    float s = (float)cell_na - (float)cal->cal_zero_na;

    float ratio = s / k;
    if (!isfinite(ratio)) {
        return O2P_UNEVALUABLE;
    }

    /* C = 1 - exp(-(S-I0)/K). Below the zero current this yields a negative
     * fraction, which is physically impossible but diagnostically meaningful:
     * either the cell polarity is inverted relative to the assumed sign
     * convention - the very thing SCHEMATIC-REVIEW.md M4 leaves open - or the
     * stored zero is larger than the cell's present output, which says the
     * zero point is stale. Report it as RANGE rather than clamping it silently
     * to zero, so the bench sees it. */
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
