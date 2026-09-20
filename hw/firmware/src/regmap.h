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
#include <stddef.h>
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
    /* 60 s TRAILING MEAN of the applied duty since FW 0x0025 - it was the
     * last 1 Hz decision before that. Same u16 0.01 % format, so decoders,
     * ingest and Grafana read it unchanged. Mean over the seconds that exist
     * when uptime is under 60 s. The instantaneous duty is HEATER_DUTY_NOW
     * (0x0009). Definition: heater_ctl.h, O2P_DUTY_MEAN_WINDOW_S. */
    O2P_REG_HEATER_DUTY  = 0x0005u, /* u16  0.01 %, 60 s trailing mean      */
    O2P_REG_FAULTS       = 0x0006u, /* u16  bitfield, see faults.h          */
    O2P_REG_SETTLE_S     = 0x0007u, /* u16  seconds remaining, 0 = settled  */
};
#define O2P_REG_PRIMARY_BASE  0x0000u
#define O2P_REG_PRIMARY_COUNT 8u

/* ---- Heater-law block: 0x0008, 2 registers, read-only, FW 0x0018 ----
 *
 * HEATER_LAW: which control law produced HEATER_DUTY_NOW this cycle (low byte,
 * O2P_HEATER_LAW_* in heater_ctl.h) plus flags about it (high byte,
 * O2P_HEATER_LAWF_*). 0xFFFF before the heater has been stepped.
 *
 * Since FW 0x0027 bit 11 (DRY_IDLE) says the gradient floor's demand is being
 * withheld because the gas reads dry - duty zero with that bit set is the
 * designed energy-saving state, not a fault. It goes absent while the floor
 * pays its periodic 120 s debt, which is how a reader tells idling from
 * idling-and-paying-its-premium (O2P_HEATER_DRY_RH_X100).
 *
 * HEATER_DUTY_NOW (FW 0x0025): the duty the hardware layer applied at this
 * cycle's publish, u16 0.01 % - what HEATER_DUTY (0x0005) meant until
 * 0x0025, when that register became a 60 s trailing mean so sparse readers
 * stop aliasing a 1 Hz decision. 0xFFFF before the first cycle publishes.
 * WHY HERE: the diagnostic block is full to 0x002F, the primary block is the
 * node's poll contract, and this block was left room to grow for exactly
 * this (see the probation block note below). A read of 0x0008 count 1 is
 * byte-for-byte what it was; count 2 is exception 02 on older firmware, which
 * is how a master tells the two apart.
 *
 * WHY A NEW BLOCK. HEATER_BLOCK cannot answer "which law": its bit 15 is
 * identical for the RH and dew laws, and the annotations are omitted on the
 * refusing/blind path, so a bench tool read that absence as "a stored tip
 * setpoint is in command" twice on 2026-09-13 - the opposite of the truth.
 * The dew law's unreachable-margin fallback made it acute: a probe holding the
 * gradient floor because its margin is unreachable looks, on every existing
 * register, exactly like a probe with both laws satisfied. The u16 had no
 * free bit (heater_ctl.h, O2P_HB_IDLE), FAULTS has none (faults.h), and the
 * diagnostic block runs solid to 0x002F against the config block at 0x0030.
 *
 * WHY HERE. 0x0008-0x000F is the only gap next to the measurement registers;
 * the other gaps sit between debug and updater blocks. Deliberately a
 * SEPARATE block rather than PRIMARY_COUNT 8 -> 9: the primary block is what
 * the node polls and the LoRaWAN codec decodes, and growing it is a contract
 * change for every master. A separate block is purely additive - a read of
 * 0x0000 count 8 is byte-for-byte what it was. */
enum {
    O2P_REG_HEATER_LAW   = 0x0008u, /* u16  O2P_HEATER_LAW_* | _LAWF_*  0xFFFF invalid */
    O2P_REG_HEATER_DUTY_NOW = 0x0009u, /* u16 0.01 %, instantaneous  0xFFFF invalid */
};
#define O2P_REG_HLAW_BASE  0x0008u
#define O2P_REG_HLAW_COUNT 2u

/* ---- Probation block: 0x000C, 2 registers, FW 0x001D ----
 *
 * The two-way proof a serial-settings change needs before the probe keeps it
 * (serial_probation.h). When the new settings go live the probe publishes a
 * fresh nonce in PROBATION_NONCE; it confirms them only when the master writes
 * that nonce back to PROBATION_ACK at the new settings.
 *
 * WHY. Until 0x001D one frame ARRIVING at the new settings confirmed them. On
 * 2026-09-13 13:09 a retime to 115200 over the farmgw BLE keeper delivered the
 * master's confirmation read to probe 3 while the reply never came back; the
 * probe confirmed, the master moved its end back to 9600, and the probe
 * answered nothing until it was power-cycled.
 *
 * NONCE reads 0 when no probation is running. ACK is write-only in effect:
 * a write of the running nonce is accepted, anything else (or any write with
 * no probation running) is exception 03; it reads 1 while the proof is held,
 * which is how a master resolves an ACK whose reply was lost. Placed in the
 * 0x0009-0x000F gap, leaving 0x0009-0x000B for the heater-law block to grow
 * (0x0009 taken by HEATER_DUTY_NOW in FW 0x0025; 0x000A-0x000B remain). */
enum {
    O2P_REG_PROBATION_NONCE = 0x000Cu, /* u16 R  nonce, 0 = no probation      */
    O2P_REG_PROBATION_ACK   = 0x000Du, /* u16 W  echo it; reads 1 while held  */
};
#define O2P_REG_PROB_BASE  0x000Cu
#define O2P_REG_PROB_COUNT 2u

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
    O2P_REG_EXP_DATA     = 0x001Fu, /* 0xFFFF = no expansion sensor present; i16 0.01 C (TMP117 on ext I2C) */
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
     * BUILD_ID is: bit 31 the working tree was dirty at build time, bit 30
     * a debug build (O2P_BUILD_ID_FLAG_DEBUG: regmap.c sets it when
     * O2P_DEBUG_ENABLE=1 and clears it otherwise, since faf52d8 on
     * 2026-09-09 - an older image reads 0 there whatever it was built as),
     * bits 29..28 reserved, bits 27..0 the 7-hex-digit prefix of the commit
     * the image was built from. Stamped by tools/pio_build_id.py, which FAILS the
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
     * HEATER_DUTY is zero when the loop declines to control. 0xFFFF invalid.
     * Since FW_VERSION 0x0010 bits 14 (IDLE) and 15 (TIP_DISARMED) are
     * ANNOTATIONS, not refusals: they name the idle states a refusal-only
     * word cannot express, and they never suppress duty. */
    O2P_REG_HEATER_BLOCK    = 0x002Eu,
    /* Duration in milliseconds of the last measurement cycle, u16. 0xFFFF invalid. */
    O2P_REG_SAMPLER_TIMING_MS = 0x002Fu,
};
#define O2P_REG_DIAG_BASE  0x0010u
#define O2P_REG_DIAG_COUNT 32u
#define O2P_REG_T_EXT      O2P_REG_EXP_DATA

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
    O2P_REG_TEMPCO_PPM_K    = 0x003Au, /* i16 ppm/K RESIDUAL on top of the (T/T_cal)^0.75 cell law (FW 0x001E); 0 = the law alone */
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
     * loaded onto it. Never carried across a config migration. Fresh
     * configs ship with it granted (regmap.c defaults, 2026-09-10): a probe
     * must be able to heat itself against condensation when no channel can
     * reach it; refusing remains a single write of zero. */
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

    /* VIN DIVIDER RATIO, u16 x 1000. 0 = the generated netlist divider
     * (hw_caps_rev_*.h). 2000..20000 = VIN_MON_MV (0x0012) is the measured
     * tap voltage times this / 1000, on either revision. Anything else is
     * refused. Flash-backed like the rest of the block, so it takes a COMMIT.
     *
     * A PER-BOARD FACT, not tuning. Probe 3 is a Rev A board whose netlist
     * says R26/R27 = 130k/20k (x7.5), and it carries 82k/10k (x9.2): Fab
     * metered 13.11 V at the probe's input terminals while 0x0012 published
     * 10710 mV (2026-09-11), a ratio of 1.224 against the 9.2/7.5 = 1.227 the
     * fitted parts predict. The generated header describes the DESIGN and must
     * go on doing so; what one board actually carries belongs in that board's
     * flash (Fab: "this calibration constants belongs in the stm non-volatile
     * storage").
     *
     * The window is x2..x20. The ratios in play are x7.5, x9.2 and Rev B's
     * x10.1; a dropped digit (920) is refused, and one digit too many does not
     * fit a u16. Storage, and why this needed no layout bump:
     * o2p_cfg_vin_div_x1000(). */
    O2P_REG_VIN_DIV_X1000     = 0x004Bu,
};
#define O2P_REG_CONFIG_BASE  0x0030u
#define O2P_REG_CONFIG_COUNT 28u

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
 * (O2P_HB_TIP_LIMIT), the runaway latch, the PA7 pin-integrity
 * assertion, and HEATER_MAX_DUTY - which still caps the commanded duty and
 * still disables the heater outright at zero. (CORRECTED 2026-09-11: the
 * rail fault is NO LONGER on this list, by Fab's order - blind mode already
 * heated through the same fault, and the heater is <1 W; O2P_HB_SUPPLY is
 * now an annotation everywhere, never a veto.) Override removes the reasons
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
    /* ADC health, read-only, rebuilt every cycle. P3 and P4 of
     * docs/2026-09-12-revb-proposals-from-the-afe-failure.md.
     *
     * The 2026-09-12 incident was invisible for fourteen hours because the
     * firmware had exactly two states for the reference: measured, or
     * everything suppressed. This register is the missing third thing - it
     * says WHICH degraded mode is in force, so a fallback can never be silent.
     *
     * bit 0  VREF sense tap outside its band this cycle
     * bit 1  internal-reference FALLBACK engaged automatically (P3)
     * bit 2  internal-reference override forced by hand (diag opcode 9)
     * bit 3  stuck mux suspected: two DIFFERENT channels returned bit-identical
     *        accumulator codes (P4). AIN0's fault returned the previous
     *        channel's sample, and nothing noticed for fourteen hours.
     * bit 4  offset self-check outside its band (P4). ADS1119 MUX=111 shorts
     *        AINP/AINN to AVDD/2 (SBAS925A Table 10), so it must read ~0.
     * bits 15..8  |offset self-check| in LSB, saturating at 255 - the evidence
     *        behind bit 4 rather than just its verdict
     */
    O2P_REG_ADC_HEALTH       = 0x0050u,

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
    /* FW_VERSION 0x000F. An SRAM burst this part cannot read safely: the
     * RAM_PARITY_CHECK option bit is ENABLED (FLASH_OPTR bit 22 reads 0; RM0444
     * Rev 6, 3.7.8, p. 102: "0: SRAM parity check enable") and the burst is not
     * wholly inside what startup wrote, .data and .bss. RM0444 2.3, p. 67:
     * parity bits are "computed and stored when writing into the SRAM" and
     * "checked when reading. If one bit fails, an NMI is generated", with a
     * bus error and so a HardFault alongside - and never-written SRAM is where
     * a parity bit fails. Nothing was dereferenced. Not returned while the bit
     * reads 1, which is the factory value (RM0444 Table 17, p. 83). The rule
     * and its limits are at peek_check() in regmap.c. */
    O2P_PEEK_ERR_PARITY = 4u,
};

