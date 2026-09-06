/* SGX-OX-ROHS-Mini oxygen conversion.
 *
 * The cell is a biased three-electrode amperometric sensor whose response is
 * LOGARITHMIC in oxygen fraction, not linear:
 *
 *     S = K * ln(1 / (1 - C))            [DS-0637 Issue 1, "Linearity"]
 *
 * with S the cell current and C the oxygen volume fraction. Inverting:
 *
 *     C = 1 - exp(-S / K)
 *
 * A single air-point calibration fixes K, because C_air is known:
 *
 *     K = S_air / ln(1 / (1 - 0.20946))  =  S_air / 0.235063
 *
 * Everything here is deliberately tri-state. A conversion that cannot be
 * evaluated returns O2_UNEVALUABLE and NO value - it must never fall through
 * to a plausible-looking number, which is the failure mode the guard checklist
 * exists to prevent.
 */
#ifndef O2P_O2_H
#define O2P_O2_H

#include <stdbool.h>
#include <stdint.h>

/* Oxygen volume fraction of dry air. 20.946 %, the standard atmospheric
 * value; the cell's own datasheet range is 0-25 %. */
#define O2P_C_AIR 0.20946f

/* ln(1/(1-0.20946)) = 0.23503902. Precomputed so the air-point calibration is
 * one divide.
 *
 * Note for anyone porting a figure out of PLAN.md: its "0.1 % O2 = 335 nA" is
 * the LINEAR approximation 70 uA * 0.001 / 0.20946. Under the actual log law
 * the same point is 70 uA * ln(1/0.999) / 0.235039 = 298 nA, 12 % lower. Use
 * the log law for calibration, test vectors and resolution budgets alike. */
#define O2P_LN_AIR 0.23503902f

/* --- water vapour --------------------------------------------------------
 *
 * The cell responds to the PARTIAL PRESSURE of oxygen, and water vapour is a
 * gas that displaces everything else pro rata:
 *
 *     C_wet = C_dry * (P - p_w) / P,      p_w = RH/100 * p_sat(T)
 *
 * At the operating point this is not a trim. O2-HUMIDITY-CORRECTION.md 2
 * measures it: fully aerated air in a 60 C pile at 100 %RH contains 16.815
 * %vol oxygen against a dry-air 20.946, a 19.7 % relative error in the
 * direction that looks like the pile going anaerobic. It was seen on the
 * bench on 2026-09-06 at a hundredth of that size (42.3 -> 63.9 %RH moved
 * both O2_COMP and O2_RAW by -0.5 %, together, which is what makes it
 * physics rather than a processing bug).
 *
 * So O2_COMP publishes DRY BASIS - oxygen as a fraction of the water-free
 * gas, which is what the compost literature, a Draeger tube and a lab
 * instrument all mean by "O2 %", and the only basis on which a trend line
 * means respiration instead of weather. O2_RAW is untouched and still carries
 * the raw cell current.
 */

/* Total-pressure window for the assumed-pressure configuration register, hPa.
 * The BMP390 is DNP on Rev A - PRESSURE_HPA publishes 0 - so without this
 * register the correction has no P at all. The bounds are generous but real:
 * 500 hPa is ~5.5 km and 1100 hPa is above any recorded sea-level pressure,
 * so a fat-fingered write cannot install a P that quietly rescales oxygen. */
#define O2P_P_HPA_MIN 500u
#define O2P_P_HPA_MAX 1100u
/* 715 m, Steingrubenhof (48.01475N 8.03294E) - the site this probe is built
 * for, per O2-HUMIDITY-CORRECTION.md 3c. A DEPLOYMENT ELSEWHERE MUST WRITE
 * THIS REGISTER: at sea level the default is 8 % low. Calibrating in situ
 * cancels the altitude term because both the air point and the measurement
 * then share the same P; it does not cancel the +/-3.5 % of weather, which is
 * not correctable in firmware without a barometer. */
#define O2P_P_HPA_DEFAULT 930u

/* Above this the vapour correction is refused rather than extrapolated.
 *
 * Two things run out at about the same place and the limit honours both: the
 * Magnus fit's stated range ends near +60 C (psychro.h), and p_w climbs
 * towards P, which sends P/(P-p_w) towards infinity. At 80 C and saturation
 * p_w is 479 hPa, 47 % of a sea-level P - already the largest correction this
 * firmware will ever apply. The pile's own excursion ceiling is 75 C
 * (PLAN.md), which this admits, flagged by TEMP_OVER; 80 C is past anything
 * the instrument is for. */
