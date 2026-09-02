/* Main-flash erase and program, shared by the application and the bootloader.
 *
 * This used to live inside config_flash.c, where it only ever wrote 32 bytes
 * of configuration. The updater writes 52 KiB of it and the bootloader copies
 * that again, so the driver is now three callers wide and belongs on its own.
 *
 * Two properties every caller depends on:
 *
 *  - Erasing or programming main flash STALLS instruction fetch on this part.
 *    A page erase is tens of milliseconds, which at 9600 baud is several
 *    character times: whatever arrives on the bus during one is lost. Callers
 *    that must stay responsive erase ONE page per call and come back.
 *  - The flash controller is left LOCKED on every exit path, including the
 *    error paths. Leaving it unlocked across a Modbus poll would put a
 *    single wild pointer between a received frame and an erased application.
 *
 * There is deliberately no watchdog feed in here. main() feeds the watchdog
 * only while the sampler is completing cycles and the RS-485 driver is not
 * stuck enabled; a feed buried in the flash driver would satisfy the watchdog
 * during exactly the jam that withheld it.
 */
#ifndef O2P_FLASH_HAL_H
#define O2P_FLASH_HAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Erase one 2 KiB page. `page` is a page index, 0..63. Returns false on any
 * controller error, or if the page index is outside the part. */
bool o2p_flash_erase_page(uint8_t page);

/* Program `len` bytes at `addr`. Both must be 8-byte aligned - the part
 * programs 64 bits at a time and a misaligned write raises PGAERR, which this
 * would report as a failure after having already written part of the data.
 * Refusing up front keeps a caller's arithmetic error from being half applied.
 *
 * The destination must be erased. Programming a non-erased doubleword raises
 * PROGERR on this family (it is not a silent AND like some NOR parts), so a
 * caller that lost track of its erase state gets an error rather than an
 * image that is a bitwise mixture of two builds. */
bool o2p_flash_program(uint32_t addr, const void *src, size_t len);

/* True if every doubleword in the page reads as erased (all ones). Used to
 * check an erase actually took, rather than trusting that it was ordered. */
bool o2p_flash_page_is_erased(uint8_t page);

#endif /* O2P_FLASH_HAL_H */
