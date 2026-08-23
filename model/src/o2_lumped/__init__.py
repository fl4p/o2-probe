"""Lumped thermal and gas-transport model for the Rev-A oxygen probe."""

from .config import MODEL_VERSION, ModelConfig, load_config
from .physics import SimulationResult, simulate
from .planar import PlanarCandidateDomain, simulate_planar_step
from .spatial import AxialDomain, simulate_axial_diffusion
from .voxel import VoxelCandidateDomain, simulate_voxel_step

__all__ = [
    "MODEL_VERSION",
    "AxialDomain",
    "ModelConfig",
    "PlanarCandidateDomain",
    "SimulationResult",
    "VoxelCandidateDomain",
    "load_config",
    "simulate",
    "simulate_axial_diffusion",
    "simulate_planar_step",
    "simulate_voxel_step",
]
