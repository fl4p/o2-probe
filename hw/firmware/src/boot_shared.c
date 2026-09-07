#include "flash_map.h"

/* The one object both images agree on the address of.
 *
 * `.shared` is a NOLOAD section at the very bottom of SRAM in both linker
 * scripts, outside the region startup zeroes, so the value survives a warm
 * reset. Placed by the linker rather than by a pointer cast to a hard-coded
 * address, so a change to the SRAM layout moves it in both images at once -
 * and if it ever fails to, the map file says so.
 *
 * `used` keeps it through -ffunction-sections/--gc-sections, which would
 * otherwise drop an object nothing in this translation unit references.
 */
o2p_bootreq_t g_o2p_bootreq __attribute__((section(".shared"), used));

/* Second object in the SAME section, so the linker gives it the same offset in
 * both images: .shared has exactly one contributing translation unit and the
 * two definitions are in a fixed order within it. SHARED is 16 bytes and these
 * two structures are 8 each, which the static assert below holds to. */
/* .shared.info, NOT .shared: within one input section the linker is free to
 * order objects as it likes, and it put this one FIRST - which moved
 * g_o2p_bootreq to +8 while the v0 bootloader already in the field still
 * reads the boot request at the base of SHARED. That mismatch does not fail
 * loudly: the old loader would read this struct as a boot request, and a
 * value that happened to match O2P_BOOTREQ_STAY would strand a potted probe
 * in the bootloader with no way back. A separate input section, placed after
 * .shared in every linker script, pins the order instead of hoping for it. */
o2p_bootinfo_t g_o2p_bootinfo __attribute__((section(".shared.info"), used));

_Static_assert(sizeof(g_o2p_bootreq) + sizeof(g_o2p_bootinfo) <= 16u,
               "SHARED region is 16 bytes in both linker scripts");
