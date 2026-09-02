/* Host tests for the RS-485 firmware updater.
 *
 * The engine runs against a RAM-backed staging slot here, which is the only
 * place its failure paths can be exercised: on the probe, "what happens when
 * the CRC is wrong" costs a flash cycle and "what happens when power drops
 * mid-transfer" costs a bench session. Everything in update.c that decides
 * whether an image is installable is tested from this file.
 *
 * The shape of the suite follows the guard-review checklist in
 * ~/.claude/CLAUDE.md: unevaluable input must not read as OK, a worse input
 * must not flip the verdict back to pass, and the known-bad case is built and
 * observed to fail rather than assumed to.
 *
 *   pio test -e native
 */
#include <unity.h>

#include <string.h>

#include "boot_desc.h"
#include "crc32.h"
#include "flash_map.h"
#include "modbus_pdu.h"
#include "update.h"

/* ------------------------------------------------------- the fake flash */

static uint8_t g_stage[O2P_STAGE_BYTES];
static bool g_program_fails;
static uint32_t g_committed_len, g_committed_crc;
static unsigned g_commit_calls;
static bool g_commit_fails;

static bool fake_erase(uint8_t page)
{
    if (page < O2P_STAGE_PAGE || page >= O2P_STAGE_PAGE + O2P_STAGE_PAGES) {
        return false;
    }
    memset(&g_stage[(page - O2P_STAGE_PAGE) * O2P_FLASH_PAGE_BYTES], 0xFF,
           O2P_FLASH_PAGE_BYTES);
    return true;
}

static bool fake_program(uint32_t addr, const void *src, size_t len)
{
    if (g_program_fails) {
        return false;
    }
    if (addr < O2P_STAGE_BASE || addr + len > O2P_STAGE_BASE + O2P_STAGE_BYTES) {
        return false;
    }
    if ((addr % 8u) != 0u || (len % 8u) != 0u) {
        return false;
    }
    /* The real part raises PROGERR on a non-erased doubleword. Modelling that
     * is the point: a test flash that quietly accepts a second write would
     * hide exactly the bug where a block is programmed twice. */
    for (size_t i = 0; i < len; i++) {
        if (g_stage[addr - O2P_STAGE_BASE + i] != 0xFFu) {
            return false;
        }
    }
    memcpy(&g_stage[addr - O2P_STAGE_BASE], src, len);
    return true;
}

static void fake_read(uint32_t addr, void *dst, size_t len)
{
    memcpy(dst, &g_stage[addr - O2P_STAGE_BASE], len);
}

static bool fake_commit(uint32_t len, uint32_t crc)
{
    g_commit_calls++;
    if (g_commit_fails) {
        return false;
    }
    g_committed_len = len;
    g_committed_crc = crc;
    return true;
}

static uint16_t fake_installs(void) { return 7u; }

static const o2p_update_ops_t k_ops = {
    .erase_page = fake_erase,
    .program = fake_program,
    .read = fake_read,
    .commit_staged = fake_commit,
    .install_count = fake_installs,
};

static o2p_update_t u;

void setUp(void)
{
    memset(g_stage, 0x5A, sizeof(g_stage));   /* not erased, not an image */
    g_program_fails = false;
    g_commit_fails = false;
    g_commit_calls = 0u;
    g_committed_len = 0xDEADBEEFu;
    g_committed_crc = 0xDEADBEEFu;
    o2p_update_init(&u, &k_ops, false, 0x0001u, 0u);
}

void tearDown(void) {}

/* ---------------------------------------------------------- the fixtures */

#define IMG_BYTES 512u
static uint8_t g_img[IMG_BYTES];

/* A byte image that looks like a real application: a vector table whose first
 * word is a stack pointer in SRAM and whose second is a reset vector inside
 * the RUN slot, with the Thumb bit set. */
static void make_image(uint32_t entry)
{
    for (unsigned i = 0; i < IMG_BYTES; i++) {
        g_img[i] = (uint8_t)(i * 7u + 3u);
    }
    const uint32_t msp = 0x20009000u;
    memcpy(&g_img[0], &msp, 4);
    memcpy(&g_img[4], &entry, 4);
}

static uint16_t status(void)
{
    uint16_t v = 0u;
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_read(&u, O2P_REG_UPD_STATUS, 1, &v));
    return v;
}

