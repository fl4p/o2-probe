#include "modbus_rtu.h"

#include "board_pins.h"
#include "mcu.h"

#include <string.h>

static uint8_t s_rx[O2P_MB_MAX_ADU];
static volatile uint16_t s_rx_len;
static volatile bool s_frame_ready;

static uint8_t s_tx[O2P_MB_MAX_ADU];
static volatile uint16_t s_tx_len;
static volatile uint16_t s_tx_pos;
static volatile bool s_tx_active;
static volatile uint32_t s_tx_start_ms;

static volatile uint16_t s_crc_errors;
static volatile uint16_t s_frame_errors;

static uint8_t s_own_addr = 3u;

static uint32_t baud_from_code(uint8_t code)
{
    switch (code) {
    case O2P_BAUD_19200: return 19200u;
    case O2P_BAUD_38400: return 38400u;
    default:             return 9600u;
    }
}

/* Bits per character on the wire, including start and stop. With parity that
 * is 1 + 8 + 1 + 1 = 11; without it, 10. RTU's inter-frame silence is 3.5
 * characters, so the receiver timeout is ceil(3.5 * bits). At 8E1 that is
 * ceil(38.5) = 39 bit times, which at 9600 baud is 4.06 ms. */
static uint32_t rtor_bit_times(uint8_t parity_code)
{
    uint32_t bits = (parity_code == O2P_PARITY_NONE) ? 10u : 11u;
    return (bits * 7u + 1u) / 2u;   /* ceil(3.5 * bits) */
}

static void de_assert(void)
{
    GPIOC->BSRR = (1u << O2P_RS485_DE_PIN);
}

static void de_release(void)
{
    GPIOC->BSRR = (1u << (O2P_RS485_DE_PIN + 16u));
}

static void gpio_init(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN | RCC_IOPENR_GPIOCEN;

    /* DE first, and low, before anything can transmit. R7 (47k) already holds
     * the transceiver in receive through MCU reset; this keeps it there. */
    de_release();
    GPIOC->OTYPER &= ~(1u << O2P_RS485_DE_PIN);
    GPIOC->OSPEEDR |= (3u << (O2P_RS485_DE_PIN * 2u));
    GPIOC->MODER = (GPIOC->MODER & ~(3u << (O2P_RS485_DE_PIN * 2u))) |
                   (1u << (O2P_RS485_DE_PIN * 2u));

    const uint32_t tx = O2P_RS485_TX_PIN, rx = O2P_RS485_RX_PIN;
    for (unsigned i = 0; i < 2u; i++) {
        uint32_t p = (i == 0u) ? tx : rx;
        GPIOA->OSPEEDR |= (3u << (p * 2u));
        GPIOA->AFR[p >> 3] = (GPIOA->AFR[p >> 3] & ~(0xFu << ((p & 7u) * 4u))) |
                             (1u << ((p & 7u) * 4u));   /* AF1 = USART1 */
        GPIOA->MODER = (GPIOA->MODER & ~(3u << (p * 2u))) | (2u << (p * 2u));
    }
}

static void usart_configure(const o2p_config_t *cfg)
{
    USART1->CR1 = 0u;   /* disable while reconfiguring */

    uint32_t brr = (O2P_SYSCLK_HZ + baud_from_code(cfg->baud_code) / 2u) /
                   baud_from_code(cfg->baud_code);
    USART1->BRR = brr;

    /* RTOR holds the receiver timeout in bit times; RTOEN in CR2 enables it. */
    USART1->RTOR = rtor_bit_times(cfg->parity_code);
    USART1->CR2 = USART_CR2_RTOEN;
    USART1->CR3 = 0u;

    uint32_t cr1 = USART_CR1_RE | USART_CR1_TE | USART_CR1_RXNEIE_RXFNEIE |
                   USART_CR1_RTOIE | USART_CR1_TCIE;
    if (cfg->parity_code != O2P_PARITY_NONE) {
        /* 8 data bits PLUS parity is a 9-bit word: M[1:0] = 01. Getting this
         * wrong costs the parity bit off the data, and the bus is 8E1
         * (tech/RS485-LS-SMT100.md:277). */
        cr1 |= USART_CR1_M0 | USART_CR1_PCE;
        if (cfg->parity_code == O2P_PARITY_ODD) {
            cr1 |= USART_CR1_PS;
        }
    }
    USART1->CR1 = cr1 | USART_CR1_UE;

    s_own_addr = cfg->slave_addr;
}

void o2p_modbus_init(const o2p_config_t *cfg)
{
    RCC->APBENR2 |= RCC_APBENR2_USART1EN;
    gpio_init();
    s_rx_len = 0u;
    s_frame_ready = false;
    s_tx_active = false;
    usart_configure(cfg);
    NVIC_SetPriority(USART1_IRQn, 1u);
    NVIC_EnableIRQ(USART1_IRQn);
}

void o2p_modbus_reconfigure(const o2p_config_t *cfg)
{
    NVIC_DisableIRQ(USART1_IRQn);
    de_release();
    s_tx_active = false;
    s_rx_len = 0u;
    s_frame_ready = false;
    usart_configure(cfg);
    NVIC_EnableIRQ(USART1_IRQn);
}

