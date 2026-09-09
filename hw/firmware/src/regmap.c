#include "regmap.h"
#include "faults.h"
#include "heater_ctl.h"
#include "heater_ctl.h"
#include "o2.h"

#include <math.h>
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
    cfg->cal_zero_na = 0;
    cfg->cal_zero_taken = 0u;   /* never measured; reported in CAL_STATE */
    cfg->cal_temp_c100 = 2500;
    cfg->tempco_ppm_per_k = 0;            /* SGX publishes no curve for this part */
    cfg->sht_pulse_interval_h = 8u;       /* PLAN.md:312, every 6-12 h */
    /* Total pressure for the water-vapour correction. Rev A has no barometer,
     * so this is the only P the firmware has; 930 hPa is the 715 m
     * Steingrubenhof site. A probe deployed elsewhere must have it written. */
    cfg->assumed_p_hpa = O2P_P_HPA_DEFAULT;
    /* No air point, so no air fraction. Zero means "unknown", which keeps
     * O2_COMP invalid until a calibration supplies both together - it must
     * NOT default to dry air, because assuming dry air at the air point is
     * precisely the 1-2 % bias this field exists to remove. */
    cfg->cal_air_frac_x1000 = 0u;
    /* Nor a calibration pressure. Zero means "unknown", which the conversion
     * reads as P_cal == P_meas - no pressure normalisation - rather than as
     * some assumed atmosphere. It is written together with the air point. */
    cfg->cal_p_hpa = 0u;
    /* Full gas-law dilution, i.e. the behaviour of every firmware before
     * 2026-09-07. NOT the 0.402 the sweep measured: that is one cell's
     * coefficient, and a default is a claim about all of them. It is also not
     * the safe value - at pile conditions full correction is worse than none
     * below alpha = 0.545 - which is why DIL_ALPHA is a per-probe bench
     * write and why O2-HUMIDITY-CORRECTION.md 15.4 is about a DECISION and
     * not about a default. */
    cfg->dil_alpha_x1000 = (uint16_t)(O2P_DIL_ALPHA_DEFAULT * 1000.0f);
    /* Heater loop. max_duty of zero means the loop is OFF by configuration as
     * well as by the compile guard: two independent switches, so enabling the
     * heater is never a single edit. See heater.h for the bench prerequisites.
     */
    cfg->heater_max_duty_x100 = 0u;
    /* No consent by default. A probe that has never been told to heat by
     * itself must not, and this is the field that says so. */
    cfg->heater_rh_consent = 0u;
    /* Persistent tip loop OFF by default, and the sentinel is what says so.
     * Note this is the one appended field whose correct default is NOT the
     * zero a memset would leave: 0 is a legal setpoint meaning "hold 0.00 C". */
    cfg->tip_setpoint_c100 = O2P_I16_INVALID;
    cfg->heater_tip_consent = 0u;
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
    /* Only two legal values. Refusing anything else means a corrupt flash
     * image cannot land on the magic by accident and cannot be stored with a
     * value that LOOKS like consent to a later reader. */
    if (cfg->heater_rh_consent != 0u &&
        cfg->heater_rh_consent != O2P_HEATER_RH_CONSENT_MAGIC) {
        return false;
    }
    /* Same argument for the temperature loop's consent. */
    if (cfg->heater_tip_consent != 0u &&
        cfg->heater_tip_consent != O2P_HEATER_TIP_CONSENT_MAGIC) {
        return false;
    }
    /* A stored setpoint must be inside the same envelope a written one is, or
     * a corrupt or downgraded record could hand the loop a target it would
     * have refused over the wire. The sentinel is the only legal value outside
     * 0..O2P_HEATER_TEST_SP_MAX_C100. */
    if (cfg->tip_setpoint_c100 != O2P_I16_INVALID &&
        (cfg->tip_setpoint_c100 < 0 ||
         cfg->tip_setpoint_c100 > O2P_HEATER_TEST_SP_MAX_C100)) {
        return false;
    }
    if (cfg->heater_max_duty_x100 > 10000u) {
        return false;
    }
    /* The ceiling is a THERMAL limit on Q2, not an arbitrary range. Switching
     * loss is duty-INDEPENDENT and scales with frequency, and the gate is
     * driven through R28 = 10 k against R29 = 100 k, which FIRMWARE.md puts at
     * "tens of microseconds" of edge - about 3 % of the period at the 1 kHz
     * design point. At the old 20 kHz ceiling two edges would be most of a
     * 50 us period and the FET would spend much of every cycle in its linear
     * region. Nobody has measured that, and no thermal load needs it: 1 kHz is
     * the tested point and 2 kHz leaves headroom without inviting a setting
     * whose dissipation is unknown. Raising this again is a bench measurement,
     * not an edit - the edge time is still UNVERIFIED, never having been put
     * on a scope. */
    if (cfg->heater_pwm_hz < 50u || cfg->heater_pwm_hz > 2000u) {
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
    /* Unlike the air point, 0 is a MEANINGFUL zero value (a cell with no
     * measurable dark current), so it cannot double as "unset" for the
     * plausibility test - but it is still the default, and the fault bit is
     * what distinguishes "measured zero" from "never measured". Screen the
     * stored number either way. */
    if (!o2p_cal_zero_plausible(cfg->cal_zero_na)) {
        return false;
    }
    /* Also checked here and not only on the Modbus write, so a corrupt flash
     * image cannot install a coefficient a master would have been refused. */
    if (cfg->tempco_ppm_per_k > O2P_TEMPCO_ABS_MAX_PPM_K ||
        cfg->tempco_ppm_per_k < -O2P_TEMPCO_ABS_MAX_PPM_K) {
        return false;
    }
    /* The other end of the gain subtraction. Bounding alpha alone bounds
     * nothing while T_cal is free. */
    if (!o2p_cal_temp_plausible(cfg->cal_temp_c100)) {
        return false;
    }
    if (cfg->cal_air_na != 0 && !o2p_cal_air_plausible(cfg->cal_air_na)) {
        return false;
    }
    if (cfg->sht_pulse_interval_h == 0u || cfg->sht_pulse_interval_h > 168u) {
        return false;
    }
    /* The assumed total pressure scales oxygen directly, so it is bounded
     * rather than merely non-zero: zero would divide, and 5 hPa or 3000 hPa
     * would rescale every reading without ever looking like a fault. There is
     * no "unset" value - the default is always installed. */
    if (cfg->assumed_p_hpa < O2P_P_HPA_MIN || cfg->assumed_p_hpa > O2P_P_HPA_MAX) {
        return false;
    }
    /* Zero means "air point of unknown humidity", which is legal and keeps
     * O2_COMP invalid. Any other value must be a fraction air can actually
     * have; %vol x 1000, so 20946 is dry air. */
    if (cfg->cal_air_frac_x1000 != 0u &&
        (cfg->cal_air_frac_x1000 < (uint16_t)(O2P_CAL_FRAC_MIN * 100000.0f) ||
         cfg->cal_air_frac_x1000 > (uint16_t)(O2P_CAL_FRAC_MAX * 100000.0f))) {
        return false;
    }
    /* The calibration pressure. Zero is legal and means "unknown" - the
     * conversion then applies no pressure normalisation at all. Any other
     * value has to be a pressure, and the same window as ASSUMED_P_HPA:
     * P_cal/P_meas scales oxygen directly, so a 5 hPa or 3000 hPa cal
     * pressure would rescale every reading without ever looking like a
     * fault. */
    if (cfg->cal_p_hpa != 0u &&
        (cfg->cal_p_hpa < O2P_P_HPA_MIN || cfg->cal_p_hpa > O2P_P_HPA_MAX)) {
        return false;
    }
    /* Dilution efficacy. Zero IS legal and means "apply no vapour correction
     * at all" - a real choice, and the one that beats full correction on this
     * cell. There is no "unset": the default is always installed, so unlike
     * the calibration fields a zero here is an instruction rather than an
     * absence. The ceiling is the same one o2.c enforces. */
    if (cfg->dil_alpha_x1000 > (uint16_t)(O2P_DIL_ALPHA_MAX * 1000.0f)) {
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
    s->t_die = O2P_I16_INVALID;
    s->t_afe = O2P_I16_INVALID;
    s->ce_mv = O2P_U16_INVALID;
    s->exp_data = O2P_U16_INVALID;
    s->we_buf_mv = O2P_U16_INVALID;
    s->re_buf_mv = O2P_U16_INVALID;
    s->cell_bias_mv = O2P_I16_INVALID;
    s->heater_block = O2P_U16_INVALID;
    s->sampler_timing_ms = O2P_U16_INVALID;
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

void o2p_regmap_set_cal_result(o2p_regmap_t *rm, uint8_t status)
{
    rm->cmd_result = (uint16_t)(((uint16_t)status << 8) |
                                O2P_CMD_RESULT_COMMIT(rm->cmd_result));
}

void o2p_regmap_set_commit_result(o2p_regmap_t *rm, uint8_t status)
{
    rm->cmd_result = (uint16_t)(((uint16_t)O2P_CMD_RESULT_CAL(rm->cmd_result) << 8) |
                                status);
}

void o2p_regmap_request_commit(o2p_regmap_t *rm)
{
    if (rm->serial_probation) {
        rm->commit_after_serial = true;
    } else {
        rm->commit_pending = true;
    }
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
        /* Left at 0 here and seeded by the caller before the bus comes up.
         * regmap.c is built for the host test suite too, so it cannot reach
         * the MCU headers o2p_reset_cause() lives behind. See main.c. */
        s->reset_cause = 0u;
    }
    rm->live = 0u;
    /* memset above leaves these at zero, and zero is wrong for both: a zero
     * setpoint is a real temperature (0.00 C) rather than "none", and zero
     * gains would make an armed temperature loop sit at 0 % duty looking
     * like a fault. Neither can energise anything - heater_test_armed is
     * false - but a mode must not come up meaning something it does not. */
    rm->heater_test_tip_sp_c100 = O2P_I16_INVALID;
    rm->heater_test_kp_x100 = O2P_HEATER_TEST_KP_X100_DEFAULT;
    rm->heater_test_ki_x100 = O2P_HEATER_TEST_KI_X100_DEFAULT;

    /* Peek mailbox initialization */
    rm->peek_status = O2P_PEEK_NONE;
    for (int w = 0; w < 4; w++) {
        rm->peek_words[w] = 0xFFFFFFFFu;
    }

    /* Sensor diagnostic mailbox initialization */
    rm->diag_status = O2P_DMBOX_STATUS_NONE;
    rm->diag_pending = false;

    /* Crash retention initialization */
    rm->crash_reason = O2P_CRASH_NONE;
}

#ifndef O2P_HOST_TEST
uint32_t o2p_crash_read_reg(uint8_t index);
void o2p_crash_clear(void);
#endif

void o2p_regmap_load_crash_context(o2p_regmap_t *rm)
{
#ifndef O2P_HOST_TEST
    if (o2p_crash_read_reg(0) == O2P_CRASH_MAGIC) {
        rm->crash_pc = o2p_crash_read_reg(1);
        rm->crash_lr = o2p_crash_read_reg(2);
        uint32_t r3 = o2p_crash_read_reg(3);
        rm->crash_reason = (uint16_t)(r3 & 0xFFu);
        rm->crash_detail = r3 >> 8;
        rm->crash_build_id = o2p_crash_read_reg(4);
    } else {
        rm->crash_reason = O2P_CRASH_NONE;
    }
#else
    (void)rm;
#endif
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

static uint16_t read_diag(const o2p_regmap_t *rm, const o2p_snapshot_t *s,
                         uint16_t a)
{
    switch (a) {
    /* Command state, not sample state: it belongs to the regmap and must NOT
     * be snapshotted, or an outcome would only become visible at the next
     * publish. */
    case O2P_REG_CMD_RESULT:    return rm->cmd_result;
    case O2P_REG_CAL_STATE:
        return (uint16_t)((rm->cfg.cal_air_na == 0
                               ? O2P_CAL_STATE_AIR_DEFAULT : 0u) |
                          (rm->cfg.cal_zero_taken == 0u
                               ? O2P_CAL_STATE_NO_ZERO : 0u));
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
    case O2P_REG_T_DIE:         return (uint16_t)s->t_die;
    case O2P_REG_T_AFE:         return (uint16_t)s->t_afe;
    case O2P_REG_CE_MV:         return s->ce_mv;
    case O2P_REG_FAULTS_EVER:   return s->faults_ever;
    case O2P_REG_ADS_FAIL_COUNT: return s->ads_fail_count;
    case O2P_REG_WE_BUF_MV:    return s->we_buf_mv;
    case O2P_REG_RE_BUF_MV:    return s->re_buf_mv;
    case O2P_REG_CELL_BIAS_MV: return (uint16_t)s->cell_bias_mv;
    /* Compile-time constants, like FW_VERSION and HW_REV: they describe the
     * image, not the cycle, so they are not carried through the snapshot. */
    case O2P_REG_BUILD_ID_HI:  return (uint16_t)((O2P_BUILD_ID >> 16) & 0xFFFFu);
    case O2P_REG_BUILD_ID_LO:  return (uint16_t)(O2P_BUILD_ID & 0xFFFFu);
    case O2P_REG_SAMPLE_SEQ:    return s->sample_seq;
    case O2P_REG_HEATER_BLOCK:  return s->heater_block;
    case O2P_REG_SAMPLER_TIMING_MS: return s->sampler_timing_ms;
    /* Named explicitly rather than left to the default. This arm used to
     * return sample_seq for anything unmatched, so every register added to
     * the block afterwards answered with a plausible, monotonically climbing
     * number until someone remembered to add its case - the failure this
     * file's whole design is against. An in-block address with no case is a
     * gap in this switch, and it says so. */
    default:                    return O2P_U16_INVALID;
    }
}

static uint16_t read_htest(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_HEATER_TEST_ARM:    return rm->heater_test_armed ? 1u : 0u;
    case O2P_REG_HEATER_TEST_DUTY:   return rm->heater_test_duty_x100;
    case O2P_REG_HEATER_TEST_TIP_SP: return (uint16_t)rm->heater_test_tip_sp_c100;
    case O2P_REG_HEATER_TEST_KP:     return rm->heater_test_kp_x100;
    case O2P_REG_HEATER_TEST_KI:     return rm->heater_test_ki_x100;
    default: break;
    }
    return 0u;
}

static uint16_t read_peek(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_PEEK_ADDR_HI: return rm->peek_addr_hi;
    case O2P_REG_PEEK_ADDR_LO: return rm->peek_addr_lo;
    case O2P_REG_PEEK_STATUS:  return rm->peek_status;
    case O2P_REG_PEEK_W0_HI:   return (uint16_t)(rm->peek_words[0] >> 16);
    case O2P_REG_PEEK_W0_LO:   return (uint16_t)(rm->peek_words[0] & 0xFFFFu);
    case O2P_REG_PEEK_W1_HI:   return (uint16_t)(rm->peek_words[1] >> 16);
    case O2P_REG_PEEK_W1_LO:   return (uint16_t)(rm->peek_words[1] & 0xFFFFu);
    case O2P_REG_PEEK_W2_HI:   return (uint16_t)(rm->peek_words[2] >> 16);
    case O2P_REG_PEEK_W2_LO:   return (uint16_t)(rm->peek_words[2] & 0xFFFFu);
    case O2P_REG_PEEK_W3_HI:   return (uint16_t)(rm->peek_words[3] >> 16);
    case O2P_REG_PEEK_W3_LO:   return (uint16_t)(rm->peek_words[3] & 0xFFFFu);
    default: break;
    }
    return O2P_U16_INVALID;
}

