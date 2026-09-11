/* Membrane-ring heater - hardware half. The control law is in heater_ctl.h.
 *
 * =====================================================================
 *  THE HEATER IS COMPILED IN (O2P_HEATER_ENABLE = 1) as of 2026-09-08.
 * =====================================================================
 *
 * Compiled in means REACHABLE, not energised. Three switches stand between
 * this file and current in the membrane, and only the first is compile-time:
 *
 *   1. O2P_HEATER_ENABLE in platformio.ini - now 1.
 *   2. HEATER_MAX_DUTY (register 0x0035), which defaults to zero and lives in
 *      flash. Zero raises O2P_HB_CONFIG_OFF and the duty is zero.
 *   3. For open-loop bench work, the volatile arm register at 0x0060, which
 *      needs a magic word and does not survive a reset.
 *
 * WHAT CHANGED, AND WHAT DID NOT.
 *
 * This build was turned on for the 80 C harsh-environment characterisation:
 * drive the ring open-loop to the firmware tip limit, then repeat the same
 * end point with an external water bath, and compare what the cell does. The
 * degradation that implies is expected and is the experiment's subject.
 *
 * The overtemperature story is unchanged and is worth stating plainly rather
 * than leaving implied. Firmware programs the TMP117's therm-mode alert at
 * 85 C and o2p_tmp117_safety_armed() latches whether that took; if it did
 * not, O2P_HB_SAFETY blocks the heater, in the bench override too. Below it
 * sits the firmware's own absolute clamp at O2P_HEATER_TIP_LIMIT_C100
 * (82.00 C, release 77.00 C - raised from 80.00/75.00 on 2026-09-08; this
 * comment still said 80.00/75.00 until the 2026-09-10 audit), which the
 * override also does not touch. What has
 * never been done is the INJECTED-FAULT test of the alert path - lowering
 * THIGH below ambient, commanding duty, and watching HEATER_LOW go high. So
 * the 85 C cutoff is configured and read back, not proven. The 80 C clamp is
 * firmware, which means it fails if firmware fails.
 *
 * Remaining bench work, none of it blocking this build:
 *
 *   1. The TMP117 alert injected-fault test above. FIRMWARE.md has the
 *      procedure.
 *   2. Gate edge and PWM frequency. R28 is 10 k into the AO3400A gate against
 *      R29's 100 k pulldown, so Vgs reaches only ~3.0 V and the edge is tens
 *      of microseconds - check FET dissipation at INTERMEDIATE duty, not only
 *      at 0 % and 100 %.
 *   3. Ring safe at 100 % duty at the 15 V input worst case: 1.61 W, against
 *      1.03 W at the 12 V nominal.
 *   4. Loop gains. The plant gain is unknown - see heater_ctl.h - so the
 *      shipped PI gains remain placeholders. The bench override exists
 *      precisely so the plant can be driven open-loop at whatever power the
 *      ring has, without first needing gains that describe it.
 *   5. Controlled dew-point crossings, per FAB-READINESS.md's open gates.
 */
#ifndef O2P_HEATER_H
#define O2P_HEATER_H

#include <stdbool.h>
#include <stdint.h>

/* How long a duty command stays good. The sampler publishes at 1 Hz; if it
 * stops, the heater must not keep driving whatever it was last told.
 * PLAN.md:309-311 asks for a "watchdog-bounded enable" and this is the
 * firmware half of that - the IWDG is the other half. The soft cut must
 * land BEFORE the IWDG's fastest bound: the IWDG is ~4.096 s nominal but as
 * fast as ~2.7 s across the LSI spread (mcu.c's own numbers), and at the
 * previous 5000 ms the reset won the race on every part off the slow tail -
 * where the cut fired silently with HEATER_DUTY still publishing the last
 * command (2026-09-10 audit F2). 2 s clears the fastest bound with margin
 * and still rides out a single missed 1 Hz publish. */
#define O2P_HEATER_STALE_MS 2000u

void o2p_heater_init(void);

/* True when o2p_heater_service() has cut drive for staleness since the last
 * apply() - cycle_publish() folds this into HEATER_BLOCK as O2P_HB_STALE. */
bool o2p_heater_stale_cut(void);

/* True if this build can drive the heater at all. */
bool o2p_heater_compiled_in(void);

/* CC1NE clear and PA7 still analog.
 *
 * PA8 is TIM1_CH1 and PA7 is TIM1_CH1N - the complement of that same channel -
 * while PA7 is also the 3V3A rail monitor, the independent witness for the
 * brownout that silently drops the cell bias. If CC1NE were ever set, the
 * timer would drive the analog input and the brownout supervision would become
 * fiction while continuing to report numbers. Both adversarial reviews raised
 * this, and a comment is not a guard, so it is asserted at runtime. */
bool o2p_heater_pin_integrity_ok(void);

/* Apply a duty (0.01 %) at the configured PWM frequency. Reconfigures the
 * timer only when the frequency actually changes. */
void o2p_heater_apply(uint16_t duty_x100, uint16_t pwm_hz);

/* Call every main-loop pass. Forces the heater off if no command has arrived
 * within O2P_HEATER_STALE_MS. */
void o2p_heater_service(void);

uint16_t o2p_heater_duty_x100(void);

/* Unconditionally drive the gate low. Every fault path ends here. */
void o2p_heater_force_off(void);

#endif /* O2P_HEATER_H */
