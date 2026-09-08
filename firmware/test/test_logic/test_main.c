/* Host tests for the portable half of the o2-probe firmware.
 *
 * Everything here is logic that can be wrong without hardware, which is
 * exactly the logic that is expensive to debug once a probe is potted and its
 * SWD connector is inside the enclosure. Run with:  pio test -e native
 */
#include <unity.h>

#include <math.h>
#include <string.h>

#include "faults.h"
#include "heater_ctl.h"
#include "modbus_pdu.h"
#include "o2.h"
#include "psychro.h"
#include "regmap.h"
#include "tmp117.h"
#include "sht4x.h"
#include "mcu_adc.h"

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
    TEST_ASSERT_EQUAL_UINT(2 * sizeof(int32_t) + 9 * sizeof(uint16_t) + 6,
                           sizeof(o2p_config_t));
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

static void test_measurement_registers_are_not_writable(void)
{
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x06, 0x00, 0x00, 0x07, 0xD0};
    size_t n = framed(req, body, sizeof(body));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, rsp[2]);
}

/* ------------------------------------------------------- oxygen the maths */

static void test_air_calibration_round_trips(void)
{
    o2p_cal_t cal = {0};
    cal.tempco_per_k = 0.0f;
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500));

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
    o2p_cal_t cal = {0};
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
    o2p_cal_t cal = {0};
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500));
    float c = 0;
    TEST_ASSERT_EQUAL(O2P_RANGE, o2p_fraction_from_current(&cal, -70000, 2500, &c));
    TEST_ASSERT_TRUE(c < 0.0f);
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, o2p_encode_percent(O2P_RANGE, c));
}

static void test_overrange_is_not_clamped_into_plausibility(void)
{
    o2p_cal_t cal = {0};
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500));
    float c = 0;
    /* Far above the cell's 30 % overload limit. */
    TEST_ASSERT_EQUAL(O2P_RANGE, o2p_fraction_from_current(&cal, 190000, 2500, &c));
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, o2p_encode_percent(O2P_RANGE, c));
}

static void test_monotonic_across_the_whole_range(void)
{
    /* As the cell current worsens toward zero the reported oxygen must fall
     * monotonically and never flip back into a plausible mid-range value. */
    o2p_cal_t cal = {0};
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500));
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
    o2p_cal_t cal = {0};
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500));
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

static void test_zero_point_round_trips_at_a_low_oxygen_point(void)
{
    /* A known I0 must come back out as the right fraction where it matters -
     * the 2 %O2 end, which is where the compost decision lives and where the
     * zero is the largest term in the budget
     * (../O2-CORRECTION-MODEL-BUDGET.md S3).
     *
     * Truth: I0 = 1000 nA, K = 297821 nA per ln-unit (a 70 uA cell, the LOW
     * edge of Issue 2's 70-130 uA population, not its nominal),
     * so the raw air reading is 71000 nA and the raw current at C = 0.02 is
     *   1000 + 297821 * ln(1/(1-0.02)) = 1000 + 6016.2 = 7016.2 nA. */
    o2p_cal_t cal = {0};
    cal.cal_zero_na = 1000;
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 71000, 2500));

    float c = 0;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 71000, 2500, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, O2P_C_AIR, c);

    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 7016, 2500, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0002f, 0.02f, c);

    /* And the whole point of having the term: ignoring the same 1000 nA -
     * i.e. what today's air-point-only calibration does - reads 2.33 %O2 for a
     * true 2.00 %. That 0.33 pp is the error the budget doc's design A
     * carries at this point, reproduced here rather than asserted in prose. */
    o2p_cal_t folded = {0};
    TEST_ASSERT_TRUE(o2p_calibrate_air(&folded, 71000, 2500));
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&folded, 7016, 2500, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, 0.0233f, c);
}

static void test_negative_zero_is_legal_because_the_sign_gate_is_open(void)
{
    /* SCHEMATIC-REVIEW.md M4 leaves the SGX polarity convention unresolved, so
     * a fitted zero may legitimately come out negative. Refusing negatives
     * would refuse the correct calibration on half the outcomes of that gate. */
    o2p_cal_t cal = {0};
    cal.cal_zero_na = -1000;
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 69000, 2500));

    float c = 0;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 69000, 2500, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, O2P_C_AIR, c);
}

static void test_zero_bound_rejects_the_far_tail_not_just_near_misses(void)
{
    /* Near misses AND the far tail, in both directions. A bound that only
     * holds close to its edge is the classic way a guard flips back to PASS on
     * absurd input - a byte-swapped write is not a near miss, it is 10^7 out. */
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(0));
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(1706));    /* the DS-0637 limit at Issue 2 nominal */
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(O2P_ZERO_CAL_ABS_MAX_NA));
    TEST_ASSERT_TRUE(o2p_cal_zero_plausible(-O2P_ZERO_CAL_ABS_MAX_NA));

    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(O2P_ZERO_CAL_ABS_MAX_NA + 1));
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(-O2P_ZERO_CAL_ABS_MAX_NA - 1));
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(70000));      /* an air point */
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(-70000));
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(292552705));  /* swapped halves */
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(-77856769));
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(INT32_MAX));
    TEST_ASSERT_FALSE(o2p_cal_zero_plausible(INT32_MIN));

    /* Monotonic in the far tail: sweep outward and the verdict must never
     * come back. */
    for (int32_t n = O2P_ZERO_CAL_ABS_MAX_NA + 1; n < 2000000000; n *= 3) {
        TEST_ASSERT_FALSE(o2p_cal_zero_plausible(n));
        TEST_ASSERT_FALSE(o2p_cal_zero_plausible(-n));
    }
}

static void test_calibrate_air_refuses_an_implausible_stored_zero(void)
{
    /* Both paths that can set a calibration must honour both bounds. The air
     * point is taken NET of the stored zero, so an air reading that passes its
     * own check still produces a wrong K against a bogus zero. */
    o2p_cal_t cal = {0};
    cal.cal_zero_na = 50000;                 /* out of window */
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 70000, 2500));
    TEST_ASSERT_EQUAL_INT32(0, cal.cal_air_na);   /* nothing stored */
}

static void test_zero_at_or_above_the_air_point_is_unevaluable(void)
{
    /* Reached only by filling the struct directly - the bounds make it
     * unreachable through either checked path, which is why o2.h asserts that
     * at compile time. The conversion refuses it anyway: a non-positive or
     * tiny K must never produce a number.
     *
     * Note what the failure looks like WITHOUT this check. At net = 1 nA,
     * K = 4.3 nA per ln-unit, so a 7000 nA reading gives exp(-1600) = 0 and
     * C = 1.0000 exactly: finite, positive, and encoded as 100.00 %vol if the
     * RANGE test were ever loosened. It is not "obviously" an error. */
    float c = 12345.0f;

    o2p_cal_t equal = {0};
    equal.cal_air_na = 70000;
    equal.cal_zero_na = 70000;               /* net 0 */
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&equal, 7000, 2500, &c));

    o2p_cal_t above = {0};
    above.cal_air_na = 70000;
    above.cal_zero_na = 90000;               /* net negative */
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&above, 7000, 2500, &c));

    o2p_cal_t sliver = {0};
    sliver.cal_air_na = 70000;
    sliver.cal_zero_na = 69999;              /* net 1 nA */
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&sliver, 7000, 2500, &c));

    /* The other tail: a zero so negative that the net overflows a plain int32
     * subtraction. That must be a rejection, not undefined behaviour. */
    o2p_cal_t overflow = {0};
    overflow.cal_air_na = 70000;
    overflow.cal_zero_na = INT32_MIN;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&overflow, 7000, 2500, &c));

    /* Nothing above wrote a value. */
    TEST_ASSERT_EQUAL_FLOAT(12345.0f, c);
}

