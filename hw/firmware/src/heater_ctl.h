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
    /* INERT on Rev A hardware: tip-minus-chamber is structurally ~0 because
     * U10 and U12 are one thermal node. Retained because the bit numbering is
     * published and because a revision with a thermally separated sensor - the
     * ring PCB's dropped temperature sensor - would make it live again. Do not
     * count it as protection; see FAB-READINESS.md. */
    O2P_HB_DT_LIMIT      = 1u << 7,  /* tip-minus-chamber at/above DT_MAX_K */
    O2P_HB_RUNAWAY       = 1u << 8,  /* latched: heat with no command */
    O2P_HB_SUPPLY        = 1u << 9,  /* rail fault - do not add 86 mA of load */
    O2P_HB_PIN_INTEGRITY = 1u << 10, /* TIM1 CH1N / PA7 assertion failed */
    O2P_HB_STALE         = 1u << 11, /* no decision recently; see heater.c */
    /* No consent to AUTONOMOUS heating: the RH loop wanted to drive and
     * HEATER_RH_CONSENT (0x0048) does not hold the magic. Never raised while
     * the bench override is armed - that path carries its own authorisation
     * and an operator. */
    O2P_HB_NO_CONSENT    = 1u << 12,
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
/* 82.00 C, raised from 80.00 on 2026-09-08.
 *
 * The clamp has to sit ABOVE the highest setpoint anyone is meant to command,
 * or it becomes the control mechanism instead of the backstop. The stated
 * experiment is to hold the tip at 80.00 C and compare against an external
 * 80.00 C bath, and with the clamp at 80.00 the loop could only be given
 * 79.00 - so the internal run topped out a kelvin below the external one and
 * the independent variable was not matched. Found by review 2026-09-08.
 *
 * Still separated from the TMP117's 85 C therm-mode threshold by 3 K, so
 * firmware continues to back off first and the hardware cutoff remains the
 * backstop for the case where firmware is the thing that failed. Two
 * mechanisms at the same threshold would be one mechanism. */
#define O2P_HEATER_TIP_LIMIT_C100  8200
#define O2P_HEATER_TIP_RELEASE_C100 7700

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
/* The longest gap between two calls that may still be treated as continuous
 * observation. This is the CALLER'S CADENCE CONTRACT, not a tuning knob:
 * o2p_heater_ctl_step() runs once per 1 s cycle, so anything beyond a few
 * seconds means the detector was not watching and the evidence it holds
 * describes a different situation. Both failure modes are real - too small and
 * evidence never accumulates at the true cadence, too large and a sparse
 * glimpse across a blind interval is credited as a sustained event - and
 * neither can be fixed inside the detector, because it cannot tell sparse
 * sampling of a real event from isolated glimpses without knowing the rate. */
#define O2P_HEATER_RUNAWAY_MAX_GAP_S 5u
/* Commanded duty at or below this still counts as "we are not asking for
 * heat", in 0.01 %. Exactly-zero was too strict: a FET stuck fully on while
 * the loop happens to be asking for a few percent produced heat nobody
 * commanded, and every call reset the evidence because the duty was nonzero.
 * Saturated compost holds the humidity error positive indefinitely, so the
 * loop need never return to exactly zero.
 *
 * The genuinely dangerous case was already covered from the other side: heat
 * that pushes the tip past dt_max trips interlocks(), which zeroes the duty
 * and then arms this detector. What this threshold adds is the case where the
 * thermal outcome stays inside the safe envelope but the FET is stuck anyway -
 * broken humidity control and wasted power rather than a hazard. Found by
 * review 2026-09-08. */
#define O2P_HEATER_RUNAWAY_IDLE_DUTY_X100 500u
#define O2P_HEATER_RUNAWAY_MARGIN_K100 200

/* Runaway threshold on tip-minus-DIE.
 *
 * The chamber-referenced test above cannot see the failure it was written for.
 * A stuck-on FET heats the whole tip assembly, and the SHT45 sits 6.6 mm from
 * the TMP117 on the same copper, so both rise together: measured 2026-09-04
 * across a 30 K excursion, |tip - chamber| never exceeded 0.17 K at ANY duty
 * from 0 to 100 %. Against a 4 K limit it can never latch.
 *
 * The die is across the transverse thermal barrier and does not track the tip.
 * Measured the same evening: tip - die swings from about -2.2 K at rest to
 * +2.1 K at only 4 % duty, and the tip reached 56 C while the die stayed near
 * 28 C. A stuck-on FET is therefore a tens-of-kelvin signal on this channel.
 *
 * 10.00 K is PROVISIONAL and chosen on bench evidence: the widest legitimate
 * zero-duty excursion observed was +3.0 K (thermal history plus the die's
 * 0.29 K/LSB dither), so this is about 3.4x that, and it catches any stuck
 * duty above roughly 12 % in still air. In a pile the coupling is far tighter
 * and the same fault produces a smaller rise - PILE-THERMAL-TEST.md is the
 * measurement that should replace this number. Until then it is a detector
 * that can see the failure, which is strictly better than one that cannot. */
