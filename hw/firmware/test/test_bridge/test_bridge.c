/* Host tests for the bench bridge's own diagnostic answer.
 *
 * The bridge exists to be believed when a transfer will not run: someone reads
 * its counters to decide whether the fault is their adapter or the probe. An
 * answer that is subtly wrong - a byte order, a CRC in the wrong end, an
 * off-by-one at the top of the block - is worse than no answer, because it
 * sends them to look at the probe.
 *
 * The interception is also the one way this image can eat a frame that was
 * meant for something else, so the guard-review checklist applies to it and
 * the cases below are written against it: a frame that cannot be evaluated
 * (short, bad CRC) must produce silence and never data, and a request that
 * gets worse must not come back to a good answer.
 *
 *   pio test -e native
 */
#include <unity.h>

#include <string.h>

#include "bridge_mailbox.h"
#include "bridge_reply.h"
#include "modbus_pdu.h"

#define ADDR 250u
#define NREGS 8u

static const uint16_t REGS[NREGS] = {
    0xB21Du, 0x0001u, 0x1234u, 0x5678u, 0x0000u, 0x0009u, 0x0060u, 0x0202u,
};

static uint8_t g_rsp[5u + 2u * NREGS];

/* Build a well-formed request and append a correct CRC. */
static size_t request(uint8_t *out, uint8_t addr, uint8_t fc, uint16_t first,
                      uint16_t count)
{
    out[0] = addr;
    out[1] = fc;
    out[2] = (uint8_t)(first >> 8);
    out[3] = (uint8_t)(first & 0xFFu);
    out[4] = (uint8_t)(count >> 8);
    out[5] = (uint8_t)(count & 0xFFu);
    const uint16_t crc = o2p_mb_crc16(out, 6u);
    out[6] = (uint8_t)(crc & 0xFFu);
    out[7] = (uint8_t)(crc >> 8);
    return 8u;
}

static size_t ask(uint8_t fc, uint16_t first, uint16_t count)
{
    uint8_t req[8];
    const size_t n = request(req, ADDR, fc, first, count);
    return o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp);
}

static void assert_crc_ok(size_t len)
{
    TEST_ASSERT_TRUE(len >= 4u);
    const uint16_t got = (uint16_t)(g_rsp[len - 2] |
                                    ((uint16_t)g_rsp[len - 1] << 8));
    TEST_ASSERT_EQUAL_UINT16(o2p_mb_crc16(g_rsp, len - 2u), got);
}

static void assert_exception(size_t len, uint8_t fc, uint8_t code)
{
    TEST_ASSERT_EQUAL_UINT(5u, len);
    TEST_ASSERT_EQUAL_UINT8(ADDR, g_rsp[0]);
    TEST_ASSERT_EQUAL_UINT8(fc | 0x80u, g_rsp[1]);
    TEST_ASSERT_EQUAL_UINT8(code, g_rsp[2]);
    assert_crc_ok(len);
}

void setUp(void) { memset(g_rsp, 0, sizeof(g_rsp)); }
void tearDown(void) {}

static void test_a_read_of_the_whole_block_comes_back_big_endian(void)
{
    const size_t len = ask(O2P_MB_FC_READ_HOLDING, 0u, NREGS);
    TEST_ASSERT_EQUAL_UINT(3u + 2u * NREGS + 2u, len);
    TEST_ASSERT_EQUAL_UINT8(ADDR, g_rsp[0]);
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_FC_READ_HOLDING, g_rsp[1]);
    TEST_ASSERT_EQUAL_UINT8(2u * NREGS, g_rsp[2]);
    for (unsigned i = 0; i < NREGS; i++) {
        TEST_ASSERT_EQUAL_UINT8(REGS[i] >> 8, g_rsp[3u + 2u * i]);
        TEST_ASSERT_EQUAL_UINT8(REGS[i] & 0xFFu, g_rsp[4u + 2u * i]);
    }
    assert_crc_ok(len);
}

