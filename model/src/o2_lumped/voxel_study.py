from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .config import ExperimentManifest, ModelConfig
from .voxel import (
    VoxelCandidateDomain,
    apply_voxel_cell_response,
    monotonic_voxel_metrics,
    simulate_voxel_gas_step,
)


class VoxelScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    geometry_status: Literal["existing_cad", "proposed_geometry"]
    volume_cm3: float = Field(gt=0)
    free_area_mm2: float = Field(gt=0)
    installed_conductance_scale: float = Field(gt=0)
    cell_tau_s: float = Field(gt=0)
    radius_mm: float = Field(gt=0)
    clear_length_mm: float = Field(gt=0)
    window_centres_deg: tuple[float, float]
    window_width_mm: float = Field(gt=0)
    window_height_mm: float = Field(gt=0)
    membrane_to_cavity_path_mm: float = Field(ge=0)
    rear_aperture_diameter_mm: float = Field(gt=0)


class VoxelStudy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pressure_kpa: float = Field(gt=0)
    gas_temp_c: float
    duration_s: float = Field(gt=0)
    output_dt_s: float = Field(gt=0, le=1.0)
    grid_spacing_xy_mm: float = Field(gt=0)
    target_grid_spacing_z_mm: float = Field(gt=0)
    effective_diffusivity_m2_s: list[float] = Field(min_length=2)
    diffusivity_provenance: Literal["measured", "fitted", "assumed", "sensitivity_only"]
    diffusivity_source: str
    front_port_weights: list[float] = Field(min_length=3)
    settling_limit_s: float = Field(gt=0)
    candidate_scenario: str
    scenarios: list[VoxelScenario] = Field(min_length=2)


@dataclass(frozen=True)
class VoxelStudyResults:
    cases: pd.DataFrame
    summary: pd.DataFrame


def load_voxel_study(path: str | Path) -> VoxelStudy:
    study = VoxelStudy.model_validate_json(Path(path).read_text())
    validate_voxel_study(study)
    return study


def validate_voxel_study(study: VoxelStudy) -> None:
    if study.gas_temp_c <= -273.15:
        raise ValueError("gas temperature must be above absolute zero")
    if not study.diffusivity_source.strip():
        raise ValueError("diffusivity source must be declared")
    if not all(
        np.isfinite(value) and value > 0.0 for value in study.effective_diffusivity_m2_s
    ):
        raise ValueError("effective diffusivities must be finite and positive")
    if not all(
        np.isfinite(value) and 0.0 <= value <= 1.0 for value in study.front_port_weights
    ):
        raise ValueError("front-port weights must lie within [0, 1]")
    if not {0.0, 1.0}.issubset(set(study.front_port_weights)):
        raise ValueError(
            "port-weight sensitivity must include rear-only and front-only endpoints"
        )
    names = [scenario.name for scenario in study.scenarios]
    if len(names) != len(set(names)):
        raise ValueError("voxel scenario names must be unique")
    if study.candidate_scenario not in names:
        raise ValueError("candidate_scenario must name a configured scenario")


