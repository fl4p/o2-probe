from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import StepWindow


def analyze_steps(frame: pd.DataFrame, windows: list[StepWindow]) -> list[dict[str, float | str | bool | None]]:
    return [_analyze_step(frame, window) for window in windows]


def _analyze_step(frame: pd.DataFrame, window: StepWindow) -> dict[str, float | str | bool | None]:
    baseline_rows = frame[
        (frame.time_s >= window.baseline_start_s) & (frame.time_s <= window.baseline_end_s)
    ]
    steady_rows = frame[
        (frame.time_s >= window.steady_start_s) & (frame.time_s <= window.steady_end_s)
    ]
    transition = frame[(frame.time_s >= window.start_s) & (frame.time_s <= window.steady_end_s)]
    if baseline_rows.empty or steady_rows.empty or transition.empty:
        raise ValueError(f"step {window.label!r} has an empty analysis window")
    baseline = float(baseline_rows["o2_probe_pct_wet"].mean())
    steady = float(steady_rows["o2_probe_pct_wet"].mean())
    reference_baseline = float(baseline_rows["o2_reference_pct_wet"].mean())
    reference_steady = float(steady_rows["o2_reference_pct_wet"].mean())
    reference_amplitude = reference_steady - reference_baseline
    target_amplitude = reference_steady - baseline
    steady_times = steady_rows["time_s"].to_numpy(dtype=float)
    steady_values = steady_rows["o2_probe_pct_wet"].to_numpy(dtype=float)
    steady_slope_per_s = (
        float(np.polyfit(steady_times - steady_times[0], steady_values, 1)[0])
        if len(steady_rows) >= 2
        else float("nan")
    )
    tolerance = max(abs(reference_amplitude) * 0.02, 1e-6)
    steady_duration = max(float(steady_times[-1] - steady_times[0]), 1.0)
    steady_state_reached = bool(
        np.isfinite(steady_slope_per_s)
        and abs(steady - reference_steady) <= tolerance
        and abs(steady_slope_per_s) <= tolerance / steady_duration
    )
    pressure_stable = (
        "pressure_reference_kpa" not in transition
        or float(np.ptp(np.concatenate([
            baseline_rows["pressure_reference_kpa"].to_numpy(dtype=float),
            transition["pressure_reference_kpa"].to_numpy(dtype=float),
        ]))) <= 0.05
    )
    result: dict[str, float | str | bool | None] = {
        "label": window.label,
        "baseline_o2_pct_wet": baseline,
        "steady_o2_pct_wet": steady,
        "reference_amplitude_o2_pct_wet": reference_amplitude,
        "target_amplitude_o2_pct_wet": target_amplitude,
        "steady_slope_o2_pct_per_min": steady_slope_per_s * 60.0,
        "steady_state_reached": steady_state_reached,
        "response_metrics_valid": pressure_stable,
        "response_metrics_invalid_reason": None if pressure_stable else "pressure changed during response window",
    }
    for fraction, name in ((0.10, "t10_s"), (1.0 - math.exp(-1.0), "t63_s"), (0.90, "t90_s")):
        result[name] = (
            _crossing_time(transition, baseline, target_amplitude, fraction, window.start_s)
            if pressure_stable
            else None
        )
    result["settling_time_2pct_s"] = (
        _settling_time(
            transition,
            reference_steady,
            reference_amplitude,
            window.start_s,
            0.02,
            steady_state_reached,
        )
        if pressure_stable
        else None
    )
    result["steady_bias_o2_pct_wet"] = steady - reference_steady
    result["heater_energy_j"] = float(np.trapezoid(
        transition["heater_applied_w"].to_numpy(dtype=float),
        transition["time_s"].to_numpy(dtype=float),
    ))
    if "o2_probe_observed_pct" in frame:
        observed = frame.loc[transition.index, "o2_probe_observed_pct"].to_numpy(dtype=float)
        predicted = transition["o2_probe_pct_wet"].to_numpy(dtype=float)
        result["rmse_o2_pct"] = float(np.sqrt(np.mean((predicted - observed) ** 2)))
    else:
        result["rmse_o2_pct"] = None
    return result


def _crossing_time(
    transition: pd.DataFrame,
    baseline: float,
    amplitude: float,
    fraction: float,
    start_s: float,
) -> float | None:
    if abs(amplitude) < 1e-12:
        return None
    normalized = (transition["o2_probe_pct_wet"].to_numpy(dtype=float) - baseline) / amplitude
    times = transition["time_s"].to_numpy(dtype=float)
    indices = np.flatnonzero(normalized >= fraction)
    if not len(indices):
        return None
    index = int(indices[0])
    if index == 0:
        return max(float(times[0] - start_s), 0.0)
    y0, y1 = normalized[index - 1], normalized[index]
    t0, t1 = times[index - 1], times[index]
    crossing = t1 if y1 == y0 else t0 + (fraction - y0) * (t1 - t0) / (y1 - y0)
    return max(float(crossing - start_s), 0.0)


def _settling_time(
    transition: pd.DataFrame,
    steady: float,
    amplitude: float,
    start_s: float,
    band_fraction: float,
    steady_state_reached: bool,
    post_settle_horizon_s: float = 10.0,
) -> float | None:
    if not steady_state_reached:
        return None
    tolerance = max(abs(amplitude) * band_fraction, 1e-6)
    errors = np.abs(transition["o2_probe_pct_wet"].to_numpy(dtype=float) - steady)
    times = transition["time_s"].to_numpy(dtype=float)
    if len(times) < 2 or float(np.max(np.diff(times))) > 1.0:
        return None
    for index in range(len(times)):
        remaining_horizon = times[-1] - times[index]
        if remaining_horizon >= post_settle_horizon_s and np.all(errors[index:] <= tolerance):
            return max(float(times[index] - start_s), 0.0)
    return None
