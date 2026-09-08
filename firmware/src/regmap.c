#include "regmap.h"
#include "faults.h"
#include "heater_ctl.h"
#include "o2.h"

#include <stddef.h>
#include <string.h>

/* Default Modbus address. 1 and 2 are the two Truebner SMT100 soil probes
 * already on this cable (tech/RS485-LS-SMT100.md:263-264), so 3 is the first
 * free unicast address. Do not "helpfully" default to 1. */
#define O2P_DEFAULT_SLAVE_ADDR 3u

void o2p_config_defaults(o2p_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cfg->slave_addr = O2P_DEFAULT_SLAVE_ADDR;
    cfg->baud_code = O2P_BAUD_9600;
    cfg->parity_code = O2P_PARITY_EVEN;   /* the bus is 8E1 */
    cfg->rh_setpoint_x100 = 8500u;        /* 85 %RH, PLAN.md:294-296 */
    cfg->dt_max_k_x100 = 400u;            /* 4 K, the designed thermal range */
    cfg->heater_pwm_hz = 1000u;
    /* Starting points, not tuned values - the plant gain is unmeasured. */
    cfg->heater_kp_x100 = O2P_HEATER_KP_X100_DEFAULT;
    cfg->heater_ki_x100 = O2P_HEATER_KI_X100_DEFAULT;
    /* No calibration by default. o2.c refuses to convert with this, and the
     * sampler substitutes the datasheet nominal and raises CAL_DEFAULT - so a
     * fresh board reports low-confidence data rather than nothing, and says
     * so. */
    cfg->cal_air_na = 0;
    /* No zero point either. Zero here means "not measured", and it is also
     * the correct arithmetic identity for that: the law degrades exactly to
     * the air-point-only behaviour, so an uncalibrated probe is not silently
     * given a zero correction it never had. */
    cfg->cal_zero_na = 0;
    cfg->cal_temp_c100 = 2500;
    /* 0 = no compensation applied. DS-0637 Issue 2 DOES publish an output-vs-
     * temperature curve, but no coefficient, and a slope eyeballed off a plot
     * is not a sourced number - so the default stays 0 until the curve is
     * digitised. (This said "SGX publishes no curve for this part", which was
     * true of Issue 1 only; corrected 2026-09-08.) See o2.h O2P_TEMPCO_DEFAULT. */
    cfg->tempco_ppm_per_k = 0;
    cfg->sht_pulse_interval_h = 8u;       /* PLAN.md:312, every 6-12 h */
    /* Heater loop. max_duty of zero means the loop is OFF by configuration as
     * well as by the compile guard: two independent switches, so enabling the
     * heater is never a single edit. See heater.h for the bench prerequisites.
     */
    cfg->heater_max_duty_x100 = 0u;
}

