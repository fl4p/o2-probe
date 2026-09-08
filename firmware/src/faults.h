/* o2-probe fault word and the validity rule derived from it.
 *
 * The fault word is Modbus register 6 of the primary block, so it reaches the
 * ChirpStack decoder on every 5-minute uplink. Everything downstream decides
 * whether to trust a reading from these bits, which makes the exact semantics
 * load-bearing rather than cosmetic.
 *
 * Two rules that are easy to get backwards, both taken from the design record:
 *
 *  - TEMP_OVER does NOT invalidate. PLAN.md:211-228 (decision 2026-08-27)
 *    deliberately deploys the SGX cell above its 60 C rating, because the
 *    thermophilic phase is the phase the probe exists to observe. Above 60 C
 *    the reading is an EXTRAPOLATION and is flagged as such, but discarding it
 *    would throw away the data the instrument was built for. This overrides
 *    compostlab research/COMPOST-O2.md section 6.
 *
 *  - CAL_DEFAULT invalidates the COMPENSATED channel but not the RAW one: an
 *    uncalibrated cell is 0.1 +/- 0.03 mA in air (DS-0637 Issue 2), so a
 *    substituted nominal can be 30 % out, which is an unknown scale factor
 *    wearing the units of a measurement. The raw current is still real data.
 *    (This said "does NOT invalidate either", which contradicted
 *    O2P_FAULTS_INVALIDATE_O2_COMP below, where the bit has always appeared.
 *    The mask was right and the prose was wrong; corrected 2026-09-08.)
 *
 *  - CAL_ZERO_DEFAULT is the same shape as TEMP_OVER, not as CAL_DEFAULT, and
 *    the difference is quantitative. A missing AIR point leaves the scale
 *    factor unknown to +/-30 %; a missing ZERO point leaves a bounded offset,
 *    DS-0637's 'Zero Signal (20 C) < 0.4 %vol O2', so the reading is wrong by
 *    at most 0.4 %O2 and least where the pile is most interesting. That is a
 *    known, bounded accuracy regime - flag it, do not discard it.
 *    ../O2-CORRECTION-MODEL-BUDGET.md has the propagation.
 */
#ifndef O2P_FAULTS_H
#define O2P_FAULTS_H

#include <stdbool.h>
#include <stdint.h>

enum {
    O2P_F_SETTLING            = 1u << 0,  /* cell bias interrupted; up to 15 min */
    O2P_F_I2C_FAIL_LMP        = 1u << 1,
    O2P_F_I2C_FAIL_ADS        = 1u << 2,
    O2P_F_I2C_FAIL_TMP        = 1u << 3,
    O2P_F_I2C_FAIL_SHT        = 1u << 4,
    O2P_F_AFE_CONFIG_MISMATCH = 1u << 5,  /* LMP91000 readback != intended */
    O2P_F_VA_LOW              = 1u << 6,  /* 3V3A brownout seen by the MCU ADC */
    O2P_F_VIN_LOW             = 1u << 7,
    O2P_F_HEATER_RUNAWAY      = 1u << 8,
    O2P_F_TEMP_OVER           = 1u << 9,  /* gas > 60 C: extrapolated, still valid */
    O2P_F_DEW_SUSPECT         = 1u << 10,
    O2P_F_ADC_RANGE           = 1u << 11, /* converter saturated or out of window */
    O2P_F_CAL_DEFAULT         = 1u << 12, /* running on datasheet nominal, not a cal */
    /* Bit 13 was EXP_PRESENT, reserved for the J2 expansion header. J2 is DNP
     * on Rev A, NO firmware ever wrote the bit, and the presence answer is
     * already published in EXP_DATA (0xFFFF = absent), so the bit carried
     * nothing. It is spent here instead. NOTE: tech/chirpstack/codec/
     * _o2_regs.js independently retired bits 13/14 on 2026-09-04 and named
     * them ads_drdy_stuck / ads_config_lost - names no firmware implements.
     * That collision is Fab's to arbitrate; the decoder's positional table is
     * updated to match THIS file, which is the map. */
    O2P_F_CAL_ZERO_DEFAULT    = 1u << 13, /* no zero point taken; offset <= 0.4 %vol */
    O2P_F_EXP_FAIL            = 1u << 14,
    O2P_F_HEATER_DISABLED     = 1u << 15, /* always set in v0 */
};

