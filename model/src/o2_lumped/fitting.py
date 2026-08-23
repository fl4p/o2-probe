from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from .config import ExperimentManifest, ModelConfig, Provenance
from .io import load_experiment_frame
from .physics import simulate, static_signal


@dataclass
class FitResult:
    config: ModelConfig
    report: dict[str, Any]


def _require_measured_override(
    manifest: ExperimentManifest,
    value_field: str,
    uncertainty_field: str,
    provenance_field: str,
    source_field: str,
) -> None:
    if getattr(manifest, value_field) is None:
        return
    uncertainty = getattr(manifest, uncertainty_field)
    provenance = getattr(manifest, provenance_field)
    source = getattr(manifest, source_field)
    if uncertainty is None or provenance != "measured" or not source or not source.strip():
        raise ValueError(
            f"calibration override {value_field} requires measured provenance, uncertainty, and source"
        )


def _static_plateaus(manifest: ExperimentManifest, frame: pd.DataFrame) -> list[dict[str, float]]:
    if not manifest.step_windows:
        raise ValueError("static calibration requires declared equilibrated steady windows")
    plateaus = []
    temp_column = "temp_block_c" if "temp_block_c" in frame else "temp_ambient_c"
    for window in manifest.step_windows:
        rows = frame[
            (frame.time_s >= window.steady_start_s) & (frame.time_s <= window.steady_end_s)
        ]
        if len(rows) < 3:
            raise ValueError(f"static plateau {window.label!r} requires at least three samples")
        duration = float(rows.time_s.iloc[-1] - rows.time_s.iloc[0])
        if duration <= 0:
            raise ValueError(f"static plateau {window.label!r} has zero duration")
        if float(np.ptp(rows.o2_reference_pct_wet.to_numpy(dtype=float))) > 0.02:
            raise ValueError(f"static plateau {window.label!r} has changing O2 reference")
        if float(np.ptp(np.asarray(rows[temp_column], dtype=float))) > 0.2:
            raise ValueError(f"static plateau {window.label!r} has changing temperature")
        if float(np.ptp(rows.pressure_reference_kpa.to_numpy(dtype=float))) > 0.05:
            raise ValueError(f"static plateau {window.label!r} has changing pressure")
        slope = float(np.polyfit(rows.time_s - rows.time_s.iloc[0], rows.cell_current_mA, 1)[0])
        if abs(slope) > 3.0 * manifest.current_sigma_mA / duration:
            raise ValueError(f"static plateau {window.label!r} current is not equilibrated")
        plateaus.append({
            "o2_pct": float(rows.o2_reference_pct_wet.mean()),
            "pressure_kpa": float(rows.pressure_reference_kpa.mean()),
            "temp_c": float(rows[temp_column].mean()),
            "current_ma": float(rows.cell_current_mA.mean()),
            "sigma_ma": manifest.current_sigma_mA / np.sqrt(len(rows)),
        })
    return plateaus


def _validate_pre_equilibration(
    config: ModelConfig,
    manifest: ExperimentManifest,
    frame: pd.DataFrame,
    stage: str,
) -> None:
    if not manifest.step_windows:
        raise ValueError(f"{stage} calibration requires a declared baseline/steady step window")
    first = min(manifest.step_windows, key=lambda window: window.start_s)
    rows = frame[
        (frame.time_s >= first.baseline_start_s) & (frame.time_s <= first.baseline_end_s)
    ]
    if len(rows) < 3 or float(frame.time_s.iloc[0]) > first.baseline_start_s:
        raise ValueError("dynamic calibration requires at least three pre-step baseline samples")
    duration = float(rows.time_s.iloc[-1] - rows.time_s.iloc[0])
    tau_requirement = 0.0
    if stage in {"access", "window"}:
        tau_requirement = 5.0 * config.cell.tau_s.require("cell.tau_s")
    if duration < max(10.0, tau_requirement):
        raise ValueError("dynamic calibration baseline is too short to verify equilibrium")
    if float(np.ptp(rows.o2_reference_pct_wet.to_numpy(dtype=float))) > 0.02:
        raise ValueError("dynamic calibration baseline O2 reference is not stable")
    if float(np.ptp(rows.pressure_reference_kpa.to_numpy(dtype=float))) > 0.05:
        raise ValueError("dynamic calibration baseline pressure is not stable")
    observed_column = "cell_current_mA" if "cell_current_mA" in rows else "o2_probe_pct"
    sigma = manifest.current_sigma_mA if observed_column == "cell_current_mA" else manifest.o2_sigma_pct
    slope = float(np.polyfit(rows.time_s - rows.time_s.iloc[0], rows[observed_column], 1)[0])
    if abs(slope) > 3.0 * sigma / duration:
        raise ValueError("dynamic calibration observed baseline is not equilibrated")
    mean_o2 = float(rows.o2_reference_pct_wet.mean())
    mean_pressure = float(rows.pressure_reference_kpa.mean())
    temp_column = "temp_block_c" if "temp_block_c" in rows else "temp_ambient_c"
    mean_temp = float(rows[temp_column].mean())
    if observed_column == "cell_current_mA":
        expected = static_signal(config, mean_o2 / 100.0, mean_pressure, mean_temp)
        tolerance = 5.0 * manifest.current_sigma_mA
    else:
        expected = mean_o2
        tolerance = max(5.0 * manifest.o2_sigma_pct, 0.3)
    if abs(float(rows[observed_column].mean()) - expected) > tolerance:
        raise ValueError("dynamic calibration baseline disagrees with the static calibration")


