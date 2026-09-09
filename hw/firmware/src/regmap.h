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

/* ---- Diagnostic block: 0x0010, O2P_REG_DIAG_COUNT registers, read-only ---- */
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
    /* LMP91000 die temperature, i16 0.01 C, 0x8000 invalid.
     *
     * This is the AFE's OWN silicon, and it is the only thing on the board
     * that reports it. T_DIE (0x0022) is the MCU, at the other end of the
     * PCB: on 2026-09-08, with the ring heater holding T_TIP at 78.00 C, the
     * MCU die sat at 49 C - a 29 K gradient across one board. So neither
     * T_TIP nor T_DIE is the AFE's temperature, and until this register
     * existed nothing measured it.
     *
     * Why it is worth a register. The published cell current is
     * (0.67*VREF - VOUT)/R_TIA with R_TIA a hardcoded 7000 (sampler_logic.h),
     * and SNAS506I specifies that resistor's ACCURACY (5 %) but publishes no
     * temperature coefficient for it and no gain-versus-temperature curve -
     * checked against Rev I, whose 35 figures contain neither. Everything
     * else in the chain is bounded and small: the ADS1119 contributes 2
     * ppm/K of gain drift MAX (SBAS925A), TcVOS_RW is 8 uV/K at the configured 24 % bias,
     * and VREF cancels because the internal zero and the ADC reference are
     * the same rail. R_TIA is the one uncharacterised term, and it drifts
     * with THIS temperature, not with T_TIP.
     *
     * So a tempco fitted against T_TIP silently contains the AFE's drift
     * scaled by however much of the tip's excursion the AFE actually saw.
     * That fraction is what this register measures. */
    O2P_REG_T_AFE           = 0x002Cu,
    /* CELL_CE_DRV in mV, u16, 0xFFFF invalid. The potentiostat's CONTROL
     * EFFORT, and the register that names which hardware fault you have.
     *
     * A1 drives the counter electrode until the reference electrode sits at
     * the commanded bias. The loop closes THROUGH THE CELL, so if the cell is
     * absent, high-impedance or on bad leads - or if A1 is dead, as it was on
     * 2026-09-04 - A1 has no feedback and CE rests against a rail while
     * TIACN/REFCN/MODECN still read back exactly as written. LMP_READBACK
     * cannot see it; CELL_BIAS_MV shows the symptom; this shows the cause.
     *
     * SNAS506I 6.5 characterises A1's drive only over 300 mV <= VCE <=
     * VS-300 mV, so outside O2P_HW_CE_COMPLIANCE_MIN/MAX_MV the amplifier is
     * not specified and the reading is a fault, not a measurement.
     *
     * NOT in the node's poll window, deliberately, and for the reason
     * CMD_RESULT and CAL_STATE are not: at 96 bytes that frame has 4 bytes of
     * DR3 headroom left, and this is a bench question answered by a laptop on
     * the bus in the same session that asks it. The FAULT reaches the radio;
     * the millivolts do not need to. */
    O2P_REG_CE_MV           = 0x002Du,
    /* Interlock bitmask from heater_ctl.h (O2P_HB_*), u16. Explains why
     * HEATER_DUTY is zero when the loop declines to control. 0xFFFF invalid. */
    O2P_REG_HEATER_BLOCK    = 0x002Eu,
    /* Duration in milliseconds of the last measurement cycle, u16. 0xFFFF invalid. */
    O2P_REG_SAMPLER_TIMING_MS = 0x002Fu,
};
#define O2P_REG_DIAG_BASE  0x0010u
#define O2P_REG_DIAG_COUNT 32u

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
/* An air point EXISTS but was taken without the cell bias being measured -
 * accepted on substitute evidence (see main.c's calibration gate). Published
 * so the constant is self-describing: a %vol derived from it is a real
 * measurement, but nothing proved the cell was at its commanded bias when the
 * point was taken. Not set when there is no air point at all; AIR_DEFAULT
 * already says that, and two bits for one condition read as two problems. */
#define O2P_CAL_STATE_BIAS_UNVERIFIED 0x0004u

#define O2P_CMD_RESULT_CAL(v)    ((uint8_t)((v) >> 8))
#define O2P_CMD_RESULT_COMMIT(v) ((uint8_t)((v) & 0xFFu))