def run_voxel_study(config: ModelConfig, study: VoxelStudy) -> VoxelStudyResults:
    validate_voxel_study(study)
    rows: list[dict[str, object]] = []
    for scenario in study.scenarios:
        working = config.model_copy(deep=True)
        working.geometry.plenum_volume_cm3.value = scenario.volume_cm3
        working.geometry.free_membrane_area_mm2.value = scenario.free_area_mm2
        working.regimes[
            "dry"
        ].conductance_multiplier.value = scenario.installed_conductance_scale
        working.cell.tau_s.value = scenario.cell_tau_s
        manifest = ExperimentManifest(
            experiment_id=scenario.name,
            csv_path="generated-in-memory",
            assembly_stage="window",
            role="simulation",
            orientation="horizontal, keyed drainage datum",
            regime="dry",
        )
        domain = VoxelCandidateDomain(
            radius_mm=scenario.radius_mm,
            clear_length_mm=scenario.clear_length_mm,
            grid_spacing_xy_mm=study.grid_spacing_xy_mm,
            target_grid_spacing_z_mm=study.target_grid_spacing_z_mm,
            window_centres_deg=scenario.window_centres_deg,
            window_width_mm=scenario.window_width_mm,
            window_height_mm=scenario.window_height_mm,
            membrane_to_cavity_path_mm=scenario.membrane_to_cavity_path_mm,
            rear_aperture_diameter_mm=scenario.rear_aperture_diameter_mm,
        )
        for diffusivity in study.effective_diffusivity_m2_s:
            gas_frame, diagnostics = simulate_voxel_gas_step(
                working,
                manifest,
                domain,
                diffusivity,
                study.duration_s,
                study.output_dt_s,
                study.pressure_kpa,
                study.gas_temp_c,
            )
            front_gas = monotonic_voxel_metrics(gas_frame, "o2_front_port_pct_wet")
            rear_gas = monotonic_voxel_metrics(gas_frame, "o2_rear_port_pct_wet")
            for weight in study.front_port_weights:
                frame, _ = apply_voxel_cell_response(
                    working,
                    gas_frame,
                    diagnostics,
                    weight,
                    study.pressure_kpa,
                    study.gas_temp_c,
                )
                metrics = monotonic_voxel_metrics(frame)
                rows.append(
                    {
                        "scenario": scenario.name,
                        "description": scenario.description,
                        "geometry_status": scenario.geometry_status,
                        "volume_cm3": scenario.volume_cm3,
                        "free_area_mm2": scenario.free_area_mm2,
                        "installed_conductance_scale": scenario.installed_conductance_scale,
                        "cell_tau_s": scenario.cell_tau_s,
                        "radius_mm": scenario.radius_mm,
                        "clear_length_mm": scenario.clear_length_mm,
                        "window_centres_deg": "/".join(
                            f"{value:g}" for value in scenario.window_centres_deg
                        ),
                        "rear_aperture_diameter_mm": scenario.rear_aperture_diameter_mm,
                        "membrane_to_cavity_path_mm": scenario.membrane_to_cavity_path_mm,
                        "effective_diffusivity_m2_s": diffusivity,
                        "diffusivity_provenance": study.diffusivity_provenance,
                        "diffusivity_source": study.diffusivity_source,
                        "front_port_weight": weight,
                        "front_port_gas_t90_s": front_gas["t90_s"],
                        "front_port_gas_settling_time_2pct_s": front_gas[
                            "settling_time_2pct_s"
                        ],
                        "rear_port_gas_t90_s": rear_gas["t90_s"],
                        "rear_port_gas_settling_time_2pct_s": rear_gas[
                            "settling_time_2pct_s"
                        ],
                        "probe_t90_s": metrics["t90_s"],
                        "probe_settling_time_2pct_s": metrics["settling_time_2pct_s"],
                        "passes_settling_limit": (
                            metrics["settling_time_2pct_s"] is not None
                            and metrics["settling_time_2pct_s"]
                            <= study.settling_limit_s
                        ),
                        "grid_spacing_xy_mm": diagnostics["grid_spacing_xy_mm"],
                        "grid_spacing_z_mm": diagnostics["grid_spacing_z_mm"],
                        "active_cells": diagnostics["active_cells"],
                        "geometric_gas_volume_cm3": diagnostics[
                            "geometric_gas_volume_cm3"
                        ],
                        "volume_capacity_scale": diagnostics["volume_capacity_scale"],
                        "front_port_nodes": diagnostics["front_port_nodes"],
                        "rear_port_nodes": diagnostics["rear_port_nodes"],
                        "transport_model": diagnostics["transport_model"],
                        "heater_convection_modeled": False,
                        "cell_consumption_modeled": False,
                    }
                )
    cases = pd.DataFrame(rows)
    summaries = []
    for scenario in study.scenarios:
        selected = cases[cases.scenario == scenario.name]
        completed = selected.dropna(subset=["probe_settling_time_2pct_s"])
        worst = completed.loc[completed.probe_settling_time_2pct_s.idxmax()]
        incomplete_count = int(selected.probe_settling_time_2pct_s.isna().sum())
        summaries.append(
            {
                "scenario": scenario.name,
                "geometry_status": scenario.geometry_status,
                "all_diffusivity_and_port_weight_cases_pass": bool(
                    selected.passes_settling_limit.all()
                ),
                "worst_probe_settling_time_2pct_s": float(
                    worst.probe_settling_time_2pct_s
                ),
                "worst_probe_t90_s": float(worst.probe_t90_s),
                "worst_effective_diffusivity_m2_s": float(
                    worst.effective_diffusivity_m2_s
                ),
                "worst_front_port_weight": float(worst.front_port_weight),
                "incomplete_response_cases": incomplete_count,
                "volume_cm3": scenario.volume_cm3,
                "free_area_mm2": scenario.free_area_mm2,
                "radius_mm": scenario.radius_mm,
                "window_centres_deg": "/".join(
                    f"{value:g}" for value in scenario.window_centres_deg
                ),
                "selection_basis": "uncalibrated_3d_voxel_sensitivity",
            }
        )
    return VoxelStudyResults(cases=cases, summary=pd.DataFrame(summaries))


