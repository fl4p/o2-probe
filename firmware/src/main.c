/* o2-probe Rev A - v0 application.
 *
 * A 1 Hz sample cycle feeding a Modbus RTU slave. No sleep modes: the probe is
 * PSU powered through the farm cable and the cell bias must run continuously,
 * so there is no power budget to optimise and every low-power mode is a way to
 * accidentally interrupt the bias.
 *
 * THE SAMPLER IS INCREMENTAL, one conversion per main-loop pass, and that is
 * not a stylistic choice. A full cycle is twelve ADS1119 conversions; at the
 * 20 SPS setting the oxygen channel alone wants eight of them at 50 ms each.
 * Run as one blocking routine that is ~500 ms during which nothing answers the
 * bus - half the master's likely timeout, spent ignoring it. Interleaved, the
 * worst case a Modbus reply can wait behind is a single conversion.
 *
 * What v0 deliberately does NOT do: drive the membrane heater (see heater.h),
 * and provide an RS-485 application bootloader (SCHEMATIC-REVIEW.md M2 - it
 * must exist before any probe is potted).
 */
#include "ads1119.h"
#include "board_pins.h"
#include "config_flash.h"
#include "faults.h"
#include "heater.h"
#include "heater_ctl.h"
#include "i2c1.h"
#include "lmp91000.h"
#include "mcu.h"
#include "mcu_adc.h"
#include "modbus_rtu.h"
#include "o2.h"
#include "psychro.h"
#include "regmap.h"
#include "sht4x.h"
#include "tmp117.h"

#include <string.h>

/* DS-0637 Note 1: after a bias interruption the cell "will become saturated
 * with oxygen gas which is consumed when the bias is reapplied", giving a
 * settling time "as long as 15 minutes". */
#define O2P_SETTLE_SECONDS 900u
_Static_assert(O2P_SETTLE_SECONDS == O2P_SETTLE_SECONDS_NOMINAL,
               "regmap.h's boot-time SETTLE_S placeholder must match the real "
               "settling period, or the first poll reports a countdown that "
               "does not match the deadline the sampler enforces");

/* Above this the SGX cell is outside its rating and the reading is an
 * extrapolation - flagged, NOT discarded (PLAN.md:211-228). */
#define O2P_TEMP_OVER_C100 6000

/* The absolute tip limit programmed into the TMP117's therm-mode alert. Above
 * the ~75 C the pile reaches, so it is a fault limit and not a thermostat. */
#define O2P_TIP_LIMIT_C100 8500
#define O2P_TIP_HYST_K100  500

#define O2P_VIN_LOW_MV 9000u
#define O2P_VA_LOW_MV  3130u

static o2p_heater_state_t g_heat;

/* Oversampling per channel. The monitors run at 90 SPS (11 ms) because they
 * only need to be right to a few millivolts; oxygen runs at 20 SPS for the
 * lowest noise, because 0.1 %vol is about 30 codes. */
#define O2P_N_VREF 2u
#define O2P_N_VIN  2u
#define O2P_N_O2   8u

static o2p_regmap_t g_rm;

static uint32_t g_settle_deadline_s;
/* Cycles a pending calibration may wait for a failed ADS before it is
 * abandoned and any commit deferred behind it is released. Bounded so that
 * neither the calibration nor the commit can be stranded indefinitely; see
 * finish_o2(). Three cycles is a transient converter fault, not an outage. */
#define O2P_CAL_WAIT_MAX_CYCLES 3u
static uint8_t g_cal_wait_cycles;
static uint32_t g_uptime_s;
static uint16_t g_settle_restarts;
static uint16_t g_sample_seq;

/* When the SHT45 heater last fired, and how long its readings stay masked.
 * Initialised so the first cycle is not masked. */
static uint32_t g_sht_pulse_ms;
static uint32_t g_next_sht_pulse_s;
#define O2P_SHT_RECOVERY_MS 30000u

static void restart_settling(void)
{
    /* Only count a restart that actually extends the deadline, so a fault
     * that persists for minutes does not inflate the counter into
     * meaninglessness. */
    uint32_t deadline = g_uptime_s + O2P_SETTLE_SECONDS;
    if (g_settle_deadline_s <= g_uptime_s && g_settle_restarts != 0xFFFFu) {
        g_settle_restarts++;
    }
    g_settle_deadline_s = deadline;
}

/* Built FRESH from g_rm.cfg on every use, never cached.
 *
 * It used to be a static copy refreshed only at boot and after COMMIT, which
 * meant an accepted Modbus write to CAL_AIR_NA, CAL_ZERO_NA, CAL_TEMP_C100 or
 * TEMPCO_PPM_K changed the readback AND the CONFIG_CRC while the conversion
 * kept using the old constants until the operator happened to commit. A master
 * could therefore verify its calibration by CRC and still be reading numbers
 * produced by the previous one - the worst shape a provenance bug can take,
 * because the check that exists to catch it reports success. The heater has
 * always read g_rm.cfg live (see the o2p_heater_inputs_t below); calibration
 * was the outlier. Found by the 2026-09-07 Codex review. */
