/* The target-side flash operations the update engine runs on, and the shared
 * word of RAM the application uses to ask for a reboot into the bootloader.
 *
 * The engine (update.c) never touches flash directly. It goes through these,
 * and these refuse every address outside the staging slot - so no arithmetic
 * error inside the engine, and no malformed frame that survives it, can reach
 * the running application, the bootloader or the configuration pages. The
 * bootloader's install path writes the run slot, and it deliberately does NOT
 * go through here: that write is a different operation with a different
 * bound, made once, after a CRC has already passed.
 */
#ifndef O2P_UPDATE_TARGET_H
#define O2P_UPDATE_TARGET_H

#include "update.h"

/* Loads the boot descriptor so UPD_INSTALLS and commit_staged have something
 * to work from. Call once, before o2p_update_init(). */
void o2p_update_target_init(void);

const o2p_update_ops_t *o2p_update_target_ops(void);

/* True if the boot descriptor says a verified image is waiting in the staging
 * slot - which is how the application knows, after a reset that interrupted a
 * transfer, that it is STAGED rather than IDLE. */
bool o2p_update_target_has_staged(uint32_t *len, uint32_t *crc);

/* Reset into the bootloader, which installs a staged image if there is one.
 * With `stay`, the loader is asked to remain in service mode instead of
 * starting the application afterwards. Does not return. */
void o2p_update_target_reboot_to_loader(bool stay);

#endif /* O2P_UPDATE_TARGET_H */
