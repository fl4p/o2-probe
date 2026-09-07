/* The o2-probe Modbus register map.
 *
 * PLAN.md:283 claims this map is "committed to DESIGN.md"; it never was. This
 * file is the map, and FIRMWARE.md carries the human-readable copy.
 *
 * Layout rationale. The master is a Dragino RS485-LS whose reads are literal
 * pre-programmed FC03 frames over a CONTIGUOUS block, and whose uplink is a
 * LoRaWAN payload with a hard 51-byte ceiling at SF12. So the channels that
 * must survive every cycle are packed into ONE eight-register block at address
 * zero: 16 bytes, one AT+COMMAND, alongside the two SMT100 blocks already on
 * the bus. Diagnostics and configuration live further out where a field
 * technician can reach them but the routine uplink never pays for them.
 *
 * Undefined addresses raise exception 02 rather than reading as zero. That is
 * deliberate: 0x0000 in the O2 register decodes as a perfectly plausible
 * 0.00 %vol, which is exactly the reading an anaerobic pile would produce.
 * A mistyped AT+COMMAND must look like a fault, not like anoxia.
 */
#ifndef O2P_REGMAP_H
#define O2P_REGMAP_H

#include <stdbool.h>
#include <stdint.h>

#include "modbus_pdu.h"
#include "update.h"

/* ---- Primary block: 0x0000, 8 registers ---- */
enum {
    /* DRY BASIS: oxygen as a fraction of the WATER-FREE gas, %vol * 100,
     * 0xFFFF invalid. See the note below - the basis is the whole point. */
    O2P_REG_O2_COMP      = 0x0000u, /* u16  %vol * 100        0xFFFF invalid */
    /* Uncorrected cell current. Neither humidity- nor pressure-corrected and
     * deliberately so: it is the raw evidence, and the only channel that
     * still means something when the SHT45 is gone. */
    O2P_REG_O2_RAW       = 0x0001u, /* i16  cell uA * 100     0x8000 invalid */
    O2P_REG_T_TIP        = 0x0002u, /* i16  0.01 C (TMP117)   0x8000 invalid */
    O2P_REG_T_CHAMBER    = 0x0003u, /* i16  0.01 C (SHT45)    0x8000 invalid */
    O2P_REG_RH_CHAMBER   = 0x0004u, /* u16  0.01 %RH          0xFFFF invalid */
    O2P_REG_HEATER_DUTY  = 0x0005u, /* u16  0.01 %                          */
    O2P_REG_FAULTS       = 0x0006u, /* u16  bitfield, see faults.h          */
    O2P_REG_SETTLE_S     = 0x0007u, /* u16  seconds remaining, 0 = settled  */
};
#define O2P_REG_PRIMARY_BASE  0x0000u
#define O2P_REG_PRIMARY_COUNT 8u

/* O2_COMP IS DRY BASIS - oxygen as a fraction of the water-free gas.
 *
 * A number whose basis is undocumented is worse than either choice, so:
 * water vapour is a gas and it displaces everything else pro rata, which
 * makes wet-basis oxygen fall as the pile gets hotter and wetter even when
 * aeration has not changed at all. In a 60 C pile at 100 %RH, fully aerated
 * air is 16.815 %vol wet against 20.946 dry - a 19.7 % error in the direction
 * that looks like anoxia, and the exact condition this probe exists for.
 * Dry basis is what the compost literature, a Draeger tube and a lab
 * instrument all report, and the only basis on which a trend line means
 * respiration rather than weather.
 *
 * The correction needs RH, chamber temperature and total pressure. When it
 * cannot be evaluated - SHT45 gone or masked, gas beyond the Magnus fit,
 * water vapour past half the total pressure - O2_COMP publishes 0xFFFF. It
 * NEVER publishes the wet-basis number under the dry-basis name. Rev A has no
 * barometer, so P comes from ASSUMED_P_HPA (0x0042).
 * Argument and evidence: O2-HUMIDITY-CORRECTION.md. */

