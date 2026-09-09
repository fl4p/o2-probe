#include "sht4x.h"

#include "board_pins.h"
#include "i2c1.h"
#include "mcu.h"

#define SHT_ADDR O2P_HW_I2C_ADDR_SHT45

uint8_t o2p_sht4x_crc8(const uint8_t *d, unsigned n)
{
    uint8_t crc = 0xFFu;
    for (unsigned i = 0; i < n; i++) {
        crc ^= d[i];
        for (unsigned b = 0; b < 8u; b++) {
            crc = (crc & 0x80u) ? (uint8_t)((crc << 1) ^ 0x31u) : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

#define crc8 o2p_sht4x_crc8

static o2p_sht_status_t command_then_read(uint8_t cmd, uint32_t wait_ms,
                                          uint8_t *rx, unsigned n)
{
    if (o2p_i2c1_write(SHT_ADDR, &cmd, 1u) != O2P_I2C_OK) {
        return O2P_SHT_IO;
    }
    /* The SHT4x holds no clock stretch: the master must simply wait. */
    o2p_delay_ms(wait_ms);
    if (o2p_i2c1_read(SHT_ADDR, rx, n) != O2P_I2C_OK) {
        return O2P_SHT_IO;
    }
    return O2P_SHT_OK;
}

o2p_sht_status_t o2p_sht4x_reset(void)
{
    const uint8_t cmd = O2P_SHT_CMD_SOFT_RESET;
    if (o2p_i2c1_write(SHT_ADDR, &cmd, 1u) != O2P_I2C_OK) {
        return O2P_SHT_IO;
    }
    o2p_delay_ms(2u);
    return O2P_SHT_OK;
}

o2p_sht_status_t o2p_sht4x_serial(uint32_t *out_serial)
{
    uint8_t rx[6];
    o2p_sht_status_t st = command_then_read(O2P_SHT_CMD_READ_SERIAL, 2u, rx, 6u);
    if (st != O2P_SHT_OK) {
        return st;
    }
    if (crc8(&rx[0], 2u) != rx[2] || crc8(&rx[3], 2u) != rx[5]) {
        return O2P_SHT_CRC;
    }
    if (out_serial != NULL) {
        *out_serial = ((uint32_t)rx[0] << 24) | ((uint32_t)rx[1] << 16) |
                      ((uint32_t)rx[3] << 8) | rx[4];
    }
    return O2P_SHT_OK;
}

o2p_sht_status_t o2p_sht4x_measure(int16_t *out_t_c100, uint16_t *out_rh_x100)
{
    uint8_t rx[6];
    if (out_t_c100 == NULL || out_rh_x100 == NULL) {
        return O2P_SHT_IO;
    }
    /* High-precision measurement takes 8.3 ms max; 12 ms covers it. */
    o2p_sht_status_t st = command_then_read(O2P_SHT_CMD_MEASURE_HIGH, 12u, rx, 6u);
    if (st != O2P_SHT_OK) {
        return st;
    }
    /* Both CRCs must pass. A single good half is not half a measurement: the
     * dew-point calculation needs T and RH from the same instant. */
    if (crc8(&rx[0], 2u) != rx[2] || crc8(&rx[3], 2u) != rx[5]) {
        return O2P_SHT_CRC;
    }

    uint16_t t_raw = (uint16_t)(((uint16_t)rx[0] << 8) | rx[1]);
    uint16_t rh_raw = (uint16_t)(((uint16_t)rx[3] << 8) | rx[4]);

    /* T = -45 + 175 * raw / 65535, in 0.01 C. */
    int32_t t_c100 = -4500 + (int32_t)(((int64_t)t_raw * 17500) / 65535);
    /* RH = -6 + 125 * raw / 65535, in 0.01 %. */
    int32_t rh_x100 = -600 + (int32_t)(((int64_t)rh_raw * 12500) / 65535);

    if (t_c100 < -4500 || t_c100 > 13000) {
        return O2P_SHT_RANGE;
    }
    /* The transfer function slightly overshoots 0-100 % by design; the
     * datasheet says to clamp. Anything beyond a couple of percent outside is
     * not overshoot, it is a broken part. */
    if (rh_x100 < -600 || rh_x100 > 11900) {
        return O2P_SHT_RANGE;
    }
    if (rh_x100 < 0) { rh_x100 = 0; }
    if (rh_x100 > 10000) { rh_x100 = 10000; }

    *out_t_c100 = (int16_t)t_c100;
    *out_rh_x100 = (uint16_t)rh_x100;
    return O2P_SHT_OK;
}

o2p_sht_status_t o2p_sht4x_heater_pulse(uint8_t cmd)
{
    if (cmd != O2P_SHT_CMD_HEAT_200MW_1S && cmd != O2P_SHT_CMD_HEAT_200MW_100MS) {
        return O2P_SHT_IO;
    }
    uint8_t rx[6];
    /* The heater commands return a measurement taken at the end of the pulse;
     * it is read and discarded so the bus is left clean. That reading is taken
     * on a deliberately heated element and must never reach the RH channel. */
    return command_then_read(cmd, (cmd == O2P_SHT_CMD_HEAT_200MW_1S) ? 1100u : 120u,
                             rx, 6u);
}
