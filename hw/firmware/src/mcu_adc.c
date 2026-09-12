#include "mcu_adc.h"

#include "board_pins.h"
#include "die_temp.h"
#include "mcu.h"
#include "regmap.h"

/* Factory VREFINT calibration, measured at VDDA = 3.0 V (STM32G0 datasheet,
 * "Internal voltage reference"). */
/* Names are O2P_-prefixed because the ST HAL/LL headers already define
 * VREFINT_CAL_ADDR and ADC_CHANNEL_VREFINT with different types. */
#define O2P_VREFINT_CAL_ADDR 0x1FFF75AAu
#define O2P_ADC_CH_VREFINT 13u

/* Factory temperature-sensor calibration, both points also taken at VDDA =
 * 3.0 V. Read off this die 2026-09-04: TS_CAL1 = 1023, TS_CAL2 = 1370 - a
 * slope of 347 counts, which is 2.54 mV/K against DS12232 Table 65's typical
 * 2.5 mV/K, and TS_CAL1 sits inside the 1013..1072 that table's V30 implies.
 * So these addresses are confirmed by the silicon, not only by the memory
 * map. The bounds and the arithmetic are in die_temp.h. */
#define O2P_TS_CAL1_ADDR 0x1FFF75A8u
#define O2P_TS_CAL2_ADDR 0x1FFF75CAu
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

    /* PA7 and PA6 to analog mode, no pull. PA6 was omitted here until
     * 2026-09-05, which is half of why vin_mv was never the input rail. */
    O2P_VA_MON_PORT->PUPDR &= ~(3u << (O2P_VA_MON_PIN * 2u));
    O2P_VA_MON_PORT->MODER |= (3u << (O2P_VA_MON_PIN * 2u));
    O2P_VIN_MON_PORT->PUPDR &= ~(3u << (O2P_VIN_MON_PIN * 2u));
    O2P_VIN_MON_PORT->MODER |= (3u << (O2P_VIN_MON_PIN * 2u));
    /* PA4, CE_MON. Same omission as PA6's would be: a channel whose pin is not
     * in analog mode converts, and converts plausibly. */
    O2P_CE_MON_PORT->PUPDR &= ~(3u << (O2P_CE_MON_PIN * 2u));
    O2P_CE_MON_PORT->MODER |= (3u << (O2P_CE_MON_PIN * 2u));

#if !O2P_HW_HAS_ADS1119
    /* Rev B's three oxygen-path analog inputs: PA0 WE_BUF, PA1 RE_BUF, PB1
     * AFE_VOUT. Same omission as PA6's above, and worse here: a pin left in
     * its reset state is a digital input with a Schmitt trigger on it, so it
     * both converts plausibly AND loads a 1 kOhm-sourced signal on the oxygen
     * channel itself.
     *
     * Clearing PUPDR matters more than it looks. A pull-up left on PB1 is a
     * resistor to 3V3D sitting on the AFE output - a bias error that TRACKS
     * THE DIGITAL RAIL, which is precisely the coupling that deleting the
     * ADS1119 and moving VREF+ to the REF3425 was done to eliminate. */
    GPIOA->PUPDR &= ~(3u << (0u * 2u));        /* PA0 */
    GPIOA->MODER |= (3u << (0u * 2u));
    GPIOA->PUPDR &= ~(3u << (1u * 2u));        /* PA1 */
    GPIOA->MODER |= (3u << (1u * 2u));
    GPIOB->PUPDR &= ~(3u << (1u * 2u));        /* PB1 */
    GPIOB->MODER |= (3u << (1u * 2u));
#endif

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

    /* Longest sampling time -- 160.5 cycles, and it is now LOAD-BEARING, not
     * merely free. The VA_MON divider went 10k/10k to 47k/47k in the
     * 2026-09-05 BOM pass (docs/archive/2026-09-09-pcb-plans/BOM-REDUCTION.md 1), taking the source impedance
     * from 5k to 23.5k to get 130 uA back off the analog rail that feeds
     * U4/U7/U8. VIN_MON is 91k/10k = 9.0k. ST DS12232 Table 59 (Maximum ADC
     * RAIN) allows 50k at 12 bits and 160.5 cycles, so 23.5k has 2.1x margin --
     * and more here, because that table is quoted at a 35 MHz ADC clock and
     * this part runs HSI16 with no PLL (mcu.c:35), making the 160.5 cycles
     * longer in real time, not shorter. VREFINT needs a long sample by
     * specification regardless, and nothing here is rate-limited. A future
     * attempt to sample FASTER must re-derive against 23.5k, not against the 5k
     * this comment used to claim: SMPR=6 (79.5 cycles) allows only 33k. */
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
    *out_mv = (uint16_t)(((uint32_t)O2P_TS_CAL_VDDA_MV * cal) / raw);
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

    uint16_t vdda = 0u, raw = 0u;
    if (!o2p_mcu_adc_read_vdda_mv(&vdda)) {
        return false;
    }
    if (!convert(O2P_ADC_CH_TEMP, &raw)) {
        return false;
    }
    /* Plausibility of the calibration words, the bounds on the result, and the
     * interpolation itself all live in die_temp.h, where env:native can feed
     * them corrupt OTP - which this file cannot, the words being read-only. */
    return o2p_die_c100_from_cal(cal1, cal2, raw, vdda, out_c100);
}