static void test_tempco_scales_k_and_not_the_measured_current(void)
{
    /* THE point of moving the correction from S to K. With I0 = 0 the two
     * placements are algebraically identical, so this test says nothing unless
     * I0 != 0; with I0 != 0 it separates them by 27x its tolerance.
     *
     * The comparison is against the placement o2.c used to have - the tempco
     * applied to the MEASURED CURRENT - carried forward naively once a zero
     * exists, i.e. C = 1 - exp(-(S/gain - I0)/K). Note it is NOT enough to
     * subtract the zero and then divide the remainder by the gain: that IS the
     * new law rearranged, and a "check" written that way passes against either
     * implementation. Measured, not assumed: the wrong variant was written into
     * o2.c and this case still passed, which is why the numbers below come from
     * the naive form.
     *
     * Setup, at the ends of the ranges the budget doc says are real:
     *   I0    = 4000 nA        - a badly aged but still in-window zero
     *   K     = 297823 nA/ln-unit (a 70 uA cell, Issue 2's low population edge),
     *                            air point 74000 nA
     *   alpha = +0.5 %/K       - the ceiling O2P_TEMPCO_ABS_MAX_PPM_K allows,
     *                            2.5x the DS-0637 Issue 2 curve
     *   read at 60.00 C against a -20.00 C calibration -> gain = 1.40
     *
     * A true 2.000 %O2 then presents 12424 nA, and:
     *   tempco on K (this code):  2.000 %O2, the truth
     *   tempco on S (the old):    1.623 %O2 - 0.38 pp out, and wrong in the
     *                             direction that makes an anoxic pile look
     *                             more anoxic than it is.
     *
     * This used alpha = +2 %/K, the "solid-membrane bound", until 2026-09-08.
     * That branch is dead physics - Issue 2's published curve is ~+0.2 %/K -
     * and 20000 ppm/K is no longer a storable coefficient, so the case was
     * recomputed at the widest correction the contract now permits. */
    o2p_cal_t cal = {0};
    cal.cal_zero_na = 4000;
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 74000, -2000));
    cal.tempco_per_k = 0.005f;

    float c = 0;
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 12424, 6000, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0002f, 0.02f, c);

    /* The air point itself is unmoved at the calibration temperature - the
     * change must not have shifted the one point that was already right. */
    TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 74000, -2000, &c));
    TEST_ASSERT_FLOAT_WITHIN(0.0005f, O2P_C_AIR, c);

    /* And the invariant behind the whole change, which is sharper than any
     * tolerance: a reading exactly AT the zero current is 0.00 %vol at EVERY
     * temperature, because the zero carries no temperature dependence. Under
     * tempco-on-S it does not even stay non-negative - at 60 C it comes out at
     * -0.55 %vol, i.e. O2P_RANGE rather than O2P_OK. */
    for (int16_t t = 1000; t <= 6000; t = (int16_t)(t + 500)) {
        TEST_ASSERT_EQUAL(O2P_OK, o2p_fraction_from_current(&cal, 4000, t, &c));
        TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, c);
    }
}

static void test_written_zero_point_must_also_be_plausible(void)
{
    /* The register path, with the same swapped-halves failure the air point
     * has. An intended -1200 nA is 0xFFFF 0xFB50; written the wrong way round
     * it is 0xFB50 0xFFFF = -77 856 769 nA, which would make the net air point
     * hugely negative. */
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t swapped[] = {0x03, 0x10, 0x00, 0x42, 0x00, 0x02, 0x04,
                               0xFB, 0x50, 0xFF, 0xFF};
    size_t n = framed(req, swapped, sizeof(swapped));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_INT32(0, rm.cfg.cal_zero_na);

    /* Correctly ordered, the same value is accepted and reads back. */
    const uint8_t good[] = {0x03, 0x10, 0x00, 0x42, 0x00, 0x02, 0x04,
                            0xFF, 0xFF, 0xFB, 0x50};
    n = framed(req, good, sizeof(good));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(8, len);
    TEST_ASSERT_EQUAL_INT32(-1200, rm.cfg.cal_zero_na);

    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x42, 0x00, 0x02};
    n = framed(req, rd, sizeof(rd));
    len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(9, len);
    TEST_ASSERT_EQUAL_HEX16(0xFFFF, (uint16_t)((rsp[3] << 8) | rsp[4]));
    TEST_ASSERT_EQUAL_HEX16(0xFB50, (uint16_t)((rsp[5] << 8) | rsp[6]));

    /* An air point written into the zero registers is refused, and leaves the
     * accepted value standing rather than half-overwriting it. */
    const uint8_t airpoint[] = {0x03, 0x10, 0x00, 0x42, 0x00, 0x02, 0x04,
                                0x00, 0x01, 0x11, 0x70};   /* 70000 nA */
    n = framed(req, airpoint, sizeof(airpoint));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_INT32(-1200, rm.cfg.cal_zero_na);

    /* A single-register FC06 to the HI half alone is refused for the same
     * reason the air point's is: half a value cannot pass the bound. */
    const uint8_t half[] = {0x03, 0x06, 0x00, 0x42, 0x00, 0x10};
    n = framed(req, half, sizeof(half));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_VALUE, rsp[2]);
    TEST_ASSERT_EQUAL_INT32(-1200, rm.cfg.cal_zero_na);
}

/* ---- 2026-09-08 review: bounds on the temperature-correction constants ---- */

static void test_absurd_tempco_is_refused(void)
{
    /* The review's case: cal_air 95000, zero -5000, Tcal 20 C, tempco +20000
     * ppm/K, gas at 60 C returned 4.503 %vol for a true 5.000 % with O2P_OK
     * set. The config that made it possible must not be storable. */
    TEST_ASSERT_FALSE(o2p_tempco_plausible(20000));
    TEST_ASSERT_FALSE(o2p_tempco_plausible(-20000));
    /* The ceiling is provisional and generous over the DS-0637 curve, so a
     * bench characterisation has room; it is not an accuracy certificate. */
    TEST_ASSERT_TRUE(o2p_tempco_plausible(2000));
    TEST_ASSERT_TRUE(o2p_tempco_plausible(-2000));
    TEST_ASSERT_TRUE(o2p_tempco_plausible(0));

    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
    cfg.tempco_ppm_per_k = 20000;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
}

