from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from o2_lumped.config import ExperimentManifest, Provenance
from o2_lumped.fitting import _finish_fit, _fit_window, _residual_groups, fit_stage
from o2_lumped.physics import simulate, static_signal


def test_window_fit_rejects_uncalibrated_prerequisites(example_config, tmp_path):
    manifest = ExperimentManifest.model_validate({
        "experiment_id": "window",
        "csv_path": str(tmp_path / "missing.csv"),
        "assembly_stage": "window",
        "role": "calibration",
        "orientation": "horizontal",
    })
    with pytest.raises(ValueError, match="prerequisites"):
        fit_stage(example_config, [manifest], "window", bootstrap_replicates=0)


def test_well_mixed_window_fit_marks_complete_assembly_scope(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    config.solver.max_step_s = 2.0
    time = np.arange(0.0, 31.0, 2.0)
    frame = pd.DataFrame({
        "time_s": time,
        "o2_reference_pct_wet": np.where(time < 4.0, 0.0, 20.95),
        "pressure_reference_kpa": 101.325,
        "temp_ambient_c": 25.0,
        "temp_inlet_c": 25.0,
        "heater_power_w": 0.0,
    })
    manifest = ExperimentManifest.model_validate({
        "experiment_id": "synthetic-window",
        "csv_path": "generated-in-memory",
        "assembly_stage": "window",
        "role": "calibration",
        "orientation": "bench",
    })
    frame["o2_probe_pct"] = simulate(config, manifest, frame).frame["o2_probe_pct_wet"]
    result = _fit_window(config, [(manifest, frame)], bootstrap=0, seed=1)
    assert result.config.gas.conductance_scope == "complete_assembly_lumped"


def test_static_stage_recovers_synthetic_parameters(example_config, tmp_path):
    truth = example_config.model_copy(deep=True)
    truth.cell.i_zero_ma.value = 0.012
    truth.cell.k_ref_ma.value = 0.51
    levels = np.array([0.0, 5.0, 10.0, 15.0, 20.95, 30.0])
    time = np.arange(120, dtype=float)
    oxygen = np.repeat(levels, 20)
    frame = pd.DataFrame({
        "time_s": time,
        "o2_reference_pct_wet": oxygen,
        "pressure_reference_kpa": np.full(len(oxygen), 101.325),
        "temp_ambient_c": np.full(len(oxygen), 25.0),
        "cell_current_mA": [static_signal(truth, value / 100.0, 101.325, 25.0) for value in oxygen],
    })
    path = tmp_path / "static.csv"
    frame.to_csv(path, index=False)
    manifest = ExperimentManifest.model_validate({
        "experiment_id": "static",
        "csv_path": str(path),
        "assembly_stage": "static",
        "role": "calibration",
        "orientation": "bench",
        "step_windows": [
            {
                "label": f"plateau-{index}",
                "baseline_start_s": float(index * 20),
                "baseline_end_s": float(index * 20 + 2),
                "start_s": float(index * 20 + 3),
                "steady_start_s": float(index * 20 + 5),
                "steady_end_s": float(index * 20 + 19),
            }
            for index in range(len(levels))
        ],
    })
    result = fit_stage(example_config, [manifest], "static", bootstrap_replicates=0)
    assert result.report["identifiable"] is True
    assert result.config.cell.i_zero_ma.value == pytest.approx(0.012, abs=2e-7)
    assert result.config.cell.k_ref_ma.value == pytest.approx(0.51, abs=2e-6)
    assert result.config.cell.i_zero_ma.provenance == Provenance.FITTED


def test_residual_groups_do_not_cross_experiment_boundaries():
    residual = np.arange(7.0)
    groups = _residual_groups(residual, [3, 4])
    assert [group.tolist() for group in groups] == [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0, 6.0]]
    with pytest.raises(ValueError, match="cover"):
        _residual_groups(residual, [2, 2])


def test_nearly_flat_one_parameter_fit_is_not_identifiable(example_config):
    result = _finish_fit(
        example_config,
        ["delay:flat"],
        np.array([1.0]),
        np.array([0.0]),
        np.array([4.0]),
        lambda theta: np.array([1e-12 * (theta[0] - 2.0)]),
        0,
        1,
        {},
        residual_group_lengths=[1],
    )
    assert result.report["identifiable"] is False
    assert result.report["minimum_scaled_information"] < 1.0


