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
#include "config_flash.h"
#include "config_migrate.h"
#include "die_temp.h"
#include "faults.h"
#include "gpio_diag.h"
#include "hw_caps.h"
#include "hw_contract.h"
#include "heater.h"
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

#include <stdio.h>

static o2p_regmap_t rm;
static o2p_mb_handlers_t handlers;

void setUp(void)
{
    o2p_regmap_init(&rm);
    handlers.read = o2p_regmap_read;
    handlers.write = o2p_regmap_write;
    handlers.ctx = &rm;
}
void tearDown(void)
{
#if O2P_DEBUG_ENABLE
    /* A peek test that fails mid-way longjmps past its own cleanup; without
     * this, its fake memory would answer every later test's peeks. */
    o2p_peek_host_read = NULL;
    o2p_peek_host_irq_depth = 0;
    o2p_peek_host_dst_addr = NULL;
    o2p_peek_host_parity_reset();
#endif
}

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
     * ZERO in the firmware because no sourced figure exists (DS-0637 Issue 1
     * and Issue 2 both carry a chart; neither is digitised), so this test also
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
    /* I2C_FAIL_SHT used to be raised for the SHT45's own SCHEDULED de-creep
     * pulse as well as for a dead sensor, so using it as O2_COMP's validity
     * criterion blanked the primary oxygen channel three times a day and
     * labelled scheduled maintenance a bus failure. The criterion is the AGE
     * of the chamber reading instead - see the cache tests below - and this
     * pins the mask so the bit cannot quietly come back.
     *
     * Since 2026-09-09 the mask does not raise the bit either; that half is
     * pinned by test_a_scheduled_mask_is_not_a_fault below. Both halves are
     * needed: this one keeps a REAL SHT45 failure from blanking O2_COMP, that
     * one keeps a scheduled mask from being reported as a failure at all. */
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
    in.chamber_fresh = true;     /* measured this cycle, not bridged */
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
    /* Since 0x0010 the block carries annotation bits: this drives the RH
     * loop (no stored tip setpoint), so TIP_DISARMED rides along. The
     * baseline's point is that no REFUSAL bit is set - assert the exact
     * word, not "nonzero would be fine". */
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED, out.block);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);
}

static void test_a_cold_dry_probe_reports_idle_not_nothing(void)
{
    /* 0x0010 (audit F5): duty 0 with no refusal must still SAY something.
     * The RH loop in command with no demand is an answer - and a cold probe
     * next to HEATER_BLOCK = 0 was indistinguishable on the bus from a
     * fault that failed to raise (tonight's "heater again blocked"
     * confusion, 2026-09-10). IDLE names the state; TIP_DISARMED names the
     * law in command. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_healthy();
    in.rh_x100 = 4000u;   /* dry: error <= 0, the loop wants no heat */
    o2p_heater_out_t out;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_IDLE | O2P_HB_TIP_DISARMED, out.block);
}

static void test_interlocks_refuse_blind_or_annotate_by_law(void)
{
    /* RENAMED AND RE-PINNED 2026-09-11 (Fab's per-law ruling: a sensor bit
     * may blind only the law whose control quantity it is). The old name
     * ("every interlock independently forces zero") stopped being true:
     * with the RH law in command, NO_TIP and NO_CHAMBER are ADVISORY - the
     * tip only feeds TIP_LIMIT, the chamber only feeds DT_LIMIT - so they
     * annotate while the loop regulates. What forces what, per the ruling:
     *   hard bits (not compiled, config off, tip limit, dt limit, pin
     *     integrity) force zero, always;
     *   the law's own control-sensor loss (NO_RH here) and SAFETY (founding
     *     membership, untouched) force the BLIND path - at the blind duty
     *     when the die gate permits it, zero when it does not;
     *   advisory losses annotate and regulate.
     * The die is stated at 27.00 C, under the gate, so the blind cells'
     * 50 % is the die gate PERMITTING it - hin_healthy()'s 57.20 C used to
     * make the same cells read zero by accident, which is what the
     * reviewer caught. */
    o2p_heater_cfg_t cfg = hcfg_default();      /* the RH law: no tip setpoint */
    o2p_heater_out_t out;

    struct { const char *name; uint16_t bit; uint16_t duty;
             uint16_t extra; int kind; } cases[] = {
        /* kind 0: hard refusal, duty 0. 1: blind path, die-gated 50 %.
         * 2: advisory annotation, the loop regulates. */
        {"not compiled",   O2P_HB_NOT_COMPILED,   0u, 0u, 0},
        {"config off",     O2P_HB_CONFIG_OFF,     0u, 0u, 0},
        {"safety",         O2P_HB_SAFETY,         O2P_HEATER_BLIND_DUTY_X100, O2P_HB_BLIND, 1},
        {"no rh",          O2P_HB_NO_RH,          O2P_HEATER_BLIND_DUTY_X100, O2P_HB_BLIND, 1},
        {"no tip",         O2P_HB_NO_TIP,         0u, 0u, 2},
        {"no chamber",     O2P_HB_NO_CHAMBER,     0u, 0u, 2},
        {"tip limit",      O2P_HB_TIP_LIMIT,      0u, 0u, 0},
        {"dt limit",       O2P_HB_DT_LIMIT,       0u, 0u, 0},
        {"pin integrity",  O2P_HB_PIN_INTEGRITY,  0u, 0u, 0},
    };

    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t c = cfg;
        o2p_heater_in_t in = hin_healthy();
        in.t_die_c100 = 2700;   /* stated: under the gate, deliberately */

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
        default:                   in.pin_integrity_ok = false; break;
        }

        o2p_heater_ctl_step(&st, &c, &in, 0u, &out);
        TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].bit) != 0u,
                                 cases[i].name);
        if (cases[i].kind == 2u) {
            TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
                "an advisory sensor loss must annotate, not stop the loop");
            TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block & O2P_HB_BLIND,
                cases[i].name);
        } else {
            TEST_ASSERT_EQUAL_UINT16_MESSAGE(cases[i].duty, out.duty_x100,
                                             cases[i].name);
            if (cases[i].extra != 0u) {
                TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].extra) != 0u,
                                         cases[i].name);
            }
        }
    }
}

static void test_supply_fault_annotates_but_does_not_veto(void)
{
    /* 2026-09-11, Fab's order: the supply veto is REMOVED. It was
     * inconsistent - blind_duty() drove 50 % through the same rail fault
     * with no sensors at all, so working sensors earned LESS heating than
     * none - and the heater is <1 W and cannot start a fire. What is true
     * now: identical inputs give identical duty regardless of supply_ok,
     * and HEATER_BLOCK carries O2P_HB_SUPPLY as an annotation so the
     * register still tells the truth about the rail. */
    o2p_heater_state_t st_ok, st_bad;
    o2p_heater_ctl_reset(&st_ok);
    o2p_heater_ctl_reset(&st_bad);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in_ok = hin_healthy();
    o2p_heater_in_t in_bad = hin_healthy();
    in_bad.supply_ok = false;
    o2p_heater_out_t out_ok, out_bad;
    o2p_heater_ctl_step(&st_ok, &cfg, &in_ok, 0u, &out_ok);
    o2p_heater_ctl_step(&st_bad, &cfg, &in_bad, 0u, &out_bad);
    TEST_ASSERT_EQUAL_UINT16(out_ok.duty_x100, out_bad.duty_x100);
    TEST_ASSERT_TRUE_MESSAGE((out_bad.block & O2P_HB_SUPPLY) != 0u,
                              "the rail fault is still reported");
    TEST_ASSERT_EQUAL_UINT16(0u, out_ok.block & O2P_HB_SUPPLY);
}

static void test_unevaluable_control_quantity_blinds_not_midranges(void)
{
    /* RENAMED AND RE-PINNED 2026-09-11 (Fab's per-law ruling). The old
     * premise ("every combination of missing sensor must be OFF") stopped
     * being true: with the RH law in command, a missing TIP or CHAMBER is
     * an advisory loss - the loop keeps answering, with the miss visible
     * in HEATER_BLOCK. What the guard-checklist rule still means, and what
     * this test now pins: a law missing its OWN control quantity (RH here)
     * never reads as a comfortable duty - it takes the blind path, at the
     * blind duty while the die gate permits (27.00 C, stated deliberately
     * instead of hin_healthy()'s 57.20 C, which used to make these cells
     * read zero by accident) - and every mask with a miss reports
     * SOMETHING in HEATER_BLOCK. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_out_t out;
    for (unsigned mask = 0u; mask < 8u; mask++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_in_t in = hin_healthy();
        in.t_die_c100 = 2700;   /* stated: under the blind gate */
        if (mask & 1u) { in.rh_valid = false; }
        if (mask & 2u) { in.tip_valid = false; }
        if (mask & 4u) { in.chamber_valid = false; }
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        if (mask == 0u) {
            TEST_ASSERT_TRUE(out.duty_x100 > 0u);   /* 95 % vs 85 %: demand */
            continue;
        }
        TEST_ASSERT_TRUE_MESSAGE(out.block != 0u,
            "every missing-sensor mask must report something");
        if (mask & 1u) {
            /* The control quantity itself is unevaluable: blind, never
             * midrange. */
            TEST_ASSERT_EQUAL_UINT16_MESSAGE(
                O2P_HEATER_BLIND_DUTY_X100, out.duty_x100,
                "a law missing its own control quantity goes blind");
            TEST_ASSERT_TRUE((out.block & O2P_HB_NO_RH) != 0u);
            TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
        } else {
            /* Advisory losses only: the loop regulates, misses visible. */
            TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
                "an advisory miss must not stop the loop");
            TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
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
    /* TIP_DISARMED rides along with the RH loop since 0x0010; no refusal
     * bit may be set in steady state. */
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED, out.block);
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

static void test_runaway_latches_on_uncommanded_heat_and_holds_while_it_persists(void)
{
    /* This test used to be ..._and_stays_latched, and asserted that "latched
     * means latched: a now-perfectly-healthy probe still refuses". That policy
     * was reversed on 2026-09-10, when an 80 C bath produced the die signature
     * with a healthy FET and disabled a working heater until reset - see
     * update_runaway() in heater_ctl.c for the evidence. What it protected is
     * kept, and is what this asserts: while the evidence persists the latch
     * holds, for as long as it persists, and a healthy interval shorter than a
     * full window does not release it. Release itself is covered by
     * test_runaway_releases_only_after_a_full_window_of_cleared_evidence. */
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

    uint32_t t = 0u;
    for (; t <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);

    /* The far tail: an hour of the same evidence, which is what a stuck FET
     * does. Monotonic - the verdict must not drift back as time passes. */
    for (uint32_t i = 0u; i < 3600u; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
        TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);
        TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) != 0u);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);

    /* A perfectly healthy probe with a full configuration, one sample short of
     * a window, still refuses. */
    o2p_heater_in_t healthy = hin_healthy();
    o2p_heater_cfg_t full = hcfg_default();
    for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
        o2p_heater_ctl_step(&st, &full, &healthy, t, &out);
        TEST_ASSERT_EQUAL_UINT16(0, out.duty_x100);
        TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) != 0u);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);
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

/* Latch through the die with the MEASURED stuck-FET separation (2026-09-04:
 * tip 56 C, die near 28 C). Leaves *t at the next free second. */
static void latch_through_die(o2p_heater_state_t *st,
                              const o2p_heater_cfg_t *cfg, uint32_t *t)
{
    o2p_heater_ctl_reset(st);
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = 4990;
    hot.t_die_c100 = (int16_t)(hot.t_tip_c100 - 2800);
    o2p_heater_out_t out;
    for (uint32_t i = 0u; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++, (*t)++) {
        o2p_heater_ctl_step(st, cfg, &hot, *t, &out);
    }
    TEST_ASSERT_TRUE(st->runaway_latched);
}

static void test_runaway_releases_only_after_a_full_window_of_cleared_evidence(void)
{
    o2p_heater_state_t st;
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    uint32_t t = 0u;
    latch_through_die(&st, &cfg, &t);

    /* Back at rest, both references valid and clear: tip-die -2.2 K, tip-ch
     * +1 K. One sample short of a window must not release. */
    o2p_heater_in_t rest = hin_healthy();
    for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) != 0u);
        TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);

    /* The full window releases... */
    o2p_heater_ctl_step(&st, &cfg, &rest, t++, &out);
    TEST_ASSERT_FALSE(st.runaway_latched);

    /* ...the heater is usable on the next decision... */
    o2p_heater_cfg_t full = hcfg_default();
    o2p_heater_ctl_step(&st, &full, &rest, t++, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_RUNAWAY) == 0u);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "a wet chamber must get heat again once released");

    /* ...and the detector is re-armed: the same evidence latches again. */
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = 4990;
    hot.t_die_c100 = (int16_t)(hot.t_tip_c100 - 2800);
    for (uint32_t i = 0u; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, &hot, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "a release must re-arm the detector, not retire it");
}

static void test_runaway_release_needs_every_reference_valid_and_clear(void)
{
    /* Guard checklist item 1, for the release: unevaluable is not OK. On Rev A
     * the chamber tracks the tip within 0.17 K whatever the FET is doing, so a
     * chamber-only "clear" would exonerate a stuck FET the moment the die
     * reading dropped out. Every case below must stay latched for three full
     * windows - which is the old latched-until-reset behaviour, and the right
     * fallback. */
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;

    for (unsigned c = 0u; c < 5u; c++) {
        o2p_heater_state_t st;
        uint32_t t = 0u;
        latch_through_die(&st, &cfg, &t);
        o2p_heater_in_t in = hin_healthy();
        const char *why = "";
        switch (c) {
        case 0u: in.die_valid = false;     why = "die lost";     break;
        case 1u: in.chamber_valid = false; why = "chamber lost"; break;
        case 2u: in.tip_valid = false;     why = "tip lost";     break;
        case 3u:
            /* Chamber clear, die still showing the stuck-FET separation. */
            in.t_tip_c100 = 5000;
            in.t_chamber_c100 = 4990;
            in.t_die_c100 = (int16_t)(in.t_tip_c100 - 2800);
            why = "die still hot";
            break;
        default:
            /* Valid for the clamp, bridged from the cache - not fresh. */
            in.chamber_fresh = false;
            why = "chamber bridged from cache";
            break;
        }
        for (uint32_t i = 0u; i < 3u * O2P_HEATER_RUNAWAY_WINDOW_S; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
        }
        TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched, why);
    }
}

static void test_runaway_release_restarts_on_a_marginal_sample_or_a_gap(void)
{
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    o2p_heater_in_t rest = hin_healthy();

    /* A sample INSIDE the hysteresis band - below the latch threshold, so it is
     * not evidence of runaway, but not far enough below it to count as clear -
     * restarts the window. This is what stops a reference hovering on its
     * threshold from releasing on dither. */
    o2p_heater_in_t marginal = hin_healthy();
    marginal.t_tip_c100 = 5000;
    marginal.t_chamber_c100 = 4990;
    marginal.t_die_c100 = (int16_t)(marginal.t_tip_c100 -
        (O2P_HEATER_RUNAWAY_DIE_K100 - O2P_HEATER_RUNAWAY_RELEASE_HYST_K100 / 2));
    {
        o2p_heater_state_t st;
        uint32_t t = 0u;
        latch_through_die(&st, &cfg, &t);
        for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        }
        o2p_heater_ctl_step(&st, &cfg, &marginal, t++, &out);
        for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        }
        TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
            "a hysteresis-band sample must restart the release window");
        o2p_heater_ctl_step(&st, &cfg, &rest, t++, &out);
        TEST_ASSERT_FALSE(st.runaway_latched);
    }

    /* A gap in observation restarts it too: an unobserved interval must not be
     * credited as clear, exactly as it is not credited as hot. */
    {
        o2p_heater_state_t st;
        uint32_t t = 0u;
        latch_through_die(&st, &cfg, &t);
        for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        }
        t += O2P_HEATER_RUNAWAY_MAX_GAP_S + 1u;
        o2p_heater_ctl_step(&st, &cfg, &rest, t++, &out);
        for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        }
        TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
            "a gap must restart the release window");
        o2p_heater_ctl_step(&st, &cfg, &rest, t++, &out);
        TEST_ASSERT_FALSE(st.runaway_latched);
    }
}

static void test_runaway_release_is_not_credited_across_an_invalid_sample(void)
{
    /* Found by review of eae463f. An unevaluable sample returned early without
     * touching the release window or its clock, so the next valid sample was
     * credited with the whole blind interval whenever it was under the 5 s gap
     * limit: 59 clear seconds, one sample with the tip invalid, one clear
     * sample, released. For LATCHING that credit errs toward latching; for
     * RELEASE it errs toward exoneration, so explicit invalidity resets it. */
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    o2p_heater_in_t rest = hin_healthy();

    for (unsigned c = 0u; c < 2u; c++) {
        o2p_heater_in_t blind = hin_healthy();
        if (c == 0u) {
            blind.tip_valid = false;
        } else {
            blind.chamber_valid = false;
            blind.die_valid = false;
        }
        o2p_heater_state_t st;
        uint32_t t = 0u;
        latch_through_die(&st, &cfg, &t);
        for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        }
        o2p_heater_ctl_step(&st, &cfg, &blind, t++, &out);
        o2p_heater_ctl_step(&st, &cfg, &rest, t++, &out);
        TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
            c == 0u ? "one tip-invalid sample must restart the release window"
                    : "one sample with both references invalid must restart it");
        /* ...and a full window is needed afterwards, from one second. */
        for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 2u; i++, t++) {
            o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
        }
        TEST_ASSERT_TRUE(st.runaway_latched);
        o2p_heater_ctl_step(&st, &cfg, &rest, t++, &out);
        TEST_ASSERT_FALSE(st.runaway_latched);
    }

    /* The pattern the review built: one valid clear sample every five seconds,
     * four explicitly invalid ones between. It used to add up to a release
     * from twelve observations. It must never release. */
    o2p_heater_state_t st;
    uint32_t t = 0u;
    latch_through_die(&st, &cfg, &t);
    o2p_heater_in_t blind = hin_healthy();
    blind.tip_valid = false;
    for (uint32_t i = 0u; i < 10u * O2P_HEATER_RUNAWAY_WINDOW_S; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, ((i % 5u) == 0u) ? &rest : &blind, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "sparse valid samples between invalid ones must not add up to a release");
}

static void test_runaway_release_does_not_count_a_bridged_chamber(void)
{
    /* Found by review of eae463f. main.c bridges the chamber temperature from
     * its cache for up to O2P_HEATER_CHAMBER_MAX_AGE_S and still passes
     * chamber_valid - right for the dT clamp. Counted toward release, it let a
     * dead SHT45 finish the window on its last reading: 20 s of real clear
     * evidence, 40 s of cache, released. */
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_out_t out;
    o2p_heater_in_t fresh = hin_healthy();
    o2p_heater_in_t bridged = hin_healthy();
    bridged.chamber_fresh = false;

    o2p_heater_state_t st;
    uint32_t t = 0u;
    latch_through_die(&st, &cfg, &t);
    for (uint32_t i = 0u; i < 20u; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, &fresh, t, &out);
    }
    for (uint32_t i = 0u; i < 3u * O2P_HEATER_RUNAWAY_WINDOW_S; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, &bridged, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "a cached chamber temperature must not complete a release");

    /* Fresh again: a full window from zero, not a resumption of the 20 s. */
    for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, t++) {
        o2p_heater_ctl_step(&st, &cfg, &fresh, t, &out);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);
    o2p_heater_ctl_step(&st, &cfg, &fresh, t++, &out);
    TEST_ASSERT_FALSE(st.runaway_latched);
}

/* 2026-09-10, probe 3 on the bench, build 75162fa: about 80 C water poured
 * into the jar at roughly 11:00 UTC with the RH loop running. One sample per
 * minute from VictoriaMetrics (gas_t_tip_c, gas_t_die_c, gas_t_chamber_c,
 * gas_rh_chamber_pct, probe="3"). The firmware runs at 1 Hz and these are
 * interpolated linearly, which cannot reproduce the die's 0.29 K/LSB dither -
 * so every instant asserted below keeps at least 20 s of margin from where the
 * interpolation puts the transition. */
