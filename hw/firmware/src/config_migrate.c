#include "config_migrate.h"

#include "modbus_pdu.h"
#include "o2.h"

#include <string.h>

/* The magic and the record size are shared with config_flash.h, which cannot
 * be included here: it pulls in the flash map and the current record layout,
 * and this file's entire job is to be about the OLD ones. They are pinned
 * against it by a static assert in config_flash.c instead, so a change to
 * either is caught at compile time rather than at the first field upgrade. */
#define MIGRATE_CONFIG_MAGIC 0x4F325043u   /* "O2PC" */
#define MIGRATE_RECORD_SIZE  64u

/* ---- layout version 2 ---------------------------------------------------
 *
 * As shipped before 2026-09-06: no assumed_p_hpa, no cal_air_frac_x1000, no
 * cal_p_hpa. 28 bytes, and slave_addr sits at offset 22. */
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
    uint8_t  slave_addr;              /* 22 */
    uint8_t  baud_code;               /* 23 */
    uint8_t  parity_code;             /* 24 */
    uint8_t  reserved[3];             /* 25..27 */
} o2p_config_v2_t;
_Static_assert(sizeof(o2p_config_v2_t) == 28u, "v2 config layout is 28 bytes");

/* ---- layout version 3 ---------------------------------------------------
 *
 * The water-vapour fields, without the calibration pressure that version 4
 * adds. 32 bytes, and slave_addr moved to offset 26 - which is why a cast
 * would be wrong rather than merely untidy.
 *
 * No board has ever run a version-3 record: version 3 existed for the length
 * of one commit that could not be built. It is decoded anyway, because the
 * cost is one struct and the alternative is a version whose records are
 * silently unreadable if one ever did reach a board. */
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
    uint8_t  slave_addr;              /* 26 */
    uint8_t  baud_code;               /* 27 */
    uint8_t  parity_code;             /* 28 */
    uint8_t  reserved[3];             /* 29..31 */
} o2p_config_v3_t;
_Static_assert(sizeof(o2p_config_v3_t) == 32u, "v3 config layout is 32 bytes");

/* ---- layout version 4 ---------------------------------------------------
 *
 * As shipped from 2026-09-06: the full water-vapour set including the
 * calibration pressure, and no dilution efficacy. 32 bytes - the same SIZE as
 * v3, which is why the version word and not the length is what decodes a
 * record, and why record_crc_ok() is given the size explicitly.
 *
 * This is the version every board in the field is running. */
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
} o2p_config_v4_t;
_Static_assert(sizeof(o2p_config_v4_t) == 32u, "v4 config layout is 32 bytes");

/* ---- layout version 5 ---------------------------------------------------
 *
 * v4 plus dil_alpha_x1000. 36 bytes. This is what the field is running as of
 * 2026-09-08, so its migration must preserve everything - a v5 record differs
 * from v6 only by the ABSENCE of a zero point, and absent is exactly what the
 * default already says. Nothing is discarded here. */
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
} o2p_config_v5_t;
_Static_assert(sizeof(o2p_config_v5_t) == 36u, "v5 config layout is 36 bytes");

/* v6 and v7. BOTH WERE UNREACHABLE UNTIL NOW, and that was a live hazard.
 *
 * config_flash.c sends any record whose layout_version differs from the
 * current one through this function, and a `default: return false` here makes
 * the caller fall back to FULL DEFAULTS - which resets slave_addr, baud_code
 * and parity_code. That is precisely the "potted probe disappears from its
 * master on a firmware update" outcome read_record()'s own comment says must
 * not happen. Versions 6 and 7 were appended without adding cases here, so
 * every bump since has silently carried that hole; bumping to 8 is what would
 * have detonated it, because v7 is the version actually on the bench probe.
 *
 * Both are strict PREFIXES of the current layout, so the fields are copied
 * one by one rather than by a block memcpy. That is not stylistic: v8 places
 * tip_setpoint_c100 over v7's reserved3[2], where a v7 record holds zeros, and
 * zero is a legal setpoint meaning "hold 0.00 C" rather than "off". A prefix
 * copy would arm a temperature loop on every upgraded probe. Copying named
 * fields leaves o2p_config_defaults()' sentinel in place instead. */
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
    uint8_t  cal_zero_taken;          /* 34 */
    uint8_t  reserved2[1];            /* 35 */
    int32_t  cal_zero_na;             /* 36 */
} o2p_config_v6_t;
_Static_assert(sizeof(o2p_config_v6_t) == 40u, "v6 config layout is 40 bytes");

