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

/* ---- Diagnostic block: 0x0010, 26 registers, read-only ---- */
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
    /* The buffered cell electrodes, and the bias between them.
     *
     * AIN2/AIN3 carry WE_BUF and RE_BUF. DESIGN.md specified differential
     * cell-bias telemetry on them and nothing ever implemented it; AIN3 was
     * meanwhile being sampled and published as vin_mv, which e31d5ac removed.
     * So the probe has never reported the one quantity that separates "the
     * cell changed" from "the measurement changed" - the question a 0.51 %
     * step in O2_RAW on 2026-09-07 could not be answered from telemetry.
     *
     * CELL_BIAS is WE - RE, the potentiostat's actual working point. It is
     * what goes wrong silently: if the counter electrode runs out of headroom
     * the bias walks off its target while every other register stays
     * plausible. 0x8000 invalid, as everywhere else. */
    O2P_REG_WE_BUF_MV       = 0x0025u, /* u16 mV at the pin, 0xFFFF invalid */
    O2P_REG_RE_BUF_MV       = 0x0026u, /* u16 mV at the pin, 0xFFFF invalid */
    O2P_REG_CELL_BIAS_MV    = 0x0027u, /* i16 mV, WE - RE, 0x8000 invalid */
    /* Which binary is this?
     *
     * FW_VERSION (0x0018) is a hand-edited constant and it read 0x0001 on
     * every probe ever built, through every install. So on 2026-09-07, when
     * O2_RAW stepped 0.51 %vol across a firmware install, telemetry could not
     * name the image on either side of the step - and the step's cause is
     * still undetermined partly because of that. A version number someone has
     * to remember to bump is not provenance.
     *
     * BUILD_ID is: bit 31 the working tree was dirty at build time, bits
     * 30..28 reserved, bits 27..0 the 7-hex-digit prefix of the commit the
     * image was built from. Stamped by tools/pio_build_id.py, which FAILS the
     * build rather than emitting a zero - an unidentifiable image is what this
     * register exists to prevent, and a probe is potted.
     *
     * Zero means "built without the stamp", which after this commit is only
     * the host test build. It is NOT reported as a commit. */
    O2P_REG_BUILD_ID_HI     = 0x0028u, /* u16, bits 31..16 */
    O2P_REG_BUILD_ID_LO     = 0x0029u, /* u16, bits 15..0  */
    /* Outcome of the last CAL_TRIGGER (high byte) and the last COMMIT (low
     * byte). A Modbus write is acknowledged when the REQUEST is accepted,
     * which says nothing about whether the calibration was taken or whether
     * it reached flash: a point is refused if the cell is still settling or
     * the gas temperature is missing, and o2p_config_store()'s return value
     * was discarded outright. All three looked like success from the bus, and
     * a power cycle before the next cycle took the calibration with it.
     *
     * Placed at 0x002A, past BUILD_ID, because 0x0022..0x0029 are a PUBLISHED
     * contract that the ChirpStack decoder already parses - putting a status
     * word inside that range would decode as a die temperature. */
    O2P_REG_CMD_RESULT      = 0x002Au,
    /* Calibration completeness, as a bitfield:
     *   bit 0  air point is the datasheet nominal, not a measurement
     *   bit 1  no zero point has been taken
     *
     * A register rather than two fault bits because the 16-bit fault word is
     * FULL - bits 13 and 14 went to ADS_DRDY_STUCK and ADS_CONFIG_LOST - and
     * because these are commissioning state, not faults: a probe with no zero
     * point is not broken, it is unfinished, and it still measures. Folding
     * the missing zero into CAL_DEFAULT would have invalidated O2_COMP
     * outright and made a probe useless until someone carried nitrogen to the
     * pile, for an error bounded at 0.4 %vol. */
    O2P_REG_CAL_STATE       = 0x002Bu,
};
#define O2P_REG_DIAG_BASE  0x0010u
#define O2P_REG_DIAG_COUNT 28u

/* Per-command status byte. Not a bitfield: these are exclusive states of one
 * command, and a bitfield invites "OK and FAILED" to coexist. */
enum {
    O2P_CMD_NONE    = 0u,
    O2P_CMD_PENDING = 1u,
    O2P_CMD_OK      = 2u,
    O2P_CMD_FAILED  = 3u,
};
#define O2P_CAL_STATE_AIR_DEFAULT   0x0001u
#define O2P_CAL_STATE_NO_ZERO       0x0002u