def _validate_stage_prerequisites(
    config: ModelConfig,
    manifests: Sequence[ExperimentManifest],
    stage: str,
) -> None:
    expected_assembly = {
        "static": "static",
        "thermal": "thermal",
        "bare": "bare",
        "access": "carrier",
        "window": "window",
    }
    if stage not in expected_assembly:
        raise ValueError(f"unsupported fit stage {stage!r}")
    expected = expected_assembly[stage]
    incompatible = [m.experiment_id for m in manifests if m.assembly_stage != expected]
    if incompatible:
        raise ValueError(f"{stage} fit requires assembly_stage={expected!r}: {incompatible}")
    simulations = [m.experiment_id for m in manifests if m.role == "simulation"]
    if simulations:
        raise ValueError(f"simulation-role manifests cannot be fitted: {simulations}")
    experiment_ids = [manifest.experiment_id for manifest in manifests]
    if len(experiment_ids) != len(set(experiment_ids)):
        raise ValueError("experiment_id values must be unique within a fit")
    if stage != "access":
        validation = [m.experiment_id for m in manifests if m.role != "calibration"]
        if validation:
            raise ValueError(f"validation data cannot be used to fit {stage}: {validation}")

    prerequisite_paths: dict[str, tuple[str, ...]] = {
        "static": (),
        "thermal": (),
        "bare": ("cell.i_zero_ma", "cell.k_ref_ma"),
        "access": ("cell.i_zero_ma", "cell.k_ref_ma", "cell.tau_s"),
        "window": (
            "cell.i_zero_ma",
            "cell.k_ref_ma",
            "cell.tau_s",
            "geometry.plenum_volume_cm3",
            "geometry.free_membrane_area_mm2",
        ),
    }
    missing = []
    for path in prerequisite_paths[stage]:
        section_name, field_name = path.split(".", 1)
        parameter = getattr(getattr(config, section_name), field_name)
        if parameter.value is None or parameter.provenance not in {Provenance.MEASURED, Provenance.FITTED}:
            missing.append(path)
    if missing:
        raise ValueError(
            f"{stage} fit prerequisites must be measured or fitted before this stage: {missing}"
        )
    if stage == "window" and any(_experiment_area(config, manifest) <= 0 for manifest in manifests):
        raise ValueError("window fitting requires positive free membrane area")
    if stage == "window":
        for manifest in manifests:
            _require_measured_override(
                manifest,
                "free_membrane_area_mm2",
                "free_membrane_area_uncertainty_mm2",
                "free_membrane_area_provenance",
                "free_membrane_area_source",
            )
            _require_measured_override(
                manifest,
                "plenum_volume_cm3",
                "plenum_volume_uncertainty_cm3",
                "plenum_volume_provenance",
                "plenum_volume_source",
            )


