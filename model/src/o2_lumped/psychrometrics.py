from __future__ import annotations

import math


def saturation_vapor_pressure_kpa(temp_c: float) -> float:
    """Buck (1981) saturation pressure over liquid water."""
    if not -80.0 <= temp_c <= 80.0:
        raise ValueError("Buck liquid-water correlation is restricted here to -80..80 C")
    return 0.61121 * math.exp((18.678 - temp_c / 234.5) * temp_c / (257.14 + temp_c))


def dew_point_c(temp_c: float, rh_pct: float) -> float:
    if not 0.0 <= rh_pct <= 100.0:
        raise ValueError("relative humidity must be within 0..100%")
    if rh_pct <= 0:
        return float("-inf")
    vapor_kpa = saturation_vapor_pressure_kpa(temp_c) * rh_pct / 100.0
    lo, hi = -80.0, 80.0
    if not saturation_vapor_pressure_kpa(lo) <= vapor_kpa <= saturation_vapor_pressure_kpa(hi):
        raise ValueError("dew point is outside the supported -80..80 C range")
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if saturation_vapor_pressure_kpa(mid) < vapor_kpa:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def local_rh_pct(ambient_temp_c: float, ambient_rh_pct: float, local_temp_c: float) -> float:
    if not 0.0 <= ambient_rh_pct <= 100.0:
        raise ValueError("relative humidity must be within 0..100%")
    return ambient_rh_pct * saturation_vapor_pressure_kpa(ambient_temp_c) / saturation_vapor_pressure_kpa(local_temp_c)
