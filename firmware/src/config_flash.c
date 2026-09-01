#include "config_flash.h"

#include "mcu.h"
#include "modbus_pdu.h"

#include <stddef.h>
#include <string.h>

/* STM32G071CB: 128 KiB of flash in 2 KiB pages, so 64 pages numbered 0..63.
 * FLASH_PAGE_SIZE comes from the ST HAL headers (0x800). Assert rather than
 * redefine, so a family change is caught instead of papered over. */
_Static_assert(FLASH_PAGE_SIZE == 2048u, "unexpected flash page size");

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
#define CONFIG_PAGE_A 62u
#define CONFIG_PAGE_B 63u
#define PAGE_ADDR(pg) (FLASH_BASE + (uint32_t)(pg) * FLASH_PAGE_SIZE)

#define CONFIG_MAGIC 0x4F325043u   /* "O2PC" */
#define CONFIG_LAYOUT_VERSION 1u

/* Fixed 64-byte record, so the layout does not move when a config field is
 * added and the flash image stays recognisable across firmware versions. */
#define CONFIG_RECORD_SIZE 64u
typedef struct {
    uint32_t magic;
    uint32_t layout_version;
    uint32_t sequence;          /* monotonic; the higher valid one wins */
    o2p_config_t cfg;
    uint16_t crc;
    uint8_t reserved[CONFIG_RECORD_SIZE - 14u - sizeof(o2p_config_t)];
} config_record_t;

/* Programming is 64-bit on this family, so the record must be a whole number
 * of double words. */
_Static_assert(sizeof(config_record_t) % 8u == 0u,
               "config record must be a multiple of 8 bytes for 64-bit flash "
               "programming");
_Static_assert(sizeof(config_record_t) <= FLASH_PAGE_SIZE, "record too large");

static uint32_t s_sequence;      /* sequence of the record currently live */
static uint8_t s_live_page = CONFIG_PAGE_B;   /* so the first write lands on A */

static uint16_t record_crc(const config_record_t *r)
{
    /* Everything up to but excluding the crc field. The reserved tail is
     * deliberately NOT covered: it exists to be repurposed by a later layout
     * version, and hashing it would make every such change look like
     * corruption to this version. */
    return o2p_mb_crc16((const uint8_t *)r, offsetof(config_record_t, crc));
}

static bool read_record(uint8_t page, config_record_t *out)
{
    const config_record_t *r = (const config_record_t *)PAGE_ADDR(page);
    if (r->magic != CONFIG_MAGIC || r->layout_version != CONFIG_LAYOUT_VERSION) {
        return false;
    }
    config_record_t local;
    memcpy(&local, r, sizeof(local));
    uint16_t want = local.crc;
    local.crc = 0u;
    if (record_crc(&local) != want) {
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

    if (!ok_a && !ok_b) {
        s_sequence = 0u;
        s_live_page = CONFIG_PAGE_B;   /* next write goes to A */
        return false;
    }
    /* Pick the higher sequence. Comparing as a signed difference makes the
     * choice correct across a 32-bit wrap, which needs 4 billion commits to
     * reach but costs nothing to handle. */
    const config_record_t *win;
    if (ok_a && ok_b) {
        win = ((int32_t)(a.sequence - b.sequence) > 0) ? &a : &b;
    } else {
        win = ok_a ? &a : &b;
    }
    s_sequence = win->sequence;
    s_live_page = (win == &a) ? CONFIG_PAGE_A : CONFIG_PAGE_B;
    *cfg = win->cfg;
    return true;
}

static bool flash_wait(void)
{
    uint32_t t0 = o2p_millis();
    while ((FLASH->SR & FLASH_SR_BSY1) != 0u) {
        if (o2p_elapsed(t0, 200u)) {
            return false;
        }
    }
    if ((FLASH->SR & FLASH_SR_EOP) != 0u) {
        FLASH->SR = FLASH_SR_EOP;
    }
    /* Any error bit means the operation did not do what was asked. */
    const uint32_t errs = FLASH_SR_OPERR | FLASH_SR_PROGERR | FLASH_SR_WRPERR |
                          FLASH_SR_PGAERR | FLASH_SR_SIZERR | FLASH_SR_PGSERR |
                          FLASH_SR_MISERR | FLASH_SR_FASTERR;
    if ((FLASH->SR & errs) != 0u) {
        FLASH->SR = errs;
        return false;
    }
    return true;
}

bool o2p_config_store(const o2p_config_t *cfg)
{
    if (!o2p_config_valid(cfg)) {
        return false;
    }
    /* Always write the page that is NOT live, so the live record survives
     * intact until this one is complete. */
    const uint8_t target = (s_live_page == CONFIG_PAGE_A) ? CONFIG_PAGE_B
                                                          : CONFIG_PAGE_A;

    config_record_t r;
    memset(&r, 0, sizeof(r));
    r.magic = CONFIG_MAGIC;
    r.layout_version = CONFIG_LAYOUT_VERSION;
    r.sequence = s_sequence + 1u;
    r.cfg = *cfg;
    r.crc = 0u;
    r.crc = record_crc(&r);

    /* Deliberately NO watchdog feed here.
     *
     * A page erase is tens of milliseconds against a 4.096 s timeout, so no
     * feed is needed - and feeding from here would be actively harmful: the
     * main loop feeds only while the sampler is completing cycles AND the
     * RS-485 driver is not stuck enabled, and a feed buried in the flash
     * driver would satisfy the watchdog during exactly the jam that withheld
     * it. A safety interlock with a second, unconditional key is not one. */
    if ((FLASH->CR & FLASH_CR_LOCK) != 0u) {
        FLASH->KEYR = 0x45670123u;
        FLASH->KEYR = 0xCDEF89ABu;
    }
    if ((FLASH->CR & FLASH_CR_LOCK) != 0u) {
        return false;
    }
    if (!flash_wait()) {
        FLASH->CR |= FLASH_CR_LOCK;
        return false;
    }

    FLASH->CR = (FLASH->CR & ~FLASH_CR_PNB) |
                ((uint32_t)target << FLASH_CR_PNB_Pos) | FLASH_CR_PER;
    FLASH->CR |= FLASH_CR_STRT;
    bool ok = flash_wait();
    FLASH->CR &= ~(FLASH_CR_PER | FLASH_CR_PNB);

    if (ok) {
        const uint32_t *src = (const uint32_t *)&r;
        FLASH->CR |= FLASH_CR_PG;
        for (unsigned i = 0; i < sizeof(r) / 8u && ok; i++) {
            volatile uint32_t *dst = (volatile uint32_t *)(PAGE_ADDR(target) + i * 8u);
            dst[0] = src[i * 2u];
            __DSB();
            dst[1] = src[i * 2u + 1u];
            ok = flash_wait();
        }
        FLASH->CR &= ~FLASH_CR_PG;
    }

    FLASH->CR |= FLASH_CR_LOCK;

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
