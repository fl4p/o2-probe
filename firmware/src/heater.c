#include "heater.h"

#include "board_pins.h"
#include "mcu.h"

static uint16_t s_duty_x100;

void o2p_heater_init(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN;

    /* Drive the gate low BEFORE switching the pin to an output, so the pin
     * never presents an undefined level to a MOSFET gate that switches 1 W. */
    GPIOA->BSRR = (1u << (O2P_HEATER_PWM_PIN + 16u));
    GPIOA->OTYPER &= ~(1u << O2P_HEATER_PWM_PIN);
    GPIOA->PUPDR &= ~(3u << (O2P_HEATER_PWM_PIN * 2u));
    GPIOA->MODER = (GPIOA->MODER & ~(3u << (O2P_HEATER_PWM_PIN * 2u))) |
                   (1u << (O2P_HEATER_PWM_PIN * 2u));   /* plain output */

    /* PA8 is TIM1_CH1 and PA7 - the 3V3A rail monitor - is TIM1_CH1N, the
     * complement of that same channel. If TIM1 is ever enabled for heater
     * PWM, CCER's CC1NE bit must stay clear or the timer will drive the
     * analog input pin. Belt and braces: keep TIM1's clock off entirely in
     * v0, so no register write anywhere can reach it.
     */
    RCC->APBENR2 &= ~RCC_APBENR2_TIM1EN;

    s_duty_x100 = 0u;
}

bool o2p_heater_set_duty_x100(uint16_t duty_x100)
{
#if O2P_HEATER_ENABLE
#error "v0 has no heater control loop. Enabling this flag without implementing \
the RH-primary PI loop AND fault-testing the TMP117 ALERT cutoff would energise \
1 W into the membrane with no closed loop and no verified hardware limit."
#else
    (void)duty_x100;
    o2p_heater_force_off();
    /* Refused, not clamped to zero and reported as success. A caller that
     * asked for heat needs to know it did not get any. */
    return duty_x100 == 0u;
#endif
}

uint16_t o2p_heater_duty_x100(void)
{
    return s_duty_x100;
}

void o2p_heater_force_off(void)
{
    GPIOA->BSRR = (1u << (O2P_HEATER_PWM_PIN + 16u));
    s_duty_x100 = 0u;
}
