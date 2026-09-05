/* MCU ADC1 rail monitors: PA7 (ADC1_IN7) = 3V3A, PA6 (ADC1_IN6) = +12V_SW.
 *
 * BOTH rails are read here and NEITHER is on the ADS1119 any more. The
 * ADS1119's AIN2/AIN3 carry the buffered cell electrodes (WE_BUF/RE_BUF), not
 * rails - an older revision had 3V3A/2 and +12V_SW/12 there, and stale
 * comments describing that map outlived it by a revision. See board_pins.h's
 * VIN_MON note for what that cost.
 *
 * 3V3A must be witnessed off-converter because the ADS1119's own AVDD IS
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
#include <stdint.h>

void o2p_mcu_adc_init(void);

/* Millivolts on the 3V3A rail, undoing the R24/R25 divider. Returns false if
 * the conversion or the VREFINT reference read failed - never a default. */
bool o2p_mcu_adc_read_va_mv(uint16_t *out_mv);

/* Millivolts on the +12V_SW input rail, undoing the R26/R27 divider. Same
 * contract: false on any failure, never a substituted default. The caller must
 * treat false as "supply not OK", because a rail that cannot be read is not a
 * rail that is known good - see phase_rails() in main.c. */
bool o2p_mcu_adc_read_vin_mv(uint16_t *out_mv);

/* VDDA/VREF+ in millivolts, derived from VREFINT. Exposed for bring-up. */
bool o2p_mcu_adc_read_vdda_mv(uint16_t *out_mv);

/* MCU die temperature in 0.01 C, from the two factory calibration points.
 *
 * This is NOT an ambient measurement and nothing in the oxygen path may
 * depend on it: it is the die, it includes the MCU's own self-heating, and
 * the part is specified to about +/-5 C. What it is good for is a second
 * opinion with no failure mode in common with the TMP117 and the SHT45 -
 * those are both on I2C1, this is on the MCU's own ADC. A tip sensor
 * reporting 80 C while the die sits at 25 C is one of them lying, and today
 * the firmware has no way to notice.
 *
 * Returns false - never a substituted default - if the calibration words are
 * implausible or either conversion fails. */
bool o2p_mcu_adc_read_die_c100(int16_t *out_c100);

#endif /* O2P_MCU_ADC_H */
