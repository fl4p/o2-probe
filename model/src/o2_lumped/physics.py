from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .config import ExperimentManifest, ModelConfig, Provenance
from .psychrometrics import dew_point_c, local_rh_pct

R_GAS = 8.314462618
FARADAY = 96485.33212


@dataclass
class SimulationResult:
    frame: pd.DataFrame
    diagnostics: dict[str, object]


class InputSeries:
    def __init__(self, frame: pd.DataFrame, delay_s: float = 0.0):
        self.frame = frame
        self.t = frame["time_s"].to_numpy(dtype=float)
        self.delay_s = delay_s

    def linear(self, column: str, t: float, default: float | None = None) -> float:
        if column not in self.frame:
            if default is None:
                raise KeyError(column)
            return default
        query = t - self.delay_s if column == "o2_reference_pct_wet" else t
        return float(np.interp(query, self.t, self.frame[column].to_numpy(dtype=float)))

    def hold(self, column: str, t: float, default: float = 0.0) -> float:
        if column not in self.frame:
            return default
        index = int(np.searchsorted(self.t, t, side="right") - 1)
        index = min(max(index, 0), len(self.t) - 1)
        return float(self.frame[column].iloc[index])

    def slope(self, column: str, t: float, default_column: str | None = None) -> float:
        if column not in self.frame:
            if default_column is None:
                return 0.0
            return self.slope(default_column, t)
        values = self.frame[column].to_numpy(dtype=float)
        if len(values) < 2:
            return 0.0
        index = int(np.searchsorted(self.t, t, side="right") - 1)
        index = min(max(index, 0), len(self.t) - 2)
        dt = self.t[index + 1] - self.t[index]
        return float((values[index + 1] - values[index]) / dt)


def static_signal(config: ModelConfig, oxygen_fraction: float, pressure_kpa: float, temp_c: float) -> float:
    i0 = config.cell.i_zero_ma.require("cell.i_zero_ma")
    k_t = _temperature_adjusted_k(config, temp_c)
    equivalent = _equivalent_fraction(config, oxygen_fraction, pressure_kpa, strict=True)
    return i0 + k_t * (-np.log1p(-equivalent))


def inverse_signal(config: ModelConfig, current_ma: float, pressure_kpa: float, temp_c: float) -> float:
    i0 = config.cell.i_zero_ma.require("cell.i_zero_ma")
    k_t = _temperature_adjusted_k(config, temp_c)
    if current_ma < i0:
        raise ValueError("cell current below I0 is outside the calibrated inverse domain")
    equivalent = 1.0 - np.exp(-(current_ma - i0) / k_t)
    oxygen_fraction = float(equivalent * config.cell.reference_pressure_kpa / pressure_kpa)
    if not 0.0 <= oxygen_fraction <= 1.0:
        raise ValueError("inverse SGX transform produced a nonphysical oxygen fraction")
    return oxygen_fraction