static void test_calibration_temperature_is_bounded(void)
{
    /* Tcal spans the cell's PUBLISHED operating range, -40..+60 C. The bound
     * was briefly -20 C, wrongly described as the cell's rating; -36 C is a
     * legitimate cold-chamber calibration and must be ACCEPTED. */
    TEST_ASSERT_TRUE(o2p_cal_temp_plausible(-3600));
    TEST_ASSERT_TRUE(o2p_cal_temp_plausible(2500));
    TEST_ASSERT_FALSE(o2p_cal_temp_plausible(-4001));
    TEST_ASSERT_FALSE(o2p_cal_temp_plausible(9000));

    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    cfg.cal_temp_c100 = 9000;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));

    /* Tcal -36 C is legitimate on its own - it is inside the cell's rating -
     * so the config layer accepts it. Paired with an out-of-contract
     * coefficient the correction collapses, and the runtime guard returns
     * UNEVALUABLE and NO value rather than a plausible wrong number.
     *
     * (This comment used to call the -10000 ppm/K half "legal by design". It
     * is not: the tempco ceiling refuses it, as
     * test_the_known_collapsed_gain_corner_stays_refused asserts. The prose
     * went stale across the round 6/7 reversal; corrected 2026-09-08.) */
    o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                     .cal_temp_c100 = -3600, .tempco_per_k = -0.010f};
    float c = -1.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, 50000, 6000, &c));
    TEST_ASSERT_EQUAL_FLOAT(-1.0f, c);   /* out_c untouched */
}

static void test_out_of_range_tempco_write_is_refused_over_modbus(void)
{
    /* The bound has to bind on the path an operator actually uses. */
    int16_t before = rm.cfg.tempco_ppm_per_k;
    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    /* FC16, TEMPCO_PPM_K (0x003A) = 20000 (0x4E20). */
    const uint8_t w[] = {0x03, 0x10, 0x00, 0x3A, 0x00, 0x01, 0x02, 0x4E, 0x20};
    size_t n = framed(req, w, sizeof(w));
    size_t rn = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_TRUE(rn > 0);
    TEST_ASSERT_EQUAL_HEX8(0x90, rsp[1]);   /* exception */
    TEST_ASSERT_EQUAL_INT16(before, rm.cfg.tempco_ppm_per_k);
}

static void test_calibrate_and_commit_in_one_frame_defers_the_commit(void)
{
    /* One FC16 spanning CAL_TRIGGER and COMMIT used to raise both flags at
     * once, so the main loop persisted the PRE-calibration image while the
     * calibration landed in RAM only. The commit must now wait for the
     * calibration to be taken. */
    rm.cal_requested = false;
    rm.commit_pending = false;
    rm.commit_after_cal = false;

    uint8_t req[64], rsp[O2P_MB_MAX_ADU];
    /* CAL_TRIGGER is 0x003D, COMMIT 0x003E - adjacent, so one frame covers
     * both. Write the magics into the pair. */
    uint8_t w[] = {0x03, 0x10, 0x00, 0x3D, 0x00, 0x02, 0x04,
                   (uint8_t)(O2P_CAL_MAGIC >> 8), (uint8_t)(O2P_CAL_MAGIC & 0xFF),
                   (uint8_t)(O2P_COMMIT_MAGIC >> 8), (uint8_t)(O2P_COMMIT_MAGIC & 0xFF)};
    size_t n = framed(req, w, sizeof(w));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);

    TEST_ASSERT_TRUE(rm.cal_requested);
    TEST_ASSERT_TRUE(rm.commit_after_cal);
    /* The whole point: nothing is written to flash before the air point. */
    TEST_ASSERT_FALSE(rm.commit_pending);
}

static void test_commit_on_its_own_is_not_deferred(void)
{
    rm.cal_requested = false;
    rm.commit_pending = false;
    rm.commit_after_cal = false;

    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    uint8_t w[] = {0x03, 0x10, 0x00, 0x3E, 0x00, 0x01, 0x02,
                   (uint8_t)(O2P_COMMIT_MAGIC >> 8), (uint8_t)(O2P_COMMIT_MAGIC & 0xFF)};
    size_t n = framed(req, w, sizeof(w));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);

    TEST_ASSERT_TRUE(rm.commit_pending);
    TEST_ASSERT_FALSE(rm.commit_after_cal);
}

/* ---- third review, 2026-09-08 ---- */

static void test_fresh_air_point_above_the_population_is_refused(void)
{
    /* The reorder that fixed provenance removed an implicit veto: an air point
     * taken with the wrong gas used to convert out of range against the OLD
     * constants and trip ADC_RANGE, which refused the calibration. 180 uA is
     * above Issue 2's 130 uA population maximum and a cell does not gain
     * sensitivity with age, so it must not overwrite a good calibration. */
    o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 1200,
                     .cal_temp_c100 = 2500, .tempco_per_k = 0.0f};
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 180000, 2500));
    TEST_ASSERT_EQUAL_INT32(100000, cal.cal_air_na);   /* untouched */

    /* A real air point still calibrates. */
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 105000, 2500));
    TEST_ASSERT_EQUAL_INT32(105000, cal.cal_air_na);
}

static void test_calibration_cannot_store_an_invalid_temperature(void)
{
    /* o2p_calibrate_air() writes cal_temp_c100 straight into the live config.
     * An out-of-range value would make that config fail o2p_config_valid(),
     * which rejects every LATER Modbus write and every commit - the probe
     * would refuse repair over the bus it just made hostile. */
    o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                     .cal_temp_c100 = 2500, .tempco_per_k = 0.0f};
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 100000, 6500));   /* +65 C */
    TEST_ASSERT_EQUAL_INT16(2500, cal.cal_temp_c100);

    /* -40 C is the cell's published floor and must still be accepted: the
     * bound was briefly -20 C, which would have refused a legitimate cold
     * calibration. */
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 100000, -4000));

    /* Whatever this path stores must always leave the config valid. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    cfg.cal_temp_c100 = cal.cal_temp_c100;
    TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
}

static void test_every_storable_calibration_temperature_keeps_config_valid(void)
{
    /* Monotonic sweep of the whole int16 range: the two guards must agree
     * exactly, or a value one accepts and the other rejects bricks writes. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    for (int32_t t = -32768; t <= 32767; t += 7) {
        o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                         .cal_temp_c100 = 2500, .tempco_per_k = 0.0f};
        bool stored = o2p_calibrate_air(&cal, 100000, (int16_t)t);
        if (stored) {
            cfg.cal_temp_c100 = cal.cal_temp_c100;
            TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
        }
    }
}

/* ---- fourth review, 2026-09-08 ---- */

static void test_commit_after_a_separate_cal_trigger_still_waits(void)
{
    /* The DOCUMENTED commissioning procedure is two requests: write
     * CAL_TRIGGER, then COMMIT. The one-frame fix did not cover it, so the
     * commit persisted the PRE-calibration image and the air point was lost at
     * the next power cycle - after both writes returned success. */
    rm.cal_requested = false;
    rm.commit_pending = false;
    rm.commit_after_cal = false;

    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    uint8_t cal[] = {0x03, 0x10, 0x00, 0x3D, 0x00, 0x01, 0x02,
                     (uint8_t)(O2P_CAL_MAGIC >> 8), (uint8_t)(O2P_CAL_MAGIC & 0xFF)};
    size_t n = framed(req, cal, sizeof(cal));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_TRUE(rm.cal_requested);

    uint8_t com[] = {0x03, 0x10, 0x00, 0x3E, 0x00, 0x01, 0x02,
                     (uint8_t)(O2P_COMMIT_MAGIC >> 8), (uint8_t)(O2P_COMMIT_MAGIC & 0xFF)};
    n = framed(req, com, sizeof(com));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);

    /* Must defer, exactly as if both had been in one frame. */
    TEST_ASSERT_TRUE(rm.commit_after_cal);
    TEST_ASSERT_FALSE(rm.commit_pending);
}

