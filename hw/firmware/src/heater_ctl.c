#include "heater_ctl.h"

#include <stddef.h>

void o2p_heater_ctl_reset(o2p_heater_state_t *st)
{
    if (st == NULL) {
        return;
    }
    st->integ = 0.0f;
    st->runaway_latched = false;
    st->runaway_evidence_s = 0u;
    st->runaway_clear_s = 0u;
    st->zero_duty_timing = false;
    st->zero_duty_since_s = 0u;
    st->dt_clamped = false;
    st->tip_clamped = false;
    st->last_mode = O2P_HEATER_MODE_RH;
}

/* Collect every reason the loop may not drive this cycle.
 *
 * Written as an accumulating mask rather than a chain of early returns so that
 * adding an interlock cannot accidentally shadow an existing one, and so each
 * can be tested in isolation. */
static uint16_t interlocks(o2p_heater_state_t *st,
                           const o2p_heater_cfg_t *cfg,
                           const o2p_heater_in_t *in)
{
    uint16_t block = 0u;

    if (!in->drive_possible) {
        block |= O2P_HB_NOT_COMPILED;
    }
    if (!in->pin_integrity_ok) {
        block |= O2P_HB_PIN_INTEGRITY;
    }
    if (cfg->max_duty_x100 == 0u) {
        block |= O2P_HB_CONFIG_OFF;
    }
    /* Autonomous heating needs explicit consent; attended bench driving does
     * not, because arming the override IS the authorisation and it cannot
     * survive a reset.
     *
     * Which consent depends on which loop the stored configuration asks for.
     * A stored tip setpoint selects the temperature loop, and an UNCONSENTED
     * one REFUSES rather than falling through to the RH loop. Silently running
     * a different control law than the one configured would be the worst of
     * both: the operator sees the ring driving, assumes their setpoint took,
     * and is actually watching a humidity loop. An unevaluable authorisation
     * must not read as permission to do something else. */
    if (!cfg->test_override) {
        if (cfg->tip_sp_valid) {
            if (!cfg->tip_consent) {
                block |= O2P_HB_NO_CONSENT;
            }
        } else if (!cfg->rh_consent) {
            block |= O2P_HB_NO_CONSENT;
        }
    }
    if (!in->safety_armed) {
        /* The TMP117's therm-mode alert is the hardware cutoff. Driving 1 W
         * into the membrane while the only autonomous limit is unprogrammed
         * is precisely what DESIGN.md:47-51 refuses to credit. */
        block |= O2P_HB_SAFETY;
    }
    if (!in->rh_valid && !cfg->test_override && !cfg->tip_sp_valid) {
        /* No humidity means no controlled quantity. Note this also covers the
         * SHT45 de-creep window: main.c marks the chamber invalid while the
         * element is deliberately warm, and a loop that trusted that reading
         * would see the pulse as the pile drying out and back off.
         *
         * Suppressed for the persistent tip loop, which controls a
         * temperature and has no use for humidity at all. This is the ONLY
         * interlock that mode suppresses - NO_CHAMBER and DT_LIMIT stay live,
         * because unlike the bench override it runs with nobody present. */
        block |= O2P_HB_NO_RH;
    }
    if (!in->tip_valid) {
        block |= O2P_HB_NO_TIP;
    }
    if (!in->chamber_valid && !cfg->test_override) {
        /* Without chamber temperature there is no dT to clamp against, so the
         * 0-4 K design envelope cannot be enforced. Refuse rather than heat
         * open-loop on temperature. */
        block |= O2P_HB_NO_CHAMBER;
    }
    /* REMOVED 2026-09-11 (Fab's order, ~01:45): the supply veto. The old
     * rule refused ALL autonomous heating on a rail fault "because heating
     * adds ~86 mA" - while blind_duty() below happily drives 50 % through
     * the SAME rail fault with no sensors at all. Working sensors earned
     * LESS heating than no sensors: backwards. The heater is <1 W and cannot
     * start a fire; heat is also exactly what a wet board needs. The bit
     * stays VISIBLE - o2p_heater_ctl_step() ORs O2P_HB_SUPPLY into
     * HEATER_BLOCK as an annotation when duty is being driven despite the
     * rail - it no longer vetoes anything. */
    if (st->runaway_latched) {
        block |= O2P_HB_RUNAWAY;
    }

    /* Absolute tip limit, with hysteresis. Evaluated only when the reading is
     * good: an unevaluable temperature is already NO_TIP above, and must not
     * silently pass the limit check as though it were cold. */
    if (in->tip_valid) {
        if (st->tip_clamped) {
            if (in->t_tip_c100 < O2P_HEATER_TIP_RELEASE_C100) {
                st->tip_clamped = false;
            }
        } else if (in->t_tip_c100 >= O2P_HEATER_TIP_LIMIT_C100) {
            st->tip_clamped = true;
        }
        if (st->tip_clamped) {
            block |= O2P_HB_TIP_LIMIT;
        }
    }

    /* dT clamp, with hysteresis, against the configured 0-4 K envelope.
     *
     * INERT on Rev A: measured 2026-09-04, |tip - chamber| stayed within
     * 0.17 K at every duty from 0 to 100 %, because U10 and U12 are 6.6 mm
     * apart on the same copper. This block cannot raise DT_LIMIT on this
     * board and must not be counted as protection - the live limits are the
     * absolute tip clamp above, and the TMP117's 85 C hardware cutoff. It is
     * kept, not deleted, because it is correct the moment a revision puts a
     * sensor somewhere thermally different. */
    if (cfg->test_override) {
        /* Drop the latch rather than merely skipping the test. A clamp left
         * set would still be set when the override is disarmed, and the loop
         * would then refuse to drive for a dT it never re-evaluated. */
        st->dt_clamped = false;
    } else if (in->tip_valid && in->chamber_valid) {
        int32_t dt = (int32_t)in->t_tip_c100 - (int32_t)in->t_chamber_c100;
        int32_t on = (int32_t)cfg->dt_max_k100;
        int32_t off = on - O2P_HEATER_DT_HYST_K100;
        if (off < 0) {
            off = 0;
        }
        if (st->dt_clamped) {
            if (dt < off) {
                st->dt_clamped = false;
            }
        } else if (dt >= on) {
            st->dt_clamped = true;
        }
        if (st->dt_clamped) {
            block |= O2P_HB_DT_LIMIT;
        }
    }

    return block;
}