def simulate(config: ModelConfig, manifest: ExperimentManifest, inputs: pd.DataFrame) -> SimulationResult:
    series = InputSeries(inputs, manifest.input_delay_s)
    times = inputs["time_s"].to_numpy(dtype=float)
    regime_name = manifest.regime or config.active_regime
    if regime_name not in config.regimes:
        raise ValueError(f"unknown regime {regime_name!r}")
    regime = config.regimes[regime_name].conductance_multiplier
    if regime_name != "dry" and (
        regime.value is None
        or regime.provenance in {Provenance.ASSUMED, Provenance.SENSITIVITY_ONLY}
    ):
        raise ValueError(f"regime {regime_name!r} must be measured or fitted before simulation")
    multiplier = regime.require(f"regimes.{regime_name}.conductance_multiplier")

    volume_cm3 = (
        manifest.plenum_volume_cm3
        if manifest.plenum_volume_cm3 is not None
        else config.geometry.plenum_volume_cm3.require("geometry.plenum_volume_cm3")
    )
    volume_m3 = volume_cm3 * 1e-6
    if volume_m3 <= 0:
        raise ValueError("plenum volume must be positive")
    direct_exposure = manifest.assembly_stage in {"static", "thermal", "bare", "carrier"}
    conductance = 0.0 if direct_exposure else _resolve_window_conductance(config, manifest) * multiplier
    tau_cell = config.cell.tau_s.require("cell.tau_s")
    if tau_cell <= 0:
        raise ValueError("cell tau must be positive")
    access_enabled = config.gas.access_enabled
    tau_access = config.gas.access_tau_s.value if access_enabled else None
    if access_enabled and (tau_access is None or tau_access <= 0):
        raise ValueError("enabled access lag requires positive gas.access_tau_s")

    thermal_available = config.thermal.resistance_k_per_w.value is not None and config.thermal.capacitance_j_per_k.value is not None
    if manifest.heater_mode == "delta_t_pi":
        if not thermal_available:
            raise ValueError("delta_t_pi requires thermal resistance and capacitance")
        if config.controller.kp_w_per_k is None or config.controller.ki_w_per_k_s is None:
            raise ValueError("delta_t_pi requires explicit nonnegative Kp and Ki")
        for name, parameter in (
            ("thermal.resistance_k_per_w", config.thermal.resistance_k_per_w),
            ("thermal.capacitance_j_per_k", config.thermal.capacitance_j_per_k),
        ):
            if parameter.provenance not in {Provenance.MEASURED, Provenance.FITTED}:
                raise ValueError(f"delta_t_pi requires {name} with measured or fitted provenance")
    if "heater_power_w" in inputs and (inputs["heater_power_w"] > config.controller.max_power_w).any():
        raise ValueError("prescribed heater_power_w exceeds controller.max_power_w")

    t0 = times[0]
    ambient0 = series.linear("temp_ambient_c", t0)
    pressure0 = series.linear("pressure_reference_kpa", t0)
    inlet0 = series.linear("temp_inlet_c", t0, ambient0)
    external0 = series.linear("o2_reference_pct_wet", t0) / 100.0
    block0 = float(inputs["temp_block_c"].iloc[0]) if "temp_block_c" in inputs else ambient0
    total0 = _total_moles(pressure0, inlet0, volume_m3)
    plenum0 = (
        external0
        if direct_exposure
        else _steady_initial_oxygen_fraction(
            config, external0, pressure0, block0, total0, conductance
        )
    )
    access0 = plenum0
    if config.cell.dynamic_domain == "normalized_output":
        drive0 = -np.log1p(-_equivalent_fraction(config, access0, pressure0, strict=True))
    else:
        drive0 = access0
    state = [block0, plenum0 * total0]
    if access_enabled:
        state.append(access0)
    state.append(float(drive0))

    integral = 0.0
    controller_power = 0.0
    next_tick = t0
    controller_ticks = 0
    rows: list[dict[str, float | bool]] = []
    domain_clips = 0

    def derivative(t: float, y: np.ndarray, power_w: float) -> np.ndarray:
        nonlocal domain_clips
        temp_block, oxygen_moles = float(y[0]), float(y[1])
        temp_ambient = series.linear("temp_ambient_c", t)
        temp_inlet = series.linear("temp_inlet_c", t, temp_ambient)
        pressure_kpa = series.linear("pressure_reference_kpa", t)
        total_moles = _total_moles(pressure_kpa, temp_inlet, volume_m3)
        total_moles_rate = _total_moles_rate(
            pressure_kpa,
            series.slope("pressure_reference_kpa", t),
            temp_inlet,
            series.slope("temp_inlet_c", t, default_column="temp_ambient_c"),
            volume_m3,
        )
        external = series.linear("o2_reference_pct_wet", t) / 100.0
        x_plenum = external if direct_exposure else max(oxygen_moles, 0.0) / total_moles
        index = 2
        if access_enabled:
            x_access = float(y[index])
            index += 1
        else:
            x_access = x_plenum
        cell_state = float(y[index])
        if thermal_available:
            rth = config.thermal.resistance_k_per_w.require("thermal.resistance_k_per_w")
            cth = config.thermal.capacitance_j_per_k.require("thermal.capacitance_j_per_k")
            applied_power = power_w if temp_block < config.controller.max_block_temp_c else 0.0
            dtemp = (applied_power - (temp_block - temp_ambient) / rth) / cth
        else:
            dtemp = series.slope("temp_block_c", t, default_column="temp_ambient_c")
        consumption = 0.0
        if config.gas.include_cell_consumption:
            current_ma = _current_from_state(config, cell_state, pressure_kpa, temp_block)
            consumption, _, _ = _cell_consumption(config, current_ma, oxygen_moles)
        # The p/T inputs define total plenum inventory. Rising inventory uses
        # external-composition make-up gas; falling inventory expels plenum gas.
        breathing_o2 = (external if total_moles_rate >= 0.0 else x_plenum) * total_moles_rate
        dn_oxygen = (
            0.0
            if direct_exposure
            else breathing_o2 + conductance * (external - x_plenum) - consumption
        )
        if oxygen_moles <= 0.0 and dn_oxygen < 0.0:
            dn_oxygen = 0.0
        result = [dtemp, dn_oxygen]
        if access_enabled:
            result.append((x_plenum - x_access) / float(tau_access))
        if config.cell.dynamic_domain == "normalized_output":
            raw_equivalent = x_access * pressure_kpa / config.cell.reference_pressure_kpa
            equivalent = _equivalent_fraction(config, x_access, pressure_kpa, strict=False)
            if equivalent != raw_equivalent:
                domain_clips += 1
            drive = -np.log1p(-equivalent)
        else:
            drive = x_access
        result.append((drive - cell_state) / tau_cell)
        return np.asarray(result, dtype=float)

    def record(t: float, y: np.ndarray, power_w: float) -> None:
        temp_block, oxygen_moles = float(y[0]), float(y[1])
        ambient = series.linear("temp_ambient_c", t)
        inlet = series.linear("temp_inlet_c", t, ambient)
        pressure = series.linear("pressure_reference_kpa", t)
        total_moles = _total_moles(pressure, inlet, volume_m3)
        x_plenum = series.linear("o2_reference_pct_wet", t) / 100.0 if direct_exposure else max(oxygen_moles, 0.0) / total_moles
        index = 2
        x_access = float(y[index]) if access_enabled else x_plenum
        if access_enabled:
            index += 1
        cell_state = float(y[index])
        current = _current_from_state(config, cell_state, pressure, temp_block)
        oxygen = inverse_signal(
            config,
            max(current, config.cell.i_zero_ma.require("cell.i_zero_ma")),
            pressure,
            temp_block,
        ) * 100.0
        k_t = _temperature_adjusted_k(config, temp_block)
        equivalent_at_reference = 1.0 - np.exp(
            -(current - config.cell.i_zero_ma.require("cell.i_zero_ma")) / k_t
        )
        available_oxygen = x_plenum * total_moles if direct_exposure else oxygen_moles
        sink, requested_sink, sink_limited = _cell_consumption(config, current, available_oxygen)
        if thermal_available:
            rate = derivative(t, y, power_w)[0]
            settled = False
        else:
            rate = float("nan")
            settled = False
        rows.append({
            "time_s": t,
            "o2_reference_pct_wet": series.linear("o2_reference_pct_wet", t),
            "o2_plenum_pct_wet": x_plenum * 100.0,
            "o2_access_pct_wet": x_access * 100.0,
            "o2_probe_pct_wet": oxygen,
            "o2_probe_pressure_compensated_pct_wet": oxygen,
            "o2_probe_equivalent_pct_at_reference_pressure": equivalent_at_reference * 100.0,
            "cell_current_mA": current,
            "cell_o2_sink_requested_mol_per_s": requested_sink,
            "cell_o2_sink_applied_mol_per_s": sink,
            "cell_o2_sink_limited": sink_limited,
            "pressure_reference_kpa": pressure,
            "temp_ambient_c": ambient,
            "temp_inlet_c": inlet,
            "rh_ambient_pct": series.linear("rh_ambient_pct", t, float("nan")),
            "temp_block_c": temp_block,
            "temp_membrane_qs_c": float("nan"),
            "rh_membrane_qs_pct": float("nan"),
            "dew_margin_qs_k": float("nan"),
            "thermal_rate_k_per_s": rate,
            "thermal_settled": settled,
            "heater_command_w": power_w,
            "heater_applied_w": power_w if temp_block < config.controller.max_block_temp_c else 0.0,
        })

    initial_power = min(series.hold("heater_power_w", t0, 0.0), config.controller.max_power_w)
    record(times[0], np.asarray(state), initial_power)
    for target in times[1:]:
        current_t = rows[-1]["time_s"]
        while current_t < target - 1e-12:
            if manifest.heater_mode == "delta_t_pi" and current_t >= next_tick - 1e-12:
                ambient = series.linear("temp_ambient_c", current_t)
                error = config.controller.target_delta_t_k - (state[0] - ambient)
                kp = float(config.controller.kp_w_per_k)
                ki = float(config.controller.ki_w_per_k_s)
                proposed_integral = integral + error * config.controller.sample_period_s
                raw = kp * error + ki * proposed_integral
                limited = float(np.clip(raw, 0.0, config.controller.max_power_w))
                if raw == limited or (raw > limited and error < 0) or (raw < limited and error > 0):
                    integral = proposed_integral
                controller_power = limited if state[0] < config.controller.max_block_temp_c else 0.0
                next_tick += config.controller.sample_period_s
                controller_ticks += 1
            if manifest.heater_mode == "prescribed_power":
                controller_power = min(series.hold("heater_power_w", current_t, 0.0), config.controller.max_power_w)
                if state[0] >= config.controller.max_block_temp_c:
                    controller_power = 0.0
            segment_end = target
            if manifest.heater_mode == "delta_t_pi":
                segment_end = min(segment_end, next_tick)
            solution = solve_ivp(
                lambda t, y: derivative(t, y, controller_power),
                (current_t, segment_end),
                np.asarray(state, dtype=float),
                method="RK45",
                rtol=config.solver.rtol,
                atol=config.solver.atol,
                max_step=min(config.solver.max_step_s, segment_end - current_t),
            )
            if not solution.success:
                raise RuntimeError(solution.message)
            state = solution.y[:, -1].tolist()
            current_t = segment_end
        if manifest.heater_mode == "prescribed_power":
            controller_power = min(series.hold("heater_power_w", target, 0.0), config.controller.max_power_w)
        record(target, np.asarray(state), controller_power)

    output = pd.DataFrame(rows)
    _apply_quasi_steady_membrane_outputs(config, output)
    return SimulationResult(output, {
        "success": True,
        "controller_ticks": controller_ticks,
        "access_model": access_enabled,
        "direct_exposure": direct_exposure,
        "thermal_model_available": thermal_available,
        "uncalibrated": config.is_uncalibrated,
        "regime": regime_name,
        "temperature_inventory_source": "temp_inlet_c" if "temp_inlet_c" in inputs else "temp_ambient_c_fallback",
        "signal_domain_clips": domain_clips,
        "consumption_limiter_activations": int(output["cell_o2_sink_limited"].sum()),
        "pressure_compensation_transient": bool(
            np.ptp(inputs["pressure_reference_kpa"].to_numpy(dtype=float)) > 1e-9
        ),
        "temperature_cutoff_activations": int((output["heater_command_w"] > output["heater_applied_w"]).sum()),
    })


