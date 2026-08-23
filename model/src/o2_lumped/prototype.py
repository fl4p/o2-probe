from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from scipy.signal import TransferFunction, step

from .config import ExperimentManifest, ModelConfig, Provenance, StepWindow
from .metrics import analyze_steps
from .physics import simulate
from .spatial import AxialDomain, simulate_axial_diffusion


R_GAS = 8.314462618


class PrototypeDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    volume_cm3: tuple[float, float, float]
    free_area_mm2: tuple[float, float, float]
    cell_to_membrane_distance_mm: tuple[float, float]
    transport_model: Literal["well_mixed_screening", "axial_1d"] = "well_mixed_screening"
    axial_length_mm: float | None = None
    sensor_position: str
    sensor_orientation: str
    membrane_orientation: str
    heater_geometry: str


class PrototypeStudy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pressure_kpa: float = Field(gt=0)
    gas_temp_c: float
    installed_conductance_scales: list[float] = Field(min_length=2)
    cell_tau_s: list[float] = Field(min_length=1)
    empirical_access_tau_s: list[float] = Field(min_length=1)
    axial_diffusivity_m2_s: list[float] = Field(min_length=2)
    axial_diffusivity_provenance: Literal[
        "measured", "fitted", "assumed", "sensitivity_only"
    ] = "sensitivity_only"
    axial_diffusivity_source: str
    reference_axial_diffusivity_m2_s: float = Field(gt=0)
    axial_nodes: int = Field(default=41, ge=5)
    settling_limit_s: float = Field(default=120.0, gt=0)
    response_dt_s: float = Field(default=0.25, gt=0)
    baseline_design: str
    frontier_areas_mm2: list[float] = Field(min_length=2)
    frontier_volumes_cm3: list[float] = Field(min_length=2)
    target_membrane_rise_k: float = Field(default=2.0, gt=0)
    maximum_block_rise_k: float = Field(default=4.0, gt=0)
    heater_power_ceiling_w: float = Field(default=1.0, gt=0)
    thermal_resistance_range_k_per_w: tuple[float, float]
    thermal_coupling_values: list[float] = Field(min_length=2)
    designs: list[PrototypeDesign] = Field(min_length=1)


@dataclass
class PrototypeResults:
    cases: pd.DataFrame
    summary: pd.DataFrame
    frontier: pd.DataFrame
    thermal: pd.DataFrame
    nonlinear_verification: pd.DataFrame
    axial_diffusion_sensitivity: pd.DataFrame
    recommended: PrototypeDesign


def load_prototype_study(path: str | Path) -> PrototypeStudy:
    return PrototypeStudy.model_validate_json(Path(path).read_text())


