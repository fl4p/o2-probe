/* SGX-OX-ROHS-Mini oxygen conversion.
 *
 * The cell is a biased three-electrode amperometric sensor whose response is
 * LOGARITHMIC in oxygen fraction, not linear:
 *
 *     S = I0 + K * ln(1 / (1 - C))       [DS-0637 Issue 1, "Linearity"]
 *
 * with S the cell current, I0 the cell's own zero current and C the oxygen
 * volume fraction. Inverting:
 *
 *     C = 1 - exp(-(S - I0) / K)
 *
 * An air point fixes K, because C_air is known - but only NET of the zero:
 *
 *     K = (S_air - I0) / ln(1 / (1 - 0.20946))  =  (S_air - I0) / 0.235039
 *
 * I0 is not a rounding term. DS-0637 rates the zero signal at "< 0.4 %vol O2
 * (20 C)", which at Issue 2's nominal 100 uA air point is up to 1706 nA - 12x
 * the LMP91000's internal-zero error and 150x a converter LSB
 * (../O2-CORRECTION-MODEL-BUDGET.md S2). Folding it into the air point instead
 * of subtracting it turns an offset into a slope error over the whole low-O2
 * range, which is where the compost decision lives: the budget doc's Monte
 * Carlo puts that at 0.37 vs 0.20 %O2 at the 2 %O2 point (S3, designs A vs B).
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
    /* Cell zero current in nanoamps: the reading a nitrogen point gives. Zero
     * means "no zero point taken", which is legal and is simply the old
     * behaviour - not a claim that the cell has none.
     *
     * Signed, and legitimately so in both directions: the SGX polarity
     * convention is still an open release gate (SCHEMATIC-REVIEW.md M4), and
     * the electronic offsets it competes with (LMP91000 internal-zero error,
     * ADS1119 offset) have no fixed sign either.
     *
     * NOT temperature-corrected, deliberately. DS-0637 Issue 1 publishes no
     * zero-vs-temperature figure and no bench sweep has measured one, so any
     * coefficient here would be invented - and an invented correction is worse
     * than none, because the number that comes out looks compensated. The same
     * reasoning as O2P_TEMPCO_DEFAULT below. When a zero-vs-temperature sweep
     * exists (O2-CORRECTION-MODEL-BUDGET.md S7 step 1 produces one for free),
     * this gains a coefficient of its own; until then it is a constant. */
    int32_t cal_zero_na;
    /* Fractional change in cell output per kelvin, referenced to cal_temp_c.
     * DS-0637 ISSUE 2 (28-May-2026) DOES publish a "%20 C Output vs
     * Temperature" curve for this cell, mean and +/-3 sigma, -40 to +60 C -
     * Issue 1, which this file was written against, did not. Read off the
     * plot it is roughly +0.2 %/K (about 84 % of the 20 C output at -40 C,
     * about 105 % at +60 C), which agrees with the continuum-capillary
     * expectation I ~ T^0.75 = +0.25 %/K. The default stays 0 until that curve
     * is DIGITISED rather than eyeballed: a number read off a chart by eye is
     * not a sourced value. Above 60 C it is extrapolation by explicit decision
     * (PLAN.md:211-228). See ../O2-CORRECTION-MODEL-BUDGET.md. */
    float   tempco_per_k;
    /* Temperature at which cal_air_na was taken, in 0.01 C. */
    int16_t cal_temp_c100;
} o2p_cal_t;

/* A plausible air-point window. DS-0637 Issue 2 gives 0.1 +/- 0.03 mA, so
 * 70-130 uA is the datasheet population (Issue 1 said 0.07 +/- 0.03, i.e.
 * 40-100 uA; the window below always spanned both); this is deliberately wider because the cell
 * ages downward and the TIA has headroom to 152 uA at 30 % O2. Anything
 * outside it is a wiring, bias or gas fault rather than a calibration.
 *
 * These bounds are in the header because BOTH paths that can set a
 * calibration must honour them: the automatic air-point routine, and a Modbus
 * write to CAL_AIR_NA_HI/LO. Only the first used to check. See
 * o2p_cal_air_plausible(). */
#define O2P_AIR_CAL_MIN_NA  20000
#define O2P_AIR_CAL_MAX_NA 200000