static uint8_t state(void) { return (uint8_t)(status() >> 8); }
static uint8_t error(void) { return (uint8_t)(status() & 0xFFu); }

static uint32_t received(void)
{
    uint16_t v[2];
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_read(&u, O2P_REG_UPD_RECV_HI, 2, v));
    return ((uint32_t)v[0] << 16) | v[1];
}

/* One frame carrying length, CRC and BEGIN, in the address order they occupy
 * - which puts the command BEFORE the numbers it consumes. This is the frame
 * an `A8` downlink can actually send, and the ordering is the trap. */
static uint8_t begin(uint32_t len, uint32_t crc)
{
    uint16_t regs[5];
    regs[0] = O2P_UPD_CMD_BEGIN;                 /* 0x0054 */
    regs[1] = (uint16_t)(len >> 16);             /* 0x0055 */
    regs[2] = (uint16_t)(len & 0xFFFFu);
    regs[3] = (uint16_t)(crc >> 16);
    regs[4] = (uint16_t)(crc & 0xFFFFu);
    return o2p_update_write(&u, O2P_REG_UPD_CMD, 5, regs);
}

static void run_to_completion(void)
{
    /* Bounded: 26 pages plus a verify, never thousands of passes. A test that
     * spun here would hang rather than fail. */
    for (unsigned i = 0; i < 1000u && o2p_update_service(&u); i++) {
    }
}

static uint8_t send_block(uint16_t seq, const uint8_t *bytes, uint16_t nbytes)
{
    uint16_t regs[1 + O2P_REG_UPD_DATA_MAX];
    regs[0] = seq;
    for (uint16_t i = 0; i < nbytes / 2u; i++) {
        regs[1 + i] = (uint16_t)((bytes[i * 2u] << 8) | bytes[i * 2u + 1u]);
    }
    return o2p_update_write(&u, O2P_REG_UPD_DATA, (uint16_t)(1u + nbytes / 2u),
                            regs);
}

/* Push a whole image in 240-byte blocks, the wire-sized block. */
static void push_image(const uint8_t *img, uint32_t len)
{
    uint16_t seq = 0u;
    for (uint32_t off = 0; off < len; off += 240u) {
        uint32_t n = len - off;
        if (n > 240u) {
            n = 240u;
        }
        TEST_ASSERT_EQUAL_UINT8(0, send_block(seq++, img + off, (uint16_t)n));
    }
}

static void transfer(uint32_t entry, uint32_t declared_crc_override)
{
    make_image(entry);
    uint32_t crc = o2p_crc32(g_img, IMG_BYTES);
    if (declared_crc_override != 0u) {
        crc = declared_crc_override;
    }
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, crc));
    run_to_completion();
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_READY, state());
    push_image(g_img, IMG_BYTES);
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_COMMIT}));
    run_to_completion();
}

/* -------------------------------------------------------------- the tests */

static void test_crc32_known_vector(void)
{
    /* The check value every CRC-32 catalogue lists, and what Python's
     * zlib.crc32(b"123456789") returns - which is how the field tool computes
     * the number this protocol carries. */
    TEST_ASSERT_EQUAL_HEX32(0xCBF43926u, o2p_crc32("123456789", 9));
    /* Empty input is 0, not the initial value. */
    TEST_ASSERT_EQUAL_HEX32(0x00000000u, o2p_crc32("", 0));
}

static void test_happy_path_stages_the_image(void)
{
    transfer(O2P_APP_BASE + 0x101u, 0u);

    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_STAGED, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_NONE, error());
    TEST_ASSERT_EQUAL_UINT32(IMG_BYTES, g_committed_len);
    TEST_ASSERT_EQUAL_HEX32(o2p_crc32(g_img, IMG_BYTES), g_committed_crc);
    TEST_ASSERT_EQUAL_MEMORY(g_img, g_stage, IMG_BYTES);
}

static void test_begin_retracts_any_previously_staged_image(void)
{
    transfer(O2P_APP_BASE + 0x101u, 0u);
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_STAGED, state());

    g_committed_len = 0xDEADBEEFu;
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, 0x12345678u));
    /* The staged flag must be dropped BEFORE the slot holding it is erased:
     * otherwise a power loss during the new transfer leaves a descriptor
     * pointing at a half-erased image. */
    TEST_ASSERT_EQUAL_UINT32(0u, g_committed_len);
}

