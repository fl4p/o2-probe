/* The bootloader's RS-485 transport: the same USART1, the same PC6 direction
 * pin, polled instead of interrupt-driven.
 *
 * modbus_rtu.c is not reused here on purpose. It is written around the
 * application's register map and configuration struct, it runs on three
 * interrupt handlers, and it carries a bus-jam backstop that cooperates with
 * main()'s watchdog policy - none of which the bootloader has. The loader has
 * one job, no sampler to interleave with, and no watchdog, so it can afford
 * to block; and every line it does not share with the application is a line
 * that cannot be broken by a change to the application.
 *
 * The framing rule is identical because the wire is identical: the USART's
 * hardware receiver timeout (RTOR/RTOF) counts the 3.5 character times of
 * silence that end an RTU frame.
 */
#ifndef O2P_LOADER_UART_H
#define O2P_LOADER_UART_H

#include <stddef.h>
#include <stdint.h>

/* `parity_code` is an O2P_PARITY_* value; `baud` is a real baud rate. */
void o2p_luart_init(uint32_t baud, uint8_t parity_code);

/* Returns the length of a complete, error-free frame copied into `out`, or 0.
 * A frame that overran the buffer or arrived with a line error is dropped
 * here: answering one would put an unrequested transmission on a shared bus. */
size_t o2p_luart_poll(uint8_t *out, size_t cap);

/* Blocking, including the wait for the last stop bit to leave the shift
 * register before DE is released. */
void o2p_luart_send(const uint8_t *buf, size_t len);

/* Put USART1 and its pins back to a state the application's own init can
 * start from, before jumping to it. */
void o2p_luart_deinit(void);

#endif /* O2P_LOADER_UART_H */
