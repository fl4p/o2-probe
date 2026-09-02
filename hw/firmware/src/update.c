#include "update.h"

#include "crc32.h"
#include "modbus_pdu.h"

#include <string.h>

/* How much of the staging slot one o2p_update_service() call CRCs. One page
 * erase is tens of milliseconds of stalled fetch and sets the pace; 1 KiB of
 * CRC is under a millisecond, so this is not the expensive half - it is
 * chunked only so that a 52 KiB verify cannot become one long silence on a
 * shared bus. */
#define VERIFY_SLICE 1024u

/* SRAM bounds for the staged image's initial stack pointer. The part has
 * 36 KiB at 0x20000000; a vector table whose first word is not in there is
 * not a vector table for this MCU. */
#define SRAM_BASE_ADDR 0x20000000u
#define SRAM_BYTES     (36u * 1024u)

/* Two ways for something to go wrong, and they must not be the same way.
 *
 * `reject` refuses ONE frame and leaves the transfer where it was. A block
 * that arrives out of order, a payload that is not a whole number of
 * doublewords, a command that does not apply yet: none of these say anything
 * about the bytes already in the slot, and a master that hit one has to be
 * able to read NEXT_SEQ and carry on. An earlier version of this file sent
 * every one of them to ERROR, which made the documented resync impossible -
 * caught by test_out_of_order_block_is_refused_and_the_master_can_resync,
 * which is why it is written the way it is.
 *
 * `fail` ends the transfer. It is for the cases where the staging slot's
 * contents are no longer something the probe can reason about: a flash
 * operation that did not do what it was told, or an image that turned out not
 * to be the one that was declared.
 */
static uint8_t reject(o2p_update_t *u, uint8_t err, uint8_t exception)
{
    u->error = err;
    return exception;
}

static void fail(o2p_update_t *u, uint8_t err)
{
    u->state = O2P_UPD_ERROR;
    u->error = err;
}

void o2p_update_init(o2p_update_t *u, const o2p_update_ops_t *ops,
                     bool in_loader, uint16_t image_version,
                     uint16_t loader_version)
{
    memset(u, 0, sizeof(*u));
    u->ops = ops;
    u->in_loader = in_loader;
    u->image_version = image_version;
    u->loader_version = loader_version;
    u->state = O2P_UPD_IDLE;
    u->error = O2P_UPD_ERR_NONE;
}

void o2p_update_adopt_staged(o2p_update_t *u, uint32_t len, uint32_t crc)
{
    /* Trusted only as far as the descriptor is: the image itself is verified
     * again by the bootloader before it installs anything, so adopting a
     * length and a CRC here cannot cause a bad image to be installed - it can
     * only cause a BOOT that the bootloader then declines. */
    if (len < O2P_IMAGE_MIN_BYTES || len > O2P_STAGE_BYTES ||
        (len % O2P_IMAGE_ALIGN) != 0u) {
        return;
    }
    u->declared_len = len;
    u->declared_crc = crc;
    u->pending_len = len;
    u->pending_crc = crc;
    u->received = len;
    u->state = O2P_UPD_STAGED;
    u->error = O2P_UPD_ERR_NONE;
}

/* ------------------------------------------------------------------ reads */

