#include "o2.h"
#include "faults.h"
#include "psychro.h"

#include <math.h>
#include <stddef.h>

o2p_status_t o2p_vapour_pressure_hpa(const o2p_gas_t *gas, float *out_pw_hpa)
{
    if (gas == NULL || out_pw_hpa == NULL) {
        return O2P_UNEVALUABLE;
    }
    /* Not measured this cycle. There is no number to compute from and no
     * defensible substitute: assuming dry air biases oxygen high by up to
     * 20 % at the operating point, assuming saturation biases it low. */
    if (!gas->valid) {
        return O2P_UNEVALUABLE;
    }
    if (!isfinite(gas->rh_pct) || !(gas->rh_pct >= 0.0f) ||
        !(gas->rh_pct <= 100.0f)) {
        return O2P_UNEVALUABLE;
    }
    if (!isfinite(gas->t_c) || !(gas->t_c <= O2P_VAPOUR_T_MAX_C)) {
        return O2P_UNEVALUABLE;
    }
    /* p_sat shares psychro.c's Magnus coefficients with the dew-margin
     * channel; there is deliberately no second copy of them here. */
    float es = 0.0f;
    if (!o2p_p_sat_hpa(gas->t_c, &es)) {
        return O2P_UNEVALUABLE;
    }
    float pw = es * (gas->rh_pct * 0.01f);
    if (!isfinite(pw) || !(pw >= 0.0f)) {
        return O2P_UNEVALUABLE;
    }
    *out_pw_hpa = pw;
    return O2P_OK;
}

/* Shared bound check: the total pressure, how much of it is water, and how
 * much of that the cell actually shows.
 *
 * Returns f_eff = 1 - alpha*(1 - (P - p_w)/P), the one number both directions
 * of the correction are built from - the air point's fraction and the
 * measurement's dry-basis divide. There is deliberately ONE function, so the
 * two sides cannot drift apart: an f here and an f_eff there is a gain error
 * that no calibration removes.
 *
 * alpha = 1 gives the plain gas-law factor and is bit-identical to what this
 * function computed before 2026-09-07. */
static o2p_status_t dilution_factor(const o2p_gas_t *gas, float alpha,
                                    float *out_f)
{
    /* An alpha that is not a number is not "no correction". Refuse it; the
     * caller emits the sentinel. */
    if (!isfinite(alpha) || !(alpha >= 0.0f) ||
        !(alpha <= O2P_DIL_ALPHA_MAX)) {
        return O2P_UNEVALUABLE;
    }
    float pw = 0.0f;
    o2p_status_t st = o2p_vapour_pressure_hpa(gas, &pw);
    if (st != O2P_OK) {
        return st;
    }
    /* A total pressure outside the configurable window is not a pressure.
     * Zero in particular: it is what PRESSURE_HPA publishes with the BMP390
     * DNP, and dividing by it would produce an infinity that later compares
     * as a plausible fraction. */
    float p = gas->p_hpa;
    if (!isfinite(p) || !(p >= (float)O2P_P_HPA_MIN) ||
        !(p <= (float)O2P_P_HPA_MAX)) {
        return O2P_UNEVALUABLE;
    }
    /* p_w approaching P sends P/(P - p_w) to infinity. Refuse, do not clamp:
     * a clamped correction publishes a number that is neither the wet value
     * nor the dry one, under the dry one's name. */
    if (!(pw <= p * O2P_VAPOUR_MAX_PW_FRACTION)) {
        return O2P_UNEVALUABLE;
    }
    float f = (p - pw) / p;
    if (!isfinite(f) || !(f > 0.0f) || !(f <= 1.0f)) {
        return O2P_UNEVALUABLE;
    }
    /* The cell's share of it. Checked on its own rather than trusted from f's
     * check: alpha above 1 pushes f_eff BELOW f, and at the p_w ceiling it can
     * reach zero, which would divide. */
    float f_eff = 1.0f - alpha * (1.0f - f);
    if (!isfinite(f_eff) || !(f_eff > 0.0f) || !(f_eff <= 1.0f)) {
        return O2P_UNEVALUABLE;
    }
    *out_f = f_eff;
    return O2P_OK;
}

o2p_status_t o2p_air_fraction(const o2p_gas_t *gas, float alpha, float *out_c)
{
    if (out_c == NULL) {
        return O2P_UNEVALUABLE;
    }
    float f = 0.0f;
    o2p_status_t st = dilution_factor(gas, alpha, &f);
    if (st != O2P_OK) {
        return st;
    }
    *out_c = O2P_C_AIR * f;
    return O2P_OK;
}

