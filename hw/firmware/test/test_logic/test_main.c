/* Host tests for the portable half of the o2-probe firmware.
 *
 * Everything here is logic that can be wrong without hardware, which is
 * exactly the logic that is expensive to debug once a probe is potted and its
 * SWD connector is inside the enclosure. Run with:  pio test -e native
 */
#include <unity.h>

#include <math.h>
#include <string.h>

#include <stdlib.h>

#include "ads1119.h"
#include "config_migrate.h"
#include "die_temp.h"
#include "faults.h"
#include "hw_caps.h"
#include "heater_ctl.h"
#include "lmp91000.h"
#include "modbus_pdu.h"
#include "o2.h"
#include "psychro.h"
#include "regmap.h"
#include "sampler_logic.h"
#include "serial_probation.h"
#include "config_select.h"
#include "transport_record.h"
#include "modbus_rtu.h"
#include "tmp117.h"

static o2p_regmap_t rm;
static o2p_mb_handlers_t handlers;

void setUp(void)
{
    o2p_regmap_init(&rm);
    handlers.read = o2p_regmap_read;
    handlers.write = o2p_regmap_write;
    handlers.ctx = &rm;
}
void tearDown(void) {}

/* --------------------------------------------------------------- CRC-16 */

static void test_crc16_known_vectors(void)
{
    /* The frame the Dragino node already sends to SMT100 probe 1
     * (tech/RS485-LS-SMT100.md:290), and our own primary-block read. */
    const uint8_t smt[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x03};
    TEST_ASSERT_EQUAL_HEX16(0xCB05, o2p_mb_crc16(smt, sizeof(smt)));

    const uint8_t ours[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    TEST_ASSERT_EQUAL_HEX16(0xEE45, o2p_mb_crc16(ours, sizeof(ours)));

    /* A discovery read of SLAVE_ADDR at the config base. */
    const uint8_t disc[] = {0xFD, 0x03, 0x00, 0x30, 0x00, 0x01};
    TEST_ASSERT_EQUAL_HEX16(0x3990, o2p_mb_crc16(disc, sizeof(disc)));
}

/* ------------------------------------------------------------ classifier */

static size_t framed(uint8_t *buf, const uint8_t *pdu, size_t n)
{
    memcpy(buf, pdu, n);
    uint16_t c = o2p_mb_crc16(buf, n);
    buf[n] = (uint8_t)(c & 0xFF);
    buf[n + 1] = (uint8_t)(c >> 8);
    return n + 2;
}

static void test_classify_addressing(void)
{
    uint8_t f[16];
    const uint8_t body[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    size_t n = framed(f, body, sizeof(body));

    TEST_ASSERT_EQUAL(O2P_MB_EXECUTE, o2p_mb_classify(f, n, 3));
    /* Addressed to us but we are configured as 4: not ours. */
    TEST_ASSERT_EQUAL(O2P_MB_DROP, o2p_mb_classify(f, n, 4));

    uint8_t b[16];
    const uint8_t bbody[] = {0x00, 0x06, 0x00, 0x30, 0x00, 0x03};
    size_t bn = framed(b, bbody, sizeof(bbody));
    TEST_ASSERT_EQUAL(O2P_MB_EXECUTE_NO_REPLY, o2p_mb_classify(b, bn, 3));

    /* 253 is the discovery alias used to find a probe whose address is
     * unknown (tech/RS485-LS-SMT100.md:247). */
    uint8_t d[16];
    const uint8_t dbody[] = {0xFD, 0x03, 0x00, 0x30, 0x00, 0x01};
    size_t dn = framed(d, dbody, sizeof(dbody));
    TEST_ASSERT_EQUAL(O2P_MB_EXECUTE, o2p_mb_classify(d, dn, 3));
}

static void test_classify_rejects_corrupt(void)
{
    uint8_t f[16];
    const uint8_t body[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    size_t n = framed(f, body, sizeof(body));

    /* One flipped bit anywhere must silence us, not provoke a reply. */
    for (size_t i = 0; i < n; i++) {
        uint8_t save = f[i];
        f[i] ^= 0x01;
        TEST_ASSERT_EQUAL(O2P_MB_DROP, o2p_mb_classify(f, n, 3));
        f[i] = save;
    }
    /* Truncated frames, as a collision or a stuck master leaves behind. */
    TEST_ASSERT_EQUAL(O2P_MB_DROP, o2p_mb_classify(f, 3, 3));
    TEST_ASSERT_EQUAL(O2P_MB_DROP, o2p_mb_classify(f, 0, 3));
}

/* -------------------------------------------------------------- dispatch */

static void test_read_primary_block(void)
{
    o2p_snapshot_t *s = o2p_regmap_staging(&rm);
    s->o2_comp = 1850;      /* 18.50 %vol */
    s->o2_raw = 6100;       /* 61.00 uA */
    s->t_tip = 5512;
    s->t_chamber = 5480;
    s->rh_chamber = 8700;
    s->heater_duty = 0;
    s->faults = O2P_F_HEATER_DISABLED;
    s->settle_s = 0;
    o2p_regmap_publish(&rm);

    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    size_t n = framed(req, body, sizeof(body));

    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(3 + 16 + 2, len);
    TEST_ASSERT_EQUAL_HEX8(0x03, rsp[0]);
    TEST_ASSERT_EQUAL_HEX8(0x03, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(16, rsp[2]);
    TEST_ASSERT_EQUAL_HEX16(1850, (rsp[3] << 8) | rsp[4]);
    TEST_ASSERT_EQUAL_HEX16(6100, (rsp[5] << 8) | rsp[6]);
    TEST_ASSERT_EQUAL_HEX16(8700, (rsp[11] << 8) | rsp[12]);
    /* And the response must carry a CRC the master will accept: computed over
     * everything but the last two bytes, transmitted low byte first. */
    uint16_t sent_crc = (uint16_t)rsp[len - 2] | ((uint16_t)rsp[len - 1] << 8);
    TEST_ASSERT_EQUAL_HEX16(o2p_mb_crc16(rsp, len - 2), sent_crc);
}

static void test_discovery_reply_uses_the_discovery_address(void)
{
    /* A master looking for a probe whose address it does not know sends to
     * 253 and must be able to recognise the answer. Replying from our own
     * unicast address would leave it unable to match request to response. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0xFD, 0x03, 0x00, 0x30, 0x00, 0x01};
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(3 + 2 + 2, len);
    TEST_ASSERT_EQUAL_HEX8(0xFD, rsp[0]);
    /* ...and the value it reports is our real address, which is the point. */
    TEST_ASSERT_EQUAL_HEX16(3, (rsp[3] << 8) | rsp[4]);
}

static void test_config_crc_register_is_read_only(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x3F, 0x12, 0x34};
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, rsp[2]);
}

static void test_16bit_value_is_not_truncated_into_a_byte_field(void)
{
    /* 0x0103 truncated to a uint8_t is 3, which is a legal slave address.
     * The write must be refused on the full value, not narrowed first. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x30, 0x01, 0x03};
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x86, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_UINT8(3, rm.cfg.slave_addr);
    TEST_ASSERT_FALSE(rm.serial_reconfig_pending);
}

static void test_config_struct_has_no_implicit_padding(void)
{
    /* The struct is written to flash byte-for-byte and hashed with a CRC.
     * Padding the compiler may leave uninitialised would make that CRC
     * non-deterministic and produce spurious "corrupt config" at boot. */
    TEST_ASSERT_EQUAL_UINT(2 * sizeof(int32_t) + 16 * sizeof(uint16_t) + 8,
                           sizeof(o2p_config_t));
    /* It DID grow with dil_alpha_x1000, from 32 to 36, and again to 40 when
     * cal_zero_na and cal_zero_taken were APPENDED - appended rather than
     * placed beside cal_air_na so that every v5 offset stays put and the
     * migration is a zero-fill instead of a re-layout. The growth is
     * paid for out of the RECORD's reserved tail, not out of the record: the
     * frame is still 64 bytes and the CRC still sits immediately after the
     * configuration, which is the invariant that actually matters. The
     * assertion below is what enforces it.
     *
     * 44 -> 48 with the persistent tip setpoint and its consent (v8). Those two
     * fields are 4 bytes; the other 2 are reserved4, which makes explicit the
     * tail padding the 4-byte alignment was already inserting. Only 6 bytes of
     * the record's reserved tail were left before this change, which is why the
     * tip loop has no flash-backed gain pair - see regmap.h. */
    TEST_ASSERT_EQUAL_UINT(48u, sizeof(o2p_config_t));
    /* config_flash.h is not reachable from a native test (it pulls in the
     * flash map), so the record arithmetic is restated here rather than
     * measured: 12 bytes of header + the configuration + a 2-byte CRC must
     * still fit inside the 64-byte frame, with a whole number of double words
     * for 64-bit flash programming. The static assert in config_flash.h is
     * the one that binds; this is the one that says so out loud. */
    TEST_ASSERT_TRUE(12u + sizeof(o2p_config_t) + 2u <= 64u);
}

static void test_read_across_block_gap_is_refused(void)
{
    /* 0x0006..0x000D spans the end of the primary block. Zero-filling the gap
     * would publish 0.00 %vol as if it were a measurement. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x03, 0x00, 0x06, 0x00, 0x08};
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(5, len);
    TEST_ASSERT_EQUAL_HEX8(0x83, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, rsp[2]);
}

static void test_unknown_function_is_exception_01(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x2B, 0x00, 0x00, 0x00, 0x01};  /* FC43 */
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(5, len);
    TEST_ASSERT_EQUAL_HEX8(0xAB, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_FUNCTION, rsp[2]);
}

static void test_broadcast_never_replies(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x00, 0x06, 0x00, 0x30, 0x00, 0x05};
    size_t n = framed(req, body, sizeof(body));
    TEST_ASSERT_EQUAL_UINT(0, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    /* ...but the write was still executed. */
    TEST_ASSERT_EQUAL_UINT8(5, rm.cfg.slave_addr);
}

/* -------------------------------------------------------- config writes */

static void test_write_rejects_illegal_slave_address(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    /* 253 is the discovery alias, not a legal unicast address. */
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x30, 0x00, 0xFD};
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x86, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_UINT(5, len);
    /* And nothing changed. */
    TEST_ASSERT_EQUAL_UINT8(3, rm.cfg.slave_addr);
    TEST_ASSERT_FALSE(rm.serial_reconfig_pending);
}

static void test_partly_illegal_multiwrite_commits_nothing(void)
{
    /* Write address=5 (legal) and baud_code=99 (illegal) in one frame. If the
     * address landed and the baud did not, the probe would answer at a new
     * address the operator does not know about. */
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x10, 0x00, 0x30, 0x00, 0x02, 0x04,
                            0x00, 0x05, 0x00, 0x63};
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(5, len);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_UINT8(3, rm.cfg.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_9600, rm.cfg.baud_code);
}

static void test_commit_and_cal_need_their_magic(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t bad[] = {0x03, 0x06, 0x00, 0x3E, 0x00, 0x01};
    size_t n = framed(req, bad, sizeof(bad));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_FALSE(rm.commit_pending);

    const uint8_t good[] = {0x03, 0x06, 0x00, 0x3E, 0x5A, 0xC1};
    n = framed(req, good, sizeof(good));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_TRUE(rm.commit_pending);
}

/* ------------------------------------------- serial settings on probation */

/* Write BAUD_CODE = 38400 with a single FC06. */
static void write_baud_38400(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x31, 0x00, 0x02};
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
}

static void test_a_serial_change_arms_probation_and_keeps_the_old_settings(void)
{
    write_baud_38400();
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, rm.cfg.baud_code);
    TEST_ASSERT_TRUE(rm.serial_reconfig_pending);
    /* Raised by the WRITE, not by the transport switch a main loop later, so
     * that a COMMIT in the very same frame is already gated by it. */
    TEST_ASSERT_TRUE(rm.serial_probation);
    /* Where it goes back TO is not this file's business: main.c arms the
     * timer with the triplet that is in FLASH, not with the one the config
     * held a moment ago. See o2p_sp_arm's caller and the comment on
     * g_stored_addr - a previous-value rule sends a failed restore back to
     * the rate the master had just left. */
}

static void test_probation_confirms_on_one_frame_and_decides_once(void)
{
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 7u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    TEST_ASSERT_EQUAL_INT(O2P_SP_WAIT, o2p_sp_service(&p, 1100u, 7u));
    /* One frame at the new settings is the whole proof. */
    TEST_ASSERT_EQUAL_INT(O2P_SP_CONFIRMED, o2p_sp_service(&p, 1200u, 8u));
    /* And it is reported once: a caller may act on the edge without tracking
     * it, and a second CONFIRMED would re-run a commit that already ran. */
    TEST_ASSERT_EQUAL_INT(O2P_SP_WAIT, o2p_sp_service(&p, 1300u, 9u));
}

static void test_probation_reverts_when_no_frame_arrives(void)
{
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 7u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    /* One millisecond short is still waiting: the boundary is the whole
     * mechanism, and a guard that fires early would revert a link that was
     * about to answer. */
    TEST_ASSERT_EQUAL_INT(O2P_SP_WAIT,
                          o2p_sp_service(&p, 1000u + O2P_SERIAL_PROBATION_MS - 1u, 7u));
    TEST_ASSERT_EQUAL_INT(O2P_SP_REVERT,
                          o2p_sp_service(&p, 1000u + O2P_SERIAL_PROBATION_MS, 7u));
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_9600, p.prev_baud_code);
    TEST_ASSERT_EQUAL_INT(O2P_SP_WAIT, o2p_sp_service(&p, 99999u, 7u));
}

static void test_probation_survives_a_millisecond_wrap(void)
{
    /* Armed 100 ms before the counter wraps. A signed or naive comparison
     * makes the deadline unreachable here and the probe never comes back. */
    o2p_serial_probation_t p = {0};
    uint32_t t0 = 0xFFFFFF9Bu;                     /* 100 ms left */
    o2p_sp_arm(&p, t0, 7u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    TEST_ASSERT_EQUAL_INT(O2P_SP_WAIT, o2p_sp_service(&p, 50u, 7u));
    TEST_ASSERT_EQUAL_INT(O2P_SP_REVERT,
                          o2p_sp_service(&p, (uint32_t)(t0 + O2P_SERIAL_PROBATION_MS), 7u));
}

static void test_probation_survives_a_frame_counter_wrap(void)
{
    /* The counter is compared for INEQUALITY. Armed at 0xFFFFFFFF, the next
     * frame takes it to 0 - which is "less than" the mark, and a magnitude
     * comparison would read the arrival as silence and revert a link that is
     * demonstrably working. */
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 0xFFFFFFFFu, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    TEST_ASSERT_EQUAL_INT(O2P_SP_CONFIRMED, o2p_sp_service(&p, 1100u, 0u));
}

static void test_a_second_change_keeps_the_first_fallback(void)
{
    /* Belt to main.c's braces. main.c always arms with the FLASH triplet, so
     * two arms in a row supply the same values anyway - but the rule is kept
     * here so that a future caller passing something else cannot make the
     * second of two bad writes the fallback for the first. An unproven
     * setting is not a fallback, it is a second guess. */
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 7u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    o2p_sp_arm(&p, 3000u, 7u, 9u, O2P_BAUD_38400, O2P_PARITY_NONE);
    TEST_ASSERT_EQUAL_UINT8(3u, p.prev_slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_9600, p.prev_baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_EVEN, p.prev_parity_code);
    /* The deadline and the mark DO move: what is being judged is the newest
     * setting, and the second write restarts its clock. */
    TEST_ASSERT_EQUAL_INT(O2P_SP_WAIT,
                          o2p_sp_service(&p, 1000u + O2P_SERIAL_PROBATION_MS, 7u));
    TEST_ASSERT_EQUAL_INT(O2P_SP_REVERT,
                          o2p_sp_service(&p, 3000u + O2P_SERIAL_PROBATION_MS, 7u));
}

static void test_a_commit_riding_a_serial_change_waits_for_it(void)
{
    /* BAUD_CODE = 38400 and COMMIT in ONE FC16. Committing straight away
     * would put the new baud in flash; the probation would then restore the
     * RAM config and leave the probe answering at 9600 while flash said
     * 38400 - so its very next reset would strand it at settings nobody could
     * reach. A self-healing mistake made permanent through the back door. */
    /* Built from the config the probe is actually holding, so the frame
     * differs from a no-op in exactly two registers and cannot fail
     * validation for an unrelated reason. 0x31 and 0x3E are not adjacent, so
     * "both in one frame" necessarily means the whole span between them. */
    uint16_t vals[14];
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_read(&rm, 0x0031, 14, vals));
    vals[0] = O2P_BAUD_38400;                       /* 0x31 BAUD_CODE */
    vals[13] = O2P_COMMIT_MAGIC;                    /* 0x3E COMMIT */
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_write(&rm, 0x0031, 14, vals));
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, rm.cfg.baud_code);
    TEST_ASSERT_TRUE(rm.serial_probation);
    TEST_ASSERT_TRUE(rm.commit_after_serial);
    TEST_ASSERT_FALSE(rm.commit_pending);
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_PENDING, O2P_CMD_RESULT_COMMIT(rm.cmd_result));
}

static void test_a_commit_with_no_serial_change_is_not_delayed(void)
{
    /* The gate must not become a tax on every commit. Nothing about a
     * calibration or an RH setpoint needs the link re-proven. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x3E, 0x5A, 0xC1};
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_FALSE(rm.serial_probation);
    TEST_ASSERT_FALSE(rm.commit_after_serial);
    TEST_ASSERT_TRUE(rm.commit_pending);
}

static void test_the_commit_gate_is_the_only_way_in(void)
{
    /* request_commit() is what main.c's calibration path calls too, so the
     * gate cannot be walked around by asking from somewhere else. */
    rm.serial_probation = true;
    o2p_regmap_request_commit(&rm);
    TEST_ASSERT_FALSE(rm.commit_pending);
    TEST_ASSERT_TRUE(rm.commit_after_serial);

    rm.serial_probation = false;
    rm.commit_after_serial = false;
    o2p_regmap_request_commit(&rm);
    TEST_ASSERT_TRUE(rm.commit_pending);
}

static void test_writing_a_serial_register_its_own_value_changes_nothing(void)
{
    /* A master that rewrites its whole config block touches all three
     * reachability registers every time. Treating that as a change armed a
     * ten-second probation and, with a COMMIT in the same frame, deferred it
     * behind proof that a five-minute Dragino poll would never deliver - so
     * the commit could only ever report FAILED. */
    uint16_t vals[14];
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_read(&rm, 0x0031, 14, vals));
    vals[13] = O2P_COMMIT_MAGIC;                    /* 0x3E COMMIT, no change */
    TEST_ASSERT_EQUAL_UINT8(0, o2p_regmap_write(&rm, 0x0031, 14, vals));
    TEST_ASSERT_FALSE(rm.serial_reconfig_pending);
    TEST_ASSERT_FALSE(rm.serial_probation);
    TEST_ASSERT_FALSE(rm.commit_after_serial);
    TEST_ASSERT_TRUE(rm.commit_pending);
}

static void test_apply_confirmed_promotes_the_waiting_commit(void)
{
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 7u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    rm.cfg.baud_code = O2P_BAUD_38400;
    rm.serial_probation = true;
    rm.commit_after_serial = true;

    TEST_ASSERT_FALSE(o2p_sp_apply(&p, O2P_SP_CONFIRMED, &rm));
    TEST_ASSERT_FALSE(rm.serial_probation);
    TEST_ASSERT_FALSE(rm.commit_after_serial);
    TEST_ASSERT_TRUE(rm.commit_pending);
    /* And the new settings STAY. */
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, rm.cfg.baud_code);
}

static void test_apply_revert_restores_only_the_three_fields(void)
{
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 7u, 5u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    rm.cfg.slave_addr = 9u;
    rm.cfg.baud_code = O2P_BAUD_38400;
    rm.cfg.parity_code = O2P_PARITY_NONE;
    rm.cfg.rh_setpoint_x100 = 4242u;      /* set by the same frame */
    rm.serial_probation = true;

    TEST_ASSERT_TRUE(o2p_sp_apply(&p, O2P_SP_REVERT, &rm));
    TEST_ASSERT_EQUAL_UINT8(5u, rm.cfg.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_9600, rm.cfg.baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_EVEN, rm.cfg.parity_code);
    /* The master's inability to reach the new ADDRESS says nothing about
     * whether it meant the new setpoint. Reverting that too would let one
     * mistyped baud code silently discard a batch of deliberate settings. */
    TEST_ASSERT_EQUAL_UINT16(4242u, rm.cfg.rh_setpoint_x100);
    TEST_ASSERT_FALSE(rm.serial_probation);
}

static void test_a_revert_fails_a_commit_in_either_queue(void)
{
    /* commit_after_cal has to be named explicitly. finish_o2() can run long
     * after the probation resolved, and by then the gate is open - so the
     * master would be told OK for a configuration whose serial change was
     * silently undone, where the non-cal path says FAILED. Two answers to one
     * question is worse than the wrong one. */
    o2p_serial_probation_t p = {0};
    o2p_sp_arm(&p, 1000u, 7u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    rm.serial_probation = true;
    rm.commit_after_cal = true;
    o2p_regmap_set_commit_result(&rm, O2P_CMD_PENDING);

    TEST_ASSERT_TRUE(o2p_sp_apply(&p, O2P_SP_REVERT, &rm));
    TEST_ASSERT_FALSE(rm.commit_after_cal);
    TEST_ASSERT_FALSE(rm.commit_pending);
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_FAILED,
                            O2P_CMD_RESULT_COMMIT(rm.cmd_result));

    /* The calibration itself survives; it can be committed again at settings
     * that work. */
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_NONE, O2P_CMD_RESULT_CAL(rm.cmd_result));
}

static void test_apply_is_a_no_op_while_the_probation_is_undecided(void)
{
    o2p_serial_probation_t p = {0};
    rm.cfg.baud_code = O2P_BAUD_38400;
    rm.serial_probation = true;
    rm.commit_after_serial = true;
    TEST_ASSERT_FALSE(o2p_sp_apply(&p, O2P_SP_WAIT, &rm));
    TEST_ASSERT_TRUE(rm.serial_probation);
    TEST_ASSERT_TRUE(rm.commit_after_serial);
    TEST_ASSERT_FALSE(rm.commit_pending);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, rm.cfg.baud_code);
}

static void test_measurement_registers_are_not_writable(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x00, 0x07, 0xD0};
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, rsp[2]);
}

/* ------------------------------------------------------- oxygen the maths */

/* Standard sea-level pressure. Every row of the table in
 * O2-HUMIDITY-CORRECTION.md section 2 is computed at this P, so the vapour
 * vectors below reproduce those numbers exactly. */
#define TEST_P_HPA 1013.25f

static o2p_gas_t gas_at(float t_c, float rh_pct, float p_hpa)
{
    o2p_gas_t g;
    g.rh_pct = rh_pct;
    g.t_c = t_c;
    g.p_hpa = p_hpa;
    g.valid = true;
    return g;
}

/* Bone-dry air. The vapour correction must be EXACTLY a no-op here, which is
 * also what keeps every pre-existing oxygen test meaning what it used to. */
static o2p_gas_t dry_air(void)
{
    return gas_at(25.0f, 0.0f, TEST_P_HPA);
}

static bool cal_air_dry(o2p_cal_t *cal, int32_t na, int16_t t100)
{
    o2p_gas_t g = dry_air();
    return o2p_calibrate_air(cal, na, t100, &g);
}

static void test_air_calibration_round_trips(void)
{
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    cal.tempco_per_k = 0.0f;
    TEST_ASSERT_TRUE(cal_air_dry(&cal, 70000, 2500));

    float c = 0;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 70000, 2500, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, O2P_C_AIR, c);
    TEST_ASSERT_EQUAL_UINT16(2095, o2p_encode_percent(O2P_OK, c));

    /* Half the air current is NOT half the oxygen - the response is
     * logarithmic. C = 1 - exp(-0.5*ln(1/(1-0.20946))) = 0.1112. */
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 35000, 2500, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.1112f, c);
}

static void test_uncalibrated_cell_is_unevaluable_not_zero(void)
{
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    float c = 12345.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, 70000, 2500, &c));
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID,
                             o2p_encode_percent(O2P_UNEVALUABLE, 0.0f));
}

static void test_inverted_cell_polarity_is_reported_not_clamped(void)
{
    /* The SGX sign convention is an open release gate
     * (SCHEMATIC-REVIEW.md M4). A negative current must surface as RANGE so
     * the bench sees it, not be clamped to a comfortable 0.00 %vol. */
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(cal_air_dry(&cal, 70000, 2500));
    float c = 0;
    TEST_ASSERT_EQUAL(O2P_RANGE, o2p_fraction_from_current(&cal, -70000, 2500, &c));
    TEST_ASSERT_TRUE(c < 0.0f);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, o2p_encode_percent(O2P_RANGE, c));
}

static void test_overrange_is_not_clamped_into_plausibility(void)
{
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(cal_air_dry(&cal, 70000, 2500));
    float c = 0;
    /* Far above the cell's 30 % overload limit. */
    TEST_ASSERT_EQUAL(O2P_RANGE, o2p_fraction_from_current(&cal, 190000, 2500, &c));
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, o2p_encode_percent(O2P_RANGE, c));
}

static void test_monotonic_across_the_whole_range(void)
{
    /* As the cell current worsens toward zero the reported oxygen must fall
     * monotonically and never flip back into a plausible mid-range value. */
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(cal_air_dry(&cal, 70000, 2500));
    float prev = 1e9f;
    for (int32_t na = 100000; na >= 0; na -= 1000) {
        float c = 0;
        o2p_status_t st = o2p_fraction_from_current(&cal, na, 2500, &c);
        TEST_ASSERT_NOT_EQUAL(O2P_UNEVALUABLE, st);
        TEST_ASSERT_TRUE(c <= prev + 1e-6f);
        prev = c;
    }
}

static void test_absurd_tempco_cannot_produce_a_number(void)
{
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(cal_air_dry(&cal, 70000, 2500));
    cal.tempco_per_k = -0.05f;          /* drives the gain through zero at +20 K */
    float c = 0;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, 70000, 4500, &c));
}

static void test_written_calibration_must_also_be_plausible(void)
{
    /* The automatic air-point routine has always range-checked its input, but
     * a Modbus WRITE to CAL_AIR_NA_HI/LO used to be accepted on the sole
     * condition that it was not negative. Writing the two halves of an
     * intended 70000 nA in the wrong order gives 0x11700001 = 292552705 nA,
     * which makes K enormous and converts every real reading to ~0.006 %vol
     * - published as 0.01 %vol with NEITHER CAL_DEFAULT nor ADC_RANGE set.
     * A buried probe would report a hard anoxic pile, in range, with a clean
     * fault word. */
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t swapped[] = {0x03, 0x10, 0x00, 0x37, 0x00, 0x02, 0x04,
                               0x11, 0x70, 0x00, 0x01};
    size_t n = framed(req, swapped, sizeof(swapped));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_INT32(0, rm.cfg.cal_air_na);

    /* The same value written correctly is accepted. */
    const uint8_t good[] = {0x03, 0x10, 0x00, 0x37, 0x00, 0x02, 0x04,
                            0x00, 0x01, 0x11, 0x70};
    n = framed(req, good, sizeof(good));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(8, len);
    TEST_ASSERT_EQUAL_INT32(70000, rm.cfg.cal_air_na);

    /* And zero still means "never calibrated", which is legal. */
    const uint8_t zero[] = {0x03, 0x10, 0x00, 0x37, 0x00, 0x02, 0x04,
                            0x00, 0x00, 0x00, 0x00};
    n = framed(req, zero, sizeof(zero));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_INT32(0, rm.cfg.cal_air_na);
}

static void test_implausible_air_point_is_rejected(void)
{
    /* A calibration taken in nitrogen, or with the cell unplugged, must not
     * overwrite a good one. */
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(cal_air_dry(&cal, 70000, 2500));
    TEST_ASSERT_FALSE(cal_air_dry(&cal, 200, 2500));
    TEST_ASSERT_FALSE(cal_air_dry(&cal, 900000, 2500));
    TEST_ASSERT_EQUAL_INT32(70000, cal.cal_air_na);
}

/* ------------------------------------------------------- validity matrix */

static void test_uncalibrated_invalidates_comp_but_not_raw(void)
{
    /* An uncalibrated cell still measures a real current, so the RAW channel
     * stands. The COMPENSATED channel is that current divided by a constant
     * nobody has measured - the datasheet nominal spans 0.04-0.10 mA - so a
     * 12 %vol reading against a true 21 %vol would be indistinguishable from
     * a genuinely alarming result. */
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_CAL_DEFAULT));
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_CAL_DEFAULT));
    /* TEMP_OVER still invalidates neither. */
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_TEMP_OVER));
    TEST_ASSERT_TRUE(o2p_o2_comp_valid(O2P_F_TEMP_OVER));
    /* Anything that kills the raw channel kills the compensated one too. */
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_ADC_RANGE));
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_SETTLING));
}

static void test_discovery_alias_refuses_writes(void)
{
    /* The SMT100 re-addressing recipe writes through 253. With two devices
     * answering the alias that reconfigures both, so ours refuses - the
     * address is recoverable by READING through 253 instead. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0xFD, 0x06, 0x00, 0x30, 0x00, 0x07};
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(5, len);
    TEST_ASSERT_EQUAL_HEX8(0x86, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_FUNCTION, rsp[2]);
    TEST_ASSERT_EQUAL_UINT8(3, rm.cfg.slave_addr);
}

static void test_snapshot_reset_clears_every_measurement_channel(void)
{
    /* The sampler builds each cycle from invalid rather than copying the
     * previous snapshot forward. If this ever stops clearing a channel, a
     * dead sensor publishes last cycle's plausible value under this cycle's
     * fault word. */
    o2p_snapshot_t *s = o2p_regmap_staging(&rm);
    s->o2_comp = 1234; s->o2_raw = 1234; s->t_tip = 1234; s->t_chamber = 1234;
    s->rh_chamber = 1234; s->dew_margin_x100 = 1234; s->vref_mv = 1234;
    s->va_mv = 1234; s->vin_mv = 1234; s->afe_vout_mv = 1234;
    s->lmp_readback = 1234; s->pressure_hpa = 1234; s->t_die = 1234;
    s->sample_seq = 77;   /* cumulative: must SURVIVE */

    o2p_snapshot_reset(s);

    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->o2_comp);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->o2_raw);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_tip);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_chamber);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_die);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->rh_chamber);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID,
                            (uint16_t)s->dew_margin_x100);
    /* The unsigned diagnostics must reset to the SENTINEL, not to zero.
     * Zero is a perfectly possible real reading for every one of them - 0 mV
     * on a collapsed rail, an all-zero LMP91000 register image after a reset
     * - so publishing zero for "not measured" would be indistinguishable from
     * a genuine and alarming measurement. */
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->vref_mv);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->va_mv);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->vin_mv);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->afe_vout_mv);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->lmp_readback);
    /* pressure_hpa is the documented exception: 0 states that the BMP390
     * footprint is not populated, which is a fact about the board. */
    TEST_ASSERT_EQUAL_UINT16(0, s->pressure_hpa);
    TEST_ASSERT_EQUAL_UINT16(77, s->sample_seq);
}

static void test_heater_gains_are_writable_and_bounded(void)
{
    /* The gains exist as registers because the plant can only be
     * characterised in a real pile, and the alternative to a register write
     * is a full firmware transfer through a bootloader that does not exist. */
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];

    /* kp = 3.50, ki = 0.25 in one FC16. */
    const uint8_t good[] = {0x03, 0x10, 0x00, 0x40, 0x00, 0x02, 0x04,
                            0x01, 0x5E, 0x00, 0x19};
    size_t n = framed(req, good, sizeof(good));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(8, len);
    TEST_ASSERT_EQUAL_UINT16(350, rm.cfg.heater_kp_x100);
    TEST_ASSERT_EQUAL_UINT16(25, rm.cfg.heater_ki_x100);

    /* Zero is legal: kp = 0 with ki > 0 is a pure integrator, and both zero
     * simply means the loop never asks for heat. */
    const uint8_t zero[] = {0x03, 0x06, 0x00, 0x40, 0x00, 0x00};
    n = framed(req, zero, sizeof(zero));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT16(0, rm.cfg.heater_kp_x100);

    /* Above the ceiling is refused, and refused ATOMICALLY - the frame that
     * carries it must change neither gain. */
    uint16_t ki_before = rm.cfg.heater_ki_x100;
    const uint8_t huge[] = {0x03, 0x10, 0x00, 0x40, 0x00, 0x02, 0x04,
                            0xFF, 0xFF, 0x00, 0x64};
    n = framed(req, huge, sizeof(huge));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_UINT16(0, rm.cfg.heater_kp_x100);
    TEST_ASSERT_EQUAL_UINT16(ki_before, rm.cfg.heater_ki_x100);
}

static void test_gain_registers_read_back_what_was_written(void)
{
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t w[] = {0x03, 0x10, 0x00, 0x40, 0x00, 0x02, 0x04,
                         0x00, 0xC8, 0x00, 0x0A};
    size_t n = framed(req, w, sizeof(w));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);

    const uint8_t r[] = {0x03, 0x03, 0x00, 0x40, 0x00, 0x02};
    n = framed(req, r, sizeof(r));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(3 + 4 + 2, len);
    TEST_ASSERT_EQUAL_UINT16(200, (rsp[3] << 8) | rsp[4]);
    TEST_ASSERT_EQUAL_UINT16(10, (rsp[5] << 8) | rsp[6]);
}