static void test_tempco_bound_rejects_gross_corruption_only(void)
{
    /* The bound screens gross implausibility. It does NOT certify accuracy: a
     * plausible-but-wrong coefficient passes and still moves a reading past
     * the decision tolerance, which is why the accuracy claim belongs to
     * calibration data. Nor is it a byte-swap screen: tempco is a single
     * 16-bit register, and 1024 ppm/K (0x0400) swaps to 4 (0x0004) - both
     * pass, silently turning a real coefficient into no correction at all.
     * (An earlier revision used 1000 -> -6141 as the example, which the
     * restored +/-5000 bound actually rejects; corrected 2026-09-08.) */
    TEST_ASSERT_TRUE(o2p_tempco_plausible(2000));    /* the published curve */
    TEST_ASSERT_TRUE(o2p_tempco_plausible(3200));    /* its +3 sigma envelope */
    TEST_ASSERT_TRUE(o2p_tempco_plausible(-3200));
    /* The ceiling is PROVISIONAL and generous over the cell curve, but silence
     * in the LMP91000 datasheet about TIA gain tempco means UNKNOWN, not
     * arbitrarily large. Widening to 10000 reintroduced a known clean-fault
     * failure, so the bound stands and is raised only against a measurement. */
    TEST_ASSERT_TRUE(o2p_tempco_plausible(5000));
    TEST_ASSERT_FALSE(o2p_tempco_plausible(10000));
    TEST_ASSERT_FALSE(o2p_tempco_plausible(32000));
    TEST_ASSERT_FALSE(o2p_tempco_plausible(-32000));
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    cfg.tempco_ppm_per_k = 32000;
    TEST_ASSERT_FALSE(o2p_config_valid(&cfg));
}

static void test_the_known_collapsed_gain_corner_stays_refused(void)
{
    /* Round 4 found it, round 6 reintroduced it by widening the guard: alpha
     * -10000 ppm/K, Tcal -40 C, read at 55 C gives a binary32 gain of
     * 0.0500000194, which passes a `> 0.05f` test and returned ~5 %O2 with
     * O2P_OK from a NEGATIVE current. It must be refused at the config layer
     * AND produce no value if it ever reaches the conversion. */
    TEST_ASSERT_FALSE(o2p_tempco_plausible(-10000));

    o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = -5000,
                     .cal_temp_c100 = -4000, .tempco_per_k = -0.010f};
    float c = -1.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, -3854, 5500, &c));
    TEST_ASSERT_EQUAL_FLOAT(-1.0f, c);
}

static void test_extrapolation_above_60c_still_converts(void)
{
    /* faults.h promises TEMP_OVER is a still-valid extrapolation, and a guard
     * must not silently cancel it. Any REALISTIC calibration - a sane
     * calibration temperature and a coefficient within the cell curve's
     * +/-3 sigma envelope - must convert across the whole operating range
     * including the thermophilic extrapolation to 85 C. */
    for (int32_t ppm = -3200; ppm <= 3200; ppm += 400) {
        for (int32_t tcal = 0; tcal <= 4000; tcal += 500) {
            o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                             .cal_temp_c100 = (int16_t)tcal,
                             .tempco_per_k = (float)ppm * 1e-6f};
            for (int32_t tmeas = -1000; tmeas <= 8500; tmeas += 500) {
                float c = 0.0f;
                TEST_ASSERT_EQUAL_MESSAGE(O2P_OK,
                    o2p_fraction_from_current(&cal, 50000, (int16_t)tmeas, &c),
                    "a realistic calibration must convert across the whole range");
            }
        }
    }
}

static void test_extreme_corner_yields_no_value_rather_than_a_wrong_one(void)
{
    /* The deliberate consequence of a physics-justified window: combining the
     * ceiling coefficient with an extreme calibration temperature asks for a
     * correction that more than halves the cell's sensitivity, which is not a
     * credible temperature correction whatever the register says. That returns
     * UNEVALUABLE and NO value - the tri-state contract working, not the
     * extrapolation contract breaking. Pinned so the distinction is deliberate
     * rather than discovered again. */
    o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                     .cal_temp_c100 = -4000, .tempco_per_k = -0.005f};
    float c = -3.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, 50000, 7000, &c));
    TEST_ASSERT_EQUAL_FLOAT(-3.0f, c);
}

static void test_gain_backstop_still_catches_an_out_of_contract_coefficient(void)
{
    /* The backstop exists for a corrupted float or a caller that bypassed
     * validation - not for coefficients the validator accepts. A tempco that
     * could never be stored must still produce NO value rather than a
     * plausible one. */
    o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                     .cal_temp_c100 = -4000, .tempco_per_k = -0.05f};
    float c = -1.0f;
    TEST_ASSERT_EQUAL(O2P_UNEVALUABLE,
                      o2p_fraction_from_current(&cal, 50000, 6000, &c));
    TEST_ASSERT_EQUAL_FLOAT(-1.0f, c);

    /* Monotonic: once out of contract, worse stays refused. */
    bool seen = false;
    for (int32_t ppm = -20000; ppm >= -60000; ppm -= 500) {
        o2p_cal_t k = {.cal_air_na = 100000, .cal_zero_na = 0,
                       .cal_temp_c100 = -4000,
                       .tempco_per_k = (float)ppm * 1e-6f};
        float v = 0.0f;
        o2p_status_t st = o2p_fraction_from_current(&k, 50000, 6000, &v);
        if (st == O2P_UNEVALUABLE) { seen = true; }
        else { TEST_ASSERT_FALSE(seen); }
    }
    TEST_ASSERT_TRUE(seen);
}

static void test_tmp117_rejects_readings_outside_the_part_range(void)
{
    /* The old check compared the converted value against int16 bounds, which
     * any int16 raw word satisfies by construction - so every bus pattern was
     * accepted as a temperature. A single flipped MSB turns 25 C into -231 C.  */
    TEST_ASSERT_TRUE(O2P_TMP117_MIN_C100 > -25600);   /* i.e. not tautological */
    TEST_ASSERT_TRUE(O2P_TMP117_MAX_C100 <  25599);

    /* 0x0C80 is +25.00 C; clearing the MSB pattern to 0x8C80 is -231.0 C. */
    int32_t good = ((int32_t)(int16_t)0x0C80 * 100) / 128;
    int32_t bad  = ((int32_t)(int16_t)0x8C80 * 100) / 128;
    TEST_ASSERT_EQUAL_INT32(2500, good);
    TEST_ASSERT_TRUE(good >= O2P_TMP117_MIN_C100 && good <= O2P_TMP117_MAX_C100);
    TEST_ASSERT_TRUE(bad < O2P_TMP117_MIN_C100);
}

