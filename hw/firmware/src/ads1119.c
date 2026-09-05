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

/* SBAS925A 8.5.3.6: RREG with r=1 returns the STATUS register, whose bit 7
 * (DRDY) is the device's own statement that a conversion result is ready.
 * That is an authoritative answer from the converter. The DRDY PIN is only a
 * signal about it, and a signal can be forged by a floating trace. */
#define ADS_STATUS_DRDY 0x80u

static o2p_ads_status_t read_status(uint8_t *st)
{
    const uint8_t tx = O2P_ADS_CMD_RREG_STAT;
    return (o2p_i2c1_write_read(ADS_ADDR, &tx, 1u, st, 1u) == O2P_I2C_OK)
               ? O2P_ADS_OK : O2P_ADS_IO;
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
/* DRDY is low before we have started anything, so it is an UNREAD result from
 * some earlier conversion. In single-shot mode nothing releases DRDY except
 * reading that result: SBAS925A 8.5.1.3's automatic release after tw(DRH)
 * applies to CONTINUOUS conversion mode, and CM is always 0 in this driver.
 *
 * That matters more than it looks. Without this drain, a single failed RDATA
 * transfer - one NACK on a bus shared with the LMP91000, TMP117 and SHT45 -
 * strands a result in the output register, and every later conversion then
 * returns at the pre-START check WITHOUT issuing the RDATA that would clear
 * it. o2p_ads1119_init() is the only other thing that releases DRDY and it
 * runs once at boot, so one transient glitch would blank the oxygen channel
 * until someone power-cycles a probe that is buried in a compost pile.
 *
 * So: read the stale result, throw it away, and check the line actually
 * released. Returns true only if DRDY is observed HIGH afterwards. A
 * misconfigured pin (the original defect: PB1 in analog mode, IDR reads 0
 * forever) drains, re-reads low, and correctly stays failed. */
static o2p_ads_status_t drain_stale_result(void)
{
    const uint8_t rdata = O2P_ADS_CMD_RDATA;
    uint8_t rx[2] = {0u, 0u};
    if (o2p_i2c1_write_read(ADS_ADDR, &rdata, 1u, rx, 2u) != O2P_I2C_OK) {
        /* The BUS failed, not the pin. Returning O2P_ADS_DRDY here would
         * publish a bus fault as a pin fault - the exact mirror image of the
         * misreport this guard exists to remove, and just as capable of
         * sending a healthy part back as scrap. */
        return O2P_ADS_IO;
    }
    if ((O2P_ADC_DRDY_PORT->IDR & (1u << O2P_ADC_DRDY_PIN)) == 0u) {
        return O2P_ADS_DRDY;   /* read the result and the line still will not release */
    }
    return O2P_ADS_OK;
}

/* The EARLIEST a conversion can legitimately finish, SBAS925A Table 4, minus
 * one millisecond because o2p_millis() has 1 ms granularity and a t0 captured
 * just before a tick can make elapsed time read up to 1 ms high.
 *
 * This exists because sampling DRDY high once after START does NOT close the
 * intermittent-line hole it was written to close. A floating pin or an open
 * R19 can read high at that sample and spuriously low on the very next loop
 * evaluation, microseconds later - long before the real 11.1 ms or 50 ms
 * conversion could have completed. RDATA then returns "the most recent
 * conversion result" (SBAS925A 8.5.3.5), which is the PREVIOUS channel, and
 * the driver accepts it as current. That is the exact failure that got a
 * healthy ADS1119 desoldered, surviving two rounds of repair at reduced odds.
 *
 * A low that arrives before physics allows is not data. It is noise, and the
 * converter is the only thing that knows the difference - so do not ask the
 * pin, ask the clock. */
static uint32_t conversion_min_ms(uint8_t dr)
{
    switch (dr) {
    /* 1 ms at 1000 SPS leaves no margin against a 1 ms tick, so the clock gate
     * cannot help here and this returns 0 - o2p_elapsed(t0, 0) is immediately
     * true. That rate is protected by the status-register confirmation below
     * and by nothing else, which is fine because the confirmation is the part
     * that actually authenticates the result. No caller uses 1000 SPS today. */
    case O2P_ADS_DR_1000SPS: return 0u;
    case O2P_ADS_DR_330SPS:  return 2u;    /* 3 ms */
    case O2P_ADS_DR_90SPS:   return 10u;   /* 11.1 ms */
    default:                 return 49u;   /* 20 SPS, 50 ms */
    }
}

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
        /* Prove the device really took the new configuration, at RUN TIME and
         * not only at boot. Until this existed, read_cfg() had exactly one
         * caller - o2p_ads1119_init() - so O2P_ADS_CONFIG was unreachable
         * after start-up and the ADS1119 IDENTITY proof was a boot-only
         * statement: a wrong device at 0x40 that ACKs writes would have
         * surfaced later only as a timeout, if at all.
         *
         * s_last_cfg cannot do this job. It is a host-side cache of what we
         * INTENDED, so by construction it agrees with itself no matter what
         * the device did with the byte.
         *
         * This runs on channel/reference changes only - three per one-second
         * cycle - not per conversion. A device that stops storing config
         * mid-cycle is therefore caught within one cycle rather than at the
         * next conversion. That is a deliberate trade against ~50 us of bus
         * time on every one of the 15 conversions in a cycle. */
        uint8_t back = 0u;
        o2p_ads_status_t vst = write_cfg(cfg);
        if (vst == O2P_ADS_OK) {
            vst = read_cfg(&back);
        }
        if (vst != O2P_ADS_OK) {
            s_last_cfg = 0xFFu;
            return vst;
        }
        if (back != cfg) {
            s_last_cfg = 0xFFu;
            return O2P_ADS_CONFIG;
        }

        int16_t throwaway = 0;
        o2p_ads_status_t st = convert_once(cfg, dr, &throwaway);
        if (st != O2P_ADS_OK) {
            s_last_cfg = 0xFFu;   /* unknown state; discard again next time */
            return st;
        }
        s_last_cfg = cfg;
    }
    /* Invalidate the cached configuration on ANY failure, including on this
     * fast path. Until now only the change path did, which made the driver's
     * safety depend on a property of its CALLER: main.c happens to use three
     * mutually distinct configs, so an abandoned phase was always followed by
     * a change and hence a re-verify. Reorder the phases, add one that reuses
     * a config, or call o2p_ads1119_average() twice, and a device that had
     * silently lost its configuration would be converted from a stale
     * s_last_cfg with no readback. A driver must not be correct only because
     * of what today's caller happens to do. */
    o2p_ads_status_t st = convert_once(cfg, dr, out_code);
    if (st != O2P_ADS_OK) {
        s_last_cfg = 0xFFu;
    }
    return st;
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
        /* Try to recover before condemning the part - see drain_stale_result().
         * Recovering here is not hiding anything: whatever stranded the result
         * (a failed RDATA, or a conversion that landed just after the timeout)
         * raised its own fault bit in the cycle where it actually happened. */
        o2p_ads_status_t dst = drain_stale_result();
        if (dst != O2P_ADS_OK) {
            return dst;
        }
    }

    /* Writing the config already restarts any conversion, but START/SYNC is
     * what actually begins one in single-shot mode. */
    const uint8_t start = O2P_ADS_CMD_START;
    if (o2p_i2c1_write(ADS_ADDR, &start, 1u) != O2P_I2C_OK) {
        return O2P_ADS_IO;
    }

    /* A conversion has just been started and the fastest data rate this driver
     * uses is 1000 SPS - 1 ms - so DRDY must still be HIGH here, microseconds
     * later. (Strictly this also assumes bounded software latency between the
     * START transfer and this read: a long enough interrupt could let a real
     * 1000 SPS conversion complete first. It holds because the committed call
     * sites use only 90 and 20 SPS and the enabled handlers are short - but
     * it is an assumption about THIS firmware, not a datasheet guarantee.) Confirming that closes the hole the drain above would otherwise
     * open: an INTERMITTENT line (a floating pin, an open R19) can read low,
     * drain, then read high by chance, and the wait below would exit on the
     * first spurious low and issue RDATA on a conversion that never finished -
     * the original "returns the previous channel" signature, at reduced odds
     * rather than eliminated. A deterministic dead line is caught either way;
     * this is for the noisy one. */
    if ((O2P_ADC_DRDY_PORT->IDR & (1u << O2P_ADC_DRDY_PIN)) == 0u) {
        return O2P_ADS_DRDY;
    }

    /* Wait on the DRDY pin (PB1, open-drain, R19 pull-up): it falls when the
     * result is ready. Polling the status register would work too but costs a
     * bus transaction per poll on a bus shared with three other devices. */
    uint32_t t0 = o2p_millis();
    uint32_t limit = conversion_timeout_ms(dr);
    uint32_t earliest = conversion_min_ms(dr);
    for (;;) {
        if ((O2P_ADC_DRDY_PORT->IDR & (1u << O2P_ADC_DRDY_PIN)) == 0u) {
            /* The pin says ready. Two things must agree before that is
             * believed. First the clock: a low earlier than the datasheet
             * allows is noise. Second, and decisively, THE DEVICE ITSELF -
             * because "earliest possible" cannot authenticate WHICH
             * conversion a noisy pin is talking about. A floating line that
             * happens to read low inside the plausible window would otherwise
             * pass the clock gate, and RDATA would hand back the most recent
             * COMPLETED conversion (SBAS925A 8.5.3.5) - the previous channel -
             * as O2P_ADS_OK. That is the original defect, and narrowing its
             * window three times is not the same as closing it.
             *
             * The status register is the authority. A pin is a rumour. */
            if (o2p_elapsed(t0, earliest)) {
                uint8_t stat = 0u;
                o2p_ads_status_t sst = read_status(&stat);
                if (sst != O2P_ADS_OK) {
                    return sst;
                }
                if ((stat & ADS_STATUS_DRDY) != 0u) {
                    break;      /* the converter itself says the result is ready */
                }
                /* Pin low, device says no result: the pin is lying. Keep
                 * waiting - the timeout below is what ends this. */
            }
        }
        if (o2p_elapsed(t0, limit)) {
            /* Distinguish a PIN failure from a DEVICE failure with evidence
             * rather than by assumption. If the converter reports a result
             * ready but the pin never fell, the pin path is broken. If the
             * converter reports nothing ready either, then the bus and the
             * command were fine but the device did not convert - a device
             * fault, not a pin fault. An earlier version of this code mapped
             * every timeout to the DRDY bit, which was a label change rather
             * than a diagnosis: TIMEOUT alone proves only "no valid ready was
             * observed", never "the pin failed". */
            uint8_t stat = 0u;
            if (read_status(&stat) == O2P_ADS_OK &&
                (stat & ADS_STATUS_DRDY) != 0u) {
                return O2P_ADS_DRDY;        /* result ready, pin never said so */
            }
            return O2P_ADS_TIMEOUT;         /* device produced no conversion */
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