static void test_config_block_read_covers_the_gains(void)
{
    /* The block grew from 16 to 18 registers with the gains, to 20 with
     * ASSUMED_P_HPA and CAL_AIR_FRAC, to 21 with CAL_P_HPA, to 22 with
     * DIL_ALPHA, to 24 with the CAL_ZERO_NA pair and to 25 with
     * HEATER_RH_CONSENT, and to 27 with TIP_SETPOINT and HEATER_TIP_CONSENT.
     * A read of all 27 must succeed; 28 must not, or the boundary rule has
     * quietly stopped being enforced. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t all[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x1B};
    size_t n = framed(req, all, sizeof(all));
    TEST_ASSERT_EQUAL_UINT(3 + 54 + 2, o2p_mb_dispatch(req, n, 3, &handlers, rsp));

    const uint8_t over[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x1C};
    n = framed(req, over, sizeof(over));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, rsp[2]);
}

/* Clip detection. The failure it exists to stop is a converter pinned against
 * a rail that keeps answering with a number that looks like a measurement. */
static void test_clip_detection(void)
{
    /* Mid-scale and ordinary readings are not clipped. The oxygen channel in
     * air sits nowhere near either rail. */
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(0));
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(1000));
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(16384));
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(-1000));

    /* Both rails, exactly. */
    TEST_ASSERT_TRUE(o2p_ads1119_code_clipped(32767));
    TEST_ASSERT_TRUE(o2p_ads1119_code_clipped(-32768));

    /* And within the noise margin of each, because a signal resting on a rail
     * dithers by a count or two and an equality test would miss it on exactly
     * the samples that matter. */
    TEST_ASSERT_TRUE(o2p_ads1119_code_clipped(32767 - O2P_ADS_CLIP_MARGIN));
    TEST_ASSERT_TRUE(o2p_ads1119_code_clipped(-32768 + O2P_ADS_CLIP_MARGIN));

    /* Just inside the margin is still a measurement: the guard must not eat
     * legitimate near-full-scale readings. */
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(32767 - O2P_ADS_CLIP_MARGIN - 1));
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(-32768 + O2P_ADS_CLIP_MARGIN + 1));

    /* Monotonicity: once clipped, worse cannot become OK again. */
    for (int32_t c = 32767 - O2P_ADS_CLIP_MARGIN; c <= 32767; c++) {
        TEST_ASSERT_TRUE(o2p_ads1119_code_clipped((int16_t)c));
    }
}

static void test_validity_matrix(void)
{
    static const uint16_t invalidating[] = {
        O2P_F_I2C_FAIL_LMP, O2P_F_I2C_FAIL_ADS,
        O2P_F_AFE_CONFIG_MISMATCH, O2P_F_VA_LOW, O2P_F_ADC_RANGE,
        O2P_F_ADS_DRDY_STUCK, O2P_F_ADS_CONFIG_LOST,
    };
    for (unsigned i = 0; i < sizeof(invalidating) / sizeof(invalidating[0]); i++) {
        TEST_ASSERT_FALSE(o2p_o2_valid(invalidating[i]));
        TEST_ASSERT_FALSE(o2p_o2_comp_valid(invalidating[i]));
    }

    /* SETTLING and CAL_DEFAULT are the two faults that split the channels.
     * Both say the DIVISOR is unusable - no equilibrium yet, or no calibration
     * constant - while the cell current underneath is a real measurement.
     * Before 2026-09-08 SETTLING blanked the raw channel too, which deleted
     * the settling transient itself for 900 s after every reset. */
    TEST_ASSERT_TRUE_MESSAGE(o2p_o2_valid(O2P_F_SETTLING),
        "an unsettled cell still has a real current, and it is the only "
        "record of the cell settling");
    TEST_ASSERT_FALSE_MESSAGE(o2p_o2_comp_valid(O2P_F_SETTLING),
        "no %vol derived from a cell that has not reached equilibrium is "
        "trustworthy");
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_CAL_DEFAULT));
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_CAL_DEFAULT));

    /* The split must survive the two arriving together - the state a probe is
     * actually in on its first power-up out of the potting jig. */
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_SETTLING | O2P_F_CAL_DEFAULT));
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_SETTLING | O2P_F_CAL_DEFAULT));

    /* ...and that an ACQUISITION fault still wins over both. */
    TEST_ASSERT_FALSE(o2p_o2_valid(O2P_F_SETTLING | O2P_F_ADS_DRDY_STUCK));

    /* The two documented exceptions. Both mark the reading as lower quality;
     * neither discards it. */
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_TEMP_OVER));
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_TEMP_OVER | O2P_F_CAL_DEFAULT |
                                  O2P_F_HEATER_DISABLED | O2P_F_DEW_SUSPECT));
    /* And a fault that does invalidate still does so in company. */
    TEST_ASSERT_FALSE(o2p_o2_valid(O2P_F_TEMP_OVER | O2P_F_ADC_RANGE));
}

static void test_snapshot_is_invalid_before_the_first_sample(void)
{
    /* A freshly initialised probe that never completes a conversion must not
     * report 0.00 %vol at 0.00 C with no faults. */
    const o2p_snapshot_t *s = o2p_regmap_live(&rm);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->o2_comp);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_tip);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_die);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->rh_chamber);
    TEST_ASSERT_TRUE((s->faults & O2P_F_SETTLING) != 0);
    /* Assert the VALUE, not the mask. "No conversion has happened yet" is a
     * property of the snapshot, and o2p_snapshot_reset() enforces it directly;
     * testing o2p_o2_valid() here used the fault mask as a PROXY for it, so
     * this case broke on 2026-09-08 when SETTLING stopped invalidating the raw
     * channel - even though the sentinel it actually cares about was still
     * correctly in place. */
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->o2_raw);
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(s->faults));
}


/* ------------------------------------------------- oxygen: water vapour
 *
 * Every vector here comes from O2-HUMIDITY-CORRECTION.md, which is the spec
 * for this correction: section 2's table, section 3b's calibration bias,
 * section 1's bench observation, and section 5's guard rules. The document
 * computes its table at standard sea-level pressure, so TEST_P_HPA does too;
 * the numbers below are the document's own, to the digit it prints.
 */

static void test_vapour_table_from_the_spec(void)
{
    /* "reads" in the section 2 table is the oxygen fraction actually PRESENT
     * in fully aerated air at that condition - the thing a wet-basis channel
     * publishes and the thing the correction has to undo. */
    static const struct { float t, rh, reads; } row[] = {
        {25.0f,  50.0f, 20.620f},
        {25.0f, 100.0f, 20.293f},
        {40.0f, 100.0f, 19.424f},
        {60.0f, 100.0f, 16.815f},   /* the operating point: -19.7 % */
        {75.0f, 100.0f, 12.902f},   /* the excursion, beyond the Magnus fit */
    };
    /* The tolerance is the DOCUMENT'S rounding, not slack in the code: the
     * table prints three decimals of %vol derived from a p_w printed to two
     * decimals of kPa, so its 19.424 is this arithmetic's 19.42299 and its
     * 12.902 is 12.89838. Five millivol still separates rows that are two
     * whole %vol apart, so nothing is being waved through - and if the
     * correction were dropped entirely, every row would be out by 0.3 to 8
     * %vol, three orders of magnitude past this. */
    for (unsigned i = 0; i < sizeof(row) / sizeof(row[0]); i++) {
        o2p_gas_t g = gas_at(row[i].t, row[i].rh, TEST_P_HPA);
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_air_fraction(&g, 1.0f, &c));
        TEST_ASSERT_FLOAT_WITHIN(0.005f, row[i].reads, c * 100.0f);

        /* And the correction is the exact inverse: wet -> dry recovers dry
         * air, which is the whole claim. */
        float dry_c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, c, 1.0f, &dry_c));
        TEST_ASSERT_FLOAT_WITHIN(0.00002f, O2P_C_AIR, dry_c);
    }
}

static void test_dry_air_correction_is_exactly_a_no_op(void)
{
    /* 0 %RH: p_w is exactly zero, the factor is exactly one. Not "close to" -
     * a special case for zero would be a branch that could rot, so this must
     * hold bit-for-bit through the general path. */
    o2p_gas_t g = dry_air();
    float c = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.20946f, 1.0f, &c));
    TEST_ASSERT_EQUAL_FLOAT(0.20946f, c);

    float pw = 12345.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&g, &pw));
    TEST_ASSERT_EQUAL_FLOAT(0.0f, pw);

    /* At every temperature, including ones where saturated air is a huge
     * correction. Dryness, not coldness, is what makes it a no-op. */
    for (float t = -20.0f; t <= O2P_VAPOUR_T_MAX_C; t += 5.0f) {
        o2p_gas_t d = gas_at(t, 0.0f, TEST_P_HPA);
        float x = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&d, 0.15f, 1.0f, &x));
        TEST_ASSERT_EQUAL_FLOAT(0.15f, x);
    }
}

static void test_calibration_in_moist_air_rescales_k(void)
{
    /* Section 3b. The air point is taken in ambient room air, which is moist;
     * attributing that current to dry 20.946 % makes K too small and every
     * later reading too large, by an amount nobody ever sees because it is
     * baked in. The three rows are the document's. */
    static const struct { float t, rh, c_true, k_err_pct; } row[] = {
        {23.4f, 42.3f, 0.2070f, 1.37f},   /* the air point this bench took */
        {25.0f, 60.0f, 0.2055f, 2.15f},
        {20.0f, 80.0f, 0.2056f, 2.11f},
    };
    for (unsigned i = 0; i < sizeof(row) / sizeof(row[0]); i++) {
        o2p_gas_t g = gas_at(row[i].t, row[i].rh, TEST_P_HPA);
        o2p_cal_t cal = { .dil_alpha = 1.0f };
        TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2340, &g));
        TEST_ASSERT_FLOAT_WITHIN(0.0001f, row[i].c_true, cal.air_frac);

        /* K = S_air / ln(1/(1-C)). The old code used the dry C for every air
         * point; the error that introduces is what the table quotes. */
        float k_true = 70000.0f / logf(1.0f / (1.0f - cal.air_frac));
        float k_dry  = 70000.0f / O2P_LN_AIR;
        TEST_ASSERT_FLOAT_WITHIN(0.02f, row[i].k_err_pct,
                                 (k_true / k_dry - 1.0f) * 100.0f);

        /* And the round trip closes: the cell current recorded at the air
         * point converts back to the fraction that was actually there, and
         * the correction lifts that to dry air. */
        float c_wet = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_fraction_from_current(&cal, 70000, 2340, &c_wet));
        TEST_ASSERT_FLOAT_WITHIN(0.0002f, row[i].c_true, c_wet);
        float c_dry = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_dry_fraction_from_current(&cal, 70000, 2340, &g,
                                                        &c_dry));
        TEST_ASSERT_FLOAT_WITHIN(0.0002f, O2P_C_AIR, c_dry);
    }
}

static void test_bench_humidity_step_no_longer_moves_the_channel(void)
{
    /* Section 1, measured 2026-09-06 with the probe undisturbed and no fault
     * flags: raising a closed chamber from 42.3 %RH / 23.4 C to 63.9 %RH /
     * 25.0 C moved the raw cell current from 100.20 to 99.68 uA, and moved
     * the published oxygen by -0.48 %.
     *
     * Calibrate at the first point - the chamber is aerated room air - and
     * the second point must come back to the same dry-basis number. */
    o2p_gas_t g1 = gas_at(23.4f, 42.3f, TEST_P_HPA);
    o2p_gas_t g2 = gas_at(25.0f, 63.9f, TEST_P_HPA);

    o2p_cal_t cal = { .dil_alpha = 1.0f };
    /* The cell's own temperature coefficient, ~+0.2 %/K, which section 1
     * identifies as the rest of the observed step. It is a shipped default of
     * ZERO in the firmware because SGX publishes no curve, so this test also
     * shows what that costs: with it, the corrected channel is flat; without
     * it, what remains is the tempco and not the humidity. */
    cal.tempco_per_k = 0.002f;
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 100200, 2340, &g1));

    float wet1 = 0.0f, wet2 = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_fraction_from_current(&cal, 100200, 2340, &wet1));
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_fraction_from_current(&cal, 99680, 2500, &wet2));
    /* The uncorrected channel moves, and by about what was seen. */
    TEST_ASSERT_TRUE((wet1 - wet2) * 100.0f > 0.05f);

    float dry1 = 0.0f, dry2 = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&cal, 100200, 2340, &g1,
                                                    &dry1));
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&cal, 99680, 2500, &g2,
                                                    &dry2));
    /* 0.02 %vol is two counts of the published register and well inside the
     * ~0.1 %vol the raw channel resolves. The uncorrected pair above is five
     * times that. */
    TEST_ASSERT_FLOAT_WITHIN(0.0002f, dry1, dry2);
    TEST_ASSERT_FLOAT_WITHIN(0.0002f, O2P_C_AIR, dry1);
}

static void test_vapour_correction_fails_closed(void)
{
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    o2p_gas_t good = gas_at(25.0f, 50.0f, TEST_P_HPA);
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500, &good));

    float c = 12345.0f;

    /* The SHT45 did not deliver this cycle. There is no RH and no chamber
     * temperature, and the ONLY acceptable answer is the sentinel: falling
     * through to the wet-basis number while still calling it corrected is the
     * failure this whole file is against. */
    o2p_gas_t none = gas_at(25.0f, 50.0f, TEST_P_HPA);
    none.valid = false;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&none, 0.20f, 1.0f, &c));
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_dry_fraction_from_current(&cal, 70000, 2500, &none, &c));
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID,
                             o2p_encode_percent(O2P_UNEVALUABLE, c));
    TEST_ASSERT_EQUAL_FLOAT(12345.0f, c);   /* nothing was written */

    /* A humidity that is not a humidity. 0 %RH is legal (and a no-op);
     * negative and >100 are sensor faults, not dry air. */
    o2p_gas_t bad_rh = gas_at(25.0f, -1.0f, TEST_P_HPA);
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&bad_rh, 0.20f, 1.0f, &c));
    bad_rh.rh_pct = 101.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&bad_rh, 0.20f, 1.0f, &c));

    /* Temperature sentinel. O2P_I16_INVALID is 0x8000, i.e. -327.68 C once
     * scaled, which is below the Magnus singularity; a NaN gets there from
     * the same place by another route. */
    o2p_gas_t bad_t = gas_at((float)O2P_I16_INVALID * 0.01f, 50.0f, TEST_P_HPA);
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&bad_t, 0.20f, 1.0f, &c));
    bad_t.t_c = NAN;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&bad_t, 0.20f, 1.0f, &c));

    /* P of zero - which is exactly what PRESSURE_HPA publishes with the
     * BMP390 DNP, so this is the case a missing ASSUMED_P_HPA would hit. It
     * must not divide by it and must not assume a standard atmosphere. */
    o2p_gas_t no_p = gas_at(25.0f, 50.0f, 0.0f);
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&no_p, 0.20f, 1.0f, &c));
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_air_fraction(&no_p, 1.0f, &c));
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 70000, 2500, &no_p));
    /* ...and the refused calibration left the good one standing. */
    TEST_ASSERT_EQUAL_INT32(70000, cal.cal_air_na);

    /* An air point taken with no humidity reading is refused outright rather
     * than stored against an assumed dry atmosphere: that assumption IS the
     * 1-2 % bias in K, and it would be permanent. */
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 70000, 2500, &none));
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 70000, 2500, NULL));

    /* An unknown air fraction cannot convert either. A stored calibration
     * from before this change has cal_air_na but no fraction, and it must
     * produce the sentinel rather than a 1-2 %-biased number. */
    o2p_cal_t stale = { .dil_alpha = 1.0f };
    stale.cal_air_na = 70000;
    stale.cal_temp_c100 = 2500;
    stale.air_frac = 0.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&stale, 70000, 2500, &c));
}

static void test_vapour_correction_is_monotonic(void)
{
    /* As the gas gets wetter, the dry-basis answer must rise and keep rising.
     * A correction that folds back would read as the pile RE-aerating exactly
     * when it is hottest and wettest. Swept to 100 %RH and to 75 C, not just
     * near room conditions. */
    for (float t = 0.0f; t <= 75.0f; t += 5.0f) {
        float prev = -1.0f;
        for (float rh = 0.0f; rh <= 100.0f; rh += 1.0f) {
            o2p_gas_t g = gas_at(t, rh, TEST_P_HPA);
            float c = 0.0f;
            TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, 1.0f, &c));
            TEST_ASSERT_TRUE(c >= prev);
            prev = c;
        }
    }
    /* And monotonic in temperature at fixed humidity, for the same reason. */
    float prev = -1.0f;
    for (float t = 0.0f; t <= 75.0f; t += 1.0f) {
        o2p_gas_t g = gas_at(t, 100.0f, TEST_P_HPA);
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, 1.0f, &c));
        TEST_ASSERT_TRUE(c >= prev);
        prev = c;
    }
    /* Monotonic in pressure too: less total pressure, more of it water, more
     * correction. */
    prev = -1.0f;
    for (float p = (float)O2P_P_HPA_MAX; p >= (float)O2P_P_HPA_MIN; p -= 10.0f) {
        o2p_gas_t g = gas_at(50.0f, 90.0f, p);
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, 1.0f, &c));
        TEST_ASSERT_TRUE(c >= prev);
        prev = c;
    }
}

static void test_vapour_correction_is_bounded_not_infinite(void)
{
    float c = 999.0f;
    /* Beyond the temperature ceiling the Magnus fit is extrapolation and the
     * correction is no longer small. Refused, not clamped, and refused for
     * every humidity above zero - and it must STAY refused as the input gets
     * worse rather than coming back with a number. */
    for (float t = O2P_VAPOUR_T_MAX_C + 0.1f; t <= 200.0f; t += 5.0f) {
        o2p_gas_t g = gas_at(t, 100.0f, TEST_P_HPA);
        TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&g, 0.16f, 1.0f, &c));
        TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_air_fraction(&g, 1.0f, &c));
    }
    TEST_ASSERT_EQUAL_FLOAT(999.0f, c);

    /* p_w approaching P sends P/(P-p_w) to infinity. At a thin 500 hPa the
     * vapour bound bites well before the temperature one does, so both guards
     * are exercised. */
    o2p_gas_t thin = gas_at(75.0f, 100.0f, (float)O2P_P_HPA_MIN);
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&thin, 0.16f, 1.0f, &c));
    TEST_ASSERT_EQUAL_FLOAT(999.0f, c);

    /* Just inside the bound the correction is large but finite, and it is
     * still a correction rather than a clamp. */
    o2p_gas_t hot = gas_at(75.0f, 100.0f, TEST_P_HPA);
    float ok = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&hot, 0.12898f, 1.0f, &ok));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, O2P_C_AIR, ok);

    /* A pressure outside the register's window is not a pressure. */
    o2p_gas_t low = gas_at(25.0f, 50.0f, (float)O2P_P_HPA_MIN - 1.0f);
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&low, 0.16f, 1.0f, &c));
    o2p_gas_t high = gas_at(25.0f, 50.0f, (float)O2P_P_HPA_MAX + 1.0f);
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_dry_from_wet(&high, 0.16f, 1.0f, &c));

    /* And the correction can carry a wet reading that is INSIDE the cell's
     * rated window out of it: 27.0 %vol wet at 60 C saturated is 33.7 %vol
     * dry. The window belongs to the published number, so that is a RANGE
     * result - the sentinel - and not a clamp into plausibility. */
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    o2p_gas_t g = gas_at(60.0f, 100.0f, TEST_P_HPA);
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 6000, &g));
    float big = 0.0f;
    o2p_status_t st = o2p_dry_fraction_from_current(&cal, 120000, 6000, &g, &big);
    TEST_ASSERT_EQUAL(O2P_RANGE, st);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, o2p_encode_percent(st, big));
}

static void test_pressure_and_air_fraction_registers_are_bounded(void)
{
    /* ASSUMED_P_HPA scales oxygen directly - sea level to 715 m is 8 % - so
     * an out-of-range write must be refused rather than installed. And the
     * default must be the documented site value, not zero, because zero is
     * the one value that makes the correction unevaluable. */
    TEST_ASSERT_EQUAL_UINT16(O2P_P_HPA_DEFAULT, rm.cfg.assumed_p_hpa);
    TEST_ASSERT_EQUAL_UINT16(0, rm.cfg.cal_air_frac_x1000);

    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t zero_p[] = {0x03, 0x06, 0x00, 0x42, 0x00, 0x00};
    size_t n = framed(req, zero_p, sizeof(zero_p));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_UINT16(O2P_P_HPA_DEFAULT, rm.cfg.assumed_p_hpa);

    const uint8_t huge_p[] = {0x03, 0x06, 0x00, 0x42, 0x0B, 0xB8};  /* 3000 */
    n = framed(req, huge_p, sizeof(huge_p));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);

    const uint8_t good_p[] = {0x03, 0x06, 0x00, 0x42, 0x03, 0xF5};  /* 1013 */
    n = framed(req, good_p, sizeof(good_p));
    TEST_ASSERT_EQUAL_UINT(8, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(1013, rm.cfg.assumed_p_hpa);

    /* CAL_AIR_FRAC: zero means "unknown", which is legal; anything else must
     * be a fraction air can actually have. 20946 is dry air. */
    const uint8_t nitrogen[] = {0x03, 0x06, 0x00, 0x43, 0x00, 0x64};  /* 0.1 % */
    n = framed(req, nitrogen, sizeof(nitrogen));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);

    const uint8_t air[] = {0x03, 0x06, 0x00, 0x43, 0x51, 0xD2};       /* 20946 */
    n = framed(req, air, sizeof(air));
    TEST_ASSERT_EQUAL_UINT(8, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(20946, rm.cfg.cal_air_frac_x1000);

    /* Both read back through the config block. */
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x42, 0x00, 0x02};
    n = framed(req, rd, sizeof(rd));
    TEST_ASSERT_EQUAL_UINT(3 + 4 + 2, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(1013, (rsp[3] << 8) | rsp[4]);
    TEST_ASSERT_EQUAL_UINT16(20946, (rsp[5] << 8) | rsp[6]);
}

static void test_o2_comp_validity_is_data_age_not_the_sht_fault_bit(void)
{
    /* I2C_FAIL_SHT is raised for the SHT45's own SCHEDULED de-creep pulse as
     * well as for a dead sensor, so using it as O2_COMP's validity criterion
     * blanked the primary oxygen channel for 30 s three times a day and
     * labelled scheduled maintenance a bus failure. The criterion is the AGE
     * of the chamber reading instead - see the cache tests below - and this
     * pins the mask so the bit cannot quietly come back. */
    TEST_ASSERT_TRUE(o2p_o2_comp_valid(O2P_F_I2C_FAIL_SHT));
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_I2C_FAIL_SHT));
    TEST_ASSERT_TRUE(o2p_o2_comp_valid(0u));
    TEST_ASSERT_EQUAL_HEX16(0u,
                            O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_I2C_FAIL_SHT);
    /* The calibration constant still does invalidate it, and the raw channel
     * is still the one that survives a dead humidity sensor. */
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_CAL_DEFAULT));
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_CAL_DEFAULT));
}

static void test_p_sat_has_exactly_one_implementation(void)
{
    /* psychro.c owns the Magnus coefficients and o2.c uses them through this
     * function. The check that they have not been forked is that the dew
     * point and the saturation pressure agree: at the dew point, the vapour
     * pressure of the original gas IS the saturation pressure. */
    static const struct { float t, rh; } pt[] = {
        {20.0f, 50.0f}, {25.0f, 100.0f}, {40.0f, 85.0f}, {60.0f, 90.0f},
    };
    for (unsigned i = 0; i < sizeof(pt) / sizeof(pt[0]); i++) {
        float td = 0.0f, es_t = 0.0f, es_td = 0.0f;
        TEST_ASSERT_TRUE(o2p_dewpoint_c(pt[i].t, pt[i].rh, &td));
        TEST_ASSERT_TRUE(o2p_p_sat_hpa(pt[i].t, &es_t));
        TEST_ASSERT_TRUE(o2p_p_sat_hpa(td, &es_td));
        TEST_ASSERT_FLOAT_WITHIN(0.01f, es_t * pt[i].rh * 0.01f, es_td);
    }
    /* The two anchor points of the fit itself, so a changed coefficient is
     * caught here and not only through a derived quantity. */
    float es0 = 0.0f, es100 = 0.0f;
    TEST_ASSERT_TRUE(o2p_p_sat_hpa(0.0f, &es0));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 6.112f, es0);
    /* And 100 C, where the fit returns 1038.4 hPa against the true 1013.25:
     * 2.5 % high, because the Sonntag coefficients are stated only to about
     * +60 C. Pinned to what the fit ACTUALLY gives rather than to physics, so
     * that a changed coefficient fails here instead of hiding inside the
     * error the extrapolation already has. It is also why the oxygen
     * correction refuses above O2P_VAPOUR_T_MAX_C rather than extrapolating
     * further. */
    TEST_ASSERT_TRUE(o2p_p_sat_hpa(100.0f, &es100));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 1038.4f, es100);
}

/* ---------------------------------------------------------- psychrometry */

static void test_dewpoint_reference_points(void)
{
    float td = 0;
    /* Saturated air: dew point equals air temperature. */
    TEST_ASSERT_TRUE(o2p_dewpoint_c(55.0f, 100.0f, &td));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 55.0f, td);

    /* 20 C / 50 %RH is 9.26 C by Magnus-Sonntag. */
    TEST_ASSERT_TRUE(o2p_dewpoint_c(20.0f, 50.0f, &td));
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 9.26f, td);
}

static void test_dewpoint_refuses_impossible_humidity(void)
{
    float td = 12345.0f;
    TEST_ASSERT_FALSE(o2p_dewpoint_c(20.0f, 0.0f, &td));
    TEST_ASSERT_FALSE(o2p_dewpoint_c(20.0f, -5.0f, &td));
    TEST_ASSERT_FALSE(o2p_dewpoint_c(20.0f, 101.0f, &td));
    TEST_ASSERT_EQUAL_FLOAT(12345.0f, td);   /* untouched */
}

static void test_dew_margin_sign(void)
{
    float m = 0;
    /* A tip 3 K above saturated chamber gas has 3 K of margin. */
    TEST_ASSERT_TRUE(o2p_dew_margin_k(58.0f, 55.0f, 100.0f, &m));
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 3.0f, m);
    /* A tip colder than the gas is condensing: margin must go negative. */
    TEST_ASSERT_TRUE(o2p_dew_margin_k(52.0f, 55.0f, 100.0f, &m));
    TEST_ASSERT_TRUE(m < 0.0f);
    /* A failed SHT45 yields no margin at all, not a comfortable one. */
    TEST_ASSERT_FALSE(o2p_dew_margin_k(58.0f, 55.0f, 0.0f, &m));
}

static void test_random_garbage_never_provokes_a_reply(void)
{
    /* "Never transmit unsolicited" is the one rule that protects the other
     * devices on this cable. Pseudo-random frames stand in for line noise, a
     * collision, and another master's traffic: none may produce a response
     * unless they happen to be a valid ADU addressed to us, which a random
     * 16-bit CRC will essentially never be.
     *
     * Fixed seed, so a failure is reproducible rather than a flake. */
    uint32_t seed = 0x13572468u;
    uint8_t buf[64], rsp[O2P_MB_MAX_ADU];
    unsigned replies = 0;

    for (unsigned trial = 0; trial < 20000u; trial++) {
        seed = seed * 1664525u + 1013904223u;
        size_t len = 1u + (seed >> 24) % 40u;
        for (size_t i = 0; i < len; i++) {
            seed = seed * 1664525u + 1013904223u;
            buf[i] = (uint8_t)(seed >> 16);
        }
        o2p_mb_disposition_t d = o2p_mb_classify(buf, len, 3);
        if (d == O2P_MB_DROP) {
            continue;
        }
        /* Passed CRC by chance and was addressed to us. It may legitimately
         * answer - but it must never run off the end of the buffer or return
         * a length longer than an ADU. */
        size_t n = o2p_mb_dispatch(buf, len, 3, &handlers, rsp);
        TEST_ASSERT_TRUE(n <= O2P_MB_MAX_ADU);
        if (n > 0u) {
            replies++;
            /* Whatever it is, it must be a well-formed ADU. */
            TEST_ASSERT_TRUE(n >= 4u);
            uint16_t sent = (uint16_t)rsp[n - 2] | ((uint16_t)rsp[n - 1] << 8);
            TEST_ASSERT_EQUAL_HEX16(o2p_mb_crc16(rsp, n - 2), sent);
        }
    }
    /* A 16-bit CRC over random bytes passes about 1 in 65536, and only a
     * fraction of those carry our address, so a handful at most. A large
     * number would mean the CRC check is not actually gating anything. */
    TEST_ASSERT_TRUE(replies < 20u);
}


/* ------------------------------------------------------- the heater loop */

static o2p_heater_cfg_t hcfg_default(void)
{
    /* Zero-initialised, then filled field by field. The zero matters: this
     * helper is the baseline every interlock test breaks exactly one thing
     * from, so a member added to the struct later must arrive as a defined
     * OFF rather than as stack garbage. It did not, once - test_override
     * landed uninitialised and eleven unrelated heater tests failed. */
    o2p_heater_cfg_t c = {0};
    c.setpoint_x100 = 8500u;     /* 85 %RH, PLAN.md:294-296 */
    c.dt_max_k100 = 400u;        /* 4 K, the designed envelope */
    c.max_duty_x100 = 10000u;
    c.kp_x100 = O2P_HEATER_KP_X100_DEFAULT;
    c.ki_x100 = O2P_HEATER_KI_X100_DEFAULT;
    /* A probe that has been told it may heat by itself. The interlock tests
     * below break exactly one thing from this baseline, and consent is a
     * precondition of the RH loop rather than one of the things under test -
     * its own coverage is test_autonomous_heating_needs_consent(). */
    c.rh_consent = true;
    return c;
}

/* An input in which every interlock is satisfied, so a test can break exactly
 * one thing and attribute the result to it. */
static o2p_heater_in_t hin_healthy(void)
{
    o2p_heater_in_t in = {0};   /* see hcfg_default() on why the zero matters */
    in.drive_possible = true;
    in.safety_armed = true;
    in.pin_integrity_ok = true;
    in.rh_valid = true;
    in.rh_x100 = 9500u;          /* wet: the loop should want heat */
    in.tip_valid = true;
    in.t_tip_c100 = 5500;
    in.chamber_valid = true;
    in.t_chamber_c100 = 5400;    /* dT = 1 K, inside the envelope */
    /* The die runs a couple of kelvin ABOVE the tip at rest - it is the MCU's
     * own junction - so tip-minus-die is negative on a healthy probe. Measured
     * -2.2 K on 2026-09-04. Leaving these unset would read indeterminate. */
    in.die_valid = true;
    in.t_die_c100 = 5720;
    in.supply_ok = true;
    return in;
}

static void test_heater_healthy_input_actually_heats(void)
{
    /* The baseline the interlock tests are differences from: if this did not
     * command heat, "duty == 0" would prove nothing about any interlock. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(0, out.block);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);
}

static void test_every_interlock_independently_forces_zero(void)
{
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_out_t out;

    struct { const char *name; uint16_t bit; } cases[] = {
        {"not compiled",   O2P_HB_NOT_COMPILED},
        {"config off",     O2P_HB_CONFIG_OFF},
        {"safety",         O2P_HB_SAFETY},
        {"no rh",          O2P_HB_NO_RH},
        {"no tip",         O2P_HB_NO_TIP},
        {"no chamber",     O2P_HB_NO_CHAMBER},
        {"tip limit",      O2P_HB_TIP_LIMIT},
        {"dt limit",       O2P_HB_DT_LIMIT},
        {"supply",         O2P_HB_SUPPLY},
        {"pin integrity",  O2P_HB_PIN_INTEGRITY},
    };

    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t c = cfg;
        o2p_heater_in_t in = hin_healthy();

        switch (cases[i].bit) {
        case O2P_HB_NOT_COMPILED:  in.drive_possible = false; break;
        case O2P_HB_CONFIG_OFF:    c.max_duty_x100 = 0u; break;
        case O2P_HB_SAFETY:        in.safety_armed = false; break;
        case O2P_HB_NO_RH:         in.rh_valid = false; break;
        case O2P_HB_NO_TIP:        in.tip_valid = false; break;
        case O2P_HB_NO_CHAMBER:    in.chamber_valid = false; break;
        case O2P_HB_TIP_LIMIT:     in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100; break;
        case O2P_HB_DT_LIMIT:      in.t_chamber_c100 =
                                       (int16_t)(in.t_tip_c100 - (int16_t)c.dt_max_k100);
                                   break;
        case O2P_HB_SUPPLY:        in.supply_ok = false; break;
        default:                   in.pin_integrity_ok = false; break;
        }

        o2p_heater_ctl_step(&st, &c, &in, 0u, &out);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(0, out.duty_x100, cases[i].name);
        TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].bit) != 0u, cases[i].name);
    }
}

static void test_unevaluable_input_is_off_not_midrange(void)
{
    /* The guard-checklist rule: missing data must never read as OK. Every
     * combination of missing sensor must be OFF, never a comfortable duty. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_out_t out;
    for (unsigned mask = 0u; mask < 8u; mask++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_in_t in = hin_healthy();
        if (mask & 1u) { in.rh_valid = false; }
        if (mask & 2u) { in.tip_valid = false; }
        if (mask & 4u) { in.chamber_valid = false; }
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        if (mask != 0u) {
            TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);
            TEST_ASSERT_TRUE(out.block != 0u);
        }
    }
}

static void test_duty_is_monotonic_in_humidity(void)
{
    /* Heating dries the chamber, so wetter must never ask for LESS heat. A
     * sign error here would make the loop run away from its setpoint, and on
     * this plant that means letting the membrane wet. */
    o2p_heater_cfg_t cfg = hcfg_default();
    uint16_t prev = 0u;
    for (uint32_t rh = 0u; rh <= 10000u; rh += 100u) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);       /* fresh state: pure static response */
        o2p_heater_in_t in = hin_healthy();
        in.rh_x100 = (uint16_t)rh;
        o2p_heater_out_t out;
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_TRUE(out.duty_x100 >= prev);
        /* At or below setpoint the loop must ask for nothing at all - not a
         * small residual. Drying past the target is not a reason to heat. */
        if (rh <= cfg.setpoint_x100) {
            TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);
        }
        prev = out.duty_x100;
    }
    /* Saturated air is the wettest input there is, so it must ask for the most
     * heat of any point in the sweep, and that must be a real demand. Note it
     * is NOT full duty: one step of proportional-plus-one-integration at
     * 100 %RH is about 31 %, and reaching the ceiling is the integrator's job
     * over the following minutes. test_duty_clamp_binds covers that path. */
    TEST_ASSERT_TRUE(prev > 0u);
}

static void test_duty_clamp_binds(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 3000u;           /* 30 % ceiling */
    o2p_heater_in_t in = hin_healthy();
    in.rh_x100 = 10000u;                 /* saturated: asks for everything */
    o2p_heater_out_t out;
    for (unsigned i = 0; i < 200u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
        TEST_ASSERT_TRUE(out.duty_x100 <= 3000u);
    }
    TEST_ASSERT_EQUAL_UINT16(3000u, out.duty_x100);
}

