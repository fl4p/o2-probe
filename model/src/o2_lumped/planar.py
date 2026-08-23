from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import expm_multiply

from .config import ExperimentManifest, ModelConfig, Provenance
from .physics import (
    R_GAS,
    _current_from_state,
    _equivalent_fraction,
    _resolve_window_conductance,
    inverse_signal,
)


@dataclass(frozen=True)
class PlanarCandidateDomain:
    """Extruded 2-D diffusion section through the dual-window local plenum.

    The section resolves the circular shroud, PCB divider, cell envelope, rear
    PCB aperture and two radial membrane windows. Off-section void volume is
    retained through an effective extrusion depth derived from total volume.
    """

    radius_mm: float = 12.0
    grid_spacing_mm: float = 0.75
    window_centres_deg: tuple[float, float] = (45.0, 135.0)
    window_width_mm: float = 10.0
    membrane_to_cavity_path_mm: float = 5.8
    pcb_half_width_mm: float = 10.0
    pcb_half_thickness_mm: float = 0.5
    rear_aperture_diameter_mm: float = 3.0
    cell_half_width_mm: float = 7.2
    cell_rear_y_mm: float = 0.5
    cell_front_y_mm: float = 8.8
    front_port_xy_mm: tuple[float, float] = (0.0, 9.5)
    rear_port_xy_mm: tuple[float, float] = (0.0, -1.5)

    def validate(self) -> None:
        positive = (
            self.radius_mm,
            self.grid_spacing_mm,
            self.window_width_mm,
            self.pcb_half_width_mm,
            self.pcb_half_thickness_mm,
            self.rear_aperture_diameter_mm,
            self.cell_half_width_mm,
        )
        if not all(np.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("planar candidate dimensions must be finite and positive")
        if self.grid_spacing_mm >= self.radius_mm / 2.0:
            raise ValueError("planar grid spacing is too coarse for the cavity")
        if self.window_width_mm >= 2.0 * self.radius_mm:
            raise ValueError("window width must be smaller than the cavity diameter")
        if (
            not np.isfinite(self.membrane_to_cavity_path_mm)
            or self.membrane_to_cavity_path_mm < 0.0
        ):
            raise ValueError("membrane-to-cavity path must be finite and nonnegative")
        if len(self.window_centres_deg) != 2 or not all(
            np.isfinite(value) for value in self.window_centres_deg
        ):
            raise ValueError("exactly two finite window centre angles are required")
        if not self.cell_rear_y_mm < self.cell_front_y_mm:
            raise ValueError("cell rear/front coordinates must be ordered")


@dataclass(frozen=True)
class PlanarTransportSystem:
    matrix: csr_matrix
    boundary_drive: np.ndarray
    coordinates_mm: np.ndarray
    front_port_index: int
    rear_port_index: int
    membrane_face_count: int
    active_cell_count: int
    effective_depth_mm: float
    diagnostics: dict[str, object]


def build_planar_transport_system(
    config: ModelConfig,
    manifest: ExperimentManifest,
    domain: PlanarCandidateDomain,
    effective_diffusivity_m2_s: float,
    pressure_kpa: float = 101.325,
    temp_c: float = 50.0,
) -> PlanarTransportSystem:
    domain.validate()
    if not np.isfinite(effective_diffusivity_m2_s) or effective_diffusivity_m2_s <= 0.0:
        raise ValueError("effective planar diffusivity must be finite and positive")
    if config.gas.conductance_scope != "intrinsic_window":
        raise ValueError("planar diffusion requires intrinsic_window conductance")
    if manifest.assembly_stage not in {"window", "validation"}:
        raise ValueError("planar diffusion applies to an enclosed window assembly")
    if not np.isfinite(pressure_kpa) or pressure_kpa <= 0.0:
        raise ValueError("positive finite pressure is required")
    if not np.isfinite(temp_c) or temp_c <= -273.15:
        raise ValueError("positive finite absolute temperature is required")
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
    if volume_m3 <= 0.0:
        raise ValueError("planar plenum volume must be positive")

    spacing_mm = domain.grid_spacing_mm
    axis = np.arange(
        -domain.radius_mm + spacing_mm / 2.0,
        domain.radius_mm,
        spacing_mm,
    )
    xx, yy = np.meshgrid(axis, axis, indexing="xy")
    inside_circle = xx**2 + yy**2 <= domain.radius_mm**2
    rear_aperture = xx**2 + yy**2 <= (domain.rear_aperture_diameter_mm / 2.0) ** 2
    pcb_solid = (
        (np.abs(xx) <= domain.pcb_half_width_mm)
        & (np.abs(yy) <= domain.pcb_half_thickness_mm)
        & ~rear_aperture
    )
    cell_solid = (
        (np.abs(xx) <= domain.cell_half_width_mm)
        & (yy >= domain.cell_rear_y_mm)
        & (yy <= domain.cell_front_y_mm)
    )
    active = inside_circle & ~pcb_solid & ~cell_solid
    active_locations = np.argwhere(active)
    if len(active_locations) < 20:
        raise ValueError("planar domain contains too few active gas cells")
    index_map = np.full(active.shape, -1, dtype=int)
    index_map[active] = np.arange(len(active_locations))
    coordinates = np.column_stack((xx[active], yy[active]))

    gas_molar_density = pressure_kpa * 1000.0 / (R_GAS * (temp_c + 273.15))
    node_capacity_mol = gas_molar_density * volume_m3 / len(active_locations)
    active_area_m2 = len(active_locations) * (spacing_mm * 1e-3) ** 2
    effective_depth_m = volume_m3 / active_area_m2
    face_area_m2 = effective_depth_m * spacing_mm * 1e-3
    internal_conductance = (
        effective_diffusivity_m2_s
        * gas_molar_density
        * face_area_m2
        / (spacing_mm * 1e-3)
    )

    rows: list[int] = []
    columns: list[int] = []
    values: list[float] = []
    diagonal = np.zeros(len(active_locations), dtype=float)
    neighbor_offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    for node, (row, column) in enumerate(active_locations):
        for drow, dcolumn in ((1, 0), (0, 1)):
            other_row, other_column = row + drow, column + dcolumn
            if (
                0 <= other_row < active.shape[0]
                and 0 <= other_column < active.shape[1]
                and active[other_row, other_column]
            ):
                other = int(index_map[other_row, other_column])
                rate = internal_conductance / node_capacity_mol
                rows.extend((node, other))
                columns.extend((other, node))
                values.extend((rate, rate))
                diagonal[node] -= rate
                diagonal[other] -= rate

    half_angle_deg = np.degrees(
        np.arcsin(domain.window_width_mm / (2.0 * domain.radius_mm))
    )
    membrane_faces: list[int] = []
    for node, (row, column) in enumerate(active_locations):
        x_mm, y_mm = coordinates[node]
        for drow, dcolumn in neighbor_offsets:
            other_row, other_column = row + drow, column + dcolumn
            neighbor_inside_circle = (
                0 <= other_row < active.shape[0]
                and 0 <= other_column < active.shape[1]
                and inside_circle[other_row, other_column]
            )
            if neighbor_inside_circle:
                continue
            face_x = x_mm + dcolumn * spacing_mm / 2.0
            face_y = y_mm + drow * spacing_mm / 2.0
            face_angle = np.degrees(np.arctan2(face_y, face_x)) % 360.0
            if any(
                abs((face_angle - centre + 180.0) % 360.0 - 180.0)
                <= half_angle_deg
                for centre in domain.window_centres_deg
            ):
                membrane_faces.append(node)
    if not membrane_faces:
        raise ValueError("grid does not resolve either membrane window")

    window_conductance = _resolve_window_conductance(config, manifest) * multiplier
    intrinsic_face_conductance = window_conductance / len(membrane_faces)
    free_area_mm2 = (
        manifest.free_membrane_area_mm2
        if manifest.free_membrane_area_mm2 is not None
        else config.geometry.free_membrane_area_mm2.require(
            "geometry.free_membrane_area_mm2"
        )
    )
    half_cell_total_conductance = (
        effective_diffusivity_m2_s
        * gas_molar_density
        * free_area_mm2
        * 1e-6
        / (0.5 * spacing_mm * 1e-3)
    )
    access_total_conductance = (
        float("inf")
        if domain.membrane_to_cavity_path_mm <= 0.0
        else effective_diffusivity_m2_s
        * gas_molar_density
        * free_area_mm2
        * 1e-6
        / (domain.membrane_to_cavity_path_mm * 1e-3)
    )
    half_cell_conductance = half_cell_total_conductance / len(membrane_faces)
    access_face_conductance = access_total_conductance / len(membrane_faces)
    boundary_face_conductance = (
        0.0
        if intrinsic_face_conductance <= 0.0
        else 1.0
        / (
            1.0 / intrinsic_face_conductance
            + 1.0 / access_face_conductance
            + 1.0 / half_cell_conductance
        )
    )
    boundary_drive = np.zeros(len(active_locations), dtype=float)
    boundary_rate = boundary_face_conductance / node_capacity_mol
    for node in membrane_faces:
        diagonal[node] -= boundary_rate
        boundary_drive[node] += boundary_rate

    rows.extend(range(len(active_locations)))
    columns.extend(range(len(active_locations)))
    values.extend(diagonal.tolist())
    matrix = coo_matrix(
        (values, (rows, columns)),
        shape=(len(active_locations), len(active_locations)),
    ).tocsr()

    def nearest_active(point: tuple[float, float]) -> int:
        distances = np.sum((coordinates - np.asarray(point)) ** 2, axis=1)
        return int(np.argmin(distances))

    front_index = nearest_active(domain.front_port_xy_mm)
    rear_index = nearest_active(domain.rear_port_xy_mm)
    steady_residual = matrix @ np.ones(len(active_locations)) + boundary_drive
    diagnostics: dict[str, object] = {
        "transport_model": "extruded_2d_finite_volume_diffusion",
        "active_cells": len(active_locations),
        "grid_spacing_mm": spacing_mm,
        "effective_depth_mm": effective_depth_m * 1000.0,
        "membrane_boundary_faces": len(membrane_faces),
        "front_port_node_xy_mm": coordinates[front_index].tolist(),
        "rear_port_node_xy_mm": coordinates[rear_index].tolist(),
        "steady_uniform_residual_max_per_s": float(np.max(np.abs(steady_residual))),
        "window_centres_deg": list(domain.window_centres_deg),
        "window_width_mm": domain.window_width_mm,
        "declared_projected_free_area_mm2": free_area_mm2,
        "membrane_to_cavity_path_mm": domain.membrane_to_cavity_path_mm,
        "access_path_conductance_mol_per_s": access_total_conductance,
        "rear_aperture_diameter_mm": domain.rear_aperture_diameter_mm,
        "effective_planar_diffusivity_m2_s": effective_diffusivity_m2_s,
        "window_conductance_mol_per_s": window_conductance,
        "heater_convection_modeled": False,
        "cell_consumption_modeled": False,
        "geometry_status": "CAD-derived extruded-section sensitivity",
    }
    return PlanarTransportSystem(
        matrix=matrix,
        boundary_drive=boundary_drive,
        coordinates_mm=coordinates,
        front_port_index=front_index,
        rear_port_index=rear_index,
        membrane_face_count=len(membrane_faces),
        active_cell_count=len(active_locations),
        effective_depth_mm=effective_depth_m * 1000.0,
        diagnostics=diagnostics,
    )


def simulate_planar_step(
    config: ModelConfig,
    manifest: ExperimentManifest,
    domain: PlanarCandidateDomain,
    effective_diffusivity_m2_s: float,
    duration_s: float = 600.0,
    output_dt_s: float = 0.5,
    front_port_weight: float = 0.5,
    pressure_kpa: float = 101.325,
    temp_c: float = 50.0,
    final_o2_pct_wet: float = 20.95,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration must be finite and positive")
    if not np.isfinite(output_dt_s) or output_dt_s <= 0.0 or output_dt_s > duration_s:
        raise ValueError("output cadence must be finite, positive and within duration")
    if not 0.0 <= front_port_weight <= 1.0:
        raise ValueError("front-port weight must be within [0, 1]")
    if pressure_kpa <= 0.0 or temp_c <= -273.15:
        raise ValueError("positive absolute pressure and temperature are required")
    if not 0.0 < final_o2_pct_wet < 100.0:
        raise ValueError("final O2 must be within (0, 100) percent")
    system = build_planar_transport_system(
        config,
        manifest,
        domain,
        effective_diffusivity_m2_s,
        pressure_kpa,
        temp_c,
    )
    sample_count = int(np.floor(duration_s / output_dt_s)) + 1
    times = np.linspace(0.0, output_dt_s * (sample_count - 1), sample_count)
    initial_offset = -np.ones(system.active_cell_count, dtype=float)
    gas_offset = expm_multiply(
        system.matrix,
        initial_offset,
        start=0.0,
        stop=float(times[-1]),
        num=len(times),
        endpoint=True,
        traceA=float(system.matrix.diagonal().sum()),
    )
    normalized_gas = np.clip(1.0 + gas_offset, 0.0, 1.0)
    front = normalized_gas[:, system.front_port_index]
    rear = normalized_gas[:, system.rear_port_index]
    sampled = front_port_weight * front + (1.0 - front_port_weight) * rear

    oxygen_fraction = sampled * final_o2_pct_wet / 100.0
    if config.cell.dynamic_domain == "normalized_output":
        drive = np.asarray([
            -np.log1p(
                -_equivalent_fraction(config, value, pressure_kpa, strict=False)
            )
            for value in oxygen_fraction
        ])
    else:
        drive = oxygen_fraction
    cell_state = np.zeros(len(times), dtype=float)
    tau_cell = config.cell.tau_s.require("cell.tau_s")
    decay = np.exp(-output_dt_s / tau_cell)
    ramp_coefficient = 1.0 - tau_cell / output_dt_s * (1.0 - decay)
    for index in range(1, len(times)):
        cell_state[index] = (
            cell_state[index - 1] * decay
            + drive[index - 1] * (1.0 - decay)
            + (drive[index] - drive[index - 1]) * ramp_coefficient
        )
    currents = np.asarray([
        _current_from_state(config, state, pressure_kpa, temp_c)
        for state in cell_state
    ])
    probe = np.asarray([
        inverse_signal(
            config,
            max(current, config.cell.i_zero_ma.require("cell.i_zero_ma")),
            pressure_kpa,
            temp_c,
        )
        * 100.0
        for current in currents
    ])
    frame = pd.DataFrame({
        "time_s": times,
        "o2_reference_pct_wet": final_o2_pct_wet,
        "o2_front_port_pct_wet": front * final_o2_pct_wet,
        "o2_rear_port_pct_wet": rear * final_o2_pct_wet,
        "o2_sampled_ports_pct_wet": sampled * final_o2_pct_wet,
        "o2_probe_pct_wet": probe,
    })
    diagnostics = {
        **system.diagnostics,
        "front_port_weight": front_port_weight,
        "pressure_kpa": pressure_kpa,
        "temp_c": temp_c,
        "duration_s": float(times[-1]),
        "output_dt_s": output_dt_s,
        "uncalibrated": True,
    }
    return frame, diagnostics


def monotonic_response_metrics(
    frame: pd.DataFrame, column: str = "o2_probe_pct_wet"
) -> dict[str, float | None]:
    times = frame.time_s.to_numpy(dtype=float)
    values = frame[column].to_numpy(dtype=float)
    target = float(frame.o2_reference_pct_wet.iloc[-1])

    def crossing(fraction: float) -> float | None:
        indices = np.flatnonzero(values >= fraction * target)
        if not len(indices):
            return None
        index = int(indices[0])
        if index == 0:
            return float(times[0])
        return float(
            np.interp(
                fraction * target,
                values[index - 1:index + 1],
                times[index - 1:index + 1],
            )
        )

    return {
        "t90_s": crossing(0.90),
        "settling_time_2pct_s": crossing(0.98),
    }
