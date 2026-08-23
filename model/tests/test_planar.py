from __future__ import annotations

import numpy as np
import pytest

from o2_lumped.config import ExperimentManifest
from o2_lumped.planar import (
    PlanarCandidateDomain,
    build_planar_transport_system,
    monotonic_response_metrics,
    simulate_planar_step,
)


def manifest():
    return ExperimentManifest.model_validate({
        "experiment_id": "planar-test",
        "csv_path": "generated-in-memory",
        "assembly_stage": "window",
        "role": "simulation",
        "orientation": "horizontal",
        "regime": "dry",
    })


def candidate_config(example_config, scale=1.0, cell_tau_s=4.343):
    config = example_config.model_copy(deep=True)
    config.geometry.plenum_volume_cm3.value = 8.0
    config.geometry.free_membrane_area_mm2.value = 180.0
    config.regimes["dry"].conductance_multiplier.value = scale
    config.cell.tau_s.value = cell_tau_s
    return config


def test_planar_matrix_has_uniform_air_steady_state(example_config):
    system = build_planar_transport_system(
        candidate_config(example_config),
        manifest(),
        PlanarCandidateDomain(),
        2e-5,
    )
    residual = system.matrix @ np.ones(system.active_cell_count) + system.boundary_drive
    assert np.max(np.abs(residual)) < 1e-10
    assert system.membrane_face_count > 0
    assert system.active_cell_count > 100


def test_same_side_windows_leave_rear_port_slower(example_config):
    frame, _ = simulate_planar_step(
        candidate_config(example_config),
        manifest(),
        PlanarCandidateDomain(window_centres_deg=(45.0, 135.0)),
        2e-5,
        duration_s=250.0,
        output_dt_s=0.5,
    )
    front = monotonic_response_metrics(frame, "o2_front_port_pct_wet")
    rear = monotonic_response_metrics(frame, "o2_rear_port_pct_wet")
    assert front["t90_s"] is not None
    assert rear["t90_s"] is not None
    assert rear["t90_s"] > 5.0 * front["t90_s"]


def test_split_windows_help_but_access_path_prevents_planar_pass(example_config):
    config = candidate_config(example_config, scale=0.05, cell_tau_s=10.0)
    same, _ = simulate_planar_step(
        config,
        manifest(),
        PlanarCandidateDomain(window_centres_deg=(45.0, 135.0)),
        2e-5,
        duration_s=300.0,
        output_dt_s=0.5,
    )
    split, _ = simulate_planar_step(
        config,
        manifest(),
        PlanarCandidateDomain(window_centres_deg=(45.0, 225.0)),
        2e-5,
        duration_s=300.0,
        output_dt_s=0.5,
    )
    same_settling = monotonic_response_metrics(same)["settling_time_2pct_s"]
    split_settling = monotonic_response_metrics(split)["settling_time_2pct_s"]
    assert same_settling is not None and same_settling > 120.0
    assert split_settling is not None and split_settling > 120.0
    assert split_settling < 0.8 * same_settling


def test_split_geometry_grid_convergence(example_config):
    config = candidate_config(example_config, scale=0.05, cell_tau_s=10.0)
    coarse, _ = simulate_planar_step(
        config,
        manifest(),
        PlanarCandidateDomain(
            window_centres_deg=(45.0, 225.0), grid_spacing_mm=1.0
        ),
        2e-5,
        duration_s=250.0,
        output_dt_s=0.5,
    )
    fine, _ = simulate_planar_step(
        config,
        manifest(),
        PlanarCandidateDomain(
            window_centres_deg=(45.0, 225.0), grid_spacing_mm=0.75
        ),
        2e-5,
        duration_s=250.0,
        output_dt_s=0.5,
    )
    coarse_settling = monotonic_response_metrics(coarse)["settling_time_2pct_s"]
    fine_settling = monotonic_response_metrics(fine)["settling_time_2pct_s"]
    assert coarse_settling is not None and fine_settling is not None
    assert coarse_settling == pytest.approx(fine_settling, rel=0.08)


def test_planar_domain_rejects_unresolved_windows():
    with pytest.raises(ValueError, match="window width"):
        PlanarCandidateDomain(window_width_mm=24.0).validate()
