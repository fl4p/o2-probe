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
               "datasheet nominal spans 0.07-0.13 mA in air, so a substituted "
               "constant can be 43 percent out and still look like a plausible "
               "oxygen reading");
_Static_assert((O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_TEMP_OVER) == 0,
               "TEMP_OVER must not invalidate either channel");
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_CAL_ZERO_DEFAULT) == 0 &&
               (O2P_FAULTS_INVALIDATE_O2_COMP & O2P_F_CAL_ZERO_DEFAULT) == 0,
               "CAL_ZERO_DEFAULT must not invalidate EITHER channel: a missing "
               "zero point is a bounded offset (DS-0637: < 0.4 %vol O2), not an "
               "unknown scale factor. Making it invalidate would blank the "
               "compensated channel on every probe built so far");
_Static_assert(O2P_F_CAL_ZERO_DEFAULT != O2P_F_CAL_DEFAULT,
               "the two calibration faults are separate bits on purpose: they "
               "differ by two orders of magnitude in consequence and one "
               "invalidates while the other does not");
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_SETTLING) != 0,
               "SETTLING must invalidate: the cell needs up to 15 min after a "
               "bias interruption (DS-0637)");
