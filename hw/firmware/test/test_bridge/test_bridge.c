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
static o2p_bridge_action_t g_act;

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
    return o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, &g_act);
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
                                                g_rsp, &g_act));
}

static void test_a_frame_too_short_to_hold_a_crc_is_answered_with_silence(void)
{
    const uint8_t req[3] = { ADDR, O2P_MB_FC_READ_HOLDING, 0u };
    for (size_t n = 0; n <= sizeof(req); n++) {
        TEST_ASSERT_EQUAL_UINT(0u, o2p_bridge_reply(ADDR, REGS, NREGS, req, n,
                                                    g_rsp, &g_act));
    }
}

/* --- what must produce an exception, not a guess ------------------------ */

static void test_an_unsupported_write_function_is_refused(void)
{
    /* FC06 stays refused. Only FC16 was given a meaning -- it is the dialect
     * the probe's own config block is written with, so a bridge that answered
     * a second verb would be the only device on the cable that did. */
    uint8_t req[8];
    const size_t n = request(req, ADDR, O2P_MB_FC_WRITE_SINGLE, 6u,
                             (uint16_t)(O2P_BRIDGE_BAUD_3 / 100u));
    const size_t len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, &g_act);
    assert_exception(len, O2P_MB_FC_WRITE_SINGLE, O2P_MB_EX_ILLEGAL_FUNCTION);
    TEST_ASSERT_FALSE(g_act.set_bus_baud);
}

/* ---- the one writable register: the bus rate ---- */

/* An FC16 request of `count` registers carrying `value`, with `bytes` declared
 * as the byte count. The malformed shapes are reachable by lying about the
 * last two, which is what the length and consistency checks are for. */
static size_t write_frame(uint8_t *out, uint16_t reg, uint16_t count,
                          uint8_t bytes, uint16_t value)
{
    out[0] = ADDR;
    out[1] = O2P_MB_FC_WRITE_MULTIPLE;
    out[2] = (uint8_t)(reg >> 8);
    out[3] = (uint8_t)(reg & 0xFFu);
    out[4] = (uint8_t)(count >> 8);
    out[5] = (uint8_t)(count & 0xFFu);
    out[6] = bytes;
    out[7] = (uint8_t)(value >> 8);
    out[8] = (uint8_t)(value & 0xFFu);
    const uint16_t crc = o2p_mb_crc16(out, 9u);
    out[9] = (uint8_t)(crc & 0xFFu);
    out[10] = (uint8_t)(crc >> 8);
    return 11u;
}

static size_t write_reg(uint16_t reg, uint16_t value)
{
    uint8_t req[11];
    const size_t n = write_frame(req, reg, 1u, 2u, value);
    return o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, &g_act);
}

static void test_the_bus_rate_can_be_moved_to_each_supported_value(void)
{
    /* Sized from the array rather than a literal 3: this loop silently stopped
     * covering the newest rate when O2P_BRIDGE_BAUD_4 was added, so the one
     * test that proves a rate is reachable did not test it. */
    const uint32_t bauds[] = {O2P_BRIDGE_BAUD_1, O2P_BRIDGE_BAUD_2,
                              O2P_BRIDGE_BAUD_3, O2P_BRIDGE_BAUD_4};
    for (unsigned i = 0; i < sizeof(bauds) / sizeof(bauds[0]); i++) {
        const size_t len = write_reg(6u, (uint16_t)(bauds[i] / 100u));
        /* FC16 answers with the address and count it applied, so the master
         * can confirm what landed rather than infer it from the absence of an
         * exception. */
        TEST_ASSERT_EQUAL_UINT(8u, len);
        assert_crc_ok(len);
        TEST_ASSERT_EQUAL_UINT8(ADDR, g_rsp[0]);
        TEST_ASSERT_EQUAL_UINT8(O2P_MB_FC_WRITE_MULTIPLE, g_rsp[1]);
        TEST_ASSERT_EQUAL_UINT16(6u, (uint16_t)((g_rsp[2] << 8) | g_rsp[3]));
        TEST_ASSERT_EQUAL_UINT16(1u, (uint16_t)((g_rsp[4] << 8) | g_rsp[5]));
        TEST_ASSERT_TRUE(g_act.set_bus_baud);
        TEST_ASSERT_EQUAL_UINT32(bauds[i], g_act.bus_baud);
    }
}

