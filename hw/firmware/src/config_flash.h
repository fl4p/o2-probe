/* Persistent configuration in the last flash page.
 *
 * The STM32G071CB has no EEPROM and the board carries no external storage, so
 * configuration lives in main flash. Two consequences shape this design:
 *
 *  - Endurance is on the order of 10 k cycles per page, so a write must be an
 *    explicit operator action (the COMMIT_MAGIC register), never a side effect
 *    of a routine write.
 *  - Erasing or programming main flash STALLS instruction fetch on this part.
 *    A page erase is tens of milliseconds, which is many character times at
 *    9600 baud. So a commit is only performed when the transmitter is idle,
 *    and the Modbus receiver is expected to lose whatever arrives during it.
 *    That is acceptable for an operator-triggered action and unacceptable as
 *    an automatic one - which is the real reason for the magic.
 *
 * A record that fails its CRC is DISCARDED and the defaults are used, with a
 * fault raised. A half-written record must never install a partial
 * configuration, and a corrupt flash image must not be able to hand the probe
 * a setting that a Modbus master would have been refused - which is why the
 * loader runs o2p_config_valid() over the recovered record too.
 */
#ifndef O2P_CONFIG_FLASH_H
#define O2P_CONFIG_FLASH_H

#include <stdbool.h>

#include <stddef.h>
#include <string.h>

#include "flash_map.h"
#include "modbus_pdu.h"
#include "regmap.h"

/* --- the stored record ---------------------------------------------------
 *
 * Public because the BOOTLOADER reads it too. It needs the slave address,
 * baud and parity to answer at all, and it must not link the application's
 * register map to get them: the loader is the thing that has to still work
 * when the application is broken, so it borrows the layout and nothing else.
 * It deliberately does not apply o2p_config_valid() - a configuration whose
 * heater limits are nonsense is still a configuration whose serial settings
 * tell you where the probe is on the bus, and being unreachable is the one
 * failure a recovery loader may not have.
 */
#define CONFIG_PAGE_A O2P_CONFIG_PAGE_A
#define CONFIG_PAGE_B O2P_CONFIG_PAGE_B

#define CONFIG_MAGIC 0x4F325043u   /* "O2PC" */
/* 2: added heater_kp_x100 / heater_ki_x100 (registers 0x0040/0x0041).
 * Bumping this makes a version-1 record unreadable rather than
 * mis-interpreted, so an older probe's stored config falls back to defaults -
 * and the defaults put HEATER_MAX_DUTY at 0, i.e. heater off. The fail-safe
 * direction of a layout change is therefore "no heat", which is the only
 * direction it is allowed to fail in. */
#define CONFIG_LAYOUT_VERSION 2u

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
_Static_assert(sizeof(config_record_t) <= O2P_FLASH_PAGE_BYTES,
               "record too large");

/* CRC-16/MODBUS over everything up to but excluding the crc field. The
 * reserved tail is deliberately NOT covered: it exists to be repurposed by a
 * later layout version, and hashing it would make every such change look like
 * corruption to this version. Shared with the bootloader, which validates the
 * same record with the same function. */
static inline uint16_t o2p_config_record_crc(const config_record_t *r)
{
    return o2p_mb_crc16((const uint8_t *)r, offsetof(config_record_t, crc));
}

/* Load the stored configuration. Returns false if there was none, or it was
 * corrupt, or it failed validation - in which case `cfg` holds the defaults. */
bool o2p_config_load(o2p_config_t *cfg);

/* Erase and rewrite the config page. Returns false on any flash error.
 * Must not be called while the RS-485 transmitter is active. */
bool o2p_config_store(const o2p_config_t *cfg);

#endif /* O2P_CONFIG_FLASH_H */