bool o2p_config_valid(const o2p_config_t *cfg)
{
    if (cfg == NULL) {
        return false;
    }
    if (cfg->slave_addr < O2P_MB_ADDR_MIN || cfg->slave_addr > O2P_MB_ADDR_MAX) {
        return false;
    }
    if (cfg->baud_code > O2P_BAUD_MAX_CODE) {
        return false;
    }
    if (cfg->parity_code > O2P_PARITY_EVEN) {
        return false;
    }
    if (cfg->rh_setpoint_x100 > 10000u) {
        return false;
    }
    /* A setpoint above the cell's 90 %RH continuous rating defeats the whole
     * point of the heater, and one below ~50 % asks for a temperature rise the
     * thermal path cannot deliver and would cook the cell trying. */
    if (cfg->rh_setpoint_x100 > 9000u || cfg->rh_setpoint_x100 < 5000u) {
        return false;
    }
    if (cfg->dt_max_k_x100 > 400u) {   /* the path is designed for 0-4 K */
        return false;
    }
    if (cfg->heater_max_duty_x100 > 10000u) {
        return false;
    }
    if (cfg->heater_pwm_hz < 50u || cfg->heater_pwm_hz > 20000u) {
        return false;
    }
    /* Gains are bounded, not merely non-negative. The ceiling is what stops a
     * fat-fingered write turning a 1 Hz PI into a bang-bang controller on a
     * 1 W heater against a membrane; kp = 100.00 already saturates the duty
     * clamp on a 1 %RH error. Zero is allowed - kp = 0 with ki > 0 is a pure
     * integrator, which is a legitimate thing to want on a slow thermal
     * plant, and both zero simply means the loop never asks for heat. */
    if (cfg->heater_kp_x100 > 10000u || cfg->heater_ki_x100 > 10000u) {
        return false;
    }
    /* Zero means "never calibrated", which is legal. Any other value must be
     * a physically plausible air point.
     *
     * Rejecting only negatives was a false-anoxia hole: writing the HI and LO
     * words of an intended 70000 nA in the wrong order yields 0x11700001 =
     * 292552705 nA, so K becomes 1.24e9 and every real reading converts to
     * 0.0056 %vol - which encodes as 0.01 %vol with NEITHER CAL_DEFAULT nor
     * ADC_RANGE set. A buried probe would report a hard anoxic pile, in
     * range, with a clean fault word. Enforcing the bounds here also forces
     * HI and LO to be written together in one FC16, because a half-written
     * value cannot pass. */
    if (cfg->cal_air_na != 0 && !o2p_cal_air_plausible(cfg->cal_air_na)) {
        return false;
    }
    /* The zero has no "0 means never set" escape, because 0 is inside its
     * plausible window already - a cell with no measured zero and a cell whose
     * measured zero is genuinely 0 nA are the same arithmetic. So this is an
     * unconditional bound, and it is checked HERE as well as in
     * o2p_calibrate_air() for the reason the air point exists to remember: a
     * Modbus write is a second path that can set a calibration, and only the
     * first one used to check.
     *
     * The same swapped-halves failure applies. Writing an intended -1200 nA as
     * 0xFB50 0xFFFF instead of 0xFFFF 0xFB50 gives -77 856 769 nA, which would
     * make the net air point negative and, unbounded, would drive every
     * reading to a saturated 1.0 fraction. Bounding it here also forces HI and
     * LO to be written together in one FC16, because a half-written value
     * cannot pass. */
    if (!o2p_cal_zero_plausible(cfg->cal_zero_na)) {
        return false;
    }
    /* The temperature correction's two constants. Unbounded until 2026-09-08,
     * when a review built a legal config that returned 4.503 %vol for a true
     * 5.000 % with a clean fault word. Both bounds and the worked cases are in
     * o2.h. The short version, corrected 2026-09-08: the tempco ceiling is a
     * PROVISIONAL corruption and gross-implausibility screen, not an accuracy
     * certificate - a plausible-but-wrong coefficient passes it and still
     * moves a reading past the decision tolerance. What refuses a collapsed
     * correction is the physics-justified gain window in o2.c, and what would
     * bound accuracy is calibration-quality data the firmware does not yet
     * record (budget doc section 14). */
    if (!o2p_tempco_plausible(cfg->tempco_ppm_per_k)) {
        return false;
    }
    if (!o2p_cal_temp_plausible(cfg->cal_temp_c100)) {
        return false;
    }
    if (cfg->sht_pulse_interval_h == 0u || cfg->sht_pulse_interval_h > 168u) {
        return false;
    }
    return true;
}

uint16_t o2p_config_crc(const o2p_config_t *cfg)
{
    /* Reuse the Modbus CRC so there is one checksum implementation to test.
     * The struct is memset to zero before every field is assigned, so its
     * padding is deterministic and safe to hash. */
    return o2p_mb_crc16((const uint8_t *)cfg, sizeof(*cfg));
}

