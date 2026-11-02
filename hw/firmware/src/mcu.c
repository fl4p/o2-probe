#include "mcu.h"

#include "flash_map.h"
#include "regmap.h"

static volatile uint32_t s_millis;
static uint16_t s_reset_cause;
static bool s_power_cycled;

#if O2P_DEBUG_ENABLE
volatile bool g_exec_active = false;
volatile uint32_t g_exec_start_ms = 0u;
volatile uint32_t g_exec_timeout_ms = 50u;

__attribute__((weak)) void o2p_exec_timeout_trampoline(void) {}
__attribute__((weak)) void o2p_exec_fault_trampoline(void) {}

void o2p_systick_c_handler(uint32_t *stack_frame, uint32_t exc_return)
{
    s_millis++;
    uint32_t sp = (uint32_t)stack_frame;
    if (g_exec_active && (exc_return & (1u << 3)) != 0u &&
        (sp & 3u) == 0u && sp >= 0x20000000u && sp <= (0x20009000u - 32u) &&
        o2p_elapsed(g_exec_start_ms, g_exec_timeout_ms)) {
        g_exec_active = false;
        /* Stacked return PC must have bit 0 clear on ARMv6-M (B1) */
        stack_frame[6] = (uint32_t)o2p_exec_timeout_trampoline & ~1u;
        /* Preserve bit 9 (STKALIGN) */
        stack_frame[7] = 0x01000000u | (stack_frame[7] & (1u << 9));
    }
}

void __attribute__((naked)) SysTick_Handler(void)
{
    __asm volatile(
        "mov r0, lr\n"
        "movs r1, #4\n"
        "tst r0, r1\n"
        "beq 1f\n"
        "mrs r0, psp\n"
        "b 2f\n"
        "1:\n"
        "mrs r0, msp\n"
        "2:\n"
        "mov r1, lr\n"
        "b o2p_systick_c_handler\n"
    );
}
#else
void SysTick_Handler(void)
{
    s_millis++;
}
#endif

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
    uint32_t flags = (csr >> 24) & 0xFFu;
    RCC->CSR |= RCC_CSR_RMVF;

    /* Both images run this, the bootloader first. Whoever sees the flags parks
     * them; whoever finds them already cleared adopts what was parked. See the
     * boot-info comment in flash_map.h for why RESET_CAUSE was always 0 and
     * why an old bootloader now yields UNKNOWN rather than a confident zero. */
    if (flags != 0u) {
        o2p_bootinfo_set(flags);
    } else {
        uint32_t parked = 0u;
        if (o2p_bootinfo_get(&parked)) {
            flags = parked;
            /* Consumed. A bootloader that never parks must not let this boot's
             * value be read again as the next boot's cause. */
            o2p_bootinfo_clear();
        } else {
            flags = O2P_RESET_CAUSE_UNKNOWN;
        }
    }
    s_reset_cause = (uint16_t)flags;
    s_power_cycled = (flags != O2P_RESET_CAUSE_UNKNOWN) &&
                     ((flags << 24) & (RCC_CSR_PWRRSTF | RCC_CSR_PINRSTF)) != 0u;

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

#if O2P_DEBUG_ENABLE
    /* Enable power interface clock, backup domain access and RTC/TAMP clock */
    RCC->APBENR1 |= RCC_APBENR1_PWREN | RCC_APBENR1_RTCAPBEN;
    PWR->CR1 |= PWR_CR1_DBP;
#endif

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
    /* Start FIRST, then configure. Writing 0xCCCC is what forces the LSI on,
     * and PVU/RVU in SR clear only once the prescaler and reload transfer into
     * the shadow registers - a transfer clocked by that same LSI. Configuring
     * first and waiting on SR before the start therefore deadlocks: the wait
     * blocks the write that would start the clock the wait depends on.
     * Measured on the first article 2026-09-01 - PC pinned in this loop,
     * RCC_CSR = 0 (LSI off), PR/RLR still at their reset values. This is the
     * order HAL_IWDG_Init uses, for exactly this reason.
     *
     * Between the start and the reload below, the watchdog runs on its reset
     * defaults: /4 with a reload of 0xFFF, about 512 ms. That is four orders of
     * magnitude more than the handful of register stores in between.
     */
    IWDG->KR = 0xCCCCu;                 /* start; cannot be stopped afterwards */
    IWDG->KR = 0x5555u;                 /* unlock PR/RLR */
    /* PR[2:0] = 100 is /64. NOT (PR_2 | PR_1): that is 110 = /256, which this
     * code had, giving a 16.384 s timeout while every comment and document
     * claimed 4.096 s - four times longer to release a jammed shared bus.
     * IWDG_PRESCALER_64 in stm32g0xx_hal_iwdg.h:86 is IWDG_PR_PR_2 alone. */
    IWDG->PR = IWDG_PR_PR_2;
    IWDG->RLR = 2047u;
    while (IWDG->SR != 0u) {
    }
    IWDG->KR = 0xAAAAu;                 /* reload, so the first period is full */
}

void o2p_wdt_feed(void)
{
    IWDG->KR = 0xAAAAu;
}

