#include "bridge_uart.h"

#include "board_pins.h"
#include "regmap.h"   /* O2P_PARITY_* */

#include <string.h>

/* A transmission that never completes must not hold DE - and with it the whole
 * cable, including the two SMT100s - forever. The number is in the header,
 * because the lowest baud this image may be built for depends on it. */
#define TX_TIMEOUT_MS O2P_BUART_TX_TIMEOUT_MS

static void de_assert(void)
{
    O2P_RS485_DE_PORT->BSRR = (1u << O2P_RS485_DE_PIN);
}

static void de_release(void)
{
    O2P_RS485_DE_PORT->BSRR = (1u << (O2P_RS485_DE_PIN + 16u));
}

/* /RE, the Rev B split (PC7), ACTIVE LOW. This image never wants standby; it
 * moves this pin only to keep Rev A's behaviour, where the one shared net
 * deafened the receiver for the length of every transmission. A bridge that
 * heard its own bus-side transmission would accumulate it and forward it back
 * up to the host as if a probe had answered. Low - listening - on every other
 * path; R45's 47k holds it there before this code runs. */
static void re_disable(void)
{
    O2P_RS485_RE_PORT->BSRR = (1u << O2P_RS485_RE_PIN);
}

static void re_enable(void)
{
    O2P_RS485_RE_PORT->BSRR = (1u << (O2P_RS485_RE_PIN + 16u));
}

static void pin_af(GPIO_TypeDef *port, uint32_t pin, uint32_t af)
{
    port->OSPEEDR |= (3u << (pin * 2u));
    port->AFR[pin >> 3] = (port->AFR[pin >> 3] & ~(0xFu << ((pin & 7u) * 4u))) |
                          (af << ((pin & 7u) * 4u));
    port->MODER = (port->MODER & ~(3u << (pin * 2u))) | (2u << (pin * 2u));
}

static void usart_config(USART_TypeDef *u, uint32_t baud, uint8_t parity_code)
{
    u->CR1 = 0u;
    u->BRR = (O2P_SYSCLK_HZ + baud / 2u) / baud;
    /* 3.5 character times: 11 bits per character with parity, 10 without. The
     * same arithmetic as modbus_rtu.c and loader_uart.c - a bridge that framed
     * differently from the probe behind it would cut long frames in half. */
    u->RTOR = ((parity_code == O2P_PARITY_NONE ? 10u : 11u) * 7u + 1u) / 2u;
    u->CR2 = USART_CR2_RTOEN;
    u->CR3 = 0u;

    uint32_t cr1 = USART_CR1_RE | USART_CR1_TE;
    if (parity_code != O2P_PARITY_NONE) {
        cr1 |= USART_CR1_M0 | USART_CR1_PCE;   /* 8 data + parity = 9-bit word */
        if (parity_code == O2P_PARITY_ODD) {
            cr1 |= USART_CR1_PS;
        }
    }
    u->CR1 = cr1 | USART_CR1_UE;
}

static void instance_init(o2p_buart_t *b, USART_TypeDef *u, bool drives_de,
                          uint32_t baud, uint8_t parity_code)
{
    memset(b, 0, sizeof(*b));
    b->usart = u;
    b->drives_de = drives_de;
    usart_config(u, baud, parity_code);
}

void o2p_buart_init_bus(o2p_buart_t *b, uint32_t baud, uint8_t parity_code)
{
    RCC->APBENR2 |= RCC_APBENR2_USART1EN;

    /* DE low before the pin is an output at all. R7's 47k already holds the
     * driver disabled through reset; this keeps it there while the bridge
     * configures itself, so plugging the bench probe into a live farm cable
     * does not mute the SMT100s. */
    de_release();
    O2P_RS485_DE_PORT->OTYPER &= ~(1u << O2P_RS485_DE_PIN);
    O2P_RS485_DE_PORT->OSPEEDR |= (3u << (O2P_RS485_DE_PIN * 2u));
    O2P_RS485_DE_PORT->MODER =
        (O2P_RS485_DE_PORT->MODER & ~(3u << (O2P_RS485_DE_PIN * 2u))) |
        (1u << (O2P_RS485_DE_PIN * 2u));

    /* /RE low, same order and for the same reason: the level is written before
     * MODER so the pin cannot glitch high on its way to becoming an output. */
    re_enable();
    O2P_RS485_RE_PORT->OTYPER &= ~(1u << O2P_RS485_RE_PIN);
    O2P_RS485_RE_PORT->OSPEEDR |= (3u << (O2P_RS485_RE_PIN * 2u));
    O2P_RS485_RE_PORT->MODER =
        (O2P_RS485_RE_PORT->MODER & ~(3u << (O2P_RS485_RE_PIN * 2u))) |
        (1u << (O2P_RS485_RE_PIN * 2u));

    pin_af(O2P_RS485_TX_PORT, O2P_RS485_TX_PIN, O2P_RS485_TX_AF);
    pin_af(O2P_RS485_RX_PORT, O2P_RS485_RX_PIN, O2P_RS485_RX_AF);

    instance_init(b, USART1, true, baud, parity_code);
}

