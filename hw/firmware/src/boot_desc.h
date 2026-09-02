/* The boot descriptor: two flash pages that say what is in the staging slot
 * and what was last installed into the run slot.
 *
 * Written by the application (when a transfer verifies) and by the bootloader
 * (when an install completes), so the record format lives here rather than
 * inside either one. Same A/B, sequence-numbered, CRC'd discipline as
 * config_flash.c, and for the same reason: the moment a record is being
 * rewritten is exactly the moment the supply can drop, and a half-written
 * descriptor must degrade to "no staged image", never to a plausible one.
 *
 * The record itself (o2p_desc_t) is declared in flash_map.h, beside the page
 * numbers it is stored in.
 */
#ifndef O2P_BOOT_DESC_H
#define O2P_BOOT_DESC_H

#include <stdbool.h>

#include "flash_map.h"

/* CRC-16/MODBUS over the record with its crc16 field zeroed. */
uint16_t o2p_desc_crc(const o2p_desc_t *d);

/* Structurally sound: magic, layout version and CRC. Says nothing about
 * whether the images it describes are actually there. */
bool o2p_desc_record_valid(const o2p_desc_t *d);

/* Which of two candidate records to believe. Either may be absent (`ok_*`
 * false). Returns 0 for A, 1 for B, or -1 when neither is usable.
 *
 * Pure, and separated from the flash access, because this is the function
 * that decides which of two competing truths a buried probe boots from, and
 * it is worth being able to test the wrap and the tie on a host. */
int o2p_desc_pick(const o2p_desc_t *a, bool ok_a,
                  const o2p_desc_t *b, bool ok_b);

/* An empty descriptor: nothing staged, nothing known to be installed. */
void o2p_desc_init(o2p_desc_t *d);

#ifndef O2P_HOST_TEST
/* Load the live descriptor. False (and an initialised `out`) when there is
 * none or both copies are corrupt - which is the state a probe that has never
 * been updated is in, and is not an error. */
bool o2p_desc_load(o2p_desc_t *out);

/* Write `d` to whichever page is not live, with the sequence advanced. The
 * caller supplies the content; sequence, magic, layout version and CRC are
 * filled in here so no caller can write a record that the loader would then
 * refuse. Verified by reading it back. */
bool o2p_desc_store(const o2p_desc_t *d);
#endif

#endif /* O2P_BOOT_DESC_H */