/* ---- Diagnostic block: 0x0010, 19 registers, read-only ---- */
enum {
    O2P_REG_VREF_MON_MV  = 0x0010u,
    O2P_REG_VA_MON_MV    = 0x0011u,
    O2P_REG_VIN_MON_MV   = 0x0012u,
    O2P_REG_AFE_VOUT_MV  = 0x0013u,
    O2P_REG_DEW_MARGIN   = 0x0014u, /* i16 0.01 K, 0x8000 invalid */
    O2P_REG_PRESSURE_HPA = 0x0015u, /* 0 when the BMP390 is DNP, as it is */
    O2P_REG_UPTIME_HI    = 0x0016u,
    O2P_REG_UPTIME_LO    = 0x0017u,
    O2P_REG_FW_VERSION   = 0x0018u,
    O2P_REG_HW_REV       = 0x0019u,
    O2P_REG_RESET_CAUSE  = 0x001Au,
    O2P_REG_LMP_READBACK = 0x001Bu, /* TIACN << 8 | REFCN, as actually read */
    O2P_REG_MB_CRC_ERRS  = 0x001Cu,
    O2P_REG_MB_FRAME_ERRS= 0x001Du,
    O2P_REG_I2C_ERRS     = 0x001Eu,
    O2P_REG_EXP_DATA     = 0x001Fu, /* 0xFFFF = no expansion head present */
    /* Sampled supervision is not proof. The MCU checks the analog rail and the
     * AFE's register image once a second, so a 3V3A excursion that begins and
     * recovers between samples is missed entirely - the readback afterwards is
     * correct and the rail reads normal, while the cell in fact needs another
     * 15 minutes. These two counters are what makes that visible from a buried
     * probe: a SETTLE_RESTARTS that climbs without a corresponding fault ever
     * being caught in an uplink is the signature of exactly that. */
    O2P_REG_SETTLE_RESTARTS = 0x0020u,
    /* Increments on every published cycle. A master that sees this frozen
     * across two polls knows the sampler has stalled even though every other
     * register still holds a plausible value. */
    O2P_REG_SAMPLE_SEQ      = 0x0021u,
    /* MCU die temperature, i16 0.01 C, 0x8000 invalid. Not an ambient
     * reading and not part of the oxygen path - it is the die, self-heating
     * included, at about +/-5 C. It is here because it is the only
     * temperature on the board that does not depend on I2C1: when T_TIP and
     * T_CHAMBER disagree with it, or vanish together, that is the bus, not
     * the weather. */
    O2P_REG_T_DIE           = 0x0022u,
    /* Every fault bit seen since power-up, never cleared.
     *
     * O2P_REG_FAULTS holds what is wrong now (plus a short latch, see
     * O2P_FAULT_LATCH_S). That is the right thing to act on and the wrong
     * thing to diagnose from: a probe that glitched once a month ago and one
     * that is glitching every hour both read clean between events. This
     * register is the difference between them. */
    O2P_REG_FAULTS_EVER     = 0x0023u,
    /* Cycles in which the ADS1119 delivered no conversion at all
     * (O2P_FAULTS_ADS_NO_CONVERSION), saturating at 0xFFFF.
     *
     * The latch guarantees such an event is SEEN; this counts how often. A
     * rate is what separates a one-off from a failing part, and the latch
     * self-clears, so without this the count is lost. */
    O2P_REG_ADS_FAIL_COUNT  = 0x0024u,
};
#define O2P_REG_DIAG_BASE  0x0010u
#define O2P_REG_DIAG_COUNT 21u

