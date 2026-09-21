/* Host tests for the heater's blind fallback (O2P_HEATER_BLIND_DUTY_X100).
 *
 * Its own suite, so it runs against heater_ctl.c without test_logic. Shaped by
 * the guard-review checklist: the unevaluable witness (the die) refuses, a
 * worse die reading never flips the verdict back, a measured overtemperature
 * is never overridden, and the known trigger - every I2C sensor gone - is
 * constructed and observed to heat.
 *
 * RE-PINNED 2026-09-11 for Fab's three rulings: (1) "fix that control loop
 * bullshit" - SAFETY alone must not discard a working setpoint; (2) "nope,
 * no stand-down. 50 is safe if MCU die is < 40 C" - the de-creep fixture
 * now uses the REAL production state (RH and chamber invalid together,
 * main.c's mask) and the die gate is the stand-down, pinned both ways;
 * (3) the per-law blind rule and "unattended loop: annotate and regulate
 * (keep <=80 C)" - a wet reason blinds only the law whose control sensor
 * it is, and the tip clamp tightens to 80.00 C while SAFETY is annotated.
 * Every fixture states its die temperature deliberately (2700 = 27.00 C
 * unless a case is about the gate itself).
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
    o2p_heater_out_t out = {0u, 0u, O2P_HEATER_LAW_REFUSED, false};
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

/* A wet reason blinds ONLY the law whose control sensor it is (Fab's
 * rulings 2026-09-11, the per-law blind rule). With a TIP law in command:
 * NO_TIP blinds (the control sensor), while SAFETY and NO_CHAMBER merely
 * annotate and the loop regulates. With the RH law in command: NO_RH and
 * SAFETY blind (the control sensor and SAFETY's untouched membership),
 * while NO_TIP and NO_CHAMBER annotate. Every fixture states its die
 * temperature deliberately - the die gate is the stand-down and nothing
 * about it may be accidental (O2P_HEATER_BLIND_DIE_MAX_C100). */
static void test_a_wet_reason_blinds_only_its_own_law(void)
{
    /* TIP law (stored setpoint 80.00 C, consented, ceiling 70 %). */
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();      /* die 27.00 C, stated not accidental */
    in.tip_valid = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);

    in = healthy();
    in.safety_armed = false;
    out = step(&c, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "SAFETY alone must not blind a tip law - it annotates (2026-09-11)");
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);

    in = healthy();
    in.chamber_valid = false;
    in.chamber_fresh = false;
    out = step(&c, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "NO_CHAMBER alone must not blind a tip law - the chamber is no law's control quantity");
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);

    /* RH law (stored tip setpoint at the sentinel, RH consented, a setpoint
     * that DEMANDS heat: heating dries, so a 30.00 % target against a
     * 40.00 % reading asks for duty). */
    o2p_heater_cfg_t rh = tip_mode();
    rh.tip_sp_valid = false;
    rh.tip_consent = false;
    rh.rh_consent = true;
    rh.setpoint_x100 = 3000u;
    in = healthy();
    in.rh_valid = false;
    out = step(&rh, &in);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_RH) != 0u);

    in = healthy();
    in.safety_armed = false;
    out = step(&rh, &in);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(
        O2P_HEATER_BLIND_DUTY_X100, out.duty_x100,
        "SAFETY keeps its founding blind membership for the RH law (not touched by the 2026-09-11 rulings)");
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);

    in = healthy();
    in.tip_valid = false;
    out = step(&rh, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "NO_TIP alone must not blind the RH law - the tip only feeds TIP_LIMIT there");
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_TIP) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);

    in = healthy();
    in.chamber_valid = false;
    in.chamber_fresh = false;
    out = step(&rh, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "NO_CHAMBER alone must not blind the RH law either");
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);

    /* CHANGED 2026-09-11 (Fab's order): a supply fault alone no longer takes
     * the blind path - it no longer vetoes the loops either, so the LOOP
     * runs: duty driven, O2P_HB_SUPPLY as an annotation, no O2P_HB_BLIND.
     * Pinned here so nobody mistakes the new behaviour for a regression. */
    in = healthy();
    in.supply_ok = false;
    out = step(&c, &in);
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
    o2p_heater_out_t out = {0u, 0u, O2P_HEATER_LAW_REFUSED, false};
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

