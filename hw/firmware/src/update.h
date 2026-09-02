/* The RS-485 firmware updater: the Modbus side of getting a new image into a
 * probe that is potted, buried, and reachable only through the same twisted
 * pair that carries its readings.
 *
 * SCHEMATIC-REVIEW.md M2 required this before any probe is potted, because
 * nothing can add it afterwards. FIRMWARE.md "Field updates" works through
 * why: the STM32's ROM bootloader speaks USART1 on the right pins but never
 * drives PC6, so it would hear every command and answer none of them; J3 is
 * inside the epoxy; and no wireless path can install self-programming code
 * into an MCU that has none. An application-level updater is the only door,
 * and it has to be built in before the door is sealed.
 *
 * ONE ENGINE, TWO CALLERS. The application links this so an update can be
 * pushed while the probe is measuring, and the bootloader links the identical
 * file so an update can still be pushed when the application is broken. A
 * second implementation for the recovery case would be a second implementation
 * exercised only in the emergency it exists for.
 *
 * ---------------------------------------------------------------------------
 * The protocol, in the order a master performs it
 *
 *   1. read  0x0050        STATUS, and 0x0051 BLOCK_MAX for the block size
 *   2. write 0x0055..0x0058  declared length and CRC-32 of the image
 *      write 0x0054        CMD = BEGIN            (may be the same frame)
 *   3. poll  0x0050        until state READY - the staging slot is erased one
 *                          page per pass so the bus stays served meanwhile
 *   4. write 0x0080.. with [seq, data...] repeatedly; the response IS the ack
 *   5. write 0x0054        CMD = COMMIT, then poll 0x0050 for STAGED
 *   6. write 0x0054        CMD = BOOT - the probe resets into the bootloader,
 *                          which installs the staged image and starts it
 *
 * Nothing here needs a function code outside FC03/FC06/FC16, and every step
 * fits in 40 bytes. That is deliberate and it is the whole reason the block
 * carries its sequence number instead of streaming: the degraded path to a
 * buried probe is the Dragino's `A8` downlink, which is one arbitrary RS-485
 * frame of at most 40 bytes with a reply of a few bytes, fired at whatever
 * cadence the LoRaWAN link allows. On that path an unacknowledged, stateful
 * stream is unrecoverable and a self-addressing block is merely slow.
 *
 *   Wire  9600 8E1, FC16 with 1 + 120 registers = 240 bytes/block: ~2 min.
 *   `A8`  FC16 with 1 + 12 registers = 24 bytes/block: ceil(len/24)
 *         blocks - about 1,100 for a full image, which is days.
 *
 * The A8 figure is a fallback with a real number attached, not a plan.
 * ---------------------------------------------------------------------------
 */
#ifndef O2P_UPDATE_H
#define O2P_UPDATE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "flash_map.h"

/* ---- control block: 0x0050, 16 registers ---- */
enum {
    O2P_REG_UPD_STATUS     = 0x0050u, /* state << 8 | error; bit 15 = bootloader */
    O2P_REG_UPD_BLOCK_MAX  = 0x0051u, /* largest data-register count accepted */
    O2P_REG_UPD_SLOT_HI    = 0x0052u, /* staging slot size, bytes */
    O2P_REG_UPD_SLOT_LO    = 0x0053u,
    O2P_REG_UPD_CMD        = 0x0054u, /* write-only, magics below, reads 0 */
    O2P_REG_UPD_LEN_HI     = 0x0055u, /* declared image length, bytes */
    O2P_REG_UPD_LEN_LO     = 0x0056u,
    O2P_REG_UPD_CRC_HI     = 0x0057u, /* declared CRC-32 (zlib) of the image */
    O2P_REG_UPD_CRC_LO     = 0x0058u,
    O2P_REG_UPD_RECV_HI    = 0x0059u, /* bytes accepted into the staging slot */
    O2P_REG_UPD_RECV_LO    = 0x005Au,
    O2P_REG_UPD_NEXT_SEQ   = 0x005Bu, /* block sequence number expected next */
    O2P_REG_UPD_LOADER_VER = 0x005Cu, /* bootloader version, 0 = the app answers */
    O2P_REG_UPD_IMAGE_VER  = 0x005Du, /* version of the image now running */
    O2P_REG_UPD_INSTALLS   = 0x005Eu, /* installs this probe has taken */
    O2P_REG_UPD_RESERVED   = 0x005Fu,
};
#define O2P_REG_UPDATE_BASE  0x0050u
#define O2P_REG_UPDATE_COUNT 16u

/* ---- data window: 0x0080, 123 registers, write-only ----
 *
 * A block is [sequence, payload...]. It is a separate block from the control
 * registers, far enough away that no plausible mistyped FC16 into the config
 * or diagnostic blocks can land in it, and long enough to hold the largest
 * write Modbus allows: FC16 carries at most 123 registers, so one block is
 * one sequence word plus up to 122 payload registers. The payload must be a
 * whole number of 64-bit flash doublewords, which caps it at 120 registers =
 * 240 bytes; the 123-register window exists so the address arithmetic never
 * depends on the alignment rule.
 */
enum { O2P_REG_UPD_DATA = 0x0080u };
#define O2P_REG_UPDDATA_BASE  0x0080u
#define O2P_REG_UPDDATA_COUNT 123u
#define O2P_REG_UPD_DATA_MAX  120u  /* payload registers after the sequence word */

/* Commands, as 16-bit magics for the same reason the config block uses them:
 * every one of these is destructive, and a stray bit in a frame that happened
 * to pass CRC must not be able to erase 52 KiB or reboot a settled cell. */