static void test_an_unsupported_rate_is_refused_and_commands_nothing(void)
{
    /* The two ways to get this wrong are a rate no probe can follow and a
     * value that is not a rate at all. Both must leave the cable where it is:
     * the bridge is the only thing on the bus that stays reachable after a bad
     * move, and only because it did not make one. */
    const uint16_t bad[6] = {0u, 1u, 24u, 48u, 576u, 0xFFFFu};
    for (unsigned i = 0; i < 6u; i++) {
        const size_t len = write_reg(6u, bad[i]);
        assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE,
                         O2P_MB_EX_ILLEGAL_VALUE);
        TEST_ASSERT_FALSE(g_act.set_bus_baud);
    }
}

static void test_no_other_register_is_writable(void)
{
    /* Known-bad calibration for the address check: walk the whole block plus
     * one past it, at a value that WOULD be accepted at register 6. */
    for (uint16_t reg = 0u; reg <= NREGS; reg++) {
        if (reg == 6u) {
            continue;
        }
        const size_t len = write_reg(reg, (uint16_t)(O2P_BRIDGE_BAUD_3 / 100u));
        assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE,
                         O2P_MB_EX_ILLEGAL_ADDRESS);
        TEST_ASSERT_FALSE(g_act.set_bus_baud);
    }
}

static void test_a_multi_register_write_is_refused_whole(void)
{
    /* A block that spans register 6 also spans a counter, and there is no way
     * to apply the half that is legal without also claiming the half that is
     * not. The declared byte count is checked against the count for the same
     * reason: they are two statements of the same thing, and a frame where
     * they disagree is not a frame this bridge understands. */
    uint8_t req[11];
    size_t n = write_frame(req, 6u, 2u, 4u, 384u);
    size_t len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, &g_act);
    assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE, O2P_MB_EX_ILLEGAL_VALUE);
    TEST_ASSERT_FALSE(g_act.set_bus_baud);

    n = write_frame(req, 6u, 1u, 4u, 384u);   /* count and byte count disagree */
    len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, &g_act);
    assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE, O2P_MB_EX_ILLEGAL_VALUE);
    TEST_ASSERT_FALSE(g_act.set_bus_baud);

    n = write_frame(req, 6u, 0u, 2u, 384u);   /* nothing to write */
    len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, &g_act);
    assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE, O2P_MB_EX_ILLEGAL_VALUE);
    TEST_ASSERT_FALSE(g_act.set_bus_baud);
}

static void test_a_caller_that_cannot_act_refuses_the_write(void)
{
    /* Unevaluable input, guard-checklist rule 1. A caller passing NULL has no
     * way to re-rate anything, so the write must fail loudly rather than be
     * answered and dropped. */
    uint8_t req[11];
    const size_t n = write_frame(req, 6u, 1u, 2u,
                                 (uint16_t)(O2P_BRIDGE_BAUD_3 / 100u));
    const size_t len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp, NULL);
    assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE,
                     O2P_MB_EX_ILLEGAL_FUNCTION);
}

static void test_a_corrupt_write_is_answered_with_silence(void)
{
    /* A write must clear the same bar a read does. Its address byte is no more
     * trustworthy than a read's, and acting on a corrupt one is worse: it
     * moves the cable rather than reporting a counter. */
    uint8_t req[11];
    const size_t n = write_frame(req, 6u, 1u, 2u,
                                 (uint16_t)(O2P_BRIDGE_BAUD_3 / 100u));
    req[8] ^= 0x01u;   /* the value, now disagreeing with the CRC */
    TEST_ASSERT_EQUAL_UINT(0u, o2p_bridge_reply(ADDR, REGS, NREGS, req, n,
                                                g_rsp, &g_act));
    TEST_ASSERT_FALSE(g_act.set_bus_baud);
}

