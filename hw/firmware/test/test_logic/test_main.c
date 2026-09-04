/* Host tests for the portable half of the o2-probe firmware.
 *
 * Everything here is logic that can be wrong without hardware, which is
 * exactly the logic that is expensive to debug once a probe is potted and its
 * SWD connector is inside the enclosure. Run with:  pio test -e native
 */
#include <unity.h>

#include <math.h>
#include <string.h>

#include "ads1119.h"
#include "die_temp.h"
#include "faults.h"
#include "heater_ctl.h"
#include "modbus_pdu.h"
#include "o2.h"
#include "psychro.h"
#include "regmap.h"

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
    TEST_ASSERT_EQUAL_UINT(sizeof(int32_t) + 9 * sizeof(uint16_t) + 6,
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
    /* The block grew from 16 to 18 registers. A read of all 18 must succeed;
     * 19 must not, or the boundary rule has quietly stopped being enforced. */
    uint8_t req[16], rsp[O2P_MB_MAX_ADU];
    const uint8_t all[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x12};
    size_t n = framed(req, all, sizeof(all));
    TEST_ASSERT_EQUAL_UINT(3 + 36 + 2, o2p_mb_dispatch(req, n, 3, &handlers, rsp));

    const uint8_t over[] = {0x03, 0x03, 0x00, 0x30, 0x00, 0x13};
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
        O2P_F_SETTLING, O2P_F_I2C_FAIL_LMP, O2P_F_I2C_FAIL_ADS,
        O2P_F_AFE_CONFIG_MISMATCH, O2P_F_VA_LOW, O2P_F_ADC_RANGE,
        O2P_F_ADS_DRDY_STUCK, O2P_F_ADS_CONFIG_LOST,
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
    TEST_ASSERT_EQUAL_HEX16((uint16_t)O2P_I16_INVALID, (uint16_t)s->t_die);
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
    RUN_TEST(test_clip_detection);
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
    return UNITY_END();
}
