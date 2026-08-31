/* o2-probe Rev A - v0 application.
 *
 * A 1 Hz sample cycle feeding a Modbus RTU slave. No sleep modes: the probe is
 * mains/PSU powered through the farm cable and the cell bias must run
 * continuously, so there is no power budget to optimise and every low-power
 * mode is a way to accidentally interrupt the bias.
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
 * settling time "as long as 15 minutes". Every restart of this timer
 * invalidates the oxygen channel until it expires. */
#define O2P_SETTLE_SECONDS 900u

/* Above this the SGX cell is outside its rating and the reading is an
 * extrapolation - flagged, NOT discarded (PLAN.md:211-228). */
#define O2P_TEMP_OVER_C100 6000

/* The absolute tip limit programmed into the TMP117's therm-mode alert. Well
 * below the cell's own destruction point but above the ~75 C the pile
 * reaches, so it is a fault limit and not a thermostat. */
#define O2P_TIP_LIMIT_C100 8500
#define O2P_TIP_HYST_K100  500

/* +12 V input. The design range is 7-15 V; below about 9 V the buck is still
 * fine but something is wrong with the cable or the supply. */
#define O2P_VIN_LOW_MV 9000u
/* 3V3A more than ~5 % low means the analog rail is sagging, which is the
 * failure that silently drops the AFE configuration. */
#define O2P_VA_LOW_MV 3130u

static o2p_regmap_t g_rm;
static o2p_cal_t g_cal;

static uint32_t g_settle_deadline_s;
static uint32_t g_uptime_s;

static void restart_settling(void)
{
    g_settle_deadline_s = g_uptime_s + O2P_SETTLE_SECONDS;
}

static void load_cal_from_config(void)
{
    g_cal.cal_air_na = g_rm.cfg.cal_air_na;
    g_cal.cal_temp_c100 = g_rm.cfg.cal_temp_c100;
    g_cal.tempco_per_k = (float)g_rm.cfg.tempco_ppm_per_k * 1e-6f;
}

/* Convert an AIN0 code to cell current in nanoamps.
 *
 *   V(AIN0) = internal_zero +/- I * R_TIA          (LMP91000, R_TIA = 7 kOhm)
 *
 * so the cell current is the DEPARTURE from the internal zero, which is 67 %
 * of VREF. Both the zero and the ADC reference come from VREF_TRIM, so this is
 * ratiometric and first-order immune to VREF drift - the reason the board
 * shares one reference between the AFE and the ADC.
 *
 * The sign is deliberately preserved. SCHEMATIC-REVIEW.md M4 leaves the SGX
 * sign convention open, and the air-versus-nitrogen bench pair is what settles
 * it; a firmware that took an absolute value here would hide the answer.
 */
#define O2P_LMP_TIA_OHM 7000
#define O2P_LMP_INT_Z_NUM 67
#define O2P_LMP_INT_Z_DEN 100

static int32_t code_to_cell_na(int32_t code, uint32_t vref_mv)
{
    int32_t uv = o2p_ads1119_code_to_uv(code, vref_mv);
    int32_t zero_uv = (int32_t)(((int64_t)vref_mv * 1000 * O2P_LMP_INT_Z_NUM) /
                                O2P_LMP_INT_Z_DEN);
    int32_t delta_uv = zero_uv - uv;   /* current sinks VOUT below the zero */
    /* I[nA] = V[uV] / R[ohm] * 1000 */
    return (int32_t)(((int64_t)delta_uv * 1000) / O2P_LMP_TIA_OHM);
}