static void test_dt_clamp_binds_and_has_hysteresis(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    /* At the limit: clamped. */
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - (int16_t)cfg.dt_max_k100);
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_DT_LIMIT) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);

    /* Just below the limit but above the release point: STILL clamped. That
     * is the hysteresis - without it this clamp chatters at 1 Hz against a
     * plant whose time constant is seconds. */
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 -
                                  (int16_t)(cfg.dt_max_k100 - 10u));
    o2p_heater_ctl_step(&st, &cfg, &in, 1u, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_DT_LIMIT) != 0u);

    /* Below the release point: clamp lets go. */
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 -
                                  (int16_t)(cfg.dt_max_k100 -
                                            O2P_HEATER_DT_HYST_K100 - 10u));
    o2p_heater_ctl_step(&st, &cfg, &in, 2u, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_DT_LIMIT) == 0u);
}

static void test_tip_limit_is_below_the_hardware_alert(void)
{
    /* Firmware must back off before the TMP117's therm-mode alert fires, or
     * the two mechanisms are one mechanism. 8500 is what main.c programs. */
    TEST_ASSERT_TRUE(O2P_HEATER_TIP_LIMIT_C100 < 8500);
    TEST_ASSERT_TRUE(O2P_HEATER_TIP_RELEASE_C100 < O2P_HEATER_TIP_LIMIT_C100);
}

static void test_integrator_cannot_wind_up_while_clamped(void)
{
    /* Hold the output hard against its ceiling for ten minutes, then ask for
     * nothing. A loop without anti-windup stays saturated for a long time
     * afterwards - which on this plant means continuing to heat a cell rated
     * to 60 C after the humidity has already collapsed. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.rh_x100 = 10000u;
    for (unsigned i = 0; i < 600u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_EQUAL_UINT16(cfg.max_duty_x100, out.duty_x100);

    /* Bone dry. The output must come off the rail immediately, not after
     * unwinding 600 seconds of accumulated error. */
    in.rh_x100 = 0u;
    o2p_heater_ctl_step(&st, &cfg, &in, 600u, &out);
    TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);
}

/* A crude first-order plant: heating dries the chamber. Only the SIGN and
 * rough scale matter here - the real gain is unknown (THERMAL-BARRIER.md:18
 * covers PCB conduction only, not the ring-to-gas path that sets it). This
 * exists to prove the loop closes and settles, not to predict hardware. */
static uint16_t fake_plant_rh(uint16_t duty_x100)
{
    int32_t rh = 10000 - ((int32_t)duty_x100 * 2000) / 10000;
    return (uint16_t)rh;
}

static void test_loop_reaches_setpoint_in_steady_state(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out = {0u, 0u};

    for (unsigned i = 0; i < 2000u; i++) {
        in.rh_x100 = fake_plant_rh(out.duty_x100);
        /* Keep dT inside the envelope so this test is about the control law
         * and not about the clamp. */
        in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - 100);
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_EQUAL_UINT16(0, out.block);
    TEST_ASSERT_INT_WITHIN(20, (int)cfg.setpoint_x100, (int)in.rh_x100);
}

static void test_runaway_does_not_false_positive_on_cold_start(void)
{
    /* At power-on the tip and chamber are the same temperature and nothing is
     * being commanded. Ten minutes of that must not latch a hardware fault. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;              /* commanding nothing */
    o2p_heater_in_t in = hin_healthy();
    in.t_tip_c100 = 2000;
    in.t_chamber_c100 = 2000;
    o2p_heater_out_t out;
    for (unsigned i = 0; i < 600u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
    TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) == 0u);
}

static void test_runaway_latches_on_uncommanded_heat_and_stays_latched(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;              /* commanding nothing, on purpose */
    o2p_heater_in_t in = hin_healthy();
    in.t_tip_c100 = 5000;
    /* Hotter than the loop is ever allowed to make it, by a clear margin. */
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                  O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_out_t out;

    for (unsigned i = 0; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);

    /* Latched means latched: a now-perfectly-healthy probe still refuses. A
     * FET that conducts unasked is a hardware failure, and the firmware that
     * just found it cannot control the heater is not what should decide the
     * fault has cleared. */
    o2p_heater_in_t healthy = hin_healthy();
    o2p_heater_cfg_t full = hcfg_default();
    for (unsigned i = 0; i < 10u; i++) {
        o2p_heater_ctl_step(&st, &full, &healthy, 1000u + i, &out);
        TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);
        TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) != 0u);
    }
}

static void test_runaway_needs_the_full_window(void)
{
    /* One hot sample is not a runaway; the window is what rejects transients
     * such as a probe carried from a warm hand into cold air. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t in = hin_healthy();
    in.t_tip_c100 = 5000;
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                  O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_out_t out;
    for (unsigned i = 0; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
}

static void test_runaway_is_not_evaluated_when_we_cannot_drive(void)
{
    /* With the heater compiled out, PA8 is a plain output held low. A hot tip
     * then says something about the environment or the sensors, not about a
     * stuck FET - and a fault bit nobody can act on is noise. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    in.drive_possible = false;
    in.t_tip_c100 = 5000;
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                  O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_out_t out;
    for (unsigned i = 0; i < 300u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
}

static void test_setpoint_default_respects_the_cell_humidity_rating(void)
{
    /* The SGX cell is rated 15-90 %RH continuous. A setpoint at or above that
     * defeats the purpose of running the loop at all. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    TEST_ASSERT_TRUE(cfg.rh_setpoint_x100 <= 9000u);
    TEST_ASSERT_TRUE(cfg.rh_setpoint_x100 >= 5000u);
    /* And the heater is off by configuration as well as by compile flag: two
     * independent switches, so enabling it is never a single edit. */
    TEST_ASSERT_EQUAL_UINT16(0, cfg.heater_max_duty_x100);
    /* The designed thermal envelope is 0-4 K, not a fixed 2 K (PLAN.md:300). */
    TEST_ASSERT_EQUAL_UINT16(400u, cfg.dt_max_k_x100);
}


/* ---------------------------------------------------------------------------
 * MCU die temperature.
 *
 * The whole reason this arithmetic is a pure function is here: on the target
 * the TS_CAL words are read-only factory OTP, so the calibration guard can
 * only ever be handed a GOOD die. A guard that has never been observed to
 * reject anything is not a guard, so the bad calibration is constructed here.
 *
 * Reference die, read over SWD 2026-09-04: TS_CAL1 = 1023, TS_CAL2 = 1370.
 * ------------------------------------------------------------------------- */
#define DIE_CAL1 1023u
#define DIE_CAL2 1370u

static void test_die_temp_reads_the_calibration_point(void)
{
    int16_t t = -1;
    /* At the raw code the factory recorded for 30 C, and at the voltage it
     * recorded it at, the answer must be exactly 30 C. */
    TEST_ASSERT_TRUE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, DIE_CAL1, 3000u, &t));
    TEST_ASSERT_EQUAL_INT16(3000, t);

    /* And the upper point, 130 C. */
    TEST_ASSERT_TRUE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, DIE_CAL2, 3000u, &t));
    TEST_ASSERT_EQUAL_INT16(13000, t);
}

static void test_die_temp_rejects_corrupt_calibration(void)
{
    int16_t t = 4242;

    /* Blank OTP, both polarities. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(0xFFFFu, 0xFFFFu, 1100u, 3000u, &t));
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(0u, 0u, 1100u, 3000u, &t));
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, 0xFFFFu, 1100u, 3000u, &t));
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(0xFFFFu, DIE_CAL2, 1100u, 3000u, &t));

    /* The case a per-endpoint guard would miss: cal1 perfect, cal2 plausible
     * on its own, but the SLOPE between them wrong. A 130 C die would read
     * about 80 C - in range, no sentinel, simply false. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, 1723u, 1100u, 3000u, &t));

    /* Inverted slope: cal2 below cal1. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, 900u, 1000u, 3000u, &t));

    /* Not one of the above wrote anything into the output. */
    TEST_ASSERT_EQUAL_INT16(4242, t);
}

static void test_die_temp_accepts_the_whole_datasheet_envelope(void)
{
    /* DS12232 Rev 5 Table 65: V30 0.742..0.785 V is TS_CAL1 1013..1072, and
     * Avg_Slope 2.3..2.7 mV/C is 314..369 counts over the 100 K between the
     * points. No part inside its own specification may be rejected - that is
     * the failure mode a too-tight guard has, and it would strand a good
     * board in the field reporting a sentinel. */
    int16_t t = 0;
    const uint16_t cal1[] = {1013u, 1072u};
    const int32_t slope[] = {314, 369};
    for (unsigned i = 0; i < 2u; i++) {
        for (unsigned j = 0; j < 2u; j++) {
            uint16_t c1 = cal1[i];
            uint16_t c2 = (uint16_t)((int32_t)c1 + slope[j]);
            TEST_ASSERT_TRUE(o2p_die_c100_from_cal(c1, c2, c1, 3000u, &t));
            TEST_ASSERT_EQUAL_INT16(3000, t);
        }
    }
}

static void test_die_temp_is_monotonic_and_does_not_wrap_at_the_tails(void)
{
    /* Monotonicity: a hotter die must never read cooler. */
    int16_t prev = INT16_MIN;
    for (uint16_t raw = 750u; raw <= 1400u; raw += 5u) {
        int16_t t = 0;
        if (!o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, raw, 3000u, &t)) {
            continue;
        }
        TEST_ASSERT_TRUE(t >= prev);
        prev = t;
    }

    /* The far tail is the interesting one. raw = 4095 interpolates to about
     * +915 C, which as a plain int16_t would WRAP to +259.94 C - a number that
     * looks like a real reading of a real fault. The result bound is what
     * stops that becoming telemetry. */
    int16_t t = 4242;
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 4095u, 3000u, &t));
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 0u, 3000u, &t));
    TEST_ASSERT_EQUAL_INT16(4242, t);
}

static void test_die_temp_keeps_the_cold_end_the_part_is_rated_for(void)
{
    /* TA min is -40 C, and the sensor's error budget is the +/-5 C tolerance
     * on the calibration temperature plus +/-2 C linearity. So a die genuinely
     * at -40 C may legitimately read several degrees lower, and the result
     * bound must sit below the rated limit rather than at it. */
    int16_t t = 0;
    TEST_ASSERT_TRUE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 780u, 3000u, &t));
    TEST_ASSERT_INT16_WITHIN(20, -4000, t);
    TEST_ASSERT_TRUE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 756u, 3000u, &t));
    TEST_ASSERT_INT16_WITHIN(20, -4700, t);
}

static void test_die_temp_rejects_impossible_conversion_inputs(void)
{
    int16_t t = 4242;
    /* A 12-bit right-aligned result cannot exceed 4095. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 5000u, 3000u, &t));
    /* VDDA outside the part's operating range means the VREFINT read that
     * produced it was itself wrong, so the scaling below it is meaningless. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 1100u, 0u, &t));
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 1100u, 5000u, &t));
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 1100u, 3000u, NULL));
    TEST_ASSERT_EQUAL_INT16(4242, t);
}

static void test_die_temp_scales_with_the_supply_it_actually_ran_at(void)
{
    /* The factory points were taken at 3.0 V. The same raw code at a higher
     * VDDA is a higher voltage and therefore a hotter die; ignoring VDDA would
     * silently bias every reading on a board whose rail is not 3.000 V. */
    int16_t at3v0 = 0, at3v3 = 0;
    TEST_ASSERT_TRUE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 1100u, 3000u, &at3v0));
    TEST_ASSERT_TRUE(o2p_die_c100_from_cal(DIE_CAL1, DIE_CAL2, 1100u, 3300u, &at3v3));
    TEST_ASSERT_TRUE(at3v3 > at3v0);
}


static void test_die_temp_band_is_the_datasheet_not_a_remembered_one(void)
{
    /* Regression pin. These bands were first written from memory as "2.0..3.1
     * mV/K" -> 273..423 counts, and TS_CAL1 as 700..1400. The real figures,
     * DS12232 Rev 5 Table 65, are 2.3..2.7 mV/C -> 314..369 and 1013..1072.
     * The values below are inside the OLD bands and outside the real part's
     * envelope, so a quiet slide back to the remembered numbers fails here
     * rather than silently re-admitting a 12%-wrong scale factor. */
    int16_t t = 4242;
    /* Slope 400 counts = 2.93 mV/C: no part is specified to do this. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, 1423u, 1100u, 3000u, &t));
    /* Slope 280 counts = 2.05 mV/C, likewise. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(DIE_CAL1, 1303u, 1100u, 3000u, &t));
    /* TS_CAL1 = 800 is V30 = 0.586 V, well under the 0.742 V minimum. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(800u, 1147u, 900u, 3000u, &t));
    /* TS_CAL1 = 1300 is V30 = 0.952 V, well over the 0.785 V maximum. */
    TEST_ASSERT_FALSE(o2p_die_c100_from_cal(1300u, 1647u, 1400u, 3000u, &t));
    TEST_ASSERT_EQUAL_INT16(4242, t);
}


static void test_pwm_ceiling_is_a_thermal_limit_not_a_range(void)
{
    /* The ceiling on heater_pwm_hz exists to keep Q2 out of its linear region.
     * Switching loss is duty-INDEPENDENT and scales with frequency, and the
     * gate is driven through R28 = 10 k, so a high frequency spends much of
     * every period on the edges. The old 20 kHz bound permitted exactly that
     * and nobody had measured it, which is why 20000 is pinned as REJECTED
     * here rather than merely absent: a quiet revert would otherwise reopen a
     * thermal failure mode that no test could see. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    TEST_ASSERT_TRUE(o2p_config_valid(&cfg));          /* 1 kHz, the design point */

    cfg.heater_pwm_hz = 2000u;                          /* the new ceiling */
    TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
    cfg.heater_pwm_hz = 2001u;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
    cfg.heater_pwm_hz = 20000u;                         /* the OLD ceiling */
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));

    cfg.heater_pwm_hz = 50u;                            /* the floor still holds */
    TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
    cfg.heater_pwm_hz = 49u;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
}


static void test_runaway_sees_a_stuck_fet_through_the_die(void)
{
    /* The failure the detector exists for, with the chamber behaving as it
     * ACTUALLY does on this board: tracking the tip within a fraction of a
     * kelvin, because the two sensors are 6.6 mm apart on the same copper.
     * The chamber-referenced test therefore cannot fire here - if this latches
     * it is the die that caught it, which is the entire point. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;                  /* commanding nothing */
    o2p_heater_in_t in = hin_healthy();
    in.t_tip_c100 = 5000;
    in.t_chamber_c100 = 4990;                /* 0.1 K - real colocated behaviour */
    /* The stimulus is MEASURED, not derived from the threshold. On
     * 2026-09-04 a stuck 100 % duty put the tip at 56 C with the die near
     * 28 C: a 28 K separation. Writing this as
     * (tip - O2P_HEATER_RUNAWAY_DIE_K100 - 50) would make the test move with
     * the constant and pass at ANY threshold - which is exactly the defect
     * this file keeps finding elsewhere. */
    in.t_die_c100 = (int16_t)(in.t_tip_c100 - 2800);

    /* Prove the chamber path is genuinely dead in this scenario before
     * relying on the conclusion. */
    int32_t dt_ch = (int32_t)in.t_tip_c100 - (int32_t)in.t_chamber_c100;
    TEST_ASSERT_TRUE(dt_ch < (int32_t)cfg.dt_max_k100 + O2P_HEATER_RUNAWAY_MARGIN_K100);

    o2p_heater_out_t out;
    for (unsigned i = 0; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);
    TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) != 0u);
}

static void test_runaway_die_path_does_not_false_positive_at_rest(void)
{
    /* A healthy probe sits with the die WARMER than the tip. Running the full
     * window must not latch, or the heater is bricked on first boot. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;
    for (unsigned i = 0; i < 600u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
}

static void test_runaway_references_are_independent(void)
{
    /* Two references exist so that losing one does not disable the other.
     * Chamber alone must still latch, and die alone must still latch. */
    o2p_heater_out_t out;

    o2p_heater_state_t st_ch;
    o2p_heater_ctl_reset(&st_ch);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t ch = hin_healthy();
    ch.die_valid = false;                       /* die gone */
    ch.t_tip_c100 = 5000;
    ch.t_chamber_c100 = (int16_t)(ch.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                  O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    for (unsigned i = 0; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++) {
        o2p_heater_ctl_step(&st_ch, &cfg, &ch, i, &out);
    }
    TEST_ASSERT_TRUE(st_ch.runaway_latched);

    o2p_heater_state_t st_die;
    o2p_heater_ctl_reset(&st_die);
    o2p_heater_in_t di = hin_healthy();
    di.chamber_valid = false;                   /* chamber gone */
    di.t_tip_c100 = 5000;
    di.t_die_c100 = (int16_t)(di.t_tip_c100 - 2800);
    for (unsigned i = 0; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++) {
        o2p_heater_ctl_step(&st_die, &cfg, &di, i, &out);
    }
    TEST_ASSERT_TRUE(st_die.runaway_latched);
}

static void test_runaway_without_any_reference_is_unevaluable_not_ok(void)
{
    /* Losing BOTH references must not be read as "no runaway". It is not
     * evidence either way - but it must also not silently latch, which would
     * brick a probe on a transient sensor failure. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t in = hin_healthy();
    in.chamber_valid = false;
    in.die_valid = false;
    in.t_tip_c100 = 9000;                       /* alarmingly hot, unprovable */
    o2p_heater_out_t out;
    for (unsigned i = 0; i < 600u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
    /* The absolute tip clamp is what protects here, and it is not optional. */
    TEST_ASSERT_TRUE((out.block & O2P_HB_TIP_LIMIT) != 0u);
}


static void test_die_runaway_threshold_brackets_the_measured_evidence(void)
{
    /* Pin the VALUE, not just the mechanism, against the two measurements that
     * bound it - so a threshold moved without new evidence fails here.
     *
     *   +3.0 K  widest legitimate tip-minus-die excursion seen at zero duty
     *           (thermal history plus the die's 0.29 K/LSB dither)
     *   +28 K   the separation a stuck 100 % duty actually produced
     *
     * The threshold must sit strictly between them. */
    TEST_ASSERT_TRUE(O2P_HEATER_RUNAWAY_DIE_K100 > 300);
    TEST_ASSERT_TRUE(O2P_HEATER_RUNAWAY_DIE_K100 < 2800);

    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;

    /* A legitimate 3.0 K excursion must not latch. */
    o2p_heater_state_t cold;
    o2p_heater_ctl_reset(&cold);
    o2p_heater_in_t ok = hin_healthy();
    ok.t_tip_c100 = 5000;
    ok.t_chamber_c100 = 4990;
    ok.t_die_c100 = (int16_t)(ok.t_tip_c100 - 300);
    for (unsigned i = 0; i < 400u; i++) {
        o2p_heater_ctl_step(&cold, &cfg, &ok, i, &out);
    }
    TEST_ASSERT_FALSE(cold.runaway_latched);
}

/* The fault latch. What it exists to stop: a converter fault that lasts one
 * cycle being published for one second out of the three hundred between
 * polls, so that every guard raising such a bit is undetectable in the field
 * however correct it is on the bench. */
static void test_fault_latch_preserves_a_one_cycle_event(void)
{
    o2p_fault_latch_t l = {0u, 0u};

    /* A clean cycle publishes nothing and latches nothing. */
    TEST_ASSERT_EQUAL_HEX16(0, o2p_fault_latch_step(&l, 0u, 100u));

    /* One cycle of DRDY_STUCK, then the fault is gone. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_ADS_DRDY_STUCK,
        o2p_fault_latch_step(&l, O2P_F_ADS_DRDY_STUCK, 101u));

    /* It must still be published a full poll interval later - this is the
     * whole point. 300 s is the nominal LoRa poll. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_ADS_DRDY_STUCK,
        o2p_fault_latch_step(&l, 0u, 101u + 300u));

    /* And it must clear by itself, or the probe would look permanently
     * faulted after a single glitch. */
    TEST_ASSERT_EQUAL_HEX16(0,
        o2p_fault_latch_step(&l, 0u, 101u + O2P_FAULT_LATCH_S));
}

static void test_fault_latch_refreshes_its_window_on_every_occurrence(void)
{
    o2p_fault_latch_t l = {0u, 0u};

    o2p_fault_latch_step(&l, O2P_F_ADS_CONFIG_LOST, 10u);

    /* Still faulting at the moment the first window would have expired. */
    uint32_t expiry = 10u + O2P_FAULT_LATCH_S;
    TEST_ASSERT_EQUAL_HEX16(O2P_F_ADS_CONFIG_LOST,
        o2p_fault_latch_step(&l, O2P_F_ADS_CONFIG_LOST, expiry));

    /* The window must have been REFRESHED by that second occurrence, so the
     * bit is still held a full poll interval later. This is the assertion
     * with teeth: a build that sets the deadline once and never renews it
     * goes quiet 330 s after the FIRST glitch, so a probe faulting every
     * minute would report clean - exactly the invisibility the latch exists
     * to remove. Verified by a known-bad run. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_ADS_CONFIG_LOST,
        o2p_fault_latch_step(&l, 0u, expiry + 300u));
}

static void test_fault_latch_is_monotonic_in_severity(void)
{
    o2p_fault_latch_t l = {0u, 0u};

    /* Worse input must never produce a cleaner published word. Accumulate
     * three different latched faults and check none of them is dropped when
     * the next arrives. */
    uint16_t seen = 0u;
    const uint16_t seq[3] = {O2P_F_ADS_DRDY_STUCK, O2P_F_ADC_RANGE,
                             O2P_F_I2C_FAIL_ADS};
    for (unsigned i = 0; i < 3u; i++) {
        seen |= seq[i];
        uint16_t pub = o2p_fault_latch_step(&l, seq[i], 200u + i);
        TEST_ASSERT_EQUAL_HEX16(seen, pub & seen);
    }

    /* All three still published together on a clean cycle. */
    TEST_ASSERT_EQUAL_HEX16(seen, o2p_fault_latch_step(&l, 0u, 203u) & seen);
}

static void test_fault_latch_only_holds_transient_bits(void)
{
    o2p_fault_latch_t l = {0u, 0u};

    /* SETTLING already lasts up to 15 minutes. Latching it would extend a
     * long fault rather than preserve a brief one, and would leave the probe
     * looking unsettled for five minutes after it had genuinely settled. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_SETTLING,
        o2p_fault_latch_step(&l, O2P_F_SETTLING, 10u));
    TEST_ASSERT_EQUAL_HEX16(0, o2p_fault_latch_step(&l, 0u, 11u));

    /* Nor the steady-state sensor bus failures, which will still be failing
     * at the next poll and need no help being seen. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_I2C_FAIL_SHT,
        o2p_fault_latch_step(&l, O2P_F_I2C_FAIL_SHT, 20u));
    TEST_ASSERT_EQUAL_HEX16(0, o2p_fault_latch_step(&l, 0u, 21u));
}

static void test_fault_latch_survives_the_uptime_wrap(void)
{
    o2p_fault_latch_t l = {0u, 0u};

    /* A fault raised just before uptime_s wraps sets a deadline that wraps
     * with it. An unsigned >= comparison would then find every subsequent
     * `now` less than the deadline and hold the bit forever - a probe stuck
     * reporting a converter fault that ended 136 years earlier. */
    const uint32_t near_wrap = 0xFFFFFF00u;
    o2p_fault_latch_step(&l, O2P_F_ADS_DRDY_STUCK, near_wrap);

    /* Held across the wrap, as it should be. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_ADS_DRDY_STUCK,
        o2p_fault_latch_step(&l, 0u, near_wrap + 100u));

    /* And released after the window, on the far side of zero. */
    TEST_ASSERT_EQUAL_HEX16(0,
        o2p_fault_latch_step(&l, 0u, near_wrap + O2P_FAULT_LATCH_S));
}

static void test_fault_latch_never_hides_a_current_fault(void)
{
    o2p_fault_latch_t l = {0u, 0u};

    /* Bits outside the latched set must pass through untouched, latch empty
     * or not: the latch adds to the published word and never filters it. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_VA_LOW | O2P_F_TEMP_OVER,
        o2p_fault_latch_step(&l, O2P_F_VA_LOW | O2P_F_TEMP_OVER, 5u));

    o2p_fault_latch_step(&l, O2P_F_ADC_RANGE, 6u);
    uint16_t pub = o2p_fault_latch_step(&l, O2P_F_HEATER_RUNAWAY, 7u);
    TEST_ASSERT_TRUE((pub & O2P_F_HEATER_RUNAWAY) != 0u);
    TEST_ASSERT_TRUE((pub & O2P_F_ADC_RANGE) != 0u);
}


/* ------------------------------------------- config migration (layout v2)
 *
 * The failure this prevents is not a lost calibration - that one is real and
 * deliberate. It is a probe that stops answering its master.
 *
 * A record whose layout_version did not match used to be discarded whole, and
 * the defaults it fell back to include slave address 3, 9600 baud, even
 * parity. A probe an operator had moved to another address, baud or parity
 * therefore went silent the moment it took a firmware update - on hardware
 * that is potted and buried in a compost pile, with no way back in over the
 * bus. The calibration argument justifies discarding two fields; it never
 * justified discarding the transport.
 */

/* The version-2 configuration exactly as it sat in flash: 28 bytes, no
 * assumed_p_hpa, no cal_air_frac_x1000, no cal_p_hpa, and slave_addr at offset
 * 22 rather than 28. Written out here rather than derived from the current
 * struct, because the whole point is that the two layouts differ. */
typedef struct {
    int32_t  cal_air_na;
    uint16_t rh_setpoint_x100;
    uint16_t dt_max_k_x100;
    uint16_t heater_max_duty_x100;
    uint16_t heater_pwm_hz;
    int16_t  cal_temp_c100;
    int16_t  tempco_ppm_per_k;
    uint16_t sht_pulse_interval_h;
    uint16_t heater_kp_x100;
    uint16_t heater_ki_x100;
    uint8_t  slave_addr;
    uint8_t  baud_code;
    uint8_t  parity_code;
    uint8_t  reserved[3];
} test_cfg_v2_t;

#define TEST_CFG_MAGIC 0x4F325043u
#define TEST_REC_BYTES 64u

/* Build the 64-byte record a version-2 probe would have on its config page,
 * CRC and all. `crc_ok` false corrupts it, to prove the CRC is still checked
 * on the migration path and not only on the current-version one. */
static void build_v2_record(uint8_t rec[TEST_REC_BYTES],
                            const test_cfg_v2_t *cfg, uint32_t seq,
                            bool crc_ok)
{
    memset(rec, 0, TEST_REC_BYTES);
    uint32_t magic = TEST_CFG_MAGIC, ver = 2u;
    memcpy(rec + 0, &magic, 4);
    memcpy(rec + 4, &ver, 4);
    memcpy(rec + 8, &seq, 4);
    memcpy(rec + 12, cfg, sizeof(*cfg));
    /* crc lives immediately after the configuration and covers everything
     * before it, with its own two bytes zero - which they already are. */
    uint16_t crc = o2p_mb_crc16(rec, 12u + sizeof(*cfg));
    if (!crc_ok) {
        crc ^= 0xFFFFu;
    }
    memcpy(rec + 12u + sizeof(*cfg), &crc, 2);
}

/* A probe that has been deployed: moved off every default the transport has,
 * with a tuned heater and a real air point. */
static test_cfg_v2_t deployed_v2(void)
{
    test_cfg_v2_t c;
    memset(&c, 0, sizeof(c));
    c.cal_air_na = 98765;          /* a real air point, taken in moist air */
    c.rh_setpoint_x100 = 7500u;
    c.dt_max_k_x100 = 250u;
    c.heater_max_duty_x100 = 3000u;
    c.heater_pwm_hz = 1500u;
    c.cal_temp_c100 = 2140;
    c.tempco_ppm_per_k = 2000;
    c.sht_pulse_interval_h = 12u;
    c.heater_kp_x100 = 450u;
    c.heater_ki_x100 = 60u;
    c.slave_addr = 17u;                  /* not the default 3 */
    c.baud_code = O2P_BAUD_38400;        /* not the default 9600 */
    c.parity_code = O2P_PARITY_NONE;     /* not the default even */
    return c;
}

/* ---- layout version 4, the one every deployed board is running ----------
 *
 * 32 bytes: the full water-vapour set, no dilution efficacy. Written out
 * separately from o2p_config_t for the same reason the v2 struct is - the
 * point is that the layouts differ, and deriving one from the other would
 * make the test agree with whatever the code does. */
typedef struct {
    int32_t  cal_air_na;
    uint16_t rh_setpoint_x100;
    uint16_t dt_max_k_x100;
    uint16_t heater_max_duty_x100;
    uint16_t heater_pwm_hz;
    int16_t  cal_temp_c100;
    int16_t  tempco_ppm_per_k;
    uint16_t sht_pulse_interval_h;
    uint16_t heater_kp_x100;
    uint16_t heater_ki_x100;
    uint16_t assumed_p_hpa;
    uint16_t cal_air_frac_x1000;
    uint16_t cal_p_hpa;
    uint8_t  slave_addr;
    uint8_t  baud_code;
    uint8_t  parity_code;
    uint8_t  reserved[1];
} test_cfg_v4_t;

static void build_v4_record(uint8_t rec[TEST_REC_BYTES],
                            const test_cfg_v4_t *cfg, uint32_t seq,
                            bool crc_ok)
{
    memset(rec, 0, TEST_REC_BYTES);
    uint32_t magic = TEST_CFG_MAGIC, ver = 4u;
    memcpy(rec + 0, &magic, 4);
    memcpy(rec + 4, &ver, 4);
    memcpy(rec + 8, &seq, 4);
    memcpy(rec + 12, cfg, sizeof(*cfg));
    uint16_t crc = o2p_mb_crc16(rec, 12u + sizeof(*cfg));
    if (!crc_ok) {
        crc ^= 0xFFFFu;
    }
    memcpy(rec + 12u + sizeof(*cfg), &crc, 2);
}

/* A v7 configuration body, byte-for-byte as the field wrote it. Declared here
 * rather than reused from config_migrate.c so that a change there which
 * accidentally alters the historical layout fails this test instead of
 * silently agreeing with itself. */
typedef struct {
    int32_t  cal_air_na;              /* 0 */
    uint16_t rh_setpoint_x100;        /* 4 */
    uint16_t dt_max_k_x100;           /* 6 */
    uint16_t heater_max_duty_x100;    /* 8 */
    uint16_t heater_pwm_hz;           /* 10 */
    int16_t  cal_temp_c100;           /* 12 */
    int16_t  tempco_ppm_per_k;        /* 14 */
    uint16_t sht_pulse_interval_h;    /* 16 */
    uint16_t heater_kp_x100;          /* 18 */
    uint16_t heater_ki_x100;          /* 20 */
    uint16_t assumed_p_hpa;           /* 22 */
    uint16_t cal_air_frac_x1000;      /* 24 */
    uint16_t cal_p_hpa;               /* 26 */
    uint8_t  slave_addr;              /* 28 */
    uint8_t  baud_code;               /* 29 */
    uint8_t  parity_code;             /* 30 */
    uint8_t  reserved[1];             /* 31 */
    uint16_t dil_alpha_x1000;         /* 32 */
    uint8_t  cal_zero_taken;          /* 34 */
    uint8_t  reserved2[1];            /* 35 */
    int32_t  cal_zero_na;             /* 36 */
    uint16_t heater_rh_consent;       /* 40 */
    /* v8 puts tip_setpoint_c100 HERE. A v7 record leaves it zero, and zero is
     * a legal setpoint - which is the whole point of the test below. */
    uint8_t  reserved3[2];            /* 42 */
} test_cfg_v7_t;
_Static_assert(sizeof(test_cfg_v7_t) == 44u, "v7 config layout is 44 bytes");

/* Same wrapper as build_v4_record, with the version and body size passed in so
 * one helper serves every appended layout. */
static void build_vn_record(uint8_t rec[TEST_REC_BYTES], const void *cfg,
                            size_t cfg_bytes, uint32_t ver, uint32_t seq)
{
    memset(rec, 0, TEST_REC_BYTES);
    uint32_t magic = TEST_CFG_MAGIC;
    memcpy(rec + 0, &magic, 4);
    memcpy(rec + 4, &ver, 4);
    memcpy(rec + 8, &seq, 4);
    memcpy(rec + 12, cfg, cfg_bytes);
    uint16_t crc = o2p_mb_crc16(rec, 12u + cfg_bytes);
    memcpy(rec + 12u + cfg_bytes, &crc, 2);
}

/* ======================= the frozen transport block =======================
 *
 * The regression: the bootloader is never rewritten in the field, so it reads
 * configuration records written by applications newer than itself. It used to
 * demand an exact CONFIG_LAYOUT_VERSION match and, failing it, fell back to
 * address 3 / 9600 / even - stranding any probe an operator had moved off the
 * default transport, at exactly the moment its application was broken enough
 * to need the loader. transport_record.h is the fix; these tests are about
 * the property that matters, which is that a loader can read a block written
 * by firmware it has never heard of.
 */

/* A configuration record from a layout version this build does not know -
 * the situation an old loader is in, written from the future's point of
 * view. `cfg_bytes` is deliberately not 48: the whole difficulty is that the
 * CRC moves with the struct. */
static void build_future_page(uint8_t page[128], uint32_t layout_version,
                              size_t cfg_bytes, uint32_t seq)
{
    memset(page, 0xFF, 128);            /* erased flash */
    memset(page, 0, 64);
    uint32_t magic = TEST_CFG_MAGIC;
    memcpy(page + 0, &magic, 4);
    memcpy(page + 4, &layout_version, 4);
    memcpy(page + 8, &seq, 4);
    uint16_t crc = o2p_mb_crc16(page, 12u + cfg_bytes);
    memcpy(page + 12u + cfg_bytes, &crc, 2);
}

static void test_transport_record_round_trips(void)
{
    o2p_transport_record_t r;
    o2p_transport_build(&r, 42u, 17u, O2P_BAUD_38400, O2P_PARITY_ODD);
    TEST_ASSERT_TRUE(o2p_transport_record_ok(&r));
    TEST_ASSERT_EQUAL_UINT32(O2P_TRANSPORT_MAGIC, r.magic);
    TEST_ASSERT_EQUAL_UINT32(42u, r.sequence);
    TEST_ASSERT_EQUAL_UINT8(O2P_TRANSPORT_VERSION, r.version);
    TEST_ASSERT_EQUAL_UINT8(17u, r.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, r.baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_ODD, r.parity_code);
    /* 16 bytes exactly, and the CRC at byte 12. If either moves, every loader
     * already in a pile is reading the wrong bytes. */
    TEST_ASSERT_EQUAL_UINT32(16u, (uint32_t)sizeof(r));
    TEST_ASSERT_EQUAL_UINT32(12u, (uint32_t)offsetof(o2p_transport_record_t, crc));
}

static void test_transport_record_rejects_what_it_should(void)
{
    o2p_transport_record_t base;
    o2p_transport_build(&base, 7u, 9u, O2P_BAUD_19200, O2P_PARITY_NONE);

    /* Erased flash is not a record. This is the ordinary case on the page an
     * older firmware wrote, and it must read as "nothing here", never as
     * address 0xFF. */
    o2p_transport_record_t erased;
    memset(&erased, 0xFF, sizeof(erased));
    TEST_ASSERT_FALSE(o2p_transport_record_ok(&erased));

    o2p_transport_record_t zeroed;
    memset(&zeroed, 0, sizeof(zeroed));
    TEST_ASSERT_FALSE(o2p_transport_record_ok(&zeroed));

    o2p_transport_record_t bad = base;
    bad.magic ^= 1u;
    TEST_ASSERT_FALSE(o2p_transport_record_ok(&bad));

    /* An unknown version is refused rather than read hopefully. The frozen
     * rule (a future need gets a SECOND block, never a version bump) is what
     * keeps this from becoming the original bug again. */
    bad = base;
    bad.version = 2u;
    TEST_ASSERT_FALSE(o2p_transport_record_ok(&bad));

    /* Every single-bit flip in the covered bytes must be caught. */
    for (unsigned byte = 0; byte < offsetof(o2p_transport_record_t, crc);
         byte++) {
        for (unsigned bit = 0; bit < 8u; bit++) {
            o2p_transport_record_t f = base;
            ((uint8_t *)&f)[byte] ^= (uint8_t)(1u << bit);
            if (f.magic != O2P_TRANSPORT_MAGIC ||
                f.version != (uint8_t)O2P_TRANSPORT_VERSION) {
                continue;   /* rejected earlier, for a different reason */
            }
            TEST_ASSERT_FALSE(o2p_transport_record_ok(&f));
        }
    }

    /* The reserved tail is NOT covered, deliberately and for the same reason
     * the configuration record's tail is not: it exists to be repurposed, and
     * hashing it would make a later firmware's use of it look like corruption
     * to this one. */
    o2p_transport_record_t spare = base;
    spare.reserved[0] = 0xA5u;
    TEST_ASSERT_TRUE(o2p_transport_record_ok(&spare));
}

static void test_transport_best_takes_the_newer_page(void)
{
    o2p_transport_record_t a, b, got;
    o2p_transport_build(&a, 10u, 5u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    o2p_transport_build(&b, 11u, 6u, O2P_BAUD_9600, O2P_PARITY_EVEN);

    TEST_ASSERT_TRUE(o2p_transport_best(&a, &b, &got));
    TEST_ASSERT_EQUAL_UINT8(6u, got.slave_addr);
    TEST_ASSERT_TRUE(o2p_transport_best(&b, &a, &got));
    TEST_ASSERT_EQUAL_UINT8(6u, got.slave_addr);

    /* One page valid, the other erased - the state right after the first
     * commit by a firmware that writes the block. */
    o2p_transport_record_t erased;
    memset(&erased, 0xFF, sizeof(erased));
    TEST_ASSERT_TRUE(o2p_transport_best(&a, &erased, &got));
    TEST_ASSERT_EQUAL_UINT8(5u, got.slave_addr);
    TEST_ASSERT_TRUE(o2p_transport_best(&erased, &a, &got));
    TEST_ASSERT_EQUAL_UINT8(5u, got.slave_addr);

    /* Neither: the caller must default, not read `got`. */
    TEST_ASSERT_FALSE(o2p_transport_best(&erased, &erased, &got));

    /* Sequence wrap. The comparison is signed on the difference, so a counter
     * that has rolled over still picks the newer record. */
    o2p_transport_build(&a, 0xFFFFFFFFu, 5u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    o2p_transport_build(&b, 0u, 6u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    TEST_ASSERT_TRUE(o2p_transport_best(&a, &b, &got));
    TEST_ASSERT_EQUAL_UINT8(6u, got.slave_addr);
}

static void test_loader_keeps_the_address_across_a_layout_bump(void)
{
    /* THE REGRESSION, built as bytes.
     *
     * A probe commissioned at address 22, 38400 8N1, then updated to a
     * firmware whose configuration layout is version 9 and whose struct is
     * four bytes longer. The loader in flash knows version 8 and cannot find
     * version 9's CRC, so it verifies nothing - which is the correct refusal,
     * and used to be the end of the story. */
    uint8_t page_a[128], page_b[128];
    build_future_page(page_a, 9u, 52u, 41u);
    memset(page_b, 0xFF, sizeof(page_b));

    o2p_transport_record_t tr;
    o2p_transport_build(&tr, 41u, 22u, O2P_BAUD_38400, O2P_PARITY_NONE);
    memcpy(page_a + O2P_TRANSPORT_OFFSET, &tr, sizeof(tr));

    o2p_transport_record_t a, b;
    memcpy(&a, page_a + O2P_TRANSPORT_OFFSET, sizeof(a));
    memcpy(&b, page_b + O2P_TRANSPORT_OFFSET, sizeof(b));

    /* cfg_ok = false is the loader's honest state here: it read the record,
     * saw a version it does not know, and declined to interpret it. */
    o2p_transport_t got;
    TEST_ASSERT_TRUE(o2p_transport_select(&a, &b, false, 0u, NULL, &got));
    TEST_ASSERT_EQUAL_UINT8(22u, got.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, got.baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_NONE, got.parity_code);

    /* And the known-bad calibration this replaces: with no block on either
     * page, the same situation yields nothing and the caller falls back to
     * the default identity. That is the bug, reproduced, and it is what the
     * two-identity knock procedure in FIRMWARE.md exists to survive on
     * loaders already potted. */
    memset(&a, 0xFF, sizeof(a));
    TEST_ASSERT_FALSE(o2p_transport_select(&a, &b, false, 0u, NULL, &got));
}

static void test_a_downgrade_does_not_resurrect_a_stale_block(void)
{
    /* Page B was written by this firmware (block, sequence 8). Page A was
     * then written by an OLDER application that does not write the block, at
     * sequence 9, after the operator moved the probe to address 31. The
     * block on B is valid, verifiable and wrong. */
    o2p_transport_record_t a, b;
    memset(&a, 0xFF, sizeof(a));
    o2p_transport_build(&b, 8u, 12u, O2P_BAUD_9600, O2P_PARITY_EVEN);

    const o2p_transport_t from_cfg = { 31u, O2P_BAUD_19200, O2P_PARITY_ODD };
    o2p_transport_t got;
    TEST_ASSERT_TRUE(o2p_transport_select(&a, &b, true, 9u, &from_cfg, &got));
    TEST_ASSERT_EQUAL_UINT8(31u, got.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_19200, got.baud_code);

    /* The other direction, and the tie. A readable record only wins when it
     * is strictly newer: at equal sequence the two describe the same commit,
     * and the block is the source that does not depend on a layout match. */
    TEST_ASSERT_TRUE(o2p_transport_select(&a, &b, true, 7u, &from_cfg, &got));
    TEST_ASSERT_EQUAL_UINT8(12u, got.slave_addr);
    TEST_ASSERT_TRUE(o2p_transport_select(&a, &b, true, 8u, &from_cfg, &got));
    TEST_ASSERT_EQUAL_UINT8(12u, got.slave_addr);
}

static void test_the_transport_block_clears_the_config_record(void)
{
    /* Layout, not luck: the block must start at or after the end of the
     * configuration record and finish inside the page. Growing the config
     * record past 64 bytes without moving the block would have the
     * application overwrite the one thing the loader can still read. */
    TEST_ASSERT_TRUE(O2P_TRANSPORT_OFFSET >= 12u + sizeof(o2p_config_t) + 2u);
    TEST_ASSERT_TRUE(O2P_TRANSPORT_OFFSET + O2P_TRANSPORT_BYTES <= 2048u);
    TEST_ASSERT_EQUAL_UINT32(0u, O2P_TRANSPORT_OFFSET % 8u);
    TEST_ASSERT_EQUAL_UINT32(0u, O2P_TRANSPORT_BYTES % 8u);
}

static void test_v4_migration_keeps_the_air_point(void)
{
    /* THE ONE MIGRATION THAT DOES NOT DISCARD THE CALIBRATION.
     *
     * Every earlier bump threw the air point away because its MEANING had
     * changed - a pre-v3 point did not know its own humidity, a pre-v4 one
     * did not know its own pressure. v5 changes nothing about a v4 air
     * point: the new field defaults to alpha = 1.0, which is precisely the
     * arithmetic v4 performed. Discarding the calibration here would force a
     * recalibration on every deployed probe for a field that reproduces the
     * behaviour those probes already have - a cost with nothing bought. */
    test_cfg_v4_t v4;
    memset(&v4, 0, sizeof(v4));
    v4.cal_air_na = 98765;
    v4.rh_setpoint_x100 = 7500u;
    v4.dt_max_k_x100 = 250u;
    v4.heater_max_duty_x100 = 3000u;
    v4.heater_pwm_hz = 1500u;
    v4.cal_temp_c100 = 2140;
    v4.tempco_ppm_per_k = 2000;
    v4.sht_pulse_interval_h = 12u;
    v4.heater_kp_x100 = 450u;
    v4.heater_ki_x100 = 60u;
    v4.assumed_p_hpa = 963u;
    v4.cal_air_frac_x1000 = 20685u;
    v4.cal_p_hpa = 963u;
    v4.slave_addr = 17u;
    v4.baud_code = O2P_BAUD_38400;
    v4.parity_code = O2P_PARITY_NONE;

    uint8_t rec[TEST_REC_BYTES];
    build_v4_record(rec, &v4, 77u, true);

    o2p_config_t out;
    uint32_t seq = 0u;
    memset(&out, 0xAA, sizeof(out));
    TEST_ASSERT_TRUE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));
    TEST_ASSERT_EQUAL_UINT32(77u, seq);

    /* The calibration, intact - all three fields that make it usable. */
    TEST_ASSERT_EQUAL_INT32(98765, out.cal_air_na);
    TEST_ASSERT_EQUAL_UINT16(20685u, out.cal_air_frac_x1000);
    TEST_ASSERT_EQUAL_UINT16(963u, out.cal_p_hpa);
    TEST_ASSERT_EQUAL_INT16(2140, out.cal_temp_c100);
    TEST_ASSERT_EQUAL_UINT16(963u, out.assumed_p_hpa);

    /* Transport and tuning, as every other migration keeps them. */
    TEST_ASSERT_EQUAL_UINT8(17u, out.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, out.baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_NONE, out.parity_code);
    TEST_ASSERT_EQUAL_UINT16(7500u, out.rh_setpoint_x100);
    TEST_ASSERT_EQUAL_UINT16(3000u, out.heater_max_duty_x100);
    TEST_ASSERT_EQUAL_INT16(2000, out.tempco_ppm_per_k);

    /* And the new field arrives at the value that reproduces v4 exactly. */
    TEST_ASSERT_EQUAL_UINT16(1000u, out.dil_alpha_x1000);
    TEST_ASSERT_TRUE(o2p_config_valid(&out));

    /* A corrupt v4 record is still refused - the CRC is checked on this path
     * too, and the caller falls back to full defaults. */
    build_v4_record(rec, &v4, 77u, false);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));
}

static void test_v2_migration_keeps_the_probe_reachable(void)
{
    const test_cfg_v2_t v2 = deployed_v2();
    uint8_t rec[TEST_REC_BYTES];
    build_v2_record(rec, &v2, 42u, true);

    o2p_config_t out;
    uint32_t seq = 0u;
    memset(&out, 0xAA, sizeof(out));
    TEST_ASSERT_TRUE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    /* THE POINT. All three transport fields survive verbatim; if any of them
     * defaulted, this probe would be answering at address 3 / 9600 / 8E1 and
     * its master would be talking to nothing. */
    TEST_ASSERT_EQUAL_UINT8(17u, out.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, out.baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_NONE, out.parity_code);

    /* And the settings an operator tuned in a pile and cannot easily retune. */
    TEST_ASSERT_EQUAL_UINT16(7500u, out.rh_setpoint_x100);
    TEST_ASSERT_EQUAL_UINT16(250u, out.dt_max_k_x100);
    TEST_ASSERT_EQUAL_UINT16(3000u, out.heater_max_duty_x100);
    TEST_ASSERT_EQUAL_UINT16(1500u, out.heater_pwm_hz);
    TEST_ASSERT_EQUAL_UINT16(450u, out.heater_kp_x100);
    TEST_ASSERT_EQUAL_UINT16(60u, out.heater_ki_x100);
    TEST_ASSERT_EQUAL_UINT16(12u, out.sht_pulse_interval_h);
    TEST_ASSERT_EQUAL_INT16(2000, out.tempco_ppm_per_k);
    TEST_ASSERT_EQUAL_INT16(2140, out.cal_temp_c100);

    /* THE CALIBRATION, AND ONLY THE CALIBRATION, IS DISCARDED. The v2 air
     * point was taken against an assumed DRY atmosphere at a humidity nobody
     * recorded, so no honest air fraction exists for it - and from layout 4 a
     * calibration must also say what pressure it was taken at. Zero on all
     * three is what raises CAL_DEFAULT and holds O2_COMP on its sentinel. */
    TEST_ASSERT_EQUAL_INT32(0, out.cal_air_na);
    TEST_ASSERT_EQUAL_UINT16(0u, out.cal_air_frac_x1000);
    TEST_ASSERT_EQUAL_UINT16(0u, out.cal_p_hpa);
    /* Which is exactly what the sampler tests for before substituting the
     * datasheet nominal and raising CAL_DEFAULT. */
    TEST_ASSERT_TRUE(out.cal_air_na <= 0);
    /* ...and a conversion on it refuses rather than inventing a number. */
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    cal.cal_air_na = out.cal_air_na;
    cal.air_frac = (float)out.cal_air_frac_x1000 * 1e-5f;
    float c = 0.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, 70000, 2500, &c));

    /* Fields that did not exist in v2 come up on their documented defaults,
     * not on whatever the old reserved bytes happened to hold. */
    TEST_ASSERT_EQUAL_UINT16(O2P_P_HPA_DEFAULT, out.assumed_p_hpa);

    /* The sequence carries across, so the higher-sequence-wins choice between
     * the two config pages still works after a migration. */
    TEST_ASSERT_EQUAL_UINT32(42u, seq);

    /* And the result is something the live register interface would accept. */
    TEST_ASSERT_TRUE(o2p_config_valid(&out));
}