def fit_stage(
    config: ModelConfig,
    manifests: Sequence[ExperimentManifest],
    stage: str,
    bootstrap_replicates: int = 200,
    seed: int = 431,
) -> FitResult:
    if not manifests:
        raise ValueError("at least one experiment manifest is required")
    _validate_stage_prerequisites(config, manifests, stage)
    datasets = [(manifest, load_experiment_frame(manifest)) for manifest in manifests]
    if stage in {"bare", "access", "window"}:
        for manifest, frame in datasets:
            _validate_pre_equilibration(config, manifest, frame, stage)
    if stage == "static":
        return _fit_static(config, datasets, bootstrap_replicates, seed)
    if stage == "thermal":
        return _fit_thermal(config, datasets, bootstrap_replicates, seed)
    if stage == "bare":
        return _fit_dynamic(config, datasets, "bare", bootstrap_replicates, seed)
    if stage == "access":
        return _fit_access(config, datasets, bootstrap_replicates, seed)
    if stage == "window":
        return _fit_window(config, datasets, bootstrap_replicates, seed)
    raise ValueError(f"unsupported fit stage {stage!r}")


def _fit_static(config, datasets, bootstrap, seed):
    if any("cell_current_mA" not in frame for _, frame in datasets):
        raise ValueError("static fitting requires cell_current_mA")
    plateau_groups = [_static_plateaus(manifest, frame) for manifest, frame in datasets]
    plateaus = [plateau for group in plateau_groups for plateau in group]
    temperatures = np.asarray([plateau["temp_c"] for plateau in plateaus])
    fit_alpha = len(np.unique(np.round(temperatures, 1))) >= 3
    names = ["cell.i_zero_ma", "cell.k_ref_ma"] + (["cell.temp_coeff_per_k"] if fit_alpha else [])
    initial = np.array([
        config.cell.i_zero_ma.value or 0.0,
        config.cell.k_ref_ma.value or 0.425,
        *([config.cell.temp_coeff_per_k.value or 0.0] if fit_alpha else []),
    ])
    lower = np.array([-0.2, 1e-6, *([-0.05] if fit_alpha else [])])
    upper = np.array([0.2, 10.0, *([0.05] if fit_alpha else [])])

    def objective(theta):
        working = config.model_copy(deep=True)
        _assign(working, names, theta)
        residuals = []
        for plateau in plateaus:
            predicted = static_signal(
                working,
                plateau["o2_pct"] / 100.0,
                plateau["pressure_kpa"],
                plateau["temp_c"],
            )
            residuals.append((predicted - plateau["current_ma"]) / plateau["sigma_ma"])
        return np.asarray(residuals)

    return _finish_fit(
        config,
        names,
        initial,
        lower,
        upper,
        objective,
        bootstrap,
        seed,
        {"fit_temperature_coefficient": fit_alpha},
        residual_group_lengths=[len(group) for group in plateau_groups],
    )


def _fit_thermal(config, datasets, bootstrap, seed):
    if any("heater_power_w" not in frame or "temp_block_c" not in frame for _, frame in datasets):
        raise ValueError("thermal fitting requires heater_power_w and temp_block_c")
    fit_eta = any("temp_membrane_c" in frame for _, frame in datasets)
    names = ["thermal.resistance_k_per_w", "thermal.capacitance_j_per_k"]
    if fit_eta:
        names.append("thermal.membrane_coupling")
    initial = np.array([20.0, 5.0, *([0.5] if fit_eta else [])])
    lower = np.array([0.05, 0.01, *([0.0] if fit_eta else [])])
    upper = np.array([500.0, 200.0, *([1.0] if fit_eta else [])])

    def objective(theta):
        working = config.model_copy(deep=True)
        _assign(working, names, theta)
        residuals = []
        for manifest, frame in datasets:
            trial = manifest.model_copy(update={"heater_mode": "prescribed_power"})
            prediction = simulate(working, trial, frame).frame
            residuals.extend(
                (prediction["temp_block_c"].to_numpy() - frame["temp_block_c"].to_numpy())
                / manifest.temperature_sigma_k
            )
            if fit_eta and "temp_membrane_c" in frame:
                eta = theta[-1]
                predicted_membrane = frame["temp_ambient_c"].to_numpy() + eta * (
                    prediction["temp_block_c"].to_numpy() - frame["temp_ambient_c"].to_numpy()
                )
                mask = _steady_mask(frame, manifest)
                residuals.extend(
                    (predicted_membrane[mask] - frame["temp_membrane_c"].to_numpy()[mask])
                    / manifest.membrane_temperature_sigma_k
                )
        return np.asarray(residuals)

    thermal_groups: list[int] = []
    for manifest, frame in datasets:
        thermal_groups.append(len(frame))
        if fit_eta and "temp_membrane_c" in frame:
            thermal_groups.append(int(_steady_mask(frame, manifest).sum()))
    return _finish_fit(
        config,
        names,
        initial,
        lower,
        upper,
        objective,
        bootstrap,
        seed,
        {"fit_membrane_coupling": fit_eta},
        residual_group_lengths=thermal_groups,
    )