static void sample_cycle(void)
{
    o2p_snapshot_t *s = o2p_regmap_staging(&g_rm);
    memcpy(s, o2p_regmap_live(&g_rm), sizeof(*s));

    uint16_t faults = O2P_F_HEATER_DISABLED;

    /* ---- rails first: everything else is interpreted in their light ---- */
    uint16_t va_mv = 0u;
    if (o2p_mcu_adc_read_va_mv(&va_mv)) {
        s->va_mv = va_mv;
        if (va_mv < O2P_VA_LOW_MV) {
            faults |= O2P_F_VA_LOW;
            /* A sagging analog rail can drop the AFE's volatile config
             * without any reset. Assume the bias went with it. */
            restart_settling();
        }
    } else {
        /* No rail reading is not a good rail reading. */
        s->va_mv = 0u;
        faults |= O2P_F_VA_LOW;
    }

    /* ---- AFE supervision: is the cell still biased as intended? ---- */
    uint16_t lmp_back = 0u;
    o2p_lmp_status_t lst = o2p_lmp91000_verify(&lmp_back);
    s->lmp_readback = lmp_back;
    if (lst == O2P_LMP_IO) {
        faults |= O2P_F_I2C_FAIL_LMP;
        restart_settling();
    } else if (lst == O2P_LMP_MISMATCH) {
        faults |= O2P_F_AFE_CONFIG_MISMATCH;
        restart_settling();
        (void)o2p_lmp91000_configure();   /* put it back; settling covers it */
    }

    /* ---- reference health, measured against the ADC's OWN reference ---- */
    uint32_t vref_mv = O2P_HW_VREF_TARGET_MV;
    int32_t vref_code = 0;
    if (o2p_ads1119_average(O2P_ADS_MUX_AIN1_AGND, O2P_ADS_DR_20SPS,
                            false, 4u, &vref_code) == O2P_ADS_OK) {
        int32_t half_uv = o2p_ads1119_code_to_uv(vref_code, O2P_ADS_INTERNAL_REF_MV);
        uint32_t measured = (uint32_t)((half_uv / 1000) *
                                       (int32_t)O2P_HW_DIV_VREF_DEN /
                                       (int32_t)O2P_HW_DIV_VREF_NUM);
        s->vref_mv = (uint16_t)measured;
        /* Out of the trim network's reachable band means the reference is not
         * what the bias depends on, so the bias is not -600 mV either. */
        if (measured < O2P_HW_VREF_MIN_MV - 100u ||
            measured > O2P_HW_VREF_MAX_MV + 100u) {
            faults |= O2P_F_ADC_RANGE;
        } else {
            vref_mv = measured;
        }
    } else {
        faults |= O2P_F_I2C_FAIL_ADS;
        s->vref_mv = 0u;
    }

    /* ---- input supply ---- */
    int32_t vin_code = 0;
    if (o2p_ads1119_average(O2P_ADS_MUX_AIN3_AGND, O2P_ADS_DR_20SPS,
                            true, 2u, &vin_code) == O2P_ADS_OK) {
        int32_t pin_uv = o2p_ads1119_code_to_uv(vin_code, vref_mv);
        uint32_t vin_mv = (uint32_t)((pin_uv / 1000) *
                                     (int32_t)O2P_HW_DIV_VIN_DEN /
                                     (int32_t)O2P_HW_DIV_VIN_NUM);
        s->vin_mv = (uint16_t)vin_mv;
        if (vin_mv < O2P_VIN_LOW_MV) {
            faults |= O2P_F_VIN_LOW;
        }
    } else {
        faults |= O2P_F_I2C_FAIL_ADS;
        s->vin_mv = 0u;
    }

    /* ---- temperatures ---- */
    int16_t t_tip = O2P_I16_INVALID;
    if (o2p_tmp117_read_c100(&t_tip) == O2P_TMP_OK) {
        s->t_tip = t_tip;
    } else {
        s->t_tip = O2P_I16_INVALID;
        t_tip = O2P_I16_INVALID;
        faults |= O2P_F_I2C_FAIL_TMP;
    }

    int16_t t_ch = 0;
    uint16_t rh = 0;
    bool chamber_ok = (o2p_sht4x_measure(&t_ch, &rh) == O2P_SHT_OK);
    if (chamber_ok) {
        s->t_chamber = t_ch;
        s->rh_chamber = rh;
    } else {
        s->t_chamber = O2P_I16_INVALID;
        s->rh_chamber = O2P_U16_INVALID;
        faults |= O2P_F_I2C_FAIL_SHT;
    }

    /* The temperature that matters for the cell's rating is the gas it sees.
     * Use the chamber when it is available and the tip otherwise. */
    int16_t t_gas = chamber_ok ? t_ch : t_tip;
    if (t_gas != O2P_I16_INVALID && t_gas > O2P_TEMP_OVER_C100) {
        faults |= O2P_F_TEMP_OVER;   /* extrapolated, still valid - by decision */
    }

    /* ---- condensation margin ---- */
    s->dew_margin_x100 = O2P_I16_INVALID;
    if (chamber_ok && t_tip != O2P_I16_INVALID) {
        float margin = 0.0f;
        if (o2p_dew_margin_k((float)t_tip * 0.01f, (float)t_ch * 0.01f,
                             (float)rh * 0.01f, &margin)) {
            float m100 = margin * 100.0f;
            if (m100 > -32768.0f && m100 < 32767.0f) {
                s->dew_margin_x100 = (int16_t)m100;
                if (margin <= 0.0f) {
                    /* The tip is at or below the dew point: the membrane is
                     * condensing. In v0 there is no heater to answer with, so
                     * this is a report, not a control action. */
                    faults |= O2P_F_DEW_SUSPECT;
                }
            }
        }
    }

    /* ---- oxygen ---- */
    int32_t o2_code = 0;
    o2p_ads_status_t ast = o2p_ads1119_average(O2P_ADS_MUX_AIN0_AGND,
                                               O2P_ADS_DR_20SPS, true, 8u,
                                               &o2_code);
    if (ast != O2P_ADS_OK) {
        faults |= O2P_F_I2C_FAIL_ADS;
        s->afe_vout_mv = 0u;
        s->o2_raw = O2P_I16_INVALID;
        s->o2_comp = O2P_U16_INVALID;
    } else {
        s->afe_vout_mv = (uint16_t)(o2p_ads1119_code_to_uv(o2_code, vref_mv) / 1000);
        int32_t cell_na = code_to_cell_na(o2_code, vref_mv);

        /* uA * 100, i.e. 10 nA per count. */
        int32_t raw_x100 = cell_na / 10;
        s->o2_raw = (raw_x100 > 32767 || raw_x100 < -32767)
                        ? O2P_I16_INVALID : (int16_t)raw_x100;

        o2p_cal_t cal = g_cal;
        if (cal.cal_air_na <= 0) {
            /* Never calibrated. Use the datasheet nominal so the probe still
             * reports something, and say loudly that it did. */
            cal.cal_air_na = O2P_CAL_AIR_NOMINAL_NA;
            faults |= O2P_F_CAL_DEFAULT;
        }

        float c = 0.0f;
        o2p_status_t st = o2p_fraction_from_current(
            &cal, cell_na, (t_gas != O2P_I16_INVALID) ? t_gas : cal.cal_temp_c100, &c);
        if (st == O2P_RANGE) {
            faults |= O2P_F_ADC_RANGE;
        }
        s->o2_comp = o2p_encode_percent(st, c);

        /* Air-point calibration, if an operator asked for one this cycle. */
        if (g_rm.cal_requested) {
            g_rm.cal_requested = false;
            if (o2p_o2_valid(faults) &&
                o2p_calibrate_air(&g_cal, cell_na,
                                  (t_gas != O2P_I16_INVALID) ? t_gas : 2500)) {
                g_rm.cfg.cal_air_na = g_cal.cal_air_na;
                g_rm.cfg.cal_temp_c100 = g_cal.cal_temp_c100;
            }
            /* A refused calibration leaves the old constants in place. */
        }
    }

    /* ---- settling ---- */
    if (g_uptime_s < g_settle_deadline_s) {
        faults |= O2P_F_SETTLING;
        s->settle_s = (uint16_t)((g_settle_deadline_s - g_uptime_s > 65535u)
                                     ? 65535u
                                     : (g_settle_deadline_s - g_uptime_s));
    } else {
        s->settle_s = 0u;
    }

    /* The single point where the validity rule is applied. Anything the fault
     * word says is untrustworthy must leave as a sentinel, whatever the
     * conversion above produced. */
    if (!o2p_o2_valid(faults)) {
        s->o2_comp = O2P_U16_INVALID;
        s->o2_raw = O2P_I16_INVALID;
    }

    s->heater_duty = o2p_heater_duty_x100();
    s->pressure_hpa = 0u;      /* BMP390 is DNP on Rev A */
    s->exp_data = O2P_U16_INVALID;   /* J2 expansion is DNP on Rev A */
    s->uptime_s = g_uptime_s;
    s->reset_cause = o2p_reset_cause();
    s->mb_crc_errs = o2p_modbus_crc_errors();
    s->mb_frame_errs = o2p_modbus_frame_errors();
    s->i2c_errs = o2p_i2c1_error_count();
    s->faults = faults;

    o2p_regmap_publish(&g_rm);
}