def run_prototype_study(config: ModelConfig, study: PrototypeStudy) -> PrototypeResults:
    _validate_study(study)
    rows: list[dict[str, object]] = []
    for design in study.designs:
        for volume_label, volume in zip(("min", "nominal", "max"), design.volume_cm3):
            for area_label, area in zip(("min", "nominal", "max"), design.free_area_mm2):
                for scale in study.installed_conductance_scales:
                    for cell_tau in study.cell_tau_s:
                        for access_tau in study.empirical_access_tau_s:
                            gas_tau = gas_time_constant_s(
                                config,
                                volume,
                                area,
                                scale,
                                study.pressure_kpa,
                                study.gas_temp_c,
                            )
                            metrics = cascade_metrics(
                                gas_tau,
                                access_tau,
                                cell_tau,
                                study.response_dt_s,
                            )
                            rows.append({
                                "design": design.name,
                                "volume_case": volume_label,
                                "volume_cm3": volume,
                                "area_case": area_label,
                                "free_area_mm2": area,
                                "installed_conductance_scale": scale,
                                "gas_tau_s": gas_tau,
                                "cell_tau_s": cell_tau,
                                "empirical_access_tau_s": access_tau,
                                **metrics,
                                "passes_settling_limit": metrics["settling_time_2pct_s"] <= study.settling_limit_s,
                                "transport_model": "well_mixed_screening",
                                "spatial_geometry_modeled": False,
                            })
    cases = pd.DataFrame(rows)
    summaries = []
    for design in study.designs:
        selected = cases[cases.design == design.name]
        central = selected[
            (selected.volume_case == "nominal")
            & (selected.area_case == "nominal")
            & np.isclose(selected.installed_conductance_scale, max(study.installed_conductance_scales))
            & np.isclose(selected.cell_tau_s, min(study.cell_tau_s))
            & np.isclose(selected.empirical_access_tau_s, min(study.empirical_access_tau_s))
        ].iloc[0]
        worst = selected.loc[selected.settling_time_2pct_s.idxmax()]
        hard_geometry = selected[
            (selected.volume_case == "max")
            & (selected.area_case == "min")
            & np.isclose(selected.cell_tau_s, max(study.cell_tau_s))
            & np.isclose(selected.empirical_access_tau_s, max(study.empirical_access_tau_s))
        ]
        passing_scales = hard_geometry.loc[
            hard_geometry.passes_settling_limit, "installed_conductance_scale"
        ]
        summaries.append({
            "design": design.name,
            "nominal_dry_no_access_settling_time_2pct_s": float(central.settling_time_2pct_s),
            "nominal_dry_no_access_t90_s": float(central.t90_s),
            "worst_studied_settling_time_2pct_s": float(worst.settling_time_2pct_s),
            "worst_case_conductance_scale": float(worst.installed_conductance_scale),
            "all_studied_cases_pass": bool(selected.passes_settling_limit.all()),
            "minimum_scale_passing_at_hard_geometry": (
                float(passing_scales.min()) if len(passing_scales) else None
            ),
            "volume_nominal_cm3": design.volume_cm3[1],
            "free_area_nominal_mm2": design.free_area_mm2[1],
            "cell_to_membrane_distance_nominal_mm": float(np.mean(design.cell_to_membrane_distance_mm)),
            "transport_model": "well_mixed_screening",
            "spatial_geometry_modeled": False,
            "selection_basis": "volume_area_screening_only",
        })
    summary = pd.DataFrame(summaries)
    recommended_name = summary.sort_values(
        ["all_studied_cases_pass", "worst_studied_settling_time_2pct_s"],
        ascending=[False, True],
    ).iloc[0].design
    recommended = next(design for design in study.designs if design.name == recommended_name)
    frontier = _frontier(config, study)
    thermal = _thermal_sensitivity(study)
    nonlinear_verification = _nonlinear_verification(config, study)
    axial_diffusion_sensitivity = _axial_diffusion_sensitivity(config, study)
    return PrototypeResults(
        cases,
        summary,
        frontier,
        thermal,
        nonlinear_verification,
        axial_diffusion_sensitivity,
        recommended,
    )


def gas_time_constant_s(
    config: ModelConfig,
    volume_cm3: float,
    free_area_mm2: float,
    installed_conductance_scale: float,
    pressure_kpa: float,
    temp_c: float,
) -> float:
    if volume_cm3 <= 0 or free_area_mm2 <= 0 or installed_conductance_scale <= 0:
        return float("inf")
    total_moles = pressure_kpa * 1000.0 * volume_cm3 * 1e-6 / (R_GAS * (temp_c + 273.15))
    conductance = _conductance_for_area(config, free_area_mm2) * installed_conductance_scale
    return float(total_moles / conductance)


def cascade_metrics(
    gas_tau_s: float,
    access_tau_s: float,
    cell_tau_s: float,
    dt_s: float = 0.25,
) -> dict[str, float]:
    taus = [tau for tau in (gas_tau_s, access_tau_s, cell_tau_s) if tau > 1e-9]
    if not taus or not all(np.isfinite(tau) for tau in taus):
        return {"t90_s": float("inf"), "settling_time_2pct_s": float("inf")}
    numerator = [1.0 / float(np.prod(taus))]
    denominator = np.poly([-1.0 / tau for tau in taus])
    system = TransferFunction(numerator, denominator)
    horizon = max(300.0, 12.0 * sum(taus))
    times = np.arange(0.0, horizon + dt_s * 0.5, dt_s)
    _, response = step(system, T=times)
    return {
        "t90_s": _crossing(times, response, 0.90),
        "settling_time_2pct_s": _crossing(times, response, 0.98),
    }


