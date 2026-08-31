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
               "CAL_DEFAULT must not invalidate: an uncalibrated cell is "
               "low-accuracy data, not absent data");
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_SETTLING) != 0,
               "SETTLING must invalidate: the cell needs up to 15 min after a "
               "bias interruption (DS-0637)");