static void test_input_registers_mirror_holding_registers(void)
{
    uint8_t holding[sizeof(g_rsp)];
    size_t a = ask(O2P_MB_FC_READ_HOLDING, 2u, 3u);
    memcpy(holding, g_rsp, a);
    const size_t b = ask(O2P_MB_FC_READ_INPUT, 2u, 3u);
    TEST_ASSERT_EQUAL_UINT(a, b);
    /* Same data, and only the function-code byte and CRC differ. */
    TEST_ASSERT_EQUAL_UINT8(O2P_MB_FC_READ_INPUT, g_rsp[1]);
    TEST_ASSERT_EQUAL_MEMORY(holding + 2, g_rsp + 2, a - 4u);
    assert_crc_ok(b);
}

static void test_a_partial_read_starts_where_it_was_asked_to(void)
{
    const size_t len = ask(O2P_MB_FC_READ_HOLDING, 5u, 2u);
    TEST_ASSERT_EQUAL_UINT(3u + 4u + 2u, len);
    TEST_ASSERT_EQUAL_UINT8(REGS[5] >> 8, g_rsp[3]);
    TEST_ASSERT_EQUAL_UINT8(REGS[6] >> 8, g_rsp[5]);
    assert_crc_ok(len);
}

static void test_the_last_register_alone_is_readable(void)
{
    const size_t len = ask(O2P_MB_FC_READ_HOLDING, NREGS - 1u, 1u);
    TEST_ASSERT_EQUAL_UINT(3u + 2u + 2u, len);
    TEST_ASSERT_EQUAL_UINT8(REGS[NREGS - 1] & 0xFFu, g_rsp[4]);
}

/* --- what must never produce data ------------------------------------- */

static void test_a_corrupt_frame_is_answered_with_silence(void)
{
    uint8_t req[8];
    const size_t n = request(req, ADDR, O2P_MB_FC_READ_HOLDING, 0u, NREGS);
    req[3] ^= 0x01u;                       /* CRC now belongs to another frame */
    TEST_ASSERT_EQUAL_UINT(0u, o2p_bridge_reply(ADDR, REGS, NREGS, req, n,
                                                g_rsp));
}

static void test_a_frame_too_short_to_hold_a_crc_is_answered_with_silence(void)
{
    const uint8_t req[3] = { ADDR, O2P_MB_FC_READ_HOLDING, 0u };
    for (size_t n = 0; n <= sizeof(req); n++) {
        TEST_ASSERT_EQUAL_UINT(0u, o2p_bridge_reply(ADDR, REGS, NREGS, req, n,
                                                    g_rsp));
    }
}

/* --- what must produce an exception, not a guess ------------------------ */

static void test_a_write_is_refused_the_bridge_has_nothing_to_set(void)
{
    uint8_t req[8];
    const size_t n = request(req, ADDR, 0x10u, 0u, 1u);
    const size_t len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp);
    assert_exception(len, 0x10u, O2P_MB_EX_ILLEGAL_FUNCTION);
}

static void test_a_read_of_the_wrong_length_is_refused(void)
{
    uint8_t req[9];
    req[0] = ADDR;
    req[1] = O2P_MB_FC_READ_HOLDING;
    memset(req + 2, 0, 5);
    req[6] = 1u;
    const uint16_t crc = o2p_mb_crc16(req, 7u);
    req[7] = (uint8_t)(crc & 0xFFu);
    req[8] = (uint8_t)(crc >> 8);
    const size_t len = o2p_bridge_reply(ADDR, REGS, NREGS, req, sizeof(req),
                                        g_rsp);
    assert_exception(len, O2P_MB_FC_READ_HOLDING, O2P_MB_EX_ILLEGAL_VALUE);
}