def candidate_config(config: ModelConfig, design: PrototypeDesign) -> ModelConfig:
    candidate = config.model_copy(deep=True)
    candidate.calibrated = False
    candidate.geometry_revision = f"{design.name}:sensitivity-concept"
    candidate.geometry.plenum_volume_cm3.value = design.volume_cm3[1]
    candidate.geometry.plenum_volume_cm3.uncertainty = max(
        design.volume_cm3[1] - design.volume_cm3[0],
        design.volume_cm3[2] - design.volume_cm3[1],
    )
    candidate.geometry.plenum_volume_cm3.provenance = Provenance.SENSITIVITY_ONLY
    candidate.geometry.plenum_volume_cm3.source = "prototype response study; verify by CAD fill-volume calculation and measurement"
    candidate.geometry.free_membrane_area_mm2.value = design.free_area_mm2[1]
    candidate.geometry.free_membrane_area_mm2.uncertainty = max(
        design.free_area_mm2[1] - design.free_area_mm2[0],
        design.free_area_mm2[2] - design.free_area_mm2[1],
    )
    candidate.geometry.free_membrane_area_mm2.provenance = Provenance.SENSITIVITY_ONLY
    candidate.geometry.free_membrane_area_mm2.source = "prototype response study projected free area; measure completed supported cartridge"
    return candidate


