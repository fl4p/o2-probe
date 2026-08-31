/* Modbus RTU transport on USART1 with a software-driven RS-485 direction pin.
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

#endif /* O2P_MODBUS_RTU_H */
