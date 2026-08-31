/* Membrane-ring heater control.
 *
 * v0 SHIPS THIS DISABLED, and that is a deliberate, documented decision:
 * DESIGN.md:47-51 and FAB-READINESS.md:61 both state that the TMP117 ALERT
 * path "is not credited as an autonomous overtemperature cutoff until firmware
 * configures and fault-tests the TMP117". Until that bench test has been run
 * and recorded, nothing here may put 1 W into a membrane carrier that sits
 * against an electrochemical cell.
 *
 * The cost of that decision is real and must be stated rather than buried: the
 * SGX cell is rated 15-90 %RH continuous, non-condensing, and the heater is
 * the only thing keeping the membrane above the dew point of saturated pore
 * gas. A v0 probe left in a pile for weeks will wet the membrane. v0 is a
 * BENCH AND SHORT-DEPLOYMENT build; the DEW_MARGIN and DEW_SUSPECT channels
 * exist so the damage is observed rather than discovered afterwards.
 */
#ifndef O2P_HEATER_H
#define O2P_HEATER_H

#include <stdbool.h>
#include <stdint.h>

void o2p_heater_init(void);

/* Request a duty in 0.01 %. In v0 any non-zero request is refused and
 * reported; the function never silently accepts one. */
bool o2p_heater_set_duty_x100(uint16_t duty_x100);

uint16_t o2p_heater_duty_x100(void);

/* Unconditionally drive the gate low. Called on every fault path. */
void o2p_heater_force_off(void);

#endif /* O2P_HEATER_H */
