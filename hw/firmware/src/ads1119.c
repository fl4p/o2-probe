#include "ads1119.h"

#include "board_pins.h"
#include "i2c1.h"
#include "mcu.h"

#define ADS_ADDR O2P_HW_I2C_ADDR_ADS1119

/* Last configuration actually converted with. SBAS925A 8.3.3 says the internal
 * reference needs under 25 us to settle "when switching from the external
 * reference source to the internal reference", and switching the multiplexer
 * likewise presents the modulator with a step. A single-shot conversion
 * started immediately after either change can therefore be taken on a settling
 * input - and this driver's very first use of that is the VREF HEALTH CHECK,
 * where a bad reading would falsely condemn a perfectly good reference. So the
 * first conversion after any change of channel or reference is discarded. */
static uint8_t s_last_cfg = 0xFFu;

static o2p_ads_status_t convert_once(uint8_t cfg, uint8_t dr, int16_t *out_code);


static uint8_t cfg_byte(uint8_t mux, uint8_t dr, bool ext_ref)
{
    /* GAIN stays at 1 and CM at single-shot. Gain 4 would halve the LSB but
     * clips at VREF/4 = 625 mV, and the oxygen channel swings about 1.06 V
     * from its 1.675 V zero - so gain 4 is unusable here, not merely
     * unnecessary. Single-shot because the sample loop is 1 Hz: continuous
     * conversion would keep the modulator running for nothing. */
    return (uint8_t)(((mux & 7u) << 5) | ((dr & 3u) << 2) | (ext_ref ? 1u : 0u));
}

static o2p_ads_status_t write_cfg(uint8_t cfg)
{
    const uint8_t tx[2] = {O2P_ADS_CMD_WREG, cfg};
    return (o2p_i2c1_write(ADS_ADDR, tx, 2u) == O2P_I2C_OK) ? O2P_ADS_OK : O2P_ADS_IO;
}

static o2p_ads_status_t read_cfg(uint8_t *cfg)
{
    const uint8_t tx = O2P_ADS_CMD_RREG_CFG;
    return (o2p_i2c1_write_read(ADS_ADDR, &tx, 1u, cfg, 1u) == O2P_I2C_OK)
               ? O2P_ADS_OK : O2P_ADS_IO;
}

o2p_ads_status_t o2p_ads1119_init(void)
{
    /* RESET pin has no GPIO on this board (R18 holds it released), so the
     * command is the only reset available - which is why it is used first,
     * before trusting anything the part says. */
    /* DRDY is an input this driver polls, and until now NOTHING configured
     * it. PB1 comes out of reset in ANALOG mode (MODER = 11), which
     * disconnects the input buffer so IDR reads 0 forever - regardless of
     * R19 holding the real pin high. The wait in convert_once() therefore
     * fell through on its FIRST evaluation, RDATA was issued before the
     * conversion had finished, and the part returned the PREVIOUS
     * conversion. Every channel read as whichever channel preceded it, which
     * is exactly the "AIN3 mirrors AIN0" signature that got a healthy
     * ADS1119 replaced. It also disabled O2P_ADS_TIMEOUT, a guard that
     * cannot fire when the wait it protects never happens.
     * No internal pull: R19 pulls the line up on the board. */
    O2P_ADC_DRDY_PORT->MODER &= ~(3u << (O2P_ADC_DRDY_PIN * 2u));

    s_last_cfg = 0xFFu;   /* a reset invalidates any cached configuration */
    const uint8_t rst = O2P_ADS_CMD_RESET;
    if (o2p_i2c1_write(ADS_ADDR, &rst, 1u) != O2P_I2C_OK) {
        return O2P_ADS_IO;
    }
    o2p_delay_ms(1u);

    /* Prove the part stores configuration. A bus stub, a short, or a
     * different device at 0x40 can all ACK an address; only an ADS1119 will
     * hand this pattern back. Reset default is 0x00, so a non-zero pattern
     * also proves the write took effect rather than the read returning the
     * default. */
    const uint8_t probe = cfg_byte(O2P_ADS_MUX_AIN1_AGND, O2P_ADS_DR_20SPS, false);
    if (write_cfg(probe) != O2P_ADS_OK) {
        return O2P_ADS_IO;
    }
    uint8_t back = 0u;
    if (read_cfg(&back) != O2P_ADS_OK) {
        return O2P_ADS_IO;
    }
    if (back != probe) {
        return O2P_ADS_CONFIG;
    }

    /* Precondition for every conversion this driver will ever do: DRDY must
     * be a readable digital input that idles HIGH. Nothing has been started
     * since the reset above, so a low here means the pin is misconfigured or
     * unreachable - and a DRDY stuck low does not fail, it silently returns
     * stale conversions. Check it once, here, rather than discover it as
     * telemetry that looks plausible. */
    if ((O2P_ADC_DRDY_PORT->IDR & (1u << O2P_ADC_DRDY_PIN)) == 0u) {
        return O2P_ADS_DRDY;
    }
    return O2P_ADS_OK;
}

