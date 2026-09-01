/* Membrane-ring heater - hardware half. The control law is in heater_ctl.h.
 *
 * =====================================================================
 *  THE HEATER IS DISABLED IN THIS BUILD (O2P_HEATER_ENABLE = 0).
 * =====================================================================
 *
 * DESIGN.md:47-51 and FAB-READINESS.md:61 both state that the TMP117 ALERT
 * path "is not credited as an autonomous overtemperature cutoff until firmware
 * configures and fault-tests the TMP117". Firmware now configures it, and
 * o2p_tmp117_safety_armed() latches whether that took. It has NOT been
 * fault-tested, because nothing in this firmware has ever executed on silicon.
 *
 * Setting O2P_HEATER_ENABLE to 1 in platformio.ini is therefore a deliberate
 * act with prerequisites, all of them bench work on a real board:
 *
 *   1. TMP117 alert fault test. Lower THIGH below ambient, command duty, and
 *      observe HEATER_LOW actually go high (heater off) on a scope. The whole
 *      hardware-cutoff argument is this one measurement. FIRMWARE.md carries
 *      the procedure.
 *   2. Gate edge and PWM frequency. SCHEMATIC-REVIEW.md H3 closure makes this
 *      "a firmware and thermal bench requirement": R28 is 10 k into the
 *      AO3400A gate against R29's 100 k pulldown, so Vgs reaches only ~3.0 V
 *      and the edge is tens of microseconds. Scope it, and check FET
 *      dissipation at INTERMEDIATE duty, not only 0 % and 100 %.
 *   3. Heater and ring safe at 100 % duty at the 15 V input worst case
 *      (1.61 W, not the 1.03 W of the 12 V nominal case).
 *   4. Loop gains tuned against the real thermal path. The plant gain is
 *      unknown - see heater_ctl.h - so the shipped gains are placeholders.
 *   5. Controlled dew-point crossings, per FAB-READINESS.md's open gates.
 *
 * Until then the pin is a plain output held low and TIM1's clock is off, so
 * no register write anywhere in this firmware can energise the ring.
 */
#ifndef O2P_HEATER_H
#define O2P_HEATER_H

#include <stdbool.h>
#include <stdint.h>

/* How long a duty command stays good. The sampler publishes at 1 Hz; if it
 * stops, the heater must not keep driving whatever it was last told.
 * PLAN.md:309-311 asks for a "watchdog-bounded enable" and this is the
 * firmware half of that - the IWDG is the other half. */
#define O2P_HEATER_STALE_MS 5000u

void o2p_heater_init(void);

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