static void test_v2_migration_falls_back_to_defaults_when_it_cannot_be_trusted(void)
{
    uint8_t rec[TEST_REC_BYTES];
    o2p_config_t out;
    uint32_t seq = 0u;

    /* A record that migrates to something INVALID is a failed migration, not
     * a configuration. 250 is past O2P_MB_ADDR_MAX (247), so this record would
     * install an unaddressable probe; the caller must fall back to full
     * defaults, which is the old behaviour and the safe one. */
    test_cfg_v2_t bad = deployed_v2();
    bad.slave_addr = 250u;
    build_v2_record(rec, &bad, 7u, true);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    /* An illegal baud code, for the same reason. */
    bad = deployed_v2();
    bad.baud_code = 9u;
    build_v2_record(rec, &bad, 7u, true);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    /* A heater setpoint outside the cell's rating: the migration must not be
     * a way to install a configuration a Modbus write would have refused. */
    bad = deployed_v2();
    bad.rh_setpoint_x100 = 9900u;
    build_v2_record(rec, &bad, 7u, true);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    /* A corrupt record is still corrupt. The CRC is checked at the OLD
     * layout's offset - 40 bytes in, not 44 - so a migration path that
     * borrowed the current offset would pass garbage through here. */
    test_cfg_v2_t good = deployed_v2();
    build_v2_record(rec, &good, 7u, false);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    /* Wrong magic, an unknown version, and a short buffer: all refused. */
    build_v2_record(rec, &good, 7u, true);
    rec[0] ^= 0xFFu;
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    build_v2_record(rec, &good, 7u, true);
    uint32_t v1 = 1u;
    memcpy(rec + 4, &v1, 4);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));

    build_v2_record(rec, &good, 7u, true);
    TEST_ASSERT_FALSE(o2p_config_migrate(rec, sizeof(rec) - 1u, &out, &seq));
    TEST_ASSERT_FALSE(o2p_config_migrate(NULL, sizeof(rec), &out, &seq));
}

/* ------------------------------------------------ oxygen: total pressure
 *
 * The cell answers to pO2 = C * P, so its current at a given fraction is
 * proportional to total pressure. K is fixed once at the air point and
 * therefore belongs to the pressure that air point was taken at. Correcting
 * only the vapour dilution - which is what this firmware did between
 * 2026-09-06 and this change - leaves the cell's own pressure-dependent gain
 * on the answer.
 */

/* The physical cell, as a test oracle: what current does an SGX cell actually
 * produce in fully aerated air at this temperature, humidity and TOTAL
 * PRESSURE, given a K taken at p_cal? The (p_act / p_cal) factor is the term
 * the firmware has to undo. */
static int32_t cell_na_in_air(const o2p_cal_t *cal, float t_c, float rh,
                              float p_act, float p_cal)
{
    float pw = 0.0f;
    o2p_gas_t g = gas_at(t_c, rh, p_act);
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&g, &pw));
    float c_wet = O2P_C_AIR * (p_act - pw) / p_act;
    float k = (float)cal->cal_air_na / logf(1.0f / (1.0f - cal->air_frac));
    float s = k * logf(1.0f / (1.0f - c_wet)) * (p_act / p_cal);
    return (int32_t)(s + 0.5f);
}

static void test_equal_pressures_change_nothing(void)
{
    /* THE NO-OP PROOF. Rev A has no barometer, so P_meas is ASSUMED_P_HPA and
     * P_cal was that same register when the air point was taken: the ratio is
     * exactly 1. This must be bit-for-bit identical to a calibration that
     * records no pressure at all, or the change is not the structural no-op it
     * claims to be. */
    o2p_gas_t g = gas_at(25.0f, 50.0f, 930.0f);
    o2p_cal_t with_p = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(o2p_calibrate_air(&with_p, 70000, 2500, &g));
    TEST_ASSERT_EQUAL_FLOAT(930.0f, with_p.cal_p_hpa);

    o2p_cal_t no_p = with_p;
    no_p.cal_p_hpa = 0.0f;          /* "unknown", as every stored record is */

    for (int32_t na = 30000; na <= 120000; na += 7000) {
        for (float t = 5.0f; t <= 60.0f; t += 11.0f) {
            o2p_gas_t m = gas_at(t, 80.0f, 930.0f);
            float a = 0.0f, b = 0.0f;
            o2p_status_t sa = o2p_dry_fraction_from_current(&with_p, na,
                                                            (int16_t)(t * 100.0f),
                                                            &m, &a);
            o2p_status_t sb = o2p_dry_fraction_from_current(&no_p, na,
                                                            (int16_t)(t * 100.0f),
                                                            &m, &b);
            TEST_ASSERT_EQUAL(sb, sa);
            /* Bit-identical, not merely close. */
            TEST_ASSERT_EQUAL_MEMORY(&b, &a, sizeof(a));
            TEST_ASSERT_EQUAL_UINT16(o2p_encode_percent(sb, b),
                                     o2p_encode_percent(sa, a));
        }
    }
}

static void test_unknown_calibration_pressure_is_no_correction_not_a_divide(void)
{
    /* Zero is the stored value of every calibration taken before layout 4, and
     * of every migrated record. It must mean "assume P_cal == P_meas", never
     * "divide by zero" and never "assume a standard atmosphere". */
    o2p_gas_t g = gas_at(25.0f, 50.0f, 930.0f);
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500, &g));
    cal.cal_p_hpa = 0.0f;

    /* Evaluated, finite and sane at a measurement pressure far from the cal
     * one - it simply is not corrected for it. */
    o2p_gas_t far_p = gas_at(25.0f, 50.0f, (float)O2P_P_HPA_MAX);
    float c = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&cal, 70000, 2500, &far_p, &c));
    TEST_ASSERT_TRUE(isfinite(c));
    TEST_ASSERT_TRUE(c > 0.0f && c < O2P_C_MAX);

    /* And a negative or non-finite stored pressure is treated the same way -
     * as no correction - rather than producing an inverted gain. */
    cal.cal_p_hpa = -930.0f;
    float d = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&cal, 70000, 2500, &far_p, &d));
    TEST_ASSERT_EQUAL_MEMORY(&c, &d, sizeof(c));
    cal.cal_p_hpa = NAN;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&cal, 70000, 2500, &far_p, &d));
    TEST_ASSERT_EQUAL_MEMORY(&c, &d, sizeof(c));
}

static void test_pressure_normalisation_has_the_right_sign_and_size(void)
{
    /* The reviewer's scenario, and its arithmetic reproduced to the digit.
     * Air point at 930 hPa, 25 C / 50 %RH; read out at the operating point,
     * 60 C / 100 %RH; weather then moves the ACTUAL pressure by +/-3.5 %. */
    const float p_cal = 930.0f;
    o2p_gas_t cal_gas = gas_at(25.0f, 50.0f, p_cal);
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500, &cal_gas));
    TEST_ASSERT_EQUAL_FLOAT(p_cal, cal.cal_p_hpa);

    static const struct { float f, no_baro_pct; } row[] = {
        {0.965f, 20.073f},   /* -4.17 % relative */
        {1.000f, 20.946f},   /*  exact           */
        {1.035f, 21.813f},   /* +4.14 % relative */
    };
    for (unsigned i = 0; i < sizeof(row) / sizeof(row[0]); i++) {
        const float p_act = p_cal * row[i].f;
        const int32_t na = cell_na_in_air(&cal, 60.0f, 100.0f, p_act, p_cal);

        /* (1) NO BAROMETER, which is Rev A. The firmware only has the assumed
         * 930, so it cannot see the weather at all and the error stands. This
         * is the number the review computed, and it is why the fix is called
         * structural: nothing here changes it. */
        o2p_gas_t assumed = gas_at(60.0f, 100.0f, p_cal);
        float c_assumed = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_dry_fraction_from_current(&cal, na, 6000,
                                                        &assumed, &c_assumed));
        TEST_ASSERT_FLOAT_WITHIN(0.01f, row[i].no_baro_pct, c_assumed * 100.0f);

        /* (2) BAROMETER FITTED, no K normalisation - the state of the
         * firmware before this change. Correcting the vapour term against the
         * real pressure while leaving K at its calibration pressure still
         * leaves about -3.21 %/+3.18 % on the answer. */
        o2p_cal_t unnormalised = cal;
        unnormalised.cal_p_hpa = 0.0f;
        o2p_gas_t measured = gas_at(60.0f, 100.0f, p_act);
        float c_half = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_dry_fraction_from_current(&unnormalised, na, 6000,
                                                        &measured, &c_half));

        /* (3) BAROMETER FITTED AND K NORMALISED. Fully aerated air comes back
         * as fully aerated air at any pressure - which is the claim. */
        float c_full = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_dry_fraction_from_current(&cal, na, 6000,
                                                        &measured, &c_full));
        TEST_ASSERT_FLOAT_WITHIN(0.0002f, O2P_C_AIR, c_full);

        /* Direction: the correction moves the half-corrected number TOWARDS
         * the truth, and by more than it was ever away from it after. */
        float err_half = fabsf(c_half - O2P_C_AIR);
        float err_full = fabsf(c_full - O2P_C_AIR);
        TEST_ASSERT_TRUE(err_full <= err_half);
        if (row[i].f != 1.000f) {
            /* At the two weather extremes the half-corrected error is real
             * and about 3.2 % relative; the fully corrected one is noise. */
            TEST_ASSERT_TRUE(err_half / O2P_C_AIR > 0.03f);
            TEST_ASSERT_TRUE(err_full / O2P_C_AIR < 0.001f);
            /* And the sign is right: less pressure reads low uncorrected. */
            if (row[i].f < 1.0f) {
                TEST_ASSERT_TRUE(c_half < O2P_C_AIR);
            } else {
                TEST_ASSERT_TRUE(c_half > O2P_C_AIR);
            }
        }
    }
}

static void test_cal_pressure_register_is_bounded(void)
{
    /* 0 is legal and means "unknown"; anything else must be a pressure in the
     * same window as ASSUMED_P_HPA, because P_cal/P_meas scales oxygen
     * directly and a fat-fingered 5 hPa would rescale every reading without
     * ever looking like a fault. */
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.cal_p_hpa);

    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t tiny[] = {0x03, 0x06, 0x00, 0x44, 0x00, 0x05};
    size_t n = framed(req, tiny, sizeof(tiny));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.cal_p_hpa);

    const uint8_t huge[] = {0x03, 0x06, 0x00, 0x44, 0x0B, 0xB8};   /* 3000 */
    n = framed(req, huge, sizeof(huge));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);

    const uint8_t site[] = {0x03, 0x06, 0x00, 0x44, 0x03, 0xA2};   /* 930 */
    n = framed(req, site, sizeof(site));
    TEST_ASSERT_EQUAL_UINT(8, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(930u, rm.cfg.cal_p_hpa);

    /* Zero is writable again: "this calibration's pressure is unknown" has to
     * be expressible, or a migrated record could not be represented. */
    const uint8_t unknown[] = {0x03, 0x06, 0x00, 0x44, 0x00, 0x00};
    n = framed(req, unknown, sizeof(unknown));
    TEST_ASSERT_EQUAL_UINT(8, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.cal_p_hpa);

    /* And it reads back through the config block. */
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x44, 0x00, 0x01};
    n = framed(req, rd, sizeof(rd));
    TEST_ASSERT_EQUAL_UINT(3 + 2 + 2, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(0u, (rsp[3] << 8) | rsp[4]);
}

/* ------------------------------------------- chamber cache and its age cap
 *
 * The SHT45's own de-creep heater fires every 8 h by default and the chamber
 * channels are masked for 30 s afterwards. With dry-basis O2_COMP depending on
 * RH, that used to blank the primary oxygen channel three times a day and
 * label the gap I2C_FAIL_SHT - scheduled maintenance reported as a bus
 * failure. The bridge is bounded by O2P_RH_MAX_AGE_S, and the bound is what
 * keeps a dead sensor from being bridged forever.
 */

static void test_a_pulse_gap_is_bridged_and_a_dead_sensor_is_not(void)
{
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    o2p_gas_t fresh = gas_at(45.0f, 88.0f, 930.0f);
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 4500, &fresh));

    o2p_gas_cache_t cache;
    memset(&cache, 0, sizeof(cache));

    /* Before the first real reading there is nothing to bridge with, and the
     * cache must not invent one. */
    o2p_gas_t g = fresh;
    g.valid = false;
    TEST_ASSERT_FALSE(o2p_gas_cache_apply(&cache, &g, 1000u));
    TEST_ASSERT_FALSE(g.valid);

    /* A measured cycle at t = 1000 s. */
    o2p_gas_cache_update(&cache, &fresh, 1000u);
    TEST_ASSERT_TRUE(cache.valid);

    float ref = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&cal, 70000, 4500, &fresh, &ref));

    /* THE PULSE. The chamber channels are masked for the whole recovery
     * window; every cycle inside it carries no RH and no chamber temperature.
     * 31 s is the worst case the derivation in o2.h covers - 30 s of mask plus
     * the sample quantisation - and it must still publish, from the same
     * sensor's own last measurement rather than from a substitute. */
    for (uint32_t dt = 1u; dt <= O2P_RH_MAX_AGE_S; dt++) {
        o2p_gas_t masked = gas_at(45.0f, 88.0f, 930.0f);
        masked.rh_pct = 0.0f;      /* what a masked cycle actually carries */
        masked.t_c = 0.0f;
        masked.valid = false;
        /* A masked cycle must never enter the cache: 0 %RH at 0 C is a
         * perfectly plausible reading, and caching it would turn a missing
         * sensor into a confident dry-air correction. */
        o2p_gas_cache_update(&cache, &masked, 1000u + dt);
        TEST_ASSERT_EQUAL_UINT32(1000u, cache.taken_s);

        TEST_ASSERT_TRUE(o2p_gas_cache_apply(&cache, &masked, 1000u + dt));
        TEST_ASSERT_TRUE(masked.valid);
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_dry_fraction_from_current(&cal, 70000, 4500,
                                                        &masked, &c));
        TEST_ASSERT_EQUAL_MEMORY(&ref, &c, sizeof(c));
        TEST_ASSERT_NOT_EQUAL(O2P_U16_INVALID, o2p_encode_percent(O2P_OK, c));
    }

    /* The cap covers the recovery window it was derived against, with margin,
     * and is not merely equal to it. */
    TEST_ASSERT_TRUE(O2P_RH_MAX_AGE_S > 32u);

    /* ONE SECOND PAST THE CAP the value is unevaluable, and the channel takes
     * its sentinel exactly as it did before. Monotonic: it must stay refused
     * as the gap grows, not come back with a number. */
    for (uint32_t dt = O2P_RH_MAX_AGE_S + 1u; dt <= O2P_RH_MAX_AGE_S + 600u;
         dt += 7u) {
        o2p_gas_t stale = gas_at(45.0f, 88.0f, 930.0f);
        stale.valid = false;
        TEST_ASSERT_FALSE(o2p_gas_cache_apply(&cache, &stale, 1000u + dt));
        TEST_ASSERT_FALSE(stale.valid);
        float c = 12345.0f;
        TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                          o2p_dry_fraction_from_current(&cal, 70000, 4500,
                                                        &stale, &c));
        TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID,
                                 o2p_encode_percent(O2P_UNEVALUABLE, c));
        TEST_ASSERT_EQUAL_FLOAT(12345.0f, c);   /* nothing was written */
    }

    /* A GENUINELY DEAD SHT45 - one that simply never answers again - reaches
     * the sentinel and stays there. This is the case the age cap exists to
     * keep separate from the pulse, and the one a cache without a cap would
     * have papered over forever. The fault bit is still raised by the sampler
     * throughout; it is just no longer what decides validity. */
    for (uint32_t t = 1000u + O2P_RH_MAX_AGE_S + 1u; t <= 1000u + 86400u;
         t += 3600u) {
        o2p_gas_t dead = gas_at(45.0f, 88.0f, 930.0f);
        dead.valid = false;
        o2p_gas_cache_update(&cache, &dead, t);       /* never accepted */
        TEST_ASSERT_FALSE(o2p_gas_cache_apply(&cache, &dead, t));
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                          o2p_dry_fraction_from_current(&cal, 70000, 4500,
                                                        &dead, &c));
    }
    /* ...and the bit it raises is still a bit, still reported, and still
     * outside both validity masks - the report and the criterion are now two
     * different things on purpose. */
    TEST_ASSERT_TRUE(O2P_F_I2C_FAIL_SHT != 0u);
    TEST_ASSERT_EQUAL_HEX16(0u, O2P_FAULTS_INVALIDATE_O2 & O2P_F_I2C_FAIL_SHT);
    TEST_ASSERT_EQUAL_HEX16(0u,
                            O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_I2C_FAIL_SHT);
}

/* main.c freezes the oxygen verdict at the end of PH_O2 so the electrode
 * diagnostics sampled afterwards cannot mute the measurement they exist to
 * explain. main.c is not host-buildable, so what is tested here is the RULE it
 * applies, written the same way round, against the case that broke it.
 *
 * Measured on live hardware 2026-09-08: probe eleven minutes into a fifteen-
 * minute settle, publishing 20.91 %vol with raw_ok = 1 and settle_s = 769 in
 * one frame. The verdict was a plain snapshot taken before cycle_publish()
 * raised O2P_F_SETTLING, so the flag simply was not in it. */
static void test_the_o2_verdict_freeze_cannot_drop_a_state_fault(void)
{
    /* The regression, reproduced. A snapshot rule loses any fault raised after
     * the freeze - and answers "valid" for a cell that is explicitly settling. */
    uint16_t at_o2 = 0u;                        /* clean at the conversion */
    uint16_t now   = O2P_F_SETTLING;            /* raised later in the cycle */
    TEST_ASSERT_TRUE(o2p_o2_valid((uint16_t)at_o2));

    /* The rule main.c now applies: subtractive, so only the faults the
     * electrode phases are ALLOWED to have raised are dropped. */
    uint16_t verdict =
        (uint16_t)(at_o2 | (now & (uint16_t)~O2P_FAULTS_POST_O2));
    /* The property under test is that the late-raised STATE FAULT SURVIVES the
     * freeze. Asserting !o2p_o2_valid() tested that only by proxy, through
     * SETTLING's membership of the raw mask - so when that membership moved
     * on 2026-09-08 the regression test for 3c8d884 started failing without
     * the regression coming back. Assert the bit, then the consequence. */
    TEST_ASSERT_TRUE_MESSAGE((verdict & O2P_F_SETTLING) != 0u,
        "the freeze must not drop a state fault raised after PH_O2");
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(verdict));

    /* And it still does the job it was introduced for: an ADS failure in
     * PH_WE/PH_RE, after a good oxygen conversion, does NOT reach backwards. */
    uint16_t late_ads = O2P_F_ADS_DRDY_STUCK | O2P_F_I2C_FAIL_ADS;
    TEST_ASSERT_FALSE(o2p_o2_valid(late_ads));   /* it would, unfrozen */
    verdict = (uint16_t)(0u | (late_ads & (uint16_t)~O2P_FAULTS_POST_O2));
    TEST_ASSERT_TRUE(o2p_o2_valid(verdict));

    /* The invariant that makes the above safe as the fault set grows: every
     * fault that invalidates oxygen and is NOT an acquisition result survives
     * the freeze. Adding one to INVALIDATE_O2 without listing it in POST_O2
     * is then automatically fail-closed - the opposite of what happened here.
     * SETTLING is the one that matters and is named explicitly. */
    TEST_ASSERT_EQUAL_HEX16(0u, O2P_FAULTS_POST_O2 & O2P_F_SETTLING);
    TEST_ASSERT_EQUAL_HEX16(
        0u, (uint16_t)(O2P_FAULTS_POST_O2 & (uint16_t)~O2P_FAULTS_INVALIDATE_O2));
}

