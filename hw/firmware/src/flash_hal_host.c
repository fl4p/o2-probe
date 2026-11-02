/* A host stand-in for main flash, so the code that WRITES configuration can be
 * tested off-chip.
 *
 * WHY THIS EXISTS. config_flash.c commits a configuration as two programs into
 * one erased page - the configuration record first, the frozen transport block
 * second - and the ORDER is load-bearing. A power cut between them must leave a
 * state in which the application and the immutable recovery loader still agree
 * on the probe's Modbus identity; the reverse order leaves an orphaned block
 * with no record, the two disagree, and a POTTED probe becomes unreachable.
 *
 * Until 2026-09-09 that rule had no producer-side coverage at all. config_flash.c
 * dereferenced flash addresses directly, so it could not compile for the host
 * and was absent from env:native. Measured: swapping its two
 * o2p_flash_program() calls still built cleanly and still passed every test.
 * Only the CONSUMER of the rule, o2p_transport_select(), was tested.
 *
 * The whole file is host-only. On the target the real driver in flash_hal.c is
 * linked instead, and this compiles to nothing.
 */
#ifdef O2P_HOST_TEST

#include "flash_hal.h"
#include "flash_map.h"

#include <string.h>

/* Backs O2P_FLASH_PTR (flash_map.h). Erased state is 0xFF, like the part. */
uint8_t o2p_host_flash[O2P_FLASH_PAGE_BYTES * O2P_FLASH_PAGES];

static int s_program_calls;
static int s_program_fail_after = -1;   /* <0 = never fail */

/* Reset the fake part. `fail_after` is the number of successful programs to
 * allow before every later one fails - the power cut. -1 never fails.
 *
 * A COUNT and not a flag, because the interesting cut is BETWEEN two specific
 * writes of one commit; a flag could only express "all" or "none", and neither
 * reaches the state that strands the probe. */
void o2p_host_flash_reset(int fail_after)
{
    memset(o2p_host_flash, 0xFF, sizeof(o2p_host_flash));
    s_program_calls = 0;
    s_program_fail_after = fail_after;
}

int o2p_host_flash_programs(void)
{
    return s_program_calls;
}

bool o2p_flash_erase_page(uint8_t page)
{
    if (page >= O2P_FLASH_PAGES) {
        return false;
    }
    memset(o2p_host_flash + (size_t)page * O2P_FLASH_PAGE_BYTES,
           0xFF, O2P_FLASH_PAGE_BYTES);
    return true;
}

bool o2p_flash_program(uint32_t addr, const void *src, size_t len)
{
    /* The real driver refuses a misaligned address or length rather than
     * half-applying it (flash_hal.h). Refusing here too keeps a caller's
     * arithmetic error from passing on the host and failing on the target. */
    if ((addr % 8u) != 0u || (len % 8u) != 0u) {
        return false;
    }
    if (addr < O2P_FLASH_ORIGIN ||
        (addr - O2P_FLASH_ORIGIN) + len > sizeof(o2p_host_flash)) {
        return false;
    }
    if (s_program_fail_after >= 0 && s_program_calls >= s_program_fail_after) {
        s_program_calls++;
        return false;                       /* the cut */
    }
    s_program_calls++;
    memcpy(o2p_host_flash + (addr - O2P_FLASH_ORIGIN), src, len);
    return true;
}

#endif /* O2P_HOST_TEST */
