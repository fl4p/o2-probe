#include "tmp117.h"

#include "board_pins.h"
#include "i2c1.h"
#include "mcu.h"

#define TMP_ADDR O2P_HW_I2C_ADDR_TMP117

/* CONV[2:0] = 011 (500 ms cycle) with AVG[1:0] = 01 (8 averaged conversions),
 * MOD = 00 continuous. Averaging costs nothing here and the 1 Hz loop wants a
 * settled number, not a fast one. */
#define TMP_CFG_BASE ((uint16_t)((0u << 10) | (3u << 7) | (1u << 5)))
#define TMP_CFG_THERM_MODE ((uint16_t)(1u << 4))   /* T/nA = 1 */
#define TMP_CFG_POL_ACTIVE_LOW ((uint16_t)(0u << 3))
#define TMP_CFG_PIN_FOLLOWS_ALERTS ((uint16_t)(0u << 2))
#define TMP_CFG_INTENDED (TMP_CFG_BASE | TMP_CFG_THERM_MODE | \
                          TMP_CFG_POL_ACTIVE_LOW | TMP_CFG_PIN_FOLLOWS_ALERTS)

/* Only the writable bits are compared on readback; 15:12 are live flags. */
#define TMP_CFG_WRITABLE_MASK 0x0FFCu

static bool wr16(uint8_t reg, uint16_t val)
{
    const uint8_t tx[3] = {reg, (uint8_t)(val >> 8), (uint8_t)(val & 0xFFu)};
    return o2p_i2c1_write(TMP_ADDR, tx, 3u) == O2P_I2C_OK;
}

static bool rd16(uint8_t reg, uint16_t *val)
{
    uint8_t rx[2];
    if (o2p_i2c1_write_read(TMP_ADDR, &reg, 1u, rx, 2u) != O2P_I2C_OK) {
        return false;
    }
    *val = (uint16_t)(((uint16_t)rx[0] << 8) | rx[1]);
    return true;
}

static int16_t c100_to_lsb(int32_t c100)
{
    /* 0.01 C -> 7.8125 m C counts: count = c100 * 10000 / 7812.5
     *                                    = c100 * 1.28
     * Done in integers as c100 * 128 / 100. */
    int32_t v = (c100 * 128) / 100;
    if (v > 32767) { v = 32767; }
    if (v < -32768) { v = -32768; }
    return (int16_t)v;
}

o2p_tmp_status_t o2p_tmp117_init(int16_t limit_c100, uint16_t hyst_k100)
{
    uint16_t id = 0u;
    if (!rd16(O2P_TMP_REG_DEVID, &id)) {
        return O2P_TMP_IO;
    }
    /* The ID register's upper nibble is a revision field; match only the
     * device ID itself (SNOSD82D 7.6.11). */
    if ((uint16_t)(id & 0x0FFFu) != O2P_TMP_DEVICE_ID) {
        return O2P_TMP_ID;
    }

    /* Limits FIRST, configuration second. Enabling therm mode before the
     * limits are set would arm the alert against whatever THIGH happens to
     * hold from EEPROM - and on a board where that pin switches 1 W into a
     * membrane, arming against an unknown threshold is not acceptable. */
    if (!wr16(O2P_TMP_REG_THIGH, (uint16_t)c100_to_lsb(limit_c100))) {
        return O2P_TMP_IO;
    }
    /* In therm mode TLOW is the hysteresis point, not a low alarm. */
    if (!wr16(O2P_TMP_REG_TLOW,
              (uint16_t)c100_to_lsb((int32_t)limit_c100 - (int32_t)hyst_k100))) {
        return O2P_TMP_IO;
    }
    if (!wr16(O2P_TMP_REG_CONFIG, TMP_CFG_INTENDED)) {
        return O2P_TMP_IO;
    }

    uint16_t back = 0u;
    if (!rd16(O2P_TMP_REG_CONFIG, &back)) {
        return O2P_TMP_IO;
    }
    if ((uint16_t)(back & TMP_CFG_WRITABLE_MASK) !=
        (uint16_t)(TMP_CFG_INTENDED & TMP_CFG_WRITABLE_MASK)) {
        return O2P_TMP_CONFIG;
    }
    return O2P_TMP_OK;
}

o2p_tmp_status_t o2p_tmp117_read_c100(int16_t *out_c100)
{
    uint16_t raw = 0u;
    if (out_c100 == NULL) {
        return O2P_TMP_IO;
    }
    if (!rd16(O2P_TMP_REG_TEMP, &raw)) {
        return O2P_TMP_IO;
    }
    /* count * 7812.5 uC -> 0.01 C is count * 100 / 128. */
    int32_t c100 = ((int32_t)(int16_t)raw * 100) / 128;
    if (c100 > 32767 || c100 < -32768) {
        return O2P_TMP_IO;
    }
    *out_c100 = (int16_t)c100;
    return O2P_TMP_OK;
}

o2p_tmp_status_t o2p_tmp117_alert_active(bool *out_active)
{
    uint16_t cfg = 0u;
    if (out_active == NULL) {
        return O2P_TMP_IO;
    }
    if (!rd16(O2P_TMP_REG_CONFIG, &cfg)) {
        return O2P_TMP_IO;
    }
    *out_active = (cfg & (1u << 15)) != 0u;   /* HIGH_Alert */
    return O2P_TMP_OK;
}
