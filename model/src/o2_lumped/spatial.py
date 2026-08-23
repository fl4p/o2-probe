from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from .config import ExperimentManifest, ModelConfig, Provenance
from .physics import (
    InputSeries,
    R_GAS,
    SimulationResult,
    _cell_consumption,
    _current_from_state,
    _equivalent_fraction,
    _temperature_adjusted_k,
    _resolve_window_conductance,
    inverse_signal,
)


@dataclass(frozen=True)
class AxialDomain:
    """One-dimensional finite-volume gas path from membrane to potted end."""

    length_mm: float
    sensor_distance_from_membrane_mm: float
    effective_diffusivity_m2_s: float
    nodes: int = 41
    diffusivity_provenance: Literal[
        "measured", "fitted", "assumed", "sensitivity_only"
    ] = "sensitivity_only"
    diffusivity_source: str = "unmeasured axial effective-diffusivity sensitivity"

    def validate(self) -> None:
        values = (
            self.length_mm,
            self.sensor_distance_from_membrane_mm,
            self.effective_diffusivity_m2_s,
        )
        if not all(np.isfinite(value) and value > 0 for value in values):
            raise ValueError("axial length, sensor distance, and diffusivity must be finite and positive")
        if self.sensor_distance_from_membrane_mm > self.length_mm:
            raise ValueError("sensor distance cannot exceed axial domain length")
        if not isinstance(self.nodes, int) or isinstance(self.nodes, bool) or self.nodes < 5:
            raise ValueError("axial domain requires at least five finite volumes")
        if self.diffusivity_provenance not in {
            "measured", "fitted", "assumed", "sensitivity_only"
        }:
            raise ValueError("invalid axial diffusivity provenance")
        if not self.diffusivity_source.strip():
            raise ValueError("axial diffusivity source must be declared")


