#include "heater_ctl.h"

#include "psychro.h"

#include <stddef.h>

void o2p_heater_ctl_reset(o2p_heater_state_t *st)
{
    if (st == NULL) {
        return;
    }
    st->integ = 0.0f;
    st->integ_floor = 0.0f;
    st->runaway_latched = false;
    st->runaway_peak_k100 = -32768;
    st->dew_unreachable = false;
    st->dew_prev_valid = false;
    st->dew_pinned = false;
    st->dew_recovered = false;
    st->dew_dwell_s = 0u;
    st->dew_clear_s = 0u;
    st->dew_prev_s = 0u;
    st->dew_retry_at_s = 0u;
    st->dew_paused = false;
    st->dew_pause_since_s = 0u;
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
 * can be tested in isolation.
 *
 * The 2026-09-11 law-aware helpers below (tip_law_in_command, law_wet_mask)
 * are used here for the annotated 80.00 C tip clamp and in
 * o2p_heater_ctl_step() for the annotation/refusal split; defined after this
 * function, declared here. */
static bool tip_law_in_command(const o2p_heater_cfg_t *cfg);
static bool dew_law_in_command(const o2p_heater_cfg_t *cfg,
                               const o2p_heater_in_t *in);
static bool gas_dew_point_c100(const o2p_heater_in_t *in, float *out_c100);
static int32_t dew_ceiling_c100(const o2p_heater_cfg_t *cfg,
                                const o2p_heater_in_t *in);
static uint16_t law_wet_mask(const o2p_heater_cfg_t *cfg,
                             const o2p_heater_in_t *in);
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
    if (dew_law_in_command(cfg, in) && in->rh_valid && in->chamber_valid) {
        /* The dew-margin law's control quantity is the gas dew point. A
         * humidity the Magnus form cannot take (<= 0 or > 100 %RH) is no
         * humidity for this law - raised under the RH sensor's own bit
         * rather than read as a comfortable margin. */
        float td_c100;
        if (!gas_dew_point_c100(in, &td_c100)) {
            block |= O2P_HB_NO_RH;
        }
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
     * silently pass the limit check as though it were cold.
     *
     * The clamp is 80.00 C, not 82.00, while SAFETY is in the annotated
     * state - a tip law in command, its sensor valid, the hardware therm
     * backstop known down (Fab's order 2026-09-11: "unattended loop:
     * annotate and regulate (keep <=80 C)"). NOT a permanent change: the
     * normal limit resumes the moment safety_armed does or no tip law is
     * in command.
     *
     * The dew-margin law (FW 0x0013) clamps at 80.00 C UNCONDITIONALLY: it
     * is the law that deliberately drives the tip toward its cap in
     * saturated gas ("margin, up to the 80 C tip cap", Fab 2026-09-11), so
     * the cap is part of the law, not a SAFETY-dependent tightening. */
    if (in->tip_valid) {
        const int32_t tip_limit =
            ((!in->safety_armed && tip_law_in_command(cfg)) ||
             dew_law_in_command(cfg, in))
                ? (int32_t)O2P_HEATER_TIP_LIMIT_ANNOTATED_C100
                : (int32_t)O2P_HEATER_TIP_LIMIT_C100;
        if (st->tip_clamped) {
            if (in->t_tip_c100 < O2P_HEATER_TIP_RELEASE_C100) {
                st->tip_clamped = false;
            }
        } else if (in->t_tip_c100 >= tip_limit) {
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
    /* HOW FAR OVER the latching threshold this sample sits, in 0.01 K, taken
     * over whichever references are valid. This is the quantity the decay
     * discriminator watches - see O2P_HEATER_RUNAWAY_DECAY_K100. INT32_MIN
     * means no reference produced one. */
    int32_t excess = INT32_MIN;
    if (in->chamber_valid) {
        int32_t dt = (int32_t)in->t_tip_c100 - (int32_t)in->t_chamber_c100;
        int32_t on = (int32_t)cfg->dt_max_k100 + O2P_HEATER_RUNAWAY_MARGIN_K100;
        if (dt - on > excess) {
            excess = dt - on;
        }
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
        if (dd - O2P_HEATER_RUNAWAY_DIE_K100 > excess) {
            excess = dd - O2P_HEATER_RUNAWAY_DIE_K100;
        }
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

    /* Clamp into the int16 the state carries. Only the COMPARISON matters,
     * and it is against a 1.00 K band, so saturating an excess of hundreds of
     * kelvin changes nothing a probe could ever experience. */
    int32_t peak_in = excess;
    if (peak_in > 32767) {
        peak_in = 32767;
    } else if (peak_in < -32768) {
        peak_in = -32768;
    }

    if (!st->zero_duty_timing) {
        st->zero_duty_timing = true;
        st->zero_duty_since_s = now_s;
        st->runaway_evidence_s = 0u;
        st->runaway_clear_s = 0u;
        st->runaway_peak_k100 = (int16_t)peak_in;
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
        st->runaway_peak_k100 = (int16_t)peak_in;
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
        st->runaway_peak_k100 = (int16_t)peak_in;
        return;
    }

    /* THE DECAY DISCRIMINATOR (O2P_HEATER_RUNAWAY_DECAY_K100). The tests
     * above are on a level, and a level cannot tell heat the firmware
     * commanded and then stopped commanding - which decays from its peak with
     * tau = 150 s - from a FET stuck on, which holds its peak. So: evidence
     * accumulates only while the excess has NOT fallen materially below the
     * highest value this window has seen.
     *
     * Re-basing the peak on the way down is the part that matters. Without
     * it, one hot excursion would leave a high-water mark that suppressed the
     * detector for as long as the window survived; with it, the peak tracks
     * the decay down and a FET that sticks on at any point is measured
     * against where the plant actually is. */
    if (peak_in > (int32_t)st->runaway_peak_k100) {
        st->runaway_peak_k100 = (int16_t)peak_in;
    } else if ((int32_t)st->runaway_peak_k100 - peak_in
                   > O2P_HEATER_RUNAWAY_DECAY_K100) {
        st->runaway_evidence_s = 0u;
        st->runaway_peak_k100 = (int16_t)peak_in;
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
/* The arithmetic half of pi_step(), on a CALLER-SUPPLIED integrator.
 *
 * Split out 2026-09-13 for the gradient floor (O2P_HEATER_FLOOR_DELTA_K100),
 * which runs concurrently with the dew law and therefore needs an integrator
 * of its own: the mode tag arbitrates between laws that take turns, and these
 * two do not. Nothing about the anti-windup changed - pi_step() below is this
 * function plus the mode/session reset it always did, so the existing callers
 * are byte-for-byte the same law.
 *
 * Anti-windup is per-integrator and against THIS loop's own limit, which is
 * what makes the high-select safe: a loser with a positive error is a loop
 * asking for more duty than it is getting, and it stops integrating at
 * max_duty exactly as if it were alone. A loser with a NEGATIVE error - the
 * ordinary case, because the winner's extra duty overshoots the loser's
 * target - unwinds toward zero on its own. */
static uint16_t pi_core(float *integ, float e, float kp, float ki,
                        float max_duty)
{
    /* An integrator is the accumulated INTEGRAL ACTION, so with no integral
     * gain there is none to hold; see pi_step() for the full argument. */
    if (ki == 0.0f) {
        *integ = 0.0f;
    }

    const float p = kp * e;

    float u = p + *integ;
    const bool at_top = (u >= max_duty);
    const bool at_bottom = (u <= 0.0f);
    if ((!at_top && !at_bottom) || (at_top && e < 0.0f) || (at_bottom && e > 0.0f)) {
        *integ += ki * e;   /* dt = 1 s by construction of the caller */
        if (*integ > max_duty) {
            *integ = max_duty;
        } else if (*integ < -max_duty) {
            *integ = -max_duty;
        }
        u = p + *integ;
    }

    if (u < 0.0f) {
        u = 0.0f;
    } else if (u > max_duty) {
        u = max_duty;
    }
    return (uint16_t)(u + 0.5f);
}

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

    /* WHY ki == 0 CLEARS THE INTEGRATOR, and why conditional integration is
     * written the way it is in pi_core(): an integrator is the accumulated
     * INTEGRAL ACTION, so with no integral gain there is none to hold.
     * Without that, writing ki = 0 leaves whatever was already wound up
     * contributing forever: with kp = 0 too, p is zero, nothing further
     * accumulates, and the output stays parked at the stale integral - so "I
     * set both gains to zero" produces sustained duty rather than none. Found
     * by review 2026-09-08. Clearing rather than refusing a zero gain keeps
     * P-only tuning (ki = 0, kp > 0) legal, which is a reasonable thing to
     * want on an unmeasured plant.
     *
     * The anti-windup is the textbook conditional integration: integrate only
     * when the output is off its limits, or when the error would drive it
     * back inside them, with the tentative output computed from the OLD
     * integrator so the decision is meaningful. */
    return pi_core(&st->integ, e, kp, ki, max_duty);
}

/* THE HARD MASK, unchanged by the 2026-09-11 rulings: the off switches, the
 * authorisations, the pin evidence, and the two measured-overtemperature
 * clamps. These refuse for every law, and TIP_LIMIT and DT_LIMIT are raised
 * only from VALID readings - a measured overtemperature is never
 * overridden. */
static const uint16_t hard_mask = O2P_HB_NOT_COMPILED | O2P_HB_CONFIG_OFF |
                                  O2P_HB_NO_CONSENT | O2P_HB_PIN_INTEGRITY |
                                  O2P_HB_TIP_LIMIT | O2P_HB_DT_LIMIT;

/* The law in command (Fab's rulings 2026-09-11: "unattended loop: annotate
 * and regulate (keep <=80 C)" and the per-law blind rule - blind must
 * require the in-command loop's own control sensor to be invalid). A tip
 * setpoint - the volatile override's or the stored one - selects a tip law
 * whose control quantity is the tip; the override without one is open loop
 * (no control quantity, the operator's duty is the command); everything
 * else is the RH law, whose control quantity is the SHT45's RH. */
static bool tip_law_in_command(const o2p_heater_cfg_t *cfg)
{
    return (cfg->test_override && cfg->test_tip_sp_valid) ||
           (!cfg->test_override && cfg->tip_sp_valid);
}

/* The wet mask, LAW-AWARE: the sensor-unavailability bits that may blind
 * THIS law - only its own control sensor's absence - plus RUNAWAY, which is
 * not a sensor bit and keeps its membership for every law (a latched
 * stuck-FET verdict blinds everything). NO_CHAMBER is in no law's mask: the
 * chamber is no law's control quantity, it only feeds DT_LIMIT. SAFETY is
 * in the tip laws' mask ONLY while their control sensor is invalid - with
 * the tip valid it annotates instead (the 2026-09-11 annotate-and-regulate
 * ruling) - so it is masked for tip laws and kept for the open-loop
 * override and the RH law, which the rulings did not touch.
 *
 * RUNAWAY's wet membership has a second face, accepted with eyes open
 * (2026-09-11, review P2-7, Fab's call on the liberal option): because the
 * latch sits in the WET set, blind_duty() may DRIVE through it - a
 * blind-driven latch can sawtooth 50 % <-> 0 while its evidence persists.
 * That is the accepted price of the 2026-09-10 wet-board stubbornness
 * ("heat is exactly what a wet board needs"): the alternative - a hard
 * RUNAWAY that zeroed the blind path - is the state where a sensor verdict
 * is what leaves a wet board cold, which is the one situation the fallback
 * exists to prevent.
 * AMENDED FW 0x001C, Fab's "A" (2026-09-13): the latch drives blind only when
 * the tip or the cell cannot be read. With both readable it refuses to zero
 * duty - see blind_duty(). */
/* The dew-margin law (FW 0x0013) holds the autonomous humidity-side slot -
 * no override, no stored tip setpoint - whenever the cell-side reading is
 * valid. See O2P_HEATER_DEW_MARGIN_K100. */
static bool dew_law_in_command(const o2p_heater_cfg_t *cfg,
                               const o2p_heater_in_t *in)
{
    return !cfg->test_override && !cfg->tip_sp_valid && in->cell_valid;
}

/* THE DEW LAW'S TIP CEILING, in 0.01 C - one function so that everything that
 * means "the ceiling" means the same number: the law's tip_room, the gradient
 * floor's setpoint clamp, and the unreachable-margin detector's `pinned` test
 * (O2P_HEATER_DEW_UNREACH_DWELL_S). If these ever disagree the detector watches
 * a ceiling the law never reaches and goes silently dormant.
 *
 * FW 0x001A: the LOWER of the absolute 79.00 C ceiling and the cell-side
 * reading plus DT_MAX_K - the gradient ceiling, see
 * O2P_HEATER_DEW_TIP_CEIL_C100. Every caller runs inside the dew law, which
 * is in command only with the cell valid, so t_cell_c100 is a measurement
 * here and never a default. */
static int32_t dew_ceiling_c100(const o2p_heater_cfg_t *cfg,
                                const o2p_heater_in_t *in)
{
    int32_t ceiling = (int32_t)O2P_HEATER_DEW_TIP_CEIL_C100;
    const int32_t gradient = (int32_t)in->t_cell_c100 +
                             (int32_t)cfg->dt_max_k100;
    if (gradient < ceiling) {
        ceiling = gradient;
    }
    return ceiling;
}

/* PAUSE the unreachable-margin detector's evidence: the seconds from here on
 * are not observation and are never credited, but nothing already counted is
 * discarded. The pause's start is kept so a long one can be told from a glitch
 * when evidence resumes (O2P_HEATER_DEW_UNREACH_PAUSE_MAX_S). */
static void dew_detector_pause(o2p_heater_state_t *st, uint32_t now_s)
{
    if (!st->dew_paused) {
        st->dew_paused = true;
        st->dew_pause_since_s = now_s;
    }
    st->dew_prev_valid = false;
}

/* The gas dew point, in 0.01 C, from the SHT45's RH at the chamber
 * temperature. False if the Magnus form cannot take the humidity; the caller
 * owns validity of the two readings. */
static bool gas_dew_point_c100(const o2p_heater_in_t *in, float *out_c100)
{
    float td_c;
    if (!o2p_dewpoint_c((float)in->t_chamber_c100 * 0.01f,
                        (float)in->rh_x100 * 0.01f, &td_c)) {
        return false;
    }
    *out_c100 = td_c * 100.0f;
    return true;
}

static uint16_t law_wet_mask(const o2p_heater_cfg_t *cfg,
                             const o2p_heater_in_t *in)
{
    uint16_t wet = O2P_HB_RUNAWAY;
    if (tip_law_in_command(cfg)) {
        wet |= O2P_HB_NO_TIP;
    } else if (cfg->test_override) {
        /* Open loop: no control quantity to lose; SAFETY keeps its founding
         * blind membership here. */
        wet |= O2P_HB_SAFETY;
    } else if (dew_law_in_command(cfg, in)) {
        /* The dew-margin law: the tip is its bound, and an unevaluable cap is
         * not a cap, so NO_TIP blinds it. SINCE FW 0x001B NO_RH and
         * NO_CHAMBER do NOT: with only humidity lost the law has no dew point
         * and withholds its own demand, while the gradient floor - tip and
         * cell only - keeps regulating under dew_ceiling_c100(). Blinding here
         * sent every SHT45 de-creep into the 50 % fallback, which ignores the
         * gradient ceiling (codex review of 496dd2e, finding 1). SAFETY
         * annotates: the 80.00 C clamp is unconditional here (interlocks()). */
        wet |= O2P_HB_NO_TIP;
    } else {
        /* The RH law: its own sensor's absence blinds it. */
        wet |= O2P_HB_NO_RH | O2P_HB_SAFETY;
    }
    return wet;
}

/* The duty the blind fallback drives, or zero if it may not. The rule and its
 * reasons are at O2P_HEATER_BLIND_DUTY_X100 in heater_ctl.h. */
static uint16_t blind_duty(const o2p_heater_cfg_t *cfg,
                           const o2p_heater_in_t *in,
                           uint16_t refusing)
{
    const uint16_t wet = law_wet_mask(cfg, in);
    if ((refusing & hard_mask) != 0u || (refusing & wet) == 0u) {
        return 0u;
    }
    /* FAB'S "A", 2026-09-13 (codex review of 455972d, finding 1): a RUNAWAY
     * latch may drive blind ONLY when the tip or the cell cannot be read. The
     * review showed the gradient floor holding a hot tip at ~2.5 % duty - under
     * RUNAWAY's idle threshold - latching the detector, and the latch then
     * driving 50 % open loop past the gradient ceiling (model: 50 C ambient,
     * die 30 C, tip to 80 C, 29 K over the cell). With both sensors readable
     * there is a working loop to fall back to, so the latch now refuses: zero
     * duty, REFUSED. The wet-board rule it amends is kept for the case it was
     * written for - a board whose temperature sensors are gone. */
    if ((refusing & O2P_HB_RUNAWAY) != 0u && in->tip_valid && in->cell_valid) {
        return 0u;
    }
    /* THE DISCRIMINATOR (Fab's order 2026-09-11: "nope, no stand-down. 50
     * is safe if MCU die is < 40 C"): nothing else stands the blind path
     * down - the die gate is the stand-down, evaluated here for every law. */
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
    /* SENSOR BITS ARE LAW-AWARE, 2026-09-11 (Fab's orders: "fix that control
     * loop bullshit", "unattended loop: annotate and regulate (keep
     * <=80 C)", and the per-law blind rule - blind must require the
     * in-command loop's own control sensor to be invalid). Live that day,
     * twice: the operator armed 50.00 C attended with the tip sensor VALID
     * and only the TMP117 therm thresholds lost - SAFETY was the sole
     * refusal, and this step() fell through to blind_duty(): 50 % open loop
     * toward the ~76 C asymptote, the setpoint silently ignored while the
     * control sensor worked. The same discard threatened the stored tip
     * setpoint the moment its chamber went invalid. Both were the fallback
     * doing the opposite of its job: it exists for a board with NO control
     * quantity, not for a working loop with one redundant backstop down.
     *
     * So a sensor-unavailability bit outside this law's hard and wet masks
     * (hard_mask/law_wet_mask above) is an ANNOTATION, exactly like SUPPLY:
     * the loop REGULATES, bounded by whatever limits remain evaluable -
     * TIP_LIMIT (tightened to 80.00 C while SAFETY is annotated, per the
     * same order), DT_LIMIT, the ceiling, RUNAWAY. NO_TIP still refuses a
     * tip law outright (no control sensor, no loop - the founding
     * sensorless case, blind), NO_RH still refuses the RH law, and every
     * hard bit refuses as before. */
    const uint16_t refusing =
        (uint16_t)(block & (hard_mask | law_wet_mask(cfg, in)));
    if (refusing != 0u) {
        /* Zero the integrator rather than freezing it. Freezing would make the
         * loop slam to whatever it had wound up to the moment an interlock
         * cleared - the opposite of what you want after a fault. Restarting
         * from proportional-only is bumpless and slow, which is correct for a
         * plant nobody has measured. */
        st->integ = 0.0f;
        st->integ_floor = 0.0f;
        /* A refused cycle PAUSES the unreachable-margin detector while the
         * dew law is still the configured law: its seconds are not credited,
         * nothing already counted is lost, and the verdict survives. 0x0019
         * discarded the evidence here instead, and frequent refusals then
         * held a probe at the ceiling indefinitely (codex review of
         * 9eb3a34, finding 2). See O2P_HEATER_DEW_UNREACH_PAUSE_MAX_S. A
         * different law configured drops the evidence and the verdict. */
        if (dew_law_in_command(cfg, in)) {
            dew_detector_pause(st, now_s);
        } else {
            st->dew_prev_valid = false;
            st->dew_pinned = false;
            st->dew_recovered = false;
            st->dew_dwell_s = 0u;
            st->dew_clear_s = 0u;
            st->dew_unreachable = false;
            st->dew_paused = false;
        }
        const uint16_t duty = blind_duty(cfg, in, refusing);
        out->duty_x100 = duty;
        out->block = (uint16_t)((block | supply_note) |
                                ((duty != 0u) ? O2P_HB_BLIND : 0u));
        /* NOT the configured law: the blind fallback is a constant duty and
         * a refusal is no duty at all. Reporting either as the law in
         * command is what let a flat duty sitting on HEATER_MAX_DUTY be read
         * as a regulator settling. */
        out->law = (duty != 0u) ? O2P_HEATER_LAW_BLIND : O2P_HEATER_LAW_REFUSED;
        update_runaway(st, cfg, in, now_s, duty);
        return;
    }

    const float max_duty = (float)cfg->max_duty_x100;
    uint16_t duty;

    /* The gradient floor is in command only alongside the dew law, so its
     * integrator is cleared on every other path - the same bumpless
     * proportional-only re-entry the mode tag gives the laws that take turns.
     * It cannot use the mode tag itself: it does not take a turn, it runs
     * concurrently. See O2P_HEATER_FLOOR_DELTA_K100. */
    if (!dew_law_in_command(cfg, in)) {
        st->integ_floor = 0.0f;
        /* The unreachable verdict belongs to the dew law, and so does its
         * evidence. Another law in command moves the tip for reasons this
         * detector cannot interpret, so neither survives the hand-over. */
        st->dew_prev_valid = false;
        st->dew_pinned = false;
        st->dew_recovered = false;
        st->dew_dwell_s = 0u;
        st->dew_clear_s = 0u;
        st->dew_unreachable = false;
        st->dew_paused = false;
    }

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
        out->law = O2P_HEATER_LAW_TIP;
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
        out->law = O2P_HEATER_LAW_OPEN;
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
        out->law = O2P_HEATER_LAW_TIP_AUTO;
    } else if (dew_law_in_command(cfg, in)) {
        /* THE DEW-MARGIN LAW (FW 0x0013; see O2P_HEATER_DEW_MARGIN_K100).
         * Positive error means the cell side is short of margin - more duty.
         * The min() with the tip's room under its ceiling is "margin, up to
         * the 80 C tip cap": when the margin cannot be met, the loop holds
         * the tip at the ceiling instead of bouncing it off the clamp.
         *
         * The dew point is guaranteed evaluable here: rh and chamber invalid
         * are NO_RH/NO_CHAMBER, an unevaluable Magnus input is NO_RH
         * (interlocks()), and all three are in this law's wet mask, which
         * returned above. So is the tip, for the same reason via NO_TIP. */
        /* NO DEW POINT IS NOT A REFUSAL (FW 0x001B). NO_RH and NO_CHAMBER no
         * longer blind this law (law_wet_mask), so the dew point can be
         * missing here - the SHT45 de-creep, or a humidity the Magnus form
         * cannot take. Then the law withholds its demand, the detector
         * pauses, and the gradient floor below regulates alone. */
        float td_c100 = 0.0f;
        const bool have_td = in->rh_valid && in->chamber_valid &&
                             gas_dew_point_c100(in, &td_c100);
        const float margin_f = (float)in->t_cell_c100 - td_c100;

        if (!have_td) {
            /* No margin to judge: pause, never credit, never discard. */
            dew_detector_pause(st, now_s);
        } else {
            /* THE UNREACHABLE-MARGIN DETECTOR, ceiling-dwell form (see
             * O2P_HEATER_DEW_UNREACH_DWELL_S). Evaluated BEFORE the demand,
             * because its whole job is to decide whether this law makes one. */
            int32_t margin_i = (int32_t)(margin_f +
                                         (margin_f < 0.0f ? -0.5f : 0.5f));
            if (margin_i > 32767) {
                margin_i = 32767;
            } else if (margin_i < -32768) {
                margin_i = -32768;
            }
            /* Evidence resumes after a pause: a short one only stopped the
             * clock (dew_prev_valid is false, so its seconds are not credited);
             * one longer than the dwell discards what was counted before it. */
            if (st->dew_paused) {
                if ((uint32_t)(now_s - st->dew_pause_since_s) >
                    O2P_HEATER_DEW_UNREACH_PAUSE_MAX_S) {
                    st->dew_pinned = false;
                    st->dew_recovered = false;
                    st->dew_dwell_s = 0u;
                    st->dew_clear_s = 0u;
                }
                st->dew_paused = false;
            }
            /* Observed seconds since the previous dew-law cycle. The clock is
             * invalid after any refusal or other law, and a gap longer than the
             * caller's cadence contract is not observation: both discard the
             * evidence, exactly as the runaway detector does. */
            uint32_t since = 0u;
            if (st->dew_prev_valid) {
                since = (uint32_t)(now_s - st->dew_prev_s);
                if (since > O2P_HEATER_RUNAWAY_MAX_GAP_S) {
                    since = 0u;
                    st->dew_pinned = false;
                    st->dew_recovered = false;
                    st->dew_dwell_s = 0u;
                    st->dew_clear_s = 0u;
                }
            }
            st->dew_prev_s = now_s;
            st->dew_prev_valid = true;

            if (st->dew_unreachable) {
                const bool recovered =
                    margin_i >= (int32_t)O2P_HEATER_DEW_MARGIN_K100 +
                                    (int32_t)O2P_HEATER_DEW_UNREACH_CLEAR_HYST_K100;
                if (!recovered) {
                    st->dew_clear_s = 0u;
                } else if (st->dew_recovered &&
                           st->dew_clear_s < O2P_HEATER_DEW_UNREACH_CLEAR_HOLD_S) {
                    st->dew_clear_s = (uint16_t)(st->dew_clear_s + since);
                }
                st->dew_recovered = recovered;
                /* The retry compares the unsigned DIFFERENCE, so a wrap of now_s
                 * neither strands nor prematurely releases it - valid while the
                 * interval is under 2^31 s, which 6 h is. */
                if (st->dew_clear_s >= O2P_HEATER_DEW_UNREACH_CLEAR_HOLD_S ||
                    (uint32_t)(now_s - st->dew_retry_at_s) < 0x80000000u) {
                    st->dew_unreachable = false;
                    st->dew_pinned = false;
                    st->dew_recovered = false;
                    st->dew_dwell_s = 0u;
                    st->dew_clear_s = 0u;
                }
            } else {
                const bool pinned =
                    margin_i < (int32_t)O2P_HEATER_DEW_MARGIN_K100 &&
                    (int32_t)in->t_tip_c100 >=
                        dew_ceiling_c100(cfg, in) -
                        (int32_t)O2P_HEATER_DEW_UNREACH_BAND_K100;
                if (!pinned) {
                    st->dew_dwell_s = 0u;
                } else if (st->dew_pinned &&
                           st->dew_dwell_s < O2P_HEATER_DEW_UNREACH_DWELL_S) {
                    st->dew_dwell_s = (uint16_t)(st->dew_dwell_s + since);
                }
                st->dew_pinned = pinned;
                if (st->dew_dwell_s >= O2P_HEATER_DEW_UNREACH_DWELL_S) {
                    st->dew_unreachable = true;
                    st->dew_retry_at_s = now_s + O2P_HEATER_DEW_UNREACH_RETRY_S;
                    st->dew_pinned = false;
                    st->dew_recovered = false;
                    st->dew_dwell_s = 0u;
                    st->dew_clear_s = 0u;
                }
            }
        }

        const float margin_short = (float)O2P_HEATER_DEW_MARGIN_K100 -
                                   margin_f;
        const float tip_room = (float)(dew_ceiling_c100(cfg, in) -
                                       (int32_t)in->t_tip_c100);
        const float e = (margin_short < tip_room) ? margin_short : tip_room;
        const float kp = (float)O2P_HEATER_DEW_KP_X100 * 0.01f;
        if (tip_room < 0.0f && st->integ > -kp * tip_room) {
            /* ABOVE THE CEILING THE OUTPUT IS ZERO (Codex review of 4fe6b36,
             * finding 2). The min() limits the error, not the integral: one
             * wound up while the margin was binding kept driving 57 % at
             * 79.50 C with the ceiling error negative, into TIP_LIMIT.
             * Back-calculate instead - park the integral where p + integ is
             * exactly zero - so the ceiling is a bound, and re-entry below it
             * restarts from there rather than from the old wind-up. A mode
             * or session change zeroes it in pi_step() regardless. */
            st->integ = -kp * tip_room;
        }
        if (st->dew_unreachable || !have_td) {
            /* NO DEMAND, not a shutdown - whether the margin is unreachable
             * or there is no dew point to regulate against (FW 0x001B). The gradient floor below is
             * high-selected against this zero and IS achievable - it is
             * tip-referenced, so the dew point chasing the tip cannot defeat
             * it - which keeps the outward gradient that actually stops
             * condensation while we stop paying for a margin we cannot buy.
             *
             * The integrator is zeroed rather than frozen, and last_mode set
             * by hand since pi_step() is not the one doing it, so a return to
             * authority restarts from the proportional term, not an old
             * integral. That is NOT bumpless: the proportional term steps the
             * duty on re-entry (codex review of d7be806: ~2.4 % -> ~20 %). */
            st->integ = 0.0f;
            st->last_mode = O2P_HEATER_MODE_DEW;
            st->last_session = cfg->session;
            duty = 0u;
        } else {
            duty = pi_step(st, O2P_HEATER_MODE_DEW, cfg->session, e, kp,
                           (float)O2P_HEATER_DEW_KI_X100 * 0.01f,
                           max_duty);
        }

        /* THE GRADIENT FLOOR, HIGH-SELECTED (O2P_HEATER_FLOOR_DELTA_K100).
         *
         * Runs every cycle the dew law does, on its own integrator, and the
         * larger of the two demands is what the ring gets. Both are lower
         * bounds, so max() is the only combination that respects both: a
         * min(), or a precedence rule, would let one law turn the other
         * DOWN, and the whole reason this one exists is that the dew law can
         * be lied to into asking for nothing.
         *
         * THE SAME CEILING BINDS IT. The floor's setpoint is clamped to
         * O2P_HEATER_DEW_TIP_CEIL_C100 rather than allowed to ask for
         * cell + delta unconditionally: in a pile near the ceiling that sum
         * is above it, and a floor that drove through the ceiling would make
         * the 80.00 C clamp the control mechanism again - the argument at
         * O2P_HEATER_TIP_LIMIT_C100. Clamping the SETPOINT (rather than
         * back-calculating as the dew law must) is enough here because this
         * law's controlled quantity IS the tip: above the clamped setpoint
         * its own error is already negative, so it unwinds instead of
         * winding up. */
        int32_t floor_sp_c100 = (int32_t)in->t_cell_c100 +
                                (int32_t)O2P_HEATER_FLOOR_DELTA_K100;
        if (floor_sp_c100 > dew_ceiling_c100(cfg, in)) {
            floor_sp_c100 = dew_ceiling_c100(cfg, in);
        }
        const float e_floor = (float)(floor_sp_c100 -
                                      (int32_t)in->t_tip_c100);
        const uint16_t floor_duty =
            pi_core(&st->integ_floor, e_floor,
                    (float)O2P_HEATER_FLOOR_KP_X100 * 0.01f,
                    (float)O2P_HEATER_FLOOR_KI_X100 * 0.01f,
                    max_duty);
        if (floor_duty > duty) {
            duty = floor_duty;
        }
        out->law = (uint16_t)(O2P_HEATER_LAW_DEW |
                              (st->dew_unreachable
                                   ? O2P_HEATER_LAWF_DEW_UNREACHABLE : 0u) |
                              (!have_td ? O2P_HEATER_LAWF_DEW_NO_DEWPOINT : 0u));
    } else {
        /* Positive error means too humid, which means not enough heat. */
        const float e = (float)in->rh_x100 - (float)cfg->setpoint_x100;
        duty = pi_step(st, O2P_HEATER_MODE_RH, cfg->session, e,
                       (float)cfg->kp_x100 * 0.01f,
                       (float)cfg->ki_x100 * 0.01f,
                       max_duty);
        out->law = O2P_HEATER_LAW_RH;
    }

    out->duty_x100 = duty;
    /* Annotation only - see interlocks() and the law-aware gate above.
     * `block` is zero on the fully healthy path; on an annotated path it
     * carries whatever sensor bits the law in command merely reports (e.g.
     * SAFETY or NO_CHAMBER while a tip loop regulates, NO_TIP while the RH
     * loop regulates) and must stay VISIBLE so HEATER_BLOCK keeps telling
     * the whole truth while the loop drives - the same contract the SUPPLY
     * annotation serves. */
    out->block = (uint16_t)(supply_note | block);
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
        /* And HEATER_LAW must not keep naming the law this latch just
         * overruled (codex review of d7be806, finding 7). */
        out->law = O2P_HEATER_LAW_REFUSED;
    }
}