static const struct {
    uint32_t s;
    int16_t  tip, die, ch;
    uint16_t rh;
} k_bath_2026_09_10[] = {
    {   0u, 2066, 2245, 2054, 7678u },   /* 11:00:04 at rest                  */
    {  60u, 2196, 2245, 2196, 7757u },   /* 11:01:04 heat arrives, duty 0     */
    { 121u, 2445, 2361, 2490, 8106u },   /* 11:02:05 chamber AHEAD of tip     */
    { 181u, 2817, 2419, 2897, 8723u },   /* 11:03:05 RH over 85 %, 5.00 %    */
    { 241u, 3370, 2535, 3442, 9089u },   /* 11:04:05                          */
    { 302u, 3708, 2710, 3764, 9192u },   /* 11:05:06 tip-die  9.98 K          */
    { 362u, 3957, 2913, 3993, 9211u },   /* 11:06:06 tip-die 10.44 K, clear   */
    { 423u, 3996, 2971, 4028, 9224u },   /* 11:07:07 faults 0x8100: LATCHED   */
    { 483u, 3935, 3116, 3968, 9354u },   /* 11:08:07 tip-die  8.19 K          */
    { 544u, 3962, 3232, 3991, 9490u },   /* 11:09:08                          */
    { 604u, 4000, 3232, 4024, 9595u },   /* 11:10:08                          */
    { 665u, 4037, 3319, 4054, 9654u },   /* 11:11:09                          */
};

static int32_t lerp_i32(int32_t a, int32_t b, uint32_t num, uint32_t den)
{
    return a + (int32_t)(((int64_t)(b - a) * (int64_t)num) / (int64_t)den);
}

static void bath_2026_09_10_at(uint32_t s, o2p_heater_in_t *in)
{
    const size_t n = sizeof(k_bath_2026_09_10) / sizeof(k_bath_2026_09_10[0]);
    size_t i = 0u;
    while (i + 2u < n && s >= k_bath_2026_09_10[i + 1u].s) {
        i++;
    }
    uint32_t den = k_bath_2026_09_10[i + 1u].s - k_bath_2026_09_10[i].s;
    uint32_t num = s - k_bath_2026_09_10[i].s;
    if (num > den) {
        num = den;
    }
    in->t_tip_c100 = (int16_t)lerp_i32(k_bath_2026_09_10[i].tip,
                                       k_bath_2026_09_10[i + 1u].tip, num, den);
    in->t_die_c100 = (int16_t)lerp_i32(k_bath_2026_09_10[i].die,
                                       k_bath_2026_09_10[i + 1u].die, num, den);
    in->t_chamber_c100 = (int16_t)lerp_i32(k_bath_2026_09_10[i].ch,
                                           k_bath_2026_09_10[i + 1u].ch, num, den);
    in->rh_x100 = (uint16_t)lerp_i32(k_bath_2026_09_10[i].rh,
                                     k_bath_2026_09_10[i + 1u].rh, num, den);
}

static void test_the_80c_bath_of_2026_09_10_latches_and_then_releases(void)
{
    /* The fixture is the real event, run through the shipping controller, so
     * the test is calibrated against a known-bad case rather than one written
     * to match the code. It must first REPRODUCE what the probe did - the loop
     * pinned at 5.00 %, not latched while tip-die was still under 10 K, latched
     * by 11:07:07 - or nothing it says about the fix means anything. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    /* Not in telemetry. Inferred from the published duty sitting at exactly
     * 5.00 % for four minutes against RH 7-9 points above setpoint. */
    cfg.max_duty_x100 = 500u;
    o2p_heater_in_t in = hin_healthy();
    o2p_heater_out_t out;

    bool latched_302 = true, latched_423 = false;
    bool latched_483 = false, latched_544 = true;
    uint16_t duty_302 = 0u;
    for (uint32_t s = 0u; s <= 665u; s++) {
        bath_2026_09_10_at(s, &in);
        o2p_heater_ctl_step(&st, &cfg, &in, 1000u + s, &out);
        switch (s) {
        case 302u: latched_302 = st.runaway_latched; duty_302 = out.duty_x100; break;
        case 423u: latched_423 = st.runaway_latched; break;
        case 483u: latched_483 = st.runaway_latched; break;
        case 544u: latched_544 = st.runaway_latched; break;
        default: break;
        }
    }

    /* Reproduction. */
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(500u, duty_302,
        "11:05:06 - the loop was pinned at its 5.00 % cap");
    TEST_ASSERT_FALSE_MESSAGE(latched_302,
        "11:05:06 - tip-die was 9.98 K and the probe was not latched");
    TEST_ASSERT_TRUE_MESSAGE(latched_423,
        "11:07:07 - the probe published HEATER_RUNAWAY");

    /* The fix. */
    TEST_ASSERT_TRUE_MESSAGE(latched_483,
        "11:08:07 - still inside the release window");
    TEST_ASSERT_FALSE_MESSAGE(latched_544,
        "11:09:08 - released once the die caught up");
    TEST_ASSERT_FALSE(st.runaway_latched);
    TEST_ASSERT_TRUE_MESSAGE((out.block & O2P_HB_RUNAWAY) == 0u,
        "11:11:09 - no runaway block");
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(500u, out.duty_x100,
        "11:11:09 - RH 96.5 %: the loop is heating again, at its cap");
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

    /* The release point must sit ABOVE the widest legitimate excursion, or a
     * probe back at rest could never release, and the hysteresis must span at
     * least two die LSBs (0.29 K each) or dither alone can chatter it. */
    TEST_ASSERT_TRUE(O2P_HEATER_RUNAWAY_DIE_K100 -
                     O2P_HEATER_RUNAWAY_RELEASE_HYST_K100 > 300);
    TEST_ASSERT_TRUE(O2P_HEATER_RUNAWAY_RELEASE_HYST_K100 >= 58);

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

/* A power cut BETWEEN the two writes of one commit must not split the probe's
 * identity, and the write ORDER is the only thing that makes that true.
 *
 * config_flash.c programs the configuration record first and the frozen
 * transport block second. A review on 2026-09-09 reported the opposite order
 * and called the resulting split Critical; the order in the code is the safe
 * one and the finding did not survive. But the property was guaranteed only by
 * a comment and by the sequencing of one `&&`, and the cost of getting it wrong
 * is a POTTED probe whose application answers at one identity and whose
 * recovery loader answers at another - i.e. a probe nobody can reach again.
 * So it gets a test, in both directions.
 *
 * The application always takes the highest-sequence VALID CONFIG RECORD; that
 * is modelled here as `app_addr`, because main.c's page walk does not compile
 * on the host. Only the loader's rule is exercised for real.
 *
 * WHAT THIS DOES NOT DO, measured rather than assumed: it does NOT catch the
 * write order being swapped. Verified 2026-09-09 by swapping the two
 * o2p_flash_program() calls in config_flash.c - the firmware still built and
 * all 212 host tests still passed. config_flash.c is not in env:native's
 * build_src_filter, so the PRODUCER of this invariant has no host coverage at
 * all; only the consumer does. Catching a swap needs config_flash.c compiled
 * for the host against a flash fake that can fail between the two programs.
 * Until then the order is guarded by a comment and by statement sequencing,
 * and this test documents WHY the order matters rather than enforcing it. */
/* The host flash fake lives in src/flash_hal_host.c so that every native test
 * links one copy of it; test_update pulls in config_flash.o too. */
void o2p_host_flash_reset(int fail_after);
int  o2p_host_flash_programs(void);
extern uint8_t o2p_host_flash[];

/* THE PRODUCER TEST. config_flash.c must program the CONFIGURATION RECORD
 * first and the transport block second; the reverse order strands a potted
 * probe whose application and recovery loader then answer at different Modbus
 * identities. Until 2026-09-09 that order was guarded by a comment and by the
 * sequencing of one `&&`: swapping the two calls built cleanly and passed
 * every test. This is the test that fails when they are swapped. */
static void test_the_commit_programs_the_config_record_before_the_block(void)
{
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    cfg.slave_addr = 22u;
    cfg.baud_code = O2P_BAUD_38400;

    /* Cut power after the FIRST program of the pair. Whatever reached flash is
     * what a loader and an application would find at the next boot. */
    o2p_host_flash_reset(1);
    (void)o2p_config_store(&cfg);      /* must report failure; checked below */

    /* Find the page that was being written: the one that is not all-erased. */
    int written = -1;
    for (uint8_t pg = CONFIG_PAGE_A; ; pg = CONFIG_PAGE_B) {
        const uint8_t *p = o2p_host_flash + (size_t)pg * O2P_FLASH_PAGE_BYTES;
        /* The WHOLE page, deliberately: if the block were programmed first
         * the record area would still read erased, and a scan limited to the
         * record would report "nothing was written" instead of the ordering
         * failure this test exists to name. */
        bool erased = true;
        for (size_t i = 0; i < O2P_FLASH_PAGE_BYTES; i++) {
            if (p[i] != 0xFFu) { erased = false; break; }
        }
        if (!erased) { written = (int)pg; }
        if (pg == CONFIG_PAGE_B) break;
    }
    TEST_ASSERT_MESSAGE(written >= 0, "the cut left nothing at all in flash");

    const uint8_t *page = o2p_host_flash +
                          (size_t)written * O2P_FLASH_PAGE_BYTES;

    /* THE ASSERTION. After exactly one successful program, the CONFIGURATION
     * RECORD must be the thing that landed and the transport block must still
     * be erased. Swap the two o2p_flash_program() calls in config_flash.c and
     * this inverts: the block is present and the record is not, which is the
     * orphaned-block state that splits the two identities. */
    config_record_t rec;
    memcpy(&rec, page, sizeof(rec));
    TEST_ASSERT_EQUAL_HEX32_MESSAGE(CONFIG_MAGIC, rec.magic,
        "the configuration record must be programmed FIRST - a transport "
        "block written before it is orphaned by a power cut and strands the "
        "probe across two Modbus identities");

    const uint8_t *blk = page + O2P_TRANSPORT_OFFSET;
    bool block_erased = true;
    for (size_t i = 0; i < sizeof(o2p_transport_record_t); i++) {
        if (blk[i] != 0xFFu) { block_erased = false; break; }
    }
    TEST_ASSERT_TRUE_MESSAGE(block_erased,
        "the transport block must be programmed SECOND");

    /* And a complete commit still works, so the ordering check above is not
     * passing because the store is simply broken. */
    o2p_host_flash_reset(-1);
    TEST_ASSERT_TRUE(o2p_config_store(&cfg));
}

static void test_a_torn_commit_keeps_loader_and_application_on_one_identity(void)
{
    o2p_transport_record_t page_a, page_b;
    o2p_transport_t got;

    /* THE REAL ORDER. Page A holds a complete older commit (seq 8, addr 3).
     * Page B's configuration record landed at seq 9 with the new identity
     * (addr 22) and power was lost before its transport block was programmed,
     * so B's block is erased flash. */
    o2p_transport_build(&page_a, 8u, 3u, O2P_BAUD_9600, O2P_PARITY_EVEN);
    memset(&page_b, 0xFF, sizeof(page_b));

    const o2p_transport_t cfg_new = { 22u, O2P_BAUD_38400, O2P_PARITY_EVEN };
    const uint8_t app_addr = 22u;   /* the app reads B: highest valid config */

    TEST_ASSERT_TRUE(o2p_transport_select(&page_a, &page_b, true, 9u,
                                          &cfg_new, &got));
    /* The loader must reach the SAME identity the application will answer on.
     * This is the assertion that matters; the specific value is secondary. */
    TEST_ASSERT_EQUAL_UINT8(app_addr, got.slave_addr);
    TEST_ASSERT_EQUAL_UINT8(O2P_BAUD_38400, got.baud_code);

    /* THE REVERSE ORDER, as the known-bad. Had the transport block been
     * programmed first, the cut would leave B with a valid block at seq 9 and
     * NO valid configuration record - so the loader follows the block to
     * addr 22 while the application falls back to A's record at addr 3. The
     * two disagree, and the probe is unreachable on whichever one is tried.
     *
     * Asserting the SPLIT here is deliberate: it is the evidence for why
     * config_flash.c programs the record first, and it fails the day someone
     * swaps those two statements. */
    o2p_transport_build(&page_b, 9u, 22u, O2P_BAUD_38400, O2P_PARITY_EVEN);
    const o2p_transport_t cfg_old = { 3u, O2P_BAUD_9600, O2P_PARITY_EVEN };
    const uint8_t app_addr_after_reverse_cut = 3u;   /* app falls back to A */

    TEST_ASSERT_TRUE(o2p_transport_select(&page_a, &page_b, true, 8u,
                                          &cfg_old, &got));
    TEST_ASSERT_EQUAL_UINT8(22u, got.slave_addr);
    TEST_ASSERT_TRUE(got.slave_addr != app_addr_after_reverse_cut);
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
    /* RH consent is NEVER carried, on any migration path (audit F1,
     * 2026-09-10). */
    TEST_ASSERT_EQUAL_UINT16(0u, out.heater_rh_consent);

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
 * channels are masked for O2P_SHT_RECOVERY_MS afterwards - 350 s since the
 * recovery was actually measured on 2026-09-07, having been a 30 s guess
 * before that. With dry-basis O2_COMP depending on
 * RH, that used to blank the primary oxygen channel three times a day and
 * label the gap I2C_FAIL_SHT - scheduled maintenance reported as a bus
 * failure. The bridge is bounded by O2P_RH_MAX_AGE_S, and the bound is what
 * keeps a dead sensor from being bridged forever.
 */

static void test_this_board_cannot_be_commanded_transceiver_deaf(void)
{
    /* The native suite is built with -DO2P_BOARD_REV_A (platformio.ini), so
     * these are the capabilities of the FABRICATED board on the bench, not of
     * the schematic. That is the whole point of the split in gen_hw_caps.py:
     * the drawing moved to a /RE on its own pin on 2026-09-07, and the copper
     * did not.
     *
     * So this test asserts 0. It is not describing a defect to be fixed in
     * software - it pins the fact that the firmware KNOWS the difference, which
     * is what stops o2p_modbus_rx_standby(true) from reporting a 700 uA saving
     * that the board cannot make. When the Rev A rework lands
     * (docs/REWORK-RS485-RE-SPLIT.md), gen_hw_caps.py is re-pinned to the
     * reworked netlist and this test is the one that has to be edited - which
     * is the intended friction, not an oversight. */
    TEST_ASSERT_EQUAL_INT(0, O2P_HW_RS485_RE_ON_ITS_OWN_PIN);

    /* No R45 either, and on THIS revision that is correct rather than a
     * fitting error: with /RE shorted to DE there is nothing for it to pull
     * down, and R7 on the shared net already holds both low through reset. */
    TEST_ASSERT_EQUAL_INT(0, O2P_HW_RS485_RE_PASSIVE_PULLDOWN);

    /* The dependency that makes the pull-down predicate meaningful rather than
     * decorative: a board may not claim the passive default without the split
     * it is the passive default OF. Checked as an implication over both
     * revisions' actual values rather than on a fixture, because a hand-built
     * pair would be testing the rule I meant to write and not the one
     * gen_hw_caps.py emits. */
    TEST_ASSERT_TRUE(!O2P_HW_RS485_RE_PASSIVE_PULLDOWN ||
                     O2P_HW_RS485_RE_ON_ITS_OWN_PIN);

    /* And the pins the firmware drives are still two different pins. board_pins.h
     * already static-asserts this; restated here because the assert protects
     * against the SCHEMATIC tying them back together, while the capability above
     * protects against the BOARD never having split them. Those are different
     * failures and only one of them has ever happened. */
    TEST_ASSERT_TRUE(O2P_HW_NET_RS485_DE_PIN != O2P_HW_NET_RS485_RE_PIN);
}

static void test_a_stale_chamber_temperature_is_the_dominant_bridge_error(void)
{
    /* WHY O2P_RH_MAX_AGE_S IS 45 s AND NOT 400 s, computed rather than argued.
     *
     * The first version of this change raised the bound to 400 s so the cache
     * would outlast the 350 s de-creep mask, justified by a comment saying the
     * dry-basis correction is only mildly sensitive to RH. The RH half of that
     * was right and the conclusion was not: the cache carries the chamber
     * TEMPERATURE too, and temperature enters through p_sat(T), which is
     * exponential. At the 60-80 C this instrument exists to observe, a stale
     * temperature dominates by an order of magnitude.
     *
     * This runs the shipped conversion at a fixed cell current, changing only
     * the gas, so the numbers are the firmware's own and not a restatement. */
    o2p_cal_t cal = { .dil_alpha = 1.0f };
    o2p_gas_t air = gas_at(20.0f, 50.0f, 1013.25f);
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 100000, 2000, &air));
    cal.tempco_per_k = 0.0f;    /* isolate the dilution term */

    /* Helper shape: same current, same reported temperature, gas differs.
     *
     * 60 uA rather than the 100 uA air point, deliberately. The dilution term
     * DIVIDES by the dry fraction, so at 75 C and saturation a full-scale air
     * current is pushed past O2P_C_MAX (0.30, the cell's rated overload) and
     * the conversion refuses - a real guard firing on a fabricated input, not
     * a bug. Measuring the sensitivity needs a current that leaves headroom
     * for the correction being measured. */
    #define DRY_AT(t_c, rh_pct, out) do {                                   \
        o2p_gas_t g_ = gas_at((t_c), (rh_pct), 1013.25f);                   \
        TEST_ASSERT_EQUAL(O2P_OK,                                           \
            o2p_dry_fraction_from_current(&cal, 60000, 2000, &g_, &(out))); \
    } while (0)

    /* The de-creep artefact itself - 1.6 %RH low - is genuinely mild, which is
     * what the original comment got right. */
    float rh_true = 0.0f, rh_err = 0.0f;
    DRY_AT(60.0f, 100.0f, rh_true);
    DRY_AT(60.0f, 98.4f, rh_err);
    float rh_rel = (rh_err - rh_true) / rh_true;
    /* BOTH errors here make O2_COMP read LOW: a smaller p_w leaves a larger
     * dry fraction in the denominator. Signed, then bounded by magnitude. */
    TEST_ASSERT_TRUE(rh_rel < 0.0f);
    TEST_ASSERT_TRUE(-rh_rel < 0.01f);                   /* ~0.4 % at 60 C */

    /* A 5 K stale TEMPERATURE, humidity saturated throughout, is an order of
     * magnitude worse at the same point - and this is the error a long bridge
     * actually incurs, because the membrane heater stands down for the whole
     * mask, so the chamber is drifting while the cached value is in use. */
    float t_true = 0.0f, t_stale = 0.0f;
    DRY_AT(65.0f, 100.0f, t_true);
    DRY_AT(60.0f, 100.0f, t_stale);
    float t_rel = (t_stale - t_true) / t_true;
    TEST_ASSERT_TRUE(t_rel < 0.0f);                      /* reads LOW */
    TEST_ASSERT_TRUE(-t_rel > 0.05f);                    /* ~6.8 %, > 5 % */

    /* MONOTONIC IN THE DIRECTION THAT MATTERS: the further into the pile's
     * thermophilic range, the worse a stale temperature gets. A bound argued
     * from bench temperatures cannot be carried to the deployment.
     *
     * 70->75 C rather than 75->80: O2P_VAPOUR_T_MAX_C is 80.0 and the model
     * refuses AT the limit, so 80 C is not a point this firmware will convert.
     * The trend is what is being pinned, and it is already established well
     * inside the supported domain. */
    float hot_true = 0.0f, hot_stale = 0.0f;
    DRY_AT(75.0f, 100.0f, hot_true);
    DRY_AT(70.0f, 100.0f, hot_stale);
    float hot_rel = -((hot_stale - hot_true) / hot_true);
    TEST_ASSERT_TRUE(hot_rel > -t_rel);                  /* worse than at 60 C */
    TEST_ASSERT_TRUE(hot_rel > 0.10f);                   /* ~10.7 % at 70->75 C */

    /* And at bench temperature the same 5 K is nearly harmless, which is why
     * this error could be missed entirely on a bench and why the bound may not
     * be justified from one. */
    float b_true = 0.0f, b_stale = 0.0f;
    DRY_AT(27.0f, 100.0f, b_true);
    DRY_AT(22.0f, 100.0f, b_stale);
    float b_rel = -((b_stale - b_true) / b_true);
    TEST_ASSERT_TRUE(b_rel < 0.02f);
    #undef DRY_AT
}

