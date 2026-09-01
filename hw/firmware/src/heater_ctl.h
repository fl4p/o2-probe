/* Membrane-heater control law and interlocks - portable, host-testable half.
 *
 * Everything here is arithmetic and decisions: no registers, no CMSIS, no
 * timer. heater.c owns the hardware. The split exists because this is the ONLY
 * part of the heater that can be validated before the probe ever meets
 * silicon, so it is the part that has to be testable.
 *
 * WHAT IS CONTROLLED, and why it is not a temperature.
 *
 * PLAN.md:294-297, verbatim: "primary loop regulates measured chamber RH
 * (SHT45, hold ~85-90 % - the actual controlled quantity: condensation margin
 * + the cell's 90 % continuous-RH spec)."
 *
 * Regulating relative humidity rather than a fixed temperature rise is the
 * whole design. PLAN.md:300-302: "+2 K gives only ~90-91 % RH on saturated
 * gas; 85 % needs ~3.1-3.7 K at 40-65 C - design the thermal path for a
 * 0-4 K dT range, not a fixed 2 K." A fixed offset that is right at 40 C is
 * wrong at 65 C, and the pile spans both.
 *
 * Heating the chamber lowers its relative humidity at constant absolute
 * humidity, so the loop is positive-acting: measured RH above setpoint asks
 * for more duty. That sign is what the monotonicity test pins down.
 *
 * THE PLANT GAIN IS UNKNOWN. THERMAL-BARRIER.md:5-9 gives 98 K/W (interval
 * 91-102, engineering bound 90-110 K/W) for the bare-PCB transverse path, and
 * :18 says plainly that this "is for PCB conduction only. It is not the
 * ring-to-ambient" path - which is the one that actually sets how many kelvin
 * a watt buys in wet pore gas. So the gains below are conservative starting
 * points, NOT design values, and they are exposed as holding registers
 * precisely because they cannot be known until the loop runs on hardware.
 */
#ifndef O2P_HEATER_CTL_H
#define O2P_HEATER_CTL_H

#include <stdbool.h>
#include <stdint.h>

/* Interlock bits. Any one of them set means duty is zero this cycle.
 *
 * They are a bitmask rather than a first-match reason code so that a buried
 * probe reporting "not heating" says everything that is wrong at once. Chasing
 * a refusal one cause at a time, five minutes per uplink, is not a diagnostic
 * procedure. Published in the diagnostic block as HEATER_BLOCK. */
enum {
    O2P_HB_NOT_COMPILED  = 1u << 0,  /* built with O2P_HEATER_ENABLE = 0 */
    O2P_HB_CONFIG_OFF    = 1u << 1,  /* HEATER_MAX_DUTY is zero */
    O2P_HB_SAFETY        = 1u << 2,  /* TMP117 therm-mode alert not armed */
    O2P_HB_NO_RH         = 1u << 3,  /* no fresh, unmasked SHT45 humidity */
    O2P_HB_NO_TIP        = 1u << 4,  /* no fresh TMP117 reading */
    O2P_HB_NO_CHAMBER    = 1u << 5,  /* no chamber temperature for the dT clamp */
    O2P_HB_TIP_LIMIT     = 1u << 6,  /* tip at/above the firmware absolute limit */
    O2P_HB_DT_LIMIT      = 1u << 7,  /* tip-minus-chamber at/above DT_MAX_K */
    O2P_HB_RUNAWAY       = 1u << 8,  /* latched: heat with no command */
    O2P_HB_SUPPLY        = 1u << 9,  /* rail fault - do not add 86 mA of load */
    O2P_HB_PIN_INTEGRITY = 1u << 10, /* TIM1 CH1N / PA7 assertion failed */
    O2P_HB_STALE         = 1u << 11, /* no decision recently; see heater.c */
};

/* Firmware's own absolute tip limit, independent of the TMP117's alert.
 *
 * DELIBERATELY BELOW the 85 C therm-mode threshold main.c programs into the
 * TMP117 (O2P_TIP_LIMIT_C100). Firmware backs off first; the hardware clamp is
 * the backstop for the case where firmware is the thing that failed. Two
 * mechanisms at the same threshold would be one mechanism.
 *
 * Hysteresis stops the clamp chattering at 1 Hz against a thermal plant whose
 * time constant is seconds. */