/* ---- Wide peek block: 0x0100, 65 registers, read/write, VOLATILE ----
 *
 * The 4-word mailbox above costs a trigger and a read per 16 bytes, so a
 * 68-byte snapshot struct took five round trips - and, worse, five separate
 * moments: the sampler publishes between any two of them, and the dump that
 * came back was a struct that never existed. This block takes the whole burst
 * in ONE trigger and holds it, so it comes back consistent however many reads
 * a small transport needs to carry it home.
 *
 * TRIGGER: exactly one FC16 of exactly 3 registers at PEEKW_ADDR_HI -
 * [addr_hi, addr_lo, words]. No 2-register form, unlike 0x0065: there is no
 * legacy master to keep working, and a default length is a length the
 * firmware did not get to check. Every other write that touches the block,
 * and a word count outside 1..O2P_PEEKW_WORDS_MAX, is exception 03 and
 * changes NOTHING - address, count, status, sequence and words all still
 * describe the previous trigger.
 *
 * A well-formed trigger always replaces the result, with OK or with the
 * reason it could not be served (ERR_ALIGN, ERR_RANGE, the same codes and the
 * same region rules as 0x0065). Words the trigger did not fill read 0xFFFF,
 * including every word of a refused burst.
 *
 * SEQ advances on every executed trigger, skipping 0 on wrap so 0 keeps
 * meaning "never triggered". It is what lets a reader that needs several
 * FC03s prove they all came from one snapshot: read it with the first chunk
 * and again after the last, and if it moved, somebody else peeked in between.
 * The echo of ADDR and WORDS is what lets a reader prove the snapshot is the
 * one it asked for.
 *
 * AT 0x0100, NOT IN 0x0065..0x007F. That window is full (peek, sensor
 * diagnostics, crash context) and 0x0080..0x00FA is the update data window
 * (update.h). 0x00FB..0x00FF is left empty as a guard: a mistyped FC16 that
 * runs off the end of an update block must land in nothing rather than in a
 * trigger. Nothing else answers at 0x01xx - not this map, not update.c, and
 * not the bootloader, which routes only the two update blocks.
 *
 * WHY 30 WORDS: see O2P_PEEKW_WORDS_MAX. */
enum {
    O2P_REG_PEEKW_ADDR_HI = 0x0100u,  /* W: target [31:16]; R: address held */
    O2P_REG_PEEKW_ADDR_LO = 0x0101u,  /* W: target [15:0]                    */
    O2P_REG_PEEKW_WORDS   = 0x0102u,  /* W: burst 1..30; R: words requested   */
    O2P_REG_PEEKW_STATUS  = 0x0103u,  /* RO: O2P_PEEK_*                        */
    O2P_REG_PEEKW_SEQ     = 0x0104u,  /* RO: executed triggers, 0 = never      */
    O2P_REG_PEEKW_DATA    = 0x0105u,  /* RO: word 0 hi, word 0 lo, word 1 hi.. */
};
#define O2P_REG_PEEKW_BASE  0x0100u
#define O2P_REG_PEEKW_COUNT 65u
#define O2P_PEEKW_HEADER    5u

/* The ceiling on one burst, in 32-bit words.
 *
 * 30 words = 120 bytes, and the whole block - 5 header registers plus 60 data
 * registers - is one FC03 whose reply is 5 + 2*65 = 135 bytes. That is chosen
 * against the transports that carry this to a probe, not against the Modbus
 * maximum. Largest reply ADU per path, read from the code 2026-09-10 (not
 * measured on a cable):
 *
 *     USB-RS485 dongle, SWD bridge mailbox, node USB serial relay   255
 *     node LoRaWAN relay, reply as an uplink at DR4/DR5             227
 *                                         at DR3                    100
 *                                         at DR0-DR2                 36
 *     Dragino RS485-LS A8 (manual's 46-byte uplink data; unverified) 46
 *
 * The radio rows are RadioLib 7.7.1's EU868 payloadLenMax (242/115/51) less
 * 15 bytes. The node uplinks the reply ADU raw, and getMaxPayloadLen()
 * subtracts whatever FOpts the MAC layer has pending - up to 15 bytes
 * (RADIOLIB_LORAWAN_FHDR_FOPTS_MAX_LEN) - so 242 holds only while nothing is
 * pending, and a reply over the live limit is dropped for good
 * (node-prototype main.cpp, PACKET_TOO_LONG). A master cannot see FOpts, so
 * the ceiling it plans against is the one that holds when they are full.
 *
 *   - It fits ONE read on every wired path and on the radio at DR4/DR5. A
 *     60-word ceiling (the most a 125-register FC03 can hold with this header,
 *     a 255-byte reply) would be one read on the wired paths only, and the
 *     radio drops an oversized reply rather than truncating it.
 *   - It holds every struct this firmware has a reason to dump except g_rm
 *     itself: o2p_snapshot_t (68 bytes), o2p_config_t (48), o2p_update_t.
 *   - The copy runs with interrupts masked and USART1 has no FIFO enabled, so
 *     the masked window must stay well inside one character time at the
 *     fastest rate offered: 95 us at 115200 8E1. 30 words is about 32 us by
 *     the disassembly (estimated, not measured); 60 would be about 64 us, two
 *     thirds of a character. See peek_copy() in regmap.c for the arithmetic.
 *   - It costs 120 bytes of the 36 KiB SRAM, once.
 *
 * Transports narrower than 135 bytes read the same snapshot in pieces, guarded
 * by SEQ. Raising this means re-deriving all four points, not editing a
 * number. */
#define O2P_PEEKW_WORDS_MAX 30u
_Static_assert(O2P_REG_PEEKW_COUNT == O2P_PEEKW_HEADER + 2u * O2P_PEEKW_WORDS_MAX,
               "the wide peek block is its header plus two registers per word");
