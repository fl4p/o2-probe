from __future__ import annotations

import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"


class Provenance(StrEnum):
    MEASURED = "measured"
    FITTED = "fitted"
    ASSUMED = "assumed"
    SENSITIVITY_ONLY = "sensitivity_only"


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None
    unit: str
    uncertainty: float | None = None
    provenance: Provenance
    source: str

    def require(self, name: str) -> float:
        if self.value is None:
            raise ValueError(f"{name} is required for this operation")
        return float(self.value)


class GeometryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plenum_volume_cm3: Parameter
    free_membrane_area_mm2: Parameter
    membrane_thickness_mm: Parameter
    rear_aperture_diameter_mm: Parameter


class ThermalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resistance_k_per_w: Parameter
    capacitance_j_per_k: Parameter
    membrane_coupling: Parameter
    settled_rate_k_per_s: float = Field(default=0.002, gt=0)
    settled_dwell_s: float = Field(default=30.0, ge=0)


class GasConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_conductance_mol_per_s: Parameter
    area_conductance_mol_per_s_m2: Parameter
    access_resistance_s_per_mol: Parameter
    area_model: Literal["fixed_conductance", "area_only", "area_plus_access"] = "fixed_conductance"
    access_tau_s: Parameter
    # Legacy configurations used the complete-assembly well-mixed fit. Default
    # conservatively to that scope so spatial use requires an explicit opt-in.
    conductance_scope: Literal[
        "intrinsic_window", "complete_assembly_lumped"
    ] = "complete_assembly_lumped"
    access_enabled: bool = False
    include_cell_consumption: bool = True
    electrons_per_o2: int = Field(default=4, gt=0)
    consumption_availability_tau_s: float = Field(default=1.0, gt=0)


class CellConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tau_s: Parameter
    i_zero_ma: Parameter
    k_ref_ma: Parameter
    temp_coeff_per_k: Parameter
    reference_temp_c: float = 20.0
    reference_pressure_kpa: float = Field(default=101.325, gt=0)
    dynamic_domain: Literal["mole_fraction", "normalized_output"] = "mole_fraction"


class ControllerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_delta_t_k: float = 2.0
    kp_w_per_k: float | None = Field(default=None, ge=0)
    ki_w_per_k_s: float | None = Field(default=None, ge=0)
    sample_period_s: float = Field(default=1.0, gt=0)
    max_power_w: float = Field(default=1.0, ge=0)
    max_block_temp_c: float = 60.0

    @model_validator(mode="after")
    def validate_controller(self) -> "ControllerConfig":
        values = [self.target_delta_t_k, self.sample_period_s, self.max_power_w, self.max_block_temp_c]
        values += [value for value in (self.kp_w_per_k, self.ki_w_per_k_s) if value is not None]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("controller values must be finite")
        return self

class RegimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conductance_multiplier: Parameter
    protocol: str


class SolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rtol: float = Field(default=1e-7, gt=0)
    atol: float = Field(default=1e-9, gt=0)
    max_step_s: float = Field(default=0.25, gt=0)


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    model_version: str = MODEL_VERSION
    geometry_revision: str
    calibrated: bool = False
    geometry: GeometryConfig
    thermal: ThermalConfig
    gas: GasConfig
    cell: CellConfig
    controller: ControllerConfig = ControllerConfig()
    regimes: dict[str, RegimeConfig]
    active_regime: str = "dry"
    solver: SolverConfig = SolverConfig()

    @model_validator(mode="after")
    def validate_model(self) -> "ModelConfig":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version!r}")
        if self.model_version != MODEL_VERSION:
            raise ValueError(f"unsupported model_version {self.model_version!r}")
        if self.active_regime not in self.regimes:
            raise ValueError(f"active_regime {self.active_regime!r} is not configured")
        for name, parameter in self.iter_parameters():
            if parameter.value is not None and not math.isfinite(parameter.value):
                raise ValueError(f"{name}.value must be finite")
            if parameter.uncertainty is not None and (
                not math.isfinite(parameter.uncertainty) or parameter.uncertainty < 0
            ):
                raise ValueError(f"{name}.uncertainty must be finite and nonnegative")
        self._validate_parameter_contract()
        return self

    def _validate_parameter_contract(self) -> None:
        contracts: dict[str, tuple[str, str]] = {
            "geometry.plenum_volume_cm3": ("cm3", "positive"),
            "geometry.free_membrane_area_mm2": ("mm2", "nonnegative"),
            "geometry.membrane_thickness_mm": ("mm", "positive"),
            "geometry.rear_aperture_diameter_mm": ("mm", "nonnegative"),
            "thermal.resistance_k_per_w": ("K/W", "positive"),
            "thermal.capacitance_j_per_k": ("J/K", "positive"),
            "thermal.membrane_coupling": ("1", "fraction"),
            "gas.window_conductance_mol_per_s": ("mol/s", "nonnegative"),
            "gas.area_conductance_mol_per_s_m2": ("mol/(s m2)", "nonnegative"),
            "gas.access_resistance_s_per_mol": ("s/mol", "nonnegative"),
            "gas.access_tau_s": ("s", "positive"),
            "cell.tau_s": ("s", "positive"),
            "cell.i_zero_ma": ("mA", "any"),
            "cell.k_ref_ma": ("mA", "positive"),
            "cell.temp_coeff_per_k": ("1/K", "any"),
        }
        for name, parameter in self.iter_parameters():
            if name.startswith("regimes."):
                expected_unit, rule = "1", "nonnegative"
            else:
                expected_unit, rule = contracts[name]
            if parameter.unit != expected_unit:
                raise ValueError(f"{name}.unit must be {expected_unit!r}, got {parameter.unit!r}")
            if parameter.value is None:
                continue
            if rule == "positive" and parameter.value <= 0:
                raise ValueError(f"{name}.value must be positive")
            if rule == "nonnegative" and parameter.value < 0:
                raise ValueError(f"{name}.value must be nonnegative")
            if rule == "fraction" and not 0 <= parameter.value <= 1:
                raise ValueError(f"{name}.value must be within [0, 1]")

    def iter_parameters(self) -> list[tuple[str, Parameter]]:
        result: list[tuple[str, Parameter]] = []
        for section_name in ("geometry", "thermal", "gas", "cell"):
            section = getattr(self, section_name)
            for field_name in type(section).model_fields:
                value = getattr(section, field_name)
                if isinstance(value, Parameter):
                    result.append((f"{section_name}.{field_name}", value))
        for regime_name, regime in self.regimes.items():
            result.append((f"regimes.{regime_name}.conductance_multiplier", regime.conductance_multiplier))
        return result

    @property
    def is_uncalibrated(self) -> bool:
        return (not self.calibrated) or any(
            p.provenance in {Provenance.ASSUMED, Provenance.SENSITIVITY_ONLY}
            for _, p in self.iter_parameters()
            if p.value is not None
        )

    def resolved_metadata(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_version": self.model_version,
            "geometry_revision": self.geometry_revision,
            "calibrated": self.calibrated,
            "uncalibrated": self.is_uncalibrated,
            "parameter_provenance": {
                name: parameter.model_dump(mode="json") for name, parameter in self.iter_parameters()
            },
            "solver": self.solver.model_dump(mode="json"),
        }


class StepWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    start_s: float
    baseline_start_s: float
    baseline_end_s: float
    steady_start_s: float
    steady_end_s: float

    @model_validator(mode="after")
    def validate_order(self) -> "StepWindow":
        if not (
            self.baseline_start_s < self.baseline_end_s <= self.start_s
            < self.steady_start_s < self.steady_end_s
        ):
            raise ValueError(f"invalid step-window ordering for {self.label!r}")
        return self


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    experiment_id: str
    csv_path: str
    assembly_stage: Literal["static", "thermal", "bare", "carrier", "window", "validation"]
    role: Literal["calibration", "validation", "simulation"]
    orientation: str
    regime: str | None = None
    heater_mode: Literal["prescribed_power", "delta_t_pi"] = "prescribed_power"
    step_windows: list[StepWindow] = Field(default_factory=list)
    free_membrane_area_mm2: float | None = None
    free_membrane_area_uncertainty_mm2: float | None = None
    free_membrane_area_provenance: Literal["measured"] | None = None
    free_membrane_area_source: str | None = None
    plenum_volume_cm3: float | None = None
    plenum_volume_uncertainty_cm3: float | None = None
    plenum_volume_provenance: Literal["measured"] | None = None
    plenum_volume_source: str | None = None
    rear_aperture_diameter_mm: float | None = None
    replicate_group: str | None = None
    input_delay_s: float = 0.0
    input_delay_bounds_s: tuple[float, float] = (-5.0, 5.0)
    current_sigma_mA: float = Field(default=0.001, gt=0)
    o2_sigma_pct: float = Field(default=0.1, gt=0)
    temperature_sigma_k: float = Field(default=0.1, gt=0)
    membrane_temperature_sigma_k: float = Field(default=0.2, gt=0)

    @model_validator(mode="after")
    def validate_manifest(self) -> "ExperimentManifest":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version!r}")
        if self.free_membrane_area_mm2 is not None and (
            not math.isfinite(self.free_membrane_area_mm2) or self.free_membrane_area_mm2 < 0
        ):
            raise ValueError("free_membrane_area_mm2 must be finite and nonnegative")
        if self.plenum_volume_cm3 is not None and (
            not math.isfinite(self.plenum_volume_cm3) or self.plenum_volume_cm3 <= 0
        ):
            raise ValueError("plenum_volume_cm3 must be finite and positive")
        if self.rear_aperture_diameter_mm is not None and (
            not math.isfinite(self.rear_aperture_diameter_mm)
            or self.rear_aperture_diameter_mm < 0
        ):
            raise ValueError("rear_aperture_diameter_mm must be finite and nonnegative")
        for name, uncertainty in (
            ("free_membrane_area_uncertainty_mm2", self.free_membrane_area_uncertainty_mm2),
            ("plenum_volume_uncertainty_cm3", self.plenum_volume_uncertainty_cm3),
        ):
            if uncertainty is not None and (not math.isfinite(uncertainty) or uncertainty < 0):
                raise ValueError(f"{name} must be finite and nonnegative")
        finite_values = (
            *self.input_delay_bounds_s,
            self.input_delay_s,
            self.current_sigma_mA,
            self.o2_sigma_pct,
            self.temperature_sigma_k,
            self.membrane_temperature_sigma_k,
        )
        if not all(math.isfinite(x) for x in finite_values):
            raise ValueError("delays and observation uncertainties must be finite")
        if self.input_delay_bounds_s[0] > self.input_delay_bounds_s[1]:
            raise ValueError("input_delay_bounds_s must be ordered")
        if not self.input_delay_bounds_s[0] <= self.input_delay_s <= self.input_delay_bounds_s[1]:
            raise ValueError("input_delay_s must fall within input_delay_bounds_s")
        return self


def load_config(path: str | Path) -> ModelConfig:
    return ModelConfig.model_validate_json(Path(path).read_text())


def load_manifest(path: str | Path) -> ExperimentManifest:
    manifest_path = Path(path)
    manifest = ExperimentManifest.model_validate_json(manifest_path.read_text())
    csv_path = Path(manifest.csv_path)
    if not csv_path.is_absolute():
        manifest.csv_path = str((manifest_path.parent / csv_path).resolve())
    return manifest


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
