from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from o2_lumped.config import ExperimentManifest
from o2_lumped.physics import inverse_signal, simulate, static_signal


def manifest(stage="window", **updates):
    values = {
        "experiment_id": "test",
        "csv_path": "unused.csv",
        "assembly_stage": stage,
        "role": "simulation",
        "orientation": "horizontal",
    }
    values.update(updates)
    return ExperimentManifest.model_validate(values)


def frame(o2=(10.0, 10.0), pressure=(101.325, 101.325), temp=(25.0, 25.0)):
    return pd.DataFrame({
        "time_s": [0.0, 20.0],
        "o2_reference_pct_wet": o2,
        "pressure_reference_kpa": pressure,
        "temp_ambient_c": temp,
        "temp_inlet_c": temp,
        "rh_ambient_pct": [50.0, 50.0],
        "heater_power_w": [0.0, 0.0],
    })


def test_static_transform_round_trip_at_pressure(example_config):
    current = static_signal(example_config, 0.18, 90.0, 35.0)
    recovered = inverse_signal(example_config, current, 90.0, 35.0)
    assert recovered == pytest.approx(0.18, rel=1e-12)


def test_zero_window_area_prevents_exchange(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    result = simulate(
        config,
        manifest(free_membrane_area_mm2=0.0),
        frame(o2=(0.0, 20.95)),
    )
    assert np.max(np.abs(result.frame["o2_plenum_pct_wet"])) < 1e-10


def test_bulk_breathing_preserves_composition(example_config):
    config = example_config.model_copy(deep=True)
    config.gas.include_cell_consumption = False
    result = simulate(
        config,
        manifest(free_membrane_area_mm2=0.0),
        frame(o2=(10.0, 10.0), pressure=(80.0, 120.0), temp=(10.0, 60.0)),
    )
    assert result.frame["o2_plenum_pct_wet"].to_numpy() == pytest.approx([10.0, 10.0], abs=2e-5)


def test_unheated_block_follows_measured_ambient(example_config):
    inputs = frame(o2=(20.95, 20.95), temp=(20.0, 40.0))
    result = simulate(example_config, manifest(stage="bare"), inputs)
    assert result.frame["temp_block_c"].to_numpy() == pytest.approx([20.0, 40.0], abs=1e-7)


def test_cell_sink_cannot_make_inventory_negative(example_config):
    config = example_config.model_copy(deep=True)
    result = simulate(
        config,
        manifest(free_membrane_area_mm2=0.0),
        frame(o2=(20.95, 20.95)),
    )
    assert (result.frame["o2_plenum_pct_wet"] >= 0.0).all()


def test_prescribed_power_above_hardware_limit_is_rejected(example_config):
    inputs = frame()
    inputs["heater_power_w"] = [1.1, 1.1]
    with pytest.raises(ValueError, match="exceeds"):
        simulate(example_config, manifest(), inputs)


def test_wet_regime_cannot_use_unmeasured_multiplier(example_config):
    with pytest.raises(ValueError, match="must be measured or fitted"):
        simulate(example_config, manifest(regime="wet"), frame())


def test_pressure_compensated_output_is_separate_from_raw_cell_response(example_config):
    inputs = pd.DataFrame({
        "time_s": [0.0, 9.999, 10.0, 10.001, 20.0],
        "o2_reference_pct_wet": [20.95] * 5,
        "pressure_reference_kpa": [80.0, 80.0, 120.0, 120.0, 120.0],
        "temp_ambient_c": [25.0] * 5,
        "temp_inlet_c": [25.0] * 5,
        "rh_ambient_pct": [50.0] * 5,
        "heater_power_w": [0.0] * 5,
    })
    result = simulate(example_config, manifest(stage="bare"), inputs)
    before = result.frame.iloc[1]
    at_step = result.frame.iloc[2]
    assert at_step.cell_current_mA == pytest.approx(before.cell_current_mA, abs=2e-5)
    assert at_step.o2_probe_equivalent_pct_at_reference_pressure == pytest.approx(
        before.o2_probe_equivalent_pct_at_reference_pressure, abs=0.01
    )
    assert abs(at_step.o2_probe_pressure_compensated_pct_wet - before.o2_probe_pressure_compensated_pct_wet) > 5.0
    assert result.diagnostics["pressure_compensation_transient"] is True
