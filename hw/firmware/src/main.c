/* o2-probe Rev A - v0 application.
 *
 * A 1 Hz sample cycle feeding a Modbus RTU slave. No sleep modes: the probe is
 * PSU powered through the farm cable and the cell bias must run continuously,
 * so there is no power budget to optimise and every low-power mode is a way to
 * accidentally interrupt the bias.
 *
 * THE SAMPLER IS INCREMENTAL, one conversion per main-loop pass, and that is
 * not a stylistic choice. A full cycle is 2 VREF + 8 O2 + 4 WE + 4 RE included
 * conversions, plus one discarded after each of the four channel/reference
 * changes: 22 in all. At the 20 SPS setting the oxygen channel alone wants
 * eight of them at 50 ms each, and the whole cycle is about 600 ms of
 * converter time (9 x 50.01 ms at 20 SPS, 13 x 11.29 ms at 90 SPS, per
 * SBAS925A section 8.3.6).
 * Run as one blocking routine that is ~500 ms during which nothing answers the
 * bus - half the master's likely timeout, spent ignoring it. Interleaved, the
 * worst case a Modbus reply can wait behind is a single conversion.
 *
 * What v0 deliberately does NOT do: drive the membrane heater (see heater.h).
 *
 * The RS-485 firmware updater (SCHEMATIC-REVIEW.md M2) IS here: update.c holds
 * the engine and the register block, and the bootloader that installs what it
 * receives is a separate image in the first 16 KiB of flash (loader_main.c).
 * The application's part is to serve the updater's registers, to do its flash
 * work only between Modbus transmissions, and to reset into the loader when
 * asked.
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
#include "sampler_logic.h"
#include "serial_probation.h"
#include "sht4x.h"
#include "tmp117.h"
#include "update.h"
#include "update_target.h"

#include <string.h>

/* DS-0637 Note 1: after a bias interruption the cell "will become saturated
 * with oxygen gas which is consumed when the bias is reapplied", giving a
 * settling time "as long as 15 minutes". */
#define O2P_SETTLE_SECONDS 900u

/* Above this the SGX cell is outside its rating and the reading is an
 * extrapolation - flagged, NOT discarded (PLAN.md:211-228). */
#define O2P_TEMP_OVER_C100 6000

/* The absolute tip limit programmed into the TMP117's therm-mode alert. Above
 * the ~75 C the pile reaches, so it is a fault limit and not a thermostat. */
#define O2P_TIP_LIMIT_C100 8500
/* The three tip thresholds are defined in three different files and only this
 * one sees all of them, so the ordering that makes them a LADDER is asserted
 * here: a commandable setpoint below the firmware clamp below the hardware
 * cutoff. Collapse any two and the mechanism they were supposed to back up
 * stops existing - which is how the setpoint ceiling came to sit a kelvin
 * under the clamp and made the stated 80 C experiment uncommandable. */
_Static_assert(O2P_HEATER_TEST_SP_MAX_C100 < O2P_HEATER_TIP_LIMIT_C100,
               "a commandable setpoint at or above the firmware clamp makes "
               "the clamp the control mechanism instead of the backstop");
_Static_assert(O2P_HEATER_TIP_LIMIT_C100 < O2P_TIP_LIMIT_C100,
               "firmware must back off before the TMP117's therm-mode cutoff; "
               "two mechanisms at one threshold are one mechanism");
_Static_assert(O2P_HEATER_TIP_RELEASE_C100 < O2P_HEATER_TIP_LIMIT_C100,
               "the clamp needs hysteresis or it chatters at 1 Hz against a "
               "plant whose time constant is seconds");
#define O2P_TIP_HYST_K100  500

#define O2P_VIN_LOW_MV 9000u
#define O2P_VA_LOW_MV  3130u

static o2p_heater_state_t g_heat;

/* Oversampling per channel. The monitors run at 90 SPS (11 ms) because they
 * only need to be right to a few millivolts; oxygen runs at 20 SPS for the
 * lowest noise, because 0.1 %vol is about 30 codes. */
#define O2P_N_VREF 2u
#define O2P_N_O2   8u
#define O2P_N_CELL 4u

static o2p_regmap_t g_rm;
static o2p_cal_t g_cal;
static o2p_update_t g_upd;

/* Reachability probation for SLAVE_ADDR/BAUD_CODE/PARITY_CODE. Zeroed at
 * startup like every other BSS global, which is `armed = false` - a probe that
 * boots from its stored config has nothing to prove. */
static o2p_serial_probation_t g_serial_probation;

/* The reachability triplet as it stands IN FLASH, refreshed at boot and after
 * every successful commit.
 *
 * This, and not "whatever the config held a moment ago", is what a probation
 * falls back to. The difference is not academic. A master that raises the baud
 * for a transfer and then puts it back performs TWO serial changes, and under
 * a previous-value rule the second one's fallback is the FIRST one's new
 * value - so a lost frame during the restore would revert the probe to the
 * fast rate the master had just finished leaving, i.e. away from the master
 * rather than towards it. The stored settings have no such direction: they
 * are where a reset lands too, so the timer and the reset agree on one
 * recovery state instead of racing between two. */
static uint8_t g_stored_addr, g_stored_baud, g_stored_parity;

static void remember_stored_serial(void)
{
    g_stored_addr = g_rm.cfg.slave_addr;
    g_stored_baud = g_rm.cfg.baud_code;
    g_stored_parity = g_rm.cfg.parity_code;
}

/* Decide a probation that is running, and act on the decision.
 *
 * Called from the deferred-work block and not from the top of the loop,
 * because a REVERT reconfigures the USART and that may only happen with the
 * transmitter idle - the same constraint the change itself was subject to.
 * Being late costs nothing here: the deadline is ten seconds and the block
 * runs many times a second.
 */
static void serial_probation_service(void)
{
    o2p_sp_outcome_t out = o2p_sp_service(&g_serial_probation, o2p_millis(),
                                          o2p_modbus_frames_ok());
    if (o2p_sp_apply(&g_serial_probation, out, &g_rm)) {
        o2p_modbus_reconfigure(&g_rm.cfg);
    }
}

static uint32_t g_settle_deadline_s;
static uint32_t g_uptime_s;
static uint16_t g_settle_restarts;
static uint16_t g_sample_seq;

static o2p_fault_latch_t g_fault_latch;   /* see o2p_fault_latch_step() */
static uint16_t g_faults_ever;            /* every bit seen since power-up */
static uint16_t g_ads_fail_count;         /* cycles with no ADS conversion */

/* When the SHT45 heater last fired, and how long its readings stay masked.
 * Initialised so the first cycle is not masked. */
static uint32_t g_sht_pulse_ms;
static uint32_t g_next_sht_pulse_s;
/* The last chamber reading that was actually measured, so the 30 s mask after
 * a scheduled SHT45 de-creep pulse is BRIDGED rather than published as an
 * oxygen sentinel three times a day. Bounded by O2P_RH_MAX_AGE_S; see o2.h
 * for the derivation and for why a dead sensor still reaches the sentinel. */