/* The ceiling for a point MEASURED in air right now, as opposed to a stored
 * constant. See o2p_calibrate_air(), the only place it applies.
 *
 * Set from the STACKED legal corner rather than from the population top: the
 * fourth review pointed out that 130 uA (Issue 2 maximum) x 1.05 (the +60 C
 * end of the temperature curve) x 1.05 (LMP91000 TIA gain accuracy, SNAS506I
 * 6.5) x 1.05 (the <5 % lifetime drift, whose SIGN DS-0637 does not restrict)
 * reaches 150.5 uA - just above the 150 uA this was first set to. The original
 * rationale claimed a cell "only loses sensitivity with age", which the
 * datasheet does not say. A guard that destroys a good calibration must not
 * treat an allowed corner as impossible, so the ceiling clears it.
 *
 * It still does the job it exists for: the 180 uA case that motivated it - a
 * wrong gas or an electrical fault silently overwriting a good calibration -
 * remains well outside. */
#define O2P_FRESH_AIR_CAL_MAX_NA 155000
_Static_assert(O2P_FRESH_AIR_CAL_MAX_NA <= O2P_AIR_CAL_MAX_NA,
               "a freshly measured air point must be no broader than a stored one");
_Static_assert(O2P_FRESH_AIR_CAL_MAX_NA > O2P_AIR_CAL_MIN_NA,
               "fresh air-point window must not be empty");

static inline bool o2p_cal_air_plausible(int32_t cell_na)
{
    return cell_na >= O2P_AIR_CAL_MIN_NA && cell_na <= O2P_AIR_CAL_MAX_NA;
}

/* A plausible zero-point window, symmetric about zero.
 *
 * DS-0637 rates the zero signal "< 0.4 %vol O2 (20 C)". Under the log law that
 * is K * ln(1/(1-0.004)) = 0.0040080 * K, i.e. 1706 nA at Issue 2's nominal
 * 100 uA air point and 2218 nA at the 130 uA top of the population. The bound
 * is set at 5000 nA - 2.9x the nominal cell's zero and 2.25x the worst
 * in-spec one (this said "about 3x the worst in-spec cell", which was the
 * nominal ratio mislabelled; 2026-09-08 review) - so that an aged or
 * marginal part is still calibratable, while the failure this bound exists to
 * catch cannot pass: 5000 nA is 1.68 %O2 equivalent, so an air point
 * mistakenly written into the zero registers, a byte-swapped word, or a cell
 * whose zero has grown into the measurement is refused rather than stored.
 *
 * SYMMETRIC because the sign is genuinely open. SCHEMATIC-REVIEW.md M4 leaves
 * the SGX polarity convention unresolved, and the electronic offsets this
 * competes with have no fixed sign either; rejecting negatives would refuse
 * the correct calibration on half the possible outcomes of that gate.
 *
 * In the header, like the air bound above, because BOTH paths that can set a
 * calibration must honour it: a Modbus write to CAL_ZERO_NA_HI/LO, and
 * o2p_calibrate_air(), which is meaningless against an implausible zero
 * because it is the zero that its air point is taken net of. */
#define O2P_ZERO_CAL_ABS_MAX_NA 5000

static inline bool o2p_cal_zero_plausible(int32_t zero_na)
{
    return zero_na >= -O2P_ZERO_CAL_ABS_MAX_NA &&
           zero_na <= O2P_ZERO_CAL_ABS_MAX_NA;
}

/* The window the NET air point (cal_air_na - cal_zero_na) can occupy if both
 * constants were individually plausible. It is derived, not a fourth magic
 * number, and the conversion re-checks it rather than trusting that whoever
 * filled the struct went through a checked path.
 *
 * This is what stops a zero at or above the air point from producing a
 * non-positive or absurdly small K. K = net / 0.235039, so net = 1 nA would
 * give K = 4.3 nA per ln-unit and convert every real current into a saturated
 * exp() - a number, not an error. Below the floor there is no conversion. */
#define O2P_NET_AIR_MIN_NA (O2P_AIR_CAL_MIN_NA - O2P_ZERO_CAL_ABS_MAX_NA)
#define O2P_NET_AIR_MAX_NA (O2P_AIR_CAL_MAX_NA + O2P_ZERO_CAL_ABS_MAX_NA)

/* Two individually plausible constants can never yield a non-positive K, so
 * the runtime net check is defence in depth rather than the only line. Assert
 * it here so that widening the zero bound past the air floor - which would
 * silently make "zero above air" reachable through the checked path - fails
 * the build instead of the field. */