static o2p_cal_t cal_from_config(void)
{
    o2p_cal_t cal;
    cal.cal_air_na = g_rm.cfg.cal_air_na;
    /* The zero point comes only from the register; there is no automatic
     * nitrogen trigger to match CAL_TRIGGER, because taking a zero needs a
     * bottle on the bench and nothing on the probe can tell nitrogen from a
     * dead cell. An operator writes the fitted value. */
    cal.cal_zero_na = g_rm.cfg.cal_zero_na;
    cal.cal_temp_c100 = g_rm.cfg.cal_temp_c100;
    cal.tempco_per_k = (float)g_rm.cfg.tempco_ppm_per_k * 1e-6f;
    return cal;
}

/* Convert an AIN0 code to cell current in nanoamps.
 *
 *   V(AIN0) = internal_zero -/+ I * R_TIA          (LMP91000, R_TIA = 7 kOhm)
 *
 * so the cell current is the DEPARTURE from the internal zero, 67 % of VREF.
 * Both the zero and the ADC reference come from VREF_TRIM, so this is
 * ratiometric and first-order immune to VREF drift.
 *
 * The sign is deliberately preserved: SCHEMATIC-REVIEW.md M4 leaves the SGX
 * sign convention open, and the air-versus-nitrogen bench pair is what settles
 * it. Taking an absolute value here would hide the answer.
 */
#define O2P_LMP_TIA_OHM 7000
#define O2P_LMP_INT_Z_NUM 67
#define O2P_LMP_INT_Z_DEN 100

static int32_t code_to_cell_na(int32_t code, uint32_t vref_mv)
{
    int32_t uv = o2p_ads1119_code_to_uv(code, vref_mv);
    int32_t zero_uv = (int32_t)(((int64_t)vref_mv * 1000 * O2P_LMP_INT_Z_NUM) /
                                O2P_LMP_INT_Z_DEN);
    int32_t delta_uv = zero_uv - uv;
    return (int32_t)(((int64_t)delta_uv * 1000) / O2P_LMP_TIA_OHM);
}

/* ------------------------------------------------------------- the sampler */

typedef enum {
    PH_IDLE = 0,
    PH_RAILS,      /* MCU ADC: 3V3A witness */
    PH_AFE,        /* LMP91000 configuration readback */
    PH_TEMPS,      /* TMP117 + SHT45 */
    PH_VREF,       /* ADS1119 AIN1 against the INTERNAL reference */
    PH_VIN,        /* ADS1119 AIN3 */
    PH_O2,         /* ADS1119 AIN0, O2P_N_O2 conversions */
    PH_PUBLISH,
} phase_t;

static phase_t g_phase;
static unsigned g_sub;          /* conversion index within the current phase */
static int32_t g_acc;           /* accumulator for the current phase */

/* Per-cycle working state, gathered as the phases run. */
static struct {
    uint16_t faults;
    uint32_t vref_mv;
    int16_t  t_tip;
    int16_t  t_chamber;
    uint16_t rh;
    bool     tip_ok;
    bool     chamber_ok;
    bool     rh_ok;
    /* Whether THIS cycle's reference measurement was usable, which is what the
     * rail readings are scaled by. Separate from ADC_RANGE because that bit is
     * shared with the oxygen conversion - see the heater interlock below. */
    bool     vref_ok;
    uint16_t heater_block;
} g_cyc;

static void cycle_begin(void)
{
    memset(&g_cyc, 0, sizeof(g_cyc));
    g_cyc.faults = 0u;
    /* Until the reference is actually measured this cycle, assume the trim
     * target rather than carrying last cycle's number forward. */
    g_cyc.vref_mv = O2P_HW_VREF_TARGET_MV;
    g_cyc.vref_ok = false;
    g_cyc.t_tip = O2P_I16_INVALID;
    g_cyc.t_chamber = O2P_I16_INVALID;
    g_sub = 0u;
    g_acc = 0;

    /* Build this cycle's snapshot from INVALID, never from the previous one.
     * Copying the old snapshot forward is how a dead sensor keeps publishing
     * last cycle's plausible value under this cycle's fault word. */
    o2p_snapshot_reset(o2p_regmap_staging(&g_rm));
}

static void phase_rails(o2p_snapshot_t *s)
{
    uint16_t va_mv = 0u;
    if (o2p_mcu_adc_read_va_mv(&va_mv)) {
        s->va_mv = va_mv;
        if (va_mv < O2P_VA_LOW_MV) {
            g_cyc.faults |= O2P_F_VA_LOW;
            /* A sagging analog rail can drop the AFE's volatile configuration
             * with no reset the MCU would notice. Assume the bias went too. */
            restart_settling();
        }
    } else {
        /* No rail reading is not a good rail reading. */
        g_cyc.faults |= O2P_F_VA_LOW;
    }
}

