/* TMP117 at the warm tip, I2C 0x49 (ADD0 strapped to V+).
 *
 * Register map verified against TI SNOSD82D (Sep 2022) section 7.6.
 *
 * This part has two jobs. The ordinary one is measuring the membrane-carrier
 * temperature. The safety one is that its open-drain ALERT pin is wired
 * DIRECTLY to the heater MOSFET gate (gen_sch.py: U10.3 and Q2.1 are both
 * HEATER_GATE), so a correctly configured alert pulls the heater off in
 * hardware, without the MCU. DESIGN.md:47-51 and FAB-READINESS.md:61 both say
 * that path "is not credited as an autonomous overtemperature cutoff until
 * firmware configures and fault-tests the TMP117" - which is precisely why v0
 * ships with the heater disabled.
 *
 * THE BIT THAT MAKES OR BREAKS THAT CUTOFF: T/nA must be 1 (therm mode).
 *
 * In ALERT mode (T/nA = 0) the datasheet says HIGH_Alert is "Cleared on read
 * of configuration register". This firmware reads the configuration register
 * to check flags, so in alert mode our own polling would RELEASE the heater
 * clamp moments after an overtemperature asserted it. In THERM mode the flag
 * instead clears only "when the conversion result is lower than the
 * hysteresis" - a real latch with a real release condition. Therm mode is not
 * a preference here, it is the difference between a cutoff and a blink.
 *
 * Two more bits, for the same reason:
 *   POL = 0        active low, so asserting pulls HEATER_GATE down = heater off.
 *   DR/Alert = 0   the pin follows the alert flags, NOT data-ready. With
 *                  DR/Alert = 1 the pin would pulse every conversion and chop
 *                  the heater at the conversion rate.
 */
#ifndef O2P_TMP117_H
#define O2P_TMP117_H

#include <stdbool.h>
#include <stdint.h>

enum {
    O2P_TMP_REG_TEMP    = 0x00u,
    O2P_TMP_REG_CONFIG  = 0x01u,
    O2P_TMP_REG_THIGH   = 0x02u,
    O2P_TMP_REG_TLOW    = 0x03u,
    O2P_TMP_REG_DEVID   = 0x0Fu,
};
#define O2P_TMP_DEVICE_ID 0x0117u

/* 1 LSB = 7.8125 m degC (SNOSD82D 7.6.2). */
#define O2P_TMP_LSB_UC 7813   /* micro-degrees, rounded from 7812.5 */

/* The part's rated operating range (SNOSD82D), in 0.01 C. A conversion outside
 * this is a bus error, not weather - see o2p_tmp117_read(), where the check
 * that was supposed to enforce this was tautological until 2026-09-08. */
#define O2P_TMP117_MIN_C100 (-5500)
#define O2P_TMP117_MAX_C100  15000

typedef enum { O2P_TMP_OK = 0, O2P_TMP_IO, O2P_TMP_ID, O2P_TMP_CONFIG } o2p_tmp_status_t;

/* Identify the part, then program continuous conversion with 8-sample
 * averaging and the therm-mode alert described above.
 *
 * `limit_c100` is the absolute cutoff in 0.01 C; `hyst_k100` how far the tip
 * must fall below it before the clamp releases.
 */
o2p_tmp_status_t o2p_tmp117_init(int16_t limit_c100, uint16_t hyst_k100);

/* Temperature in 0.01 C. */
o2p_tmp_status_t o2p_tmp117_read_c100(int16_t *out_c100);

/* True only if o2p_tmp117_init() last completed successfully AND the most
 * recent o2p_tmp117_verify_safety() agreed. The v1 heater loop MUST refuse to
 * energise while this is false: the whole hardware-cutoff argument rests on
 * the therm-mode alert actually being programmed, and a silently failed init
 * leaves temperature reads working perfectly while the cutoff is not armed. */
bool o2p_tmp117_safety_armed(void);

/* Re-read the configuration register and confirm it still matches intent. */
o2p_tmp_status_t o2p_tmp117_verify_safety(void);

/* True while the therm-mode high alert is asserted, i.e. while the hardware
 * is holding the heater off. Reading this clears nothing in therm mode. */
o2p_tmp_status_t o2p_tmp117_alert_active(bool *out_active);

#endif /* O2P_TMP117_H */