#define O2P_HEATER_TIP_LIMIT_C100  8000
#define O2P_HEATER_TIP_RELEASE_C100 7500

/* The dT clamp releases half a kelvin below DT_MAX_K, same reasoning. */
#define O2P_HEATER_DT_HYST_K100 50

/* Runaway: the tip is hot while we are commanding nothing.
 *
 * Cannot false-positive on a cold start, because at power-on the tip and the
 * chamber are the same temperature and dT is ~0 - the detector needs dT to
 * EXCEED the configured maximum by a further margin, sustained, with duty
 * commanded at zero throughout. The window rejects transients such as a probe
 * carried in a warm hand into cold air.
 *
 * The margin is above DT_MAX_K rather than above zero because a small standing
 * dT is expected: the TMP117 reads PCB copper on the heated island while the
 * SHT45 reads chamber gas, and PLAN.md:304-307 warns those two disagree by
 * design ("U10 measures PCB copper, but the 5 g ABS cell couples via three
 * pins and gas"). Only a difference larger than the loop is ever allowed to
 * command is evidence of uncommanded heat. */
#define O2P_HEATER_RUNAWAY_WINDOW_S 60u
#define O2P_HEATER_RUNAWAY_MARGIN_K100 200

/* Conservative default gains. Error is in 0.01 %RH, output in 0.01 % duty.
 *
 * kp = 2.00 means a 10 %RH error asks for 20 % duty; ki = 0.10 means the same
 * error integrates about 1 % of duty per second, reaching full scale in a
 * couple of minutes. Slow on purpose: a loop that cannot be tuned before it is
 * potted should err towards sluggish rather than towards overshooting into a
 * cell rated to 60 C.
 *
 * UNVERIFIED. These are not derived from a measured plant - see the header
 * comment on why no such plant model exists yet. */
#define O2P_HEATER_KP_X100_DEFAULT 200u
#define O2P_HEATER_KI_X100_DEFAULT 10u

typedef struct {
    uint16_t setpoint_x100;    /* target chamber RH, 0.01 %RH */
    uint16_t dt_max_k100;      /* tip-above-chamber clamp, 0.01 K */
    uint16_t max_duty_x100;    /* output clamp, 0.01 %; zero disables */
    uint16_t kp_x100;
    uint16_t ki_x100;          /* per second */
} o2p_heater_cfg_t;

typedef struct {
    bool     drive_possible;   /* heater hardware is under our control at all */
    bool     safety_armed;     /* o2p_tmp117_safety_armed() */
    bool     pin_integrity_ok; /* CC1NE clear and PA7 still analog */
    bool     rh_valid;
    uint16_t rh_x100;
    bool     tip_valid;
    int16_t  t_tip_c100;
    bool     chamber_valid;
    int16_t  t_chamber_c100;
    bool     supply_ok;
} o2p_heater_in_t;

typedef struct {
    float    integ;            /* integrator, carried in duty units */
    bool     runaway_latched;
    bool     zero_duty_timing;
    uint32_t zero_duty_since_s;
    bool     dt_clamped;       /* hysteresis latches */
    bool     tip_clamped;
} o2p_heater_state_t;

typedef struct {
    uint16_t duty_x100;
    uint16_t block;            /* O2P_HB_* ; zero means the loop is driving */
} o2p_heater_out_t;

void o2p_heater_ctl_reset(o2p_heater_state_t *st);

/* One 1 Hz step. `now_s` is a monotonic seconds counter used only for the
 * runaway window; it may wrap.
 *
 * Guarantees the tests pin down: any interlock forces duty zero; an input that
 * cannot be evaluated is an interlock, never a mid-range duty; and the
 * integrator cannot accumulate while the output is clamped. */
void o2p_heater_ctl_step(o2p_heater_state_t *st,
                         const o2p_heater_cfg_t *cfg,
                         const o2p_heater_in_t *in,
                         uint32_t now_s,
                         o2p_heater_out_t *out);

#endif /* O2P_HEATER_CTL_H */