void o2p_buart_init_host(o2p_buart_t *b, uint32_t baud, uint8_t parity_code)
{
    RCC->APBENR1 |= RCC_APBENR1_USART2EN;

    pin_af(O2P_EXP_UART_TX_PORT, O2P_EXP_UART_TX_PIN, O2P_EXP_UART_TX_AF);
    pin_af(O2P_EXP_UART_RX_PORT, O2P_EXP_UART_RX_PIN, O2P_EXP_UART_RX_AF);

    instance_init(b, USART2, false, baud, parity_code);
}

void o2p_buart_accumulate(o2p_buart_t *b)
{
    USART_TypeDef *u = b->usart;
    uint32_t isr = u->ISR;

    while ((isr & USART_ISR_RXNE_RXFNE) != 0u) {
        /* The error flags belong to THIS character and must be read before
         * RDR: reading RDR is what clears RXNE and advances to the next. */
        const bool bad = (isr & (USART_ISR_PE | USART_ISR_FE | USART_ISR_NE)) != 0u;
        uint8_t byte = (uint8_t)u->RDR;
        if (bad) {
            u->ICR = USART_ICR_PECF | USART_ICR_FECF | USART_ICR_NECF;
            b->poisoned = true;
        }
        if (b->len < sizeof(b->buf)) {
            b->buf[b->len++] = byte;
        } else {
            /* Longer than any legal ADU. Poison rather than wrap: a frame
             * assembled from the tail of an overrun is not a frame. */
            b->poisoned = true;
        }
        isr = u->ISR;
    }

    if ((isr & USART_ISR_ORE) != 0u) {
        u->ICR = USART_ICR_ORECF;
        b->poisoned = true;
    }
}

size_t o2p_buart_poll(o2p_buart_t *b, uint8_t *out, size_t cap)
{
    o2p_buart_accumulate(b);

    USART_TypeDef *u = b->usart;
    if ((u->ISR & USART_ISR_RTOF) == 0u) {
        return 0u;
    }
    u->ICR = USART_ICR_RTOCF;

    const size_t n = b->len;
    const bool bad = b->poisoned;
    b->len = 0u;
    b->poisoned = false;

    if (n == 0u) {
        return 0u;               /* a timeout with no characters is not a frame */
    }
    if (bad || n > cap) {
        b->drops++;
        return 0u;
    }
    b->frames++;
    memcpy(out, b->buf, n);
    return n;
}

void o2p_buart_send(o2p_buart_t *b, o2p_buart_t *peer, const uint8_t *buf,
                    size_t len)
{
    if (len == 0u) {
        return;
    }
    USART_TypeDef *u = b->usart;
    const uint32_t t0 = o2p_millis();

    if (b->drives_de) {
        de_assert();
        re_disable();   /* do not accumulate our own transmission */
    }
    for (size_t i = 0; i < len; i++) {
        while ((u->ISR & USART_ISR_TXE_TXFNF) == 0u) {
            if (peer != NULL) {
                o2p_buart_accumulate(peer);
            }
            if (o2p_elapsed(t0, TX_TIMEOUT_MS)) {
                goto done;
            }
        }
        u->TDR = buf[i];
    }
    /* TC, not TXE: TXE only means the holding register is free, and releasing
     * DE there truncates the last character on the wire. */
    while ((u->ISR & USART_ISR_TC) == 0u) {
        if (peer != NULL) {
            o2p_buart_accumulate(peer);
        }
        if (o2p_elapsed(t0, TX_TIMEOUT_MS)) {
            break;
        }
    }
done:
    /* One release, on every path including the timeouts. DE stuck high does
     * not merely mute this board - it drives the shared cable and silences
     * every other node on it. /RE goes back low in the same breath, or the
     * bridge would be deaf to the reply it exists to carry. */
    if (b->drives_de) {
        de_release();
        re_enable();
    }
    u->ICR = USART_ICR_TCCF;
}