#define O2P_HEATER_RUNAWAY_DIE_K100 1000

/* Release hysteresis below BOTH runaway thresholds, in 0.01 K.
 *
 * Sized against the noise it has to reject, not against any event: one scaled
 * die count is 100 K over the 347-count calibration span, 0.288 K (mcu_adc.c,
 * die_temp.h), so 1.00 K is 3.47 counts - comfortably above adjacent-count
 * dither. THAT IS AN ARGUMENT FROM THE LSB, NOT A MEASUREMENT: the die is
 * converted each cycle without temporal averaging, against a separately
 * sampled VDDA, and its 1 Hz noise amplitude has never been recorded. Whether
 * a reference sitting on its threshold can chatter the release is therefore
 * conditional on that amplitude, and the full-window dwell is what actually
 * stands between dither and a release. It must also leave the release point
 * ABOVE the widest legitimate zero-duty excursion (+3.0 K, see
 * O2P_HEATER_RUNAWAY_DIE_K100), or a probe back at rest could never release;
 * 9.00 K is. Pinned by test_die_runaway_threshold_brackets_the_measured_evidence.
 *
 * Why a release exists at all is in update_runaway() (heater_ctl.c): on
 * 2026-09-10 an 80 C bath produced the die-referenced signature with no sign
 * of the FET conducting, and latched-until-reset disabled the heater. */
#define O2P_HEATER_RUNAWAY_RELEASE_HYST_K100 100

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

/* Tip-loop defaults. Error is in 0.01 K, output in 0.01 % duty, so kp = 50
 * means a 2 K shortfall asks for full duty and ki = 0.5 means a 1 K standing
 * error integrates about 0.5 % of duty per second.
 *
 * Chosen to saturate early and integrate slowly, which suits a plant that is
 * ~1 W into a thermal mass with a time constant of seconds to tens of
 * seconds: overshoot costs little because the absolute clamp is a kelvin
 * above any legal setpoint, while a sluggish approach costs only bench time.
 * PROVISIONAL, like every other number about this plant - and unlike the RH
 * gains these are volatile registers, so they can be moved without a reflash. */
#define O2P_HEATER_TEST_KP_X100_DEFAULT 5000u
#define O2P_HEATER_TEST_KI_X100_DEFAULT 50u


