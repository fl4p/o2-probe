/* MCU ADC1 on PA7 (ADC1_IN7) - the independent 3V3A witness.
 *
 * The ADS1119 also measures 3V3A/2 on its AIN2, but the ADS1119's own AVDD IS
 * 3V3A: a converter cannot report its own supply collapsing. PA7 exists so a
 * 3V3A brownout - which silently drops the LMP91000's volatile configuration
 * and therefore the cell bias, with the MCU still happily running
 * (PLAN.md:273-280) - is detectable at all.
 *
 * This ADC's reference is VREF+ = 3V3D, a different rail, so absolute volts
 * come from the factory VREFINT calibration rather than an assumed 3.3 V.
 */
#ifndef O2P_MCU_ADC_H
#define O2P_MCU_ADC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Plausible VDDA window, millivolts. The STM32G071 is rated 1.7-3.6 V; this is
 * wider than the board's 3.3 V nominal on purpose, so a marginal-but-real rail
 * is still measured and can trip VA_LOW rather than vanishing as a failed
 * read. Outside it the computed rail is not a low voltage, it is a corrupted
 * VREFINT conversion - see o2p_mcu_adc_read_vdda_mv(). */
/* Factory VREFINT calibration, measured at VDDA = 3.0 V (STM32G0 datasheet,
 * "Internal voltage reference"). Prefixed because the ST HAL headers define
 * VREFINT_CAL_ADDR with a different type. */
#define O2P_VREFINT_CAL_VDDA_MV 3000u

#define O2P_VDDA_PLAUSIBLE_MIN_MV 1600u
#define O2P_VDDA_PLAUSIBLE_MAX_MV 3700u

/* The pure part of the VDDA computation, in the header so the host tests can
 * exercise the shipped decision - mcu_adc.c reaches ADC registers and cannot
 * compile on the host, so a test that only re-asserted the constants above
 * proved nothing about the code using them (sixth review, 2026-09-08).
 *
 * NOTE the residual this does NOT close: a single uncorroborated VREFINT
 * sample can be corrupted into a value that is still INSIDE the window and
 * merely wrong - raw 1436 against a 1650 calibration reads 3447 mV, enough to
 * lift a real 3.000 V rail past the 3.130 V VA_LOW threshold. Catching that
 * needs a second, independent measurement of 3V3A; ADS1119 AIN2 is wired for
 * exactly that and is never sampled. See O2-CORRECTION-MODEL-BUDGET.md S13. */
static inline bool o2p_vdda_from_vrefint(uint16_t cal, uint16_t raw,
                                         uint16_t *out_mv)
{
    if (out_mv == NULL) {
        return false;
    }
    /* A blank or unprogrammed calibration word would produce a nonsense VDDA
     * that every later conversion inherits. Refuse instead. */
    if (cal < 1000u || cal > 2000u || raw == 0u) {
        return false;
    }
    uint32_t vdda = ((uint32_t)O2P_VREFINT_CAL_VDDA_MV * cal) / raw;
    if (vdda < O2P_VDDA_PLAUSIBLE_MIN_MV || vdda > O2P_VDDA_PLAUSIBLE_MAX_MV) {
        return false;
    }
    *out_mv = (uint16_t)vdda;
    return true;
}

#include <stdbool.h>
#include <stdint.h>

void o2p_mcu_adc_init(void);

/* Millivolts on the 3V3A rail, undoing the R24/R25 divider. Returns false if
 * the conversion or the VREFINT reference read failed - never a default. */
bool o2p_mcu_adc_read_va_mv(uint16_t *out_mv);

/* VDDA/VREF+ in millivolts, derived from VREFINT. Exposed for bring-up. */
bool o2p_mcu_adc_read_vdda_mv(uint16_t *out_mv);

#endif /* O2P_MCU_ADC_H */