/* The de-creep window, pinned on the REAL production state. The old fixture
 * (rh invalid, chamber still VALID) never occurs - the SHT45's mask takes
 * the chamber with the RH, and test_main.c:4451's own comment called the
 * fixture dishonest. Corrected 2026-09-11 with Fab's ruling: "nope, no
 * stand-down. 50 is safe if MCU die is < 40 C" - the RH law's control
 * sensor is down, NO_RH blinds it, the ring rides at the blind duty until
 * the window ends OR the die gate closes, whichever comes first. */
static void test_the_de_creep_mask_blinds_the_rh_law_until_the_die_gate_closes(void)
{
    o2p_heater_cfg_t c = tip_mode();
    c.tip_sp_valid = false;
    c.tip_consent = false;
    c.rh_consent = true;
    /* The mask as main.c applies it: RH AND chamber invalid together. */
    o2p_heater_in_t in = healthy();      /* die 27.00 C: under the 40 C gate */
    in.rh_valid = false;
    in.chamber_valid = false;
    in.chamber_fresh = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_RH) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);

    /* The stand-down: same state, die at/above the gate - duty zero, the
     * die IS the discriminator (Fab's order 2026-09-11). */
    in.t_die_c100 = O2P_HEATER_BLIND_DIE_MAX_C100;
    out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
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

/* ----------------- SAFETY vs the attended setpoint (2026-09-11 fix) ------
 *
 * The 2026-09-11 bench incident (Fab: "fix that control loop bullshit"):
 * the operator armed 50.00 C attended, the tip sensor was VALID, and only
 * the TMP117 therm thresholds were lost - so SAFETY was the sole refusal
 * and step() fell to the blind fallback: 50 % open loop, unbounded, the
 * setpoint silently ignored. The fix (heater_ctl.c, o2p_heater_ctl_step()):
 * SAFETY alone becomes an annotation on the attended tip loop. These pin
 * both halves of the asymmetry and the bounds that make it safe. */

static o2p_heater_cfg_t override_tip_mode(void)
{
    /* The incident's configuration: attended override, tip setpoint
     * 50.00 C, ceiling raised to 100 % by the app, default test gains. */
    o2p_heater_cfg_t c = tip_mode();
    c.test_override = true;
    c.test_tip_sp_valid = true;
    c.test_tip_sp_c100 = 5000;
    c.max_duty_x100 = 10000u;
    return c;
}

static void test_safety_alone_does_not_discard_the_attended_setpoint(void)
{
    o2p_heater_cfg_t c = override_tip_mode();
    o2p_heater_in_t in = healthy();
    in.safety_armed = false;               /* the sole refusal, as on the day */
    o2p_heater_out_t out = step(&c, &in);
    /* The tip loop runs: cold tip (26.00 C) vs 50.00 C saturates the PI
     * output at the ceiling - the loop is IN COMMAND, not the fallback. */
    TEST_ASSERT_EQUAL_UINT16(10000u, out.duty_x100);
    /* SAFETY stays VISIBLE - the register keeps telling the whole truth
     * while driving, the SUPPLY annotation's contract. */
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
    /* And it is NOT the blind path. */
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_TIP_LIMIT);
}

