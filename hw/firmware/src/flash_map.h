/* The one place that says where anything lives in the STM32G071CB's flash.
 *
 * Three images share this part - the bootloader, the running application and
 * a staged application that has been pushed over RS-485 but not yet installed
 * - plus two record areas. Every one of those boundaries is load-bearing in a
 * way that cannot be checked at runtime by the code that gets it wrong: a
 * linker script that lets the application grow into the staging slot produces
 * a probe that erases itself the first time someone updates it, and nothing
 * before that moment looks unusual. So the numbers live here once, the two
 * linker scripts are derived from them by hand, and tools/check_flash_map.py
 * fails the build when the scripts and this header disagree.
 *
 * Layout (128 KiB, 64 pages of 2 KiB):
 *
 *   page  0..7    0x08000000  16 KiB  bootloader        NEVER rewritten
 *   page  8..33   0x08004000  52 KiB  run slot          the application
 *   page 34..59   0x08011000  52 KiB  staging slot      received image
 *   page 60..61   0x0801E000   4 KiB  boot descriptor   A/B
 *   page 62..63   0x0801F000   4 KiB  configuration     A/B (config_flash.c)
 *
 * Why a staging slot rather than writing the run slot directly: the probe is
 * potted and buried, and a power interruption is the ordinary case, not the
 * exotic one - the farm supply is a 12 V feed shared with a LoRaWAN node on a
 * mast. Downloading over the running image means every transfer has a window,
 * minutes wide, in which a brownout leaves no application at all. Downloading
 * beside it means the worst case is a wasted transfer.
 *
 * Why not two equal slots with a boot-time choice (true A/B): that needs the
 * application to be position-independent or built twice, once per slot. The
 * copy this design does instead costs ~2 s at install time, once, and keeps
 * ONE application binary that is always linked at one address. Nothing else
 * in this firmware would survive being built two ways without being tested
 * two ways.
 */
#ifndef O2P_FLASH_MAP_H
#define O2P_FLASH_MAP_H

#include <stddef.h>
#include <stdint.h>

#define O2P_FLASH_ORIGIN     0x08000000u
#define O2P_FLASH_PAGE_BYTES 2048u
#define O2P_FLASH_PAGES      64u

#define O2P_BOOT_PAGE      0u
#define O2P_BOOT_PAGES     8u
#define O2P_APP_PAGE       8u
#define O2P_APP_PAGES      26u
#define O2P_STAGE_PAGE     34u
#define O2P_STAGE_PAGES    26u
#define O2P_DESC_PAGE_A    60u
#define O2P_DESC_PAGE_B    61u
/* 62 and 63 are config_flash.c's A/B pages. Named here so this map is the
 * complete picture and an attempt to reuse them shows up as a conflict. */
#define O2P_CONFIG_PAGE_A  62u
#define O2P_CONFIG_PAGE_B  63u

#define O2P_PAGE_ADDR(pg)  (O2P_FLASH_ORIGIN + (uint32_t)(pg) * O2P_FLASH_PAGE_BYTES)

#define O2P_BOOT_BASE   O2P_PAGE_ADDR(O2P_BOOT_PAGE)
#define O2P_BOOT_BYTES  (O2P_BOOT_PAGES * O2P_FLASH_PAGE_BYTES)
#define O2P_APP_BASE    O2P_PAGE_ADDR(O2P_APP_PAGE)
#define O2P_APP_BYTES   (O2P_APP_PAGES * O2P_FLASH_PAGE_BYTES)
#define O2P_STAGE_BASE  O2P_PAGE_ADDR(O2P_STAGE_PAGE)
#define O2P_STAGE_BYTES (O2P_STAGE_PAGES * O2P_FLASH_PAGE_BYTES)

/* An image smaller than a vector table plus a handful of instructions is not
 * an image; refusing it early keeps a truncated transfer from ever reaching
 * the CRC stage, where it would merely fail more expensively. */
#define O2P_IMAGE_MIN_BYTES 256u

/* Flash is programmed 64 bits at a time on this family, so every length and
 * offset the updater handles is a multiple of 8. The final block of an image
 * is padded to that boundary; the padding is inside the declared length, so
 * the CRC covers it and both sides compute the same number. */
#define O2P_IMAGE_ALIGN 8u

/* --- what the bootloader hands to the application, and back --------------
 *
 * One word of RAM that survives a warm reset, at a fixed address in BOTH
 * images (see the SHARED region in the linker scripts). It is how the
 * application says "reset into the bootloader and stay there" without a wire.
 *
 * It is guarded by a value and its complement rather than a single magic,
 * because after a power-on reset this word holds whatever the SRAM powered up
 * to. A single 32-bit magic would be forged by chance about once in four
 * billion boots, which sounds safe until you remember what it would do:
 * strand a buried probe in a bootloader that never starts the application.
 * Two words that must be exact complements make it 2^-64 and the check costs
 * one comparison. */
#define O2P_BOOTREQ_STAY  0x5052424Cu  /* "PRBL" - stay in the bootloader */
#define O2P_BOOTREQ_NONE  0u

typedef struct {
    volatile uint32_t request;
    volatile uint32_t inverse;
} o2p_bootreq_t;

/* Defined by boot_shared.c in both images, placed by the linker at the base
 * of the SHARED region. */
extern o2p_bootreq_t g_o2p_bootreq;