static void test_wrong_crc_is_rejected_and_nothing_is_staged(void)
{
    transfer(O2P_APP_BASE + 0x101u, 0xBADBAD00u);

    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERROR, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_CRC, error());
    /* The only commit_staged call was BEGIN's retraction, with length 0. */
    TEST_ASSERT_EQUAL_UINT32(0u, g_committed_len);
}

static void test_image_for_the_wrong_slot_is_rejected_although_the_crc_is_right(void)
{
    /* An image linked at 0x08000000 - the bootloader's own build, or an
     * application built before the slot moved. Its CRC is perfect. Its reset
     * vector points into the bootloader. */
    transfer(O2P_BOOT_BASE + 0x101u, 0u);

    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERROR, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_IMAGE, error());
    TEST_ASSERT_EQUAL_UINT32(0u, g_committed_len);
}

static void test_image_without_a_thumb_reset_vector_is_rejected(void)
{
    transfer(O2P_APP_BASE + 0x100u, 0u);   /* even address: not Thumb */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERROR, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_IMAGE, error());
}

static void test_truncated_transfer_cannot_commit(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();

    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));
    /* Half the image, then COMMIT. The CRC of what arrived is not the CRC of
     * the image, but the length check must catch it before the CRC even runs
     * - a truncated image is not "unverified", it is refused. */
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                             (uint16_t[]){O2P_UPD_CMD_COMMIT}));
    /* Refused, but the transfer survives: the blocks already in the slot are
     * good and the master can send the rest. */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_RECEIVING, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_LENGTH, error());
    TEST_ASSERT_EQUAL_UINT32(0u, g_committed_len);

    for (uint32_t off = 240u; off < IMG_BYTES; off += 240u) {
        uint32_t n = IMG_BYTES - off;
        if (n > 240u) {
            n = 240u;
        }
        TEST_ASSERT_EQUAL_UINT8(0, send_block((uint16_t)(off / 240u),
                                              g_img + off, (uint16_t)n));
    }
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_COMMIT}));
    run_to_completion();
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_STAGED, state());
}

static void test_repeat_of_the_last_block_is_acknowledged_not_reprogrammed(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();

    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));
    TEST_ASSERT_EQUAL_UINT32(240u, received());

    /* The reply was lost; the master resends. A second program of the same
     * doublewords would fail on the real part (PROGERR on non-erased flash),
     * and the fake models that - so if this returned anything but success,
     * the engine reprogrammed. */
    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));
    TEST_ASSERT_EQUAL_UINT32(240u, received());

    /* And the transfer continues normally afterwards. */
    TEST_ASSERT_EQUAL_UINT8(0, send_block(1u, g_img + 240u, 240u));
    TEST_ASSERT_EQUAL_UINT32(480u, received());
}

static void test_a_retry_with_a_different_length_is_not_a_retry(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();
    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));

    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            send_block(0u, g_img, 8u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_SEQUENCE, error());
}

static void test_out_of_order_block_is_refused_and_the_master_can_resync(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();
    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));

    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            send_block(5u, g_img + 240u, 240u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_SEQUENCE, error());
    TEST_ASSERT_EQUAL_UINT32(240u, received());

    /* NEXT_SEQ is how the master finds its place again. */
    uint16_t next = 0u;
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_read(&u, O2P_REG_UPD_NEXT_SEQ, 1,
                                               &next));
    TEST_ASSERT_EQUAL_UINT16(1u, next);
    TEST_ASSERT_EQUAL_UINT8(0, send_block(next, g_img + 240u, 240u));
    TEST_ASSERT_EQUAL_UINT32(480u, received());
}

static void test_misaligned_payload_is_refused(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();

    /* 30 bytes: a whole number of registers, not a whole number of the 64-bit
     * doublewords this part programs. Accepting it would either drop two
     * bytes or write past the block. */
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE, send_block(0u, g_img, 30u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_ALIGN, error());
    TEST_ASSERT_EQUAL_UINT32(0u, received());
    /* Recoverable: the same block at a legal size is accepted. */
    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));
}

