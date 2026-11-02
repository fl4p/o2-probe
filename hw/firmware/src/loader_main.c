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
#include "transport_record.h"
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
 * configured for, and everything about how it gets them is shaped by one
 * constraint: THIS IMAGE IS NEVER REWRITTEN IN THE FIELD, so it will be
 * reading records written by applications that did not exist when it was
 * compiled.
 *
 * PRIMARY SOURCE: the frozen 16-byte transport block (transport_record.h),
 * written beside every configuration record in the same erase. Its layout
 * never changes, its CRC never moves, and it carries nothing but the three
 * bytes needed here - so a loader from 2026 can verify one written by a
 * firmware from any later year. This is the path that is meant to run.
 *
 * FALLBACK: the configuration record itself, and only when its layout version
 * is exactly the one this build was compiled with. That restriction is not
 * caution, it is arithmetic - the record's CRC sits immediately after a
 * struct that grows, so a loader that does not know the size cannot find the
 * checksum, and fields read out of bytes you cannot verify are not evidence.
 * The fallback exists for records written BEFORE the transport block did, by
 * a matching application; it is the old behaviour, kept and demoted.
 *
 * The fallback outranks the transport block when, and only when, it is
 * demonstrably NEWER - a higher sequence. That case is a downgrade: an
 * application without the transport block committed a configuration after one
 * with it did, leaving a valid but stale block on the other page. Preferring
 * the block by default and the record by sequence covers both directions.
 *
 * Neither source is run through o2p_config_valid(). That function rejects,
 * among other things, a heater setpoint outside 50-90 %RH; a probe
 * misconfigured that way is still a probe that answers at address 7, and
 * refusing to read its address because its heater limits are silly would make
 * the recovery loader unreachable for a reason that has nothing to do with
 * reaching it. Only the three fields used here are range-checked - and they
 * are range-checked on EVERY path, including the transport block, because the
 * block's CRC proves the bytes are the ones that were written, not that a
 * baud code this build has never heard of means anything to it.
 */
static void apply_serial(uint8_t addr, uint8_t baud_code, uint8_t parity_code,
                         uint32_t *baud, uint8_t *parity)
{
    if (addr >= O2P_MB_ADDR_MIN && addr <= O2P_MB_ADDR_MAX) {
        g_addr = addr;
    }
    switch (baud_code) {
    case O2P_BAUD_19200: *baud = 19200u; break;
    case O2P_BAUD_38400: *baud = 38400u; break;
    /* THE LOADER MUST KNOW EVERY RATE THE APP CAN BE SET TO, and this case is
     * why: the default below is 9600, so a loader that does not recognise the
     * stored code comes up at 9600 while the master is talking 115200 - and
     * the loader is the update path, so the one tool that could fix it is the
     * one that cannot reach it. Adding a rate to regmap.h without adding it
     * here strands a re-rated probe at its next reset into service mode. */
    case O2P_BAUD_115200: *baud = 115200u; break;
    case O2P_BAUD_57600: *baud = 57600u; break;
    default:             *baud = 9600u;  break;
    }
    if (parity_code <= O2P_PARITY_EVEN) {
        *parity = parity_code;
    }
}

/* The newest configuration record this build can actually verify, if any. */
static bool best_readable_config(config_record_t *out)
{
    bool found = false;
    for (unsigned i = 0; i < 2u; i++) {
        const uint8_t page = (i == 0u) ? CONFIG_PAGE_A : CONFIG_PAGE_B;
        config_record_t r;
        memcpy(&r, (const void *)O2P_PAGE_ADDR(page), sizeof(r));
        if (r.magic != CONFIG_MAGIC ||
            r.layout_version != CONFIG_LAYOUT_VERSION) {
            continue;
        }
        const uint16_t want = r.crc;
        r.crc = 0u;
        if (o2p_config_record_crc(&r) != want) {
            continue;
        }
        if (!found || (int32_t)(r.sequence - out->sequence) > 0) {
            *out = r;
            found = true;
        }
    }
    return found;
}

