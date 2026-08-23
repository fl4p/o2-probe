from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from o2_lumped.config import ExperimentManifest
from o2_lumped.spatial import AxialDomain, simulate_axial_diffusion


def manifest(**updates):
    values = {
        "experiment_id": "axial-test",
        "csv_path": "generated-in-memory",
        "assembly_stage": "window",
        "role": "simulation",
        "orientation": "horizontal",
        "regime": "dry",
    }
    values.update(updates)
    return ExperimentManifest.model_validate(values)


def step_frame(duration_s=500.0, dt_s=0.25, final_o2_pct=20.95):
    # The tiny second sample approximates an ideal boundary step while retaining
    # the initial internal concentration in the first sample.
    times = np.concatenate(
        ([0.0, 1e-6], np.arange(dt_s, duration_s + 0.5 * dt_s, dt_s))
    )
    reference = np.full(len(times), final_o2_pct)
    reference[0] = 0.0
    return pd.DataFrame(
        {
            "time_s": times,
            "o2_reference_pct_wet": reference,
            "pressure_reference_kpa": 101.325,
            "temp_ambient_c": 25.0,
            "temp_inlet_c": 25.0,
            "rh_ambient_pct": 50.0,
            "heater_power_w": 0.0,
        }
    )


def crossing_time(frame, column, fraction):
    values = frame[column].to_numpy(dtype=float)
    times = frame.time_s.to_numpy(dtype=float)
    target = values[-1] * fraction
    indices = np.flatnonzero(values >= target)
    index = int(indices[0])
    if index == 0:
        return float(times[0])
    return float(
        np.interp(target, values[index - 1 : index + 1], times[index - 1 : index + 1])
    )


def test_axial_domain_rejects_sensor_beyond_closed_end():
    with pytest.raises(ValueError, match="cannot exceed"):
        AxialDomain(35.0, 36.0, 2e-5).validate()


def test_axial_domain_rejects_invalid_runtime_provenance():
    with pytest.raises(ValueError, match="provenance"):
        AxialDomain(
            50.0,
            38.5,
            2e-5,
            diffusivity_provenance="unknown",  # type: ignore[arg-type]
        ).validate()


@pytest.mark.parametrize("nodes", [5.5, float("nan"), True])
def test_axial_domain_rejects_noninteger_nodes(nodes):
    with pytest.raises(ValueError, match="five finite volumes"):
        AxialDomain(50.0, 38.5, 2e-5, nodes=nodes).validate()  # type: ignore[arg-type]


