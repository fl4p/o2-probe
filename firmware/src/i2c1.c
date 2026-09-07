#include "i2c1.h"

#include "board_pins.h"
#include "mcu.h"

/* I2CCLK = PCLK = 16 MHz, 100 kHz standard mode, analog filter enabled.
 * Value from the RM0444 I2C_TIMINGR examples for a 16 MHz peripheral clock -
 * PRESC=3, SCLDEL=0, SDADEL=4, SCLH=0x0F, SCLL=0x13. */
#define O2P_I2C_TIMINGR 0x30420F13u

/* A single byte at 100 kHz is 90 us, and the longest transfer here is a
 * 6-byte SHT45 read plus addressing, well under 1 ms. 25 ms is generous
 * enough to never fire on a healthy bus and short enough that four dead
 * devices still leave the 1 Hz sample loop with time to spare. */
#define O2P_I2C_TIMEOUT_MS 25u

/* This driver configures both I2C pins through one port pointer, so they must
 * actually be on the same bank. Nothing else would notice if a future
 * schematic moved SDA to another port - the static assertions in
 * board_pins.h compare package pin NUMBERS, not banks. */
_Static_assert(O2P_I2C_SCL_PORT == O2P_I2C_SDA_PORT,
               "I2C SCL and SDA are no longer on the same GPIO bank");

static uint16_t s_errors;

static void bump_errors(void)
{
    if (s_errors != 0xFFFFu) {
        s_errors++;   /* saturate: a wrapped counter reads as "healthy again" */
    }
}

void o2p_i2c1_init(void)
{
    RCC->APBENR1 |= RCC_APBENR1_I2C1EN;

    /* PB6/PB7 to AF6, open-drain, no internal pull-up: R10/R11 (4.7k) are
     * fitted externally and the internal ~40k would only weaken the edges. */
    const uint32_t pins[2] = {O2P_I2C_SCL_PIN, O2P_I2C_SDA_PIN};
    for (unsigned i = 0; i < 2u; i++) {
        uint32_t p = pins[i];
        O2P_I2C_SCL_PORT->OTYPER |= (1u << p);
        O2P_I2C_SCL_PORT->OSPEEDR |= (3u << (p * 2u));
        O2P_I2C_SCL_PORT->PUPDR &= ~(3u << (p * 2u));
        O2P_I2C_SCL_PORT->AFR[p >> 3] = (O2P_I2C_SCL_PORT->AFR[p >> 3] & ~(0xFu << ((p & 7u) * 4u))) |
                             (6u << ((p & 7u) * 4u));
        O2P_I2C_SCL_PORT->MODER = (O2P_I2C_SCL_PORT->MODER & ~(3u << (p * 2u))) | (2u << (p * 2u));
    }

    I2C1->CR1 = 0u;
    I2C1->TIMINGR = O2P_I2C_TIMINGR;
    I2C1->CR1 = I2C_CR1_PE;
}

uint16_t o2p_i2c1_error_count(void)
{
    return s_errors;
}

void o2p_i2c1_bus_recover(void)
{
    /* Drive nine clocks with SDA released, then a STOP. A slave that was
     * mid-byte when we reset finishes its transfer and lets go. */
    I2C1->CR1 &= ~I2C_CR1_PE;

    const uint32_t scl = O2P_I2C_SCL_PIN, sda = O2P_I2C_SDA_PIN;
    for (unsigned i = 0; i < 2u; i++) {
        uint32_t p = (i == 0u) ? scl : sda;
        O2P_I2C_SCL_PORT->MODER = (O2P_I2C_SCL_PORT->MODER & ~(3u << (p * 2u))) | (1u << (p * 2u)); /* output */
        O2P_I2C_SCL_PORT->BSRR = (1u << p);   /* released (open-drain high) */
    }
    for (unsigned i = 0; i < 9u; i++) {
        O2P_I2C_SCL_PORT->BSRR = (1u << (scl + 16u));
        for (volatile unsigned d = 0; d < 80u; d++) { }
        O2P_I2C_SCL_PORT->BSRR = (1u << scl);
        for (volatile unsigned d = 0; d < 80u; d++) { }
    }
    /* STOP: SDA low then high while SCL is high. */
    O2P_I2C_SCL_PORT->BSRR = (1u << (sda + 16u));
    for (volatile unsigned d = 0; d < 80u; d++) { }
    O2P_I2C_SCL_PORT->BSRR = (1u << sda);

    o2p_i2c1_init();
    bump_errors();
}