static void test_a_fresh_reading_is_never_overridden_by_the_cache(void)
{
    o2p_gas_cache_t cache;
    memset(&cache, 0, sizeof(cache));
    o2p_gas_t old_gas = gas_at(20.0f, 30.0f, 930.0f);
    o2p_gas_cache_update(&cache, &old_gas, 100u);

    o2p_gas_t now = gas_at(55.0f, 95.0f, 930.0f);
    TEST_ASSERT_TRUE(o2p_gas_cache_apply(&cache, &now, 101u));
    TEST_ASSERT_EQUAL_FLOAT(55.0f, now.t_c);
    TEST_ASSERT_EQUAL_FLOAT(95.0f, now.rh_pct);

    /* And an out-of-range reading cannot enter the cache at all, so a failing
     * part cannot leave a poisoned entry behind to be bridged from. */
    o2p_gas_t bad = gas_at(25.0f, 150.0f, 930.0f);
    o2p_gas_cache_update(&cache, &bad, 200u);
    TEST_ASSERT_EQUAL_UINT32(100u, cache.taken_s);
    bad.t_c = NAN;
    bad.rh_pct = 50.0f;
    o2p_gas_cache_update(&cache, &bad, 200u);
    TEST_ASSERT_EQUAL_UINT32(100u, cache.taken_s);

    /* An uptime that has gone backwards - which only a wrap can do, at 136
     * years - ages out rather than reading as fresh. */
    o2p_gas_t g = gas_at(20.0f, 30.0f, 930.0f);
    g.valid = false;
    TEST_ASSERT_FALSE(o2p_gas_cache_apply(&cache, &g, 99u));
}



/* --------------------------------------------- dilution efficacy (alpha) --
 *
 * The gas law is not in dispute; how much of it the CELL SHOWS is. The
 * 2026-09-07 sweep put this cell at alpha = 0.402 +/- 0.046 over an 18.2 hPa
 * isothermal dry-down, with the tempco identified separately on a disjoint
 * isobaric leg (O2-HUMIDITY-CORRECTION.md 15.3). These tests pin the three
 * things that can go wrong with putting a number like that in firmware:
 * alpha = 1 must be the old behaviour bit-for-bit, the air point and the
 * measurement must use the SAME alpha, and a bad alpha must refuse rather
 * than fall back to 1.
 */

/* alpha the sweep measured, and its %vol x 1000 register spelling. */
#define TEST_ALPHA      0.402f
#define TEST_ALPHA_X1K  402u

/* What a cell with efficacy `alpha` actually puts out in fully aerated air.
 * The gas is diluted by f; the CELL responds as though it were diluted by
 * f_eff. Pressure is held equal to the calibration pressure here - the
 * pressure term has its own oracle above and mixing them would test neither.
 *
 * `k` IS PASSED IN, NOT DERIVED FROM cal->air_frac, and that is the whole
 * difference between an oracle and a mirror. An earlier version computed
 * k = cal_air_na / L(cal->air_frac) - but cal->air_frac is produced by
 * o2p_calibrate_air(), which is under test. If o2p_air_fraction() used the
 * WRONG fraction, this oracle adopted the same wrong fraction and the round
 * trip closed anyway. Review 2026-09-07 called it circular on the calibration
 * side, and it was: the test passed for a year of alphas and would have
 * passed for the wrong one too.
 *
 * Now k comes from the physics, computed once from a first-principles air
 * point, and the calibration has to AGREE with it rather than define it. */
static int32_t cell_na_alpha(float k, float t_c, float rh,
                             float p_hpa, float alpha)
{
    float pw = 0.0f;
    o2p_gas_t g = gas_at(t_c, rh, p_hpa);
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&g, &pw));
    float f_eff = 1.0f - alpha * (pw / p_hpa);
    float c_app = O2P_C_AIR * f_eff;
    return (int32_t)(k * logf(1.0f / (1.0f - c_app)) + 0.5f);
}

/* The cell constant, from the physics and nothing the firmware computed: a
 * cell that yields `na` at these conditions with this efficacy. */
static float k_from_air_point(int32_t na, float t_c, float rh, float p_hpa,
                              float alpha)
{
    float pw = 0.0f;
    o2p_gas_t g = gas_at(t_c, rh, p_hpa);
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&g, &pw));
    float c_app = O2P_C_AIR * (1.0f - alpha * (pw / p_hpa));
    return (float)na / logf(1.0f / (1.0f - c_app));
}

static void test_alpha_one_is_the_full_gas_law(void)
{
    /* THE NO-OP PROOF. Every number in sections 2-14 was computed at alpha =
     * 1, so the default must reproduce them exactly - not nearly. */
    o2p_gas_t g = gas_at(60.0f, 100.0f, TEST_P_HPA);
    float pw = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&g, &pw));

    float alpha1 = 0.0f, plain = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16815f, 1.0f, &alpha1));
    plain = 0.16815f * TEST_P_HPA / (TEST_P_HPA - pw);
    TEST_ASSERT_EQUAL_FLOAT(plain, alpha1);

    float air = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_air_fraction(&g, 1.0f, &air));
    TEST_ASSERT_EQUAL_FLOAT(O2P_C_AIR * (TEST_P_HPA - pw) / TEST_P_HPA, air);
}

static void test_alpha_zero_is_exactly_no_correction(void)
{
    /* Zero is a SETTING, not an absence - and on this cell it is the setting
     * that beats alpha = 1 at pile conditions (15.4). It must be the exact
     * identity, at any humidity, or "no correction" is a near-miss. */
    const float rhs[] = {0.0f, 42.3f, 88.0f, 100.0f};
    for (size_t i = 0; i < sizeof(rhs) / sizeof(rhs[0]); i++) {
        o2p_gas_t g = gas_at(45.0f, rhs[i], 963.0f);
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.18f, 0.0f, &c));
        TEST_ASSERT_EQUAL_FLOAT(0.18f, c);
        float air = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK, o2p_air_fraction(&g, 0.0f, &air));
        TEST_ASSERT_EQUAL_FLOAT(O2P_C_AIR, air);
    }
}

static void test_alpha_scales_the_correction_it_does_not_scale_the_answer(void)
{
    /* The fitted alpha applies alpha of the DILUTION, i.e. f_eff = 1 -
     * alpha*(1-f). Getting this wrong as c_wet/f * alpha, or as
     * c_wet/(alpha*f), both look plausible and both are wrong; this is the
     * arithmetic that separates them. */
    o2p_gas_t g = gas_at(60.0f, 100.0f, 963.0f);
    float pw = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&g, &pw));
    float f = (963.0f - pw) / 963.0f;
    float want = 0.16f / (1.0f - TEST_ALPHA * (1.0f - f));

    float got = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, TEST_ALPHA, &got));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, want, got);

    /* And it lies strictly between the two extremes, closer to no correction
     * than to full - which is the whole reason 15.4 reverses the decision. */
    float none = 0.0f, full = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, 0.0f, &none));
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, 1.0f, &full));
    TEST_ASSERT_TRUE(got > none);
    TEST_ASSERT_TRUE(got < full);
    TEST_ASSERT_TRUE(got - none < full - got);
}

static void test_a_cell_with_this_alpha_reads_dry_air_at_any_humidity(void)
{
    /* THE END-TO-END CLAIM, and the only test here that would catch the air
     * point and the measurement disagreeing about alpha.
     *
     * Build a cell that genuinely shows only alpha of the dilution. Calibrate
     * it in moist room air - the 23.4 C / 42.3 %RH point this bench actually
     * took. Then read it across the full humidity span the sweep covered. If
     * the model is implemented consistently on both sides, every reading
     * comes back at dry air; if o2p_air_fraction() were left on the plain gas
     * law while the measurement used alpha, K would carry the difference and
     * the error would grow with humidity - invisible at the calibration point
     * and largest where it matters. */
    o2p_cal_t cal = { .dil_alpha = TEST_ALPHA };
    o2p_gas_t cal_gas = gas_at(23.4f, 42.3f, 963.0f);
    /* K from the PHYSICS, before the firmware sees anything. Everything below
     * is then checked against it rather than against itself. */
    const float k_true = k_from_air_point(70000, 23.4f, 42.3f, 963.0f,
                                          TEST_ALPHA);
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2340, &cal_gas));
    TEST_ASSERT_EQUAL_INT16(2340, cal.cal_temp_c100);
    /* THE NON-CIRCULAR ASSERTION: the fraction the firmware stored must be
     * the one the physics says was present, to a part in 10^4. This is what
     * catches an o2p_air_fraction() that used f instead of f_eff - the case
     * the old oracle structurally could not see. */
    TEST_ASSERT_FLOAT_WITHIN(0.0001f,
                             1.0f - expf(-(float)cal.cal_air_na / k_true),
                             cal.air_frac);

    const float rhs[] = {5.0f, 20.0f, 42.3f, 60.0f, 85.0f, 100.0f};
    for (size_t i = 0; i < sizeof(rhs) / sizeof(rhs[0]); i++) {
        o2p_gas_t g = gas_at(23.4f, rhs[i], 963.0f);
        int32_t na = cell_na_alpha(k_true, 23.4f, rhs[i], 963.0f, TEST_ALPHA);
        float c = 0.0f;
        TEST_ASSERT_EQUAL(O2P_OK,
                          o2p_dry_fraction_from_current(&cal, na, 2340, &g, &c));
        /* 0.02 pp, i.e. the same order as the 0.018 pp the fit achieved on
         * the real trace - here it is quantisation of cell_na to whole
         * nanoamps, not model error. */
        TEST_ASSERT_FLOAT_WITHIN(0.0002f, O2P_C_AIR, c);
    }

    /* The counter-proof: correcting the SAME cell with the naive alpha = 1
     * over-corrects, and does so most where the water is. This is the
     * measured failure 15.4 is about, not a hypothetical. */
    o2p_cal_t naive = cal;
    naive.dil_alpha = 1.0f;
    o2p_gas_t wet = gas_at(23.4f, 100.0f, 963.0f);
    int32_t na = cell_na_alpha(k_true, 23.4f, 100.0f, 963.0f, TEST_ALPHA);
    float over = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_fraction_from_current(&naive, na, 2340, &wet, &over));
    TEST_ASSERT_TRUE(over > O2P_C_AIR + 0.001f);
}

static void test_a_bad_alpha_refuses_it_does_not_default_to_one(void)
{
    /* Substituting 1.0 for a nonsense alpha would publish the naive
     * correction under the fitted one's name - a wrong number wearing the
     * right label, which is the failure mode this whole file is written
     * against. */
    o2p_gas_t g = gas_at(45.0f, 80.0f, 963.0f);
    float c = 12345.0f;
    const float bad[] = {NAN, INFINITY, -INFINITY, -0.001f, -1.0f,
                         O2P_DIL_ALPHA_MAX + 0.001f, 100.0f};
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                          o2p_dry_from_wet(&g, 0.18f, bad[i], &c));
        TEST_ASSERT_EQUAL(O2P_UNEVALUABLE, o2p_air_fraction(&g, bad[i], &c));
        TEST_ASSERT_EQUAL_FLOAT(12345.0f, c);   /* nothing was written */
    }
    /* Both ends of the legal range are legal. */
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.18f, 0.0f, &c));
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_from_wet(&g, 0.18f, O2P_DIL_ALPHA_MAX, &c));
}

static void test_an_alpha_that_divides_by_nothing_is_refused(void)
{
    /* alpha above 1 pushes f_eff BELOW f, and f's own bound cannot catch
     * that: at the vapour ceiling f is 0.5, perfectly legal, while f_eff at
     * alpha = 2 is zero and would divide.
     *
     * The two bounds compose exactly - alpha <= 2 and p_w <= P/2 meet at
     * f_eff = 0 and nowhere before it - so this is reachable only by
     * standing on both limits at once, which is what the fixture does:
     * P is set to exactly twice the vapour pressure at 80 C saturated.
     * Refused, never clamped: a clamped f_eff publishes a number that is
     * neither the corrected value nor the raw one. */
    o2p_gas_t probe = gas_at(80.0f, 100.0f, 1013.25f);
    float pw = 0.0f;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_vapour_pressure_hpa(&probe, &pw));

    o2p_gas_t g = gas_at(80.0f, 100.0f, 2.0f * pw);   /* p_w is exactly P/2 */
    float c = 12345.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_dry_from_wet(&g, 0.16f, O2P_DIL_ALPHA_MAX, &c));
    TEST_ASSERT_EQUAL_FLOAT(12345.0f, c);
    /* The same gas at alpha = 1 still converts, so the refusal is about
     * f_eff and not about the gas being out of range - which is the whole
     * point of checking f_eff separately from f. */
    TEST_ASSERT_EQUAL(O2P_OK, o2p_dry_from_wet(&g, 0.16f, 1.0f, &c));
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 0.32f, c);        /* exactly doubled */

    /* One step back from the corner it evaluates, with a correction of about
     * 20x. Nothing here is clamped on the way. */
    o2p_gas_t inside = gas_at(80.0f, 100.0f, 2.1f * pw);
    TEST_ASSERT_EQUAL(O2P_OK,
                      o2p_dry_from_wet(&inside, 0.005f, O2P_DIL_ALPHA_MAX, &c));
    TEST_ASSERT_TRUE(c > 0.09f && c < 0.12f);
}

static void test_dil_alpha_register_bounds_and_default(void)
{
    o2p_config_t c;
    o2p_config_defaults(&c);
    /* The default is the full gas law, NOT the measured 0.402: a firmware
     * default is a claim about every cell. */
    TEST_ASSERT_EQUAL_UINT16(1000u, c.dil_alpha_x1000);
    TEST_ASSERT_TRUE(o2p_config_valid(&c));

    c.dil_alpha_x1000 = 0u;            /* no correction is a legal setting */
    TEST_ASSERT_TRUE(o2p_config_valid(&c));
    c.dil_alpha_x1000 = TEST_ALPHA_X1K;
    TEST_ASSERT_TRUE(o2p_config_valid(&c));
    c.dil_alpha_x1000 = 2000u;
    TEST_ASSERT_TRUE(o2p_config_valid(&c));
    c.dil_alpha_x1000 = 2001u;
    TEST_ASSERT_FALSE(o2p_config_valid(&c));
    c.dil_alpha_x1000 = 65535u;
    TEST_ASSERT_FALSE(o2p_config_valid(&c));
}

static void test_writing_dil_alpha_re_references_the_air_fraction(void)
{
    /* CAL_AIR_FRAC is C_air * f_eff(alpha_old) and K is fixed against it, so
     * a new alpha would rescale every later reading by the ratio if the
     * stored fraction were left alone. It is restated under the new alpha
     * instead - the same measurement, a different cell model - because
     * f_eff = 1 - alpha*(1-f) inverts exactly and nothing is missing. */
    rm.cfg.dil_alpha_x1000 = 1000u;
    /* The bench's own air point: 23.4 C / 42.3 %RH at 963 hPa, which is
     * p_w = 12.14 hPa, f = 0.98739, and at alpha = 1 an air fraction of
     * C_AIR * f = 0.20682. */
    rm.cfg.cal_air_frac_x1000 = 20682u;
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x45, 0x01, 0x92};  /* 402 */
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x06, rsp[1]);            /* echoed, not an exception */
    TEST_ASSERT_EQUAL_UINT16(TEST_ALPHA_X1K, rm.cfg.dil_alpha_x1000);
    /* 1 - f = 0.012604; at alpha 0.402 that is 0.005067, so the fraction
     * moves from 0.20682 up towards dry air, to 0.20840. It must move UP -
     * a smaller alpha means the cell showed less of the dilution than the
     * old model credited it with. */
    TEST_ASSERT_UINT16_WITHIN(2u, 20840u, rm.cfg.cal_air_frac_x1000);
    TEST_ASSERT_TRUE(rm.cfg.cal_air_frac_x1000 > 20682u);
    TEST_ASSERT_TRUE(rm.cfg.cal_air_frac_x1000 < 20946u);   /* never past dry */
    TEST_ASSERT_TRUE(o2p_config_valid(&rm.cfg));

    /* And it is REVERSIBLE: back to alpha = 1 restores the number, so the
     * transform is the exact inversion it claims to be and not a one-way
     * approximation that drifts every time someone tunes alpha. */
    const uint8_t back[] = {0x03, 0x06, 0x00, 0x45, 0x03, 0xE8};  /* 1000 */
    n = framed(req, back, sizeof(back));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_UINT16_WITHIN(2u, 20682u, rm.cfg.cal_air_frac_x1000);

    /* Re-writing the SAME alpha changes nothing at all. */
    rm.cfg.cal_air_frac_x1000 = 20828u;
    n = framed(req, back, sizeof(back));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT16(20828u, rm.cfg.cal_air_frac_x1000);

    /* An uncalibrated probe stays uncalibrated - zero is "unknown" and does
     * not get re-referenced into a plausible-looking fraction. */
    rm.cfg.cal_air_frac_x1000 = 0u;
    n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.cal_air_frac_x1000);

    /* And alpha_old = 0 is the one case that cannot be inverted: at alpha 0
     * the stored fraction is C_AIR whatever the humidity was, so (1-f) is
     * genuinely gone. It falls back to "unknown" rather than inventing one. */
    rm.cfg.dil_alpha_x1000 = 0u;
    rm.cfg.cal_air_frac_x1000 = 20946u;
    n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT16(TEST_ALPHA_X1K, rm.cfg.dil_alpha_x1000);
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.cal_air_frac_x1000);

    /* It reads back. */
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x45, 0x00, 0x01};
    n = framed(req, rd, sizeof(rd));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT16(TEST_ALPHA_X1K, (rsp[3] << 8) | rsp[4]);
}

static void test_a_whole_block_write_does_not_lose_the_calibration(void)
{
    /* THE ORDERING TRAP, pinned. A master rewriting the whole config block in
     * one FC16 applies 0x0043 before 0x0045, so an implementation that
     * ZEROED the air fraction on an alpha change would silently discard the
     * calibration the same frame had just supplied - a correct write losing
     * data, with an echoed response and no exception. Re-referencing has no
     * such order dependence: the value written at 0x0043 is what 0x0045
     * restates. */
    rm.cfg.dil_alpha_x1000 = 1000u;
    rm.cfg.cal_air_frac_x1000 = 0u;

    /* FC16 over ASSUMED_P_HPA, CAL_AIR_FRAC, CAL_P_HPA, DIL_ALPHA -
     * 0x0042..0x0045, the four registers this change is written with.
     *
     * A MASTER THAT STATES THE FRACTION IS TAKEN LITERALLY. It said, in one
     * frame, "the air fraction is 20682 and alpha is 453"; transforming the
     * number it just supplied would be second-guessing it, and which of the
     * two it meant would depend on word order inside the frame. The
     * restatement is for a write that changes alpha ALONE. */
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {
        0x03, 0x10, 0x00, 0x42, 0x00, 0x04, 0x08,
        0x03, 0xC3,          /* 0x0042 ASSUMED_P_HPA = 963  */
        0x50, 0xCA,          /* 0x0043 CAL_AIR_FRAC  = 20682 */
        0x03, 0xC3,          /* 0x0044 CAL_P_HPA     = 963  */
        0x01, 0x92,          /* 0x0045 DIL_ALPHA     = 402  */
    };
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);            /* not an exception */

    TEST_ASSERT_EQUAL_UINT16(963u, rm.cfg.assumed_p_hpa);
    TEST_ASSERT_EQUAL_UINT16(963u, rm.cfg.cal_p_hpa);
    TEST_ASSERT_EQUAL_UINT16(TEST_ALPHA_X1K, rm.cfg.dil_alpha_x1000);
    /* Verbatim - not zeroed, and not transformed either. */
    TEST_ASSERT_EQUAL_UINT16(20682u, rm.cfg.cal_air_frac_x1000);
    TEST_ASSERT_TRUE(o2p_config_valid(&rm.cfg));

    /* Whereas alpha ALONE, in its own frame, does restate it - and the two
     * paths must not be confused, because one word of a frame decides which
     * applies. */
    rm.cfg.dil_alpha_x1000 = 1000u;
    rm.cfg.cal_air_frac_x1000 = 20682u;
    const uint8_t alone[] = {0x03, 0x06, 0x00, 0x45, 0x01, 0x92};
    n = framed(req, alone, sizeof(alone));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_UINT16_WITHIN(2u, 20840u, rm.cfg.cal_air_frac_x1000);
}

static void test_an_unrecoverable_alpha_refuses_rather_than_inventing(void)
{
    /* The restatement divides by alpha_old, and CAL_AIR_FRAC is quantised to
     * 1e-5, so one LSB becomes 1e-5/alpha_old of air fraction. Below about
     * alpha_old = 0.01 the stored value rounds to dry air for EVERY humidity
     * and (1-f) is not imprecise, it is GONE.
     *
     * The first implementation treated only exact zero as loss and happily
     * produced a plausible wrong fraction from an unrecoverable one - a
     * measured ~0.12 pp of permanent calibration error, passing validation
     * and looking like a calibration. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t to_402[] = {0x03, 0x06, 0x00, 0x45, 0x01, 0x92};

    rm.cfg.dil_alpha_x1000 = 1u;               /* alpha_old = 0.001 */
    rm.cfg.cal_air_frac_x1000 = 20946u;        /* what ANY humidity rounds to */
    size_t n = framed(req, to_402, sizeof(to_402));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT16(TEST_ALPHA_X1K, rm.cfg.dil_alpha_x1000);
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.cal_air_frac_x1000);

    /* alpha_old = 1.000 is recoverable and must still work, or the guard has
     * eaten the ordinary path it exists to protect. */
    rm.cfg.dil_alpha_x1000 = 1000u;
    rm.cfg.cal_air_frac_x1000 = 20682u;
    n = framed(req, to_402, sizeof(to_402));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_UINT16_WITHIN(2u, 20840u, rm.cfg.cal_air_frac_x1000);
}

/* ---- CMD_RESULT and the calibrate/commit ordering, 2026-09-08 ---- */

static uint16_t read_cmd_result(o2p_regmap_t *r)
{
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    o2p_mb_handlers_t h = {.read = o2p_regmap_read, .write = o2p_regmap_write,
                           .ctx = r};
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x2A, 0x00, 0x01};
    size_t n = framed(req, rd, sizeof(rd));
    size_t rn = o2p_mb_dispatch(req, n, 3, &h, rsp);
    TEST_ASSERT_TRUE_MESSAGE(rn > 0, "CMD_RESULT must be readable over Modbus");
    TEST_ASSERT_EQUAL_HEX8(0x03, rsp[1]);
    return (uint16_t)((rsp[3] << 8) | rsp[4]);
}

static uint8_t write_cal_commit(o2p_regmap_t *r, bool cal, bool commit)
{
    uint8_t req[64], rsp[O2P_MB_MAX_ADU];
    o2p_mb_handlers_t h = {.read = o2p_regmap_read, .write = o2p_regmap_write,
                           .ctx = r};
    uint16_t cv = cal ? O2P_CAL_MAGIC : 0u;
    uint16_t mv = commit ? O2P_COMMIT_MAGIC : 0u;
    uint8_t w[] = {0x03, 0x10, 0x00, O2P_REG_CAL_TRIGGER & 0xFF, 0x00, 0x02, 0x04,
                   (uint8_t)(cv >> 8), (uint8_t)(cv & 0xFF),
                   (uint8_t)(mv >> 8), (uint8_t)(mv & 0xFF)};
    size_t n = framed(req, w, sizeof(w));
    size_t rn = o2p_mb_dispatch(req, n, 3, &h, rsp);
    TEST_ASSERT_TRUE(rn > 0);
    return rsp[1];
}


/* ------------------------------------------- the heater bench override */

static void arm_override(o2p_heater_cfg_t *cfg, uint16_t duty_x100)
{
    cfg->test_override = true;
    cfg->test_duty_x100 = duty_x100;
}

/* ------------------------- the PERSISTENT tip-temperature loop (0x0049/4A) */

/* Baseline for the persistent mode: a stored setpoint below the tip, with
 * consent given. Breaks exactly one thing per test, like hcfg_default(). */
static o2p_heater_cfg_t hcfg_tip_auto(void)
{
    o2p_heater_cfg_t c = hcfg_default();
    c.tip_sp_valid = true;
    c.tip_sp_c100 = 7800;              /* 78.00 C, inside the 80.00 bound */
    c.tip_consent = true;
    c.test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
    c.test_ki_x100 = O2P_HEATER_TEST_KI_X100_DEFAULT;
    return c;
}

static void test_persistent_tip_setpoint_needs_its_own_consent(void)
{
    /* THE ONE THAT MATTERS. rh_consent is TRUE here, so the probe is
     * authorised to heat autonomously - just not to chase a TEMPERATURE.
     *
     * The wrong behaviour is not "it heats": it is falling through to the RH
     * loop, which would drive the ring perfectly happily while the operator
     * watches a setpoint they believe is in force. An unevaluable
     * authorisation must refuse, not silently do something else. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.tip_consent = false;
    TEST_ASSERT_TRUE(cfg.rh_consent);   /* the RH loop WOULD be allowed */

    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE_MESSAGE((out.block & O2P_HB_NO_CONSENT) != 0u,
        "a stored setpoint without tip consent must raise NO_CONSENT");
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "it must not fall through to the RH loop and drive anyway");
}

static void test_persistent_tip_setpoint_drives_towards_its_target(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    /* Tip AND chamber together. On Rev A they are one thermal node, so a
     * fixture that moves only the tip invents a dT the hardware cannot produce
     * and trips the clamp this mode deliberately keeps live.
     *
     * THE EVIDENCE, stated accurately because it was first cited wrongly: the
     * 2026-09-04 CSV holds 0 % and 4 % duty only and peaks at 0.17 K; the wider
     * sweep in FAB-READINESS.md:261 reaches -0.37/-0.38/-0.14 K at 50/93/100 %,
     * and PILE-THERMAL-TEST.md:215 measured +0.220 K. So the honest figure is
     * UNDER 0.4 K across the measured duty range, not 0.17 K at every duty.
     * Still better than 10x margin to the 4 K clamp, so the conclusion holds -
     * but no run in the repo is fast enough to prove a ramp transient cannot
     * cross it. Corrected after review 2026-09-08. */
    in.t_tip_c100 = 7000;               /* 8 K short of the 78.00 setpoint */
    in.t_chamber_c100 = 6990;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "a tip below setpoint must ask for duty");

    /* Above the setpoint the same loop must ask for nothing. Monotonicity:
     * as the input crosses the target the verdict must not stay ON. */
    o2p_heater_ctl_reset(&st);
    in.t_tip_c100 = 7900;
    in.t_chamber_c100 = 7890;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "a tip above setpoint must not ask for heat");
}

static void test_persistent_tip_loop_does_not_need_humidity(void)
{
    /* The single interlock this mode suppresses. A temperature loop has no use
     * for RH, and refusing to hold a commanded temperature because the SHT45 is
     * in its de-creep window would be a refusal with no reason behind it.
     *
     * THE FIRST VERSION OF THIS TEST WAS DISHONEST, and a review caught it: it
     * set rh_valid = false while leaving the chamber valid, which is a state
     * production never reaches during the event the comment invoked. cycle_begin()
     * invalidates BOTH, so during a real de-creep pulse the controller would have
     * seen chamber_valid = false and refused on NO_CHAMBER while this test
     * happily passed.
     *
     * What makes the production state match this fixture is the cache bridge in
     * main.c, which restores the CHAMBER (and only the chamber) from the same
     * <= 45 s cache the oxygen path uses. So the pair below is the real pair:
     * bridged chamber -> drives; expired cache -> refuses. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    /* During the pulse, with the bridge supplying a chamber reading. */
    in.rh_valid = false;
    in.t_tip_c100 = 7000;
    in.t_chamber_c100 = 6990;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block,
        "the tip loop must clear NO_RH");
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);

    /* Past the bridge's age bound, or with a genuinely dead SHT45: the chamber
     * goes with the humidity and the loop must refuse. This is the half the
     * original test omitted, and it is the one that proves the bridge is a
     * BOUNDED substitution rather than a suppression. */
    o2p_heater_ctl_reset(&st);
    in.chamber_valid = false;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE_MESSAGE((out.block & O2P_HB_NO_CHAMBER) != 0u,
        "an expired bridge must refuse, not keep driving on a stale reference");
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
}

static void test_persistent_tip_loop_still_honours_the_dt_clamp(void)
{
    /* WHERE IT DIFFERS FROM THE BENCH OVERRIDE, and the difference is the
     * point. The override suppresses DT_LIMIT because exceeding the envelope
     * IS the experiment and an operator owns that. Nobody owns this one. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - 4000);   /* 40 K, 10x the envelope */
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE_MESSAGE((out.block & O2P_HB_DT_LIMIT) != 0u,
        "the persistent loop must NOT inherit the override's dT suppression");
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
}

static void test_persistent_tip_loop_still_needs_a_chamber_reading(void)
{
    /* Follows from the above: without a chamber temperature the dT envelope
     * cannot be enforced, and this mode keeps that envelope. Suppressing
     * NO_CHAMBER while keeping DT_LIMIT would be a clamp that cannot fire. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.chamber_valid = false;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
}

static void test_the_bench_override_outranks_a_stored_setpoint(void)
{
    /* Precedence. An armed override means an operator is at the bench NOW,
     * and their intent outranks anything a previous session left in flash. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.t_tip_c100 = 7000;              /* the stored loop would want duty */
    in.t_chamber_c100 = 6990;
    arm_override(&cfg, 1234u);         /* open loop, no test setpoint */

    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(1234u, out.duty_x100,
        "the override's open-loop duty must win over the stored setpoint");
}

static void test_a_v7_record_does_not_arm_a_temperature_loop(void)
{
    /* THE MIGRATION HAZARD THIS FIELD CREATED.
     *
     * v8 places tip_setpoint_c100 over v7's reserved3[2], where a v7 record
     * holds ZEROS - and zero is a legal setpoint meaning "hold 0.00 C", not
     * "off". A prefix copy would hand every upgraded probe an armed
     * temperature loop. The sentinel must survive instead.
     *
     * The same record also proves the case exists at all: before this change
     * config_migrate.c had no case 6 or 7, so a v7 record fell to
     * `default: return false` and the caller loaded FULL DEFAULTS - resetting
     * slave_addr, baud_code and parity_code, which is the "potted probe
     * disappears from its master" outcome read_record() exists to prevent. */
    test_cfg_v7_t v7;
    memset(&v7, 0, sizeof(v7));
    v7.cal_air_na = 123456;
    v7.rh_setpoint_x100 = 8500u;
    v7.dt_max_k_x100 = 400u;
    v7.heater_max_duty_x100 = 5000u;
    v7.heater_pwm_hz = 1000u;
    v7.cal_temp_c100 = 2500;
    v7.tempco_ppm_per_k = 800;
    v7.sht_pulse_interval_h = 24u;
    v7.heater_kp_x100 = 200u;
    v7.heater_ki_x100 = 10u;
    v7.assumed_p_hpa = 1013u;
    v7.cal_air_frac_x1000 = 20900u;
    v7.cal_p_hpa = 1013u;
    v7.dil_alpha_x1000 = 1000u;
    v7.slave_addr = 42u;                       /* moved off the default */
    v7.baud_code = O2P_BAUD_38400;
    v7.parity_code = O2P_PARITY_NONE;
    /* Consent that WAS given under v7, to prove it is not carried. */
    v7.heater_rh_consent = O2P_HEATER_RH_CONSENT_MAGIC;

    uint8_t rec[TEST_REC_BYTES];
    build_vn_record(rec, &v7, sizeof(v7), 7u, 99u);

    o2p_config_t out;
    uint32_t seq = 0u;
    memset(&out, 0xAA, sizeof(out));
    TEST_ASSERT_TRUE_MESSAGE(o2p_config_migrate(rec, sizeof(rec), &out, &seq),
        "a v7 record must migrate, not fall through to full defaults");
    TEST_ASSERT_EQUAL_UINT32(99u, seq);

    /* Reachability: the whole reason the migration exists. */
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(42u, out.slave_addr,
        "a migrated probe must keep answering at its own address");
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, out.baud_code);
    TEST_ASSERT_EQUAL_UINT8(O2P_PARITY_NONE, out.parity_code);

    /* The new field lands OFF, not on 0.00 C. */
    TEST_ASSERT_EQUAL_HEX16_MESSAGE((uint16_t)O2P_I16_INVALID,
        (uint16_t)out.tip_setpoint_c100,
        "a v7 record's zeros must not become a 0.00 C setpoint");
    TEST_ASSERT_EQUAL_UINT16(0u, out.heater_tip_consent);
    /* Neither consent is ever carried. */
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.heater_rh_consent,
        "consent must never survive a migration");
    /* The calibration survives: nothing about its meaning changed in v8. */
    TEST_ASSERT_EQUAL_INT32(123456, out.cal_air_na);
}

static void test_tip_setpoint_and_consent_are_bounded_on_the_wire(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];

    /* Above the 80.00 C bound. */
    const uint8_t hot[] = {0x03, 0x06, 0x00, 0x49, 0x1F, 0x90};   /* 81.44 C */
    size_t n = framed(req, hot, sizeof(hot));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);

    /* Negative, and not the sentinel: a units or sign error, refused rather
     * than quietly meaning "never heat". */
    const uint8_t neg[] = {0x03, 0x06, 0x00, 0x49, 0xFF, 0x9C};   /* -1.00 C */
    n = framed(req, neg, sizeof(neg));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);

    /* The sentinel itself is how the mode is turned off, so it must pass. */
    const uint8_t off[] = {0x03, 0x06, 0x00, 0x49, 0x80, 0x00};
    n = framed(req, off, sizeof(off));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x06, rsp[1]);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID,
                            (uint16_t)rm.cfg.tip_setpoint_c100);

    /* 80.00 C exactly - the stated experiment - must be commandable. */
    const uint8_t ok[] = {0x03, 0x06, 0x00, 0x49, 0x1F, 0x40};
    n = framed(req, ok, sizeof(ok));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x06, rsp[1]);
    TEST_ASSERT_EQUAL_INT16(8000, rm.cfg.tip_setpoint_c100);

    /* Consent takes its magic and nothing else - not even the RH one. */
    const uint8_t wrong[] = {0x03, 0x06, 0x00, 0x4A, 0x9C, 0x07};
    n = framed(req, wrong, sizeof(wrong));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(O2P_MB_EX_ILLEGAL_VALUE, rsp[2],
        "the RH consent magic must not authorise the temperature loop");
    TEST_ASSERT_EQUAL_UINT16(0u, rm.cfg.heater_tip_consent);

    const uint8_t right[] = {0x03, 0x06, 0x00, 0x4A, 0x71, 0xC0};
    n = framed(req, right, sizeof(right));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(0x06, rsp[1]);
    TEST_ASSERT_EQUAL_HEX16(O2P_HEATER_TIP_CONSENT_MAGIC,
                            rm.cfg.heater_tip_consent);
}

