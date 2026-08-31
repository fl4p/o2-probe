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

#include "regmap.h"

/* Load the stored configuration. Returns false if there was none, or it was
 * corrupt, or it failed validation - in which case `cfg` holds the defaults. */
bool o2p_config_load(o2p_config_t *cfg);

/* Erase and rewrite the config page. Returns false on any flash error.
 * Must not be called while the RS-485 transmitter is active. */
bool o2p_config_store(const o2p_config_t *cfg);

#endif /* O2P_CONFIG_FLASH_H */