static void test_fresh_air_ceiling_clears_the_stacked_legal_corner(void)
{
    /* 130 uA population max x 1.05 (temperature) x 1.05 (TIA gain accuracy)
     * x 1.05 (lifetime drift, sign unrestricted by DS-0637) = 150.5 uA. A
     * destructive guard must not reject an allowed corner. */
    TEST_ASSERT_TRUE(O2P_FRESH_AIR_CAL_MAX_NA >= 150500);
    /* But the 180 uA wrong-gas case it exists for is still refused. */
    TEST_ASSERT_TRUE(O2P_FRESH_AIR_CAL_MAX_NA < 180000);
}

/* ---- fifth review, 2026-09-08 ---- */

static void test_legal_configs_either_convert_or_yield_no_value(void)
{
    /* The contract across the whole legal box, including the above-60 C
     * extrapolation the fault word promises: every configuration the
     * validator accepts must either convert, or return UNEVALUABLE with the
     * output UNTOUCHED. What must never happen is a number that is wrong.
     *
     * Some legal configurations ARE arithmetically degenerate - at the
     * corruption-only ceiling a correction can drive the gain through zero -
     * and refusing those is correct: no value beats a wrong one. */
    o2p_config_t cfg;
    o2p_config_defaults(&cfg);
    for (int32_t ppm = -O2P_TEMPCO_ABS_MAX_PPM_K;
         ppm <= O2P_TEMPCO_ABS_MAX_PPM_K; ppm += 500) {
        for (int32_t tcal = O2P_CAL_TEMP_MIN_C100;
             tcal <= O2P_CAL_TEMP_MAX_C100; tcal += 1000) {
            for (int32_t tmeas = -4000; tmeas <= 8000; tmeas += 1000) {
                cfg.tempco_ppm_per_k = (int16_t)ppm;
                cfg.cal_temp_c100 = (int16_t)tcal;
                TEST_ASSERT_TRUE(o2p_config_valid(&cfg));
                o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                                 .cal_temp_c100 = (int16_t)tcal,
                                 .tempco_per_k = (float)ppm * 1e-6f};
                const float sentinel = -7.0f;
                float c = sentinel;
                o2p_status_t st = o2p_fraction_from_current(
                    &cal, 50000, (int16_t)tmeas, &c);
                if (st == O2P_UNEVALUABLE) {
                    TEST_ASSERT_EQUAL_FLOAT(sentinel, c);
                } else {
                    TEST_ASSERT_TRUE(c >= 0.0f && c <= 1.0f);
                }
            }
        }
    }
}

static void test_a_realistic_coefficient_converts_across_the_whole_range(void)
{
    /* The case that must never be refused: a real characterised cell at the
     * published slope, read anywhere from a cold bench to a thermophilic
     * pile. */
    for (int32_t ppm = -3200; ppm <= 3200; ppm += 400) {
        o2p_cal_t cal = {.cal_air_na = 100000, .cal_zero_na = 0,
                         .cal_temp_c100 = 2000,
                         .tempco_per_k = (float)ppm * 1e-6f};
        for (int32_t tmeas = -4000; tmeas <= 8000; tmeas += 500) {
            float c = 0.0f;
            TEST_ASSERT_EQUAL(O2P_OK,
                o2p_fraction_from_current(&cal, 50000, (int16_t)tmeas, &c));
        }
    }
}

static void test_sht4x_decode_rejects_only_what_a_working_part_cannot_produce(void)
{
    /* Calls the SHIPPED decision (o2p_sht4x_decode), not its constants: the
     * sixth review pointed out that a test asserting only the macros passes
     * even with the driver's check reverted. */
    int16_t t = 0; uint16_t rh = 0;

    /* A normal reading decodes. raw 0x6666 ~ 25 C; 0x8000 ~ 56 %RH. */
    TEST_ASSERT_EQUAL(O2P_SHT_OK, o2p_sht4x_decode(0x6666, 0x8000, &t, &rh));
    TEST_ASSERT_INT16_WITHIN(200, 2500, t);

    /* A SATURATED pile is the normal case here, and Sensirion documents a
     * temporary +3 %RH offset after long exposure above 80 %RH. An
     * above-100 % reading must therefore be CLAMPED, never rejected - a
     * -3..103 % window would have refused exactly the condition the humidity
     * channel exists to observe. */
    TEST_ASSERT_EQUAL(O2P_SHT_OK, o2p_sht4x_decode(0x6666, 0xE353, &t, &rh));
    TEST_ASSERT_EQUAL_UINT16(10000, rh);       /* clamped, not refused */

    /* The extreme raw words are outside the part's rating and are refused. */
    TEST_ASSERT_EQUAL(O2P_SHT_RANGE, o2p_sht4x_decode(0x0000, 0x8000, &t, &rh));
    TEST_ASSERT_EQUAL(O2P_SHT_RANGE, o2p_sht4x_decode(0xFFFF, 0x8000, &t, &rh));
}

static void test_sht4x_decode_leaves_outputs_untouched_when_it_refuses(void)
{
    int16_t t = -12345; uint16_t rh = 54321;
    TEST_ASSERT_EQUAL(O2P_SHT_RANGE, o2p_sht4x_decode(0x0000, 0x8000, &t, &rh));
    TEST_ASSERT_EQUAL_INT16(-12345, t);
    TEST_ASSERT_EQUAL_UINT16(54321, rh);
}

static void test_vdda_computation_rejects_an_impossible_rail(void)
{
    /* Calls the shipped computation, not the macros around it. */
    uint16_t mv = 0u;
    TEST_ASSERT_TRUE(o2p_vdda_from_vrefint(1650u, 1500u, &mv));
    TEST_ASSERT_UINT16_WITHIN(50, 3300, mv);

    /* The corrupted sample from the fifth review: 4350 mV on a part that
     * cannot run there. */
    TEST_ASSERT_FALSE(o2p_vdda_from_vrefint(1650u, 1138u, &mv));
    /* A blank calibration word, and a zero divisor. */
    TEST_ASSERT_FALSE(o2p_vdda_from_vrefint(0xFFFFu, 1500u, &mv));
    TEST_ASSERT_FALSE(o2p_vdda_from_vrefint(1650u, 0u, &mv));
}

static void test_vdda_corrupted_but_plausible_is_a_known_gap(void)
{
    /* Documented, not fixed: a single uncorroborated VREFINT sample can be
     * corrupted into a value INSIDE the window. raw 1436 reads 3447 mV, which
     * lifts a real 3.000 V rail past the 3.130 V VA_LOW threshold. Closing it
     * needs the independent ADS1119 AIN2 measurement, which is wired and never
     * sampled. This test pins the gap so it cannot be forgotten or silently
     * "fixed" by a bound that does not actually close it. */
    uint16_t mv = 0u;
    TEST_ASSERT_TRUE(o2p_vdda_from_vrefint(1650u, 1436u, &mv));
    TEST_ASSERT_UINT16_WITHIN(5, 3447, mv);
}