/* Latch a heater that is warming the tip while we command nothing.
 *
 * Runs only when the hardware is genuinely under our control: with the heater
 * compiled out, PA8 is a plain output held low and a hot tip means something
 * about the environment or the sensors, not a stuck FET. Attributing it to
 * runaway then would be a fault bit that no one can act on.
 *
 * HOLDS WHILE THE EVIDENCE PERSISTS. Until 2026-09-10 it latched until reset,
 * on this argument: "A FET that conducts without being asked, or a gate node
 * driven by something else, is a hardware failure - and the firmware that just
 * discovered it cannot control the heater is not the thing that should decide
 * the fault has cleared. Auto-clearing would re-arm 1 W against a membrane
 * every time the tip cooled."
 *
 * WHAT REFUTED THE PREMISE. On 2026-09-10 about 80 C water was poured into
 * the bench jar with the RH loop running (probe 3, build 75162fa). The tip rose
 * 20 K in six minutes, starting two minutes BEFORE any duty was commanded,
 * while the die lagged across the thermal barrier; tip-minus-die crossed 10 K
 * and this latched at 11:07 UTC with no sign of the FET conducting. VIN held
 * its 10710 mV baseline through the uncommanded rise; the 15-23 mV dip seen
 * while 5.00 % WAS commanded puts the source impedance at 3.9-6.0 ohm, so
 * continuous conduction (76.5 mA through 140 ohm) would have sagged it by an
 * estimated 0.30-0.46 V. And the chamber ran up to 0.8 K AHEAD of the tip,
 * which ring heat never does on this board (<= 0.17 K at any duty, measured
 * 2026-09-04). HOW FAR THAT GOES: it excludes continuous conduction, not a
 * small leak - published VIN resolves only 7.5 mV (main.c truncates to whole
 * ADC millivolts before the 7.5 divider ratio), so a 0.5 mA leak would be
 * invisible. Such a leak dissipates ~35 uW and cannot produce this signature,
 * so the latch here was attributing the bath to the FET either way; and VIN
 * also read 10695 mV once at zero duty, so it is corroboration, not proof.
 * So the signature does not mean uncommanded conduction: any environment that heats the tip end
 * faster than the die end produces it, and a probe pushed into a hot pile is
 * exactly that. Latched until reset, one such event disabled the heater
 * until someone power-cycled a probe that is meant to be buried.
 *
 * HOW NARROWLY TO READ THE CHANGE. The latch sets on the same evidence, holds
 * duty at zero, and holds for as long as that evidence persists - which is what
 * a stuck FET does, because it keeps heating. It releases only after
 * O2P_HEATER_RUNAWAY_WINDOW_S of evidence that is evaluable on EVERY reference
 * and below both thresholds by O2P_HEATER_RUNAWAY_RELEASE_HYST_K100. Every
 * reference is the point: on Rev A the chamber tracks the tip within 0.17 K
 * whatever the FET is doing, so the chamber alone can never exonerate one, and
 * a lost die sensor therefore falls back to the old latched-until-reset
 * behaviour instead of releasing. Three further rules, all found by review of
 * eae463f and all erring toward staying latched:
 *   - a chamber temperature BRIDGED from the cache (main.c) does not count;
 *     release requires chamber_fresh as well as chamber_valid, because a dead
 *     SHT45 could otherwise finish the window on its last reading;
 *   - a sample with the tip, or both references, invalid RESETS the release
 *     window. For latching, crediting up to O2P_HEATER_RUNAWAY_MAX_GAP_S of
 *     blindness errs toward latching and is kept; for release it errs toward
 *     exoneration, so it is not;
 *   - arming the bench override DISCARDS banked release evidence. Accumulation
 *     is frozen while armed so arming cannot erase a stuck FET's record; clear
 *     evidence is reset so arming cannot carry a half-proved exoneration across
 *     an interval nobody could observe.
 * No register write clears the latch, and FAULTS_EVER keeps HEATER_RUNAWAY
 * after a release, so the event is never erased.
 *
 * WHAT IS GIVEN UP, stated rather than implied. "Re-arm every time the tip
 * cooled" survives in one failure class: a firmware-side fault that heats while
 * duty reads idle AND that forcing duty to zero does stop. That now cycles - a
 * window of evidence to latch, a window of clear evidence to release - where it
 * used to stop for good, visible as HEATER_RUNAWAY toggling. What bounds it: the
 * TMP117 ALERT is open-drain (VOL <= 0.4 V at 3 mA, TI SNOSD82) on the gate node,
 * so it overpowers the MCU's drive through R28 (<= 0.33 mA) and can hold the FET
 * off against a firmware fault - at its 85 C TRIP point, with overshoot never
 * measured and the alert path never fault-injected. The 82 C firmware clamp
 * helps only if the faulty path still honours a zero command. Neither stops a
 * drain-source short or a strong driver directly on the gate, and no duty
 * command does either, latched or not.
 */
