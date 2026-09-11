/* Host tests for the heater's blind fallback (O2P_HEATER_BLIND_DUTY_X100).
 *
 * Its own suite, so it runs against heater_ctl.c without test_logic. Shaped by
 * the guard-review checklist: the unevaluable witness (the die) refuses, a
 * worse die reading never flips the verdict back, a measured overtemperature
 * is never overridden, and the known trigger - every I2C sensor gone - is
 * constructed and observed to heat.
 *
 *   pio test -e native -f test_heater_blind
 */
#include <unity.h>

#include "heater_ctl.h"

static o2p_heater_cfg_t tip_mode(void)
{
    /* The 2026-09-10 bench configuration: persistent tip setpoint 80.00 C
     * with its consent, duty capped at 70 %. */
    o2p_heater_cfg_t c = {0};
    c.setpoint_x100 = 8500u;
    c.dt_max_k100 = 400u;
    c.max_duty_x100 = 7000u;
    c.kp_x100 = O2P_HEATER_KP_X100_DEFAULT;
    c.ki_x100 = O2P_HEATER_KI_X100_DEFAULT;
    c.test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
    c.test_ki_x100 = O2P_HEATER_TEST_KI_X100_DEFAULT;
    c.tip_consent = true;
    c.tip_sp_valid = true;
    c.tip_sp_c100 = 8000;
    return c;
}

static o2p_heater_in_t healthy(void)
{
    o2p_heater_in_t in = {0};
    in.drive_possible = true;
    in.safety_armed = true;
    in.pin_integrity_ok = true;
    in.rh_valid = true;
    in.rh_x100 = 4000u;
    in.tip_valid = true;
    in.t_tip_c100 = 2600;
    in.chamber_valid = true;
    in.t_chamber_c100 = 2590;
    in.chamber_fresh = true;
    in.die_valid = true;
    in.t_die_c100 = 2700;
    in.supply_ok = true;
    return in;
}

/* Every I2C sensor gone, as at 15:1x UTC: HEATER_BLOCK 0x001C. The die is the
 * MCU's own ADC and still reads. */
static o2p_heater_in_t i2c_dead(void)
{
    o2p_heater_in_t in = healthy();
    in.safety_armed = false;
    in.rh_valid = false;
    in.tip_valid = false;
    in.chamber_valid = false;
    in.chamber_fresh = false;
    return in;
}

static o2p_heater_out_t step(const o2p_heater_cfg_t *c, const o2p_heater_in_t *in)
{
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    o2p_heater_out_t out = {0u, 0u};
    o2p_heater_ctl_step(&st, c, in, 100u, &out);
    return out;
}

void setUp(void) {}
void tearDown(void) {}

static void test_a_dead_i2c_bus_heats_at_the_blind_duty(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = i2c_dead();
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_TIP) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
}

static void test_a_healthy_probe_never_takes_the_blind_path(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block);
    TEST_ASSERT_EQUAL_UINT16(7000u, out.duty_x100);   /* the tip loop, saturated */
}

static void test_each_wet_board_reason_alone_triggers_it(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();
    in.tip_valid = false;
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, step(&c, &in).duty_x100);
    in = healthy();
    in.safety_armed = false;
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, step(&c, &in).duty_x100);
    in = healthy();
    in.chamber_valid = false;
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, step(&c, &in).duty_x100);
    /* CHANGED 2026-09-11 (Fab's order): a supply fault alone no longer takes
     * the blind path - it no longer vetoes the loops either, so the LOOP
     * runs: duty driven, O2P_HB_SUPPLY as an annotation, no O2P_HB_BLIND.
     * Pinned here so nobody mistakes the new behaviour for a regression. */
    in = healthy();
    in.supply_ok = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_SUPPLY) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
}

static void test_a_latched_runaway_heats_blind(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();
    o2p_heater_state_t st;
    o2p_heater_ctl_reset(&st);
    st.runaway_latched = true;
    o2p_heater_out_t out = {0u, 0u};
    o2p_heater_ctl_step(&st, &c, &in, 100u, &out);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, out.duty_x100);
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_RUNAWAY | O2P_HB_BLIND, out.block);
}

static void test_the_off_switches_still_refuse(void)
{
    o2p_heater_in_t in = i2c_dead();
    o2p_heater_cfg_t c = tip_mode();
    c.max_duty_x100 = 0u;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) == 0u);

    c = tip_mode();
    in.drive_possible = false;
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
}

static void test_no_consent_still_refuses(void)
{
    o2p_heater_in_t in = i2c_dead();
    o2p_heater_cfg_t c = tip_mode();
    c.tip_consent = false;
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
    c = tip_mode();
    c.tip_sp_valid = false;
    c.rh_consent = false;
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
}

static void test_pin_integrity_still_refuses(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = i2c_dead();
    in.pin_integrity_ok = false;
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
}

static void test_a_measured_overtemperature_is_never_overridden(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();
    in.chamber_valid = false;               /* a wet-board reason is present */
    in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100;
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
    in.t_tip_c100 = 15000;                  /* the far tail */
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
}

static void test_the_die_is_the_last_witness(void)
{
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = i2c_dead();
    in.die_valid = false;
    TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);

    in = i2c_dead();
    in.t_die_c100 = O2P_HEATER_BLIND_DIE_MAX_C100 - 1;
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, step(&c, &in).duty_x100);
    for (int t = O2P_HEATER_BLIND_DIE_MAX_C100; t < 12500; t += 500) {
        in.t_die_c100 = (int16_t)t;
        TEST_ASSERT_EQUAL_UINT16(0u, step(&c, &in).duty_x100);
    }
}

static void test_the_humidity_de_creep_mask_does_not_trigger_it(void)
{
    o2p_heater_cfg_t c = tip_mode();
    c.tip_sp_valid = false;
    c.tip_consent = false;
    c.rh_consent = true;
    o2p_heater_in_t in = healthy();
    in.rh_valid = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_EQUAL_UINT16(O2P_HB_NO_RH, out.block);
}

static void test_the_caps_still_apply(void)
{
    o2p_heater_in_t in = i2c_dead();
    o2p_heater_cfg_t c = tip_mode();
    c.max_duty_x100 = 500u;
    TEST_ASSERT_EQUAL_UINT16(500u, step(&c, &in).duty_x100);

    c = tip_mode();
    c.test_override = true;
    c.test_duty_x100 = 300u;
    TEST_ASSERT_EQUAL_UINT16(300u, step(&c, &in).duty_x100);

    c.test_duty_x100 = 0u;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) == 0u);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_a_dead_i2c_bus_heats_at_the_blind_duty);
    RUN_TEST(test_a_healthy_probe_never_takes_the_blind_path);
    RUN_TEST(test_each_wet_board_reason_alone_triggers_it);
    RUN_TEST(test_a_latched_runaway_heats_blind);
    RUN_TEST(test_the_off_switches_still_refuse);
    RUN_TEST(test_no_consent_still_refuses);
    RUN_TEST(test_pin_integrity_still_refuses);
    RUN_TEST(test_a_measured_overtemperature_is_never_overridden);
    RUN_TEST(test_the_die_is_the_last_witness);
    RUN_TEST(test_the_humidity_de_creep_mask_does_not_trigger_it);
    RUN_TEST(test_the_caps_still_apply);
    return UNITY_END();
}
