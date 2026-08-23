from __future__ import annotations

import numpy as np
import pandas as pd

from o2_lumped.config import StepWindow
from o2_lumped.metrics import analyze_steps


WINDOW = StepWindow(
    label="step",
    start_s=20.0,
    baseline_start_s=0.0,
    baseline_end_s=10.0,
    steady_start_s=80.0,
    steady_end_s=120.0,
)


def response_frame(tau_s: float, final_time_s: float = 120.0):
    time = np.arange(0.0, final_time_s + 0.5, 0.5)
    reference = np.where(time < 20.0, 0.0, 20.0)
    response = np.where(time < 20.0, 0.0, 20.0 * (1.0 - np.exp(-(time - 20.0) / tau_s)))
    return pd.DataFrame({
        "time_s": time,
        "o2_reference_pct_wet": reference,
        "o2_probe_pct_wet": response,
        "heater_applied_w": np.zeros_like(time),
    })


def test_settling_uses_reference_target_and_reports_complete_response():
    result = analyze_steps(response_frame(8.0), [WINDOW])[0]
    assert result["steady_state_reached"] is True
    assert 17.5 < result["t90_s"] < 19.5
    assert 30.0 < result["settling_time_2pct_s"] < 32.5


def test_unfinished_slow_response_does_not_claim_settling():
    result = analyze_steps(response_frame(100.0), [WINDOW])[0]
    assert result["steady_state_reached"] is False
    assert result["settling_time_2pct_s"] is None


def test_sparse_trace_does_not_claim_continuous_settling():
    sparse = response_frame(8.0).iloc[::10].reset_index(drop=True)
    result = analyze_steps(sparse, [WINDOW])[0]
    assert result["settling_time_2pct_s"] is None


def test_pressure_change_invalidates_response_time_metrics():
    frame = response_frame(8.0)
    frame["pressure_reference_kpa"] = np.where(frame.time_s < 20.0, 90.0, 110.0)
    result = analyze_steps(frame, [WINDOW])[0]
    assert result["response_metrics_valid"] is False
    assert result["t90_s"] is None
    assert result["settling_time_2pct_s"] is None
