/* The choices o2p_config_load() and o2p_config_store() make, with no flash in
 * them.
 *
 * config_flash.c reaches the flash controller and a linker-defined page map,
 * so it cannot compile on the host and had no coverage at all - which matters
 * because the decisions here are the ones that pick WHICH stored configuration
 * a probe boots on, and getting that wrong loses a calibration or the probe's
 * bus address. The two claims worth pinning are that the newer record wins
 * across a 32-bit sequence wrap, and that a write never lands on the page
 * currently holding the live record.
 */
#ifndef O2P_CONFIG_SELECT_H
#define O2P_CONFIG_SELECT_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    O2P_CFG_PICK_NONE = 0,   /* neither page holds a usable record */
    O2P_CFG_PICK_A,
    O2P_CFG_PICK_B
} o2p_cfg_pick_t;

/* Which of the two records to boot from, given whether each one parsed and
 * what sequence it carried.
 *
 * The comparison is a SIGNED difference, not `>`. Sequence is a free-running
 * u32 incremented once per commit, so an unsigned compare would pick the
 * older record for the one commit that crosses 0xFFFFFFFF. That needs four
 * billion commits to reach and costs nothing to handle correctly, which is
 * the only reason to prefer being right to being simple here. */
static inline o2p_cfg_pick_t o2p_config_pick(bool ok_a, uint32_t seq_a,
                                             bool ok_b, uint32_t seq_b)
{
    if (!ok_a && !ok_b) {
        return O2P_CFG_PICK_NONE;
    }
    if (ok_a && ok_b) {
        return ((int32_t)(seq_a - seq_b) > 0) ? O2P_CFG_PICK_A
                                              : O2P_CFG_PICK_B;
    }
    return ok_a ? O2P_CFG_PICK_A : O2P_CFG_PICK_B;
}

/* The page a store must write. Always the one NOT holding the live record, so
 * a power loss part-way through leaves the previous configuration intact and
 * still the higher sequence. */
static inline uint8_t o2p_config_other_page(uint8_t live_page,
                                            uint8_t page_a, uint8_t page_b)
{
    return (live_page == page_a) ? page_b : page_a;
}

#endif /* O2P_CONFIG_SELECT_H */
