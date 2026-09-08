#include "config_flash.h"

#include "config_migrate.h"
#include "config_select.h"
#include "flash_hal.h"
#include "mcu.h"
#include "modbus_pdu.h"

#include <stddef.h>
#include <string.h>

/* STM32G071CB: 128 KiB of flash in 2 KiB pages, so 64 pages numbered 0..63.
 * FLASH_PAGE_SIZE comes from the ST HAL headers (0x800). Assert rather than
 * redefine, so a family change is caught instead of papered over. */
_Static_assert(FLASH_PAGE_SIZE == 2048u, "unexpected flash page size");
_Static_assert(FLASH_PAGE_SIZE == O2P_FLASH_PAGE_BYTES,
               "flash_map.h and the ST headers disagree about the page size");

/* TWO pages, used alternately.
 *
 * A single page cannot be updated atomically: erase then program means that
 * between the two there is no valid record at all, and a power loss in that
 * window loses the air-point calibration - which costs a nitrogen bottle and
 * 15 minutes of settling to recreate, on a probe that may already be buried.
 * With two pages the OLD record stays intact and valid until the new one is
 * completely written, and the loader simply picks the valid record with the
 * higher sequence number.
 *
 * These two pages are reserved from the application in the board JSON
 * (maximum_size = 128 KiB - 2 pages), so a growing image cannot silently
 * overwrite them.
 */
static uint32_t s_sequence;      /* sequence of the record currently live */
static uint8_t s_live_page = CONFIG_PAGE_B;   /* so the first write lands on A */

/* config_migrate.c deliberately does not include this header - it is about
 * the layouts this one has superseded - so its private copies of the magic and
 * the record size are pinned here instead of drifting. */
_Static_assert(CONFIG_RECORD_SIZE == 64u,
               "config_migrate.c assumes a 64-byte record");

static bool read_record(uint8_t page, config_record_t *out)
{
    const config_record_t *r = (const config_record_t *)O2P_PAGE_ADDR(page);
    if (r->magic != CONFIG_MAGIC) {
        return false;
    }
    if (r->layout_version != CONFIG_LAYOUT_VERSION) {
        /* An OLDER layout is migrated, not discarded.
         *
         * Discarding it defaults the whole structure, including slave_addr,
         * baud_code and parity_code - so a probe an operator had moved off the
         * default transport stops answering its master the moment it takes a
         * firmware update, with no way back in over the bus. On a potted probe
         * in a pile that is unrecoverable. What genuinely cannot be carried
         * across a version bump is the AIR POINT, and config_migrate.c zeroes
         * exactly that and nothing else; see its header for the field-by-field
         * argument. A migration that fails, for any reason, still falls back
         * to full defaults exactly as before. */
        uint8_t raw[CONFIG_RECORD_SIZE];
        memcpy(raw, r, sizeof(raw));
        o2p_config_t cfg;
        uint32_t seq = 0u;
        if (!o2p_config_migrate(raw, sizeof(raw), &cfg, &seq)) {
            return false;
        }
        memset(out, 0, sizeof(*out));
        out->magic = CONFIG_MAGIC;
        out->layout_version = CONFIG_LAYOUT_VERSION;
        out->sequence = seq;
        out->cfg = cfg;
        /* The record on the page is still the old one and is NOT rewritten
         * here: a flash write is an operator action (see the header), and this
         * migration is idempotent, so every boot re-derives the same result
         * until someone commits. The sequence is carried so the next commit
         * still wins the higher-sequence comparison. */
        return true;
    }
    config_record_t local;
    memcpy(&local, r, sizeof(local));
    uint16_t want = local.crc;
    local.crc = 0u;
    if (o2p_config_record_crc(&local) != want) {
        return false;
    }
    /* A stored record still has to pass the same validation a live Modbus
     * write would. Otherwise a corrupt-but-CRC-valid image could install a
     * setting the register interface would have rejected. */
    if (!o2p_config_valid(&local.cfg)) {
        return false;
    }
    *out = local;
    return true;
}

bool o2p_config_load(o2p_config_t *cfg)
{
    o2p_config_defaults(cfg);

    config_record_t a, b;
    bool ok_a = read_record(CONFIG_PAGE_A, &a);
    bool ok_b = read_record(CONFIG_PAGE_B, &b);

    /* The choice itself is in config_select.h so the host tests exercise the
     * shipped decision rather than a restatement of it. */
    o2p_cfg_pick_t pick = o2p_config_pick(ok_a, a.sequence, ok_b, b.sequence);
    if (pick == O2P_CFG_PICK_NONE) {
        s_sequence = 0u;
        s_live_page = CONFIG_PAGE_B;   /* next write goes to A */
        return false;
    }
    const config_record_t *win = (pick == O2P_CFG_PICK_A) ? &a : &b;
    s_sequence = win->sequence;
    s_live_page = (win == &a) ? CONFIG_PAGE_A : CONFIG_PAGE_B;
    *cfg = win->cfg;
    return true;
}

bool o2p_config_store(const o2p_config_t *cfg)
{
    if (!o2p_config_valid(cfg)) {
        return false;
    }
    /* Always write the page that is NOT live, so the live record survives
     * intact until this one is complete. */
    const uint8_t target = o2p_config_other_page(s_live_page, CONFIG_PAGE_A,
                                                 CONFIG_PAGE_B);

    config_record_t r;
    memset(&r, 0, sizeof(r));
    r.magic = CONFIG_MAGIC;
    r.layout_version = CONFIG_LAYOUT_VERSION;
    r.sequence = s_sequence + 1u;
    r.cfg = *cfg;
    r.crc = 0u;
    r.crc = o2p_config_record_crc(&r);

    /* Deliberately NO watchdog feed anywhere on this path, here or inside
     * flash_hal.c.
     *
     * A page erase is tens of milliseconds against a 4.096 s timeout, so no
     * feed is needed - and feeding from here would be actively harmful: the
     * main loop feeds only while the sampler is completing cycles AND the
     * RS-485 driver is not stuck enabled, and a feed buried in the flash
     * driver would satisfy the watchdog during exactly the jam that withheld
     * it. A safety interlock with a second, unconditional key is not one. */
    bool ok = o2p_flash_erase_page(target) &&
              o2p_flash_program(O2P_PAGE_ADDR(target), &r, sizeof(r));

    /* Verify through the load path, so a store that produced something the
     * loader would reject is reported now rather than discovered at the next
     * boot - by which time the other page may also have been overwritten. */
    if (ok) {
        config_record_t back;
        ok = read_record(target, &back) &&
             memcmp(&back.cfg, cfg, sizeof(back.cfg)) == 0 &&
             back.sequence == r.sequence;
    }
    if (ok) {
        s_sequence = r.sequence;
        s_live_page = target;
    }
    return ok;
}