static void test_override_drives_open_loop_with_no_humidity(void)
{
    /* The reason the mode exists. The RH loop refuses to drive without a
     * controlled quantity, which is correct for a dew-point regulator and
     * useless for characterising the plant that regulator was written for. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.rh_valid = false;
    in.chamber_valid = false;
    arm_override(&cfg, 4000u);

    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block,
        "override must clear NO_RH and NO_CHAMBER");
    TEST_ASSERT_EQUAL_UINT16(4000u, out.duty_x100);
}

static void test_override_ignores_the_dt_clamp(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    /* 40 K above chamber: ten times the configured envelope. */
    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - 4000);
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_DT_LIMIT) != 0u);

    arm_override(&cfg, 2500u);
    o2p_heater_ctl_step(&st, &cfg, &in, 1u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block);
    TEST_ASSERT_EQUAL_UINT16(2500u, out.duty_x100);
}

static void test_disarming_does_not_inherit_a_stale_dt_clamp(void)
{
    /* The clamp latches with hysteresis. If the override merely SKIPPED the
     * test instead of dropping the latch, the PI loop would come back still
     * clamped for a dT it had not looked at since. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.t_chamber_c100 = (int16_t)(in.t_tip_c100 - 4000);
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE(st.dt_clamped);

    arm_override(&cfg, 1000u);
    o2p_heater_ctl_step(&st, &cfg, &in, 1u, &out);
    TEST_ASSERT_FALSE(st.dt_clamped);

    /* Back to the loop, with a dT that is now inside the envelope. */
    cfg.test_override = false;
    in.t_chamber_c100 = in.t_tip_c100;
    o2p_heater_ctl_step(&st, &cfg, &in, 2u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block & O2P_HB_DT_LIMIT,
        "a dropped clamp must not reappear on the first unclamped cycle");
}

static void test_override_is_clamped_by_max_duty(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.max_duty_x100 = 1500u;
    arm_override(&cfg, 10000u);
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(1500u, out.duty_x100);
}

static void test_override_does_not_bypass_the_hardware_interlocks(void)
{
    /* The list that makes this mode acceptable at all. Each is broken alone,
     * from an otherwise healthy input, with the override armed at full duty:
     * every one must still force zero. */
    struct { const char *name; int which; uint16_t bit; } cases[] = {
        { "safety",        0, O2P_HB_SAFETY        },
        { "no tip",        1, O2P_HB_NO_TIP        },
        { "tip limit",     2, O2P_HB_TIP_LIMIT     },
        { "supply",        3, O2P_HB_SUPPLY        },
        { "pin integrity", 4, O2P_HB_PIN_INTEGRITY },
        { "not compiled",  5, O2P_HB_NOT_COMPILED  },
        { "config off",    6, O2P_HB_CONFIG_OFF    },
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t cfg = hcfg_default();
        o2p_heater_in_t in = hin_healthy();
        o2p_heater_out_t out;
        arm_override(&cfg, 10000u);

        switch (cases[i].which) {
        case 0: in.safety_armed = false; break;
        case 1: in.tip_valid = false; break;
        case 2: in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100; break;
        case 3: in.supply_ok = false; break;
        case 4: in.pin_integrity_ok = false; break;
        case 5: in.drive_possible = false; break;
        case 6: cfg.max_duty_x100 = 0u; break;
        default: break;
        }
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100, cases[i].name);
        TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].bit) != 0u,
                                 cases[i].name);
    }
}

static void test_override_cannot_clear_a_latched_runaway(void)
{
    /* Suspending ACCUMULATION is the concession; clearing the LATCH would
     * make a magic word over Modbus the way to re-arm 1 W against a membrane
     * after the firmware concluded the FET was stuck on. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    st.runaway_latched = true;
    arm_override(&cfg, 5000u);
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) != 0u);
    TEST_ASSERT_TRUE(st.runaway_latched);
}

static void test_override_does_not_latch_runaway_on_external_heat(void)
{
    /* The 80 C bath: tip tens of kelvin above the die at zero commanded duty
     * is exactly the die-referenced runaway signature, and latching there
     * would disable the heater for the rest of the run. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    arm_override(&cfg, 0u);                 /* armed, commanding nothing */
    in.die_valid = true;
    in.t_tip_c100 = 8000 - 100;             /* just under the tip clamp */
    in.t_die_c100 = 2800;                   /* 52 K below: bath, not a FET */

    for (uint32_t t = 0u; t <= O2P_HEATER_RUNAWAY_WINDOW_S + 5u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "external heat under an armed override must not latch runaway");

    /* And the detector comes straight back when the override is dropped. */
    cfg.test_override = false;
    cfg.test_duty_x100 = 0u;
    in.rh_x100 = 8500u;                     /* at setpoint: duty stays idle */
    for (uint32_t t = 100u; t <= 100u + O2P_HEATER_RUNAWAY_WINDOW_S + 5u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "dropping the override must restore runaway detection");
}

static void test_heater_test_registers_are_volatile_and_magic_gated(void)
{
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    uint16_t v[2];

    /* Cleared by init: the mode must never come up armed after a reset. */
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&r, O2P_REG_HTEST_BASE, 2u, v));
    TEST_ASSERT_EQUAL_UINT16(0u, v[0]);
    TEST_ASSERT_EQUAL_UINT16(0u, v[1]);

    /* A plain 1 does not arm. */
    uint16_t w = 1u;
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&r, O2P_REG_HEATER_TEST_ARM, 1u, &w));
    TEST_ASSERT_FALSE(r.heater_test_armed);

    /* The magic does, and ARM reads back as a flag, not as the token. */
    w = O2P_HEATER_TEST_MAGIC;
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&r, O2P_REG_HEATER_TEST_ARM, 1u, &w));
    TEST_ASSERT_TRUE(r.heater_test_armed);
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&r, O2P_REG_HEATER_TEST_ARM, 1u, v));
    TEST_ASSERT_EQUAL_UINT16(1u, v[0]);

    /* Anything else disarms - switching off must never be refused. */
    w = 0x1234u;
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&r, O2P_REG_HEATER_TEST_ARM, 1u, &w));
    TEST_ASSERT_FALSE(r.heater_test_armed);
}

static void test_a_rejected_heater_test_frame_changes_nothing(void)
{
    o2p_regmap_t r;
    o2p_regmap_init(&r);

    /* Arm and set a duty, so there is prior state to preserve. */
    uint16_t ok[2] = { O2P_HEATER_TEST_MAGIC, 3000u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&r, O2P_REG_HTEST_BASE, 2u, ok));
    TEST_ASSERT_TRUE(r.heater_test_armed);
    TEST_ASSERT_EQUAL_UINT16(3000u, r.heater_test_duty_x100);

    /* One frame that disarms AND names an impossible duty. All-or-nothing:
     * the operator asked for one state and must not be left in another. */
    uint16_t bad[2] = { 0u, 10001u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&r, O2P_REG_HTEST_BASE, 2u, bad));
    TEST_ASSERT_TRUE(r.heater_test_armed);
    TEST_ASSERT_EQUAL_UINT16(3000u, r.heater_test_duty_x100);
}

static void test_the_heater_test_block_is_not_part_of_the_config(void)
{
    /* It has no flash-backed home on purpose. Two consequences a reader
     * should be able to see asserted: it does not move the config CRC, and a
     * read cannot span from the config block into it. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    uint16_t crc_before = o2p_config_crc(&r.cfg);

    uint16_t w[2] = { O2P_HEATER_TEST_MAGIC, 7500u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&r, O2P_REG_HTEST_BASE, 2u, w));
    TEST_ASSERT_EQUAL_UINT16(crc_before, o2p_config_crc(&r.cfg));

    uint16_t out[32];
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
        o2p_regmap_read(&r, O2P_REG_CONFIG_BASE, O2P_REG_CONFIG_COUNT + 2u, out));
}

static void test_the_heater_test_block_does_not_shadow_the_updater(void)
{
    /* Written because it happened. The block was first placed at 0x0050,
     * which is O2P_REG_UPDATE_BASE - and because the dispatcher tries the
     * fixed blocks before routing to the updater, UPD_STATUS would have read
     * back as an arm flag and OTA would have stopped working on a probe with
     * no wired bridge. An address is only free if it is free in update.h too. */
    TEST_ASSERT_TRUE_MESSAGE(
        O2P_REG_HTEST_BASE + O2P_REG_HTEST_COUNT <= O2P_REG_UPDATE_BASE ||
        O2P_REG_HTEST_BASE >= O2P_REG_UPDATE_BASE + O2P_REG_UPDATE_COUNT,
        "heater test block overlaps the update block");
    TEST_ASSERT_TRUE_MESSAGE(
        O2P_REG_HTEST_BASE + O2P_REG_HTEST_COUNT <= O2P_REG_UPDDATA_BASE ||
        O2P_REG_HTEST_BASE >= O2P_REG_UPDDATA_BASE + O2P_REG_UPDDATA_COUNT,
        "heater test block overlaps the update data window");
    TEST_ASSERT_TRUE_MESSAGE(
        O2P_REG_HTEST_BASE >= O2P_REG_CONFIG_BASE + O2P_REG_CONFIG_COUNT,
        "heater test block overlaps the config block");
}

/* ------------------------------- the tip-temperature setpoint mode */

/* A crude first-order thermal plant, only good enough to show the loop
 * converges: the tip approaches (ambient + gain * duty) with time constant
 * TAU. Numbers are a plausible ~1 W ring, not a measured plant. */
typedef struct { float t_c100; } fake_tip_t;
static void plant_step(fake_tip_t *pl, uint16_t duty_x100)
{
    const float ambient = 2500.0f;      /* 25.00 C */
    const float k = 0.60f;              /* 100 % duty -> +60.00 K steady */
    const float tau = 20.0f;            /* seconds */
    const float target = ambient + k * (float)duty_x100;
    pl->t_c100 += (target - pl->t_c100) / tau;
}

static void test_tip_setpoint_converges_and_holds(void)
{
    /* The whole reason this mode exists: a PLATEAU, not a sawtooth bouncing
     * off the absolute clamp. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.test_override = true;
    cfg.test_tip_sp_valid = true;
    cfg.test_tip_sp_c100 = 7800;        /* 78.00 C, a kelvin under the clamp */
    cfg.test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
    cfg.test_ki_x100 = O2P_HEATER_TEST_KI_X100_DEFAULT;

    fake_tip_t pl = { 2500.0f };
    for (uint32_t t = 0; t < 3000u; t++) {
        in.t_tip_c100 = (int16_t)pl.t_c100;
        in.t_chamber_c100 = 2500;
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
        plant_step(&pl, out.duty_x100);
    }
    TEST_ASSERT_INT16_WITHIN_MESSAGE(50, 7800, (int16_t)pl.t_c100,
        "the tip loop must settle within 0.5 K of its setpoint");
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block & O2P_HB_TIP_LIMIT,
        "a setpoint below the clamp must never reach the clamp");
    TEST_ASSERT_FALSE_MESSAGE(st.tip_clamped,
        "the absolute clamp must stay a backstop, not the control mechanism");
}

static void test_tip_setpoint_asks_for_more_duty_when_colder(void)
{
    o2p_heater_state_t st;
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;
    cfg.test_override = true;
    cfg.test_tip_sp_valid = true;
    cfg.test_tip_sp_c100 = 7000;
    cfg.test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
    cfg.test_ki_x100 = 0u;              /* proportional only, so it is a pure
                                         * function of the current error */

    uint16_t prev = 0xFFFFu;
    for (int16_t tip = 6900; tip >= 6000; tip = (int16_t)(tip - 100)) {
        o2p_heater_ctl_reset(&st);
        in.t_tip_c100 = tip;
        in.t_chamber_c100 = 2500;
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 >= prev || prev == 0xFFFFu,
                                 "duty must not fall as the tip gets colder");
        prev = out.duty_x100;
    }
    /* And above the setpoint it asks for nothing at all. */
    o2p_heater_ctl_reset(&st);
    in.t_tip_c100 = 7100;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
}

static void test_the_integrator_does_not_leak_between_loops(void)
{
    /* An integral wound up in 0.01 %RH means nothing in 0.01 K. Carrying it
     * across a mode switch would slam the output on the first cycle. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    /* Wind the RH loop up hard. */
    in.rh_x100 = 10000u;
    for (uint32_t t = 0; t < 60u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.integ > 0.0f, "the RH loop should have wound up");

    /* Switch to the tip loop with the tip ALREADY above setpoint: a correct
     * loop asks for zero, a leaked integrator asks for duty. */
    cfg.test_override = true;
    cfg.test_tip_sp_valid = true;
    cfg.test_tip_sp_c100 = 4000;
    cfg.test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
    cfg.test_ki_x100 = O2P_HEATER_TEST_KI_X100_DEFAULT;
    in.t_tip_c100 = 5000;               /* 10 K hotter than asked */
    o2p_heater_ctl_step(&st, &cfg, &in, 100u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "a tip already above setpoint must command zero on the first cycle");
    TEST_ASSERT_EQUAL_UINT8(O2P_HEATER_MODE_TIP, st.last_mode);

    /* And back again, with the chamber already dry. */
    cfg.test_override = false;
    cfg.test_tip_sp_valid = false;
    in.rh_x100 = 1000u;
    o2p_heater_ctl_step(&st, &cfg, &in, 101u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "a dry chamber must command zero on the first cycle back");
}

static void test_tip_mode_still_obeys_every_hardware_interlock(void)
{
    /* The setpoint loop is not a second way in. Same list as the open-loop
     * override, with a setpoint far above the tip so the loop wants full duty. */
    struct { const char *name; int which; uint16_t bit; } cases[] = {
        { "safety",        0, O2P_HB_SAFETY        },
        { "no tip",        1, O2P_HB_NO_TIP        },
        { "tip limit",     2, O2P_HB_TIP_LIMIT     },
        { "supply",        3, O2P_HB_SUPPLY        },
        { "pin integrity", 4, O2P_HB_PIN_INTEGRITY },
        { "not compiled",  5, O2P_HB_NOT_COMPILED  },
        { "config off",    6, O2P_HB_CONFIG_OFF    },
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t cfg = hcfg_default();
        o2p_heater_in_t in = hin_healthy();
        o2p_heater_out_t out;
        cfg.test_override = true;
        cfg.test_tip_sp_valid = true;
        cfg.test_tip_sp_c100 = O2P_HEATER_TEST_SP_MAX_C100;
        cfg.test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
        cfg.test_ki_x100 = O2P_HEATER_TEST_KI_X100_DEFAULT;
        in.t_tip_c100 = 2500;

        switch (cases[i].which) {
        case 0: in.safety_armed = false; break;
        case 1: in.tip_valid = false; break;
        case 2: in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100; break;
        case 3: in.supply_ok = false; break;
        case 4: in.pin_integrity_ok = false; break;
        case 5: in.drive_possible = false; break;
        case 6: cfg.max_duty_x100 = 0u; break;
        default: break;
        }
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100, cases[i].name);
        TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].bit) != 0u,
                                 cases[i].name);
    }
}

static void test_the_setpoint_must_stay_below_the_clamp(void)
{
    /* A setpoint at or above the absolute clamp would put the loop and the
     * protection device in a fight, which is the arrangement this mode was
     * added to get rid of. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    TEST_ASSERT_TRUE(O2P_HEATER_TEST_SP_MAX_C100 < O2P_HEATER_TIP_LIMIT_C100);

    uint16_t v = (uint16_t)(O2P_HEATER_TEST_SP_MAX_C100 + 1);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
        o2p_regmap_write(&r, O2P_REG_HEATER_TEST_TIP_SP, 1u, &v));

    v = (uint16_t)O2P_HEATER_TIP_LIMIT_C100;
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
        o2p_regmap_write(&r, O2P_REG_HEATER_TEST_TIP_SP, 1u, &v));

    /* A negative that is not the sentinel is a sign or units error, and must
     * not pass as a loop that simply never asks for heat. */
    v = (uint16_t)(int16_t)-100;
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
        o2p_regmap_write(&r, O2P_REG_HEATER_TEST_TIP_SP, 1u, &v));

    /* The legal top of the range, and the sentinel, both take. */
    v = (uint16_t)O2P_HEATER_TEST_SP_MAX_C100;
    TEST_ASSERT_EQUAL_HEX8(0u,
        o2p_regmap_write(&r, O2P_REG_HEATER_TEST_TIP_SP, 1u, &v));
    TEST_ASSERT_EQUAL_INT16(O2P_HEATER_TEST_SP_MAX_C100, r.heater_test_tip_sp_c100);

    v = (uint16_t)O2P_I16_INVALID;
    TEST_ASSERT_EQUAL_HEX8(0u,
        o2p_regmap_write(&r, O2P_REG_HEATER_TEST_TIP_SP, 1u, &v));
    TEST_ASSERT_EQUAL_INT16(O2P_I16_INVALID, r.heater_test_tip_sp_c100);
}

static void test_the_test_block_comes_up_meaning_open_loop(void)
{
    /* memset would leave the setpoint at 0, which is a real temperature, and
     * the gains at 0, which looks like a broken loop rather than no loop. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    TEST_ASSERT_EQUAL_INT16_MESSAGE(O2P_I16_INVALID, r.heater_test_tip_sp_c100,
        "a fresh map must mean 'no temperature target', not 0.00 C");
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_TEST_KP_X100_DEFAULT, r.heater_test_kp_x100);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_TEST_KI_X100_DEFAULT, r.heater_test_ki_x100);
    TEST_ASSERT_FALSE(r.heater_test_armed);

    uint16_t v[5];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&r, O2P_REG_HTEST_BASE, 5u, v));
    TEST_ASSERT_EQUAL_UINT16((uint16_t)O2P_I16_INVALID, v[2]);
}

static void test_a_rejected_setpoint_frame_changes_no_register(void)
{
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    uint16_t ok[5] = { O2P_HEATER_TEST_MAGIC, 2000u, 7000u, 400u, 20u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&r, O2P_REG_HTEST_BASE, 5u, ok));

    /* Disarm plus an illegal setpoint in one frame: all-or-nothing. */
    uint16_t bad[5] = { 0u, 3000u, 9000u, 111u, 22u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
        o2p_regmap_write(&r, O2P_REG_HTEST_BASE, 5u, bad));
    TEST_ASSERT_TRUE(r.heater_test_armed);
    TEST_ASSERT_EQUAL_UINT16(2000u, r.heater_test_duty_x100);
    TEST_ASSERT_EQUAL_INT16(7000, r.heater_test_tip_sp_c100);
    TEST_ASSERT_EQUAL_UINT16(400u, r.heater_test_kp_x100);
    TEST_ASSERT_EQUAL_UINT16(20u, r.heater_test_ki_x100);
}

static void test_zeroing_the_gains_stops_the_heater(void)
{
    /* The defect: the integrator was cleared only on a MODE change, and both
     * gains accept zero. Wind the loop up, then write kp = ki = 0 - p is zero
     * and nothing further accumulates, so the output stayed parked at the
     * stale integral and "both gains to zero" produced sustained duty. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    in.rh_x100 = 10000u;                 /* saturated: wind it up */
    for (unsigned i = 0; i < 120u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u, "the loop should be driving");
    TEST_ASSERT_TRUE_MESSAGE(st.integ > 0.0f, "and carrying an integral");

    cfg.kp_x100 = 0u;
    cfg.ki_x100 = 0u;
    o2p_heater_ctl_step(&st, &cfg, &in, 200u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "zero gains must mean zero output, not the last integral");
}

static void test_p_only_tuning_stays_legal(void)
{
    /* The fix clears the integrator whenever ki is zero, so check it did not
     * outlaw a P-only controller - a reasonable thing to want on a plant
     * nobody has characterised. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.ki_x100 = 0u;
    cfg.kp_x100 = 200u;
    in.rh_x100 = (uint16_t)(cfg.setpoint_x100 + 1000u);   /* 10 %RH above */
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u, "P-only must still drive");
    TEST_ASSERT_EQUAL_FLOAT(0.0f, st.integ);
}

static void test_rearming_does_not_inherit_the_previous_integral(void)
{
    /* A disarm and re-arm served between two 1 Hz decisions changes neither
     * the mode tag nor any input, so the loop resumed a fresh bench run
     * carrying the previous run's wind-up. The session counter is what makes
     * that edge visible. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.test_override = true;
    cfg.test_tip_sp_valid = true;
    cfg.test_tip_sp_c100 = 6000;         /* tip loop, far above ambient */
    cfg.test_kp_x100 = 50u;
    cfg.test_ki_x100 = 10u;
    cfg.session = 1u;
    for (unsigned i = 0; i < 60u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.integ > 0.0f, "the tip loop should wind up");

    /* Disarmed and re-armed between cycles: same mode, new session. */
    cfg.session = 2u;
    o2p_heater_ctl_step(&st, &cfg, &in, 100u, &out);

    /* The step RESETS and then integrates once, so the integral is not zero
     * afterwards - it is exactly what a controller starting from nothing
     * would hold. Compare against that rather than against zero, which is why
     * this runs a second, freshly reset controller through the identical
     * step: it asserts "started from zero wind-up" instead of asserting an
     * implementation detail about ordering. */
    o2p_heater_state_t fresh;
    o2p_heater_ctl_reset(&fresh);
    o2p_heater_out_t fout;
    o2p_heater_ctl_step(&fresh, &cfg, &in, 100u, &fout);
    TEST_ASSERT_EQUAL_FLOAT_MESSAGE(fresh.integ, st.integ,
        "a new override session must start from zero wind-up");
    TEST_ASSERT_EQUAL_UINT16(fout.duty_x100, out.duty_x100);
}

static void test_arming_cannot_erase_runaway_evidence(void)
{
    /* The abuse: the detector used to clear its accumulated evidence on every
     * armed sample, and the caller runs at 1 Hz against a 60 s window - so one
     * armed sample every 60 s held the counter at zero forever while a stuck
     * FET went on heating. Arming may now FREEZE the detector; it may not wipe
     * it. Alternating arm/disarm therefore only delays the latch. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.max_duty_x100 = 0u;          /* CONFIG_OFF: duty is zero throughout */
    in.die_valid = true;
    in.t_tip_c100 = 6000;
    in.t_die_c100 = 2800;            /* 32 K over the die: uncommanded heat */

    /* Alternate armed / disarmed every cycle for well over two windows. */
    for (uint32_t t = 0u; t < (O2P_HEATER_RUNAWAY_WINDOW_S * 3u); t++) {
        cfg.test_override = (t % 2u) == 0u;
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "alternating arm/disarm must not hold the detector at zero forever");
}

static void test_a_continuously_armed_override_still_suppresses(void)
{
    /* The residual, asserted so it stays a KNOWN limit rather than becoming a
     * surprise: while armed we cannot tell commanded heat, or a hot bath, from
     * a stuck FET, so accumulation stops. This is why the mode is volatile,
     * magic-gated and documented as attended. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.test_override = true;
    cfg.test_duty_x100 = 0u;
    in.die_valid = true;
    in.t_tip_c100 = 6000;
    in.t_die_c100 = 2800;
    for (uint32_t t = 0u; t < (O2P_HEATER_RUNAWAY_WINDOW_S * 3u); t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "an external bath under an armed override must not latch runaway");
}

static void test_autonomous_heating_needs_consent(void)
{
    /* The guarantee that O2P_HEATER_ENABLE=0 used to provide for free. With
     * the ring compiled in, a nonzero stored duty maximum was on its own
     * enough to start the RH loop on a buried probe with nobody present. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    /* Everything healthy, a generous duty maximum, humidity well above
     * setpoint - the loop wants to heat - but no consent. */
    cfg.rh_consent = false;
    cfg.max_duty_x100 = 10000u;
    in.rh_x100 = 9900u;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "a stored duty maximum must not by itself start autonomous heating");
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CONSENT) != 0u);

    /* With consent, the same inputs drive. */
    cfg.rh_consent = true;
    o2p_heater_ctl_step(&st, &cfg, &in, 1u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);
}

static void test_the_bench_override_does_not_need_consent(void)
{
    /* Consent gates UNATTENDED heating. Arming the override is itself the
     * authorisation, it needs its own magic, and it cannot survive a reset -
     * so requiring both would be ceremony, not safety. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    cfg.rh_consent = false;
    cfg.test_override = true;
    cfg.test_duty_x100 = 2500u;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block & O2P_HB_NO_CONSENT,
        "NO_CONSENT must never be raised against the attended override");
    TEST_ASSERT_EQUAL_UINT16(2500u, out.duty_x100);
}

static void test_consent_is_never_carried_across_a_migration(void)
{
    /* The failure this whole field exists to prevent: an upgrade landing on a
     * probe whose old record said "heat hard", and heating. An older record
     * was written by firmware that could not express consent, so there is no
     * honest value to carry - only zero. */
    o2p_config_t c;
    o2p_config_defaults(&c);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, c.heater_rh_consent,
        "a probe that was never told to heat by itself must not");

    /* And only the two legal values may ever be stored, so a corrupt image
     * cannot land on something that reads as consent. */
    c.heater_rh_consent = O2P_HEATER_RH_CONSENT_MAGIC;
    TEST_ASSERT_TRUE(o2p_config_valid(&c));
    c.heater_rh_consent = 1u;
    TEST_ASSERT_FALSE(o2p_config_valid(&c));
    c.heater_rh_consent = (uint16_t)(O2P_HEATER_RH_CONSENT_MAGIC ^ 0x0001u);
    TEST_ASSERT_FALSE_MESSAGE(o2p_config_valid(&c),
        "one flipped bit in the magic must not read as consent");
}

static void test_the_tip_thresholds_form_a_ladder(void)
{
    /* Host copy of the assert in main.c. main.c is not host-buildable, and
     * this ordering is the whole protection argument: setpoint < firmware
     * clamp < hardware cutoff. The 85.00 C figure is the TMP117 therm-mode
     * threshold main.c programs (O2P_TIP_LIMIT_C100). */
    TEST_ASSERT_TRUE_MESSAGE(
        O2P_HEATER_TEST_SP_MAX_C100 < O2P_HEATER_TIP_LIMIT_C100,
        "the clamp must sit above every commandable setpoint");
    TEST_ASSERT_TRUE_MESSAGE(O2P_HEATER_TIP_LIMIT_C100 < 8500,
        "firmware must back off before the hardware cutoff");
    TEST_ASSERT_TRUE(O2P_HEATER_TIP_RELEASE_C100 < O2P_HEATER_TIP_LIMIT_C100);

    /* The experiment this was raised for: 80.00 C must be commandable, so a
     * tip run and an external 80 C bath compare the same temperature. */
    TEST_ASSERT_TRUE_MESSAGE(O2P_HEATER_TEST_SP_MAX_C100 >= 8000,
        "80.00 C must be a legal setpoint or the internal and external legs "
        "of the harsh-environment test are at different temperatures");
}

static void test_cmd_result_reads_none_before_any_command(void)
{
    /* An untouched result register that read OK would be worse than none: a
     * commissioning script polling it would pass before it ever wrote a
     * trigger. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    uint16_t v = read_cmd_result(&r);
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_NONE, O2P_CMD_RESULT_CAL(v));
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_NONE, O2P_CMD_RESULT_COMMIT(v));
}

static void test_calibrate_and_save_defers_the_commit(void)
{
    /* The whole point: nothing reaches flash before the air point is taken.
     * Previously both flags were raised together and the main loop serviced
     * commit_pending as soon as the reply was off the wire, storing the
     * PRE-calibration image while the master had a success for both. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    TEST_ASSERT_EQUAL_HEX8(0x10, write_cal_commit(&r, true, true));

    TEST_ASSERT_TRUE(r.cal_requested);
    TEST_ASSERT_TRUE(r.commit_after_cal);
    TEST_ASSERT_FALSE_MESSAGE(r.commit_pending,
        "a co-requested commit must not be armed before the calibration");

    uint16_t v = read_cmd_result(&r);
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_PENDING, O2P_CMD_RESULT_CAL(v));
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_PENDING, O2P_CMD_RESULT_COMMIT(v));
}

static void test_a_later_commit_frame_also_waits_for_a_pending_cal(void)
{
    /* The DOCUMENTED procedure is two frames - write CAL_TRIGGER, then
     * COMMIT - so fixing only the one-frame case would have left the
     * documented path storing the pre-calibration image. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    write_cal_commit(&r, true, false);
    TEST_ASSERT_TRUE(r.cal_requested);

    write_cal_commit(&r, false, true);
    TEST_ASSERT_TRUE(r.commit_after_cal);
    TEST_ASSERT_FALSE(r.commit_pending);
}

static void test_a_commit_on_its_own_is_not_deferred(void)
{
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    write_cal_commit(&r, false, true);
    TEST_ASSERT_TRUE(r.commit_pending);
    TEST_ASSERT_FALSE(r.commit_after_cal);
}

static void test_a_commit_outcome_never_clobbers_the_cal_outcome(void)
{
    /* Both halves share one 16-bit word, so a packed write is exactly how a
     * commit result would overwrite a calibration still outstanding - and a
     * master polling for "not PENDING" would stop one command early. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    o2p_regmap_set_cal_result(&r, O2P_CMD_PENDING);
    o2p_regmap_set_commit_result(&r, O2P_CMD_FAILED);

    uint16_t v = read_cmd_result(&r);
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_PENDING, O2P_CMD_RESULT_CAL(v));
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_FAILED, O2P_CMD_RESULT_COMMIT(v));

    o2p_regmap_set_cal_result(&r, O2P_CMD_OK);
    v = read_cmd_result(&r);
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_OK, O2P_CMD_RESULT_CAL(v));
    TEST_ASSERT_EQUAL_UINT8(O2P_CMD_FAILED, O2P_CMD_RESULT_COMMIT(v));
}

static void test_cmd_result_sits_outside_the_published_decoder_block(void)
{
    /* 0x0022..0x0029 are parsed by the ChirpStack decoder as T_DIE,
     * FAULTS_EVER, ADS_FAIL_COUNT, the cell buffers and BUILD_ID. A status
     * word inside that range would decode as a die temperature - a plausible
     * number from the wrong register. */
    TEST_ASSERT_TRUE(O2P_REG_CMD_RESULT > O2P_REG_BUILD_ID_LO);
    TEST_ASSERT_EQUAL_HEX16(0x002A, O2P_REG_CMD_RESULT);
    /* And it must be inside the block a single FC03 can reach. */
    TEST_ASSERT_TRUE(O2P_REG_CMD_RESULT <
                     O2P_REG_DIAG_BASE + O2P_REG_DIAG_COUNT);
}

static void test_tmp117_rejects_a_reading_outside_the_rating(void)
{
    /* The old bound was (c100 > 32767 || c100 < -32768) on a value whose
     * image is -25600..25599 - tautologically false, so every word the
     * register could hold was accepted as a temperature. */
    TEST_ASSERT_TRUE(O2P_TMP117_MAX_C100 < 25599);
    TEST_ASSERT_TRUE(O2P_TMP117_MIN_C100 > -25600);
}

/* ---- cell zero point, 2026-09-08 ---- */

typedef struct {
    int32_t  cal_air_na;
    uint16_t rh_setpoint_x100;
    uint16_t dt_max_k_x100;
    uint16_t heater_max_duty_x100;
    uint16_t heater_pwm_hz;
    int16_t  cal_temp_c100;
    int16_t  tempco_ppm_per_k;
    uint16_t sht_pulse_interval_h;
    uint16_t heater_kp_x100;
    uint16_t heater_ki_x100;
    uint16_t assumed_p_hpa;
    uint16_t cal_air_frac_x1000;
    uint16_t cal_p_hpa;
    uint8_t  slave_addr;
    uint8_t  baud_code;
    uint8_t  parity_code;
    uint8_t  reserved[1];
    uint16_t dil_alpha_x1000;
    uint8_t  reserved2[2];
} test_cfg_v5_t;

static void build_v5_record(uint8_t rec[TEST_REC_BYTES],
                            const test_cfg_v5_t *cfg, uint32_t seq)
{
    memset(rec, 0, TEST_REC_BYTES);
    uint32_t magic = TEST_CFG_MAGIC, ver = 5u;
    memcpy(rec + 0, &magic, 4);
    memcpy(rec + 4, &ver, 4);
    memcpy(rec + 8, &seq, 4);
    memcpy(rec + 12, cfg, sizeof(*cfg));
    uint16_t crc = o2p_mb_crc16(rec, 12u + sizeof(*cfg));
    memcpy(rec + 12u + sizeof(*cfg), &crc, 2);
}

static o2p_cal_t zero_test_cal(int32_t air_na, int32_t zero_na)
{
    o2p_cal_t c;
    memset(&c, 0, sizeof(c));
    c.cal_air_na = air_na;
    c.cal_temp_c100 = 2000;
    c.tempco_per_k = 0.0f;
    c.air_frac = 0.2095f;
    c.cal_p_hpa = 0.0f;
    c.dil_alpha = 1.0f;
    c.zero_na = zero_na;
    return c;
}

static void test_zero_point_is_an_offset_not_a_slope(void)
{
    /* THE REASON THE FIELD EXISTS. The law is I = I0 + K*ln(1/(1-C)), so a
     * dark current is an OFFSET. Folding it into K instead - which is what
     * storing a raw air point and never subtracting did - spreads it across
     * the range as a gain error, smallest at the air point and largest where
     * compost control actually acts.
     *
     * Build a cell with a real 2000 nA zero, calibrated in air. Ask what a
     * current corresponding to a true 5 %vol reads, with and without the
     * subtraction. */
    const int32_t zero = 2000;
    const int32_t air_raw = 100000;          /* including the zero */
    o2p_cal_t good = zero_test_cal(air_raw, zero);

    /* The current this cell genuinely produces at 5 %vol: I0 + K*ln(...) with
     * K built from the NET air current. */
    float k = (float)(air_raw - zero) / logf(1.0f / (1.0f - 0.2095f));
    float i_5pct = (float)zero + k * logf(1.0f / (1.0f - 0.05f));

    float c_good = 0.0f;
    TEST_ASSERT_EQUAL_INT(O2P_OK,
        o2p_fraction_from_current(&good, (int32_t)(i_5pct + 0.5f), 2000, &c_good));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, 0.05f, c_good);

    /* Now the old behaviour: same cell, same current, zero not subtracted. */
    o2p_cal_t blind = zero_test_cal(air_raw, 0);
    float c_blind = 0.0f;
    TEST_ASSERT_EQUAL_INT(O2P_OK,
        o2p_fraction_from_current(&blind, (int32_t)(i_5pct + 0.5f), 2000, &c_blind));

    /* It reads HIGH, and by much more than the 2 % relative the same offset
     * costs at the air point - which is the whole argument for subtracting it
     * rather than absorbing it. */
    TEST_ASSERT_TRUE_MESSAGE(c_blind > c_good,
        "an unsubtracted dark current must bias the reading upward");
    float rel = (c_blind - c_good) / c_good;
    TEST_ASSERT_TRUE_MESSAGE(rel > 0.02f,
        "at 5 %vol the error must exceed the air-point error, not match it");
}

