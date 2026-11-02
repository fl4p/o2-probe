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

static bool s_safety_armed;

/* The limits o2p_tmp117_init() actually programmed, kept so that a later
 * verification can check the THRESHOLD and not merely the mode. Therm mode
 * with the wrong THIGH is not a cutoff at the limit this firmware chose; it is
 * a cutoff at whatever the register happens to hold. */
static bool s_limits_known;
static uint16_t s_thigh_lsb;
static uint16_t s_tlow_lsb;

static bool s_ext_present;
static uint8_t s_ext_addr;
static uint8_t s_ext_fail_count;

static bool wr16_addr(uint8_t addr, uint8_t reg, uint16_t val)
{
    const uint8_t tx[3] = {reg, (uint8_t)(val >> 8), (uint8_t)(val & 0xFFu)};
    return o2p_i2c1_write(addr, tx, 3u) == O2P_I2C_OK;
}

static bool rd16_addr(uint8_t addr, uint8_t reg, uint16_t *val)
{
    uint8_t rx[2];
    if (o2p_i2c1_write_read(addr, &reg, 1u, rx, 2u) != O2P_I2C_OK) {
        return false;
    }
    *val = (uint16_t)(((uint16_t)rx[0] << 8) | rx[1]);
    return true;
}

static bool wr16(uint8_t reg, uint16_t val)
{
    return wr16_addr(TMP_ADDR, reg, val);
}