def render_prototype_report(config: ModelConfig, study: PrototypeStudy, results: PrototypeResults) -> str:
    recommended = results.recommended
    baseline = next(design for design in study.designs if design.name == study.baseline_design)
    baseline_distance = float(np.mean(baseline.cell_to_membrane_distance_mm))
    current = results.summary[results.summary.design == study.baseline_design].iloc[0]
    chosen = results.summary[results.summary.design == recommended.name].iloc[0]
    verified_chosen = results.nonlinear_verification[
        (results.nonlinear_verification.design == recommended.name)
        & (results.nonlinear_verification.case == "hard")
    ].iloc[0]
    current_axial_rows = results.axial_diffusion_sensitivity[
        (results.axial_diffusion_sensitivity.design == current.design)
        & (results.axial_diffusion_sensitivity.case == "central")
    ]
    current_axial_reference = current_axial_rows[
        np.isclose(
            current_axial_rows.effective_axial_diffusivity_m2_s,
            study.reference_axial_diffusivity_m2_s,
        )
    ].iloc[0]
    current_axial_settling = current_axial_rows.settling_time_2pct_s.dropna()
    minimum_eta = study.target_membrane_rise_k / study.maximum_block_rise_k
    return f"""# Prototype response study

Status: **uncalibrated sensitivity study**, not a validated compost response prediction.

## Screening outcome

Retain `{recommended.name}` as the response-oriented **build candidate**, not a verified response decision: {recommended.description}

- effective gas volume target: {recommended.volume_cm3[1]:g} cm³ nominal, {recommended.volume_cm3[0]:g}–{recommended.volume_cm3[2]:g} cm³ study band;
- supported free membrane area: {recommended.free_area_mm2[1]:g} mm² nominal, {recommended.free_area_mm2[0]:g}–{recommended.free_area_mm2[2]:g} mm² band;
- cell-to-membrane path: {recommended.cell_to_membrane_distance_mm[0]:g}–{recommended.cell_to_membrane_distance_mm[1]:g} mm;
- cell: {recommended.sensor_position}; orientation: {recommended.sensor_orientation};
- membrane: {recommended.membrane_orientation};
- heater: {recommended.heater_geometry}.

The current Rev-A is **not well mixed**. With its {baseline.axial_length_mm:g} mm closed axial domain and the cell {baseline_distance:g} mm behind the membrane, the heater-off 1-D finite-volume model gives t90={current_axial_reference.t90_s:.1f} s and 2% settling={current_axial_reference.settling_time_2pct_s:.1f} s at the reference effective diffusivity {study.reference_axial_diffusivity_m2_s:.2g} m²/s. Across the uncalibrated {min(study.axial_diffusivity_m2_s):.2g}–{max(study.axial_diffusivity_m2_s):.2g} m²/s range, central-case settling spans {current_axial_settling.min():.1f}–{current_axial_settling.max():.1f} s. The {current.nominal_dry_no_access_settling_time_2pct_s:.1f} s current-design result is only an idealized well-mixed estimate that omitted the axial path; it is not the current geometry's predicted response.

Under the deliberately hard **well-mixed volume/area sensitivity** (largest volume, smallest area, {min(study.installed_conductance_scales):g}× installed conductance, {max(study.cell_tau_s):g} s cell lag and {max(study.empirical_access_tau_s):g} s empirical access lag), the proposed dual-side concept's linearized 2% estimate is {chosen.worst_studied_settling_time_2pct_s:.1f} s and its nonlinear well-mixed check gives {verified_chosen.settling_time_2pct_s:.1f} s. The candidate's nominal-dry, no-access well-mixed estimate is {chosen.nominal_dry_no_access_settling_time_2pct_s:.1f} s. These screening numbers do not bound the spatial result. The separate `voxel` study represents the finite candidate geometry and is the governing numerical screen for its 1–2 minute target.

The 120 s result means only **“passes the chosen {min(study.installed_conductance_scales):g}× conductance sensitivity scenario.”** It is not evidence that a wet or fouled PMV15T assembly retains that conductance. Lower conductance can exceed 120 s. The multiplier and any geometry-specific access lag must be measured.

The axial model explicitly includes the existing design's domain length and sensor depth. It still replaces PCB, package and port blockage by one effective diffusivity and therefore remains a sensitivity model. The separate 3-D voxel model resolves the candidate's finite windows, PCB, cell envelope, rear aperture and membrane access gap. Drainage, water films, heater convection and true sensor-port coupling remain unvalidated. Promote the geometry only with complete-path measurements.

## Why this geometry

The current axial membrane is about {baseline_distance:g} mm from the cell and leaves roughly {current.volume_nominal_cm3:g} cm³ effective gas volume. Its large membrane area makes the membrane/inventory time constant only a few seconds in the central sensitivity case; the explicit model shows the long axial diffusion path is the main response penalty. Moving the cell/window system into a local, filled or shrouded microplenum is intended to shorten that path while reducing inventory without deliberately restricting the membrane. Two drained side facets keep the membrane close to the cell's lateral gas faces and avoid an upward-facing liquid pocket. The routed rear PCB aperture remains mandatory.

Do not interpret the heater as an air pump. Heater power is absent from the gas-transfer equation because no calibrated power/orientation/convection law exists. Its job is condensation margin. With a maximum allowed block rise of {study.maximum_block_rise_k:g} K and desired membrane rise of {study.target_membrane_rise_k:g} K, measured membrane coupling must be at least η={minimum_eta:.2f}. A remote cell-island heater cannot be accepted if the measured coupling is lower; the proposed dry-side carrier-rim heater remains a concept until temporary cold-spot thermometry validates it. The one-node model provides only quasi-steady thermal screening.

## Build constraints

1. Seal the local cavity at both PCB crossings and on both sides of the radial shroud/tube annulus, then measure connected effective free volume; the response target is ≤{recommended.volume_cm3[2]:g} cm³, not a geometric guess.
2. Measure projected free area after the PP support; the response target is ≥{recommended.free_area_mm2[0]:g} mm².
3. Key installation so membrane facets face sideways/downward and all lower edges drain into an open gap behind the debris guard.
4. Keep both SGX faces clear; retain the routed ~3 mm rear aperture until a physical cell establishes the true port size.
5. Thermally bond the cell body to the island, heat the membrane carrier from the dry side, and keep the membrane below vendor/material limits.
6. Preheat before accepting O₂ response data; thermal warm-up and O₂ settling are separate gates.
7. A/B test PMV15T against MMS341 in identical cartridges. Do not substitute vendor pressure airflow for concentration-step conductance.

## Required validation

Run complete-path steps at horizontal, vertical and inverted cell orientations; membrane facets keyed downward and deliberately misoriented; heater off and regulated; dry, saturated, droplet-covered, drained, condensate-exposed and aged/fouled states. The nonlinear verification uses dry transport equations with a 100% RH input; RH does not affect transport in V1 and this is not wet validation. Promote this geometry only when every required regime has a measured conductance multiplier and held-out 2% settling remains ≤{study.settling_limit_s:g} s.

Generated from model version `{config.model_version}`. See `axial_diffusion_sensitivity.csv`, `prototype_cases.csv`, `design_summary.csv`, `nonlinear_verification.csv`, `feasible_frontier.csv`, `thermal_sensitivity.csv` and the plots for the full sensitivity matrix.
"""