def _current_from_state(config: ModelConfig, state: float, pressure_kpa: float, temp_c: float) -> float:
    i0 = config.cell.i_zero_ma.require("cell.i_zero_ma")
    k_t = _temperature_adjusted_k(config, temp_c)
    if config.cell.dynamic_domain == "normalized_output":
        return i0 + k_t * state
    equivalent = _equivalent_fraction(config, state, pressure_kpa, strict=False)
    return i0 + k_t * (-np.log1p(-equivalent))


def _temperature_adjusted_k(config: ModelConfig, temp_c: float) -> float:
    k_ref = config.cell.k_ref_ma.require("cell.k_ref_ma")
    alpha = config.cell.temp_coeff_per_k.value or 0.0
    k_t = k_ref * (1.0 + alpha * (temp_c - config.cell.reference_temp_c))
    if not np.isfinite(k_t) or k_t <= 0:
        raise ValueError("temperature-adjusted K must be finite and positive")
    return float(k_t)


def _cell_consumption(
    config: ModelConfig,
    current_ma: float,
    oxygen_moles: float,
) -> tuple[float, float, bool]:
    if not config.gas.include_cell_consumption:
        return 0.0, 0.0, False
    faradaic_a = max(
        (current_ma - config.cell.i_zero_ma.require("cell.i_zero_ma")) * 1e-3,
        0.0,
    )
    requested = faradaic_a / (config.gas.electrons_per_o2 * FARADAY)
    inventory = max(oxygen_moles, 0.0)
    reserve = requested * config.gas.consumption_availability_tau_s
    applied = requested * inventory / (inventory + reserve) if requested > 0.0 else 0.0
    return float(applied), float(requested), bool(applied < 0.99 * requested)


