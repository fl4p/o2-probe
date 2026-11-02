/* OP_READ_GPIO - validation, snapshot and packing. The contract is in
 * gpio_diag.h; register access goes through gpio_hal.h so every decision here
 * runs on the host against a fake that counts loads. */
#include "gpio_diag.h"

#if O2P_DEBUG_ENABLE

static const uint16_t k_bonded[O2P_GPIO_PORT_SLOTS] = {
    [O2P_GPIO_PORT_A]        = O2P_GPIO_BONDED_A,
    [O2P_GPIO_PORT_B]        = O2P_GPIO_BONDED_B,
    [O2P_GPIO_PORT_C]        = O2P_GPIO_BONDED_C,
    [O2P_GPIO_PORT_D]        = O2P_GPIO_BONDED_D,
    [O2P_GPIO_PORT_E_ABSENT] = 0x0000u,
    [O2P_GPIO_PORT_F]        = O2P_GPIO_BONDED_F,
};

bool o2p_gpio_pin_bonded(uint8_t port, uint8_t pin)
{
    if (port >= O2P_GPIO_PORT_SLOTS || pin > 15u) {
        return false;
    }
    return (k_bonded[port] & (1u << pin)) != 0u;
}

uint16_t o2p_gpio_diag_read(uint16_t param, o2p_gpio_diag_result_t *out)
{
    const uint8_t port = O2P_GPIO_PARAM_PORT(param);
    const uint8_t pin = O2P_GPIO_PARAM_PIN(param);

    out->rdata[0] = 0u;
    out->rdata[1] = 0u;
    out->rdata[2] = 0u;
    out->analog_mask = 0u;

    /* FIRST, and before anything is loaded - RCC included. The table is the
     * only thing standing between a typo in PARAM and a load at the address
     * GPIOE would have, where the G071 maps nothing. */
    if (!o2p_gpio_pin_bonded(port, pin)) {
        return O2P_DMBOX_STATUS_ERR_GPIO_NO_PIN;
    }

    /* ONE MASKED SECTION FOR THE CLOCK CHECK AND EVERY LOAD.
     *
     * The five registers must describe one instant. Nothing that changes a pin's
     * MODE runs in an interrupt (see the dispatch comment in regmap.c), but the
     * USART1 TC interrupt does change PC6/PC7's ODR and therefore their IDR,
     * and a snapshot that straddled it would pair a latch with a level from
     * two different moments - exactly the "ODR != IDR" pattern the CLI flags
     * as a shorted pin.
     *
     * The clock check is inside the same section so that "the clock was on"
     * is true of the loads that follow it, not merely of the moment before.
     * Nothing in this firmware gates a GPIO clock at run time today; that is a
     * property of the rest of the tree, and this should not depend on it.
     *
     * Cost: one RCC load, six GPIO loads and the shifts below it, well inside
     * the peek copy's budget (regmap.c, peek_copy()). */
    uint32_t moder = 0u, otyper = 0u, pupdr = 0u, idr = 0u, odr = 0u, afr = 0u;
    o2p_gpio_irq_t s = o2p_gpio_hal_irq_save();
    const bool clocked = (o2p_gpio_hal_iopenr() & (1u << port)) != 0u;
    if (clocked) {
        moder  = o2p_gpio_hal_read(port, O2P_GPIO_REG_MODER);
        otyper = o2p_gpio_hal_read(port, O2P_GPIO_REG_OTYPER);
        pupdr  = o2p_gpio_hal_read(port, O2P_GPIO_REG_PUPDR);
        idr    = o2p_gpio_hal_read(port, O2P_GPIO_REG_IDR);
        odr    = o2p_gpio_hal_read(port, O2P_GPIO_REG_ODR);
        afr    = o2p_gpio_hal_read(port, pin < 8u ? O2P_GPIO_REG_AFRL
                                                  : O2P_GPIO_REG_AFRH);
    }
    o2p_gpio_hal_irq_restore(s);

    /* Never enabled here: waking a port up to inspect it would report the
     * reset state of a peripheral the firmware never configured, as though it
     * were the firmware's configuration. */
    if (!clocked) {
        return O2P_DMBOX_STATUS_ERR_GPIO_UNCLOCKED;
    }

    const unsigned mode = (unsigned)(moder >> (2u * pin)) & 3u;
    const unsigned pull = (unsigned)(pupdr >> (2u * pin)) & 3u;
    const unsigned af   = (unsigned)(afr >> (4u * (pin & 7u))) & 0xFu;

    uint16_t analog = 0u;
    for (unsigned n = 0; n < 16u; n++) {
        if (((moder >> (2u * n)) & 3u) == O2P_GPIO_MODE_ANALOG) {
            analog = (uint16_t)(analog | (1u << n));
        }
    }

    uint16_t r0 = (uint16_t)(O2P_GPIO_R0_CONFIG_VALID |
                             mode |
                             (pull << O2P_GPIO_R0_PULL_SHIFT) |
                             (af << O2P_GPIO_R0_AF_SHIFT));
    if (((otyper >> pin) & 1u) != 0u) {
        r0 |= O2P_GPIO_R0_OPEN_DRAIN;
    }
    if (((odr >> pin) & 1u) != 0u) {
        r0 |= O2P_GPIO_R0_ODR;
    }

    out->rdata[1] = (uint16_t)(idr & 0xFFFFu);
    out->rdata[2] = (uint16_t)(odr & 0xFFFFu);
    out->analog_mask = analog;

    /* ANALOG MODE HAS NO LEVEL. ST RM0444 Rev 6, 7.3.13 "Analog configuration":
     * "The Schmitt trigger input is deactivated ... The output of the Schmitt
     * trigger is forced to a constant value (0)" and "Read access to the input
     * data register gets the value '0'". So the 0 in IDR is a property of the
     * mode, not of the pad. Reporting it as LOW is precisely how PB1 hid for a
     * whole bring-up. The configuration goes out and the level does not: no
     * LEVEL bit, no LEVEL_VALID, and a status that is not OK.
     *
     * Every OTHER mode samples the pad: 7.3.10 (input), 7.3.11 (output) and
     * 7.3.12 (alternate function) all state "The Schmitt trigger input is
     * activated", and for output and AF that the pin's data is sampled into
     * IDR - which is what makes ODR != IDR on an output a real finding. */
    if (mode == O2P_GPIO_MODE_ANALOG) {
        out->rdata[0] = r0;
        return O2P_DMBOX_STATUS_GPIO_NOT_SAMPLED;
    }

    if (((idr >> pin) & 1u) != 0u) {
        r0 |= O2P_GPIO_R0_LEVEL;
    }
    out->rdata[0] = (uint16_t)(r0 | O2P_GPIO_R0_LEVEL_VALID);
    return O2P_DMBOX_STATUS_OK;
}

#endif /* O2P_DEBUG_ENABLE */
