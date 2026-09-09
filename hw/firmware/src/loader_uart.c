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

/* /RE, the Rev B split (PC7). ACTIVE LOW: low listens, high deafens.
 *
 * THE LOADER NEVER USES STANDBY. The only reason it touches this pin at all is
 * ECHO: on Rev A the single shared net deafened the receiver for the duration
 * of every transmission, so the loader never heard its own reply. With /RE left
 * low during a transmit the reply lands straight back in s_buf, the receiver
 * timeout frames it, and o2p_luart_poll() hands loader_main.c a frame that
 * carries this probe's OWN address and a valid CRC - which o2p_mb_classify()
 * duly returns as O2P_MB_EXECUTE. The loader would answer itself, and it would
 * do it while a technician is trying to reflash a potted probe. So /RE is
 * driven high with DE and low again on every exit path, byte-for-byte the Rev A
 * behaviour.
 *
 * Outside a transmission this pin is LOW, always. R45's 47k already holds it
 * there through reset, before any of this code runs; that is what makes the
 * loader reachable at all on a probe whose application is gone. */
static void re_disable(void)
{
    O2P_RS485_RE_PORT->BSRR = (1u << O2P_RS485_RE_PIN);
}

static void re_enable(void)
{
    O2P_RS485_RE_PORT->BSRR = (1u << (O2P_RS485_RE_PIN + 16u));
}

static void gpio_init(void)
{
    /* DE low before the pin becomes an output at all. R7's 47k already holds
     * the driver disabled through reset; this keeps it there while the loader
     * configures itself. */
    de_release();
    O2P_RS485_DE_PORT->OTYPER &= ~(1u << O2P_RS485_DE_PIN);
    O2P_RS485_DE_PORT->OSPEEDR |= (3u << (O2P_RS485_DE_PIN * 2u));
    O2P_RS485_DE_PORT->MODER =
        (O2P_RS485_DE_PORT->MODER & ~(3u << (O2P_RS485_DE_PIN * 2u))) |
        (1u << (O2P_RS485_DE_PIN * 2u));

    /* /RE low, likewise before MODER, so the receiver cannot blink off on the
     * way to becoming an output. R45's 47k held it there already. */
    re_enable();
    O2P_RS485_RE_PORT->OTYPER &= ~(1u << O2P_RS485_RE_PIN);
    O2P_RS485_RE_PORT->OSPEEDR |= (3u << (O2P_RS485_RE_PIN * 2u));
    O2P_RS485_RE_PORT->MODER =
        (O2P_RS485_RE_PORT->MODER & ~(3u << (O2P_RS485_RE_PIN * 2u))) |
        (1u << (O2P_RS485_RE_PIN * 2u));

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
    /* The RTU inter-frame silence. ONE shared rule (modbus_pdu.h) rather than a
     * copy, and it has to stay shared - a loader that framed differently from
     * the application would be reachable at one baud rate and not the other,
     * which is precisely the strand this file's baud decode exists to avoid. */
    USART1->RTOR = o2p_mb_rtor_bit_times(baud, parity_code == O2P_PARITY_NONE);
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
    re_disable();       /* do not hear our own reply; see re_disable() above */
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
     * not merely mute this probe - it drives the shared cable and silences the
     * two SMT100s on it. /RE goes back low in the same breath: a loader that
     * exits this function deaf is a loader that cannot be talked to again, and
     * the whole point of this image is to be reachable when nothing else is. */
    de_release();
    re_enable();
    USART1->ICR = USART_ICR_TCCF;
}

void o2p_luart_deinit(void)
{
    de_release();
    re_enable();        /* hand the application a LISTENING transceiver */
    USART1->CR1 = 0u;
    /* Reset the peripheral rather than merely disabling it, so the
     * application's own init starts from the same register state it would
     * see after a power-on - no stale RTOR, no half-cleared status. */
    RCC->APBRSTR2 |= RCC_APBRSTR2_USART1RST;
    RCC->APBRSTR2 &= ~RCC_APBRSTR2_USART1RST;
}