static void test_a_scheduled_mask_is_not_a_fault(void)
{
    /* THE BUG, measured 2026-09-06 and -09-07 and recorded in
     * SHT-DECREEP-MASK-IS-TOO-SHORT.md: the de-creep mask raised I2C_FAIL_SHT,
     * so a maintenance action this firmware itself ordered was, at the Modbus
     * interface, indistinguishable from a dead humidity sensor - with I2C_ERRS
     * at 0 throughout, so the counter could not separate them either.
     *
     * These are the functions phase_sht() actually calls (main.c), not a
     * restatement of them, which is the only way this test can fail when the
     * shipping rule changes. */

    /* A mask AFTER A CLEAN PULSE reports nothing. It is not a failure and must
     * not read as one. */
    TEST_ASSERT_EQUAL_HEX16(0u, o2p_sht_phase_faults(true, false, false));
    TEST_ASSERT_EQUAL_HEX16(0u, o2p_sht_phase_faults(true, false, true));

    /* A mask entered because the PULSE ITSELF failed on the bus reports the
     * failure for the whole window. This is the case the first version of the
     * change silently lost: main.c masks whether the heater command succeeded
     * or not, so without this an observed I2C failure spends 350 s looking
     * exactly like healthy maintenance, and the next cycle that would have
     * "reported the SHT as failed" is itself inside the mask and never
     * reaches a measurement. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_I2C_FAIL_SHT,
                            o2p_sht_phase_faults(true, true, false));
    TEST_ASSERT_EQUAL_HEX16(O2P_F_I2C_FAIL_SHT,
                            o2p_sht_phase_faults(true, true, true));

    /* A sensor that did not answer still does, from the first failed
     * measurement - the property the change had to preserve. */
    TEST_ASSERT_EQUAL_HEX16(O2P_F_I2C_FAIL_SHT,
                            o2p_sht_phase_faults(false, false, false));
    TEST_ASSERT_EQUAL_HEX16(0u, o2p_sht_phase_faults(false, false, true));

    /* The window itself. Masked from the pulse until the constant expires,
     * clear on the tick after - and MONOTONIC in the direction that matters:
     * once the window has closed it must not reopen as the gap grows, or a
     * long-silent sensor would look like a permanent maintenance window. */
    const uint32_t t0 = 1234567u;
    TEST_ASSERT_TRUE(o2p_sht_masked(t0, t0));
    TEST_ASSERT_TRUE(o2p_sht_masked(t0 + O2P_SHT_RECOVERY_MS - 1u, t0));
    TEST_ASSERT_FALSE(o2p_sht_masked(t0 + O2P_SHT_RECOVERY_MS, t0));
    for (uint32_t dt = O2P_SHT_RECOVERY_MS; dt < O2P_SHT_RECOVERY_MS + 100000u;
         dt += 997u) {
        TEST_ASSERT_FALSE(o2p_sht_masked(t0 + dt, t0));
    }

    /* Across the 49-day o2p_millis() wrap, which is the case a naive
     * `now > pulse + span` gets wrong by masking for another 49 days. */
    const uint32_t near_wrap = 0xFFFFFF00u;
    TEST_ASSERT_TRUE(o2p_sht_masked(near_wrap + 1000u, near_wrap));
    TEST_ASSERT_FALSE(o2p_sht_masked(near_wrap + O2P_SHT_RECOVERY_MS,
                                     near_wrap));

    /* main.c seeds g_sht_pulse_ms = millis() - O2P_SHT_RECOVERY_MS at boot so
     * the first cycle reads the sensor. A probe that reset would otherwise
     * publish no humidity for the first 350 s of every boot. */
    const uint32_t boot_ms = 42u;
    TEST_ASSERT_FALSE(o2p_sht_masked(boot_ms,
                                     boot_ms - O2P_SHT_RECOVERY_MS));

    /* THE CACHE DELIBERATELY DOES NOT OUTLAST THE MASK, and an earlier version
     * of this test asserted that it must. That assertion encoded the circular
     * reasoning it was supposed to guard: sizing a staleness budget to the gap
     * you want to paper over justifies any number. O2_COMP takes its sentinel
     * for the remainder of each mask instead, and O2_RAW - which needs no
     * SHT45 - keeps publishing throughout. See O2P_RH_MAX_AGE_S in o2.h. */
    TEST_ASSERT_TRUE((uint32_t)O2P_RH_MAX_AGE_S * 1000u < O2P_SHT_RECOVERY_MS);
}

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
     * 352.1 s is the worst case the derivation in o2.h covers - 350 s of mask
     * plus the 1.1 s pulse plus the sample quantisation - and it must still
     * publish, from the same sensor's own last measurement rather than from a
     * substitute. */
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

    /* The cap covers the 32.1 s worst case it was derived against - the pulse
     * plus a sample cycle plus the 30 s window that derivation assumed - with
     * margin, and is not merely equal to it.
     *
     * It is NOT written against O2P_SHT_RECOVERY_MS, and that is the point.
     * Tying it to the mask is what produced a 400 s bridge publishing a
     * dry-basis number up to 17 % wrong at pile temperature; the bound belongs
     * to how fast chamber temperature and humidity go wrong, which the mask
     * does not affect. If a slew measurement ever moves it, this literal moves
     * with that measurement and not with the mask. */
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

    /* Past the bridge's age bound, or with a genuinely dead SHT45: the
     * chamber goes with the humidity. OVERTURNED 2026-09-11 (Fab's per-law
     * ruling: the chamber is no law's control quantity, it only feeds
     * DT_LIMIT): the loop REGULATES through NO_CHAMBER as an annotation.
     * The bridge is no longer what stands between this loop and driving;
     * what a fresh reference still buys is DT_LIMIT's release evidence
     * (chamber_fresh, heater_ctl.c - bridged is good enough for latching,
     * not for exonerating). The die is stated deliberately: 57.20 C from
     * hin_healthy(), above the blind gate and moot here only because no
     * blind path is taken. */
    o2p_heater_ctl_reset(&st);
    in.chamber_valid = false;
    in.chamber_fresh = false;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE_MESSAGE((out.block & O2P_HB_NO_CHAMBER) != 0u,
        "NO_CHAMBER must stay visible while the loop drives");
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "a tip law regulates through a dead chamber (2026-09-11 ruling)");
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
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

static void test_persistent_tip_loop_regulates_through_no_chamber(void)
{
    /* RENAMED AND RE-PINNED 2026-09-11 (Fab's per-law ruling: the chamber is
     * no law's control quantity - it only feeds DT_LIMIT). The old pin
     * ("still needs a chamber reading") demanded duty 0 on NO_CHAMBER and
     * passed twice over by accident: the refusal it asserted was overturned
     * by the ruling, and the blind path that would have replaced it was
     * already closed by hin_healthy()'s die = 57.20 C sitting above
     * O2P_HEATER_BLIND_DIE_MAX_C100 - the reviewer's finding. The die is
     * now stated where it matters instead of inherited silently. DT_LIMIT
     * stays fully live as the hard bound; it simply cannot fire on a
     * chamber it cannot read, and an unevaluable clamp is not a refusal of
     * the loop. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_healthy();   /* die 57.20 C: stated, and moot - no blind path */
    o2p_heater_out_t out;

    in.chamber_valid = false;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "the persistent tip loop regulates through NO_CHAMBER (2026-09-11)");
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_DT_LIMIT);
}

/* ---------------------------------------------- the dew-margin law (0x0013) */

/* Baseline for the dew-margin law: hin_healthy() plus a valid cell-side
 * reading 2 K below the gas dew point. Chamber 54.00 C at 95.00 %RH gives
 * Td = 52.95 C (Magnus 17.62/243.12), so the cell at 50.95 C has -2.00 K of
 * margin - 6 K short of the 4 K target. Tip 55.00 C: 24 K under the ceiling.
 * The die stays at hin_healthy()'s 57.20 C, above the blind gate, so any
 * duty seen here came from the regulator, not the fallback.
 *
 * Tests that move the tip move the chamber with it: DT_LIMIT (tip - chamber
 * >= 4 K) is a hard refusal, and a hot tip over a 54 C chamber would trip it
 * and prove nothing about this law. */
static o2p_heater_in_t hin_dew(void)
{
    o2p_heater_in_t in = hin_healthy();
    in.cell_valid = true;
    in.t_cell_c100 = 5095;
    return in;
}

static uint16_t dew_step_fresh(const o2p_heater_cfg_t *cfg,
                               const o2p_heater_in_t *in,
                               o2p_heater_out_t *out)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_ctl_step(&st, cfg, in, 0u, out);
    return out->duty_x100;
}

static void test_dew_law_heats_a_cell_short_of_margin(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT8(O2P_HEATER_MODE_DEW, st.last_mode);
    /* No refusal, no blind, no IDLE - just the sentinel annotation. */
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED, out.block);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);
}

static void test_dew_law_idles_with_margin_to_spare(void)
{
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    /* Td = 52.95 C; the cell 5 K above it has a kelvin more than the target. */
    in.t_cell_c100 = 5795;
    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED | O2P_HB_IDLE, out.block);
}

static void test_dew_law_reads_the_cell_not_the_tip_or_the_rh_setpoint(void)
{
    /* The discriminating case: 80 %RH is BELOW the RH law's 85 % setpoint, so
     * the RH law idles; and the tip at 57 C sits 7.5 K above the dew point, so
     * a tip-referenced margin looks comfortable. Only the cell - 2 K below
     * Td = 49.47 C - says the membrane is condensing. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;
    in.rh_x100 = 8000u;
    in.t_tip_c100 = 5700;
    in.t_cell_c100 = 4747;

    TEST_ASSERT_TRUE_MESSAGE(dew_step_fresh(&cfg, &in, &out) > 0u,
        "a cell below the dew point must be heated whatever the tip and RH say");
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED, out.block);

    in.cell_valid = false;   /* the same probe with no cell reading */
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, dew_step_fresh(&cfg, &in, &out),
        "without a cell the RH law is in command, and 80 %RH is under its setpoint");
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED | O2P_HB_IDLE, out.block);
}

static void test_dew_law_falls_back_to_the_rh_law_without_a_cell(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    in.cell_valid = false;
    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT8(O2P_HEATER_MODE_RH, st.last_mode);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);   /* 95 %RH: the RH law heats */
}

static void test_dew_law_hand_over_restarts_the_integrator(void)
{
    /* An integral wound up in 0.01 %RH is meaningless in 0.01 K of margin. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    in.cell_valid = false;
    for (uint32_t t = 0u; t < 30u; t++) {
        o2p_heater_ctl_step(&st, &cfg, &in, t, &out);
    }
    TEST_ASSERT_TRUE(st.integ > 1000.0f);   /* 10 %RH x ki 0.10 x 30 s */

    in.cell_valid = true;
    o2p_heater_ctl_step(&st, &cfg, &in, 30u, &out);
    TEST_ASSERT_EQUAL_UINT8(O2P_HEATER_MODE_DEW, st.last_mode);
    /* One second of dew-law integration from zero: ki 0.05 x ~600 = ~30. */
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 30.0f, st.integ);
}

static void test_dew_law_regulates_through_safety(void)
{
    /* The steam-bath configuration: therm thresholds lost, tip valid. Under
     * the RH law SAFETY blinds, and the die gate then closes the blind path -
     * which is why the heater sat at zero. The dew law regulates instead. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;
    in.safety_armed = false;

    TEST_ASSERT_TRUE(dew_step_fresh(&cfg, &in, &out) > 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);

    in.cell_valid = false;   /* the RH law, same inputs: refused, die-gated */
    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
}

static void test_dew_law_clamps_the_tip_at_80c_even_with_safety_armed(void)
{
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;
    TEST_ASSERT_TRUE(in.safety_armed);

    in.t_tip_c100 = 8000;
    in.t_chamber_c100 = 7900;
    in.t_cell_c100 = 5000;   /* margin far short: the law wants heat */
    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_TRUE((out.block & O2P_HB_TIP_LIMIT) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_DT_LIMIT);

    /* The contrast: the RH law with safety armed clamps at 82.00, not 80.00. */
    in.cell_valid = false;
    TEST_ASSERT_TRUE(dew_step_fresh(&cfg, &in, &out) > 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_TIP_LIMIT);
}

static void test_dew_law_holds_the_tip_under_its_79c_ceiling(void)
{
    /* Margin still short, tip between the ceiling and the clamp: the ceiling
     * wins the min(), so the regulator backs off before the clamp is needed. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    in.t_tip_c100 = 7950;
    in.t_chamber_c100 = 7850;
    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_TIP_LIMIT);
    TEST_ASSERT_TRUE((out.block & O2P_HB_IDLE) != 0u);

    /* Half a kelvin under the ceiling: kp 5 x 50 = 250, plus one second of
     * integral (ki 0.05 x 50 = 2.5). */
    in.t_tip_c100 = 7850;
    in.t_chamber_c100 = 7750;
    TEST_ASSERT_UINT16_WITHIN(2u, 253u, dew_step_fresh(&cfg, &in, &out));
}

static void test_dew_law_without_a_tip_does_not_regulate(void)
{
    /* The tip is the law's only bound: an unevaluable cap is not a cap. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;
    in.tip_valid = false;

    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_TIP) != 0u);

    in.t_die_c100 = 3000;   /* die under the gate: the blind fallback runs */
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100,
                             dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
}

static void test_dew_law_needs_its_dew_point(void)
{
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    in.chamber_valid = false;   /* annotates the RH law; refuses this one */
    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);

    in = hin_dew();
    in.rh_valid = false;
    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_RH) != 0u);

    /* Valid-flagged humidities the Magnus form cannot take must not read as
     * an infinite margin. */
    static const uint16_t bad_rh[] = { 0u, 10001u, 65535u };
    for (unsigned i = 0u; i < sizeof bad_rh / sizeof bad_rh[0]; i++) {
        in = hin_dew();
        in.rh_x100 = bad_rh[i];
        TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
        TEST_ASSERT_TRUE((out.block & O2P_HB_NO_RH) != 0u);
    }
}

static void test_dew_law_needs_rh_consent(void)
{
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;
    cfg.rh_consent = false;

    TEST_ASSERT_EQUAL_UINT16(0u, dew_step_fresh(&cfg, &in, &out));
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CONSENT) != 0u);
}

static void test_dew_law_yields_to_a_stored_tip_setpoint(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_tip_auto();
    o2p_heater_in_t in = hin_dew();
    o2p_heater_out_t out;

    o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
    TEST_ASSERT_EQUAL_UINT8(O2P_HEATER_MODE_TIP_AUTO, st.last_mode);
}