def _conductance_for_area(config: ModelConfig, free_area_mm2: float) -> float:
    base_area = config.geometry.free_membrane_area_mm2.require("geometry.free_membrane_area_mm2")
    if config.gas.area_model == "fixed_conductance":
        if not np.isclose(free_area_mm2, base_area):
            raise ValueError("prototype area search requires area_only or area_plus_access conductance model")
        return config.gas.window_conductance_mol_per_s.require("gas.window_conductance_mol_per_s")
    if config.gas.area_model == "area_only":
        base = config.gas.window_conductance_mol_per_s.require("gas.window_conductance_mol_per_s")
        return base * free_area_mm2 / base_area
    k_area = config.gas.area_conductance_mol_per_s_m2.require(
        "gas.area_conductance_mol_per_s_m2"
    )
    resistance = config.gas.access_resistance_s_per_mol.require(
        "gas.access_resistance_s_per_mol"
    )
    return 1.0 / (1.0 / (free_area_mm2 * 1e-6 * k_area) + resistance)


def _crossing(times: np.ndarray, response: np.ndarray, target: float) -> float:
    indices = np.flatnonzero(response >= target)
    if not len(indices):
        return float("inf")
    index = int(indices[0])
    if index == 0:
        return float(times[0])
    t0, t1 = times[index - 1], times[index]
    y0, y1 = response[index - 1], response[index]
    return float(t1 if y1 == y0 else t0 + (target - y0) * (t1 - t0) / (y1 - y0))


def _frontier(config: ModelConfig, study: PrototypeStudy) -> pd.DataFrame:
    rows = []
    scale = min(study.installed_conductance_scales)
    cell_tau = max(study.cell_tau_s)
    access_tau = max(study.empirical_access_tau_s)
    for area in study.frontier_areas_mm2:
        passing = []
        for volume in study.frontier_volumes_cm3:
            gas_tau = gas_time_constant_s(
                config, volume, area, scale, study.pressure_kpa, study.gas_temp_c
            )
            settling = cascade_metrics(gas_tau, access_tau, cell_tau, study.response_dt_s)[
                "settling_time_2pct_s"
            ]
            if settling <= study.settling_limit_s:
                passing.append((volume, settling))
        rows.append({
            "free_area_mm2": area,
            "maximum_volume_cm3_at_limit": max((item[0] for item in passing), default=np.nan),
            "settling_time_at_frontier_s": (
                max(passing, key=lambda item: item[0])[1] if passing else np.nan
            ),
            "installed_conductance_scale": scale,
            "cell_tau_s": cell_tau,
            "empirical_access_tau_s": access_tau,
        })
    return pd.DataFrame(rows)


