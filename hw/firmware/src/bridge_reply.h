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

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* A write this function ACCEPTED and answered, which the caller must now carry
 * out on hardware. Kept as data rather than done here so that this file stays
 * arithmetic only and the whole decision is testable on the host.
 *
 * The reply is already built when this is set, and the caller must send it
 * BEFORE acting: the answer to "change the bus rate" has to leave at the rate
 * the master is still listening at. That is why the two are separate steps.
 */
typedef struct {
    bool     set_bus_baud;
    uint32_t bus_baud;   /* only meaningful when set_bus_baud */
} o2p_bridge_action_t;

/* The bus rates the bridge will accept, and why only these: they are exactly
 * the probe's O2P_REG_BAUD_CODE enum. A bridge that could be moved to a rate
 * no probe can be moved to would be a bridge that can talk to nothing,
 * recoverable only over the host lead. The cable's own limit is far higher --
 * the THVD1410 is rated to 500 kbps -- so the binding constraint here is the
 * other end, not the wire.
 *
 * These are keyed by POSITION, not by the probe's code: check_update_tool.py
 * compares the SET of values against o2p_update.py's BAUD_CODES, so the order
 * is free but the membership is not. 57600 added 2026-09-13 with code 4. */
#define O2P_BRIDGE_BAUD_1 9600u
#define O2P_BRIDGE_BAUD_2 19200u
#define O2P_BRIDGE_BAUD_3 38400u
#define O2P_BRIDGE_BAUD_4 115200u
#define O2P_BRIDGE_BAUD_5 57600u

/* THE LIST THE ACCEPTING BRANCH ITERATES. write_regs() and test_bridge.c both
 * read THIS, so a rate declared above but missing here cannot be accepted, and
 * nothing can be accepted that is not declared: the set check_update_tool.py
 * scrapes from the #defines and the set the firmware actually takes are the
 * same set by construction, not by anyone remembering.
 *
 * It exists because the hand-written list drifted TWICE, in both directions.
 * O2P_BRIDGE_BAUD_4 was added and test_bridge.c's loop kept covering three
 * rates, so the one test that proves a rate is reachable did not test the new
 * one (fixed then by sizing the loop from the array - which left the array
 * itself hand-written). O2P_BRIDGE_BAUD_5 was added 2026-09-13 and write_regs()
 * kept checking four: the bridge declared 57600 here, static-asserted it in
 * bridge_main.c, advertised it to the updater, and answered exception 03 to
 * anyone who wrote it. check_update_tool.py compared these DECLARATIONS against
 * the tool and reported agreement the whole time - a guard that could not see
 * the branch it was guarding. Found by the codex xhigh review of 5e163a1. */
#define O2P_BRIDGE_BAUD_LIST                                 \
    O2P_BRIDGE_BAUD_1, O2P_BRIDGE_BAUD_2, O2P_BRIDGE_BAUD_3, \
    O2P_BRIDGE_BAUD_4, O2P_BRIDGE_BAUD_5

/* Build the bridge's own answer to `req`, which the caller has already found
 * to be addressed to `addr`.
 *
 * `regs` is the whole readable block, `nregs` its length. `rsp` must have room
 * for 5 + 2 * nregs bytes.
 *
 * `act`, if given, is cleared and then filled in for a write the bridge
 * accepted. Passing NULL means the caller cannot carry an action out, and
 * every write is refused rather than answered and silently dropped -- a caller
 * that cannot act must not look like one that did.
 *
 * Returns the response length, or 0 when nothing may be sent - a frame too
 * short to hold a CRC, or one whose CRC does not check. Silence is the only
 * correct answer to a corrupt frame: its address byte is not trustworthy
 * either, so it is not established that it was ever meant for us.
 */
size_t o2p_bridge_reply(uint8_t addr, const uint16_t *regs, unsigned nregs,
                        const uint8_t *req, size_t n, uint8_t *rsp,
                        o2p_bridge_action_t *act);

#endif /* O2P_BRIDGE_REPLY_H */