/* ---- Config block: 0x0030, 21 registers, read/write, flash-backed ---- */
enum {
    O2P_REG_SLAVE_ADDR      = 0x0030u,
    O2P_REG_BAUD_CODE       = 0x0031u,
    O2P_REG_PARITY_CODE     = 0x0032u,
    O2P_REG_RH_SETPOINT     = 0x0033u, /* 0.01 %RH, v1 heater loop target */
    O2P_REG_DT_MAX_K        = 0x0034u, /* 0.01 K, tip-above-chamber clamp */
    O2P_REG_HEATER_MAX_DUTY = 0x0035u, /* 0.01 % */
    O2P_REG_HEATER_PWM_HZ   = 0x0036u,
    O2P_REG_CAL_AIR_NA_HI   = 0x0037u,
    O2P_REG_CAL_AIR_NA_LO   = 0x0038u,
    O2P_REG_CAL_TEMP_C100   = 0x0039u, /* i16 */
    O2P_REG_TEMPCO_PPM_K    = 0x003Au, /* i16 ppm/K; 0 = no compensation */
    O2P_REG_SHT_PULSE_H     = 0x003Bu,
    O2P_REG_SHT_PULSE_TRIG  = 0x003Cu,
    O2P_REG_CAL_TRIGGER     = 0x003Du, /* write O2P_CAL_MAGIC to take an air point */
    O2P_REG_COMMIT          = 0x003Eu, /* write O2P_COMMIT_MAGIC to persist */
    O2P_REG_CONFIG_CRC      = 0x003Fu, /* read-only CRC of the live config */
    /* PI gains, 0.01 units. These are registers rather than compile-time
     * constants for one reason: the plant they tune cannot be characterised
     * anywhere but in a real pile. THERMAL-BARRIER.md bounds the PCB
     * conduction path only, not ring-to-gas, so the shipped values are
     * starting points and nothing more.
     *
     * The alternative was reflashing to change a number, and post-pot that
     * means the RS-485 bootloader plus a full image transfer. Two register
     * writes with a laptop at the node is the difference between tuning the
     * loop and not tuning it. */
    O2P_REG_HEATER_KP       = 0x0040u, /* proportional gain x100 */
    O2P_REG_HEATER_KI       = 0x0041u, /* integral gain x100, per second */
    /* Assumed total pressure in hPa, used whenever PRESSURE_HPA reads 0 -
     * which on Rev A is always, the BMP390 being DNP. Without it the
     * water-vapour correction has no P and O2_COMP cannot be computed at all.
     * Defaults to 930 hPa, the 715 m Steingrubenhof site; a probe deployed
     * anywhere else should have this written. NOT because "sea level is 8 %
     * away" - that was this comment's claim until 2026-09-06 and it confuses
     * a difference in absolute pressure with an error in the published
     * number. P appears twice, in K and in the dilution factor, and the two
     * uses largely cancel: calibrating AND deploying at sea level on this
     * default costs about +2 % relative, not +8 %. The +/-3.5 % of WEATHER
     * does not cancel, because it moves P after K is fixed, and is worth
     * about -4.2 %/+4.1 % at 60 C/100 %RH - see CAL_P_HPA below.
     * Range O2P_P_HPA_MIN..MAX. */
    O2P_REG_ASSUMED_P_HPA   = 0x0042u, /* u16 hPa */
    /* The oxygen fraction actually present when the air point was taken,
     * %vol x 1000 (20946 = dry air). NOT a duplicate of O2P_C_AIR: the air
     * point is taken in moist room air, so the current in CAL_AIR_NA belongs
     * to the wet fraction, and attributing it to dry air mis-scales K by
     * 1-2 % for the life of the probe. Written by the CAL_TRIGGER routine
     * from the SHT45 and ASSUMED_P_HPA; a hand-written CAL_AIR_NA should be
     * accompanied by this. Zero means "unknown" and O2_COMP stays invalid. */
    O2P_REG_CAL_AIR_FRAC    = 0x0043u, /* u16 %vol x 1000 */
    /* The TOTAL PRESSURE in force when the air point was taken, hPa, 0 =
     * unknown. Not a duplicate of ASSUMED_P_HPA: that one is the pressure NOW
     * and this one is the pressure THEN, and the cell's gain is proportional
     * to total pressure because it answers to pO2 = C * P. K is fixed at the
     * air point, so a measurement taken at a different P needs its current
     * normalised by P_cal/P_meas before the inverse - without which even a
     * populated barometer would correct the vapour dilution and leave the
     * cell's own pressure-dependent gain uncorrected.
     *
     * Written by the CAL_TRIGGER routine from whatever P was in force then.
     * Zero means "unknown", and the conversion then assumes P_cal == P_meas,
     * i.e. no correction - which is exactly the pre-2026-09-06 behaviour and
     * is what a Rev A board with no barometer gets anyway, since P_meas is
     * then ASSUMED_P_HPA and equals P_cal by construction.
     * Range 0, or O2P_P_HPA_MIN..MAX. */
    O2P_REG_CAL_P_HPA       = 0x0044u, /* u16 hPa, 0 = unknown */
    /* DILUTION EFFICACY, x1000. 1000 = the full gas-law correction.
     *
     * How much of the water-vapour dilution this cell's current actually
     * shows. The gas law says the correction is P/(P-p_w); the 2026-09-07
     * sweep says the cell moves only alpha of it, alpha = 0.453 +/- 0.052
     * (O2-HUMIDITY-CORRECTION.md 15.3), so the factor applied is
     * f_eff = 1 - alpha*(1 - (P-p_w)/P). At 1000 this register changes
     * nothing and the firmware behaves as it did before.
     *
     * A PER-CELL BENCH COEFFICIENT, not a field trim. It takes two disjoint
     * legs to identify - an isothermal humidity ramp for alpha and an
     * isobaric temperature ramp for TEMPCO_PPM_K - and it is not derivable
     * from anything the probe can see in a pile.
     *
     * WRITING IT RESTATES CAL_AIR_FRAC (0x0043) under the new alpha. The
     * stored air fraction is C_air * f_eff(alpha_old) and K is fixed against
     * it, so leaving it alone would rescale every later reading by the ratio.
     * Nothing has to be re-measured to fix that - f_eff inverts exactly - so
     * no recalibration is required and the register is safe to write in any
     * order, including inside a whole-block FC16. The one case that cannot be
     * inverted is alpha_old = 0, where the humidity at the air point is
     * genuinely gone; that falls back to zero, i.e. "unknown".
     * Range 0..2000, see O2P_DIL_ALPHA_MAX. */
    O2P_REG_DIL_ALPHA       = 0x0045u, /* u16 alpha x 1000 */
};
#define O2P_REG_CONFIG_BASE  0x0030u
#define O2P_REG_CONFIG_COUNT 22u