def simulate_axial_diffusion(
    config: ModelConfig,
    manifest: ExperimentManifest,
    inputs: pd.DataFrame,
    domain: AxialDomain,
) -> SimulationResult:
    """Simulate axial molecular/effective diffusion without heater-driven flow.

    Pressure and inlet temperature must remain constant. The membrane is a
    Robin boundary at x=0, the potting wall is no-flux at x=L, and the sensor
    reads the finite volume containing its measured axial datum.
    """
    domain.validate()
    if manifest.assembly_stage not in {"window", "validation"}:
        raise ValueError("axial diffusion model applies to the enclosed window assembly")
    if config.gas.conductance_scope != "intrinsic_window":
        raise ValueError(
            "axial diffusion requires intrinsic_window conductance; a complete-assembly "
            "lumped fit may already contain axial resistance"
        )
    times = inputs["time_s"].to_numpy(dtype=float)
    if len(times) < 2 or not np.all(np.diff(times) > 0):
        raise ValueError("strictly increasing time samples are required")
    pressure_values = inputs["pressure_reference_kpa"].to_numpy(dtype=float)
    inlet_column = "temp_inlet_c" if "temp_inlet_c" in inputs else "temp_ambient_c"
    temperature_values = inputs[inlet_column].to_numpy(dtype=float)
    if not np.all(np.isfinite(pressure_values)) or np.any(pressure_values <= 0.0):
        raise ValueError("positive finite pressure is required")
    if not np.all(np.isfinite(temperature_values)) or np.any(temperature_values <= -273.15):
        raise ValueError("positive finite absolute temperature is required")
    if np.ptp(pressure_values) > 1e-9 or np.ptp(temperature_values) > 1e-9:
        raise ValueError("axial V1 requires constant pressure and inlet temperature")
    if "heater_power_w" in inputs and np.max(np.abs(inputs["heater_power_w"])) > 1e-12:
        raise ValueError("axial V1 is heater-off; no uncalibrated convection law is available")

    pressure_kpa = float(pressure_values[0])
    temp_c = float(temperature_values[0])
    temp_k = temp_c + 273.15
    volume_cm3 = (
        manifest.plenum_volume_cm3
        if manifest.plenum_volume_cm3 is not None
        else config.geometry.plenum_volume_cm3.require("geometry.plenum_volume_cm3")
    )
    volume_m3 = volume_cm3 * 1e-6
    length_m = domain.length_mm * 1e-3
    dx = length_m / domain.nodes
    cross_section_m2 = volume_m3 / length_m
    gas_molar_density = pressure_kpa * 1000.0 / (R_GAS * temp_k)
    node_capacity_mol = gas_molar_density * cross_section_m2 * dx
    internal_conductance = (
        domain.effective_diffusivity_m2_s * gas_molar_density * cross_section_m2 / dx
    )
    window_conductance = _resolve_window_conductance(config, manifest)
    regime_name = manifest.regime or config.active_regime
    if regime_name not in config.regimes:
        raise ValueError(f"unknown regime {regime_name!r}")
    regime = config.regimes[regime_name].conductance_multiplier
    if regime_name != "dry" and (
        regime.value is None
        or regime.provenance in {Provenance.ASSUMED, Provenance.SENSITIVITY_ONLY}
    ):
        raise ValueError(f"regime {regime_name!r} must be measured or fitted before simulation")
    multiplier = regime.require(
        f"regimes.{regime_name}.conductance_multiplier"
    )
    window_conductance *= multiplier
    half_cell_conductance = (
        domain.effective_diffusivity_m2_s
        * gas_molar_density
        * cross_section_m2
        / (0.5 * dx)
    )
    boundary_conductance = (
        0.0
        if window_conductance <= 0.0
        else 1.0 / (1.0 / window_conductance + 1.0 / half_cell_conductance)
    )
    sensor_index = min(
        int(domain.sensor_distance_from_membrane_mm / domain.length_mm * domain.nodes),
        domain.nodes - 1,
    )
    node_centres_mm = (np.arange(domain.nodes) + 0.5) * domain.length_mm / domain.nodes

    series = InputSeries(inputs, manifest.input_delay_s)
    reference = inputs["o2_reference_pct_wet"].to_numpy(dtype=float) / 100.0

    def external_fraction(t: float) -> float:
        return series.linear("o2_reference_pct_wet", t) / 100.0

    initial_fraction = external_fraction(float(times[0]))
    if config.gas.include_cell_consumption and initial_fraction > 1e-12:
        raise ValueError(
            "axial V1 with cell consumption requires a zero-O2 initial condition; "
            "nonzero initialization needs a spatial steady-state solve"
        )
    if config.cell.dynamic_domain == "normalized_output":
        initial_drive = -np.log1p(
            -_equivalent_fraction(config, initial_fraction, pressure_kpa, strict=True)
        )
    else:
        initial_drive = initial_fraction
    initial = np.concatenate([
        np.full(domain.nodes, initial_fraction, dtype=float),
        np.array([initial_drive], dtype=float),
    ])
    tau_cell = config.cell.tau_s.require("cell.tau_s")

    def derivative(t: float, state: np.ndarray) -> np.ndarray:
        fractions = state[:domain.nodes]
        cell_state = float(state[-1])
        rates = np.zeros(domain.nodes, dtype=float)
        membrane_flux = boundary_conductance * (external_fraction(t) - fractions[0])
        rates[0] += membrane_flux / node_capacity_mol
        interface_flux = internal_conductance * (fractions[:-1] - fractions[1:])
        rates[:-1] -= interface_flux / node_capacity_mol
        rates[1:] += interface_flux / node_capacity_mol

        if config.gas.include_cell_consumption:
            current = _current_from_state(config, cell_state, pressure_kpa, temp_c)
            sink, _, _ = _cell_consumption(
                config,
                current,
                max(fractions[sensor_index], 0.0) * node_capacity_mol,
            )
            rates[sensor_index] -= sink / node_capacity_mol
            if fractions[sensor_index] <= 0.0 and rates[sensor_index] < 0.0:
                rates[sensor_index] = 0.0

        sensor_fraction = float(np.clip(fractions[sensor_index], 0.0, 1.0))
        if config.cell.dynamic_domain == "normalized_output":
            drive = -np.log1p(
                -_equivalent_fraction(config, sensor_fraction, pressure_kpa, strict=False)
            )
        else:
            drive = sensor_fraction
        return np.concatenate([rates, np.array([(drive - cell_state) / tau_cell])])

    solution = solve_ivp(
        derivative,
        (float(times[0]), float(times[-1])),
        initial,
        t_eval=times,
        method="BDF",
        rtol=config.solver.rtol,
        atol=config.solver.atol,
        max_step=config.solver.max_step_s,
    )
    if not solution.success:
        raise RuntimeError(solution.message)

    fractions = np.clip(solution.y[:domain.nodes, :], 0.0, 1.0)
    cell_states = solution.y[-1, :]
    sensor_fraction = fractions[sensor_index, :]
    currents = np.asarray([
        _current_from_state(config, state, pressure_kpa, temp_c) for state in cell_states
    ])
    oxygen = np.asarray([
        inverse_signal(
            config,
            max(current, config.cell.i_zero_ma.require("cell.i_zero_ma")),
            pressure_kpa,
            temp_c,
        )
        * 100.0
        for current in currents
    ])
    k_t = _temperature_adjusted_k(config, temp_c)
    equivalent_reference = (
        1.0
        - np.exp(
            -(currents - config.cell.i_zero_ma.require("cell.i_zero_ma")) / k_t
        )
    ) * 100.0
    frame = pd.DataFrame({
        "time_s": times,
        "o2_reference_pct_wet": reference * 100.0,
        "o2_membrane_side_node_pct_wet": fractions[0, :] * 100.0,
        "o2_sensor_location_pct_wet": sensor_fraction * 100.0,
        "o2_rear_wall_node_pct_wet": fractions[-1, :] * 100.0,
        "o2_plenum_pct_wet": np.mean(fractions, axis=0) * 100.0,
        "o2_access_pct_wet": sensor_fraction * 100.0,
        "o2_probe_pct_wet": oxygen,
        "o2_probe_pressure_compensated_pct_wet": oxygen,
        "o2_probe_equivalent_pct_at_reference_pressure": equivalent_reference,
        "cell_current_mA": currents,
        "pressure_reference_kpa": pressure_kpa,
        "temp_ambient_c": inputs["temp_ambient_c"].to_numpy(dtype=float),
        "temp_inlet_c": temperature_values,
        "rh_ambient_pct": (
            inputs["rh_ambient_pct"].to_numpy(dtype=float)
            if "rh_ambient_pct" in inputs
            else np.full(len(times), np.nan)
        ),
        "temp_block_c": temp_c,
        "temp_membrane_qs_c": np.nan,
        "rh_membrane_qs_pct": np.nan,
        "dew_margin_qs_k": np.nan,
        "thermal_rate_k_per_s": np.nan,
        "thermal_settled": False,
        "heater_command_w": 0.0,
        "heater_applied_w": 0.0,
    })
    return SimulationResult(frame, {
        "success": True,
        "transport_model": "axial_finite_volume_diffusion",
        "axial_nodes": domain.nodes,
        "axial_length_mm": domain.length_mm,
        "sensor_distance_from_membrane_mm": domain.sensor_distance_from_membrane_mm,
        "sensor_node_index": sensor_index,
        "sensor_node_centre_mm": float(node_centres_mm[sensor_index]),
        "effective_axial_diffusivity_m2_s": domain.effective_diffusivity_m2_s,
        "effective_cross_section_mm2": cross_section_m2 * 1e6,
        "window_conductance_mol_per_s": window_conductance,
        "boundary_conductance_with_half_cell_mol_per_s": boundary_conductance,
        "heater_convection_modeled": False,
        "input_delay_s": manifest.input_delay_s,
        "effective_axial_diffusivity_provenance": domain.diffusivity_provenance,
        "effective_axial_diffusivity_source": domain.diffusivity_source,
        "uncalibrated": (
            config.is_uncalibrated
            or domain.diffusivity_provenance in {"assumed", "sensitivity_only"}
        ),
    })