void o2p_snapshot_reset(o2p_snapshot_t *s)
{
    /* Measurement channels start invalid. Counters and identity fields are
     * NOT reset here - they are cumulative or constant, and the sampler
     * rewrites them unconditionally every cycle. */
    s->o2_comp = O2P_U16_INVALID;
    s->o2_raw = O2P_I16_INVALID;
    s->t_tip = O2P_I16_INVALID;
    s->t_chamber = O2P_I16_INVALID;
    s->rh_chamber = O2P_U16_INVALID;
    s->dew_margin_x100 = O2P_I16_INVALID;
    s->exp_data = O2P_U16_INVALID;
    /* 0xFFFF, not 0. Zero is a perfectly possible real reading for every one
     * of these - 0 mV on a collapsed rail, an all-zero LMP91000 register image
     * after a reset - so publishing zero for "not measured" is exactly the
     * plausible-looking failure this file exists to prevent. 65.535 V is not
     * a value any of these channels can reach.
     *
     * pressure_hpa is the deliberate exception: 0 is its documented value for
     * the DNP BMP390 footprint, which is a fact about the board rather than a
     * failed measurement. */
    s->vref_mv = O2P_U16_INVALID;
    s->va_mv = O2P_U16_INVALID;
    s->vin_mv = O2P_U16_INVALID;
    s->afe_vout_mv = O2P_U16_INVALID;
    s->lmp_readback = O2P_U16_INVALID;
    s->pressure_hpa = 0u;
}

void o2p_regmap_init(o2p_regmap_t *rm)
{
    memset(rm, 0, sizeof(*rm));
    o2p_config_defaults(&rm->cfg);
    for (unsigned i = 0; i < 2u; i++) {
        o2p_snapshot_t *s = &rm->buf[i];
        /* Before the first sample completes, every channel must read invalid.
         * A zeroed snapshot would publish 0.00 %vol, 0.00 C and no faults -
         * a fully plausible anoxic pile - for as long as the first conversion
         * takes, and forever if it never completes. */
        o2p_snapshot_reset(s);
        s->faults = O2P_F_SETTLING | O2P_F_HEATER_DISABLED;
        s->reset_cause = 0u;
    }
    rm->live = 0u;
}

o2p_snapshot_t *o2p_regmap_staging(o2p_regmap_t *rm)
{
    return &rm->buf[rm->live ^ 1u];
}

void o2p_regmap_publish(o2p_regmap_t *rm)
{
    /* Single aligned byte write; readers see either the old or the new index,
     * never a mixture. Both sides run in the main loop today, but the flip
     * keeps this correct if the transport ever moves into an interrupt. */
    rm->live ^= 1u;
}

const o2p_snapshot_t *o2p_regmap_live(const o2p_regmap_t *rm)
{
    return &rm->buf[rm->live];
}

/* ------------------------------------------------------------------ reads */

static bool in_block(uint16_t addr, uint16_t count, uint16_t base, uint16_t n)
{
    return addr >= base && (uint32_t)addr + count <= (uint32_t)base + n;
}

static uint16_t read_primary(const o2p_snapshot_t *s, uint16_t a)
{
    switch (a) {
    case O2P_REG_O2_COMP:     return s->o2_comp;
    case O2P_REG_O2_RAW:      return (uint16_t)s->o2_raw;
    case O2P_REG_T_TIP:       return (uint16_t)s->t_tip;
    case O2P_REG_T_CHAMBER:   return (uint16_t)s->t_chamber;
    case O2P_REG_RH_CHAMBER:  return s->rh_chamber;
    case O2P_REG_HEATER_DUTY: return s->heater_duty;
    case O2P_REG_FAULTS:      return s->faults;
    default:                  return s->settle_s;
    }
}

