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
 * for, per O2-HUMIDITY-CORRECTION.md 3c.
 *
 * "8 % low at sea level" is what this comment used to say and it is WRONG.
 * The 8.2 % is the altitude difference in absolute pressure; it is not the
 * error in the published number, because P appears twice - once in the air
 * point's own fraction and once in the measurement's dilution - and the two
 * uses partially cancel. Calibrating and deploying at sea level with this
 * default left in place gives about +2.10 % relative at a 25 C/50 %RH air
 * point read out at 60 C/100 %RH, not +8 %. Getting it right still matters,
 * and a DEPLOYMENT ELSEWHERE SHOULD WRITE THIS REGISTER - but the number to
 * quote is 2 %, and the residual depends on both conditions.
 *
 * What in-situ calibration cancels is the SYSTEMATIC part: with CAL_P_HPA
 * recorded, K carries the pressure it was taken at and the measurement is
 * normalised by P_cal/P_meas, so an assumed P that is wrong by a constant
 * cancels exactly. What it cannot cancel is the +/-3.5 % of WEATHER, which
 * moves P_meas after the air point was taken - about -4.17 %/+4.14 % relative
 * on the published number at 60 C/100 %RH. That is not correctable in
 * firmware without a barometer; with one, the CAL_P_HPA normalisation is
 * what corrects it. */
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
    /* How much of the modelled water-vapour dilution the CELL ACTUALLY SHOWS.
     *
     * The gas law is not in question: water vapour displaces oxygen pro rata,
     * and at 60 C saturated that is a 20 % effect. What the 2026-09-07 sweep
     * measured is that this cell's CURRENT moves only a fraction of it -
     * alpha = 0.402 +/- 0.046 over an 18.2 hPa isothermal dry-down
     * (O2-HUMIDITY-CORRECTION.md 15.3 and 15.9). That is the value the FIRMWARE consumes. The sweep's regression is on ln(current)
     * and yields 0.453 in that domain; the firmware applies alpha to
     * CONCENTRATION and then goes through the cell's log law, whose local gain
     * d ln S/d ln C = C/((1-C)L(C)) is 1.1273 at 20.946 %vol. 0.453/1.1273 =
     * 0.402. Flashing the log-domain number would overstate the correction by
     * 12 %, about +0.17 pp at pile conditions. A capillary cell is a diffusion
     * barrier, not an open port, so its transport partly re-references
     * itself to the wet gas; whatever the mechanism, the number is what the
     * cell does.
     *
     * So the dilution factor the CORRECTION uses is not f = (P-p_w)/P but
     *
     *     f_eff = 1 - alpha * (1 - f)
     *
     * and the same f_eff appears on both sides - in the air point's fraction
     * and in the measurement - because it describes the cell, not the gas.
     * Using f there and f_eff here, or the reverse, would leave a residual
     * that no calibration can remove.
     *
     * alpha = 1 is the naive full correction and is what this firmware did
     * until 2026-09-07. It is NOT the safe default: at pile conditions the
     * threshold below which full correction is worse than no correction is
     * alpha = 1/(1+f) = 0.545 - a threshold derived from f_eff, so it is
     * already in THIS domain - and this cell is 3.1 sigma under it (15.4).
     * The default stays 1.0 all the same, because 0.402 is one cell's
     * measured coefficient and a firmware default is a claim about every
     * cell. Write DIL_ALPHA (0x0045) per probe. */
    float   dil_alpha;
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
    /* The TOTAL PRESSURE in force when cal_air_na was measured, hPa.
     *
     * The cell answers to pO2 = C * P, so its current at a given fraction is
     * proportional to total pressure. K is fixed once, at the air point, and
     * therefore carries that pressure inside it: a measurement made at a
     * different P must have its current normalised by P_cal/P_meas before the
     * inverse, or the pressure difference lands on the answer as gain error.
     * The vapour-dilution factor uses P as well, but correcting only that
     * leaves this one uncorrected - which was the state of this firmware
     * until 2026-09-06.
     *
     * ZERO MEANS UNKNOWN, and unknown is read as P_cal == P_meas, i.e. no
     * normalisation. That is not a guess dressed as a measurement: with no
     * barometer fitted, P_meas is ASSUMED_P_HPA and P_cal was the same
     * register, so the ratio is exactly 1 and the branch changes no number on
     * Rev A. It is the structure that lets a populated BMP390 actually fix
     * the weather term. */
    float   cal_p_hpa;
    /* Cell dark current in nanoamps, SIGNED. Subtracted from every measured
     * current AND from the air point before K is derived, because the law is
     * I = I0 + K*ln(...): I0 is an OFFSET, and folding it into K instead - as
     * this firmware did until 2026-09-08 - turns it into a slope error across
     * the whole range. At DS-0637's rated 0.4 %vol zero that is roughly 2 %
     * relative at the 20.9 % air point but about 8 % at 5 %vol, which is
     * where compost control acts.
     *
     * Zero is both "no zero point taken" and a legitimate measured zero; the
     * two are arithmetically identical here and separated for the operator by
     * cal_zero_taken / CAL_STATE, not by this field. */
    int32_t zero_na;
} o2p_cal_t;

