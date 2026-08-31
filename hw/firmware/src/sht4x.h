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

#include <stdbool.h>
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

o2p_sht_status_t o2p_sht4x_reset(void);
o2p_sht_status_t o2p_sht4x_serial(uint32_t *out_serial);

/* One high-precision measurement. Temperature in 0.01 C, RH in 0.01 %.
 * RH is clamped to 0..100 % as the datasheet directs, but a raw value far
 * outside that range is reported as O2P_SHT_RANGE rather than clamped
 * silently - out-of-range means the part is failing, and the dew-point
 * calculation must not be fed a clamped fiction. */
o2p_sht_status_t o2p_sht4x_measure(int16_t *out_t_c100, uint16_t *out_rh_x100);

/* Fire the on-chip heater. PLAN.md:312 uses this every 6-12 h for two
 * purposes: de-creep after long exposure to high RH, and dew detection - a
 * dry sensor recovers its RH reading quickly after the pulse while a wetted
 * one shows a slow-recovery signature. The pulse and its settling window must
 * be MASKED from the reported RH channel, or the de-creep looks like the pile
 * drying out. */
o2p_sht_status_t o2p_sht4x_heater_pulse(uint8_t cmd);

#endif /* O2P_SHT4X_H */