static void test_a_zero_at_or_above_the_air_point_is_unevaluable(void)
{
    /* Not a small error - a sign inversion, and it must never reach the
     * logarithm. */
    float c = 1.0f;
    o2p_cal_t bad = zero_test_cal(100000, 100000);
    TEST_ASSERT_EQUAL_INT(O2P_UNEVALUABLE,
        o2p_fraction_from_current(&bad, 50000, 2000, &c));
    o2p_cal_t worse = zero_test_cal(100000, 150000);
    TEST_ASSERT_EQUAL_INT(O2P_UNEVALUABLE,
        o2p_fraction_from_current(&worse, 50000, 2000, &c));
}

static void test_a_negative_zero_is_accepted(void)
{
    /* The TIA and ADC offsets are real and signed. Clamping a negative zero
     * to 0 would bias every low-O2 reading upward - the region that matters. */
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(-1500));
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(0));
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(2489));   /* DS-0637 0.4 %vol top */
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(60000)); /* a whole air point */
}

static void test_config_refuses_an_implausible_stored_zero(void)
{
    /* A corrupt flash image must not install a zero a Modbus master would
     * have been refused. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
    cfg.cal_zero_na = 500000;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
    cfg.cal_zero_na = -500000;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
}

static void test_cal_state_reports_an_unfinished_commissioning(void)
{
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    o2p_mb_handlers_t h = {.read = o2p_regmap_read, .write = o2p_regmap_write,
                           .ctx = &r};
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x2B, 0x00, 0x01};
    size_t n = framed(req, rd, sizeof(rd));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    uint16_t st = (uint16_t)((rsp[3] << 8) | rsp[4]);
    /* A fresh probe: no air point and no zero point. */
    TEST_ASSERT_TRUE((st & O2P_CAL_STATE_AIR_DEFAULT) != 0u);
    TEST_ASSERT_TRUE((st & O2P_CAL_STATE_NO_ZERO) != 0u);

    /* A measured zero of exactly 0 nA must clear NO_ZERO - the flag, not the
     * value, is what says commissioning happened. */
    r.cfg.cal_zero_na = 0;
    r.cfg.cal_zero_taken = 1u;
    n = framed(req, rd, sizeof(rd));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    st = (uint16_t)((rsp[3] << 8) | rsp[4]);
    TEST_ASSERT_TRUE((st & O2P_CAL_STATE_NO_ZERO) == 0u);
}

static void test_v5_migration_keeps_everything_and_adds_no_zero(void)
{
    /* v5 is what the field is running. It differs from v6 only by the ABSENCE
     * of a zero point, so nothing may be discarded - unlike v2/v3, whose air
     * point changed meaning. */
    test_cfg_v5_t v5;
    memset(&v5, 0, sizeof(v5));
    v5.cal_air_na = 101500;
    v5.rh_setpoint_x100 = 7500u;
    v5.dt_max_k_x100 = 250u;
    v5.heater_max_duty_x100 = 3000u;
    v5.heater_pwm_hz = 1500u;
    v5.cal_temp_c100 = 2140;
    v5.tempco_ppm_per_k = 2000;
    v5.sht_pulse_interval_h = 12u;
    v5.heater_kp_x100 = 450u;
    v5.heater_ki_x100 = 60u;
    v5.assumed_p_hpa = 963u;
    v5.cal_air_frac_x1000 = 20685u;
    v5.cal_p_hpa = 963u;
    v5.slave_addr = 17u;
    v5.baud_code = O2P_BAUD_38400;
    v5.parity_code = O2P_PARITY_NONE;
    v5.dil_alpha_x1000 = 900u;

    uint8_t rec[TEST_REC_BYTES];
    build_v5_record(rec, &v5, 91u);

    o2p_config_t out;
    uint32_t seq = 0u;
    memset(&out, 0xAA, sizeof(out));
    TEST_ASSERT_TRUE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));
    TEST_ASSERT_EQUAL_UINT32(91u, seq);

    /* The calibration survives intact - forcing a recalibration on every
     * deployed probe for an appended field would be the bug. */
    TEST_ASSERT_EQUAL_INT32(101500, out.cal_air_na);
    TEST_ASSERT_EQUAL_UINT16(20685u, out.cal_air_frac_x1000);
    TEST_ASSERT_EQUAL_UINT16(963u, out.cal_p_hpa);
    TEST_ASSERT_EQUAL_INT16(2140, out.cal_temp_c100);
    TEST_ASSERT_EQUAL_UINT16(900u, out.dil_alpha_x1000);
    /* Reachability, the reason the migration exists at all. */
    TEST_ASSERT_EQUAL_UINT8(17u, out.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, out.baud_code);
    /* And the new field says, honestly, that no zero point was ever taken. */
    TEST_ASSERT_EQUAL_INT32(0, out.cal_zero_na);
    TEST_ASSERT_EQUAL_UINT8(0u, out.cal_zero_taken);
    TEST_ASSERT_TRUE(o2p_config_valid(&out));
}

/* ---- runaway needs SUSTAINED evidence, 2026-09-08 ---- */

static void test_runaway_does_not_latch_on_one_hot_sample(void)
{
    /* The detector used to wait 60 s of zero duty and then latch on the FIRST
     * high-dT sample it saw. That is an arming DELAY, not a sustain
     * requirement: one noisy tip reading disabled the heater permanently.
     * Sit cold for well past the window, then present a single hot sample. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    o2p_heater_in_t cold = hin_healthy();

    uint32_t t = 0u;
    for (; t < 300u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &cold, t, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);

    o2p_heater_in_t hot = cold;
    hot.t_tip_c100 = (int16_t)(hot.t_die_c100 + O2P_HEATER_RUNAWAY_DIE_K100 + 500);
    o2p_heater_ctl_step(&st, &cfg, &hot, t++, &out);
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "one hot sample must not latch a permanent runaway");

    /* Back to normal - the evidence must be discarded, not banked. */
    for (unsigned i = 0; i < 10u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &cold, t++, &out);
    }
    TEST_ASSERT_EQUAL_UINT16(0u, st.runaway_evidence_s);
    TEST_ASSERT_FALSE(st.runaway_latched);
}

static void test_runaway_latches_on_sustained_uncommanded_heat(void)
{
    /* The true positive must still fire, or the sustain requirement has
     * simply disabled the detector. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = (int16_t)(hot.t_die_c100 + O2P_HEATER_RUNAWAY_DIE_K100 + 500);

    for (uint32_t t = 0u; t <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &hot, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "sustained uncommanded heat must still latch");
}

static void test_runaway_discards_evidence_across_a_blind_gap(void)
{
    /* A detector cannot tell sparse sampling of a real event from isolated
     * glimpses across an interval it was not watching. Beyond the cadence
     * contract the evidence describes a different situation, so it goes. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = (int16_t)(hot.t_die_c100 + O2P_HEATER_RUNAWAY_DIE_K100 + 500);

    uint32_t t = 0u;
    /* Half a window of real evidence... */
    for (unsigned i = 0; i < (O2P_HEATER_RUNAWAY_WINDOW_S / 2u); i++) {
        o2p_heater_ctl_step(&st, &cfg, &hot, t++, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
    /* ...then a jump far beyond the cadence contract. The next sample is a
     * glimpse, not a continuation. */
    t += 10u * O2P_HEATER_RUNAWAY_MAX_GAP_S;
    o2p_heater_ctl_step(&st, &cfg, &hot, t++, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, st.runaway_evidence_s);
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "evidence from before a blind gap must not be extended across it");
}

/* ---- tempco bound and the nominal air point, 2026-09-08 ---- */

static void test_tempco_register_refuses_an_absurd_coefficient(void)
{
    /* The register was written straight into the config with no check, so an
     * i16 allowed +/-32767 ppm/K - a gain of 4.3 or of -2.3 across a 100 K
     * excursion, on every later reading. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    o2p_mb_handlers_t h = {.read = o2p_regmap_read, .write = o2p_regmap_write,
                           .ctx = &r};
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];

    uint16_t bad = (uint16_t)(int16_t)20000;
    uint8_t w[] = {0x03, 0x10, 0x00, 0x3A, 0x00, 0x01, 0x02,
                   (uint8_t)(bad >> 8), (uint8_t)(bad & 0xFF)};
    size_t n = framed(req, w, sizeof(w));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    TEST_ASSERT_EQUAL_HEX8(0x90, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_INT16(0, r.cfg.tempco_ppm_per_k);

    /* A legal one still lands. */
    uint16_t ok = (uint16_t)(int16_t)2000;
    uint8_t w2[] = {0x03, 0x10, 0x00, 0x3A, 0x00, 0x01, 0x02,
                    (uint8_t)(ok >> 8), (uint8_t)(ok & 0xFF)};
    n = framed(req, w2, sizeof(w2));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);
    TEST_ASSERT_EQUAL_INT16(2000, r.cfg.tempco_ppm_per_k);
}

static void test_a_corrupt_flash_tempco_is_refused_too(void)
{
    /* A flash image must not install what a Modbus master would be refused. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    cfg.tempco_ppm_per_k = (int16_t)-20000;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
}

static void test_the_gain_guard_refuses_only_sign_and_nonfinite(void)
{
    /* A sign-inverted gain must never reach the division; a legal-but-extreme
     * one must not be silently rejected, because that would revoke the
     * TEMP_OVER extrapolation contract. alpha = -5000 ppm/K at the bound, read
     * 200 K above the calibration point, gives gain = 0 - refused. */
    float c = 0.0f;
    o2p_cal_t inverted = zero_test_cal(100000, 0);
    inverted.cal_temp_c100 = 0;
    inverted.tempco_per_k = -5000e-6f;
    TEST_ASSERT_EQUAL_INT(O2P_UNEVALUABLE,
        o2p_fraction_from_current(&inverted, 50000, 25000, &c));

    /* Well inside, the same coefficient converts normally. */
    o2p_cal_t fine = zero_test_cal(100000, 0);
    fine.cal_temp_c100 = 2000;
    fine.tempco_per_k = -5000e-6f;
    TEST_ASSERT_EQUAL_INT(O2P_OK,
        o2p_fraction_from_current(&fine, 50000, 4000, &c));
}

static void test_the_uncalibrated_nominal_matches_the_tia_headroom(void)
{
    /* The nominal is the fallback every uncalibrated probe converts against,
     * so it has to be the same cell the rest of the tree is sized for. The
     * TIA headroom figure used throughout is 152 uA at 30 %vol; scaled to the
     * 20.9 % air point that is ~106 uA, which a 70 uA nominal contradicts. */
    TEST_ASSERT_EQUAL_INT32(100000, O2P_CAL_AIR_NOMINAL_NA);
    int32_t from_headroom_na = (int32_t)(152000.0 * 20.9 / 30.0);
    TEST_ASSERT_INT32_WITHIN(12000, from_headroom_na, O2P_CAL_AIR_NOMINAL_NA);
    /* And it must sit inside the window the air-point validator accepts. */
    TEST_ASSERT_TRUE(o2p_cal_air_plausible(O2P_CAL_AIR_NOMINAL_NA));
}

/* ---- modbus receive frame assembly, 2026-09-08 ----
 *
 * modbus_rtu.c had NO host coverage, and it is where the two worst bugs in
 * this subsystem live: a response deadline that is never stamped (the probe
 * answers nothing, ever) and a line error that truncates instead of poisoning
 * (the probe answers a request it never heard the start of). */

static void test_a_clean_frame_completes_at_the_gap(void)
{
    uint8_t buf[O2P_MB_MAX_ADU];
    o2p_mb_rx_t rx;
    o2p_mb_rx_reset(&rx);
    const uint8_t adu[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    for (unsigned i = 0; i < sizeof(adu); i++) {
        o2p_mb_rx_byte(&rx, adu[i], buf, (uint16_t)sizeof(buf));
    }
    TEST_ASSERT_FALSE(rx.ready);
    TEST_ASSERT_TRUE(o2p_mb_rx_gap(&rx));
    TEST_ASSERT_TRUE(rx.ready);
    TEST_ASSERT_EQUAL_UINT16(sizeof(adu), rx.len);
    TEST_ASSERT_EQUAL_MEMORY(adu, buf, sizeof(adu));
}

static void test_a_line_error_poisons_the_whole_frame(void)
{
    /* THE BUG THIS EXISTS FOR. A parity error used to set the length to zero
     * and carry on, so the bytes AFTER the error started a fresh frame. If
     * what remained on the wire formed a valid ADU, the probe executed a
     * request whose beginning it never heard - and on a 9600 8E1 bus shared
     * with two SMT100s, the tail of someone else's frame is exactly what
     * follows. */
    uint8_t buf[O2P_MB_MAX_ADU];
    o2p_mb_rx_t rx;
    o2p_mb_rx_reset(&rx);

    o2p_mb_rx_byte(&rx, 0x03, buf, (uint16_t)sizeof(buf));
    o2p_mb_rx_line_error(&rx);          /* parity error mid-frame */
    /* A complete, perfectly valid request now arrives on the tail. */
    const uint8_t rest[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    for (unsigned i = 0; i < sizeof(rest); i++) {
        o2p_mb_rx_byte(&rx, rest[i], buf, (uint16_t)sizeof(buf));
    }
    TEST_ASSERT_FALSE_MESSAGE(o2p_mb_rx_gap(&rx),
        "a frame containing a line error must not be executed");
    TEST_ASSERT_FALSE(rx.ready);
}

static void test_the_poison_lasts_exactly_one_frame(void)
{
    /* Poisoning that outlived its frame would make one parity error deafen
     * the probe permanently - the opposite failure, and just as fatal. */
    uint8_t buf[O2P_MB_MAX_ADU];
    o2p_mb_rx_t rx;
    o2p_mb_rx_reset(&rx);

    o2p_mb_rx_byte(&rx, 0x03, buf, (uint16_t)sizeof(buf));
    o2p_mb_rx_line_error(&rx);
    TEST_ASSERT_FALSE(o2p_mb_rx_gap(&rx));
    TEST_ASSERT_FALSE(rx.poisoned);

    const uint8_t adu[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    for (unsigned i = 0; i < sizeof(adu); i++) {
        o2p_mb_rx_byte(&rx, adu[i], buf, (uint16_t)sizeof(buf));
    }
    TEST_ASSERT_TRUE_MESSAGE(o2p_mb_rx_gap(&rx),
        "the frame after a poisoned one must be answered normally");
}

static void test_an_overlong_frame_saturates_rather_than_overruns(void)
{
    uint8_t buf[O2P_MB_MAX_ADU];
    o2p_mb_rx_t rx;
    o2p_mb_rx_reset(&rx);
    for (unsigned i = 0; i < O2P_MB_MAX_ADU * 2u; i++) {
        o2p_mb_rx_byte(&rx, (uint8_t)i, buf, (uint16_t)sizeof(buf));
    }
    TEST_ASSERT_EQUAL_UINT16(O2P_MB_MAX_ADU, rx.len);
    /* Too long is still "a frame", and it is the CRC that rejects it. */
    TEST_ASSERT_TRUE(o2p_mb_rx_gap(&rx));
}

static void test_a_ready_frame_is_never_overwritten(void)
{
    /* The main loop has not consumed it yet; new traffic must not scribble
     * over the request being answered. */
    uint8_t buf[O2P_MB_MAX_ADU];
    o2p_mb_rx_t rx;
    o2p_mb_rx_reset(&rx);
    const uint8_t adu[] = {0x03, 0x03, 0x00, 0x00, 0x00, 0x08};
    for (unsigned i = 0; i < sizeof(adu); i++) {
        o2p_mb_rx_byte(&rx, adu[i], buf, (uint16_t)sizeof(buf));
    }
    TEST_ASSERT_TRUE(o2p_mb_rx_gap(&rx));

    o2p_mb_rx_byte(&rx, 0xFF, buf, (uint16_t)sizeof(buf));
    TEST_ASSERT_EQUAL_UINT16(sizeof(adu), rx.len);
    TEST_ASSERT_EQUAL_MEMORY(adu, buf, sizeof(adu));
}

/* ---- review findings, 2026-09-08 ---- */

static void test_an_unbounded_cal_temp_defeats_the_tempco_bound(void)
{
    /* Gain is 1 + alpha*(T_meas - T_cal). Bounding alpha alone bounds nothing
     * while T_cal is free: i16 admits 0x8000 = -327.68 C, which with alpha at
     * its own limit gives gain 2.76 and reports a true 5.00 %vol as 1.84 %vol
     * - across the compost turn threshold, in range, below TEMP_OVER and with
     * a clean fault word. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    o2p_mb_handlers_t h = {.read = o2p_regmap_read, .write = o2p_regmap_write,
                           .ctx = &r};
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    uint16_t v = 0x8000u;
    uint8_t w[] = {0x03, 0x10, 0x00, 0x39, 0x00, 0x01, 0x02,
                   (uint8_t)(v >> 8), (uint8_t)(v & 0xFF)};
    size_t n = framed(req, w, sizeof(w));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_INT16(2500, r.cfg.cal_temp_c100);

    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    cfg.cal_temp_c100 = (int16_t)-32768;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
}

static void test_writing_a_zero_point_marks_it_taken(void)
{
    /* cal_zero_taken was initialised to 0, read by CAL_STATE, and set to 1
     * nowhere in production code - so a zeroed probe reported NO_ZERO forever
     * while the arithmetic used the new value. */
    o2p_regmap_t r;
    o2p_regmap_init(&r);
    TEST_ASSERT_EQUAL_UINT8(0u, r.cfg.cal_zero_taken);

    o2p_mb_handlers_t h = {.read = o2p_regmap_read, .write = o2p_regmap_write,
                           .ctx = &r};
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    /* CAL_ZERO_NA_HI/LO = 0x0046/0x0047, writing +1800 nA. */
    uint8_t w[] = {0x03, 0x10, 0x00, 0x46, 0x00, 0x02, 0x04,
                   0x00, 0x00, 0x07, 0x08};
    size_t n = framed(req, w, sizeof(w));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);
    TEST_ASSERT_EQUAL_INT32(1800, r.cfg.cal_zero_na);
    TEST_ASSERT_EQUAL_UINT8(1u, r.cfg.cal_zero_taken);

    /* And CAL_STATE must stop claiming the probe has no zero point. */
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x2B, 0x00, 0x01};
    n = framed(req, rd, sizeof(rd));
    TEST_ASSERT_TRUE(o2p_mb_dispatch(req, n, 3, &h, rsp) > 0);
    uint16_t st = (uint16_t)((rsp[3] << 8) | rsp[4]);
    TEST_ASSERT_TRUE((st & O2P_CAL_STATE_NO_ZERO) == 0u);
}

static void test_a_v5_record_with_a_now_illegal_tempco_is_not_thrown_away(void)
{
    /* v5 allowed any int16_t tempco. v6 bounds it. Copying the old value
     * across and then validating would fail the WHOLE record - and a failed
     * record means full defaults, which resets slave_addr, baud and parity. A
     * potted probe on a non-default address would vanish from its master on a
     * firmware update, over a field it may not even be using. */
    test_cfg_v5_t v5;
    memset(&v5, 0, sizeof(v5));
    v5.cal_air_na = 101500;
    v5.rh_setpoint_x100 = 7500u;
    v5.dt_max_k_x100 = 250u;
    v5.heater_max_duty_x100 = 3000u;
    v5.heater_pwm_hz = 1500u;
    v5.cal_temp_c100 = 2140;
    v5.tempco_ppm_per_k = 5001;          /* legal in v5, illegal in v6 */
    v5.sht_pulse_interval_h = 12u;
    v5.heater_kp_x100 = 450u;
    v5.heater_ki_x100 = 60u;
    v5.assumed_p_hpa = 963u;
    v5.cal_air_frac_x1000 = 20685u;
    v5.cal_p_hpa = 963u;
    v5.slave_addr = 17u;
    v5.baud_code = O2P_BAUD_38400;
    v5.parity_code = O2P_PARITY_NONE;
    v5.dil_alpha_x1000 = 1000u;

    uint8_t rec[TEST_REC_BYTES];
    build_v5_record(rec, &v5, 91u);

    o2p_config_t out;
    uint32_t seq = 0u;
    TEST_ASSERT_TRUE_MESSAGE(o2p_config_migrate(rec, sizeof(rec), &out, &seq),
        "a v5 record must not be discarded over a field v6 newly bounds");
    /* Reachability above all - this is what a rejected record would lose. */
    TEST_ASSERT_EQUAL_UINT8(17u, out.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, out.baud_code);
    /* The untrustworthy field alone is reset, to "no compensation". */
    TEST_ASSERT_EQUAL_INT16(0, out.tempco_ppm_per_k);
    /* The calibration survives: nothing about it was in question. */
    TEST_ASSERT_EQUAL_INT32(101500, out.cal_air_na);
}

static void test_a_v5_record_with_an_absurd_cal_temp_drops_the_air_point(void)
{
    /* Unlike the tempco, a nonsense calibration temperature cannot be
     * defaulted quietly: 25 C would keep converting against a reference the
     * probe never saw. The air point goes with it, raising CAL_DEFAULT. */
    test_cfg_v5_t v5;
    memset(&v5, 0, sizeof(v5));
    v5.cal_air_na = 101500;
    v5.rh_setpoint_x100 = 7500u;
    v5.dt_max_k_x100 = 250u;
    v5.heater_max_duty_x100 = 3000u;
    v5.heater_pwm_hz = 1500u;
    v5.cal_temp_c100 = (int16_t)-32768;
    v5.sht_pulse_interval_h = 12u;
    v5.heater_kp_x100 = 450u;
    v5.heater_ki_x100 = 60u;
    v5.assumed_p_hpa = 963u;
    v5.cal_air_frac_x1000 = 20685u;
    v5.cal_p_hpa = 963u;
    v5.slave_addr = 17u;
    v5.baud_code = O2P_BAUD_38400;
    v5.parity_code = O2P_PARITY_NONE;
    v5.dil_alpha_x1000 = 1000u;

    uint8_t rec[TEST_REC_BYTES];
    build_v5_record(rec, &v5, 92u);
    o2p_config_t out;
    uint32_t seq = 0u;
    TEST_ASSERT_TRUE(o2p_config_migrate(rec, sizeof(rec), &out, &seq));
    TEST_ASSERT_EQUAL_UINT8(17u, out.slave_addr);       /* still reachable */
    TEST_ASSERT_EQUAL_INT32(0, out.cal_air_na);         /* raises CAL_DEFAULT */
    TEST_ASSERT_TRUE(o2p_cal_temp_plausible(out.cal_temp_c100));
}

static void test_runaway_sees_heat_under_a_low_commanded_duty(void)
{
    /* A FET stuck fully on while the loop asks for a few percent is heat
     * nobody commanded, and exactly-zero was too strict a test: saturated
     * compost holds the humidity error positive, so the loop need never return
     * to zero. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_out_t out;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = (int16_t)(hot.t_die_c100 + O2P_HEATER_RUNAWAY_DIE_K100 + 500);

    /* Drive update_runaway directly through the public step with a duty the
     * controller would command at a small error: below the idle threshold. */
    for (uint32_t t = 0u; t <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &hot, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "uncommanded heat under a near-idle duty must still latch");
}

static void test_the_isr_and_the_tested_state_machine_are_one(void)
{
    /* The helpers were extracted so the shipped decision could be tested, and
     * modbus_rtu.c then duplicated the logic instead of calling them - so the
     * tests exercised a parallel copy. They had already drifted: reset cleared
     * the poison and the reconfiguration path did not. This asserts the
     * property that made the drift possible is gone: a reset clears every
     * field, poison included. */
    o2p_mb_rx_t rx;
    rx.len = 7u; rx.ready = true; rx.poisoned = true;
    o2p_mb_rx_reset(&rx);
    TEST_ASSERT_EQUAL_UINT16(0u, rx.len);
    TEST_ASSERT_FALSE(rx.ready);
    TEST_ASSERT_FALSE_MESSAGE(rx.poisoned,
        "a reset must clear the poison, or a line error racing a serial "
        "reconfiguration discards the next valid frame");
}

/* ---- LMP91000 die temperature, SNAS506I Table 1 --------------------------
 *
 * The anchors below are ROWS OF TABLE 1, transcribed, not values produced by
 * the implementation and then blessed. That is the whole point: the fit is
 * only worth anything if it is pinned to the datasheet rather than to itself.
 * Endpoints and the operating band; the full 126-row sweep was run offline
 * and its worst cases are the two tolerances asserted here. */
static void test_afe_die_temperature_follows_the_datasheet_table(void)
{
    int16_t c100 = 0;

    /* 0..85 C, the band this register is for: within 0.41 C of the table. */
    const struct { uint16_t mv; int16_t c; } hot[] = {
        { 1560,  0 }, { 1359, 25 }, { 1154, 50 }, { 920, 78 }, { 861, 85 },
    };
    for (unsigned i = 0; i < sizeof hot / sizeof hot[0]; i++) {
        TEST_ASSERT_TRUE(o2p_lmp_temp_c100_from_mv(hot[i].mv, &c100));
        TEST_ASSERT_INT16_WITHIN(41, (int16_t)(hot[i].c * 100), c100);
    }

    /* The cold end is EXTRAPOLATION and the header says so. Assert the real
     * error, so that a later "improvement" to the coefficients cannot quietly
     * make the cold end worse than documented. */
    TEST_ASSERT_TRUE(o2p_lmp_temp_c100_from_mv(1875u, &c100));
    TEST_ASSERT_INT16_WITHIN(212, -4000, c100);

    /* Outside the specified VOUT window nothing is written, and the caller's
     * variable keeps whatever it held - an unevaluable input is not a
     * temperature and must not be reported as one. */
    c100 = 0x5A5A;
    TEST_ASSERT_FALSE(o2p_lmp_temp_c100_from_mv(1876u, &c100));
    TEST_ASSERT_EQUAL_HEX16(0x5A5A, (uint16_t)c100);
    TEST_ASSERT_FALSE(o2p_lmp_temp_c100_from_mv(860u, &c100));
    TEST_ASSERT_EQUAL_HEX16(0x5A5A, (uint16_t)c100);
    TEST_ASSERT_FALSE(o2p_lmp_temp_c100_from_mv(1359u, NULL));

    /* Monotonic: more millivolts is colder, with no fold-back anywhere in the
     * window. A sign slip in the integer form would still pass the anchors. */
    int16_t prev = 32767;
    for (uint16_t mv = 861u; mv <= 1875u; mv++) {
        TEST_ASSERT_TRUE(o2p_lmp_temp_c100_from_mv(mv, &c100));
        TEST_ASSERT_TRUE(c100 < prev);
        prev = c100;
    }

    /* 110 would read the same sensor with the TIA off, unbiasing the cell and
     * costing the DS-0637 settling penalty. It must be 111. */
    TEST_ASSERT_EQUAL_HEX8(0x07u, O2P_LMP_MODECN_TEMP);

    /* Which readback values mean the cell STOPPED being driven. This decides
     * whether a failed mode switch owes a settling restart, and getting it
     * wrong in the safe direction holds a healthy probe out of the compensated
     * channel for 15 minutes at a time. 011 and 111 keep the potentiostat
     * running; everything else, including anything unrecognised, does not. */
    TEST_ASSERT_FALSE(o2p_lmp_mode_unbiases_the_cell(0x03u));
    TEST_ASSERT_FALSE(o2p_lmp_mode_unbiases_the_cell(0x07u));
    TEST_ASSERT_TRUE(o2p_lmp_mode_unbiases_the_cell(0x06u));   /* TIA off */
    TEST_ASSERT_TRUE(o2p_lmp_mode_unbiases_the_cell(0x00u));   /* deep sleep */
    TEST_ASSERT_TRUE(o2p_lmp_mode_unbiases_the_cell(0x02u));   /* standby */
    TEST_ASSERT_TRUE(o2p_lmp_mode_unbiases_the_cell(0x05u));   /* undefined */
    /* FET_SHORT set alongside a running mode must not flip the verdict. */
    TEST_ASSERT_FALSE(o2p_lmp_mode_unbiases_the_cell(0x83u));

    /* The hazard the mode readback exists for: the oxygen channel's own swing
     * decodes as a perfectly plausible temperature, so no value check can
     * stand in for verifying MODECN. Pin it, so nobody later "hardens" this
     * with a range test and believes it did something. */
    TEST_ASSERT_TRUE(o2p_lmp_temp_c100_from_mv(934u, &c100));
    TEST_ASSERT_TRUE(c100 > 7000 && c100 < 8000);
    TEST_ASSERT_TRUE(o2p_lmp_temp_c100_from_mv(965u, &c100));
    TEST_ASSERT_TRUE(c100 > 7000 && c100 < 8000);
}

/* The bias PREDICATE, and the derivation of what it compares against.
 *
 * WHAT THIS DOES NOT DO, stated plainly because the first version of this
 * comment implied otherwise and a review called it: it does not exercise the
 * production guard. main.c does not compile on the host, so nothing here
 * drives finish_electrode(), inspects g_cyc.faults, advances the sampler, or
 * observes an air point being refused. Deleting the check in main.c leaves
 * this test green. Guard-checklist item 7 is UNMET for that path and the only
 * honest fix is a host-buildable sampler, not a better assertion here.
 *
 * What it does cover is the part that used to be two hand-copied literals: the
 * commanded target is now DERIVED from O2P_LMP_REFCN_INTENDED, and the
 * derivation is checked against SNAS506I 7.6.4's own BIAS table. */
static void test_the_cell_bias_window_catches_an_open_potentiostat(void)
{
    /* SNAS506I 7.6.4, BIAS[3:0], transcribed. Every code, so a change to the
     * decoder cannot pass by matching only the one step we happen to use. */
    static const int32_t bias_table[16] = {
        0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 24, 24
    };
    for (uint8_t code = 0u; code < 14u; code++) {
        TEST_ASSERT_EQUAL_INT32(bias_table[code], o2p_lmp_bias_percent(code));
    }
    /* The configured constant really is 24 %, negative sign. */
    TEST_ASSERT_EQUAL_INT32(24, o2p_lmp_bias_percent(O2P_LMP_REFCN_INTENDED));
    TEST_ASSERT_EQUAL_HEX8(0x00u, (uint8_t)(O2P_LMP_REFCN_INTENDED & 0x10u));

    const int32_t vref = 2492;
    const int32_t want = o2p_lmp_commanded_bias_mv(vref);
    TEST_ASSERT_INT32_WITHIN(2, -598, want);
    /* Negative, because BIAS_SIGN 0 is (VWE-VRE)<0 and the telemetry is
     * WE - RE. A sign slip here is the one error that would make the guard
     * fire on every healthy probe instead of no broken one. */
    TEST_ASSERT_TRUE(want < 0);

    /* Healthy: the bench measured 597 mV against 598.56 commanded on
     * 2026-09-04, and DS-0637 allows +/-10 mV. Must NOT fire. */
    TEST_ASSERT_TRUE(labs((long)(-597 - want)) <= O2P_CELL_BIAS_TOLERANCE_MV);
    TEST_ASSERT_TRUE(labs((long)(-608 - want)) <= O2P_CELL_BIAS_TOLERANCE_MV);

    /* KNOWN-BAD, and the reason this exists: the probe read +341 mV on
     * 2026-09-08 - wrong magnitude AND wrong sign - for hours, with a clean
     * fault word. Construct it and observe the guard fail. */
    TEST_ASSERT_TRUE(labs((long)(341 - want)) > O2P_CELL_BIAS_TOLERANCE_MV);

    /* An unbiased cell is the canonical open loop. */
    TEST_ASSERT_TRUE(labs((long)(0 - want)) > O2P_CELL_BIAS_TOLERANCE_MV);

    /* Monotone in the failure direction: once out, it stays out. No fold-back
     * at the far tail, where a signed-arithmetic slip would show. */
    for (int32_t b = 341; b <= 3000; b += 7) {
        TEST_ASSERT_TRUE(labs((long)(b - want)) > O2P_CELL_BIAS_TOLERANCE_MV);
    }
    for (int32_t b = -3000; b <= -800; b += 7) {
        TEST_ASSERT_TRUE(labs((long)(b - want)) > O2P_CELL_BIAS_TOLERANCE_MV);
    }

    /* Wide enough to clear every legitimate error term by an order of
     * magnitude: VOS_RW is +/-1750 uV MAX at 24 % bias, and its DRIFT
     * TcVOS_RW is +/-8 uV/K (SNAS506I 6.5 - two different parameters, and an
     * earlier version of this comment used the wrong name for the first). The
     * VREF trim band is +/-20 mV, which moves the target by 4.8 mV. */
    TEST_ASSERT_TRUE(O2P_CELL_BIAS_TOLERANCE_MV > 10 * 2);
    TEST_ASSERT_TRUE(O2P_CELL_BIAS_TOLERANCE_MV < (-want) / 2);
}

/* The as-built gate on that predicate, added 2026-09-09.
 *
 * SAME HONESTY LIMIT as the test above, restated because it is easy to read
 * this one as stronger than it is: main.c does not compile on the host, so
 * nothing here drives finish_electrode(). This does NOT prove that the gate
 * suppresses the fault bit on the real sampler. Guard-checklist item 7 stays
 * UNMET for that path until there is a host-buildable sampler.
 *
 * What it does pin down is the two things that would silently undo the fix:
 * the default, and whether the fix is a mute button. */
static void test_the_bias_guard_is_gated_on_as_built_wiring(void)
{
    /* The host tests are built for the bench board (O2P_BOARD_REV_A), whose
     * AIN2/AIN3 are the VA and VIN rail monitors - so the capability is 0 and
     * the guard must refuse to judge. This value is DERIVED by
     * tools/gen_hw_caps.py from the fabricated netlist at 16b5a606, not
     * written by hand, and tools/test_pcb_netlist.py checks the derivation
     * against pads confirmed with a meter. Asserting it here catches a
     * regeneration that silently changed the answer. */
    TEST_ASSERT_EQUAL_INT(0, O2P_HW_BIAS_ADC_REACHES_ELECTRODES);

    /* And the revision really was selected: hw_caps.h #errors without it, but
     * a test that never included the header would still pass, so say it. */
#ifndef O2P_BOARD_REV_A
    TEST_FAIL_MESSAGE("host tests must be built for a named board revision");
#endif

    /* FIX, NOT MUTE (guard-checklist item 8). The gate must change only
     * WHETHER the window is consulted, never HOW it decides. On a board where
     * the channels do reach the electrodes, the known-bad case that motivated
     * the guard - +341 mV measured against -598 mV commanded, wrong magnitude
     * and wrong sign, published for hours on 2026-09-08 - must still be
     * outside the window. If a later edit "fixes" the false fault by widening
     * the tolerance instead, this fails. */
    const int32_t want = o2p_lmp_commanded_bias_mv(2492);
    TEST_ASSERT_TRUE(labs((long)(341 - want)) > O2P_CELL_BIAS_TOLERANCE_MV);
    TEST_ASSERT_TRUE(labs((long)(0 - want)) > O2P_CELL_BIAS_TOLERANCE_MV);
    TEST_ASSERT_TRUE(labs((long)(-597 - want)) <= O2P_CELL_BIAS_TOLERANCE_MV);

    /* And the gate is a compile-time constant that can be overridden per
     * environment, not a runtime flag some later code can set from telemetry.
     * The board it describes cannot change while the firmware is running. */
#ifndef O2P_HW_BIAS_ADC_REACHES_ELECTRODES
    TEST_FAIL_MESSAGE("O2P_HW_BIAS_ADC_REACHES_ELECTRODES must be defined");
#endif
    /* The channel names travel with the capability, so a diagnosis never has
     * to guess which board's map it is reading. */
    TEST_ASSERT_EQUAL_STRING("/ADC_VA_MON",  O2P_HW_ADC_AIN2_NET);
    TEST_ASSERT_EQUAL_STRING("/ADC_VIN_MON", O2P_HW_ADC_AIN3_NET);
}

static void test_the_rev_a_divider_scaling(void)
{
    /* On Rev A, VA_MON is R24/R25 10k/10k = 2.0; VIN_MON is R26/R27 130k/20k = 7.5.
     * Raw tap voltages must be scaled to avoid permanently triggering VA_LOW and VIN_LOW. */
    TEST_ASSERT_EQUAL_UINT32(10000u, O2P_HW_DIV_VA_ADS_NUM);
    TEST_ASSERT_EQUAL_UINT32(20000u, O2P_HW_DIV_VA_ADS_DEN);
    TEST_ASSERT_EQUAL_UINT32(20000u, O2P_HW_DIV_VIN_ADS_NUM);
    TEST_ASSERT_EQUAL_UINT32(150000u, O2P_HW_DIV_VIN_ADS_DEN);

    uint16_t va_scaled = o2p_scale_va_ads(1650u);
    TEST_ASSERT_EQUAL_UINT16(3300u, va_scaled);
    TEST_ASSERT_TRUE(va_scaled >= O2P_VA_LOW_MV);

    uint16_t vin_scaled = o2p_scale_vin_ads(1600u);
    TEST_ASSERT_EQUAL_UINT16(12000u, vin_scaled);
    TEST_ASSERT_TRUE(vin_scaled >= O2P_VIN_LOW_MV);

    /* Clamping to 0xFFFE so a railed measurement never emits 0xFFFF (O2P_U16_INVALID) */
    TEST_ASSERT_EQUAL_UINT16(0xFFFEu, o2p_scale_vin_ads(10000u));
}

static void test_the_wire_version_tracks_the_wire_contract(void)
{
    /* FW_VERSION's own rule is that it is bumped whenever the wire contract
     * changes. It sat at 0x0002 describing a 26-register block while the block
     * was 28, which left a master no way to tell the two apart before reading. */
    TEST_ASSERT_EQUAL_HEX16(0x000Bu, O2P_FW_VERSION);
    TEST_ASSERT_EQUAL_UINT16(27u, O2P_REG_CONFIG_COUNT);
    /* 0x000B: diag block grew with HEATER_BLOCK and SAMPLER_TIMING_MS.
     * 0x000A: config block grew with TIP_SETPOINT and HEATER_TIP_CONSENT,
     *         the persistent tip-temperature loop.
     * 0x0009: diag block grew with CE_MV, the counter-electrode drive.
     * 0x0008: diag block grew with T_AFE, the LMP91000 die temperature.
     * 0x0007: config block grew with HEATER_RH_CONSENT.
     * 0x0006: the raw channel stopped going silent for 900 s after a reset. */
    TEST_ASSERT_TRUE((O2P_FAULTS_INVALIDATE_O2 & O2P_F_SETTLING) == 0u);
    TEST_ASSERT_TRUE((O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_SETTLING) != 0u);
    TEST_ASSERT_EQUAL_UINT16(32u, O2P_REG_DIAG_COUNT);
    /* 0x0004: the heater test block appeared at an address that previously
     * answered exception 02, and the heater became drivable at all. */
    TEST_ASSERT_EQUAL_UINT16(5u, O2P_REG_HTEST_COUNT);
}

/* ---- main.c and config_flash.c decisions, 2026-09-08 ----
 *
 * Neither file compiles on the host, and neither had any coverage. Two of the
 * three fatal bugs in this firmware's review cycle lived in files with that
 * property, so the decisions are lifted into headers and driven here. */

static void test_cell_current_is_the_departure_from_the_internal_zero(void)
{
    /* The internal zero is 67 % of VREF; a code that lands exactly there is
     * zero cell current, whatever VREF is. */
    const uint32_t vref = 2500u;
    int32_t zero_uv = (int32_t)(((int64_t)vref * 1000 * 67) / 100);
    int32_t zero_code = (int32_t)(((int64_t)zero_uv * 32768) / ((int64_t)vref * 1000));
    TEST_ASSERT_INT32_WITHIN(60, 0, o2p_cell_na_from_code(zero_code, vref));

    /* One TIA volt-drop below the zero is +I. 7 kOhm and 100 uA is 700 mV. */
    int32_t uv_100ua = zero_uv - 700000;
    int32_t code_100ua = (int32_t)(((int64_t)uv_100ua * 32768) / ((int64_t)vref * 1000));
    TEST_ASSERT_INT32_WITHIN(200, 100000, o2p_cell_na_from_code(code_100ua, vref));
}

static void test_cell_current_keeps_its_sign(void)
{
    /* SCHEMATIC-REVIEW.md M4 leaves the SGX sign convention open and the
     * air-versus-nitrogen bench pair is what settles it. An absolute value
     * here would hide the answer. */
    const uint32_t vref = 2500u;
    int32_t zero_uv = (int32_t)(((int64_t)vref * 1000 * 67) / 100);
    int32_t above = (int32_t)((((int64_t)zero_uv + 700000) * 32768) /
                              ((int64_t)vref * 1000));
    TEST_ASSERT_TRUE_MESSAGE(o2p_cell_na_from_code(above, vref) < 0,
        "a code above the internal zero must yield a negative current");
}

static void test_cell_current_is_ratiometric_in_vref(void)
{
    /* Both the LMP91000's zero and the ADC's reference come from VREF_TRIM,
     * so the same fraction of full scale must mean the same current at a
     * different VREF - that is the whole point of the ratiometric wiring. */
    for (unsigned i = 0; i < 2u; i++) {
        uint32_t vref = (i == 0u) ? 2500u : 2048u;
        int32_t zero_uv = (int32_t)(((int64_t)vref * 1000 * 67) / 100);
        int32_t uv = zero_uv - 700000;
        int32_t code = (int32_t)(((int64_t)uv * 32768) / ((int64_t)vref * 1000));
        TEST_ASSERT_INT32_WITHIN(400, 100000, o2p_cell_na_from_code(code, vref));
    }
}

static void test_the_chamber_speaks_for_the_gas_not_the_heated_tip(void)
{
    /* The tip is heated on purpose and reads the ring. Preferring it would
     * bias the tempco correction by whatever the heater is doing. */
    TEST_ASSERT_EQUAL_INT16(2100, o2p_gas_temperature(true, 2100, true, 4500));
    TEST_ASSERT_EQUAL_INT16(4500, o2p_gas_temperature(false, 2100, true, 4500));
    /* Both down is UNEVALUABLE, never a stale or zero temperature. This is
     * what the old inline form got only accidentally right: it read t_tip
     * whenever the chamber had failed, without checking the tip had read. */
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID,
        (uint16_t)o2p_gas_temperature(false, 2100, false, 4500));
}