static void test_a_write_of_the_wrong_length_is_refused(void)
{
    /* Every length but eleven, with a CRC that is correct for it -- so what is
     * being refused is the shape and not the checksum. */
    for (size_t n = 4u; n <= 16u; n++) {
        if (n == 11u) {
            continue;
        }
        uint8_t req[16];
        memset(req, 0, sizeof(req));
        req[0] = ADDR;
        req[1] = O2P_MB_FC_WRITE_MULTIPLE;
        req[3] = 6u;
        const uint16_t crc = o2p_mb_crc16(req, n - 2u);
        req[n - 2] = (uint8_t)(crc & 0xFFu);
        req[n - 1] = (uint8_t)(crc >> 8);
        const size_t len = o2p_bridge_reply(ADDR, REGS, NREGS, req, n, g_rsp,
                                            &g_act);
        assert_exception(len, O2P_MB_FC_WRITE_MULTIPLE,
                         O2P_MB_EX_ILLEGAL_VALUE);
        TEST_ASSERT_FALSE(g_act.set_bus_baud);
    }
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
                                        g_rsp, &g_act);
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


static void test_the_frame_timeout_follows_the_spec_above_19200(void)
{
    /* Modbus over Serial Line v1.02, 2.5.1.1: 3.5 character times up to 19200
     * baud, and a FIXED 1.750 ms above it. Every UART in this firmware used to
     * compute ceil(3.5 * bits) and ignore the baud, so the absolute silence
     * collapsed as the bus sped up. */

    /* Unchanged where the character rule still governs - this is what makes the
     * fix safe to ship on the rates already deployed. */
    TEST_ASSERT_EQUAL_UINT32(39u, o2p_mb_rtor_bit_times(9600u,  0u));
    TEST_ASSERT_EQUAL_UINT32(39u, o2p_mb_rtor_bit_times(19200u, 0u));

    /* KNOWN-BAD CALIBRATION. These are the two rates the old code got wrong.
     * 39 bit times is 1003 us at 38400 and 334 us at 115200, both under the
     * 1750 us floor; if either of these ever reads 39 again the bug is back. */
    TEST_ASSERT_EQUAL_UINT32(68u,  o2p_mb_rtor_bit_times(38400u,  0u));
    TEST_ASSERT_EQUAL_UINT32(202u, o2p_mb_rtor_bit_times(115200u, 0u));

    /* The floor is an ABSOLUTE time, so check it in microseconds rather than
     * trusting the bit-time arithmetic that produced it. */
    for (unsigned i = 0; i < 4u; i++) {
        const uint32_t bauds[4] = {9600u, 19200u, 38400u, 115200u};
        const uint32_t bits = o2p_mb_rtor_bit_times(bauds[i], 0u);
        const uint32_t us   = (uint32_t)((uint64_t)bits * 1000000u / bauds[i]);
        /* Either at least 3.5 characters, or at least the spec's fixed timer.
         * Above 19200 only the second can be satisfied. */
        TEST_ASSERT_TRUE(us >= 1750u || bauds[i] <= 19200u);
        TEST_ASSERT_TRUE(bits >= 39u);          /* never SHORTER than before */
    }

    /* 8N1 is 10 bits, so the character rule gives ceil(35) = 35 - and the floor
     * still governs above 19200 regardless of parity. */
    TEST_ASSERT_EQUAL_UINT32(35u,  o2p_mb_rtor_bit_times(9600u,   1u));
    TEST_ASSERT_EQUAL_UINT32(202u, o2p_mb_rtor_bit_times(115200u, 1u));
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
    RUN_TEST(test_an_unsupported_write_function_is_refused);
    RUN_TEST(test_the_bus_rate_can_be_moved_to_each_supported_value);
    RUN_TEST(test_an_unsupported_rate_is_refused_and_commands_nothing);
    RUN_TEST(test_no_other_register_is_writable);
    RUN_TEST(test_a_multi_register_write_is_refused_whole);
    RUN_TEST(test_a_caller_that_cannot_act_refuses_the_write);
    RUN_TEST(test_a_corrupt_write_is_answered_with_silence);
    RUN_TEST(test_a_write_of_the_wrong_length_is_refused);
    RUN_TEST(test_a_read_of_the_wrong_length_is_refused);
    RUN_TEST(test_reads_off_the_end_are_refused_and_stay_refused);
    RUN_TEST(test_only_a_possible_adu_is_transmitted);
    RUN_TEST(test_the_reply_window_is_clamped_at_both_ends);
    RUN_TEST(test_the_frame_timeout_follows_the_spec_above_19200);
    return UNITY_END();
}
