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

/* Factory temperature-sensor calibration, both points also taken at VDDA =
 * 3.0 V. Read off this die 2026-09-04: TS_CAL1 = 1023, TS_CAL2 = 1370. That
 * is a slope of 3.47 LSB/K, which at 12 bits against 3.0 V is 2.54 mV/K -
 * the datasheet's typical 2.5 mV/K, so the addresses are confirmed by the
 * silicon and not only by the memory map. */
#define O2P_TS_CAL1_ADDR 0x1FFF75A8u
#define O2P_TS_CAL2_ADDR 0x1FFF75CAu
#define O2P_TS_CAL1_C100 3000
#define O2P_TS_CAL2_C100 13000
#define O2P_ADC_CH_TEMP 12u

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

    /* Both internal channels on: VREFINT for the absolute reference, and the
     * temperature sensor. ST specifies tSTART through
     * LL_ADC_DELAY_TEMPSENSOR_STAB_US = 120 us, and the buffer needs a
     * further 15 us from ADC enable. This runs once at boot, so pay a whole
     * tick rather than reason about whether the ADEN handshake below happens
     * to cover either. */
    ADC1_COMMON->CCR |= ADC_CCR_VREFEN | ADC_CCR_TSEN;
    o2p_delay_ms(1u);

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
    *out_mv = (uint16_t)(((uint32_t)O2P_VREFINT_CAL_VDDA_MV * cal) / raw);
    return true;
}

bool o2p_mcu_adc_read_die_c100(int16_t *out_c100)
{
    /* TSEN, not ADEN: the temperature channel needs its own enable, and
     * testing the wrong one would pass on any path that left TSEN clear. */
    if (out_c100 == NULL || (ADC1_COMMON->CCR & ADC_CCR_TSEN) == 0u) {
        return false;
    }
    uint16_t cal1 = *(volatile uint16_t *)O2P_TS_CAL1_ADDR;
    uint16_t cal2 = *(volatile uint16_t *)O2P_TS_CAL2_ADDR;
    /* Guard the SLOPE, not just the two values. Bounding each endpoint
     * separately admits almost any scale factor - a correct cal1 with a
     * corrupted cal2 anywhere above it passes, and a 30 C die still reads
     * about 30 C while a 60 C die reads 40 or 140. The difference is the
     * quantity that scales the answer: 100 K at 2.0..3.1 mV/K, 12 bits
     * against 3.0 V, is 273..423 counts. Blank OTP (all ones or all zeros)
     * fails this too. */
    int32_t slope = (int32_t)cal2 - (int32_t)cal1;
    if (cal1 < 700u || cal1 > 1400u || slope < 273 || slope > 423) {
        return false;
    }

    uint16_t vdda = 0u, raw = 0u;
    if (!o2p_mcu_adc_read_vdda_mv(&vdda)) {
        return false;
    }
    if (!convert(O2P_ADC_CH_TEMP, &raw)) {
        return false;
    }

    /* The calibration points were taken at 3.0 V, this converter runs at
     * VDDA, so scale the raw count into calibration volts before
     * interpolating between the two points. */
    int32_t scaled = ((int32_t)raw * (int32_t)vdda) /
                     (int32_t)O2P_VREFINT_CAL_VDDA_MV;
    int32_t span_c100 = O2P_TS_CAL2_C100 - O2P_TS_CAL1_C100;
    int32_t t_c100 = ((span_c100 * (scaled - (int32_t)cal1)) / slope)
                     + O2P_TS_CAL1_C100;

    /* Reject only what cannot be a temperature at all. The bounds sit OUTSIDE
     * the part's limits on purpose: TA min is -40 C and TJ max is 130 C, but
     * this sensor is +/-5 C, so a real -38 C die may legitimately read -43 C
     * and clipping at the rated limit would throw away good readings at the
     * cold end. Anything past these is a failed conversion, not weather. */
    if (t_c100 < -5000 || t_c100 > 14000) {
        return false;
    }
    *out_c100 = (int16_t)t_c100;
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