def _fit_dynamic(config, datasets, kind, bootstrap, seed):
    names = ["cell.tau_s"] + [f"delay:{manifest.experiment_id}" for manifest, _ in datasets]
    initial = np.array([config.cell.tau_s.value or 4.0] + [manifest.input_delay_s for manifest, _ in datasets])
    lower = np.array([0.02] + [manifest.input_delay_bounds_s[0] for manifest, _ in datasets])
    upper = np.array([300.0] + [manifest.input_delay_bounds_s[1] for manifest, _ in datasets])

    def objective(theta):
        working = config.model_copy(deep=True)
        working.gas.access_enabled = False
        _set_parameter(working, "cell.tau_s", theta[0])
        residuals = []
        for index, (manifest, frame) in enumerate(datasets):
            trial = manifest.model_copy(update={"assembly_stage": kind, "input_delay_s": float(theta[index + 1])})
            prediction = simulate(working, trial, frame).frame
            residuals.extend(_observation_residual(manifest, frame, prediction))
        return np.concatenate(residuals)

    return _finish_fit(
        config,
        names,
        initial,
        lower,
        upper,
        objective,
        bootstrap,
        seed,
        {"dynamic_stage": kind},
        residual_group_lengths=[len(frame) for _, frame in datasets],
    )


def _fit_access(config, datasets, bootstrap, seed):
    calibration = [(m, f) for m, f in datasets if m.role == "calibration"]
    validation = [(m, f) for m, f in datasets if m.role == "validation"]
    if not calibration:
        raise ValueError("access fitting requires calibration experiments")
    initial = np.array([config.gas.access_tau_s.value or 2.0])
    lower, upper = np.array([0.01]), np.array([300.0])

    def residual_for(theta, selected, enabled=True):
        working = config.model_copy(deep=True)
        working.gas.access_enabled = enabled
        _set_parameter(working, "gas.access_tau_s", float(theta[0]) if enabled else 1.0)
        residuals = []
        for manifest, frame in selected:
            trial = manifest.model_copy(update={"assembly_stage": "carrier"})
            prediction = simulate(working, trial, frame).frame
            residuals.extend(_observation_residual(manifest, frame, prediction))
        return np.concatenate(residuals)

    def objective(theta):
        return residual_for(theta, calibration, True)

    fitted = _finish_fit(
        config,
        ["gas.access_tau_s"],
        initial,
        lower,
        upper,
        objective,
        bootstrap,
        seed,
        {"access_parameter_interpretation": "generic carrier lag; not an aperture-flow law"},
        residual_group_lengths=[len(frame) for _, frame in calibration],
    )
    best_tau = fitted.config.gas.access_tau_s.require("gas.access_tau_s")
    fitted.config.gas.access_enabled = True
    extended = residual_for(np.array([best_tau]), calibration, True)
    baseline = residual_for(np.array([1.0]), calibration, False)
    aicc_extended = _aicc(extended, 1)
    aicc_baseline = _aicc(baseline, 0)
    replicate_groups = [manifest.replicate_group for manifest, _ in calibration]
    replicate_requirement = any(
        group is not None and replicate_groups.count(group) >= 3
        for group in set(replicate_groups)
    )
    validation_improvement = None
    if validation:
        ext_val = residual_for(np.array([best_tau]), validation, True)
        base_val = residual_for(np.array([1.0]), validation, False)
        validation_improvement = 1.0 - np.sqrt(np.mean(ext_val**2)) / np.sqrt(np.mean(base_val**2))
    profile_low = fitted.report["profile_intervals"]["gas.access_tau_s"][0]
    promoted = bool(
        fitted.report["identifiable"] and
        fitted.report["bootstrap_interval_kind"] == "reportable" and
        replicate_requirement and profile_low > 0.01 and
        aicc_extended is not None and aicc_baseline is not None and
        aicc_extended <= aicc_baseline - 6.0 and
        validation_improvement is not None and validation_improvement >= 0.10
    )
    fitted.config.gas.access_enabled = promoted
    fitted.report.update({
        "aicc_baseline": aicc_baseline,
        "aicc_extended": aicc_extended,
        "validation_standardized_residual_rmse_improvement_fraction": validation_improvement,
        "replicate_requirement_met": replicate_requirement,
        "carrier_lag_model_promoted": promoted,
    })
    return fitted


