#include "heater.h"

#include "board_pins.h"
#include "mcu.h"

static uint16_t s_duty_x100;
static uint16_t s_pwm_hz;
static uint32_t s_last_cmd_ms;
static bool s_have_cmd;

bool o2p_heater_compiled_in(void)
{
#if O2P_HEATER_ENABLE
    return true;
#else
    return false;
#endif
}

/* PA7 must still be analog: MODER bits for that pin == 0b11. */
static bool pa7_is_analog(void)
{
    uint32_t moder = O2P_VA_MON_PORT->MODER >> (O2P_VA_MON_PIN * 2u);
    return (moder & 3u) == 3u;
}

bool o2p_heater_pin_integrity_ok(void)
{
    if (!pa7_is_analog()) {
        return false;
    }
#if O2P_HEATER_ENABLE
    /* Only read TIM1 when its clock is actually running; a gated peripheral
     * does not return meaningful register contents. */
    if ((RCC->APBENR2 & RCC_APBENR2_TIM1EN) != 0u) {
        if ((TIM1->CCER & TIM_CCER_CC1NE) != 0u) {
            return false;
        }
    }
#endif
    return true;
}

static void gate_low_gpio(void)
{
    /* Drive the gate low BEFORE switching the pin to an output, so the pin
     * never presents an undefined level to a MOSFET gate that switches 1 W. */
    O2P_HEATER_PWM_PORT->BSRR = (1u << (O2P_HEATER_PWM_PIN + 16u));
    O2P_HEATER_PWM_PORT->OTYPER &= ~(1u << O2P_HEATER_PWM_PIN);
    O2P_HEATER_PWM_PORT->PUPDR &= ~(3u << (O2P_HEATER_PWM_PIN * 2u));
    O2P_HEATER_PWM_PORT->MODER =
        (O2P_HEATER_PWM_PORT->MODER & ~(3u << (O2P_HEATER_PWM_PIN * 2u))) |
        (1u << (O2P_HEATER_PWM_PIN * 2u));   /* plain output */
}

void o2p_heater_init(void)
{
    gate_low_gpio();
    s_duty_x100 = 0u;
    s_pwm_hz = 0u;
    s_have_cmd = false;

#if !O2P_HEATER_ENABLE
    /* Belt and braces for the disabled build: with TIM1's clock gated off, no
     * register write anywhere can reach the timer that shares this pin. */
    RCC->APBENR2 &= ~RCC_APBENR2_TIM1EN;
#endif
}

#if O2P_HEATER_ENABLE

/* Derive prescaler and reload for a target frequency from the 16 MHz core
 * clock, keeping ARR as large as the divider allows so the duty resolution
 * stays as fine as possible. */
static void timer_set_frequency(uint16_t hz)
{
    uint32_t ticks = O2P_SYSCLK_HZ / (hz ? hz : 1u);
    uint32_t psc = 0u;
    while ((ticks / (psc + 1u)) > 65536u) {
        psc++;
    }
    uint32_t arr = (ticks / (psc + 1u));
    if (arr == 0u) {
        arr = 1u;
    }
    TIM1->PSC = (uint16_t)psc;
    TIM1->ARR = (uint16_t)(arr - 1u);
    TIM1->EGR = TIM_EGR_UG;      /* latch PSC/ARR immediately */
}