_Static_assert(O2P_REG_PEEKW_DATA == O2P_REG_PEEKW_BASE + O2P_PEEKW_HEADER,
               "the data registers start right after the header");
_Static_assert(O2P_REG_PEEKW_BASE >= O2P_REG_UPDDATA_BASE + O2P_REG_UPDDATA_COUNT,
               "the wide peek block must not overlap the update data window");

/* ---- Arbitrary code execution mailbox: 0x0150, read/write, VOLATILE ---- */
enum {
    O2P_REG_EXEC_CMD         = 0x0150u, /* W: 0x5A01 = RUN, 0x5A00 = ABORT; R: held cmd */
    O2P_REG_EXEC_LEN         = 0x0151u, /* W/R: byte length of code (2..128, even)       */
    O2P_REG_EXEC_PARAM_HI    = 0x0152u, /* W/R: function argument R0 [31:16]             */
    O2P_REG_EXEC_PARAM_LO    = 0x0153u, /* W/R: function argument R0 [15:0]              */
    O2P_REG_EXEC_TIMEOUT_MS  = 0x0154u, /* W/R: execution timeout in ms (0=50, max 1000) */
    O2P_REG_EXEC_STATUS      = 0x0155u, /* RO: status (NONE, PENDING, OK, FAULT, etc.)  */
    O2P_REG_EXEC_RESULT_HI   = 0x0156u, /* RO: return value [31:16]                      */
    O2P_REG_EXEC_RESULT_LO   = 0x0157u, /* RO: return value [15:0]                       */
    O2P_REG_EXEC_CODE_START  = 0x0158u, /* W/R: code payload registers                   */
};
#define O2P_REG_EXEC_BASE        0x0150u
#define O2P_REG_EXEC_HDR_COUNT   8u
#define O2P_REG_EXEC_CODE_BASE   0x0158u
#define O2P_REG_EXEC_CODE_COUNT  64u
#define O2P_REG_EXEC_COUNT       72u

_Static_assert(O2P_REG_EXEC_COUNT == O2P_REG_EXEC_HDR_COUNT + O2P_REG_EXEC_CODE_COUNT,
               "exec count is header count plus code count");

/* ---- Memory poke mailbox: 0x0198, 12 registers, read/write, VOLATILE ----
 * (FW_VERSION 0x0012, 2026-09-11) The WRITE counterpart of the peek at
 * 0x0065, for the bench state a read cannot fix: Fab's order "the equivalent
 * write command of the peek", after a lost TMP117 threshold pair could only
 * be repaired by an MCU reset because no runtime path could write memory.
 *
 * The trigger is ONE FC16 starting exactly at O2P_REG_POKE_ADDR_HI, of
 * 3 + 2*words registers: [addr_hi, addr_lo, words, w0_hi, w0_lo, ...].
 * `words` is 1..4, so the accepted counts are exactly 5, 7, 9 and 11 - the
 * payload travels in the trigger frame, so (unlike the peek, whose data
 * registers are OUTPUT) the payload registers sit contiguously behind the
 * header and STATUS is the read-only tail. Every other write touching the
 * block is exception 03 and changes NOTHING - the same shape-then-act
 * contract as the wide peek at regmap.h's 0x0100 entry.
 *
 * WHAT IT MAY WRITE: .data/.bss only. The rules and the reasoning are at
 * poke_check() in regmap.c; in short, the poke admits exactly the span the
 * peek admits under the parity gate, so anything poked is peekable back for
 * verification. Flash, peripherals (SCB AIRCR included), the UID, SHARED
 * and the stack/heap-gap are all ERR_RANGE, deliberately. */
enum {
    O2P_REG_POKE_ADDR_HI       = 0x0198u,  /* W: target [31:16]; R: held      */
    O2P_REG_POKE_ADDR_LO       = 0x0199u,  /* W: target [15:0]; R: held       */
    O2P_REG_POKE_WORDS         = 0x019Au,  /* W: 1..4; R: words last poked    */
    O2P_REG_POKE_W0_HI         = 0x019Bu,  /* W: payload; R: payload held     */
    O2P_REG_POKE_W0_LO         = 0x019Cu,
    O2P_REG_POKE_W1_HI         = 0x019Du,
    O2P_REG_POKE_W1_LO         = 0x019Eu,
    O2P_REG_POKE_W2_HI         = 0x019Fu,
    O2P_REG_POKE_W2_LO         = 0x01A0u,
    O2P_REG_POKE_W3_HI         = 0x01A1u,
    O2P_REG_POKE_W3_LO         = 0x01A2u,
    O2P_REG_POKE_STATUS        = 0x01A3u,  /* RO: O2P_POKE_*                  */
};
#define O2P_REG_POKE_BASE  0x0198u
#define O2P_REG_POKE_COUNT 12u

/* The poke's status vocabulary deliberately mirrors O2P_PEEK_*. There is no
 * ERR_PARITY: RM0444 2.3 (p. 67) computes and stores the parity bit "when
 * writing into the SRAM", so a store cannot hit the read-side NMI that a
 * never-written word can - the span gate below is policy, not parity. */
enum {
    O2P_POKE_NONE      = 0u,
    O2P_POKE_OK        = 1u,
    O2P_POKE_ERR_RANGE = 2u,
    O2P_POKE_ERR_ALIGN = 3u,
};

/* ---- Wide poke block: 0x01B0, 65 registers, read/write, VOLATILE ----
 *
 * The poke counterpart of the wide peek at 0x0100, for the same reason that
 * block exists: 4 words per round trip does not scale to patching a struct.
 * One FC16 of 3 + 2*words registers at O2P_REG_POKEW_ADDR_HI -
 * [addr_hi, addr_lo, words, payload...] - writes the whole burst in one
 * trigger, `words` 1..O2P_PEEKW_WORDS_MAX, so accepted counts run 5..63,
 * inside the 123-register FC16 ceiling (modbus_pdu.c:73).
 *
 * 0x01A4..0x01AF is left empty as a guard between this block and the poke
 * mailbox above, on the same convention as 0x00FB..0x00FF (a malformed FC16
 * that runs off the end of a block lands in nothing).
 *
 * LAYOUT DEVIATION FROM 0x0100, on purpose: the wide peek holds its data
 * after STATUS and SEQ because its data is output a master reads back;
 * this block's data is INPUT, and it must be contiguous with the trigger
 * header for one-frame delivery. STATUS and SEQ are the read-only tail. */
enum {
    O2P_REG_POKEW_ADDR_HI = 0x01B0u,  /* W: target [31:16]; R: address held */
    O2P_REG_POKEW_ADDR_LO = 0x01B1u,  /* W: target [15:0]                   */
    O2P_REG_POKEW_WORDS   = 0x01B2u,  /* W: burst 1..30; R: words requested */
    O2P_REG_POKEW_DATA    = 0x01B3u,  /* W: word 0 hi, word 0 lo, ...; R: held */
    O2P_REG_POKEW_STATUS  = 0x01EFu,  /* RO: O2P_POKE_*                     */
    O2P_REG_POKEW_SEQ     = 0x01F0u,  /* RO: executed triggers, 0 = never   */
};
#define O2P_REG_POKEW_BASE  0x01B0u
#define O2P_REG_POKEW_HEADER 3u
#define O2P_REG_POKEW_COUNT 65u

_Static_assert(O2P_REG_POKE_BASE >= O2P_REG_EXEC_BASE + O2P_REG_EXEC_COUNT,
               "the poke mailbox must not overlap the exec block");
_Static_assert(O2P_REG_POKEW_BASE >= O2P_REG_POKE_BASE + O2P_REG_POKE_COUNT + 12u,
               "the wide poke block must sit beyond the poke mailbox and its guard");
_Static_assert(O2P_REG_POKEW_COUNT == O2P_REG_POKEW_HEADER + 2u * O2P_PEEKW_WORDS_MAX + 2u,
               "wide poke is its header plus two registers per word plus STATUS and SEQ");
_Static_assert(O2P_REG_POKEW_STATUS == O2P_REG_POKEW_BASE + O2P_REG_POKEW_HEADER +
               2u * O2P_PEEKW_WORDS_MAX,
               "STATUS and SEQ are the tail after the payload registers");

#define O2P_EXEC_MAGIC_MASK      0xFF00u
#define O2P_EXEC_MAGIC           0x5A00u
#define O2P_EXEC_OP_ABORT        0x00u
#define O2P_EXEC_OP_RUN          0x01u

