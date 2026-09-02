#include "bridge_mailbox.h"

#include <string.h>

/* The host build compiles this file for its two pure guards only; Mach-O has
 * no ".mailbox" and the placement is meaningless off the target anyway. What
 * must not happen is the target build losing the attribute silently, so the
 * address is checked in the ELF by tools/pio_image_check.py rather than
 * trusted here. */
#ifdef O2P_HOST_TEST
o2p_mailbox_t g_o2p_mailbox;
#else
o2p_mailbox_t g_o2p_mailbox __attribute__((section(".mailbox"), used));
#endif

void o2p_mailbox_init(void)
{
    memset((void *)&g_o2p_mailbox, 0, sizeof(g_o2p_mailbox));
    g_o2p_mailbox.version = O2P_MBX_VERSION;
    g_o2p_mailbox.reply_ms = O2P_MBX_REPLY_MS_DEFAULT;
    /* Magic last, for the same reason the sequence words are written last:
     * a host that finds the magic has found a mailbox that is fully set up. */
    g_o2p_mailbox.magic = O2P_MBX_MAGIC;
}

bool o2p_mailbox_len_ok(uint32_t len)
{
    return len >= 4u && len <= (uint32_t)O2P_MB_MAX_ADU;
}

uint32_t o2p_mailbox_reply_window(uint32_t asked_ms)
{
    if (asked_ms == 0u) {
        return O2P_MBX_REPLY_MS_DEFAULT;
    }
    return asked_ms > O2P_MBX_REPLY_MS_MAX ? O2P_MBX_REPLY_MS_MAX : asked_ms;
}