static void phase_afe(o2p_snapshot_t *s)
{
    uint16_t back = 0u;
    o2p_lmp_status_t lst = o2p_lmp91000_verify(&back);
    s->lmp_readback = back;
    if (lst == O2P_LMP_IO) {
        g_cyc.faults |= O2P_F_I2C_FAIL_LMP;
        restart_settling();
    } else if (lst == O2P_LMP_MISMATCH) {
        g_cyc.faults |= O2P_F_AFE_CONFIG_MISMATCH;
        restart_settling();
        (void)o2p_lmp91000_configure();
    }
}

static void phase_temps(o2p_snapshot_t *s)
{
    int16_t t = 0;
    if (o2p_tmp117_read_c100(&t) == O2P_TMP_OK) {
        s->t_tip = t;
        g_cyc.t_tip = t;
        g_cyc.tip_ok = true;
    } else {
        g_cyc.faults |= O2P_F_I2C_FAIL_TMP;
    }
    /* Re-verify the safety configuration periodically, not just at boot: the
     * therm-mode alert is the heater's hardware cutoff, and a part that lost
     * its configuration to a glitch would otherwise keep reporting fine
     * temperatures with the cutoff silently disarmed. */
    /* UNCONDITIONALLY, not only when already disarmed. Gating this on
     * !armed made it unreachable on every successful boot: init() sets armed
     * after checking CONFIG alone, so the THIGH/TLOW readback added in round 5
     * never ran, and a part that later lost its thresholds was never caught -
     * armed stayed true precisely because nothing re-checked it. A
     * verification that only runs when you already know the answer is not a
     * verification (sixth review, 2026-09-08). */
    {
        if (o2p_tmp117_verify_safety() != O2P_TMP_OK) {
            g_cyc.faults |= O2P_F_I2C_FAIL_TMP;
        }
    }

    /* The SHT45's on-chip heater pulse deliberately warms the element. The
     * measurement it returns, and everything for some seconds afterwards, is
     * of a heated sensor - so the chamber channels stay INVALID until the
     * recovery window closes. Publishing a post-pulse reading would look
     * exactly like the pile drying out.
     *
     * The window is a conservative guess: Sensirion documents the heater
     * commands but this firmware has not measured the recovery time on this
     * part in this chamber. Treat it as unverified until a bench run replaces
     * it - which is also the measurement that turns the slow-recovery
     * signature into the DEW_SUSPECT classifier PLAN.md:312 asks for. */
    if (!o2p_elapsed(g_sht_pulse_ms, O2P_SHT_RECOVERY_MS)) {
        g_cyc.faults |= O2P_F_I2C_FAIL_SHT;
        /* The chamber channels are suppressed during recovery, but the TIP
         * reading is still good and finish_o2() still falls back to it for the
         * oxygen correction - so the overtemperature test below must not be
         * skipped with them. Returning here published a 70 C sample, tempco-
         * corrected, WITHOUT the TEMP_OVER qualifier that says the reading is
         * extrapolated past the cell's rated range, and the only visible fault
         * was the SHT recovery we caused ourselves. Found by the fourth
         * review, 2026-09-08. */
        if (g_cyc.tip_ok && g_cyc.t_tip > O2P_TEMP_OVER_C100) {
            g_cyc.faults |= O2P_F_TEMP_OVER;
        }
        return;
    }

    int16_t tc = 0;
    uint16_t rh = 0;
    if (o2p_sht4x_measure(&tc, &rh) == O2P_SHT_OK) {
        s->t_chamber = tc;
        s->rh_chamber = rh;
        g_cyc.t_chamber = tc;
        g_cyc.rh = rh;
        g_cyc.chamber_ok = true;
        g_cyc.rh_ok = true;
    } else {
        g_cyc.faults |= O2P_F_I2C_FAIL_SHT;
    }

    /* The temperature that matters for the cell's rating is the gas it sees. */
    int16_t t_gas = g_cyc.chamber_ok ? g_cyc.t_chamber : g_cyc.t_tip;
    if ((g_cyc.chamber_ok || g_cyc.tip_ok) && t_gas > O2P_TEMP_OVER_C100) {
        g_cyc.faults |= O2P_F_TEMP_OVER;   /* extrapolated, still valid */
    }

    /* Condensation margin. */
    if (g_cyc.chamber_ok && g_cyc.tip_ok) {
        float margin = 0.0f;
        if (o2p_dew_margin_k((float)g_cyc.t_tip * 0.01f,
                             (float)g_cyc.t_chamber * 0.01f,
                             (float)g_cyc.rh * 0.01f, &margin)) {
            float m100 = margin * 100.0f;
            if (m100 > -32760.0f && m100 < 32760.0f) {
                s->dew_margin_x100 = (int16_t)m100;
                if (margin <= 0.0f) {
                    /* The tip is at or below the dew point: the membrane is
                     * condensing. v0 has no heater to answer with, so this is
                     * a report, not a control action. */
                    g_cyc.faults |= O2P_F_DEW_SUSPECT;
                }
            }
        }
    }
}