typedef struct {
    o2p_config_v6_t v6;               /* 0 */
    uint16_t heater_rh_consent;       /* 40 */
    uint8_t  reserved3[2];            /* 42 */
} o2p_config_v7_t;
_Static_assert(sizeof(o2p_config_v7_t) == 44u, "v7 config layout is 44 bytes");

/* Carry a v6-shaped body. Unlike carry_common(), the CALIBRATION SURVIVES:
 * nothing about what cal_air_na, the zero point or the dilution model mean
 * changed between v6, v7 and v8 - the only additions were consent fields and
 * a setpoint - so discarding a good air point here would force a needless
 * recalibration on every probe in the field. */
static void carry_v6_body(o2p_config_t *out, const o2p_config_v6_t *v)
{
    out->cal_air_na = v->cal_air_na;
    out->rh_setpoint_x100 = v->rh_setpoint_x100;
    out->dt_max_k_x100 = v->dt_max_k_x100;
    out->heater_max_duty_x100 = v->heater_max_duty_x100;
    out->heater_pwm_hz = v->heater_pwm_hz;
    out->cal_temp_c100 = v->cal_temp_c100;
    out->tempco_ppm_per_k = v->tempco_ppm_per_k;
    out->sht_pulse_interval_h = v->sht_pulse_interval_h;
    out->heater_kp_x100 = v->heater_kp_x100;
    out->heater_ki_x100 = v->heater_ki_x100;
    out->assumed_p_hpa = v->assumed_p_hpa;
    out->cal_air_frac_x1000 = v->cal_air_frac_x1000;
    out->cal_p_hpa = v->cal_p_hpa;
    out->dil_alpha_x1000 = v->dil_alpha_x1000;
    out->cal_zero_taken = v->cal_zero_taken;
    out->cal_zero_na = v->cal_zero_na;
    /* Reachability. The whole reason this file exists. */
    out->slave_addr = v->slave_addr;
    out->baud_code = v->baud_code;
    out->parity_code = v->parity_code;
    /* NEITHER CONSENT IS EVER CARRIED, and tip_setpoint_c100 keeps the
     * sentinel o2p_config_defaults() put there. An upgrade always lands with
     * both autonomous loops off, whatever the old record said - the same rule
     * heater_rh_consent has had since v7, applied to the new one before it can
     * acquire a history of exceptions. */
    out->heater_rh_consent = 0u;
    out->heater_tip_consent = 0u;
}

/* The record wrapper is the same shape in every version - magic, layout
 * version, sequence, configuration, CRC, reserved tail to 64 bytes - so only
 * the configuration's size moves, and with it the CRC's offset. */
#define REC_HDR_BYTES 12u   /* magic + layout_version + sequence */

static uint32_t rd_u32(const uint8_t *p)
{
    uint32_t v;
    memcpy(&v, p, sizeof(v));
    return v;
}

static uint16_t rd_u16(const uint8_t *p)
{
    uint16_t v;
    memcpy(&v, p, sizeof(v));
    return v;
}

/* CRC-16/MODBUS over everything up to but excluding the crc field, exactly as
 * the version that wrote the record computed it. The reserved tail is not
 * covered, in any version. */