#define O2P_CMD_RESULT_CAL(v)    ((uint8_t)((v) >> 8))
#define O2P_CMD_RESULT_COMMIT(v) ((uint8_t)((v) & 0xFFu))

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
     * sweep says the cell moves only alpha of it, alpha = 0.402 +/- 0.046
     * (O2-HUMIDITY-CORRECTION.md 15.3, in the concentration domain this
     * register is applied in - the log-current regression's 0.453 divided by
     * the cell law's local gain 1.1273), so the factor applied is
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
    /* Cell zero current, i32 nanoamps, SIGNED. 0 = no zero point taken.
     *
     * DS-0637 rates the zero signal "< 0.4 %vol O2 (20 C)" - 1706 nA at Issue
     * 2's nominal 100 uA cell, 2218 nA at the top of the population. Either
     * way it is 8-100x every electronic offset in the chain. Folded into the
     * air point it becomes a SLOPE error across the whole low-O2 range;
     * subtracted here it is the offset it actually is. Compost control acts
     * near 5 %vol, where a slope error is worst.
     *
     * Appended at the end of the block rather than beside CAL_AIR_NA where it
     * belongs logically: the map is a published contract - AT+COMMAND frames
     * on the Dragino name literal addresses - so nothing already in it may be
     * renumbered to make room. */
    O2P_REG_CAL_ZERO_NA_HI  = 0x0046u,
    O2P_REG_CAL_ZERO_NA_LO  = 0x0047u,
};
#define O2P_REG_CONFIG_BASE  0x0030u
#define O2P_REG_CONFIG_COUNT 24u

/* ---- Heater test block: 0x0060, 2 registers, read/write, VOLATILE ----
 *
 * The bench override. It exists so the ring can be driven open-loop at a
 * chosen duty, at any humidity, without the dT clamp - which is the only way
 * to characterise a thermal plant that the RH loop was written to regulate
 * but that nobody has ever measured (heater_ctl.h says so in its own header).
 *
 * DELIBERATELY NOT IN THE CONFIG BLOCK, and therefore not in flash. A test
 * mode that survives a power cycle is a test mode that gets left on in a
 * potted probe two metres down a compost pile. Arming is lost on reset, on
 * brownout, and on every path that re-runs o2p_regmap_init(), and there is no
 * register write anywhere that can make it persistent.
 *
 * WHAT IT DOES NOT BYPASS, and this is the point of listing them: the TMP117
 * therm-mode cutoff (O2P_HB_SAFETY), a missing tip temperature
 * (O2P_HB_NO_TIP), the absolute tip limit at O2P_HEATER_TIP_LIMIT_C100
 * (O2P_HB_TIP_LIMIT), the rail fault, the runaway latch, the PA7 pin-integrity
 * assertion, and HEATER_MAX_DUTY - which still caps the commanded duty and
 * still disables the heater outright at zero. Override removes the reasons
 * the loop declines to CONTROL; it removes none of the reasons the hardware
 * declines to BURN.
 *
 * With TIP_LIMIT and its 5 K release left in place, an armed override is a
 * bang-bang thermostat between 75.00 and 80.00 C. That is not a limitation
 * worked around - for "drive the tip to 80 C" it is the whole mechanism.
 *
 * AT 0x0060, NOT at 0x0048 where the config block ends. 0x0050 is
 * O2P_REG_UPDATE_BASE (update.h) and 0x0080 is the update data window, so the
 * free ground between them is 0x0060-0x007F. Placing this block immediately
 * after the config block would also have put it one register-count bump away
 * from being read as configuration. */
enum {
    /* Write O2P_HEATER_TEST_MAGIC to arm, 0 to disarm. Reads back 1 or 0
     * rather than the magic: what a reader wants to know is whether the
     * override is live, and echoing a token invites a read-modify-write to
     * re-arm it by accident. */
    O2P_REG_HEATER_TEST_ARM  = 0x0060u,
    /* Open-loop duty while armed, 0.01 %. Clamped to HEATER_MAX_DUTY. */
    O2P_REG_HEATER_TEST_DUTY = 0x0061u,
};
#define O2P_REG_HTEST_BASE  0x0060u
#define O2P_REG_HTEST_COUNT 2u

/* Same reasoning as O2P_COMMIT_MAGIC: energising 1 W into the membrane must
 * not be one flipped bit away in a frame that happened to pass CRC. */
#define O2P_HEATER_TEST_MAGIC 0x8EA7u

/* Deliberate magics rather than "write 1". A flash cycle and a recalibration
 * are both destructive and both are one stray bit away in a noisy RS-485
 * frame that happened to pass CRC; requiring a 16-bit token makes an accident
 * implausible. This is the same economy the SGX and FDO2 datasheets demand of
 * their own limited flash-cycle budgets. */
#define O2P_COMMIT_MAGIC 0x5AC1u
#define O2P_CAL_MAGIC    0xCA11u

