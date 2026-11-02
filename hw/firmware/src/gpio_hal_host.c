/* A host stand-in for the GPIO and RCC registers OP_READ_GPIO loads.
 *
 * Every load is COUNTED, because the guards this exists to test are guards
 * against loads: an unclocked port must be answered without touching its
 * registers, and a pin that does not exist without touching anything at all. A
 * status code alone cannot prove either - a guard that read the registers and
 * then reported the refusal anyway would return the same status. The counters
 * can.
 *
 * The whole file is host-only. On the target gpio_hal.c is linked instead, and
 * this compiles to nothing.
 */
#ifdef O2P_HOST_TEST

#include "gpio_hal.h"
#include "regmap.h"

#include <stddef.h>
#include <string.h>

#if O2P_DEBUG_ENABLE

/* The same offsets gpio_hal.c pins CMSIS's GPIO_TypeDef to. */
_Static_assert(offsetof(o2p_host_gpio_regs_t, MODER)   == O2P_GPIO_OFS_MODER,   "fake MODER offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, OTYPER)  == O2P_GPIO_OFS_OTYPER,  "fake OTYPER offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, OSPEEDR) == O2P_GPIO_OFS_OSPEEDR, "fake OSPEEDR offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, PUPDR)   == O2P_GPIO_OFS_PUPDR,   "fake PUPDR offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, IDR)     == O2P_GPIO_OFS_IDR,     "fake IDR offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, ODR)     == O2P_GPIO_OFS_ODR,     "fake ODR offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, BSRR)    == O2P_GPIO_OFS_BSRR,    "fake BSRR offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, LCKR)    == O2P_GPIO_OFS_LCKR,    "fake LCKR offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, AFR)     == O2P_GPIO_OFS_AFRL,    "fake AFRL offset");
_Static_assert(offsetof(o2p_host_gpio_regs_t, BRR)     == O2P_GPIO_OFS_BRR,     "fake BRR offset");

o2p_host_gpio_regs_t o2p_host_gpio[O2P_GPIO_PORT_SLOTS];
uint32_t o2p_host_iopenr;
unsigned o2p_host_gpio_reads;
unsigned o2p_host_rcc_reads;
unsigned o2p_host_gpio_unmasked_reads;
unsigned o2p_host_rcc_unmasked_reads;
int o2p_host_gpio_irq_depth;

void o2p_host_gpio_reset(void)
{
    memset(o2p_host_gpio, 0, sizeof(o2p_host_gpio));
    for (unsigned p = 0; p < O2P_GPIO_PORT_SLOTS; p++) {
        o2p_host_gpio[p].MODER = 0xFFFFFFFFu;          /* every pin analog */
    }
    /* Port A resets with PA13/PA14 in AF (SWD) and their pulls on: RM0444
     * Rev 6 7.5.1 and 7.5.4, and 7.3.1 "PA14: SWCLK in pull-down, PA13: SWDIO
     * in pull-up". */
    o2p_host_gpio[O2P_GPIO_PORT_A].MODER = 0xEBFFFFFFu;
    o2p_host_gpio[O2P_GPIO_PORT_A].PUPDR = 0x24000000u;
    /* What o2p_clock_init() enables: A, B and C. */
    o2p_host_iopenr = (1u << O2P_GPIO_PORT_A) | (1u << O2P_GPIO_PORT_B) |
                      (1u << O2P_GPIO_PORT_C);
    o2p_host_gpio_reads = 0u;
    o2p_host_rcc_reads = 0u;
    o2p_host_gpio_unmasked_reads = 0u;
    o2p_host_rcc_unmasked_reads = 0u;
    o2p_host_gpio_irq_depth = 0;
}

uint32_t o2p_gpio_hal_read(uint8_t port, o2p_gpio_reg_t reg)
{
    o2p_host_gpio_reads++;
    if (o2p_host_gpio_irq_depth <= 0) {
        o2p_host_gpio_unmasked_reads++;
    }
    /* A load the part would not have answered - no port here, or its clock
     * off - returns a value no test expects, so a guard that failed to stop it
     * shows up in the decoded result as well as in the counter. */
    if (port >= O2P_GPIO_PORT_SLOTS || port == O2P_GPIO_PORT_E_ABSENT ||
        (o2p_host_iopenr & (1u << port)) == 0u) {
        return 0xDEADBEEFu;
    }
    const o2p_host_gpio_regs_t *g = &o2p_host_gpio[port];
    switch (reg) {
    case O2P_GPIO_REG_MODER:  return g->MODER;
    case O2P_GPIO_REG_OTYPER: return g->OTYPER;
    case O2P_GPIO_REG_PUPDR:  return g->PUPDR;
    case O2P_GPIO_REG_IDR:    return g->IDR;
    case O2P_GPIO_REG_ODR:    return g->ODR;
    case O2P_GPIO_REG_AFRL:   return g->AFR[0];
    case O2P_GPIO_REG_AFRH:   return g->AFR[1];
    default:                  return 0xDEADBEEFu;
    }
}

uint32_t o2p_gpio_hal_iopenr(void)
{
    o2p_host_rcc_reads++;
    if (o2p_host_gpio_irq_depth <= 0) {
        o2p_host_rcc_unmasked_reads++;
    }
    return o2p_host_iopenr;
}

o2p_gpio_irq_t o2p_gpio_hal_irq_save(void)
{
    o2p_host_gpio_irq_depth++;
    return 0u;
}

void o2p_gpio_hal_irq_restore(o2p_gpio_irq_t saved)
{
    (void)saved;
    o2p_host_gpio_irq_depth--;
}

#endif /* O2P_DEBUG_ENABLE */
#endif /* O2P_HOST_TEST */
