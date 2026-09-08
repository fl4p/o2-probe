/* SHT45-AD1F chamber humidity/temperature, I2C 0x44 (fixed).
 *
 * DESIGN.md and PLAN.md:20-24 are explicit that this is a CONDENSATION-MARGIN
 * HEALTH CHANNEL, not a calibrated hygrometer: the polyimide-membrane variant
 * carries roughly a +3 %RH standing offset after long exposure above 80 %RH,
 * and the compost atmosphere attacks the polymer. Treat its RH as a trend and
 * a dew-point input, never as an accuracy claim.
 *
 * Commands and the CRC-8 (poly 0x31, init 0xFF) are the standard SHT4x set.
 */
#ifndef O2P_SHT4X_H
#define O2P_SHT4X_H

/* The part's rated ranges (Sensirion SHT4x datasheet V7.3), in 0.01 units.
 * These bound the RATING, unlike the transfer function's own image, which any
 * 16-bit word satisfies by construction - see o2p_sht4x_measure(). */
#define O2P_SHT_T_MIN_C100 (-4000)
#define O2P_SHT_T_MAX_C100  12500
/* RH rejection bounds - deliberately WIDE, and not a datasheet limit.
 *
 * Sensirion's transfer function is allowed to return values outside 0-100 %RH
 * and the datasheet says to CLAMP them, not to treat them as faults. It also
 * documents a temporary offset of about +3 %RH after prolonged operation above
 * 80 %RH - which is exactly this application, a saturated compost pore gas.
 * A -3..103 % rejection window (briefly used here) therefore had no datasheet
 * basis and would have rejected legitimate readings from a wet probe: the very
 * condition the humidity channel exists to observe. Found by the sixth review.
 *
 * So rejection is reserved for readings far enough outside the rating to be
 * implausible, and the ordinary overshoot is clamped afterwards as the
 * datasheet directs. The CRC catches transmission corruption; this is an
 * OPERATIONAL PLAUSIBILITY SCREEN, not proof of a bus error and not a rated
 * limit - Sensirion nowhere states that >110 %RH means a broken part, and the
 * endpoints below are an engineering choice (seventh review). */
#define O2P_SHT_RH_MIN_X100 (-500)
#define O2P_SHT_RH_MAX_X100  11000



#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum {
    O2P_SHT_CMD_MEASURE_HIGH = 0xFDu,
    O2P_SHT_CMD_READ_SERIAL  = 0x89u,
    O2P_SHT_CMD_SOFT_RESET   = 0x94u,
    /* Heater pulses. The datasheet limits the heater to at most 10 % duty,
     * which at one 1-second pulse is one pulse per 10 seconds - we use one
     * per several hours, so the limit is respected by orders of magnitude. */
    O2P_SHT_CMD_HEAT_200MW_1S   = 0x39u,
    O2P_SHT_CMD_HEAT_200MW_100MS= 0x32u,
};

typedef enum { O2P_SHT_OK = 0, O2P_SHT_IO, O2P_SHT_CRC, O2P_SHT_RANGE } o2p_sht_status_t;

/* The pure part of a measurement: raw words in, engineering units and a
 * verdict out. It lives in the header so the HOST TESTS can exercise the
 * decision this driver actually makes - sht4x.c pulls in CMSIS through i2c1
 * and cannot compile on the host, so a test that only checked the constants
 * above proved nothing about the code using them (sixth review). CRC checking
 * stays in the .c, where the bus is. */
static inline o2p_sht_status_t o2p_sht4x_decode(uint16_t t_raw, uint16_t rh_raw,
                                                int16_t *out_t_c100,
                                                uint16_t *out_rh_x100)
{
    if (out_t_c100 == NULL || out_rh_x100 == NULL) {
        return O2P_SHT_IO;
    }
    /* T = -45 + 175 * raw / 65535, in 0.01 C. */
    int32_t t_c100 = -4500 + (int32_t)(((int64_t)t_raw * 17500) / 65535);
    /* RH = -6 + 125 * raw / 65535, in 0.01 %. */
    int32_t rh_x100 = -600 + (int32_t)(((int64_t)rh_raw * 12500) / 65535);

    if (t_c100 < O2P_SHT_T_MIN_C100 || t_c100 > O2P_SHT_T_MAX_C100) {
        return O2P_SHT_RANGE;
    }
    if (rh_x100 < O2P_SHT_RH_MIN_X100 || rh_x100 > O2P_SHT_RH_MAX_X100) {
        return O2P_SHT_RANGE;
    }
    /* Sensirion directs that the overshoot be clamped, not rejected. */
    if (rh_x100 < 0) { rh_x100 = 0; }
    if (rh_x100 > 10000) { rh_x100 = 10000; }

    *out_t_c100 = (int16_t)t_c100;
    *out_rh_x100 = (uint16_t)rh_x100;
    return O2P_SHT_OK;
}

o2p_sht_status_t o2p_sht4x_reset(void);
o2p_sht_status_t o2p_sht4x_serial(uint32_t *out_serial);

/* One high-precision measurement. Temperature in 0.01 C, RH in 0.01 %.
 *
 * RH is clamped to 0..100 % as the datasheet directs. A value far outside the
 * RATING is reported as O2P_SHT_RANGE rather than clamped silently, so the
 * dew-point calculation is never fed a clamped fiction. That rejection is an
 * operational plausibility screen (see the bounds above), NOT a datasheet
 * limit and not proof the part has failed - the previous wording said both at
 * once; corrected 2026-09-08. */
o2p_sht_status_t o2p_sht4x_measure(int16_t *out_t_c100, uint16_t *out_rh_x100);

/* Fire the on-chip heater. PLAN.md:312 uses this every 6-12 h for two
 * purposes: de-creep after long exposure to high RH, and dew detection - a
 * dry sensor recovers its RH reading quickly after the pulse while a wetted
 * one shows a slow-recovery signature. The pulse and its settling window must
 * be MASKED from the reported RH channel, or the de-creep looks like the pile
 * drying out. */
o2p_sht_status_t o2p_sht4x_heater_pulse(uint8_t cmd);

#endif /* O2P_SHT4X_H */