static void update_runaway(o2p_heater_state_t *st,
                           const o2p_heater_cfg_t *cfg,
                           const o2p_heater_in_t *in,
                           uint32_t now_s,
                           uint16_t duty_x100)
{
    if (!in->drive_possible) {
        return;
    }
    /* The bench override suspends ACCUMULATION - never the latch, which
     * interlocks() still honours and which no register write can clear.
     *
     * The detector's premise is that heat the firmware did not command is
     * evidence of a stuck FET. In a deliberate thermal test that premise is
     * false by construction: the probe is in a hot bath or beside a heat gun,
     * so the tip runs tens of kelvin above the die across the thermal barrier
     * at zero duty, which is exactly the die-referenced signature. It would
     * latch inside the 60 s window and disable the heater until the bath had
     * equilibrated with the die end - which interrupts the experiment rather
     * than reporting on it.
     *
     * What is given up is small and bounded: the detector already returns
     * early whenever duty exceeds the idle threshold, so it was never
     * watching while the ring was actually being driven. What remains is the
     * TMP117's 85 C therm-mode cutoff, the absolute tip clamp, and an
     * operator standing at the bench - which is the whole reason this mode
     * requires a magic word and cannot survive a reset. */
    if (cfg->test_override) {
        /* FREEZE the detector; do not wipe it. It used to clear both the
         * timing and the accumulated evidence, which made arming a way to
         * erase the detector's memory - and because the caller runs at 1 Hz
         * against a 60 s window, one armed sample every 60 s held the counter
         * at zero forever while a genuinely stuck FET went on heating.
         *
         * The clock is still advanced, so an armed sample does not look like
         * a gap in observation to the next disarmed one. That is what stops
         * alternating arm/disarm from resetting the evidence: disarmed
         * samples continue to accumulate from where they left off, so the
         * latch is delayed in proportion to the duty cycle of the abuse
         * rather than prevented outright.
         *
         * What remains, unavoidably, is that CONTINUOUSLY armed suppresses
         * accumulation - while armed we cannot distinguish commanded heat, or
         * a hot bath, from a stuck FET. That residual is exactly why this mode
         * needs a magic word, cannot survive a reset, and is documented as
         * attended. */
        /* RELEASE EVIDENCE IS RESET, NOT FROZEN - asymmetric on purpose, and
         * both directions err toward staying latched. Freezing accumulation
         * keeps arming from erasing a stuck FET's record. Freezing clear
         * evidence would do the opposite: 59 banked seconds carried across an
         * armed interval nobody could observe, released by the first clear
         * sample after disarming. Found by review of eae463f. */
        st->runaway_clear_s = 0u;
        st->zero_duty_timing = true;
        st->zero_duty_since_s = now_s;
        return;
    }
    /* Commanded heat is not runaway - but "commanded" has to mean a duty that
     * could actually explain the excess, not merely a nonzero one. */
    if (duty_x100 > O2P_HEATER_RUNAWAY_IDLE_DUTY_X100) {
        st->zero_duty_timing = false;
        st->runaway_evidence_s = 0u;
        st->runaway_clear_s = 0u;
        return;
    }
    /* Unevaluable is not evidence either way - but it is also not a reason to
     * hold the clock, because holding it would credit the unobserved interval
     * once observation resumes. Leave the accumulator alone and let the gap
     * test below discard it if the blindness lasted. */
    if (!in->tip_valid || (!in->chamber_valid && !in->die_valid)) {
        if (st->runaway_latched) {
            /* For RELEASE the blind interval is not credited: reset the window
             * and move the clock, so the next valid sample earns one second,
             * not the whole gap. Leaving both alone released a latch on 59
             * clear seconds, one invalid sample and one clear one. Found by
             * review of eae463f. The latching path above is unchanged. */
            st->runaway_clear_s = 0u;
            st->zero_duty_since_s = now_s;
        }
        return;
    }

    /* Two independent tests, OR'd, because the chamber-referenced one cannot
     * fire on a board whose sensors sit on the same copper. Chamber first,
     * for a revision whose sensors are actually separated. */
    bool hot = false;
    /* The release criterion is NOT "not hot". It needs every reference valid
     * and each below its threshold by the hysteresis, so it starts false and
     * any missing or marginal reference keeps it false. */
    bool cleared = true;
    if (in->chamber_valid) {
        int32_t dt = (int32_t)in->t_tip_c100 - (int32_t)in->t_chamber_c100;
        int32_t on = (int32_t)cfg->dt_max_k100 + O2P_HEATER_RUNAWAY_MARGIN_K100;
        if (dt > on) {
            hot = true;
        }
        if (dt > on - O2P_HEATER_RUNAWAY_RELEASE_HYST_K100) {
            cleared = false;
        }
        if (!in->chamber_fresh) {
            /* Bridged from the cache: good enough for the clamp and for
             * latching, not for exonerating. See chamber_fresh. */
            cleared = false;
        }
    } else {
        cleared = false;
    }
    /* Die-referenced: the one that can see a stuck-on FET while the loop is
     * idle, because the die is across the thermal barrier and does not follow
     * the tip. It does NOT see a FET stuck on while the loop is commanding
     * substantial heat - nothing here can, without a thermal model of the
     * plant. That case is covered from the other side, by the dt_max interlock
     * zeroing the duty, and only for excursions large enough to trip it. */
    if (in->die_valid) {
        int32_t dd = (int32_t)in->t_tip_c100 - (int32_t)in->t_die_c100;
        if (dd > O2P_HEATER_RUNAWAY_DIE_K100) {
            hot = true;
        }
        if (dd > O2P_HEATER_RUNAWAY_DIE_K100 -
                     O2P_HEATER_RUNAWAY_RELEASE_HYST_K100) {
            cleared = false;
        }
    } else {
        cleared = false;
    }

    if (!st->zero_duty_timing) {
        st->zero_duty_timing = true;
        st->zero_duty_since_s = now_s;
        st->runaway_evidence_s = 0u;
        st->runaway_clear_s = 0u;
        return;
    }
    /* Unsigned subtraction, so a wrap of now_s is harmless. */
    uint32_t since = (uint32_t)(now_s - st->zero_duty_since_s);
    st->zero_duty_since_s = now_s;
    if (since > O2P_HEATER_RUNAWAY_MAX_GAP_S) {
        /* We were not watching. What we hold describes a different
         * situation, so it is discarded rather than extended. */
        st->runaway_evidence_s = 0u;
        st->runaway_clear_s = 0u;
        return;
    }

    if (st->runaway_latched) {
        /* Releasing. Any sample that is not fully cleared - hot, inside the
         * hysteresis band, missing a reference, or carrying a bridged chamber
         * temperature - restarts the window. */
        if (!cleared) {
            st->runaway_clear_s = 0u;
            return;
        }
        if (st->runaway_clear_s < O2P_HEATER_RUNAWAY_WINDOW_S) {
            st->runaway_clear_s = (uint16_t)(st->runaway_clear_s + since);
        }
        if (st->runaway_clear_s >= O2P_HEATER_RUNAWAY_WINDOW_S) {
            st->runaway_latched = false;
            st->runaway_clear_s = 0u;
            st->runaway_evidence_s = 0u;
        }
        return;
    }

    if (!hot) {
        st->runaway_evidence_s = 0u;
        return;
    }
    if (st->runaway_evidence_s < O2P_HEATER_RUNAWAY_WINDOW_S) {
        st->runaway_evidence_s = (uint16_t)(st->runaway_evidence_s + since);
    }
    if (st->runaway_evidence_s >= O2P_HEATER_RUNAWAY_WINDOW_S) {
        st->runaway_latched = true;
        st->runaway_clear_s = 0u;
    }
}