#ifndef O2P_HOST_TEST
#if O2P_DEBUG_ENABLE
void o2p_hardfault_c_handler(uint32_t *stack_frame, uint32_t exc_return)
{
    (void)exc_return;
    uint32_t sp = (uint32_t)stack_frame;
    uint32_t pc = 0u;
    uint32_t lr = 0u;

    if ((sp & 3u) == 0u && sp >= 0x20000000u && sp <= (0x20009000u - 32u)) {
        pc = stack_frame[6];
        lr = stack_frame[5];
    }

    if (g_exec_active && (sp & 3u) == 0u && sp >= 0x20000000u && sp <= (0x20009000u - 32u)) {
        /* Only intercept if returning to Thread mode (EXC_RETURN bit 3 set, H1) */
        if ((exc_return & (1u << 3)) != 0u) {
            g_exec_active = false;
            /* Stacked return PC must have bit 0 clear on ARMv6-M (B1) */
            stack_frame[6] = (uint32_t)o2p_exec_fault_trampoline & ~1u;
            /* Preserve bit 9 (STKALIGN) */
            stack_frame[7] = 0x01000000u | (stack_frame[7] & (1u << 9));
            return;
        }
    }

    /* Backup-domain access, established HERE rather than assumed.
     *
     * o2p_clock_init() enables PWR, the RTC/TAMP APB clock and DBP, and every
     * image calls it first - so this held for any fault at ordinary runtime,
     * which is why it survived review as an assumption that happens to hold.
     * It does not hold for a fault DURING startup or in the earlier part of
     * o2p_clock_init() itself, and there the failure is worse than losing the
     * record: with the writes ignored, the BKP0R invalidate below is ignored
     * too, so a magic left by an EARLIER crash survives and is decoded on the
     * next boot as though it described this one. Both resets are software
     * resets, so nothing downstream can tell them apart. Re-enabling costs a
     * few register writes on a path that ends in a reset. */
    RCC->APBENR1 |= RCC_APBENR1_PWREN | RCC_APBENR1_RTCAPBEN;
    (void)RCC->APBENR1;   /* ensure the clock is running before PWR is touched */
    PWR->CR1 |= PWR_CR1_DBP;
    (void)PWR->CR1;

    /* Atomic sequence: invalidate first, write payload, then commit magic */
    TAMP->BKP0R = 0u;
    TAMP->BKP1R = pc;
    TAMP->BKP2R = lr;
    TAMP->BKP3R = (uint32_t)O2P_CRASH_HARDFAULT;
    TAMP->BKP4R = (uint32_t)O2P_BUILD_ID;
    TAMP->BKP0R = O2P_CRASH_MAGIC;

    NVIC_SystemReset();
    while (1) {}
}

void __attribute__((naked)) HardFault_Handler(void)
{
    __asm volatile(
        "mov r0, lr\n"
        "movs r1, #4\n"
        "tst r0, r1\n"
        "beq 1f\n"
        "mrs r0, psp\n"
        "b 2f\n"
        "1:\n"
        "mrs r0, msp\n"
        "2:\n"
        "mov r1, lr\n"
        "b o2p_hardfault_c_handler\n"
    );
}

void assert_failed(uint8_t *file, uint32_t line)
{
    (void)file;
    TAMP->BKP0R = 0u;
    TAMP->BKP1R = 0u;
    TAMP->BKP2R = 0u;
    TAMP->BKP3R = ((uint32_t)O2P_CRASH_ASSERT & 0xFFu) | ((uint32_t)line << 8);
    TAMP->BKP4R = (uint32_t)O2P_BUILD_ID;
    TAMP->BKP0R = O2P_CRASH_MAGIC;

    NVIC_SystemReset();
    while (1) {}
}

void __assert_func(const char *file, int line, const char *func, const char *expr)
{
    (void)file; (void)func; (void)expr;
    assert_failed((uint8_t *)file, (uint32_t)line);
}

uint32_t o2p_crash_read_reg(uint8_t index)
{
    switch (index) {
    case 0: return TAMP->BKP0R;
    case 1: return TAMP->BKP1R;
    case 2: return TAMP->BKP2R;
    case 3: return TAMP->BKP3R;
    case 4: return TAMP->BKP4R;
    default: return 0u;
    }
}

void o2p_crash_clear(void)
{
    TAMP->BKP0R = 0u;
}

void o2p_crash_set_breadcrumb(uint32_t val)
{
    if (TAMP->BKP0R != O2P_CRASH_MAGIC) {
        TAMP->BKP3R = val;
    }
}
#else /* !O2P_DEBUG_ENABLE */
void HardFault_Handler(void)
{
    NVIC_SystemReset();
    while (1) {}
}

void assert_failed(uint8_t *file, uint32_t line)
{
    (void)file; (void)line;
    NVIC_SystemReset();
    while (1) {}
}

void __assert_func(const char *file, int line, const char *func, const char *expr)
{
    (void)file; (void)line; (void)func; (void)expr;
    NVIC_SystemReset();
    while (1) {}
}
#endif /* O2P_DEBUG_ENABLE */
#endif /* !O2P_HOST_TEST */