def _fit_window(config, datasets, bootstrap, seed):
    areas = sorted({
        _experiment_area(config, manifest)
        for manifest, _ in datasets
    })
    names = [f"window_g:{area:g}" for area in areas]
    base_g = config.gas.window_conductance_mol_per_s.value or 1e-4
    initial = np.log(np.full(len(areas), base_g))
    lower = np.log(np.full(len(areas), 1e-9))
    upper = np.log(np.full(len(areas), 1e-1))
    area_index = {area: index for index, area in enumerate(areas)}

    def objective(log_g):
        residuals = []
        for manifest, frame in datasets:
            area = _experiment_area(config, manifest)
            working = config.model_copy(deep=True)
            working.gas.area_model = "fixed_conductance"
            _set_parameter(working, "gas.window_conductance_mol_per_s", float(np.exp(log_g[area_index[area]])))
            trial = manifest.model_copy(update={"assembly_stage": "window", "free_membrane_area_mm2": None})
            prediction = simulate(working, trial, frame).frame
            residuals.extend(_observation_residual(manifest, frame, prediction))
        return np.concatenate(residuals)

    raw = _finish_fit(
        config,
        names,
        initial,
        lower,
        upper,
        objective,
        bootstrap,
        seed,
        {},
        transform=np.exp,
        residual_group_lengths=[len(frame) for _, frame in datasets],
    )
    # The well-mixed complete-assembly fit may absorb unresolved axial delay.
    # Mark its scope so it cannot later be added in series with that delay.
    raw.config.gas.conductance_scope = "complete_assembly_lumped"
    conductances = {str(area): float(raw.report["best_values"][name]) for area, name in zip(areas, names)}
    nominal_area = config.geometry.free_membrane_area_mm2.require("geometry.free_membrane_area_mm2")
    nominal_matches = [area for area in areas if np.isclose(area, nominal_area, rtol=0.0, atol=1e-6)]
    raw.config.gas.area_model = "fixed_conductance"
    area_law = None
    area_law_promoted = False
    intervals = raw.report["bootstrap_intervals_95pct"]
    uncertainty_available = raw.report["bootstrap_interval_kind"] == "reportable" and all(
        name in intervals for name in names
    )
    if len(areas) >= 5 and uncertainty_available:
        area_m2 = np.asarray(areas) * 1e-6
        observed_g = np.asarray([conductances[str(area)] for area in areas])
        log_observed = np.log(observed_g)
        log_sigma = np.asarray([
            max((np.log(intervals[name][1]) - np.log(intervals[name][0])) / 3.92, 1e-6)
            for name in names
        ])
        area_only = least_squares(
            lambda theta: (np.log(area_m2 * np.exp(theta[0])) - log_observed) / log_sigma,
            np.array([np.log(max(float(np.median(observed_g / area_m2)), 1e-12))]),
            max_nfev=500,
        )
        law = least_squares(
            lambda theta: (
                np.log(1.0 / (1.0 / (area_m2 * np.exp(theta[0])) + np.exp(theta[1])))
                - log_observed
            ) / log_sigma,
            np.log([
                max(float(np.median(observed_g / area_m2)), 1e-12),
                max(
                    float(
                        1.0 / np.max(observed_g)
                        - 1.0 / (np.max(area_m2) * np.median(observed_g / area_m2))
                    ),
                    1e-12,
                ),
            ]),
            max_nfev=500,
        )
        k_area, resistance = np.exp(law.x)
        area_residual = law.fun
        predicted_log_g = np.log(
            1.0 / (1.0 / (area_m2 * k_area) + resistance)
        )
        rms_log_residual = float(np.sqrt(np.mean((predicted_log_g - log_observed) ** 2)))
        area_only_aicc = _aicc(area_only.fun, 1)
        area_access_aicc = _aicc(area_residual, 2)
        singular = np.linalg.svd(law.jac, compute_uv=False)
        condition = float(singular[0] / singular[-1]) if len(singular) >= 2 and singular[-1] > 0 else None
        area_law_promoted = bool(
            raw.report["identifiable"]
            and law.success
            and condition is not None
            and condition <= 1e8
            and area_only_aicc is not None
            and area_access_aicc is not None
            and area_access_aicc <= area_only_aicc - 6.0
            and rms_log_residual <= 0.25
        )
        area_law = {
            "area_conductance_mol_per_s_m2": float(k_area),
            "access_resistance_s_per_mol": float(resistance),
            "optimizer_success": bool(law.success),
            "jacobian_condition_number": condition,
            "rms_log_residual": rms_log_residual,
            "aicc_area_only": area_only_aicc,
            "aicc_area_plus_access": area_access_aicc,
        }
        if area_law_promoted:
            raw.config.gas.area_model = "area_plus_access"
            _set_parameter(raw.config, "gas.area_conductance_mol_per_s_m2", k_area)
            _set_parameter(raw.config, "gas.access_resistance_s_per_mol", resistance)
            nominal_g = 1.0 / (1.0 / (nominal_area * 1e-6 * k_area) + resistance)
            _set_parameter(raw.config, "gas.window_conductance_mol_per_s", nominal_g)
    if not area_law_promoted and nominal_matches:
        nominal_g = conductances[str(nominal_matches[0])]
        _set_parameter(raw.config, "gas.window_conductance_mol_per_s", nominal_g)
    nominal_covered = bool(nominal_matches or area_law_promoted)
    if not nominal_covered:
        raw.report["identifiable"] = False
    raw.report["conductance_by_area_mm2"] = conductances
    raw.report["area_access_law"] = area_law
    raw.report["area_access_law_promoted"] = area_law_promoted
    raw.report["area_access_law_minimum_unique_areas"] = 5
    raw.report["area_access_law_requires_reportable_conductance_intervals"] = True
    raw.report["nominal_geometry_covered"] = nominal_covered
    return raw


