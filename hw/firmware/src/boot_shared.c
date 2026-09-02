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
