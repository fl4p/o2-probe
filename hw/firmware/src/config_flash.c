#include "config_flash.h"

#include "mcu.h"
#include "modbus_pdu.h"

#include <stddef.h>
#include <string.h>

/* STM32G071CB: 128 KiB of flash in 2 KiB pages, so 64 pages numbered 0..63.
 * The configuration record lives alone in the last one. */
/* FLASH_PAGE_SIZE comes from the ST HAL headers (0x800). Assert rather than
 * redefine, so a family change is caught instead of papered over. */
_Static_assert(FLASH_PAGE_SIZE == 2048u, "unexpected flash page size");
#define CONFIG_PAGE 63u
#define CONFIG_ADDR (FLASH_BASE + CONFIG_PAGE * FLASH_PAGE_SIZE)

#define CONFIG_MAGIC 0x4F325043u   /* "O2PC" */
#define CONFIG_LAYOUT_VERSION 1u

/* Fixed 64-byte record, so the layout does not move when a config field is
 * added and the flash image stays recognisable across firmware versions. */
#define CONFIG_RECORD_SIZE 64u
typedef struct {
    uint32_t magic;
    uint32_t layout_version;
    o2p_config_t cfg;
    uint16_t crc;
    uint8_t reserved[CONFIG_RECORD_SIZE - 10u - sizeof(o2p_config_t)];
} config_record_t;

/* Programming is 64-bit on this family, so the record must be a whole number
 * of double words. */
_Static_assert(sizeof(config_record_t) % 8u == 0u,
               "config record must be a multiple of 8 bytes for 64-bit flash "
               "programming");
_Static_assert(sizeof(config_record_t) <= FLASH_PAGE_SIZE, "record too large");

static uint16_t record_crc(const config_record_t *r)
{
    /* Everything up to but excluding the crc field. */
    return o2p_mb_crc16((const uint8_t *)r,
                        offsetof(config_record_t, crc));
}

bool o2p_config_load(o2p_config_t *cfg)
{
    o2p_config_defaults(cfg);

    const config_record_t *r = (const config_record_t *)CONFIG_ADDR;
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
     * write would. Otherwise a corrupt-but-CRC-valid image, or a record
     * written by an older layout that happened to match, could install a
     * setting the register interface would have rejected. */
    if (!o2p_config_valid(&local.cfg)) {
        return false;
    }
    *cfg = local.cfg;
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

    config_record_t r;
    memset(&r, 0, sizeof(r));
    r.magic = CONFIG_MAGIC;
    r.layout_version = CONFIG_LAYOUT_VERSION;
    r.cfg = *cfg;
    r.crc = 0u;
    r.crc = record_crc(&r);

    /* Feed the watchdog before stalling: a page erase is tens of milliseconds
     * of frozen instruction fetch, and the point of the ~4 s timeout is that
     * it must not fire here. */
    o2p_wdt_feed();

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

    /* Erase. From here until the write completes, a power loss leaves an
     * erased page - which o2p_config_load rejects on the magic, so the probe
     * comes back on defaults rather than on half a record. */
    FLASH->CR = (FLASH->CR & ~FLASH_CR_PNB) |
                ((uint32_t)CONFIG_PAGE << FLASH_CR_PNB_Pos) | FLASH_CR_PER;
    FLASH->CR |= FLASH_CR_STRT;
    bool ok = flash_wait();
    FLASH->CR &= ~(FLASH_CR_PER | FLASH_CR_PNB);

    if (ok) {
        o2p_wdt_feed();
        const uint32_t *src = (const uint32_t *)&r;
        FLASH->CR |= FLASH_CR_PG;
        for (unsigned i = 0; i < sizeof(r) / 8u && ok; i++) {
            volatile uint32_t *dst = (volatile uint32_t *)(CONFIG_ADDR + i * 8u);
            dst[0] = src[i * 2u];
            __DSB();
            dst[1] = src[i * 2u + 1u];
            ok = flash_wait();
        }
        FLASH->CR &= ~FLASH_CR_PG;
    }

    FLASH->CR |= FLASH_CR_LOCK;

    /* Verify by reading back through the load path, so a store that produced
     * something the loader would reject is reported as a failure now rather
     * than discovered at the next boot. */
    if (ok) {
        o2p_config_t check;
        ok = o2p_config_load(&check) && memcmp(&check, cfg, sizeof(check)) == 0;
    }
    return ok;
}