def test_window_override_requires_measurement_provenance(example_config, tmp_path):
    config = example_config.model_copy(deep=True)
    for parameter in (
        config.cell.i_zero_ma,
        config.cell.k_ref_ma,
        config.cell.tau_s,
        config.geometry.plenum_volume_cm3,
        config.geometry.free_membrane_area_mm2,
    ):
        parameter.provenance = Provenance.MEASURED
    manifest = ExperimentManifest.model_validate({
        "experiment_id": "window-override",
        "csv_path": str(tmp_path / "not-read.csv"),
        "assembly_stage": "window",
        "role": "calibration",
        "orientation": "bench",
        "free_membrane_area_mm2": 100.0,
    })
    with pytest.raises(ValueError, match="requires measured provenance"):
        fit_stage(config, [manifest], "window", bootstrap_replicates=0)


def test_dynamic_baseline_must_match_static_calibration(example_config, tmp_path):
    config = example_config.model_copy(deep=True)
    config.cell.i_zero_ma.provenance = Provenance.MEASURED
    config.cell.k_ref_ma.provenance = Provenance.MEASURED
    time = np.arange(31.0)
    frame = pd.DataFrame({
        "time_s": time,
        "o2_reference_pct_wet": np.full(len(time), 20.0),
        "pressure_reference_kpa": np.full(len(time), 101.325),
        "temp_ambient_c": np.full(len(time), 25.0),
        "cell_current_mA": np.zeros(len(time)),
    })
    path = tmp_path / "bad-baseline.csv"
    frame.to_csv(path, index=False)
    manifest = ExperimentManifest.model_validate({
        "experiment_id": "bad-baseline",
        "csv_path": str(path),
        "assembly_stage": "bare",
        "role": "calibration",
        "orientation": "bench",
        "step_windows": [{
            "label": "step",
            "baseline_start_s": 0.0,
            "baseline_end_s": 10.0,
            "start_s": 15.0,
            "steady_start_s": 20.0,
            "steady_end_s": 30.0,
        }],
    })
    with pytest.raises(ValueError, match="disagrees with the static calibration"):
        fit_stage(config, [manifest], "bare", bootstrap_replicates=0)


def test_static_plateau_rejects_changing_pressure(example_config, tmp_path):
    time = np.arange(21.0)
    frame = pd.DataFrame({
        "time_s": time,
        "o2_reference_pct_wet": np.full(len(time), 20.0),
        "pressure_reference_kpa": np.where((time % 2) == 0, 80.0, 120.0),
        "temp_ambient_c": np.full(len(time), 25.0),
        "cell_current_mA": np.full(len(time), 0.1),
    })
    path = tmp_path / "pressure-plateau.csv"
    frame.to_csv(path, index=False)
    manifest = ExperimentManifest.model_validate({
        "experiment_id": "pressure-plateau",
        "csv_path": str(path),
        "assembly_stage": "static",
        "role": "calibration",
        "orientation": "bench",
        "step_windows": [{
            "label": "plateau",
            "baseline_start_s": 0.0,
            "baseline_end_s": 2.0,
            "start_s": 3.0,
            "steady_start_s": 5.0,
            "steady_end_s": 20.0,
        }],
    })
    with pytest.raises(ValueError, match="changing pressure"):
        fit_stage(example_config, [manifest], "static", bootstrap_replicates=0)


def test_profile_width_is_scaled_to_estimate_not_arbitrary_bounds(example_config):
    result = _finish_fit(
        example_config,
        ["delay:wide"],
        np.array([2.0]),
        np.array([0.0]),
        np.array([300.0]),
        lambda theta: np.array([theta[0] - 2.0]),
        0,
        1,
        {},
        residual_group_lengths=[1],
    )
    assert result.report["minimum_scaled_information"] >= 1.0
    assert result.report["profile_too_wide"] == ["delay:wide"]
    assert result.report["identifiable"] is False