/* Two masks, because the raw cell current and the compensated volume fraction
 * fail for different reasons.
 *
 * O2_RAW is a physical measurement of the cell: microamps through a known
 * transimpedance. It is meaningful with no calibration at all, and it is the
 * channel the bench uses to resolve the open sign-convention gate.
 *
 * O2_COMP is that current divided by a calibration constant. Without an air
 * point there IS no constant - the datasheet nominal spans 0.07 to 0.13 mA,
 * so a substituted nominal can be wrong by -30 % to +30 %. A number that may
 * be 30 % out is not "lower-confidence data", it is an unknown scale factor
 * wearing the units of a measurement, and 15.2 %vol against a true 21 %vol is
 * indistinguishable from a real, alarming result. So CAL_DEFAULT invalidates
 * the compensated channel while leaving the raw one intact. */
#define O2P_FAULTS_INVALIDATE_O2 ( \
      O2P_F_SETTLING            \
    | O2P_F_I2C_FAIL_LMP        \
    | O2P_F_I2C_FAIL_ADS        \
    | O2P_F_AFE_CONFIG_MISMATCH \
    | O2P_F_VA_LOW              \
    | O2P_F_ADC_RANGE )

/* Everything above, plus the reasons the CONVERSION cannot be trusted even
 * when the current reading is fine. */
#define O2P_FAULTS_INVALIDATE_O2_COMP ( \
      O2P_FAULTS_INVALIDATE_O2 \
    | O2P_F_CAL_DEFAULT )

/* CAL_ZERO_DEFAULT appears in NEITHER mask, deliberately. It is in no
 * invalidation list for the same reason TEMP_OVER is not: the reading is
 * real, its error is bounded and documented, and a compost decision taken at
 * 5 %O2 does not change because the number might be 5.4 %. Widening this to
 * an invalidating fault would blank the compensated channel on every probe
 * built so far - none has a zero point, and there is no bench to take one on
 * yet - which is how a guard gets switched off rather than satisfied. */

/* The chamber channels have their own dependencies: RH and chamber
 * temperature come from the SHT45, tip temperature from the TMP117. */
#define O2P_FAULTS_INVALIDATE_CHAMBER (O2P_F_I2C_FAIL_SHT)
#define O2P_FAULTS_INVALIDATE_TIP     (O2P_F_I2C_FAIL_TMP)

/* Sentinels. Chosen so no legitimate value can collide with them:
 *   0xFFFF as u16  - O2_COMP tops out at 3000 (30.00 %vol, the cell's overload
 *                    limit), RH_CHAMBER at 10000, HEATER_DUTY at 10000.
 *   0x8000 as i16  - the most negative int16; temperatures are 0.01 C and the
 *                    cell is rated to -40 C (-4000), O2_RAW is uA*100.
 * 0xFFFF is also already the system-wide "failed Modbus read" marker that the
 * Dragino node inserts and smt100-2probe-decoder.js:56 rejects, so an invalid
 * o2-probe reading and a dead o2-probe look the same downstream - which is
 * correct: both mean "no oxygen number this cycle".
 */
#define O2P_U16_INVALID 0xFFFFu
#define O2P_I16_INVALID ((int16_t)0x8000)

/* Is the raw cell-current channel trustworthy? */
static inline bool o2p_o2_valid(uint16_t faults)
{
    return (faults & O2P_FAULTS_INVALIDATE_O2) == 0u;
}

/* Is the compensated %vol channel trustworthy? */
static inline bool o2p_o2_comp_valid(uint16_t faults)
{
    return (faults & O2P_FAULTS_INVALIDATE_O2_COMP) == 0u;
}

#endif /* O2P_FAULTS_H */
