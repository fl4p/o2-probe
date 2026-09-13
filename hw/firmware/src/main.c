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
#include "hw_caps.h"
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
                                          g_rm.probation_acked);
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
/* Did the LAST heater-pulse transaction fail on the bus?
 *
 * Assigned at every pulse attempt, so it is self-clearing: a successful pulse
 * replaces a failed one's flag and nothing has to remember to reset it. It
 * exists because the mask no longer raises a fault by itself, and a pulse that
 * NACKed is a real I2C failure that would otherwise spend its whole 350 s
 * window looking exactly like scheduled maintenance. */
static bool g_sht_pulse_failed;
/* The last chamber reading that was actually measured, so the mask after a
 * scheduled SHT45 de-creep pulse is BRIDGED rather than published as an
 * oxygen sentinel three times a day. Bounded by O2P_RH_MAX_AGE_S; see o2.h
 * for the derivation and for why a dead sensor still reaches the sentinel.
 *
 * O2P_SHT_RECOVERY_MS used to be defined HERE, 30 s, and o2.h derived the
 * cache bound from it across a file boundary with nothing enforcing the
 * relation. Both now live in o2.h under one derivation and one static
 * assertion; the measurement that moved it to 350 s is quoted there. */
static o2p_gas_cache_t g_gas_cache;

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
    PH_OFFSET,     /* P4: ADS1119 MUX=111, inputs shorted to AVDD/2 */
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
    int16_t  t_ext;
    uint16_t rh;
    bool     tip_ok;
    bool     ext_ok;
    bool     ext_fresh;     /* ext Data_Ready seen recently; heater bridge only */
    /* tip_ok says the read SUCCEEDED; this says the part has actually
     * converted since we last looked. Only the heater consumes it - see
     * phase_temps(). */
    bool     tip_fresh;
    bool     chamber_ok;
    bool     rh_ok;
    uint16_t heater_block;
    /* HEATER_LAW (0x0008). 0xFFFF on a cycle the heater was not stepped - the
     * memset at cycle start zeroes this, so it is set explicitly below rather
     * than left at a zero that would read as O2P_HEATER_LAW_RH. */
    uint16_t heater_law;
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
    /* The debug override (diag opcode 9) as latched for THIS cycle: every
     * ADS1119 conversion on the internal 2.048 V reference, scaled by it. */
    bool     ads_internal;
    /* P3: the sense tap faulted, so THIS cycle runs on the ADS1119's internal
     * 2.048 V reference automatically. Distinct from ads_internal, which is a
     * human forcing it: a fallback that cannot be told apart from a deliberate
     * override is not a diagnosis. */
    bool     ads_fallback;
    /* P4 evidence, published in ADC_HEALTH rather than inferred later. */
    bool     mux_stuck;
    bool     offset_bad;
    int32_t  offset_code;
    uint8_t  prev_mux;
    int32_t  prev_code;
    bool     prev_valid;
} g_cyc;

static uint32_t s_cycle_start_ms;

