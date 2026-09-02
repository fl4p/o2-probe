/* The one piece of the bench bridge that can be wrong without the wire
 * showing it, split out so the host tests can drive it.
 *
 * Everything else in bridge_main.c either works or is obviously dead: a frame
 * arrives or it does not, DE rises or it does not. This does arithmetic - CRC
 * placement, byte order, a bounds check on a count the caller supplies - and
 * arithmetic that is wrong here answers a diagnostic read with a plausible
 * lie, at the exact moment someone is using it to decide whether their adapter
 * or their probe is at fault.
 */
#ifndef O2P_BRIDGE_REPLY_H
#define O2P_BRIDGE_REPLY_H

#include <stddef.h>
#include <stdint.h>

/* Build the bridge's own answer to `req`, which the caller has already found
 * to be addressed to `addr`.
 *
 * `regs` is the whole readable block, `nregs` its length. `rsp` must have room
 * for 5 + 2 * nregs bytes.
 *
 * Returns the response length, or 0 when nothing may be sent - a frame too
 * short to hold a CRC, or one whose CRC does not check. Silence is the only
 * correct answer to a corrupt frame: its address byte is not trustworthy
 * either, so it is not established that it was ever meant for us.
 */
size_t o2p_bridge_reply(uint8_t addr, const uint16_t *regs, unsigned nregs,
                        const uint8_t *req, size_t n, uint8_t *rsp);

#endif /* O2P_BRIDGE_REPLY_H */