/* The air point's fraction is stored as %vol x 1000 in a u16 config register,
 * so these are its bounds. 0.15..0.25 brackets every atmosphere this cell
 * will ever be calibrated in: dry air is 0.20946 and saturated air at 60 C is
 * 0.168, both inside; nitrogen and pure oxygen are not. */
#define O2P_CAL_FRAC_MIN 0.15f
#define O2P_CAL_FRAC_MAX 0.25f

/* A plausible air-point window. DS-0637 Issue 2 gives 0.1 mA nominal, so the
 * population sits near 100 uA (this comment said "0.07 +/- 0.03 mA, so
 * 40-100 uA" against Issue 1 and disagreed with the constants below as well
 * as with the rest of the tree; corrected 2026-09-08). Original note kept for
 * the reasoning: the window is deliberately wider than the population because
 * a cell ages downward and the TIA has headroom to 152 uA at 30 % O2
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

/* A TIGHTER window, used only when the cell's bias could not be MEASURED.
 *
 * Added 2026-09-09 after review. The wide window above exists so an aged cell
 * still calibrates - a cell drifts downward over life and refusing it would
 * strand a working probe. That is the right trade when something else has
 * already proved the cell is at its commanded bias.
 *
 * When nothing has, it is the wrong trade. The failure it lets through:
 * a partially faulty RE or electrode path, REFCN still reading back 0xCD,
 * rails healthy, air current 60 uA. That passes 20-200 uA, is stored
 * PERMANENTLY, and a later true 10 %vol then decodes near 16 % - inside the
 * publishable range, with no fault bit anywhere.
 *
 * So: less evidence, tighter bound. DS-0637 Issue 2 gives 0.1 +/- 0.03 mA in
 * air, and a point outside the datasheet's own population is not something to
 * store silently on no other evidence.
 *
 * THIS IS NOT A BIAS CHECK and must not be described as one. It bounds the
 * damage; it does not establish the bias. An earlier version of the
 * calibration gate argued from DS-0637 Note 1 that current magnitude says
 * nothing about bias at all - that MISREAD the note, which describes the
 * post-bias settling transient ("saturated with oxygen gas which is consumed
 * when the bias is reapplied"), not the output of an unbiased cell. The note
 * does not license discarding this check. */
#define O2P_AIR_CAL_UNVERIFIED_MIN_NA  70000
#define O2P_AIR_CAL_UNVERIFIED_MAX_NA 130000

static inline bool o2p_cal_air_plausible(int32_t cell_na)
{
    return cell_na >= O2P_AIR_CAL_MIN_NA && cell_na <= O2P_AIR_CAL_MAX_NA;
}

/* Zero-point acceptance window, nanoamps. A CORRUPTION AND TYPO SCREEN, not an
 * accuracy claim - no runtime check can tell a wrong-but-legal zero from a
 * right one, because that is a property of the nitrogen the point was taken
 * in, not of the number.
 *
 * DS-0637 rates the zero signal "< 0.4 %vol O2 (20 C)". At the top of the
 * population (130 uA in 20.9 %vol, i.e. 6.22 uA per %vol) 0.4 %vol is 2489 nA,
 * so a correct zero is a few thousand nanoamps at most. The window is opened
 * to +/-6000 to leave room for a cell that has aged past its rating and still
 * deserves to be measured rather than silently refused; NEGATIVE values are
 * accepted because the TIA and ADC offsets are real and signed, and forcing a
 * negative offset to zero would bias every low-O2 reading upward - the exact
 * region compost control acts in. */
#define O2P_ZERO_CAL_MIN_NA (-6000)
#define O2P_ZERO_CAL_MAX_NA   6000