static void test_dew_law_duty_is_monotonic_in_margin(void)
{
    /* Guard checklist 2: as the cell gets colder (or the gas wetter) the
     * duty must never fall, out to the far tail. Fresh state per point so
     * the integrator does not blur the static map. Tip 70 C over a 69 C
     * chamber: 9 K of ceiling room, no DT_LIMIT. */
    o2p_heater_cfg_t cfg = hcfg_default();
    o2p_heater_out_t out;
    uint16_t prev = 0u;
    for (int16_t cell = 7000; cell >= -4000; cell = (int16_t)(cell - 250)) {
        o2p_heater_in_t in = hin_dew();
        in.t_tip_c100 = 7000;
        in.t_chamber_c100 = 6900;
        in.t_cell_c100 = cell;
        const uint16_t d = dew_step_fresh(&cfg, &in, &out);
        TEST_ASSERT_TRUE_MESSAGE(d >= prev, "duty fell as the cell got colder");
        prev = d;
    }
    TEST_ASSERT_TRUE(prev > 0u);

    prev = 0u;
    for (uint16_t rh = 100u; rh <= 10000u; rh = (uint16_t)(rh + 100u)) {
        o2p_heater_in_t in = hin_dew();
        in.rh_x100 = rh;
        in.t_cell_c100 = 5400;
        const uint16_t d = dew_step_fresh(&cfg, &in, &out);
        TEST_ASSERT_TRUE_MESSAGE(d >= prev, "duty fell as the gas got wetter");
        prev = d;
    }
    TEST_ASSERT_TRUE(prev > 0u);
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
     * from an otherwise healthy input, with the OPEN-LOOP override armed at
     * full duty. RE-PINNED 2026-09-11 (Fab's per-law ruling + the die-gate
     * ruling): "supply" had already left this list (the rail fault is an
     * annotation now, regmap.h's dated correction), and two more entries
     * changed shape rather than leaving:
     *   - "safety" still stops the open loop - via the BLIND path, whose
     *     duty the die gate now decides. At the stated 27.00 C (under the
     *     gate) that is the 50 % blind duty, NOT zero; the old pin's zero
     *     was hin_healthy()'s 57.20 C closing the gate by accident. At
     *     40.00 C and above it is zero - the die gate is the stand-down.
     *   - "no tip" no longer stops it at all: the open loop has no control
     *     quantity to lose, so NO_TIP is an advisory annotation and the
     *     operator's duty stands.
     * The hard bits (tip limit, pin integrity, not compiled, config off)
     * still force zero, and that is the list that makes the mode
     * acceptable. */
    struct { const char *name; int which; uint16_t bit; uint16_t duty;
             uint16_t extra; int kind; } cases[] = {
        /* kind 0: hard, duty 0. 1: blind, die-gated. 2: annotation, drives. */
        { "safety",        0, O2P_HB_SAFETY,        O2P_HEATER_BLIND_DUTY_X100, O2P_HB_BLIND, 1 },
        { "no tip",        1, O2P_HB_NO_TIP,        0u, 0u, 2 },
        { "tip limit",     2, O2P_HB_TIP_LIMIT,     0u, 0u, 0 },
        { "pin integrity", 4, O2P_HB_PIN_INTEGRITY, 0u, 0u, 0 },
        { "not compiled",  5, O2P_HB_NOT_COMPILED,  0u, 0u, 0 },
        { "config off",    6, O2P_HB_CONFIG_OFF,    0u, 0u, 0 },
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t cfg = hcfg_default();
        o2p_heater_in_t in = hin_healthy();
        o2p_heater_out_t out;
        arm_override(&cfg, 10000u);
        in.t_die_c100 = 2700;   /* stated: under the gate, so the safety
                                   case's blind duty is what it permits */

        switch (cases[i].which) {
        case 0: in.safety_armed = false; break;
        case 1: in.tip_valid = false; break;
        case 2: in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100; break;
        case 4: in.pin_integrity_ok = false; break;
        case 5: in.drive_possible = false; break;
        case 6: cfg.max_duty_x100 = 0u; break;
        default: break;
        }
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].bit) != 0u,
                                 cases[i].name);
        if (cases[i].kind == 2u) {
            TEST_ASSERT_EQUAL_UINT16_MESSAGE(10000u, out.duty_x100,
                cases[i].name);
            TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.block & O2P_HB_BLIND,
                cases[i].name);
        } else {
            TEST_ASSERT_EQUAL_UINT16_MESSAGE(cases[i].duty, out.duty_x100,
                                             cases[i].name);
            if (cases[i].extra != 0u) {
                TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].extra) != 0u,
                                         cases[i].name);
            }
        }
    }

    /* The stand-down half of the safety case: same state, die at the gate
     * - the blind duty is zero, the die IS the discriminator (Fab's order
     * 2026-09-11: "nope, no stand-down. 50 is safe if MCU die is < 40 C"). */
    {
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t cfg = hcfg_default();
        o2p_heater_in_t in = hin_healthy();
        o2p_heater_out_t out;
        arm_override(&cfg, 10000u);
        in.safety_armed = false;
        in.t_die_c100 = O2P_HEATER_BLIND_DIE_MAX_C100;
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
        TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
        TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
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

    /* Since the latch can release on cleared evidence, arming must not be a
     * way to accumulate that evidence: three windows armed, at rest, with
     * every reference valid and clear, must leave it latched. */
    o2p_heater_in_t rest = hin_healthy();
    for (uint32_t t = 1u; t <= 3u * O2P_HEATER_RUNAWAY_WINDOW_S; t++) {
        o2p_heater_ctl_step(&st, &cfg, &rest, t, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "an armed override must not accumulate release evidence");

    /* Nor may BANKED release evidence survive an armed period. Found by review
     * of eae463f: freezing it, as accumulation is frozen, carried 59 s of
     * exoneration across an interval nobody could observe, and the first clear
     * sample after disarming released the latch. */
    o2p_heater_state_t b;
    o2p_heater_ctl_reset(&b);
    o2p_heater_cfg_t bcfg = hcfg_default();
    bcfg.max_duty_x100 = 0u;
    b.runaway_latched = true;
    uint32_t bt = 0u;
    /* One sample starts the clock; the next 59 are credited. */
    for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S; i++, bt++) {
        o2p_heater_ctl_step(&b, &bcfg, &rest, bt, &out);
    }
    TEST_ASSERT_TRUE(b.runaway_latched);
    arm_override(&bcfg, 0u);
    for (uint32_t i = 0u; i < 600u; i++, bt++) {
        o2p_heater_ctl_step(&b, &bcfg, &rest, bt, &out);
    }
    bcfg.test_override = false;
    bcfg.test_duty_x100 = 0u;
    for (uint32_t i = 0u; i < O2P_HEATER_RUNAWAY_WINDOW_S - 1u; i++, bt++) {
        o2p_heater_ctl_step(&b, &bcfg, &rest, bt, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(b.runaway_latched,
        "arming must discard banked release evidence, not freeze it");
    o2p_heater_ctl_step(&b, &bcfg, &rest, bt++, &out);
    TEST_ASSERT_FALSE(b.runaway_latched);
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
     * override, with a setpoint far above the tip so the loop wants full
     * duty. RE-PINNED 2026-09-11 (Fab's rulings): SAFETY alone no longer
     * refuses a tip law - it annotates and the loop runs, so the safety
     * case moved out of this refusal table into its own pin below - and
     * the die is stated at 27.00 C, under the blind gate, so the no-tip
     * case's blind duty is what the DIE GATE permits, visible and
     * deliberate, never an accident of hin_healthy()'s 57.20 C. */
    struct { const char *name; int which; uint16_t bit; uint16_t duty;
             uint16_t extra; } cases[] = {
        { "no tip",        1, O2P_HB_NO_TIP,        O2P_HEATER_BLIND_DUTY_X100, O2P_HB_BLIND },
        { "tip limit",     2, O2P_HB_TIP_LIMIT,     0u, 0u },
        { "pin integrity", 4, O2P_HB_PIN_INTEGRITY, 0u, 0u },
        { "not compiled",  5, O2P_HB_NOT_COMPILED,  0u, 0u },
        { "config off",    6, O2P_HB_CONFIG_OFF,    0u, 0u },
    };
    /* ("supply" removed from this table 2026-09-11, Fab's order - the rail
     * fault no longer vetoes any path; O2P_HB_SUPPLY is an annotation. See
     * test_supply_fault_annotates_but_does_not_veto.) */
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
        in.t_die_c100 = 2700;   /* stated: UNDER the blind gate, so the
                                   no-tip case's 50 % is permitted, not accidental */

        switch (cases[i].which) {
        case 1: in.tip_valid = false; break;
        case 2: in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100; break;
        case 4: in.pin_integrity_ok = false; break;
        case 5: in.drive_possible = false; break;
        case 6: cfg.max_duty_x100 = 0u; break;
        default: break;
        }
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(cases[i].duty, out.duty_x100,
                                         cases[i].name);
        TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].bit) != 0u,
                                 cases[i].name);
        if (cases[i].extra != 0u) {
            TEST_ASSERT_TRUE_MESSAGE((out.block & cases[i].extra) != 0u,
                                     cases[i].name);
        }
    }

    /* SAFETY ALONE, 2026-09-11 (Fab's order: "fix that control loop
     * bullshit"): the annotation pin the case it used to be in the table
     * for. The tip law runs at full demand with SAFETY visible in
     * HEATER_BLOCK - the state whose old duty-0 pin was the setpoint
     * discard the ruling ended. */
    {
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
        in.safety_armed = false;
        o2p_heater_ctl_step(&st, &cfg, &in, 0u, &out);
        TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
            "SAFETY alone must not refuse a tip law - annotate and regulate");
        TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
        TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
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

    /* With consent, the same inputs drive. TIP_DISARMED rides along with
     * the RH law since 0x0010 - it is an annotation, not a refusal. */
    cfg.rh_consent = true;
    o2p_heater_ctl_step(&st, &cfg, &in, 1u, &out);
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_TIP_DISARMED, out.block);
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
    /* The migration failure this field exists to prevent: an upgrade landing
     * on a probe whose old record said "heat hard", and heating. An older
     * record was written by firmware that could not express consent, so there
     * is no honest value to carry - only zero. The migration output is
     * asserted elsewhere; what is asserted here is the FRESH default, which
     * changed 2026-09-10 to granted, for the same measured reason as the
     * regmap.c comment: a board at 99 %RH could not heat itself. */
    o2p_config_t c;
    o2p_config_defaults(&c);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(O2P_HEATER_RH_CONSENT_MAGIC,
        c.heater_rh_consent,
        "fresh configs ship with RH consent granted (2026-09-10); refusing "
        "is a single write of zero, and max_duty still defaults to off");

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

static void test_ext_tmp117_address_and_register_mapping(void)
{
    /* The external TMP117 sits on ext I2C (tmp117-probe, ADD0=SDA -> 0x4A).
     * It must not collide with any on-board I2C device. */
    TEST_ASSERT_EQUAL_HEX8(0x4Au, O2P_HW_I2C_ADDR_TMP117_EXT);
    TEST_ASSERT_TRUE(O2P_HW_I2C_ADDR_TMP117_EXT != O2P_HW_I2C_ADDR_TMP117);
    TEST_ASSERT_TRUE(O2P_HW_I2C_ADDR_TMP117_EXT != O2P_HW_I2C_ADDR_LMP91000);
    TEST_ASSERT_TRUE(O2P_HW_I2C_ADDR_TMP117_EXT != O2P_HW_I2C_ADDR_SHT45);
    TEST_ASSERT_TRUE(O2P_HW_I2C_ADDR_TMP117_EXT != O2P_HW_I2C_ADDR_ADS1119);

    /* O2P_REG_T_EXT maps to O2P_REG_EXP_DATA (0x001F) in the diagnostic block. */
    TEST_ASSERT_EQUAL_HEX16(0x001Fu, O2P_REG_EXP_DATA);
    TEST_ASSERT_EQUAL_HEX16(O2P_REG_EXP_DATA, O2P_REG_T_EXT);

    /* Test readback through regmap: absent returns 0xFFFF, present returns int16 */
    o2p_regmap_t rm_test;
    o2p_regmap_init(&rm_test);

    o2p_snapshot_t *s = o2p_regmap_staging(&rm_test);
    o2p_snapshot_reset(s);
    TEST_ASSERT_EQUAL_HEX16(O2P_U16_INVALID, s->exp_data);

    /* Publish snapshot with invalid / absent ext sensor */
    o2p_regmap_publish(&rm_test);
    uint16_t val = 0;
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm_test, O2P_REG_T_EXT, 1u, &val));
    TEST_ASSERT_EQUAL_HEX16(0xFFFFu, val);

    /* Publish snapshot with a valid ext temperature, e.g. 23.50 C (2350 c100) */
    s = o2p_regmap_staging(&rm_test);
    s->exp_data = (uint16_t)2350;
    o2p_regmap_publish(&rm_test);
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm_test, O2P_REG_T_EXT, 1u, &val));
    TEST_ASSERT_EQUAL_INT16(2350, (int16_t)val);

    /* Negative temperature, e.g. -10.00 C (-1000 c100) */
    s = o2p_regmap_staging(&rm_test);
    s->exp_data = (uint16_t)(int16_t)-1000;
    o2p_regmap_publish(&rm_test);
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm_test, O2P_REG_T_EXT, 1u, &val));
    TEST_ASSERT_EQUAL_INT16(-1000, (int16_t)val);

    /* TMP117 raw to c100 conversion and rating bounds:
     * 1 LSB = 7.8125 mC (count * 100 / 128) */
    int32_t c_zero = ((int32_t)(int16_t)0x0000 * 100) / 128;
    TEST_ASSERT_EQUAL_INT32(0, c_zero);

    int32_t c_25 = ((int32_t)(int16_t)0x0C80 * 100) / 128;
    TEST_ASSERT_EQUAL_INT32(2500, c_25);

    int32_t c_m25 = ((int32_t)(int16_t)(uint16_t)0xF380 * 100) / 128;
    TEST_ASSERT_EQUAL_INT32(-2500, c_m25);

    /* POR value (0x8000 = -256 C) is strictly outside operating rating */
    int32_t c_por = ((int32_t)(int16_t)(uint16_t)0x8000 * 100) / 128;
    TEST_ASSERT_TRUE(c_por < O2P_TMP117_MIN_C100);

    /* Max rating +150 C (0x4B00) */
    int32_t c_150 = ((int32_t)(int16_t)0x4B00 * 100) / 128;
    TEST_ASSERT_EQUAL_INT32(15000, c_150);
    TEST_ASSERT_TRUE(c_150 <= O2P_TMP117_MAX_C100);
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
    /* RH consent is NEVER carried, on any migration path (audit F1,
     * 2026-09-10): v5 copies field-by-field and used to leave the
     * fresh-config default standing, which since tonight GRANTS consent.
     * The field runs v5 - a deployed unit upgrading must not come up
     * consented and armed off its stored max_duty. */
    TEST_ASSERT_EQUAL_UINT16(0u, out.heater_rh_consent);

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
        "one hot sample must not latch runaway");

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

/* CAL_STATE must say how the air point was obtained, not just that one exists.
 *
 * Added 2026-09-09 with the calibration gate change. On a board whose AIN2/AIN3
 * are rail monitors the cell bias cannot be measured, so an air point is
 * accepted on weaker evidence (the AFE's own register image, via
 * O2P_FAULTS_INVALIDATE_O2) and must SAY SO. A constant that cannot report its
 * own provenance is the failure this tree keeps writing postmortems about. */
static void test_cal_state_reports_an_unverified_bias(void)
{
    o2p_regmap_t rm;
    uint16_t v[1];
    o2p_regmap_init(&rm);

    /* No air point at all: AIR_DEFAULT, and NOT bias-unverified. Two bits for
     * one condition would read as two problems. */
    rm.cfg.cal_air_na = 0;
    rm.cfg.cal_bias_verified = 0u;
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_TRUE(v[0] & O2P_CAL_STATE_AIR_DEFAULT);
    TEST_ASSERT_FALSE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);

    /* An air point taken WITHOUT a measured bias. */
    rm.cfg.cal_air_na = 99000;
    rm.cfg.cal_bias_verified = 0u;
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_FALSE(v[0] & O2P_CAL_STATE_AIR_DEFAULT);
    TEST_ASSERT_TRUE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);

    /* And one taken with it. */
    rm.cfg.cal_bias_verified = 1u;
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_FALSE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);

    /* THE MIGRATION PROPERTY, which is why the polarity is "verified" and not
     * "unverified": a v8 record has ZERO in this byte, and zero must read as
     * the conservative answer. If someone flips the sense later, every probe
     * upgraded from v8 silently claims evidence it never had. */
    o2p_config_t old_record;
    memset(&old_record, 0, sizeof(old_record));
    old_record.cal_air_na = 99000;
    rm.cfg = old_record;
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_TRUE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);
}

/* A hand-written air point must not inherit the previous point's provenance.
 *
 * Review finding, 2026-09-09: CAL_AIR_NA_HI/LO replaced the constant and left
 * cal_bias_verified alone, so a Modbus write could land a calibration that
 * CAL_STATE then reported as bias-verified because an EARLIER point had been.
 * A bit that can lie is worse than no bit. */
static void test_a_written_air_point_resets_its_provenance(void)
{
    o2p_regmap_t rm;
    uint16_t v[1];
    o2p_regmap_init(&rm);

    /* Start from a point that WAS verified. */
    rm.cfg.cal_air_na = 99000;
    rm.cfg.cal_bias_verified = 1u;
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_FALSE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);

    /* Overwrite it over the wire. Either half must clear the bit. */
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_write(&rm, O2P_REG_CAL_AIR_NA_LO, 1u,
                                                 (uint16_t[]){ 40000u & 0xFFFFu }));
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_TRUE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);

    rm.cfg.cal_bias_verified = 1u;
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_write(&rm, O2P_REG_CAL_AIR_NA_HI, 1u,
                                                 (uint16_t[]){ 1u }));
    TEST_ASSERT_EQUAL_UINT8(0u, o2p_regmap_read(&rm, O2P_REG_CAL_STATE, 1u, v));
    TEST_ASSERT_TRUE(v[0] & O2P_CAL_STATE_BIAS_UNVERIFIED);
}

/* The window that applies when the bias could NOT be measured.
 *
 * WHAT THIS DOES NOT TEST, stated because the neighbouring bias tests make the
 * same admission: main.c does not compile on the host, so nothing here drives
 * the calibration gate. This pins the CONSTANTS and the relationship between
 * them, which is what a later edit would get wrong. */
static void test_the_unverified_air_window_is_the_datasheet_population(void)
{
    /* DS-0637 Issue 2: 0.1 +/- 0.03 mA in air. */
    TEST_ASSERT_EQUAL_INT32( 70000, O2P_AIR_CAL_UNVERIFIED_MIN_NA);
    TEST_ASSERT_EQUAL_INT32(130000, O2P_AIR_CAL_UNVERIFIED_MAX_NA);

    /* STRICTLY TIGHTER than the window used when the bias IS measured. If a
     * later edit widens it to match, the safeguard is gone and this fails. */
    TEST_ASSERT_TRUE(O2P_AIR_CAL_UNVERIFIED_MIN_NA > O2P_AIR_CAL_MIN_NA);
    TEST_ASSERT_TRUE(O2P_AIR_CAL_UNVERIFIED_MAX_NA < O2P_AIR_CAL_MAX_NA);

    /* THE KNOWN-BAD from the review: a partially faulty electrode path reading
     * 60 uA in air passes the wide window and must NOT pass this one. */
    TEST_ASSERT_TRUE(60000 >= O2P_AIR_CAL_MIN_NA);              /* wide: accepts */
    TEST_ASSERT_TRUE(60000 <  O2P_AIR_CAL_UNVERIFIED_MIN_NA);   /* tight: refuses */

    /* And the point actually taken on the bench, 99160 nA, must still pass -
     * a safeguard that refuses the healthy case is not a safeguard. */
    TEST_ASSERT_TRUE(99160 >= O2P_AIR_CAL_UNVERIFIED_MIN_NA &&
                     99160 <= O2P_AIR_CAL_UNVERIFIED_MAX_NA);
}

static void test_the_wire_version_tracks_the_wire_contract(void)
{
    /* FW_VERSION's own rule is that it is bumped whenever the wire contract
     * changes. It sat at 0x0002 describing a 26-register block while the block
     * was 28, which left a master no way to tell the two apart before reading. */
    /* 0x0013: the dew-margin heater law - the autonomous humidity-side slot
     *         regulates cell-side T_EXT to 4 K above the gas dew point
     *         whenever T_EXT is valid (Fab's order, 2026-09-11); no new
     *         register, HEATER_BLOCK bits unchanged, the law is new.
     * 0x0012: poke mailbox 0x0198 and wide poke 0x01B0 - the WRITE
     *         counterpart of the peek (Fab's order, 2026-09-11); SRAM
     *         .data/.bss writes only, flash/peripherals/SHARED refused.
     * 0x0011: the supply veto is REMOVED - O2P_HB_SUPPLY is annotation-only
     *         on every path (Fab's order, 2026-09-11; no wire-format change,
     *         the bit still appears, it just stops refusing).
     * 0x0010: fresh configs ship RH consent; HEATER_BLOCK's last two bits
     *         are annotations (IDLE, TIP_DISARMED); the staleness cut
     *         precedes the IWDG's fastest bound and raises STALE; T_TIP
     *         steps the thermal mass cannot make are rejected for a cycle.
     * 0x000F: a busy diagnostic mailbox refuses with exception 06 instead of
     *         03-plus-ERR_BUSY, and a peek can answer ERR_PARITY (4). */
    TEST_ASSERT_EQUAL_HEX16(0x0013u, O2P_FW_VERSION);
    TEST_ASSERT_EQUAL_HEX16(0xC000u,
        (uint16_t)(O2P_HB_IDLE | O2P_HB_TIP_DISARMED));
    /* The staleness cut must win the race against the watchdog's fastest
     * bound (~2.7 s across the LSI spread, mcu.c's own numbers) - at the
     * old 5000 ms the reset won on every part off the slow tail (F2). */
    TEST_ASSERT_TRUE(O2P_HEATER_STALE_MS < 2700u);
    TEST_ASSERT_EQUAL_HEX8(0x06u, O2P_MB_EX_DEVICE_BUSY);
#if O2P_DEBUG_ENABLE
    TEST_ASSERT_EQUAL_UINT16(4u, O2P_PEEK_ERR_PARITY);
#endif
    TEST_ASSERT_EQUAL_UINT16(27u, O2P_REG_CONFIG_COUNT);
#if O2P_DEBUG_ENABLE
    /* 0x000D: the wide peek block appeared at 0x0100, 65 registers, where
     *         every address previously answered exception 02.
     * 0x000C: the 4-word peek trigger took an explicit burst length. */
    TEST_ASSERT_EQUAL_HEX16(0x0100u, O2P_REG_PEEKW_BASE);
    TEST_ASSERT_EQUAL_UINT16(65u, O2P_REG_PEEKW_COUNT);
    TEST_ASSERT_EQUAL_UINT16(30u, O2P_PEEKW_WORDS_MAX);
    TEST_ASSERT_EQUAL_UINT16(11u, O2P_REG_PEEK_COUNT);
#endif
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

/* The peek burst length is the master's to choose, and the firmware is what
 * has to validate it.
 *
 * While every request was a fixed four-word burst, the whole-burst range check
 * rejected every target whose region has fewer than four words left - which is
 * every address the register-map document lists under "Device Constants". The
 * 96-bit UID is three words and the flash-size register is one, so BOTH were
 * unreachable: the mailbox answered ERR_RANGE to the exact reads it was
 * documented to serve. A one-word peek at the last word of SRAM or Flash was
 * refused for the same reason. */
static void test_peek_burst_length_is_requested_not_assumed(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    /* The 96-bit UID: three words, and only reachable as a three-word burst. */
    uint16_t uid3[3] = { 0x1FFFu, 0x7590u, 3u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, uid3));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);
    /* The word past the request is padding, not a fourth UID word. */
    TEST_ASSERT_EQUAL_HEX32(0xFFFFFFFFu, rm.peek_words[3]);

    uint16_t uid4[3] = { 0x1FFFu, 0x7590u, 4u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, uid4));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peek_status);

    /* The flash-size register is a region of exactly one word. */
    uint16_t fsz[3] = { 0x1FFFu, 0x75E0u, 1u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, fsz));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);

    uint16_t fsz2[3] = { 0x1FFFu, 0x75E0u, 2u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, fsz2));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peek_status);

    /* The last aligned word of SRAM: readable alone, not as the head of a
     * burst that would run off the end. */
    uint16_t sram_last1[3] = { 0x2000u, 0x8FFCu, 1u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, sram_last1));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);

    uint16_t sram_last2[3] = { 0x2000u, 0x8FFCu, 2u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, sram_last2));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peek_status);

    /* A burst may not cross out of the region it started in. */
    uint16_t flash_last[3] = { 0x0801u, 0xFFFCu, 2u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, flash_last));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peek_status);
}