static void test_zero_point_is_covered_by_the_config_crc(void)
{
    /* CONFIG_CRC is what a master uses to confirm the probe is running the
     * configuration it thinks it wrote. A calibration constant outside it
     * would let the zero change with the CRC unmoved. */
    uint16_t before = o2p_config_crc(&rm.cfg);

    uint8_t req[32], rsp[O2P_MB_MAX_ADU];
    const uint8_t w[] = {0x03, 0x10, 0x00, 0x42, 0x00, 0x02, 0x04,
                         0x00, 0x00, 0x04, 0xB0};      /* +1200 nA */
    size_t n = framed(req, w, sizeof(w));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_INT32(1200, rm.cfg.cal_zero_na);
    TEST_ASSERT_NOT_EQUAL(before, o2p_config_crc(&rm.cfg));

    /* And the register reports the live config, not a cached value. */
    const uint8_t rd[] = {0x03, 0x03, 0x00, 0x3F, 0x00, 0x01};
    n = framed(req, rd, sizeof(rd));
    o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_HEX16(o2p_config_crc(&rm.cfg),
                            (uint16_t)((rsp[3] << 8) | rsp[4]));
}

static void test_config_block_read_covers_the_zero_registers(void)
{
    /* The block grew to 20 registers. A read of the whole block must still be
     * one legal FC03 - the Dragino's AT+COMMAND frames are literal. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t body[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x14};
    size_t n = framed(req, body, sizeof(body));
    size_t len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(3u + 40u + 2u, len);
    TEST_ASSERT_EQUAL_HEX8(0x03, rsp[1]);

    /* One past the end is still refused. */
    const uint8_t over[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x15};
    n = framed(req, over, sizeof(over));
    len = o2p_mb_dispatch(req, n, 3, &handlers, rsp);
    TEST_ASSERT_EQUAL_UINT(5, len);
    TEST_ASSERT_EQUAL_HEX8(O2P_MB_EX_ILLEGAL_ADDRESS, rsp[2]);
}

static void test_monotonic_across_the_whole_range_with_a_zero(void)
{
    /* The monotonicity sweep again, with the zero term live and a tempco on
     * top of it. As the current falls the reported oxygen must fall with it
     * and never flip back into a plausible mid-range value - including well
     * below the zero, where the fraction is negative and RANGE. */
    o2p_cal_t cal = {0};
    cal.cal_zero_na = 1200;
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 71200, 2500));
    cal.tempco_per_k = 0.0025f;

    float prev = 1e9f;
    for (int32_t na = 120000; na >= -20000; na -= 500) {
        float c = 0;
        o2p_status_t st = o2p_fraction_from_current(&cal, na, 5500, &c);
        TEST_ASSERT_NOT_EQUAL(O2P_UNEVALUABLE, st);
        TEST_ASSERT_TRUE(c <= prev + 1e-6f);
        prev = c;
    }
    TEST_ASSERT_TRUE(prev < 0.0f);
}

static void test_implausible_air_point_is_rejected(void)
{
    /* A calibration taken in nitrogen, or with the cell unplugged, must not
     * overwrite a good one. */
    o2p_cal_t cal = {0};
    TEST_ASSERT_TRUE(o2p_calibrate_air(&cal, 70000, 2500));
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 200, 2500));
    TEST_ASSERT_FALSE(o2p_calibrate_air(&cal, 900000, 2500));
    TEST_ASSERT_EQUAL_INT32(70000, cal.cal_air_na);
}

/* ------------------------------------------------------- validity matrix */

static void test_missing_zero_point_flags_without_invalidating(void)
{
    /* The two calibration faults are deliberately different shapes. A missing
     * AIR point is an unknown scale factor (+/-43 %) and invalidates the
     * compensated channel; a missing ZERO point is a bounded offset
     * (DS-0637: < 0.4 %vol O2) and invalidates nothing. Getting this backwards
     * in either direction is a real failure: invalidating would blank every
     * probe built so far, and folding it into CAL_DEFAULT would discard good
     * data for a 0.4 %O2 effect. */
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_CAL_ZERO_DEFAULT));
    TEST_ASSERT_TRUE(o2p_o2_comp_valid(O2P_F_CAL_ZERO_DEFAULT));
    /* It is its own bit, not an alias of CAL_DEFAULT. */
    TEST_ASSERT_NOT_EQUAL(O2P_F_CAL_DEFAULT, O2P_F_CAL_ZERO_DEFAULT);
    /* Both together: the air point still rules the compensated channel. */
    TEST_ASSERT_FALSE(o2p_o2_comp_valid(O2P_F_CAL_DEFAULT | O2P_F_CAL_ZERO_DEFAULT));
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_CAL_DEFAULT | O2P_F_CAL_ZERO_DEFAULT));
    /* And it does not rescue a channel something else killed. */
    TEST_ASSERT_FALSE(o2p_o2_valid(O2P_F_CAL_ZERO_DEFAULT | O2P_F_ADC_RANGE));
}

static void test_zero_fault_bit_does_not_collide_with_its_neighbours(void)
{
    /* The fault word is FULL - all sixteen bits are assigned - so this bit was
     * taken from the retired EXP_PRESENT. A collision would silently merge two
     * conditions in the uplink, where the decoder's table is positional. */
    uint16_t assigned = (uint16_t)(
        O2P_F_SETTLING | O2P_F_I2C_FAIL_LMP | O2P_F_I2C_FAIL_ADS |
        O2P_F_I2C_FAIL_TMP | O2P_F_I2C_FAIL_SHT | O2P_F_AFE_CONFIG_MISMATCH |
        O2P_F_VA_LOW | O2P_F_VIN_LOW | O2P_F_HEATER_RUNAWAY | O2P_F_TEMP_OVER |
        O2P_F_DEW_SUSPECT | O2P_F_ADC_RANGE | O2P_F_CAL_DEFAULT |
        O2P_F_CAL_ZERO_DEFAULT | O2P_F_EXP_FAIL | O2P_F_HEATER_DISABLED);
    TEST_ASSERT_EQUAL_HEX16(0xFFFFu, assigned);   /* all sixteen, no overlap */
    TEST_ASSERT_EQUAL_HEX16(0x2000u, O2P_F_CAL_ZERO_DEFAULT);
}