/* The PI core, shared by the humidity loop and the tip-temperature loop.
 *
 * Factored out rather than copied because the anti-windup is the part that is
 * easy to get subtly wrong, and two copies drift. `e` is in whatever units the
 * caller's controlled quantity uses, positive meaning "ask for more duty";
 * only that sign convention is shared, and each caller owns its own gains.
 *
 * `mode` zeroes the integrator whenever the controlled quantity changes: an
 * integral wound up in 0.01 %RH has no meaning in 0.01 K, and carrying it
 * across would slam the output on the first cycle after a mode switch. */
static uint16_t pi_step(o2p_heater_state_t *st, uint8_t mode, uint8_t session,
                        float e, float kp, float ki, float max_duty)
{
    if (st->last_mode != mode || st->last_session != session) {
        /* Mode change, or a NEW override session. The session counter exists
         * because a disarm and re-arm served between two 1 Hz decisions is
         * invisible to the mode tag alone - the loop would resume a fresh
         * bench run carrying the previous run's integral. */
        st->integ = 0.0f;
        st->last_mode = mode;
        st->last_session = session;
    }

    /* An integrator is the accumulated INTEGRAL ACTION, so with no integral
     * gain there is none to hold. Without this, writing ki = 0 leaves whatever
     * was already wound up contributing forever: with kp = 0 too, p is zero,
     * nothing further accumulates, and the output stays parked at the stale
     * integral - so "I set both gains to zero" produces sustained duty rather
     * than none. Found by review 2026-09-08. Clearing here rather than
     * refusing a zero gain keeps P-only tuning (ki = 0, kp > 0) legal, which
     * is a reasonable thing to want on an unmeasured plant. */
    if (ki == 0.0f) {
        st->integ = 0.0f;
    }

    const float p = kp * e;

    /* Conditional integration. Integrate only when the output is off its
     * limits, or when the error would drive it back inside them - the textbook
     * anti-windup that costs nothing and is trivially testable. Computing the
     * tentative output from the OLD integrator first is what makes the
     * decision meaningful. */
    float u = p + st->integ;
    const bool at_top = (u >= max_duty);
    const bool at_bottom = (u <= 0.0f);
    if ((!at_top && !at_bottom) || (at_top && e < 0.0f) || (at_bottom && e > 0.0f)) {
        st->integ += ki * e;   /* dt = 1 s by construction of the caller */
        /* Bound the integrator itself as well, so a long excursion cannot
         * park it somewhere it takes minutes to unwind from. */
        if (st->integ > max_duty) {
            st->integ = max_duty;
        } else if (st->integ < -max_duty) {
            st->integ = -max_duty;
        }
        u = p + st->integ;
    }

    if (u < 0.0f) {
        u = 0.0f;
    } else if (u > max_duty) {
        u = max_duty;
    }
    return (uint16_t)(u + 0.5f);
}