#define O2P_VAPOUR_T_MAX_C 80.0f
/* And the hard bound on the correction itself, independent of temperature: a
 * vapour pressure at half the total is a factor of two on the answer. Beyond
 * it the number would be arithmetic, not a measurement. */
#define O2P_VAPOUR_MAX_PW_FRACTION 0.5f

/* The cell's maximum overload (DS-0637): above this the reading is not merely
 * inaccurate, the cell is outside its rated range. */
#define O2P_C_MAX 0.30f

typedef enum {
    O2P_OK = 0,
    O2P_RANGE,        /* evaluated, but outside the cell's rated window */
    O2P_UNEVALUABLE,  /* no usable number - caller MUST emit the sentinel */
} o2p_status_t;

/* The gas the cell is sitting in, for the vapour correction.
 *
 * `valid` is not decoration. RH and chamber temperature come from the SHT45,
 * which can be absent, failing, or masked for 30 s after its own heater
 * pulse - and in every one of those cases the corrected value CANNOT BE
 * COMPUTED. This struct carries that fact to the arithmetic instead of
 * letting a zeroed RH stand in for a measured one, because "0 %RH" is a
 * perfectly plausible dry-air reading that would make the correction a
 * silent no-op and publish the wet-basis number under the dry-basis name. */
typedef struct {
    float rh_pct;   /* chamber relative humidity, 0..100 % */
    float t_c;      /* chamber gas temperature, C */
    float p_hpa;    /* total pressure: the barometer, else the config value */
    bool  valid;    /* false when RH or chamber temperature is a sentinel */
} o2p_gas_t;

typedef struct {
    /* Air-point calibration: cell current in air, in nanoamps. Zero or
     * negative means "never calibrated" and the caller must set CAL_DEFAULT. */
    int32_t cal_air_na;
    /* Fractional change in cell output per kelvin, referenced to cal_temp_c.
     * SGX does not publish an output-vs-temperature curve for the Mini in
     * DS-0637 Issue 1, so this is a HOLDING REGISTER with a documented default
     * rather than a datasheet constant. Above 60 C it is extrapolation by
     * explicit decision (PLAN.md:211-228). */
    float   tempco_per_k;
    /* Temperature at which cal_air_na was taken, in 0.01 C. */
    int16_t cal_temp_c100;
    /* The oxygen volume fraction actually PRESENT when cal_air_na was
     * measured - not O2P_C_AIR.
     *
     * The air point is taken in ambient room air, which is moist, so the
     * current recorded corresponds to the WET fraction. Attributing it to dry
     * 20.946 % mis-scales K for every subsequent reading by 1-2 %
     * (O2-HUMIDITY-CORRECTION.md 3b: +1.37 % at the 23.4 C / 42.3 %RH air
     * point actually taken on this bench, +2.15 % at 25 C / 60 %RH). It is a
     * bias in K itself and correcting the measurement does not touch it - a
     * probe calibrated in a damp shed and one calibrated in a dry lab
     * genuinely disagree.
     *
     * cal_air_na stays exactly what the ADC read, so it can still be compared
     * against O2_RAW in air. THIS is the number that says what that current
     * meant. Zero or out of range means "unknown", and the conversion refuses
     * rather than assuming dry air. */
    float   air_frac;
} o2p_cal_t;

/* The air point's fraction is stored as %vol x 1000 in a u16 config register,
 * so these are its bounds. 0.15..0.25 brackets every atmosphere this cell
 * will ever be calibrated in: dry air is 0.20946 and saturated air at 60 C is
 * 0.168, both inside; nitrogen and pure oxygen are not. */
#define O2P_CAL_FRAC_MIN 0.15f
#define O2P_CAL_FRAC_MAX 0.25f

/* A plausible air-point window. DS-0637 gives 0.07 +/- 0.03 mA, so 40-100 uA
 * is the datasheet population; this is deliberately wider because the cell
 * ages downward and the TIA has headroom to 152 uA at 30 % O2. Anything
 * outside it is a wiring, bias or gas fault rather than a calibration.
 *
 * These bounds are in the header because BOTH paths that can set a
 * calibration must honour them: the automatic air-point routine, and a Modbus
 * write to CAL_AIR_NA_HI/LO. Only the first used to check. See
 * o2p_cal_air_plausible(). */
