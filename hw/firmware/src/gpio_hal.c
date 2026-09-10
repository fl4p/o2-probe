/* The target half of gpio_hal.h: CMSIS register access for OP_READ_GPIO.
 *
 * Host builds link gpio_hal_host.c instead, and a nodebug image compiles this to
 * nothing along with the rest of the diagnostic mailbox. */
#ifndef O2P_HOST_TEST

#include "gpio_hal.h"
#include "mcu.h"

#include <stddef.h>

#if O2P_DEBUG_ENABLE

/* The layout gpio_hal_host.c fakes is the one this file reads by field name.
 * Pin both to RM0444's offsets, so a CMSIS header that ever disagreed with the
 * fake - or the fake with the part - fails here rather than passing on the host
 * and reading the wrong register on the probe. */
_Static_assert(offsetof(GPIO_TypeDef, MODER)   == O2P_GPIO_OFS_MODER,   "GPIO MODER offset");
_Static_assert(offsetof(GPIO_TypeDef, OTYPER)  == O2P_GPIO_OFS_OTYPER,  "GPIO OTYPER offset");
_Static_assert(offsetof(GPIO_TypeDef, OSPEEDR) == O2P_GPIO_OFS_OSPEEDR, "GPIO OSPEEDR offset");
_Static_assert(offsetof(GPIO_TypeDef, PUPDR)   == O2P_GPIO_OFS_PUPDR,   "GPIO PUPDR offset");
_Static_assert(offsetof(GPIO_TypeDef, IDR)     == O2P_GPIO_OFS_IDR,     "GPIO IDR offset");
_Static_assert(offsetof(GPIO_TypeDef, ODR)     == O2P_GPIO_OFS_ODR,     "GPIO ODR offset");
_Static_assert(offsetof(GPIO_TypeDef, BSRR)    == O2P_GPIO_OFS_BSRR,    "GPIO BSRR offset");
_Static_assert(offsetof(GPIO_TypeDef, LCKR)    == O2P_GPIO_OFS_LCKR,    "GPIO LCKR offset");
_Static_assert(offsetof(GPIO_TypeDef, AFR)     == O2P_GPIO_OFS_AFRL,    "GPIO AFRL offset");
_Static_assert(offsetof(GPIO_TypeDef, BRR)     == O2P_GPIO_OFS_BRR,     "GPIO BRR offset");
_Static_assert(offsetof(RCC_TypeDef, IOPENR)   == O2P_RCC_OFS_IOPENR,   "RCC IOPENR offset");

/* gpio_diag.c tests clock bit (1 << port index). That is only the right bit if
 * the index, the IOPENR bit and the port's place in the IO bus all agree. */
_Static_assert(RCC_IOPENR_GPIOAEN == (1UL << O2P_GPIO_PORT_A), "IOPENR bit for port A");
_Static_assert(RCC_IOPENR_GPIOBEN == (1UL << O2P_GPIO_PORT_B), "IOPENR bit for port B");
_Static_assert(RCC_IOPENR_GPIOCEN == (1UL << O2P_GPIO_PORT_C), "IOPENR bit for port C");
_Static_assert(RCC_IOPENR_GPIODEN == (1UL << O2P_GPIO_PORT_D), "IOPENR bit for port D");
_Static_assert(RCC_IOPENR_GPIOFEN == (1UL << O2P_GPIO_PORT_F), "IOPENR bit for port F");
_Static_assert(GPIOB_BASE == GPIOA_BASE + 0x400UL * O2P_GPIO_PORT_B, "GPIOB base");
_Static_assert(GPIOC_BASE == GPIOA_BASE + 0x400UL * O2P_GPIO_PORT_C, "GPIOC base");
_Static_assert(GPIOD_BASE == GPIOA_BASE + 0x400UL * O2P_GPIO_PORT_D, "GPIOD base");
_Static_assert(GPIOF_BASE == GPIOA_BASE + 0x400UL * O2P_GPIO_PORT_F, "GPIOF base");

static const GPIO_TypeDef *port_regs(uint8_t port)
{
    switch (port) {
    case O2P_GPIO_PORT_A: return GPIOA;
    case O2P_GPIO_PORT_B: return GPIOB;
    case O2P_GPIO_PORT_C: return GPIOC;
    case O2P_GPIO_PORT_D: return GPIOD;
    case O2P_GPIO_PORT_F: return GPIOF;
    default:              return NULL;   /* no port E on this part */
    }
}

uint32_t o2p_gpio_hal_read(uint8_t port, o2p_gpio_reg_t reg)
{
    const GPIO_TypeDef *g = port_regs(port);
    /* Unreachable through gpio_diag.c, which admits only bonded pins. Kept so
     * a future caller that forgets cannot turn index 4 into a load at the
     * GPIOE address, where nothing is mapped. */
    if (g == NULL) {
        return 0u;
    }
    switch (reg) {
    case O2P_GPIO_REG_MODER:  return g->MODER;
    case O2P_GPIO_REG_OTYPER: return g->OTYPER;
    case O2P_GPIO_REG_PUPDR:  return g->PUPDR;
    case O2P_GPIO_REG_IDR:    return g->IDR;
    case O2P_GPIO_REG_ODR:    return g->ODR;
    case O2P_GPIO_REG_AFRL:   return g->AFR[0];
    case O2P_GPIO_REG_AFRH:   return g->AFR[1];
    default:                  return 0u;
    }
}

uint32_t o2p_gpio_hal_iopenr(void)
{
    return RCC->IOPENR;
}

o2p_gpio_irq_t o2p_gpio_hal_irq_save(void)
{
    uint32_t s = __get_PRIMASK();
    __disable_irq();
    return s;
}

void o2p_gpio_hal_irq_restore(o2p_gpio_irq_t saved)
{
    __set_PRIMASK(saved);
}

#endif /* O2P_DEBUG_ENABLE */
#endif /* !O2P_HOST_TEST */