static o2p_gas_cache_t g_gas_cache;
#define O2P_SHT_RECOVERY_MS 30000u

static void restart_settling(void)
{
    /* Only count a restart that actually extends the deadline, so a fault
     * that persists for minutes does not inflate the counter into
     * meaninglessness. */
    g_settle_deadline_s = o2p_settle_restart(g_uptime_s, g_settle_deadline_s,
                                            O2P_SETTLE_SECONDS,
                                            &g_settle_restarts);
}

static void load_cal_from_config(void)
{
    g_cal.cal_air_na = g_rm.cfg.cal_air_na;
    g_cal.zero_na = g_rm.cfg.cal_zero_na;
    g_cal.cal_temp_c100 = g_rm.cfg.cal_temp_c100;
    g_cal.tempco_per_k = (float)g_rm.cfg.tempco_ppm_per_k * 1e-6f;
    /* %vol x 1000 -> fraction. Zero stays zero, i.e. "the humidity at the air
     * point is unknown", and o2.c refuses to convert on it. */
    g_cal.air_frac = (float)g_rm.cfg.cal_air_frac_x1000 * 1e-5f;
    /* Zero stays zero, i.e. "the pressure at the air point is unknown", which
     * o2.c reads as P_cal == P_meas and applies no pressure normalisation. */
    g_cal.cal_p_hpa = (float)g_rm.cfg.cal_p_hpa;
    /* x1000 -> fraction. Zero is a real setting here, not "unknown": it means
     * apply no vapour correction. o2.c refuses only a value that is not a
     * number or is past O2P_DIL_ALPHA_MAX, and o2p_config_valid() has already
     * bounded what can reach this. */
    g_cal.dil_alpha = (float)g_rm.cfg.dil_alpha_x1000 * 1e-3f;
}

/* ------------------------------------------------------------- the sampler */

typedef enum {
    PH_IDLE = 0,
    PH_RAILS,      /* MCU ADC: 3V3A witness */
    PH_AFE,        /* LMP91000 configuration readback */
    PH_TEMPS,      /* TMP117 + SHT45 */
    PH_VREF,       /* ADS1119 AIN1 against the INTERNAL reference */
    PH_O2,         /* ADS1119 AIN0, O2P_N_O2 conversions */
    PH_WE,         /* ADS1119 AIN2, WE_BUF */
    PH_RE,         /* ADS1119 AIN3, RE_BUF */
    PH_TAFE,       /* LMP91000 die temperature, on AIN0 in OP_MODE 111 */
    PH_PUBLISH,
} phase_t;

static phase_t g_phase;
static unsigned g_sub;          /* conversion index within the current phase */
static int32_t g_acc;           /* accumulator for the current phase */
static bool g_acc_clipped;      /* any conversion in this phase hit full scale */

/* Per-cycle working state, gathered as the phases run. */
static struct {
    uint16_t faults;
    uint32_t vref_mv;
    int16_t  t_tip;
    int16_t  t_chamber;
    uint16_t rh;
    bool     tip_ok;
    /* tip_ok says the read SUCCEEDED; this says the part has actually
     * converted since we last looked. Only the heater consumes it - see
     * phase_temps(). */
    bool     tip_fresh;
    bool     chamber_ok;
    bool     rh_ok;
    uint16_t heater_block;
    /* The fault word AS IT STOOD when the oxygen conversion finished.
     *
     * PH_WE and PH_RE run AFTER PH_O2 and share the cycle-wide fault word, and
     * every ADS failure bit is in O2P_FAULTS_INVALIDATE_O2. Without this, a
     * converter hiccup while reading the diagnostic electrodes would replace an
     * oxygen result that had already been measured cleanly with a sentinel -
     * a diagnostic channel muting the measurement it exists to explain, which
     * is precisely what putting those phases last was supposed to prevent.
     *
     * The failure is still reported: it lands in FAULTS like any other, and the
     * electrode channels themselves go to their sentinels. What it no longer
     * does is reach backwards. */
    uint16_t faults_at_o2;
    bool     o2_measured;
    /* The reference was actually CONVERTED this cycle and was not wild.
     * cycle_begin() seeds vref_mv with the trim TARGET so a channel that runs
     * before PH_VREF still has a number, which means "vref_mv is populated" is
     * not the same question as "vref_mv is a measurement". Every channel
     * scaled BY the reference has to ask the second one.
     *
     * It does NOT mean "inside the trim band": finish_vref() accepts 100 mV
     * beyond each end before raising ADC_RANGE, so this can be true at 2380 or
     * 2620 mV. That slack is deliberate there and is not this flag's promise
     * to make. Corrected after review 2026-09-08 said the comment claimed it. */
    bool     vref_measured;
} g_cyc;