_Static_assert(O2P_NET_AIR_MIN_NA > 0,
               "zero-point bound must not reach the air-point floor");

/* The three assumptions the derivation above rests on, asserted rather than
 * assumed. The 2026-09-08 review found the window itself correct but
 * under-asserted: editing ONLY O2P_AIR_CAL_MAX_NA to 9000 leaves the
 * assertion above passing while producing NET_MIN 15000 > NET_MAX 14000, so
 * every conversion returns UNEVALUABLE and the probe reports nothing at all.
 * A component-bound edit that inverts the window is a build error now. */
_Static_assert(O2P_ZERO_CAL_ABS_MAX_NA >= 0,
               "zero bound is a magnitude; a negative one inverts both edges");
_Static_assert(O2P_AIR_CAL_MIN_NA <= O2P_AIR_CAL_MAX_NA,
               "air-point window must not be inverted");
_Static_assert(O2P_NET_AIR_MIN_NA <= O2P_NET_AIR_MAX_NA,
               "derived net-air window must not be inverted");

/* Datasheet nominal for an uncalibrated cell: 0.1 mA in air (DS-0637 Issue 2,
 * 28-May-2026). The tolerance on that is +/-0.03 mA, i.e. +/-30 %, which is
 * why using it sets CAL_DEFAULT rather than passing silently.
 *
 * This was 70000 against Issue 1's 0.07 mA. The rest of the project had
 * already moved: PLAN.md's "152 uA at 30 % O2" TIA headroom figure and
 * model/config/uncalibrated_example.json's k_ref 0.425 mA are both derived
 * from 0.1 mA, so only this header and the budget doc were still on Issue 1.
 * A stale nominal here is a 43 % scale error on every uncalibrated probe. */
#define O2P_CAL_AIR_NOMINAL_NA 100000

/* Default tempco until a digitised curve or a bench characterisation replaces
 * it. DS-0637 Issue 2 publishes a curve but no coefficient, and a value
 * eyeballed off that plot is not a sourced number; 0 means "no compensation
 * applied", which is honest - an invented coefficient would be worse than
 * none, because it would look like a correction had been made. */
#define O2P_TEMPCO_DEFAULT 0.0f

/* Plausibility bounds on the two temperature-correction constants.
 *
 * READ THIS BEFORE CHANGING EITHER NUMBER. Three reviews in a row tried to
 * make a bound here carry safety it cannot carry, and each attempt was wrong
 * in a different direction:
 *
 *   - 10000 ppm/K with a near-zero gain floor: a legal config returned
 *     4.503 %vol for a true 5.000 % (round 2), and later 5.001 % from a
 *     NEGATIVE current through a binary32 corner (round 4).
 *   - A tightened runtime gain window 0.5..2.0: walked through FROM THE
 *     INSIDE at gain 1.9999, true 5 % reading 2.53 % (round 5).
 *   - 5000 ppm/K, justified as "2.5x the published curve": the sixth review
 *     showed that is not a bound at all. The firmware stores a LUMPED
 *     cell-plus-AFE coefficient (O2-CORRECTION-MODEL-BUDGET.md S3), the
 *     DS-0637 +/-3 sigma envelope alone already implies 2000-3200 ppm/K, and
 *     LMP91000 publishes NO temperature coefficient for its TIA gain - so the
 *     legitimate lumped value cannot be bounded from datasheets at all. A
 *     5000 ceiling therefore risks REFUSING a correctly characterised probe,
 *     which is worse than the failure it was meant to prevent: it blocks
 *     calibration outright, with no service override.
 *
 * THE LESSON, stated so the next person does not re-derive it: no bound here
 * makes a WRONG coefficient accurate. At any legal value a wrong alpha is
 * indistinguishable, at conversion time, from a right one. Accuracy is a
 * property of the CALIBRATION DATA.
 *
 * BUT - and the seventh review was right to call the previous revision of this
 * comment capitulation dressed as honesty - that argument justifies dropping
 * the ACCURACY claim, not dropping the bound. Widening to 10000 ppm/K with a
 * near-zero gain floor reintroduced the exact clean-fault failure round 4 had
 * already found: alpha -10000 ppm/K, Tcal -40 C, read at 55 C gives a binary32
 * gain of 0.0500000194, which passes a `> 0.05f` test and returns ~5 %O2 with
 * O2P_OK from a NEGATIVE current. Removing a guard because it cannot do
 * everything is how a guard gets switched off rather than satisfied.
 *
 * So the two reviews are adjudicated rather than alternated between:
 *
 *   - Round 6 was right that this cannot be justified as "2.5x the published
 *     curve", and right that refusing a real characterisation would be a
 *     serious failure - it would block calibration outright.
 *   - Round 7 was right that datasheet SILENCE on the LMP91000 TIA gain
 *     tempco means UNKNOWN, not arbitrarily large, and that silence licenses
 *     nothing.
 *
 * The bound is therefore PROVISIONAL and says so: 5000 ppm/K, from the cell
 * curve's ~2000 ppm/K plus a generous unmeasured-AFE allowance. It is a
 * corruption and gross-implausibility screen, NOT an accuracy certificate. If
 * a real characterisation lands above it, the correct response is to RAISE it
 * against that measurement and record the evidence - not to treat the refusal
 * as a hardware problem. Refusing is visible and recoverable; accepting a
 * wrong coefficient is silent and produces a wrong operational decision.
 *
 * What the bound does NOT do, so nobody claims it later: it does not stop a
 * plausible-but-wrong coefficient. A stored 3000 against a true 2000 over a
 * 40 K span still moves a true 5 %O2 by more than the 0.1-point decision
 * tolerance, with a clean fault word. Only calibration-quality data closes
 * that, and this firmware does not yet record any - see
 * O2-CORRECTION-MODEL-BUDGET.md section 14, which is an open decision for Fab.
 *
 * Tcal spans the cell's PUBLISHED operating range, -40 to +60 C. (It said
 * -20 C and called that the cell's rating, which was wrong; DS-0637 rates
 * -40 C, and the narrow bound would have refused a legitimate cold-chamber
 * calibration.) */