def _thermal_sensitivity(study: PrototypeStudy) -> pd.DataFrame:
    resistance_min, resistance_max = study.thermal_resistance_range_k_per_w
    rows = []
    for coupling in study.thermal_coupling_values:
        block_rise = study.target_membrane_rise_k / coupling
        rows.append({
            "membrane_coupling_eta": coupling,
            "required_block_rise_k": block_rise,
            "required_power_at_low_rth_w": block_rise / resistance_min,
            "required_power_at_high_rth_w": block_rise / resistance_max,
            "passes_block_rise_limit": block_rise <= study.maximum_block_rise_k,
            "passes_power_ceiling": block_rise / resistance_min <= study.heater_power_ceiling_w,
        })
    return pd.DataFrame(rows)


def _nonlinear_verification(config: ModelConfig, study: PrototypeStudy) -> pd.DataFrame:
    time = np.arange(0.0, 600.0 + study.response_dt_s * 0.5, study.response_dt_s)
    inputs = pd.DataFrame({
        "time_s": time,
        "o2_reference_pct_wet": np.where(time < 60.0, 0.0, 20.95),
        "pressure_reference_kpa": np.full(len(time), study.pressure_kpa),
        "temp_ambient_c": np.full(len(time), study.gas_temp_c),
        "temp_inlet_c": np.full(len(time), study.gas_temp_c),
        "rh_ambient_pct": np.full(len(time), 100.0),
        "heater_power_w": np.zeros(len(time)),
    })
    window = StepWindow(
        label="nitrogen_to_air",
        baseline_start_s=20.0,
        baseline_end_s=50.0,
        start_s=60.0,
        steady_start_s=500.0,
        steady_end_s=600.0,
    )
    rows = []
    for design in study.designs:
        for case_name, volume, area, scale, cell_tau, access_tau in (
            (
                "central",
                design.volume_cm3[1],
                design.free_area_mm2[1],
                max(study.installed_conductance_scales),
                min(study.cell_tau_s),
                min(study.empirical_access_tau_s),
            ),
            (
                "hard",
                design.volume_cm3[2],
                design.free_area_mm2[0],
                min(study.installed_conductance_scales),
                max(study.cell_tau_s),
                max(study.empirical_access_tau_s),
            ),
        ):
            working = config.model_copy(deep=True)
            working.geometry.plenum_volume_cm3.value = volume
            working.geometry.free_membrane_area_mm2.value = area
            working.cell.tau_s.value = cell_tau
            working.gas.access_enabled = access_tau > 0.0
            if access_tau > 0.0:
                working.gas.access_tau_s.value = access_tau
                working.gas.access_tau_s.provenance = Provenance.SENSITIVITY_ONLY
            working.regimes["dry"].conductance_multiplier.value = scale
            manifest = ExperimentManifest(
                experiment_id=f"{design.name}-{case_name}",
                csv_path="generated-in-memory",
                assembly_stage="window",
                role="simulation",
                orientation=design.sensor_orientation,
                regime="dry",
                step_windows=[window],
            )
            result = simulate(working, manifest, inputs)
            metrics = analyze_steps(result.frame, [window])[0]
            rows.append({
                "design": design.name,
                "case": case_name,
                "volume_cm3": volume,
                "free_area_mm2": area,
                "installed_conductance_scale": scale,
                "cell_tau_s": cell_tau,
                "empirical_access_tau_s": access_tau,
                "t90_s": metrics["t90_s"],
                "settling_time_2pct_s": metrics["settling_time_2pct_s"],
                "steady_bias_o2_pct_wet": metrics["steady_bias_o2_pct_wet"],
                "passes_settling_limit": (
                    metrics["settling_time_2pct_s"] is not None
                    and metrics["settling_time_2pct_s"] <= study.settling_limit_s
                ),
                "transport_regime_equations": "dry",
                "rh_input_pct": 100.0,
                "humidity_effect_modeled": False,
                "transport_model": "well_mixed_screening",
            })
    return pd.DataFrame(rows)


