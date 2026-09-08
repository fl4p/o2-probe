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

/* Plausible VDDA window, millivolts. The STM32G071 is rated 1.7-3.6 V; this is
 * wider than the board's 3.3 V nominal on purpose, so a marginal-but-real rail
 * is still measured and can trip VA_LOW rather than vanishing as a failed
 * read. Outside it the computed rail is not a low voltage, it is a corrupted
 * VREFINT conversion - see o2p_mcu_adc_read_vdda_mv(). */
#define O2P_VDDA_PLAUSIBLE_MIN_MV 1600u
#define O2P_VDDA_PLAUSIBLE_MAX_MV 3700u

#include <stdbool.h>
#include <stdint.h>

void o2p_mcu_adc_init(void);

/* Millivolts on the 3V3A rail, undoing the R24/R25 divider. Returns false if
 * the conversion or the VREFINT reference read failed - never a default. */
bool o2p_mcu_adc_read_va_mv(uint16_t *out_mv);

/* VDDA/VREF+ in millivolts, derived from VREFINT. Exposed for bring-up. */
bool o2p_mcu_adc_read_vdda_mv(uint16_t *out_mv);

#endif /* O2P_MCU_ADC_H */