static uint16_t read_reg(const o2p_update_t *u, uint16_t a)
{
    switch (a) {
    case O2P_REG_UPD_STATUS:
        return (uint16_t)(((uint16_t)u->state << 8) | u->error |
                          (u->in_loader ? O2P_UPD_STATUS_LOADER : 0u));
    case O2P_REG_UPD_BLOCK_MAX:  return O2P_REG_UPD_DATA_MAX;
    case O2P_REG_UPD_SLOT_HI:    return (uint16_t)(O2P_STAGE_BYTES >> 16);
    case O2P_REG_UPD_SLOT_LO:    return (uint16_t)(O2P_STAGE_BYTES & 0xFFFFu);
    /* The command register reads as zero: it is an edge, not state. Reading
     * back the last command would suggest one is pending when none is. */
    case O2P_REG_UPD_CMD:        return 0u;
    /* LEN and CRC read back what the NEXT begin would use, which during a
     * transfer is what the current one is using - they are latched at BEGIN
     * and cannot be moved under a transfer in flight. */
    case O2P_REG_UPD_LEN_HI:     return (uint16_t)(u->pending_len >> 16);
    case O2P_REG_UPD_LEN_LO:     return (uint16_t)(u->pending_len & 0xFFFFu);
    case O2P_REG_UPD_CRC_HI:     return (uint16_t)(u->pending_crc >> 16);
    case O2P_REG_UPD_CRC_LO:     return (uint16_t)(u->pending_crc & 0xFFFFu);
    case O2P_REG_UPD_RECV_HI:    return (uint16_t)(u->received >> 16);
    case O2P_REG_UPD_RECV_LO:    return (uint16_t)(u->received & 0xFFFFu);
    case O2P_REG_UPD_NEXT_SEQ:   return u->next_seq;
    case O2P_REG_UPD_LOADER_VER: return u->loader_version;
    case O2P_REG_UPD_IMAGE_VER:  return u->image_version;
    case O2P_REG_UPD_INSTALLS:
        return (u->ops != NULL && u->ops->install_count != NULL)
                   ? u->ops->install_count() : 0u;
    default:                     return 0u;
    }
}

uint8_t o2p_update_read(o2p_update_t *u, uint16_t addr, uint16_t count,
                        uint16_t *out)
{
    if (u == NULL || out == NULL || count == 0u) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
    for (uint16_t i = 0; i < count; i++) {
        uint16_t a = (uint16_t)(addr + i);
        /* The data window is write-only and reads as zero rather than as the
         * staging slot. Exposing 52 KiB of flash through a read window would
         * make the probe a way to read back an image it was told to accept,
         * which is a capability nothing needs and one more thing to get
         * wrong; the CRC is how a transfer is checked. */
        out[i] = (a >= O2P_REG_UPDDATA_BASE) ? 0u : read_reg(u, a);
    }
    return 0u;
}

/* ----------------------------------------------------------------- writes */