bool o2p_modbus_tx_busy(void)
{
    return s_tx_active;
}

uint16_t o2p_modbus_crc_errors(void) { return s_crc_errors; }
uint16_t o2p_modbus_frame_errors(void) { return s_frame_errors; }

void USART1_IRQHandler(void)
{
    uint32_t isr = USART1->ISR;

    /* Line errors. Clearing them and dropping the partial frame is the whole
     * response: a framing or parity error means we did not hear the master
     * correctly, and answering a half-heard request is worse than silence. */
    if ((isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE | USART_ISR_PE)) != 0u) {
        USART1->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF | USART_ICR_PECF;
        s_rx_len = 0u;
        if (s_frame_errors != 0xFFFFu) {
            s_frame_errors++;
        }
        /* Fall through: RXNE may still hold the byte that arrived with the
         * error, and it must be drained or the flag never clears. */
    }

    if ((isr & USART_ISR_RXNE_RXFNE) != 0u) {
        uint8_t b = (uint8_t)USART1->RDR;
        /* Never overwrite a frame the main loop has not consumed, and never
         * run off the end of the buffer. An over-long frame is truncated to
         * "too long", which fails the CRC check and is dropped. */
        if (!s_frame_ready && s_rx_len < O2P_MB_MAX_ADU) {
            s_rx[s_rx_len++] = b;
        } else if (s_rx_len >= O2P_MB_MAX_ADU) {
            s_rx_len = O2P_MB_MAX_ADU;   /* saturate, stay flagged as too long */
        }
    }

    if ((isr & USART_ISR_RTOF) != 0u) {
        USART1->ICR = USART_ICR_RTOCF;
        if (!s_frame_ready && s_rx_len > 0u) {
            s_frame_ready = true;
        } else {
            s_rx_len = 0u;
        }
    }

    if ((isr & USART_ISR_TC) != 0u) {
        USART1->ICR = USART_ICR_TCCF;
        if (s_tx_active) {
            if (s_tx_pos < s_tx_len) {
                USART1->TDR = s_tx[s_tx_pos++];
            } else {
                /* TC means the last stop bit has left the shift register, so
                 * the transceiver can be released without truncating it.
                 * Releasing on TXE instead would cut the final character. */
                de_release();
                s_tx_active = false;
                /* Discard anything the transceiver echoed back into RX while
                 * we were driving the bus. */
                s_rx_len = 0u;
                s_frame_ready = false;
            }
        }
    }
}

static void transmit(const uint8_t *buf, uint16_t len)
{
    if (len == 0u) {
        return;
    }
    memcpy(s_tx, buf, len);
    s_tx_len = len;
    s_tx_pos = 0u;

    de_assert();
    /* The THVD1410 needs its enable to settle before the first bit; one
     * character time is far more than its ~70 ns propagation delay and costs
     * nothing at a 5-minute poll interval. */
    for (volatile unsigned d = 0; d < 200u; d++) { }

    s_tx_active = true;
    s_tx_start_ms = o2p_millis();
    USART1->ICR = USART_ICR_TCCF;
    USART1->TDR = s_tx[s_tx_pos++];
}

bool o2p_modbus_poll(o2p_regmap_t *rm)
{
    /* Backstop for a transmission that never completes - a clock glitch or a
     * lost TC would otherwise leave DE asserted and jam the shared bus for
     * every other device on the cable, permanently. 250 ms is longer than the
     * longest possible response (a 256-byte frame at 9600 8E1 is 293 ms...
     * so scale it with the frame we actually queued). */
    if (s_tx_active) {
        uint32_t worst_ms = 50u + ((uint32_t)s_tx_len * 11u * 1000u) /
                                      9600u;
        if (o2p_elapsed(s_tx_start_ms, worst_ms)) {
            de_release();
            s_tx_active = false;
            if (s_frame_errors != 0xFFFFu) {
                s_frame_errors++;
            }
        }
        return false;
    }

    if (!s_frame_ready) {
        return false;
    }

    uint16_t len = s_rx_len;
    o2p_mb_disposition_t d = o2p_mb_classify(s_rx, len, s_own_addr);
    if (d == O2P_MB_DROP) {
        /* Only count a CRC failure when the frame was long enough to have a
         * CRC and was addressed to us or to everyone; otherwise every frame
         * for the two SMT100s on this cable would inflate our error count. */
        if (len >= 4u && (s_rx[0] == s_own_addr || s_rx[0] == O2P_MB_ADDR_BROADCAST ||
                          s_rx[0] == O2P_MB_ADDR_DISCOVERY)) {
            if (s_crc_errors != 0xFFFFu) {
                s_crc_errors++;
            }
        }
    } else {
        o2p_mb_handlers_t h = {o2p_regmap_read, o2p_regmap_write, rm};
        uint8_t rsp[O2P_MB_MAX_ADU];
        size_t n = o2p_mb_dispatch(s_rx, len, s_own_addr, &h, rsp);
        if (n > 0u && d == O2P_MB_EXECUTE) {
            transmit(rsp, (uint16_t)n);
        }
    }

    s_rx_len = 0u;
    s_frame_ready = false;
    return true;
}