typedef struct {
    uint16_t setpoint_x100;    /* target chamber RH, 0.01 %RH */
    uint16_t dt_max_k100;      /* tip-above-chamber clamp, 0.01 K */
    uint16_t max_duty_x100;    /* output clamp, 0.01 %; zero disables */
    uint16_t kp_x100;
    uint16_t ki_x100;          /* per second */
    /* BENCH OVERRIDE (register 0x0060). Drives `test_duty_x100` open-loop and
     * suppresses exactly three interlocks: NO_RH, NO_CHAMBER and DT_LIMIT.
     *
     * Those three and no others because they are the interlocks that protect
     * the CONTROLLED QUANTITY, not the hardware. The loop regulates chamber
     * RH, so without humidity it has no error signal and without a chamber
     * temperature it cannot honour the 0-4 K envelope - both are refusals to
     * control, and an open-loop duty is not controlling anything. dT is that
     * envelope itself, and the envelope exists to hold the cell near ambient
     * for a dew-point loop; a deliberate thermal characterisation is the one
     * case where exceeding it is the experiment.
     *
     * Every interlock that answers to the hardware stays live: SAFETY,
     * NO_TIP, TIP_LIMIT, SUPPLY, RUNAWAY, PIN_INTEGRITY, NOT_COMPILED, and
     * max_duty_x100 which still clamps the commanded value and still means
     * "off" at zero. */
    bool     test_override;
    uint16_t test_duty_x100;   /* 0.01 %, clamped to max_duty_x100 */
    /* HEATER_RH_CONSENT holds its magic. Gates the RH loop ONLY.
     *
     * The heater used to be compiled out, so O2P_HB_NOT_COMPILED refused
     * every path whatever the stored configuration said. Once the ring is
     * compiled in, a nonzero heater_max_duty_x100 in flash is on its own
     * enough to start an unvalidated loop on a buried probe with nobody
     * present, and migrations carry that maximum forward by design. This is
     * the consent that replaces the compile flag's guarantee. */
    bool     rh_consent;
    /* Increments on every 0 -> 1 arm of the bench override. Only equality
     * between consecutive cycles is used, so wrapping is harmless. */
    uint8_t  session;
    /* TIP TEMPERATURE SETPOINT MODE. When test_tip_sp_valid is set, the
     * override closes a PI loop on tip temperature instead of commanding
     * test_duty_x100 open loop.
     *
     * This exists because the alternative is not temperature control at all.
     * Nothing in this firmware regulates a temperature: the only loop is on
     * chamber RH, and the 80.00/75.00 C pair is the absolute CLAMP with its
     * anti-chatter hysteresis. Driving open loop against that clamp yields a
     * mean near 77.5 C with +/-2.5 K of sawtooth, and reaches it by bouncing
     * a protection device off its limits once per thermal time constant.
     *
     * With a setpoint bounded below the clamp, the clamp goes back to being
     * a backstop: it firing at all means the loop failed. */
    bool     test_tip_sp_valid;
    int16_t  test_tip_sp_c100;
    /* Gains for the TIP loop only. The RH loop's kp/ki above are in %RH and
     * do not transfer - error here is in 0.01 K. */
    uint16_t test_kp_x100;
    uint16_t test_ki_x100;
    /* PERSISTENT TIP SETPOINT MODE (registers 0x0049 and 0x004A), the flash-backed
     * counterpart of the volatile block above.
     *
     * Precedence is override > persistent tip > RH, and it is not arbitrary:
     * an armed override means an operator is standing at the bench right now,
     * and their intent outranks anything a previous session committed to
     * flash.
     *
     * WHAT THIS MODE SUPPRESSES, and it is one interlock rather than the
     * override's three. NO_RH only: a temperature loop genuinely has no use
     * for humidity, and refusing to hold a commanded temperature because the
     * SHT45 is in its de-creep window would be a refusal with no reason
     * behind it.
     *
     * NO_CHAMBER and DT_LIMIT stay LIVE, unlike under the override. The
     * override suppresses them because exceeding the 0-4 K envelope IS the
     * experiment and an operator is present to own that. Here nobody is
     * present, so the envelope keeps its meaning. On Rev A this costs
     * nothing - the dT clamp is structurally inert, tip and chamber being one
     * thermal node - but on a revision with a thermally separated sensor it
     * is the difference between a loop that holds 80 C in a pile and one that
     * refuses to. Refusing is correct: holding a tip tens of kelvin above the
     * chamber with nobody watching is the exact thing the envelope exists to
     * prevent. */
    bool     tip_consent;
    bool     tip_sp_valid;
    int16_t  tip_sp_c100;
    /* No gains of its own: it uses test_kp_x100/test_ki_x100 above. The flash
     * record had six spare bytes and the setpoint plus its consent took four;
     * see O2P_REG_HEATER_TIP_CONSENT for why the target and the authorisation
     * are the two things that had to survive a reset. */
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
    /* The chamber temperature was MEASURED this cycle rather than bridged from
     * the cache. chamber_valid alone admits a cached value (main.c), which is
     * right for the dT clamp and for latching and wrong for EXONERATING a
     * latched runaway: release requires both. A zero-initialised caller gets
     * "not fresh", which can only delay a release. */
    bool     chamber_fresh;
    /* MCU die, o2p_mcu_adc_read_die_c100(). The ONLY sensor on this board
     * thermally separated from the tip - U10 and U12 sit 6.6 mm apart on the
     * same copper and cannot disagree. Used for runaway detection only; it is
     * +/-5 C absolute, which is useless for a 4 K clamp but irrelevant against
     * the tens of kelvin a stuck-on FET produces. */
    bool     die_valid;
    int16_t  t_die_c100;
    bool     supply_ok;
} o2p_heater_in_t;

typedef struct {
    float    integ;            /* integrator, carried in duty units */
    bool     runaway_latched;
    bool     zero_duty_timing;
    uint32_t zero_duty_since_s;
    /* Seconds of OBSERVED, valid, uncommanded-heat evidence. Not elapsed time
     * and not a timestamp difference: only intervals the detector actually
     * looked at are counted, so a gap in sampling cannot be credited as if
     * the condition had held through it. */
    uint16_t runaway_evidence_s;
    /* Seconds of observed evidence, while LATCHED, that the signature has
     * cleared: every reference valid, and each below its threshold by
     * O2P_HEATER_RUNAWAY_RELEASE_HYST_K100. Counted by the same rules as
     * runaway_evidence_s, and reset by any hot or hysteresis-band sample, any
     * gap longer than O2P_HEATER_RUNAWAY_MAX_GAP_S, and any lost reference. */
    uint16_t runaway_clear_s;
    bool     dt_clamped;       /* hysteresis latches */
    bool     tip_clamped;
    /* Which loop produced the current integrator, so that switching between
     * them cannot inherit a wound-up integral whose units and plant are both
     * different. See O2P_HEATER_MODE_*. */
    uint8_t  last_mode;
    /* Which override session the integrator belongs to. A disarm and re-arm
     * served between two 1 Hz decisions changes neither the mode nor any
     * input, so without this a new bench run inherits the last one's wind-up. */
    uint8_t  last_session;
} o2p_heater_state_t;

enum {
    O2P_HEATER_MODE_RH   = 0u,  /* the shipped humidity loop */
    O2P_HEATER_MODE_OPEN = 1u,  /* override, open-loop duty */
    O2P_HEATER_MODE_TIP  = 2u,  /* override, tip-temperature loop */
    /* The PERSISTENT tip loop. A distinct tag from O2P_HEATER_MODE_TIP even
     * though the control law is identical, because pi_step() resets the
     * integrator on a mode change and these two modes have different gains
     * and different authorisation. Sliding between them with a wound-up
     * integral would carry a bench run's history into an unattended one. */
    O2P_HEATER_MODE_TIP_AUTO = 3u,
};

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