/* ---- Config block: 0x0030, 27 registers, read/write, flash-backed ---- */
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
    /* Consent to AUTONOMOUS heating - the RH loop only. Write
     * O2P_HEATER_RH_CONSENT_MAGIC to permit it; any other value, zero
     * included, refuses. See o2p_config_t.heater_rh_consent for why this is
     * a separate field from HEATER_MAX_DUTY rather than a second meaning
     * loaded onto it. Never carried across a config migration. */
    O2P_REG_HEATER_RH_CONSENT = 0x0048u,

    /* ---- PERSISTENT TIP-TEMPERATURE SETPOINT, 0x0049 and 0x004A ----
     *
     * The autonomous temperature loop. Until now this firmware regulated
     * exactly one quantity - chamber RH - and the only way to hold a
     * TEMPERATURE was the volatile bench override at 0x0060, which needs an
     * operator to arm it and which every reset clears. That is correct for a
     * characterisation run and useless for anything that has to survive a
     * power cycle: a reflash at 14:21 on 2026-09-08 silently ended a bath
     * comparison mid-experiment, because the arm lives in RAM by design.
     *
     * These four registers are the flash-backed twin the override deliberately
     * does NOT have. They are a separate control MODE, not a second way to
     * spell the override, and they carry their own consent.
     *
     * Target tip temperature, i16 0.01 C. O2P_I16_INVALID means no target and
     * the mode is off - the same sentinel and the same bound as 0x0062, so an
     * operator who learned one learns both. */
    O2P_REG_TIP_SETPOINT      = 0x0049u,
    /* Consent to AUTONOMOUS TEMPERATURE heating. A third magic, and the
     * argument for it is the one already made for splitting TEST from RH: the
     * three authorise different things. RH consent permits a loop whose whole
     * purpose is to sit a few kelvin above ambient inside a 0-4 K envelope;
     * this permits holding an absolute temperature that may be tens of kelvin
     * above it, unattended, until someone writes the sentinel back. Reusing
     * O2P_HEATER_RH_CONSENT_MAGIC would let consent given for the mild loop
     * silently authorise the aggressive one. Never carried across a
     * migration. */
    O2P_REG_HEATER_TIP_CONSENT = 0x004Au,
    /* NO PERSISTENT GAIN PAIR, and the reason is a hard limit rather than a
     * judgement. The flash record is fixed at CONFIG_RECORD_SIZE = 64 bytes,
     * of which 14 are header and CRC, so o2p_config_t may not exceed 50 bytes
     * and only six were free. Setpoint and consent take four of them; a
     * flash-backed kp/ki pair would need four more.
     *
     * So BOTH tip loops share the volatile gains at 0x0063/0x0064, and a
     * reset restores the conservative defaults. That is the right thing to
     * lose: gains are tuning, and a probe coming back from a power cycle
     * resuming on saturate-early/integrate-slowly defaults is safer than one
     * resuming on somebody's aggressive bench tuning. What must survive a
     * reset is the TARGET and the AUTHORISATION to pursue it, and those do. */
};
#define O2P_REG_CONFIG_BASE  0x0030u
#define O2P_REG_CONFIG_COUNT 27u

/* ---- Heater test block: 0x0060, 5 registers, read/write, VOLATILE ----
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
    /* Duty while armed with no temperature target, 0.01 %. Clamped to the
     * configured duty maximum. */
    O2P_REG_HEATER_TEST_DUTY = 0x0061u,
    /* TIP TEMPERATURE SETPOINT, i16 0.01 C, O2P_I16_INVALID = none.
     *
     * Writing a real temperature here turns the override from open-loop duty
     * into a closed loop on tip temperature, which is the difference between
     * a plateau and a sawtooth. Without it the ring runs at TEST_DUTY until
     * the absolute clamp cuts it at 80.00 C and releases at 75.00 C: a mean
     * near 77.5 C with +/-2.5 K of ripple, produced by bouncing a PROTECTION
     * device off its limits. A clamp that fires every cycle in normal use has
     * stopped being a clamp.
     *
     * Bounded at O2P_HEATER_TEST_SP_MAX_C100, two kelvin below the clamp, so
     * the clamp stays the backstop it was written to be: if TIP_LIMIT fires
     * while a setpoint is in force, the loop has failed and that is worth
     * knowing, which it is not when the clamp IS the control mechanism. */
    O2P_REG_HEATER_TEST_TIP_SP = 0x0062u,
    /* Gains for the TIP loop only, 0.01 units. Volatile like the rest of the
     * block, and deliberately NOT the flash-backed HEATER_KP/HEATER_KI at
     * 0x0040/0x0041: those tune the humidity loop, whose error is in %RH and
     * whose gains would be meaningless here - and overwriting a probe's RH
     * tuning as a side effect of a bench test is not a trade anyone offered.
     *
     * Registers rather than constants because the plant is unmeasured, and
     * the entire reason this block exists is that reflashing a potted probe
     * to change a number is not a tuning loop. */
    O2P_REG_HEATER_TEST_KP   = 0x0063u,
    O2P_REG_HEATER_TEST_KI   = 0x0064u,
};
#define O2P_REG_HTEST_BASE  0x0060u
#define O2P_REG_HTEST_COUNT 5u