o2p_status_t o2p_dry_from_wet(const o2p_gas_t *gas, float c_wet, float alpha,
                              float *out_c_dry)
{
    if (out_c_dry == NULL) {
        return O2P_UNEVALUABLE;
    }
    if (!isfinite(c_wet)) {
        return O2P_UNEVALUABLE;
    }
    float f = 0.0f;
    o2p_status_t st = dilution_factor(gas, alpha, &f);
    if (st != O2P_OK) {
        return st;
    }
    /* At 0 %RH, p_w is exactly 0, f is exactly 1, f_eff is exactly 1 for any
     * alpha, and this is exactly the identity - no special case, so there is
     * no branch that can rot. */
    float c = c_wet / f;
    if (!isfinite(c)) {
        return O2P_UNEVALUABLE;
    }
    *out_c_dry = c;
    return O2P_OK;
}

bool o2p_calibrate_air(o2p_cal_t *cal, int32_t cell_na, int16_t temp_c100,
                       const o2p_gas_t *gas)
{
    if (cal == NULL) {
        return false;
    }
    /* A bad calibration must never overwrite a good one, so an implausible
     * air point is rejected rather than stored. */
    if (!o2p_cal_air_plausible(cell_na)) {
        return false;
    }
    /* Nor may an air point of unknown humidity: it would bake a 1-2 % bias of
     * unknown sign into K for the life of the probe (O2-HUMIDITY-CORRECTION
     * 3b). Refusing leaves the previous calibration standing. */
    float c_air = 0.0f;
    if (o2p_air_fraction(gas, cal->dil_alpha, &c_air) != O2P_OK) {
        return false;
    }
    if (!(c_air >= O2P_CAL_FRAC_MIN) || !(c_air <= O2P_CAL_FRAC_MAX)) {
        return false;
    }
    cal->cal_air_na = cell_na;
    cal->cal_temp_c100 = temp_c100;
    cal->air_frac = c_air;
    /* K is fixed here and carries this pressure inside it, so the pressure
     * has to be stored with it. gas->p_hpa has already passed the window
     * check inside o2p_air_fraction(), so it is a real pressure by the time
     * it gets here. Storing it is what lets a later measurement at a
     * different P be normalised instead of silently mis-scaled. */
    cal->cal_p_hpa = gas->p_hpa;
    return true;
}

/* The cell law, with the measurement referred back to the conditions K was
 * taken at.
 *
 * `p_meas_hpa` is the total pressure NOW, or 0 for "do not normalise". The
 * cell answers to pO2 = C * P, so the same fraction at a different total
 * pressure produces a proportionally different current; K is fixed once at
 * the air point and therefore belongs to P_cal. Referring the measured
 * current back by P_cal/P_meas is what makes the inverse valid at any other
 * pressure. Correcting the vapour dilution alone - which is all this firmware
 * did before 2026-09-06 - leaves this term on the answer.
 */
