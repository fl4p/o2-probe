/* Psychrometry for the condensation-margin channel.
 *
 * The probe exists in 100 %RH pore gas. A buried probe conducts heat outward,
 * so without a heated membrane every surface sits below the dew point and the
 * SGX cell - rated 15-90 %RH continuous, non-condensing - drowns. The margin
 * computed here is the quantity the v1 heater loop will regulate, and in v0 it
 * is the channel that tells us whether the cell is being destroyed.
 *
 * Magnus-Tetens with the Sonntag coefficients over water.
 */
#ifndef O2P_PSYCHRO_H
#define O2P_PSYCHRO_H

#include <stdbool.h>

/* Magnus coefficients over water, valid roughly -45..+60 C. The pile runs to
 * ~75 C, beyond the fit's stated range, so a dew point computed up there is an
 * extrapolation - the same honesty problem as the cell's tempco. */
#define O2P_MAGNUS_A 17.62f
#define O2P_MAGNUS_B 243.12f

/* Dew point in C from air temperature (C) and relative humidity (%).
 * Returns false and writes nothing if the inputs cannot yield a dew point:
 * RH <= 0 has no logarithm, and RH > 100 is not a measurement. */
bool o2p_dewpoint_c(float t_c, float rh_pct, float *out_td_c);

/* Condensation margin: how far the warm tip sits ABOVE the chamber dew point.
 * Negative means the tip is at or below dew point and is condensing, which is
 * the failure the heater exists to prevent. Returns false if unevaluable. */
bool o2p_dew_margin_k(float t_tip_c, float t_chamber_c, float rh_pct,
                      float *out_margin_k);

#endif /* O2P_PSYCHRO_H */