#define O2P_AIR_CAL_MIN_NA  20000
#define O2P_AIR_CAL_MAX_NA 200000

static inline bool o2p_cal_air_plausible(int32_t cell_na)
{
    return cell_na >= O2P_AIR_CAL_MIN_NA && cell_na <= O2P_AIR_CAL_MAX_NA;
}

/* Datasheet nominal for an uncalibrated cell: 0.07 mA in air (DS-0637). The
 * tolerance on that is +/-0.03 mA, i.e. +/-43 %, which is why using it sets
 * CAL_DEFAULT rather than passing silently. */
#define O2P_CAL_AIR_NOMINAL_NA 70000

/* Default tempco until a bench characterisation replaces it. SGX publishes no
 * figure for this part; 0 means "no compensation applied", which is honest -
 * an invented coefficient would be worse than none, because it would look
 * like a correction had been made. */
#define O2P_TEMPCO_DEFAULT 0.0f

/* Water-vapour partial pressure in hPa for `gas`, RH/100 * p_sat(T).
 *
 * O2P_UNEVALUABLE - and NOTHING written - if the gas is not measured, the
 * humidity is not a humidity, or the temperature is beyond
 * O2P_VAPOUR_T_MAX_C. */
o2p_status_t o2p_vapour_pressure_hpa(const o2p_gas_t *gas, float *out_pw_hpa);

/* The oxygen volume fraction actually present in fully aerated air at these
 * conditions: O2P_C_AIR * (P - p_w) / P. This is what an air-point
 * calibration is really taken against. */
o2p_status_t o2p_air_fraction(const o2p_gas_t *gas, float *out_c);

/* Wet-basis fraction -> dry-basis: C_dry = C_wet * P / (P - p_w).
 *
 * Exactly a no-op at 0 %RH, by construction rather than by a special case.
 * Monotonically increasing in RH and in temperature, and REFUSED rather than
 * folded back or clamped once p_w passes O2P_VAPOUR_MAX_PW_FRACTION of P. */
o2p_status_t o2p_dry_from_wet(const o2p_gas_t *gas, float c_wet,
                              float *out_c_dry);

/* Convert a measured cell current to oxygen volume fraction.
 *
 *   cell_na    signed cell current, nanoamps. Signed because the SGX sign
 *              convention is an open release gate (SCHEMATIC-REVIEW.md M4) and
 *              the firmware must be able to report either polarity.
 *   temp_c100  cell temperature in 0.01 C, for the tempco correction.
 *   out_c      oxygen volume fraction, written only on OK or RANGE.
 *
 * The fraction returned is WET BASIS - it is what the cell law gives, and the
 * cell law is about the gas actually at the membrane. Callers that publish
 * O2_COMP want o2p_dry_fraction_from_current() instead.
 */
o2p_status_t o2p_fraction_from_current(const o2p_cal_t *cal,
                                       int32_t cell_na,
                                       int16_t temp_c100,
                                       float *out_c);

/* The published path: cell current -> wet-basis fraction -> DRY BASIS.
 *
 * Fails closed. If the gas cannot be evaluated the result is
 * O2P_UNEVALUABLE and nothing is written - it never falls through to the
 * uncorrected number while still being called corrected, which is the exact
 * failure mode this header was written against. */
o2p_status_t o2p_dry_fraction_from_current(const o2p_cal_t *cal,
                                           int32_t cell_na,
                                           int16_t temp_c100,
                                           const o2p_gas_t *gas,
                                           float *out_c_dry);

/* Derive K from an air-point reading taken in `gas`.
 *
 * Returns false if the reading is not a plausible air point OR if the gas is
 * unevaluable, in which case the calibration is REJECTED and the old one
 * stands - a bad calibration must never overwrite a good one, and an air
 * point whose humidity is unknown is a K with a 1-2 % bias of unknown sign
 * baked in for the life of the probe. Refusing costs an operator one retry;
 * accepting costs every reading afterwards. */
bool o2p_calibrate_air(o2p_cal_t *cal, int32_t cell_na, int16_t temp_c100,
                       const o2p_gas_t *gas);

/* %vol * 100, clamped into the Modbus u16 range, or O2P_U16_INVALID. */
uint16_t o2p_encode_percent(o2p_status_t st, float c);

#endif /* O2P_O2_H */