static uint16_t read_dmbox(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_DIAG_CMD:        return rm->diag_cmd;
    case O2P_REG_DIAG_PARAM:      return rm->diag_param;
    case O2P_REG_DIAG_STATUS:     return rm->diag_status;
    case O2P_REG_DIAG_RDATA0:     return rm->diag_rdata0;
    case O2P_REG_DIAG_RDATA1:     return rm->diag_rdata1;
    case O2P_REG_DIAG_RDATA2:     return rm->diag_rdata2;
    case O2P_REG_DIAG_CRC_STATUS: return rm->diag_crc_status;
    default: break;
    }
    return O2P_U16_INVALID;
}

static uint16_t read_crash(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_CRASH_REASON:      return rm->crash_reason;
    case O2P_REG_CRASH_PC_HI:       return (uint16_t)(rm->crash_pc >> 16);
    case O2P_REG_CRASH_PC_LO:       return (uint16_t)(rm->crash_pc & 0xFFFFu);
    case O2P_REG_CRASH_LR_HI:       return (uint16_t)(rm->crash_lr >> 16);
    case O2P_REG_CRASH_LR_LO:       return (uint16_t)(rm->crash_lr & 0xFFFFu);
    case O2P_REG_CRASH_DETAIL_HI:   return (uint16_t)(rm->crash_detail >> 16);
    case O2P_REG_CRASH_DETAIL_LO:   return (uint16_t)(rm->crash_detail & 0xFFFFu);
    case O2P_REG_CRASH_BUILD_ID_HI: return (uint16_t)(rm->crash_build_id >> 16);
    case O2P_REG_CRASH_BUILD_ID_LO: return (uint16_t)(rm->crash_build_id & 0xFFFFu);
    default: break;
    }
    return O2P_U16_INVALID;
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
    case O2P_REG_HEATER_RH_CONSENT: return c->heater_rh_consent;
    case O2P_REG_TIP_SETPOINT:      return (uint16_t)c->tip_setpoint_c100;
    case O2P_REG_HEATER_TIP_CONSENT: return c->heater_tip_consent;
    case O2P_REG_HEATER_PWM_HZ:   return c->heater_pwm_hz;
    case O2P_REG_HEATER_KP:       return c->heater_kp_x100;
    case O2P_REG_HEATER_KI:       return c->heater_ki_x100;
    case O2P_REG_CAL_ZERO_NA_HI:  return (uint16_t)((uint32_t)c->cal_zero_na >> 16);
    case O2P_REG_CAL_ZERO_NA_LO:  return (uint16_t)((uint32_t)c->cal_zero_na & 0xFFFFu);
    case O2P_REG_CAL_AIR_NA_HI:   return (uint16_t)((uint32_t)c->cal_air_na >> 16);
    case O2P_REG_CAL_AIR_NA_LO:   return (uint16_t)((uint32_t)c->cal_air_na & 0xFFFFu);
    case O2P_REG_CAL_TEMP_C100:   return (uint16_t)c->cal_temp_c100;
    case O2P_REG_TEMPCO_PPM_K:    return (uint16_t)c->tempco_ppm_per_k;
    case O2P_REG_SHT_PULSE_H:     return c->sht_pulse_interval_h;
    case O2P_REG_ASSUMED_P_HPA:   return c->assumed_p_hpa;
    case O2P_REG_CAL_AIR_FRAC:    return c->cal_air_frac_x1000;
    case O2P_REG_CAL_P_HPA:       return c->cal_p_hpa;
    case O2P_REG_DIL_ALPHA:       return c->dil_alpha_x1000;
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
            out[i] = read_diag(rm, s, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_CONFIG_BASE, O2P_REG_CONFIG_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_config(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_HTEST_BASE, O2P_REG_HTEST_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_htest(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_PEEK_BASE, O2P_REG_PEEK_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_peek(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_DMBOX_BASE, O2P_REG_DMBOX_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_dmbox(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_CRASH_BASE, O2P_REG_CRASH_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_crash(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    /* The updater's two blocks. Routed rather than implemented here: the same
     * engine answers these registers in the bootloader, where none of the
     * rest of this file exists. */
    if (rm->upd != NULL &&
        (in_block(addr, count, O2P_REG_UPDATE_BASE, O2P_REG_UPDATE_COUNT) ||
         in_block(addr, count, O2P_REG_UPDDATA_BASE, O2P_REG_UPDDATA_COUNT))) {
        return o2p_update_read(rm->upd, addr, count, out);
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

    /* CHANGED, not merely written. `c` is the trial copy, which still holds
     * the live value for any field this frame has not touched, so comparing
     * against it is comparing against the running configuration.
     *
     * Writing a register its own current value must be a no-op, because a
     * master that rewrites its whole config block - a normal thing to do -
     * touches all three of these every time. Treating that as a change armed
     * a ten-second probation and, with a COMMIT in the same frame, deferred
     * it behind proof that would never come from a master polling at five
     * minutes: the commit could then only ever report FAILED. It would also
     * arm a probation whose fallback is FLASH on a probe whose RAM settings
     * deliberately differ from it - which is exactly the state the field
     * updater creates - and drop it back mid-transfer. */
    switch (a) {
    case O2P_REG_SLAVE_ADDR:
        if (c->slave_addr != (uint8_t)v) { c->slave_addr = (uint8_t)v; *serial_changed = true; }
        break;
    case O2P_REG_BAUD_CODE:
        if (c->baud_code != (uint8_t)v) { c->baud_code = (uint8_t)v; *serial_changed = true; }
        break;
    case O2P_REG_PARITY_CODE:
        if (c->parity_code != (uint8_t)v) { c->parity_code = (uint8_t)v; *serial_changed = true; }
        break;
    case O2P_REG_RH_SETPOINT:     c->rh_setpoint_x100 = v; break;
    case O2P_REG_DT_MAX_K:        c->dt_max_k_x100 = v; break;
    case O2P_REG_HEATER_MAX_DUTY: c->heater_max_duty_x100 = v; break;
    case O2P_REG_HEATER_RH_CONSENT:
        /* Validated here rather than only in o2p_config_valid(), so the
         * exception names the register the master actually got wrong. */
        if (v != 0u && v != O2P_HEATER_RH_CONSENT_MAGIC) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        c->heater_rh_consent = v;
        break;
    case O2P_REG_HEATER_TIP_CONSENT:
        if (v != 0u && v != O2P_HEATER_TIP_CONSENT_MAGIC) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        c->heater_tip_consent = v;
        break;
    case O2P_REG_TIP_SETPOINT:
        /* Identical bounds to the volatile 0x0062, deliberately: an operator
         * who learned the envelope at the bench must not find a different one
         * in flash. The sentinel, or 0..O2P_HEATER_TEST_SP_MAX_C100. A
         * negative that is not the sentinel is a units or sign error and is
         * refused rather than quietly meaning "never heat". */
        if (v != (uint16_t)O2P_I16_INVALID &&
            ((int16_t)v > O2P_HEATER_TEST_SP_MAX_C100 || (int16_t)v < 0)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        c->tip_setpoint_c100 = (int16_t)v;
        break;
    case O2P_REG_HEATER_PWM_HZ:   c->heater_pwm_hz = v; break;
    case O2P_REG_HEATER_KP:       c->heater_kp_x100 = v; break;
    case O2P_REG_HEATER_KI:       c->heater_ki_x100 = v; break;
    /* Writing either half is what MARKS the zero point as taken. Without this
     * the flag was initialised to 0, read by CAL_STATE, and never set anywhere
     * in production code - so a probe that had been zeroed went on reporting
     * NO_ZERO forever while the arithmetic used the new value. The flag exists
     * precisely because 0 nA is both a real measured zero and the
     * never-measured default; a flag nothing sets cannot tell them apart.
     * Found by review 2026-09-08. */
    case O2P_REG_CAL_ZERO_NA_HI:
        c->cal_zero_na = (int32_t)(((uint32_t)v << 16) |
                                   ((uint32_t)c->cal_zero_na & 0xFFFFu));
        c->cal_zero_taken = 1u;
        break;
    case O2P_REG_CAL_ZERO_NA_LO:
        c->cal_zero_na = (int32_t)(((uint32_t)c->cal_zero_na & 0xFFFF0000u) | v);
        c->cal_zero_taken = 1u;
        break;
    case O2P_REG_CAL_AIR_NA_HI:
        c->cal_air_na = (int32_t)(((uint32_t)v << 16) |
                                  ((uint32_t)c->cal_air_na & 0xFFFFu));
        break;
    case O2P_REG_CAL_AIR_NA_LO:
        c->cal_air_na = (int32_t)(((uint32_t)c->cal_air_na & 0xFFFF0000u) | v);
        break;
    case O2P_REG_CAL_TEMP_C100: {
        int16_t t = (int16_t)v;
        if (!o2p_cal_temp_plausible(t)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        c->cal_temp_c100 = t;
        break;
    }
    case O2P_REG_TEMPCO_PPM_K: {
        int16_t t = (int16_t)v;
        if (t > O2P_TEMPCO_ABS_MAX_PPM_K || t < -O2P_TEMPCO_ABS_MAX_PPM_K) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        c->tempco_ppm_per_k = t;
        break;
    }
    case O2P_REG_SHT_PULSE_H:     c->sht_pulse_interval_h = v; break;
    case O2P_REG_ASSUMED_P_HPA:   c->assumed_p_hpa = v; break;
    case O2P_REG_CAL_AIR_FRAC:    c->cal_air_frac_x1000 = v; break;
    case O2P_REG_CAL_P_HPA:       c->cal_p_hpa = v; break;
    case O2P_REG_DIL_ALPHA:
        /* The VALUE ONLY. Restating CAL_AIR_FRAC is a TRANSACTION-level
         * decision, not a per-word one - see reference_air_frac() and its
         * caller below. Doing it here was wrong in a way a whole-block FC16
         * makes routine: words are applied in ascending order, so 0x0043
         * lands before 0x0045, and a master writing the pair it actually
         * wants had its own correct fraction transformed a second time. */
        c->dil_alpha_x1000 = v;
        break;
    default:
        return O2P_MB_EX_ILLEGAL_ADDRESS;
    }
    return 0u;
}

/* Restate a stored air fraction under a new alpha.
 *
 * CAL_AIR_FRAC is C_air * f_eff(alpha_old) and K is fixed against it, so a
 * new alpha would rescale every later reading by the ratio if it were left
 * alone. f_eff = 1 - alpha*(1-f) inverts exactly, so nothing has to be
 * re-measured:
 *
 *     alpha_old * (1 - f) = 1 - air_frac_old / C_AIR
 *     air_frac_new        = C_AIR * (1 - (alpha_new/alpha_old) * that)
 *
 * WHEN IT REFUSES, which is the half adversarial review found missing. The
 * stored fraction is %vol x 1000 in a u16, so (1-f) is recovered from a
 * QUANTISED number and the recovery is then divided by alpha_old. One LSB of
 * CAL_AIR_FRAC therefore becomes 1e-5/alpha_old of air fraction, and as
 * alpha_old shrinks that grows without bound: by alpha_old = 0.001 the stored
 * value rounds to 20946 for EVERY humidity, so (1-f) is not imprecise, it is
 * gone. Treating only exact zero as loss - which is what this did - turned an
 * unrecoverable fraction into a plausible wrong one, measured at ~0.12 pp.
 * The quantity to bound is the ALPHA RATIO: C_AIR cancels out of the error
 * term, so one LSB in becomes alpha_new/alpha_old LSB out.
 *
 * So the floor is on the RECOVERED ERROR rather than on alpha itself, and
 * refusing means zero: "unknown", which holds O2_COMP on its sentinel until a
 * fresh air point. Never a number nobody can justify. */
static void reference_air_frac(o2p_config_t *c, uint16_t alpha_old)
{
    uint16_t frac = c->cal_air_frac_x1000;
    if (frac == 0u) {
        return;                     /* never calibrated; nothing to restate */
    }
    if (alpha_old == 0u ||
        ((float)c->dil_alpha_x1000 / (float)alpha_old)
            > O2P_AIR_FRAC_MAX_AMPLIFY) {
        c->cal_air_frac_x1000 = 0u;
        return;
    }
    float f_old = (float)frac * 1e-5f;
    float dil = (1.0f - f_old / O2P_C_AIR) *
                ((float)c->dil_alpha_x1000 / (float)alpha_old);
    float f_new = O2P_C_AIR * (1.0f - dil);
    float x100000 = f_new * 100000.0f + 0.5f;
    if (isfinite(x100000) &&
        x100000 >= O2P_CAL_FRAC_MIN * 100000.0f &&
        x100000 <= O2P_CAL_FRAC_MAX * 100000.0f) {
        c->cal_air_frac_x1000 = (uint16_t)x100000;
    } else {
        c->cal_air_frac_x1000 = 0u;
    }
}

uint8_t o2p_regmap_write(void *ctx, uint16_t addr, uint16_t count, const uint16_t *in)
{
    o2p_regmap_t *rm = (o2p_regmap_t *)ctx;
    if (rm == NULL || in == NULL || count == 0u) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
    if (rm->upd != NULL &&
        (in_block(addr, count, O2P_REG_UPDATE_BASE, O2P_REG_UPDATE_COUNT) ||
         in_block(addr, count, O2P_REG_UPDDATA_BASE, O2P_REG_UPDDATA_COUNT))) {
        return o2p_update_write(rm->upd, addr, count, in);
    }
    /* The heater bench override. Handled here rather than through the config
     * machinery below because it deliberately has no flash-backed home: it
     * must not be reachable by COMMIT, must not appear in the config CRC, and
     * must not survive a reset. Validated and applied all-or-nothing on the
     * same principle as the config block - a frame that arms the override and
     * then names an illegal duty must do neither. */
    if (in_block(addr, count, O2P_REG_HTEST_BASE, O2P_REG_HTEST_COUNT)) {
        bool arm = rm->heater_test_armed;
        uint16_t duty = rm->heater_test_duty_x100;
        int16_t sp = rm->heater_test_tip_sp_c100;
        uint16_t kp = rm->heater_test_kp_x100;
        uint16_t ki = rm->heater_test_ki_x100;
        for (uint16_t i = 0; i < count; i++) {
            uint16_t a = (uint16_t)(addr + i);
            uint16_t v = in[i];
            switch (a) {
            case O2P_REG_HEATER_TEST_ARM:
                /* Only the magic arms. Anything else disarms rather than
                 * erroring: a master trying to switch the heater OFF must
                 * always succeed, whatever it writes. */
                arm = (v == O2P_HEATER_TEST_MAGIC);
                break;
            case O2P_REG_HEATER_TEST_DUTY:
                if (v > 10000u) {
                    return O2P_MB_EX_ILLEGAL_VALUE;
                }
                duty = v;
                break;
            case O2P_REG_HEATER_TEST_TIP_SP:
                /* The sentinel, or a temperature at least a kelvin below the
                 * absolute clamp. Negatives other than the sentinel are
                 * refused rather than quietly meaning "never heat": a master
                 * that wrote one has made a units or sign error, and letting
                 * it through would present a broken setpoint as a working
                 * loop that simply never asks for duty. */
                if (v != (uint16_t)O2P_I16_INVALID &&
                    (int16_t)v > O2P_HEATER_TEST_SP_MAX_C100) {
                    return O2P_MB_EX_ILLEGAL_VALUE;
                }
                if (v != (uint16_t)O2P_I16_INVALID && (int16_t)v < 0) {
                    return O2P_MB_EX_ILLEGAL_VALUE;
                }
                sp = (int16_t)v;
                break;
            case O2P_REG_HEATER_TEST_KP:
                kp = v;
                break;
            default:
                ki = v;
                break;
            }
        }
        /* Everything except the arm flag first, then the arm flag. The
         * opposite order leaves a window of one control cycle in which the
         * override is live carrying the PREVIOUS setpoint, duty and gains,
         * and on a 1 Hz loop that window is long enough to drive the ring. */
        rm->heater_test_duty_x100 = duty;
        rm->heater_test_tip_sp_c100 = sp;
        rm->heater_test_kp_x100 = kp;
        rm->heater_test_ki_x100 = ki;
        /* Count the ARM EDGE, before the flag the loop reads, so the loop can
         * never see a new session's arm carrying the previous session's
         * counter. Re-arming while already armed is not a new session. */
        if (arm && !rm->heater_test_armed) {
            rm->heater_test_session = (uint8_t)(rm->heater_test_session + 1u);
        }
        rm->heater_test_armed = arm;
        return 0u;
    }

    /* Memory peek mailbox: atomic 2-register FC16 write required */
    if (in_block(addr, count, O2P_REG_PEEK_BASE, O2P_REG_PEEK_COUNT)) {
        if (addr != O2P_REG_PEEK_BASE || count != 2u) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        rm->peek_addr_hi = in[0];
        rm->peek_addr_lo = in[1];
        uint32_t target = ((uint32_t)in[0] << 16) | (uint32_t)in[1];

        if ((target & 3u) != 0u) {
            rm->peek_status = O2P_PEEK_ERR_ALIGN;
            for (int w = 0; w < 4; w++) rm->peek_words[w] = 0xFFFFFFFFu;
            return 0u;
        }

        bool in_sram = (target >= 0x20000000u && target <= 0x20008FFCu);
        bool in_flash = (target >= 0x08000000u && target <= 0x0801FFFCu);
        bool in_sys = ((target >= 0x1FFF7590u && target <= 0x1FFF7598u) || target == 0x1FFF75E0u);

        if (!in_sram && !in_flash && !in_sys) {
            rm->peek_status = O2P_PEEK_ERR_RANGE;
            for (int w = 0; w < 4; w++) rm->peek_words[w] = 0xFFFFFFFFu;
            return 0u;
        }

        for (int w = 0; w < 4; w++) {
            uint32_t a = target + (uint32_t)w * 4u;
            bool ok = (in_sram && a <= 0x20008FFCu) ||
                      (in_flash && a <= 0x0801FFFCu) ||
                      (in_sys && ((a >= 0x1FFF7590u && a <= 0x1FFF7598u) || a == 0x1FFF75E0u));
            if (ok) {
#ifndef O2P_HOST_TEST
                rm->peek_words[w] = *(const volatile uint32_t *)a;
#else
                rm->peek_words[w] = 0x12345678u + (uint32_t)w;
#endif
            } else {
                rm->peek_words[w] = 0xFFFFFFFFu;
            }
        }
        rm->peek_status = O2P_PEEK_OK;
        return 0u;
    }

    /* Sensor diagnostic mailbox */
    if (in_block(addr, count, O2P_REG_DMBOX_BASE, O2P_REG_DMBOX_COUNT)) {
        if (addr != O2P_REG_DMBOX_BASE || count < 1u || count > 2u) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint16_t cmd = in[0];
        if ((cmd & O2P_DIAG_MAGIC_MASK) != O2P_DIAG_MAGIC) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint8_t op = (uint8_t)(cmd & 0xFFu);
        if (op < O2P_OP_READ_LMP_REG || op > O2P_OP_READ_SHT_SAMPLE) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        rm->diag_cmd = cmd;
        if (count == 2u) {
            rm->diag_param = in[1];
        }
        rm->diag_status = O2P_DMBOX_STATUS_PENDING;
        rm->diag_pending = true;
        return 0u;
    }

    /* Crash retention mailbox: writing 0 clears record */
    if (in_block(addr, count, O2P_REG_CRASH_BASE, O2P_REG_CRASH_COUNT)) {
        if (in[0] == 0u) {
#ifndef O2P_HOST_TEST
            o2p_crash_clear();
#endif
            rm->crash_reason = O2P_CRASH_NONE;
            rm->crash_pc = 0u;
            rm->crash_lr = 0u;
            rm->crash_detail = 0u;
            rm->crash_build_id = 0u;
            return 0u;
        }
        return O2P_MB_EX_ILLEGAL_VALUE;
    }

    /* Only the config block and the updater are writable. The primary and
     * diagnostic blocks are measurements; a master that tries to write one is
     * confused, and letting it through would let the bus fabricate readings. */
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
    /* Transaction scope for the alpha restatement. A master that writes
     * CAL_AIR_FRAC in the SAME frame has supplied the value it wants, and it
     * must not then be transformed as though it belonged to the old alpha. */
    uint16_t alpha_before = trial.dil_alpha_x1000;
    bool frac_written = false;

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
            if (a == O2P_REG_CAL_AIR_FRAC) {
                frac_written = true;
            }
            uint8_t ex = apply_config_word(&trial, a, v, &serial_changed);
            if (ex != 0u) {
                return ex;
            }
            break;
        }
        }
    }

    /* AFTER the whole frame, so word order inside it cannot matter, and only
     * when the master did not state the fraction itself. */
    if (trial.dil_alpha_x1000 != alpha_before && !frac_written) {
        reference_air_frac(&trial, alpha_before);
    }

    if (!o2p_config_valid(&trial)) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }

    rm->cfg = trial;
    if (serial_changed) {
        /* Raised HERE rather than when the transport switches, so a COMMIT in
         * this same frame is gated by it. The write and the commit are decided
         * in one pass; the switch happens a main loop later. */
        rm->serial_probation = true;
        /* Applied by the transport once the reply has physically left the
         * wire. Changing address or baud here would abandon the master
         * mid-frame and make the probe unreachable at both settings. */
        rm->serial_reconfig_pending = true;
    }
    /* "Calibrate and save" in ONE frame must mean exactly that, in that
     * order. Both flags were raised at once, and the main loop services
     * commit_pending as soon as the reply is off the wire - typically well
     * before the next conversion reaches the air routine. Flash then stored
     * the PRE-calibration image and the point landed in RAM only. The same
     * hole existed for the DOCUMENTED two-frame procedure (write CAL_TRIGGER,
     * then COMMIT), because a COMMIT-only frame did not notice the pending
     * calibration. */
    if (want_cal) {
        rm->cal_requested = true;
        o2p_regmap_set_cal_result(rm, O2P_CMD_PENDING);
        if (want_commit) {
            rm->commit_after_cal = true;
            o2p_regmap_set_commit_result(rm, O2P_CMD_PENDING);
        }
    } else if (want_commit) {
        if (rm->cal_requested) {
            rm->commit_after_cal = true;
        } else {
            o2p_regmap_request_commit(rm);
        }
        o2p_regmap_set_commit_result(rm, O2P_CMD_PENDING);
    }
    if (want_pulse) {
        rm->sht_pulse_requested = true;
    }
    return 0u;
}