static void test_reads_off_the_end_are_refused_and_stay_refused(void)
{
    /* Monotone: as the request reaches further past the block, the answer
     * must not come back to data. The far tail is checked as well as the
     * near miss, because a bound written as first + count wraps there. */
    const struct { uint16_t first, count; } bad[] = {
        { 0u, 0u },                 /* zero registers is not a read */
        { 0u, NREGS + 1u },
        { NREGS - 1u, 2u },         /* one past the end */
        { NREGS, 1u },
        { 0xFFFFu, 1u },
        { 0xFFFFu, 0xFFFFu },       /* first + count wraps to 0xFFFE */
        { 1u, 0xFFFFu },
    };
    for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        const size_t len = ask(O2P_MB_FC_READ_HOLDING, bad[i].first,
                               bad[i].count);
        assert_exception(len, O2P_MB_FC_READ_HOLDING,
                         O2P_MB_EX_ILLEGAL_ADDRESS);
    }
}

/* --- the SWD mailbox's two pure guards ---------------------------------- */

static void test_only_a_possible_adu_is_transmitted(void)
{
    /* The length comes from a debugger writing SRAM. There is no framing to
     * catch a wrong one, so this is the only thing between a stray word and a
     * transmission built out of whatever the buffer held. */
    TEST_ASSERT_FALSE(o2p_mailbox_len_ok(0u));
    TEST_ASSERT_FALSE(o2p_mailbox_len_ok(3u));       /* no room for a CRC */
    TEST_ASSERT_TRUE(o2p_mailbox_len_ok(4u));
    TEST_ASSERT_TRUE(o2p_mailbox_len_ok(O2P_MB_MAX_ADU));
    TEST_ASSERT_FALSE(o2p_mailbox_len_ok(O2P_MB_MAX_ADU + 1u));
    /* The far tail, not just the near miss: a length that wrapped or was
     * never written must not come back to a pass. */
    TEST_ASSERT_FALSE(o2p_mailbox_len_ok(0xFFFFFFFFu));
    TEST_ASSERT_FALSE(o2p_mailbox_len_ok(0x80000000u));
}

static void test_the_reply_window_is_clamped_at_both_ends(void)
{
    /* Zero means "unset", not "do not wait": a host that never wrote the
     * field would otherwise make every transaction report silence. */
    TEST_ASSERT_EQUAL_UINT32(O2P_MBX_REPLY_MS_DEFAULT,
                             o2p_mailbox_reply_window(0u));
    TEST_ASSERT_EQUAL_UINT32(50u, o2p_mailbox_reply_window(50u));
    TEST_ASSERT_EQUAL_UINT32(O2P_MBX_REPLY_MS_MAX,
                             o2p_mailbox_reply_window(O2P_MBX_REPLY_MS_MAX));
    /* An hour would hold the bridge - and the cable - for an hour. */
    TEST_ASSERT_EQUAL_UINT32(O2P_MBX_REPLY_MS_MAX,
                             o2p_mailbox_reply_window(3600000u));
    TEST_ASSERT_EQUAL_UINT32(O2P_MBX_REPLY_MS_MAX,
                             o2p_mailbox_reply_window(0xFFFFFFFFu));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_a_read_of_the_whole_block_comes_back_big_endian);
    RUN_TEST(test_input_registers_mirror_holding_registers);
    RUN_TEST(test_a_partial_read_starts_where_it_was_asked_to);
    RUN_TEST(test_the_last_register_alone_is_readable);
    RUN_TEST(test_a_corrupt_frame_is_answered_with_silence);
    RUN_TEST(test_a_frame_too_short_to_hold_a_crc_is_answered_with_silence);
    RUN_TEST(test_a_write_is_refused_the_bridge_has_nothing_to_set);
    RUN_TEST(test_a_read_of_the_wrong_length_is_refused);
    RUN_TEST(test_reads_off_the_end_are_refused_and_stay_refused);
    RUN_TEST(test_only_a_possible_adu_is_transmitted);
    RUN_TEST(test_the_reply_window_is_clamped_at_both_ends);
    return UNITY_END();
}
