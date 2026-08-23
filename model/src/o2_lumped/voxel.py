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
class VoxelCandidateDomain:
    """CAD-derived 3-D local-plenum diffusion geometry in millimetres."""

    radius_mm: float = 12.0
    clear_length_mm: float = 20.6
    grid_spacing_xy_mm: float = 1.0
    target_grid_spacing_z_mm: float = 1.0
    window_centres_deg: tuple[float, float] = (45.0, 135.0)
    window_width_mm: float = 10.0
    window_height_mm: float = 10.0
    membrane_to_cavity_path_mm: float = 5.8
    pcb_half_width_mm: float = 10.0
    pcb_half_thickness_mm: float = 0.5
    rear_aperture_diameter_mm: float = 3.0
    cell_radius_mm: float = 7.2
    cell_rear_y_mm: float = 0.5
    cell_front_y_mm: float = 8.8
    front_port_diameter_mm: float = 10.6

    def validate(self) -> None:
        positive = (
            self.radius_mm,
            self.clear_length_mm,
            self.grid_spacing_xy_mm,
            self.target_grid_spacing_z_mm,
            self.window_width_mm,
            self.window_height_mm,
            self.pcb_half_width_mm,
            self.pcb_half_thickness_mm,
            self.rear_aperture_diameter_mm,
            self.cell_radius_mm,
            self.front_port_diameter_mm,
        )
        if not all(np.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("voxel candidate dimensions must be finite and positive")
        if self.grid_spacing_xy_mm >= self.radius_mm / 2.0:
            raise ValueError("voxel xy grid spacing is too coarse")
        if self.target_grid_spacing_z_mm >= self.clear_length_mm / 4.0:
            raise ValueError("voxel z grid spacing is too coarse")
        if self.window_width_mm >= 2.0 * self.radius_mm:
            raise ValueError("window width must be smaller than the cavity diameter")
        if self.window_height_mm > self.clear_length_mm:
            raise ValueError("window height cannot exceed clear cavity length")
        if (
            not np.isfinite(self.membrane_to_cavity_path_mm)
            or self.membrane_to_cavity_path_mm < 0.0
        ):
            raise ValueError("membrane-to-cavity path must be finite and nonnegative")
        if len(self.window_centres_deg) != 2 or not all(
            np.isfinite(value) for value in self.window_centres_deg
        ):
            raise ValueError("exactly two finite window angles are required")
        if not self.cell_rear_y_mm < self.cell_front_y_mm:
            raise ValueError("cell rear/front coordinates must be ordered")


@dataclass(frozen=True)
class VoxelTransportSystem:
    matrix: csr_matrix
    boundary_drive: np.ndarray
    coordinates_mm: np.ndarray
    front_port_indices: np.ndarray
    rear_port_indices: np.ndarray
    active_cell_count: int
    membrane_face_count: int
    geometric_gas_volume_cm3: float
    modeled_gas_volume_cm3: float
    diagnostics: dict[str, object]


def build_voxel_transport_system(
    config: ModelConfig,
    manifest: ExperimentManifest,
    domain: VoxelCandidateDomain,
    effective_diffusivity_m2_s: float,
    pressure_kpa: float = 101.325,
    temp_c: float = 50.0,
) -> VoxelTransportSystem:
    domain.validate()
    if not np.isfinite(effective_diffusivity_m2_s) or effective_diffusivity_m2_s <= 0.0:
        raise ValueError("effective voxel diffusivity must be finite and positive")
    if config.gas.conductance_scope != "intrinsic_window":
        raise ValueError("voxel diffusion requires intrinsic_window conductance")
    if manifest.assembly_stage not in {"window", "validation"}:
        raise ValueError("voxel diffusion applies to an enclosed window assembly")
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
        raise ValueError(
            f"regime {regime_name!r} must be measured or fitted before simulation"
        )
    multiplier = regime.require(f"regimes.{regime_name}.conductance_multiplier")

    volume_cm3 = (
        manifest.plenum_volume_cm3
        if manifest.plenum_volume_cm3 is not None
        else config.geometry.plenum_volume_cm3.require("geometry.plenum_volume_cm3")
    )
    if volume_cm3 <= 0.0:
        raise ValueError("voxel plenum volume must be positive")
    modeled_volume_m3 = volume_cm3 * 1e-6

    spacing_xy_mm = domain.grid_spacing_xy_mm
    xy_axis = np.arange(
        -domain.radius_mm + spacing_xy_mm / 2.0,
        domain.radius_mm,
        spacing_xy_mm,
    )
    z_cells = int(np.ceil(domain.clear_length_mm / domain.target_grid_spacing_z_mm))
    spacing_z_mm = domain.clear_length_mm / z_cells
    z_axis = (
        np.arange(z_cells, dtype=float) + 0.5
    ) * spacing_z_mm - domain.clear_length_mm / 2.0
    xx, yy, zz = np.meshgrid(xy_axis, xy_axis, z_axis, indexing="ij")
    inside_cylinder = xx**2 + yy**2 <= domain.radius_mm**2
    rear_aperture = xx**2 + zz**2 <= (domain.rear_aperture_diameter_mm / 2.0) ** 2
    pcb_solid = (
        (np.abs(xx) <= domain.pcb_half_width_mm)
        & (np.abs(yy) <= domain.pcb_half_thickness_mm)
        & ~rear_aperture
    )
    cell_solid = (
        (xx**2 + zz**2 <= domain.cell_radius_mm**2)
        & (yy >= domain.cell_rear_y_mm)
        & (yy <= domain.cell_front_y_mm)
    )
    active = inside_cylinder & ~pcb_solid & ~cell_solid
    active_locations = np.argwhere(active)
    if len(active_locations) < 100:
        raise ValueError("voxel domain contains too few active gas cells")
    index_map = np.full(active.shape, -1, dtype=int)
    index_map[active] = np.arange(len(active_locations))
    coordinates = np.column_stack((xx[active], yy[active], zz[active]))

    dx_m = spacing_xy_mm * 1e-3
    dz_m = spacing_z_mm * 1e-3
    geometric_cell_volume_m3 = dx_m * dx_m * dz_m
    geometric_volume_m3 = len(active_locations) * geometric_cell_volume_m3
    gas_molar_density = pressure_kpa * 1000.0 / (R_GAS * (temp_c + 273.15))
    node_capacity_mol = gas_molar_density * modeled_volume_m3 / len(active_locations)
    conductance_x_y = (
        effective_diffusivity_m2_s * gas_molar_density * (dx_m * dz_m) / dx_m
    )
    conductance_z = (
        effective_diffusivity_m2_s * gas_molar_density * (dx_m * dx_m) / dz_m
    )

    rows: list[int] = []
    columns: list[int] = []
    values: list[float] = []
    diagonal = np.zeros(len(active_locations), dtype=float)
    positive_neighbors = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    for node, (ix, iy, iz) in enumerate(active_locations):
        for dix, diy, diz in positive_neighbors:
            other_location = (ix + dix, iy + diy, iz + diz)
            if (
                other_location[0] < active.shape[0]
                and other_location[1] < active.shape[1]
                and other_location[2] < active.shape[2]
                and active[other_location]
            ):
                other = int(index_map[other_location])
                conductance = conductance_z if diz else conductance_x_y
                rate = conductance / node_capacity_mol
                rows.extend((node, other))
                columns.extend((other, node))
                values.extend((rate, rate))
                diagonal[node] -= rate
                diagonal[other] -= rate

    half_angle_deg = np.degrees(
        np.arcsin(domain.window_width_mm / (2.0 * domain.radius_mm))
    )
    membrane_faces: list[int] = []
    radial_neighbors = ((-1, 0), (1, 0), (0, -1), (0, 1))
    for node, (ix, iy, iz) in enumerate(active_locations):
        x_mm, y_mm, z_mm = coordinates[node]
        if abs(z_mm) > domain.window_height_mm / 2.0:
            continue
        for dix, diy in radial_neighbors:
            other_x, other_y = ix + dix, iy + diy
            neighbor_inside_cylinder = (
                0 <= other_x < active.shape[0]
                and 0 <= other_y < active.shape[1]
                and inside_cylinder[other_x, other_y, iz]
            )
            if neighbor_inside_cylinder:
                continue
            face_x = x_mm + dix * spacing_xy_mm / 2.0
            face_y = y_mm + diy * spacing_xy_mm / 2.0
            face_angle = np.degrees(np.arctan2(face_y, face_x)) % 360.0
            if any(
                abs((face_angle - centre + 180.0) % 360.0 - 180.0) <= half_angle_deg
                for centre in domain.window_centres_deg
            ):
                membrane_faces.append(node)
    if not membrane_faces:
        raise ValueError("voxel grid does not resolve either membrane window")

    window_conductance = _resolve_window_conductance(config, manifest) * multiplier
    intrinsic_face_conductance = window_conductance / len(membrane_faces)
    free_area_mm2 = (
        manifest.free_membrane_area_mm2
        if manifest.free_membrane_area_mm2 is not None
        else config.geometry.free_membrane_area_mm2.require(
            "geometry.free_membrane_area_mm2"
        )
    )
    # Use the declared projected free area for the gas-side half-cell
    # resistance. A Cartesian stair-step count overestimates a curved surface
    # and would otherwise make the result depend on grid orientation.
    half_cell_total_conductance = (
        effective_diffusivity_m2_s
        * gas_molar_density
        * free_area_mm2
        * 1e-6
        / (0.5 * dx_m)
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
    boundary_rate = boundary_face_conductance / node_capacity_mol
    boundary_drive = np.zeros(len(active_locations), dtype=float)
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

    front_port_mask = (
        (coordinates[:, 1] > domain.cell_front_y_mm)
        & (coordinates[:, 1] <= domain.cell_front_y_mm + 1.5 * spacing_xy_mm)
        & (
            coordinates[:, 0] ** 2 + coordinates[:, 2] ** 2
            <= (domain.front_port_diameter_mm / 2.0) ** 2
        )
    )
    rear_port_mask = (
        (coordinates[:, 1] < -domain.pcb_half_thickness_mm)
        & (coordinates[:, 1] >= -domain.pcb_half_thickness_mm - 1.5 * spacing_xy_mm)
        & (
            coordinates[:, 0] ** 2 + coordinates[:, 2] ** 2
            <= (domain.rear_aperture_diameter_mm / 2.0) ** 2
        )
    )
    front_indices = np.flatnonzero(front_port_mask)
    rear_indices = np.flatnonzero(rear_port_mask)
    if not len(front_indices) or not len(rear_indices):
        raise ValueError("voxel grid does not resolve both sensor port surfaces")

    steady_residual = matrix @ np.ones(len(active_locations)) + boundary_drive
    diagnostics: dict[str, object] = {
        "transport_model": "cad_3d_voxel_finite_volume_diffusion",
        "active_cells": len(active_locations),
        "grid_spacing_xy_mm": spacing_xy_mm,
        "grid_spacing_z_mm": spacing_z_mm,
        "geometric_gas_volume_cm3": geometric_volume_m3 * 1e6,
        "modeled_gas_volume_cm3": volume_cm3,
        "volume_capacity_scale": modeled_volume_m3 / geometric_volume_m3,
        "membrane_boundary_faces": len(membrane_faces),
        "represented_membrane_area_mm2": len(membrane_faces)
        * spacing_xy_mm
        * spacing_z_mm,
        "declared_projected_free_area_mm2": free_area_mm2,
        "membrane_to_cavity_path_mm": domain.membrane_to_cavity_path_mm,
        "access_path_conductance_mol_per_s": access_total_conductance,
        "front_port_nodes": len(front_indices),
        "rear_port_nodes": len(rear_indices),
        "steady_uniform_residual_max_per_s": float(np.max(np.abs(steady_residual))),
        "window_centres_deg": list(domain.window_centres_deg),
        "effective_voxel_diffusivity_m2_s": effective_diffusivity_m2_s,
        "window_conductance_mol_per_s": window_conductance,
        "heater_convection_modeled": False,
        "cell_consumption_modeled": False,
        "sensor_coupling_mode": (
            "front/rear interface-adjacent gas-slab average weight sensitivity"
        ),
        "geometry_status": "CAD-derived voxel sensitivity; not fabrication validation",
    }
    return VoxelTransportSystem(
        matrix=matrix,
        boundary_drive=boundary_drive,
        coordinates_mm=coordinates,
        front_port_indices=front_indices,
        rear_port_indices=rear_indices,
        active_cell_count=len(active_locations),
        membrane_face_count=len(membrane_faces),
        geometric_gas_volume_cm3=geometric_volume_m3 * 1e6,
        modeled_gas_volume_cm3=volume_cm3,
        diagnostics=diagnostics,
    )


def simulate_voxel_step(
    config: ModelConfig,
    manifest: ExperimentManifest,
    domain: VoxelCandidateDomain,
    effective_diffusivity_m2_s: float,
    duration_s: float = 400.0,
    output_dt_s: float = 1.0,
    front_port_weight: float = 0.5,
    pressure_kpa: float = 101.325,
    temp_c: float = 50.0,
    final_o2_pct_wet: float = 20.95,
) -> tuple[pd.DataFrame, dict[str, object]]:
    gas_frame, diagnostics = simulate_voxel_gas_step(
        config,
        manifest,
        domain,
        effective_diffusivity_m2_s,
        duration_s,
        output_dt_s,
        pressure_kpa,
        temp_c,
        final_o2_pct_wet,
    )
    return apply_voxel_cell_response(
        config,
        gas_frame,
        diagnostics,
        front_port_weight,
        pressure_kpa,
        temp_c,
    )


def simulate_voxel_gas_step(
    config: ModelConfig,
    manifest: ExperimentManifest,
    domain: VoxelCandidateDomain,
    effective_diffusivity_m2_s: float,
    duration_s: float = 400.0,
    output_dt_s: float = 1.0,
    pressure_kpa: float = 101.325,
    temp_c: float = 50.0,
    final_o2_pct_wet: float = 20.95,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if config.gas.include_cell_consumption:
        # The sparse matrix-exponential solution is linear. Consumption is
        # negligible for the present air step but must not disappear silently.
        consumption_note = (
            "configured cell consumption omitted from linear voxel sensitivity"
        )
    else:
        consumption_note = "cell consumption disabled"
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration must be finite and positive")
    if not np.isfinite(output_dt_s) or not 0.0 < output_dt_s <= 1.0:
        raise ValueError("voxel output cadence must be within (0, 1] s")
    system = build_voxel_transport_system(
        config,
        manifest,
        domain,
        effective_diffusivity_m2_s,
        pressure_kpa,
        temp_c,
    )
    sample_count = int(np.floor(duration_s / output_dt_s)) + 1
    times = np.arange(sample_count, dtype=float) * output_dt_s
    gas_offset = expm_multiply(
        system.matrix,
        -np.ones(system.active_cell_count, dtype=float),
        start=0.0,
        stop=float(times[-1]),
        num=len(times),
        endpoint=True,
        traceA=float(system.matrix.diagonal().sum()),
    )
    normalized_gas = np.clip(1.0 + gas_offset, 0.0, 1.0)
    front = np.mean(normalized_gas[:, system.front_port_indices], axis=1)
    rear = np.mean(normalized_gas[:, system.rear_port_indices], axis=1)
    frame = pd.DataFrame(
        {
            "time_s": times,
            "o2_reference_pct_wet": final_o2_pct_wet,
            "o2_front_port_pct_wet": front * final_o2_pct_wet,
            "o2_rear_port_pct_wet": rear * final_o2_pct_wet,
        }
    )
    diagnostics = {
        **system.diagnostics,
        "cell_consumption_note": consumption_note,
        "pressure_kpa": pressure_kpa,
        "temp_c": temp_c,
        "duration_s": float(times[-1]),
        "output_dt_s": output_dt_s,
        "uncalibrated": True,
    }
    return frame, diagnostics


def apply_voxel_cell_response(
    config: ModelConfig,
    gas_frame: pd.DataFrame,
    diagnostics: dict[str, object],
    front_port_weight: float,
    pressure_kpa: float = 101.325,
    temp_c: float = 50.0,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not 0.0 <= front_port_weight <= 1.0:
        raise ValueError("front-port weight must be within [0, 1]")
    frame = gas_frame.copy()
    times = frame.time_s.to_numpy(dtype=float)
    if len(times) < 2 or not np.allclose(np.diff(times), np.diff(times)[0]):
        raise ValueError("voxel cell response requires a uniform output cadence")
    output_dt_s = float(times[1] - times[0])
    sampled_pct = front_port_weight * frame.o2_front_port_pct_wet.to_numpy(
        dtype=float
    ) + (1.0 - front_port_weight) * frame.o2_rear_port_pct_wet.to_numpy(dtype=float)
    oxygen_fraction = sampled_pct / 100.0
    if config.cell.dynamic_domain == "normalized_output":
        drive = np.asarray(
            [
                -np.log1p(
                    -_equivalent_fraction(config, value, pressure_kpa, strict=False)
                )
                for value in oxygen_fraction
            ]
        )
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
    currents = np.asarray(
        [
            _current_from_state(config, state, pressure_kpa, temp_c)
            for state in cell_state
        ]
    )
    probe = np.asarray(
        [
            inverse_signal(
                config,
                max(current, config.cell.i_zero_ma.require("cell.i_zero_ma")),
                pressure_kpa,
                temp_c,
            )
            * 100.0
            for current in currents
        ]
    )
    frame["o2_sampled_ports_pct_wet"] = sampled_pct
    frame["o2_probe_pct_wet"] = probe
    updated_diagnostics = {
        **diagnostics,
        "front_port_weight": front_port_weight,
    }
    return frame, updated_diagnostics


def monotonic_voxel_metrics(
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
                values[index - 1 : index + 1],
                times[index - 1 : index + 1],
            )
        )

    return {"t90_s": crossing(0.90), "settling_time_2pct_s": crossing(0.98)}