#ifndef O2P_DEBUG_ENABLE
#define O2P_DEBUG_ENABLE 1
#endif

#if O2P_DEBUG_ENABLE
/* ---- Memory peek block: 0x0065, 11 registers, read/write, VOLATILE ----
 *
 * The trigger is an FC16 write starting exactly at O2P_REG_PEEK_ADDR_HI, of
 * either 2 registers (address hi/lo; 4 words are read) or 3 registers (address
 * hi/lo plus a word count of 1..4). O2P_REG_PEEK_STATUS is therefore write-
 * as-count / read-as-status: the third register of a trigger write carries the
 * requested burst length, and the firmware overwrites it with the outcome.
 * Words beyond the requested count read back as 0xFFFFFFFF. */
enum {
    O2P_REG_PEEK_ADDR_HI       = 0x0065u,
    O2P_REG_PEEK_ADDR_LO       = 0x0066u,
    O2P_REG_PEEK_STATUS        = 0x0067u,   /* W: burst words 1..4; R: status */
    O2P_REG_PEEK_W0_HI         = 0x0068u,
    O2P_REG_PEEK_W0_LO         = 0x0069u,
    O2P_REG_PEEK_W1_HI         = 0x006Au,
    O2P_REG_PEEK_W1_LO         = 0x006Bu,
    O2P_REG_PEEK_W2_HI         = 0x006Cu,
    O2P_REG_PEEK_W2_LO         = 0x006Du,
    O2P_REG_PEEK_W3_HI         = 0x006Eu,
    O2P_REG_PEEK_W3_LO         = 0x006Fu,
};
#define O2P_REG_PEEK_BASE  0x0065u
#define O2P_REG_PEEK_COUNT 11u

enum {
    O2P_PEEK_NONE      = 0u,
    O2P_PEEK_OK        = 1u,
    O2P_PEEK_ERR_RANGE = 2u,
    O2P_PEEK_ERR_ALIGN = 3u,
};

/* ---- Sensor diagnostic mailbox: 0x0070, 7 registers, read/write, VOLATILE ---- */
enum {
    O2P_REG_DIAG_CMD         = 0x0070u,
    O2P_REG_DIAG_PARAM       = 0x0071u,
    O2P_REG_DIAG_STATUS      = 0x0072u,
    O2P_REG_DIAG_RDATA0      = 0x0073u,
    O2P_REG_DIAG_RDATA1      = 0x0074u,
    O2P_REG_DIAG_RDATA2      = 0x0075u,
    O2P_REG_DIAG_CRC_STATUS  = 0x0076u,
};
#define O2P_REG_DMBOX_BASE  0x0070u
#define O2P_REG_DMBOX_COUNT 7u

#define O2P_DIAG_MAGIC_MASK 0xFF00u
#define O2P_DIAG_MAGIC      0x5A00u

enum {
    O2P_DMBOX_STATUS_NONE        = 0u,
    O2P_DMBOX_STATUS_PENDING     = 1u,
    O2P_DMBOX_STATUS_OK          = 2u,
    O2P_DMBOX_STATUS_ERR_OPCODE  = 3u,
    O2P_DMBOX_STATUS_ERR_NACK    = 4u,
    O2P_DMBOX_STATUS_ERR_TIMEOUT = 5u,
    O2P_DMBOX_STATUS_ERR_BUSY    = 6u,
};

enum {
    O2P_OP_READ_LMP_REG    = 0x01u,
    O2P_OP_TRIM_LMP_TIACN  = 0x02u,
    O2P_OP_READ_ADS_STATUS = 0x03u,
    O2P_OP_READ_ADS_CONFIG = 0x04u,
    O2P_OP_READ_TMP_REG    = 0x05u,
    O2P_OP_READ_SHT_SERIAL = 0x06u,
    O2P_OP_READ_SHT_SAMPLE = 0x07u,
};