def _finish_fit(
    config,
    names,
    initial,
    lower,
    upper,
    objective,
    bootstrap,
    seed,
    extra,
    transform=None,
    residual_group_lengths=None,
):
    solution = least_squares(objective, initial, bounds=(lower, upper), loss="linear", max_nfev=600)
    residual = objective(solution.x)
    jacobian = solution.jac
    scales = np.maximum.reduce([
        np.abs(solution.x),
        0.01 * (upper - lower),
        np.full_like(solution.x, 1e-12),
    ])
    singular = np.linalg.svd(jacobian * scales, compute_uv=False) if jacobian.size else np.array([])
    threshold = max(
        singular[0] * max(jacobian.shape) * np.finfo(float).eps,
        singular[0] / 1e8,
    ) if len(singular) else 0.0
    rank = int(np.sum(singular > threshold)) if len(singular) else 0
    bounds_hit = [
        name
        for name, value, lo, hi in zip(names, solution.x, lower, upper)
        if _value_hits_bound(value, lo, hi)
    ]
    linear_cost = 0.5 * float(np.sum(residual**2))
    profile = _profile_intervals(objective, solution.x, lower, upper, names, linear_cost)
    samples, failed, invalid_bootstrap = _bootstrap(
        objective,
        solution.x,
        lower,
        upper,
        residual,
        bootstrap,
        seed,
        residual_group_lengths,
    )
    final_values = transform(solution.x) if transform is not None else solution.x
    intervals = {}
    if len(samples):
        transformed_samples = transform(samples) if transform is not None else samples
        for index, name in enumerate(names):
            intervals[name] = np.percentile(transformed_samples[:, index], [2.5, 97.5]).tolist()
    working = config.model_copy(deep=True)
    for name, value in zip(names, final_values):
        if ":" not in name and not name.startswith("delay:"):
            _set_parameter(working, name, float(value))
    condition = float(singular[0] / singular[-1]) if len(singular) and singular[-1] > 0 else None
    profile_bounds_hit = []
    wide_profiles = []
    profile_width_over_scale = {}
    for index, name in enumerate(names):
        low, high = profile[name]
        if _value_hits_bound(low, lower[index], upper[index]) or _value_hits_bound(
            high, lower[index], upper[index]
        ):
            profile_bounds_hit.append(name)
        normalized_width = (high - low) / scales[index]
        profile_width_over_scale[name] = float(normalized_width)
        if normalized_width > 1.0:
            wide_profiles.append(name)
    minimum_scaled_information = float(singular[-1]) if len(singular) else 0.0
    identifiable = bool(
        solution.success
        and rank == len(names)
        and not bounds_hit
        and condition is not None
        and condition <= 1e8
        and minimum_scaled_information >= 1.0
        and not profile_bounds_hit
        and not wide_profiles
    )
    bootstrap_kind = "reportable" if len(samples) >= 1000 else "quick_diagnostic"
    report = {
        "success": bool(solution.success),
        "message": solution.message,
        "fit_loss": "linear_gaussian",
        "cost": float(solution.cost),
        "linear_cost": linear_cost,
        "n_residuals": len(residual),
        "parameter_names": names,
        "best_values": {name: float(value) for name, value in zip(names, final_values)},
        "scaled_jacobian_rank": rank,
        "scaled_jacobian_singular_values": singular.tolist(),
        "scaled_jacobian_condition_number": condition,
        "identifiability_condition_limit": 1e8,
        "minimum_scaled_information": minimum_scaled_information,
        "minimum_scaled_information_limit": 1.0,
        "bounds_hit": bounds_hit,
        "profile_bounds_hit": profile_bounds_hit,
        "profile_too_wide": wide_profiles,
        "profile_width_over_parameter_scale": profile_width_over_scale,
        "profile_width_over_parameter_scale_limit": 1.0,
        "identifiable": identifiable,
        "profile_intervals": {
            name: (transform(np.asarray(bounds)).tolist() if transform is not None else bounds)
            for name, bounds in profile.items()
        },
        "bootstrap_replicates_requested": bootstrap,
        "bootstrap_replicates_successful": int(len(samples)),
        "bootstrap_replicates_failed": failed,
        "bootstrap_replicates_rejected_bound_or_unidentifiable": invalid_bootstrap,
        "bootstrap_interval_kind": bootstrap_kind,
        "bootstrap_intervals_95pct": intervals,
        **extra,
    }
    return FitResult(working, report)