/* The duty the blind fallback drives, or zero if it may not. The rule and its
 * reasons are at O2P_HEATER_BLIND_DUTY_X100 in heater_ctl.h. */
static uint16_t blind_duty(const o2p_heater_cfg_t *cfg,
                           const o2p_heater_in_t *in,
                           uint16_t block)
{
    const uint16_t hard = O2P_HB_NOT_COMPILED | O2P_HB_CONFIG_OFF |
                          O2P_HB_NO_CONSENT | O2P_HB_PIN_INTEGRITY |
                          O2P_HB_TIP_LIMIT | O2P_HB_DT_LIMIT;
    const uint16_t wet = O2P_HB_SAFETY | O2P_HB_NO_TIP | O2P_HB_NO_CHAMBER |
                         O2P_HB_SUPPLY | O2P_HB_RUNAWAY;
    if ((block & hard) != 0u || (block & wet) == 0u) {
        return 0u;
    }
    if (!in->die_valid || in->t_die_c100 >= O2P_HEATER_BLIND_DIE_MAX_C100) {
        return 0u;
    }
    uint16_t duty = O2P_HEATER_BLIND_DUTY_X100;
    if (duty > cfg->max_duty_x100) {
        duty = cfg->max_duty_x100;
    }
    /* An operator's open-loop duty is a ceiling too. The override's tip loop
     * has no duty of its own, so only the cap applies there. */
    if (cfg->test_override && !cfg->test_tip_sp_valid &&
        duty > cfg->test_duty_x100) {
        duty = cfg->test_duty_x100;
    }
    return duty;
}