/* ---- Crash context retention: 0x0077, 9 registers, read/write, RETENTION ---- */
enum {
    O2P_REG_CRASH_REASON      = 0x0077u,
    O2P_REG_CRASH_PC_HI       = 0x0078u,
    O2P_REG_CRASH_PC_LO       = 0x0079u,
    O2P_REG_CRASH_LR_HI       = 0x007Au,
    O2P_REG_CRASH_LR_LO       = 0x007Bu,
    O2P_REG_CRASH_DETAIL_HI   = 0x007Cu,
    O2P_REG_CRASH_DETAIL_LO   = 0x007Du,
    O2P_REG_CRASH_BUILD_ID_HI = 0x007Eu,
    O2P_REG_CRASH_BUILD_ID_LO = 0x007Fu,
};
#define O2P_REG_CRASH_BASE  0x0077u
#define O2P_REG_CRASH_COUNT 9u

#define O2P_CRASH_MAGIC 0xC8A54001u

enum {
    O2P_CRASH_NONE      = 0u,
    O2P_CRASH_HARDFAULT = 1u,
    O2P_CRASH_ASSERT    = 2u,
    O2P_CRASH_IWDG      = 3u,
};
#endif /* O2P_DEBUG_ENABLE */

/* A setpoint must sit strictly below the absolute clamp, by enough that the
 * loop's own overshoot does not routinely reach it. Two kelvin, against a
 * clamp raised to 82.00 C on 2026-09-08 so that 80.00 C is commandable at
 * all - see O2P_HEATER_TIP_LIMIT_C100. */
#define O2P_HEATER_TEST_SP_MAX_C100 8000

/* Same reasoning as O2P_COMMIT_MAGIC: energising 1 W into the membrane must
 * not be one flipped bit away in a frame that happened to pass CRC. */
#define O2P_HEATER_TEST_MAGIC 0x8EA7u

/* Consent to autonomous (RH-loop) heating, register 0x0048. A distinct token
 * from O2P_HEATER_TEST_MAGIC on purpose: the two authorise different things -
 * attended bench driving versus unattended field driving - and a single magic
 * would let a habit formed at the bench grant the other by muscle memory. */
#define O2P_HEATER_RH_CONSENT_MAGIC 0x9C07u

/* Consent to autonomous TEMPERATURE heating, register 0x004A. Distinct from
 * both magics above for the reason given at O2P_REG_HEATER_TIP_CONSENT: this
 * one authorises holding an absolute tip temperature with nobody present,
 * which is a strictly larger permission than either of the others. */
#define O2P_HEATER_TIP_CONSENT_MAGIC 0x71C0u

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
 * 0x0005 grows that block from 2 registers to 5, adding the tip-temperature
 * setpoint and its two gains. Wire-visible for the same reason: 0x0062-0x0064
 * answered exception 02 under 0x0004.
 *
 * 0x0006 is O2_RAW (0x0001) no longer being blanked by SETTLING. A master
 * that saw the 0x8000 sentinel for the whole 900 s after every reset now gets
 * cell current throughout. The sentinel's MEANING is unchanged; its frequency
 * is not. A consumer that inferred "the probe reset" from the gap in that
 * channel must read SETTLE_S (0x0007) or the SETTLING fault bit instead -
 * both were already in every frame, and both stayed populated across exactly
 * the window the current went missing.
 *
 * 0x0007 grows the config block from 24 registers to 25 with
 * HEATER_RH_CONSENT at 0x0048, and makes autonomous heating refuse without
 * it. Wire-visible twice over: a new register answers where exception 02 used
 * to, and a probe whose stored HEATER_MAX_DUTY was nonzero now declines to
 * heat until consent is written.
 *
 * 0x000B adds HEATER_BLOCK (0x002E) and SAMPLER_TIMING_MS (0x002F) to the
 * diagnostic block, expanding it from 30 to 32 registers.
 *
 * 0x000C makes the peek trigger accept a third register carrying the burst
 * length (1..4 words). No register moves, but the wire behaviour changes in
 * both directions: a 3-register write to 0x0065 used to be exception 03 and is
 * now the documented form, and addresses that answered ERR_RANGE because four
 * words would not fit - the whole of the UID and the flash-size register - now
 * answer OK for a burst that does fit.
 *
 * For "which build is this", read BUILD_ID (0x0028/0x0029) - this number is
 * hand-maintained and says nothing about the binary. */
#define O2P_FW_VERSION 0x000Cu  /* v0.12 - peek trigger accepts an explicit 1..4 word burst count */

/* Overridden by tools/pio_build_id.py on every target build. The default is
 * reached only by the host test build, and means "no stamp", never a commit. */