def _profile_intervals(objective, optimum, lower, upper, names, minimum_cost):
    result = {}
    for fixed_index, name in enumerate(names):
        low = _profile_bound(
            objective, optimum, lower, upper, fixed_index, minimum_cost + 1.92, -1.0
        )
        high = _profile_bound(
            objective, optimum, lower, upper, fixed_index, minimum_cost + 1.92, 1.0
        )
        result[name] = [low, high]
    return result


def _profile_bound(objective, optimum, lower, upper, fixed_index, cutoff, direction):
    free_indices = [index for index in range(len(optimum)) if index != fixed_index]

    def cost_at(value):
        if free_indices:
            def reduced(free):
                theta = optimum.copy()
                theta[fixed_index] = value
                theta[free_indices] = free
                return objective(theta)

            attempt = least_squares(
                reduced,
                optimum[free_indices],
                bounds=(lower[free_indices], upper[free_indices]),
                loss="linear",
                max_nfev=200,
            )
            return 0.5 * float(np.sum(reduced(attempt.x) ** 2))
        theta = optimum.copy()
        theta[fixed_index] = value
        return 0.5 * float(np.sum(objective(theta) ** 2))

    bound = lower[fixed_index] if direction < 0 else upper[fixed_index]
    span = upper[fixed_index] - lower[fixed_index]
    accepted = float(optimum[fixed_index])
    step = max(0.01 * span, np.finfo(float).eps * max(abs(accepted), 1.0))
    rejected = None
    while not np.isclose(accepted, bound):
        candidate = float(np.clip(accepted + direction * step, lower[fixed_index], upper[fixed_index]))
        if cost_at(candidate) <= cutoff:
            accepted = candidate
            if candidate == bound:
                return candidate
            step *= 1.8
        else:
            rejected = candidate
            break
    if rejected is None:
        return accepted
    inside, outside = accepted, rejected
    for _ in range(14):
        midpoint = 0.5 * (inside + outside)
        if cost_at(midpoint) <= cutoff:
            inside = midpoint
        else:
            outside = midpoint
    return float(inside)