static inline bool o2p_cal_zero_plausible(int32_t zero_na)
{
    return zero_na >= O2P_ZERO_CAL_MIN_NA && zero_na <= O2P_ZERO_CAL_MAX_NA;
}

/* Datasheet nominal for an uncalibrated cell, DS-0637 Issue 2: 0.1 mA in air.
 * Using it at all sets CAL_DEFAULT, because the population spread is wide.
 *
 * This was 70000, from Issue 1's 0.07 mA, while the rest of THIS tree had
 * already moved to the Issue 2 cell: lmp91000.h and o2.h both size the TIA
 * headroom from "~152 uA at 30 % O2", which is 106 uA at 20.9 % and cannot be
 * derived from a 70 uA cell, and O2-HUMIDITY-CORRECTION.md:1193 records the
 * bench cell at "~100 uA". A stale nominal here is a 43 % scale error on every
 * uncalibrated probe, in the one path that exists to carry a probe that has
 * not been calibrated yet. Corrected 2026-09-08. */
#define O2P_CAL_AIR_NOMINAL_NA 100000

/* Default tempco until a bench characterisation replaces it. SGX publishes no
 * figure for this part; 0 means "no compensation applied", which is honest -
 * an invented coefficient would be worse than none, because it would look
 * like a correction had been made. */
/* Bound on the stored temperature coefficient. A CORRUPTION AND TYPO SCREEN,
 * nothing more: SGX publishes no curve for this cell, so no runtime check can
 * tell a wrong-but-legal alpha from a right one - that is a property of the
 * bench characterisation the number came from, not of the number. What this
 * does stop is a garbled Modbus write or a flash bit-flip installing a
 * coefficient that distorts every later reading. i16 allows +/-32767 ppm/K,
 * which at a 100 K excursion is a gain of 4.3 or of -2.3; 5000 ppm/K is
 * already an order of magnitude past any amperometric cell's published
 * tempco. */
#define O2P_TEMPCO_ABS_MAX_PPM_K 5000

/* Bound on the stored CALIBRATION TEMPERATURE, 0.01 C. Without it the tempco
 * bound above bounds nothing: gain is 1 + alpha*(T_meas - T_cal), so an
 * unbounded T_cal makes the product unbounded whatever alpha is limited to.
 * i16 admits 0x8000 = -327.68 C, which with alpha at its own limit gives a
 * gain of 2.76 and reports a true 5.00 %vol as 1.84 %vol - across the compost
 * turn threshold, in range, below TEMP_OVER, and with a completely clean fault
 * word. Found by review 2026-09-08, which also disproved the comment claiming
 * gain magnitude was "owned" by the tempco bound; it is owned by BOTH ends of
 * this subtraction. -40..+60 C spans any environment an air or nitrogen point
 * is credibly taken in. */
#define O2P_CAL_TEMP_MIN_C100 (-4000)
#define O2P_CAL_TEMP_MAX_C100   6000

static inline bool o2p_cal_temp_plausible(int16_t c100)
{
    return c100 >= O2P_CAL_TEMP_MIN_C100 && c100 <= O2P_CAL_TEMP_MAX_C100;
}

#define O2P_TEMPCO_DEFAULT 0.0f

/* Dilution efficacy, see o2p_cal_t::dil_alpha. 1.0 is the full gas-law
 * correction - the behaviour before 2026-09-07 - and is the default because a
 * measured 0.402 belongs to the cell it was measured on.
 *
 * The ceiling is 2.0 rather than 1.0: a cell that over-responds to vapour is
 * not something anyone has excluded, and a bound that forbids it would be an
 * assumption wearing a range check. What it does forbid is a fat-fingered
 * write - alpha is what stands between the published number and the raw one,
 * and beyond 2.0 with p_w at its own ceiling, f_eff reaches zero and the
 * correction becomes a divide by nothing. */
#define O2P_DIL_ALPHA_DEFAULT 1.0f
#define O2P_DIL_ALPHA_MAX     2.0f

/* How far one LSB of the stored air fraction may be amplified by a DIL_ALPHA
 * restatement before it is refused instead.
 *
 * THE ARITHMETIC, because the first attempt at this guard bounded the wrong
 * quantity. CAL_AIR_FRAC is the fraction x 100000, so one LSB is 1e-5. The
 * inversion is
 *
 *     air_frac_new = C_AIR * (1 - (1 - air_frac_old/C_AIR) * a_new/a_old)
 *
 * and C_AIR cancels out of the error term exactly: an error d in air_frac_old
 * lands on air_frac_new as d * (a_new/a_old). So the amplification is the
 * ALPHA RATIO and nothing else - not 1/a_old, which is what the first version
 * bounded and which let a_old = 0.001 -> 0.453 through untouched.
 *
 * 10 counts is 1e-4 of fraction, which is 0.01 %vol - exactly one LSB of
 * O2_COMP as published. So the rule is "a restatement may not move the
 * published number by more than its own resolution", which is the tightest
 * bound that is still about the measurement rather than about the float. */
