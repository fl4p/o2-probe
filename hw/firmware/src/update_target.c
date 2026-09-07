#include "update_target.h"

#include "board_pins.h"
#include "boot_desc.h"
#include "flash_hal.h"
#include "flash_map.h"
#include "mcu.h"

#include <string.h>

static o2p_desc_t s_desc;

void o2p_update_target_init(void)
{
    /* A probe that has never been updated has no descriptor. That is not an
     * error and must not look like one: o2p_desc_load leaves an empty record
     * behind, which says "nothing staged, nothing known installed". */
    (void)o2p_desc_load(&s_desc);
}

static bool in_stage(uint32_t addr, uint32_t len)
{
    if (len == 0u || len > O2P_STAGE_BYTES) {
        return false;
    }
    if (addr < O2P_STAGE_BASE) {
        return false;
    }
    /* Written as a subtraction against the slot end rather than addr + len,
     * so a length that would wrap the 32-bit sum cannot pass the test. */
    return (addr - O2P_STAGE_BASE) <= O2P_STAGE_BYTES - len;
}

static bool op_erase_page(uint8_t page)
{
    if (page < O2P_STAGE_PAGE || page >= O2P_STAGE_PAGE + O2P_STAGE_PAGES) {
        return false;
    }
    return o2p_flash_erase_page(page);
}

static bool op_program(uint32_t addr, const void *src, size_t len)
{
    if (!in_stage(addr, (uint32_t)len)) {
        return false;
    }
    return o2p_flash_program(addr, src, len);
}

static void op_read(uint32_t addr, void *dst, size_t len)
{
    memcpy(dst, (const void *)addr, len);
}

static bool op_commit_staged(uint32_t len, uint32_t crc)
{
    o2p_desc_t d = s_desc;
    if (len == 0u) {
        d.flags &= (uint16_t)~O2P_DESC_F_STAGED;
        d.staged_len = 0u;
        d.staged_crc = 0u;
    } else {
        d.flags |= O2P_DESC_F_STAGED;
        d.staged_len = len;
        d.staged_crc = crc;
    }
    if (!o2p_desc_store(&d)) {
        return false;
    }
    s_desc = d;
    return true;
}

static uint16_t op_install_count(void)
{
    return s_desc.install_count;
}

static const o2p_update_ops_t k_ops = {
    .erase_page    = op_erase_page,
    .program       = op_program,
    .read          = op_read,
    .commit_staged = op_commit_staged,
    .install_count = op_install_count,
};

const o2p_update_ops_t *o2p_update_target_ops(void)
{
    return &k_ops;
}

bool o2p_update_target_has_staged(uint32_t *len, uint32_t *crc)
{
    if ((s_desc.flags & O2P_DESC_F_STAGED) == 0u) {
        return false;
    }
    if (len != NULL) {
        *len = s_desc.staged_len;
    }
    if (crc != NULL) {
        *crc = s_desc.staged_crc;
    }
    return true;
}

void o2p_update_target_reboot_to_loader(bool stay)
{
    /* Only a STAY request writes the shared word. A plain BOOT must leave it
     * clear: the bootloader installs whatever is staged either way, and a
     * STAY left behind would strand the probe in the loader - not measuring,
     * cell unbiased - until someone comes back with a laptop. */
    if (stay) {
        o2p_bootreq_set(O2P_BOOTREQ_STAY);
    } else {
        o2p_bootreq_clear();
    }
    /* The reset must not race the last bytes of the Modbus reply, so the
     * caller only gets here once the transmitter is idle - and DE is driven
     * low here as well, because a reset with DE still asserted would hold the
     * shared cable down through the bootloader's own start-up and silence the
     * two SMT100s with it. R7's 47k pull-down does the same job through the
     * reset itself; this makes it true one instruction earlier. */
    O2P_RS485_DE_PORT->BSRR = (1u << (O2P_RS485_DE_PIN + 16u));
    /* And /RE low with it (Rev B, PC7): whatever this application had asked of
     * the receiver, the image about to run is a bootloader whose only job is
     * to be TALKED TO. The reset returns the pin to high-impedance and R45's
     * 47k does the same thing a moment later, exactly as R7 does for DE; this
     * makes it true one instruction earlier. */
    O2P_RS485_RE_PORT->BSRR = (1u << (O2P_RS485_RE_PIN + 16u));
    __DSB();
    NVIC_SystemReset();
}