static bool record_crc_ok(const uint8_t *rec, size_t cfg_bytes)
{
    size_t crc_off = REC_HDR_BYTES + cfg_bytes;
    uint16_t want = rd_u16(rec + crc_off);
    uint8_t tmp[MIGRATE_RECORD_SIZE];
    memcpy(tmp, rec, MIGRATE_RECORD_SIZE);
    /* The stored CRC was computed with the crc field zeroed. */
    tmp[crc_off] = 0u;
    tmp[crc_off + 1u] = 0u;
    return o2p_mb_crc16(tmp, crc_off) == want;
}

/* The one policy statement, applied identically to every old version.
 *
 * TRANSPORT AND TUNING SURVIVE; THE AIR POINT DOES NOT. The air point is the
 * only thing whose MEANING changed - a pre-v3 cal_air_na was recorded against
 * an assumed dry atmosphere at an unrecorded humidity, and from v4 a
 * calibration also has to say what pressure it was taken at. Anything this
 * function cannot state honestly is left at its default, which for the three
 * calibration fields is zero, which is what raises CAL_DEFAULT and holds
 * O2_COMP on its sentinel until an operator takes a fresh air point.
 *
 * assumed_p_hpa is NOT carried from v3 either, for the same reason in reverse:
 * it is meaningful, but it is only meaningful next to the air point it was in
 * force for, and that air point is being discarded. The default reinstalls the
 * documented site value. */
static void carry_common(o2p_config_t *out,
                         uint16_t rh_setpoint_x100, uint16_t dt_max_k_x100,
                         uint16_t heater_max_duty_x100, uint16_t heater_pwm_hz,
                         int16_t cal_temp_c100, int16_t tempco_ppm_per_k,
                         uint16_t sht_pulse_interval_h,
                         uint16_t heater_kp_x100, uint16_t heater_ki_x100,
                         uint8_t slave_addr, uint8_t baud_code,
                         uint8_t parity_code)
{
    /* Reachability. The whole reason this file exists. */
    out->slave_addr = slave_addr;
    out->baud_code = baud_code;
    out->parity_code = parity_code;
    /* Heater configuration. Unchanged in meaning across every version here,
     * and re-tuning a loop in a buried pile is not a thing an operator can
     * do. max_duty comes across as stored, including a stored zero. */
    out->rh_setpoint_x100 = rh_setpoint_x100;
    out->dt_max_k_x100 = dt_max_k_x100;
    out->heater_max_duty_x100 = heater_max_duty_x100;
    /* NEVER carried. An older record was written by firmware in which the
     * heater was compiled out, or in which consent did not exist, so it
     * cannot express consent and inventing one would be this function
     * granting an authorisation nobody gave. Every upgrade lands with
     * autonomous heating off, whatever max_duty came across. */
    out->heater_rh_consent = 0u;
    out->heater_pwm_hz = heater_pwm_hz;
    out->heater_kp_x100 = heater_kp_x100;
    out->heater_ki_x100 = heater_ki_x100;
    /* Maintenance schedule and the cell's temperature coefficient: both are
     * settings rather than measurements, and neither changed meaning. */
    out->sht_pulse_interval_h = sht_pulse_interval_h;
    out->tempco_ppm_per_k = tempco_ppm_per_k;
    /* The temperature the old air point was taken at. It is kept because it
     * is the reference for tempco and it costs nothing to be right about;
     * with cal_air_na zeroed nothing converts from it until a fresh air point
     * overwrites it anyway. */
    out->cal_temp_c100 = cal_temp_c100;

    /* Discarded, explicitly rather than by omission. */
    out->cal_air_na = 0;
    out->cal_air_frac_x1000 = 0u;
    out->cal_p_hpa = 0u;
}

