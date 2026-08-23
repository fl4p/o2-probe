from __future__ import annotations

from pathlib import Path

import pytest

from o2_lumped.config import Provenance
from o2_lumped.prototype import (
    _axial_diffusion_sensitivity,
    candidate_config,
    cascade_metrics,
    gas_time_constant_s,
    load_prototype_study,
    _validate_study,
)


ROOT = Path(__file__).resolve().parents[1]


def test_single_lag_response_matches_analytic_crossings():
    metrics = cascade_metrics(0.0, 0.0, 10.0, 0.05)
    assert metrics["t90_s"] == pytest.approx(10.0 * 2.302585, abs=0.06)
    assert metrics["settling_time_2pct_s"] == pytest.approx(10.0 * 3.912023, abs=0.06)


def test_response_candidate_meets_well_mixed_hard_screening_case(example_config):
    study = load_prototype_study(ROOT / "examples" / "prototype_study.json")
    existing = study.designs[0]
    candidate = study.designs[-1]
    hard_scale = min(study.installed_conductance_scales)
    hard_cell = max(study.cell_tau_s)
    hard_access = max(study.empirical_access_tau_s)

    existing_tau = gas_time_constant_s(
        example_config,
        existing.volume_cm3[2],
        existing.free_area_mm2[0],
        hard_scale,
        study.pressure_kpa,
        study.gas_temp_c,
    )
    candidate_tau = gas_time_constant_s(
        example_config,
        candidate.volume_cm3[2],
        candidate.free_area_mm2[0],
        hard_scale,
        study.pressure_kpa,
        study.gas_temp_c,
    )
    existing_settle = cascade_metrics(existing_tau, hard_access, hard_cell)["settling_time_2pct_s"]
    candidate_settle = cascade_metrics(candidate_tau, hard_access, hard_cell)["settling_time_2pct_s"]
    assert existing_settle > study.settling_limit_s
    assert candidate_settle <= study.settling_limit_s


def test_rev_a_axial_result_exceeds_well_mixed_screening(example_config):
    study = load_prototype_study(ROOT / "examples" / "prototype_study.json")
    assert study.designs[0].axial_length_mm == 44.0
    assert study.designs[0].cell_to_membrane_distance_mm == (29.0, 36.0)
    assert study.designs[0].volume_cm3 == (20.3, 23.3, 26.3)
    study.designs = [study.designs[0]]
    study.axial_diffusivity_m2_s = [2e-5, 3e-5]
    study.response_dt_s = 1.0
    study.axial_nodes = 21
    axial = _axial_diffusion_sensitivity(example_config, study)
    central = axial[
        (axial.case == "central")
        & (axial.effective_axial_diffusivity_m2_s == 2e-5)
    ].iloc[0]
    well_mixed_tau = gas_time_constant_s(
        example_config,
        study.designs[0].volume_cm3[1],
        study.designs[0].free_area_mm2[1],
        1.0,
        study.pressure_kpa,
        study.gas_temp_c,
    )
    well_mixed = cascade_metrics(well_mixed_tau, 0.0, min(study.cell_tau_s), 1.0)
    assert central.t90_s == pytest.approx(104.0, abs=3.0)
    assert central.settling_time_2pct_s > 160.0
    assert central.settling_time_2pct_s > 5.0 * well_mixed["settling_time_2pct_s"]
    assert central.steady_state_reached
    assert central.response_metrics_valid


def test_candidate_config_remains_explicitly_uncalibrated(example_config):
    study = load_prototype_study(ROOT / "examples" / "prototype_study.json")
    config = candidate_config(example_config, study.designs[-1])
    assert config.calibrated is False
    assert config.geometry.plenum_volume_cm3.value == 4.9
    assert config.geometry.plenum_volume_cm3.provenance == Provenance.SENSITIVITY_ONLY
    assert config.is_uncalibrated is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("thermal_coupling_values", [0.0, 0.5], "positive"),
        ("thermal_resistance_range_k_per_w", (0.0, 40.0), "positive"),
        ("thermal_resistance_range_k_per_w", (40.0, 10.0), "ordered"),
    ],
)
def test_prototype_study_rejects_zero_or_unordered_thermal_inputs(field, value, message):
    study = load_prototype_study(ROOT / "examples" / "prototype_study.json")
    setattr(study, field, value)
    with pytest.raises(ValueError, match=message):
        _validate_study(study)