def test_complete_assembly_conductance_is_rejected(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.conductance_scope = "complete_assembly_lumped"
    with pytest.raises(ValueError, match="may already contain axial resistance"):
        simulate_axial_diffusion(
            config, manifest(), step_frame(20.0), AxialDomain(50.0, 38.5, 2e-5)
        )


def test_nonzero_initial_o2_requires_steady_initialization_with_consumption(
    example_config,
):
    inputs = step_frame(20.0)
    inputs["o2_reference_pct_wet"] = 20.95
    with pytest.raises(ValueError, match="spatial steady-state"):
        simulate_axial_diffusion(
            example_config, manifest(), inputs, AxialDomain(50.0, 38.5, 2e-5)
        )


def test_unmeasured_wet_regime_is_rejected(example_config):
    with pytest.raises(ValueError, match="must be measured or fitted"):
        simulate_axial_diffusion(
            example_config,
            manifest(regime="wet"),
            step_frame(20.0),
            AxialDomain(50.0, 38.5, 2e-5),
        )


def test_uniform_composition_remains_uniform_without_consumption(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    inputs = step_frame(duration_s=20.0)
    inputs["o2_reference_pct_wet"] = 12.0
    result = simulate_axial_diffusion(
        config,
        manifest(),
        inputs,
        AxialDomain(50.0, 38.5, 2e-5, nodes=21),
    )
    for column in (
        "o2_membrane_side_node_pct_wet",
        "o2_sensor_location_pct_wet",
        "o2_rear_wall_node_pct_wet",
        "o2_plenum_pct_wet",
    ):
        assert result.frame[column].to_numpy() == pytest.approx(12.0, abs=1e-10)


def test_sensor_depth_changes_response_time(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    inputs = step_frame()
    near = simulate_axial_diffusion(
        config, manifest(), inputs, AxialDomain(50.0, 10.0, 2e-5, nodes=51)
    )
    deep = simulate_axial_diffusion(
        config, manifest(), inputs, AxialDomain(50.0, 38.5, 2e-5, nodes=51)
    )
    near_t90 = crossing_time(near.frame, "o2_sensor_location_pct_wet", 0.90)
    deep_t90 = crossing_time(deep.frame, "o2_sensor_location_pct_wet", 0.90)
    assert deep_t90 > 1.5 * near_t90


def test_input_delay_shifts_boundary_response(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    inputs = step_frame()
    no_delay = simulate_axial_diffusion(
        config, manifest(), inputs, AxialDomain(50.0, 38.5, 2e-5, nodes=41)
    )
    delayed = simulate_axial_diffusion(
        config,
        manifest(input_delay_s=5.0, input_delay_bounds_s=(-5.0, 5.0)),
        inputs,
        AxialDomain(50.0, 38.5, 2e-5, nodes=41),
    )
    base_t90 = crossing_time(no_delay.frame, "o2_sensor_location_pct_wet", 0.90)
    delayed_t90 = crossing_time(delayed.frame, "o2_sensor_location_pct_wet", 0.90)
    assert delayed_t90 - base_t90 == pytest.approx(5.0, abs=0.3)
    assert delayed.diagnostics["input_delay_s"] == 5.0


def test_grid_convergence_for_rev_a_depth(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    inputs = step_frame()
    coarse = simulate_axial_diffusion(
        config, manifest(), inputs, AxialDomain(50.0, 38.5, 2e-5, nodes=41)
    )
    fine = simulate_axial_diffusion(
        config, manifest(), inputs, AxialDomain(50.0, 38.5, 2e-5, nodes=81)
    )
    coarse_t90 = crossing_time(coarse.frame, "o2_sensor_location_pct_wet", 0.90)
    fine_t90 = crossing_time(fine.frame, "o2_sensor_location_pct_wet", 0.90)
    assert coarse_t90 == pytest.approx(fine_t90, rel=0.02)


def test_dirichlet_closed_slab_matches_diffusion_series(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    config.gas.area_model = "fixed_conductance"
    config.gas.window_conductance_mol_per_s.value = 1e3
    config.cell.tau_s.value = 1e-4
    config.solver.max_step_s = 0.02
    length_m = 0.010
    diffusivity = 1e-5
    nodes = 41
    sensor_index = nodes - 1
    sensor_x_m = (sensor_index + 0.5) * length_m / nodes
    inputs = step_frame(duration_s=40.0, dt_s=0.1, final_o2_pct=100.0)
    result = simulate_axial_diffusion(
        config,
        manifest(),
        inputs,
        AxialDomain(
            length_m * 1000.0,
            sensor_x_m * 1000.0,
            diffusivity,
            nodes=nodes,
        ),
    )

    times = result.frame.time_s.to_numpy(dtype=float)
    remaining = np.zeros_like(times)
    for order in range(400):
        eigenvalue = (order + 0.5) * np.pi / length_m
        remaining += (
            2.0
            / (length_m * eigenvalue)
            * np.sin(eigenvalue * sensor_x_m)
            * np.exp(-diffusivity * eigenvalue**2 * np.maximum(times - 1e-6, 0.0))
        )
    analytic = 1.0 - remaining
    numerical = result.frame.o2_sensor_location_pct_wet.to_numpy(dtype=float) / 100.0
    comparison = times >= 0.5
    assert numerical[comparison] == pytest.approx(analytic[comparison], abs=0.011)