/* Bumped whenever the WIRE contract changes, which is the only thing a master
 * can act on: 0x0002 was the diagnostic block growing from 24 registers to 26,
 * and 0x0003 is 26 to 28 (CMD_RESULT, CAL_STATE) plus the config block
 * growing to 24 with the CAL_ZERO_NA pair.
 *
 * It was left at 0x0002 across that change, which made the register a liar by
 * its own stated rule and gave a master no way to tell a 28-register probe
 * from a 26-register one before reading it. Found by review 2026-09-08.
 *
 * 0x0004 adds the volatile heater test block at 0x0060 and turns the heater
 * on in the shipped build (O2P_HEATER_ENABLE=1). Both are wire-visible: the
 * new block answers where 0x0060 previously raised exception 02, and
 * HEATER_DUTY can now be nonzero, which on every earlier version it could not.
 *
 * For "which build is this", read BUILD_ID (0x0028/0x0029) - this number is
 * hand-maintained and says nothing about the binary. */
#define O2P_FW_VERSION 0x0004u  /* v0.4 - heater live, test block at 0x0060 */

/* Overridden by tools/pio_build_id.py on every target build. The default is
 * reached only by the host test build, and means "no stamp", never a commit. */
#ifndef O2P_BUILD_ID
#define O2P_BUILD_ID 0x00000000UL
#endif
#define O2P_BUILD_ID_UNSTAMPED 0x00000000UL
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
    /* 1 once a zero point has been TAKEN. Needed because 0 nA is a legitimate
     * measured zero as well as the never-measured default, and the two have
     * identical arithmetic (subtract nothing) but opposite meanings to an
     * operator deciding whether commissioning is finished. */
    uint8_t  cal_zero_taken;          /* 34 */
    uint8_t  reserved2[1];            /* 35 */
    /* APPENDED, deliberately. Placing it beside cal_air_na would move every
     * field after it and make the migration a re-layout instead of a
     * zero-fill; here every v5 offset is untouched and the only thing a v5
     * record lacks is this field, whose correct value for a probe that never
     * took a zero point is exactly the 0 it gets. */
    int32_t  cal_zero_na;             /* 36 */
} o2p_config_t;
/* The record wrapper in config_flash.h is a fixed 64 bytes and pads to it, so
 * growing this struct spends the record's RESERVED TAIL rather than the frame.
 *
 * The CRC does move - it sits immediately after the configuration, so it went
 * from byte 48 in v5 to byte 52 in v6. That is safe only because
 * config_migrate.c computes the CRC offset from the VERSION-SPECIFIC
 * configuration size, so a v5 record is never checked at the v6 offset. An
 * earlier version of this comment claimed the CRC did not move at all, which
 * would have made the version-specific length look like dead code to anyone
 * tidying up. Corrected after review, 2026-09-08. Pinned so a field added without checking the
 * arithmetic fails to compile instead of shifting every offset by two. */
_Static_assert(sizeof(o2p_config_t) == 40u, "config layout is 40 bytes");

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
    uint16_t we_buf_mv;
    uint16_t re_buf_mv;
    int16_t  cell_bias_mv;
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
    /* Set when ONE FC16 asked for both a calibration and a commit, or when a
     * COMMIT arrives while a calibration is still outstanding. The commit then
     * waits for the point to be taken instead of racing it - otherwise flash
     * stores the PRE-calibration image, the point lands in RAM only, and the
     * master has a successful write acknowledging both. */
    volatile bool commit_after_cal;
    volatile bool sht_pulse_requested;
    /* Heater bench override, 0x0050/0x0051. Volatile by construction: these
     * are the only two settable quantities in this struct with no home in
     * o2p_config_t, and they have none on purpose - see the block comment. */
    volatile bool heater_test_armed;
    volatile uint16_t heater_test_duty_x100;
    /* Packed CMD_RESULT, see O2P_REG_CMD_RESULT. One 16-bit word so a Modbus
     * reader never sees a half-updated pair. */
    volatile uint16_t cmd_result;

    /* The firmware updater, or NULL. It is reached through the register map
     * because that is where a Modbus master reaches everything - but it is
     * deliberately not PART of the register map: the update engine is shared
     * verbatim with the bootloader, which has no configuration, no snapshot
     * and no sampler. When this is NULL the update blocks answer exception 02
     * exactly as any other undefined address does. */
    o2p_update_t *upd;
} o2p_regmap_t;

void o2p_regmap_init(o2p_regmap_t *rm);

/* Record the outcome of a finished command. Separate setters rather than one
 * packed write, so a commit result can never clobber a calibration result
 * that is still PENDING. */
void o2p_regmap_set_cal_result(o2p_regmap_t *rm, uint8_t status);
void o2p_regmap_set_commit_result(o2p_regmap_t *rm, uint8_t status);

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