enum {
    O2P_EXEC_STATUS_NONE        = 0u,
    O2P_EXEC_STATUS_PENDING     = 1u,
    O2P_EXEC_STATUS_OK          = 2u,
    O2P_EXEC_STATUS_ERR_OPCODE  = 3u,
    O2P_EXEC_STATUS_ERR_LEN     = 4u,
    O2P_EXEC_STATUS_FAULT       = 5u,
    O2P_EXEC_STATUS_TIMEOUT     = 6u,
};

_Static_assert(O2P_REG_EXEC_BASE >= O2P_REG_PEEKW_BASE + O2P_REG_PEEKW_COUNT,
               "the exec block must not overlap the wide peek block");

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
    /* NO LONGER PUBLISHED since FW_VERSION 0x000F. Up to 0x000E a write that
     * arrived while an I2C opcode was queued was refused by writing this into
     * DIAG_STATUS - the queued command's own status - so the master that had
     * queued it read ERR_BUSY, a status its command never produced, and a
     * reader that takes any non-PENDING status as final stopped there. The
     * refusal is now exception 06 (O2P_MB_EX_DEVICE_BUSY) and writes nothing.
     * The value stays reserved so a reader of an older probe can still name
     * it. */
    O2P_DMBOX_STATUS_ERR_BUSY    = 6u,
    /* OP_READ_GPIO only, FW_VERSION 0x000E. Distinct codes rather than
     * ERR_NACK/ERR_TIMEOUT, which mean something specific about an I2C part:
     * a reader that saw ERR_NACK for an unclocked port would go looking for a
     * dead sensor. NOT_SAMPLED is not an ERR_ because its configuration data
     * is real - only the level is absent. See gpio_diag.h. */
    O2P_DMBOX_STATUS_GPIO_NOT_SAMPLED   = 7u,
    O2P_DMBOX_STATUS_ERR_GPIO_UNCLOCKED = 8u,
    O2P_DMBOX_STATUS_ERR_GPIO_NO_PIN    = 9u,
};