static void cycle_begin(void)
{
    memset(&g_cyc, 0, sizeof(g_cyc));
    s_cycle_start_ms = o2p_millis();
    g_cyc.faults = 0u;
    /* Until the reference is actually measured this cycle, assume the trim
     * target rather than carrying last cycle's number forward. */
    g_cyc.vref_mv = O2P_HW_VREF_TARGET_MV;
#if O2P_DEBUG_ENABLE
    /* Latched once, here: a flag written mid-cycle takes effect at the next
     * cycle, so no phase averages conversions taken against two references. */
    g_cyc.ads_internal = (g_rm.ads_internal_ref != 0u);
#endif
    /* P3/P4 state is PER CYCLE: a fallback that engaged last cycle must not
     * silently persist, and a stuck-mux signature must be re-earned. */
    g_cyc.ads_fallback = false;
    g_cyc.mux_stuck = false;
    g_cyc.offset_bad = false;
    g_cyc.offset_code = 0;
    g_cyc.prev_valid = false;
    g_cyc.t_tip = O2P_I16_INVALID;
    g_cyc.t_chamber = O2P_I16_INVALID;
    g_cyc.t_ext = O2P_I16_INVALID;
    g_cyc.ext_ok = false;
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

#if O2P_HW_VIN_MON_ON_MCU
    uint16_t vin_mv = 0u;
    if (o2p_mcu_adc_read_vin_mv(o2p_cfg_vin_div_x1000(&g_rm.cfg), &vin_mv)) {
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
#endif

    /* Die temperature, from the same ADC and therefore free of I2C1. It
     * raises no fault of its own: it is a +/-5 C reading of the silicon, not
     * of the gas, and nothing downstream may act on it. It is published so
     * that a T_TIP or T_CHAMBER which disagrees with it, or which vanishes
     * while it survives, points at the bus rather than at the weather. */
    int16_t die_c100 = 0;
    if (o2p_mcu_adc_read_die_c100(&die_c100)) {
        s->t_die = die_c100;
    }

#if O2P_HW_CE_MON_CONNECTED
    /* The counter-electrode drive: PUBLISHED, and deliberately NOT judged.
     * Only read on boards where CE_MON connects to an MCU pin (Rev B).
     * On Rev A, PA4 is unconnected, so s->ce_mv stays the invalid sentinel. */
    uint16_t ce_mv = 0u;
    if (o2p_mcu_adc_read_ce_mv(&ce_mv)) {
        s->ce_mv = ce_mv;
    }
#endif
}

#if O2P_DEBUG_ENABLE
static uint32_t g_afe_override_s;
#endif

static void phase_afe(o2p_snapshot_t *s)
{
    uint16_t back = 0u;
    o2p_lmp_status_t lst = o2p_lmp91000_verify(&back);
    s->lmp_readback = back;
#if O2P_DEBUG_ENABLE
    if (g_uptime_s < g_afe_override_s) {
        g_cyc.faults |= O2P_F_AFE_CONFIG_MISMATCH;
        return;
    }
#endif
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
        /* One-word glitch rejection (2026-09-10 audit F7). The TMP117
         * transaction has no CRC, and the 17:53 event - tip stepping
         * 79.3 -> 63.3 C in one 1 Hz cycle at 100 % duty, no reset,
         * self-recovery - fits a single corrupted word and nothing else:
         * this thermal mass cannot move 16 K in a second, and every
         * firmware drive-cut path publishes duty 0. A step that large
         * against the last ACCEPTED value is discarded for this cycle:
         * not an I2C failure (that would be a lie about the bus) and not
         * a temperature (that would command 100 % duty against a phantom
         * error) - the tip simply publishes invalid and the loop sees
         * NO_TIP, which is the safe reaction. After ten consecutive
         * rejections the new value is taken as the baseline: a sensor
         * that has genuinely moved, or is broken and stuck, must not be
         * locked out of the loop forever. */
        static int16_t s_prev_tip_c100;
        static bool s_have_tip;
        static uint8_t s_tip_glitch_cycles;
        const bool glitch =
            s_have_tip &&
            (t > s_prev_tip_c100 + 200 || t < s_prev_tip_c100 - 200);
        if (glitch && s_tip_glitch_cycles < 10u) {
            s_tip_glitch_cycles++;
        } else {
            s_prev_tip_c100 = t;
            s_have_tip = true;
            s_tip_glitch_cycles = 0u;
            s->t_tip = t;
            g_cyc.t_tip = t;
            g_cyc.tip_ok = true;
        }
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

    /* External TMP117 on ext I2C (expansion connector / flying leads).
     * If not present, probe periodically (every 10 cycles). */
    if (!o2p_tmp117_ext_present()) {
        static uint8_t s_ext_probe_div;
        if (++s_ext_probe_div >= 10u) {
            s_ext_probe_div = 0u;
            (void)o2p_tmp117_ext_init();
        }
    }
    /* Conversion freshness for the dew-margin law, the tip's rule applied to
     * the ext part (Codex review of 4fe6b36, finding 1). BEFORE the TEMP read,
     * which clears Data_Ready. Only the heater's bridge consumes it: T_EXT
     * still publishes every good read. */
    static uint8_t s_ext_notready_cycles = O2P_TIP_STALE_CYCLES;
    bool ext_ready = false;
    if (o2p_tmp117_ext_present() &&
        o2p_tmp117_ext_data_ready(&ext_ready) == O2P_TMP_OK && ext_ready) {
        s_ext_notready_cycles = 0u;
    } else if (s_ext_notready_cycles < 0xFFu) {
        s_ext_notready_cycles++;
    }
    g_cyc.ext_fresh = (s_ext_notready_cycles < O2P_TIP_STALE_CYCLES);

    int16_t text = 0;
    if (o2p_tmp117_ext_read_c100(&text) == O2P_TMP_OK) {
        /* Single-word glitch rejection for external sensor on flying leads. */
        static int16_t s_prev_ext_c100;
        static bool s_have_ext;
        static uint8_t s_ext_glitch_cycles;
        const bool glitch = s_have_ext &&
            (text > s_prev_ext_c100 + 300 || text < s_prev_ext_c100 - 300);
        if (glitch && s_ext_glitch_cycles < 5u) {
            s_ext_glitch_cycles++;
        } else {
            s_prev_ext_c100 = text;
            s_have_ext = true;
            s_ext_glitch_cycles = 0u;
            g_cyc.t_ext = text;
            g_cyc.ext_ok = true;
        }
    }

    /* The SHT45's on-chip heater pulse deliberately warms the element. The
     * measurement it returns, and everything for some seconds afterwards, is
     * of a heated sensor - so the chamber channels stay INVALID until the
     * recovery window closes. Publishing a post-pulse reading would look
     * exactly like the pile drying out.
     *
     * The window was a conservative guess and it was WRONG: measured on the
     * bench 2026-09-07, recovery to 0.10 %RH takes 325 s, not 30 s. o2.h now
     * carries the constant, the measurement and the derivation of the cache
     * bound that has to cover it (SHT-DECREEP-MASK-IS-TOO-SHORT.md).
     *
     * NO FAULT IS RAISED HERE ANY MORE, and that is the point of this hunk.
     * The mask used to set I2C_FAIL_SHT, which made a maintenance action the
     * firmware itself ordered indistinguishable at the Modbus interface from
     * a failed humidity sensor - with I2C_ERRS sitting at 0 throughout, so the
     * counter and the fault bit disagreed and a consumer could not tell them
     * apart from that either. The fault word is not short of ways to say
     * "broken"; it had no way to say "not broken, come back shortly".
     *
     * What a consumer sees instead, and why it is sufficient:
     *
     *   masked   T_CHAMBER/RH_CHAMBER at their sentinels, no fault bit. The
     *            snapshot was reset to INVALID by cycle_begin() and this early
     *            return writes nothing, so the sentinels are published by
     *            omission, not by a substitution anyone has to trust.
     *   broken   the same sentinels WITH I2C_FAIL_SHT, raised below from the
     *            first measurement that actually fails.
     *
     * So the absence of the bit is the discriminator, which is the "distinct
     * status" SHT-DECREEP-MASK-IS-TOO-SHORT.md asked for - reached by removing
     * a false statement rather than by spending a register the diagnostic
     * block does not have (0x0010..0x002F are all assigned, regmap.h).
     *
     * The dry-basis oxygen channel does not go with it: o2p_gas_cache_apply()
     * bridges the gap from this sensor's own last real reading, bounded by
     * O2P_RH_MAX_AGE_S, which the static assertion in o2.h ties to this mask.
     *
     * THE HEATER RIDES THROUGH THE WINDOW BLIND, 2026-09-11 (Fab's order:
     * "nope, no stand-down. 50 is safe if MCU die is < 40 C") - corrected
     * from the earlier "stands down for the whole window", which described
     * the intent, not the firmware: the mask takes the RH AND the chamber
     * reading together (the same sensor), NO_RH lands the RH law on the
     * blind path (heater_ctl.c, law_wet_mask), and the ring drives
     * O2P_HEATER_BLIND_DUTY_X100 bounded by the ceiling and the
     * O2P_HEATER_BLIND_DIE_MAX_C100 gate - the die crossing 40 C IS the
     * stand-down, die-referenced instead of schedule-referenced. The window
     * lasts 350 s rather than 25 s - about 1.2 % of the time, on a
     * schedule, three times a day. Only the RH law: a persistent tip law
     * keeps regulating through it (its control sensor is the tip; NO_RH and
     * NO_CHAMBER are annotations to it, heater_ctl.c), its chamber
     * temperature from the same cache (see the dT clamp below), and
     * O2P_REG_HEATER_BLOCK names NO_RH/NO_CHAMBER on the bus, so it is
     * visible rather than silent. The pulse drives the measured
     * RH LOW, and a loop that regulated on it would read the chamber as drier
     * than it is and under-heat, which is the direction that condenses. */
    if (o2p_sht_masked(o2p_millis(), g_sht_pulse_ms)) {
        g_cyc.faults |= o2p_sht_phase_faults(true, g_sht_pulse_failed, false);
        return;
    }

    int16_t tc = 0;
    uint16_t rh = 0;
    bool measure_ok = (o2p_sht4x_measure(&tc, &rh) == O2P_SHT_OK);
    if (measure_ok) {
        s->t_chamber = tc;
        s->rh_chamber = rh;
        g_cyc.t_chamber = tc;
        g_cyc.rh = rh;
        g_cyc.chamber_ok = true;
        g_cyc.rh_ok = true;
    }
    /* Both outcomes go through the same gate, including the masked return
     * above - which adds nothing, and is written as a call rather than as no
     * call at all so that the host test exercises THIS site's rule and not a
     * second copy of it. */
    g_cyc.faults |= o2p_sht_phase_faults(false, g_sht_pulse_failed, measure_ok);

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

/* Millivolts at ADS1119 full scale for a conversion that ASKED for the external
 * reference: the measured VREF_TRIM normally, or the internal 2.048 V while the
 * debug override is in force (diag opcode 9, O2P_OP_ADS_INTERNAL_REF; latched
 * per cycle in cycle_begin(), so one average never mixes references). Fab
 * 2026-09-11: "let it use the internal ref for all channels now, for
 * debugging. the external ref is down". */
static bool ads_on_internal(void)
{
    /* Forced by hand, or fallen back to because the sense tap faulted. */
    return g_cyc.ads_internal || g_cyc.ads_fallback;
}

static uint32_t ads_ext_scale_mv(void)
{
    return ads_on_internal() ? O2P_ADS_INTERNAL_REF_MV : g_cyc.vref_mv;
}

/* P4. A stuck mux returns the PREVIOUS channel's sample, so two different
 * channels yielding bit-identical accumulator codes is a direct signature of
 * it. On 2026-09-12 AIN0 did exactly that and the only reason anyone noticed
 * was a coincidence - AFE_VOUT happened to equal VREF_MON/2, and the history
 * showed them tracking to within 4 mV from the failure onward while being
 * independent before it. Fourteen hours, caught by eye.
 *
 * Bit-identical is deliberately strict. Two channels CAN legitimately land on
 * the same code, so this is evidence and not a verdict: it sets a bit in
 * ADC_HEALTH and never suppresses a reading. A near-miss tolerance would fire
 * on real signals - WE_BUF and RE_BUF sit within a few mV of each other by
 * design whenever the cell is unbiased. */
static void note_channel_code(uint8_t mux, int32_t code)
{
    if (o2p_mux_stuck_signature(g_cyc.prev_valid, g_cyc.prev_mux,
                                g_cyc.prev_code, mux, code)) {
        g_cyc.mux_stuck = true;
    }
    g_cyc.prev_mux = mux;
    g_cyc.prev_code = code;
    g_cyc.prev_valid = true;
}

/* One ADS1119 conversion into g_acc. Returns true when the phase is done. */
static bool accumulate(uint8_t mux, uint8_t dr, bool ext_ref, unsigned n)
{
    int16_t code = 0;
    o2p_ads_status_t st = o2p_ads1119_convert(mux, dr,
                                              ext_ref && !ads_on_internal(),
                                              &code);
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
    if (g_sub >= n) {
        /* Compare per-phase AVERAGES, not raw samples: the phases use
         * different conversion counts, so the accumulator alone is not
         * comparable between them. The offset self-check is excluded -- it is
         * SUPPOSED to sit near zero every cycle and would false-positive
         * against any other channel that happened to. */
        if (mux != O2P_ADS_MUX_OFFSET) {
            note_channel_code(mux, g_acc / (int32_t)n);
        }
        return true;
    }
    return false;
}

static void finish_vref(o2p_snapshot_t *s)
{
    static bool s_vref_was_out;   /* true while VREF_MON sits outside the
                                   * trim band; cleared on re-entry, where
                                   * the settle window restarts (F6) */
    if ((g_cyc.faults & O2P_FAULTS_ADS_NO_CONVERSION) != 0u) {
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_VREF;
    int32_t half_uv = o2p_ads1119_code_to_uv(code, O2P_ADS_INTERNAL_REF_MV);
    /* PER-REVISION, from hw_caps, NOT from hw_contract: Rev A reads a 47k/47k
     * halved copy on ADS AIN1 and must double it, Rev B reads /VREF_TRIM
     * undivided on PA5 and must not. Deriving this from the live schematic
     * would have made deleting R34/R35 for Rev B silently halve the Rev A
     * bench board's reference reading. */
    int32_t measured = (half_uv / 1000) * (int32_t)O2P_HW_DIV_VREF_MON_DEN /
                       (int32_t)O2P_HW_DIV_VREF_MON_NUM;
    if (measured < 0) {
        measured = 0;
    }
    s->vref_mv = (uint16_t)measured;
    /* Outside the trim network's reachable band, the reference is not what
     * the -600 mV bias depends on, so the bias is not -600 mV either. */
    if (measured < (int32_t)O2P_HW_VREF_MIN_MV - 100 ||
        measured > (int32_t)O2P_HW_VREF_MAX_MV + 100) {
        g_cyc.faults |= O2P_F_ADC_RANGE;
        s_vref_was_out = true;
        /* P3. Until 2026-09-12 this branch suppressed every externally
         * referenced channel for as long as the tap was bad - VIN, VA, WE, RE
         * and oxygen all went to sentinel because ONE DIAGNOSTIC input leaked,
         * while VIN was perfectly measurable the whole time (proved on the
         * bench: diag opcode 9 returned 13138 mV immediately). A diagnostic
         * channel must not be able to disable the measurement channels.
         *
         * So: switch this cycle to the internal 2.048 V reference and keep
         * reporting, DEGRADED AND SAID SO. The oxygen channel loses its
         * ratiometry and its absolute scale now depends on the ADS's own
         * 2.048 V (+/-0.25 %, SBAS925 p.329) instead of cancelling - which is
         * worse, and still enormously better than no reading at all. Every
         * consumer can see it in ADC_HEALTH bit 1. */
        g_cyc.ads_fallback = true;
    } else {
        if (s_vref_was_out) {
            /* The reference is back inside the trim band after being
             * outside it. The commanded cell bias rode the whole excursion
             * (0.67 x VREF: a 2.5 V -> 0.3 V -> 2.5 V swing is at least as
             * violent as the VA_LOW interruptions phase_rails already
             * restarts settling for), so the window starts HERE, at
             * recovery - not wherever mid-fault the old deadline stood
             * (2026-09-10 audit F6; the 15:01 collapse and its 18:02
             * recovery were the case that proved the gap). */
            s_vref_was_out = false;
            restart_settling();
        }
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
/* The sample_seq the verdict was ESTABLISHED in, and the reason the verdict
 * alone is not enough.
 *
 * Review 2026-09-08 broke the claim at the calibration gate, which said an
 * "UNKNOWN - no reading yet, or a cycle in which the electrodes could not be
 * converted - refuses rather than assuming the best". Only the first half was
 * true. UNKNOWN is assigned inside finish_electrode()'s RE branch, AFTER four
 * early returns - no conversion, this phase clipped, a negative code, an
 * unmeasured reference - so a cycle that could not convert the electrodes left
 * the PREVIOUS cycle's verdict standing, with no bound on its age. A BIAS_GOOD
 * from a healthy cycle could therefore authorise a PERMANENT air calibration
 * an arbitrary number of failed cycles later, which is exactly the "stale
 * value wearing the units of a measurement" this file is written against.
 *
 * The verdict is legitimately one cycle old at the gate - finish_o2() runs two
 * phases BEFORE the electrodes - so age is the discriminator, not freshness.
 * Stamped only where a complete WE+RE pair produced it. */
static uint16_t s_bias_verdict_seq;

/* BIAS_GOOD, and no older than the one cycle the phase order costs.
 *
 * Unsigned 16-bit subtraction, so g_sample_seq wrapping is not a special case:
 * the difference is correct across the wrap and only the difference is used. */
static bool bias_verified_recently(void)
{
    if (s_bias_verdict != BIAS_GOOD) {
        return false;
    }
    return (uint16_t)(g_sample_seq - s_bias_verdict_seq) <= 1u;
}

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
    /* Under the internal-reference override (diag opcode 9) the scale is
     * 2048 mV, not VREF, so a collapsed reference no longer blanks these. */
    if (g_acc_clipped || (!ads_on_internal() && !g_cyc.vref_measured)) {
        return;
    }
    int32_t code = g_acc / (int32_t)O2P_N_CELL;
    if (code < 0) {
        return;
    }
    int32_t uv = o2p_ads1119_code_to_uv(code, ads_ext_scale_mv());
    int32_t mv = uv / 1000;
    if (mv < 0 || mv > 65534) {
        return;
    }
    if (working) {
#if O2P_HW_BIAS_ADC_REACHES_ELECTRODES
        s->we_buf_mv = (uint16_t)mv;
#elif O2P_HW_VA_MON_ON_ADS
        s->va_mv = o2p_scale_va_ads((uint16_t)mv);
        if (s->va_mv < O2P_VA_LOW_MV) {
            g_cyc.faults |= O2P_F_VA_LOW;
        }
#endif
    } else {
#if O2P_HW_BIAS_ADC_REACHES_ELECTRODES
        s->re_buf_mv = (uint16_t)mv;
#elif O2P_HW_VIN_MON_ON_ADS
        s->vin_mv = o2p_scale_vin_ads((uint16_t)mv,
                                      o2p_cfg_vin_div_x1000(&g_rm.cfg));
        if (s->vin_mv < O2P_VIN_LOW_MV) {
            g_cyc.faults |= O2P_F_VIN_LOW;
        }
#endif
        /* Both halves present, and neither is the invalid sentinel, or the
         * bias stays invalid. A difference computed from one real reading and
         * one 0xFFFF is a number, which is the problem. */
        s_bias_verdict = BIAS_UNKNOWN;
        if (s->we_buf_mv != O2P_U16_INVALID) {
            int32_t bias = (int32_t)s->we_buf_mv - mv;
            if (bias > 32767) { bias = 32767; }
            if (bias < -32767) { bias = -32767; }
            /* Only if those two channels reach the electrodes on THIS board.
             * They do not on the Rev A first article - hw_caps.h and the generated per-revision
             * header explain
             * what AIN2/AIN3 actually carry there, and why this is a build
             * flag rather than a comment. A difference of two rails
             * published in a register called CELL_BIAS_MV is precisely the
             * "number that looks like a measurement" this file keeps writing
             * postmortems about, so it stays the invalid sentinel and the
             * verdict stays BIAS_UNKNOWN.
             *
             * BIAS_UNKNOWN is not benign: bias_verified_recently() refuses it,
             * so calibration is still gated exactly as it was. What changes is
             * only that a board with no bias telemetry no longer reports a
             * bias FAULT it cannot possibly have evidence for. Measured
             * 2026-09-09: a healthy probe - loop in regulation, 99.9 uA in air
             * against DS-0637's 40-100 uA - withheld every oxygen reading on
             * this bit alone. */
            if (O2P_HW_BIAS_ADC_REACHES_ELECTRODES) {
                s->cell_bias_mv = (int16_t)bias;
            }

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
            if (g_cyc.vref_measured && O2P_HW_BIAS_ADC_REACHES_ELECTRODES) {
                int32_t want = o2p_lmp_commanded_bias_mv((int32_t)g_cyc.vref_mv);
                int32_t err = bias - want;
                if (err < 0) { err = -err; }
                if (err > O2P_CELL_BIAS_TOLERANCE_MV) {
                    g_cyc.faults |= O2P_F_AFE_CONFIG_MISMATCH;
                    s_bias_verdict = BIAS_BAD;
                } else {
                    s_bias_verdict = BIAS_GOOD;
                }
                /* Stamped HERE and nowhere else: this is the only point at
                 * which a complete WE+RE pair, against a measured reference,
                 * has actually produced a verdict. */
                s_bias_verdict_seq = g_sample_seq;
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
    /* Skipped under the internal-reference override (diag opcode 9): the
     * scale is then 2048 mV, and the LMP91000 temperature output is
     * ground-referred (SNAS506I 7.3.1.5), so nothing here depends on VREF. */
    if (!g_cyc.ads_internal && !g_cyc.vref_measured) {
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
    int32_t uv = o2p_ads1119_code_to_uv(code, ads_ext_scale_mv());
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
    /* A pinned converter is not a measurement. */
    if (g_acc_clipped) {
        g_cyc.faults |= O2P_F_ADC_RANGE;
    }
    int32_t code = g_acc / (int32_t)O2P_N_O2;
    int32_t uv = o2p_ads1119_code_to_uv(code, ads_ext_scale_mv());

    /* AFE_VOUT_MV IS THE UNCONDITIONAL CHANNEL, and deliberately so. It is
     * the converter's own output in millivolts, published whatever happened,
     * because a rail IS the diagnostic: 24 mV named the pin 10-11 bridge and
     * 2495 mV named the collapsed A1 on 2026-09-08. Its scale is nominal
     * rather than measured when VREF_MON reads its sentinel; that is a 0.3 %
     * question on a number being read for its order of magnitude. */
    s->afe_vout_mv = (uv < 0) ? 0u : (uint16_t)(uv / 1000);

    /* Under opcode 9 the volts above are absolute (internal reference), so the
     * current takes them as they are and only the internal zero uses VREF -
     * no longer ratiometric; O2_RAW below still requires a measured VREF. */
    int32_t cell_na = g_cyc.ads_internal
        ? o2p_cell_na_from_uv(uv, g_cyc.vref_mv)
        : o2p_cell_na_from_code(code, g_cyc.vref_mv);

    /* O2_RAW, ON THE OTHER HAND, IS A CURRENT, and a current derived from a
     * rail is a fabrication - 2026-09-09, from the Codex review of the
     * always-publish change.
     *
     * Fab's instruction on 2026-09-08 was "raw is raw and it's ok if it's not
     * ok", and it stands: the FAULT WORD no longer withholds this value.
     * Nothing in O2P_FAULTS_INVALIDATE_O2 blanks it, so a dead I2C bus, a
     * mismatched AFE config or a low VA all still publish their microamps and
     * let the consumer judge. What is refused here is narrower and is not a
     * judgement about trust: these two conditions mean the arithmetic below
     * has no input. A saturated converter has lost the code, so 32767 is
     * where the ADC stopped counting and not where the cell was; an unmeasured
     * VREF means the volts-per-count came from the trim TARGET, and this
     * channel then divides an assumed reference by a bias derived from the
     * same assumption. Measured 2026-09-08 with a railed AFE: VOUT 2495
     * against VREF 2496 encodes as -117.5 uA, which is inside the SGX cell's
     * 70-130 uA air band with a sign flip - the one shape a reader cannot
     * dismiss at a glance.
     *
     * This is the same guard finish_we_re() and finish_t_afe() already apply,
     * for the same reason, and it tests g_acc_clipped and vref_measured
     * DIRECTLY rather than reading the cumulative fault word - see the long
     * note in finish_we_re(). The bench loses nothing: AFE_VOUT_MV (0x0013)
     * above carries the rail, and ADC_RANGE in the fault word says why. */
    if (!g_acc_clipped && g_cyc.vref_measured) {
        /* uA * 100, i.e. 10 nA per count. */
        s->o2_raw = o2p_encode_raw_ua_x100(cell_na);
    }

    /* The CELL temperature (FW 0x001E): the cell-side T_EXT, bridged across
     * its glitch filter, else chamber-else-tip. See o2p_cell_temperature(). */
    static o2p_cell_bridge_t s_o2_cell;
    o2p_cell_bridge_note(&s_o2_cell, g_cyc.ext_ok, g_cyc.ext_fresh,
                         g_cyc.t_ext, g_uptime_s);
    int16_t t_ext_bridged = O2P_I16_INVALID;
    const bool ext_live = o2p_cell_bridge_get(&s_o2_cell, g_uptime_s,
                                              O2P_O2_CELL_MAX_AGE_S,
                                              &t_ext_bridged);
    const int16_t t_cell = o2p_cell_temperature(ext_live, t_ext_bridged,
                                                g_cyc.chamber_ok, g_cyc.t_chamber,
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

    /* No temperature is not a compensated reading. Since FW 0x001E the cell
     * law always applies, so this no longer depends on TEMPCO_PPM_K being
     * non-zero: rather than converting at the calibration temperature and
     * presenting the result as compensated, refuse it. */
    if (t_cell == O2P_I16_INVALID) {
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
            &cal, cell_na, t_cell, &gas, &c);
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
        /* And the cell has to have BEEN AT ITS COMMANDED BIAS *RECENTLY*. See
         * s_bias_verdict_seq: an air point is permanent, the bias check does
         * not run until two phases after this decision, so the verdict is
         * always one cycle old here - but only one. A cycle in which the
         * electrodes could not be converted leaves no verdict at all, and
         * bias_verified_recently() refuses that rather than reading the last
         * healthy cycle's answer, however long ago it was. */
        /* THE BIAS PRECONDITION, AND WHAT REPLACES IT ON A BOARD THAT CANNOT
         * MEASURE ONE. Added 2026-09-09.
         *
         * bias_verified_recently() is the right gate when the electrodes are
         * actually converted. On the fabricated Rev A article they are not -
         * AIN2/AIN3 are the VA and VIN rail monitors (hw_caps_rev_a.h) - so
         * O2P_HW_BIAS_ADC_REACHES_ELECTRODES is 0, the verdict stays
         * BIAS_UNKNOWN forever, and this gate can NEVER be satisfied.
         *
         * Measured 2026-09-09 on a fully healthy probe: cell 99.2 uA in room
         * air, reference 2496 mV, settle expired, register image 0x0CCD, every
         * other precondition passing - CAL_RESULT came back FAILED. No air
         * point, so CAL_DEFAULT stays set, so O2_COMP stays invalid, so the
         * probe can never publish oxygen. A safety gate that cannot be
         * satisfied is not conservative, it is a deadlock.
         *
         * What replaces it is NOT a bypass, and it is deliberately not a
         * tighter current window either. An unbiased cell does not read zero -
         * DS-0637 Note 1 says it saturates with oxygen - so current magnitude
         * is not evidence of bias, and a band tight enough to look like proof
         * would also refuse a legitimately aged cell. The evidence that
         * actually exists is the AFE's own register image: phase_afe() calls
         * o2p_lmp91000_verify() every cycle and raises AFE_CONFIG_MISMATCH on
         * any disagreement, and that bit is in O2P_FAULTS_INVALIDATE_O2 - so
         * o2p_o2_valid() below ALREADY requires that the AFE reports the
         * commanded bias configuration. Together with `settled` and
         * o2p_calibrate_air()'s own plausibility window, that is the whole of
         * what this board can honestly assert.
         *
         * It is weaker than a measured bias, and that is precisely why the
         * result is recorded: cal_bias_verified is stored WITH the point and
         * published as CAL_STATE_BIAS_UNVERIFIED, so a %vol derived from it
         * carries its own provenance instead of looking like a verified one. */
        const bool bias_measurable = (O2P_HW_BIAS_ADC_REACHES_ELECTRODES != 0);
        const bool bias_measured = bias_verified_recently();

        /* CORRECTION, 2026-09-09, from review of the commit that introduced
         * this gate. That commit refused to bound the current, arguing from
         * DS-0637 Note 1 that an unbiased cell saturates with oxygen and so
         * current magnitude proves nothing about bias. THAT MISREAD THE NOTE:
         * it describes the settling transient AFTER bias is reapplied - the
         * stored oxygen "is consumed when the bias is reapplied" - and says
         * nothing about what an unbiased cell outputs. The note does not
         * license discarding the check, and discarding it left a real hole:
         * a partially faulty electrode path reading 60 uA in air passes
         * o2p_calibrate_air()'s 20-200 uA window, is stored permanently, and
         * decodes a later true 10 %vol as roughly 16 %.
         *
         * So when the bias cannot be measured, the stored point must at least
         * lie inside the cell's own datasheet population. This does NOT
         * establish the bias - nothing on this board can - it bounds the
         * damage of accepting a point without one. */
        const bool air_current_plausible_unverified =
            (cell_na >= O2P_AIR_CAL_UNVERIFIED_MIN_NA &&
             cell_na <= O2P_AIR_CAL_UNVERIFIED_MAX_NA);
        const bool bias_evidence =
            bias_measurable ? bias_measured : air_current_plausible_unverified;

        /* THE REFERENCE MUST BE THE SENSOR THE CONVERSION USES (FW 0x001E).
         * cal_temp_c100 is what every later (T/T_cal)^0.75 is taken against.
         * On a probe with a T_EXT sensor the conversion runs on T_EXT, so an
         * air point stored on the chamber fallback would carry the chamber's
         * offset from the cell into every reading for life - ~0.7 K at the
         * 2026-09-12 air point, 0.18 % of K. Refused rather than stored; a
         * probe with no T_EXT fitted calibrates on the fallback it converts
         * on, which is consistent. */
        const bool cal_temp_ok = (t_cell != O2P_I16_INVALID) &&
                                 (!o2p_tmp117_ext_present() || ext_live);

        if (settled && cal_temp_ok &&
            bias_evidence &&
            o2p_o2_valid(g_cyc.faults) &&
            o2p_calibrate_air(&g_cal, cell_na, t_cell, &fresh)) {
            g_rm.cfg.cal_air_na = g_cal.cal_air_na;
            g_rm.cfg.cal_temp_c100 = g_cal.cal_temp_c100;
            /* Stored WITH the point, like every other term it depends on: a
             * constant that cannot say how it was obtained is the failure this
             * file keeps writing postmortems about. */
            g_rm.cfg.cal_bias_verified = bias_measured ? 1u : 0u;
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
    /* P3/P4: say which degraded mode is in force. Built every cycle, so a
     * fallback that clears is visible as one that cleared. */
    {
        uint16_t h = 0u;
        if ((g_cyc.faults & O2P_F_ADC_RANGE) != 0u && !g_cyc.vref_measured) {
            h |= O2P_ADCH_VREF_OUT_OF_BAND;
        }
        if (g_cyc.ads_fallback) { h |= O2P_ADCH_REF_FALLBACK; }
        if (g_cyc.ads_internal) { h |= O2P_ADCH_REF_FORCED; }
        if (g_cyc.mux_stuck)    { h |= O2P_ADCH_MUX_STUCK; }
        if (g_cyc.offset_bad)   { h |= O2P_ADCH_OFFSET_BAD; }
        int32_t mag = g_cyc.offset_code < 0 ? -g_cyc.offset_code : g_cyc.offset_code;
        if (mag > 255) { mag = 255; }
        h |= (uint16_t)((uint32_t)mag << 8);
        s->adc_health = h;
    }
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
    /* O2_RAW IS NO LONGER BLANKED BY THE FAULT WORD - 2026-09-08.
     *
     * Fab, 2026-09-08: "raw is raw and it's ok if it's not ok."
     *
     * The FAULTS word is register 6 of this same primary block, so it is in
     * every frame that carries the number, and the ChirpStack decoder names
     * every set bit in its warnings. Anyone deciding whether to trust the
     * current reads that. There is deliberately no second validity flag: the
     * decoder's raw_ok was removed with this change, because a flag derived
     * from a duplicated copy of the mask above is a thing that can drift away
     * from the firmware, and the fault word cannot.
     *
     * What blanking cost is debugging. O2_COMP is already withheld on all of
     * these faults, so the untrustworthy %vol never reaches anyone; blanking
     * the raw current on top of that removed the only remaining evidence of
     * what the cell was doing, at exactly the moments a human was trying to
     * find out. Measured twice on 2026-09-08: SETTLING deleted the 900 s
     * recovery transient after every reset (fixed then, same argument), and
     * that evening a saturated AFE with a cell fitted left the question "is
     * this cell drawing current, and how much" with no channel to answer on
     * for the whole investigation.
     *
     * There is no sentinel-collision risk and no invented number here. The
     * snapshot is rebuilt from O2P_I16_INVALID at the start of every cycle by
     * o2p_snapshot_reset(), and finish_o2() writes o2_raw only from a
     * conversion that actually completed. So a cycle that produced no
     * conversion still publishes the sentinel - it is simply never
     * overwritten - while a cycle that DID convert, with a converter that did
     * not saturate and a reference that was really read, publishes what it
     * converted no matter which fault bits are set alongside it. Those last
     * two conditions were added on 2026-09-09; finish_o2() has the argument,
     * and AFE_VOUT_MV is what carries the bench diagnostic when they fail.
     *
     * O2_COMP keeps its sentinel. It is a quotient by a calibration constant
     * that may not exist, so there is no underlying measurement to preserve. */
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
            /* Persistent tip loop, registers 0x0049 and 0x004A. Read from the
             * CONFIG this time, not the volatile map: surviving a reset is the
             * entire point of the mode. */
            .tip_consent     = (g_rm.cfg.heater_tip_consent ==
                                O2P_HEATER_TIP_CONSENT_MAGIC),
            .tip_sp_valid    = (g_rm.cfg.tip_setpoint_c100 != O2P_I16_INVALID),
            .tip_sp_c100     = g_rm.cfg.tip_setpoint_c100,
        };
        /* CHAMBER TEMPERATURE FOR THE dT CLAMP, bridged across the scheduled
         * SHT45 de-creep mask.
         *
         * cycle_begin() invalidates chamber AND humidity, and phase_sht()
         * restores neither for O2P_SHT_RECOVERY_MS after a pulse. The
         * persistent tip loop suppresses NO_RH but deliberately keeps
         * NO_CHAMBER live, so without this it stops for the whole mask on a
         * schedule - a loop that refuses intermittently for a reason nobody
         * can see from outside, which is worse than one that refuses
         * consistently. Found by review 2026-09-08.
         *
         * Uses the SAME cache and the SAME bound as the oxygen path
         * (O2P_RH_MAX_AGE_S = 45 s, derived in o2.h against a 32.1 s worst
         * case), so the age policy stays in one place rather than acquiring a
         * second copy that can drift. Past the bound the gas stays invalid and
         * NO_CHAMBER fires again: a genuinely dead SHT45 still blocks the
         * heater, which is the property that had to survive.
         *
         * ONLY THE TEMPERATURE IS BRIDGED, not the humidity. Chamber
         * temperature moves on minutes and is an INPUT to a clamp; relative
         * humidity is the RH loop's CONTROLLED QUANTITY and is the very thing
         * the pulse perturbs. Substituting a cached value for a clamp's
         * reference is not the same act as substituting one for the quantity
         * you are regulating, and the RH loop keeps refusing as before. */
        bool    heater_chamber_ok = g_cyc.chamber_ok;
        int16_t heater_t_chamber  = g_cyc.t_chamber;
        if (!heater_chamber_ok) {
            o2p_gas_t bridged;
            bridged.rh_pct = 0.0f;
            bridged.t_c    = 0.0f;
            bridged.p_hpa  = 0.0f;
            bridged.valid  = false;
            if (o2p_gas_cache_apply_bounded(&g_gas_cache, &bridged,
                                            g_uptime_s,
                                            O2P_HEATER_CHAMBER_MAX_AGE_S)) {
                const float c100 = bridged.t_c * 100.0f;
                heater_t_chamber =
                    (int16_t)(c100 + (c100 >= 0.0f ? 0.5f : -0.5f));
                heater_chamber_ok = true;
            }
        }

        /* CELL-SIDE TEMPERATURE FOR THE DEW-MARGIN LAW (FW 0x0013), bridged
         * for O2P_HEATER_CELL_MAX_AGE_S across the ext glitch filter's
         * withheld readings - see that constant. The age runs from the last
         * reading that was both accepted AND fresh (ext Data_Ready, see
         * phase_temps): a frozen conversion engine still answers I2C, and
         * refreshing on every read held a constant margin forever - a warm
         * frozen cell reading would have kept a drowning cell cold (Codex
         * review of 4fe6b36, finding 1; the tip ceiling only bounds the
         * opposite failure). The rule lives in o2p_cell_bridge_*()
         * (sampler_logic.h), shared with the oxygen path since FW 0x001E;
         * this instance keeps its own age bound and, as before, its last
         * value when the bridge has lapsed. */
        static o2p_cell_bridge_t s_heater_cell;
        static int16_t s_heater_cell_c100;
        o2p_cell_bridge_note(&s_heater_cell, g_cyc.ext_ok, g_cyc.ext_fresh,
                             g_cyc.t_ext, g_uptime_s);
        const bool heater_cell_ok = o2p_cell_bridge_get(
            &s_heater_cell, g_uptime_s, O2P_HEATER_CELL_MAX_AGE_S,
            &s_heater_cell_c100);

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
            .chamber_valid    = heater_chamber_ok,
            .t_chamber_c100   = heater_t_chamber,
            /* Measured THIS cycle, as opposed to bridged above. The runaway
             * release will not exonerate a FET on a cached chamber reading;
             * see chamber_fresh in heater_ctl.h. */
            .chamber_fresh    = g_cyc.chamber_ok,
            /* The die is a diagnostic channel everywhere else; here it is the
             * only reference that can witness a stuck-on FET. */
            .die_valid        = (s->t_die != O2P_I16_INVALID),
            .t_die_c100       = s->t_die,
            /* REMOVED as a veto 2026-09-11 (Fab's order): "heating adds
             * ~86 mA, a rail out of tolerance is not the place for more
             * load" - overruled. The heater is <1 W and cannot start a
             * fire, and blind mode already heated through the same fault;
             * heat is also what a wet board needs. supply_ok now only
             * annotates HEATER_BLOCK (O2P_HB_SUPPLY), it no longer gates
             * duty. See heater_ctl.c interlocks(). */
            .supply_ok        = (g_cyc.faults &
                                 (O2P_F_VA_LOW | O2P_F_VIN_LOW)) == 0u,
            /* The dew-margin law's reference surface; bridged above. */
            .cell_valid       = heater_cell_ok,
            .t_cell_c100      = s_heater_cell_c100,
        };
        /* law defaults to REFUSED, not 0: zero is O2P_HEATER_LAW_RH, and a
         * step that returned without writing it must not publish a law. */
        o2p_heater_out_t hout = {0u, 0u, O2P_HEATER_LAW_REFUSED};
        o2p_heater_ctl_step(&g_heat, &hcfg, &hin, g_uptime_s, &hout);
        o2p_heater_apply(hout.duty_x100, g_rm.cfg.heater_pwm_hz);
        g_cyc.heater_block = hout.block;   /* kept for the fault word below */
        g_cyc.heater_law = hout.law;
        if (g_heat.runaway_latched) {
            g_cyc.faults |= O2P_F_HEATER_RUNAWAY;
        }
        /* HEATER_DISABLED now means "not driving this cycle", whatever the
         * reason. In v0 it was a constant; the reason bits are in
         * HEATER_BLOCK. The blind fallback drives WITH reason bits set
         * (O2P_HB_BLIND), so a blocked mask is not driving only at zero duty. */
        if (hout.block != 0u && hout.duty_x100 == 0u &&
            (hout.block & (O2P_HB_IDLE | O2P_HB_TIP_DISARMED)) == 0u) {
            /* The annotation bits (0x0010) are answers, not faults: an
             * idle RH loop on a cold, dry probe must not count as
             * HEATER_DISABLED. */
            g_cyc.faults |= O2P_F_HEATER_DISABLED;
        }
    }
    s->heater_duty = o2p_heater_duty_x100();
    s->heater_block = g_cyc.heater_block;
    s->heater_law = g_cyc.heater_law;
    /* The staleness cut runs on the heater's own tick, not the sampler's,
     * and it drives the gate low WITHOUT passing through heater_ctl - so
     * fold its latch in here. Until 0x0010 the bit existed in the contract
     * and in the host decoders and nothing could raise it (audit F3). */
    if (o2p_heater_stale_cut()) {
        s->heater_block |= O2P_HB_STALE;
    }
    s->sampler_timing_ms = (uint16_t)(o2p_millis() - s_cycle_start_ms);
    s->pressure_hpa = 0u;             /* BMP390 is DNP on Rev A */
    if (g_cyc.ext_ok) {
        s->exp_data = (g_cyc.t_ext == (int16_t)O2P_U16_INVALID)
            ? (uint16_t)0
            : (uint16_t)g_cyc.t_ext;
    } else {
        s->exp_data = O2P_U16_INVALID;    /* no external sensor present */
    }
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
                g_phase = PH_OFFSET; g_sub = 0; g_acc = 0; g_acc_clipped = false;
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
            g_phase = PH_OFFSET; g_sub = 0; g_acc = 0; g_acc_clipped = false;
        }
        break;

    /* P4, and LAST: the converter's own offset, with its inputs shorted to
     * AVDD/2 by MUX=111 (SBAS925A Table 10). It must read near zero. Anything
     * else is the converter itself, not the board, and it is measured here
     * rather than assumed - the 2026-09-12 failure was diagnosed for five
     * hours partly because nothing on the probe could say whether the ADS was
     * healthy. One conversion per cycle, after every measurement is closed, so
     * it cannot perturb one. */
    case PH_OFFSET:
        if (accumulate(O2P_ADS_MUX_OFFSET, O2P_ADS_DR_90SPS, false, 1u)) {
            g_cyc.offset_code = g_acc;
            if (o2p_adc_offset_out_of_band(g_acc, O2P_ADC_OFFSET_MAX_LSB)) {
                g_cyc.offset_bad = true;
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

#if O2P_DEBUG_ENABLE
static void execute_diag_command(o2p_regmap_t *rm)
{
    uint8_t op = (uint8_t)(rm->diag_cmd & 0xFFu);
    uint16_t p = rm->diag_param;
    rm->diag_rdata0 = 0u;
    rm->diag_rdata1 = 0u;
    rm->diag_rdata2 = 0u;
    rm->diag_crc_status = 0u;

    switch (op) {
    case O2P_OP_READ_LMP_REG: {
        if (p > 0xFFu) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return;
        }
        uint8_t reg = (uint8_t)p;
        if (reg != 0x00 && reg != 0x01 && reg != 0x10 && reg != 0x11 && reg != 0x12) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return;
        }
        uint8_t val = 0;
        o2p_i2c_status_t st = o2p_i2c1_write_read(O2P_HW_I2C_ADDR_LMP91000, &reg, 1u, &val, 1u);
        if (st == O2P_I2C_OK) {
            rm->diag_rdata0 = (uint16_t)val;
            rm->diag_status = O2P_DMBOX_STATUS_OK;
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    case O2P_OP_TRIM_LMP_TIACN: {
        if (p > 0xFFu || (p & 0xE0u) != 0u) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return;
        }
        uint8_t val = (uint8_t)p;
        uint8_t payload[2] = { 0x10u, val };
        o2p_i2c_status_t st = o2p_i2c1_write(O2P_HW_I2C_ADDR_LMP91000, payload, 2u);
        if (st == O2P_I2C_OK) {
            g_afe_override_s = g_uptime_s + 60u;
            rm->diag_status = O2P_DMBOX_STATUS_OK;
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    case O2P_OP_READ_ADS_STATUS: {
        uint8_t cmd = 0x24u;
        uint8_t val = 0;
        o2p_i2c_status_t st = o2p_i2c1_write_read(O2P_HW_I2C_ADDR_ADS1119, &cmd, 1u, &val, 1u);
        if (st == O2P_I2C_OK) {
            rm->diag_rdata0 = (uint16_t)val;
            rm->diag_status = O2P_DMBOX_STATUS_OK;
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    case O2P_OP_READ_ADS_CONFIG: {
        uint8_t cmd = 0x20u;
        uint8_t val = 0;
        o2p_i2c_status_t st = o2p_i2c1_write_read(O2P_HW_I2C_ADDR_ADS1119, &cmd, 1u, &val, 1u);
        if (st == O2P_I2C_OK) {
            rm->diag_rdata0 = (uint16_t)val;
            rm->diag_status = O2P_DMBOX_STATUS_OK;
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    case O2P_OP_READ_TMP_REG: {
        uint8_t dev = (uint8_t)(p >> 8);
        uint8_t reg = (uint8_t)(p & 0xFFu);
        if (dev > 1u) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return;
        }
        if (reg > 0x08u && reg != 0x0Fu) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
            return;
        }
        /* RESTRICTION (Codex review of b3f7711, finding 3): a read of the
         * ext part's CONFIG or TEMP register here clears its Data_Ready
         * without phase_temps seeing it. Repeated diagnostic reads between
         * a conversion and the sampling phase can make a healthy part look
         * stale, expire the heater's cell bridge and hand the dew-margin law
         * to the RH law. Harmless for the occasional bench peek; do not
         * poll the ext part through this mailbox while the dew law matters. */
        uint8_t ext_addr = o2p_tmp117_ext_address();
        uint8_t addr = (dev == 1u)
            ? (ext_addr != 0u ? ext_addr : O2P_HW_I2C_ADDR_TMP117_EXT)
            : O2P_HW_I2C_ADDR_TMP117;
        uint8_t buf[2] = {0};
        o2p_i2c_status_t st = o2p_i2c1_write_read(addr, &reg, 1u, buf, 2u);
        if (st == O2P_I2C_OK) {
            rm->diag_rdata0 = ((uint16_t)buf[0] << 8) | buf[1];
            rm->diag_status = O2P_DMBOX_STATUS_OK;
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    case O2P_OP_READ_SHT_SERIAL: {
        uint8_t cmd = 0x89u;
        uint8_t buf[6] = {0};
        o2p_i2c_status_t st = o2p_i2c1_write_read(O2P_HW_I2C_ADDR_SHT45, &cmd, 1u, buf, 6u);
        if (st == O2P_I2C_OK) {
            bool crc0_ok = (o2p_sht4x_crc8(&buf[0], 2u) == buf[2]);
            bool crc1_ok = (o2p_sht4x_crc8(&buf[3], 2u) == buf[5]);
            rm->diag_crc_status = (crc0_ok ? 1u : 0u) | (crc1_ok ? 2u : 0u);
            if (crc0_ok && crc1_ok) {
                rm->diag_rdata0 = ((uint16_t)buf[0] << 8) | buf[1];
                rm->diag_rdata1 = ((uint16_t)buf[3] << 8) | buf[4];
                rm->diag_status = O2P_DMBOX_STATUS_OK;
            } else {
                rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
            }
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    case O2P_OP_READ_SHT_SAMPLE: {
        uint8_t cmd = 0xFDu;
        o2p_i2c_status_t st = o2p_i2c1_write(O2P_HW_I2C_ADDR_SHT45, &cmd, 1u);
        if (st != O2P_I2C_OK) {
            rm->diag_status = (st == O2P_I2C_TIMEOUT) ? O2P_DMBOX_STATUS_ERR_TIMEOUT : O2P_DMBOX_STATUS_ERR_NACK;
            return;
        }
        o2p_delay_ms(10u);
        uint8_t buf[6] = {0};
        st = o2p_i2c1_read(O2P_HW_I2C_ADDR_SHT45, buf, 6u);
        if (st == O2P_I2C_OK) {
            bool crc0_ok = (o2p_sht4x_crc8(&buf[0], 2u) == buf[2]);
            bool crc1_ok = (o2p_sht4x_crc8(&buf[3], 2u) == buf[5]);
            rm->diag_crc_status = (crc0_ok ? 1u : 0u) | (crc1_ok ? 2u : 0u);
            if (crc0_ok && crc1_ok) {
                rm->diag_rdata0 = ((uint16_t)buf[0] << 8) | buf[1];
                rm->diag_rdata1 = ((uint16_t)buf[3] << 8) | buf[4];
                rm->diag_status = O2P_DMBOX_STATUS_OK;
            } else {
                rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
            }
        } else if (st == O2P_I2C_TIMEOUT) {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_TIMEOUT;
        } else {
            rm->diag_status = O2P_DMBOX_STATUS_ERR_NACK;
        }
        break;
    }
    default:
        rm->diag_status = O2P_DMBOX_STATUS_ERR_OPCODE;
        break;
    }
}

#include <setjmp.h>

static jmp_buf s_exec_jmp;
static uint32_t s_exec_code_aligned[O2P_REG_EXEC_CODE_COUNT / 2u];

void o2p_exec_timeout_trampoline(void)
{
    longjmp(s_exec_jmp, (int)O2P_EXEC_STATUS_TIMEOUT);
}

void o2p_exec_fault_trampoline(void)
{
    longjmp(s_exec_jmp, (int)O2P_EXEC_STATUS_FAULT);
}

static void execute_arbitrary_code(o2p_regmap_t *rm)
{
    /* Force heater off before executing arbitrary code (H4) */
    o2p_heater_force_off();

    /* Copy only the declared bytes (LEN) into the 4-byte aligned buffer,
     * and fill the remainder with BKPT 0 (0xBE00) trap instructions (M4) */
    uint16_t code_words = (uint16_t)(rm->exec_len / 2u);
    if (code_words > O2P_REG_EXEC_CODE_COUNT) {
        code_words = O2P_REG_EXEC_CODE_COUNT;
    }
    for (size_t i = 0; i < code_words; i++) {
        ((uint16_t *)s_exec_code_aligned)[i] = rm->exec_code[i];
    }
    for (size_t i = code_words; i < O2P_REG_EXEC_CODE_COUNT; i++) {
        ((uint16_t *)s_exec_code_aligned)[i] = 0xBE00u; /* BKPT 0 trap */
    }

    __DSB();
    __ISB();

    uint32_t timeout = rm->exec_timeout_ms ? rm->exec_timeout_ms : 50u;
    if (timeout > 1000u) timeout = 1000u;

    g_exec_timeout_ms = timeout;
    g_exec_start_ms = o2p_millis();

    typedef uint32_t (*thumb_fn_t)(uint32_t arg);
    thumb_fn_t fn = (thumb_fn_t)((uintptr_t)s_exec_code_aligned | 1u);
    uint32_t arg = ((uint32_t)rm->exec_param_hi << 16) | rm->exec_param_lo;

    /* Ensure RS-485 transceiver DE is low (receiver mode) before calling code */
    o2p_modbus_de_release();

    /* Ensure interrupts are active before entering setjmp (H2) */
    __enable_irq();

    switch (setjmp(s_exec_jmp)) {
    case 0: {
        g_exec_active = true;
        uint32_t res = fn(arg);
        g_exec_active = false;
        rm->exec_result_hi = (uint16_t)(res >> 16);
        rm->exec_result_lo = (uint16_t)(res & 0xFFFFu);
        rm->exec_status = O2P_EXEC_STATUS_OK;
        break;
    }
    case (int)O2P_EXEC_STATUS_TIMEOUT:
        g_exec_active = false;
        rm->exec_status = O2P_EXEC_STATUS_TIMEOUT;
        rm->exec_result_hi = 0u;
        rm->exec_result_lo = 0u;
        break;
    default:
        g_exec_active = false;
        rm->exec_status = O2P_EXEC_STATUS_FAULT;
        rm->exec_result_hi = 0u;
        rm->exec_result_lo = 0u;
        break;
    }

    /* Restore interrupt state: re-enable if user code ran cpsid i (H2) */
    __enable_irq();

    /* Force heater off again in case user code energized it (Finding 5) */
    o2p_heater_force_off();

    /* Force RS-485 transceiver DE low again so bus is never left driven */
    o2p_modbus_de_release();
}
#endif

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
    (void)o2p_tmp117_ext_init();
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
    o2p_regmap_load_crash_context(&g_rm);

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
                /* Armed BEFORE the switch, and the nonce published before
                 * it too: from the switch on, the only way to read it is at
                 * the new settings, which is what makes the ACK two-way
                 * proof (serial_probation.h). An ACK from a previous
                 * probation is cleared here as well as by the write that
                 * asked for this change. */
                const uint16_t nonce = o2p_sp_make_nonce(o2p_millis(),
                                                         o2p_modbus_frames_ok());
                g_rm.probation_acked = false;
                o2p_sp_arm(&g_serial_probation, o2p_millis(), nonce,
                           g_stored_addr, g_stored_baud, g_stored_parity);
                g_rm.probation_nonce = g_serial_probation.nonce;
                o2p_modbus_reconfigure(&g_rm.cfg);
            }
            /* Before the commit, so a confirmation reached on this pass can
             * release a commit that was waiting for it without costing
             * another lap. */
            serial_probation_service();
#if O2P_DEBUG_ENABLE
            o2p_crash_set_breadcrumb(((uint32_t)g_phase & 0xFFu) | ((uint32_t)g_sample_seq << 8));
            if (g_phase == PH_IDLE && g_rm.diag_pending) {
                g_rm.diag_pending = false;
                execute_diag_command(&g_rm);
            }
            if (g_phase == PH_IDLE && g_rm.exec_pending) {
                g_rm.exec_pending = false;
                execute_arbitrary_code(&g_rm);
            }
#endif
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
                bool pulse_ok = (o2p_sht4x_heater_pulse(
                                     O2P_SHT_CMD_HEAT_200MW_1S) == O2P_SHT_OK);
                g_sht_pulse_failed = !pulse_ok;
                if (!pulse_ok) {
                    /* A pulse that did not complete leaves the element in an
                     * unknown thermal state; keep the mask, and re-stamp it so
                     * the window runs from where the attempt stopped.
                     *
                     * "let the next cycle report the SHT as failed" is what
                     * this comment used to say, and it was true only while the
                     * mask raised I2C_FAIL_SHT unconditionally - the next cycle
                     * is INSIDE the mask and never reaches a measurement. The
                     * flag above is what reports it now. */
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
