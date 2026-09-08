/* ADS1119 16-bit delta-sigma ADC, I2C 0x40 (A0 = A1 = GND).
 *
 * Register and command encodings verified against TI SBAS925A (Nov 2018),
 * Table 7 "Command Definitions" and Table 10 "Configuration Register Field
 * Descriptions" - not from memory.
 *
 * The board wires REFP to VREF_TRIM and REFN to GND, so oxygen is measured
 * RATIOMETRICALLY against the same reference that sets the LMP91000's bias and
 * internal zero. One exception, and it is deliberate: the VREF health check
 * reads VREF/2 against the ADC's own internal 2.048 V reference, because a
 * converter referenced to the thing it is checking cannot detect that thing
 * drifting (gen_sch.py C29 note).
 */
#ifndef O2P_ADS1119_H
#define O2P_ADS1119_H

#include <stdbool.h>
#include <stdint.h>

/* Commands, SBAS925A Table 7. The low bits are don't-care. */
enum {
    O2P_ADS_CMD_RESET     = 0x06u,  /* 0000 011x */
    O2P_ADS_CMD_START     = 0x08u,  /* 0000 100x */
    O2P_ADS_CMD_POWERDOWN = 0x02u,  /* 0000 001x */
    O2P_ADS_CMD_RDATA     = 0x10u,  /* 0001 xxxx */
    O2P_ADS_CMD_RREG_CFG  = 0x20u,  /* 0010 0rxx, r = 0 -> config */
    O2P_ADS_CMD_RREG_STAT = 0x24u,  /* r = 1 -> status */
    O2P_ADS_CMD_WREG      = 0x40u,  /* 0100 00xx */
};

/* Config register: MUX[2:0] 7:5 | GAIN 4 | DR[1:0] 3:2 | CM 1 | VREF 0. */
enum {
    O2P_ADS_MUX_AIN0_AGND = 3u,  /* 011 - AFE_VOUT, the oxygen channel */
    O2P_ADS_MUX_AIN1_AGND = 4u,  /* 100 - VREF_TRIM / 2 */
    O2P_ADS_MUX_AIN2_AGND = 5u,  /* 101 - 3V3A / 2 */
    O2P_ADS_MUX_AIN3_AGND = 6u,  /* 110 - +12V_SW * 10/92 */
};
enum { O2P_ADS_DR_20SPS = 0u, O2P_ADS_DR_90SPS = 1u,
       O2P_ADS_DR_330SPS = 2u, O2P_ADS_DR_1000SPS = 3u };
enum { O2P_ADS_REF_INTERNAL = 0u, O2P_ADS_REF_EXTERNAL = 1u };

#define O2P_ADS_INTERNAL_REF_MV 2048u

typedef enum {
    O2P_ADS_OK = 0,
    O2P_ADS_IO,        /* the I2C transfer failed */
    O2P_ADS_TIMEOUT,   /* DRDY never asserted */
    O2P_ADS_CONFIG,    /* the config register did not read back as written */
} o2p_ads_status_t;

/* Reset the part and prove it is really an ADS1119 responding by writing a
 * non-default config and reading it back. A device that acknowledges its
 * address but does not store configuration is not this chip. */
o2p_ads_status_t o2p_ads1119_init(void);

/* One single-shot conversion. Returns the raw signed code.
 *
 * In single-ended mode the device "only uses the code range that represents
 * positive differential voltages" (SBAS925A 8.3.2), so a healthy reading is
 * 0..32767 and a negative code means the input went below AGND - reported
 * rather than clamped, because on AIN0 that is exactly the inverted-cell-
 * polarity symptom the bench needs to see.
 */
o2p_ads_status_t o2p_ads1119_convert(uint8_t mux, uint8_t dr, bool ext_ref,
                                     int16_t *out_code);

/* Average n conversions of one channel. Returns the first error encountered:
 * a partial average is not a measurement. */
o2p_ads_status_t o2p_ads1119_average(uint8_t mux, uint8_t dr, bool ext_ref,
                                     unsigned n, int32_t *out_code);

/* MICROvolts at the ADC pin, given the reference actually used - as the name
 * says and every caller assumes. The comment said millivolts. */
int32_t o2p_ads1119_code_to_uv(int32_t code, uint32_t vref_mv);

#endif /* O2P_ADS1119_H */