static void cycle_begin(void)
{
    memset(&g_cyc, 0, sizeof(g_cyc));
    g_cyc.faults = 0u;
    /* Until the reference is actually measured this cycle, assume the trim
     * target rather than carrying last cycle's number forward. */
    g_cyc.vref_mv = O2P_HW_VREF_TARGET_MV;
    g_cyc.t_tip = O2P_I16_INVALID;
    g_cyc.t_chamber = O2P_I16_INVALID;
    g_sub = 0u;
    g_acc = 0;
    g_acc_clipped = false;

    /* SETTLING is raised HERE, at the top of the cycle, and not where
     * settle_s is computed in cycle_publish().
     *
     * It is not an acquisition result. It is a statement about the cell's
     * bias history that is already true before a single conversion is taken,
     * and it is the strongest reason there is to distrust the number this
     * cycle is about to produce. Raising it in cycle_publish() put it AFTER
     * the point where the oxygen verdict is frozen at the end of PH_O2, so
     * the verdict could not see it: measured 2026-09-08, a probe eleven
     * minutes into a fifteen-minute settle published 20.91 %vol with
     * raw_ok = 1 and settle_s = 769 in the same frame.
     *
     * The freeze exists so that a diagnostic phase running after PH_O2 cannot
     * mute the oxygen it exists to explain. That argument covers faults the
     * ACQUISITION raises downstream of the measurement. It never covered a
     * state flag that outranks the measurement entirely, and reading the
     * freeze as if it did turned "the cell is not ready" into "the cell is
     * fine". */
    if (g_uptime_s < g_settle_deadline_s) {
        g_cyc.faults |= O2P_F_SETTLING;
    }

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

    /* The INPUT rail, on this same ADC since 2026-09-05. It used to be read
     * from ADS1119 AIN3 and scaled by the VIN divider - but AIN3 is RE_BUF,
     * the buffered reference electrode, so vin_mv was never the input rail and
     * O2P_F_VIN_LOW could not fire. supply_ok gates the heater on that fault,
     * so the undervoltage interlock was dead. Both rails are read the same way
     * here now, which is the arrangement that makes the two hard to desync. */
    uint16_t vin_mv = 0u;
    if (o2p_mcu_adc_read_vin_mv(&vin_mv)) {
        s->vin_mv = vin_mv;
        if (vin_mv < O2P_VIN_LOW_MV) {
            g_cyc.faults |= O2P_F_VIN_LOW;
        }
    } else {
        /* Same rule as VA, and it is a CHANGE: the old ADS1119 path left no
         * fault at all when the conversion failed, so an unreadable input rail
         * read as a healthy one. Unevaluable is not OK. */
        g_cyc.faults |= O2P_F_VIN_LOW;
    }

    /* Die temperature, from the same ADC and therefore free of I2C1. It
     * raises no fault of its own: it is a +/-5 C reading of the silicon, not
     * of the gas, and nothing downstream may act on it. It is published so
     * that a T_TIP or T_CHAMBER which disagrees with it, or which vanishes
     * while it survives, points at the bus rather than at the weather. */
    int16_t die_c100 = 0;
    if (o2p_mcu_adc_read_die_c100(&die_c100)) {
        s->t_die = die_c100;
    }

    /* The counter-electrode drive: PUBLISHED, and deliberately NOT judged.
     *
     * It is the diagnostic that separates "the AFE is misconfigured" from "the
     * AFE is configured and the cell is not there", which is the failure that
     * killed U7 on 2026-09-04 unseen. But turning it into a fault here would
     * have been a guard built on numbers nobody has measured, and the cost of
     * a false positive is the oxygen channel:
     *
     *  - SNAS506I characterises A1 over 300 mV <= VCE <= VS-300 mV, and the
     *    91k/91k divider is 1 % on each leg, so a true 300 mV reconstructs
     *    anywhere in roughly 297-303 mV. The low corner faults a compliant
     *    point.
     *  - The ceiling is derived from a worst-case-low 3V3A. A HEALTHY rail
     *    allows VCE above it, so a healthy loop can sit outside the window.
     *  - gen_sch.py:783 records that this cell's real CE operating point has
     *    never been measured, so there is no evidence a good probe stays
     *    inside any narrower window either.
     *
     * The bias check is what detects the failure; it compares against a value
     * the datasheet actually specifies. Once someone measures the healthy CE
     * range on a working cell, a window here can be added with evidence behind
     * it. Review 2026-09-08, and Fab's call not to let this blank oxygen.
     *
     * A failed conversion leaves the invalid sentinel, which is the honest
     * answer and needs no fault of its own now that nothing is judged. */
    uint16_t ce_mv = 0u;
    if (o2p_mcu_adc_read_ce_mv(&ce_mv)) {
        s->ce_mv = ce_mv;
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

/* Consecutive cycles in which the TMP117 reported no new conversion.
 *
 * Tolerates a couple of misses before declaring the tip stale: the part runs a
 * 500 ms conversion cycle against this sampler's 1 Hz, so a healthy part is
 * ready every time, but a single missed poll must not drop the heater. Three
 * cycles is ~3 s, comfortably inside the 5 s O2P_HEATER_STALE_MS watchdog that
 * backs it up. Static rather than in g_cyc, which is memset every cycle. */
static uint8_t s_tip_notready_cycles;
#define O2P_TIP_STALE_CYCLES 3u

static void phase_temps(o2p_snapshot_t *s)
{
    int16_t t = 0;

    /* BEFORE the temperature read, because reading TEMP also clears
     * Data_Ready and would make every cycle look fresh. */
    bool ready = false;
    if (o2p_tmp117_data_ready(&ready) == O2P_TMP_OK && ready) {
        s_tip_notready_cycles = 0u;
    } else if (s_tip_notready_cycles < 0xFFu) {
        s_tip_notready_cycles++;
    }
    g_cyc.tip_fresh = (s_tip_notready_cycles < O2P_TIP_STALE_CYCLES);

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
     * temperatures with the cutoff silently disarmed.
     *
     * This used to be guarded by !armed, which meant it ran only while ALREADY
     * disarmed - so after a successful boot it never ran again and the glitch
     * above was exactly the case it could not catch. It now runs on a cadence.
     *
     * Every cycle while disarmed, so recovery is prompt; every tenth otherwise.
     * The slow cadence is deliberate and the heater fault test depends on it:
     * that test writes THIGH below the tip from the bench and watches the gate
     * fall, which the hardware does within one TMP117 conversion (500 ms). If
     * firmware noticed the changed threshold and cut duty at the same rate,
     * the trace could not distinguish the hardware cutoff from the firmware
     * interlock - which is the entire point of the measurement. Ten seconds
     * leaves that 20x separation while still bounding how long a genuinely
     * disarmed part can go unnoticed. */
    static uint8_t s_tmp_verify_div;
    bool armed = o2p_tmp117_safety_armed();
    if (!armed || ++s_tmp_verify_div >= 10u) {
        s_tmp_verify_div = 0u;
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

    /* The temperature that matters for the cell's rating is the gas it sees.
     * Shared with finish_o2() through o2p_gas_temperature() so the two cannot
     * disagree about which sensor speaks for the gas: this site used to read
     * g_cyc.t_tip whenever the chamber had failed, WITHOUT checking that the
     * tip had read either, and was correct only because the guard below
     * happened to exclude the both-failed case. */
    int16_t t_gas = o2p_gas_temperature(g_cyc.chamber_ok, g_cyc.t_chamber,
                                        g_cyc.tip_ok, g_cyc.t_tip);
    if (t_gas != O2P_I16_INVALID && t_gas > O2P_TEMP_OVER_C100) {
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
        /* A DRDY that does not behave is a PIN failure, not a bus failure, and
         * it gets its own bit. Collapsing every status into I2C_FAIL_ADS is how
         * a healthy ADS1119 came to be desoldered: the bus was fine, the fault
         * word said otherwise, and the board was believed.
         *
         * The driver decides which of those two a timeout was, by asking the
         * device: if the STATUS register reports a result ready but the pin
         * never fell, that is a pin fault and it returns O2P_ADS_DRDY; if the
         * device reports nothing ready either, the bus and the command worked
         * and the DEVICE did not convert, which is O2P_ADS_TIMEOUT.
         *
         * A previous version routed every timeout to the DRDY bit on the
         * argument that WREG and START had succeeded. That was a label change,
         * not a diagnosis - an acknowledged START, a stalled oscillator, a
         * brownout after START and a wrong device all produce a timeout with a
         * perfectly healthy pin. Distinguishing them needs evidence, so the
         * driver now collects some. */
        switch (st) {
        case O2P_ADS_DRDY:    g_cyc.faults |= O2P_F_ADS_DRDY_STUCK;  break;
        case O2P_ADS_CONFIG:  g_cyc.faults |= O2P_F_ADS_CONFIG_LOST; break;
        default:              g_cyc.faults |= O2P_F_I2C_FAIL_ADS;    break;
        }
        g_sub = n;          /* abandon the phase; a partial average is not a
                             * measurement of any defined interval */
        g_acc = 0;
        g_acc_clipped = false;
        return true;
    }
    /* Clip detection, per conversion rather than on the average. A converter
     * pinned at full scale reports the same code however the input moves, so
     * it cannot say "the signal left my range" - it just keeps answering. That
     * is how six minutes of a saturated TIA were read as a steady 607 uA when
     * the cell was actually polarising: 622 uA and 240 uA are the same number
     * once the channel is pinned.
     *
     * Checking the AVERAGE would miss a channel that clips on only some of the
     * eight O2 conversions, which is exactly what a signal drifting into the
     * rail looks like on its way in. The accumulator keeps no per-conversion
     * codes, so the flag is carried here instead.
     *
     * Full scale is +32767; single-ended readings should not go negative at
     * all, so -32768 is included as the other rail rather than assumed
     * unreachable. */
    if (o2p_ads1119_code_clipped(code)) {
        g_acc_clipped = true;
    }
    g_acc += code;
    g_sub++;
    return g_sub >= n;
}

static void finish_vref(o2p_snapshot_t *s)
{
    if ((g_cyc.faults & O2P_FAULTS_ADS_NO_CONVERSION) != 0u) {
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
        g_cyc.vref_measured = true;
    }
}


/* The gas the cell is in this cycle, for the water-vapour correction.
 *
 * `valid` is false whenever the SHT45 did not deliver BOTH a humidity and a
 * chamber temperature this cycle. Substituting the TIP temperature would be
 * worse than refusing: the tip is heated, so its saturation pressure is not
 * the gas's, and a plausible wrong correction is the failure mode this
 * firmware is written against.
 *
 * What IS substituted is the chamber's own last measured reading, for at most
 * O2P_RH_MAX_AGE_S. That is not a fallback to a plausible number - it is the
 * same sensor's real measurement, bounded by an age that covers the 30 s
 * post-pulse mask and nothing longer. Past the cap the gas stays invalid and
 * O2_COMP publishes its sentinel, so a dead SHT45 is still reported as one;
 * what no longer happens is a scheduled de-creep pulse blanking the primary
 * oxygen channel and labelling it a bus failure.
 *
 * P comes from the barometer when there is one. There is not: the BMP390 is
 * DNP on Rev A and PRESSURE_HPA publishes 0, so this is the ASSUMED_P_HPA
 * register in practice. The test is written against the snapshot anyway so
 * that populating the part on a later revision needs no change here. */
static o2p_gas_t cycle_gas(const o2p_snapshot_t *s)
{
    o2p_gas_t g;
    g.valid = g_cyc.chamber_ok && g_cyc.rh_ok;
    g.rh_pct = (float)g_cyc.rh * 0.01f;
    g.t_c = (float)g_cyc.t_chamber * 0.01f;
    g.p_hpa = (s->pressure_hpa != 0u) ? (float)s->pressure_hpa
                                      : (float)g_rm.cfg.assumed_p_hpa;
    /* Only a measured gas enters the cache; the bridging happens at the use
     * site, so the caller can still tell a fresh reading from a bridged one. */
    o2p_gas_cache_update(&g_gas_cache, &g, g_uptime_s);
    return g;
}

/* Was the cell at its commanded bias when we last managed to look?
 *
 * Tri-state, and UNKNOWN refuses. The bias is measured in PH_WE/PH_RE, which
 * run AFTER finish_o2() has already decided whether to accept an air point -
 * so within one cycle the calibration cannot see its own cycle's verdict. It
 * uses the previous cycle's, which is sound because the bias is a physical
 * standing condition, not a per-sample quantity: a cell that was 939 mV off
 * target a second ago is not at target now.
 *
 * This exists because an air point is PERMANENT. o2.h is explicit that a bad
 * one carries a bias "for the life of the probe", and on 2026-09-08 the probe
 * ran for hours at +341 mV against a commanded -598 mV with a clean fault
 * word - a calibration taken in that window would have been stored, and the
 * later discovery of the bias fault could not have taken it back. Found by
 * review 2026-09-08. */
typedef enum {
    BIAS_UNKNOWN = 0,
    BIAS_GOOD,
    BIAS_BAD,
} bias_verdict_t;
static bias_verdict_t s_bias_verdict;

/* WE_BUF and RE_BUF, the buffered cell electrodes on AIN2/AIN3.
 *
 * Buffered straight to the pin - no divider - so the code converts to
 * millivolts and stops. Referenced to the external VREF, the same reference
 * the oxygen channel uses, because the point of the pair is the DIFFERENCE and
 * a difference across two references measures the references.
 *
 * SAMPLED AFTER PH_O2 ON PURPOSE. Putting them before it would change which
 * channel the mux leaves when it converts AIN0, and a channel change in front
 * of the oxygen conversion is the leading suspect for the 0.51 % step in
 * O2_RAW across the 2026-09-07 install. Ordering them behind O2 makes this
 * telemetry unable to move the number it exists to explain.
 */
static void finish_electrode(o2p_snapshot_t *s, bool working)
{
    if ((g_cyc.faults & O2P_FAULTS_ADS_NO_CONVERSION) != 0u) {
        return;
    }
    /* Every way this reading can be electrically meaningless, refused rather
     * than clamped. Clamping a negative code to 0 mV was the bug: 0 is not the
     * invalid sentinel, so a failed WE read became a real-looking 0 mV and the
     * bias computed from it became a real-looking number from no measurement.
     *
     *  - g_acc_clipped: the converter saturated.
     *  - a negative code: SBAS925A 8.3.2 - in single-ended mode only the
     *    positive range is used, so below AGND is outside the valid domain.
     *  - an unmeasured VREF: these channels are scaled BY that reference, and
     *    finish_vref() keeps the nominal scale when it refuses one, so the
     *    volts would be assumed rather than measured.
     *
     * That last test READ THE SHARED FAULT WORD until 2026-09-08, and the
     * fault word is cumulative within a cycle. PH_O2 runs before PH_WE, and
     * finish_o2() raises ADC_RANGE from two conditions that say nothing about
     * these channels: a pinned O2 conversion, and an out-of-range COMPUTED
     * oxygen fraction. So the moment the AFE collapsed, the bias diagnostic
     * that exists to explain a collapsed AFE went silent with it - measured
     * 2026-09-08, bit 11 set from 17:40 on and WE/RE/CELL_BIAS_MV sentinel
     * for every cycle after. A guard must not be disarmed by the failure it
     * is there to name. vref_measured asks the question actually meant here.
     */
    if (g_acc_clipped || !g_cyc.vref_measured) {
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_CELL;
    if (code < 0) {
        return;
    }
    int32_t uv = o2p_ads1119_code_to_uv(code, g_cyc.vref_mv);
    int32_t mv = uv / 1000;
    if (mv < 0 || mv > 65534) {
        return;
    }
    if (working) {
        s->we_buf_mv = (uint16_t)mv;
    } else {
        s->re_buf_mv = (uint16_t)mv;
        /* Both halves present, and neither is the invalid sentinel, or the
         * bias stays invalid. A difference computed from one real reading and
         * one 0xFFFF is a number, which is the problem. */
        s_bias_verdict = BIAS_UNKNOWN;
        if (s->we_buf_mv != O2P_U16_INVALID) {
            int32_t bias = (int32_t)s->we_buf_mv - mv;
            if (bias > 32767) { bias = 32767; }
            if (bias < -32767) { bias = -32767; }
            s->cell_bias_mv = (int16_t)bias;

            /* And COMPARE it with what was commanded, which hw_contract.h has
             * specified since 2026-09-04 as the point of this pair - "an
             * EXISTENCE check: is the cell biased at all" - and which nothing
             * implemented until 2026-09-08. Measuring a quantity and never
             * testing it is how the probe published hours of oxygen from a
             * cell reading +341 mV against a commanded -598 mV without one
             * fault bit.
             *
             * The target is DERIVED FROM O2P_LMP_REFCN_INTENDED rather than
             * written here as 24 % and a minus sign. Two hardcoded copies of a
             * value whose only source of truth is that constant would agree
             * today and go stale together the day the bias step changes -
             * exactly the source-of-truth failure the guard checklist names.
             * Review 2026-09-08. The window is deliberately far wider than
             * DS-0637's own +/-10 mV: this is not a trim check and must not
             * fire on a healthy probe. The buffers are unity followers with
             * their own offsets, VREF has a +/-20 mV trim band, and the
             * datasheet's VOS_RW reaches +/-1750 uV MAX at this bias (that is
             * VOS_RW, the offset; TcVOS_RW is its +/-8 uV/K DRIFT - the first
             * version of this comment used the wrong name). 150 mV
             * clears all of that by an order of magnitude while still being a
             * quarter of the commanded value - it catches an open loop, a
             * reversed sign, and a bias that is simply not there.
             *
             * AFE_CONFIG_MISMATCH rather than a bit of its own because the
             * fault word has none left, and because the meaning fits: the AFE
             * is not delivering the configuration it acknowledged. CE_MV and
             * LMP_READBACK are what separate the analog cause from the digital
             * one.
             *
             * WHAT THIS DOES, precisely, because the first version of this
             * comment claimed something it did not do. The bit is in
             * INVALIDATE_O2 and absent from POST_O2, so raising it here - after
             * the oxygen verdict was frozen - still withholds both O2_RAW and
             * O2_COMP for this cycle. It does NOT restart settling and does NOT
             * rewrite the LMP91000: phase_afe() drives those from its own
             * readback, and a bad bias is not evidence the register image is
             * wrong. Withholding the reading is the safety-critical part and it
             * is what this delivers; a settling restart would add a way to wedge
             * a healthy probe forever without adding protection. Fab's call,
             * 2026-09-08, after review found the original claim false. */
            if (g_cyc.vref_measured) {
                int32_t want = o2p_lmp_commanded_bias_mv((int32_t)g_cyc.vref_mv);
                int32_t err = bias - want;
                if (err < 0) { err = -err; }
                if (err > O2P_CELL_BIAS_TOLERANCE_MV) {
                    g_cyc.faults |= O2P_F_AFE_CONFIG_MISMATCH;
                    s_bias_verdict = BIAS_BAD;
                } else {
                    s_bias_verdict = BIAS_GOOD;
                }
            }
        }
    }
}

/* LMP91000 die temperature from the AIN0 accumulation taken while OP_MODE was
 * 111. Everything about this is the same as an electrode read except what the
 * pin is carrying, so the same three refusals apply: a clipped converter, a
 * VREF outside the trim band (these volts are scaled BY it), and a negative
 * code, which single-ended mode cannot legitimately produce.
 *
 * There is no plausibility check on the resulting temperature, deliberately.
 * The oxygen channel's own swing decodes to a believable 72-77 C, so any
 * window wide enough to accept real readings also accepts a failed mode
 * switch. The mode readback in o2p_lmp91000_temp_enter() is the check; adding
 * a second one here that cannot discriminate would only look like defence. */
static void finish_t_afe(o2p_snapshot_t *s)
{
    /* The reference has to have been MEASURED, not assumed. cycle_begin()
     * seeds g_cyc.vref_mv with the 2500 mV trim target, and finish_vref()
     * returns early on a failed conversion WITHOUT replacing it and without
     * raising ADC_RANGE - so a transient ADS failure in PH_VREF followed by a
     * healthy temperature conversion would publish a number scaled by a
     * reference nobody read. Small in magnitude here, roughly 0.3 C, and
     * exactly the kind of unevaluable input that must not read as OK.
     *
     * This replaces a cycle-wide ADC_RANGE test, which was wrong in both
     * directions: it missed the assumed-reference case entirely, and it threw
     * away a perfectly good temperature whenever the OXYGEN channel clipped -
     * losing the diagnostic precisely when things were going wrong. What
     * matters to this channel is its own conversions plus the reference.
     * Found by review 2026-09-08. */
    if (!g_cyc.vref_measured) {
        return;
    }
    if (g_acc_clipped || (g_cyc.faults & O2P_FAULTS_ADS_NO_CONVERSION) != 0u) {
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_CELL;
    if (code < 0) {
        return;
    }
    /* ROUNDED, not truncated. The other channels floor microvolts and can
     * afford to; this one is bounded by a window taken from Table 1's
     * endpoints, and flooring puts the +85 C endpoint OUTSIDE it: at the
     * measured VREF of 2494 mV, a true 861 mV reconstructs as 860977 uV,
     * floors to 860, and is refused - the datasheet's own hot endpoint,
     * rejected as implausible. Rounding also halves the quantisation error,
     * which flooring pushed from the advertised 0.41/2.12 C to 0.53/2.21 C
     * end to end. Found by review 2026-09-08. */
    int32_t uv = o2p_ads1119_code_to_uv(code, g_cyc.vref_mv);
    int32_t mv = (uv + 500) / 1000;
    if (mv < 0 || mv > 65534) {
        return;
    }
    int16_t c100 = 0;
    if (o2p_lmp_temp_c100_from_mv((uint16_t)mv, &c100)) {
        s->t_afe = c100;
    }
}

static void finish_o2(o2p_snapshot_t *s)
{
    if ((g_cyc.faults & O2P_FAULTS_ADS_NO_CONVERSION) != 0u) {
        return;
    }
    /* A pinned converter is not a measurement. Raise ADC_RANGE - which
     * already means "converter saturated or out of window" and already
     * invalidates O2 - so the reading is withheld rather than published as a
     * confident number that happens to be the rail. The raw code is still
     * recorded below for the bench; what changes is that nothing downstream
     * treats it as valid. */
    if (g_acc_clipped) {
        g_cyc.faults |= O2P_F_ADC_RANGE;
    }
    int32_t code = g_acc / (int32_t)O2P_N_O2;
    int32_t uv = o2p_ads1119_code_to_uv(code, g_cyc.vref_mv);
    s->afe_vout_mv = (uv < 0) ? 0u : (uint16_t)(uv / 1000);

    int32_t cell_na = o2p_cell_na_from_code(code, g_cyc.vref_mv);

    /* uA * 100, i.e. 10 nA per count. */
    s->o2_raw = o2p_encode_raw_ua_x100(cell_na);

    int16_t t_gas = o2p_gas_temperature(g_cyc.chamber_ok, g_cyc.t_chamber,
                                        g_cyc.tip_ok, g_cyc.t_tip);

    o2p_cal_t cal = g_cal;
    if (cal.cal_air_na <= 0) {
        /* Never calibrated. Substitute the datasheet nominal so the raw
         * channel still converts, and raise CAL_DEFAULT - which invalidates
         * the COMPENSATED channel, because that nominal spans 0.04-0.10 mA. */
        cal.cal_air_na = O2P_CAL_AIR_NOMINAL_NA;
        g_cyc.faults |= O2P_F_CAL_DEFAULT;
    }

    /* Two gases, and the difference is deliberate. `fresh` is what the SHT45
     * delivered THIS cycle and nothing else; `gas` is that, or the same
     * sensor's last measurement if it is younger than O2P_RH_MAX_AGE_S. The
     * published conversion may bridge; an air-point calibration may not. */
    const o2p_gas_t fresh = cycle_gas(s);
    o2p_gas_t gas = fresh;
    (void)o2p_gas_cache_apply(&g_gas_cache, &gas, g_uptime_s);

    /* A non-zero temperature coefficient with no temperature is not a
     * compensated reading. Rather than silently applying a zero correction
     * and presenting the result as compensated, refuse it. */
    if (cal.tempco_per_k != 0.0f && t_gas == O2P_I16_INVALID) {
        g_cyc.faults |= O2P_F_I2C_FAIL_TMP;
        s->o2_comp = O2P_U16_INVALID;
    } else {
        /* DRY BASIS. The dilution term is up to 20 % at the operating point,
         * and it is unevaluable without RH, chamber temperature and P - in
         * which case this returns UNEVALUABLE and o2p_encode_percent emits
         * the sentinel. It does not fall back to the wet-basis number: that
         * would publish the uncorrected reading under the corrected name. */
        float c = 0.0f;
        o2p_status_t st = o2p_dry_fraction_from_current(
            &cal, cell_na,
            (t_gas != O2P_I16_INVALID) ? t_gas : cal.cal_temp_c100, &gas, &c);
        if (st == O2P_RANGE) {
            g_cyc.faults |= O2P_F_ADC_RANGE;
        }
        s->o2_comp = o2p_encode_percent(st, c);
    }

    /* Air-point calibration, if an operator asked for one. */
    if (g_rm.cal_requested) {
        g_rm.cal_requested = false;
        /* Judge the raw channel, not the compensated one: a probe that has
         * never been calibrated always fails the compensated test, which
         * would make calibration impossible. */
        /* `fresh`, NOT `gas`: a calibration is permanent, so it gets a
         * humidity measured in this cycle or none at all. Bridging a 30 s gap
         * is right for a sample that will be superseded in a second and wrong
         * for a constant that every later reading divides by. */
        /* SETTLING is not in g_cyc.faults yet, so o2p_o2_valid() alone would
         * accept an air point taken during the documented 15-minute post-bias
         * settle - storing a transient current as the probe's permanent air
         * constant, and invalidating the very sample it came from seconds
         * later. Test the deadline directly. */
        bool settled = (g_uptime_s >= g_settle_deadline_s);
        /* And a calibration needs a MEASURED temperature, not a fallback one.
         * The conversion may substitute cal_temp_c100 for a missing gas
         * temperature - that only means "assume we are at the calibration
         * temperature", which is recoverable. Storing a fabricated 25.00 C AS
         * the calibration temperature is not: it becomes the permanent
         * reference every later tempco correction is measured against, so a
         * probe calibrated with both temperature sensors down carries a false
         * reference for life while looking perfectly calibrated. Temperature
         * faults are deliberately absent from the raw-O2 validity mask, so
         * o2p_o2_valid() does not catch this. */
        /* And the cell has to have BEEN AT ITS COMMANDED BIAS. See
         * s_bias_verdict: an air point is permanent, the bias check does not
         * run until two phases after this decision, and UNKNOWN - no reading
         * yet, or a cycle in which the electrodes could not be converted -
         * refuses rather than assuming the best. */
        if (settled && t_gas != O2P_I16_INVALID &&
            s_bias_verdict == BIAS_GOOD &&
            o2p_o2_valid(g_cyc.faults) &&
            o2p_calibrate_air(&g_cal, cell_na, t_gas, &fresh)) {
            g_rm.cfg.cal_air_na = g_cal.cal_air_na;
            g_rm.cfg.cal_temp_c100 = g_cal.cal_temp_c100;
            /* Stored WITH the air point, never separately: a cal_air_na
             * without the fraction it was taken at is the 1-2 % bias again,
             * and one without the pressure it was taken at leaves the cell's
             * pressure-dependent gain permanently uncorrected. */
            g_rm.cfg.cal_air_frac_x1000 =
                (uint16_t)(g_cal.air_frac * 100000.0f + 0.5f);
            g_rm.cfg.cal_p_hpa = (uint16_t)(g_cal.cal_p_hpa + 0.5f);
            o2p_regmap_set_cal_result(&g_rm, O2P_CMD_OK);
        } else {
            /* Every refusal below was previously indistinguishable from
             * success on the bus. */
            o2p_regmap_set_cal_result(&g_rm, O2P_CMD_FAILED);
        }
        /* A commit asked for alongside the calibration waits until here, so
         * what reaches flash is the calibration the master was acknowledged
         * for. Raised even when the point was refused: the operator asked for
         * the live config to be persisted, and that is what it gets. */
        if (g_rm.commit_after_cal) {
            g_rm.commit_after_cal = false;
            /* Through the gate, not straight to commit_pending: a frame that
             * asked for a calibration, a serial change and a commit at once
             * has TWO things to wait for, and this is only one of them. */
            o2p_regmap_request_commit(&g_rm);
        }
        /* A refused calibration leaves the old constants in place. An air
         * point taken with the SHT45 down is refused here, not stored with an
         * assumed humidity: O2-HUMIDITY-CORRECTION.md 3b measures that
         * assumption as a permanent +1.4 to +2.2 % error in K. */
    }
}

static void cycle_publish(o2p_snapshot_t *s)
{
    /* The FLAG was raised in cycle_begin(), before PH_O2 froze the oxygen
     * verdict; only the countdown is computed here. Re-raising it is kept so
     * a settle window that OPENS mid-cycle - o2p_settle_restart() is callable
     * from the supervision - is still reported in this frame's fault word.
     * That is deliberately a weaker guarantee than the verdict gets: a window
     * that opened after the conversion cannot invalidate it retroactively,
     * and the next cycle sees it from the top. */
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
    /* The freeze is SUBTRACTIVE: start from the fault word as it stands now
     * and drop only the faults the electrode phases are allowed to have
     * raised since PH_O2 (O2P_FAULTS_POST_O2). A snapshot would instead have
     * dropped everything raised later, including state flags that outrank the
     * measurement - which is exactly how SETTLING got lost. */
    uint16_t o2_faults = g_cyc.o2_measured
        ? (uint16_t)(g_cyc.faults_at_o2 |
                     (g_cyc.faults & (uint16_t)~O2P_FAULTS_POST_O2))
        : g_cyc.faults;
    if (!o2p_o2_valid(o2_faults)) {
        s->o2_raw = O2P_I16_INVALID;
    }
    if (!o2p_o2_comp_valid(o2_faults)) {
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
            /* Bench override, registers 0x0060/0x0061. Read straight from the
             * register map rather than copied into the config: it is
             * volatile on purpose and must not acquire a flash-backed twin. */
            .rh_consent      = (g_rm.cfg.heater_rh_consent ==
                                O2P_HEATER_RH_CONSENT_MAGIC),
            .session         = g_rm.heater_test_session,
            .test_override   = g_rm.heater_test_armed,
            .test_duty_x100  = g_rm.heater_test_duty_x100,
            .test_tip_sp_valid =
                (g_rm.heater_test_tip_sp_c100 != O2P_I16_INVALID),
            .test_tip_sp_c100 = g_rm.heater_test_tip_sp_c100,
            .test_kp_x100    = g_rm.heater_test_kp_x100,
            .test_ki_x100    = g_rm.heater_test_ki_x100,
            /* Persistent tip loop, registers 0x0049..0x004C. Read from the
             * CONFIG this time, not the volatile map: surviving a reset is the
             * entire point of the mode. */
            .tip_consent     = (g_rm.cfg.heater_tip_consent ==
                                O2P_HEATER_TIP_CONSENT_MAGIC),
            .tip_sp_valid    = (g_rm.cfg.tip_setpoint_c100 != O2P_I16_INVALID),
            .tip_sp_c100     = g_rm.cfg.tip_setpoint_c100,
        };
        const o2p_heater_in_t hin = {
            .drive_possible   = o2p_heater_compiled_in(),
            .safety_armed     = o2p_tmp117_safety_armed(),
            .pin_integrity_ok = o2p_heater_pin_integrity_ok(),
            .rh_valid         = g_cyc.rh_ok,
            .rh_x100          = g_cyc.rh,
            /* Freshness is part of validity FOR THE HEATER, and only for it.
             * A frozen conversion engine reads as a healthy constant
             * temperature: the tip PI would hold duty against a fixed error
             * and the 80 C clamp would be watching the same frozen number, so
             * neither backs off. T_TIP itself still publishes normally - the
             * measurement channel is not this interlock's business, and
             * blanking it here would hide the evidence. */
            .tip_valid        = g_cyc.tip_ok && g_cyc.tip_fresh,
            .t_tip_c100       = g_cyc.t_tip,
            .chamber_valid    = g_cyc.chamber_ok,
            .t_chamber_c100   = g_cyc.t_chamber,
            /* The die is a diagnostic channel everywhere else; here it is the
             * only reference that can witness a stuck-on FET. */
            .die_valid        = (s->t_die != O2P_I16_INVALID),
            .t_die_c100       = s->t_die,
            /* Heating adds ~86 mA. A rail already out of tolerance is not the
             * place to put more load, and VA_LOW in particular means the AFE
             * may have lost its bias already. */
            .supply_ok        = (g_cyc.faults &
                                 (O2P_F_VA_LOW | O2P_F_VIN_LOW)) == 0u,
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

    /* Latch the transient bits, then publish this cycle's faults OR whatever
     * is still latched.
     *
     * The order matters: bits raised THIS cycle are added to the latch before
     * the window is tested, so a fault that is still present cannot be
     * expired by a deadline set when it first appeared. The window is
     * refreshed on every new occurrence, so a repeatedly glitching probe
     * never shows clean between glitches. */
    if ((g_cyc.faults & O2P_FAULTS_ADS_NO_CONVERSION) != 0u &&
        g_ads_fail_count != 0xFFFFu) {
        g_ads_fail_count++;             /* saturates rather than wrapping */
    }

    s->faults = o2p_fault_latch_step(&g_fault_latch, g_cyc.faults, g_uptime_s);

    /* Accumulated from the PUBLISHED word, so what FAULTS_EVER reports is
     * exactly what a reader could have seen, latch included - not a second,
     * subtly different history. */
    g_faults_ever |= s->faults;
    s->faults_ever = g_faults_ever;
    s->ads_fail_count = g_ads_fail_count;

    o2p_regmap_publish(&g_rm);
}

/* One step of the sampler. Returns true when a cycle has just been published. */
static bool sampler_step(void)
{
    o2p_snapshot_t *s = o2p_regmap_staging(&g_rm);

    switch (g_phase) {
    case PH_RAILS:  phase_rails(s); g_phase = PH_AFE;   break;
    case PH_AFE:    phase_afe(s);   g_phase = PH_TEMPS; break;
    case PH_TEMPS:  phase_temps(s); g_phase = PH_VREF; g_sub = 0; g_acc = 0; g_acc_clipped = false; break;

    case PH_VREF:
        /* Measured against the ADS1119's OWN internal reference: a converter
         * referenced to the thing it is checking cannot detect that thing
         * drifting. */
        if (accumulate(O2P_ADS_MUX_AIN1_AGND, O2P_ADS_DR_90SPS, false, O2P_N_VREF)) {
            finish_vref(s);
            /* Straight to O2: the old PH_VIN step in between sampled AIN3 as
             * though it were the input rail. VIN is read in phase_rails now. */
            g_phase = PH_O2; g_sub = 0; g_acc = 0; g_acc_clipped = false;
        }
        break;

    case PH_O2:
        if (accumulate(O2P_ADS_MUX_AIN0_AGND, O2P_ADS_DR_20SPS, true, O2P_N_O2)) {
            finish_o2(s);
            /* Freeze the verdict on oxygen here, before the electrode phases
             * can add converter faults to the same word. */
            g_cyc.faults_at_o2 = g_cyc.faults;
            g_cyc.o2_measured = true;
            g_phase = PH_WE; g_sub = 0; g_acc = 0; g_acc_clipped = false;
        }
        break;

    case PH_WE:
        if (accumulate(O2P_ADS_MUX_AIN2_AGND, O2P_ADS_DR_90SPS, true, O2P_N_CELL)) {
            finish_electrode(s, true);
            g_phase = PH_RE; g_sub = 0; g_acc = 0; g_acc_clipped = false;
        }
        break;

    case PH_RE:
        if (accumulate(O2P_ADS_MUX_AIN3_AGND, O2P_ADS_DR_90SPS, true, O2P_N_CELL)) {
            finish_electrode(s, false);
            g_phase = PH_TAFE; g_sub = 0; g_acc = 0; g_acc_clipped = false;
        }
        break;

    /* LAST, and after PH_O2 has frozen its verdict into faults_at_o2.
     *
     * For the length of this phase VOUT carries the die temperature instead of
     * the TIA output, so AIN0 is not oxygen. Putting it here means no oxygen
     * conversion can overlap the window: this cycle's reading was taken and
     * closed several phases ago, and the next cycle begins with phase_afe(),
     * whose MODECN readback is exactly what catches a mode this failed to
     * restore. So the recovery path already exists and is not duplicated here.
     *
     * OP_MODE 111 leaves the TIA powered, so the cell is never unbiased and
     * none of this costs the DS-0637 settling penalty. */
    case PH_TAFE:
        if (g_sub == 0u) {
            uint8_t back = 0u;
            o2p_lmp_status_t tst = o2p_lmp91000_temp_enter(&back);
            if (tst != O2P_LMP_OK) {
                /* T_AFE stays at its invalid sentinel either way - an
                 * unreadable temperature is not a temperature - but the two
                 * failures are NOT the same event and must not be reported as
                 * one.
                 *
                 * IO is a bus problem and takes no position on the cell.
                 *
                 * MISMATCH means the part read back a mode we did not ask for,
                 * and the one that matters is 110: temperature with the TIA
                 * OFF, which unbiases the cell and starts the DS-0637 fifteen
                 * minutes. temp_enter() restores 011 before returning, so by
                 * the next cycle phase_afe() sees a clean register image and
                 * the interruption is erased from the record - the probe would
                 * then publish oxygen from a cell that was actually settling.
                 * Raising it here is the only place that event is visible.
                 * Found by review 2026-09-08. */
                if (tst == O2P_LMP_IO) {
                    g_cyc.faults |= O2P_F_I2C_FAIL_LMP;
                } else {
                    g_cyc.faults |= O2P_F_AFE_CONFIG_MISMATCH;
                    /* Only if the mode we actually read STOPPED driving the
                     * cell. The common safe case is that the write was ignored
                     * and MODECN is still 011 - the potentiostat never paused,
                     * nothing is settling, and restarting it would hold a
                     * healthy probe out of the compensated channel for fifteen
                     * minutes every time an intermittent I2C glitch landed
                     * here. The first version restarted unconditionally because
                     * set_mode() discarded the readback that answers this.
                     * Review 2026-09-08. */
                    if (o2p_lmp_mode_unbiases_the_cell(back)) {
                        restart_settling();
                    }
                }
                g_phase = PH_PUBLISH;
                break;
            }
        }
        if (accumulate(O2P_ADS_MUX_AIN0_AGND, O2P_ADS_DR_90SPS, true, O2P_N_CELL)) {
            finish_t_afe(s);
            if (o2p_lmp91000_temp_exit() != O2P_LMP_OK) {
                /* VOUT may still be the sensor. Say so now rather than let the
                 * next cycle be the first sign; phase_afe() does the actual
                 * reconfiguration and settling decision. */
                g_cyc.faults |= O2P_F_AFE_CONFIG_MISMATCH;
            }
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

    /* Deliberately discarded, and the reason is now narrower than it used to
     * be claimed. Both preconditions init proves ARE re-checked at run time:
     * DRDY before every conversion, and the config readback on every
     * channel/reference change (ads1119.c). Each reaches the fault word as
     * O2P_F_ADS_DRDY_STUCK or O2P_F_I2C_FAIL_ADS.
     *
     * An earlier version of this comment claimed the config was re-verified
     * per conversion when read_cfg() had exactly one caller - inside init. It
     * was not true, and a specific comment describing a check that does not
     * exist is worse than no comment: it tells the next reader to stop
     * looking. The check it described now exists, which is why this is
     * discardable at all.
     *
     * A boot-only check would report to nobody - there is no fault word yet
     * at this point in bring-up - and that is precisely the shape that let a
     * dead DRDY masquerade as measurements. */
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

    /* Seed the reset cause into BOTH snapshots before the bus is enabled.

     * Modbus answers about 1.6 s before the first cycle publishes, and a

     * diagnostic poll in that window would otherwise read 0 - a real RCC

     * value meaning "no flags", which is the exact confident zero this

     * channel was fixed to stop reporting. */

    for (unsigned i = 0; i < 2u; i++) {

        g_rm.buf[i].reset_cause = o2p_reset_cause();

    }
    (void)o2p_config_load(&g_rm.cfg);   /* defaults on absence or corruption */
    remember_stored_serial();
    load_cal_from_config();

    /* The updater, before the bus is served: a master that polls the update
     * block during the first millisecond must get a real answer, not
     * exception 02 from a register map whose engine is not attached yet. */
    o2p_update_target_init();
    o2p_update_init(&g_upd, o2p_update_target_ops(), false, O2P_FW_VERSION, 0u);
    {
        uint32_t staged_len, staged_crc;
        if (o2p_update_target_has_staged(&staged_len, &staged_crc)) {
            /* A transfer completed and verified, and then the probe reset
             * before it was told to boot. Come up saying so, rather than
             * IDLE - otherwise the only way to find out is to push the image
             * again. */
            o2p_update_adopt_staged(&g_upd, staged_len, staged_crc);
        }
    }
    g_rm.upd = &g_upd;

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
                /* Armed BEFORE the switch. The frame mark has to be taken
                 * while the old settings are still live, or a frame that
                 * arrived in the gap would be counted as proof of settings it
                 * was never sent at. */
                o2p_sp_arm(&g_serial_probation, o2p_millis(),
                           o2p_modbus_frames_ok(), g_stored_addr,
                           g_stored_baud, g_stored_parity);
                o2p_modbus_reconfigure(&g_rm.cfg);
            }
            /* Before the commit, so a confirmation reached on this pass can
             * release a commit that was waiting for it without costing
             * another lap. */
            serial_probation_service();
            if (g_rm.commit_pending) {
                g_rm.commit_pending = false;
                /* The return value used to be discarded, so a failed erase or
                 * program - a worn page, a brownout mid-write - left the
                 * master believing the configuration was persisted while the
                 * probe still ran from RAM. */
                bool stored = o2p_config_store(&g_rm.cfg);
                o2p_regmap_set_commit_result(
                    &g_rm, stored ? O2P_CMD_OK : O2P_CMD_FAILED);
                if (stored) {
                    /* Flash and the fallback move together, or the next
                     * probation would restore settings that are no longer the
                     * ones a reset would produce. A FAILED store deliberately
                     * leaves the old fallback in place: nothing reached
                     * flash, so nothing about a reset changed either. */
                    remember_stored_serial();
                }
                load_cal_from_config();
            }

            /* One page erase, or one slice of a verify CRC, per pass. Here
             * with the other deferred work because both stall instruction
             * fetch: doing either while the transmitter is running would
             * stop the code that has to release DE afterwards. */
            (void)o2p_update_service(&g_upd);

            if (g_upd.boot_requested) {
                /* Everything from here is one-way. The heater is forced off
                 * first because the reset is about to leave a PWM pin behind
                 * with no code driving it, and 1 W against the membrane
                 * carrier is not a thing to leave to a pull-down. */
                o2p_heater_force_off();
                o2p_update_target_reboot_to_loader(g_upd.stay_requested);
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