/* Deliberate magics rather than "write 1". A flash cycle and a recalibration
 * are both destructive and both are one stray bit away in a noisy RS-485
 * frame that happened to pass CRC; requiring a 16-bit token makes an accident
 * implausible. This is the same economy the SGX and FDO2 datasheets demand of
 * their own limited flash-cycle budgets. */
#define O2P_COMMIT_MAGIC 0x5AC1u
#define O2P_CAL_MAGIC    0xCA11u

#define O2P_FW_VERSION 0x0001u  /* v0.1 */
#define O2P_HW_REV     0x000Au  /* Rev A */

/* Baud/parity codes. Defaults match the bus the probe joins: the Truebner
 * SMT100s on this cable are 9600 8E1 and the node is configured
 * AT+BAUDR=9600 / AT+PARITY=2 (tech/RS485-LS-SMT100.md:277-283). A probe that
 * came up 8N1 would be silent in a way indistinguishable from bad wiring. */
enum { O2P_BAUD_9600 = 0u, O2P_BAUD_19200 = 1u, O2P_BAUD_38400 = 2u, O2P_BAUD_MAX_CODE = 2u };
enum { O2P_PARITY_NONE = 0u, O2P_PARITY_ODD = 1u, O2P_PARITY_EVEN = 2u };

/* Field order is chosen so the struct has NO implicit padding: it is written
 * to flash byte-for-byte and hashed with a CRC, and padding a compiler is
 * free to leave uninitialised would make that CRC non-deterministic. Widest
 * members first, then the bytes, then explicit reserved bytes to a multiple
 * of the 4-byte alignment. */
typedef struct {
    int32_t  cal_air_na;              /* 0 */
    uint16_t rh_setpoint_x100;        /* 4 */
    uint16_t dt_max_k_x100;           /* 6 */
    uint16_t heater_max_duty_x100;    /* 8 */
    uint16_t heater_pwm_hz;           /* 10 */
    int16_t  cal_temp_c100;           /* 12 */
    int16_t  tempco_ppm_per_k;        /* 14 */
    uint16_t sht_pulse_interval_h;    /* 16 */
    uint16_t heater_kp_x100;          /* 18 */
    uint16_t heater_ki_x100;          /* 20 */
    uint16_t assumed_p_hpa;           /* 22 */
    uint16_t cal_air_frac_x1000;      /* 24 */
    uint16_t cal_p_hpa;               /* 26 */
    uint8_t  slave_addr;              /* 28 */
    uint8_t  baud_code;               /* 29 */
    uint8_t  parity_code;             /* 30 */
    uint8_t  reserved[1];             /* 31 */
    uint16_t dil_alpha_x1000;         /* 32 */
    uint8_t  reserved2[2];            /* 34 */
} o2p_config_t;
/* The record wrapper in config_flash.h is a fixed 64 bytes and pads to it, so
 * growing this struct spends the record's reserved tail rather than moving
 * the CRC into a new place. Pinned so a field added without checking the
 * arithmetic fails to compile instead of shifting every offset by two. */
