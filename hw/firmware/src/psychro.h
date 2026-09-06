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
/* Saturation pressure at 0 C, hPa, the Sonntag prefactor that goes with the
 * two coefficients above. It is here rather than in o2.c because there must
 * be exactly ONE Magnus implementation in this firmware: the oxygen channel's
 * water-vapour correction and the dew-margin channel are the same physics,
 * and two copies of these three numbers is how they drift apart.
 * O2-HUMIDITY-CORRECTION.md 5 says so explicitly. */
#define O2P_MAGNUS_ES0_HPA 6.112f

/* Saturation vapour pressure over water, in hPa, at t_c.
 *
 *     e_s = 6.112 * exp(A*t / (B+t))          [Sonntag, over water]
 *
 * Returns false and writes nothing if the temperature cannot yield one - not
 * finite, or at the Magnus singularity. Note what it does NOT refuse: the
 * fit's stated range ends near +60 C and the pile runs to ~75 C, so a value
 * up there is an EXTRAPOLATION. Refusing it here would silently disable the
 * oxygen vapour correction exactly where it is largest, so the range judgement
 * is left to the caller, which has a fault word to say so with (see
 * O2P_VAPOUR_T_MAX_C in o2.h).
 *
 * This is the function o2.c uses; it must not grow a second implementation. */
bool o2p_p_sat_hpa(float t_c, float *out_hpa);

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