def _axial_diffusion_sensitivity(
    config: ModelConfig, study: PrototypeStudy
) -> pd.DataFrame:
    """Evaluate explicitly axial designs without credit for heater convection."""
    rows: list[dict[str, object]] = []
    for design in study.designs:
        if design.transport_model != "axial_1d":
            continue
        assert design.axial_length_mm is not None
        cases = (
            (
                "central",
                design.volume_cm3[1],
                design.free_area_mm2[1],
                float(np.mean(design.cell_to_membrane_distance_mm)),
                max(study.installed_conductance_scales),
                min(study.cell_tau_s),
            ),
            (
                "hard_geometry_no_empirical_access_lag",
                design.volume_cm3[2],
                design.free_area_mm2[0],
                design.cell_to_membrane_distance_mm[1],
                min(study.installed_conductance_scales),
                max(study.cell_tau_s),
            ),
        )
        for case_name, volume, area, distance, scale, cell_tau in cases:
            for diffusivity in study.axial_diffusivity_m2_s:
                membrane_tau = gas_time_constant_s(
                    config,
                    volume,
                    area,
                    scale,
                    study.pressure_kpa,
                    study.gas_temp_c,
                )
                diffusion_tau = (design.axial_length_mm * 1e-3) ** 2 / diffusivity
                horizon = max(
                    600.0,
                    60.0 + 7.0 * (membrane_tau + diffusion_tau + cell_tau) + 200.0,
                )
                time = np.arange(
                    0.0, horizon + study.response_dt_s * 0.5, study.response_dt_s
                )
                inputs = pd.DataFrame({
                    "time_s": time,
                    "o2_reference_pct_wet": np.where(time < 60.0, 0.0, 20.95),
                    "pressure_reference_kpa": study.pressure_kpa,
                    "temp_ambient_c": study.gas_temp_c,
                    "temp_inlet_c": study.gas_temp_c,
                    "rh_ambient_pct": 100.0,
                    "heater_power_w": 0.0,
                })
                window = StepWindow(
                    label="nitrogen_to_air",
                    baseline_start_s=20.0,
                    baseline_end_s=50.0,
                    start_s=60.0,
                    steady_start_s=horizon - 150.0,
                    steady_end_s=horizon,
                )
                working = config.model_copy(deep=True)
                working.geometry.plenum_volume_cm3.value = volume
                working.geometry.free_membrane_area_mm2.value = area
                working.cell.tau_s.value = cell_tau
                working.gas.access_enabled = False
                working.regimes["dry"].conductance_multiplier.value = scale
                manifest = ExperimentManifest(
                    experiment_id=f"{design.name}-{case_name}-{diffusivity:g}",
                    csv_path="generated-in-memory",
                    assembly_stage="window",
                    role="simulation",
                    orientation=design.sensor_orientation,
                    regime="dry",
                    step_windows=[window],
                )
                domain = AxialDomain(
                    length_mm=design.axial_length_mm,
                    sensor_distance_from_membrane_mm=distance,
                    effective_diffusivity_m2_s=diffusivity,
                    nodes=study.axial_nodes,
                    diffusivity_provenance=study.axial_diffusivity_provenance,
                    diffusivity_source=study.axial_diffusivity_source,
                )
                result = simulate_axial_diffusion(working, manifest, inputs, domain)
                metrics = analyze_steps(result.frame, [window])[0]
                rows.append({
                    "design": design.name,
                    "case": case_name,
                    "volume_cm3": volume,
                    "free_area_mm2": area,
                    "axial_length_mm": design.axial_length_mm,
                    "sensor_distance_from_membrane_mm": distance,
                    "effective_axial_diffusivity_m2_s": diffusivity,
                    "effective_axial_diffusivity_provenance": study.axial_diffusivity_provenance,
                    "effective_axial_diffusivity_source": study.axial_diffusivity_source,
                    "installed_conductance_scale": scale,
                    "cell_tau_s": cell_tau,
                    "empirical_access_tau_s": 0.0,
                    "t90_s": metrics["t90_s"],
                    "settling_time_2pct_s": metrics["settling_time_2pct_s"],
                    "steady_bias_o2_pct_wet": metrics["steady_bias_o2_pct_wet"],
                    "steady_state_reached": metrics["steady_state_reached"],
                    "response_metrics_valid": metrics["response_metrics_valid"],
                    "passes_settling_limit": (
                        metrics["settling_time_2pct_s"] is not None
                        and metrics["settling_time_2pct_s"] <= study.settling_limit_s
                    ),
                    "transport_model": "axial_finite_volume_diffusion",
                    "heater_power_w": 0.0,
                    "heater_convection_modeled": False,
                    "humidity_effect_modeled": False,
                    "axial_nodes": study.axial_nodes,
                })
    return pd.DataFrame(rows)