static void test_uncalibrated_invalidates_comp_but_not_raw(void)
{
    /* An uncalibrated cell still measures a real current, so the RAW channel
     * stands. The COMPENSATED channel is that current divided by a constant
     * nobody has measured - the datasheet nominal spans 0.07-0.13 mA - so a
     * 15.2 %vol reading against a true 21 %vol would be indistinguishable
     * from a genuinely alarming result. */
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
    s->lmp_readback = 1234; s->pressure_hpa = 1234;
    s->sample_seq = 77;   /* cumulative: must SURVIVE */

    o2p_snapshot_reset(s);

    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->o2_comp);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->o2_raw);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_tip);
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_chamber);
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
    /* The block grew from 16 to 18 registers when the PI gains landed, and to
     * 20 with CAL_ZERO_NA. A read that stops at the gains must still succeed,
     * and the gains must still be the last two words it returns - appending
     * the zero registers must not have shifted them.
     *
     * The block boundary itself moved with the block, so it is asserted at its
     * new edge in test_config_block_read_covers_the_zero_registers rather than
     * here; leaving it at 19 would have made this test pass on a map where the
     * rule had stopped being enforced at all. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t all[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x12};
    size_t n = framed(req, all, sizeof(all));
    TEST_ASSERT_EQUAL_UINT(3 + 36 + 2, o2p_mb_dispatch(req, n, 3, &handlers, rsp));
    TEST_ASSERT_EQUAL_UINT16(rm.cfg.heater_kp_x100,
                             (uint16_t)((rsp[3 + 32] << 8) | rsp[3 + 33]));
    TEST_ASSERT_EQUAL_UINT16(rm.cfg.heater_ki_x100,
                             (uint16_t)((rsp[3 + 34] << 8) | rsp[3 + 35]));
}

static void test_validity_matrix(void)
{
    static const uint16_t invalidating[] = {
        O2P_F_SETTLING, O2P_F_I2C_FAIL_LMP, O2P_F_I2C_FAIL_ADS,
        O2P_F_AFE_CONFIG_MISMATCH, O2P_F_VA_LOW, O2P_F_ADC_RANGE,
    };
    for (unsigned i = 0; i < sizeof(invalidating) / sizeof(invalidating[0]); i++) {
        TEST_ASSERT_FALSE(o2p_o2_valid(invalidating[i]));
    }
    /* The two documented exceptions. Both mark the reading as lower quality;
     * neither discards it. */
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_TEMP_OVER));
    TEST_ASSERT_TRUE(o2p_o2_valid(O2P_F_CAL_DEFAULT));
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
    TEST_ASSERT_EQUAL_UINT16(O2P_U16_INVALID, s->rh_chamber);
    TEST_ASSERT_TRUE((s->faults & O2P_F_SETTLING) != 0);
    TEST_ASSERT_FALSE(o2p_o2_valid(s->faults));
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
    o2p_heater_cfg_t c;
    c.setpoint_x100 = 8500u;     /* 85 %RH, PLAN.md:294-296 */
    c.dt_max_k100 = 400u;        /* 4 K, the designed envelope */
    c.max_duty_x100 = 10000u;
    c.kp_x100 = O2P_HEATER_KP_X100_DEFAULT;
    c.ki_x100 = O2P_HEATER_KI_X100_DEFAULT;
    return c;
}

/* An input in which every interlock is satisfied, so a test can break exactly
 * one thing and attribute the result to it. */
static o2p_heater_in_t hin_healthy(void)
{
    o2p_heater_in_t in;
    in.drive_possible = true;
    in.safety_armed = true;
    in.pin_integrity_ok = true;
    in.rh_valid = true;
    in.rh_x100 = 9500u;          /* wet: the loop should want heat */
    in.tip_valid = true;
    in.t_tip_c100 = 5500;
    in.chamber_valid = true;
    in.t_chamber_c100 = 5400;    /* dT = 1 K, inside the envelope */
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

static void test_runaway_latches_at_an_irregular_but_credible_cadence(void)
{
    /* The ninth review's counterexample: valid high observations at 0, 6, 12 …
     * accumulated NOTHING against the original 5 s bound, masking a genuine
     * runaway forever. The bound encodes the caller's cadence and must be
     * generous enough for jitter and transient sensor loss. */
    /* ABSOLUTE periods, deliberately not derived from
     * O2P_HEATER_RUNAWAY_MAX_GAP_S: a loop bounded by the constant adapts to
     * whatever the constant becomes and cannot catch it being tightened back
     * under the sampler's real jitter. 6 s is the ninth review's exact
     * counterexample. */
    const unsigned periods[] = {1u, 2u, 5u, 6u, 8u};
    for (unsigned pi = 0; pi < (sizeof(periods) / sizeof(periods[0])); pi++) {
        unsigned period = periods[pi];
        o2p_heater_state_t st;
        o2p_heater_ctl_reset(&st);
        o2p_heater_cfg_t cfg = hcfg_default();
        cfg.max_duty_x100 = 0u;
        o2p_heater_in_t hot = hin_healthy();
        hot.t_tip_c100 = 5000;
        hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                       O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
        o2p_heater_out_t out;
        for (uint32_t t = 0; t <= (O2P_HEATER_RUNAWAY_WINDOW_S * 2u); t += period) {
            o2p_heater_ctl_step(&st, &cfg, &hot, t, &out);
        }
        TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
            "a caller inside the cadence contract must still latch a runaway");
    }
}

static void test_runaway_ignores_evidence_beyond_the_cadence_contract(void)
{
    /* And the other edge: observations further apart than the contract allows
     * are isolated glimpses, not evidence about the interval between them. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_out_t out;
    for (uint32_t t = 0; t <= (O2P_HEATER_RUNAWAY_WINDOW_S * 40u);
         t += (O2P_HEATER_RUNAWAY_MAX_GAP_S + 1u)) {
        o2p_heater_ctl_step(&st, &cfg, &hot, t, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);
}

static void test_runaway_repeated_isolated_highs_never_accumulate(void)
{
    /* The class the previous test missed: capping each contribution at 5 s
     * still CREDITED 5 s for a 100 s blind gap, so thirteen instantaneous
     * observations 100 s apart reached 60 s of "evidence" and latched without
     * the condition ever being watched. A gap longer than the cap must discard
     * the evidence, not clip its contribution. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_in_t blind = hot;
    blind.tip_valid = false;
    o2p_heater_out_t out;

    for (unsigned burst = 0; burst < 20u; burst++) {
        uint32_t t0 = burst * 100u;
        o2p_heater_ctl_step(&st, &cfg, &hot, t0, &out);
        for (unsigned i = 1; i < 100u; i++) {
            o2p_heater_ctl_step(&st, &cfg, &blind, t0 + i, &out);
        }
    }
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "isolated observations across blind gaps must not accumulate");
}

static void test_runaway_alternating_valid_invalid_still_latches(void)
{
    /* The other side of the same rule: a two-second interval with a valid high
     * observation at BOTH ends is genuine evidence about that interval, so an
     * every-other-second sensor must not be able to mask a runaway heater. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_in_t blind = hot;
    blind.chamber_valid = false;
    o2p_heater_out_t out;

    for (unsigned i = 0; i <= (O2P_HEATER_RUNAWAY_WINDOW_S * 2u) + 4u; i++) {
        o2p_heater_ctl_step(&st, &cfg, (i % 2u) ? &blind : &hot, i, &out);
    }
    TEST_ASSERT_TRUE(st.runaway_latched);
}

static void test_runaway_does_not_latch_on_two_isolated_samples(void)
{
    /* The defect round 6's fix still had: holding the start timestamp across
     * invalid samples let the ELAPSED test count the unobserved gap, so two
     * isolated high samples 60 s apart latched with no evidence between them.
     * Evidence must be accumulated, not inferred from wall time. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_in_t blind = hot;
    blind.tip_valid = false;
    o2p_heater_out_t out;

    o2p_heater_ctl_step(&st, &cfg, &hot, 0u, &out);          /* one high sample */
    for (unsigned i = 1; i < O2P_HEATER_RUNAWAY_WINDOW_S; i++) {
        o2p_heater_ctl_step(&st, &cfg, &blind, i, &out);     /* nothing observed */
    }
    o2p_heater_ctl_step(&st, &cfg, &hot, O2P_HEATER_RUNAWAY_WINDOW_S, &out);
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "an unobserved gap must not count as sustained high-dT evidence");
}

