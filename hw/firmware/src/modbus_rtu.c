#include "modbus_rtu.h"

#include "board_pins.h"
#include "mcu.h"

#include <string.h>

/* How stale a received request may be before we refuse to answer it. The
 * normal worst case is one ADS1119 conversion, about 50 ms; anything near a
 * second means a blocking operation ran long, and the master has moved on. */
#define O2P_MB_RESPONSE_DEADLINE_MS 400u

/* gpio_init() configures TX and RX through one port pointer. */
_Static_assert(O2P_RS485_TX_PORT == O2P_RS485_RX_PORT,
               "USART1 TX and RX are no longer on the same GPIO bank");

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
/* Set when any byte of the frame being assembled arrived with a line error.
 * Cleared only by the receiver timeout that ends the frame. */
static volatile bool s_rx_poisoned;
/* When the completed frame was framed, for the response deadline below. */
static volatile uint32_t s_frame_ms;

static uint8_t s_own_addr = 3u;
static uint32_t s_baud = 9600u;
static volatile bool s_jam_suspected;

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

/* o2p_millis() is a plain read of a volatile counter, safe from the ISR. */
static inline uint32_t s_millis_snapshot(void)
{
    return o2p_millis();
}

static void de_assert(void)
{
    O2P_RS485_DE_PORT->BSRR = (1u << O2P_RS485_DE_PIN);
}

static void de_release(void)
{
    O2P_RS485_DE_PORT->BSRR = (1u << (O2P_RS485_DE_PIN + 16u));
}

/* /RE is ACTIVE LOW: low listens, high deafens the receiver. Rev A had it
 * shorted to DE, so these two functions were one function; Rev B splits them
 * onto PC6/PC7 and the DEFAULT BEHAVIOUR HERE IS UNCHANGED - re_disable() is
 * called exactly where the old shared net went high (transmit) and
 * re_restore() exactly where it went low again. */
static void re_enable(void)
{
    O2P_RS485_RE_PORT->BSRR = (1u << (O2P_RS485_RE_PIN + 16u));
}

static void re_disable(void)
{
    O2P_RS485_RE_PORT->BSRR = (1u << O2P_RS485_RE_PIN);
}

/* Set when the caller has explicitly asked for transceiver standby. Nothing in
 * this file sets it; main.c does not call it yet. It exists so that the return
 * from a transmission goes back to the state the SYSTEM asked for rather than
 * unconditionally re-enabling the receiver - otherwise a standby probe would
 * silently come back to 700 uA the first time it answered a broadcast. */
static volatile bool s_rx_standby;

/* The one place that decides /RE outside a transmission. */
static void re_restore(void)
{
    if (s_rx_standby) {
        re_disable();
    } else {
        re_enable();
    }
}