static inline int o2p_bootreq_is(uint32_t what)
{
    return g_o2p_bootreq.request == what && g_o2p_bootreq.inverse == ~what;
}

static inline void o2p_bootreq_set(uint32_t what)
{
    g_o2p_bootreq.request = what;
    g_o2p_bootreq.inverse = ~what;
}

static inline void o2p_bootreq_clear(void)
{
    /* Deliberately NOT the complement pair: cleared means "no request", and
     * writing a valid pair for O2P_BOOTREQ_NONE would make zeroed RAM - the
     * commonest random state there is - indistinguishable from a deliberate
     * clear. Nothing reads NONE as a request, so it only has to fail the
     * STAY test, which an all-zero word does. */
    g_o2p_bootreq.request = 0u;
    g_o2p_bootreq.inverse = 0u;
}

/* --- reset cause handed across the loader/application boundary ---------
 *
 * RCC_CSR's reset flags are sticky and o2p_clock_init() clears them with RMVF
 * so the NEXT reset cannot be read as whatever happened last time. The
 * bootloader runs that same init first (loader_main.c calls o2p_clock_init),
 * so by the time the application calls it the flags are already gone and
 * RESET_CAUSE published 0 - "no flags set" - for every reset the probe has
 * ever had. Zero is indistinguishable from a brownout there, which is exactly
 * the question a buried probe gets asked.
 *
 * So whoever latches a NON-EMPTY set of flags parks them here, and whoever
 * finds the register empty adopts them and clears the slot. With both images
 * updated the application sees what the loader latched. With an OLD loader -
 * and the loader is flashed over SWD before potting, so most probes will never
 * get a new one - nothing is ever parked, the slot stays cleared from the
 * previous boot's adoption, and RESET_CAUSE reads the UNKNOWN sentinel instead
 * of a confident zero. Honest beats plausible.
 *
 * The complement pair is the same trick as the boot request: this lives in a
 * NOLOAD section, so on a cold boot it holds whatever the SRAM powered up
 * with, and an all-zero word must not validate.
 */
typedef struct {
    volatile uint32_t cause;
    volatile uint32_t inverse;
} o2p_bootinfo_t;

extern o2p_bootinfo_t g_o2p_bootinfo;

/* Bits that can actually be set in (RCC_CSR >> 24) on STM32G0. The flags live
 * at CSR bits 25..31 (stm32g071xx.h: OBLRSTF 25, PINRSTF 26, PWRRSTF 27,
 * SFTRSTF 28, IWDGRSTF 29, WWDGRSTF 30, LPWRRSTF 31), so after the shift they
 * are bits 1..7 and bit 0 is never set. Nothing else is a reset flag, so
 * nothing else is a cause - and restricting the domain is what stops a cold boot from adopting
 * random SRAM. A v0 bootloader parks nothing, so on a cold boot these bytes
 * hold whatever the RAM powered up with; the complement pair alone leaves a
 * 1-in-2^32 chance of a garbage word validating, and SRAM power-up patterns
 * are not independent random bits. Out-of-domain values are refused, which
 * turns that residue into UNKNOWN instead of a plausible cause. */
#define O2P_RESET_CAUSE_MASK 0xFEu

static inline int o2p_bootinfo_get(uint32_t *out)
{
    uint32_t c = g_o2p_bootinfo.cause;
    if (c == 0u || g_o2p_bootinfo.inverse != ~c) {
        return 0;
    }
    if ((c & ~(uint32_t)O2P_RESET_CAUSE_MASK) != 0u) {
        return 0;
    }
    if (out != NULL) {
        *out = c;
    }
    return 1;
}

static inline void o2p_bootinfo_set(uint32_t cause)
{
    g_o2p_bootinfo.cause = cause;
    g_o2p_bootinfo.inverse = ~cause;
}

static inline void o2p_bootinfo_clear(void)
{
    g_o2p_bootinfo.cause = 0u;
    g_o2p_bootinfo.inverse = 0u;
}

/* --- the boot descriptor -------------------------------------------------
 *
 * Written by the application when a transfer verifies, read by the bootloader
 * at every reset, rewritten by the bootloader when an install completes. It
 * is the only thing that makes an image in the staging slot different from
 * 52 KiB of leftovers from the last transfer.
 *
 * Field order gives the struct no implicit padding: it is CRC'd byte for byte
 * and written to flash byte for byte, and a padding byte the compiler is free
 * to leave uninitialised would make the CRC non-deterministic. Same reasoning,
 * and the same failure, as config_flash.c's record.
 */
#define O2P_DESC_MAGIC          0x4F32444Du  /* "O2DM" */
#define O2P_DESC_LAYOUT_VERSION 1u

/* Bits in o2p_desc_t.flags. */
#define O2P_DESC_F_STAGED 0x0001u  /* the staging slot holds a verified image */

typedef struct {
    uint32_t magic;
    uint32_t sequence;         /* higher wins, compared as a signed difference */
    uint32_t staged_len;
    uint32_t staged_crc;       /* CRC-32 (zlib) over staged_len bytes */
    uint32_t installed_len;
    uint32_t installed_crc;
    uint16_t layout_version;
    uint16_t flags;
    uint16_t install_count;    /* diagnostic: installs this probe has taken */
    uint16_t crc16;            /* CRC-16/MODBUS over the record with crc16 = 0 */
} o2p_desc_t;

#define O2P_DESC_BYTES 32u

#endif /* O2P_FLASH_MAP_H */
