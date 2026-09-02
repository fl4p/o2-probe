/* o2-probe RS-485 bootloader.
 *
 * 16 KiB at the bottom of flash that never gets rewritten in the field, whose
 * whole purpose is to be the thing that still works. It:
 *
 *   1. installs a verified image from the staging slot into the run slot,
 *   2. starts the application,
 *   3. and, if asked within a one-second window after any reset, does neither
 *      and answers the updater's register block instead.
 *
 * (3) is the recovery path, and it is the reason this is a separate image at
 * all. An application that boots but has stopped answering Modbus - a stalled
 * sampler, a jammed DE line, a configuration that put it on the wrong address
 * - cannot be updated by itself. A potted probe has no J3 and no BOOT0 to
 * reach. The knock window is the only remaining door, and it costs one second
 * of start-up on an instrument that already spends fifteen minutes settling
 * its cell after every reset.
 *
 * WHAT THIS CANNOT DO: roll back. There is one staging slot, and installing
 * consumes it, so the previous image is gone the moment the run slot is
 * erased. An image that verifies, installs and then misbehaves is recovered
 * through the knock window, not automatically. Two 52 KiB slots plus a
 * bootloader do not fit in 128 KiB alongside the configuration and descriptor
 * pages; keeping a golden image instead of a staging slot would mean no
 * update path at all. This is the trade, and it is why the knock window is
 * not optional.
 */
#include "boot_desc.h"
#include "config_flash.h"
#include "crc32.h"
#include "flash_hal.h"
#include "flash_map.h"
#include "loader_uart.h"
#include "mcu.h"
#include "modbus_pdu.h"
#include "regmap.h"
#include "update.h"
#include "update_target.h"

#include <string.h>

#define O2P_LOADER_VERSION 0x0001u

/* How long after a reset the loader listens for a knock before starting the
 * application. One frame at 9600 8E1 is a few milliseconds; a second is
 * enough for a technician's script to hit the window on the first try. */
#define KNOCK_WINDOW_MS 1000u

/* If the loader is in service mode with a startable application waiting, and
 * nobody talks to it for this long, it starts the application anyway. A probe
 * left in the loader is a probe that is not measuring and whose cell is not
 * biased; the technician who knocked has clearly gone. */
#define SERVICE_IDLE_MS (10u * 60u * 1000u)

#define SRAM_BASE_ADDR 0x20000000u
#define SRAM_BYTES     (36u * 1024u)

static o2p_update_t g_u;
static o2p_desc_t g_desc;
static uint8_t g_rx[O2P_MB_MAX_ADU];
static uint8_t g_tx[O2P_MB_MAX_ADU];
static uint8_t g_addr = 3u;

/* ------------------------------------------------------- serial settings */

/* The loader needs the address, baud and parity the probe is actually
 * configured for, and it reads them from the SAME record the application
 * writes - not from a copy of its own that could drift.
 *
 * It deliberately does not run o2p_config_valid() over the record. That
 * function rejects, among other things, a heater setpoint outside 50-90 %RH;
 * a probe misconfigured that way is still a probe that answers at address 7,
 * and refusing to read its address because its heater limits are silly would
 * make the recovery loader unreachable for a reason that has nothing to do
 * with reaching it. Only the three fields used here are range-checked.
 */
