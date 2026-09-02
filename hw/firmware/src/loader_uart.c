#include "loader_uart.h"

#include "board_pins.h"
#include "mcu.h"
#include "modbus_pdu.h"
#include "regmap.h"   /* O2P_PARITY_* */

#include <string.h>

/* A transmission that never completes must not hold DE - and with it the
 * whole cable, including the two SMT100s - forever. 256 bytes at 9600 8E1 is
 * 293 ms; anything past 500 ms means the USART is not shifting. */
#define TX_TIMEOUT_MS 500u

static uint8_t s_buf[O2P_MB_MAX_ADU];
static size_t s_len;
static bool s_poisoned;

static void de_assert(void)
{
    O2P_RS485_DE_PORT->BSRR = (1u << O2P_RS485_DE_PIN);
}

static void de_release(void)
{
    O2P_RS485_DE_PORT->BSRR = (1u << (O2P_RS485_DE_PIN + 16u));
}

static void gpio_init(void)
{
    /* DE low before the pin becomes an output at all. R7's 47k already holds
     * the transceiver in receive through reset; this keeps it there while the
     * loader configures itself. */
    de_release();
    O2P_RS485_DE_PORT->OTYPER &= ~(1u << O2P_RS485_DE_PIN);
    O2P_RS485_DE_PORT->OSPEEDR |= (3u << (O2P_RS485_DE_PIN * 2u));
    O2P_RS485_DE_PORT->MODER =
        (O2P_RS485_DE_PORT->MODER & ~(3u << (O2P_RS485_DE_PIN * 2u))) |
        (1u << (O2P_RS485_DE_PIN * 2u));

    const uint32_t pins[2] = { O2P_RS485_TX_PIN, O2P_RS485_RX_PIN };
    for (unsigned i = 0; i < 2u; i++) {
        uint32_t p = pins[i];
        O2P_RS485_TX_PORT->OSPEEDR |= (3u << (p * 2u));
        O2P_RS485_TX_PORT->AFR[p >> 3] =
            (O2P_RS485_TX_PORT->AFR[p >> 3] & ~(0xFu << ((p & 7u) * 4u))) |
            ((uint32_t)O2P_RS485_TX_AF << ((p & 7u) * 4u));
        O2P_RS485_TX_PORT->MODER =
            (O2P_RS485_TX_PORT->MODER & ~(3u << (p * 2u))) | (2u << (p * 2u));
    }
}

void o2p_luart_init(uint32_t baud, uint8_t parity_code)
{
    RCC->APBENR2 |= RCC_APBENR2_USART1EN;
    gpio_init();

    s_len = 0u;
    s_poisoned = false;

    USART1->CR1 = 0u;
    USART1->BRR = (O2P_SYSCLK_HZ + baud / 2u) / baud;
    /* 3.5 character times, the RTU inter-frame silence: 11 bits per character
     * with parity, 10 without. Same arithmetic as modbus_rtu.c, and it has to
     * stay the same - a loader that framed differently from the application
     * would be reachable at one baud rate and not the other. */
    USART1->RTOR = ((parity_code == O2P_PARITY_NONE ? 10u : 11u) * 7u + 1u) / 2u;
    USART1->CR2 = USART_CR2_RTOEN;
    USART1->CR3 = 0u;

    uint32_t cr1 = USART_CR1_RE | USART_CR1_TE;
    if (parity_code != O2P_PARITY_NONE) {
        cr1 |= USART_CR1_M0 | USART_CR1_PCE;   /* 8 data + parity = 9-bit word */
        if (parity_code == O2P_PARITY_ODD) {
            cr1 |= USART_CR1_PS;
        }
    }
    USART1->CR1 = cr1 | USART_CR1_UE;
}

size_t o2p_luart_poll(uint8_t *out, size_t cap)
{
    uint32_t isr = USART1->ISR;

    while ((isr & USART_ISR_RXNE_RXFNE) != 0u) {
        /* Read the error flags that belong to THIS character before RDR is
         * read: reading RDR is what clears RXNE and advances to the next. */
        const bool bad = (isr & (USART_ISR_PE | USART_ISR_FE | USART_ISR_NE)) != 0u;
        uint8_t b = (uint8_t)USART1->RDR;
        if (bad) {
            USART1->ICR = USART_ICR_PECF | USART_ICR_FECF | USART_ICR_NECF;
            s_poisoned = true;
        }
        if (s_len < sizeof(s_buf)) {
            s_buf[s_len++] = b;
        } else {
            /* Longer than any legal ADU. Poison rather than wrap: a frame
             * assembled from the tail of an overrun is not a frame. */
            s_poisoned = true;
        }
        isr = USART1->ISR;
    }

    if ((isr & USART_ISR_ORE) != 0u) {
        USART1->ICR = USART_ICR_ORECF;
        s_poisoned = true;
    }

    if ((isr & USART_ISR_RTOF) == 0u) {
        return 0u;
    }
    USART1->ICR = USART_ICR_RTOCF;

    const size_t n = s_len;
    const bool bad = s_poisoned;
    s_len = 0u;
    s_poisoned = false;

    if (bad || n == 0u || n > cap) {
        return 0u;
    }
    memcpy(out, s_buf, n);
    return n;
}

void o2p_luart_send(const uint8_t *buf, size_t len)
{
    if (len == 0u) {
        return;
    }
    const uint32_t t0 = o2p_millis();
    de_assert();
    for (size_t i = 0; i < len; i++) {
        while ((USART1->ISR & USART_ISR_TXE_TXFNF) == 0u) {
            if (o2p_elapsed(t0, TX_TIMEOUT_MS)) {
                goto done;
            }
        }
        USART1->TDR = buf[i];
    }
    /* TC, not TXE: TXE only means the holding register is free, and releasing
     * DE there truncates the last character on the wire. */
    while ((USART1->ISR & USART_ISR_TC) == 0u) {
        if (o2p_elapsed(t0, TX_TIMEOUT_MS)) {
            break;
        }
    }
done:
    /* One release, on every path including the timeouts. DE stuck high does
     * not merely mute this probe: PC6 drives DE and ~RE together, so it
     * silences the two SMT100s on the same cable. */
    de_release();
    USART1->ICR = USART_ICR_TCCF;
}

void o2p_luart_deinit(void)
{
    de_release();
    USART1->CR1 = 0u;
    /* Reset the peripheral rather than merely disabling it, so the
     * application's own init starts from the same register state it would
     * see after a power-on - no stale RTOR, no half-cleared status. */
    RCC->APBRSTR2 |= RCC_APBRSTR2_USART1RST;
    RCC->APBRSTR2 &= ~RCC_APBRSTR2_USART1RST;
}