static uint8_t cmd_begin(o2p_update_t *u)
{
    if (u->state == O2P_UPD_ERASING || u->state == O2P_UPD_VERIFYING) {
        return reject(u, O2P_UPD_ERR_STATE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (u->pending_len < O2P_IMAGE_MIN_BYTES ||
        u->pending_len > O2P_STAGE_BYTES ||
        (u->pending_len % O2P_IMAGE_ALIGN) != 0u) {
        return reject(u, O2P_UPD_ERR_LENGTH, O2P_MB_EX_ILLEGAL_VALUE);
    }
    /* Retract any previously staged image BEFORE the slot that holds it is
     * erased. Otherwise a power loss between here and the end of the transfer
     * leaves a descriptor that says "a verified image is staged" pointing at a
     * slot that is half erased. The bootloader would re-verify and refuse it,
     * so this is belt and braces - but the belt is one flash record and the
     * braces are the only thing standing between a buried probe and an
     * install of rubbish. */
    if (u->ops == NULL || u->ops->commit_staged == NULL ||
        !u->ops->commit_staged(0u, 0u)) {
        fail(u, O2P_UPD_ERR_FLASH);
        return O2P_MB_EX_DEVICE_FAILURE;
    }

    u->declared_len = u->pending_len;
    u->declared_crc = u->pending_crc;
    u->received = 0u;
    u->next_seq = 0u;
    u->last_block_bytes = 0u;
    u->erase_next = 0u;
    u->verify_off = 0u;
    u->verify_crc = O2P_CRC32_INIT;
    u->state = O2P_UPD_ERASING;
    u->error = O2P_UPD_ERR_NONE;
    return 0u;
}

static uint8_t cmd_commit(o2p_update_t *u)
{
    if (u->state != O2P_UPD_RECEIVING) {
        return reject(u, O2P_UPD_ERR_STATE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (u->received != u->declared_len) {
        /* Short of the declared length. This is the case that must not be
         * allowed to "pass with what arrived": a truncated image whose CRC is
         * computed over only the bytes received would verify perfectly and
         * install a half firmware.
         *
         * A reject, not a failure: the blocks already in the slot are still
         * good and the master can simply send the rest. */
        return reject(u, O2P_UPD_ERR_LENGTH, O2P_MB_EX_ILLEGAL_VALUE);
    }
    u->verify_off = 0u;
    u->verify_crc = O2P_CRC32_INIT;
    u->state = O2P_UPD_VERIFYING;
    u->error = O2P_UPD_ERR_NONE;
    return 0u;
}

static uint8_t cmd_boot(o2p_update_t *u)
{
    if (u->in_loader) {
        /* In the bootloader there is nothing to reset into: it installs what
         * is staged as part of starting up. Refuse rather than reset, so a
         * master running the same script in both places does not spin. */
        return reject(u, O2P_UPD_ERR_STATE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (u->state != O2P_UPD_STAGED) {
        /* Nothing staged: a reset would cost the cell another 15 minutes of
         * settling and install nothing. */
        return reject(u, O2P_UPD_ERR_NOIMAGE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    u->boot_requested = true;
    return 0u;
}

static uint8_t cmd_abort(o2p_update_t *u)
{
    if (u->state == O2P_UPD_ERASING || u->state == O2P_UPD_VERIFYING) {
        /* Both are mid-flash-operation. Aborting there would leave the engine
         * and the flash disagreeing about what is erased. */
        return reject(u, O2P_UPD_ERR_STATE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (u->state == O2P_UPD_STAGED) {
        if (u->ops == NULL || u->ops->commit_staged == NULL ||
            !u->ops->commit_staged(0u, 0u)) {
            fail(u, O2P_UPD_ERR_FLASH);
            return O2P_MB_EX_DEVICE_FAILURE;
        }
    }
    u->state = O2P_UPD_IDLE;
    u->error = O2P_UPD_ERR_NONE;
    u->received = 0u;
    u->next_seq = 0u;
    u->last_block_bytes = 0u;
    u->boot_requested = false;
    return 0u;
}

/* STAY means the same thing in both images, from opposite sides: end up in
 * the bootloader with the application NOT running.
 *
 * In the loader it is the knock that keeps it in service mode instead of
 * starting the application - the only way back into a probe whose application
 * is valid enough to boot and too broken to answer.
 *
 * In the application it is the deliberate version of the same thing: reset
 * into the loader and stay there. A technician pushing an image over a cable
 * to a probe whose sampler is misbehaving does not have to fight it for the
 * bus.
 */
static uint8_t cmd_stay(o2p_update_t *u)
{
    u->stay_requested = true;
    if (!u->in_loader) {
        u->boot_requested = true;
    }
    return 0u;
}

static uint8_t write_control(o2p_update_t *u, uint16_t addr, uint16_t count,
                             const uint16_t *in)
{
    /* Two passes, so one frame can carry the length, the CRC and BEGIN
     * regardless of the order the addresses fall in. The command register
     * sits at 0x0054, BELOW the length and CRC it consumes; applying the
     * frame in address order would run BEGIN against the previous transfer's
     * numbers. That single frame is what makes an `A8` downlink able to start
     * a transfer at all, so the ordering is not a convenience. */
    uint16_t cmd = 0u;
    bool have_cmd = false;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t a = (uint16_t)(addr + i);
        uint16_t v = in[i];
        switch (a) {
        case O2P_REG_UPD_CMD:
            cmd = v;
            have_cmd = true;
            break;
        case O2P_REG_UPD_LEN_HI:
            u->pending_len = ((uint32_t)v << 16) | (u->pending_len & 0xFFFFu);
            break;
        case O2P_REG_UPD_LEN_LO:
            u->pending_len = (u->pending_len & 0xFFFF0000u) | v;
            break;
        case O2P_REG_UPD_CRC_HI:
            u->pending_crc = ((uint32_t)v << 16) | (u->pending_crc & 0xFFFFu);
            break;
        case O2P_REG_UPD_CRC_LO:
            u->pending_crc = (u->pending_crc & 0xFFFF0000u) | v;
            break;
        default:
            /* Everything else in the block is status. Refusing beats ignoring:
             * a master that believes it set RECV or NEXT_SEQ has a model of
             * the transfer that the probe does not share. */
            return O2P_MB_EX_ILLEGAL_ADDRESS;
        }
    }

    if (!have_cmd) {
        return 0u;
    }
    switch (cmd) {
    case O2P_UPD_CMD_BEGIN:  return cmd_begin(u);
    case O2P_UPD_CMD_COMMIT: return cmd_commit(u);
    case O2P_UPD_CMD_BOOT:   return cmd_boot(u);
    case O2P_UPD_CMD_ABORT:  return cmd_abort(u);
    case O2P_UPD_CMD_STAY:   return cmd_stay(u);
    default:
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
}

static uint8_t write_data(o2p_update_t *u, uint16_t addr, uint16_t count,
                          const uint16_t *in)
{
    /* A block must start at the window base. Its position in the image comes
     * from the sequence number, not from the register address, and a master
     * that writes at an offset has a different protocol in mind than this one
     * implements. */
    if (addr != O2P_REG_UPDDATA_BASE) {
        return O2P_MB_EX_ILLEGAL_ADDRESS;
    }
    if (u->state != O2P_UPD_READY && u->state != O2P_UPD_RECEIVING) {
        return reject(u, O2P_UPD_ERR_STATE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (count < 2u) {
        return reject(u, O2P_UPD_ERR_LENGTH, O2P_MB_EX_ILLEGAL_VALUE);
    }

    const uint16_t seq = in[0];
    const uint32_t payload = (uint32_t)(count - 1u) * 2u;

    if ((payload % O2P_IMAGE_ALIGN) != 0u || payload > (O2P_REG_UPD_DATA_MAX * 2u)) {
        return reject(u, O2P_UPD_ERR_ALIGN, O2P_MB_EX_ILLEGAL_VALUE);
    }

    /* An exact repeat of the block just accepted is an ACK that got lost on
     * the way back, not an error: acknowledge it again and program nothing.
     * Without this a master on the `A8` path - where a lost reply is routine -
     * has no way to distinguish "not received" from "received, reply lost",
     * and would either skip a block or double-write one.
     *
     * The length must match too. A retry that carries a different number of
     * bytes under the same sequence number is not a retry. */
    if (u->next_seq > 0u && seq == (uint16_t)(u->next_seq - 1u)) {
        if (payload != u->last_block_bytes) {
            return reject(u, O2P_UPD_ERR_SEQUENCE, O2P_MB_EX_ILLEGAL_VALUE);
        }
        return 0u;
    }
    if (seq != u->next_seq) {
        return reject(u, O2P_UPD_ERR_SEQUENCE, O2P_MB_EX_ILLEGAL_VALUE);
    }
    if (payload > u->declared_len - u->received) {
        return reject(u, O2P_UPD_ERR_LENGTH, O2P_MB_EX_ILLEGAL_VALUE);
    }

    /* Registers are big-endian on the wire and the image is a byte stream, so
     * the payload is serialised explicitly. memcpy of the uint16_t array would
     * work only by accident of this MCU's endianness and would silently
     * byte-swap every image if this ever ran anywhere else. */
    uint8_t buf[O2P_REG_UPD_DATA_MAX * 2u];
    for (uint16_t i = 0; i < count - 1u; i++) {
        buf[i * 2u]      = (uint8_t)(in[i + 1u] >> 8);
        buf[i * 2u + 1u] = (uint8_t)(in[i + 1u] & 0xFFu);
    }

    if (u->ops == NULL || u->ops->program == NULL ||
        !u->ops->program(O2P_STAGE_BASE + u->received, buf, payload)) {
        fail(u, O2P_UPD_ERR_FLASH);
        return O2P_MB_EX_DEVICE_FAILURE;
    }

    u->received += payload;
    u->last_block_bytes = (uint16_t)payload;
    u->next_seq++;
    u->state = O2P_UPD_RECEIVING;
    u->error = O2P_UPD_ERR_NONE;
    return 0u;
}

uint8_t o2p_update_write(o2p_update_t *u, uint16_t addr, uint16_t count,
                         const uint16_t *in)
{
    if (u == NULL || in == NULL || count == 0u) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
    if (addr >= O2P_REG_UPDDATA_BASE) {
        return write_data(u, addr, count, in);
    }
    return write_control(u, addr, count, in);
}

/* --------------------------------------------------------- deferred work */

/* Does the staged image look like something that can run FROM THE RUN SLOT?
 *
 * This is the check that catches the mistake nobody expects to make and
 * everybody eventually makes: pushing firmware.bin from the bootloader build,
 * or from a build still linked at 0x08000000. Such an image has a perfectly
 * good CRC. It would install, and its reset vector would point into the
 * bootloader's own pages, so the probe would come up running whatever happens
 * to be there. A CRC proves the bytes arrived; only the vector table says
 * they are the right bytes for this slot. */
static bool image_plausible(o2p_update_t *u)
{
    uint32_t vec[2];
    u->ops->read(O2P_STAGE_BASE, vec, sizeof(vec));

    const uint32_t msp = vec[0];
    const uint32_t reset = vec[1];

    if (msp < SRAM_BASE_ADDR || msp > SRAM_BASE_ADDR + SRAM_BYTES) {
        return false;
    }
    /* Thumb state: every reset vector on a Cortex-M has bit 0 set. */
    if ((reset & 1u) == 0u) {
        return false;
    }
    const uint32_t entry = reset & ~1u;
    if (entry < O2P_APP_BASE || entry >= O2P_APP_BASE + u->declared_len) {
        return false;
    }
    return true;
}

bool o2p_update_service(o2p_update_t *u)
{
    if (u == NULL || u->ops == NULL) {
        return false;
    }

    if (u->state == O2P_UPD_ERASING) {
        if (u->ops->erase_page == NULL ||
            !u->ops->erase_page((uint8_t)(O2P_STAGE_PAGE + u->erase_next))) {
            fail(u, O2P_UPD_ERR_FLASH);
            return false;
        }
        u->erase_next++;
        if (u->erase_next >= O2P_STAGE_PAGES) {
            u->state = O2P_UPD_READY;
            return false;
        }
        return true;
    }

    if (u->state == O2P_UPD_VERIFYING) {
        uint8_t buf[128];
        uint32_t done = 0u;
        while (done < VERIFY_SLICE && u->verify_off < u->declared_len) {
            uint32_t n = u->declared_len - u->verify_off;
            if (n > sizeof(buf)) {
                n = sizeof(buf);
            }
            u->ops->read(O2P_STAGE_BASE + u->verify_off, buf, n);
            u->verify_crc = o2p_crc32_update(u->verify_crc, buf, n);
            u->verify_off += n;
            done += n;
        }
        if (u->verify_off < u->declared_len) {
            return true;
        }
        if (o2p_crc32_final(u->verify_crc) != u->declared_crc) {
            fail(u, O2P_UPD_ERR_CRC);
            return false;
        }
        if (!image_plausible(u)) {
            fail(u, O2P_UPD_ERR_IMAGE);
            return false;
        }
        if (u->ops->commit_staged == NULL ||
            !u->ops->commit_staged(u->declared_len, u->declared_crc)) {
            fail(u, O2P_UPD_ERR_FLASH);
            return false;
        }
        u->state = O2P_UPD_STAGED;
        u->error = O2P_UPD_ERR_NONE;
        return false;
    }

    return false;
}
