#include "regmap.h"
#include "faults.h"
#include "flash_map.h"   /* O2P_BOOT_BASE, O2P_APP_BASE/_BYTES for the peek flash bound */
#include "gpio_diag.h"
#include "heater_ctl.h"
#ifndef O2P_HOST_TEST
#include "mcu.h"
#endif
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
    cfg->tempco_ppm_per_k = 0;            /* no sourced figure: DS-0637's curve (Issues 1 and 2) is undigitised (o2.h) */
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
    /* RH-loop consent GRANTED by default since 2026-09-10. A probe that
     * cannot prevent its own condensation while no control channel is
     * reachable is the worse risk, and the loop this authorises is the mild
     * one: a few kelvin above ambient inside a 0-4 K envelope, with every
     * burn-side interlock still applying. Two gates remain in front of it:
     * heater_max_duty_x100 still defaults to zero above, so enabling the
     * heater is never a single edit, and a config MIGRATION still lands on
     * zero - an upgrade re-asks, because an older record cannot honestly
     * express consent. Writing 0 to 0x0048 still refuses, permanently.
     * Measured motivation: 2026-09-10, a bench board at 99 %RH with a
     * collapsing dew margin could not heat itself because consent had never
     * been granted, and the grant write was locked out by the node's CTRL
     * budget at exactly that moment. */
    cfg->heater_rh_consent = O2P_HEATER_RH_CONSENT_MAGIC;
    /* Persistent tip loop OFF by default, and the sentinel is what says so.
     * Note this is the one appended field whose correct default is NOT the
     * zero a memset would leave: 0 is a legal setpoint meaning "hold 0.00 C". */
    cfg->tip_setpoint_c100 = O2P_I16_INVALID;
    cfg->heater_tip_consent = 0u;
    /* The netlist divider. The memset already left it; stated because WHY it
     * is zero - every record written before 0x004B existed means exactly this -
     * is what let the field skip a layout bump (regmap.h). */
    o2p_cfg_set_vin_div_x1000(cfg, O2P_VIN_DIV_X1000_NETLIST);
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
    /* VIN_DIV_X1000 is NOT screened here, on purpose: no record is refused
     * over it. Its consumers fall back to the netlist divider instead - see
     * o2p_vin_div_x1000_in_window() for why that is the safe direction. */
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

#if O2P_DEBUG_ENABLE
#define O2P_EFFECTIVE_BUILD_ID ((uint32_t)O2P_BUILD_ID | O2P_BUILD_ID_FLAG_DEBUG)
#else
#define O2P_EFFECTIVE_BUILD_ID ((uint32_t)O2P_BUILD_ID & ~O2P_BUILD_ID_FLAG_DEBUG)
#endif

uint32_t g_o2p_build_id = O2P_EFFECTIVE_BUILD_ID;

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

#if O2P_DEBUG_ENABLE
    /* Peek mailbox initialization */
    rm->peek_status = O2P_PEEK_NONE;
    for (int w = 0; w < 4; w++) {
        rm->peek_words[w] = 0xFFFFFFFFu;
    }
    /* Wide peek: nothing held, sequence 0 = never triggered, and every word
     * reads as unexecuted rather than as a plausible zero. */
    rm->peekw_status = O2P_PEEK_NONE;
    rm->peekw_seq = 0u;
    for (unsigned w = 0; w < O2P_PEEKW_WORDS_MAX; w++) {
        rm->peekw_words[w] = 0xFFFFFFFFu;
    }
    /* Poke mailbox and wide poke (2026-09-11): nothing held, no payload, and
     * the same 0 = never-triggered convention for the wide sequence. */
    rm->poke_addr_hi = 0u;
    rm->poke_addr_lo = 0u;
    rm->poke_words_held = 0u;
    rm->poke_status = O2P_POKE_NONE;
    for (unsigned w = 0; w < 4u; w++) {
        rm->poke_words[w] = 0u;
    }
    rm->pokew_addr = 0u;
    rm->pokew_words_req = 0u;
    rm->pokew_status = O2P_POKE_NONE;
    rm->pokew_seq = 0u;
    for (unsigned w = 0; w < O2P_PEEKW_WORDS_MAX; w++) {
        rm->pokew_words[w] = 0u;
    }

    /* Sensor diagnostic mailbox initialization */
    rm->diag_status = O2P_DMBOX_STATUS_NONE;
    rm->diag_pending = false;

    /* Crash retention initialization */
    rm->crash_reason = O2P_CRASH_NONE;
    rm->crash_build_id = g_o2p_build_id;

    /* Arbitrary code execution mailbox */
    rm->exec_cmd = 0u;
    rm->exec_len = 0u;
    rm->exec_param_hi = 0u;
    rm->exec_param_lo = 0u;
    rm->exec_timeout_ms = 50u;
    rm->exec_status = O2P_EXEC_STATUS_NONE;
    rm->exec_result_hi = 0u;
    rm->exec_result_lo = 0u;
    for (unsigned i = 0; i < O2P_REG_EXEC_CODE_COUNT; i++) {
        rm->exec_code[i] = 0u;
    }
    rm->exec_pending = false;
#endif
}

#if O2P_DEBUG_ENABLE
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
    } else if (o2p_reset_cause() & (1u << 5)) {
        /* IWDGRSTF set: independent watchdog timeout reset.
         * Report IWDG reason and the last sampler breadcrumb from BKP3R. */
        rm->crash_reason = O2P_CRASH_IWDG;
        rm->crash_pc = 0u;
        rm->crash_lr = 0u;
        rm->crash_detail = o2p_crash_read_reg(3);
        rm->crash_build_id = (uint32_t)O2P_BUILD_ID;
    } else {
        rm->crash_reason = O2P_CRASH_NONE;
    }
#else
    (void)rm;
#endif
}
#endif

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

/* Containment is what dispatches a write; OVERLAP is what refuses one.
 *
 * The two are not the same test, and the difference was wire-visible: a write
 * that straddles a mailbox boundary is contained in nothing, so it fell past
 * every branch to the config-block check and was refused as ILLEGAL_ADDRESS.
 * The addresses are perfectly legal - the LENGTH is what makes the frame
 * malformed, which is ILLEGAL_VALUE, and is what these blocks promise for any
 * write that touches them without matching their exact shape. Nothing was
 * ever written by such a frame; only the exception code was wrong, and a
 * master that distinguishes "no such register" from "bad request" was told
 * the first when it should have heard the second. */
static bool overlaps_block(uint16_t addr, uint16_t count, uint16_t base, uint16_t n)
{
    return (uint32_t)addr < (uint32_t)base + n && (uint32_t)addr + count > base;
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
                               ? O2P_CAL_STATE_NO_ZERO : 0u) |
                          /* Only meaningful once an air point exists: with no
                           * point there is nothing whose provenance to
                           * qualify, and AIR_DEFAULT already reports that. */
                          ((rm->cfg.cal_air_na != 0 &&
                            rm->cfg.cal_bias_verified == 0u)
                               ? O2P_CAL_STATE_BIAS_UNVERIFIED : 0u));
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
    case O2P_REG_BUILD_ID_HI:  return (uint16_t)((g_o2p_build_id >> 16) & 0xFFFFu);
    case O2P_REG_BUILD_ID_LO:  return (uint16_t)(g_o2p_build_id & 0xFFFFu);
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

#if O2P_DEBUG_ENABLE
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