static void test_block_past_the_declared_length_is_refused(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(256u, o2p_crc32(g_img, 256u)));
    run_to_completion();

    TEST_ASSERT_EQUAL_UINT8(0, send_block(0u, g_img, 240u));
    /* 240 + 240 > 256. The overrun must not be silently truncated to fit. */
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            send_block(1u, g_img + 240u, 240u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_LENGTH, error());
    TEST_ASSERT_EQUAL_UINT32(240u, received());
}

static void test_impossible_declared_lengths_are_refused(void)
{
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE, begin(0u, 0u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_LENGTH, error());
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE, begin(100u, 0u));
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            begin(O2P_STAGE_BYTES + 8u, 0u));
    /* Not a whole number of doublewords. */
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE, begin(1004u, 0u));
    /* None of them started an erase, and none of them ended the session:
     * a refused BEGIN leaves the engine exactly where it was. */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());
}

static void test_flash_failure_is_reported_as_a_device_failure(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();

    g_program_fails = true;
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_DEVICE_FAILURE, send_block(0u, g_img, 240u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERROR, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_FLASH, error());
    TEST_ASSERT_EQUAL_UINT32(0u, received());
}

static void test_a_failed_descriptor_write_does_not_report_a_staged_image(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();
    push_image(g_img, IMG_BYTES);
    g_commit_fails = true;
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_COMMIT}));
    run_to_completion();

    /* The image is in the slot and its CRC is right, but the record that
     * would make the bootloader install it could not be written. Reporting
     * STAGED here would tell the master to reboot into a loader that will
     * find nothing to do. */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERROR, state());
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_FLASH, error());
}

static void test_boot_needs_a_staged_image(void)
{
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                             (uint16_t[]){O2P_UPD_CMD_BOOT}));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_NOIMAGE, error());
    TEST_ASSERT_FALSE(u.boot_requested);

    transfer(O2P_APP_BASE + 0x101u, 0u);
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_BOOT}));
    TEST_ASSERT_TRUE(u.boot_requested);
}

static void test_stay_asks_the_application_to_reboot_into_the_loader(void)
{
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_STAY}));
    TEST_ASSERT_TRUE(u.stay_requested);
    TEST_ASSERT_TRUE(u.boot_requested);

    /* In the loader the same command means "do not start the application",
     * and there is nothing to reboot into. */
    o2p_update_init(&u, &k_ops, true, 0u, 0x0001u);
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_STAY}));
    TEST_ASSERT_TRUE(u.stay_requested);
    TEST_ASSERT_FALSE(u.boot_requested);
}

static void test_abort_retracts_a_staged_image(void)
{
    transfer(O2P_APP_BASE + 0x101u, 0u);
    g_committed_len = 0xDEADBEEFu;
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                                (uint16_t[]){O2P_UPD_CMD_ABORT}));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());
    TEST_ASSERT_EQUAL_UINT32(0u, g_committed_len);
}

static void test_unknown_command_is_refused(void)
{
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE,
                            o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                             (uint16_t[]){0x0001u}));
    /* A stray value must not be a command, and must not have changed state. */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());
}

static void test_status_registers_report_who_is_answering(void)
{
    TEST_ASSERT_EQUAL_HEX16(0x0000u, status() & O2P_UPD_STATUS_LOADER);

    o2p_update_init(&u, &k_ops, true, 0u, 0x0001u);
    TEST_ASSERT_EQUAL_HEX16(O2P_UPD_STATUS_LOADER,
                            status() & O2P_UPD_STATUS_LOADER);

    uint16_t v[2];
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_read(&u, O2P_REG_UPD_SLOT_HI, 2, v));
    TEST_ASSERT_EQUAL_UINT32(O2P_STAGE_BYTES,
                             ((uint32_t)v[0] << 16) | v[1]);

    uint16_t n = 0u;
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_read(&u, O2P_REG_UPD_BLOCK_MAX, 1, &n));
    TEST_ASSERT_EQUAL_UINT16(O2P_REG_UPD_DATA_MAX, n);
    /* The advertised block size must actually be accepted, and must be a
     * whole number of doublewords - a master that believes this number and
     * gets ERR_ALIGN has been lied to. */
    TEST_ASSERT_EQUAL_UINT32(0u, (n * 2u) % O2P_IMAGE_ALIGN);
}

