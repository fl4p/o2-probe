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
_Static_assert((O2P_FAULTS_INVALIDATE_O2 & O2P_F_SETTLING) != 0,
               "SETTLING must invalidate: the cell needs up to 15 min after a "
               "bias interruption (DS-0637)");
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