static bool rd16(uint8_t reg, uint16_t *val)
{
    return rd16_addr(TMP_ADDR, reg, val);
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

bool o2p_tmp117_safety_armed(void)
{
    return s_safety_armed;
}

o2p_tmp_status_t o2p_tmp117_verify_safety(void)
{
    /* Nothing to verify against until init has programmed the limits, and a
     * part that was never configured must not be able to arm itself by
     * happening to read back something. Unevaluable is disarmed, not OK. */
    if (!s_limits_known) {
        s_safety_armed = false;
        return O2P_TMP_CONFIG;
    }

    uint16_t back = 0u;
    if (!rd16(O2P_TMP_REG_CONFIG, &back)) {
        s_safety_armed = false;
        return O2P_TMP_IO;
    }
    if ((uint16_t)(back & TMP_CFG_WRITABLE_MASK) !=
        (uint16_t)(TMP_CFG_INTENDED & TMP_CFG_WRITABLE_MASK)) {
        s_safety_armed = false;
        return O2P_TMP_CONFIG;
    }

    /* The thresholds, not just the mode. THIGH is the cutoff and TLOW is its
     * hysteresis point; either one silently reverting to the part's EEPROM
     * default (+192 C / -256 C) leaves therm mode enabled and the config
     * register perfectly correct, while the heater has no usable limit at
     * all. Checking CONFIG alone cannot see that. */
    uint16_t thigh = 0u, tlow = 0u;
    if (!rd16(O2P_TMP_REG_THIGH, &thigh) || !rd16(O2P_TMP_REG_TLOW, &tlow)) {
        s_safety_armed = false;
        return O2P_TMP_IO;
    }
    if (thigh != s_thigh_lsb || tlow != s_tlow_lsb) {
        s_safety_armed = false;
        return O2P_TMP_CONFIG;
    }

    s_safety_armed = true;
    return O2P_TMP_OK;
}

o2p_tmp_status_t o2p_tmp117_init(int16_t limit_c100, uint16_t hyst_k100)
{
    uint16_t id = 0u;
    s_safety_armed = false;
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
    s_thigh_lsb = (uint16_t)c100_to_lsb(limit_c100);
    /* In therm mode TLOW is the hysteresis point, not a low alarm. */
    s_tlow_lsb = (uint16_t)c100_to_lsb((int32_t)limit_c100 - (int32_t)hyst_k100);
    s_limits_known = true;

    if (!wr16(O2P_TMP_REG_THIGH, s_thigh_lsb)) {
        return O2P_TMP_IO;
    }
    if (!wr16(O2P_TMP_REG_TLOW, s_tlow_lsb)) {
        return O2P_TMP_IO;
    }
    if (!wr16(O2P_TMP_REG_CONFIG, TMP_CFG_INTENDED)) {
        return O2P_TMP_IO;
    }

    /* Read back all three, not just the mode. An I2C write that is ACKed has
     * reached the part; it has not necessarily been stored, and the limits are
     * the half that makes this an 85 C cutoff rather than an alert at whatever
     * EEPROM held. This is the same comparison the periodic re-verification
     * does, so arm through it and keep one definition of "armed". */
    return o2p_tmp117_verify_safety();
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
    if (c100 < O2P_TMP117_MIN_C100 || c100 > O2P_TMP117_MAX_C100) {
        return O2P_TMP_RANGE;
    }
    *out_c100 = (int16_t)c100;
    return O2P_TMP_OK;
}

o2p_tmp_status_t o2p_tmp117_data_ready(bool *out_ready)
{
    uint16_t cfg = 0u;
    if (out_ready == NULL) {
        return O2P_TMP_IO;
    }
    if (!rd16(O2P_TMP_REG_CONFIG, &cfg)) {
        return O2P_TMP_IO;
    }
    *out_ready = (cfg & (1u << 13)) != 0u;   /* Data_Ready */
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

bool o2p_tmp117_ext_present(void)
{
    return s_ext_present;
}

uint8_t o2p_tmp117_ext_address(void)
{
    return s_ext_addr;
}

o2p_tmp_status_t o2p_tmp117_ext_data_ready(bool *out_ready)
{
    uint16_t cfg = 0u;
    if (out_ready == NULL || !s_ext_present || s_ext_addr == 0u) {
        return O2P_TMP_IO;
    }
    if (!rd16_addr(s_ext_addr, O2P_TMP_REG_CONFIG, &cfg)) {
        return O2P_TMP_IO;
    }
    *out_ready = (cfg & (1u << 13)) != 0u;   /* Data_Ready */
    return O2P_TMP_OK;
}

o2p_tmp_status_t o2p_tmp117_ext_init(void)
{
    s_ext_present = false;
    s_ext_addr = 0u;

    const uint8_t candidate_addrs[2] = {
        O2P_HW_I2C_ADDR_TMP117_EXT,  /* 0x4A: ADD0 strapped to SDA (default on tmp117-probe) */
        0x4Bu                        /* 0x4B: ADD0 strapped to SCL (alternate) */
    };

    for (unsigned i = 0; i < 2u; i++) {
        uint8_t a = candidate_addrs[i];
        if (o2p_i2c1_probe(a) != O2P_I2C_OK) {
            continue;
        }
        uint16_t id = 0u;
        if (!rd16_addr(a, O2P_TMP_REG_DEVID, &id)) {
            continue;
        }
        if ((uint16_t)(id & 0x0FFFu) != O2P_TMP_DEVICE_ID) {
            continue;
        }
        /* Continuous conversion, 8-sample averaging, 500 ms conversion cycle.
         * The external sensor does not use therm mode or hardware alert cutoff. */
        if (!wr16_addr(a, O2P_TMP_REG_CONFIG, TMP_CFG_BASE)) {
            continue;
        }
        s_ext_addr = a;
        s_ext_present = true;
        s_ext_fail_count = 0u;
        return O2P_TMP_OK;
    }
    return O2P_TMP_IO;
}

o2p_tmp_status_t o2p_tmp117_ext_read_c100(int16_t *out_c100)
{
    if (out_c100 == NULL) {
        return O2P_TMP_IO;
    }
    if (!s_ext_present || s_ext_addr == 0u) {
        return O2P_TMP_IO;
    }
    uint16_t raw = 0u;
    if (!rd16_addr(s_ext_addr, O2P_TMP_REG_TEMP, &raw)) {
        if (++s_ext_fail_count >= 3u) {
            s_ext_present = false;
        }
        return O2P_TMP_IO;
    }
    s_ext_fail_count = 0u;
    int32_t c100 = ((int32_t)(int16_t)raw * 100) / 128;
    if (c100 < O2P_TMP117_MIN_C100 || c100 > O2P_TMP117_MAX_C100) {
        return O2P_TMP_RANGE;
    }
    *out_c100 = (int16_t)c100;
    return O2P_TMP_OK;
}