static void read_serial(uint32_t *baud, uint8_t *parity)
{
    *baud = 9600u;
    *parity = O2P_PARITY_EVEN;
    g_addr = 3u;

    o2p_transport_record_t tr[2];
    for (unsigned i = 0; i < 2u; i++) {
        const uint8_t page = (i == 0u) ? CONFIG_PAGE_A : CONFIG_PAGE_B;
        memcpy(&tr[i], (const void *)(O2P_PAGE_ADDR(page) +
                                      O2P_TRANSPORT_OFFSET), sizeof(tr[i]));
    }
    config_record_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    const bool have_cfg = best_readable_config(&cfg);
    o2p_transport_t from_cfg = { 0u, 0u, 0u };
    if (have_cfg) {
        from_cfg.slave_addr = cfg.cfg.slave_addr;
        from_cfg.baud_code = cfg.cfg.baud_code;
        from_cfg.parity_code = cfg.cfg.parity_code;
    }

    o2p_transport_t chosen;
    if (o2p_transport_select(&tr[0], &tr[1], have_cfg, cfg.sequence, &from_cfg,
                             &chosen)) {
        apply_serial(chosen.slave_addr, chosen.baud_code, chosen.parity_code,
                     baud, parity);
    }
    /* Neither readable: the defaults set at the top stand, and they are the
     * identity a recovery host must try when the configured one is silent.
     * FIRMWARE.md documents that two-identity knock procedure - it is the
     * whole recovery path for a probe whose loader predates the transport
     * block. */
}

/* ------------------------------------------------------------ image tests */

/* Does the vector table at `image_base` belong to an image LINKED for
 * `link_base`?
 *
 * The two are the same thing for the run slot and deliberately different for a
 * staged image: an application in the staging slot is linked to run from
 * 0x08004000, so its reset vector points at the run slot and not at the bytes
 * it currently occupies. Checking a staged image against its own address would
 * reject every correct image there is - which is exactly what this function
 * did when it took one base, and is why it now takes two. */