/* A write that straddles a mailbox boundary is a bad LENGTH, not a bad
 * ADDRESS. It was refused either way - nothing is ever written by such a frame
 * - but it answered ILLEGAL_ADDRESS, which tells a master the register does
 * not exist when in fact its request was malformed. */
static void test_a_write_straddling_a_mailbox_is_an_illegal_value(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    /* Runs off the end of the heater-test block into the peek trigger. */
    uint16_t straddle_htest[2] = { 0u, 0x2000u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_HEATER_TEST_KI, 2u,
                                            straddle_htest));

    /* Starts one register below the peek block and reaches its first word. */
    uint16_t straddle_peek[2] = { 0u, 0x2000u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, (uint16_t)(O2P_REG_PEEK_BASE - 1u),
                                            2u, straddle_peek));
    /* ... and did not execute a peek on the way past. */
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_NONE, rm.peek_status);

    /* Off the end of the peek block into the diagnostic mailbox. */
    uint16_t straddle_dmbox[2] = { 0u, 0u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_PEEK_W3_LO, 2u,
                                            straddle_dmbox));
    TEST_ASSERT_FALSE(rm.diag_pending);

    /* Off the end of the diagnostic mailbox into the crash block. */
    uint16_t straddle_crash[2] = { 0u, 0u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_DIAG_CRC_STATUS, 2u,
                                            straddle_crash));

    /* An address genuinely outside every block is still ILLEGAL_ADDRESS: the
     * new rule must not swallow the case it was never about. */
    uint16_t nowhere[1] = { 0u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_write(&rm, 0x0200u, 1u, nowhere));
}

/* A malformed trigger must not disturb the previous result. */
static void test_peek_rejects_a_count_outside_one_to_four(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    uint16_t good[3] = { 0x2000u, 0x0100u, 2u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, good));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);
    TEST_ASSERT_EQUAL_HEX32(0xFFFFFFFFu, rm.peek_words[2]);

    uint16_t zero[3] = { 0x2000u, 0x0200u, 0u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, zero));
    uint16_t five[3] = { 0x2000u, 0x0200u, 5u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, five));

    /* Refused, so the address and status still describe the accepted peek. */
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);
    TEST_ASSERT_EQUAL_HEX16(0x0100u, rm.peek_addr_lo);

    /* Four registers is not a trigger at all. */
    uint16_t four[4] = { 0x2000u, 0x0200u, 1u, 0u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 4u, four));
}

/* The two-register trigger predates the count and still means four words. */
static void test_peek_two_register_trigger_still_means_four_words(void)
{
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);

    uint16_t sram[2] = { 0x2000u, 0x0100u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 2u, sram));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peek_status);
    for (int w = 0; w < 4; w++) {
        TEST_ASSERT_NOT_EQUAL_HEX32(0xFFFFFFFFu, rm.peek_words[w]);
    }

    /* And it is still refused where four words do not fit. */
    uint16_t uid[2] = { 0x1FFFu, 0x7590u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 2u, uid));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peek_status);
}

/* ---- wide peek block, 0x0100 ---------------------------------------------
 *
 * The fake memory answers a pattern of the ADDRESS and an epoch, and it counts
 * every address it is asked for. A status code says what the firmware decided;
 * the dereference count says what it actually touched, and on a Cortex-M0+ the
 * second is the one that HardFaults. So every refusal below is checked both
 * ways: the right status AND zero dereferences. */
static unsigned s_pk_reads;       /* dereferences since pk_count_from_here() */
static unsigned s_pk_unmasked;    /* ... of which outside a masked section */
static uint32_t s_pk_min, s_pk_max;
static uint32_t s_pk_epoch;       /* bump to "change memory" after a trigger */

/* Bit 31 clear, so it can never be the 0xFFFFFFFF an unexecuted word reads. */
static uint32_t pk_pattern(uint32_t a)
{
    return (a ^ 0x5A5A5A5Au ^ (s_pk_epoch * 0x01000193u)) & 0x7FFFFFFFu;
}

static uint32_t pk_fake_read(uint32_t a)
{
    s_pk_reads++;
    if (o2p_peek_host_irq_depth <= 0) {
        s_pk_unmasked++;
    }
    if (a < s_pk_min) s_pk_min = a;
    if (a > s_pk_max) s_pk_max = a;
    return pk_pattern(a);
}

static void pk_count_from_here(void)
{
    s_pk_reads = 0u;
    s_pk_min = 0xFFFFFFFFu;
    s_pk_max = 0u;
}

static void pk_arm(void)
{
    o2p_peek_host_read = pk_fake_read;
    s_pk_unmasked = 0u;
    s_pk_epoch = 0u;
    pk_count_from_here();
}

static uint8_t pkw_trigger(uint32_t target, uint16_t words)
{
    uint16_t t[3] = { (uint16_t)(target >> 16), (uint16_t)(target & 0xFFFFu), words };
    return o2p_regmap_write(&rm, O2P_REG_PEEKW_BASE, 3u, t);
}

static size_t pk_adu(uint8_t *buf, const uint8_t *pdu, size_t n)
{
    buf[0] = 3u;
    memcpy(buf + 1, pdu, n);
    uint16_t crc = o2p_mb_crc16(buf, n + 1u);
    buf[n + 1u] = (uint8_t)(crc & 0xFFu);
    buf[n + 2u] = (uint8_t)(crc >> 8);
    return n + 3u;
}

static uint32_t pkw_word(const uint16_t *block, unsigned w)
{
    return ((uint32_t)block[O2P_PEEKW_HEADER + 2u * w] << 16) |
           (uint32_t)block[O2P_PEEKW_HEADER + 2u * w + 1u];
}

static void test_peekw_reads_as_nothing_held_until_triggered(void)
{
    uint16_t out[O2P_REG_PEEKW_COUNT];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE,
                                               O2P_REG_PEEKW_COUNT, out));
    TEST_ASSERT_EQUAL_HEX16(0u, out[0]);
    TEST_ASSERT_EQUAL_HEX16(0u, out[1]);
    TEST_ASSERT_EQUAL_UINT16(0u, out[2]);
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_NONE, out[3]);
    TEST_ASSERT_EQUAL_UINT16(0u, out[4]);
    /* 0x0000 would be a plausible word of SRAM. Nothing has been read, and
     * the data says so. */
    for (unsigned i = O2P_PEEKW_HEADER; i < O2P_REG_PEEKW_COUNT; i++) {
        TEST_ASSERT_EQUAL_HEX16(0xFFFFu, out[i]);
    }
}

/* The point of the block: one trigger, one read, the whole burst - driven
 * through the real PDU layer so the frame sizes are the ones on the wire. */
static void test_peekw_one_trigger_and_one_read_return_the_whole_burst(void)
{
    pk_arm();
    const uint32_t target = 0x20000100u;
    uint8_t req[O2P_MB_MAX_ADU], rsp[O2P_MB_MAX_ADU];

    const uint8_t fc16[] = { 0x10, 0x01, 0x00, 0x00, 0x03, 0x06,
                             0x20, 0x00, 0x01, 0x00, 0x00, O2P_PEEKW_WORDS_MAX };
    size_t n = pk_adu(req, fc16, sizeof fc16);
    /* The trigger is 15 bytes: inside the Dragino A8's 40-byte ceiling. */
    TEST_ASSERT_EQUAL_UINT(15u, n);
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(8u, len);
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);

    TEST_ASSERT_EQUAL_UINT(O2P_PEEKW_WORDS_MAX, s_pk_reads);
    TEST_ASSERT_EQUAL_HEX32(target, s_pk_min);
    TEST_ASSERT_EQUAL_HEX32(target + 4u * (O2P_PEEKW_WORDS_MAX - 1u), s_pk_max);
    TEST_ASSERT_EQUAL_UINT_MESSAGE(0u, s_pk_unmasked,
        "every dereference must happen with interrupts masked");
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, o2p_peek_host_irq_depth,
        "the mask must be restored after the copy");

    const uint8_t fc03[] = { 0x03, 0x01, 0x00, 0x00, O2P_REG_PEEKW_COUNT };
    n = pk_adu(req, fc03, sizeof fc03);
    len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    /* 5 + 2 * 65 = 135 bytes: one read on every wired path and on the radio
     * at DR4/DR5 (regmap.h, O2P_PEEKW_WORDS_MAX). */
    TEST_ASSERT_EQUAL_UINT(135u, len);
    TEST_ASSERT_TRUE(len <= O2P_MB_MAX_ADU);
    TEST_ASSERT_EQUAL_HEX8(0x03, rsp[1]);
    TEST_ASSERT_EQUAL_UINT8(130u, rsp[2]);

    uint16_t block[O2P_REG_PEEKW_COUNT];
    for (unsigned i = 0; i < O2P_REG_PEEKW_COUNT; i++) {
        block[i] = (uint16_t)(((uint16_t)rsp[3u + 2u * i] << 8) | rsp[4u + 2u * i]);
    }
    TEST_ASSERT_EQUAL_HEX16(0x2000u, block[0]);
    TEST_ASSERT_EQUAL_HEX16(0x0100u, block[1]);
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEKW_WORDS_MAX, block[2]);
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, block[3]);
    TEST_ASSERT_EQUAL_UINT16(1u, block[4]);
    for (unsigned w = 0; w < O2P_PEEKW_WORDS_MAX; w++) {
        TEST_ASSERT_EQUAL_HEX32(pk_pattern(target + 4u * w), pkw_word(block, w));
    }
    /* The read served the snapshot; it did not go back to memory. */
    TEST_ASSERT_EQUAL_UINT(O2P_PEEKW_WORDS_MAX, s_pk_reads);
}

/* A snapshot, not a window: memory that changes after the trigger does not
 * change the answer, however many reads a narrow transport splits it into. */
static void test_peekw_serves_the_trigger_time_snapshot_not_live_memory(void)
{
    pk_arm();
    const uint32_t target = 0x20000200u;
    const uint16_t words = 17u;   /* one o2p_snapshot_t, 68 bytes */
    uint32_t want[17];
    for (unsigned w = 0; w < words; w++) {
        want[w] = pk_pattern(target + 4u * w);
    }
    TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(target, words));
    s_pk_epoch = 7u;                         /* "the sampler published" */
    TEST_ASSERT_NOT_EQUAL(want[0], pk_pattern(target));

    uint16_t whole[O2P_REG_PEEKW_COUNT];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE,
                                               O2P_REG_PEEKW_COUNT, whole));
    for (unsigned w = 0; w < words; w++) {
        TEST_ASSERT_EQUAL_HEX32(want[w], pkw_word(whole, w));
    }
    for (unsigned w = words; w < O2P_PEEKW_WORDS_MAX; w++) {
        TEST_ASSERT_EQUAL_HEX32(0xFFFFFFFFu, pkw_word(whole, w));
    }

    /* Carried the way a 51-byte uplink would: header plus 9 words (23
     * registers, a 51-byte reply), then the other 8 words. */
    uint16_t a[23], b[16];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE, 23u, a));
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm,
        (uint16_t)(O2P_REG_PEEKW_DATA + 18u), 16u, b));
    TEST_ASSERT_EQUAL_HEX16_ARRAY(whole, a, 23u);
    TEST_ASSERT_EQUAL_HEX16_ARRAY(&whole[23], b, 16u);

    /* And a trigger from anybody else in between moves SEQ, which is how
     * such a reader knows its pieces no longer belong together. */
    uint16_t seq_before = a[4];
    TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(0x08004000u, 2u));
    uint16_t hdr[O2P_PEEKW_HEADER];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE,
                                               O2P_PEEKW_HEADER, hdr));
    TEST_ASSERT_NOT_EQUAL(seq_before, hdr[4]);
}

/* Every write that is not exactly the trigger is exception 03, and changes
 * nothing: not the address, not the count, not the status, not the sequence,
 * not one word - and it dereferences nothing. */
static void test_peekw_a_malformed_trigger_changes_nothing_and_touches_no_memory(void)
{
    pk_arm();
    TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(0x08004000u, 4u));
    uint16_t before[O2P_REG_PEEKW_COUNT], after[O2P_REG_PEEKW_COUNT];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE,
                                               O2P_REG_PEEKW_COUNT, before));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, before[3]);
    pk_count_from_here();

    uint16_t zero[3]  = { 0x2000u, 0x0000u, 0u };
    uint16_t over[3]  = { 0x2000u, 0x0000u, (uint16_t)(O2P_PEEKW_WORDS_MAX + 1u) };
    uint16_t huge[3]  = { 0x2000u, 0x0000u, 0xFFFFu };
    uint16_t two[2]   = { 0x2000u, 0x0000u };
    uint16_t four[4]  = { 0x2000u, 0x0000u, 1u, 0u };
    uint16_t good[3]  = { 0x2000u, 0x0000u, 1u };
    uint16_t many[123];
    for (unsigned i = 0; i < 123u; i++) many[i] = (i == 2u) ? 1u : 0x2000u;

    const struct { uint16_t addr; uint16_t count; const uint16_t *in; } bad[] = {
        { O2P_REG_PEEKW_BASE, 3u, zero },     /* count 0 */
        { O2P_REG_PEEKW_BASE, 3u, over },     /* count N_MAX + 1 */
        { O2P_REG_PEEKW_BASE, 3u, huge },     /* count 0xFFFF */
        { O2P_REG_PEEKW_BASE, 2u, two },      /* the 0x0065 short form */
        { O2P_REG_PEEKW_BASE, 4u, four },
        { O2P_REG_PEEKW_BASE, 1u, two },      /* an FC06 */
        { O2P_REG_PEEKW_BASE, 123u, many },   /* the largest FC16 there is */
        { O2P_REG_PEEKW_ADDR_LO, 1u, two },
        { O2P_REG_PEEKW_ADDR_LO, 3u, good },  /* right length, wrong offset */
        { O2P_REG_PEEKW_WORDS, 1u, good },
        { O2P_REG_PEEKW_STATUS, 1u, good },
        { O2P_REG_PEEKW_SEQ, 1u, good },
        { O2P_REG_PEEKW_DATA, 3u, good },
        { (uint16_t)(O2P_REG_PEEKW_BASE + O2P_REG_PEEKW_COUNT - 1u), 1u, good },
        { (uint16_t)(O2P_REG_PEEKW_BASE - 1u), 3u, good },  /* straddles in */
        { (uint16_t)(O2P_REG_PEEKW_BASE + O2P_REG_PEEKW_COUNT - 2u), 3u, good },
    };
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        TEST_ASSERT_EQUAL_HEX8_MESSAGE(O2P_MB_EX_ILLEGAL_VALUE,
            o2p_regmap_write(&rm, bad[i].addr, bad[i].count, bad[i].in),
            "a write that is not exactly the trigger must be exception 03");
    }
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE,
                                               O2P_REG_PEEKW_COUNT, after));
    TEST_ASSERT_EQUAL_HEX16_ARRAY(before, after, O2P_REG_PEEKW_COUNT);
    TEST_ASSERT_EQUAL_UINT(0u, s_pk_reads);

    /* The guard gap below the block and the address past it are not
     * registers, and a read that straddles the end is not contained. */
    uint16_t out[2];
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, o2p_regmap_read(&rm, 0x00FFu, 1u, out));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
        o2p_regmap_read(&rm, (uint16_t)(O2P_REG_PEEKW_BASE + O2P_REG_PEEKW_COUNT), 1u, out));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
        o2p_regmap_read(&rm, (uint16_t)(O2P_REG_PEEKW_BASE + O2P_REG_PEEKW_COUNT - 1u), 2u, out));
}

/* A well-formed trigger at a target that may not be read is served with a
 * status, replaces the previous result, and dereferences nothing. */
static void test_peekw_refuses_misaligned_and_unmapped_targets_without_dereferencing(void)
{
    pk_arm();
    static const struct { uint32_t a; uint16_t st; } bad[] = {
        { 0x20000001u, O2P_PEEK_ERR_ALIGN }, { 0x20000002u, O2P_PEEK_ERR_ALIGN },
        { 0x20000003u, O2P_PEEK_ERR_ALIGN }, { 0x0801FFFFu, O2P_PEEK_ERR_ALIGN },
        { 0xFFFFFFFFu, O2P_PEEK_ERR_ALIGN },
        /* The boot alias of flash at 0: mapped, and still not in the table. */
        { 0x00000000u, O2P_PEEK_ERR_RANGE },
        { 0x07FFFFFCu, O2P_PEEK_ERR_RANGE }, { 0x08020000u, O2P_PEEK_ERR_RANGE },
        { 0x1FFFFFFCu, O2P_PEEK_ERR_RANGE }, { 0x20009000u, O2P_PEEK_ERR_RANGE },
        { 0x1FFF758Cu, O2P_PEEK_ERR_RANGE }, { 0x1FFF759Cu, O2P_PEEK_ERR_RANGE },
        { 0x1FFF75DCu, O2P_PEEK_ERR_RANGE }, { 0x1FFF75E4u, O2P_PEEK_ERR_RANGE },
        /* Peripherals and the system space: destructive or faulting reads. */
        { 0x40000000u, O2P_PEEK_ERR_RANGE }, { 0x50000000u, O2P_PEEK_ERR_RANGE },
        { 0xE000E010u, O2P_PEEK_ERR_RANGE }, { 0xFFFFFFFCu, O2P_PEEK_ERR_RANGE },
    };
    static const uint16_t lens[] = { 1u, 2u, O2P_PEEKW_WORDS_MAX };
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        for (unsigned j = 0; j < sizeof lens / sizeof lens[0]; j++) {
            /* A good result first, so a refusal that failed to replace it
             * would be visible as stale data under a fresh status. */
            TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(0x20000000u, O2P_PEEKW_WORDS_MAX));
            TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peekw_status);
            uint16_t seq = rm.peekw_seq;
            pk_count_from_here();

            TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(bad[i].a, lens[j]));
            TEST_ASSERT_EQUAL_UINT16(bad[i].st, rm.peekw_status);
            TEST_ASSERT_EQUAL_UINT_MESSAGE(0u, s_pk_reads,
                "a refused target must not be dereferenced at all");
            TEST_ASSERT_EQUAL_UINT16((uint16_t)(seq + 1u), rm.peekw_seq);

            uint16_t out[O2P_REG_PEEKW_COUNT];
            TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_PEEKW_BASE,
                                                       O2P_REG_PEEKW_COUNT, out));
            TEST_ASSERT_EQUAL_HEX16((uint16_t)(bad[i].a >> 16), out[0]);
            TEST_ASSERT_EQUAL_HEX16((uint16_t)(bad[i].a & 0xFFFFu), out[1]);
            TEST_ASSERT_EQUAL_UINT16(lens[j], out[2]);
            for (unsigned k = O2P_PEEKW_HEADER; k < O2P_REG_PEEKW_COUNT; k++) {
                TEST_ASSERT_EQUAL_HEX16(0xFFFFu, out[k]);
            }
        }
    }
}

/* The far tail of every region, every burst length: OK exactly when the burst
 * fits, the dereferences never pass the region's last word, and once a burst
 * is too long for a target no longer burst is ever OK again. */
