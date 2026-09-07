/* LMP91000 configurable potentiostat AFE, I2C 0x48 (fixed).
 *
 * Register encodings verified against TI SNAS506I (Dec 2014) section 7.6 -
 * Table 2 register map and the TIACN / REFCN / MODECN field tables.
 *
 * The bias is the whole reason this part is here. The SGX-OX-ROHS-Mini is a
 * BIASED three-electrode cell needing -600 +/- 10 mV between working and
 * reference electrodes (DS-0637). With an external reference the LMP91000
 * expresses bias as a percentage of VREF (SNAS506I 7.6.4), and 24 % is the
 * TOP step it offers - so 0.24 * 2.500 V = 600.0 mV exactly, and the +/-10 mV
 * window means VREF must be trimmed to 2.500 V within about +/-42 mV. That is
 * a manual bench adjustment of RV1; firmware can only verify it.
 *
 * Two failure modes this driver exists to catch:
 *
 *  - The part powers up in DEEP SLEEP with VOLATILE configuration. A 3V3A
 *    brownout with the MCU still running drops the cell bias without any
 *    reset the MCU would notice (PLAN.md:273-280). Hence readback
 *    supervision on every cycle, not just at boot.
 *  - Losing bias costs up to FIFTEEN MINUTES of settling before the cell
 *    reads correctly again (DS-0637 Note 1). So a detected mismatch is not
 *    just "rewrite it": it must restart the settling timer and invalidate the
 *    oxygen channel until it expires.
 */
#ifndef O2P_LMP91000_H
#define O2P_LMP91000_H

#include <stdbool.h>
#include <stdint.h>

enum {
    O2P_LMP_REG_STATUS = 0x00u,  /* bit0: 1 = ready */
    O2P_LMP_REG_LOCK   = 0x01u,  /* bit0: 0 = TIACN/REFCN writable, 1 = locked */
    O2P_LMP_REG_TIACN  = 0x10u,
    O2P_LMP_REG_REFCN  = 0x11u,
    O2P_LMP_REG_MODECN = 0x12u,
};

/* TIACN = TIA_GAIN[4:2] | RLOAD[1:0].
 *   TIA_GAIN 011 = 7 kOhm. PLAN.md:254 sizes the chain for >=150 uA: the cell
 *   reaches ~152 uA at 30 % O2, which across 7 kOhm is a 1.06 V excursion from
 *   the 1.675 V internal zero - inside the 0-3.3 V output range. 14 kOhm would
 *   clip; 3.5 kOhm would waste half the ADC.
 *   RLOAD 00 = 10 Ohm, the smallest offered, because the load resistor sits in
 *   series with the working electrode and only adds error here.
 */
#define O2P_LMP_TIACN_INTENDED  ((uint8_t)((3u << 2) | 0u))   /* 0x0C */

/* REFCN = REF_SOURCE[7] | INT_Z[6:5] | BIAS_SIGN[4] | BIAS[3:0].
 *   REF_SOURCE 1 = external: the trimmed 2.500 V on VREF_TRIM, shared with the
 *   ADS1119's REFP so the measurement is ratiometric.
 *   INT_Z 10 = 67 %. The cell current is unipolar, so putting the zero high
 *   gives the whole downward swing to signal.
 *   BIAS_SIGN 0 = negative, i.e. (VWE - VRE) < 0, which is what the SGX cell
 *   specifies. NOTE: SCHEMATIC-REVIEW.md M4 leaves the SGX SIGN CONVENTION as
 *   an open release gate - this encodes the datasheet reading, and the bench
 *   air-versus-nitrogen pair is what confirms it.
 *   BIAS 1101 = 24 %, the maximum step.
 */
#define O2P_LMP_REFCN_INTENDED  ((uint8_t)(0x80u | (2u << 5) | (0u << 4) | 0x0Du)) /* 0xCD */

/* MODECN = FET_SHORT[7] | OP_MODE[2:0]. 011 = 3-lead amperometric cell.
 * FET_SHORT stays 0: shorting the cell is for storage, and doing it here
 * would trigger the 15-minute settling penalty every time. */
#define O2P_LMP_MODECN_INTENDED ((uint8_t)0x03u)

typedef enum {
    O2P_LMP_OK = 0,
    O2P_LMP_IO,
    O2P_LMP_MISMATCH,   /* readback differs from intent - bias may be gone */
} o2p_lmp_status_t;

/* Drive MENB low (it is already pulled low by R17) and write the full
 * configuration. Safe to call repeatedly; it unlocks, writes, re-reads. */
o2p_lmp_status_t o2p_lmp91000_configure(void);

/* Read TIACN/REFCN/MODECN back and compare with intent. This is the bias
 * supervisor: call it every cycle. `out_readback` receives TIACN << 8 | REFCN
 * for the diagnostic register, so a mismatch can be diagnosed remotely from
 * a buried probe rather than guessed at. */
o2p_lmp_status_t o2p_lmp91000_verify(uint16_t *out_readback);

void o2p_lmp91000_gpio_init(void);

#endif /* O2P_LMP91000_H */