static void test_runaway_evidence_survives_a_wrap_of_the_clock(void)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_out_t out;
    uint32_t t = 0xFFFFFFF0u;
    for (unsigned i = 0; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 4u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &hot, t, &out);
        t++;                       /* wraps through zero mid-window */
    }
    TEST_ASSERT_TRUE(st.runaway_latched);
}

static void test_runaway_survives_intermittent_sensor_dropouts(void)
{
    /* The false NEGATIVE the fifth round's fix opened: restarting the window
     * on any invalid sample let ONE bad reading per 59 s keep a genuinely
     * runaway 1 W heater from ever latching. An outage may delay the latch; it
     * must not prevent it. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t hot = hin_healthy();
    hot.t_tip_c100 = 5000;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_out_t out;

    for (unsigned i = 0; i <= (O2P_HEATER_RUNAWAY_WINDOW_S * 3u); i++) {
        o2p_heater_in_t in = hot;
        if ((i % 30u) == 0u) {          /* a dropout every 30 s */
            in.tip_valid = false;
        }
        o2p_heater_ctl_step(&st, &cfg, &in, i, &out);
    }
    TEST_ASSERT_TRUE_MESSAGE(st.runaway_latched,
        "an intermittent sensor must not be able to mask a runaway heater");
}

static void test_runaway_needs_sustained_high_dt_not_one_sample(void)
{
    /* The false POSITIVE in the other direction: the window used to time zero
     * duty and test dT only once at the end, so a normal minute followed by a
     * single high sample latched. */
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_cfg_t cfg = hcfg_default();
    cfg.max_duty_x100 = 0u;
    o2p_heater_in_t cool = hin_healthy();
    cool.t_tip_c100 = 3000;
    cool.t_chamber_c100 = 3000;          /* dT nil: nothing wrong */
    o2p_heater_out_t out;

    for (unsigned i = 0; i <= O2P_HEATER_RUNAWAY_WINDOW_S + 2u; i++) {
        o2p_heater_ctl_step(&st, &cfg, &cool, i, &out);
    }
    TEST_ASSERT_FALSE(st.runaway_latched);

    /* One high sample after a quiet window must not be enough. */
    o2p_heater_in_t hot = cool;
    hot.t_chamber_c100 = (int16_t)(hot.t_tip_c100 - (int16_t)cfg.dt_max_k100 -
                                   O2P_HEATER_RUNAWAY_MARGIN_K100 - 50);
    o2p_heater_ctl_step(&st, &cfg, &hot, O2P_HEATER_RUNAWAY_WINDOW_S + 3u, &out);
    TEST_ASSERT_FALSE_MESSAGE(st.runaway_latched,
        "a single high-dT sample must not latch runaway");
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
    RUN_TEST(test_zero_point_round_trips_at_a_low_oxygen_point);
    RUN_TEST(test_negative_zero_is_legal_because_the_sign_gate_is_open);
    RUN_TEST(test_zero_bound_rejects_the_far_tail_not_just_near_misses);
    RUN_TEST(test_calibrate_air_refuses_an_implausible_stored_zero);
    RUN_TEST(test_zero_at_or_above_the_air_point_is_unevaluable);
    RUN_TEST(test_tempco_scales_k_and_not_the_measured_current);
    RUN_TEST(test_written_zero_point_must_also_be_plausible);
    RUN_TEST(test_absurd_tempco_is_refused);
    RUN_TEST(test_calibration_temperature_is_bounded);
    RUN_TEST(test_out_of_range_tempco_write_is_refused_over_modbus);
    RUN_TEST(test_calibrate_and_commit_in_one_frame_defers_the_commit);
    RUN_TEST(test_commit_on_its_own_is_not_deferred);
    RUN_TEST(test_fresh_air_point_above_the_population_is_refused);
    RUN_TEST(test_calibration_cannot_store_an_invalid_temperature);
    RUN_TEST(test_every_storable_calibration_temperature_keeps_config_valid);
    RUN_TEST(test_commit_after_a_separate_cal_trigger_still_waits);
    RUN_TEST(test_tempco_bound_rejects_gross_corruption_only);
    RUN_TEST(test_the_known_collapsed_gain_corner_stays_refused);
    RUN_TEST(test_extrapolation_above_60c_still_converts);
    RUN_TEST(test_extreme_corner_yields_no_value_rather_than_a_wrong_one);
    RUN_TEST(test_gain_backstop_still_catches_an_out_of_contract_coefficient);
    RUN_TEST(test_tmp117_rejects_readings_outside_the_part_range);
    RUN_TEST(test_fresh_air_ceiling_clears_the_stacked_legal_corner);
    RUN_TEST(test_legal_configs_either_convert_or_yield_no_value);
    RUN_TEST(test_a_realistic_coefficient_converts_across_the_whole_range);
    RUN_TEST(test_sht4x_decode_rejects_only_what_a_working_part_cannot_produce);
    RUN_TEST(test_sht4x_decode_leaves_outputs_untouched_when_it_refuses);
    RUN_TEST(test_vdda_computation_rejects_an_impossible_rail);
    RUN_TEST(test_vdda_corrupted_but_plausible_is_a_known_gap);
    RUN_TEST(test_zero_point_is_covered_by_the_config_crc);
    RUN_TEST(test_config_block_read_covers_the_zero_registers);
    RUN_TEST(test_monotonic_across_the_whole_range_with_a_zero);
    RUN_TEST(test_implausible_air_point_is_rejected);
    RUN_TEST(test_written_calibration_must_also_be_plausible);
    RUN_TEST(test_uncalibrated_invalidates_comp_but_not_raw);
    RUN_TEST(test_missing_zero_point_flags_without_invalidating);
    RUN_TEST(test_zero_fault_bit_does_not_collide_with_its_neighbours);
    RUN_TEST(test_discovery_alias_refuses_writes);
    RUN_TEST(test_snapshot_reset_clears_every_measurement_channel);
    RUN_TEST(test_heater_gains_are_writable_and_bounded);
    RUN_TEST(test_gain_registers_read_back_what_was_written);
    RUN_TEST(test_config_block_read_covers_the_gains);
    RUN_TEST(test_validity_matrix);
    RUN_TEST(test_snapshot_is_invalid_before_the_first_sample);
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
    RUN_TEST(test_runaway_latches_at_an_irregular_but_credible_cadence);
    RUN_TEST(test_runaway_ignores_evidence_beyond_the_cadence_contract);
    RUN_TEST(test_runaway_repeated_isolated_highs_never_accumulate);
    RUN_TEST(test_runaway_alternating_valid_invalid_still_latches);
    RUN_TEST(test_runaway_does_not_latch_on_two_isolated_samples);
    RUN_TEST(test_runaway_evidence_survives_a_wrap_of_the_clock);
    RUN_TEST(test_runaway_survives_intermittent_sensor_dropouts);
    RUN_TEST(test_runaway_needs_sustained_high_dt_not_one_sample);
    RUN_TEST(test_runaway_latches_on_uncommanded_heat_and_stays_latched);
    RUN_TEST(test_runaway_needs_the_full_window);
    RUN_TEST(test_runaway_is_not_evaluated_when_we_cannot_drive);
    RUN_TEST(test_setpoint_default_respects_the_cell_humidity_rating);
    return UNITY_END();
}
