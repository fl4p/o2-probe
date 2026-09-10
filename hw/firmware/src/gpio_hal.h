/* The register access behind OP_READ_GPIO (gpio_diag.h), and nothing else.
 *
 * WHY A SEAM. The decisions the opcode makes - which pins exist, whether a
 * port's clock is running, which bits decode to what, and above all when a
 * level must NOT be reported - are exactly the logic that can be wrong without
 * hardware, and on a potted probe nobody gets to find out with a scope. Reading
 * GPIOx->MODER directly would have kept that logic off the host, the way
 * config_flash.c was kept off it until flash_hal_host.c existed.
 *
 * READ-ONLY BY CONSTRUCTION. There is no write function here, and there must
 * never be one: PLAN-MODBUS-DEBUG.md 5.1 rejects generic register writes, and a
 * pin-state query that could change a pin would be a way to switch the RS-485
 * driver or the heater gate from the bus. The only verbs are "load one GPIO
 * register", "load RCC_IOPENR" and "mask/unmask interrupts".
 *
 * Two implementations, never both in one image:
 *   gpio_hal.c       the target: CMSIS GPIO_TypeDef / RCC_TypeDef, by field name
 *   gpio_hal_host.c  the host: a fake register set that counts every load
 */
#ifndef O2P_GPIO_HAL_H
#define O2P_GPIO_HAL_H

#include <stdbool.h>
#include <stdint.h>

/* Port index as the opcode encodes it. It is ALSO the RCC_IOPENR enable bit and
 * the port's distance from IOPORT_BASE in 0x400 steps - all three are the same
 * number on STM32G0, and gpio_hal.c asserts it against the CMSIS header rather
 * than trusting this comment. Index 4 is where GPIOE would be; the G071 has no
 * port E, so nothing is ever loaded through it. */
enum {
    O2P_GPIO_PORT_A = 0u,
    O2P_GPIO_PORT_B = 1u,
    O2P_GPIO_PORT_C = 2u,
    O2P_GPIO_PORT_D = 3u,
    O2P_GPIO_PORT_E_ABSENT = 4u,
    O2P_GPIO_PORT_F = 5u,
    O2P_GPIO_PORT_SLOTS = 6u,
};

/* The registers the opcode reads. OSPEEDR, BSRR, LCKR and BRR are deliberately
 * absent: BSRR and BRR are write-only (they read as zero and mean nothing), and
 * speed and lock say nothing about the question "what is this pin doing". */
typedef enum {
    O2P_GPIO_REG_MODER,
    O2P_GPIO_REG_OTYPER,
    O2P_GPIO_REG_PUPDR,
    O2P_GPIO_REG_IDR,
    O2P_GPIO_REG_ODR,
    O2P_GPIO_REG_AFRL,   /* GPIO_TypeDef AFR[0], pins 0..7  */
    O2P_GPIO_REG_AFRH,   /* GPIO_TypeDef AFR[1], pins 8..15 */
} o2p_gpio_reg_t;

/* The RM0444 GPIO register map offsets. Both implementations assert their
 * layout against THESE numbers - the target against CMSIS's GPIO_TypeDef, the
 * host against its fake - so neither can drift from the part without the build
 * saying so. */
#define O2P_GPIO_OFS_MODER   0x00u
#define O2P_GPIO_OFS_OTYPER  0x04u
#define O2P_GPIO_OFS_OSPEEDR 0x08u
#define O2P_GPIO_OFS_PUPDR   0x0Cu
#define O2P_GPIO_OFS_IDR     0x10u
#define O2P_GPIO_OFS_ODR     0x14u
#define O2P_GPIO_OFS_BSRR    0x18u
#define O2P_GPIO_OFS_LCKR    0x1Cu
#define O2P_GPIO_OFS_AFRL    0x20u
#define O2P_GPIO_OFS_AFRH    0x24u
#define O2P_GPIO_OFS_BRR     0x28u
#define O2P_RCC_OFS_IOPENR   0x34u

/* One load of one register of a port whose clock the CALLER has already seen
 * enabled. Loading an unclocked port is not something this function checks:
 * that check belongs to gpio_diag.c, where the host tests can see it happen. */
uint32_t o2p_gpio_hal_read(uint8_t port, o2p_gpio_reg_t reg);

/* One load of RCC_IOPENR. */
uint32_t o2p_gpio_hal_iopenr(void);

/* PRIMASK saved and RESTORED, not unconditionally re-enabled, so a caller that
 * is already masked stays masked - the same contract as peek_irq_save(). */
typedef uint32_t o2p_gpio_irq_t;
o2p_gpio_irq_t o2p_gpio_hal_irq_save(void);
void o2p_gpio_hal_irq_restore(o2p_gpio_irq_t saved);

#ifdef O2P_HOST_TEST
/* The fake, laid out field for field like CMSIS's GPIO_TypeDef. */
typedef struct {
    uint32_t MODER, OTYPER, OSPEEDR, PUPDR, IDR, ODR, BSRR, LCKR;
    uint32_t AFR[2];
    uint32_t BRR;
} o2p_host_gpio_regs_t;

extern o2p_host_gpio_regs_t o2p_host_gpio[O2P_GPIO_PORT_SLOTS];
extern uint32_t o2p_host_iopenr;
/* Every GPIO register load, every RCC_IOPENR load, and the loads of either made
 * while NOT inside a masked section - which must stay zero. */
extern unsigned o2p_host_gpio_reads;
extern unsigned o2p_host_rcc_reads;
extern unsigned o2p_host_gpio_unmasked_reads;
extern unsigned o2p_host_rcc_unmasked_reads;
extern int o2p_host_gpio_irq_depth;
/* Reset values of the part - ST RM0444 Rev 6 7.5.1: MODER 0xEBFFFFFF on port A
 * (PA13/PA14 in AF for SWD), 0xFFFFFFFF elsewhere, i.e. analog; 7.5.4: PUPDR
 * 0x24000000 on port A, 0 elsewhere - with the clocks as mcu.c leaves them
 * (A, B, C on) and the counters zeroed. */
void o2p_host_gpio_reset(void);
#endif

#endif /* O2P_GPIO_HAL_H */