static bool vectors_plausible(uint32_t image_base, uint32_t link_base,
                              uint32_t len)
{
    const uint32_t msp = *(const uint32_t *)image_base;
    const uint32_t reset = *(const uint32_t *)(image_base + 4u);

    if (msp < SRAM_BASE_ADDR || msp > SRAM_BASE_ADDR + SRAM_BYTES) {
        return false;
    }
    if ((reset & 1u) == 0u) {   /* Thumb bit; always set on a Cortex-M */
        return false;
    }
    const uint32_t entry = reset & ~1u;
    return entry >= link_base && entry < link_base + len;
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
    if (!vectors_plausible(O2P_APP_BASE, O2P_APP_BASE, O2P_APP_BYTES)) {
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
/* What an install attempt left behind, which is not the same question as
 * whether it succeeded. REFUSED means nothing was touched and the application
 * that was there is still there. DAMAGED means the run slot was erased and the
 * copy did not complete - its first bytes may well be a plausible vector table
 * followed by nothing, which is exactly what the no-descriptor fallback in
 * app_startable() would wave through. */
typedef enum { INSTALL_OK, INSTALL_REFUSED, INSTALL_DAMAGED } install_result_t;

static install_result_t install_staged(void)
{
    const uint32_t len = g_desc.staged_len;

    /* Verify the staging slot BEFORE erasing anything. The application
     * verified it once already, before setting the flag; this repeats the
     * check because between then and now the probe has been reset, and the
     * one thing that must not happen is erasing a working application to make
     * room for an image that did not survive the wait. */
    if (crc_range(O2P_STAGE_BASE, len) != g_desc.staged_crc ||
        !vectors_plausible(O2P_STAGE_BASE, O2P_APP_BASE, len)) {
        /* Not installable. Drop the flag so the loader does not retry it at
         * every boot forever, and leave the running application alone. */
        o2p_desc_t d = g_desc;
        d.flags &= (uint16_t)~O2P_DESC_F_STAGED;
        d.staged_len = 0u;
        d.staged_crc = 0u;
        if (o2p_desc_store(&d)) {
            g_desc = d;
        }
        return INSTALL_REFUSED;
    }

    for (uint8_t i = 0; i < O2P_APP_PAGES; i++) {
        if (!o2p_flash_erase_page((uint8_t)(O2P_APP_PAGE + i))) {
            return INSTALL_DAMAGED;
        }
    }
    /* Through a RAM buffer, not flash-to-flash. Programming stalls every
     * access to the flash array, so a source operand fetched from the same
     * array during a program operation is at best relying on the stall
     * behaving; ST's own procedure programs from RAM. 256 bytes of stack is
     * cheaper than the doubt. */
    uint8_t buf[256];
    for (uint32_t off = 0; off < len; off += sizeof(buf)) {
        uint32_t n = len - off;
        if (n > sizeof(buf)) {
            n = sizeof(buf);
        }
        memcpy(buf, (const void *)(O2P_STAGE_BASE + off), n);
        if (!o2p_flash_program(O2P_APP_BASE + off, buf, n)) {
            return INSTALL_DAMAGED;
        }
    }
    if (crc_range(O2P_APP_BASE, len) != g_desc.staged_crc) {
        return INSTALL_DAMAGED;
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
         * it is right - but only if the in-RAM descriptor is made to describe
         * the flash that now exists. Leaving it describing the PREVIOUS
         * application makes app_startable() CRC the new bytes against the old
         * length and reject them, and the probe stays in the loader; if the
         * alternate descriptor page is permanently unwritable, every boot
         * recopies the image and strands it again.
         *
         * So finish the record here, the way a successful store would have.
         * Flash still says an image is staged, so the next boot reinstalls the
         * same bytes - idempotent, and visible, because install_count in flash
         * stops advancing. */
        d.magic = O2P_DESC_MAGIC;
        d.layout_version = O2P_DESC_LAYOUT_VERSION;
        d.crc16 = 0u;
        d.crc16 = o2p_desc_crc(&d);
    }
    g_desc = d;
    return INSTALL_OK;
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

/* True if the frame was executed and answered normally - not dropped, and not
 * answered with an exception. The knock window needs that distinction: a frame
 * that LOOKS like STAY but is refused by the dispatcher (a write through the
 * read-only discovery alias, a STAY smuggled in beside registers this block
 * does not accept) must not stop the probe from starting. */
static bool serve(const uint8_t *adu, size_t len)
{
    if (o2p_mb_classify(adu, len, g_addr) != O2P_MB_EXECUTE) {
        return false;
    }
    size_t n = o2p_mb_dispatch(adu, len, g_addr, &k_handlers, g_tx);
    if (n == 0u) {
        return false;
    }
    o2p_luart_send(g_tx, n);
    return (g_tx[1] & 0x80u) == 0u;
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

    /* The discovery alias is read-only everywhere else in this firmware
     * (modbus_pdu.h:48), and every probe on the cable answers to it. A STAY
     * accepted through it would park EVERY probe in its loader at once, and
     * they would then collide answering the next frame. */
    if (adu[0] == O2P_MB_ADDR_DISCOVERY) {
        return false;
    }

    if (fc == O2P_MB_FC_WRITE_SINGLE) {
        /* Exact length. A frame with trailing bytes is not this frame, and
         * the CRC that made it here belongs to those bytes too. */
        if (len != 8u) {
            return false;
        }
        const uint16_t val = (uint16_t)((adu[4] << 8) | adu[5]);
        return start == O2P_REG_UPD_CMD && val == O2P_UPD_CMD_STAY;
    }
    if (fc == O2P_MB_FC_WRITE_MULTIPLE) {
        const uint16_t count = (uint16_t)((adu[4] << 8) | adu[5]);
        const uint8_t bytes = adu[6];
        if (count == 0u || bytes != count * 2u || len != 9u + (size_t)bytes) {
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

    install_result_t installed = INSTALL_OK;
    if (o2p_desc_record_valid(&g_desc) &&
        (g_desc.flags & O2P_DESC_F_STAGED) != 0u) {
        installed = install_staged();
    }

    /* After the install, so the engine's copy of the descriptor is the one the
     * install wrote. */
    o2p_update_target_init();
    o2p_update_init(&g_u, o2p_update_target_ops(), true, 0u,
                    O2P_LOADER_VERSION);

    /* An install that erased the run slot and did not finish leaves bytes
     * there that can pass a vector-table check and nothing else. Never start
     * those: stay in the loader and let the master push the image again. */
    bool startable = app_startable() && installed != INSTALL_DAMAGED;
    bool stay = asked_to_stay;

    if (!stay && startable) {
        const uint32_t t0 = o2p_millis();
        while (!o2p_elapsed(t0, KNOCK_WINDOW_MS)) {
            size_t n = o2p_luart_poll(g_rx, sizeof(g_rx));
            if (n == 0u) {
                continue;
            }
            if (o2p_mb_classify(g_rx, n, g_addr) == O2P_MB_EXECUTE &&
                frame_is_stay(g_rx, n) && serve(g_rx, n)) {
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
            /* Only a frame addressed to THIS probe counts as company. The
             * cable carries the Dragino's five-minute poll of two SMT100s; if
             * that refreshed the idle timer, the ten-minute fallback below
             * would never fire and a probe left in service mode would stay
             * there for good. */
            if (o2p_mb_classify(g_rx, n, g_addr) != O2P_MB_DROP) {
                last_frame_ms = o2p_millis();
            }
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
