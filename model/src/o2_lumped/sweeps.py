from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import ExperimentManifest, ModelConfig, Parameter, Provenance, load_manifest
from .io import load_experiment_frame, resample_input_frame
from .metrics import analyze_steps
from .physics import simulate


class SweepAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter: str
    values: list[float] = Field(min_length=2)

    @model_validator(mode="after")
    def finite_values(self) -> "SweepAxis":
        if not all(np.isfinite(value) for value in self.values):
            raise ValueError("sweep-axis values must be finite")
        return self


class SweepManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_manifest: str
    axes: list[SweepAxis] = Field(min_length=1, max_length=2)
    metric: str = "settling_time_2pct_s"
    output_dt_s: float = Field(default=0.25, gt=0)


def load_sweep_manifest(path: str | Path) -> SweepManifest:
    sweep_path = Path(path)
    sweep = SweepManifest.model_validate_json(sweep_path.read_text())
    experiment = Path(sweep.experiment_manifest)
    if not experiment.is_absolute():
        sweep.experiment_manifest = str((sweep_path.parent / experiment).resolve())
    return sweep


def run_sweep(config: ModelConfig, sweep: SweepManifest) -> pd.DataFrame:
    manifest = load_manifest(sweep.experiment_manifest)
    source = load_experiment_frame(manifest)
    inputs = resample_input_frame(source, sweep.output_dt_s)
    rows = []
    combinations = np.array(np.meshgrid(*[axis.values for axis in sweep.axes], indexing="ij")).reshape(len(sweep.axes), -1).T
    for combination in combinations:
        working = config.model_copy(deep=True)
        trial = manifest.model_copy(deep=True)
        row: dict[str, float] = {}
        for axis, value in zip(sweep.axes, combination):
            _apply_sweep_value(working, trial, axis.parameter, float(value))
            row[axis.parameter] = float(value)
        working = ModelConfig.model_validate(working.model_dump())
        trial = ExperimentManifest.model_validate(trial.model_dump())
        result = simulate(working, trial, inputs)
        metrics = analyze_steps(result.frame, trial.step_windows)
        if not metrics:
            raise ValueError("sweep experiment must define at least one step window")
        metric = metrics[0].get(sweep.metric)
        row[sweep.metric] = _metric_float(metric, sweep.metric)
        row["t90_s"] = _metric_float(metrics[0]["t90_s"], "t90_s")
        row["steady_bias_o2_pct_wet"] = _metric_float(
            metrics[0]["steady_bias_o2_pct_wet"], "steady_bias_o2_pct_wet"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _apply_sweep_value(config: ModelConfig, manifest: ExperimentManifest, path: str, value: float) -> None:
    manifest_fields = {"free_membrane_area_mm2", "plenum_volume_cm3", "input_delay_s"}
    if path in manifest_fields:
        setattr(manifest, path, value)
        return
    effective_parameter_paths = {
        "thermal.resistance_k_per_w",
        "thermal.capacitance_j_per_k",
        "thermal.membrane_coupling",
        "gas.window_conductance_mol_per_s",
        "gas.area_conductance_mol_per_s_m2",
        "gas.access_resistance_s_per_mol",
        "gas.access_tau_s",
        "cell.tau_s",
        "cell.i_zero_ma",
        "cell.k_ref_ma",
        "cell.temp_coeff_per_k",
    }
    if path not in effective_parameter_paths:
        raise ValueError(f"unknown or ineffective sweep parameter {path!r}")
    if "." not in path:
        raise ValueError(f"unknown sweep parameter {path!r}")
    section_name, field_name = path.split(".", 1)
    section = getattr(config, section_name, None)
    parameter = getattr(section, field_name, None) if section is not None else None
    if not isinstance(parameter, Parameter):
        raise ValueError(f"unknown sweep parameter {path!r}")
    parameter.value = value
    parameter.provenance = Provenance.SENSITIVITY_ONLY
    parameter.source = "sweep override"


def _metric_float(value: float | str | bool | None, name: str) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
        raise TypeError(f"metric {name!r} is not numeric")
    return float(value)
