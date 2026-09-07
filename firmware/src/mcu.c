#include "mcu.h"

static volatile uint32_t s_millis;
static uint16_t s_reset_cause;
static bool s_power_cycled;

void SysTick_Handler(void)
{
    s_millis++;
}

uint32_t o2p_millis(void)
{
    return s_millis;
}

void o2p_delay_ms(uint32_t ms)
{
    uint32_t t0 = o2p_millis();
    while (!o2p_elapsed(t0, ms)) {
        __WFI();
    }
}

void o2p_clock_init(void)
{
    /* Latch and clear the reset cause before anything else can reset us
     * again. RCC_CSR flags are sticky across resets, so leaving them set
     * makes the next power-on look like whatever happened last time. */
    uint32_t csr = RCC->CSR;
    s_reset_cause = (uint16_t)(csr >> 24);
    s_power_cycled = (csr & (RCC_CSR_PWRRSTF | RCC_CSR_PINRSTF)) != 0u;
    RCC->CSR |= RCC_CSR_RMVF;

    /* HSI16 on and selected, HSIDIV = /1 -> SYSCLK = 16 MHz.
     * This is the reset state on STM32G0, but stating it explicitly means a
     * bootloader that left the clock somewhere else cannot hand us a running
     * PLL and a wrong baud rate. */
    RCC->CR |= RCC_CR_HSION;
    while ((RCC->CR & RCC_CR_HSIRDY) == 0u) {
    }
    RCC->CR &= ~RCC_CR_HSIDIV;                 /* HSIDIV = 000 = /1 */
    RCC->CFGR &= ~RCC_CFGR_SW;                 /* SW = 000 = HSISYS */
    while ((RCC->CFGR & RCC_CFGR_SWS) != 0u) {
    }
    /* 16 MHz needs zero flash wait states in range 1 (RM0444 Table 'Number of
     * wait states'), which is the reset value; assert it rather than assume. */
    FLASH->ACR &= ~FLASH_ACR_LATENCY;   /* latency field 0 = zero wait states */

    /* Every GPIO bank this board uses, enabled once. Drivers then reference
     * ports only through the board_pins.h bindings, so moving a net between
     * banks cannot leave a driver configuring the old one. */
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN | RCC_IOPENR_GPIOBEN | RCC_IOPENR_GPIOCEN;

    SystemCoreClock = O2P_SYSCLK_HZ;
    SysTick_Config(O2P_SYSCLK_HZ / 1000u);
}

uint16_t o2p_reset_cause(void)
{
    return s_reset_cause;
}

bool o2p_reset_was_power_cycle(void)
{
    return s_power_cycled;
}

void o2p_wdt_init(void)
{
    /* LSI is nominally 32 kHz with a wide tolerance. Prescaler /64 and a
     * reload of 2047 gives (2047+1) * 64 / 32000 = 4.096 s nominal, roughly
     * 2.7-6.5 s over the LSI's spread. That is long enough that a 2 KB flash erase (about 22 ms
     * typical, 40 ms max) cannot trip it, and short enough that a wedged
     * probe returns to service within one 5-minute poll interval.
     *
     * What this watchdog must NOT do is mask a stuck sensor: it is fed from
     * the main loop only while the sample cycle is still completing, so a
     * probe that stops sampling resets instead of quietly serving stale
     * registers forever. See main.c.
     */
    IWDG->KR = 0x5555u;                 /* unlock PR/RLR */
    /* PR[2:0] = 100 is /64. NOT (PR_2 | PR_1): that is 110 = /256, which this
     * code had, giving a 16.384 s timeout while every comment and document
     * claimed 4.096 s - four times longer to release a jammed shared bus.
     * IWDG_PRESCALER_64 in stm32g0xx_hal_iwdg.h:86 is IWDG_PR_PR_2 alone. */
    IWDG->PR = IWDG_PR_PR_2;
    IWDG->RLR = 2047u;
    while (IWDG->SR != 0u) {
    }
    IWDG->KR = 0xCCCCu;                 /* start; cannot be stopped afterwards */
}

void o2p_wdt_feed(void)
{
    IWDG->KR = 0xAAAAu;
}