static void test_peekw_far_tail_of_every_region_is_exact_and_monotonic(void)
{
    pk_arm();
    static const struct { uint32_t first, last; } region[] = {
        /* Flash is the loader + run slot only (N4 mitigation): pages 0..33,
         * ending at O2P_APP_BASE + O2P_APP_BYTES - 4 = 0x08010FFC. */
        { 0x20000000u, 0x20008FFCu }, { 0x08000000u, 0x08010FFCu },
        { 0x1FFF7590u, 0x1FFF7598u }, { 0x1FFF75E0u, 0x1FFF75E0u },
    };
    for (unsigned r = 0; r < sizeof region / sizeof region[0]; r++) {
        for (uint32_t left = 1u; left <= O2P_PEEKW_WORDS_MAX + 1u; left++) {
            uint32_t target = region[r].last - 4u * (left - 1u);
            if (target < region[r].first || target > region[r].last) {
                break;
            }
            bool refused = false;
            for (uint16_t words = 1u; words <= O2P_PEEKW_WORDS_MAX; words++) {
                pk_count_from_here();
                TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(target, words));
                if (words <= left) {
                    TEST_ASSERT_FALSE_MESSAGE(refused,
                        "a longer burst became OK after a shorter one was refused");
                    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peekw_status);
                    TEST_ASSERT_EQUAL_UINT(words, s_pk_reads);
                    TEST_ASSERT_EQUAL_HEX32(target, s_pk_min);
                    TEST_ASSERT_TRUE(s_pk_max <= region[r].last);
                } else {
                    refused = true;
                    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peekw_status);
                    TEST_ASSERT_EQUAL_UINT(0u, s_pk_reads);
                }
            }
        }
        /* One word BEFORE the region, a burst that would end inside it is
         * still refused: a burst must start in the region it reads. */
        uint32_t below = region[r].first - 4u;
        for (uint16_t words = 1u; words <= O2P_PEEKW_WORDS_MAX; words++) {
            pk_count_from_here();
            TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(below, words));
            TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peekw_status);
            TEST_ASSERT_EQUAL_UINT(0u, s_pk_reads);
        }
    }
    /* Address overflow: bursts whose last word would wrap past 0xFFFFFFFF. */
    static const uint32_t wraps[] = { 0xFFFFFFFCu, 0xFFFFFFF0u, 0xFFFFFF90u, 0xFFFFFF8Cu };
    for (unsigned i = 0; i < sizeof wraps / sizeof wraps[0]; i++) {
        pk_count_from_here();
        TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(wraps[i], O2P_PEEKW_WORDS_MAX));
        TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_RANGE, rm.peekw_status);
        TEST_ASSERT_EQUAL_UINT(0u, s_pk_reads);
    }
}

static void test_peekw_seq_counts_executed_triggers_and_skips_zero(void)
{
    rm.peekw_seq = 0xFFFFu;
    TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(0x20000000u, 1u));
    TEST_ASSERT_EQUAL_UINT16(1u, rm.peekw_seq);
    /* A refusal by STATUS is an executed trigger: it replaced the result. */
    TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(0x20000001u, 1u));
    TEST_ASSERT_EQUAL_UINT16(2u, rm.peekw_seq);
    /* A refusal by EXCEPTION is not: nothing was replaced. */
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, pkw_trigger(0x20000000u, 0u));
    TEST_ASSERT_EQUAL_UINT16(2u, rm.peekw_seq);
}

/* N1 (independent review, 2026-09-10): the snapshot copy's destination is
 * g_rm's own SRAM buffer, so a peek of SRAM can name the words being copied
 * into. This drives peek_load through a hook that ALIASES the real regmap
 * object - the exact relation the address-derived oracle cannot express - and
 * checks that an overlapping burst comes back as the source held BEFORE the
 * copy. The ascending-only copy read words a lower store had already
 * clobbered; the memmove-safe copy does not. */
static uint32_t pk_alias_base;
static uint32_t pk_alias_load(uint32_t a)
{
    s_pk_reads++;
    if (o2p_peek_host_irq_depth <= 0) {
        s_pk_unmasked++;
    }
    uint32_t w;
    memcpy(&w, (const char *)&rm + (a - pk_alias_base), sizeof w);
    return w;
}
static uint32_t pk_alias_dst_addr(const uint32_t *dst)
{
    return pk_alias_base + (uint32_t)((const char *)dst - (const char *)&rm);
}
static void test_peekw_overlapping_its_own_buffer_copies_the_source_not_a_clobber(void)
{
    o2p_regmap_init(&rm);
    pk_alias_base = 0x20000000u;   /* peek 0x20000000 == &rm[0] */
    o2p_peek_host_read = pk_alias_load;
    o2p_peek_host_dst_addr = pk_alias_dst_addr;
    s_pk_unmasked = 0u;

    for (unsigned i = 0; i < O2P_PEEKW_WORDS_MAX; i++) {
        rm.peekw_words[i] = 0x11111111u * (i + 1u);
    }
    /* Source starts one word BELOW the destination buffer, so [target, +4w)
     * overlaps peekw_words from below - the case that corrupts ascending. */
    uint32_t target = pk_alias_dst_addr(rm.peekw_words) - 4u;
    uint32_t expect[4];
    for (unsigned i = 0; i < 4u; i++) {
        memcpy(&expect[i], (const char *)&rm + (target + 4u * i - pk_alias_base), 4u);
    }
    TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(target, 4u));
    TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peekw_status);
    for (unsigned i = 0; i < 4u; i++) {
        TEST_ASSERT_EQUAL_HEX32_MESSAGE(expect[i], rm.peekw_words[i],
            "an overlapping peek returned a word its own copy had overwritten");
    }
    /* The direction choice is made outside the mask; the copy still ran with
     * interrupts masked throughout. */
    TEST_ASSERT_EQUAL_UINT(0u, s_pk_unmasked);
    o2p_peek_host_read = NULL;
    o2p_peek_host_dst_addr = NULL;
}

/* Both blocks answer from one validator. If they ever disagree about a target
 * and a length, one of them is dereferencing something the other thinks is
 * unsafe. */
static void test_peekw_and_the_4_word_mailbox_share_one_idea_of_safe(void)
{
    pk_arm();
    static const uint32_t targets[] = {
        0x20008FF0u, 0x20008FF4u, 0x20008FF8u, 0x20008FFCu, 0x20009000u,
        0x08010FF8u, 0x08011000u, 0x1FFF7590u, 0x1FFF7594u, 0x1FFF7598u,
        0x1FFF75E0u, 0x1FFF75E4u, 0x20000002u, 0x40000000u, 0xFFFFFFFCu,
    };
    for (unsigned i = 0; i < sizeof targets / sizeof targets[0]; i++) {
        for (uint16_t words = 1u; words <= 4u; words++) {
            uint16_t narrow[3] = { (uint16_t)(targets[i] >> 16),
                                   (uint16_t)(targets[i] & 0xFFFFu), words };
            TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, narrow));
            TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(targets[i], words));
            TEST_ASSERT_EQUAL_UINT16(rm.peek_status, rm.peekw_status);
            for (unsigned w = 0; w < 4u; w++) {
                TEST_ASSERT_EQUAL_HEX32(rm.peek_words[w], rm.peekw_words[w]);
            }
        }
    }
    /* The 4-word mailbox's copy is masked too, now that it is the same copy. */
    TEST_ASSERT_EQUAL_UINT(0u, s_pk_unmasked);
}

/* One target through BOTH blocks: the status each publishes, and exactly the
 * dereferences an OK makes - none for a refusal. */
static void pk_expect(uint32_t a, uint16_t words, uint16_t st)
{
    char msg[64];
    snprintf(msg, sizeof msg, "target 0x%08lX, %u words", (unsigned long)a, words);
    pk_count_from_here();
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0u, pkw_trigger(a, words), msg);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(st, rm.peekw_status, msg);
    TEST_ASSERT_EQUAL_UINT_MESSAGE(st == O2P_PEEK_OK ? words : 0u, s_pk_reads, msg);
    if (words <= 4u) {
        uint16_t t[3] = { (uint16_t)(a >> 16), (uint16_t)(a & 0xFFFFu), words };
        pk_count_from_here();
        TEST_ASSERT_EQUAL_HEX8_MESSAGE(0u, o2p_regmap_write(&rm, O2P_REG_PEEK_BASE, 3u, t), msg);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(st, rm.peek_status, msg);
        TEST_ASSERT_EQUAL_UINT_MESSAGE(st == O2P_PEEK_OK ? words : 0u, s_pk_reads, msg);
    }
}

/* Review R2: the FIRST word of every region is readable. The far-tail test
 * walks each region's end and refuses the word below its start, so a lower
 * bound moved up by one word (flash from 0x08000004) passed everything. */
static void test_peek_the_first_word_of_every_region_is_readable(void)
{
    pk_arm();
    static const uint32_t first[] = { 0x20000000u, 0x08000000u, 0x1FFF7590u, 0x1FFF75E0u };
    for (unsigned r = 0; r < sizeof first / sizeof first[0]; r++) {
        pk_expect(first[r], 1u, O2P_PEEK_OK);
        TEST_ASSERT_EQUAL_HEX32(first[r], s_pk_min);
        pk_expect(first[r] - 4u, 1u, O2P_PEEK_ERR_RANGE);
    }
}

#define PK_OPTR_PARITY_ON (0xFFFFFFFFu & ~(1uL << 22))

/* Review F1. With RAM_PARITY_CHECK enabled, only what startup wrote may be
 * dereferenced. The seam's map is the 2026-09-10 env:o2probe one: SHARED
 * 0x20000000..0F, .data 0x20000010..87, .bss 0x20000088..0x2000058B. */
static void test_peek_parity_on_reads_only_what_startup_wrote(void)
{
    pk_arm();
    static const struct { uint32_t a; uint16_t words; uint16_t on; } cases[] = {
        { 0x20000010u, 30u, O2P_PEEK_OK },          /* first word of .data */
        { 0x20000084u, 2u,  O2P_PEEK_OK },          /* .data into .bss, abutting */
        { 0x20000588u, 1u,  O2P_PEEK_OK },          /* last word of .bss */
        { 0x20000570u, 7u,  O2P_PEEK_OK },          /* ... reached by a burst */
        { 0x20000570u, 8u,  O2P_PEEK_ERR_PARITY },  /* one word too many */
        { 0x2000058Cu, 1u,  O2P_PEEK_ERR_PARITY },  /* heap gap */
        { 0x20000000u, 1u,  O2P_PEEK_ERR_PARITY },  /* SHARED, the boot hand-off */
        { 0x2000000Cu, 2u,  O2P_PEEK_ERR_PARITY },  /* SHARED into .data */
        { 0x20004000u, 4u,  O2P_PEEK_ERR_PARITY },
        { 0x20008FFCu, 1u,  O2P_PEEK_ERR_PARITY },  /* top of the stack */
        { 0x20008FF8u, 3u,  O2P_PEEK_ERR_RANGE },   /* off SRAM: range first */
        { 0x20009000u, 1u,  O2P_PEEK_ERR_RANGE },
        { 0x20000011u, 1u,  O2P_PEEK_ERR_ALIGN },
        { 0x08000000u, 30u, O2P_PEEK_OK },          /* flash is not gated */
        { 0x08010FFCu, 1u,  O2P_PEEK_OK },          /* run-slot tail (N4 bound) */
        { 0x1FFF7590u, 3u,  O2P_PEEK_OK },
        { 0x1FFF75E0u, 1u,  O2P_PEEK_OK },
    };
    /* KNOWN-BAD CALIBRATION FIRST. With the factory option byte every SRAM
     * case above reads OK and dereferences its words - so the refusals below
     * are the gate's doing, not an accident of the targets. */
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        o2p_peek_host_optr = 0xFFFFFFFFu;
        uint16_t off = (cases[i].on == O2P_PEEK_ERR_PARITY) ? O2P_PEEK_OK : cases[i].on;
        pk_expect(cases[i].a, cases[i].words, off);
    }
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        o2p_peek_host_optr = PK_OPTR_PARITY_ON;
        pk_expect(cases[i].a, cases[i].words, cases[i].on);
    }
    /* Bit-exact: bit 22 alone decides, not "the register is nonzero". */
    o2p_peek_host_optr = (uint32_t)(1uL << 22);
    pk_expect(0x20008FFCu, 1u, O2P_PEEK_OK);
    /* UNEVALUABLE: an OPTR that reads 0 - an unclocked flash interface -
     * means ENABLED, and restricts. */
    o2p_peek_host_optr = 0u;
    pk_expect(0x20008FFCu, 1u, O2P_PEEK_ERR_PARITY);
    pk_expect(0x20000100u, 4u, O2P_PEEK_OK);
    TEST_ASSERT_EQUAL_UINT(0u, s_pk_unmasked);
}

/* The far tail of the written span, every burst length: exact at _ebss, and
 * never OK again once refused. Same shape as the region far-tail test. */
static void test_peek_parity_on_far_tail_at_ebss_is_exact_and_monotonic(void)
{
    pk_arm();
    o2p_peek_host_optr = PK_OPTR_PARITY_ON;
    const uint32_t last = 0x20000588u;
    for (uint32_t left = 1u; left <= O2P_PEEKW_WORDS_MAX + 1u; left++) {
        uint32_t target = last - 4u * (left - 1u);
        bool refused = false;
        for (uint16_t words = 1u; words <= O2P_PEEKW_WORDS_MAX; words++) {
            pk_count_from_here();
            TEST_ASSERT_EQUAL_HEX8(0u, pkw_trigger(target, words));
            if (words <= left) {
                TEST_ASSERT_FALSE(refused);
                TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_OK, rm.peekw_status);
                TEST_ASSERT_TRUE(s_pk_max <= last);
            } else {
                refused = true;
                TEST_ASSERT_EQUAL_UINT16(O2P_PEEK_ERR_PARITY, rm.peekw_status);
                TEST_ASSERT_EQUAL_UINT(0u, s_pk_reads);
            }
        }
    }
}

/* What the linker could hand the gate that the 2026-09-10 map does not: a
 * section between .data and .bss, bounds that are not word-aligned, and an
 * empty or inverted span. Each must narrow what is admitted, never widen it. */
static void test_peek_parity_on_odd_linker_maps_only_ever_narrow(void)
{
    pk_arm();
    o2p_peek_host_optr = PK_OPTR_PARITY_ON;

    /* A gap: .data ends at 0x20000080, .bss starts at 0x20000088. */
    o2p_peek_host_edata = 0x20000080u;
    o2p_peek_host_sbss = 0x20000088u;
    pk_expect(0x2000007Cu, 1u, O2P_PEEK_OK);
    pk_expect(0x2000007Cu, 2u, O2P_PEEK_ERR_PARITY);   /* would cross the gap */
    pk_expect(0x20000080u, 1u, O2P_PEEK_ERR_PARITY);   /* in the gap */
    pk_expect(0x20000088u, 30u, O2P_PEEK_OK);
    o2p_peek_host_parity_reset();
    o2p_peek_host_optr = PK_OPTR_PARITY_ON;

    /* Unaligned bounds round INWARD. */
    o2p_peek_host_sdata = 0x20000011u;
    o2p_peek_host_ebss = 0x2000058Eu;
    pk_expect(0x20000010u, 1u, O2P_PEEK_ERR_PARITY);
    pk_expect(0x20000014u, 1u, O2P_PEEK_OK);
    pk_expect(0x20000588u, 1u, O2P_PEEK_OK);
    pk_expect(0x2000058Cu, 1u, O2P_PEEK_ERR_PARITY);
    o2p_peek_host_parity_reset();
    o2p_peek_host_optr = PK_OPTR_PARITY_ON;

    /* Empty, then inverted: nothing in SRAM is admitted. */
    o2p_peek_host_sdata = o2p_peek_host_edata = o2p_peek_host_sbss =
        o2p_peek_host_ebss = 0x20000100u;
    pk_expect(0x20000100u, 1u, O2P_PEEK_ERR_PARITY);
    o2p_peek_host_sdata = o2p_peek_host_edata = o2p_peek_host_sbss = 0x20000500u;
    o2p_peek_host_ebss = 0x20000100u;
    pk_expect(0x20000100u, 1u, O2P_PEEK_ERR_PARITY);
    pk_expect(0x200004FCu, 1u, O2P_PEEK_ERR_PARITY);
    pk_expect(0x08004000u, 4u, O2P_PEEK_OK);
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
    rm.diag_pending = false;

    /* OP_READ_TMP_REG accepts dev 0 (tip) and dev 1 (ext I2C) */
    uint16_t cmd_tmp[2] = { (uint16_t)(0x5A00u | O2P_OP_READ_TMP_REG), 0x0000u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_DMBOX_BASE, 2u, cmd_tmp));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_PENDING, rm.diag_status);
    rm.diag_pending = false;

    uint16_t cmd_tmp_ext[2] = { (uint16_t)(0x5A00u | O2P_OP_READ_TMP_REG), 0x0100u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm, O2P_REG_DMBOX_BASE, 2u, cmd_tmp_ext));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_PENDING, rm.diag_status);
    rm.diag_pending = false;

    /* An unassigned opcode is refused */
    uint16_t cmd_bad_op[2] = { (uint16_t)(0x5A00u | 0x09u), 0x0000u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm, O2P_REG_DMBOX_BASE, 2u, cmd_bad_op));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_OPCODE, rm.diag_status);
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

/* ------------------------------------------------- OP_READ_GPIO, 0x5A08
 *
 * Driven through o2p_regmap_write/read - the Modbus handlers - against the
 * counting GPIO/RCC fake in gpio_hal_host.c. Every refusal is checked by what
 * was NOT loaded, not only by the status it returned. */

/* The LQFP48 I/O pads of the STM32G071CBT7, as NAMES. Deliberately not the
 * masks in gpio_diag.h: a typo in a mask must not be able to agree with itself.
 * Source cited at O2P_GPIO_BONDED_A. */
static const char *const k_lqfp48_io[] = {
    "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7",
    "PA8", "PA9", "PA10", "PA11", "PA12", "PA13", "PA14", "PA15",
    "PB0", "PB1", "PB2", "PB3", "PB4", "PB5", "PB6", "PB7",
    "PB8", "PB9", "PB10", "PB11", "PB12", "PB13", "PB14", "PB15",
    "PC6", "PC7", "PC13", "PC14", "PC15",
    "PD0", "PD1", "PD2", "PD3",
    "PF0", "PF1", "PF2",
};

static bool gpio_named_on_package(unsigned port, unsigned pin)
{
    for (size_t i = 0; i < sizeof k_lqfp48_io / sizeof k_lqfp48_io[0]; i++) {
        const char *s = k_lqfp48_io[i];
        unsigned p = (s[1] == 'F') ? 5u : (unsigned)(s[1] - 'A');
        if (p == port && (unsigned)atoi(s + 2) == pin) {
            return true;
        }
    }
    return false;
}

#define GPIO_R0_MODE(r) ((unsigned)((r) & O2P_GPIO_R0_MODE_MASK))
#define GPIO_R0_PULL(r) ((unsigned)(((r) & O2P_GPIO_R0_PULL_MASK) >> O2P_GPIO_R0_PULL_SHIFT))
#define GPIO_R0_AF(r)   ((unsigned)(((r) & O2P_GPIO_R0_AF_MASK) >> O2P_GPIO_R0_AF_SHIFT))

static uint8_t gpio_cmd_raw(uint16_t count, uint16_t op, uint16_t param)
{
    uint16_t w[2] = { (uint16_t)(O2P_DIAG_MAGIC | op), param };
    return o2p_regmap_write(&rm, O2P_REG_DMBOX_BASE, count, w);
}

static uint8_t gpio_cmd(unsigned port, unsigned pin)
{
    return gpio_cmd_raw(2u, O2P_OP_READ_GPIO, O2P_GPIO_PARAM(port, pin));
}

/* DIAG_STATUS, RDATA0, RDATA1, RDATA2, CRC_STATUS - as a master reads them. */
static void gpio_result(uint16_t out[5])
{
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_DIAG_STATUS, 5u, out));
}

static void fake_field(uint32_t *reg, unsigned width, unsigned index, uint32_t v)
{
    uint32_t mask = ((1u << width) - 1u) << (width * index);
    *reg = (*reg & ~mask) | ((v << (width * index)) & mask);
}