def _bootstrap(objective, optimum, lower, upper, residual, replicates, seed, group_lengths):
    if replicates <= 0 or not len(residual):
        return np.empty((0, len(optimum))), 0, 0
    rng = np.random.default_rng(seed)
    groups = _residual_groups(residual - np.mean(residual), group_lengths)
    samples = []
    failed = 0
    invalid = 0
    for _ in range(replicates):
        sampled_groups = []
        for group in groups:
            block = _autocorrelation_block_length(group)
            sampled_groups.append(_moving_block_sample(group, block, rng))
        sampled = np.concatenate(sampled_groups)
        try:
            attempt = least_squares(
                lambda theta: objective(theta) - residual + sampled,
                optimum, bounds=(lower, upper), loss="linear", max_nfev=250,
            )
            if attempt.success:
                scales = np.maximum.reduce([
                    np.abs(attempt.x),
                    0.01 * (upper - lower),
                    np.full_like(attempt.x, 1e-12),
                ])
                singular = np.linalg.svd(attempt.jac * scales, compute_uv=False)
                condition = (
                    float(singular[0] / singular[-1])
                    if len(singular) and singular[-1] > 0
                    else float("inf")
                )
                hits_bound = any(
                    _value_hits_bound(value, lo, hi)
                    for value, lo, hi in zip(attempt.x, lower, upper)
                )
                if hits_bound or not len(singular) or singular[-1] < 1.0 or condition > 1e8:
                    invalid += 1
                else:
                    samples.append(attempt.x)
            else:
                failed += 1
        except Exception:
            failed += 1
    return np.asarray(samples), failed, invalid


def _value_hits_bound(value: float, lower: float, upper: float) -> bool:
    tolerance = max(1e-8 * (upper - lower), 1e-12)
    return value <= lower + tolerance or value >= upper - tolerance


def _residual_groups(residual, group_lengths):
    if group_lengths is None:
        return [residual]
    if any(length <= 0 for length in group_lengths) or sum(group_lengths) != len(residual):
        raise ValueError("residual group lengths must be positive and cover all residuals")
    groups = []
    start = 0
    for length in group_lengths:
        groups.append(residual[start:start + length])
        start += length
    return groups


def _autocorrelation_block_length(residual):
    centered = residual - np.mean(residual)
    variance = np.dot(centered, centered)
    if variance <= 0:
        return 1
    for lag in range(1, min(len(residual) // 2, 100)):
        correlation = np.dot(centered[:-lag], centered[lag:]) / variance
        if correlation <= np.exp(-1):
            return max(lag, 1)
    return max(1, min(len(residual) // 10, 20))


def _moving_block_sample(residual, block, rng):
    output = []
    while len(output) < len(residual):
        start = int(rng.integers(0, max(len(residual) - block + 1, 1)))
        output.extend(residual[start:start + block])
    return np.asarray(output[:len(residual)])


def _observation_residual(
    manifest: ExperimentManifest,
    observed: pd.DataFrame,
    predicted: pd.DataFrame,
) -> list[np.ndarray]:
    if "cell_current_mA" in observed:
        return [
            (predicted["cell_current_mA"].to_numpy() - observed["cell_current_mA"].to_numpy())
            / manifest.current_sigma_mA
        ]
    return [
        (predicted["o2_probe_pct_wet"].to_numpy() - observed["o2_probe_pct"].to_numpy())
        / manifest.o2_sigma_pct
    ]


def _steady_mask(frame: pd.DataFrame, manifest: ExperimentManifest) -> np.ndarray:
    mask = np.zeros(len(frame), dtype=bool)
    for window in manifest.step_windows:
        mask |= (frame.time_s >= window.steady_start_s) & (frame.time_s <= window.steady_end_s)
    return mask if mask.any() else np.ones(len(frame), dtype=bool)


def _experiment_area(config: ModelConfig, manifest: ExperimentManifest) -> float:
    if manifest.free_membrane_area_mm2 is not None:
        return float(manifest.free_membrane_area_mm2)
    return config.geometry.free_membrane_area_mm2.require("geometry.free_membrane_area_mm2")


def _assign(config: ModelConfig, names: list[str], values: np.ndarray) -> None:
    for name, value in zip(names, values):
        _set_parameter(config, name, float(value))


def _set_parameter(config: ModelConfig, path: str, value: float) -> None:
    section_name, field_name = path.split(".", 1)
    parameter = getattr(getattr(config, section_name), field_name)
    parameter.value = float(value)
    parameter.provenance = Provenance.FITTED
    parameter.source = "fitted by o2-lumped"


def _aicc(residual: np.ndarray, parameters: int) -> float | None:
    n = len(residual)
    if n <= parameters + 1:
        return None
    rss = max(float(np.sum(residual**2)), np.finfo(float).tiny)
    aic = n * np.log(rss / n) + 2 * parameters
    correction = 2 * parameters * (parameters + 1) / (n - parameters - 1)
    return float(aic + correction)