#define O2P_AIR_FRAC_MAX_AMPLIFY 10.0f

/* Water-vapour partial pressure in hPa for `gas`, RH/100 * p_sat(T).
 *
 * O2P_UNEVALUABLE - and NOTHING written - if the gas is not measured, the
 * humidity is not a humidity, or the temperature is beyond
 * O2P_VAPOUR_T_MAX_C. */
o2p_status_t o2p_vapour_pressure_hpa(const o2p_gas_t *gas, float *out_pw_hpa);

/* What the CELL reads in fully aerated air at these conditions:
 * O2P_C_AIR * f_eff, f_eff = 1 - alpha*(1 - (P-p_w)/P). This is what an
 * air-point calibration is really taken against, and it carries alpha for the
 * same reason the measurement does - K is fixed against this number, so if
 * the two sides disagree about how much dilution the cell shows, the
 * disagreement lands on every later reading as gain error. At alpha = 1 it is
 * the plain gas-law fraction O2P_C_AIR * (P - p_w) / P. */
o2p_status_t o2p_air_fraction(const o2p_gas_t *gas, float alpha, float *out_c);

/* Apparent fraction -> dry basis: C_dry = C_wet / f_eff, with
 * f_eff = 1 - alpha*(1 - (P-p_w)/P) - the full gas-law correction
 * C_wet * P / (P - p_w) exactly when alpha = 1.
 *
 * Exactly a no-op at 0 %RH for ANY alpha, by construction rather than by a
 * special case: p_w = 0 gives f = 1 gives f_eff = 1. Monotonically increasing
 * in RH and in temperature for alpha > 0, and REFUSED rather than folded back
 * or clamped once p_w passes O2P_VAPOUR_MAX_PW_FRACTION of P, or once alpha
 * drives f_eff to zero.
 *
 * An alpha that is not finite or lies outside 0..O2P_DIL_ALPHA_MAX is
 * UNEVALUABLE, not silently replaced by 1.0: a substituted alpha would
 * publish the naive correction under the fitted one's name. */