/* Both rail monitors are the same measurement with a different channel and a
 * different divider, so they share one body. Keeping them separate is how the
 * VIN half went missing for a revision while the VA half worked. */
static bool read_divided_rail(uint32_t channel, uint32_t num, uint32_t den,
                              uint16_t *out_mv)
{
    uint16_t vdda = 0u, raw = 0u;
    if (out_mv == NULL) {
        return false;
    }
    if (!o2p_mcu_adc_read_vdda_mv(&vdda)) {
        return false;
    }
    if (!convert(channel, &raw)) {
        return false;
    }
    /* Pin volts, then undo the divider using the GENERATED contract - so a
     * divider change in the schematic cannot silently rescale this. */
    uint32_t pin_mv = ((uint32_t)raw * vdda) / 4095u;
    uint32_t rail_mv = (pin_mv * den) / num;
    if (rail_mv > 0xFFFFu) {
        return false;
    }
    *out_mv = (uint16_t)rail_mv;
    return true;
}

bool o2p_mcu_adc_read_vin_mv(uint16_t div_x1000, uint16_t *out_mv)
{
    if (o2p_vin_div_x1000_in_window(div_x1000)) {
        return read_divided_rail(O2P_VIN_MON_ADC_CH, 1000u, div_x1000, out_mv);
    }
    return read_divided_rail(O2P_VIN_MON_ADC_CH,
                             O2P_HW_DIV_VIN_NUM, O2P_HW_DIV_VIN_DEN, out_mv);
}

bool o2p_mcu_adc_read_va_mv(uint16_t *out_mv)
{
    return read_divided_rail(O2P_VA_MON_ADC_CH,
                             O2P_HW_DIV_VA_NUM, O2P_HW_DIV_VA_DEN, out_mv);
}

bool o2p_mcu_adc_read_ce_mv(uint16_t *out_mv)
{
    return read_divided_rail(O2P_CE_MON_ADC_CH,
                             O2P_HW_DIV_CE_NUM, O2P_HW_DIV_CE_DEN, out_mv);
}

/* ------------------------------------------------------------------- Rev B */
#if !O2P_HW_HAS_ADS1119

/* Channel numbers from DS12232 Table 12: PA0 = ADC_IN0, PA1 = ADC_IN1, and
 * PB1 = ADC_IN9. PB1 is the one worth double-checking against the pin TABLE
 * rather than the pinout figure -- an earlier revision of this port had it as
 * IN18, which converts, and converts plausibly. */
#define O2P_ADC_CH_WE_BUF   0u
#define O2P_ADC_CH_RE_BUF   1u
#define O2P_ADC_CH_AFE_VOUT 9u

static bool read_code(uint32_t channel, uint16_t *out_code)
{
    if (out_code == NULL || (ADC1->CR & ADC_CR_ADEN) == 0u) {
        return false;
    }
    return convert(channel, out_code);
}

bool o2p_mcu_adc_read_we_code(uint16_t *out_code)
{
    return read_code(O2P_ADC_CH_WE_BUF, out_code);
}

bool o2p_mcu_adc_read_re_code(uint16_t *out_code)
{
    return read_code(O2P_ADC_CH_RE_BUF, out_code);
}

bool o2p_mcu_adc_read_afe_code(uint16_t *out_code)
{
    return read_code(O2P_ADC_CH_AFE_VOUT, out_code);
}

bool o2p_mcu_adc_calfact(uint8_t *out_calfact)
{
    if (out_calfact == NULL || (ADC1->CR & ADC_CR_ADEN) == 0u) {
        return false;
    }
    *out_calfact = (uint8_t)(ADC1->CALFACT & ADC_CALFACT_CALFACT);
    return true;
}

bool o2p_mcu_adc_offset_erratum_active(void)
{
    uint8_t calfact = 0u;
    if (!o2p_mcu_adc_calfact(&calfact)) {
        /* Unknown, not clear. The header says so; this returning false is the
         * caller's cue to ask for the value when the difference matters. */
        return false;
    }
    return o2p_calfact_railed(calfact);
}

#endif /* !O2P_HW_HAS_ADS1119 */