#define O2P_UPD_CMD_BEGIN  0xB001u  /* erase the staging slot, start a transfer */
#define O2P_UPD_CMD_COMMIT 0xB002u  /* verify what was received */
#define O2P_UPD_CMD_BOOT   0xB003u  /* reset into the bootloader to install it */
#define O2P_UPD_CMD_ABORT  0xB004u  /* discard the transfer */
#define O2P_UPD_CMD_STAY   0xB005u  /* bootloader only: do not start the app */

/* States, the high byte of STATUS. */
enum {
    O2P_UPD_IDLE      = 0u,
    O2P_UPD_ERASING   = 1u,
    O2P_UPD_READY     = 2u,
    O2P_UPD_RECEIVING = 3u,
    O2P_UPD_VERIFYING = 4u,
    O2P_UPD_STAGED    = 5u,
    O2P_UPD_ERROR     = 6u,
};

/* Errors, the low byte of STATUS. Kept even when a later command succeeds, so
 * a master that missed a response can still find out what went wrong. */
enum {
    O2P_UPD_ERR_NONE     = 0u,
    O2P_UPD_ERR_STATE    = 1u,  /* command does not apply in this state */
    O2P_UPD_ERR_LENGTH   = 2u,  /* declared length impossible, or overrun */
    O2P_UPD_ERR_SEQUENCE = 3u,  /* block out of order; read NEXT_SEQ and resume */
    O2P_UPD_ERR_ALIGN    = 4u,  /* payload not a whole number of doublewords */
    O2P_UPD_ERR_FLASH    = 5u,  /* erase, program or read-back failed */
    O2P_UPD_ERR_CRC      = 6u,  /* the received image is not the declared one */
    O2P_UPD_ERR_IMAGE    = 7u,  /* verified, but not an image for the run slot */
    O2P_UPD_ERR_NOIMAGE  = 8u,  /* BOOT with nothing staged */
};

/* Bit 15 of STATUS: the bootloader, not the application, is answering. A
 * master that sees this knows the probe is not measuring. */
#define O2P_UPD_STATUS_LOADER 0x8000u

/* Flash and storage operations, injected rather than called directly, so the
 * engine's state machine can be tested on a host against a RAM-backed slot.
 * The target implementations are one line each over flash_hal.c. */
typedef struct {
    bool (*erase_page)(uint8_t page);
    bool (*program)(uint32_t addr, const void *src, size_t len);
    void (*read)(uint32_t addr, void *dst, size_t len);
    /* Called once, when a transfer has verified: record the staged image in
     * the boot descriptor so the bootloader will install it. */
    bool (*commit_staged)(uint32_t len, uint32_t crc);
    /* Diagnostic only: installs this probe has taken, for UPD_INSTALLS. */
    uint16_t (*install_count)(void);
} o2p_update_ops_t;

typedef struct {
    const o2p_update_ops_t *ops;
    bool     in_loader;
    uint16_t image_version;
    uint16_t loader_version;

    uint8_t  state;
    uint8_t  error;

    /* What a BEGIN would use. Writes to LEN/CRC land here and are latched
     * into declared_* only by BEGIN, so a frame that arrives mid-transfer
     * cannot move the target under a transfer already in flight. */
    uint32_t pending_len;
    uint32_t pending_crc;

    uint32_t declared_len;
    uint32_t declared_crc;
    uint32_t received;
    uint16_t next_seq;
    uint16_t last_block_bytes;

    uint8_t  erase_next;      /* next staging page to erase, as an index 0.. */
    uint32_t verify_off;      /* bytes CRC'd so far */
    uint32_t verify_crc;      /* running CRC-32 state */

    /* Set when the master asked to reboot into the bootloader. The transport
     * owner clears it: the reply has to leave the wire first, or the master
     * is left waiting on a probe that already reset. */
    bool     boot_requested;
    /* Bootloader only: the master asked it not to start the application. */
    bool     stay_requested;
} o2p_update_t;

void o2p_update_init(o2p_update_t *u, const o2p_update_ops_t *ops,
                     bool in_loader, uint16_t image_version,
                     uint16_t loader_version);

/* Called at start-up when the boot descriptor already carries a verified
 * staged image - which is what a probe looks like after a transfer that
 * finished and then lost power, or was reset, before the BOOT command. The
 * engine comes up in STAGED rather than IDLE so the master can simply issue
 * BOOT instead of pushing 23 KiB again. */
void o2p_update_adopt_staged(o2p_update_t *u, uint32_t len, uint32_t crc);

/* Modbus read/write for the 0x0050 block. Both return a Modbus exception code
 * or 0, matching o2p_mb_read_fn / o2p_mb_write_fn's contract. `addr`/`count`
 * are assumed to lie inside the block; the caller has already checked that. */
uint8_t o2p_update_read(o2p_update_t *u, uint16_t addr, uint16_t count,
                        uint16_t *out);
uint8_t o2p_update_write(o2p_update_t *u, uint16_t addr, uint16_t count,
                         const uint16_t *in);

/* Deferred work: at most one page erase, or one slice of the verify CRC, per
 * call. Returns true if there is more to do.
 *
 * Erasing the whole 52 KiB slot takes about three quarters of a second of
 * stalled instruction fetch, and a verify reads all of it. Neither may be
 * done in one go: the probe would be deaf on a shared bus for long enough for
 * the master to time out, and the watchdog is fed only when the sampler
 * completes cycles. One page at a time keeps both alive.
 *
 * Must not be called while the RS-485 transmitter is active - erasing stalls
 * the fetch that would have released DE. */
bool o2p_update_service(o2p_update_t *u);

static inline bool o2p_update_busy(const o2p_update_t *u)
{
    return u->state == O2P_UPD_ERASING || u->state == O2P_UPD_VERIFYING;
}

#endif /* O2P_UPDATE_H */