/* Conversion times, SBAS925A Table 4, plus the 28.5 tCLK start latency:
 * 20 SPS is 50 ms, 90 SPS 11.1 ms, 330 SPS 3 ms, 1000 SPS 1 ms. Budget
 * generously - a timeout here becomes a fault bit, not a retry storm. */
static uint32_t conversion_timeout_ms(uint8_t dr)
{
    switch (dr) {
    case O2P_ADS_DR_1000SPS: return 5u;
    case O2P_ADS_DR_330SPS:  return 10u;
    case O2P_ADS_DR_90SPS:   return 25u;
    default:                 return 80u;   /* 20 SPS */
    }
}

o2p_ads_status_t o2p_ads1119_convert(uint8_t mux, uint8_t dr, bool ext_ref,
                                     int16_t *out_code)
{
    if (out_code == NULL) {
        return O2P_ADS_IO;
    }
    uint8_t cfg = cfg_byte(mux, dr, ext_ref);
    if (cfg != s_last_cfg) {
        int16_t throwaway = 0;
        o2p_ads_status_t st = convert_once(cfg, dr, &throwaway);
        if (st != O2P_ADS_OK) {
            s_last_cfg = 0xFFu;   /* unknown state; discard again next time */
            return st;
        }
        s_last_cfg = cfg;
    }
    return convert_once(cfg, dr, out_code);
}

static o2p_ads_status_t convert_once(uint8_t cfg, uint8_t dr, int16_t *out_code)
{
    o2p_ads_status_t st = write_cfg(cfg);
    if (st != O2P_ADS_OK) {
        return st;
    }

    /* DRDY must idle HIGH here: nothing has been started yet, so a low line
     * cannot be this conversion's completion. Checking it once at init is not
     * enough - the pin can be misconfigured by any later code, and a DRDY
     * stuck low never fails, it satisfies the wait below on its first
     * evaluation and returns the PREVIOUS conversion forever. That is the
     * failure that got a healthy ADS1119 replaced, and O2P_ADS_TIMEOUT cannot
     * catch it: a timeout only fires for DRDY stuck HIGH. This costs one GPIO
     * read per conversion and no bus traffic. */
    if ((O2P_ADC_DRDY_PORT->IDR & (1u << O2P_ADC_DRDY_PIN)) == 0u) {
        return O2P_ADS_DRDY;
    }

    /* Writing the config already restarts any conversion, but START/SYNC is
     * what actually begins one in single-shot mode. */
    const uint8_t start = O2P_ADS_CMD_START;
    if (o2p_i2c1_write(ADS_ADDR, &start, 1u) != O2P_I2C_OK) {
        return O2P_ADS_IO;
    }

    /* Wait on the DRDY pin (PB1, open-drain, R19 pull-up): it falls when the
     * result is ready. Polling the status register would work too but costs a
     * bus transaction per poll on a bus shared with three other devices. */
    uint32_t t0 = o2p_millis();
    uint32_t limit = conversion_timeout_ms(dr);
    while ((O2P_ADC_DRDY_PORT->IDR & (1u << O2P_ADC_DRDY_PIN)) != 0u) {
        if (o2p_elapsed(t0, limit)) {
            return O2P_ADS_TIMEOUT;
        }
    }

    const uint8_t rdata = O2P_ADS_CMD_RDATA;
    uint8_t rx[2] = {0u, 0u};
    if (o2p_i2c1_write_read(ADS_ADDR, &rdata, 1u, rx, 2u) != O2P_I2C_OK) {
        return O2P_ADS_IO;
    }
    *out_code = (int16_t)(((uint16_t)rx[0] << 8) | rx[1]);
    return O2P_ADS_OK;
}

o2p_ads_status_t o2p_ads1119_average(uint8_t mux, uint8_t dr, bool ext_ref,
                                     unsigned n, int32_t *out_code)
{
    if (out_code == NULL || n == 0u || n > 64u) {
        return O2P_ADS_IO;
    }
    int32_t acc = 0;
    for (unsigned i = 0; i < n; i++) {
        int16_t c = 0;
        o2p_ads_status_t st = o2p_ads1119_convert(mux, dr, ext_ref, &c);
        if (st != O2P_ADS_OK) {
            /* Do not average what we have. Half a sample set taken before a
             * device died is not a lower-confidence reading, it is a reading
             * of an unknown interval. */
            return st;
        }
        acc += c;
    }
    *out_code = acc / (int32_t)n;
    return O2P_ADS_OK;
}

int32_t o2p_ads1119_code_to_uv(int32_t code, uint32_t vref_mv)
{
    /* FSR = +/-VREF at gain 1, and full scale is 2^15 codes (SBAS925A 8.4.5:
     * 1 LSB = 2*VREF/2^16 = +FS/2^15). With VREF = 2500 mV that is 76.29 uV
     * per code. Done in int64 so the intermediate cannot overflow: 32767 *
     * 2500000 exceeds int32. */
    int64_t uv = ((int64_t)code * (int64_t)vref_mv * 1000) / 32768;
    return (int32_t)uv;
}