#ifndef O2P_BUILD_ID
#define O2P_BUILD_ID 0x00000000UL
#endif
#define O2P_BUILD_ID_UNSTAMPED 0x00000000UL
#define O2P_BUILD_ID_FLAG_DIRTY (1u << 31)
#define O2P_BUILD_ID_FLAG_DEBUG (1u << 30)
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
    /* CONSENT TO AUTONOMOUS HEATING, register 0x0048. Layout version 7.
     *
     * Only O2P_HEATER_RH_CONSENT_MAGIC permits the RH loop to drive the ring;
     * anything else, zero included, raises O2P_HB_NO_CONSENT and the duty is
     * zero. It does NOT gate the bench override, which has its own magic, is
     * volatile, and is used with an operator present.
     *
     * WHY THIS IS NOT heater_max_duty_x100. Until 2026-09-08 the heater was
     * compiled out, so O2P_HB_NOT_COMPILED blocked every path regardless of
     * configuration and a stored duty maximum could not energise anything.
     * Turning the ring on removed that guarantee and left a nonzero stored
     * maximum sufficient, by itself, to start an unvalidated control loop on
     * a buried probe with nobody present - and every migration deliberately
     * carries that maximum forward. The duty maximum answers "how hard", which
     * is a tuning question; this answers "at all", which is a consent
     * question, and one field cannot be both. Found by review 2026-09-08.
     *
     * config_migrate.c NEVER carries it: an upgrade always lands with
     * autonomous heating off, whatever the old record said. */
    uint16_t heater_rh_consent;       /* 40 */
    /* PERSISTENT TIP-TEMPERATURE SETPOINT MODE, registers 0x0049..0x004A.
     * Layout version 8. Appended for the same reason versions 6 and 7 were:
     * every v7 offset above is untouched, so the migration is a zero-fill
     * rather than a re-layout.
     *
     * The correct value of tip_setpoint_c100 for a probe that has never been
     * given a target is exactly the sentinel, and the correct value of
     * heater_tip_consent for a probe upgraded from a record that could not
     * express consent is exactly zero - so both defaults fall out of the
     * zero-fill, EXCEPT that 0 is a legal temperature and would mean "hold
     * 0.00 C" rather than "off". config_migrate.c therefore writes the
     * sentinel explicitly; see the note there.
     *
     * NOTE THIS TAKES OVER v7's reserved3[2] AT OFFSET 42 rather than being
     * appended past it, because six bytes were all that remained. A v7 record
     * therefore has ZEROS where this field now lives, and zero is a legal
     * setpoint meaning "hold 0.00 C" - not "off". The migration must write the
     * sentinel over it explicitly; a plain prefix copy would silently arm a
     * temperature loop on every upgraded probe. */
    int16_t  tip_setpoint_c100;       /* 42 */
    /* Only O2P_HEATER_TIP_CONSENT_MAGIC permits the autonomous tip loop to
     * drive the ring. NEVER carried across a migration, exactly like
     * heater_rh_consent: an upgrade always lands with autonomous temperature
     * heating off, whatever the old record said. */
    uint16_t heater_tip_consent;      /* 44 */
    /* Explicit, not implicit. The struct aligns to 4 for cal_air_na/cal_zero_na,
     * so without this the compiler pads to 48 anyway and the next field appended
     * here would silently land on tail padding a previous version had left
     * uninitialised. Naming it keeps every byte of the record accounted for. */
    /* Was this probe's air point taken with the cell bias actually MEASURED?
     *
     * 0 = no. Takes over one byte of v8's reserved4[2] at offset 46, and the
     * polarity is chosen so that NO MIGRATION IS NEEDED and no layout version
     * bump either: an older record has zero here, zero reads as "not
     * verified", and that is the TRUE answer for every calibration this
     * firmware has ever stored. On the fabricated Rev A board AIN2/AIN3 are
     * rail monitors (hw_caps_rev_a.h), so any bias verdict that authorised a
     * past air point was computed from two power rails and never saw the cell.
     *
     * Compare tip_setpoint_c100 at offset 42, which took over v7's reserved3
     * with the OPPOSITE polarity - zero was a legal setpoint meaning "hold
     * 0.00 C", so that one needed an explicit migration to avoid arming a
     * heater. Getting this the safe way round is deliberate, not luck: an
     * upgraded probe must not claim evidence it does not have. */
    uint8_t  cal_bias_verified;       /* 46 */
    uint8_t  reserved5[1];            /* 47 */
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
_Static_assert(sizeof(o2p_config_t) == 48u, "config layout is 48 bytes");
/* The record is 64 bytes: 12 of header, the configuration, then a 2-byte
 * CRC. Exceeding this silently shrinks config_flash.h's reserved tail to
 * zero and then past it, so assert the headroom here where the struct is
 * edited rather than discovering it as a confusing error in another file. */