enum {
    O2P_OP_READ_LMP_REG    = 0x01u,
    O2P_OP_TRIM_LMP_TIACN  = 0x02u,
    O2P_OP_READ_ADS_STATUS = 0x03u,
    O2P_OP_READ_ADS_CONFIG = 0x04u,
    /* TMP117 register read. PARAM = (dev << 8) | reg, where dev 0 is on-board
     * tip (0x49) and dev 1 is ext I2C (0x4A/0x4B). */
    O2P_OP_READ_TMP_REG    = 0x05u,
    O2P_OP_READ_SHT_SERIAL = 0x06u,
    O2P_OP_READ_SHT_SAMPLE = 0x07u,
    /* One MCU pin's mode, pull, type, AF, latch and level, plus its port's
     * IDR/ODR. Read-only; served in the write, not deferred. PARAM = port << 8
     * | pin. Encoding and packing: gpio_diag.h. */
    O2P_OP_READ_GPIO       = 0x08u,
    /* ADS1119 reference override, FW_VERSION 0x0015 (Fab 2026-09-11, "let it
     * use the internal ref for all channels now, for debugging. the external
     * ref is down"). PARAM 0 = the normal per-channel references, 1 = EVERY
     * conversion on the internal 2.048 V reference and scaled by it. VOLATILE:
     * a reset clears it. Served in the write like OP_READ_GPIO; RDATA0 echoes
     * the value now in force. The flag is o2p_regmap_t.ads_internal_ref, a
     * uint32_t in .bss, so the poke mailbox reaches it too. main.c latches it
     * once per cycle - see ads_ext_scale_mv(). */
    O2P_OP_ADS_INTERNAL_REF = 0x09u,
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
 * clamp raised to 92.00 C on 2026-09-19 so that 90.00 C is commandable at
 * all - see O2P_HEATER_TIP_LIMIT_C100. (Was 80.00 against an 82.00 clamp,
 * itself raised from 80.00 on 2026-09-08 for the same reason: the stated
 * experiment must be commandable, or the clamp is the control mechanism.) */
#define O2P_HEATER_TEST_SP_MAX_C100 9000

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
 * 0x000D adds the wide peek block at 0x0100 (65 registers: a 3-register FC16
 * trigger of address and 1..30 words, then one FC03 of up to 60 data
 * registers). Wire-visible in both directions, on a debug build only:
 * 0x0100..0x0140 answered exception 02 to every read and write and now
 * answers them, with exception 03 for any write that is not exactly the
 * trigger. Nothing that answered under 0x000C changed: 0x0065..0x006F keep
 * their layout, trigger forms and status codes. That mailbox now copies its
 * words with interrupts masked too, which no master can tell from the wire.
 * A nodebug build reports the same 0x000D and still answers exception 02 at
 * 0x0100, exactly as it does at 0x0065 - so "FW_VERSION >= 0x000D" means the
 * block MAY exist, and BUILD_ID bit 30 or the exception is what says it does.
 *
 * 0x000E adds OP_READ_GPIO (0x08) to the diagnostic mailbox at 0x0070, and
 * three DIAG_STATUS codes with it: 7 GPIO_NOT_SAMPLED (analog-mode pin, config
 * reported, no level), 8 ERR_GPIO_UNCLOCKED (port clock off, nothing loaded),
 * 9 ERR_GPIO_NO_PIN (no such bonded pin, nothing loaded). Wire-visible: DIAG_CMD
 * 0x5A08 used to be exception 03 with status ERR_OPCODE and is now accepted,
 * and a master decoding DIAG_STATUS must know 7..9. For this opcode only,
 * DIAG_CRC_STATUS carries the port's analog-pin mask instead of a CRC mask.
 * It is served inside the write, so its status is never PENDING. No register
 * moved and opcodes 0x01..0x07 are unchanged. Debug builds only; a nodebug
 * build reports 0x000E and still answers exception 02 at 0x0070.
 *
 * 0x000F changes two refusals, both on debug builds only, and adds nothing.
 * (1) THE DIAGNOSTIC MAILBOX'S BUSY REFUSAL. A well-shaped write to 0x0070
 * while an I2C opcode is queued used to be exception 03 AND set DIAG_STATUS
 * to 6 ERR_BUSY, overwriting the queued command's PENDING. It is now
 * exception 06 (SERVER DEVICE BUSY) and writes nothing: the master that was
 * refused learns it from the exception, and the master polling the queued
 * command keeps seeing PENDING until its real result. DIAG_STATUS 6 is never
 * published any more. A malformed write (wrong offset or length) is still
 * exception 03; while busy it used to write ERR_BUSY as well, and now writes
 * nothing. A bad magic or unknown opcode while busy is now exception 06 with
 * nothing written, where it used to be 03 plus ERR_BUSY; while idle it is
 * unchanged (03 and ERR_OPCODE). A master that treated any exception as
 * "refused" is unaffected; one that matched on 03 to detect busy must match
 * 06. (2) THE SRAM PARITY GATE. Both
 * peek blocks answer status 4 ERR_PARITY for an SRAM burst outside .data and
 * .bss when the RAM_PARITY_CHECK option bit is enabled. With the bit at its
 * factory value (disabled), every peek answers exactly as under 0x000E.
 * (3) THE FLASH PEEK REGION SHRINKS to the loader and run slot,
 * 0x08000000..0x08010FFC (was the whole 128 KiB to 0x0801FFFC). A peek of the
 * staging slot, the boot descriptor or the config pages now answers ERR_RANGE.
 * Independent review N4: those three are the flash areas a power loss can tear,
 * and reading a torn doubleword raises an ECC NMI that the default handler does
 * not survive (regmap.c, peek_region_last; PLAN-MODBUS-DEBUG.md 3.6).
 * (4) THE SNAPSHOT COPY IS OVERLAP-SAFE. When a peek names the SRAM the copy
 * writes into (g_rm's own snapshot buffer), the words used to come back
 * corrupt with STATUS still OK; the copy now runs in the memmove-safe
 * direction (review N1). No wire FORMAT changes for (3) or (4) - the same
 * status codes on the same registers - only which targets are refused and
 * whether an overlapping SRAM peek is trustworthy. All four points folded into
 * this one 0x000F entry because 0x000F was not yet committed at the time.
 *
 * 0x0010 is the compost-readiness image (2026-09-10, the condensation
 * emergency). Wire-visible changes, on every build:
 * (1) A FRESH CONFIG SHIPS HEATER_RH_CONSENT GRANTED: 0x0048 reads 0x9C07
 * out of the box, so a probe that has never been configured can run its
 * RH loop the moment max_duty (0x0035) is raised off its 0 default. The
 * default was 0 since the register existed; a master that treats "fresh ==
 * refused" as an invariant must read the register instead. Migrations
 * still land on 0 for EVERY source version (v4/v5 state it explicitly
 * now), and writing 0 still withdraws.
 * (2) HEATER_BLOCK (0x002E) gains the word's last two bits, both
 * annotations rather than refusals: 14 IDLE (a loop is in command with no
 * demand - duty 0 is the answer, not a fault) and 15 TIP_DISARMED (the
 * stored tip setpoint is at the 0x8000 sentinel, so the RH loop is the
 * configured law). Neither suppresses duty, and fault bit 15
 * (HEATER_DISABLED) no longer fires for them alone.
 * (3) THE STALENESS CUT moves to 2 s (was 5) so it always precedes the
 * IWDG's fastest bound, and when it fires HEATER_BLOCK gains bit 11 STALE
 * - which the contract has named since the beginning and which nothing
 * could raise until now.
 * (4) TIP GLITCH REJECTION: a T_TIP step the thermal mass cannot make in
 * one 1 Hz cycle is discarded for that cycle (tip publishes invalid, the
 * loop sees NO_TIP), re-syncing to the new value after ten consecutive
 * rejections so a genuinely moved or broken sensor is not locked out
 * forever. T_TIP no longer steps 16 K in a second because one I2C word
 * said so.
 * Behavioural but not wire-contractual: VREF re-entering the trim band
 * after being outside it now restarts the cell settling window at
 * recovery, because the commanded bias (0.67 x VREF) rode the whole
 * excursion.
 *
 * For "which build is this", read BUILD_ID (0x0028/0x0029) - this number is
 * hand-maintained and says nothing about the binary. */
#define O2P_FW_VERSION 0x002Au  /* v0.41 - the dry-air idle gate gains a PILE LOCKOUT on absolute cell temperature (Fab 2026-09-20: "will the heater restore its old behaviour in the pile?", then "proceed"). MEASURED ANSWER, from probe 3's own 24.2 h burial of 2026-09-17/18: NO, not reliably. Chamber RH ran 38.96..91.26 % in the windrow and was UNDER the 90 % gate threshold for 238 of 270 samples - the SHT45 sits on the tip\'s copper, the pile holds the probe at 50..77 C, and heating collapses RELATIVE humidity while the gas stays saturated, so a buried probe reads "dry" 88 % of the time and O2P_HEATER_DRY_RH_X100 blocks nothing underground. Worse, the two conditions are NOT independent evidence: the margin is T_EXT minus the GAS dew point and that dew point is Magnus on the same chamber RH, so a depressed RH puts the dew point too low and the margin too HIGH - they fail together and for one reason. At 12:01:00 on 09-17, probe already in the pile at T_EXT 51.15 C, it read RH 58.90 % and margin 8.56 K: both conditions satisfied, on the one sample of 76 where the margin cleared 6.00 K. The gate would have withheld the gradient floor inside the windrow. (Codex review finding 2, which the burial data turns from a hypothetical into an observation.) The gate therefore now also requires the CELL under O2P_HEATER_DRY_MAX_CELL_C100 = 35.00 C, releasing at 37.00 - the one gate input no humidity error can move, and the honest encoding of "not inside the pile" rather than an inference from a sensor the heater warms. T_EXT and not the chamber because the chamber carries the heater\'s own rise on Rev A while the cell is coupled at 3..11 %; an invalid cell reading refuses the gate like every other unevaluable input. Far above any bench (20.6..21.6 C through the 2026-09-20 acceptance run) and far below any pile, including the 48.61 C read on the way in. Three tests, the first built from the measured burial sample and calibrated against a build without the lockout, where it fails with "the gate engaged on a probe that was in the pile". ALSO FIXED: hin_dry_bench() had a 51.00 C cell - a pile temperature in a fixture called bench - and now carries the real measured bench numbers. Compile-time constants only, no config layout change. v0.40 - four fixes to the dry-air idle gate from the codex review of 0a5587a/7a06286 (Fab 2026-09-20: "spawn a reviewer on your code changes and the energy saving feature", then "push it over BLE"). THE TEST WAS THE DEFECT: test_the_dry_gate_is_monotonic_in_wetness() swept RH through dew_step_fresh(), which resets the state and takes ONE step, so the 120 s debt was unpaid at every point and the gate could not engage anywhere in the sweep - the test written for guard-checklist item 2 passed against a build with the gate deleted, which is item 7 failing. It now settles the gate at the sweep geometry in dry gas, asserts DRY_IDLE is set before presenting each wet sample, and asserts a gated cycle spends nothing; calibrated against the known-bad build, where it fails with "the gate never engaged on dry inputs". THE DEBT COULD PAY ITSELF IN TIME THE RING NEVER SAW: dry_idle_gate() credited any interval inside the unreachable detector O2P_HEATER_RUNAWAY_MAX_GAP_S (5 s), but heater.c stops driving O2P_HEATER_STALE_MS (2 s) after the apply() that commanded it, so a 3..5 s cadence - reachable whenever the 1 Hz cycle slips - heated for 2 s and credited up to 5. One interval now claims at most O2P_HEATER_DRY_CREDIT_MAX_S; under-crediting runs the floor LONGER, which costs energy and never condensation. Two boundaries: an engaged gate releases AT 5.00 K (strict > on the exit side) rather than below it, matching the contract its own comment stated, and the margin must be isfinite() - a +INF margin satisfies any >= and was the one row of checklist item 1 the conjunction did not cover, unreachable today because temperatures are integers and Magnus rejects invalid input, so a guard and not a fix. NOT FIXED, because it is a design decision and not a defect: the two gate conditions are not independent evidence under a FAULTY humidity sensor - at chamber 50.00 C, cell 46.20 C and a reported 60 % RH the gate idles, while an actual 84 % puts the cell 0.34 K BELOW the dew point. The 1800 s cap bounds that exposure but does not refute it, so this remains sound as a storage energy policy and NOT as an autonomous condensation safeguard under that fault; an explicit storage mode is the honest form and is Fab\'s call. Compile-time constants only, no config layout change. v0.39 - the cell temperature law gains a KNEE at 36.00 C (Fab 2026-09-20: "flash the fitted model to the probe"). The 2026-09-13 outdoor fit measured (T/T_cal)^0.75 over 13-36 C at 0.19 % rms, and the firmware then EXTRAPOLATED that one power law to every temperature above - including the 55-77 C band the probe actually works in. The 2026-09-19 oven soak measured what the cell does up there: n_eff +0.573 +-0.010 at 41.37 C (30 samples, 50 min, alpha-independent to 0.013) and +0.095/+0.225/+0.348 at 75.81 C for alpha 0.402/0.715/1.000, which as LOCAL exponents read +0.75 to 36 C, +0.065 from 36 to 41.37, and -0.001 from 41.37 to 75.81. That is a KNEE, not a drift, and no single power law describes both ends. o2p_cell_t_lnf() is therefore piecewise linear in ln(T/T_ref): the 0.75 law up to the knee, straight to the 41.37 C anchor, straight to the 75.81 C anchor, and HELD above it. Held and not extrapolated because two anchors constrain a line BETWEEN them and say nothing beyond, and an extrapolated exponent compounds into the exponent of a ratio - the exact failure being removed. Nothing below 36 C changes, bit for bit, so the outdoor fit is preserved rather than refitted over. This is the "fitted table" OVEN-SOAK-TEST.md section 8 asks for and NOT a residual in TEMPCO_PPM_K, which would double-count against the law still in force below the knee. Corrected-O2 error against 20.946 %vol at the top hold: published -6.37 %, the old law -5.95 %, uncorrected -1.01 %, a single refitted exponent -1.38 %, this law -0.00 %; out of sample at the 23.70 C R2 bracket, -0.09 %, inside the +-0.3 % the plan set. Applied to the 2026-09-17 in-pile capture (probe 3 buried 24.2 h at 66-77 C) it moves the published oxygen +6 % through the afternoon and +9.4 % overnight, where the windrow went under 1 %vol at 76 C. WHAT IS NOT MEASURED: 41.4-75.8 C is two anchors and a straight line, so everything in that span is interpolation, and the 55-60 C run that would place the knee properly is still owed. The law is deliberately NOT monotonic above 41.37 C - it is flat to within 0.05 % and exactly constant above 75.81 C - and test_cell_t_law_gain_values pins that shape segment by segment rather than asserting a rise that would re-assert the extrapolation. Compile-time constants only, no config layout change. v0.38 - the gradient floor gains a DRY-AIR IDLE GATE, so a probe out of the pile stops paying for heat (Fab 2026-09-19: "is there an energy saving mode, when probe is not inside the pile and RH is <90%, so heater stays off most of the time?" then "do it"). The dew law was already free in dry gas - its error goes negative and pi_core() clamps to zero - and the FLOOR was the one paying, demanding T_cell + 2.00 K whatever the humidity did. On the repo's measured bench plant (theta 68 K/W, tau 150 s, 3-11 % cell coupling) holding that gradient costs ~3 % STEADY duty, i.e. ~80-84 d of the 10 Ah battery against 233 d with the heater off - the ~76 % seen on a step is the PI's transient, not a consumption figure (codex review of 0a5587a, finding 4). The floor's demand is now withheld while RH is under 90 % AND the cell-side dew margin is at least 6.00 K. BOTH, because heating the chamber lowers its RH at constant absolute humidity: an RH-only gate switches the floor off by its own success, and against the wet-enclosure plant it dropped the gradient from 2.00 K to 0.40 K. The margin threshold sits 2 K above the dew law's own target so the gate can only act where that law is comfortably satisfied, which keeps the combination monotonic - wetter gas can only raise duty. NOT A LATCH, AND THE PREMIUM IS A DEBT: nothing here can tell a dry probe from one lied to by a wetted SHT45, so each idle period ends after 1800 s and the next may not start until the floor has driven 120 OBSERVED seconds - seconds it drives for any reason pay that debt, so a wet excursion settles it instead of cancelling it (codex review of 0a5587a, finding 1: a cancellable window bought 4 driven seconds in 2 h under one bad humidity sample every 1799 s). Modelled cost ~14 % of the continuous floor's energy, ~184 d. Never engages on an unevaluable humidity, and never under a RUNAWAY latch, where the floor is the only regulator left (0x001F). HEATER_LAW gains high-byte bit 11 = DRY_IDLE, absent during the re-assert window. Compile-time constants only, no config layout change. v0.37 - the tip protection LADDER moves +10 K so a 90.00 C tip is commandable (Fab 2026-09-19: "pump up the heater so the tip gets to 90 C", then "raise and push"). Three thresholds in three files move TOGETHER, preserving every separation the main.c _Static_asserts encode: commandable setpoint O2P_HEATER_TEST_SP_MAX_C100 80.00 -> 90.00, firmware clamp O2P_HEATER_TIP_LIMIT_C100 82.00 -> 92.00 with release 77.00 -> 87.00 (same 5 K hysteresis), TMP117 therm-mode cutoff O2P_TIP_LIMIT_C100 85.00 -> 95.00 (same 3 K above firmware). Raising the setpoint alone would have collapsed the ladder and made the clamp the control mechanism - the exact fault the 2026-09-08 change fixed. NOT changed: the dew law's 79/80 C ceilings, which bound the LAWS and not the bench override, and the 80.00 C SAFETY-annotated clamp for a known-down therm backstop (Fab 2026-09-11). The cell's datasheet maximum is 60 C, so FAULTS carries TEMP_OVER throughout a 90 C run by design. No config layout change. v0.36 - HEATER_DUTY (0x0005) becomes the 60 s trailing mean of the applied duty, same u16 0.01 % format, and the instantaneous duty moves to HEATER_DUTY_NOW (0x0009), growing the heater-law block from 1 register to 2 (Fab 2026-09-17: "yes let an agent implement that"). The loop decides at 1 Hz and its readers sample sparsely - the node every 60 s - so Grafana plotted a 1-in-60 snapshot and aliased (0 / 8.5 / 0 / 1.9 %). The window is time-based, one sample of o2p_heater_duty_x100() per second of uptime, because a read-reset mean would make each of several masters depend on the others' reads. Under 60 s of uptime it is the mean of the seconds that exist. No config layout change. v0.35 - the RS-485 baud enum gains 57600 as CODE 4 (Fab 2026-09-13: "try 57600"). Appended, NOT inserted in rate order: a code is stored in flash and echoed by a master, so renumbering 115200 off 3 would re-point every stored config and every deployed tool. The table is now ordered by code and not by speed, which is the case o2p_update.py fastest_code() was written against and which was until now only hypothetical. Two motives: at 38400 a 240-byte staging block is wire-bound (~69 ms wire against a ~44 ms BLE write, measured cycle 105.1 ms / 2155 B/s), so the next step is worth ~1.4x; and 115200 on probe 3 returns ZERO reply bytes, which 57600 discriminates - at 16 MHz both divide equally cleanly (BRR 278 -> 57554, BRR 139 -> 115108, both -0.08 %), so a 57600 that replies puts the fault in rate-dependent TX/DE or node RX timing rather than the 2026-09-12 rework. Four switches move together: modbus_rtu.c, loader_main.c (a loader that drops to 9600 on an unknown code strands the probe out of reach of the one tool that could fix it), and the bridge's rate macros that check_update_tool.py cross-checks. v0.34 - HEATER_LAW no longer publishes the RUNAWAY_FLOOR bit on the single cycle a latch releases (Fab 2026-09-13: "fix it"; codex review of a75c1f4, finding 5). The law word is built before update_runaway() runs, so a release left the flag claiming a latch was in force for one cycle. The duty is untouched - the floor computed it. HEATER_BLOCK's matching RUNAWAY staleness is pre-existing and left alone. 0x0022 is reserved for the peer session's probation fixes. v0.33 - a runaway latch can release while the gradient floor runs (Fab 2026-09-13: "let the latch release"; codex review of a75c1f4, finding 3). Floor duty above the 5 % idle threshold wiped RUNAWAY's release evidence every cycle, so a false latch stayed set after its thermal signature had gone. Release is now judged on the signature alone while the floor is the law under the latch; new-latch detection is unchanged. v0.32 - a short cell-reading dropout is not a dead cell (Fab 2026-09-13: "fix it"; the inherited P1 of the codex reviews of 455972d, c7baa57 and a75c1f4). Once a valid T_EXT has been seen, the reading missing for under 60 s no longer reaches the 50 % blind fallback, and no longer hands the dew law over: the unreachable-margin detector pauses and its verdict survives. Before, a flickering cell (13 s valid, 11 s missing) alternated refusal with blind 50 % and took the tip 17 K over the cell, and one missing cycle every 500 s reset the dwell and held a hot probe at the ceiling for hours. A cell missing longer than 60 s still gets the wet-board blind fallback; a probe that never had a cell reading is unaffected. v0.31 - a false RUNAWAY latch no longer ends anti-condensation heat (Fab 2026-09-13: "fix the false latch issue"; codex review of c7baa57, finding 2). Under 0x001C a latch with tip and cell readable refused to zero duty, and release needs a fresh chamber and tip-die <= 9 K, which a hot pile with cooler electronics never meets - so environmental heat could latch the probe cold indefinitely. Now, with the dew law configured and RUNAWAY the only refusal, the gradient floor keeps regulating under dew_ceiling_c100() (dew demand withheld, detector paused); HEATER_LAW high-byte bit 10 = RUNAWAY_FLOOR. A genuine stuck FET is unaffected: the floor asks for nothing over a hot tip. Hard refusals and other laws unchanged. v0.30 - the oxygen conversion's temperature term is the cell law (T/T_cal)^0.75 on the cell-side T_EXT (Fab 2026-09-13: "yes", on the physics law over the digitised DS-0637 curve). Until now it was a linear TEMPCO_PPM_K on chamber-else-tip, both board nodes, with 0 in force since the reflashes - so the published O2 moved ~1 %vol over a 13-36 C outdoor day. T_EXT is bridged 10 s across its glitch filter with the heater's freshness rule (now one shared helper), falls back to chamber-else-tip, and a missing temperature REFUSES O2_COMP instead of publishing uncorrected. An air point needs T_EXT on a probe that has one. TEMPCO_PPM_K becomes a residual on top of the law, default 0; no config layout change. v0.29 -serial probation is TWO-WAY (Fab 2026-09-13: "proceed"). A serial-settings change now confirms only when the master echoes a nonce the probe publishes at the new settings, in the new probation block at 0x000C (NONCE) / 0x000D (ACK). Until now one frame ARRIVING confirmed it, and at 13:09 that stranded probe 3 at 115200: the master's read reached the probe, the reply never reached the node, the master went back to 9600, and only a power-cycle recovered it. v0.28 -Fab's "A" on the codex xhigh review of 455972d, finding 1: a RUNAWAY latch drives the 50 % blind fallback only when the tip or the cell cannot be read; with both readable it refuses to zero duty. The gradient floor holding a hot tip at ~2.5 % duty sat under RUNAWAY's 5 % idle threshold, latched it, and the latch drove blind past the gradient ceiling. v0.27 - two fixes from the codex xhigh review of 9eb3a34/496dd2e (Fab 2026-09-13 "yes"): (1) losing only humidity (NO_RH/NO_CHAMBER, e.g. every SHT45 de-creep) no longer blinds the dew law into the 50 % fallback, which ignored the gradient ceiling - the law withholds its demand and the gradient floor regulates under dew_ceiling_c100(); HEATER_LAW gains high-byte bit 9, no dew point; (2) the unreachable-margin dwell PAUSES across refused and dew-point-less cycles instead of resetting, so frequent refusals can no longer hold a probe at the ceiling; a pause over 600 s or a hand-over still discards the evidence. No config layout change. v0.26 - the dew law's tip ceiling becomes a GRADIENT ceiling, min(79 C, T_cell + DT_MAX_K) (Fab 2026-09-13: "fix it, flash it"). Under 0x0017 the dew law ran the tip 22 -> 69 C at 100 % duty in a wet enclosure with the cell fitted: nothing bounded it in kelvin short of 79 C, and how far 1.2 W gets depends on theta. DT_MAX_K, the stored 0-4 K envelope, was enforced only against the chamber, which shares the tip's copper on Rev A; it is now also the dew law's and the floor's bound against the cell, so the excursion is bounded whatever the plant. Tunable by register, no layout bump. v0.25 - the unreachable-margin detector rebuilt as a CEILING-DWELL test after the codex xhigh review of 0x0018, which was never flashed (Fab 2026-09-13, option A). 0x0018 asked "did 5 K of tip buy 0.5 K of margin", which needs >= 10 % cell coupling on a plant that measures 3-11 %, credited outside heat as its own climb, missed plants that cannot climb 5 K and cleared on its own retreat. Now: margin short AND tip within 1 K of the 79 C ceiling for 600 observed s; recovery needs the margin 1 K over target for 600 s, or the 6 h retry; evidence is discarded across refused cycles while the verdict survives the dew law's own refusals; HEATER_LAW reads REFUSED on the cycle a runaway latches. HEATER_LAW encoding unchanged. v0.24 - unreachable-margin detector and HEATER_LAW (Fab 2026-09-13: "build the unreachable-margin detector"). In a wet enclosure the gas dew point rose with the tip (dTd/dTtip 0.89 against a cell coupling of 0.026), so the dew law ran to full duty and would have held the 79 C ceiling indefinitely without closing its error. When a 5 K tip climb buys under 0.5 K of cell-side margin the dew law now withholds its demand and the high-selected gradient floor holds the tip instead; it clears when the margin reaches target or after 6 h. New read-only block 0x0008 HEATER_LAW publishes the law in command and the unreachable flag, because no existing register could tell that fallback from both laws satisfied. v0.23 - runaway detector gains a DECAY DISCRIMINATOR (Fab 2026-09-13: "this is not a runaway situation", "fix the runaway latch now"). The tip-minus-die test is on a LEVEL with a 60 s window against a plant whose tau is 150 s, so any commanded excursion past 10 K latched on the way DOWN - measured that day: the dew law drove the tip 17.5 -> 40.7 C, demand collapsed, the latch set during the cool-down with the FET innocent. Evidence now accumulates only while the excess has not fallen 1.00 K below its peak in this window: commanded heat decays from a peak, a stuck FET holds one. v0.22 - gradient floor high-selected against the dew-margin law (Fab 2026-09-13: "should we combine +2k and the 4k dew margin?" / "lets do it then"): duty = max(dew, floor), floor = PI on (T_cell + 2.00 K) - T_tip with its own integrator, clamped to the same 79 C ceiling. Covers a valid-but-lying SHT45, whose low RH makes the dew law ask for nothing while the membrane condenses; the floor's chain is two TMP117s and no humidity. Compile-time constants only - NO config layout bump, so no migration and no lost air point. v0.21 - diag opcode 9 O2P_OP_ADS_INTERNAL_REF: volatile debug flag, every ADS1119 conversion on the internal 2.048 V reference (Fab 2026-09-11: "let it use the internal ref for all channels now, for debugging. the external ref is down"); v0.20 - VIN_DIV_X1000 at 0x004B, config block 27 -> 28 registers, no layout bump (Fab 2026-09-11: "this calibration constants belongs in the stm non-volatile storage"); v0.19 - dew-margin heater law (Fab 2026-09-11, steam bath: "fix it so it keeps a reasonable dew-margin"): cell-side TMP117 minus gas dew point held at 4 K, tip ceiling 79 C / clamp 80 C, RH law as fallback without a cell reading; v0.18 - poke mailbox 0x0198 + wide poke 0x01B0 (Fab 2026-09-11: "the equivalent write command of the peek" - SRAM .data/.bss writes only, flash/peripherals/SHARED/stack refused); v0.17 - supply veto removed (Fab 2026-09-11: <1 W, blind already heated through it; O2P_HB_SUPPLY now annotation-only); v0.16 was compost-readiness: fresh RH consent, HB IDLE/TIP_DISARMED, stale cut 2 s + STALE bit, tip glitch reject, VREF settle on recovery */

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
/* 115200 added 2026-09-09. The transceiver is the part that decides whether a
 * rate is physically available, and it is not close: U5 is a THVD1410 (BOM
 * line 51), rated 500 kbps signalling in its datasheet - "Low EMI 500 kbps and
 * 50 Mbps Data Rates", the 500 kbps half of the family, THVD1450 being the
 * 50 Mbps part. 115.2 kbps sits 4.3x inside that, and the slew-rate limiting
 * that caps it at 500 kbps is the same feature that keeps reflections tame on
 * a long cable.
 *
 * NOT VERIFIED ON THE DEPLOYED CABLE. The datasheet bounds the transceiver,
 * not this installation: no measurement of THIS cable's length, termination or
 * error rate at 115200 has been taken. The probation timer in
 * serial_probation.h is what makes trying it safe - a rate the cable cannot
 * carry means no frame arrives at the new rate and the probe puts itself back
 * within O2P_SERIAL_PROBATION_MS. */
/* 57600 = code 4, added 2026-09-13 (Fab: "try 57600"). It is APPENDED, not
 * inserted in rate order: a code is stored in flash and echoed by a master, so
 * renumbering 115200 from 3 to 4 would make every stored config and every
 * deployed tool mean a different rate than it did. This table is ordered by
 * CODE, not by speed, and nothing may assume the two agree - in particular
 * o2p_update.py's fastest_code() picks by BAUD_CODES[c], never by max(c).
 *
 * WHY. At 38400 a 240-byte staging block spends ~69 ms on the wire against a
 * ~44 ms BLE write (measured 2026-09-13: cycle 105.1 ms, 2155 B/s), so the
 * transfer is wire-bound and the next step up is worth ~1.4x. It is also the
 * discriminator for the 115200 no-reply failure on probe 3: at 16 MHz both
 * rates divide equally cleanly (BRR 278 -> 57554, BRR 139 -> 115108, both
 * -0.08 %), so if 57600 replies and 115200 does not, the fault is
 * rate-dependent - TX/DE turnaround or node RX timing - and NOT the
 * 2026-09-12 hot-air rework, which is rate-blind.
 *
 * Adding a code means four switches, not one: modbus_rtu.c baud_from_code(),
 * loader_main.c's independent copy (a bootloader that drops to 9600 on a code
 * it does not know cannot be talked to), and the bridge's rate macros that
 * tools/check_update_tool.py cross-checks against BAUD_CODES. */
enum { O2P_BAUD_9600 = 0u, O2P_BAUD_19200 = 1u, O2P_BAUD_38400 = 2u,
       O2P_BAUD_115200 = 3u, O2P_BAUD_57600 = 4u, O2P_BAUD_MAX_CODE = 4u };
enum { O2P_PARITY_NONE = 0u, O2P_PARITY_ODD = 1u, O2P_PARITY_EVEN = 2u };

/* Field order is chosen so the struct has NO implicit padding: it is written
 * to flash byte-for-byte and hashed with a CRC, and padding a compiler is
 * free to leave uninitialised would make that CRC non-deterministic. Widest
 * members first, then the bytes, then explicit reserved bytes to a multiple
 * of the 4-byte alignment. */
enum {
    O2P_ADCH_VREF_OUT_OF_BAND = 1u << 0,
    O2P_ADCH_REF_FALLBACK     = 1u << 1,
    O2P_ADCH_REF_FORCED       = 1u << 2,
    O2P_ADCH_MUX_STUCK        = 1u << 3,
    O2P_ADCH_OFFSET_BAD       = 1u << 4,
};

/* The offset self-check band, in ADS1119 LSB. SBAS925A gives offset drift in
 * the microvolt decade; 64 LSB at gain 1 is ~4.9 mV, far outside any healthy
 * offset and far inside a stuck or shorted input. */
#define O2P_ADC_OFFSET_MAX_LSB 64

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
    /* VIN divider ratio x 1000, HIGH byte - register 0x004B. Composed with
     * vin_div_x1000_lo at offset 35 by o2p_cfg_vin_div_x1000(); see there for
     * why one u16 lives in two non-adjacent bytes. */
    uint8_t  vin_div_x1000_hi;        /* 31 */
    uint16_t dil_alpha_x1000;         /* 32 */
    /* 1 once a zero point has been TAKEN. Needed because 0 nA is a legitimate
     * measured zero as well as the never-measured default, and the two have
     * identical arithmetic (subtract nothing) but opposite meanings to an
     * operator deciding whether commissioning is finished. */
    uint8_t  cal_zero_taken;          /* 34 */
    uint8_t  vin_div_x1000_lo;        /* 35 - LOW byte of 0x004B, see offset 31 */
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

/* ---- VIN_DIV_X1000 (0x004B) storage ---------------------------------------
 *
 * TWO NON-ADJACENT BYTES, offsets 31 and 35, because those are free and
 * nothing next to either one is. Making them adjacent means moving a field,
 * which is a re-layout, which is a layout version bump, which sends every probe
 * through config_migrate.c - and that discards both heater consents by policy.
 * The value is composed here explicitly, so its byte order is this code's and
 * not the compiler's, and the offsets are pinned so a later edit cannot slide
 * it onto a field.
 *
 * NO VERSION BUMP IS NEEDED because zero is what every existing record already
 * holds there, and zero means "the netlist divider" - the arithmetic those
 * records were run with. Offset 31 was reserved in every layout since v4 and
 * offset 35 since v6; the defaults memset the struct, every migration starts
 * from the defaults, and no firmware ever wrote either byte. Same polarity
 * argument as cal_bias_verified at offset 46.
 *
 * Offset 47 is now the record's last spare byte. */
#define O2P_VIN_DIV_X1000_NETLIST 0u
#define O2P_VIN_DIV_X1000_MIN     2000u
#define O2P_VIN_DIV_X1000_MAX     20000u
_Static_assert(offsetof(o2p_config_t, vin_div_x1000_hi) == 31u,
               "VIN_DIV high byte must stay in v4's reserved byte at 31");
_Static_assert(offsetof(o2p_config_t, vin_div_x1000_lo) == 35u,
               "VIN_DIV low byte must stay in v6's reserved byte at 35");

static inline uint16_t o2p_cfg_vin_div_x1000(const o2p_config_t *c)
{
    return (uint16_t)(((uint16_t)c->vin_div_x1000_hi << 8) | c->vin_div_x1000_lo);
}

static inline void o2p_cfg_set_vin_div_x1000(o2p_config_t *c, uint16_t v)
{
    c->vin_div_x1000_hi = (uint8_t)(v >> 8);
    c->vin_div_x1000_lo = (uint8_t)(v & 0xFFu);
}

/* Is a stored ratio one the register write would have accepted? Every consumer
 * asks this instead of trusting the bytes: anything outside the window - 0 by
 * design, or a pattern that never came through a write - scales by the netlist
 * divider.
 *
 * DELIBERATELY NOT a clause of o2p_config_valid(). A record that fails that
 * function boots on FULL DEFAULTS, which resets slave_addr, baud and parity,
 * and these are bytes older firmware never wrote and never checked. Refusing a
 * whole record over a supply-monitor scale factor would trade a wrong voltage
 * reading for a potted probe that no longer answers its master. */
static inline bool o2p_vin_div_x1000_in_window(uint16_t v)
{
    return v >= O2P_VIN_DIV_X1000_MIN && v <= O2P_VIN_DIV_X1000_MAX;
}

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
    uint16_t adc_health;
    uint16_t faults_ever;
    uint16_t ads_fail_count;
    uint16_t we_buf_mv;
    uint16_t re_buf_mv;
    int16_t  cell_bias_mv;
    uint16_t heater_block;
    uint16_t heater_law;       /* HEATER_LAW, 0x0008 */
    uint16_t heater_duty_now;  /* HEATER_DUTY_NOW, 0x0009 (FW 0x0025) */
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
    /* FW 0x001D, the two-way proof (serial_probation.h). The nonce main.c
     * publishes when the new settings go live - 0 before that and after the
     * probation resolves - and whether the master has echoed it. */
    volatile uint16_t probation_nonce;
    volatile bool probation_acked;
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
    /* Heater bench override, 0x0060/0x0061. Volatile by construction: these
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

    /* Wide peek block. The words are a SNAPSHOT taken at trigger time, not a
     * window onto live memory: reads only ever return what was copied then. */
    uint32_t peekw_addr;
    uint16_t peekw_words_req;
    uint16_t peekw_status;
    uint16_t peekw_seq;
    uint32_t peekw_words[O2P_PEEKW_WORDS_MAX];

    /* Memory poke mailbox and wide poke (2026-09-11, FW_VERSION 0x0012):
     * the write counterparts above. The payload is HELD after the trigger
     * so a readback shows exactly what was sent - the poke's own answer to
     * "did it take" before any peek is aimed at the target. */
    uint16_t poke_addr_hi;
    uint16_t poke_addr_lo;
    uint16_t poke_words_held;
    uint16_t poke_status;
    uint32_t poke_words[4];

    uint32_t pokew_addr;
    uint16_t pokew_words_req;
    uint16_t pokew_status;
    uint16_t pokew_seq;
    uint32_t pokew_words[O2P_PEEKW_WORDS_MAX];

    /* Sensor diagnostic mailbox */
    uint16_t diag_cmd;
    uint16_t diag_param;
    uint16_t diag_status;
    uint16_t diag_rdata0;
    uint16_t diag_rdata1;
    uint16_t diag_rdata2;
    uint16_t diag_crc_status;
    volatile bool diag_pending;
    /* O2P_OP_ADS_INTERNAL_REF (diag opcode 9): nonzero = every ADS1119
     * conversion on the internal 2.048 V reference. uint32_t, not bool, so it
     * is one aligned word the poke mailbox can write and the peek read back.
     * Volatile and zeroed by o2p_regmap_init(), i.e. off after every reset. */
    volatile uint32_t ads_internal_ref;

    /* Arbitrary code execution mailbox */
    uint16_t exec_cmd;
    uint16_t exec_len;
    uint16_t exec_param_hi;
    uint16_t exec_param_lo;
    uint16_t exec_timeout_ms;
    uint16_t exec_status;
    uint16_t exec_result_hi;
    uint16_t exec_result_lo;
    uint16_t exec_code[O2P_REG_EXEC_CODE_COUNT];
    volatile bool exec_pending;

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
#ifdef O2P_HOST_TEST
/* Host builds have no SRAM or flash at the addresses a peek names. Every
 * dereference the peek paths would make goes through this instead, so a test
 * can back the regions with a pattern AND see every address that was touched
 * - which is how a test proves a refused burst dereferenced nothing, rather
 * than inferring it from a status code. NULL gives a fixed pattern of the
 * address. o2p_peek_host_irq_depth counts the masked sections the copy is
 * inside, so a test can check the copy never runs with interrupts enabled. */
extern uint32_t (*o2p_peek_host_read)(uint32_t addr);
extern int o2p_peek_host_irq_depth;
/* The peek-space address the copy should treat `dst` as living at, for the N1
 * source/destination overlap test. NULL (the default) means no overlap, and
 * the copy runs ascending as it did before the fix. */
extern uint32_t (*o2p_peek_host_dst_addr)(const uint32_t *dst);
/* The poke's store seam (2026-09-11): every store the poke paths would make
 * goes through this, so a test can back the regions with memory AND count
 * every store - which is how a test proves a refused poke wrote nothing,
 * rather than inferring it from a status code. The peek-space address the
 * store should treat its payload buffer as living at, for the write-side
 * overlap test (the N1 mirror). NULL means no overlap. */
extern void (*o2p_peek_host_store)(uint32_t addr, uint32_t val);
extern uint32_t (*o2p_peek_host_src_addr)(const uint32_t *src);
/* The SRAM parity gate's inputs (O2P_PEEK_ERR_PARITY): what FLASH_OPTR reads,
 * and the linker's _sdata/_edata/_sbss/_ebss. o2p_peek_host_parity_reset()
 * restores the factory option byte (parity check disabled) and a fixed map. */
extern uint32_t o2p_peek_host_optr;
extern uint32_t o2p_peek_host_sdata, o2p_peek_host_edata;
extern uint32_t o2p_peek_host_sbss, o2p_peek_host_ebss;
void o2p_peek_host_parity_reset(void);
#endif
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
