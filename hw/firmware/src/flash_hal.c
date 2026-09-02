#include "flash_hal.h"

#include "flash_map.h"
#include "mcu.h"

#include <string.h>

/* Long enough for a page erase (tens of ms) with margin, short enough that a
 * controller that never clears BSY cannot hang the probe. */
#define FLASH_TIMEOUT_MS 200u

static bool flash_wait(void)
{
    uint32_t t0 = o2p_millis();
    while ((FLASH->SR & FLASH_SR_BSY1) != 0u) {
        if (o2p_elapsed(t0, FLASH_TIMEOUT_MS)) {
            return false;
        }
    }
    if ((FLASH->SR & FLASH_SR_EOP) != 0u) {
        FLASH->SR = FLASH_SR_EOP;
    }
    /* Any error bit means the operation did not do what was asked. Cleared
     * here so the NEXT operation starts from a clean status - a sticky bit
     * from a previous failure would otherwise fail an operation that worked. */
    const uint32_t errs = FLASH_SR_OPERR | FLASH_SR_PROGERR | FLASH_SR_WRPERR |
                          FLASH_SR_PGAERR | FLASH_SR_SIZERR | FLASH_SR_PGSERR |
                          FLASH_SR_MISERR | FLASH_SR_FASTERR;
    if ((FLASH->SR & errs) != 0u) {
        FLASH->SR = errs;
        return false;
    }
    return true;
}

static bool flash_unlock(void)
{
    if ((FLASH->CR & FLASH_CR_LOCK) != 0u) {
        FLASH->KEYR = 0x45670123u;
        FLASH->KEYR = 0xCDEF89ABu;
    }
    return (FLASH->CR & FLASH_CR_LOCK) == 0u;
}

static void flash_lock(void)
{
    FLASH->CR |= FLASH_CR_LOCK;
}

bool o2p_flash_erase_page(uint8_t page)
{
    if (page >= O2P_FLASH_PAGES) {
        return false;
    }
    if (!flash_unlock()) {
        return false;
    }
    bool ok = flash_wait();
    if (ok) {
        FLASH->CR = (FLASH->CR & ~FLASH_CR_PNB) |
                    ((uint32_t)page << FLASH_CR_PNB_Pos) | FLASH_CR_PER;
        FLASH->CR |= FLASH_CR_STRT;
        ok = flash_wait();
        FLASH->CR &= ~(FLASH_CR_PER | FLASH_CR_PNB);
    }
    flash_lock();
    return ok;
}

bool o2p_flash_program(uint32_t addr, const void *src, size_t len)
{
    if (src == NULL || len == 0u) {
        return false;
    }
    /* Alignment and bounds first, before the controller is unlocked: an
     * argument error must not be able to leave flash unlocked, and must not
     * be discovered halfway through a write. */
    if ((addr % O2P_IMAGE_ALIGN) != 0u || (len % O2P_IMAGE_ALIGN) != 0u) {
        return false;
    }
    /* Both halves written as subtractions on the right-hand side: the sum
     * form, (addr - origin) + len, wraps for a large enough aligned len and
     * lets the check pass. No caller can supply one today - in_stage() bounds
     * every update write and payloads cap at 240 bytes - but this is the
     * generic entry point and it is the wrong place to rely on that. */
    const uint32_t span = (uint32_t)O2P_FLASH_PAGES * O2P_FLASH_PAGE_BYTES;
    if (addr < O2P_FLASH_ORIGIN || len > span ||
        (addr - O2P_FLASH_ORIGIN) > span - len) {
        return false;
    }
    if (!flash_unlock()) {
        return false;
    }
    bool ok = flash_wait();
    if (ok) {
        const uint8_t *p = (const uint8_t *)src;
        FLASH->CR |= FLASH_CR_PG;
        for (size_t off = 0; off < len && ok; off += 8u) {
            /* Copied through a local rather than dereferenced from `src`:
             * the caller's buffer is a byte pointer into a Modbus frame and
             * need not be 4-byte aligned, and an unaligned 32-bit load faults
             * on Cortex-M0+. */
            uint32_t w[2];
            memcpy(w, p + off, 8u);
            volatile uint32_t *dst = (volatile uint32_t *)(addr + off);
            dst[0] = w[0];
            __DSB();
            dst[1] = w[1];
            ok = flash_wait();
        }
        FLASH->CR &= ~FLASH_CR_PG;
    }
    flash_lock();

    /* Read back. The controller reports its own errors, but the one failure
     * it cannot report is a cell that programmed and did not hold - and this
     * driver's callers are an updater and a bootloader, where "wrote it,
     * believed it, jumped to it" is the failure that leaves a buried probe
     * silent. */
    if (ok && memcmp((const void *)addr, src, len) != 0) {
        ok = false;
    }
    return ok;
}

bool o2p_flash_page_is_erased(uint8_t page)
{
    if (page >= O2P_FLASH_PAGES) {
        return false;
    }
    const uint32_t *p = (const uint32_t *)O2P_PAGE_ADDR(page);
    for (unsigned i = 0; i < O2P_FLASH_PAGE_BYTES / 4u; i++) {
        if (p[i] != 0xFFFFFFFFu) {
            return false;
        }
    }
    return true;
}