/* One ADS1119 conversion into g_acc. Returns true when the phase is done. */
static bool accumulate(uint8_t mux, uint8_t dr, bool ext_ref, unsigned n)
{
    int16_t code = 0;
    o2p_ads_status_t st = o2p_ads1119_convert(mux, dr, ext_ref, &code);
    if (st != O2P_ADS_OK) {
        g_cyc.faults |= O2P_F_I2C_FAIL_ADS;
        g_sub = n;          /* abandon the phase; a partial average is not a
                             * measurement of any defined interval */
        g_acc = 0;
        return true;
    }
    g_acc += code;
    g_sub++;
    return g_sub >= n;
}

static void finish_vref(o2p_snapshot_t *s)
{
    if ((g_cyc.faults & O2P_F_I2C_FAIL_ADS) != 0u) {
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_VREF;
    int32_t half_uv = o2p_ads1119_code_to_uv(code, O2P_ADS_INTERNAL_REF_MV);
    int32_t measured = (half_uv / 1000) * (int32_t)O2P_HW_DIV_VREF_DEN /
                       (int32_t)O2P_HW_DIV_VREF_NUM;
    if (measured < 0) {
        measured = 0;
    }
    s->vref_mv = (uint16_t)measured;
    /* Outside the trim network's reachable band, the reference is not what
     * the -600 mV bias depends on, so the bias is not -600 mV either. */
    if (measured < (int32_t)O2P_HW_VREF_MIN_MV - 100 ||
        measured > (int32_t)O2P_HW_VREF_MAX_MV + 100) {
        g_cyc.faults |= O2P_F_ADC_RANGE;
    } else {
        g_cyc.vref_mv = (uint32_t)measured;
        g_cyc.vref_ok = true;
    }
}

static void finish_vin(o2p_snapshot_t *s)
{
    if ((g_cyc.faults & O2P_F_I2C_FAIL_ADS) != 0u) {
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_VIN;
    int32_t pin_uv = o2p_ads1119_code_to_uv(code, g_cyc.vref_mv);
    int32_t vin_mv = (pin_uv / 1000) * (int32_t)O2P_HW_DIV_VIN_DEN /
                     (int32_t)O2P_HW_DIV_VIN_NUM;
    if (vin_mv < 0) {
        vin_mv = 0;
    }
    s->vin_mv = (vin_mv > 0xFFFF) ? 0xFFFFu : (uint16_t)vin_mv;
    if (vin_mv < (int32_t)O2P_VIN_LOW_MV) {
        g_cyc.faults |= O2P_F_VIN_LOW;
    }
}

static void finish_o2(o2p_snapshot_t *s)
{
    if ((g_cyc.faults & O2P_F_I2C_FAIL_ADS) != 0u) {
        /* No conversion this cycle, so no air point can be taken. A commit
         * deferred behind that calibration must not wait forever - a
         * repeatedly failing ADS still reaches PH_PUBLISH and still feeds the
         * watchdog, so the probe stays up and responsive, and a reboot would
         * lose a configuration write the master was told had succeeded.
         *
         * But releasing the commit IMMEDIATELY, as the third review's fix did,
         * is also wrong: it persists the PRE-calibration image while the
         * calibration request is still outstanding, and when the converter
         * recovers the air point lands in RAM with no commit behind it. The
         * operator asked for "calibrate and save" and got "save the old one,
         * then calibrate into RAM" - one premature commit and a lost
         * calibration. Found by the fourth review, 2026-09-08.
         *
         * So the wait is BOUNDED instead. A few cycles of grace for a
         * transient converter fault, then the calibration is abandoned
         * explicitly and the commit released, so nothing is stranded and
         * nothing is persisted while it could still have changed. */
        if (g_rm.cal_requested) {
            if (g_rm.cal_renewed) {
                g_rm.cal_renewed = false;
                g_cal_wait_cycles = 0u;
            }
            g_cal_wait_cycles++;
            /* Post-increment compare: the Nth failure abandons. Written as
             * `if (c < MAX) c++; else abandon`, this waited for MAX+1 failures
             * - four, not the three the comment and the budget doc both
             * claimed (fifth review, 2026-09-08). A small error, but the
             * documented number was wrong, which is how a bounded wait stops
             * being a bound anyone can reason about. */
            if (g_cal_wait_cycles < O2P_CAL_WAIT_MAX_CYCLES) {
                /* keep waiting */
            } else {
                g_rm.cal_requested = false;
                g_rm.cal_renewed = false;
                g_cal_wait_cycles = 0u;
                if (g_rm.commit_after_cal) {
                    g_rm.commit_after_cal = false;
                    g_rm.commit_pending = true;
                }
            }
        }
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_O2;
    int32_t uv = o2p_ads1119_code_to_uv(code, g_cyc.vref_mv);
    s->afe_vout_mv = (uv < 0) ? 0u : (uint16_t)(uv / 1000);

    int32_t cell_na = code_to_cell_na(code, g_cyc.vref_mv);

    /* uA * 100, i.e. 10 nA per count. */
    int32_t raw_x100 = cell_na / 10;
    s->o2_raw = (raw_x100 > 32767 || raw_x100 < -32767)
                    ? O2P_I16_INVALID : (int16_t)raw_x100;

    int16_t t_gas = g_cyc.chamber_ok ? g_cyc.t_chamber
                                     : (g_cyc.tip_ok ? g_cyc.t_tip
                                                     : O2P_I16_INVALID);

    /* Air-point calibration FIRST, if an operator asked for one, so that the
     * value published from this cycle and the CONFIG_CRC/readback describing
     * it are the same calibration.
     *
     * This used to run after the conversion, at the end of this function. The
     * 2026-09-08 review found the consequence: the sample was converted with
     * the OLD constants, then g_rm.cfg was changed, and PH_PUBLISH shipped the
     * old number under a readback and CONFIG_CRC that described the new one.
     * A master that did the obvious thing - calibrate, then read back the CRC
     * to confirm - was confirming a calibration it had not yet seen applied.
     * That is the same class of defect as the g_cal cache removed on
     * 2026-09-07, just one cycle wide instead of unbounded.
     *
     * Taking the point first also makes the cycle self-consistent in the way
     * an operator expects: calibrate in air and THIS sample reads ~20.95 %,
     * rather than one stale cycle followed by a correct one.
     *
     * Judge the raw channel, not the compensated one: a probe that has never
     * been calibrated always fails the compensated test, which would make
     * calibration impossible. o2p_calibrate_air() bounds the current itself,
     * so moving ahead of the conversion loses no check that mattered - the
     * only fault this no longer sees is an ADC_RANGE raised by converting
     * against the constants we are about to replace. */
    if (g_rm.cal_requested) {
        g_rm.cal_requested = false;
        g_rm.cal_renewed = false;
        g_cal_wait_cycles = 0u;
        o2p_cal_t taken = cal_from_config();
        /* SETTLING is not in g_cyc.faults yet - cycle_publish() adds it - so
         * o2p_o2_valid() alone would accept an air point taken during the
         * documented 15-minute post-bias settle, store a transient current as
         * the probe's permanent air constant, and invalidate the very sample
         * it came from seconds later. Test the deadline directly (third
         * review, 2026-09-08). The request is dropped rather than held: an
         * operator who calibrates too early should be told by the unchanged
         * constants, not surprised by a calibration landing a quarter of an
         * hour after they asked for it. */
        bool settled = (g_uptime_s >= g_settle_deadline_s);
        /* And a calibration needs a MEASURED temperature, not a fallback one.
         * The conversion may substitute cal_temp_c100 for a missing gas
         * temperature - that only means "assume we are at the calibration
         * temperature", which is recoverable and self-correcting. Storing a
         * fabricated 25.00 C AS the calibration temperature is not: it becomes
         * the permanent reference every later tempco correction is measured
         * against, so a probe that calibrated with both temperature sensors
         * down carries a false reference for the rest of its life while
         * looking perfectly calibrated. Temperature faults are deliberately
         * absent from the raw-O2 validity mask, so o2p_o2_valid() does not
         * catch this. Found by the fourth review, 2026-09-08. */
        if (settled && t_gas != O2P_I16_INVALID && o2p_o2_valid(g_cyc.faults) &&
            o2p_calibrate_air(&taken, cell_na, t_gas)) {
            g_rm.cfg.cal_air_na = taken.cal_air_na;
            g_rm.cfg.cal_temp_c100 = taken.cal_temp_c100;
        }
        /* A refused calibration leaves the old constants in place. */

        /* A commit asked for in the SAME frame waits until here, so that what
         * reaches flash is the calibration the master was acknowledged for.
         * Raised even when the point was refused: the operator asked for the
         * live config to be persisted, and the live config is what it gets. */
        if (g_rm.commit_after_cal) {
            g_rm.commit_after_cal = false;
            g_rm.commit_pending = true;
        }
    }

    o2p_cal_t cal = cal_from_config();
    if (cal.cal_air_na <= 0) {
        /* Never calibrated. Substitute the datasheet nominal so the raw
         * channel still converts, and raise CAL_DEFAULT - which invalidates
         * the COMPENSATED channel, because that nominal spans 0.07-0.13 mA. */
        cal.cal_air_na = O2P_CAL_AIR_NOMINAL_NA;
        g_cyc.faults |= O2P_F_CAL_DEFAULT;
    }

    /* No zero point taken. Unlike the air point there is nothing to
     * substitute - zero IS the substitute, and it is what the law degrades to
     * - so the reading stands and the fault says which accuracy regime it was
     * produced in (faults.h, CAL_ZERO_DEFAULT).
     *
     * A stored 0 is read as "never taken" rather than "measured as zero".
     * Those are indistinguishable in the register, and this is the direction
     * the ambiguity must fail in: a bench that genuinely measures 0 nA gets a
     * flag it can explain, while the alternative silently certifies every
     * uncalibrated probe. One LSB is 10.9 nA, so a bench with a real zero
     * point has a value to write. */
    if (cal.cal_zero_na == 0) {
        g_cyc.faults |= O2P_F_CAL_ZERO_DEFAULT;
    }

    /* A non-zero temperature coefficient with no temperature is not a
     * compensated reading. Rather than silently applying a zero correction
     * and presenting the result as compensated, refuse it. */
    if (cal.tempco_per_k != 0.0f && t_gas == O2P_I16_INVALID) {
        g_cyc.faults |= O2P_F_I2C_FAIL_TMP;
        s->o2_comp = O2P_U16_INVALID;
    } else {
        float c = 0.0f;
        o2p_status_t st = o2p_fraction_from_current(
            &cal, cell_na,
            (t_gas != O2P_I16_INVALID) ? t_gas : cal.cal_temp_c100, &c);
        if (st == O2P_RANGE) {
            g_cyc.faults |= O2P_F_ADC_RANGE;
        }
        s->o2_comp = o2p_encode_percent(st, c);
    }

}

static void cycle_publish(o2p_snapshot_t *s)
{
    if (g_uptime_s < g_settle_deadline_s) {
        g_cyc.faults |= O2P_F_SETTLING;
        uint32_t left = g_settle_deadline_s - g_uptime_s;
        s->settle_s = (left > 65535u) ? 65535u : (uint16_t)left;
    } else {
        s->settle_s = 0u;
    }

    /* The single point where the validity rule is applied. Whatever the
     * conversions produced, anything the fault word calls untrustworthy
     * leaves as a sentinel. Raw and compensated have different masks. */
    if (!o2p_o2_valid(g_cyc.faults)) {
        s->o2_raw = O2P_I16_INVALID;
    }
    if (!o2p_o2_comp_valid(g_cyc.faults)) {
        s->o2_comp = O2P_U16_INVALID;
    }

    /* Decide the heater LAST, from this cycle's inputs only.
     *
     * Doing it here rather than in a phase of its own keeps every phase
     * non-blocking and guarantees the decision sees the rail, AFE, temperature
     * and humidity results together - a loop that ran before the rail check
     * could command heat into a supply already known to be sagging. */
    {
        const o2p_heater_cfg_t hcfg = {
            .setpoint_x100 = g_rm.cfg.rh_setpoint_x100,
            .dt_max_k100   = g_rm.cfg.dt_max_k_x100,
            .max_duty_x100 = g_rm.cfg.heater_max_duty_x100,
            /* Compile-time gains. They belong in holding registers - the
             * plant gain cannot be known before the loop runs, and a potted
             * probe has no SWD to reflash through - but adding registers
             * changes the map, and the map's prose copy lives in ../DESIGN.md,
             * outside this work's boundary. Flagged as follow-up rather than
             * done half-way. */
            .kp_x100       = g_rm.cfg.heater_kp_x100,
            .ki_x100       = g_rm.cfg.heater_ki_x100,
        };
        const o2p_heater_in_t hin = {
            .drive_possible   = o2p_heater_compiled_in(),
            .safety_armed     = o2p_tmp117_safety_armed(),
            .pin_integrity_ok = o2p_heater_pin_integrity_ok(),
            .rh_valid         = g_cyc.rh_ok,
            .rh_x100          = g_cyc.rh,
            .tip_valid        = g_cyc.tip_ok,
            .t_tip_c100       = g_cyc.t_tip,
            .chamber_valid    = g_cyc.chamber_ok,
            .t_chamber_c100   = g_cyc.t_chamber,
            /* Heating adds ~86 mA. A rail already out of tolerance is not the
             * place to put more load, and VA_LOW in particular means the AFE
             * may have lost its bias already.
             *
             * I2C_FAIL_ADS belongs in this test even though it is not a rail
             * fault: finish_vin() returns early on a latched ADS failure and
             * therefore never raises VIN_LOW, so an UNMEASURED input rail read
             * as "no fault" and authorised the load. An interlock whose input
             * is missing must fail closed, not open (fifth review). */
            /* An interlock input derived from a measurement known to be
             * invalid must fail closed: when VREF is outside the trim band,
             * finish_vref() keeps the 2500 mV default and finish_vin() scales
             * VIN with it, so an actual 2.0 V reference makes an actual 8 V
             * input measure ~10 V and sail past the 9 V interlock.
             *
             * Tested through vref_ok rather than ADC_RANGE. Round 6 used the
             * fault bit, and the seventh review showed that conflates two
             * unrelated provenances: ADC_RANGE is ALSO raised by an oxygen
             * conversion that saturates, so a polarity error, a stale zero or
             * a genuine overload - none of which say anything about the
             * supply - would disable heating as a "supply" fault. The bit
             * stays shared for O2 validity; the interlock uses the specific
             * predicate it actually means. */
            .supply_ok        = (g_cyc.faults &
                                 (O2P_F_VA_LOW | O2P_F_VIN_LOW |
                                  O2P_F_I2C_FAIL_ADS)) == 0u &&
                                g_cyc.vref_ok,
        };
        o2p_heater_out_t hout = {0u, 0u};
        o2p_heater_ctl_step(&g_heat, &hcfg, &hin, g_uptime_s, &hout);
        o2p_heater_apply(hout.duty_x100, g_rm.cfg.heater_pwm_hz);
        g_cyc.heater_block = hout.block;   /* kept for the fault word below */
        if (g_heat.runaway_latched) {
            g_cyc.faults |= O2P_F_HEATER_RUNAWAY;
        }
        /* HEATER_DISABLED now means "not driving this cycle", whatever the
         * reason. In v0 it was a constant; the reason bits are in
         * HEATER_BLOCK. */
        if (hout.block != 0u) {
            g_cyc.faults |= O2P_F_HEATER_DISABLED;
        }
    }
    s->heater_duty = o2p_heater_duty_x100();
    s->pressure_hpa = 0u;             /* BMP390 is DNP on Rev A */
    s->exp_data = O2P_U16_INVALID;    /* J2 expansion is DNP on Rev A */
    s->uptime_s = g_uptime_s;
    s->reset_cause = o2p_reset_cause();
    s->mb_crc_errs = o2p_modbus_crc_errors();
    s->mb_frame_errs = o2p_modbus_frame_errors();
    s->i2c_errs = o2p_i2c1_error_count();
    s->settle_restarts = g_settle_restarts;
    s->sample_seq = ++g_sample_seq;
    s->faults = g_cyc.faults;

    o2p_regmap_publish(&g_rm);
}

/* One step of the sampler. Returns true when a cycle has just been published. */
static bool sampler_step(void)
{
    o2p_snapshot_t *s = o2p_regmap_staging(&g_rm);

    switch (g_phase) {
    case PH_RAILS:  phase_rails(s); g_phase = PH_AFE;   break;
    case PH_AFE:    phase_afe(s);   g_phase = PH_TEMPS; break;
    case PH_TEMPS:  phase_temps(s); g_phase = PH_VREF; g_sub = 0; g_acc = 0; break;

    case PH_VREF:
        /* Measured against the ADS1119's OWN internal reference: a converter
         * referenced to the thing it is checking cannot detect that thing
         * drifting. */
        if (accumulate(O2P_ADS_MUX_AIN1_AGND, O2P_ADS_DR_90SPS, false, O2P_N_VREF)) {
            finish_vref(s);
            g_phase = PH_VIN; g_sub = 0; g_acc = 0;
        }
        break;

    case PH_VIN:
        if (accumulate(O2P_ADS_MUX_AIN3_AGND, O2P_ADS_DR_90SPS, true, O2P_N_VIN)) {
            finish_vin(s);
            g_phase = PH_O2; g_sub = 0; g_acc = 0;
        }
        break;

    case PH_O2:
        if (accumulate(O2P_ADS_MUX_AIN0_AGND, O2P_ADS_DR_20SPS, true, O2P_N_O2)) {
            finish_o2(s);
            g_phase = PH_PUBLISH;
        }
        break;

    case PH_PUBLISH:
        cycle_publish(s);
        g_phase = PH_IDLE;
        return true;

    default:
        break;
    }
    return false;
}

/* ---------------------------------------------------------------- bring-up */

static void bring_up_devices(void)
{
    o2p_i2c1_init();
    o2p_lmp91000_gpio_init();
    o2p_mcu_adc_init();

    (void)o2p_ads1119_init();
    /* The result matters and is latched inside the driver: a TMP117 whose
     * therm-mode alert failed to program still answers temperature reads
     * perfectly, so nothing else would ever notice that the hardware heater
     * cutoff is not armed. v1's heater must gate on
     * o2p_tmp117_safety_armed(); v0 surfaces it as a fault. */
    (void)o2p_tmp117_init(O2P_TIP_LIMIT_C100, O2P_TIP_HYST_K100);
    (void)o2p_sht4x_reset();

    /* An earlier version of this skipped the 15-minute settling wait when the
     * reset was not a power-cycle AND the LMP91000's registers read back
     * intact, on the theory that the bias had therefore never dropped. That
     * inference does not hold: the readback proves only that the AFE's
     * DIGITAL configuration survived, not that VREF_TRIM stayed present. An
     * EMI event that resets the MCU can equally collapse the reference buffer
     * for a few milliseconds; VREF recovers long before the readback happens,
     * and the probe then publishes oxygen from a cell that genuinely needs
     * another quarter of an hour.
     *
     * So: every reset settles. Fifteen minutes of honest invalidity, at most
     * once per reset, beats an unknown interval of confident wrong numbers
     * from a buried instrument.
     */
    if (o2p_lmp91000_verify(NULL) != O2P_LMP_OK) {
        (void)o2p_lmp91000_configure();
    }
    restart_settling();
}

int main(void)
{
    o2p_clock_init();

    /* Heater off before anything else can run long enough to matter. */
    o2p_heater_init();
    o2p_heater_force_off();
    o2p_heater_ctl_reset(&g_heat);

    o2p_regmap_init(&g_rm);
    (void)o2p_config_load(&g_rm.cfg);   /* defaults on absence or corruption */

    bring_up_devices();
    o2p_modbus_init(&g_rm.cfg);
    o2p_wdt_init();

    /* First scheduled pulse one interval after boot, not immediately: a probe
     * that resets repeatedly must not pulse its humidity sensor every time. */
    g_next_sht_pulse_s = (uint32_t)g_rm.cfg.sht_pulse_interval_h * 3600u;
    g_sht_pulse_ms = o2p_millis() - O2P_SHT_RECOVERY_MS;

    uint32_t last_cycle_ms = o2p_millis();
    uint32_t last_second_ms = last_cycle_ms;
    bool cycle_completed = false;

    for (;;) {
        /* Serve the bus first, and between every sampler step. */
        (void)o2p_modbus_poll(&g_rm);

        /* A duty command is only good for a second. If the sampler stalls,
         * the heater must not keep driving on a stale decision. */
        o2p_heater_service();

        if (o2p_elapsed(last_second_ms, 1000u)) {
            last_second_ms += 1000u;
            g_uptime_s++;
        }

        if (g_phase == PH_IDLE) {
            if (o2p_elapsed(last_cycle_ms, 1000u)) {
                last_cycle_ms = o2p_millis();
                cycle_begin();
                g_phase = PH_RAILS;
            }
        } else if (sampler_step()) {
            cycle_completed = true;
        }

        /* Deferred work that must not run mid-transmission. The commit in
         * particular runs only after the response has physically left the
         * wire, so the master is never left waiting on a flash erase. */
        if (!o2p_modbus_tx_busy()) {
            if (g_rm.serial_reconfig_pending) {
                g_rm.serial_reconfig_pending = false;
                o2p_modbus_reconfigure(&g_rm.cfg);
            }
            if (g_rm.commit_pending) {
                g_rm.commit_pending = false;
                (void)o2p_config_store(&g_rm.cfg);
            }
            /* De-creep maintenance, on the configured interval as well as on
             * demand. PLAN.md:312 asks for every 6-12 h; the interval is a
             * holding register, defaulting to 8 h. Without this the stored
             * interval was persisted and then never read by anything. */
            bool due = (g_uptime_s >= g_next_sht_pulse_s);
            if (g_rm.sht_pulse_requested || due) {
                g_rm.sht_pulse_requested = false;
                g_next_sht_pulse_s = g_uptime_s +
                    (uint32_t)g_rm.cfg.sht_pulse_interval_h * 3600u;
                /* Mask BEFORE the pulse, not after: the call blocks for over
                 * a second, and a cycle that lands in the middle of it must
                 * not publish the heated reading either. */
                g_sht_pulse_ms = o2p_millis();
                if (o2p_sht4x_heater_pulse(O2P_SHT_CMD_HEAT_200MW_1S) != O2P_SHT_OK) {
                    /* A pulse that did not complete leaves the element in an
                     * unknown thermal state; keep the mask and let the next
                     * cycle report the SHT as failed. */
                    g_sht_pulse_ms = o2p_millis();
                }
            }
        }

        /* The watchdog is fed only when BOTH invariants still hold: the
         * sampler is completing cycles, and the RS-485 driver is not stuck
         * enabled.
         *
         * The second one is why this is not a bare feed. PC6 drives DE and
         * ~RE together, so a stuck-high PC6 drives the shared cable and
         * silences the two SMT100s as well as this probe. The software
         * backstop that would normally release it lives in the same CPU that
         * must be wedged for the release to have been missed - so software
         * cannot be its own last line of defence. Withholding the feed makes
         * the reset, and R7's 47k pull-down on DE, the release path that does
         * not depend on this CPU running code at all.
         */
        if (cycle_completed && !o2p_modbus_bus_jam_suspected()) {
            cycle_completed = false;
            o2p_wdt_feed();
        }
    }
}