def render_voxel_report(study: VoxelStudy, results: VoxelStudyResults) -> str:
    candidate = results.summary[
        results.summary.scenario == study.candidate_scenario
    ].iloc[0]
    existing = results.summary[results.summary.geometry_status == "existing_cad"].iloc[
        0
    ]
    existing_result = (
        f"does not reach the 2% band within {study.duration_s:g} s in "
        f"{int(existing.incomplete_response_cases)} tested case(s); its slowest "
        f"completed result is {existing.worst_probe_settling_time_2pct_s:.1f} s"
        if existing.incomplete_response_cases
        else f"has a worst 2% settling result of {existing.worst_probe_settling_time_2pct_s:.1f} s"
    )
    return f"""# Candidate 3-D spatial response study

Status: **uncalibrated CAD-derived voxel sensitivity**, not a response guarantee.

The existing same-side coupon layout fails the hard spatial sensitivity: it {existing_result}. The proposed
`{study.candidate_scenario}` geometry gives {candidate.worst_probe_settling_time_2pct_s:.1f} s
in its worst tested effective-diffusivity/port-coupling case and
{"passes" if candidate.all_diffusivity_and_port_weight_cases_pass else "does not pass"}
the {study.settling_limit_s:g} s screening limit across the declared matrix.

The candidate screen requires:

- connected effective gas volume no greater than {candidate.volume_cm3:g} cm³;
- supported projected free membrane area at least {candidate.free_area_mm2:g} mm²;
- local shroud ID {2 * candidate.radius_mm:g} mm;
- membrane-to-cavity access length no greater than {results.cases[results.cases.scenario == study.candidate_scenario].iloc[0].membrane_to_cavity_path_mm:g} mm;
- membrane facet centres at {candidate.window_centres_deg} degrees in the keyed
  installation datum, placing one coupon on each PCB side while both remain in
  the two lower/drainable quadrants;
- the rear PCB aperture retained and both modeled sensor port surfaces open;
- no response credit from heater convection.

The screen spans effective diffusivity {min(study.effective_diffusivity_m2_s):.2g}–{max(study.effective_diffusivity_m2_s):.2g} m²/s and front-port coupling weights
{min(study.front_port_weights):g}–{max(study.front_port_weights):g}, including rear-only and front-only endpoints.
Diffusivity, installed conductance scale, and sensor port coupling are unmeasured.
The voxel model resolves the finite window height, PCB, cylindrical cell envelope,
rear aperture and interface-adjacent gas slabs at both ports, but it is not CFD and does not model
compost flow, water films, heater convection or cell consumption. Confirm with
complete-path dry/wet/fouled steps before fabrication release. The declared
membrane-to-cavity access length is a quasi-steady series resistance; the access
channel itself is not voxelized, so the existing 5.8 mm-path failure is a robust
screen rather than a resolved channel-flow prediction.
"""