static void read_serial(uint32_t *baud, uint8_t *parity)
{
    *baud = 9600u;
    *parity = O2P_PARITY_EVEN;
    g_addr = 3u;

    const config_record_t *best = NULL;
    config_record_t rec[2];
    for (unsigned i = 0; i < 2u; i++) {
        const uint8_t page = (i == 0u) ? CONFIG_PAGE_A : CONFIG_PAGE_B;
        memcpy(&rec[i], (const void *)O2P_PAGE_ADDR(page), sizeof(rec[i]));
        if (rec[i].magic != CONFIG_MAGIC ||
            rec[i].layout_version != CONFIG_LAYOUT_VERSION) {
            continue;
        }
        config_record_t t = rec[i];
        const uint16_t want = t.crc;
        t.crc = 0u;
        if (o2p_config_record_crc(&t) != want) {
            continue;
        }
        if (best == NULL || (int32_t)(rec[i].sequence - best->sequence) > 0) {
            best = &rec[i];
        }
    }
    if (best == NULL) {
        return;
    }
    if (best->cfg.slave_addr >= O2P_MB_ADDR_MIN &&
        best->cfg.slave_addr <= O2P_MB_ADDR_MAX) {
        g_addr = best->cfg.slave_addr;
    }
    switch (best->cfg.baud_code) {
    case O2P_BAUD_19200: *baud = 19200u; break;
    case O2P_BAUD_38400: *baud = 38400u; break;
    default:             *baud = 9600u;  break;
    }
    if (best->cfg.parity_code <= O2P_PARITY_EVEN) {
        *parity = best->cfg.parity_code;
    }
}

/* ------------------------------------------------------------ image tests */

static bool vectors_plausible(uint32_t base, uint32_t bytes)
{
    const uint32_t msp = *(const uint32_t *)base;
    const uint32_t reset = *(const uint32_t *)(base + 4u);

    if (msp < SRAM_BASE_ADDR || msp > SRAM_BASE_ADDR + SRAM_BYTES) {
        return false;
    }
    if ((reset & 1u) == 0u) {   /* Thumb bit; always set on a Cortex-M */
        return false;
    }
    const uint32_t entry = reset & ~1u;
    return entry >= base && entry < base + bytes;
}

static uint32_t crc_range(uint32_t base, uint32_t len)
{
    return o2p_crc32((const void *)base, len);
}

/* Is there something in the run slot worth jumping to?
 *
 * Two levels, and the weaker one is not a shortcut. A probe whose application
 * was flashed over SWD - every probe, before its first field update - has no
 * installed_crc to check against, and refusing to start it would brick every
 * bench board the moment this loader was installed. So: check the CRC when
 * the descriptor knows one, and fall back to the vector table when it does
 * not. What must never happen is the reverse - a descriptor that HAS a CRC
 * and disagrees with flash being started anyway on the strength of a
 * plausible vector table.
 */
static bool app_startable(void)
{
    if (!vectors_plausible(O2P_APP_BASE, O2P_APP_BYTES)) {
        return false;
    }
    if (o2p_desc_record_valid(&g_desc) && g_desc.installed_len > 0u) {
        return crc_range(O2P_APP_BASE, g_desc.installed_len) ==
               g_desc.installed_crc;
    }
    return true;
}

/* ---------------------------------------------------------------- install */

/* Copy the staged image into the run slot.
 *
 * The dangerous window is inside here and cannot be designed away: between
 * the first erased page of the run slot and the last programmed byte there is
 * no application. What makes it survivable is that the staged image and the
 * descriptor flag are both still intact throughout - so a probe that loses
 * power mid-copy comes back to this same function and does it again. The flag
 * is cleared only after the copy has been read back and verified.
 */
static bool install_staged(void)
{
    const uint32_t len = g_desc.staged_len;

    /* Verify the staging slot BEFORE erasing anything. The application
     * verified it once already, before setting the flag; this repeats the
     * check because between then and now the probe has been reset, and the
     * one thing that must not happen is erasing a working application to make
     * room for an image that did not survive the wait. */
    if (crc_range(O2P_STAGE_BASE, len) != g_desc.staged_crc ||
        !vectors_plausible(O2P_STAGE_BASE, len)) {
        /* Not installable. Drop the flag so the loader does not retry it at
         * every boot forever, and leave the running application alone. */
        o2p_desc_t d = g_desc;
        d.flags &= (uint16_t)~O2P_DESC_F_STAGED;
        d.staged_len = 0u;
        d.staged_crc = 0u;
        if (o2p_desc_store(&d)) {
            g_desc = d;
        }
        return false;
    }

    for (uint8_t i = 0; i < O2P_APP_PAGES; i++) {
        if (!o2p_flash_erase_page((uint8_t)(O2P_APP_PAGE + i))) {
            return false;
        }
    }
    for (uint32_t off = 0; off < len; off += 256u) {
        uint32_t n = len - off;
        if (n > 256u) {
            n = 256u;
        }
        if (!o2p_flash_program(O2P_APP_BASE + off,
                               (const void *)(O2P_STAGE_BASE + off), n)) {
            return false;
        }
    }
    if (crc_range(O2P_APP_BASE, len) != g_desc.staged_crc) {
        return false;
    }

    o2p_desc_t d = g_desc;
    d.installed_len = len;
    d.installed_crc = g_desc.staged_crc;
    d.flags &= (uint16_t)~O2P_DESC_F_STAGED;
    d.staged_len = 0u;
    d.staged_crc = 0u;
    if (d.install_count != 0xFFFFu) {
        d.install_count++;
    }
    if (!o2p_desc_store(&d)) {
        /* The image is in and verified; only the bookkeeping failed. Starting
         * it is right - but the descriptor still says an image is staged, so
         * the next boot will install the same bytes again. Idempotent, and
         * visible: install_count stops advancing. */
        return true;
    }
    g_desc = d;
    return true;
}

