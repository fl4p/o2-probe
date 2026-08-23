from __future__ import annotations

import pandas as pd
import pytest

from o2_lumped.config import ExperimentManifest, ModelConfig
from o2_lumped.io import resample_input_frame
from o2_lumped.sweeps import _apply_sweep_value


def test_resampling_holds_heater_command():
    source = pd.DataFrame({
        "time_s": [0.0, 10.0, 20.0],
        "o2_reference_pct_wet": [0.0, 20.0, 20.0],
        "pressure_reference_kpa": [101.325] * 3,
        "temp_ambient_c": [25.0] * 3,
        "heater_power_w": [0.0, 1.0, 0.0],
    })
    result = resample_input_frame(source, 5.0)
    assert result["heater_power_w"].tolist() == [0.0, 0.0, 1.0, 1.0, 0.0]


def test_model_rejects_wrong_parameter_unit(example_config):
    raw = example_config.model_dump()
    raw["geometry"]["plenum_volume_cm3"]["unit"] = "m3"
    with pytest.raises(ValueError, match="unit"):
        ModelConfig.model_validate(raw)


def test_model_rejects_nonfinite_uncertainty(example_config):
    raw = example_config.model_dump()
    raw["geometry"]["plenum_volume_cm3"]["uncertainty"] = float("nan")
    with pytest.raises(ValueError, match="uncertainty"):
        ModelConfig.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    ["free_membrane_area_mm2", "plenum_volume_cm3", "rear_aperture_diameter_mm"],
)
def test_manifest_rejects_nonfinite_geometry_overrides(field):
    raw = {
        "experiment_id": "nonfinite-geometry",
        "csv_path": "unused.csv",
        "assembly_stage": "window",
        "role": "simulation",
        "orientation": "horizontal",
        field: float("inf"),
    }
    with pytest.raises(ValueError, match="finite"):
        ExperimentManifest.model_validate(raw)


def test_sweep_rejects_ineffective_rear_aperture(example_config):
    trial = ExperimentManifest.model_validate({
        "experiment_id": "sweep",
        "csv_path": "unused.csv",
        "assembly_stage": "window",
        "role": "simulation",
        "orientation": "horizontal",
    })
    with pytest.raises(ValueError, match="ineffective"):
        _apply_sweep_value(example_config, trial, "rear_aperture_diameter_mm", 4.0)
