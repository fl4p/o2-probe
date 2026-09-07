/* Modbus RTU transport on USART1 with software-driven RS-485 enables.
 *
 * TWO enable pins since Rev B: PC6 = DE (driver enable, active high) and
 * PC7 = /RE (receiver enable, active LOW). Rev A shorted them together, which
 * cost the THVD1410's 0.1 uA standby state; see o2p_modbus_rx_standby() and
 * ../../POWER-BUDGET.md. The default runtime behaviour of this driver is
 * unchanged by the split: /RE goes high exactly when DE goes high.
 *
 * Why software DE: PC6 carries the DE net, and PC6 has NO USART1_DE alternate
 * function on the STM32G071 - only TIM2_CH3 (AF2) and TIM3_CH1 (AF1). USART1's
 * hardware driver-enable exists only on PA12 and PB3, and neither reaches the
 * THVD1410. PLAN.md:261 assumed "USART+DE"; the board as generated cannot do
 * it, so DE is asserted before transmission and released in the
 * transmission-complete interrupt.
 *
 * Framing uses the USART's hardware receiver timeout (RTOR/RTOF), which counts
 * bit periods after the last received stop bit - exactly the RTU end-of-frame
 * condition, with no second timer and no polling.
 */
#ifndef O2P_MODBUS_RTU_H
#define O2P_MODBUS_RTU_H

#include <stdbool.h>
#include <stdint.h>

#include "modbus_pdu.h"
#include "regmap.h"

void o2p_modbus_init(const o2p_config_t *cfg);

/* Apply a new address/baud/parity. Safe to call only when the transmitter is
 * idle; o2p_modbus_poll enforces that. */
void o2p_modbus_reconfigure(const o2p_config_t *cfg);

/* Service one received frame, if any. Call from the main loop. Returns true
 * if a frame was processed. */
bool o2p_modbus_poll(o2p_regmap_t *rm);

/* True while a response is still being shifted out. */
bool o2p_modbus_tx_busy(void);

uint16_t o2p_modbus_crc_errors(void);
uint16_t o2p_modbus_frame_errors(void);

/* True if the RS-485 driver has been enabled for far longer than any frame
 * could take. A stuck-high PC6 does not merely mute this probe - it drives the
 * shared cable and silences the two SMT100s as well. (Before Rev B, PC6 also
 * carried ~RE, so the same fault deafened this probe too; splitting /RE onto
 * PC7 removes that second effect but not the first, which is the one that
 * matters here.) Software cannot be its own last line of defence here: the
 * backstop timer lives in the same CPU that would have to be wedged for the
 * TC interrupt to have been missed. main() therefore stops feeding the
 * watchdog when this is true, so the reset - and R7's 47k pull-down on DE -
 * becomes the release path that does not depend on this CPU running code.
 * R7 SURVIVES THE REV B SPLIT UNTOUCHED and that argument still reads true:
 * DE keeps its own 47k to GND, so reset still releases the bus with no code
 * running. R45 is the matching 47k on /RE, and it is what keeps the probe
 * LISTENING through the same reset. */
bool o2p_modbus_bus_jam_suspected(void);

/* Put the transceiver into, or take it out of, its 0.1 uA standby state
 * (/RE high, DE low). A probe in standby is DEAF: it cannot be polled and
 * cannot be reached by the RS-485 field updater, so this is not a power knob
 * to be turned lightly. Nothing in the shipped control flow calls it - the
 * split exists so the state is reachable at all, which Rev A hardware was not.
 * Refused (returns false) while a response is still being transmitted.
 * The real saving on this board is about 630 uA, not the datasheet's 700 uA:
 * see the block comment in modbus_rtu.c. */
bool o2p_modbus_rx_standby(bool on);
bool o2p_modbus_rx_standby_active(void);

#endif /* O2P_MODBUS_RTU_H */