#define O2P_TEMPCO_ABS_MAX_PPM_K 5000
#define O2P_CAL_TEMP_MIN_C100    (-4000)  /* -40 C, DS-0637 operating range */
#define O2P_CAL_TEMP_MAX_C100      6000   /* +60 C */

static inline bool o2p_tempco_plausible(int32_t ppm_per_k)
{
    return ppm_per_k >= -O2P_TEMPCO_ABS_MAX_PPM_K &&
           ppm_per_k <= O2P_TEMPCO_ABS_MAX_PPM_K;
}

static inline bool o2p_cal_temp_plausible(int32_t c100)
{
    return c100 >= O2P_CAL_TEMP_MIN_C100 && c100 <= O2P_CAL_TEMP_MAX_C100;
}

/* Convert a measured cell current to oxygen volume fraction.
 *
 *   cell_na    signed cell current, nanoamps. Signed because the SGX sign
 *              convention is an open release gate (SCHEMATIC-REVIEW.md M4) and
 *              the firmware must be able to report either polarity.
 *   temp_c100  cell temperature in 0.01 C, for the tempco correction.
 *   out_c      oxygen volume fraction, written only on OK or RANGE.
 *
 * The tempco scales K, not S. Those are algebraically identical only while
 * I0 is zero; with a zero point present, applying the gain to S would give the
 * zero a temperature dependence nobody has measured
 * (../O2-CORRECTION-MODEL-BUDGET.md S6).
 */
o2p_status_t o2p_fraction_from_current(const o2p_cal_t *cal,
                                       int32_t cell_na,
                                       int16_t temp_c100,
                                       float *out_c);

/* Store an air-point reading, from which K is derived NET of the zero already
 * in `cal`. Returns false if the RAW reading is not a plausible air point, or
 * if the stored zero it would be taken net of is itself implausible - in which
 * case the calibration is REJECTED and the old one stands. A bad calibration
 * must never overwrite a good one.
 *
 * The plausibility test is on the RAW reading, not the net one: the air bound
 * describes what a cell in air produces at the ADC, and subtracting the zero
 * first would let a large bogus zero drag an out-of-range air point into the
 * window. The net is checked separately, against its own derived bounds. */
bool o2p_calibrate_air(o2p_cal_t *cal, int32_t cell_na, int16_t temp_c100);

/* %vol * 100, clamped into the Modbus u16 range, or O2P_U16_INVALID. */
uint16_t o2p_encode_percent(o2p_status_t st, float c);

#endif /* O2P_O2_H */