static void gpio_init(void)
{
    /* DE first, and low, before anything can transmit. R7 (47k) already holds
     * the transceiver's DRIVER off through MCU reset; this keeps it there. */
    de_release();
    O2P_RS485_DE_PORT->OTYPER &= ~(1u << O2P_RS485_DE_PIN);
    O2P_RS485_DE_PORT->OSPEEDR |= (3u << (O2P_RS485_DE_PIN * 2u));
    O2P_RS485_DE_PORT->MODER = (O2P_RS485_DE_PORT->MODER & ~(3u << (O2P_RS485_DE_PIN * 2u))) |
                   (1u << (O2P_RS485_DE_PIN * 2u));

    /* /RE next, and low, so the receiver is on before the USART is. R45 (47k)
     * already holds it there through reset - that is what keeps a probe with
     * no running application reachable over the bus - so this only takes over
     * the same level actively. Written BEFORE MODER for the same reason DE is:
     * the pin must never glitch high on its way to becoming an output. */
    re_restore();
    O2P_RS485_RE_PORT->OTYPER &= ~(1u << O2P_RS485_RE_PIN);
    O2P_RS485_RE_PORT->OSPEEDR |= (3u << (O2P_RS485_RE_PIN * 2u));
    O2P_RS485_RE_PORT->MODER = (O2P_RS485_RE_PORT->MODER & ~(3u << (O2P_RS485_RE_PIN * 2u))) |
                   (1u << (O2P_RS485_RE_PIN * 2u));

    const uint32_t tx = O2P_RS485_TX_PIN, rx = O2P_RS485_RX_PIN;
    for (unsigned i = 0; i < 2u; i++) {
        uint32_t p = (i == 0u) ? tx : rx;
        O2P_RS485_TX_PORT->OSPEEDR |= (3u << (p * 2u));
        O2P_RS485_TX_PORT->AFR[p >> 3] = (O2P_RS485_TX_PORT->AFR[p >> 3] & ~(0xFu << ((p & 7u) * 4u))) |
                             (1u << ((p & 7u) * 4u));   /* AF1 = USART1 */
        O2P_RS485_TX_PORT->MODER = (O2P_RS485_TX_PORT->MODER & ~(3u << (p * 2u))) | (2u << (p * 2u));
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
    s_baud = baud_from_code(cfg->baud_code);
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
    re_restore();
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
bool o2p_modbus_bus_jam_suspected(void) { return s_jam_suspected; }

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
            /* Stamp the frame HERE, in the interrupt that completed it. The
             * deadline below is "how long has this request been waiting for
             * the main loop", and a timestamp that is never taken reads as
             * zero - which is 400 ms in the past from the first half-second
             * of uptime onwards, so every frame is dropped and the probe
             * answers nothing, forever. */
            s_frame_ms = o2p_millis();
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
                re_restore();
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

    /* Order matters only in that both must be set before the first bit. This
     * pair reproduces Rev A's single-net behaviour exactly: the old shared net
     * going high asserted DE and de-asserted /RE in the same instant. */
    de_assert();
    re_disable();
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
    /* Backstop for a transmission that never completes: a lost TC would
     * otherwise leave DE asserted and jam the shared cable for every other
     * device on it, permanently.
     *
     * The bound is computed from the CONFIGURED baud rate, not a hardcoded
     * one. Deriving it from 9600 happens to be conservative today because
     * every supported rate is faster - but that is an accident of the current
     * baud table, and a future 4800 entry would silently make the backstop
     * fire mid-frame and truncate the reply. */
    if (s_tx_active) {
        uint32_t bits = (uint32_t)s_tx_len * 11u;
        uint32_t worst_ms = 50u + (bits * 1000u) / (s_baud ? s_baud : 9600u);
        if (o2p_elapsed(s_tx_start_ms, worst_ms)) {
            de_release();
            re_restore();
            s_tx_active = false;
            if (s_frame_errors != 0xFFFFu) {
                s_frame_errors++;
            }
        }
        return false;
    }

    /* DE must be LOW whenever we are not transmitting. Checked here, outside
     * the transmit branch, because the TC handler clears s_tx_active in the
     * same breath as it releases DE - so a release that did not take effect
     * would never be examined again, and the probe would drive the shared
     * cable forever while the sampler happily kept feeding the watchdog.
     *
     * IDR, not ODR: ODR only reports what we asked for. IDR is the pin. */
    if ((O2P_RS485_DE_PORT->IDR & (1u << O2P_RS485_DE_PIN)) != 0u) {
        de_release();                       /* idempotent; try again */
        re_restore();
        if ((O2P_RS485_DE_PORT->IDR & (1u << O2P_RS485_DE_PIN)) != 0u) {
            /* Still driven after a fresh release: this CPU can no longer free
             * the bus, so stop pretending it can. main() withholds the
             * watchdog feed on this, making the reset - and R7's 47k
             * pull-down - the release path that needs no code to run. */
            s_jam_suspected = true;
        }
    }

    if (!s_frame_ready) {
        return false;
    }

    uint16_t len = s_rx_len;

    /* Drop a request we took too long to reach. The Dragino master's Modbus
     * timeout is about 1 s; a reply sent after it has given up does not just
     * go unheard, it lands on top of whatever transaction the master started
     * next and corrupts another slave's answer. Better one lost poll than a
     * frame injected into someone else's exchange. */
    if (o2p_elapsed(s_frame_ms, O2P_MB_RESPONSE_DEADLINE_MS)) {
        s_rx_len = 0u;
        s_frame_ready = false;
        if (s_frame_errors != 0xFFFFu) {
            s_frame_errors++;
        }
        return false;
    }

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

/* ---- Transceiver standby -------------------------------------------------
 *
 * THVD1410 ICC, SLLSEY3E Electrical Characteristics:
 *   /RE=0, DE=0                driver off, receiver on   700 uA typ / 960 max
 *   /RE=VCC, DE=0, D open      BOTH DISABLED             0.1 uA typ / 1 uA max
 *
 * NOTHING CALLS THIS YET, deliberately. Wiring standby into the sampler's
 * control flow is a protocol decision, not a driver decision: a deaf probe
 * cannot be polled by the Modbus master and cannot be reached by the RS-485
 * field updater, and POWER-BUDGET.md sets out why an unsolicited-transmit
 * scheme collides with a 60 s master poll at a fixed phase. This function only
 * makes the state REACHABLE, which Rev A hardware was not.
 *
 * What it costs and what it saves, so the caller is not misled:
 *  - The saving is the receiver's 700 uA.
 *  - The floor is NOT 0.1 uA on this board. Commanding standby drives /RE high
 *    against R45's 47k pull-down, which is 3.3 V / 47k = 70 uA. Net saving is
 *    therefore about 630 uA, a 10x cut on the transceiver, not 7000x. R45 is
 *    not optional - it is the reason a bootloader-only probe is still
 *    reachable - so this is a property of the board, not of this code.
 *  - "D open" in the datasheet row means the driver input idle. USART1 holds
 *    TX high when it is not shifting, matching the D pin's internal pull-up,
 *    so no extra current flows there.
 *
 * Entering standby does NOT touch USART1. The receiver stops delivering edges,
 * so no frame arrives; RXNE/RTOF simply never fire. Leaving standby is a
 * single pin write and the part's enable time is tens of nanoseconds, far
 * inside one 1.146 ms character at 9600 baud - but a frame already in flight
 * when standby is left is lost, so the caller must expect to miss one poll.
 *
 * Refused while a transmission is in flight: /RE is held high for the duration
 * of a transmit and re_restore() decides its level when TC lands, so flipping
 * the flag mid-frame would take effect at an unpredictable moment. Returns
 * true if the requested state is now in force.
 */
bool o2p_modbus_rx_standby(bool on)
{
    if (s_tx_active) {
        return false;
    }
    s_rx_standby = on;
    re_restore();
    return true;
}

bool o2p_modbus_rx_standby_active(void)
{
    return s_rx_standby;
}