def _steady_initial_oxygen_fraction(
    config: ModelConfig,
    external_fraction: float,
    pressure_kpa: float,
    temp_c: float,
    total_moles: float,
    conductance_mol_per_s: float,
) -> float:
    if (
        not config.gas.include_cell_consumption
        or external_fraction <= 0.0
        or conductance_mol_per_s <= 0.0
    ):
        return external_fraction

    def balance(fraction: float) -> float:
        current = static_signal(config, fraction, pressure_kpa, temp_c)
        sink, _, _ = _cell_consumption(config, current, fraction * total_moles)
        return conductance_mol_per_s * (external_fraction - fraction) - sink

    return float(brentq(balance, 0.0, external_fraction, xtol=1e-14, rtol=1e-12))


def _equivalent_fraction(config: ModelConfig, oxygen_fraction: float, pressure_kpa: float, strict: bool) -> float:
    equivalent = oxygen_fraction * pressure_kpa / config.cell.reference_pressure_kpa
    if strict and not 0.0 <= equivalent < 1.0:
        raise ValueError(f"SGX logarithmic domain requires 0 <= equivalent O2 fraction < 1, got {equivalent}")
    return float(np.clip(equivalent, 0.0, 1.0 - 1e-12))


def _total_moles(pressure_kpa: float, temp_c: float, volume_m3: float) -> float:
    temp_k = temp_c + 273.15
    if pressure_kpa <= 0 or temp_k <= 0:
        raise ValueError("positive absolute pressure and temperature are required")
    return pressure_kpa * 1000.0 * volume_m3 / (R_GAS * temp_k)