static void timer_init(uint16_t hz)
{
    RCC->APBENR2 |= RCC_APBENR2_TIM1EN;

    TIM1->CR1 = 0u;
    TIM1->CCER = 0u;             /* CC1NE explicitly clear - see heater.h */
    TIM1->CCMR1 = (6u << TIM_CCMR1_OC1M_Pos) | TIM_CCMR1_OC1PE;  /* PWM mode 1 */
    TIM1->CCR1 = 0u;
    timer_set_frequency(hz);

    /* CC1E only. CC1NE is never set, and TIM1's complementary outputs stay
     * disabled, so PA7 is never driven by the timer. */
    TIM1->CCER = TIM_CCER_CC1E;
    TIM1->BDTR |= TIM_BDTR_MOE;  /* advanced timer: main output enable */
    TIM1->CR1 |= TIM_CR1_ARPE | TIM_CR1_CEN;

    /* PA8 to AF2 only once the timer is producing a zero-duty waveform, so the
     * gate never sees a transient high while the channel is configured. */
    uint32_t p = O2P_HEATER_PWM_PIN;
    O2P_HEATER_PWM_PORT->OSPEEDR &= ~(3u << (p * 2u));   /* slow edge; the gate
                                                          * RC dominates anyway */
    O2P_HEATER_PWM_PORT->AFR[p >> 3] =
        (O2P_HEATER_PWM_PORT->AFR[p >> 3] & ~(0xFu << ((p & 7u) * 4u))) |
        ((uint32_t)O2P_HEATER_PWM_AF << ((p & 7u) * 4u));
    O2P_HEATER_PWM_PORT->MODER =
        (O2P_HEATER_PWM_PORT->MODER & ~(3u << (p * 2u))) | (2u << (p * 2u));
}

void o2p_heater_apply(uint16_t duty_x100, uint16_t pwm_hz)
{
    s_last_cmd_ms = o2p_millis();
    s_have_cmd = true;

    if (duty_x100 == 0u) {
        o2p_heater_force_off();
        return;
    }
    /* Never take a command on trust: if the complementary-output guard has
     * failed, the analog rail monitor is compromised and heating is the last
     * thing to do about it. */
    if (!o2p_heater_pin_integrity_ok()) {
        o2p_heater_force_off();
        return;
    }

    if (pwm_hz != s_pwm_hz) {
        timer_init(pwm_hz);
        s_pwm_hz = pwm_hz;
    }

    uint32_t arr = (uint32_t)TIM1->ARR + 1u;
    uint32_t ccr = ((uint32_t)duty_x100 * arr) / 10000u;
    if (ccr > arr) {
        ccr = arr;
    }
    TIM1->CCR1 = (uint16_t)ccr;
    s_duty_x100 = duty_x100;
}

void o2p_heater_force_off(void)
{
    if ((RCC->APBENR2 & RCC_APBENR2_TIM1EN) != 0u) {
        TIM1->CCR1 = 0u;
        TIM1->CCER = 0u;
        TIM1->BDTR &= ~TIM_BDTR_MOE;
        TIM1->CR1 &= ~TIM_CR1_CEN;
    }
    /* Take the pin back off the timer entirely and hold it low, so "off" does
     * not depend on the timer still behaving. */
    gate_low_gpio();
    s_pwm_hz = 0u;
    s_duty_x100 = 0u;
}

#else  /* !O2P_HEATER_ENABLE */

void o2p_heater_apply(uint16_t duty_x100, uint16_t pwm_hz)
{
    (void)duty_x100;
    (void)pwm_hz;
    s_last_cmd_ms = o2p_millis();
    s_have_cmd = true;
    /* The controller already refuses to ask for heat in this build - it sees
     * O2P_HB_NOT_COMPILED - so a non-zero duty reaching here would be a bug in
     * the caller, not a configuration choice. Hold the gate low regardless. */
    o2p_heater_force_off();
}

void o2p_heater_force_off(void)
{
    gate_low_gpio();
    s_duty_x100 = 0u;
}

#endif /* O2P_HEATER_ENABLE */

void o2p_heater_service(void)
{
    if (s_duty_x100 == 0u) {
        return;
    }
    if (!s_have_cmd || o2p_elapsed(s_last_cmd_ms, O2P_HEATER_STALE_MS)) {
        /* The sampler has stopped publishing. Whatever the last command was,
         * it is now a guess about a probe nobody is measuring. */
        o2p_heater_force_off();
    }
}

uint16_t o2p_heater_duty_x100(void)
{
    return s_duty_x100;
}
