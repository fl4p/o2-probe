#include "lmp91000.h"

#include "board_pins.h"
#include "i2c1.h"
#include "mcu.h"

#define LMP_ADDR O2P_HW_I2C_ADDR_LMP91000

void o2p_lmp91000_gpio_init(void)
{
    /* MENB is active low and R17 (100k) already holds it there, so the AFE is
     * addressable through MCU reset - deliberate, per PLAN.md:234-236, so that
     * I2C availability does not depend on firmware having run. Driving it
     * actively just makes that state independent of the pull-down's leakage. */
    O2P_AFE_MENB_PORT->BSRR = (1u << (O2P_AFE_MENB_PIN + 16u));         /* low = enabled */
    O2P_AFE_MENB_PORT->OTYPER &= ~(1u << O2P_AFE_MENB_PIN);
    O2P_AFE_MENB_PORT->MODER = (O2P_AFE_MENB_PORT->MODER & ~(3u << (O2P_AFE_MENB_PIN * 2u))) |
                   (1u << (O2P_AFE_MENB_PIN * 2u));         /* output */
}

static bool wr(uint8_t reg, uint8_t val)
{
    const uint8_t tx[2] = {reg, val};
    return o2p_i2c1_write(LMP_ADDR, tx, 2u) == O2P_I2C_OK;
}

static bool rd(uint8_t reg, uint8_t *val)
{
    return o2p_i2c1_write_read(LMP_ADDR, &reg, 1u, val, 1u) == O2P_I2C_OK;
}

o2p_lmp_status_t o2p_lmp91000_configure(void)
{
    uint8_t status = 0u;
    if (!rd(O2P_LMP_REG_STATUS, &status)) {
        return O2P_LMP_IO;
    }
    if ((status & 1u) == 0u) {
        /* Not ready yet. The caller retries; it must not proceed to write
         * configuration the part will ignore. */
        return O2P_LMP_IO;
    }

    /* TIACN and REFCN are write-protected by the LOCK register, which resets
     * to 1 (read-only). Unlock, write, then LEAVE IT UNLOCKED - re-locking
     * would make the periodic rewrite-on-mismatch path fail silently exactly
     * when it is needed. */
    if (!wr(O2P_LMP_REG_LOCK, 0x00u)) {
        return O2P_LMP_IO;
    }
    if (!wr(O2P_LMP_REG_TIACN, O2P_LMP_TIACN_INTENDED)) {
        return O2P_LMP_IO;
    }
    if (!wr(O2P_LMP_REG_REFCN, O2P_LMP_REFCN_INTENDED)) {
        return O2P_LMP_IO;
    }
    /* MODECN is not lock-protected. Written last: it is what takes the part
     * out of deep sleep, so the bias network is already configured when the
     * cell is first driven. Writing it first would briefly bias the cell with
     * the reset-default 50 % internal zero and 0 % bias. */
    if (!wr(O2P_LMP_REG_MODECN, O2P_LMP_MODECN_INTENDED)) {
        return O2P_LMP_IO;
    }
    return o2p_lmp91000_verify(NULL);
}

o2p_lmp_status_t o2p_lmp91000_verify(uint16_t *out_readback)
{
    uint8_t tiacn = 0u, refcn = 0u, modecn = 0u;
    if (!rd(O2P_LMP_REG_TIACN, &tiacn) ||
        !rd(O2P_LMP_REG_REFCN, &refcn) ||
        !rd(O2P_LMP_REG_MODECN, &modecn)) {
        return O2P_LMP_IO;
    }
    if (out_readback != NULL) {
        *out_readback = (uint16_t)(((uint16_t)tiacn << 8) | refcn);
    }
    /* TIACN bits 7:5 are RESERVED and are not guaranteed to read back as
     * written, so compare only the defined fields. Comparing the whole byte
     * would produce a permanent false mismatch, which is worse than no check:
     * it would hold the probe in SETTLING forever. */
    if ((uint8_t)(tiacn & 0x1Fu) != O2P_LMP_TIACN_INTENDED) {
        return O2P_LMP_MISMATCH;
    }
    if (refcn != O2P_LMP_REFCN_INTENDED) {
        return O2P_LMP_MISMATCH;
    }
    /* MODECN bits 6:3 are reserved; OP_MODE and FET_SHORT are what matter. */
    if ((uint8_t)(modecn & 0x87u) != O2P_LMP_MODECN_INTENDED) {
        return O2P_LMP_MISMATCH;
    }
    return O2P_LMP_OK;
}
