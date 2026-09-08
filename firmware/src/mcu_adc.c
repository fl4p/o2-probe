#include "mcu_adc.h"

#include "board_pins.h"
#include "mcu.h"

/* Factory VREFINT calibration, measured at VDDA = 3.0 V (STM32G0 datasheet,
 * "Internal voltage reference"). */
/* Names are O2P_-prefixed because the ST HAL/LL headers already define
 * VREFINT_CAL_ADDR and ADC_CHANNEL_VREFINT with different types. */
#define O2P_VREFINT_CAL_ADDR 0x1FFF75AAu
#define O2P_VREFINT_CAL_VDDA_MV 3000u
#define O2P_ADC_CH_VREFINT 13u

static bool convert(uint32_t channel, uint16_t *out)
{
    /* One channel at a time: CHSELR in its default (non-sequencer) mode is a
     * bitmap, and setting a single bit removes any ambiguity about which
     * result belongs to which input. */
    ADC1->CHSELR = (1u << channel);
    /* Wait for the channel-selection update to be acknowledged. */
    uint32_t t0 = o2p_millis();
    while ((ADC1->ISR & ADC_ISR_CCRDY) == 0u) {
        if (o2p_elapsed(t0, 5u)) {
            return false;
        }
    }
    ADC1->ISR = ADC_ISR_CCRDY;

    ADC1->CR |= ADC_CR_ADSTART;
    t0 = o2p_millis();
    while ((ADC1->ISR & ADC_ISR_EOC) == 0u) {
        if (o2p_elapsed(t0, 10u)) {
            ADC1->CR |= ADC_CR_ADSTP;
            return false;
        }
    }
    *out = (uint16_t)ADC1->DR;
    return true;
}

void o2p_mcu_adc_init(void)
{
    RCC->APBENR2 |= RCC_APBENR2_ADCEN;

    /* PA7 to analog mode, no pull. */
    O2P_VA_MON_PORT->PUPDR &= ~(3u << (O2P_VA_MON_PIN * 2u));
    O2P_VA_MON_PORT->MODER |= (3u << (O2P_VA_MON_PIN * 2u));

    ADC1->CR = 0u;
    ADC1->CR = ADC_CR_ADVREGEN;
    /* tADCVREG_STUP is 20 us; 1 ms of tick granularity is the cheapest way to
     * be certain, and this runs once at boot. */
    o2p_delay_ms(1u);

    ADC1->CR |= ADC_CR_ADCAL;
    uint32_t t0 = o2p_millis();
    while ((ADC1->CR & ADC_CR_ADCAL) != 0u) {
        if (o2p_elapsed(t0, 10u)) {
            return;   /* leave the ADC disabled; reads will fail honestly */
        }
    }

    /* Longest sampling time. The VA_MON divider is 10k||10k = 5k source
     * impedance and VREFINT needs a long sample by specification; nothing
     * here is rate-limited, so there is no reason to sample fast. */
    ADC1->SMPR = 7u;
    ADC1->CFGR1 = 0u;          /* 12-bit, single conversion, right aligned */

    ADC1_COMMON->CCR |= ADC_CCR_VREFEN;

    ADC1->ISR = ADC_ISR_ADRDY;
    ADC1->CR |= ADC_CR_ADEN;
    t0 = o2p_millis();
    while ((ADC1->ISR & ADC_ISR_ADRDY) == 0u) {
        if (o2p_elapsed(t0, 10u)) {
            return;
        }
    }
}

bool o2p_mcu_adc_read_vdda_mv(uint16_t *out_mv)
{
    if (out_mv == NULL || (ADC1->CR & ADC_CR_ADEN) == 0u) {
        return false;
    }
    uint16_t cal = *(volatile uint16_t *)O2P_VREFINT_CAL_ADDR;
    /* A blank or unprogrammed calibration word would produce a nonsense VDDA
     * that every later conversion inherits. Refuse instead. */
    if (cal < 1000u || cal > 2000u) {
        return false;
    }
    uint16_t raw = 0u;
    if (!convert(O2P_ADC_CH_VREFINT, &raw) || raw == 0u) {
        return false;
    }
    uint32_t vdda = ((uint32_t)O2P_VREFINT_CAL_VDDA_MV * cal) / raw;
    /* Bound the RESULT, not just its inputs. A corrupted VREFINT sample passes
     * the raw != 0 test and produces an arbitrarily large VDDA - a sample of
     * 1138 against a 1650 calibration word yields 4350 mV, which this part
     * cannot run at - and every rail derived from it inherits the error. The
     * supervision downstream only ever checks for LOW voltage, so an
     * impossibly high VDDA raised no fault at all and could additionally
     * overflow the uint16 cast. An unevaluable rail must be reported as a
     * failed read, not as a number (fifth review, 2026-09-08).
     *
     * The STM32G071 is rated 1.7-3.6 V; the window below is deliberately wider
     * than the board's 3.3 V nominal so a genuinely marginal but real rail is
     * still measured and can trip the VA_LOW threshold that exists for it. */
    if (vdda < O2P_VDDA_PLAUSIBLE_MIN_MV || vdda > O2P_VDDA_PLAUSIBLE_MAX_MV) {
        return false;
    }
    *out_mv = (uint16_t)vdda;
    return true;
}

bool o2p_mcu_adc_read_va_mv(uint16_t *out_mv)
{
    uint16_t vdda = 0u, raw = 0u;
    if (out_mv == NULL) {
        return false;
    }
    if (!o2p_mcu_adc_read_vdda_mv(&vdda)) {
        return false;
    }
    if (!convert(O2P_VA_MON_ADC_CH, &raw)) {
        return false;
    }
    /* Pin volts, then undo R24/R25 using the generated contract - so a
     * divider change in the schematic cannot silently rescale this. */
    uint32_t pin_mv = ((uint32_t)raw * vdda) / 4095u;
    uint32_t rail_mv = (pin_mv * O2P_HW_DIV_VA_DEN) / O2P_HW_DIV_VA_NUM;
    if (rail_mv > 0xFFFFu) {
        return false;
    }
    *out_mv = (uint16_t)rail_mv;
    return true;
}
