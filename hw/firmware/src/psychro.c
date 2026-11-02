#include "psychro.h"

#include <math.h>
#include <stddef.h>

bool o2p_p_sat_hpa(float t_c, float *out_hpa)
{
    if (out_hpa == NULL) {
        return false;
    }
    if (!isfinite(t_c)) {
        return false;
    }
    /* Same singularity guard as o2p_dewpoint_c, for the same reason. */
    if (!(t_c > -(O2P_MAGNUS_B - 1.0f))) {
        return false;
    }
    float es = O2P_MAGNUS_ES0_HPA * expf((O2P_MAGNUS_A * t_c) /
                                         (O2P_MAGNUS_B + t_c));
    if (!isfinite(es) || !(es > 0.0f)) {
        return false;
    }
    *out_hpa = es;
    return true;
}

bool o2p_dewpoint_c(float t_c, float rh_pct, float *out_td_c)
{
    if (out_td_c == NULL) {
        return false;
    }
    /* An RH of exactly zero has no logarithm, and a negative or >100 reading
     * is a sensor fault rather than dry air. Refusing here is what keeps a
     * failed SHT45 from producing a comfortable-looking dew point. */
    if (!(rh_pct > 0.0f) || !(rh_pct <= 100.0f)) {
        return false;
    }
    if (!isfinite(t_c)) {
        return false;
    }
    /* The Magnus form is singular at t = -B; nothing in this application goes
     * near -243 C, but the guard costs nothing and removes an infinity. */
    if (!(t_c > -(O2P_MAGNUS_B - 1.0f))) {
        return false;
    }

    float alpha = logf(rh_pct / 100.0f) + (O2P_MAGNUS_A * t_c) / (O2P_MAGNUS_B + t_c);
    float denom = O2P_MAGNUS_A - alpha;
    if (!(fabsf(denom) > 1e-6f)) {
        return false;
    }
    float td = (O2P_MAGNUS_B * alpha) / denom;
    if (!isfinite(td)) {
        return false;
    }
    *out_td_c = td;
    return true;
}

bool o2p_dew_margin_k(float t_tip_c, float t_chamber_c, float rh_pct,
                      float *out_margin_k)
{
    if (out_margin_k == NULL) {
        return false;
    }
    float td;
    if (!o2p_dewpoint_c(t_chamber_c, rh_pct, &td)) {
        return false;
    }
    if (!isfinite(t_tip_c)) {
        return false;
    }
    *out_margin_k = t_tip_c - td;
    return true;
}