def _validate_study(study: PrototypeStudy) -> None:
    strictly_positive = (
        ("installed_conductance_scales", study.installed_conductance_scales),
        ("cell_tau_s", study.cell_tau_s),
        ("frontier_areas_mm2", study.frontier_areas_mm2),
        ("frontier_volumes_cm3", study.frontier_volumes_cm3),
        ("thermal_coupling_values", study.thermal_coupling_values),
        ("axial_diffusivity_m2_s", study.axial_diffusivity_m2_s),
    )
    for name, values in strictly_positive:
        if not all(np.isfinite(value) and value > 0 for value in values):
            raise ValueError(f"{name} values must be finite and positive")
    if not all(
        np.isfinite(value) and value >= 0 for value in study.empirical_access_tau_s
    ):
        raise ValueError("empirical_access_tau_s values must be finite and nonnegative")
    resistance_min, resistance_max = study.thermal_resistance_range_k_per_w
    if not (
        np.isfinite(resistance_min)
        and np.isfinite(resistance_max)
        and 0 < resistance_min <= resistance_max
    ):
        raise ValueError("thermal_resistance_range_k_per_w must be finite, positive, and ordered")
    if study.gas_temp_c <= -273.15:
        raise ValueError("gas_temp_c must be above absolute zero")
    design_names = [design.name for design in study.designs]
    if len(design_names) != len(set(design_names)):
        raise ValueError("prototype design names must be unique")
    if study.baseline_design not in design_names:
        raise ValueError("baseline_design must name one configured design")
    baseline = next(
        design for design in study.designs if design.name == study.baseline_design
    )
    if baseline.transport_model != "axial_1d":
        raise ValueError("baseline_design must select an axial_1d design")
    if not study.axial_diffusivity_source.strip():
        raise ValueError("axial_diffusivity_source must be declared")
    if not any(
        np.isclose(value, study.reference_axial_diffusivity_m2_s)
        for value in study.axial_diffusivity_m2_s
    ):
        raise ValueError("reference axial diffusivity must be one of the sensitivity values")
    for design in study.designs:
        for name, values in (("volume_cm3", design.volume_cm3), ("free_area_mm2", design.free_area_mm2)):
            if not (0 < values[0] <= values[1] <= values[2]):
                raise ValueError(f"{design.name}.{name} must be positive and ordered min/nominal/max")
        if not (
            0 < design.cell_to_membrane_distance_mm[0]
            <= design.cell_to_membrane_distance_mm[1]
        ):
            raise ValueError(f"{design.name}.cell_to_membrane_distance_mm must be positive and ordered")
        if design.transport_model == "axial_1d":
            if design.axial_length_mm is None or design.axial_length_mm <= 0:
                raise ValueError(f"{design.name}.axial_length_mm must be positive for axial_1d")
            if design.cell_to_membrane_distance_mm[1] > design.axial_length_mm:
                raise ValueError(
                    f"{design.name} sensor distance cannot exceed axial_length_mm"
                )
        elif design.axial_length_mm is not None:
            raise ValueError(
                f"{design.name}.axial_length_mm is only valid for axial_1d"
            )
