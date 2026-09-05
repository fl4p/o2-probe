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
    /* AIN2/AIN3 are the BUFFERED CELL ELECTRODES, WE_BUF and RE_BUF - not
     * rails. They read 3V3A/2 and +12V_SW*10/92 in an older revision, and this
     * comment still said so on 2026-09-05 while main.c sampled AIN3 and called
     * the result vin_mv. Both rails now live on the MCU's own ADC (mcu_adc.h).
     * NOTHING READS AIN2/AIN3 TODAY: the differential cell-bias telemetry
     * DESIGN.md describes for them is specified but not implemented. */
    O2P_ADS_MUX_AIN2_AGND = 5u,  /* 101 - WE_BUF */
    O2P_ADS_MUX_AIN3_AGND = 6u,  /* 110 - RE_BUF */
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
    /* DRDY was already low before a conversion was started - so it cannot be
     * this conversion's completion. Distinct from O2P_ADS_TIMEOUT, which is
     * DRDY stuck HIGH: that one announces itself by never arriving, while
     * stuck LOW is the silent failure, satisfying the wait instantly and
     * handing back the PREVIOUS conversion for as long as the board runs. */
    O2P_ADS_DRDY,
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

/* Is this conversion pinned against a rail?
 *
 * A saturated converter reports the same code however the input moves, so it
 * cannot say "the signal left my range" - it just keeps answering, and the
 * answer looks like a measurement. Six minutes of a saturated TIA were once
 * read as a steady 607 uA while the cell was actually polarising: 622 uA and
 * 240 uA are the same number once the channel is pinned.
 *
 * Positive full scale is +32767. Single-ended readings should not go negative
 * at all (SBAS925A 8.3.2), so the negative rail is included rather than
 * assumed unreachable - a negative code already means something is wrong, and
 * one pinned at -32768 is wrong AND unquantified.
 *
 * The margin is a few LSB rather than an exact equality: a signal sitting on
 * the rail dithers by a count or two of noise, and an equality test would miss
 * it on exactly the samples where it matters. */
#define O2P_ADS_CLIP_MARGIN 8

static inline bool o2p_ads1119_code_clipped(int16_t code)
{
    return (code >= (32767 - O2P_ADS_CLIP_MARGIN)) ||
           (code <= (-32768 + O2P_ADS_CLIP_MARGIN));
}

/* Average n conversions of one channel. Returns the first error encountered:
 * a partial average is not a measurement. */
o2p_ads_status_t o2p_ads1119_average(uint8_t mux, uint8_t dr, bool ext_ref,
                                     unsigned n, int32_t *out_code);

/* Millivolts at the ADC pin, given the reference actually used. */
int32_t o2p_ads1119_code_to_uv(int32_t code, uint32_t vref_mv);

#endif /* O2P_ADS1119_H */