static void test_safety_annotates_the_committed_tip_loop_and_clamps_at_80(void)
{
    /* OVERTURNED 2026-09-11 (Fab's order: "unattended loop: annotate and
     * regulate (keep <=80 C)"): the committed/persistent tip loop with its
     * sensor valid and only the therm backstop down REGULATES with SAFETY
     * as an annotation - the same rule as the attended override, now
     * uniform across the tip-setpoint laws. The old pin here demanded a
     * blind 50 % and a silently discarded stored setpoint: the exact
     * failure the ruling ended. tip_mode() is the PERSISTENT setpoint,
     * no override - pinned explicitly so the uniformity is not read as an
     * accident. */
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();      /* die 27.00 C, tip 26.00 C */
    in.safety_armed = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "SAFETY alone must not discard the committed setpoint either");
    TEST_ASSERT_EQUAL_UINT16(7000u, out.duty_x100);  /* the tip loop, saturated */
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);

    /* The annotated clamp: 80.00 C while the backstop is down. 80.50 C is
     * BELOW the normal 82.00 limit - with the backstop up it regulates -
     * but with SAFETY annotated it must refuse (keep <=80 C). The chamber
     * tracks 1 K under the tip throughout, so DT_LIMIT stays quiet and
     * these pins are about the tip clamp alone. */
    in.t_tip_c100 = 8050;
    in.t_chamber_c100 = 7950;
    out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "80.50 C must refuse while SAFETY is annotated - the clamp is 80.00, not 82.00");
    TEST_ASSERT_TRUE((out.block & O2P_HB_TIP_LIMIT) != 0u);

    in.safety_armed = true;              /* the backstop credited again */
    in.t_tip_c100 = 8050;
    in.t_chamber_c100 = 7950;
    out = step(&c, &in);
    /* No TIP_LIMIT at 80.50 C with the backstop up - under the normal
     * 82.00 limit. Duty 0 is the LOOP's answer (the setpoint is 80.00, the
     * tip is above it: no demand), not a refusal - which is the distinction
     * this pin exists to make. */
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_TIP_LIMIT);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_SAFETY);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(0u, out.duty_x100,
        "80.50 C against an 80.00 setpoint is no heat demand - duty 0 from the loop, not a clamp");

    /* And just under the annotated clamp the loop still regulates. */
    in.safety_armed = false;
    in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_ANNOTATED_C100 - 50;
    in.t_chamber_c100 = O2P_HEATER_TIP_LIMIT_ANNOTATED_C100 - 150;
    out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_TIP_LIMIT);
    TEST_ASSERT_TRUE(out.duty_x100 > 0u);
}

static void test_a_tip_law_regulates_through_a_dead_chamber(void)
{
    /* Fab's ruling 2026-09-11 (per-law blind): the chamber is no law's
     * control quantity - it only feeds DT_LIMIT. A tip law with its sensor
     * valid REGULATES through NO_CHAMBER; the old "refuse rather than heat
     * open-loop on temperature" premise is overruled. DT_LIMIT's own
     * evidence-based latch stays fully live as the hard bound - it simply
     * cannot fire on a chamber it cannot read. Both tip laws pinned: the
     * committed one and the attended override. */
    o2p_heater_cfg_t c = tip_mode();
    o2p_heater_in_t in = healthy();      /* die 27.00 C */
    in.chamber_valid = false;
    in.chamber_fresh = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(7000u, out.duty_x100);  /* the tip loop, saturated */
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_CHAMBER) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_DT_LIMIT);

    o2p_heater_cfg_t ov = override_tip_mode();
    out = step(&ov, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "the attended tip law regulates through a dead chamber too");
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
    /* The override suppresses NO_CHAMBER (attended: the operator is the
     * bound on dT) - only the committed loop reports it. */
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_NO_CHAMBER);
}

static void test_the_rh_law_regulates_through_a_dead_tip(void)
{
    /* The mirror cell of the per-law rule: the tip only feeds TIP_LIMIT
     * for the RH law, so NO_TIP annotates while the RH loop regulates on
     * its own valid sensor. Setpoint 50.00 % against a 40.00 % reading, so
     * the loop has demand and "regulates" is observable as duty > 0.
     * tip_clamped's latch semantics are unchanged - an unevaluable tip
     * neither clamps nor exonerates. */
    o2p_heater_cfg_t c = tip_mode();
    c.tip_sp_valid = false;
    c.tip_consent = false;
    c.rh_consent = true;
    c.setpoint_x100 = 3000u;   /* heating dries: 30 % target vs 40 % reading is demand */
    o2p_heater_in_t in = healthy();      /* die 27.00 C, RH 40.00 % */
    in.tip_valid = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_TRUE_MESSAGE(out.duty_x100 > 0u,
        "NO_TIP alone must not stop the RH law - its control sensor is the RH");
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_TIP) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_TIP_LIMIT);
}