static o2p_status_t fraction_from_current_at_p(const o2p_cal_t *cal,
                                               int32_t cell_na,
                                               int16_t temp_c100,
                                               float p_meas_hpa,
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

    /* Pressure normalisation, referred to the calibration pressure.
     *
     * A cal_p_hpa of zero means the air point predates this field or was
     * taken with no pressure in force. Unknown is read as P_cal == P_meas -
     * no correction - rather than as an assumed atmosphere, because assuming
     * one would rescale every reading of a probe whose stored calibration
     * never claimed a pressure. On Rev A there is no barometer, so P_meas is
     * ASSUMED_P_HPA and P_cal was that same register when the air point was
     * taken: the ratio is exactly 1 and this changes no published number.
     * What it changes is that populating the BMP390 now fixes the weather
     * term instead of correcting only half of it. */
    if (cal->cal_p_hpa > 0.0f && isfinite(cal->cal_p_hpa) &&
        isfinite(p_meas_hpa) && p_meas_hpa > 0.0f) {
        float p_ratio = cal->cal_p_hpa / p_meas_hpa;
        if (!isfinite(p_ratio) || !(p_ratio > 0.0f)) {
            return O2P_UNEVALUABLE;
        }
        s *= p_ratio;
    }

    /* K is referenced to the fraction that was ACTUALLY THERE at the air
     * point, not to dry air. Using O2P_LN_AIR here - which is what this line
     * did until 2026-09-06 - attributes a moist-air current to a dry-air
     * fraction and mis-scales every subsequent reading by 1-2 %. An unknown
     * or implausible air fraction is refused rather than defaulted, because
     * defaulting it IS the bug. */
    if (!isfinite(cal->air_frac) ||
        !(cal->air_frac >= O2P_CAL_FRAC_MIN) ||
        !(cal->air_frac <= O2P_CAL_FRAC_MAX)) {
        return O2P_UNEVALUABLE;
    }
    float ln_air = logf(1.0f / (1.0f - cal->air_frac));
    if (!isfinite(ln_air) || !(ln_air > 0.0f)) {
        return O2P_UNEVALUABLE;
    }
    float k = (float)cal->cal_air_na / ln_air;
    /* k is positive by construction (cal_air_na > 0 and ln_air > 0), so no
     * divide guard is needed beyond the checks above. */

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

o2p_status_t o2p_fraction_from_current(const o2p_cal_t *cal,
                                       int32_t cell_na,
                                       int16_t temp_c100,
                                       float *out_c)
{
    /* No pressure supplied, so no pressure normalisation. This entry point is
     * the wet-basis cell law on its own; the published path goes through
     * o2p_dry_fraction_from_current(), which has the gas and does normalise. */
    return fraction_from_current_at_p(cal, cell_na, temp_c100, 0.0f, out_c);
}

o2p_status_t o2p_dry_fraction_from_current(const o2p_cal_t *cal,
                                           int32_t cell_na,
                                           int16_t temp_c100,
                                           const o2p_gas_t *gas,
                                           float *out_c_dry)
{
    if (out_c_dry == NULL) {
        return O2P_UNEVALUABLE;
    }
    /* The pressure the cell is in NOW, so the cell law can be referred back to
     * the pressure K was taken at. A gas that is not valid carries no usable
     * pressure either; o2p_dry_from_wet() below refuses it, and passing 0
     * here means the normalisation is simply not applied on the way. */
    float p_meas = (gas != NULL && gas->valid) ? gas->p_hpa : 0.0f;
    float c_wet = 0.0f;
    o2p_status_t st = fraction_from_current_at_p(cal, cell_na, temp_c100,
                                                 p_meas, &c_wet);
    if (st == O2P_UNEVALUABLE) {
        return st;
    }
    /* The gas is evaluated even when the wet fraction was already RANGE, so
     * that a probe reporting an inverted polarity or an overload still says
     * so rather than being masked by a missing SHT45 - but an unevaluable gas
     * still wins, because there is no dry-basis number to publish. */
    float c_dry = 0.0f;
    o2p_status_t vst = o2p_dry_from_wet(gas, c_wet, cal->dil_alpha, &c_dry);
    if (vst != O2P_OK) {
        return O2P_UNEVALUABLE;
    }
    *out_c_dry = c_dry;
    if (st != O2P_OK) {
        return st;
    }
    /* Correcting to dry basis can carry a wet-basis reading that was inside
     * the cell's window out of it - 25 %vol wet at 60 C saturated is 31 %vol
     * dry. The window belongs to the published number, so it is re-applied
     * here rather than inherited. */
    if (c_dry < 0.0f || c_dry > O2P_C_MAX) {
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

/* --- the last-good chamber reading -------------------------------------- */

void o2p_gas_cache_update(o2p_gas_cache_t *c, const o2p_gas_t *fresh,
                          uint32_t now_s)
{
    if (c == NULL || fresh == NULL) {
        return;
    }
    /* Only a gas that was actually MEASURED this cycle may enter the cache.
     * A masked or failed cycle carries zeroed fields, and 0 %RH at 0 C is a
     * perfectly plausible reading - caching it would turn a missing sensor
     * into a confident dry-air correction, which is the whole failure mode
     * this file is written against. */
    if (!fresh->valid) {
        return;
    }
    if (!isfinite(fresh->rh_pct) || !(fresh->rh_pct >= 0.0f) ||
        !(fresh->rh_pct <= 100.0f) || !isfinite(fresh->t_c)) {
        return;
    }
    c->rh_pct = fresh->rh_pct;
    c->t_c = fresh->t_c;
    c->taken_s = now_s;
    c->valid = true;
}

bool o2p_gas_cache_apply(const o2p_gas_cache_t *c, o2p_gas_t *gas,
                         uint32_t now_s)
{
    if (gas == NULL) {
        return false;
    }
    if (gas->valid) {
        return true;          /* a fresh reading is never overridden */
    }
    if (c == NULL || !c->valid) {
        return false;
    }
    /* Unsigned difference, so an uptime that has wrapped past 2^32 seconds
     * (136 years) cannot present a future timestamp as a fresh one. A
     * now_s BEFORE taken_s wraps to a huge age and fails the cap, which is
     * the safe direction. */
    uint32_t age = now_s - c->taken_s;
    if (age > O2P_RH_MAX_AGE_S) {
        return false;         /* unevaluable: the caller publishes the sentinel */
    }
    gas->rh_pct = c->rh_pct;
    gas->t_c = c->t_c;
    gas->valid = true;
    return true;
}