static uint16_t read_diag(const o2p_snapshot_t *s, uint16_t a)
{
    switch (a) {
    case O2P_REG_VREF_MON_MV:   return s->vref_mv;
    case O2P_REG_VA_MON_MV:     return s->va_mv;
    case O2P_REG_VIN_MON_MV:    return s->vin_mv;
    case O2P_REG_AFE_VOUT_MV:   return s->afe_vout_mv;
    case O2P_REG_DEW_MARGIN:    return (uint16_t)s->dew_margin_x100;
    case O2P_REG_PRESSURE_HPA:  return s->pressure_hpa;
    case O2P_REG_UPTIME_HI:     return (uint16_t)(s->uptime_s >> 16);
    case O2P_REG_UPTIME_LO:     return (uint16_t)(s->uptime_s & 0xFFFFu);
    case O2P_REG_FW_VERSION:    return O2P_FW_VERSION;
    case O2P_REG_HW_REV:        return O2P_HW_REV;
    case O2P_REG_RESET_CAUSE:   return s->reset_cause;
    case O2P_REG_LMP_READBACK:  return s->lmp_readback;
    case O2P_REG_MB_CRC_ERRS:   return s->mb_crc_errs;
    case O2P_REG_MB_FRAME_ERRS: return s->mb_frame_errs;
    case O2P_REG_I2C_ERRS:      return s->i2c_errs;
    case O2P_REG_EXP_DATA:      return s->exp_data;
    case O2P_REG_SETTLE_RESTARTS: return s->settle_restarts;
    default:                    return s->sample_seq;
    }
}

static uint16_t read_config(const o2p_regmap_t *rm, uint16_t a)
{
    const o2p_config_t *c = &rm->cfg;
    switch (a) {
    case O2P_REG_SLAVE_ADDR:      return c->slave_addr;
    case O2P_REG_BAUD_CODE:       return c->baud_code;
    case O2P_REG_PARITY_CODE:     return c->parity_code;
    case O2P_REG_RH_SETPOINT:     return c->rh_setpoint_x100;
    case O2P_REG_DT_MAX_K:        return c->dt_max_k_x100;
    case O2P_REG_HEATER_MAX_DUTY: return c->heater_max_duty_x100;
    case O2P_REG_HEATER_PWM_HZ:   return c->heater_pwm_hz;
    case O2P_REG_HEATER_KP:       return c->heater_kp_x100;
    case O2P_REG_HEATER_KI:       return c->heater_ki_x100;
    case O2P_REG_CAL_AIR_NA_HI:   return (uint16_t)((uint32_t)c->cal_air_na >> 16);
    case O2P_REG_CAL_AIR_NA_LO:   return (uint16_t)((uint32_t)c->cal_air_na & 0xFFFFu);
    case O2P_REG_CAL_ZERO_NA_HI:  return (uint16_t)((uint32_t)c->cal_zero_na >> 16);
    case O2P_REG_CAL_ZERO_NA_LO:  return (uint16_t)((uint32_t)c->cal_zero_na & 0xFFFFu);
    case O2P_REG_CAL_TEMP_C100:   return (uint16_t)c->cal_temp_c100;
    case O2P_REG_TEMPCO_PPM_K:    return (uint16_t)c->tempco_ppm_per_k;
    case O2P_REG_SHT_PULSE_H:     return c->sht_pulse_interval_h;
    /* The trigger registers read back as zero: they are edges, not state.
     * Reading a 1 would suggest a calibration is pending when it is not. */
    case O2P_REG_SHT_PULSE_TRIG:  return 0u;
    case O2P_REG_CAL_TRIGGER:     return 0u;
    case O2P_REG_COMMIT:          return 0u;
    default:                      return o2p_config_crc(c);
    }
}

