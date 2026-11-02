#include "sampler.h"

/* Per-revision availability.
 *
 * A table rather than a chain of #ifs at each call site, so that adding a
 * revision is one row and forgetting a channel is a missing row rather than a
 * silently-taken else-branch.
 */
#if O2P_HW_HAS_ADS1119

/* Rev A. Every channel exists: AIN1 is the 47k/47k reference sense tap, AIN0
 * the AFE output, AIN2/AIN3 the buffered electrodes, and the ADS1119 has its
 * own shorted-input offset mode. */
static const bool k_available[O2P_CH_COUNT] = {
    [O2P_CH_VREF]   = true,
    [O2P_CH_AFE]    = true,
    [O2P_CH_WE]     = true,
    [O2P_CH_RE]     = true,
    [O2P_CH_OFFSET] = true,
};

#else

/* Rev B. Two channels genuinely do not exist and are NOT substituted:
 *
 *   O2P_CH_VREF - R34/R35, the 47k/47k sense divider, are deleted, and PA5 is
 *   not wired to /VREF_TRIM. The reference is now the ADC's own VREF+, so
 *   there is no on-chip channel that measures it independently. VREFINT is a
 *   COLLAPSE DETECTOR, not a drift monitor: its tempco (50 ppm/degC) and
 *   ACoeff (1000 ppm/1000 h) are 8x and 40x worse than the REF3425 it would be
 *   watching, so reporting it as a reference reading would be reporting the
 *   worse part's drift as the better part's.
 *
 *   O2P_CH_OFFSET - the ADS1119's shorted-input self-check. The STM32 SAR has
 *   no equivalent. Its nearest relative is CALFACT (see mcu_adc.h), which
 *   answers a different and more specific question: whether ES0418 2.6.7's
 *   offset erratum fired on this die.
 */
static const bool k_available[O2P_CH_COUNT] = {
    [O2P_CH_VREF]   = false,
    [O2P_CH_AFE]    = true,
    [O2P_CH_WE]     = true,
    [O2P_CH_RE]     = true,
    [O2P_CH_OFFSET] = false,
};

#endif

static const char *const k_names[O2P_CH_COUNT] = {
    [O2P_CH_VREF]   = "VREF",
    [O2P_CH_AFE]    = "AFE",
    [O2P_CH_WE]     = "WE",
    [O2P_CH_RE]     = "RE",
    [O2P_CH_OFFSET] = "OFFSET",
};

bool o2p_sampler_channel_available(o2p_channel_t ch)
{
    if ((unsigned)ch >= (unsigned)O2P_CH_COUNT) {
        return false;
    }
    return k_available[ch];
}

const char *o2p_sampler_channel_name(o2p_channel_t ch)
{
    if ((unsigned)ch >= (unsigned)O2P_CH_COUNT) {
        return "?";
    }
    return k_names[ch];
}