/* ------------------------------------------------------------ Modbus glue */

static bool in_block(uint16_t addr, uint16_t count, uint16_t base, uint16_t n)
{
    return addr >= base && (uint32_t)addr + count <= (uint32_t)base + n;
}

static uint8_t loader_read(void *ctx, uint16_t addr, uint16_t count,
                           uint16_t *out)
{
    (void)ctx;
    if (in_block(addr, count, O2P_REG_UPDATE_BASE, O2P_REG_UPDATE_COUNT) ||
        in_block(addr, count, O2P_REG_UPDDATA_BASE, O2P_REG_UPDDATA_COUNT)) {
        return o2p_update_read(&g_u, addr, count, out);
    }
    /* Everything the application publishes - oxygen, temperatures, faults -
     * is absent here, and reads of it are refused rather than answered with
     * zeros. A master that reads 0.00 %vol from a probe in its bootloader
     * would be reading a plausible anaerobic pile. */
    return O2P_MB_EX_ILLEGAL_ADDRESS;
}

static uint8_t loader_write(void *ctx, uint16_t addr, uint16_t count,
                            const uint16_t *in)
{
    (void)ctx;
    if (in_block(addr, count, O2P_REG_UPDATE_BASE, O2P_REG_UPDATE_COUNT) ||
        in_block(addr, count, O2P_REG_UPDDATA_BASE, O2P_REG_UPDDATA_COUNT)) {
        return o2p_update_write(&g_u, addr, count, in);
    }
    return O2P_MB_EX_ILLEGAL_ADDRESS;
}

static const o2p_mb_handlers_t k_handlers = {
    .read = loader_read,
    .write = loader_write,
    .ctx = NULL,
};

static void serve(const uint8_t *adu, size_t len)
{
    if (o2p_mb_classify(adu, len, g_addr) != O2P_MB_EXECUTE) {
        return;
    }
    size_t n = o2p_mb_dispatch(adu, len, g_addr, &k_handlers, g_tx);
    if (n > 0u) {
        o2p_luart_send(g_tx, n);
    }
}

/* Is this frame a write of CMD = STAY, and nothing else?
 *
 * Used only during the knock window, where the loader must not act on any
 * other command. A BEGIN accepted here would erase 52 KiB and then the loader
 * would jump to the application anyway, leaving a transfer that can never
 * complete; a frame that merely reads status must not stop the probe from
 * starting. So the window recognises exactly one thing and stays silent for
 * everything else.
 */