o2p_status_t o2p_dry_from_wet(const o2p_gas_t *gas, float c_wet, float alpha,
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

/* --- the last-good chamber reading, and how old it may be ----------------
 *
 * THE PROBLEM THIS SOLVES. The SHT45's own de-creep heater fires on a
 * schedule - every 8 h by default - and the chamber channels are masked for
 * O2P_SHT_RECOVERY_MS afterwards, because a post-pulse reading is of a
 * deliberately heated element. Until 2026-09-06 that mask also carried
 * I2C_FAIL_SHT, and with dry-basis O2_COMP depending on RH, every scheduled
 * pulse blanked the primary oxygen channel - three times a day - and
 * labelled scheduled maintenance as a sensor failure. With 15-30 minute
 * uplinks and a commensurate pulse schedule, a coincident sample loses a
 * whole O2 uplink.
 *
 * THE FIX IS TO MAKE VALIDITY A MATTER OF DATA AGE, NOT OF A FAULT BIT.
 * Chamber RH and gas temperature are slowly varying - the chamber is a sealed
 * volume against a thermal mass with a ~110 s time constant (theta = 117 K/W,
 * C = 0.94 J/K, measured 2026-09-06) - so the gap is a gap to be bridged,
 * not a failure to be reported. Past the cap the value is unevaluable and
 * O2_COMP takes its sentinel exactly as before: a dead SHT45 still reaches
 * the sentinel, it just takes O2P_RH_MAX_AGE_S to get there, and the fault
 * bit is raised throughout either way.
 */

/* How long the chamber channels stay masked after a de-creep pulse.
 *
 * MEASURED, 2026-09-07, twice, and it was WRONG BY AN ORDER OF MAGNITUDE
 * until then. This constant was 30 s and carried a comment admitting it was a
 * guess. Two unattended scheduled pulses eight hours apart were fitted against
 * the chamber's own drying curve (SHT-DECREEP-MASK-IS-TOO-SHORT.md, from
 * bench-logs/modbus-poll-2026-09-06.csv and -09-07.csv, pre-pulse residual
 * sd 0.054 %RH, n = 333):
 *
 *   back to within 0.50 %RH   115 s
 *                  0.20 %RH   228 s
 *                  0.10 %RH   325 s
 *                  0.05 %RH   not reached inside the observation window
 *
 * At t+40 s - ten seconds after the old mask expired - the published RH was
 * 1.63 %RH LOW, and it stayed more than 0.2 %RH low to t+228 s. So the old
 * value published exactly the artefact sht4x.h says the mask exists to
 * prevent: a 1.6 %RH downward step decaying over about six minutes, three
 * times a day, labelled humidity. On a pile that is a drying event that did
 * not happen.
 *
 * 350 s is the 0.10 %RH criterion plus the next whole sample. It is NOT
 * enough for 0.05 %RH, which the run could not bound. n = 2, one article, one
 * chamber, ~22 C and 40-50 %RH - and the SHT4x datasheet (v7.3 s4.9) gives no
 * recovery-time guarantee at all, only a warning about heater-induced offsets
 * and a restriction to ambient below 65 C. So this bounds the artefact ON THE
 * BENCH and is not established for a saturated 60-80 C pile, where a sensor
 * with more adsorbed water to drive off may well take longer.
 *
 * O2P_RH_MAX_AGE_S IS NOT DERIVED FROM THIS. It was, briefly, and that was the
 * error; see its own comment. */
#define O2P_SHT_RECOVERY_MS 350000u

/* Maximum age of a cached chamber reading, in seconds.
 *
 * DERIVED FROM HOW FAST THE BRIDGED QUANTITY GOES WRONG, NOT FROM THE MASK.
 * That distinction is the whole content of this constant and it was got
 * backwards once, on 2026-09-09, in the same commit that lengthened the mask:
 * the bound was raised 45 -> 400 s "so the cache covers the mask", with a
 * _Static_assert binding the two. Sizing a staleness budget to the length of
 * the gap you want to paper over is circular - it can justify any number, and
 * it justified one that publishes a materially wrong reading. Reverted here,
 * and the assertion is deliberately NOT reinstated in either direction.
 *
 *   30.0 s  the mask this was originally derived against
 *  + 1.1 s  the pulse command itself, which BLOCKS for 1100 ms
 *           (o2p_sht4x_heater_pulse, sht4x.c)
 *  + 1.0 s  the 1 Hz sample cycle
 *  = 32.1 s, and 45 s is that with 40 % margin
 *
 * WHY 400 s WAS WRONG, computed from THIS FILE'S OWN FORMULA rather than
 * argued. The cache carries the chamber TEMPERATURE as well as its humidity,
 * and temperature is by far the more sensitive of the two, because it enters
 * through p_sat(T) which is exponential. Relative error in the PUBLISHED
 * O2_COMP, computed through o2p_dry_fraction_from_current() itself; both
 * errors make it read LOW, because a smaller p_w leaves a larger dry fraction
 * in the denominator:
 *
 *   from 1.6 %RH of error (the de-creep artefact itself):
 *      22 C  -0.04 %      60 C  -0.39 %      70 C  -0.71 %     75 C  -0.99 %
 *   from 5 K of stale TEMPERATURE, humidity saturated throughout:
 *      22 C  -0.93 %      55 C  -4.93 %      60 C  -6.34 %     70 C -10.77 %
 *
 * (75 C is where the table stops because the pile's excursion ceiling is 75 C
 * and O2P_VAPOUR_T_MAX_C refuses at 80 C, so a hotter row would not be a
 * number this firmware ever publishes.)
 *
 * The earlier justification here quoted only the first row and called the
 * sensitivity "mild". At the temperatures this instrument exists to observe -
 * the thermophilic phase - it is not mild, and the second row is the one a
 * long bridge actually incurs. test_a_stale_chamber_temperature_is_the_
 * dominant_bridge_error pins these against the shipped conversion, so the
 * table cannot rot into prose.
 *
 * The mechanism makes it worse rather than better: the RH loop stands down for
 * the whole mask (main.c), so the membrane heater stops, so the chamber is
 * DRIFTING during exactly the window the cached value is used to cover. The
 * bridge is least accurate precisely when it is needed.
 *
 * WHAT THIS COSTS, and why it is the right side. O2_COMP now takes its
 * sentinel for the remainder of each mask - about 305 s, three times a day,
 * roughly 1.2 % of samples. That is the outcome the cache was added to avoid,
 * and it is accepted here because the alternative is worse and this file
 * already says so about a different constant: a number that may be 5-17 % out
 * "is not lower-confidence data, it is an unknown scale factor wearing the
 * units of a measurement" (faults.h on CAL_DEFAULT). Refusing costs a
 * compensated sample; publishing costs the ability to believe any of them.
 *
 * O2_RAW IS UNAFFECTED THROUGHOUT. The raw cell current does not need the
 * SHT45 and keeps its own mask, so the probe's physical measurement of the
 * cell keeps flowing across every de-creep window; it is only the dry-basis
 * conversion that pauses. That is what makes the refusal affordable.
 *
 * If a future measurement bounds how fast chamber temperature can move during
 * a mask, this may be raised on that evidence - a slew bound, not a mask
 * length. */
#define O2P_RH_MAX_AGE_S 45u

/* The same idea for the HEATER's dT clamp, and a separate constant on purpose.
 *
 * main.c bridges the chamber TEMPERATURE from the same cache so the persistent
 * tip loop does not stop for the whole mask. That reference feeds a CLAMP
 * (heater_ctl.c), and a clamp compares a fresh measurement against it: a stale
 * reference does not merely add noise, it moves the trip point. Cached 60 C
 * against an actual 55 C turns a real +4 K excursion into a computed -1 K and
 * the clamp does not fire.
 *
 * It was silently coupled to O2P_RH_MAX_AGE_S until 2026-09-09, so raising the
 * oxygen bound to 400 s extended a thermal interlock's reference to 3.6 tau of
 * the chamber's ~110 s time constant without anyone deciding to. Even with the
 * oxygen bound restored, the two must not share a name: they answer different
 * questions and the next edit to one must not silently move the other.
 *
 * Same value, different derivation: 45 s is ~0.4 tau, short enough that the
 * reference cannot have moved far. Past it the loop refuses on NO_CHAMBER,
 * which is visible in HEATER_BLOCK (0x002E) - so for the remainder of a mask
 * the tip loop stands down alongside the RH loop. That reopens, for ~305 s
 * three times a day, the "loop that refuses intermittently" objection from the
 * 2026-09-08 review, and it is accepted: a clamp evaluated against a reference
 * that may be several K wrong is not protection, and on Rev A this block is
 * measured inert anyway (heater_ctl.c). */
#define O2P_HEATER_CHAMBER_MAX_AGE_S 45u

/* The most recent chamber reading that was actually measured. */
typedef struct {
    float    rh_pct;
    float    t_c;
    uint32_t taken_s;   /* uptime second it was taken */
    bool     valid;     /* false until the first real reading */
} o2p_gas_cache_t;

/* Record a freshly measured gas. Ignores anything not marked valid, so a
 * masked or failed cycle can never poison the cache with a substitute. */
void o2p_gas_cache_update(o2p_gas_cache_t *c, const o2p_gas_t *fresh,
                          uint32_t now_s);

/* Fill `gas`'s humidity and temperature from the cache when this cycle has
 * none of its own. Returns true if `gas` came out valid.
 *
 * A gas that is already valid is left completely alone. Otherwise the cache
 * is used only if it holds a reading and that reading is at most
 * O2P_RH_MAX_AGE_S old; past that the gas stays invalid and the caller
 * publishes the sentinel. The pressure field is NOT cached - it comes from
 * the barometer or a config register and is available every cycle. */
/* The same, with the caller naming its own staleness budget.
 *
 * The oxygen path and the heater's dT clamp bridge the SAME cache for
 * DIFFERENT reasons and must be allowed to disagree about how old is too old -
 * see O2P_HEATER_CHAMBER_MAX_AGE_S. They shared one bound until 2026-09-09,
 * which is how a change to an oxygen data-age policy silently moved a thermal
 * interlock's trip point. o2p_gas_cache_apply() below is this with
 * O2P_RH_MAX_AGE_S, kept so the oxygen path cannot pass the wrong one. */
bool o2p_gas_cache_apply_bounded(const o2p_gas_cache_t *c, o2p_gas_t *gas,
                                 uint32_t now_s, uint32_t max_age_s);

bool o2p_gas_cache_apply(const o2p_gas_cache_t *c, o2p_gas_t *gas,
                         uint32_t now_s);

#endif /* O2P_O2_H */