def _total_moles_rate(
    pressure_kpa: float,
    pressure_rate_kpa_per_s: float,
    temp_c: float,
    temp_rate_k_per_s: float,
    volume_m3: float,
) -> float:
    temp_k = temp_c + 273.15
    if pressure_kpa <= 0 or temp_k <= 0:
        raise ValueError("positive absolute pressure and temperature are required")
    scale = 1000.0 * volume_m3 / R_GAS
    return float(scale * (pressure_rate_kpa_per_s / temp_k - pressure_kpa * temp_rate_k_per_s / temp_k**2))


def _resolve_window_conductance(config: ModelConfig, manifest: ExperimentManifest) -> float:
    area_mm2 = manifest.free_membrane_area_mm2
    base_area_mm2 = config.geometry.free_membrane_area_mm2.require("geometry.free_membrane_area_mm2")
    if area_mm2 is None:
        area_mm2 = base_area_mm2
    model = config.gas.area_model
    if model == "fixed_conductance":
        if manifest.free_membrane_area_mm2 is not None and not np.isclose(area_mm2, base_area_mm2):
            raise ValueError("free-area override requires an explicit area scaling model")
        return config.gas.window_conductance_mol_per_s.require("gas.window_conductance_mol_per_s")
    if model == "area_only":
        base = config.gas.window_conductance_mol_per_s.require("gas.window_conductance_mol_per_s")
        return base * area_mm2 / base_area_mm2 if base_area_mm2 > 0 else 0.0
    area_m2 = area_mm2 * 1e-6
    if area_m2 <= 0:
        return 0.0
    k_area = config.gas.area_conductance_mol_per_s_m2.require("gas.area_conductance_mol_per_s_m2")
    resistance = config.gas.access_resistance_s_per_mol.require("gas.access_resistance_s_per_mol")
    if k_area <= 0:
        return 0.0
    return 1.0 / (1.0 / (area_m2 * k_area) + resistance)


def _apply_quasi_steady_membrane_outputs(config: ModelConfig, output: pd.DataFrame) -> None:
    if config.thermal.resistance_k_per_w.value is None or config.thermal.capacitance_j_per_k.value is None:
        return
    eta = config.thermal.membrane_coupling.value
    if eta is None:
        return
    dwell = 0.0
    settled: list[bool] = []
    previous_t = float(output["time_s"].iloc[0])
    for row in output.itertuples(index=False):
        candidate = abs(row.thermal_rate_k_per_s) <= config.thermal.settled_rate_k_per_s
        if candidate:
            dwell += max(float(row.time_s) - previous_t, 0.0)
        else:
            dwell = 0.0
        settled.append(candidate and dwell >= config.thermal.settled_dwell_s)
        previous_t = float(row.time_s)
    output["thermal_settled"] = settled
    for index in output.index[output["thermal_settled"]]:
        ambient = float(output.at[index, "temp_ambient_c"])
        block = float(output.at[index, "temp_block_c"])
        membrane = ambient + eta * (block - ambient)
        output.at[index, "temp_membrane_qs_c"] = membrane
        if "rh_ambient_pct" in output:
            rh_ambient = float(output.at[index, "rh_ambient_pct"])
        else:
            rh_ambient = float("nan")
        if np.isfinite(rh_ambient):
            output.at[index, "rh_membrane_qs_pct"] = local_rh_pct(ambient, rh_ambient, membrane)
            output.at[index, "dew_margin_qs_k"] = membrane - dew_point_c(ambient, rh_ambient)
