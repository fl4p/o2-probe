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

/* ---- Primary block: 0x0000, 8 registers ---- */
enum {
    O2P_REG_O2_COMP      = 0x0000u, /* u16  %vol * 100        0xFFFF invalid */
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

/* ---- Diagnostic block: 0x0010, 16 registers, read-only ---- */
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
};
#define O2P_REG_DIAG_BASE  0x0010u
#define O2P_REG_DIAG_COUNT 18u

/* ---- Config block: 0x0030, 20 registers, read/write, flash-backed ---- */
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
    /* Cell zero current, i32 nanoamps, SIGNED, default 0 = no zero point.
     *
     * Appended at the end rather than placed beside CAL_AIR_NA_HI/LO at
     * 0x0037/0x0038 where they belong logically. The map is a published
     * contract - AT+COMMAND frames on the Dragino name literal addresses - so
     * nothing already in it may be renumbered to make room. Read them with
     * CAL_AIR_NA in one FC03 of the whole config block; the addresses are
     * apart, the meaning is not.
     *
     * DS-0637 rates the zero signal "< 0.4 %vol O2 (20 C)" - 1706 nA at Issue
     * 2's nominal 100 uA cell, 2218 nA at the top of the population. (This
     * said 1194 nA, which was derived from Issue 1's 70 uA nominal and went
     * stale when the rest of the tree moved to Issue 2; corrected 2026-09-08.)
     * Either way it is 8-100x every electronic offset in the chain. Folded into
     * the air point it becomes a slope error across the whole low-O2 range;
     * subtracted here it is an offset. See ../O2-CORRECTION-MODEL-BUDGET.md.
     *
     * Bounded by o2p_cal_zero_plausible() on write, like the air point - an
     * out-of-window value is refused, not stored. */
    O2P_REG_CAL_ZERO_NA_HI  = 0x0042u,
    O2P_REG_CAL_ZERO_NA_LO  = 0x0043u,
};
#define O2P_REG_CONFIG_BASE  0x0030u
#define O2P_REG_CONFIG_COUNT 20u

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
    int32_t  cal_zero_na;             /* 4 */
    uint16_t rh_setpoint_x100;        /* 8 */
    uint16_t dt_max_k_x100;           /* 10 */
    uint16_t heater_max_duty_x100;    /* 12 */
    uint16_t heater_pwm_hz;           /* 14 */
    int16_t  cal_temp_c100;           /* 16 */
    int16_t  tempco_ppm_per_k;        /* 18 */
    uint16_t sht_pulse_interval_h;    /* 20 */
    uint16_t heater_kp_x100;          /* 22 */
    uint16_t heater_ki_x100;          /* 24 */
    uint8_t  slave_addr;              /* 26 */
    uint8_t  baud_code;               /* 27 */
    uint8_t  parity_code;             /* 28 */
    uint8_t  reserved[3];             /* 29..31 */
} o2p_config_t;

/* Adding cal_zero_na moved every field after it and grew the struct from 28 to
 * 32 bytes, so a config record written by an older image no longer parses as
 * this layout. CONFIG_LAYOUT_VERSION in config_flash.c gates exactly that, and
 * the bump (2 -> 3) IS made - it landed in the same commit as this field.
 *
 * This note used to say the bump was still required, and that without it an
 * old record would be caught by its CRC "with probability 65535/65536". Both
 * halves were wrong and both are corrected at CONFIG_LAYOUT_VERSION: the CRC
 * check would have passed deterministically, and what rejects a v2 record is
 * a field-placement coincidence in o2p_config_valid(). Corrected 2026-09-08
 * after a review found the stale instruction still telling a maintainer to
 * redo work that was already done. */

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
    /* Set when ONE FC16 asked for both a calibration and a commit. The commit
     * then waits for the calibration to be taken, instead of racing it. See
     * o2p_regmap_write() and finish_o2(). */
    volatile bool commit_after_cal;
    volatile bool sht_pulse_requested;
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