static void test_a_refused_control_frame_changes_nothing(void)
{
    /* The frame reaches over the length and CRC and on into RECV_HI, which is
     * status. It must be refused - and the length it carried must not survive
     * the refusal, or the NEXT BEGIN starts a transfer against numbers the
     * master never successfully sent and does not know it has. */
    uint16_t regs[6];
    regs[0] = O2P_UPD_CMD_ABORT;                 /* 0x0054, no side effect */
    regs[1] = 0u;                                /* 0x0055 len hi */
    regs[2] = 4096u;                             /* 0x0056 len lo */
    regs[3] = 0u;                                /* 0x0057 crc hi */
    regs[4] = 0u;                                /* 0x0058 crc lo */
    regs[5] = 0x1234u;                           /* 0x0059 RECV_HI: read-only */
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_ADDRESS,
                            o2p_update_write(&u, O2P_REG_UPD_CMD, 6, regs));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());

    /* A bare BEGIN now must find no length at all, not the smuggled 4096. */
    TEST_ASSERT_NOT_EQUAL(0, o2p_update_write(&u, O2P_REG_UPD_CMD, 1,
                                              (uint16_t[]){O2P_UPD_CMD_BEGIN}));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());
}

static void test_status_registers_are_read_only(void)
{
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_ADDRESS,
                            o2p_update_write(&u, O2P_REG_UPD_RECV_HI, 1,
                                             (uint16_t[]){0x1234u}));
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_ADDRESS,
                            o2p_update_write(&u, O2P_REG_UPD_NEXT_SEQ, 1,
                                             (uint16_t[]){0x1234u}));
}

static void test_data_window_reads_as_zero(void)
{
    uint16_t v[4] = {1u, 2u, 3u, 4u};
    TEST_ASSERT_EQUAL_UINT8(0, o2p_update_read(&u, O2P_REG_UPD_DATA, 4, v));
    for (unsigned i = 0; i < 4u; i++) {
        TEST_ASSERT_EQUAL_UINT16(0u, v[i]);
    }
}

static void test_a_block_must_start_at_the_window_base(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();

    uint16_t regs[5] = {0u, 1u, 2u, 3u, 4u};
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_ADDRESS,
                            o2p_update_write(&u, O2P_REG_UPD_DATA + 1u, 5,
                                             regs));
}

static void test_blocks_are_refused_before_the_erase_finishes(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERASING, state());

    TEST_ASSERT_EQUAL_UINT8(O2P_MB_EX_ILLEGAL_VALUE, send_block(0u, g_img, 240u));
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERR_STATE, error());
    /* And the erase it interrupted nothing of carries on to completion. */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_ERASING, state());
    run_to_completion();
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_READY, state());
}

static void test_the_erase_covers_the_whole_staging_slot(void)
{
    make_image(O2P_APP_BASE + 0x101u);
    TEST_ASSERT_EQUAL_UINT8(0, begin(IMG_BYTES, o2p_crc32(g_img, IMG_BYTES)));
    run_to_completion();
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_READY, state());
    for (uint32_t i = 0; i < O2P_STAGE_BYTES; i++) {
        if (g_stage[i] != 0xFFu) {
            TEST_FAIL_MESSAGE("staging slot not fully erased before READY");
        }
    }
}

static void test_adopt_staged_refuses_nonsense(void)
{
    o2p_update_adopt_staged(&u, 0u, 0u);
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());
    o2p_update_adopt_staged(&u, O2P_STAGE_BYTES + 8u, 0u);
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());
    o2p_update_adopt_staged(&u, 1004u, 0u);   /* not a doubleword multiple */
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_IDLE, state());

    o2p_update_adopt_staged(&u, 4096u, 0x1234u);
    TEST_ASSERT_EQUAL_UINT8(O2P_UPD_STAGED, state());
}

/* ------------------------------------------------------- boot descriptor */