_Static_assert(sizeof(o2p_config_t) == 36u, "config layout is 36 bytes");

/* Live measurement snapshot, published atomically by the sampler. */
typedef struct {
    uint16_t o2_comp;
    int16_t  o2_raw;
    int16_t  t_tip;
    int16_t  t_chamber;
    uint16_t rh_chamber;
    uint16_t heater_duty;
    uint16_t faults;
    uint16_t settle_s;

    uint16_t vref_mv;
    uint16_t va_mv;
    uint16_t vin_mv;
    uint16_t afe_vout_mv;
    int16_t  dew_margin_x100;
    uint16_t pressure_hpa;
    uint32_t uptime_s;
    uint16_t reset_cause;
    uint16_t lmp_readback;
    uint16_t mb_crc_errs;
    uint16_t mb_frame_errs;
    uint16_t i2c_errs;
    uint16_t exp_data;
    uint16_t settle_restarts;
    uint16_t sample_seq;
    int16_t  t_die;
    uint16_t faults_ever;
    uint16_t ads_fail_count;
} o2p_snapshot_t;

/* Reset every channel to its invalid sentinel. The sampler calls this at the
 * START of each cycle rather than copying the previous snapshot forward, so a
 * channel whose read failed this cycle CANNOT publish last cycle's plausible
 * value under this cycle's fault word. Carrying values forward is the classic
 * way a dead sensor keeps looking alive. */
void o2p_snapshot_reset(o2p_snapshot_t *s);

typedef struct {
    o2p_snapshot_t buf[2];
    volatile uint8_t live;      /* index of the buffer readers may use */

    o2p_config_t cfg;
    /* Set when a write changed the serial parameters. The transport applies
     * it only after the response has physically left the wire - changing baud
     * or address mid-reply would strand the master with a half-read frame. */
    volatile bool serial_reconfig_pending;
    volatile bool commit_pending;
    volatile bool cal_requested;
    volatile bool sht_pulse_requested;

    /* The firmware updater, or NULL. It is reached through the register map
     * because that is where a Modbus master reaches everything - but it is
     * deliberately not PART of the register map: the update engine is shared
     * verbatim with the bootloader, which has no configuration, no snapshot
     * and no sampler. When this is NULL the update blocks answer exception 02
     * exactly as any other undefined address does. */
    o2p_update_t *upd;
} o2p_regmap_t;

void o2p_regmap_init(o2p_regmap_t *rm);

/* Sampler side: get the buffer to fill, then publish it. */
o2p_snapshot_t *o2p_regmap_staging(o2p_regmap_t *rm);
void o2p_regmap_publish(o2p_regmap_t *rm);
const o2p_snapshot_t *o2p_regmap_live(const o2p_regmap_t *rm);

/* Modbus side. Both match the o2p_mb_read_fn / o2p_mb_write_fn signatures. */
uint8_t o2p_regmap_read(void *ctx, uint16_t addr, uint16_t count, uint16_t *out);
uint8_t o2p_regmap_write(void *ctx, uint16_t addr, uint16_t count, const uint16_t *in);

/* True if `cfg` is self-consistent and safe to run from. Used both on a
 * Modbus write and when loading from flash, so a corrupt flash image cannot
 * install a configuration a Modbus master would have been refused. */
bool o2p_config_valid(const o2p_config_t *cfg);
void o2p_config_defaults(o2p_config_t *cfg);
uint16_t o2p_config_crc(const o2p_config_t *cfg);

#endif /* O2P_REGMAP_H */
