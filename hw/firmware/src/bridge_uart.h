/* The bench bridge's two USARTs, as one driver with two instances.
 *
 * The bridge is a spare, UNPOTTED probe used as an RS-485 adapter: a laptop's
 * 3.3 V USB-TTL lead on USART2 (PA2/PA3), the farm cable on USART1 through the
 * board's own THVD1410. Frames are carried across verbatim.
 *
 * This does not reuse loader_uart.c, and the duplication is deliberate. That
 * file belongs to the bootloader - the image that has to still work when the
 * application does not - and a bench tool is not a reason to touch it. It also
 * keeps one set of statics for one USART, which is exactly what a bridge
 * cannot have.
 *
 * The framing rule is the one both other images use, because the wire is the
 * same wire: the USART's hardware receiver timeout (RTOR/RTOF) counts the 3.5
 * character times of silence that end an RTU frame. That timeout is also what
 * tells the bridge when a host frame is complete, and therefore when it may
 * assert DE - a half-duplex bridge cannot know either thing any sooner.
 */
#ifndef O2P_BRIDGE_UART_H
#define O2P_BRIDGE_UART_H

#include "mcu.h"
#include "modbus_pdu.h"

#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    USART_TypeDef *usart;
    bool           drives_de;      /* true on the RS-485 side only */
    uint8_t        buf[O2P_MB_MAX_ADU];
    size_t         len;
    bool           poisoned;
    uint16_t       frames;         /* complete frames handed out */
    uint16_t       drops;          /* frames discarded: line error or overrun */
} o2p_buart_t;

/* USART1 + PA9/PA10 + the PC6 direction pin: the farm RS-485 side. */
void o2p_buart_init_bus(o2p_buart_t *b, uint32_t baud, uint8_t parity_code);

/* USART2 + PA2/PA3: the host TTL side. No direction pin - it is full duplex,
 * point to point, and there is nothing else on it. */
void o2p_buart_init_host(o2p_buart_t *b, uint32_t baud, uint8_t parity_code);

/* Length of a complete frame copied into `out`, or 0. A frame that overran the
 * buffer or carried a parity/framing/noise/overrun error is counted in `drops`
 * and discarded: forwarding bytes already known to be wrong would turn a line
 * fault at one end into a mystery at the other, and silence is what a Modbus
 * master is built to survive. */
size_t o2p_buart_poll(o2p_buart_t *b, uint8_t *out, size_t cap);

/* Blocking, including the wait for the last stop bit to clear the shift
 * register before DE is released. */
void o2p_buart_send(o2p_buart_t *b, const uint8_t *buf, size_t len);

#endif /* O2P_BRIDGE_UART_H */