static void fake_pin(unsigned port, unsigned pin, unsigned mode, unsigned pull,
                     unsigned open_drain, unsigned af)
{
    o2p_host_gpio_regs_t *g = &o2p_host_gpio[port];
    fake_field(&g->MODER, 2u, pin, mode);
    fake_field(&g->PUPDR, 2u, pin, pull);
    fake_field(&g->OTYPER, 1u, pin, open_drain);
    fake_field(&g->AFR[pin >> 3], 4u, pin & 7u, af);
}

static void test_gpio_an_analog_pin_is_not_sampled_whatever_its_idr_bit_says(void)
{
    /* PB1, the ADS1119's DRDY, in the mode it sat in for a whole bring-up.
     * The pad's voltage cannot reach IDR in analog mode, so neither a 1 nor a
     * 0 in the fake's IDR bit may come back as a level - and the known-bad is
     * the 0, which is what the real part shows and what looked like LOW. */
    o2p_host_gpio_reset();
    fake_pin(O2P_GPIO_PORT_B, 1u, O2P_GPIO_MODE_ANALOG, O2P_GPIO_PULL_DOWN, 0u, 0x3u);
    const uint32_t idr[] = { 0x0002u, 0x0000u, 0xFFFFu, 0xFFFDu };
    for (size_t i = 0; i < sizeof idr / sizeof idr[0]; i++) {
        o2p_host_gpio[O2P_GPIO_PORT_B].IDR = idr[i];
        TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_B, 1u));
        uint16_t r[5];
        gpio_result(r);
        TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_GPIO_NOT_SAMPLED, r[0]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[1] & (O2P_GPIO_R0_LEVEL | O2P_GPIO_R0_LEVEL_VALID));
        /* ...and the configuration that explains WHY still goes out. */
        TEST_ASSERT_TRUE((r[1] & O2P_GPIO_R0_CONFIG_VALID) != 0u);
        TEST_ASSERT_EQUAL_UINT(O2P_GPIO_MODE_ANALOG, GPIO_R0_MODE(r[1]));
        TEST_ASSERT_EQUAL_UINT(O2P_GPIO_PULL_DOWN, GPIO_R0_PULL(r[1]));
        TEST_ASSERT_EQUAL_UINT(3u, GPIO_R0_AF(r[1]));
        TEST_ASSERT_EQUAL_HEX16((uint16_t)idr[i], r[2]);
        TEST_ASSERT_TRUE((r[4] & (1u << 1)) != 0u);   /* analog mask names PB1 */
    }
}

static void test_gpio_an_input_pin_reports_its_real_level_both_ways(void)
{
    /* Both extremes of the shift and of the AFR split, plus the DRDY pin. The
     * other fifteen IDR bits are always the OPPOSITE of the pin's, so reading
     * the wrong bit cannot pass by agreeing. */
    const struct { uint8_t port, pin; } pins[] = {
        { O2P_GPIO_PORT_B, 1u }, { O2P_GPIO_PORT_A, 0u },
        { O2P_GPIO_PORT_B, 15u }, { O2P_GPIO_PORT_C, 13u }, { O2P_GPIO_PORT_A, 8u },
    };
    for (size_t i = 0; i < sizeof pins / sizeof pins[0]; i++) {
        unsigned port = pins[i].port, pin = pins[i].pin;
        for (unsigned level = 0; level < 2u; level++) {
            o2p_host_gpio_reset();
            fake_pin(port, pin, O2P_GPIO_MODE_INPUT, O2P_GPIO_PULL_UP, 0u, 0u);
            uint32_t idr = level ? (1u << pin) : (0xFFFFu & ~(1u << pin));
            o2p_host_gpio[port].IDR = idr;
            TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(port, pin));
            uint16_t r[5];
            gpio_result(r);
            TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, r[0]);
            TEST_ASSERT_TRUE((r[1] & O2P_GPIO_R0_LEVEL_VALID) != 0u);
            TEST_ASSERT_EQUAL_UINT(level, (r[1] & O2P_GPIO_R0_LEVEL) ? 1u : 0u);
            TEST_ASSERT_EQUAL_UINT(O2P_GPIO_MODE_INPUT, GPIO_R0_MODE(r[1]));
            TEST_ASSERT_EQUAL_HEX16((uint16_t)idr, r[2]);
            TEST_ASSERT_EQUAL_HEX16(0u, r[4] & (1u << pin));
        }
    }
}

static void test_gpio_an_output_pin_reports_latch_and_level_separately(void)
{
    /* PC6, the RS-485 DE. ODR is what the firmware asked for and IDR is what
     * the pad did; a stuck or overloaded driver is the case where they differ,
     * and a decoder that published one as the other would hide it. */
    for (unsigned odr = 0; odr < 2u; odr++) {
        for (unsigned idr = 0; idr < 2u; idr++) {
            o2p_host_gpio_reset();
            fake_pin(O2P_GPIO_PORT_C, 6u, O2P_GPIO_MODE_OUTPUT, O2P_GPIO_PULL_NONE, 0u, 0u);
            o2p_host_gpio[O2P_GPIO_PORT_C].ODR = odr ? (1u << 6) : (0xFFFFu & ~(1u << 6));
            o2p_host_gpio[O2P_GPIO_PORT_C].IDR = idr ? (1u << 6) : (0xFFFFu & ~(1u << 6));
            TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_C, 6u));
            uint16_t r[5];
            gpio_result(r);
            TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, r[0]);
            TEST_ASSERT_EQUAL_UINT(O2P_GPIO_MODE_OUTPUT, GPIO_R0_MODE(r[1]));
            TEST_ASSERT_EQUAL_UINT(odr, (r[1] & O2P_GPIO_R0_ODR) ? 1u : 0u);
            TEST_ASSERT_EQUAL_UINT(idr, (r[1] & O2P_GPIO_R0_LEVEL) ? 1u : 0u);
            TEST_ASSERT_TRUE((r[1] & O2P_GPIO_R0_LEVEL_VALID) != 0u);
            TEST_ASSERT_EQUAL_HEX16((uint16_t)o2p_host_gpio[O2P_GPIO_PORT_C].ODR, r[3]);
            TEST_ASSERT_EQUAL_HEX16((uint16_t)o2p_host_gpio[O2P_GPIO_PORT_C].IDR, r[2]);
        }
    }
}

static void test_gpio_an_unclocked_port_is_refused_without_loading_it(void)
{
    /* D and F are bonded and never clocked (mcu.c enables A, B, C). */
    const struct { uint8_t port, pin; uint32_t iopenr; } cases[] = {
        { O2P_GPIO_PORT_D, 0u, 0x07u },
        { O2P_GPIO_PORT_F, 2u, 0x07u },
        { O2P_GPIO_PORT_B, 1u, 0x05u },
        { O2P_GPIO_PORT_A, 0u, 0x00u },
        /* The far tail: every OTHER enable bit set, this port's clear. */
        { O2P_GPIO_PORT_B, 7u, 0xFFFFFFFFu & ~(1u << O2P_GPIO_PORT_B) },
        { O2P_GPIO_PORT_F, 0u, 0xFFFFFFFFu & ~(1u << O2P_GPIO_PORT_F) },
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        o2p_host_gpio_reset();
        o2p_host_iopenr = cases[i].iopenr;
        /* A plausible input pin at HIGH behind the gate, so a gate that leaked
         * would publish a believable result rather than the fake's poison. */
        fake_pin(cases[i].port, cases[i].pin, O2P_GPIO_MODE_INPUT, 0u, 0u, 0u);
        o2p_host_gpio[cases[i].port].IDR = 0xFFFFu;
        TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(cases[i].port, cases[i].pin));
        uint16_t r[5];
        gpio_result(r);
        TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_GPIO_UNCLOCKED, r[0]);
        TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_reads);
        TEST_ASSERT_EQUAL_UINT(1u, o2p_host_rcc_reads);
        TEST_ASSERT_EQUAL_HEX16(0u, r[1]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[2]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[3]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[4]);
        /* Never woken up to be looked at. */
        TEST_ASSERT_EQUAL_HEX32(cases[i].iopenr, o2p_host_iopenr);
    }

    /* And the gate opens exactly when the bit does: D with its clock on. */
    o2p_host_gpio_reset();
    o2p_host_iopenr |= (1u << O2P_GPIO_PORT_D);
    fake_pin(O2P_GPIO_PORT_D, 0u, O2P_GPIO_MODE_INPUT, 0u, 0u, 0u);
    TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_D, 0u));
    uint16_t r[5];
    gpio_result(r);
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, r[0]);
    TEST_ASSERT_EQUAL_UINT(6u, o2p_host_gpio_reads);
}

static void test_gpio_an_absent_pin_is_refused_without_loading_anything(void)
{
    const uint16_t params[] = {
        O2P_GPIO_PARAM(O2P_GPIO_PORT_C, 0u),   /* PC0: in the die, not on the LQFP48 */
        O2P_GPIO_PARAM(O2P_GPIO_PORT_C, 5u),
        O2P_GPIO_PARAM(O2P_GPIO_PORT_C, 8u),
        O2P_GPIO_PARAM(O2P_GPIO_PORT_C, 12u),
        O2P_GPIO_PARAM(O2P_GPIO_PORT_D, 4u),
        O2P_GPIO_PARAM(O2P_GPIO_PORT_D, 15u),
        O2P_GPIO_PARAM(O2P_GPIO_PORT_F, 3u),
        O2P_GPIO_PARAM(O2P_GPIO_PORT_A, 16u),  /* pin 16 */
        O2P_GPIO_PARAM(O2P_GPIO_PORT_B, 0xFFu),
        O2P_GPIO_PARAM(4u, 0u),                /* port E, which this part lacks */
        O2P_GPIO_PARAM(4u, 3u),
        O2P_GPIO_PARAM(6u, 0u),
        O2P_GPIO_PARAM(0xFFu, 0u),             /* port 0xFF */
        0xFFFFu,
    };
    for (size_t i = 0; i < sizeof params / sizeof params[0]; i++) {
        o2p_host_gpio_reset();
        /* Every clock on: the refusal must not lean on the clock gate. */
        o2p_host_iopenr = 0xFFFFFFFFu;
        TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd_raw(2u, O2P_OP_READ_GPIO, params[i]));
        uint16_t r[5];
        gpio_result(r);
        TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_GPIO_NO_PIN, r[0]);
        TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_reads);
        TEST_ASSERT_EQUAL_UINT(0u, o2p_host_rcc_reads);
        TEST_ASSERT_EQUAL_HEX16(0u, r[1]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[2]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[3]);
        TEST_ASSERT_EQUAL_HEX16(0u, r[4]);
        uint16_t p = 0u;
        TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm, O2P_REG_DIAG_PARAM, 1u, &p));
        TEST_ASSERT_EQUAL_HEX16(params[i], p);   /* the refusal says what it refused */
    }
}

static void test_gpio_every_parameter_is_classified_by_the_package(void)
{
    /* All 65536 parameters, every clock on, every pin an input: exactly the
     * pads named in k_lqfp48_io come back OK with six loads, and everything
     * else - however far out - is refused with none. */
    unsigned ok = 0u;
    for (uint32_t param = 0; param <= 0xFFFFu; param++) {
        o2p_host_gpio_reset();
        o2p_host_iopenr = 0xFFFFFFFFu;
        for (unsigned p = 0; p < O2P_GPIO_PORT_SLOTS; p++) {
            o2p_host_gpio[p].MODER = 0u;
        }
        rm.diag_pending = false;
        TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd_raw(2u, O2P_OP_READ_GPIO, (uint16_t)param));
        unsigned port = param >> 8, pin = param & 0xFFu;
        if (gpio_named_on_package(port, pin)) {
            TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, rm.diag_status);
            TEST_ASSERT_EQUAL_UINT(6u, o2p_host_gpio_reads);
            TEST_ASSERT_TRUE(o2p_gpio_pin_bonded((uint8_t)port, (uint8_t)pin));
            ok++;
        } else {
            TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_GPIO_NO_PIN, rm.diag_status);
            TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_reads + o2p_host_rcc_reads);
        }
    }
    /* 44 I/O on the LQFP48. */
    TEST_ASSERT_EQUAL_UINT(44u, ok);
    TEST_ASSERT_EQUAL_UINT(sizeof k_lqfp48_io / sizeof k_lqfp48_io[0], ok);
}

static void test_gpio_decodes_each_field_from_its_own_bits(void)
{
    /* The pin under test and its fifteen neighbours carry opposite values in
     * every field, at the shift extremes and on both sides of the AFRL/AFRH
     * split, so an off-by-one index cannot decode the right answer. */
    const uint8_t pins[] = { 0u, 7u, 8u, 13u, 15u };
    for (size_t i = 0; i < sizeof pins; i++) {
        unsigned pin = pins[i];
        for (unsigned variant = 0; variant < 2u; variant++) {
            unsigned mode = variant ? O2P_GPIO_MODE_AF : O2P_GPIO_MODE_OUTPUT;
            unsigned pull = variant ? O2P_GPIO_PULL_DOWN : O2P_GPIO_PULL_RESERVED;
            unsigned od = variant;
            unsigned af = variant ? 0xBu : 0x4u;
            o2p_host_gpio_reset();
            for (unsigned n = 0; n < 16u; n++) {
                fake_pin(O2P_GPIO_PORT_A, n, variant ? O2P_GPIO_MODE_INPUT : O2P_GPIO_MODE_AF,
                         variant ? O2P_GPIO_PULL_UP : O2P_GPIO_PULL_NONE, !variant, (~af) & 0xFu);
            }
            fake_pin(O2P_GPIO_PORT_A, pin, mode, pull, od, af);
            o2p_host_gpio[O2P_GPIO_PORT_A].ODR = variant ? (1u << pin) : (0xFFFFu & ~(1u << pin));
            o2p_host_gpio[O2P_GPIO_PORT_A].IDR = variant ? (0xFFFFu & ~(1u << pin)) : (1u << pin);
            TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_A, pin));
            uint16_t r[5];
            gpio_result(r);
            TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, r[0]);
            TEST_ASSERT_EQUAL_UINT(mode, GPIO_R0_MODE(r[1]));
            TEST_ASSERT_EQUAL_UINT(pull, GPIO_R0_PULL(r[1]));
            TEST_ASSERT_EQUAL_UINT(od, (r[1] & O2P_GPIO_R0_OPEN_DRAIN) ? 1u : 0u);
            TEST_ASSERT_EQUAL_UINT(af, GPIO_R0_AF(r[1]));
            TEST_ASSERT_EQUAL_UINT(variant, (r[1] & O2P_GPIO_R0_ODR) ? 1u : 0u);
            TEST_ASSERT_EQUAL_UINT(!variant, (r[1] & O2P_GPIO_R0_LEVEL) ? 1u : 0u);
            TEST_ASSERT_EQUAL_HEX16(0u, r[1] & 0x3080u);   /* reserved bits stay 0 */
            TEST_ASSERT_EQUAL_HEX16(0u, r[4]);             /* nothing analog on A */
        }
    }
}

static void test_gpio_snapshot_is_one_masked_section_and_writes_nothing(void)
{
    o2p_host_gpio_reset();
    fake_pin(O2P_GPIO_PORT_C, 7u, O2P_GPIO_MODE_OUTPUT, O2P_GPIO_PULL_NONE, 0u, 0u);
    o2p_host_gpio[O2P_GPIO_PORT_C].ODR = 0x0080u;
    o2p_host_gpio[O2P_GPIO_PORT_C].IDR = 0x2080u;
    o2p_host_gpio_regs_t before[O2P_GPIO_PORT_SLOTS];
    memcpy(before, o2p_host_gpio, sizeof before);
    uint32_t iopenr_before = o2p_host_iopenr;

    TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_C, 7u));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, rm.diag_status);
    TEST_ASSERT_EQUAL_UINT(6u, o2p_host_gpio_reads);
    TEST_ASSERT_EQUAL_UINT(1u, o2p_host_rcc_reads);
    /* The clock check and all six loads inside ONE mask, and the mask undone. */
    TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_unmasked_reads);
    TEST_ASSERT_EQUAL_UINT(0u, o2p_host_rcc_unmasked_reads);
    TEST_ASSERT_EQUAL_INT(0, o2p_host_gpio_irq_depth);
    TEST_ASSERT_EQUAL_MEMORY(before, o2p_host_gpio, sizeof before);
    TEST_ASSERT_EQUAL_HEX32(iopenr_before, o2p_host_iopenr);
    /* Served in the write: nothing is left for main.c to run. */
    TEST_ASSERT_FALSE(rm.diag_pending);
}

static void test_gpio_is_reachable_through_the_modbus_pdu_layer(void)
{
    /* The whole path a master uses, frames and all: FC16 of [0x5A08, PB1] to
     * 0x0070, then FC03 of the seven mailbox registers. */
    o2p_host_gpio_reset();
    fake_pin(O2P_GPIO_PORT_B, 1u, O2P_GPIO_MODE_INPUT, O2P_GPIO_PULL_NONE, 0u, 0u);
    o2p_host_gpio[O2P_GPIO_PORT_B].IDR = 0x0002u;

    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t wr[] = { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04,
                           0x5A, 0x08, 0x01, 0x01 };
    size_t n = framed(req, wr, sizeof wr);
    TEST_ASSERT_EQUAL_UINT(8u, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);

    const uint8_t rd[] = { 0x03, 0x03, 0x00, 0x70, 0x00, 0x07 };
    n = framed(req, rd, sizeof rd);
    TEST_ASSERT_EQUAL_UINT(3u + 14u + 2u, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    uint16_t reg[7];
    for (unsigned i = 0; i < 7u; i++) {
        reg[i] = (uint16_t)((rsp[3 + 2 * i] << 8) | rsp[4 + 2 * i]);
    }
    TEST_ASSERT_EQUAL_HEX16(0x5A08u, reg[0]);
    TEST_ASSERT_EQUAL_HEX16(0x0101u, reg[1]);
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_OK, reg[2]);
    TEST_ASSERT_EQUAL_HEX16(O2P_GPIO_R0_CONFIG_VALID | O2P_GPIO_R0_LEVEL_VALID |
                            O2P_GPIO_R0_LEVEL, reg[3]);

    /* Opcode 0x09 is still nobody's. */
    const uint8_t bad[] = { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04,
                            0x5A, 0x09, 0x01, 0x01 };
    n = framed(req, bad, sizeof bad);
    TEST_ASSERT_EQUAL_UINT(5u, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_HEX8(0x90, rsp[1]);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
}

static void test_gpio_malformed_busy_or_refused_commands_leave_no_stale_level(void)
{
    o2p_host_gpio_reset();
    fake_pin(O2P_GPIO_PORT_B, 1u, O2P_GPIO_MODE_INPUT, O2P_GPIO_PULL_NONE, 0u, 0u);
    o2p_host_gpio[O2P_GPIO_PORT_B].IDR = 0xFFFFu;
    TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_B, 1u));
    TEST_ASSERT_TRUE((rm.diag_rdata0 & O2P_GPIO_R0_LEVEL_VALID) != 0u);

    /* A refusal after a good read must not leave the good read's level
     * readable under the refusal's status. */
    o2p_host_gpio_reset();
    TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_C, 0u));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_GPIO_NO_PIN, rm.diag_status);
    TEST_ASSERT_EQUAL_HEX16(0u, rm.diag_rdata0);
    TEST_ASSERT_EQUAL_HEX16(0u, rm.diag_rdata1);

    /* No parameter: the opcode needs one. Refused like opcodes 0x01/0x05. */
    o2p_host_gpio_reset();
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, gpio_cmd_raw(1u, O2P_OP_READ_GPIO, 0u));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_ERR_OPCODE, rm.diag_status);
    TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_reads + o2p_host_rcc_reads);

    /* A queued I2C opcode owns the result registers until main.c runs it:
     * the GPIO request is refused with exception 06 and writes NOTHING - not
     * even DIAG_STATUS, which is the queued command's. Up to 0x000E this
     * wrote ERR_BUSY there (review F2, 2026-09-10). */
    o2p_host_gpio_reset();
    rm.diag_cmd = (uint16_t)(O2P_DIAG_MAGIC | O2P_OP_READ_LMP_REG);
    rm.diag_param = 0x0010u;
    rm.diag_status = O2P_DMBOX_STATUS_PENDING;
    rm.diag_pending = true;
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_DEVICE_BUSY, gpio_cmd(O2P_GPIO_PORT_B, 1u));
    TEST_ASSERT_EQUAL_UINT16(O2P_DMBOX_STATUS_PENDING, rm.diag_status);
    TEST_ASSERT_EQUAL_HEX16(O2P_DIAG_MAGIC | O2P_OP_READ_LMP_REG, rm.diag_cmd);
    TEST_ASSERT_EQUAL_HEX16(0x0010u, rm.diag_param);
    TEST_ASSERT_TRUE(rm.diag_pending);
    TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_reads + o2p_host_rcc_reads);
    rm.diag_pending = false;
}

