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

/* The cell's maximum overload (DS-0637): above this the reading is not merely
 * inaccurate, the cell is outside its rated range. */
#define O2P_C_MAX 0.30f

typedef enum {
    O2P_OK = 0,
    O2P_RANGE,        /* evaluated, but outside the cell's rated window */
    O2P_UNEVALUABLE,  /* no usable number - caller MUST emit the sentinel */
} o2p_status_t;

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
} o2p_cal_t;

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

/* Convert a measured cell current to oxygen volume fraction.
 *
 *   cell_na    signed cell current, nanoamps. Signed because the SGX sign
 *              convention is an open release gate (SCHEMATIC-REVIEW.md M4) and
 *              the firmware must be able to report either polarity.
 *   temp_c100  cell temperature in 0.01 C, for the tempco correction.
 *   out_c      oxygen volume fraction, written only on OK or RANGE.
 */
o2p_status_t o2p_fraction_from_current(const o2p_cal_t *cal,
                                       int32_t cell_na,
                                       int16_t temp_c100,
                                       float *out_c);

/* Derive K from an air-point reading. Returns false if the reading is not a
 * plausible air point, in which case the calibration is REJECTED and the old
 * one stands - a bad calibration must never overwrite a good one. */
bool o2p_calibrate_air(o2p_cal_t *cal, int32_t cell_na, int16_t temp_c100);

/* %vol * 100, clamped into the Modbus u16 range, or O2P_U16_INVALID. */
uint16_t o2p_encode_percent(o2p_status_t st, float c);

#endif /* O2P_O2_H */