/* Reads serve the snapshot the last trigger took. Nothing here dereferences a
 * target address - that happens once, at trigger time, in peek_copy(). */
static uint16_t read_peekw(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_PEEKW_ADDR_HI: return (uint16_t)(rm->peekw_addr >> 16);
    case O2P_REG_PEEKW_ADDR_LO: return (uint16_t)(rm->peekw_addr & 0xFFFFu);
    case O2P_REG_PEEKW_WORDS:   return rm->peekw_words_req;
    case O2P_REG_PEEKW_STATUS:  return rm->peekw_status;
    case O2P_REG_PEEKW_SEQ:     return rm->peekw_seq;
    default: break;
    }
    /* in_block() has already confined `a` to the block, so the index is below
     * 2 * O2P_PEEKW_WORDS_MAX. Checked again anyway: running off this array
     * would publish a neighbouring field of the regmap as target memory. */
    if (a < O2P_REG_PEEKW_DATA) {
        return O2P_U16_INVALID;
    }
    unsigned i = (unsigned)(a - O2P_REG_PEEKW_DATA);
    if (i >= 2u * O2P_PEEKW_WORDS_MAX) {
        return O2P_U16_INVALID;
    }
    uint32_t w = rm->peekw_words[i / 2u];
    return (i & 1u) ? (uint16_t)(w & 0xFFFFu) : (uint16_t)(w >> 16);
}

/* ---- Poke mailbox + wide poke reads (2026-09-11, FW_VERSION 0x0012) ----
 *
 * Everything reads back what the last trigger HELD - address, word count and
 * the payload - plus the outcome in STATUS. That is the write side's answer
 * to "did it take": the payload registers echo what was sent before any
 * peek is aimed at the target, so a master can tell a refused poke (status,
 * nothing stored) from a served one (status OK, payload held, memory
 * changed) without a second guess. */
static uint16_t read_poke(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_POKE_ADDR_HI: return rm->poke_addr_hi;
    case O2P_REG_POKE_ADDR_LO: return rm->poke_addr_lo;
    case O2P_REG_POKE_WORDS:   return rm->poke_words_held;
    case O2P_REG_POKE_STATUS:  return rm->poke_status;
    default: break;
    }
    if (a < O2P_REG_POKE_W0_HI || a > O2P_REG_POKE_W3_LO) {
        return O2P_U16_INVALID;
    }
    unsigned i = (unsigned)(a - O2P_REG_POKE_W0_HI);
    uint32_t w = rm->poke_words[i / 2u];
    return (i & 1u) ? (uint16_t)(w & 0xFFFFu) : (uint16_t)(w >> 16);
}

static uint16_t read_pokew(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_POKEW_ADDR_HI: return (uint16_t)(rm->pokew_addr >> 16);
    case O2P_REG_POKEW_ADDR_LO: return (uint16_t)(rm->pokew_addr & 0xFFFFu);
    case O2P_REG_POKEW_WORDS:   return rm->pokew_words_req;
    case O2P_REG_POKEW_STATUS:  return rm->pokew_status;
    case O2P_REG_POKEW_SEQ:     return rm->pokew_seq;
    default: break;
    }
    if (a < O2P_REG_POKEW_DATA ||
        a >= O2P_REG_POKEW_DATA + 2u * O2P_PEEKW_WORDS_MAX) {
        return O2P_U16_INVALID;
    }
    unsigned i = (unsigned)(a - O2P_REG_POKEW_DATA);
    uint32_t w = rm->pokew_words[i / 2u];
    return (i & 1u) ? (uint16_t)(w & 0xFFFFu) : (uint16_t)(w >> 16);
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