static void bring_up_devices(void)
{
    o2p_i2c1_init();
    o2p_lmp91000_gpio_init();
    o2p_mcu_adc_init();

    (void)o2p_ads1119_init();
    (void)o2p_tmp117_init(O2P_TIP_LIMIT_C100, O2P_TIP_HYST_K100);
    (void)o2p_sht4x_reset();
    (void)o2p_lmp91000_configure();

    /* Applying bias is itself the start of the settling interval. */
    restart_settling();
}

int main(void)
{
    o2p_clock_init();

    /* Heater off before anything else can run long enough to matter. */
    o2p_heater_init();
    o2p_heater_force_off();

    o2p_regmap_init(&g_rm);
    if (!o2p_config_load(&g_rm.cfg)) {
        /* No stored configuration, or it was corrupt. Defaults are already
         * loaded; the CAL_DEFAULT bit will follow from cal_air_na == 0. */
    }
    load_cal_from_config();

    bring_up_devices();
    o2p_modbus_init(&g_rm.cfg);
    o2p_wdt_init();

    uint32_t last_sample_ms = o2p_millis();
    uint32_t last_second_ms = last_sample_ms;
    bool sampled_since_feed = false;

    for (;;) {
        /* Serve the bus first: a 5-minute poll must never wait behind a
         * sample cycle that is retrying a dead device. */
        (void)o2p_modbus_poll(&g_rm);

        if (o2p_elapsed(last_second_ms, 1000u)) {
            last_second_ms += 1000u;
            g_uptime_s++;
        }

        if (o2p_elapsed(last_sample_ms, 1000u)) {
            last_sample_ms = o2p_millis();
            sample_cycle();
            sampled_since_feed = true;
        }

        /* Deferred work that must not run mid-transmission. */
        if (!o2p_modbus_tx_busy()) {
            if (g_rm.serial_reconfig_pending) {
                g_rm.serial_reconfig_pending = false;
                o2p_modbus_reconfigure(&g_rm.cfg);
            }
            if (g_rm.commit_pending) {
                g_rm.commit_pending = false;
                (void)o2p_config_store(&g_rm.cfg);
                load_cal_from_config();
            }
            if (g_rm.sht_pulse_requested) {
                g_rm.sht_pulse_requested = false;
                (void)o2p_sht4x_heater_pulse(O2P_SHT_CMD_HEAT_200MW_1S);
            }
        }

        /* The watchdog is fed only when the sample loop is still completing
         * cycles. A probe whose sampler has wedged must RESET, not sit there
         * serving a stale snapshot to the bus forever - serving stale data
         * indefinitely is the failure this watchdog exists to prevent, so
         * feeding it from a bare `for(;;)` would defeat its only purpose.
         */
        if (sampled_since_feed) {
            sampled_since_feed = false;
            o2p_wdt_feed();
        }
    }
}