/* Review F2, through the WHOLE path a master uses: the dispatch, frames and
 * all. Master 1 queues an I2C opcode; master 2's GPIO query, a second I2C
 * opcode, a bad magic and a malformed frame all arrive before main.c runs it.
 * None of them may change a register master 1 is polling. */
static void test_dmbox_a_busy_refusal_is_exception_06_and_writes_nothing(void)
{
    o2p_host_gpio_reset();
    fake_pin(O2P_GPIO_PORT_B, 1u, O2P_GPIO_MODE_INPUT, O2P_GPIO_PULL_NONE, 0u, 0u);
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];

    const uint8_t queue_lmp[] = { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04,
                                  0x5A, 0x01, 0x00, 0x10 };
    size_t n = framed(req, queue_lmp, sizeof queue_lmp);
    TEST_ASSERT_EQUAL_UINT(8u, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);

    const uint8_t rd[] = { 0x03, 0x03, 0x00, 0x70, 0x00, 0x07 };
    uint8_t before[3u + 14u + 2u];
    n = framed(req, rd, sizeof rd);
    TEST_ASSERT_EQUAL_UINT(sizeof before, o2p_mb_dispatch(req, n, 3, &handlers, before));
    TEST_ASSERT_EQUAL_HEX8(0x5A, before[3]);
    TEST_ASSERT_EQUAL_HEX8(O2P_DMBOX_STATUS_PENDING, before[8]);

    static const struct { uint8_t pdu[11]; size_t len; uint8_t ex; } refused[] = {
        /* GPIO PB1 - the reviewer's sequence */
        { { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04, 0x5A, 0x08, 0x01, 0x01 }, 11u, 0x06 },
        /* another I2C opcode */
        { { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04, 0x5A, 0x05, 0x00, 0x0F }, 11u, 0x06 },
        /* a bad magic: while busy, it may not write ERR_OPCODE either */
        { { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04, 0x12, 0x08, 0x01, 0x01 }, 11u, 0x06 },
        /* an opcode nobody owns */
        { { 0x03, 0x10, 0x00, 0x70, 0x00, 0x02, 0x04, 0x5A, 0x09, 0x01, 0x01 }, 11u, 0x06 },
        /* malformed shape: exception 03 as ever, and still nothing written */
        { { 0x03, 0x10, 0x00, 0x71, 0x00, 0x01, 0x02, 0x00, 0x00 }, 9u, 0x03 },
    };
    for (size_t i = 0; i < sizeof refused / sizeof refused[0]; i++) {
        n = framed(req, refused[i].pdu, refused[i].len);
        TEST_ASSERT_EQUAL_UINT(5u, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
        TEST_ASSERT_EQUAL_HEX8(0x90, rsp[1]);
        TEST_ASSERT_EQUAL_HEX8(refused[i].ex, rsp[2]);

        uint8_t after[sizeof before];
        n = framed(req, rd, sizeof rd);
        TEST_ASSERT_EQUAL_UINT(sizeof after, o2p_mb_dispatch(req, n, 3, &handlers, after));
        TEST_ASSERT_EQUAL_HEX8_ARRAY(before, after, sizeof before);
        TEST_ASSERT_TRUE(rm.diag_pending);
    }
    TEST_ASSERT_EQUAL_UINT(0u, o2p_host_gpio_reads + o2p_host_rcc_reads);

    /* Once main.c has run it, the mailbox is free again and GPIO is served. */
    rm.diag_pending = false;
    rm.diag_status = O2P_DMBOX_STATUS_OK;
    n = framed(req, refused[0].pdu, refused[0].len);
    TEST_ASSERT_EQUAL_UINT(8u, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_HEX8(0x10, rsp[1]);
}

static void test_exec_mailbox_operations(void)
{
    o2p_regmap_t rm_local;
    o2p_regmap_init(&rm_local);

    uint16_t out[16];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm_local, O2P_REG_EXEC_BASE, 8u, out));
    TEST_ASSERT_EQUAL_UINT16(0u, out[0]); /* CMD */
    TEST_ASSERT_EQUAL_UINT16(0u, out[1]); /* LEN */
    TEST_ASSERT_EQUAL_UINT16(0u, out[2]); /* PARAM_HI */
    TEST_ASSERT_EQUAL_UINT16(0u, out[3]); /* PARAM_LO */
    TEST_ASSERT_EQUAL_UINT16(50u, out[4]); /* TIMEOUT_MS */
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_NONE, out[5]); /* STATUS */
    TEST_ASSERT_EQUAL_UINT16(0u, out[6]); /* RESULT_HI */
    TEST_ASSERT_EQUAL_UINT16(0u, out[7]); /* RESULT_LO */
    TEST_ASSERT_FALSE(rm_local.exec_pending);

    /* Write 4 halfwords of code to 0x0158 */
    uint16_t code[4] = { 0x4600u, 0x4770u, 0x1234u, 0x5678u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm_local, O2P_REG_EXEC_CODE_BASE, 4u, code));
    uint16_t code_read[4];
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_read(&rm_local, O2P_REG_EXEC_CODE_BASE, 4u, code_read));
    TEST_ASSERT_EQUAL_HEX16_ARRAY(code, code_read, 4);

    /* Invalid length: 0 */
    uint16_t setup_bad_len[5] = { 0x5A01u, 0u, 0x0001u, 0x0002u, 100u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, setup_bad_len));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_ERR_LEN, rm_local.exec_status);
    TEST_ASSERT_FALSE(rm_local.exec_pending);

    /* Invalid length: odd */
    setup_bad_len[1] = 5u;
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, setup_bad_len));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_ERR_LEN, rm_local.exec_status);

    /* Invalid length: > 128 */
    setup_bad_len[1] = 130u;
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, setup_bad_len));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_ERR_LEN, rm_local.exec_status);

    /* Invalid magic */
    uint16_t bad_magic[5] = { 0x1201u, 8u, 0x0001u, 0x0002u, 100u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, bad_magic));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_ERR_OPCODE, rm_local.exec_status);

    /* Valid trigger: length 8, param 0x12345678, timeout 100 */
    uint16_t valid_run[5] = { 0x5A01u, 8u, 0x1234u, 0x5678u, 100u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, valid_run));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_PENDING, rm_local.exec_status);
    TEST_ASSERT_TRUE(rm_local.exec_pending);

    /* While busy, another write is refused with exception 06 SERVER_BUSY */
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_DEVICE_BUSY,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, valid_run));

    /* M1: Abort directly cancels while exec_pending is true */
    uint16_t abort_cmd[1] = { 0x5A00u };
    TEST_ASSERT_EQUAL_HEX8(0u, o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 1u, abort_cmd));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_NONE, rm_local.exec_status);
    TEST_ASSERT_FALSE(rm_local.exec_pending);

    /* M3: Writing strictly to read-only status/result is refused */
    uint16_t ro_write[1] = { 0x1234u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_STATUS, 1u, ro_write));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_RESULT_HI, 2u, ro_write));

    /* Finding 4: Spanning write across TIMEOUT_MS into read-only STATUS is refused */
    uint16_t span_ro[4] = { 50u, 0u, 0u, 0u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_TIMEOUT_MS, 4u, span_ro));

    /* Finding 2: Direct write to EXEC_LEN with invalid value is refused */
    uint16_t bad_direct_len = 7u; /* odd */
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_LEN, 1u, &bad_direct_len));
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_ERR_LEN, rm_local.exec_status);

    /* M2: Rejected command does not mutate staged fields */
    uint16_t prev_len = rm_local.exec_len;
    uint16_t bad_cmd_seq[5] = { 0x1201u, 30u, 0x9999u, 0x8888u, 200u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE,
                           o2p_regmap_write(&rm_local, O2P_REG_EXEC_BASE, 5u, bad_cmd_seq));
    TEST_ASSERT_EQUAL_UINT16(prev_len, rm_local.exec_len);
    TEST_ASSERT_EQUAL_UINT16(O2P_EXEC_STATUS_ERR_OPCODE, rm_local.exec_status);
}

/* Review R1: the analog mask must describe all sixteen pins. Every earlier
 * check looked at low pins only, so a loop that stopped at pin 14 passed. */
static void test_gpio_analog_mask_covers_pin_15_and_pin_0(void)
{
    static const uint16_t want[] = { 0x8000u, 0x0001u, 0xFFFEu, 0x7FFFu, 0xFFFFu };
    for (size_t i = 0; i < sizeof want / sizeof want[0]; i++) {
        o2p_host_gpio_reset();
        o2p_host_gpio_regs_t *g = &o2p_host_gpio[O2P_GPIO_PORT_A];
        g->MODER = 0u;
        for (unsigned p = 0; p < 16u; p++) {
            if ((want[i] >> p) & 1u) {
                fake_field(&g->MODER, 2u, p, O2P_GPIO_MODE_ANALOG);
            }
        }
        /* Query a pin whose own mode is irrelevant to the mask: PA8. */
        TEST_ASSERT_EQUAL_HEX8(0u, gpio_cmd(O2P_GPIO_PORT_A, 8u));
        uint16_t r[5];
        gpio_result(r);
        TEST_ASSERT_EQUAL_HEX16(want[i], r[4]);
    }
}

static void test_gpio_wire_codes_are_the_published_ones(void)
{
    /* Wire contract, FW_VERSION 0x000E. gpio_diag.h, PLAN-MODBUS-DEBUG.md 5.3,
     * FIRMWARE.md and tools/o2p_cli.py all carry these numbers. */
    TEST_ASSERT_EQUAL_HEX8(0x08u, O2P_OP_READ_GPIO);
    TEST_ASSERT_EQUAL_UINT(7u, O2P_DMBOX_STATUS_GPIO_NOT_SAMPLED);
    TEST_ASSERT_EQUAL_UINT(8u, O2P_DMBOX_STATUS_ERR_GPIO_UNCLOCKED);
    TEST_ASSERT_EQUAL_UINT(9u, O2P_DMBOX_STATUS_ERR_GPIO_NO_PIN);
    TEST_ASSERT_EQUAL_HEX16(0x0501u, O2P_GPIO_PARAM(O2P_GPIO_PORT_F, 1u));
    TEST_ASSERT_EQUAL_HEX16(0x8000u, O2P_GPIO_R0_CONFIG_VALID);
    TEST_ASSERT_EQUAL_HEX16(0x4000u, O2P_GPIO_R0_LEVEL_VALID);
    TEST_ASSERT_EQUAL_HEX16(0x0040u, O2P_GPIO_R0_LEVEL);
    TEST_ASSERT_EQUAL_HEX16(0x0020u, O2P_GPIO_R0_ODR);
    TEST_ASSERT_EQUAL_HEX16(0x0010u, O2P_GPIO_R0_OPEN_DRAIN);
    TEST_ASSERT_EQUAL_HEX16(0x0F00u, O2P_GPIO_R0_AF_MASK);
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
    /* The wide peek block is compiled out with the rest: its header, its
     * data, and its trigger all answer as undefined addresses. */
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_read(&rm, 0x0100u, 2u, out));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_read(&rm, 0x0105u, 2u, out));
    uint16_t trig[3] = { 0x2000u, 0x0000u, 1u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_write(&rm, 0x0100u, 3u, trig));
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_write(&rm, 0x0065u, 3u, trig));
}
#endif

#if !O2P_DEBUG_ENABLE
static void test_gpio_opcode_is_compiled_out_with_the_mailbox(void)
{
    /* A nodebug image has no mailbox to carry the opcode, so the pin query is
     * an undefined address like the rest - not an OK with nothing behind it. */
    o2p_regmap_t rm;
    o2p_regmap_init(&rm);
    uint16_t cmd[2] = { 0x5A08u, 0x0101u };
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_write(&rm, 0x0070u, 2u, cmd));
    uint16_t out[5];
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS,
                           o2p_regmap_read(&rm, 0x0072u, 5u, out));
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
    RUN_TEST(test_this_board_cannot_be_commanded_transceiver_deaf);
    RUN_TEST(test_a_stale_chamber_temperature_is_the_dominant_bridge_error);
    RUN_TEST(test_a_scheduled_mask_is_not_a_fault);
    RUN_TEST(test_a_pulse_gap_is_bridged_and_a_dead_sensor_is_not);
    RUN_TEST(test_the_o2_verdict_freeze_cannot_drop_a_state_fault);
    RUN_TEST(test_a_fresh_reading_is_never_overridden_by_the_cache);
    RUN_TEST(test_p_sat_has_exactly_one_implementation);
    RUN_TEST(test_dewpoint_reference_points);
    RUN_TEST(test_dewpoint_refuses_impossible_humidity);
    RUN_TEST(test_dew_margin_sign);
    RUN_TEST(test_heater_healthy_input_actually_heats);
    RUN_TEST(test_a_cold_dry_probe_reports_idle_not_nothing);
    RUN_TEST(test_interlocks_refuse_blind_or_annotate_by_law);
    RUN_TEST(test_supply_fault_annotates_but_does_not_veto);
    RUN_TEST(test_unevaluable_control_quantity_blinds_not_midranges);
    RUN_TEST(test_duty_is_monotonic_in_humidity);
    RUN_TEST(test_duty_clamp_binds);
    RUN_TEST(test_dt_clamp_binds_and_has_hysteresis);
    RUN_TEST(test_tip_limit_is_below_the_hardware_alert);
    RUN_TEST(test_integrator_cannot_wind_up_while_clamped);
    RUN_TEST(test_loop_reaches_setpoint_in_steady_state);
    RUN_TEST(test_runaway_does_not_false_positive_on_cold_start);
    RUN_TEST(test_runaway_latches_on_uncommanded_heat_and_holds_while_it_persists);
    RUN_TEST(test_runaway_needs_the_full_window);
    RUN_TEST(test_runaway_releases_only_after_a_full_window_of_cleared_evidence);
    RUN_TEST(test_runaway_release_needs_every_reference_valid_and_clear);
    RUN_TEST(test_runaway_release_restarts_on_a_marginal_sample_or_a_gap);
    RUN_TEST(test_runaway_release_is_not_credited_across_an_invalid_sample);
    RUN_TEST(test_runaway_release_does_not_count_a_bridged_chamber);
    RUN_TEST(test_the_80c_bath_of_2026_09_10_latches_and_then_releases);
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
    RUN_TEST(test_persistent_tip_loop_regulates_through_no_chamber);
    RUN_TEST(test_dew_law_heats_a_cell_short_of_margin);
    RUN_TEST(test_dew_law_idles_with_margin_to_spare);
    RUN_TEST(test_dew_law_reads_the_cell_not_the_tip_or_the_rh_setpoint);
    RUN_TEST(test_dew_law_falls_back_to_the_rh_law_without_a_cell);
    RUN_TEST(test_dew_law_hand_over_restarts_the_integrator);
    RUN_TEST(test_dew_law_regulates_through_safety);
    RUN_TEST(test_dew_law_clamps_the_tip_at_80c_even_with_safety_armed);
    RUN_TEST(test_dew_law_holds_the_tip_under_its_79c_ceiling);
    RUN_TEST(test_dew_law_without_a_tip_does_not_regulate);
    RUN_TEST(test_dew_law_needs_its_dew_point);
    RUN_TEST(test_dew_law_needs_rh_consent);
    RUN_TEST(test_dew_law_yields_to_a_stored_tip_setpoint);
    RUN_TEST(test_dew_law_duty_is_monotonic_in_margin);
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
    RUN_TEST(test_ext_tmp117_address_and_register_mapping);
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
    RUN_TEST(test_cal_state_reports_an_unverified_bias);
    RUN_TEST(test_a_written_air_point_resets_its_provenance);
    RUN_TEST(test_the_unverified_air_window_is_the_datasheet_population);
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
    RUN_TEST(test_a_torn_commit_keeps_loader_and_application_on_one_identity);
    RUN_TEST(test_the_commit_programs_the_config_record_before_the_block);
    RUN_TEST(test_the_transport_block_clears_the_config_record);
#if O2P_DEBUG_ENABLE
    RUN_TEST(test_peek_mailbox_bounds_and_alignment);
    RUN_TEST(test_peek_burst_length_is_requested_not_assumed);
    RUN_TEST(test_peek_rejects_a_count_outside_one_to_four);
    RUN_TEST(test_a_write_straddling_a_mailbox_is_an_illegal_value);
    RUN_TEST(test_peek_two_register_trigger_still_means_four_words);
    RUN_TEST(test_peekw_reads_as_nothing_held_until_triggered);
    RUN_TEST(test_peekw_one_trigger_and_one_read_return_the_whole_burst);
    RUN_TEST(test_peekw_serves_the_trigger_time_snapshot_not_live_memory);
    RUN_TEST(test_peekw_a_malformed_trigger_changes_nothing_and_touches_no_memory);
    RUN_TEST(test_peekw_refuses_misaligned_and_unmapped_targets_without_dereferencing);
    RUN_TEST(test_peekw_far_tail_of_every_region_is_exact_and_monotonic);
    RUN_TEST(test_peekw_seq_counts_executed_triggers_and_skips_zero);
    RUN_TEST(test_peekw_and_the_4_word_mailbox_share_one_idea_of_safe);
    RUN_TEST(test_peekw_overlapping_its_own_buffer_copies_the_source_not_a_clobber);
    RUN_TEST(test_peek_the_first_word_of_every_region_is_readable);
    RUN_TEST(test_peek_parity_on_reads_only_what_startup_wrote);
    RUN_TEST(test_peek_parity_on_far_tail_at_ebss_is_exact_and_monotonic);
    RUN_TEST(test_peek_parity_on_odd_linker_maps_only_ever_narrow);
    RUN_TEST(test_dmbox_validation_and_opcodes);
    RUN_TEST(test_crash_mailbox_read_and_clear);
    RUN_TEST(test_gpio_an_analog_pin_is_not_sampled_whatever_its_idr_bit_says);
    RUN_TEST(test_gpio_an_input_pin_reports_its_real_level_both_ways);
    RUN_TEST(test_gpio_an_output_pin_reports_latch_and_level_separately);
    RUN_TEST(test_gpio_an_unclocked_port_is_refused_without_loading_it);
    RUN_TEST(test_gpio_an_absent_pin_is_refused_without_loading_anything);
    RUN_TEST(test_gpio_every_parameter_is_classified_by_the_package);
    RUN_TEST(test_gpio_decodes_each_field_from_its_own_bits);
    RUN_TEST(test_gpio_snapshot_is_one_masked_section_and_writes_nothing);
    RUN_TEST(test_gpio_is_reachable_through_the_modbus_pdu_layer);
    RUN_TEST(test_gpio_malformed_busy_or_refused_commands_leave_no_stale_level);
    RUN_TEST(test_dmbox_a_busy_refusal_is_exception_06_and_writes_nothing);
    RUN_TEST(test_exec_mailbox_operations);
    RUN_TEST(test_gpio_analog_mask_covers_pin_15_and_pin_0);
    RUN_TEST(test_gpio_wire_codes_are_the_published_ones);
#else
    RUN_TEST(test_debug_mailboxes_disabled);
    RUN_TEST(test_gpio_opcode_is_compiled_out_with_the_mailbox);
#endif
    return UNITY_END();
}