static void test_descriptor_validation(void)
{
    o2p_desc_t d;
    o2p_desc_init(&d);
    TEST_ASSERT_TRUE(o2p_desc_record_valid(&d));

    o2p_desc_t bad = d;
    bad.magic ^= 1u;
    TEST_ASSERT_FALSE(o2p_desc_record_valid(&bad));

    bad = d;
    bad.layout_version++;
    TEST_ASSERT_FALSE(o2p_desc_record_valid(&bad));

    bad = d;
    bad.install_count = 3u;              /* changed without refreshing the CRC */
    TEST_ASSERT_FALSE(o2p_desc_record_valid(&bad));

    /* A record that is structurally perfect and describes an impossible
     * image. Believing it would mean installing 60 KiB out of a 52 KiB slot. */
    bad = d;
    bad.flags = O2P_DESC_F_STAGED;
    bad.staged_len = O2P_STAGE_BYTES + 8u;
    bad.crc16 = 0u;
    bad.crc16 = o2p_desc_crc(&bad);
    TEST_ASSERT_FALSE(o2p_desc_record_valid(&bad));

    /* Staged, but not a whole number of doublewords. */
    bad.staged_len = 1004u;
    bad.crc16 = 0u;
    bad.crc16 = o2p_desc_crc(&bad);
    TEST_ASSERT_FALSE(o2p_desc_record_valid(&bad));
}

static void test_descriptor_pick(void)
{
    o2p_desc_t a, b;
    o2p_desc_init(&a);
    o2p_desc_init(&b);

    TEST_ASSERT_EQUAL_INT(-1, o2p_desc_pick(&a, false, &b, false));
    TEST_ASSERT_EQUAL_INT(0, o2p_desc_pick(&a, true, &b, false));
    TEST_ASSERT_EQUAL_INT(1, o2p_desc_pick(&a, false, &b, true));

    a.sequence = 5u;
    b.sequence = 4u;
    TEST_ASSERT_EQUAL_INT(0, o2p_desc_pick(&a, true, &b, true));

    /* Across the 32-bit wrap: 0 is one newer than 0xFFFFFFFF, and a plain
     * unsigned comparison would pick the older record for the rest of time. */
    a.sequence = 0xFFFFFFFFu;
    b.sequence = 0u;
    TEST_ASSERT_EQUAL_INT(1, o2p_desc_pick(&a, true, &b, true));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_crc32_known_vector);
    RUN_TEST(test_happy_path_stages_the_image);
    RUN_TEST(test_begin_retracts_any_previously_staged_image);
    RUN_TEST(test_wrong_crc_is_rejected_and_nothing_is_staged);
    RUN_TEST(test_image_for_the_wrong_slot_is_rejected_although_the_crc_is_right);
    RUN_TEST(test_image_without_a_thumb_reset_vector_is_rejected);
    RUN_TEST(test_truncated_transfer_cannot_commit);
    RUN_TEST(test_repeat_of_the_last_block_is_acknowledged_not_reprogrammed);
    RUN_TEST(test_a_retry_with_a_different_length_is_not_a_retry);
    RUN_TEST(test_out_of_order_block_is_refused_and_the_master_can_resync);
    RUN_TEST(test_misaligned_payload_is_refused);
    RUN_TEST(test_block_past_the_declared_length_is_refused);
    RUN_TEST(test_impossible_declared_lengths_are_refused);
    RUN_TEST(test_flash_failure_is_reported_as_a_device_failure);
    RUN_TEST(test_a_failed_descriptor_write_does_not_report_a_staged_image);
    RUN_TEST(test_boot_needs_a_staged_image);
    RUN_TEST(test_stay_asks_the_application_to_reboot_into_the_loader);
    RUN_TEST(test_abort_retracts_a_staged_image);
    RUN_TEST(test_unknown_command_is_refused);
    RUN_TEST(test_status_registers_report_who_is_answering);
    RUN_TEST(test_a_refused_control_frame_changes_nothing);
    RUN_TEST(test_status_registers_are_read_only);
    RUN_TEST(test_data_window_reads_as_zero);
    RUN_TEST(test_a_block_must_start_at_the_window_base);
    RUN_TEST(test_blocks_are_refused_before_the_erase_finishes);
    RUN_TEST(test_the_erase_covers_the_whole_staging_slot);
    RUN_TEST(test_adopt_staged_refuses_nonsense);
    RUN_TEST(test_descriptor_validation);
    RUN_TEST(test_descriptor_pick);
    return UNITY_END();
}