/* Wait for any of `mask` in ISR, or a NACK, or the timeout. */
static o2p_i2c_status_t wait_isr(uint32_t mask)
{
    uint32_t t0 = o2p_millis();
    for (;;) {
        uint32_t isr = I2C1->ISR;
        if ((isr & I2C_ISR_NACKF) != 0u) {
            /* A NACK ends the transfer. With AUTOEND the peripheral raises
             * STOP by itself; finish() still forces one and waits for STOPF,
             * so the bus is released either way. Clear the flag here so the
             * STOPF wait that follows does not immediately see it again. */
            I2C1->ICR = I2C_ICR_NACKCF;
            return O2P_I2C_NACK;
        }
        if ((isr & mask) != 0u) {
            return O2P_I2C_OK;
        }
        if (o2p_elapsed(t0, O2P_I2C_TIMEOUT_MS)) {
            return O2P_I2C_TIMEOUT;
        }
    }
}

static o2p_i2c_status_t start(uint8_t addr7, size_t len, bool read, bool autoend)
{
    if (len > 255u) {
        return O2P_I2C_ARG;
    }
    if ((I2C1->ISR & I2C_ISR_BUSY) != 0u) {
        o2p_i2c1_bus_recover();
        if ((I2C1->ISR & I2C_ISR_BUSY) != 0u) {
            return O2P_I2C_BUSY;
        }
    }
    uint32_t cr2 = ((uint32_t)addr7 << 1) |
                   ((uint32_t)len << I2C_CR2_NBYTES_Pos) |
                   I2C_CR2_START;
    if (read) {
        cr2 |= I2C_CR2_RD_WRN;
    }
    if (autoend) {
        cr2 |= I2C_CR2_AUTOEND;
    }
    I2C1->ICR = I2C_ICR_NACKCF | I2C_ICR_STOPCF | I2C_ICR_BERRCF |
                I2C_ICR_ARLOCF | I2C_ICR_OVRCF;
    I2C1->CR2 = cr2;
    return O2P_I2C_OK;
}

static o2p_i2c_status_t push(const uint8_t *buf, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        o2p_i2c_status_t st = wait_isr(I2C_ISR_TXIS);
        if (st != O2P_I2C_OK) {
            return st;
        }
        I2C1->TXDR = buf[i];
    }
    return O2P_I2C_OK;
}

static o2p_i2c_status_t pull(uint8_t *buf, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        o2p_i2c_status_t st = wait_isr(I2C_ISR_RXNE);
        if (st != O2P_I2C_OK) {
            return st;
        }
        buf[i] = (uint8_t)I2C1->RXDR;
    }
    return O2P_I2C_OK;
}

static o2p_i2c_status_t finish(o2p_i2c_status_t st)
{
    if (st != O2P_I2C_OK) {
        /* Force a STOP so the bus is released even on a NACK or timeout;
         * leaving it held would take every other device down too. */
        I2C1->CR2 |= I2C_CR2_STOP;
        (void)wait_isr(I2C_ISR_STOPF);
        I2C1->ICR = I2C_ICR_STOPCF;
        bump_errors();
        return st;
    }
    o2p_i2c_status_t s = wait_isr(I2C_ISR_STOPF);
    I2C1->ICR = I2C_ICR_STOPCF;
    if (s != O2P_I2C_OK) {
        bump_errors();
    }
    return s;
}

o2p_i2c_status_t o2p_i2c1_write(uint8_t addr7, const uint8_t *buf, size_t len)
{
    if (buf == NULL && len != 0u) {
        return O2P_I2C_ARG;
    }
    o2p_i2c_status_t st = start(addr7, len, false, true);
    if (st != O2P_I2C_OK) {
        bump_errors();
        return st;
    }
    return finish(push(buf, len));
}

o2p_i2c_status_t o2p_i2c1_read(uint8_t addr7, uint8_t *buf, size_t len)
{
    if (buf == NULL || len == 0u) {
        return O2P_I2C_ARG;
    }
    o2p_i2c_status_t st = start(addr7, len, true, true);
    if (st != O2P_I2C_OK) {
        bump_errors();
        return st;
    }
    return finish(pull(buf, len));
}

o2p_i2c_status_t o2p_i2c1_write_read(uint8_t addr7,
                                     const uint8_t *wbuf, size_t wlen,
                                     uint8_t *rbuf, size_t rlen)
{
    if (wbuf == NULL || wlen == 0u || rbuf == NULL || rlen == 0u) {
        return O2P_I2C_ARG;
    }
    /* Write phase without AUTOEND so the repeated START can follow. */
    o2p_i2c_status_t st = start(addr7, wlen, false, false);
    if (st != O2P_I2C_OK) {
        bump_errors();
        return st;
    }
    st = push(wbuf, wlen);
    if (st != O2P_I2C_OK) {
        return finish(st);
    }
    st = wait_isr(I2C_ISR_TC);
    if (st != O2P_I2C_OK) {
        return finish(st);
    }
    /* Repeated START for the read phase. */
    I2C1->CR2 = ((uint32_t)addr7 << 1) | ((uint32_t)rlen << I2C_CR2_NBYTES_Pos) |
                I2C_CR2_RD_WRN | I2C_CR2_START | I2C_CR2_AUTOEND;
    return finish(pull(rbuf, rlen));
}