_Static_assert(sizeof(o2p_config_t) <= 50u,
               "config must leave room for the 12-byte header and 2-byte CRC "
               "inside CONFIG_RECORD_SIZE = 64");
/* v7 grew it 40 -> 44 (heater_rh_consent plus its padding), so the CRC moves
 * again, 52 -> 56, and the fixed 64-byte record's reserved tail shrinks from
 * 10 bytes to 6. Both still fit, and the version-specific size arithmetic in
 * config_migrate.c means a v6 record is still checked at the v6 offset. */

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
    int16_t  t_afe;
    uint16_t ce_mv;
    uint16_t faults_ever;
    uint16_t ads_fail_count;
    uint16_t we_buf_mv;
    uint16_t re_buf_mv;
    int16_t  cell_bias_mv;
    uint16_t heater_block;
    uint16_t sampler_timing_ms;
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
    /* True from the moment a serial change is accepted until it has been
     * proven or reverted (serial_probation.h). Read by the commit gate: what
     * is written to flash must never be a configuration the master has not
     * demonstrated it can still reach. */
    volatile bool serial_probation;
    /* A commit that arrived while the settings it would capture were still
     * unproven. Promoted when they are; failed when they are not. */
    volatile bool commit_after_serial;
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
    /* Bumped on every 0 -> 1 arm. The control loop compares it between cycles
     * to notice a disarm/re-arm pair that was served inside one 1 Hz interval
     * and would otherwise be invisible - see o2p_heater_state_t.last_session. */
    volatile uint8_t heater_test_session;
    volatile uint16_t heater_test_duty_x100;
    /* O2P_I16_INVALID means "no temperature target": the override then runs
     * open loop on heater_test_duty_x100. */
    volatile int16_t heater_test_tip_sp_c100;
    volatile uint16_t heater_test_kp_x100;
    volatile uint16_t heater_test_ki_x100;
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

#if O2P_DEBUG_ENABLE
    /* Memory peek mailbox */
    uint16_t peek_addr_hi;
    uint16_t peek_addr_lo;
    uint16_t peek_status;
    uint32_t peek_words[4];

    /* Sensor diagnostic mailbox */
    uint16_t diag_cmd;
    uint16_t diag_param;
    uint16_t diag_status;
    uint16_t diag_rdata0;
    uint16_t diag_rdata1;
    uint16_t diag_rdata2;
    uint16_t diag_crc_status;
    volatile bool diag_pending;

    /* Crash retention */
    uint16_t crash_reason;
    uint32_t crash_pc;
    uint32_t crash_lr;
    uint32_t crash_detail;
    uint32_t crash_build_id;
#endif /* O2P_DEBUG_ENABLE */
} o2p_regmap_t;

#if O2P_DEBUG_ENABLE
void o2p_regmap_load_crash_context(o2p_regmap_t *rm);
#else
static inline void o2p_regmap_load_crash_context(o2p_regmap_t *rm) { (void)rm; }
#endif

void o2p_regmap_init(o2p_regmap_t *rm);

/* Record the outcome of a finished command. Separate setters rather than one
 * packed write, so a commit result can never clobber a calibration result
 * that is still PENDING. */
void o2p_regmap_set_cal_result(o2p_regmap_t *rm, uint8_t status);
void o2p_regmap_set_commit_result(o2p_regmap_t *rm, uint8_t status);

/* Ask for the live config to be written to flash.
 *
 * The only way a commit is REQUESTED. (main.c raises commit_pending directly
 * in one place - promoting a request this function deferred, on the far side
 * of the gate - so this is the only entry, not the only assignment.)
 *
 * A commit taken while a serial
 * change is still on probation would persist settings that have not been shown
 * to work: the probation timer would then put the RAM config back and leave
 * flash holding the unreachable ones, so the probe would come up on them at
 * its very next reset - turning a self-healing mistake into a permanent one.
 * That is the exact failure the probation exists to prevent, arriving through
 * the back door. So the request waits instead, and main.c promotes or fails it
 * with the probation's outcome. */
void o2p_regmap_request_commit(o2p_regmap_t *rm);

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