bool o2p_config_migrate(const void *record, size_t len,
                        o2p_config_t *out, uint32_t *out_seq)
{
    if (record == NULL || out == NULL || out_seq == NULL ||
        len < MIGRATE_RECORD_SIZE) {
        return false;
    }
    const uint8_t *rec = (const uint8_t *)record;
    if (rd_u32(rec) != MIGRATE_CONFIG_MAGIC) {
        return false;
    }
    uint32_t version = rd_u32(rec + 4u);
    uint32_t sequence = rd_u32(rec + 8u);
    const uint8_t *cfg = rec + REC_HDR_BYTES;

    o2p_config_t migrated;
    o2p_config_defaults(&migrated);

    switch (version) {
    case 2u: {
        if (!record_crc_ok(rec, sizeof(o2p_config_v2_t))) {
            return false;
        }
        o2p_config_v2_t v2;
        memcpy(&v2, cfg, sizeof(v2));
        carry_common(&migrated, v2.rh_setpoint_x100, v2.dt_max_k_x100,
                     v2.heater_max_duty_x100, v2.heater_pwm_hz,
                     v2.cal_temp_c100, v2.tempco_ppm_per_k,
                     v2.sht_pulse_interval_h, v2.heater_kp_x100,
                     v2.heater_ki_x100, v2.slave_addr, v2.baud_code,
                     v2.parity_code);
        break;
    }
    case 4u: {
        /* The one version whose air point survives, because v5 changed
         * nothing about what it meant - see config_flash.h. carry_common() is
         * NOT used here: its whole policy is "discard the calibration", and
         * applying it would force a recalibration on every deployed probe for
         * a field that defaults to the behaviour it already had. */
        if (!record_crc_ok(rec, sizeof(o2p_config_v4_t))) {
            return false;
        }
        o2p_config_v4_t v4;
        memcpy(&v4, cfg, sizeof(v4));
        migrated.cal_air_na = v4.cal_air_na;
        migrated.rh_setpoint_x100 = v4.rh_setpoint_x100;
        migrated.dt_max_k_x100 = v4.dt_max_k_x100;
        migrated.heater_max_duty_x100 = v4.heater_max_duty_x100;
        migrated.heater_pwm_hz = v4.heater_pwm_hz;
        migrated.cal_temp_c100 = v4.cal_temp_c100;
        migrated.tempco_ppm_per_k = v4.tempco_ppm_per_k;
        migrated.sht_pulse_interval_h = v4.sht_pulse_interval_h;
        migrated.heater_kp_x100 = v4.heater_kp_x100;
        migrated.heater_ki_x100 = v4.heater_ki_x100;
        migrated.assumed_p_hpa = v4.assumed_p_hpa;
        migrated.cal_air_frac_x1000 = v4.cal_air_frac_x1000;
        migrated.cal_p_hpa = v4.cal_p_hpa;
        migrated.slave_addr = v4.slave_addr;
        migrated.baud_code = v4.baud_code;
        migrated.parity_code = v4.parity_code;
        /* dil_alpha_x1000 keeps the default o2p_config_defaults() installed,
         * 1000, which is the arithmetic v4 performed. */
        break;
    }
    case 5u: {
        /* Everything survives. v6 appends the zero point and its taken flag,
         * and a v5 probe has never taken one - so the honest value is the
         * default, which o2p_config_defaults() has already installed and
         * CAL_STATE reports as NO_ZERO. Carrying the air point across is
         * correct here in a way it was not for v2/v3: its MEANING is
         * unchanged, because subtracting a zero of 0 is what v5 did. */
        if (!record_crc_ok(rec, sizeof(o2p_config_v5_t))) {
            return false;
        }
        o2p_config_v5_t v5;
        memcpy(&v5, cfg, sizeof(v5));
        migrated.cal_air_na = v5.cal_air_na;
        migrated.rh_setpoint_x100 = v5.rh_setpoint_x100;
        migrated.dt_max_k_x100 = v5.dt_max_k_x100;
        migrated.heater_max_duty_x100 = v5.heater_max_duty_x100;
        migrated.heater_pwm_hz = v5.heater_pwm_hz;
        migrated.cal_temp_c100 = v5.cal_temp_c100;
        migrated.tempco_ppm_per_k = v5.tempco_ppm_per_k;
        migrated.sht_pulse_interval_h = v5.sht_pulse_interval_h;
        migrated.heater_kp_x100 = v5.heater_kp_x100;
        migrated.heater_ki_x100 = v5.heater_ki_x100;
        migrated.assumed_p_hpa = v5.assumed_p_hpa;
        migrated.cal_air_frac_x1000 = v5.cal_air_frac_x1000;
        migrated.cal_p_hpa = v5.cal_p_hpa;
        migrated.dil_alpha_x1000 = v5.dil_alpha_x1000;
        migrated.slave_addr = v5.slave_addr;
        migrated.baud_code = v5.baud_code;
        migrated.parity_code = v5.parity_code;
        break;
    }
    case 6u: {
        if (!record_crc_ok(rec, sizeof(o2p_config_v6_t))) {
            return false;
        }
        o2p_config_v6_t v6;
        memcpy(&v6, cfg, sizeof(v6));
        carry_v6_body(&migrated, &v6);
        break;
    }
    case 7u: {
        if (!record_crc_ok(rec, sizeof(o2p_config_v7_t))) {
            return false;
        }
        o2p_config_v7_t v7;
        memcpy(&v7, cfg, sizeof(v7));
        carry_v6_body(&migrated, &v7.v6);
        /* v7.heater_rh_consent is deliberately NOT read. See carry_v6_body. */
        break;
    }
    case 3u: {
        if (!record_crc_ok(rec, sizeof(o2p_config_v3_t))) {
            return false;
        }
        o2p_config_v3_t v3;
        memcpy(&v3, cfg, sizeof(v3));
        carry_common(&migrated, v3.rh_setpoint_x100, v3.dt_max_k_x100,
                     v3.heater_max_duty_x100, v3.heater_pwm_hz,
                     v3.cal_temp_c100, v3.tempco_ppm_per_k,
                     v3.sht_pulse_interval_h, v3.heater_kp_x100,
                     v3.heater_ki_x100, v3.slave_addr, v3.baud_code,
                     v3.parity_code);
        break;
    }
    default:
        /* Version 1, or something from the future, or a half-erased page. */
        return false;
    }

    /* SANITISE THE FIELDS THIS VERSION NEWLY BOUNDS, BEFORE VALIDATING.
     *
     * v5 and earlier accepted any int16_t in tempco_ppm_per_k and
     * cal_temp_c100; v6 bounds both, because together they set the gain and an
     * unbounded pair reports a true 5.00 %vol as 1.84 %vol. Copying such a
     * value across and THEN validating would fail the whole record - and a
     * failed record means full defaults, which resets slave_addr, baud and
     * parity. A potted probe on a non-default address would simply disappear
     * from its master on a firmware update, for a field it is not even using.
     * Found by review 2026-09-08: "everything survives" was false for part of
     * the legal v5 state space.
     *
     * So the offending FIELD is reset, not the record. Zero tempco means "no
     * compensation", which is the honest reading of a coefficient we have just
     * decided we cannot trust, and it is the shipped default anyway. An
     * out-of-range calibration temperature takes the default with the air
     * point cleared alongside it, because a calibration whose reference
     * temperature is nonsense is not a calibration - and unlike the tempco,
     * silently substituting 25 C would keep converting against a reference the
     * probe never saw. */
    if (migrated.tempco_ppm_per_k > O2P_TEMPCO_ABS_MAX_PPM_K ||
        migrated.tempco_ppm_per_k < -O2P_TEMPCO_ABS_MAX_PPM_K) {
        migrated.tempco_ppm_per_k = 0;
    }
    if (!o2p_cal_temp_plausible(migrated.cal_temp_c100)) {
        migrated.cal_temp_c100 = 2500;
        migrated.cal_air_na = 0;            /* raises CAL_DEFAULT */
        migrated.cal_air_frac_x1000 = 0u;
        migrated.cal_p_hpa = 0u;
    }

    /* What remains faces exactly the check a Modbus write would. A migration
     * that produced an out-of-range baud code or an implausible heater limit
     * is still a failed migration: the caller falls back to full defaults,
     * which is the old behaviour and the safe one. */
    if (!o2p_config_valid(&migrated)) {
        return false;
    }
    *out = migrated;
    *out_seq = sequence;
    return true;
}
