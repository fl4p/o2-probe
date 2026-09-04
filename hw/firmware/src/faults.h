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
 *  - CAL_DEFAULT does NOT invalidate either, but it must reach the decoder: an
 *    uncalibrated cell is 0.07 +/- 0.03 mA in air, so the reading can be 40 %
 *    out. It is real data of known-poor accuracy, not garbage.
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
    /* DRDY was low before a conversion was started and did not release when
     * drained. Distinct from I2C_FAIL_ADS on purpose: the bus can be
     * perfectly healthy while this pin is not, and reporting a pin failure as
     * a bus failure is what sent a healthy ADS1119 back as scrap. Bit 13 was
     * EXP_PRESENT, reserved for the J2 expansion header, which is DNP on
     * Rev A and written by no code - see FIRMWARE.md. */
    O2P_F_ADS_DRDY_STUCK      = 1u << 13,
    /* The ADS1119's config register did not read back as written. Distinct
     * from I2C_FAIL_ADS because the bus demonstrably WORKED - the readback
     * completed, it just disagreed - and distinct from AFE_CONFIG_MISMATCH,
     * which is the LMP91000's. This says: the thing at 0x40 is not storing
     * configuration, so it is either failing or is not an ADS1119. Making the
     * check reachable at run time (ads1119.c) without giving it a bit of its
     * own would have left it indistinguishable from one NACK. Bit 14 was
     * EXP_FAIL, for the J2 header that is DNP on Rev A. */
    O2P_F_ADS_CONFIG_LOST     = 1u << 14,
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
 * point there IS no constant - the datasheet nominal spans 0.04 to 0.10 mA,
 * so a substituted nominal can be wrong by -43 % to +43 %. A number that may
 * be 43 % out is not "lower-confidence data", it is an unknown scale factor
 * wearing the units of a measurement, and 12 %vol against a true 21 %vol is
 * indistinguishable from a real, alarming result. So CAL_DEFAULT invalidates
 * the compensated channel while leaving the raw one intact. */
#define O2P_FAULTS_INVALIDATE_O2 ( \
      O2P_F_SETTLING            \
    | O2P_F_I2C_FAIL_LMP        \
    | O2P_F_I2C_FAIL_ADS        \
    | O2P_F_AFE_CONFIG_MISMATCH \
    | O2P_F_VA_LOW              \
    | O2P_F_ADS_DRDY_STUCK      \
    | O2P_F_ADS_CONFIG_LOST     \
    | O2P_F_ADC_RANGE )

/* Everything above, plus the reasons the CONVERSION cannot be trusted even
 * when the current reading is fine. */
#define O2P_FAULTS_INVALIDATE_O2_COMP ( \
      O2P_FAULTS_INVALIDATE_O2 \
    | O2P_F_CAL_DEFAULT )

/* "The ADS1119 did not deliver a conversion this phase", for the callers that
 * must not compute from an abandoned accumulator. This mask exists because
 * splitting DRDY out of I2C_FAIL_ADS silently broke every site that tested the
 * single bit: they would have fallen through on a DRDY failure and divided a
 * zeroed g_acc into a plausible-looking reading. Test the MASK, never one bit,
 * so the next status added here cannot reintroduce that. */
#define O2P_FAULTS_ADS_NO_CONVERSION ( \
      O2P_F_I2C_FAIL_ADS   \
    | O2P_F_ADS_DRDY_STUCK \
    | O2P_F_ADS_CONFIG_LOST )

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
