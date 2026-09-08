/* The fault word is header-only logic; this translation unit exists so the
 * host test environment has something to link and so a future non-inline
 * helper has an obvious home. */
#include "faults.h"

/* Compile-time proof that the two documented non-invalidating faults really
 * are excluded from the invalidation mask. This is the rule most likely to be
 * "tidied" by someone who has not read PLAN.md:211-228. */
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_TEMP_OVER) == 0,
               "TEMP_OVER must not invalidate: it flags extrapolation above "
               "60 C, and discarding those readings loses the thermophilic "
               "phase the probe exists to observe (PLAN.md:211-228)");
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_CAL_DEFAULT) == 0,
               "CAL_DEFAULT must not invalidate the RAW channel: cell current "
               "is a real measurement with or without a calibration constant");
_Static_assert((O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_CAL_DEFAULT) != 0,
               "CAL_DEFAULT MUST invalidate the COMPENSATED channel: the "
               "datasheet nominal spans 0.04-0.10 mA in air, so a substituted "
               "constant can be 43 percent out and still look like a plausible "
               "oxygen reading");
_Static_assert((O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_TEMP_OVER) == 0,
               "TEMP_OVER must not invalidate either channel");
_Static_assert((O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_SETTLING) != 0,
               "SETTLING must invalidate the COMPENSATED channel: the cell "
               "needs up to 15 min after a bias interruption (DS-0637), and no "
               "%vol derived from a cell that has not reached equilibrium is "
               "trustworthy");
/* The other half of that classification, and the reason it is asserted rather
 * than left to the mask definition: O2P_FAULTS_INVALIDATE_O2_COMP is written
 * in terms of O2P_FAULTS_INVALIDATE_O2, so moving a bit between them is a
 * one-line edit that can silently strip a gate from the verdict (3c8d884) or
 * silently restore one to the raw channel. Both directions are pinned.
 *
 * Warmup does not make the cell current meaningless - it makes it
 * UNINTERPRETABLE AS OXYGEN, which is a statement about the divisor, not the
 * measurement. During warmup the current is the only record of the cell
 * recovering, and blanking it deleted the 101.04 -> 100.60 uA transient across
 * both power cycles on 2026-09-08, which was the evidence for whether the
 * 900 s window is long enough. Same reasoning as CAL_DEFAULT above. */
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_SETTLING) == 0,
               "SETTLING must NOT invalidate the RAW channel: cell current is "
               "a real measurement of an unsettled cell, and it is the only "
               "record of the settling transient itself");
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_ADS_DRDY_STUCK) != 0,
               "ADS_DRDY_STUCK must invalidate: a DRDY that will not release "
               "means the converter either produced nothing or would hand back "
               "a PREVIOUS conversion, and stale data wearing the current "
               "timestamp is the failure this whole guard exists to stop");
_Static_assert((O2P_F_ADS_DRDY_STUCK & O2P_F_I2C_FAIL_ADS) == 0,
               "ADS_DRDY_STUCK must stay a SEPARATE bit from I2C_FAIL_ADS: "
               "collapsing a pin failure into the bus fault is what got a "
               "healthy ADS1119 replaced");
_Static_assert((O2P_FAULTS_ADS_NO_CONVERSION & O2P_FAULTS_INVALIDATE_O2)
                   == O2P_FAULTS_ADS_NO_CONVERSION,
               "every way the ADS1119 can fail to deliver a conversion must "
               "also invalidate O2: there is no reading to publish");
_Static_assert((O2P_FAULTS_ADS_NO_CONVERSION & O2P_F_ADS_CONFIG_LOST) != 0,
               "a config the device did not store means the conversion was "
               "taken on an unknown channel or reference: there is no reading");
_Static_assert((O2P_FAULTS_LATCHED & O2P_FAULTS_INVALIDATE_O2)
                   == O2P_FAULTS_LATCHED,
               "only bits that invalidate O2 may be latched: holding a bit "
               "past the cycle it occurred in overstates the present, and "
               "that is only worth doing for a fault that made the reading "
               "untrustworthy");
_Static_assert((O2P_FAULTS_LATCHED & O2P_F_SETTLING) == 0,
               "SETTLING must NOT be latched: it already lasts up to 15 min, "
               "so latching it would extend a long fault rather than preserve "
               "a brief one, and would keep the probe looking unsettled for "
               "five minutes after it had genuinely settled");
_Static_assert((O2P_FAULTS_LATCHED & O2P_FAULTS_ADS_NO_CONVERSION)
                   == O2P_FAULTS_ADS_NO_CONVERSION,
               "every ADS no-conversion bit must be latched: these are "
               "precisely the one-cycle events that a five-minute poll misses "
               "299 times out of 300, which is what the latch is for");

uint16_t o2p_fault_latch_step(o2p_fault_latch_t *l, uint16_t cycle_faults,
                              uint32_t now_s)
{
    const uint16_t fresh = (uint16_t)(cycle_faults & O2P_FAULTS_LATCHED);

    if (fresh != 0u) {
        /* Refreshing the window on every occurrence is what keeps a
         * repeatedly glitching probe from reading clean between glitches -
         * without it the deadline is set once and a probe faulting every
         * minute goes quiet 330 s in. That behaviour IS load-bearing and is
         * tested.
         *
         * Handling `fresh` before the expiry test is only tidiness: when the
         * fault is still occurring, `cycle_faults` carries it into the
         * returned word regardless of what the latch does, so both orderings
         * publish the same thing. Deliberately not claimed as a guard - a
         * known-bad run with the orderings swapped passes every test here,
         * because there is nothing to catch. */
        l->bits |= fresh;
        l->until_s = now_s + O2P_FAULT_LATCH_S;
    } else if (l->bits != 0u) {
        /* Signed difference, so the comparison survives the uptime counter
         * wrapping.
         *
         * Measured, with a known-bad build using a plain unsigned `>=`: a
         * fault raised just before the wrap sets `until_s` to a small
         * post-wrap value, so the very next cycle finds a huge `now_s` past
         * it and RELEASES the bit immediately - the latch silently stops
         * working for the one event it was holding. (The intuition that it
         * would instead stick forever is wrong; it fails open, not closed,
         * which is the worse of the two.) */
        if ((int32_t)(now_s - l->until_s) >= 0) {
            l->bits = 0u;
        }
    }

    return (uint16_t)(cycle_faults | l->bits);
}