uint8_t o2p_regmap_read(void *ctx, uint16_t addr, uint16_t count, uint16_t *out)
{
    o2p_regmap_t *rm = (o2p_regmap_t *)ctx;
    if (rm == NULL || out == NULL || count == 0u) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
    const o2p_snapshot_t *s = o2p_regmap_live(rm);

    /* A read must lie entirely inside ONE block. Spanning the gap between
     * blocks is refused rather than zero-filled: the gap is not a register
     * that happens to be zero, and a master reading across it has been
     * misconfigured. */
    if (in_block(addr, count, O2P_REG_PRIMARY_BASE, O2P_REG_PRIMARY_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_primary(s, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_DIAG_BASE, O2P_REG_DIAG_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_diag(s, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_CONFIG_BASE, O2P_REG_CONFIG_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_config(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    return O2P_MB_EX_ILLEGAL_ADDRESS;
}

/* ----------------------------------------------------------------- writes */

static uint8_t apply_config_word(o2p_config_t *c, uint16_t a, uint16_t v,
                                 bool *serial_changed)
{
    /* Range-check the FULL 16-bit value before narrowing into a uint8_t
     * field. Truncating first would let 0x0103 arrive as slave address 3 and
     * sail through o2p_config_valid(), silently accepting a write the master
     * did not make. */
    switch (a) {
    case O2P_REG_SLAVE_ADDR:
    case O2P_REG_BAUD_CODE:
    case O2P_REG_PARITY_CODE:
        if (v > 0xFFu) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        break;
    default:
        break;
    }

    switch (a) {
    case O2P_REG_SLAVE_ADDR:      c->slave_addr = (uint8_t)v; *serial_changed = true; break;
    case O2P_REG_BAUD_CODE:       c->baud_code = (uint8_t)v;  *serial_changed = true; break;
    case O2P_REG_PARITY_CODE:     c->parity_code = (uint8_t)v; *serial_changed = true; break;
    case O2P_REG_RH_SETPOINT:     c->rh_setpoint_x100 = v; break;
    case O2P_REG_DT_MAX_K:        c->dt_max_k_x100 = v; break;
    case O2P_REG_HEATER_MAX_DUTY: c->heater_max_duty_x100 = v; break;
    case O2P_REG_HEATER_PWM_HZ:   c->heater_pwm_hz = v; break;
    case O2P_REG_HEATER_KP:       c->heater_kp_x100 = v; break;
    case O2P_REG_HEATER_KI:       c->heater_ki_x100 = v; break;
    case O2P_REG_CAL_AIR_NA_HI:
        c->cal_air_na = (int32_t)(((uint32_t)v << 16) |
                                  ((uint32_t)c->cal_air_na & 0xFFFFu));
        break;
    case O2P_REG_CAL_AIR_NA_LO:
        c->cal_air_na = (int32_t)(((uint32_t)c->cal_air_na & 0xFFFF0000u) | v);
        break;
    case O2P_REG_CAL_ZERO_NA_HI:
        c->cal_zero_na = (int32_t)(((uint32_t)v << 16) |
                                   ((uint32_t)c->cal_zero_na & 0xFFFFu));
        break;
    case O2P_REG_CAL_ZERO_NA_LO:
        c->cal_zero_na = (int32_t)(((uint32_t)c->cal_zero_na & 0xFFFF0000u) | v);
        break;
    case O2P_REG_CAL_TEMP_C100:   c->cal_temp_c100 = (int16_t)v; break;
    case O2P_REG_TEMPCO_PPM_K:    c->tempco_ppm_per_k = (int16_t)v; break;
    case O2P_REG_SHT_PULSE_H:     c->sht_pulse_interval_h = v; break;
    default:
        return O2P_MB_EX_ILLEGAL_ADDRESS;
    }
    return 0u;
}

uint8_t o2p_regmap_write(void *ctx, uint16_t addr, uint16_t count, const uint16_t *in)
{
    o2p_regmap_t *rm = (o2p_regmap_t *)ctx;
    if (rm == NULL || in == NULL || count == 0u) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
    /* Only the config block is writable. The primary and diagnostic blocks are
     * measurements; a master that tries to write one is confused, and letting
     * it through would let the bus fabricate readings. */
    if (!in_block(addr, count, O2P_REG_CONFIG_BASE, O2P_REG_CONFIG_COUNT)) {
        return O2P_MB_EX_ILLEGAL_ADDRESS;
    }

    /* Validate against a COPY and commit all-or-nothing. A multi-register
     * write that is half legal must not leave the probe running on half a
     * configuration - in particular it must not change the baud rate and then
     * reject the address in the same frame. */
    o2p_config_t trial = rm->cfg;
    bool serial_changed = false;
    bool want_commit = false, want_cal = false, want_pulse = false;

    for (uint16_t i = 0; i < count; i++) {
        uint16_t a = (uint16_t)(addr + i);
        uint16_t v = in[i];
        switch (a) {
        case O2P_REG_CONFIG_CRC:
            /* Read-only. Refusing beats ignoring: a master that thinks it set
             * the CRC would believe a corrupt config had been accepted. */
            return O2P_MB_EX_ILLEGAL_ADDRESS;
        case O2P_REG_COMMIT:
            if (v != 0u && v != O2P_COMMIT_MAGIC) {
                return O2P_MB_EX_ILLEGAL_VALUE;
            }
            want_commit = (v == O2P_COMMIT_MAGIC);
            break;
        case O2P_REG_CAL_TRIGGER:
            if (v != 0u && v != O2P_CAL_MAGIC) {
                return O2P_MB_EX_ILLEGAL_VALUE;
            }
            want_cal = (v == O2P_CAL_MAGIC);
            break;
        case O2P_REG_SHT_PULSE_TRIG:
            if (v > 1u) {
                return O2P_MB_EX_ILLEGAL_VALUE;
            }
            want_pulse = (v == 1u);
            break;
        default: {
            uint8_t ex = apply_config_word(&trial, a, v, &serial_changed);
            if (ex != 0u) {
                return ex;
            }
            break;
        }
        }
    }

    if (!o2p_config_valid(&trial)) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }

    rm->cfg = trial;
    if (serial_changed) {
        /* Applied by the transport once the reply has physically left the
         * wire. Changing address or baud here would abandon the master
         * mid-frame and make the probe unreachable at both settings. */
        rm->serial_reconfig_pending = true;
    }
    /* "Calibrate and save" in ONE frame must mean exactly that, in that order.
     *
     * Both flags are collected independently above, so a single FC16 spanning
     * CAL_TRIGGER and COMMIT used to raise both at once - and the main loop
     * services commit_pending as soon as the reply is off the wire, which is
     * typically well before the next finish_o2() reaches the air routine. The
     * flash then stored the PRE-calibration image, the calibration landed in
     * RAM only, and the master had a successful write acknowledging both. A
     * power cycle silently discarded the calibration it had just confirmed.
     * Found by the 2026-09-08 review.
     *
     * So a co-requested commit is deferred: finish_o2() raises commit_pending
     * once the calibration has actually been taken. A commit asked for on its
     * own is unaffected and still runs at the next quiet moment. */
    if (want_cal) {
        /* A NEW trigger is a new request and gets a full retry budget. Without
         * this, a second CAL_TRIGGER inherited the exhausted counter of the
         * one before it and was discarded on the very next failed conversion -
         * an operator retrying a calibration got a shorter grace period each
         * time, silently (fifth review, 2026-09-08). */
        rm->cal_renewed = true;
        rm->cal_requested = true;
        if (want_commit) {
            rm->commit_after_cal = true;
        }
    } else if (want_commit) {
        /* A COMMIT that arrives while a calibration is still outstanding waits
         * for it too, exactly as if both had been in one frame.
         *
         * The one-frame case was fixed first, and that fix was incomplete in
         * the worst possible way: the DOCUMENTED commissioning procedure is
         * two requests - "write CAL_TRIGGER, then COMMIT" (FIRMWARE.md) - and
         * a COMMIT-only frame did not notice the pending calibration. The main
         * loop then persisted the PRE-calibration image, the air point landed
         * in RAM only, and the operator's calibration was lost at the next
         * power cycle after both writes returned success. Found by the fourth
         * review, 2026-09-08. */
        if (rm->cal_requested) {
            rm->commit_after_cal = true;
        } else {
            rm->commit_pending = true;
        }
    }
    if (want_pulse) {
        rm->sht_pulse_requested = true;
    }
    return 0u;
}
