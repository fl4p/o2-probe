#include "heater_ctl.h"

#include <stddef.h>

void o2p_heater_ctl_reset(o2p_heater_state_t *st)
{
    if (st == NULL) {
        return;
    }
    st->integ = 0.0f;
    st->runaway_latched = false;
    st->zero_duty_timing = false;
    st->zero_duty_since_s = 0u;
    st->dt_clamped = false;
    st->tip_clamped = false;
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
    if (!in->safety_armed) {
        /* The TMP117's therm-mode alert is the hardware cutoff. Driving 1 W
         * into the membrane while the only autonomous limit is unprogrammed
         * is precisely what DESIGN.md:47-51 refuses to credit. */
        block |= O2P_HB_SAFETY;
    }
    if (!in->rh_valid) {
        /* No humidity means no controlled quantity. Note this also covers the
         * SHT45 de-creep window: main.c marks the chamber invalid while the
         * element is deliberately warm, and a loop that trusted that reading
         * would see the pulse as the pile drying out and back off. */
        block |= O2P_HB_NO_RH;
    }
    if (!in->tip_valid) {
        block |= O2P_HB_NO_TIP;
    }
    if (!in->chamber_valid) {
        /* Without chamber temperature there is no dT to clamp against, so the
         * 0-4 K design envelope cannot be enforced. Refuse rather than heat
         * open-loop on temperature. */
        block |= O2P_HB_NO_CHAMBER;
    }
    if (!in->supply_ok) {
        block |= O2P_HB_SUPPLY;
    }
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

    /* dT clamp, with hysteresis, against the configured 0-4 K envelope. */
    if (in->tip_valid && in->chamber_valid) {
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
 * LATCHES UNTIL RESET, on purpose. A FET that conducts without being asked, or
 * a gate node driven by something else, is a hardware failure - and the
 * firmware that just discovered it cannot control the heater is not the thing
 * that should decide the fault has cleared. Auto-clearing would re-arm 1 W
 * against a membrane every time the tip cooled. The cost is that a false
 * positive disables heating until the next reset; it is reported through
 * HEATER_BLOCK, and the safe direction is the one that does not cook the cell.
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
    if (duty_x100 != 0u) {
        st->zero_duty_timing = false;
        return;
    }
    if (!st->zero_duty_timing) {
        st->zero_duty_timing = true;
        st->zero_duty_since_s = now_s;
        return;
    }
    /* Unsigned subtraction, so a wrap of now_s is harmless. */
    if ((uint32_t)(now_s - st->zero_duty_since_s) < O2P_HEATER_RUNAWAY_WINDOW_S) {
        return;
    }
    if (!in->tip_valid || !in->chamber_valid) {
        return;   /* cannot evaluate; not evidence either way */
    }
    int32_t dt = (int32_t)in->t_tip_c100 - (int32_t)in->t_chamber_c100;
    if (dt > (int32_t)cfg->dt_max_k100 + O2P_HEATER_RUNAWAY_MARGIN_K100) {
        st->runaway_latched = true;
    }
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
    if (block != 0u) {
        /* Zero the integrator rather than freezing it. Freezing would make the
         * loop slam to whatever it had wound up to the moment an interlock
         * cleared - the opposite of what you want after a fault. Restarting
         * from proportional-only is bumpless and slow, which is correct for a
         * plant nobody has measured. */
        st->integ = 0.0f;
        out->duty_x100 = 0u;
        out->block = block;
        update_runaway(st, cfg, in, now_s, 0u);
        return;
    }

    const float max_duty = (float)cfg->max_duty_x100;
    const float kp = (float)cfg->kp_x100 * 0.01f;
    const float ki = (float)cfg->ki_x100 * 0.01f;

    /* Positive error means too humid, which means not enough heat. */
    const float e = (float)in->rh_x100 - (float)cfg->setpoint_x100;
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

    out->duty_x100 = (uint16_t)(u + 0.5f);
    out->block = 0u;

    update_runaway(st, cfg, in, now_s, out->duty_x100);
    if (st->runaway_latched) {
        /* Latched this very cycle: do not wait a cycle to act on it. */
        out->duty_x100 = 0u;
        out->block = O2P_HB_RUNAWAY;
        st->integ = 0.0f;
    }
}