static uint16_t read_exec(const o2p_regmap_t *rm, uint16_t a)
{
    switch (a) {
    case O2P_REG_EXEC_CMD:        return rm->exec_cmd;
    case O2P_REG_EXEC_LEN:        return rm->exec_len;
    case O2P_REG_EXEC_PARAM_HI:   return rm->exec_param_hi;
    case O2P_REG_EXEC_PARAM_LO:   return rm->exec_param_lo;
    case O2P_REG_EXEC_TIMEOUT_MS: return rm->exec_timeout_ms;
    case O2P_REG_EXEC_STATUS:     return rm->exec_status;
    case O2P_REG_EXEC_RESULT_HI:  return rm->exec_result_hi;
    case O2P_REG_EXEC_RESULT_LO:  return rm->exec_result_lo;
    default: break;
    }
    if (a >= O2P_REG_EXEC_CODE_BASE && a < O2P_REG_EXEC_CODE_BASE + O2P_REG_EXEC_CODE_COUNT) {
        return rm->exec_code[a - O2P_REG_EXEC_CODE_BASE];
    }
    return O2P_U16_INVALID;
}
#endif

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
    /* The stored bytes, not the ratio in force: a pattern outside the window
     * reads back as itself, so an operator can see it, while the sampler
     * scales by the netlist. */
    case O2P_REG_VIN_DIV_X1000:   return o2p_cfg_vin_div_x1000(c);
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
#if O2P_DEBUG_ENABLE
    if (in_block(addr, count, O2P_REG_PEEK_BASE, O2P_REG_PEEK_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_peek(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_PEEKW_BASE, O2P_REG_PEEKW_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_peekw(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_POKE_BASE, O2P_REG_POKE_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_poke(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
    if (in_block(addr, count, O2P_REG_POKEW_BASE, O2P_REG_POKEW_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_pokew(rm, (uint16_t)(addr + i));
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
    if (in_block(addr, count, O2P_REG_EXEC_BASE, O2P_REG_EXEC_COUNT)) {
        for (uint16_t i = 0; i < count; i++) {
            out[i] = read_exec(rm, (uint16_t)(addr + i));
        }
        return 0u;
    }
#endif
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
    /* Both halves clear cal_bias_verified, for the same reason cal_zero_taken
     * is SET on the zero path above: a constant and its provenance must move
     * together. A hand-written air point was not verified by this firmware
     * against anything - whatever the previous point's provenance was, it does
     * not describe this one. Without this, a Modbus write inherits the old
     * bit and CAL_STATE reports a bias-verified calibration that nothing
     * verified, which is worse than having no bit at all. Found by review,
     * 2026-09-09. */
    case O2P_REG_CAL_AIR_NA_HI:
        c->cal_air_na = (int32_t)(((uint32_t)v << 16) |
                                  ((uint32_t)c->cal_air_na & 0xFFFFu));
        c->cal_bias_verified = 0u;
        break;
    case O2P_REG_CAL_AIR_NA_LO:
        c->cal_air_na = (int32_t)(((uint32_t)c->cal_air_na & 0xFFFF0000u) | v);
        c->cal_bias_verified = 0u;
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
    case O2P_REG_VIN_DIV_X1000:
        /* The only place the window is enforced, because o2p_config_valid()
         * deliberately does not look at this field (regmap.h). 0 puts the
         * probe back on the netlist divider. */
        if (v != O2P_VIN_DIV_X1000_NETLIST && !o2p_vin_div_x1000_in_window(v)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        o2p_cfg_set_vin_div_x1000(c, v);
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

#if O2P_DEBUG_ENABLE
/* ---- memory peek, shared by the 4-word mailbox and the wide block ----
 *
 * ONE validator and ONE copy loop for both blocks. On a Cortex-M0+ there is no
 * configurable BusFault: a misaligned load, an unmapped address or an unclocked
 * peripheral is a HardFault, and on a potted board that is a probe that resets
 * every time somebody asks it a debugging question. */

#ifdef O2P_HOST_TEST
uint32_t (*o2p_peek_host_read)(uint32_t addr) = NULL;
int o2p_peek_host_irq_depth = 0;
/* The parity seam's defaults: the factory option byte (bit 22 set, parity
 * check DISABLED) and the .data/.bss bounds of the 2026-09-10 env:o2probe map.
 * The bounds are test data, not the image's - the image reads its own. */
#define O2P_PEEK_HOST_OPTR_FACTORY 0xFFFFFFFFu
#define O2P_PEEK_HOST_SDATA        0x20000010u
#define O2P_PEEK_HOST_EDATA        0x20000088u
#define O2P_PEEK_HOST_SBSS         0x20000088u
#define O2P_PEEK_HOST_EBSS         0x2000058Cu
uint32_t o2p_peek_host_optr  = O2P_PEEK_HOST_OPTR_FACTORY;
uint32_t o2p_peek_host_sdata = O2P_PEEK_HOST_SDATA;
uint32_t o2p_peek_host_edata = O2P_PEEK_HOST_EDATA;
uint32_t o2p_peek_host_sbss  = O2P_PEEK_HOST_SBSS;
uint32_t o2p_peek_host_ebss  = O2P_PEEK_HOST_EBSS;
void o2p_peek_host_parity_reset(void)
{
    o2p_peek_host_optr  = O2P_PEEK_HOST_OPTR_FACTORY;
    o2p_peek_host_sdata = O2P_PEEK_HOST_SDATA;
    o2p_peek_host_edata = O2P_PEEK_HOST_EDATA;
    o2p_peek_host_sbss  = O2P_PEEK_HOST_SBSS;
    o2p_peek_host_ebss  = O2P_PEEK_HOST_EBSS;
}
static uint32_t peek_optr(void)
{
    return o2p_peek_host_optr;
}
static void peek_written(uint32_t *sdata, uint32_t *edata, uint32_t *sbss, uint32_t *ebss)
{
    *sdata = o2p_peek_host_sdata;
    *edata = o2p_peek_host_edata;
    *sbss = o2p_peek_host_sbss;
    *ebss = o2p_peek_host_ebss;
}
typedef int o2p_peek_irq_t;
static o2p_peek_irq_t peek_irq_save(void)
{
    o2p_peek_host_irq_depth++;
    return 0;
}
static void peek_irq_restore(o2p_peek_irq_t s)
{
    (void)s;
    o2p_peek_host_irq_depth--;
}
static uint32_t peek_load(uint32_t a)
{
    return (o2p_peek_host_read != NULL) ? o2p_peek_host_read(a) : (a ^ 0xA5A5A5A5u);
}
/* The peek-space address of the destination buffer. On the target it is just
 * the pointer; on the host the destination is a plain object whose pointer is
 * NOT in the peeked address space, so a test that wants to exercise the
 * source/destination OVERLAP (N1) supplies the address its o2p_peek_host_read
 * hook would map onto dst. NULL means "no overlap possible", which keeps the
 * ascending copy the address-derived oracle tests already exercise. */
uint32_t (*o2p_peek_host_dst_addr)(const uint32_t *dst) = NULL;
static uint32_t peek_dst_addr(const uint32_t *dst)
{
    return (o2p_peek_host_dst_addr != NULL) ? o2p_peek_host_dst_addr(dst) : 0u;
}
/* The poke's seams (2026-09-11): every store a poke would make, and the
 * poke-space address of the payload buffer it copies from. NULL defaults -
 * a suite that installs neither sees stores vanish and no overlap, which
 * is the pre-poke behaviour and fine for every suite but the poke's own. */
void (*o2p_peek_host_store)(uint32_t addr, uint32_t val) = NULL;
uint32_t (*o2p_peek_host_src_addr)(const uint32_t *src) = NULL;
static void peek_store(uint32_t a, uint32_t v)
{
    if (o2p_peek_host_store != NULL) {
        o2p_peek_host_store(a, v);
    }
}
static uint32_t poke_src_addr(const uint32_t *src)
{
    return (o2p_peek_host_src_addr != NULL) ? o2p_peek_host_src_addr(src) : 0u;
}
#else
/* ldscript/o2probe_app.ld (ST's stock names). */
extern const uint8_t _sdata[], _edata[], _sbss[], _ebss[];
static inline uint32_t peek_optr(void)
{
    return FLASH->OPTR;
}
static inline void peek_written(uint32_t *sdata, uint32_t *edata, uint32_t *sbss, uint32_t *ebss)
{
    *sdata = (uint32_t)(uintptr_t)_sdata;
    *edata = (uint32_t)(uintptr_t)_edata;
    *sbss = (uint32_t)(uintptr_t)_sbss;
    *ebss = (uint32_t)(uintptr_t)_ebss;
}
typedef uint32_t o2p_peek_irq_t;
/* PRIMASK is saved and RESTORED, not unconditionally re-enabled, so this stays
 * correct if a caller is ever already masked. */
static inline o2p_peek_irq_t peek_irq_save(void)
{
    uint32_t s = __get_PRIMASK();
    __disable_irq();
    return s;
}
static inline void peek_irq_restore(o2p_peek_irq_t s)
{
    __set_PRIMASK(s);
}
static inline uint32_t peek_load(uint32_t a)
{
    return *(const volatile uint32_t *)a;
}
/* dst is g_rm's own snapshot buffer, in SRAM: its address IS its peek-space
 * address, so the overlap test below compares like with like. */
static inline uint32_t peek_dst_addr(const uint32_t *dst)
{
    return (uint32_t)(uintptr_t)dst;
}
/* The poke's target side: a store is a plain volatile store, and src is
 * g_rm's own payload buffer, in SRAM, whose address IS its poke-space
 * address - the same like-with-like rule as peek_dst_addr above. */
static inline void peek_store(uint32_t a, uint32_t v)
{
    *(volatile uint32_t *)a = v;
}
static inline uint32_t poke_src_addr(const uint32_t *src)
{
    return (uint32_t)(uintptr_t)src;
}
#endif

/* The readable region containing `target`, as the address of its LAST aligned
 * word. Exactly PLAN-MODBUS-DEBUG.md 3.1: SRAM, flash, the three words of the
 * 96-bit UID and the one flash-size word - nothing with a read side effect and
 * none of the unmapped holes between them. The flash-size register is a region
 * of one word and the UID of three, which is why a burst's length is part of
 * the check rather than an afterthought.
 *
 * FLASH IS ONLY THE LOADER AND THE RUN SLOT (pages 0..33, 0x08000000..
 * O2P_APP_BASE + O2P_APP_BYTES), NOT the whole 128 KiB. N4 mitigation
 * (independent review, 2026-09-10): a flash doubleword left half-programmed by
 * a power loss carries a bad ECC, and reading it raises a double-error NMI
 * (RM0444 Rev 6 3.3.3, p. 74: "When two errors are detected ... a NMI is
 * generated"; 3.3.6, p. 77: "The address concerned might trigger an ECC
 * interrupt or an NMI when accessed later on"). The NMI vector is the default
 * infinite loop, so such a peek hangs until the IWDG resets a potted probe.
 * There is no recoverable read on a Cortex-M0+: the NMI resumes at the stacked
 * PC - the faulting load - and nothing in RM0444 lets a handler step past it,
 * while 3.3.3 warns a re-read "may not generate an ECC error if the data is
 * still present in the current buffer", so recovery is not even deterministic.
 * The three flash areas a power loss can tear are all written at RUN TIME -
 * staging during a push, the boot descriptor when a transfer verifies, the
 * config pages on COMMIT - and none is inside the loader or run slot, which
 * are written only by the loader while the application is not running. So the
 * peek is confined to those two, where the running image is by definition
 * intact enough to execute. A peek of staging, the descriptor or config now
 * answers ERR_RANGE. This is a mitigation, not a proof the excluded pages
 * would fault: no torn page was ever read on a probe. */
static bool peek_region_last(uint32_t target, uint32_t *last)
{
    if (target >= 0x20000000u && target <= 0x20008FFCu) {
        *last = 0x20008FFCu;
    } else if (target >= O2P_BOOT_BASE &&
               target <= O2P_APP_BASE + O2P_APP_BYTES - 4u) {
        *last = O2P_APP_BASE + O2P_APP_BYTES - 4u;
    } else if (target >= 0x1FFF7590u && target <= 0x1FFF7598u) {
        *last = 0x1FFF7598u;
    } else if (target == 0x1FFF75E0u) {
        *last = 0x1FFF75E0u;
    } else {
        return false;
    }
    return true;
}

/* Whether [target, target + 4*words) lies wholly inside the written span
 * [lo, end), and if so its last word. lo is rounded up and end down to whole
 * words, so a span the linker did not align cannot admit a partial word. An
 * empty or inverted span admits nothing. `target` is already aligned. */
static bool peek_span_in(uint32_t target, uint16_t words, uint32_t lo, uint32_t end,
                         uint32_t *last)
{
    lo = (lo + 3u) & ~3u;
    end &= ~3u;
    if (end <= lo || target < lo || target >= end) {
        return false;
    }
    if ((uint32_t)words - 1u > (end - 4u - target) / 4u) {
        return false;
    }
    *last = end - 4u;
    return true;
}

/* ---- The SRAM parity gate (FW_VERSION 0x000F, O2P_PEEK_ERR_PARITY) ----
 *
 * WHY. With the RAM_PARITY_CHECK option bit enabled, reading SRAM that has not
 * been written since power-on can raise NMI plus a HardFault (RM0444 Rev 6,
 * 2.3, p. 67, whose note advises initialising "the whole SRAM at the beginning
 * of the code, to avoid getting parity errors when reading non-initialized
 * locations"). This firmware does not, and must not: the bottom 16 bytes are
 * SHARED, the boot hand-off that has to survive a warm reset
 * (ldscript/o2probe_app.ld). Both peek blocks could name any of the 36 KiB.
 *
 * WHAT IS ADMITTED while the bit reads 0: a burst wholly inside .data or .bss,
 * or inside both when they abut. Startup writes every word of both before
 * main() - CopyDataInit and FillZerobss in framework-stm32cubeg0's
 * startup_stm32g071xx.s store whole words, 4 bytes a step, between the
 * linker's ALIGN(4) bounds - which is what makes their parity bits valid.
 *
 * WHAT IS NOT, deliberately: SHARED, the heap gap, and THE STACK. The obvious
 * "SP up to _estack" is not proven written: a frame reserves space with one
 * SUB and writes only what the code assigns, so padding, unused array tails
 * and never-assigned locals stay as power-on left them. Every symbol `peek`
 * resolves from the ELF is in .data, .bss or flash, so that is what is kept.
 *
 * FLASH IS NOT GATED. RAM_PARITY_CHECK covers SRAM only; flash carries ECC
 * (RM0444 3.3.3, p. 74), and an erased flash word is written state as far as
 * that is concerned.
 *
 * UNEVALUABLE INPUT FAILS CLOSED. The bit's enabled state is 0, so an OPTR
 * that read as zero - the flash interface clock off, say - restricts peeks
 * rather than admitting them. FLASHEN resets to 1 (RCC_AHBENR 0x0000 0100,
 * RM0444 5.4.14, p. 193) and nothing in src/ clears it.
 *
 * PRECONDITION: FLASH_OPTR holds the LOADED option bytes. It would not after
 * a write to FLASH_OPTR that had not yet been through OBL_LAUNCH or a reset
 * (RM0444 3.4.2, p. 84), and nothing in src/ writes FLASH_OPTR, FLASH_OPTKEYR
 * or OBL_LAUNCH - checked 2026-09-10 by grepping src/ for OPTR, OPTKEY,
 * OPTSTRT, OBL_LAUNCH, WRP and RDP.
 *
 * REASONED, NOT MEASURED: whether this image boots at all with the bit
 * enabled. RM0444 Table 7 (p. 66) gives the G071 32 KiB of SRAM with parity on
 * against 36 KiB off, and the linker puts _estack at 0x20009000, in the 4 KiB
 * that would be gone. No probe has had the bit set, and none should. This
 * gate is for the image that does run, and costs one register load per
 * trigger. */
#define O2P_PEEK_SRAM_FIRST 0x20000000u
#define O2P_PEEK_SRAM_LAST  0x20008FFCu
/* FLASH_OPTR bit 22, RM0444 3.7.8. Spelled out so the host build can use it;
 * the target build holds it to the CMSIS definition. */
#define O2P_OPTR_RAM_PARITY_CHECK (1uL << 22)
#ifndef O2P_HOST_TEST
_Static_assert(O2P_OPTR_RAM_PARITY_CHECK == FLASH_OPTR_RAM_PARITY_CHECK,
               "RAM_PARITY_CHECK is FLASH_OPTR bit 22 in stm32g071xx.h");
#endif

static bool peek_sram_parity_enabled(void)
{
    return (peek_optr() & O2P_OPTR_RAM_PARITY_CHECK) == 0u;
}

static uint16_t peek_check(uint32_t target, uint16_t words, uint32_t *last)
{
    if ((target & 3u) != 0u) {
        return O2P_PEEK_ERR_ALIGN;
    }
    if (!peek_region_last(target, last)) {
        return O2P_PEEK_ERR_RANGE;
    }
    if ((uint32_t)words - 1u > (*last - target) / 4u) {
        return O2P_PEEK_ERR_RANGE;
    }
    /* Read at trigger time, every time: there is no cached "parity is off"
     * to go stale. */
    if (target >= O2P_PEEK_SRAM_FIRST && target <= O2P_PEEK_SRAM_LAST &&
        peek_sram_parity_enabled()) {
        uint32_t sdata = 0u, edata = 0u, sbss = 0u, ebss = 0u;
        peek_written(&sdata, &edata, &sbss, &ebss);
        bool ok;
        if (edata == sbss) {
            ok = peek_span_in(target, words, sdata, ebss, last);
        } else {
            /* A section placed between them was not written by startup, so a
             * burst may not cross the gap. */
            ok = peek_span_in(target, words, sdata, edata, last) ||
                 peek_span_in(target, words, sbss, ebss, last);
        }
        if (!ok) {
            return O2P_PEEK_ERR_PARITY;
        }
    }
    return O2P_PEEK_OK;
}

/* ---- The poke validator (FW_VERSION 0x0012, 2026-09-11) ----
 *
 * WHAT IT ADMITS, and each exclusion's reason:
 *
 * SRAM, the .data/.bss written span, and NOTHING ELSE. The read-side parity
 * gate (peek_check above) admits that span because those are the words whose
 * parity startup made valid; the poke admits the SAME span for the OPPOSITE
 * parity reason - RM0444 2.3, p. 67, computes and stores a word's parity
 * "when writing into the SRAM", so a store cannot hit the never-written NMI
 * a read can, and any SRAM word would be safe to WRITE. The span is kept
 * anyway, for two reasons that are policy, not parity:
 *   1. SYMMETRY: whatever the poke may write, the peek may read back, so a
 *      master verifies a poke with the read it already has. Admitting more
 *      write space than read space would be a write whose only verification
 *      is its own status word.
 *   2. THE SPAN IS THE LINKER'S PROMISE: .data and .bss are the words the
 *      image can NAME - "a variable" - which is what a poke is for. Outside
 *      it sits SHARED (the bottom 16 bytes, the boot hand-off that must
 *      survive a warm reset - ldscript/o2probe_app.ld), the stack an ISR is
 *      running on, and never-written SRAM whose parity the poke would fix
 *      but whose CONTENT nothing reasoned about. Writing those with a casual
 *      poke is how a debug tool becomes a potted brick.
 *
 * FLASH IS REFUSED, as the peek's own N4 comment reasons at the wide-block
 * bound above: a runtime flash write tears pages (bad ECC, NMI, a hung
 * probe), and the only sanctioned runtime flash writer in this firmware is
 * the updater's, which stages and commits through its own protocol.
 *
 * PERIPHERALS AND SYSTEM REGISTERS ARE REFUSED, including SCB AIRCR
 * (0xE000ED0C): the peek reads them nowhere either (peek_region_last admits
 * SRAM, the loader and run slot, the UID and the flash-size word only), and a
 * peripheral write is an arbitrary side effect - an SYSRESETREQ through a
 * poke would be an undocumented reset path competing with the ones the
 * firmware owns. A deliberate bench-reset op, if wanted, is a new register
 * with its own review, not an accident of this one.
 *
 * No ERR_PARITY code exists for the poke (regmap.h's O2P_POKE_* comment):
 * a store creates valid parity, so the parity failure mode simply cannot
 * happen on this path. */
static uint16_t poke_check(uint32_t target, uint16_t words, uint32_t *last)
{
    if ((target & 3u) != 0u) {
        return O2P_POKE_ERR_ALIGN;
    }
    /* SRAM bound first, exactly the peek's: nothing above 0x20008FFC and
     * nothing below 0x20000000, so flash, peripherals, the UID and the
     * flash-size word all fail here before any span arithmetic. */
    if (target < O2P_PEEK_SRAM_FIRST || target > O2P_PEEK_SRAM_LAST) {
        return O2P_POKE_ERR_RANGE;
    }
    if ((uint32_t)words - 1u > (O2P_PEEK_SRAM_LAST - target) / 4u) {
        return O2P_POKE_ERR_RANGE;
    }
    *last = O2P_PEEK_SRAM_LAST;
    /* The same written-span logic the read uses, unconditionally: the read
     * consults it only under the parity bit, the poke always, because for the
     * poke the span is the whole policy (see the block comment above). */
    uint32_t sdata = 0u, edata = 0u, sbss = 0u, ebss = 0u;
    peek_written(&sdata, &edata, &sbss, &ebss);
    bool ok;
    if (edata == sbss) {
        ok = peek_span_in(target, words, sdata, ebss, last);
    } else {
        /* A section placed between .data and .bss is outside the span the
         * linker promised, and a burst may not cross the gap in it. */
        ok = peek_span_in(target, words, sdata, edata, last) ||
             peek_span_in(target, words, sbss, ebss, last);
    }
    if (!ok) {
        return O2P_POKE_ERR_RANGE;
    }
    return O2P_POKE_OK;
}

/* Copy a burst peek_check() has passed into dst[0..words), and 0xFFFFFFFF into
 * the rest of dst. Returns false if any word was not copied, which the caller
 * turns into a refusal rather than an OK with holes in it.
 *
 * OVERLAP-SAFE, memmove-style. dst is g_rm's own peekw_words/peek_words, in
 * SRAM, so a peek of SRAM can name the very words being copied into. An
 * ascending copy reads dst[n] = *(target + 4n): when dst sits ABOVE the source
 * (dst_addr > target) a lower store clobbers a source word a higher load has
 * not read yet, and the burst comes back corrupt with STATUS still OK. N1
 * (independent review, 2026-09-10): an overlapping `peek g_rm` returned four
 * zeros as if measured. The fix is memmove's rule - walk high-to-low when the
 * destination is above the source, low-to-high otherwise - which reads every
 * source word before any store can reach it. Disjoint bursts (the normal case)
 * are correct either way.
 *
 * INTERRUPTS ARE MASKED FOR THE COPY, AND ONLY FOR THE COPY. The trigger is
 * served from the main loop, so the sampler cannot run mid-copy anyway; what
 * the mask adds is the two interrupts that write memory - SysTick advancing
 * the millisecond count, and USART1 moving its receive state. Without it a
 * struct holding either can come back torn between two words, and a torn
 * struct is a set of plausible values that were never true together. The
 * whole point of taking the burst in one trigger is that it is one moment.
 *
 * The cost is bounded by the character time, not by taste. USART1 runs
 * without its FIFO, so RDR holds one character and a second one completing
 * inside the mask would overrun it. At 115200 8E1, the fastest rate this
 * firmware offers, a character is 95 us. The masked loop is one load and one
 * store per word plus the loop counter either way - the direction choice is a
 * single compare made OUTSIDE the mask - so the ~17 clock cycles a word
 * estimated from the 2026-09-10 env:o2probe disassembly are unchanged by N1's
 * fix. A 30-word burst is therefore about 32 us at 16 MHz with zero flash wait
 * states (mcu.c), a third of a character - an ESTIMATE from the disassembly,
 * NOT a measurement on the board, and the reason O2P_PEEKW_WORDS_MAX is not
 * 60. In practice nothing should arrive in the window at all: the master is
 * waiting for this very reply.
 *
 * Validation stays outside the mask - it is arithmetic, and the mask is for
 * what can change underneath. The per-word bound below repeats peek_check()
 * because the cost of it being wrong is a HardFault on a potted board; it runs
 * before the mask so the masked window holds only the loads and stores. */
static bool peek_copy(uint32_t target, uint16_t words, uint32_t last,
                      uint32_t *dst, unsigned dst_len)
{
    /* The largest prefix [0, copyable) whose every word is in range. Addresses
     * ascend from `target` (the region's lowest), so if word k is out of range
     * every later word is too: a prefix is all peek_check() can have passed,
     * and all this may dereference. */
    unsigned copyable = ((unsigned)words < dst_len) ? (unsigned)words : dst_len;
    while (copyable > 0u) {
        uint32_t a = target + (uint32_t)(copyable - 1u) * 4u;
        if (a >= target && a <= last) {
            break;
        }
        copyable--;
    }
    bool descending = peek_dst_addr(dst) > target;
    o2p_peek_irq_t s = peek_irq_save();
    if (descending) {
        for (unsigned i = copyable; i-- > 0u; ) {
            dst[i] = peek_load(target + (uint32_t)i * 4u);
        }
    } else {
        for (unsigned i = 0u; i < copyable; i++) {
            dst[i] = peek_load(target + (uint32_t)i * 4u);
        }
    }
    peek_irq_restore(s);
    bool complete = (copyable == (unsigned)words);
    for (unsigned n = copyable; n < dst_len; n++) {
        dst[n] = 0xFFFFFFFFu;
    }
    return complete;
}

/* Store a burst poke_check() has passed from src[0..words) into target.
 * The WRITE mirror of peek_copy(), inheriting its two properties:
 *
 * OVERLAP-SAFE, memmove-style. src is g_rm's own payload buffer, in SRAM, so
 * a poke can name the very words being copied from. The roles are the
 * REVERSE of peek_copy's - there the destination was the regmap buffer and
 * the source the target; here the destination IS the target and the source
 * the payload - so the walk is the reverse too: when the payload sits BELOW
 * the target (src_addr < target, destination above source) an ascending
 * store clobbers a payload word a later load has not read yet, and the poke
 * writes corrupted values with STATUS still OK - the write-side image of N1
 * (independent review, 2026-09-10), whose read-side fix this mirrors. Walk
 * high-to-low when the payload is below the target, low-to-high otherwise;
 * a src_addr of 0 (the host default, "no overlap possible") walks ascending,
 * the pre-poke order. Disjoint pokes (the normal case) are correct either
 * way.
 *
 * INTERRUPTS ARE MASKED FOR THE STORES, AND ONLY THE STORES - the same
 * argument as peek_copy, run the other way: there the mask kept a torn
 * struct from being READ as one moment; here it keeps a struct an ISR reads
 * from being seen HALF-POKED, old and new values plausible together. The
 * same 95 us character bound at 115200 8E1 applies, and the same ~17 clock
 * cycles a word estimated from the 2026-09-10 disassembly, so a 30-word poke
 * is about 32 us at 16 MHz - an ESTIMATE, not a measurement, and the reason
 * the burst ceiling stays O2P_PEEKW_WORDS_MAX.
 *
 * Validation stays outside the mask - it is arithmetic, and the per-word
 * bound repeats poke_check() because the cost of it being wrong is a store
 * into a region the policy above excluded. */
static bool poke_store(uint32_t target, uint16_t words, uint32_t last,
                       const uint32_t *src)
{
    /* The largest prefix [0, storable) whose every word is in range, so this
     * never dereferences past the SRAM bound poke_check() enforced. */
    unsigned storable = (unsigned)words;
    while (storable > 0u) {
        uint32_t a = target + (uint32_t)(storable - 1u) * 4u;
        if (a >= target && a <= last) {
            break;
        }
        storable--;
    }
    bool descending;
    {
        uint32_t src_a = poke_src_addr(src);
        /* Destination above source (memmove's rule, see the block comment):
         * walk high-to-low so every payload word is read before any store
         * can reach it. 0 = no overlap the host knows of: ascending. */
        descending = (src_a != 0u) && (src_a < target);
    }
    o2p_peek_irq_t s = peek_irq_save();
    if (descending) {
        for (unsigned i = storable; i-- > 0u; ) {
            peek_store(target + (uint32_t)i * 4u, src[i]);
        }
    } else {
        for (unsigned i = 0u; i < storable; i++) {
            peek_store(target + (uint32_t)i * 4u, src[i]);
        }
    }
    peek_irq_restore(s);
    return storable == (unsigned)words;
}
#endif /* O2P_DEBUG_ENABLE */

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
                /* UNVALIDATED, DELIBERATELY (accepted 2026-09-11, Fab's call
                 * on review P2-5 - the liberal option): the volatile gains
                 * ride in with no range check and are SHARED with the
                 * committed tip loop (heater_ctl.c - the record had no room
                 * for a flash-backed pair). The bounds that hold the result
                 * are HEATER_MAX_DUTY and the 82.00 C tip clamp: a nonsense
                 * gain can mis-tune the loop but cannot move those. */
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

#if O2P_DEBUG_ENABLE
    /* Memory peek mailbox: atomic FC16 trigger write required.
     *
     * Two accepted forms, both starting exactly at O2P_REG_PEEK_BASE:
     *   2 registers - address hi/lo, burst length defaults to 4 words;
     *   3 registers - address hi/lo plus the requested word count, 1..4.
     *
     * The third register is how the 1..4-word burst the register-map document
     * advertises actually reaches the firmware. Without it every request was a
     * fixed 4-word burst, and the length could only be validated after the
     * fact by the client, which is not validation. A count outside 1..4 is a
     * malformed trigger and is refused like any other, leaving the previous
     * result and status untouched rather than half-overwritten. */
    if (in_block(addr, count, O2P_REG_PEEK_BASE, O2P_REG_PEEK_COUNT)) {
        if (addr != O2P_REG_PEEK_BASE || (count != 2u && count != 3u)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint16_t words = (count == 3u) ? in[2] : 4u;
        if (words < 1u || words > 4u) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        rm->peek_addr_hi = in[0];
        rm->peek_addr_lo = in[1];
        uint32_t target = ((uint32_t)in[0] << 16) | (uint32_t)in[1];

        /* The validator and the copy are shared with the wide block, so the
         * two cannot drift into different ideas of what is safe to
         * dereference. Behaviour on the wire is what 0x000C shipped: status
         * and address are always replaced by a well-formed trigger, and every
         * word of a refused burst reads 0xFFFFFFFF. */
        uint32_t last = 0u;
        uint16_t st = peek_check(target, words, &last);
        if (st == O2P_PEEK_OK && !peek_copy(target, words, last, rm->peek_words, 4u)) {
            st = O2P_PEEK_ERR_RANGE;
        }
        if (st != O2P_PEEK_OK) {
            for (unsigned w = 0; w < 4u; w++) rm->peek_words[w] = 0xFFFFFFFFu;
        }
        rm->peek_status = st;
        return 0u;
    }

    /* Wide peek block, 0x0100. The contract is in regmap.h; in short, the
     * SHAPE is checked first and a wrong shape changes nothing at all, then
     * a well-formed trigger always replaces the held result - with the data,
     * or with the reason there is none. */
    if (in_block(addr, count, O2P_REG_PEEKW_BASE, O2P_REG_PEEKW_COUNT)) {
        if (addr != O2P_REG_PEEKW_BASE || count != 3u) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint16_t words = in[2];
        if (words < 1u || words > O2P_PEEKW_WORDS_MAX) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint32_t target = ((uint32_t)in[0] << 16) | (uint32_t)in[1];
        uint32_t last = 0u;
        uint16_t st = peek_check(target, words, &last);
        if (st == O2P_PEEK_OK &&
            !peek_copy(target, words, last, rm->peekw_words, O2P_PEEKW_WORDS_MAX)) {
            st = O2P_PEEK_ERR_RANGE;
        }
        if (st != O2P_PEEK_OK) {
            for (unsigned w = 0; w < O2P_PEEKW_WORDS_MAX; w++) {
                rm->peekw_words[w] = 0xFFFFFFFFu;
            }
        }
        rm->peekw_addr = target;
        rm->peekw_words_req = words;
        rm->peekw_status = st;
        /* 0 stays "never triggered", so a reader comparing SEQ across its
         * chunks cannot mistake a wrap for the initial state. */
        rm->peekw_seq = (uint16_t)(rm->peekw_seq == 0xFFFFu ? 1u : rm->peekw_seq + 1u);
        return 0u;
    }

    /* Memory poke mailbox (2026-09-11, FW_VERSION 0x0012): the write
     * counterpart of the peek above. ONE FC16 starting exactly at
     * O2P_REG_POKE_ADDR_HI of exactly 3 + 2*words registers - the payload
     * rides the trigger frame, so the count and the word count in it must
     * agree, and any other shape (a lone STATUS write, a short frame, a
     * frame that starts mid-block) is exception 03 and changes NOTHING,
     * exactly the wide peek's contract one block up.
     *
     * A WELL-FORMED trigger always replaces the held state - address, word
     * count, payload and status - even when the poke is REFUSED: unlike a
     * refused peek (whose words read back as 0xFFFFFFFF so no half-result
     * looks measured), a refused poke's payload is not a result at all, it
     * is the request, and holding it lets the readback show exactly what was
     * attempted while the status says it never landed. Nothing was stored.
     */
    if (in_block(addr, count, O2P_REG_POKE_BASE, O2P_REG_POKE_COUNT)) {
        uint16_t words = (count >= 3u) ? in[2] : 0u;
        if (addr != O2P_REG_POKE_BASE || words < 1u || words > 4u ||
            count != (uint16_t)(3u + 2u * words)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint32_t target = ((uint32_t)in[0] << 16) | (uint32_t)in[1];
        for (unsigned w = 0; w < 4u; w++) {
            rm->poke_words[w] = (w < words)
                ? (((uint32_t)in[3u + 2u * w] << 16) | (uint32_t)in[4u + 2u * w])
                : 0u;
        }
        rm->poke_addr_hi = in[0];
        rm->poke_addr_lo = in[1];
        rm->poke_words_held = words;
        uint32_t last = 0u;
        uint16_t st = poke_check(target, words, &last);
        if (st == O2P_POKE_OK && !poke_store(target, words, last, rm->poke_words)) {
            st = O2P_POKE_ERR_RANGE;
        }
        rm->poke_status = st;
        return 0u;
    }

    /* Wide poke block (2026-09-11, FW_VERSION 0x0012): the poke counterpart
     * of the wide peek, same trigger discipline - ONE FC16 of exactly
     * 3 + 2*words registers at O2P_REG_POKEW_ADDR_HI, words 1..30, payload in
     * the frame. SEQ advances on every executed trigger and skips 0 on wrap,
     * so 0 keeps meaning "never triggered" for a reader comparing SEQ
     * across chunks. */
    if (in_block(addr, count, O2P_REG_POKEW_BASE, O2P_REG_POKEW_COUNT)) {
        uint16_t words = (count >= 3u) ? in[2] : 0u;
        if (addr != O2P_REG_POKEW_ADDR_HI || words < 1u ||
            words > O2P_PEEKW_WORDS_MAX ||
            count != (uint16_t)(3u + 2u * words)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint32_t target = ((uint32_t)in[0] << 16) | (uint32_t)in[1];
        for (unsigned w = 0; w < O2P_PEEKW_WORDS_MAX; w++) {
            rm->pokew_words[w] = (w < words)
                ? (((uint32_t)in[3u + 2u * w] << 16) | (uint32_t)in[4u + 2u * w])
                : 0u;
        }
        rm->pokew_addr = target;
        rm->pokew_words_req = words;
        uint32_t last = 0u;
        uint16_t st = poke_check(target, words, &last);
        if (st == O2P_POKE_OK && !poke_store(target, words, last, rm->pokew_words)) {
            st = O2P_POKE_ERR_RANGE;
        }
        rm->pokew_status = st;
        rm->pokew_seq = (uint16_t)(rm->pokew_seq == 0xFFFFu ? 1u : rm->pokew_seq + 1u);
        return 0u;
    }

    /* Sensor diagnostic mailbox */
    if (in_block(addr, count, O2P_REG_DMBOX_BASE, O2P_REG_DMBOX_COUNT)) {
        /* SHAPE, then BUSY, then everything that writes a register.
         *
         * A queued I2C opcode owns every result register, DIAG_STATUS
         * included, until main.c has run it. Up to FW_VERSION 0x000E a write
         * arriving in that window was refused by setting DIAG_STATUS to
         * ERR_BUSY - overwriting the queued command's PENDING with a status
         * that command never produced. The master that queued it polls for
         * "not PENDING", took ERR_BUSY as its answer, and stopped; its
         * command then ran and nobody read the result (review F2,
         * 2026-09-10, confirmed through this function).
         *
         * So the refusal says BUSY on the wire, to the master that was
         * refused, and nowhere else: exception 06, SERVER DEVICE BUSY, which
         * is what the Modbus specification has for "retry later". Not 03: a
         * refused master must be able to tell "your request is wrong" from
         * "the mailbox is taken", and 03 already means the first.
         *
         * The shape check stays first because it writes nothing and its
         * answer does not depend on the queue. Every check after BUSY may
         * write DIAG_STATUS (ERR_OPCODE), which is exactly why BUSY has to
         * come before them: while busy, a bad magic is refused as busy
         * rather than allowed to write ERR_OPCODE over PENDING. */
        if (addr != O2P_REG_DMBOX_BASE || count < 1u || count > 2u) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        if (rm->diag_pending) {
            return O2P_MB_EX_DEVICE_BUSY;
        }
        uint16_t cmd = in[0];
        if ((cmd & O2P_DIAG_MAGIC_MASK) != O2P_DIAG_MAGIC) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        uint8_t op = (uint8_t)(cmd & 0xFFu);
        if (op < O2P_OP_READ_LMP_REG || op > O2P_OP_READ_GPIO) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        /* OP_READ_GPIO IS SERVED HERE, inside the write that asks for it, and
         * not queued for main.c like opcodes 0x01..0x07. The difference is
         * deliberate.
         *
         * Those seven are I2C transactions - up to 25 ms each, one with a
         * 10 ms conversion wait, on a bus the sampler owns between its phases
         * - which is why main.c runs them only in PH_IDLE and only once the
         * reply has left the wire. This one is seven register loads, the same
         * class of work as the two peek triggers above, which are also served
         * in the write.
         *
         * The property that could have argued for deferring - that MODER,
         * PUPDR, OTYPER, AFR, IDR and ODR describe ONE instant relative to the
         * code that changes pin modes - holds at this point already. Every
         * writer of a pin's mode is main-loop code that runs to completion
         * before it returns: o2p_i2c1_bus_recover() drives PB6/PB7 as outputs
         * and re-runs o2p_i2c1_init() before returning; heater.c (PA8),
         * ads1119.c (PB1), mcu_adc.c (PA4/PA6/PA7), lmp91000.c (PB0) and
         * modbus_rtu.c (PA9/PA10/PC6/PC7) configure inside their own calls.
         * This handler is reached from o2p_modbus_poll() in that same loop, so
         * it cannot land half-way through any of them, PH_IDLE or not. No
         * interrupt changes a pin MODE: SysTick counts milliseconds, and
         * USART1's TC handler only drives DE and /RE (PC6/PC7) through BSRR -
         * which the snapshot excludes by masking interrupts around its loads.
         * Checked 2026-09-10 by grepping src/ for MODER/PUPDR/OTYPER/AFR/BSRR
         * writers and for every *_Handler.
         *
         * What serving it here buys: the result exists when the write is
         * acknowledged, so a port walk is sixteen request pairs rather than
         * sixteen sampler cycles; and the path a host test drives through
         * o2p_mb_dispatch() is the WHOLE path. A deferred case in main.c
         * would be a line no host test can reach.
         *
         * BUSY still applies (checked above, exception 06): a queued I2C
         * opcode owns the result registers until it has run, and this would
         * overwrite them. */
        if (op == O2P_OP_READ_GPIO) {
            if (count != 2u) {
                rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
                return O2P_MB_EX_ILLEGAL_VALUE;
            }
            o2p_gpio_diag_result_t res;
            uint16_t st = o2p_gpio_diag_read(in[1], &res);
            rm->diag_cmd = cmd;
            rm->diag_param = in[1];
            rm->diag_rdata0 = res.rdata[0];
            rm->diag_rdata1 = res.rdata[1];
            rm->diag_rdata2 = res.rdata[2];
            rm->diag_crc_status = res.analog_mask;
            rm->diag_status = st;
            return 0u;
        }
        bool needs_param = (op == O2P_OP_READ_LMP_REG ||
                            op == O2P_OP_TRIM_LMP_TIACN ||
                            op == O2P_OP_READ_TMP_REG);
        if (needs_param && count != 2u) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return O2P_MB_EX_ILLEGAL_VALUE;
        }
        rm->diag_cmd = cmd;
        rm->diag_param = (count == 2u) ? in[1] : 0u;
        rm->diag_status = O2P_DMBOX_STATUS_PENDING;
        rm->diag_pending = true;
        return 0u;
    }

    /* Arbitrary code execution mailbox */
    if (in_block(addr, count, O2P_REG_EXEC_BASE, O2P_REG_EXEC_COUNT)) {
        /* M1: Allow validated ABORT to cancel a pending execution before the busy check */
        if (addr == O2P_REG_EXEC_CMD && in[0] == (O2P_EXEC_MAGIC | O2P_EXEC_OP_ABORT)) {
            rm->exec_cmd = in[0];
            rm->exec_pending = false;
            rm->exec_status = O2P_EXEC_STATUS_NONE;
            return 0u;
        }

        if (rm->exec_pending) {
            return O2P_MB_EX_DEVICE_BUSY;
        }

        /* M3 / Finding 4: Reject any write overlapping read-only registers (STATUS, RESULT_HI, RESULT_LO) */
        if (overlaps_block(addr, count, O2P_REG_EXEC_STATUS, 3u)) {
            return O2P_MB_EX_ILLEGAL_VALUE;
        }

        /* M2: If writing CMD (0x0150), validate magic, opcode, and candidate length
         * BEFORE modifying any internal staged registers. */
        if (addr == O2P_REG_EXEC_CMD) {
            uint16_t cmd = in[0];
            if ((cmd & O2P_EXEC_MAGIC_MASK) != O2P_EXEC_MAGIC) {
                rm->exec_status = O2P_EXEC_STATUS_ERR_OPCODE;
                return O2P_MB_EX_ILLEGAL_VALUE;
            }

            uint8_t op = (uint8_t)(cmd & 0xFFu);
            if (op != O2P_EXEC_OP_RUN && op != O2P_EXEC_OP_ABORT) {
                rm->exec_status = O2P_EXEC_STATUS_ERR_OPCODE;
                return O2P_MB_EX_ILLEGAL_VALUE;
            }

            if (op == O2P_EXEC_OP_RUN) {
                uint16_t candidate_len = (count > 1u) ? in[1] : rm->exec_len;
                if (candidate_len < 2u || candidate_len > (O2P_REG_EXEC_CODE_COUNT * 2u) || (candidate_len & 1u) != 0u) {
                    rm->exec_status = O2P_EXEC_STATUS_ERR_LEN;
                    return O2P_MB_EX_ILLEGAL_VALUE;
                }
            }
        }

        /* All validations passed; apply writes to writable fields */
        for (uint16_t i = 0; i < count; i++) {
            uint16_t a = (uint16_t)(addr + i);
            uint16_t v = in[i];

            if (a >= O2P_REG_EXEC_CODE_BASE && a < O2P_REG_EXEC_CODE_BASE + O2P_REG_EXEC_CODE_COUNT) {
                rm->exec_code[a - O2P_REG_EXEC_CODE_BASE] = v;
            } else {
                switch (a) {
                case O2P_REG_EXEC_CMD:
                    rm->exec_cmd = v;
                    break;
                case O2P_REG_EXEC_LEN:
                    /* Finding 2: Validate direct length writes */
                    if (v < 2u || v > (O2P_REG_EXEC_CODE_COUNT * 2u) || (v & 1u) != 0u) {
                        rm->exec_status = O2P_EXEC_STATUS_ERR_LEN;
                        return O2P_MB_EX_ILLEGAL_VALUE;
                    }
                    rm->exec_len = v;
                    break;
                case O2P_REG_EXEC_PARAM_HI:
                    rm->exec_param_hi = v;
                    break;
                case O2P_REG_EXEC_PARAM_LO:
                    rm->exec_param_lo = v;
                    break;
                case O2P_REG_EXEC_TIMEOUT_MS:
                    rm->exec_timeout_ms = v;
                    break;
                default:
                    /* Skip read-only status and result registers */
                    break;
                }
            }
        }

        if (addr == O2P_REG_EXEC_CMD) {
            uint8_t op = (uint8_t)(in[0] & 0xFFu);
            if (op == O2P_EXEC_OP_RUN) {
                rm->exec_status = O2P_EXEC_STATUS_PENDING;
                rm->exec_pending = true;
            } else {
                rm->exec_pending = false;
                rm->exec_status = O2P_EXEC_STATUS_NONE;
            }
        }

        return 0u;
    }

    /* Crash retention mailbox: writing 0 strictly to CRASH_BUILD_ID_LO clears record */
    if (in_block(addr, count, O2P_REG_CRASH_BASE, O2P_REG_CRASH_COUNT)) {
        if (addr == O2P_REG_CRASH_BUILD_ID_LO && count == 1u && in[0] == 0u) {
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
#endif

    /* Reaching here having touched a mailbox means the frame overlapped one
     * without being contained in it - every contained case returned above. */
    if (overlaps_block(addr, count, O2P_REG_HTEST_BASE, O2P_REG_HTEST_COUNT)
#if O2P_DEBUG_ENABLE
        || overlaps_block(addr, count, O2P_REG_PEEK_BASE, O2P_REG_PEEK_COUNT)
        || overlaps_block(addr, count, O2P_REG_PEEKW_BASE, O2P_REG_PEEKW_COUNT)
        || overlaps_block(addr, count, O2P_REG_EXEC_BASE, O2P_REG_EXEC_COUNT)
        || overlaps_block(addr, count, O2P_REG_DMBOX_BASE, O2P_REG_DMBOX_COUNT)
        || overlaps_block(addr, count, O2P_REG_CRASH_BASE, O2P_REG_CRASH_COUNT)
#endif
        ) {
        return O2P_MB_EX_ILLEGAL_VALUE;
    }
    if (rm->upd != NULL &&
        (overlaps_block(addr, count, O2P_REG_UPDATE_BASE, O2P_REG_UPDATE_COUNT) ||
         overlaps_block(addr, count, O2P_REG_UPDDATA_BASE, O2P_REG_UPDDATA_COUNT))) {
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