void o2p_heater_ctl_step(o2p_heater_state_t *st,
                         const o2p_heater_cfg_t *cfg,
                         const o2p_heater_in_t *in,
                         uint32_t now_s,
                         o2p_heater_out_t *out)
{
    if (st == NULL || cfg == NULL || in == NULL || out == NULL) {
        return;
    }

    uint16_t block = interlocks(st, cfg, in);
    /* Annotation, not refusal (removed as a veto 2026-09-11, Fab's order):
     * a rail fault is reported so the register explains why the duty reads
     * what it reads, but no longer stops the heater. See interlocks(). */
    const uint16_t supply_note = in->supply_ok ? 0u : O2P_HB_SUPPLY;
    if (block != 0u) {
        /* Zero the integrator rather than freezing it. Freezing would make the
         * loop slam to whatever it had wound up to the moment an interlock
         * cleared - the opposite of what you want after a fault. Restarting
         * from proportional-only is bumpless and slow, which is correct for a
         * plant nobody has measured. */
        st->integ = 0.0f;
        const uint16_t duty = blind_duty(cfg, in, block);
        out->duty_x100 = duty;
        out->block = (uint16_t)((block | supply_note) |
                                ((duty != 0u) ? O2P_HB_BLIND : 0u));
        update_runaway(st, cfg, in, now_s, duty);
        return;
    }

    const float max_duty = (float)cfg->max_duty_x100;
    uint16_t duty;

    if (cfg->test_override && cfg->test_tip_sp_valid) {
        /* Tip-temperature loop. Positive error means too cold, which means
         * more duty - the same sign convention the humidity loop uses.
         *
         * in->tip_valid is guaranteed here: an invalid tip is O2P_HB_NO_TIP,
         * which the override does not suppress and which returned above. */
        const float e = (float)((int32_t)cfg->test_tip_sp_c100 -
                                (int32_t)in->t_tip_c100);
        duty = pi_step(st, O2P_HEATER_MODE_TIP, cfg->session, e,
                       (float)cfg->test_kp_x100 * 0.01f,
                       (float)cfg->test_ki_x100 * 0.01f,
                       max_duty);
    } else if (cfg->test_override) {
        /* Open loop. The integrator is zeroed through the mode switch, so
         * disarming hands the next loop the same bumpless proportional-only
         * restart that clearing an interlock does. */
        if (st->last_mode != O2P_HEATER_MODE_OPEN) {
            st->integ = 0.0f;
            st->last_mode = O2P_HEATER_MODE_OPEN;
        }
        duty = cfg->test_duty_x100;
        if (duty > cfg->max_duty_x100) {
            duty = cfg->max_duty_x100;
        }
    } else if (cfg->tip_sp_valid) {
        /* PERSISTENT tip-temperature loop. Same control law and same sign
         * convention as the override's, sharing the override's volatile gains
         * (the record had no room for a flash-backed pair) and carrying its own
         * mode tag so the integrator restarts when authority changes hands.
         *
         * cfg->tip_consent is guaranteed true here: an unconsented setpoint
         * raises O2P_HB_NO_CONSENT in interlocks() and returned above.
         * in->tip_valid is guaranteed for the same reason NO_TIP gives. */
        const float e = (float)((int32_t)cfg->tip_sp_c100 -
                                (int32_t)in->t_tip_c100);
        duty = pi_step(st, O2P_HEATER_MODE_TIP_AUTO, cfg->session, e,
                       (float)cfg->test_kp_x100 * 0.01f,
                       (float)cfg->test_ki_x100 * 0.01f,
                       max_duty);
    } else {
        /* Positive error means too humid, which means not enough heat. */
        const float e = (float)in->rh_x100 - (float)cfg->setpoint_x100;
        duty = pi_step(st, O2P_HEATER_MODE_RH, cfg->session, e,
                       (float)cfg->kp_x100 * 0.01f,
                       (float)cfg->ki_x100 * 0.01f,
                       max_duty);
    }

    out->duty_x100 = duty;
    out->block = supply_note;   /* annotation only - see interlocks() */
    /* Annotations, not refusals (see the bit definitions): duty 0 with no
     * interlock raised is an answer, not a fault, and a stored tip setpoint
     * at the sentinel selects the RH loop - both belong in HEATER_BLOCK so
     * the register explains why duty is zero in these cases too. */
    if (duty == 0u && !cfg->test_override) {
        out->block |= O2P_HB_IDLE;
    }
    if (!cfg->tip_sp_valid && !cfg->test_override) {
        out->block |= O2P_HB_TIP_DISARMED;
    }

    update_runaway(st, cfg, in, now_s, out->duty_x100);
    if (st->runaway_latched) {
        /* Latched this very cycle: do not wait a cycle to act on it.
         * (CORRECTED 2026-09-11, codex-xhigh audit finding 9: this used to
         * OVERWRITE the mask, dropping the supply annotation on the latch
         * cycle - the register must keep telling the whole truth even while
         * refusing to burn. OR it in instead.) */
        out->duty_x100 = 0u;
        out->block |= O2P_HB_RUNAWAY;
        st->integ = 0.0f;
    }
}