static bool frame_is_stay(const uint8_t *adu, size_t len)
{
    if (len < 8u) {
        return false;
    }
    const uint8_t fc = adu[1];
    const uint16_t start = (uint16_t)((adu[2] << 8) | adu[3]);

    if (fc == O2P_MB_FC_WRITE_SINGLE) {
        const uint16_t val = (uint16_t)((adu[4] << 8) | adu[5]);
        return start == O2P_REG_UPD_CMD && val == O2P_UPD_CMD_STAY;
    }
    if (fc == O2P_MB_FC_WRITE_MULTIPLE) {
        const uint16_t count = (uint16_t)((adu[4] << 8) | adu[5]);
        const uint8_t bytes = adu[6];
        if (count == 0u || bytes != count * 2u || len < 9u + (size_t)bytes) {
            return false;
        }
        if (O2P_REG_UPD_CMD < start || O2P_REG_UPD_CMD >= start + count) {
            return false;
        }
        const unsigned i = (unsigned)(O2P_REG_UPD_CMD - start);
        const uint16_t val = (uint16_t)((adu[7 + i * 2u] << 8) | adu[8 + i * 2u]);
        return val == O2P_UPD_CMD_STAY;
    }
    return false;
}

/* --------------------------------------------------------------- the jump */

static void start_application(void)
{
    const uint32_t msp = *(const uint32_t *)O2P_APP_BASE;
    const uint32_t pc = *(const uint32_t *)(O2P_APP_BASE + 4u);

    o2p_luart_deinit();

    /* Stop the only interrupt source the loader started, and clear anything
     * it left pending: the application sets its own vector table up, but not
     * before the first tick could otherwise arrive through it. */
    SysTick->CTRL = 0u;
    SysTick->LOAD = 0u;
    SysTick->VAL = 0u;
    SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk;

    SCB->VTOR = O2P_APP_BASE;
    __DSB();
    __ISB();
    __set_MSP(msp);
    ((void (*)(void))pc)();

    /* Not reached. If it ever is, reset rather than fall into whatever
     * follows this function in flash. */
    NVIC_SystemReset();
}

/* ------------------------------------------------------------------- main */

int main(void)
{
    o2p_clock_init();

    const bool asked_to_stay = o2p_bootreq_is(O2P_BOOTREQ_STAY);
    /* Cleared immediately, and before anything can fail: a request that
     * survived into the next boot would strand the probe in the loader. */
    o2p_bootreq_clear();

    uint32_t baud;
    uint8_t parity;
    read_serial(&baud, &parity);
    o2p_luart_init(baud, parity);

    (void)o2p_desc_load(&g_desc);

    if (o2p_desc_record_valid(&g_desc) &&
        (g_desc.flags & O2P_DESC_F_STAGED) != 0u) {
        (void)install_staged();
    }

    /* After the install, so the engine's copy of the descriptor is the one the
     * install wrote. */
    o2p_update_target_init();
    o2p_update_init(&g_u, o2p_update_target_ops(), true, 0u,
                    O2P_LOADER_VERSION);

    bool startable = app_startable();
    bool stay = asked_to_stay;

    if (!stay && startable) {
        const uint32_t t0 = o2p_millis();
        while (!o2p_elapsed(t0, KNOCK_WINDOW_MS)) {
            size_t n = o2p_luart_poll(g_rx, sizeof(g_rx));
            if (n == 0u) {
                continue;
            }
            if (o2p_mb_classify(g_rx, n, g_addr) == O2P_MB_EXECUTE &&
                frame_is_stay(g_rx, n)) {
                serve(g_rx, n);
                stay = true;
                break;
            }
        }
        if (!stay) {
            start_application();
        }
    }

    /* Service mode. */
    uint32_t last_frame_ms = o2p_millis();
    for (;;) {
        size_t n = o2p_luart_poll(g_rx, sizeof(g_rx));
        if (n > 0u) {
            last_frame_ms = o2p_millis();
            serve(g_rx, n);
        }

        (void)o2p_update_service(&g_u);

        /* A transfer that verified here is installed the same way one pushed
         * by the application is: by resetting into this loader again, so the
         * install path has exactly one implementation and gets exercised on
         * every update rather than only on the recovery ones. */
        if (g_u.state == O2P_UPD_STAGED) {
            o2p_bootreq_clear();
            NVIC_SystemReset();
        }

        if (startable && o2p_elapsed(last_frame_ms, SERVICE_IDLE_MS)) {
            /* Whoever knocked has gone. A probe sitting in its bootloader is
             * not measuring and its cell is not biased, which is a worse
             * state than a possibly-imperfect application. */
            start_application();
        }
    }
}