static void test_safety_still_blinds_the_open_loop_override(void)
{
    /* No setpoint is armed, so there is nothing to discard: the operator's
     * duty is the command and the blind rule's die bound applies. */
    o2p_heater_cfg_t c = override_tip_mode();
    c.test_tip_sp_valid = false;
    c.test_duty_x100 = 4000u;
    o2p_heater_in_t in = healthy();
    in.safety_armed = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(4000u, out.duty_x100);   /* blind, capped at the operator's duty */
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
}

static void test_a_measured_overtemperature_refuses_even_attended_with_safety_down(void)
{
    /* The bound that makes the fix safe: TIP_LIMIT is a MEASURED fact from
     * the same sensor the loop trusts, and it still forces zero even when
     * SAFETY is down alongside it - a measured overtemperature is never
     * overridden, wet-board rule included (heater_ctl.h). */
    o2p_heater_cfg_t c = override_tip_mode();
    o2p_heater_in_t in = healthy();
    in.safety_armed = false;
    in.t_tip_c100 = O2P_HEATER_TIP_LIMIT_C100;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(0u, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_TIP_LIMIT) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_SAFETY) != 0u);
    TEST_ASSERT_EQUAL_UINT16(0u, out.block & O2P_HB_BLIND);
}

static void test_no_tip_still_blinds_even_with_an_attended_setpoint(void)
{
    /* Without the control sensor there is no loop to run, setpoint or not:
     * the wet-board fallback is exactly for this board. */
    o2p_heater_cfg_t c = override_tip_mode();
    o2p_heater_in_t in = healthy();
    in.safety_armed = false;
    in.tip_valid = false;
    o2p_heater_out_t out = step(&c, &in);
    TEST_ASSERT_EQUAL_UINT16(O2P_HEATER_BLIND_DUTY_X100, out.duty_x100);
    TEST_ASSERT_TRUE((out.block & O2P_HB_BLIND) != 0u);
    TEST_ASSERT_TRUE((out.block & O2P_HB_NO_TIP) != 0u);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_a_dead_i2c_bus_heats_at_the_blind_duty);
    RUN_TEST(test_a_healthy_probe_never_takes_the_blind_path);
    RUN_TEST(test_a_wet_reason_blinds_only_its_own_law);
    RUN_TEST(test_a_latched_runaway_heats_blind);
    RUN_TEST(test_the_off_switches_still_refuse);
    RUN_TEST(test_no_consent_still_refuses);
    RUN_TEST(test_pin_integrity_still_refuses);
    RUN_TEST(test_a_measured_overtemperature_is_never_overridden);
    RUN_TEST(test_the_die_is_the_last_witness);
    RUN_TEST(test_the_de_creep_mask_blinds_the_rh_law_until_the_die_gate_closes);
    RUN_TEST(test_the_caps_still_apply);
    RUN_TEST(test_safety_alone_does_not_discard_the_attended_setpoint);
    RUN_TEST(test_safety_annotates_the_committed_tip_loop_and_clamps_at_80);
    RUN_TEST(test_a_tip_law_regulates_through_a_dead_chamber);
    RUN_TEST(test_the_rh_law_regulates_through_a_dead_tip);
    RUN_TEST(test_safety_still_blinds_the_open_loop_override);
    RUN_TEST(test_a_measured_overtemperature_refuses_even_attended_with_safety_down);
    RUN_TEST(test_no_tip_still_blinds_even_with_an_attended_setpoint);
    return UNITY_END();
}
