from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from o2_lumped.config import ExperimentManifest
from o2_lumped.voxel import (
    VoxelCandidateDomain,
    apply_voxel_cell_response,
    build_voxel_transport_system,
    monotonic_voxel_metrics,
    simulate_voxel_gas_step,
    simulate_voxel_step,
)


def manifest():
    return ExperimentManifest.model_validate(
        {
            "experiment_id": "voxel-test",
            "csv_path": "generated-in-memory",
            "assembly_stage": "window",
            "role": "simulation",
            "orientation": "horizontal",
            "regime": "dry",
        }
    )


def working_config(example_config, volume, area, scale=0.05, cell_tau=10.0):
    config = example_config.model_copy(deep=True)
    config.geometry.plenum_volume_cm3.value = volume
    config.geometry.free_membrane_area_mm2.value = area
    config.regimes["dry"].conductance_multiplier.value = scale
    config.cell.tau_s.value = cell_tau
    return config


def optimized_domain(spacing=1.0):
    return VoxelCandidateDomain(
        radius_mm=11.5,
        clear_length_mm=15.9,
        window_centres_deg=(45.0, 315.0),
        membrane_to_cavity_path_mm=0.25,
        grid_spacing_xy_mm=spacing,
        target_grid_spacing_z_mm=spacing,
    )


def test_voxel_matrix_has_uniform_air_steady_state(example_config):
    system = build_voxel_transport_system(
        working_config(example_config, 5.0, 180.0),
        manifest(),
        optimized_domain(),
        1e-5,
    )
    residual = system.matrix @ np.ones(system.active_cell_count) + system.boundary_drive
    assert np.max(np.abs(residual)) < 1e-10
    assert system.active_cell_count > 1000
    assert len(system.front_port_indices) > len(system.rear_port_indices) > 0
    assert system.geometric_gas_volume_cm3 == pytest.approx(5.05, abs=0.1)
    assert 0.95 < system.diagnostics["volume_capacity_scale"] < 1.05


def test_closed_voxel_matrix_conserves_inventory(example_config):
    config = working_config(example_config, 5.0, 180.0)
    config.gas.area_model = "fixed_conductance"
    config.gas.window_conductance_mol_per_s.value = 0.0
    system = build_voxel_transport_system(config, manifest(), optimized_domain(), 1e-5)
    assert np.max(np.abs(system.boundary_drive)) == 0.0
    column_sums = np.asarray(system.matrix.sum(axis=0)).ravel()
    assert np.max(np.abs(column_sums)) < 1e-10


def test_optimized_drainable_split_meets_hard_port_weight_range(example_config):
    config = working_config(example_config, 5.0, 180.0)
    gas, diagnostics = simulate_voxel_gas_step(
        config,
        manifest(),
        optimized_domain(),
        1e-5,
        duration_s=220.0,
        output_dt_s=1.0,
    )
    settling = []
    for weight in (0.0, 0.5, 1.0):
        frame, _ = apply_voxel_cell_response(config, gas, diagnostics, weight)
        metric = monotonic_voxel_metrics(frame)["settling_time_2pct_s"]
        assert metric is not None
        settling.append(metric)
        assert np.all(np.diff(frame.o2_probe_pct_wet.to_numpy()) >= -1e-10)
    assert max(settling) < 120.0
    assert min(settling) > 60.0
    assert settling[0] > settling[-1]


def test_membrane_access_path_slows_local_transport(example_config):
    config = working_config(example_config, 5.0, 180.0)
    settling = []
    for access_mm in (0.25, 5.8):
        domain = replace(
            optimized_domain(),
            membrane_to_cavity_path_mm=access_mm,
            grid_spacing_xy_mm=1.25,
            target_grid_spacing_z_mm=1.25,
        )
        frame, _ = simulate_voxel_step(
            config,
            manifest(),
            domain,
            1e-5,
            duration_s=300.0,
            output_dt_s=1.0,
            front_port_weight=0.0,
        )
        settling.append(monotonic_voxel_metrics(frame)["settling_time_2pct_s"])
    assert settling[0] is not None and settling[1] is not None
    assert settling[1] > 1.25 * settling[0]


def test_cell_lag_matches_exact_linear_drive_solution(example_config):
    config = example_config.model_copy(deep=True)
    config.cell.dynamic_domain = "mole_fraction"
    config.cell.tau_s.value = 5.0
    times = np.arange(0.0, 21.0, 1.0)
    slope_fraction_per_s = 0.005
    drive_pct = 100.0 * slope_fraction_per_s * times
    gas = pd.DataFrame(
        {
            "time_s": times,
            "o2_reference_pct_wet": drive_pct[-1],
            "o2_front_port_pct_wet": drive_pct,
            "o2_rear_port_pct_wet": drive_pct,
        }
    )
    frame, _ = apply_voxel_cell_response(config, gas, {}, front_port_weight=0.5)
    expected_pct = (
        100.0 * slope_fraction_per_s * (times - 5.0 + 5.0 * np.exp(-times / 5.0))
    )
    assert frame.o2_probe_pct_wet.to_numpy() == pytest.approx(expected_pct, abs=1e-10)


def test_same_side_cad_hard_case_fails_target(example_config):
    config = working_config(example_config, 9.0, 170.0)
    frame, _ = simulate_voxel_step(
        config,
        manifest(),
        VoxelCandidateDomain(
            window_centres_deg=(45.0, 135.0),
            membrane_to_cavity_path_mm=5.8,
            grid_spacing_xy_mm=1.25,
            target_grid_spacing_z_mm=1.25,
        ),
        1e-5,
        duration_s=350.0,
        output_dt_s=1.0,
        front_port_weight=0.5,
    )
    settling = monotonic_voxel_metrics(frame)["settling_time_2pct_s"]
    assert settling is None or settling > 200.0


def test_optimized_voxel_rear_port_grid_convergence(example_config):
    config = working_config(example_config, 5.0, 180.0)
    values = []
    for spacing in (1.0, 0.75):
        frame, _ = simulate_voxel_step(
            config,
            manifest(),
            optimized_domain(spacing),
            1e-5,
            duration_s=220.0,
            output_dt_s=1.0,
            front_port_weight=0.0,
        )
        values.append(monotonic_voxel_metrics(frame)["settling_time_2pct_s"])
    assert values[0] is not None and values[1] is not None
    assert values[0] == pytest.approx(values[1], rel=0.03)