static void test_raw_current_saturates_to_its_sentinel(void)
{
    TEST_ASSERT_EQUAL_INT16(10000, o2p_encode_raw_ua_x100(100000));
    TEST_ASSERT_EQUAL_INT16(-10000, o2p_encode_raw_ua_x100(-100000));
    /* Past the register's range it must be the sentinel, not a wrapped
     * number that reads as a plausible small current. */
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID,
        (uint16_t)o2p_encode_raw_ua_x100(400000));
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID,
        (uint16_t)o2p_encode_raw_ua_x100(-400000));
}

/* WHY finish_o2() REFUSES A CLIPPED CONVERSION - the measurement that made
 * the case, from the bench of 2026-09-08 and the review of 2026-09-09.
 *
 * The encoder above cannot save us here, and this test exists to pin that
 * down rather than leave it as an argument in a comment. A saturated
 * converter does not produce an out-of-range current that the sentinel catches
 * - it produces a MODEST one, because the cell current is the DEPARTURE from
 * the internal zero at 67 % of VREF, and the distance from there to either
 * rail is about a third of full scale. Across 7 kOhm that is roughly 120 uA,
 * which is the middle of the SGX-OX-ROHS-Mini's 70-130 uA air band.
 *
 * So the number a railed AFE publishes is not merely wrong, it is wrong in
 * the one shape a reader cannot dismiss at a glance: a believable air current
 * with a flipped sign. Nothing downstream of the register can distinguish it,
 * which is why the refusal has to happen where the code is, in finish_o2(),
 * and not in the fault mask - see faults.h. */
static void test_a_railed_conversion_encodes_as_a_believable_air_current(void)
{
    const uint32_t vref_mv = 2496u;   /* as measured on the bench that evening */

    int32_t na = o2p_cell_na_from_code(32767, vref_mv);
    int16_t raw = o2p_encode_raw_ua_x100(na);

    /* Not the sentinel. It encodes cleanly, which is the whole problem. */
    TEST_ASSERT_NOT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)raw);

    /* And its magnitude lands inside the datasheet's air band for the cell,
     * to within a microamp of the -117.5 uA the review reported. */
    int32_t ua_x100 = (raw < 0) ? -(int32_t)raw : (int32_t)raw;
    TEST_ASSERT_TRUE(ua_x100 > 7000 && ua_x100 < 13000);
    TEST_ASSERT_INT32_WITHIN(100, 11750, ua_x100);

    /* THE TWO RAILS ARE NOT SYMMETRIC, and only one of them is dangerous.
     * The internal zero sits at 67 % of VREF, so the positive rail is a third
     * of full scale away and the negative rail is two thirds - about 595 uA,
     * which overflows the register and does emit the sentinel. Half the
     * failure mode is caught for free by arithmetic. That is not a guard,
     * it is a coincidence of where INT_Z happens to sit, and it is exactly
     * the half that did NOT occur on the bench: the AFE railed HIGH. */
    na = o2p_cell_na_from_code(-32768, vref_mv);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID,
        (uint16_t)o2p_encode_raw_ua_x100(na));

    /* Both codes ARE recognised as clipped. The detector was never the weak
     * link; acting on it was. */
    TEST_ASSERT_TRUE(o2p_ads1119_code_clipped(32767));
    TEST_ASSERT_TRUE(o2p_ads1119_code_clipped(-32768));
    /* A real air reading near the internal zero is not clipped, so the guard
     * costs nothing in normal operation. */
    TEST_ASSERT_FALSE(o2p_ads1119_code_clipped(21955));
}

static void test_settle_restarts_count_only_real_restarts(void)
{
    /* The counter's job is to make a bias interruption the once-a-second
     * supervision MISSED visible from a buried probe. One that also climbs
     * during a fault you can already see is no longer that evidence. */
    uint16_t n = 0u;
    uint32_t deadline = o2p_settle_restart(100u, 0u, 900u, &n);
    TEST_ASSERT_EQUAL_UINT32(1000u, deadline);
    TEST_ASSERT_EQUAL_UINT16(1u, n);

    /* Still inside the window: the deadline extends, the counter does not. */
    deadline = o2p_settle_restart(200u, deadline, 900u, &n);
    TEST_ASSERT_EQUAL_UINT32(1100u, deadline);
    TEST_ASSERT_EQUAL_UINT16(1u, n);

    /* And it saturates rather than wrapping to zero, which would read as a
     * probe that had never restarted. */
    n = 0xFFFFu;
    (void)o2p_settle_restart(5000u, 0u, 900u, &n);
    TEST_ASSERT_EQUAL_UINT16(0xFFFFu, n);
}

static void test_the_newer_config_record_wins(void)
{
    TEST_ASSERT_EQUAL_INT(O2P_CFG_PICK_A, o2p_config_pick(true, 9u, true, 4u));
    TEST_ASSERT_EQUAL_INT(O2P_CFG_PICK_B, o2p_config_pick(true, 4u, true, 9u));
    /* A single readable record is the answer whichever page it is on. */
    TEST_ASSERT_EQUAL_INT(O2P_CFG_PICK_A, o2p_config_pick(true, 1u, false, 99u));
    TEST_ASSERT_EQUAL_INT(O2P_CFG_PICK_B, o2p_config_pick(false, 99u, true, 1u));
    TEST_ASSERT_EQUAL_INT(O2P_CFG_PICK_NONE, o2p_config_pick(false, 0u, false, 0u));
}

static void test_the_config_choice_survives_a_sequence_wrap(void)
{
    /* Sequence is a free-running u32. An unsigned compare would pick the OLDER
     * record for the one commit that crosses 0xFFFFFFFF - restoring a stale
     * calibration, and a stale bus address with it. */
    TEST_ASSERT_EQUAL_INT_MESSAGE(O2P_CFG_PICK_B,
        o2p_config_pick(true, 0xFFFFFFFFu, true, 0x00000000u),
        "the record written AFTER the wrap must win");
    TEST_ASSERT_EQUAL_INT(O2P_CFG_PICK_A,
        o2p_config_pick(true, 0x00000001u, true, 0xFFFFFFFEu));
}

static void test_a_store_never_overwrites_the_live_record(void)
{
    /* A power loss part-way through a write must leave the previous
     * configuration intact and still the higher sequence. */
    TEST_ASSERT_EQUAL_UINT8(1u, o2p_config_other_page(0u, 0u, 1u));
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_config_other_page(1u, 0u, 1u));
    /* Alternating from either start visits both pages and never repeats. */
    uint8_t live = 0u;
    for (unsigned i = 0; i < 4u; i++) {
        uint8_t next = o2p_config_other_page(live, 0u, 1u);
        TEST_ASSERT_NOT_EQUAL(live, next);
        live = next;
    }
}

#if O2P_DEBUG_ENABLE
static void test_peek_mailbox_bounds_and_alignment(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_NONE, rm.peek_status);
    for (int w = 0; w < 4; w++) {
        TEST_ASSERT_EQUAL_HEX32(0xFFFFFFFFu, rm.peek_words[w]);
    }

    uint16_t single = 0x2000u;
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_PEEK_ADDR_HI, 1u, &single));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_PEEK_ADDR_LO, 1u, &single));

    uint16_t misaligned[2] = { 0x2000u, 0x0001u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 2u, misaligned));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_ALIGN, rm.peek_status);
    TEST_ASSERT_EQUAL_HEX32(0xFFFFFFFFu, rm.peek_words[0]);

    uint16_t out_of_bounds[2] = { 0x4000u, 0x0000u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 2u, out_of_bounds));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peek_status);

    uint16_t sram[2] = { 0x2000u, 0x0100u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 2u, sram));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);

    uint16_t out[11];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEK_BASE, 11u, out));
    TEST_ASSERT_EQUAL_HEX16(0x2000u, out[0]);
    TEST_ASSERT_EQUAL_HEX16(0x0100u, out[1]);
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, out[2]);
}

static void test_dmbox_validation_and_opcodes(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_NONE, rm.diag_status);
    TEST_ASSERT_FALSE(rm.diag_pending);

    uint16_t bad_magic[2] = { 0x1201u, 0x0000u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_DMBOX_BASE, 2u, bad_magic));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_OPCODE, rm.diag_status);

    uint16_t cmd[2] = { (uint16_t)(0x5A00u | O2P_OP_READ_LMP_REG), 0x0010u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_DMBOX_BASE, 2u, cmd));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_PENDING, rm.diag_status);
    TEST_ASSERT_TRUE(rm.diag_pending);
}

static void test_crash_mailbox_read_and_clear(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    rm.crash_reason = O2P_CRASH_HARDFAULT;
    rm.crash_pc = 0x08004123u;
    rm.crash_lr = 0x08004456u;
    rm.crash_detail = 0u;
    rm.crash_build_id = 0x12345678u;

    uint16_t out[9];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_CRASH_BASE, 9u, out));
    TEST_ASSERT_EQUAL_UINT16(O2P_CRASH_HARDFAULT, out[0]);
    TEST_ASSERT_EQUAL_HEX16(0x0800u, out[1]);
    TEST_ASSERT_EQUAL_HEX16(0x4123u, out[2]);
    TEST_ASSERT_EQUAL_HEX16(0x0800u, out[3]);
    TEST_ASSERT_EQUAL_HEX16(0x4456u, out[4]);
    TEST_ASSERT_EQUAL_HEX16(0x1234u, out[7]);
    TEST_ASSERT_EQUAL_HEX16(0x5678u, out[8]);

    uint16_t zero = 0u;
    /* Writing to other registers in the crash block is rejected */
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_CRASH_BASE, 1u, &zero));
    /* Writing 0 to CRASH_BUILD_ID_LO clears the record */
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_CRASH_BUILD_ID_LO, 1u, &zero));
    TEST_ASSERT_EQUAL_UINT16(O2P_CRASH_NONE, rm.crash_reason);
    TEST_ASSERT_EQUAL_HEX32(0u, rm.crash_pc);
}
#else
static void test_debug_mailboxes_disabled(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);
    uint16_t out[2];
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_read(&rm, 0x0065u, 2u, out));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_read(&rm, 0x0070u, 2u, out));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_read(&rm, 0x0077u, 2u, out));
}
#endif

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_crc16_known_vectors);
    RUN_TEST(test_random_garbage_never_provokes_a_reply);
    RUN_TEST(test_classify_addressing);
    RUN_TEST(test_classify_rejects_corrupt);
    RUN_TEST(test_read_primary_block);
    RUN_TEST(test_discovery_reply_uses_the_discovery_address);
    RUN_TEST(test_config_crc_register_is_read_only);
    RUN_TEST(test_16bit_value_is_not_truncated_into_a_byte_field);
    RUN_TEST(test_config_struct_has_no_implicit_padding);
    RUN_TEST(test_read_across_block_gap_is_refused);
    RUN_TEST(test_unknown_function_is_exception_01);
    RUN_TEST(test_broadcast_never_replies);
    RUN_TEST(test_write_rejects_illegal_slave_address);
    RUN_TEST(test_partly_illegal_multiwrite_commits_nothing);
    RUN_TEST(test_commit_and_cal_need_their_magic);
    RUN_TEST(test_measurement_registers_are_not_writable);
    RUN_TEST(test_air_calibration_round_trips);
    RUN_TEST(test_uncalibrated_cell_is_unevaluable_not_zero);
    RUN_TEST(test_inverted_cell_polarity_is_reported_not_clamped);
    RUN_TEST(test_overrange_is_not_clamped_into_plausibility);
    RUN_TEST(test_monotonic_across_the_whole_range);
    RUN_TEST(test_absurd_tempco_cannot_produce_a_number);
    RUN_TEST(test_implausible_air_point_is_rejected);
    RUN_TEST(test_written_calibration_must_also_be_plausible);
    RUN_TEST(test_uncalibrated_invalidates_comp_but_not_raw);
    RUN_TEST(test_discovery_alias_refuses_writes);
    RUN_TEST(test_snapshot_reset_clears_every_measurement_channel);
    RUN_TEST(test_heater_gains_are_writable_and_bounded);
    RUN_TEST(test_gain_registers_read_back_what_was_written);
    RUN_TEST(test_config_block_read_covers_the_gains);
    RUN_TEST(test_alpha_one_is_the_full_gas_law);
    RUN_TEST(test_alpha_zero_is_exactly_no_correction);
    RUN_TEST(test_alpha_scales_the_correction_it_does_not_scale_the_answer);
    RUN_TEST(test_a_cell_with_this_alpha_reads_dry_air_at_any_humidity);
    RUN_TEST(test_a_bad_alpha_refuses_it_does_not_default_to_one);
    RUN_TEST(test_an_alpha_that_divides_by_nothing_is_refused);
    RUN_TEST(test_dil_alpha_register_bounds_and_default);
    RUN_TEST(test_writing_dil_alpha_re_references_the_air_fraction);
    RUN_TEST(test_a_whole_block_write_does_not_lose_the_calibration);
    RUN_TEST(test_an_unrecoverable_alpha_refuses_rather_than_inventing);
    RUN_TEST(test_v4_migration_keeps_the_air_point);
    RUN_TEST(test_clip_detection);
    RUN_TEST(test_fault_latch_preserves_a_one_cycle_event);
    RUN_TEST(test_fault_latch_refreshes_its_window_on_every_occurrence);
    RUN_TEST(test_fault_latch_is_monotonic_in_severity);
    RUN_TEST(test_fault_latch_only_holds_transient_bits);
    RUN_TEST(test_fault_latch_survives_the_uptime_wrap);
    RUN_TEST(test_fault_latch_never_hides_a_current_fault);
    RUN_TEST(test_validity_matrix);
    RUN_TEST(test_snapshot_is_invalid_before_the_first_sample);
    RUN_TEST(test_vapour_table_from_the_spec);
    RUN_TEST(test_dry_air_correction_is_exactly_a_no_op);
    RUN_TEST(test_calibration_in_moist_air_rescales_k);
    RUN_TEST(test_bench_humidity_step_no_longer_moves_the_channel);
    RUN_TEST(test_vapour_correction_fails_closed);
    RUN_TEST(test_vapour_correction_is_monotonic);
    RUN_TEST(test_vapour_correction_is_bounded_not_infinite);
    RUN_TEST(test_pressure_and_air_fraction_registers_are_bounded);
    RUN_TEST(test_o2_comp_validity_is_data_age_not_the_sht_fault_bit);
    RUN_TEST(test_v2_migration_keeps_the_probe_reachable);
    RUN_TEST(test_v2_migration_falls_back_to_defaults_when_it_cannot_be_trusted);
    RUN_TEST(test_equal_pressures_change_nothing);
    RUN_TEST(test_unknown_calibration_pressure_is_no_correction_not_a_divide);
    RUN_TEST(test_pressure_normalisation_has_the_right_sign_and_size);
    RUN_TEST(test_cal_pressure_register_is_bounded);
    RUN_TEST(test_a_pulse_gap_is_bridged_and_a_dead_sensor_is_not);
    RUN_TEST(test_the_o2_verdict_freeze_cannot_drop_a_state_fault);
    RUN_TEST(test_a_fresh_reading_is_never_overridden_by_the_cache);
    RUN_TEST(test_p_sat_has_exactly_one_implementation);
    RUN_TEST(test_dewpoint_reference_points);
    RUN_TEST(test_dewpoint_refuses_impossible_humidity);
    RUN_TEST(test_dew_margin_sign);
    RUN_TEST(test_heater_healthy_input_actually_heats);
    RUN_TEST(test_every_interlock_independently_forces_zero);
    RUN_TEST(test_unevaluable_input_is_off_not_midrange);
    RUN_TEST(test_duty_is_monotonic_in_humidity);
    RUN_TEST(test_duty_clamp_binds);
    RUN_TEST(test_dt_clamp_binds_and_has_hysteresis);
    RUN_TEST(test_tip_limit_is_below_the_hardware_alert);
    RUN_TEST(test_integrator_cannot_wind_up_while_clamped);
    RUN_TEST(test_loop_reaches_setpoint_in_steady_state);
    RUN_TEST(test_runaway_does_not_false_positive_on_cold_start);
    RUN_TEST(test_runaway_latches_on_uncommanded_heat_and_stays_latched);
    RUN_TEST(test_runaway_needs_the_full_window);
    RUN_TEST(test_runaway_is_not_evaluated_when_we_cannot_drive);
    RUN_TEST(test_setpoint_default_respects_the_cell_humidity_rating);
    RUN_TEST(test_die_temp_reads_the_calibration_point);
    RUN_TEST(test_die_temp_rejects_corrupt_calibration);
    RUN_TEST(test_die_temp_accepts_the_whole_datasheet_envelope);
    RUN_TEST(test_die_temp_is_monotonic_and_does_not_wrap_at_the_tails);
    RUN_TEST(test_die_temp_keeps_the_cold_end_the_part_is_rated_for);
    RUN_TEST(test_die_temp_rejects_impossible_conversion_inputs);
    RUN_TEST(test_die_temp_scales_with_the_supply_it_actually_ran_at);
    RUN_TEST(test_die_temp_band_is_the_datasheet_not_a_remembered_one);
    RUN_TEST(test_pwm_ceiling_is_a_thermal_limit_not_a_range);
    RUN_TEST(test_die_runaway_threshold_brackets_the_measured_evidence);
    RUN_TEST(test_runaway_sees_a_stuck_fet_through_the_die);
    RUN_TEST(test_runaway_die_path_does_not_false_positive_at_rest);
    RUN_TEST(test_runaway_references_are_independent);
    RUN_TEST(test_runaway_without_any_reference_is_unevaluable_not_ok);
    RUN_TEST(test_persistent_tip_setpoint_needs_its_own_consent);
    RUN_TEST(test_persistent_tip_setpoint_drives_towards_its_target);
    RUN_TEST(test_persistent_tip_loop_does_not_need_humidity);
    RUN_TEST(test_persistent_tip_loop_still_honours_the_dt_clamp);
    RUN_TEST(test_persistent_tip_loop_still_needs_a_chamber_reading);
    RUN_TEST(test_the_bench_override_outranks_a_stored_setpoint);
    RUN_TEST(test_a_v7_record_does_not_arm_a_temperature_loop);
    RUN_TEST(test_tip_setpoint_and_consent_are_bounded_on_the_wire);
    RUN_TEST(test_override_drives_open_loop_with_no_humidity);
    RUN_TEST(test_override_ignores_the_dt_clamp);
    RUN_TEST(test_disarming_does_not_inherit_a_stale_dt_clamp);
    RUN_TEST(test_override_is_clamped_by_max_duty);
    RUN_TEST(test_override_does_not_bypass_the_hardware_interlocks);
    RUN_TEST(test_override_cannot_clear_a_latched_runaway);
    RUN_TEST(test_override_does_not_latch_runaway_on_external_heat);
    RUN_TEST(test_heater_test_registers_are_volatile_and_magic_gated);
    RUN_TEST(test_a_rejected_heater_test_frame_changes_nothing);
    RUN_TEST(test_the_heater_test_block_is_not_part_of_the_config);
    RUN_TEST(test_the_heater_test_block_does_not_shadow_the_updater);
    RUN_TEST(test_the_tip_thresholds_form_a_ladder);
    RUN_TEST(test_zeroing_the_gains_stops_the_heater);
    RUN_TEST(test_p_only_tuning_stays_legal);
    RUN_TEST(test_rearming_does_not_inherit_the_previous_integral);
    RUN_TEST(test_arming_cannot_erase_runaway_evidence);
    RUN_TEST(test_a_continuously_armed_override_still_suppresses);
    RUN_TEST(test_autonomous_heating_needs_consent);
    RUN_TEST(test_the_bench_override_does_not_need_consent);
    RUN_TEST(test_consent_is_never_carried_across_a_migration);
    RUN_TEST(test_tip_setpoint_converges_and_holds);
    RUN_TEST(test_tip_setpoint_asks_for_more_duty_when_colder);
    RUN_TEST(test_the_integrator_does_not_leak_between_loops);
    RUN_TEST(test_tip_mode_still_obeys_every_hardware_interlock);
    RUN_TEST(test_the_setpoint_must_stay_below_the_clamp);
    RUN_TEST(test_the_test_block_comes_up_meaning_open_loop);
    RUN_TEST(test_a_rejected_setpoint_frame_changes_no_register);
    RUN_TEST(test_cmd_result_reads_none_before_any_command);
    RUN_TEST(test_calibrate_and_save_defers_the_commit);
    RUN_TEST(test_a_later_commit_frame_also_waits_for_a_pending_cal);
    RUN_TEST(test_a_commit_on_its_own_is_not_deferred);
    RUN_TEST(test_a_commit_outcome_never_clobbers_the_cal_outcome);
    RUN_TEST(test_cmd_result_sits_outside_the_published_decoder_block);
    RUN_TEST(test_tmp117_rejects_a_reading_outside_the_rating);
    RUN_TEST(test_zero_point_is_an_offset_not_a_slope);
    RUN_TEST(test_a_zero_at_or_above_the_air_point_is_unevaluable);
    RUN_TEST(test_a_negative_zero_is_accepted);
    RUN_TEST(test_config_refuses_an_implausible_stored_zero);
    RUN_TEST(test_cal_state_reports_an_unfinished_commissioning);
    RUN_TEST(test_v5_migration_keeps_everything_and_adds_no_zero);
    RUN_TEST(test_runaway_does_not_latch_on_one_hot_sample);
    RUN_TEST(test_runaway_latches_on_sustained_uncommanded_heat);
    RUN_TEST(test_runaway_discards_evidence_across_a_blind_gap);
    RUN_TEST(test_tempco_register_refuses_an_absurd_coefficient);
    RUN_TEST(test_a_corrupt_flash_tempco_is_refused_too);
    RUN_TEST(test_the_gain_guard_refuses_only_sign_and_nonfinite);
    RUN_TEST(test_the_uncalibrated_nominal_matches_the_tia_headroom);
    RUN_TEST(test_a_clean_frame_completes_at_the_gap);
    RUN_TEST(test_a_line_error_poisons_the_whole_frame);
    RUN_TEST(test_the_poison_lasts_exactly_one_frame);
    RUN_TEST(test_an_overlong_frame_saturates_rather_than_overruns);
    RUN_TEST(test_a_ready_frame_is_never_overwritten);
    RUN_TEST(test_an_unbounded_cal_temp_defeats_the_tempco_bound);
    RUN_TEST(test_writing_a_zero_point_marks_it_taken);
    RUN_TEST(test_a_v5_record_with_a_now_illegal_tempco_is_not_thrown_away);
    RUN_TEST(test_a_v5_record_with_an_absurd_cal_temp_drops_the_air_point);
    RUN_TEST(test_runaway_sees_heat_under_a_low_commanded_duty);
    RUN_TEST(test_the_isr_and_the_tested_state_machine_are_one);
    RUN_TEST(test_afe_die_temperature_follows_the_datasheet_table);
    RUN_TEST(test_the_cell_bias_window_catches_an_open_potentiostat);
    RUN_TEST(test_the_bias_guard_is_gated_on_as_built_wiring);
    RUN_TEST(test_the_rev_a_divider_scaling);
    RUN_TEST(test_the_wire_version_tracks_the_wire_contract);
    RUN_TEST(test_cell_current_is_the_departure_from_the_internal_zero);
    RUN_TEST(test_cell_current_keeps_its_sign);
    RUN_TEST(test_cell_current_is_ratiometric_in_vref);
    RUN_TEST(test_the_chamber_speaks_for_the_gas_not_the_heated_tip);
    RUN_TEST(test_raw_current_saturates_to_its_sentinel);
    RUN_TEST(test_a_railed_conversion_encodes_as_a_believable_air_current);
    RUN_TEST(test_settle_restarts_count_only_real_restarts);
    RUN_TEST(test_the_newer_config_record_wins);
    RUN_TEST(test_the_config_choice_survives_a_sequence_wrap);
    RUN_TEST(test_a_store_never_overwrites_the_live_record);
    RUN_TEST(test_a_serial_change_arms_probation_and_keeps_the_old_settings);
    RUN_TEST(test_probation_confirms_on_one_frame_and_decides_once);
    RUN_TEST(test_probation_reverts_when_no_frame_arrives);
    RUN_TEST(test_probation_survives_a_millisecond_wrap);
    RUN_TEST(test_probation_survives_a_frame_counter_wrap);
    RUN_TEST(test_a_second_change_keeps_the_first_fallback);
    RUN_TEST(test_a_commit_riding_a_serial_change_waits_for_it);
    RUN_TEST(test_a_commit_with_no_serial_change_is_not_delayed);
    RUN_TEST(test_the_commit_gate_is_the_only_way_in);
    RUN_TEST(test_writing_a_serial_register_its_own_value_changes_nothing);
    RUN_TEST(test_apply_confirmed_promotes_the_waiting_commit);
    RUN_TEST(test_apply_revert_restores_only_the_three_fields);
    RUN_TEST(test_a_revert_fails_a_commit_in_either_queue);
    RUN_TEST(test_apply_is_a_no_op_while_the_probation_is_undecided);
    RUN_TEST(test_transport_record_round_trips);
    RUN_TEST(test_transport_record_rejects_what_it_should);
    RUN_TEST(test_transport_best_takes_the_newer_page);
    RUN_TEST(test_loader_keeps_the_address_across_a_layout_bump);
    RUN_TEST(test_a_downgrade_does_not_resurrect_a_stale_block);
    RUN_TEST(test_the_transport_block_clears_the_config_record);
#if O2P_DEBUG_ENABLE
    RUN_TEST(test_peek_mailbox_bounds_and_alignment);
    RUN_TEST(test_dmbox_validation_and_opcodes);
    RUN_TEST(test_crash_mailbox_read_and_clear);
#else
    RUN_TEST(test_debug_mailboxes_disabled);
#endif
    return UNITY_END();
}
