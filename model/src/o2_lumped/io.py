from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ExperimentManifest

COMMON_COLUMNS = {"time_s", "o2_reference_pct_wet", "pressure_reference_kpa", "temp_ambient_c"}
STAGE_COLUMNS = {
    "static": {"cell_current_mA"},
    "thermal": {"heater_power_w", "temp_block_c"},
    "bare": set(),
    "carrier": set(),
    "window": set(),
    "validation": set(),
}


def load_experiment_frame(manifest: ExperimentManifest) -> pd.DataFrame:
    path = Path(manifest.csv_path)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    required = set(COMMON_COLUMNS) | STAGE_COLUMNS[manifest.assembly_stage]
    missing = required - set(frame.columns)
    if manifest.role != "simulation" and manifest.assembly_stage in {"bare", "carrier", "window", "validation"}:
        if not ({"cell_current_mA", "o2_probe_pct"} & set(frame.columns)):
            missing.add("cell_current_mA or o2_probe_pct")
    if missing:
        raise ValueError(f"{manifest.experiment_id}: missing required columns: {sorted(missing)}")
    if len(frame) < 2:
        raise ValueError(f"{manifest.experiment_id}: at least two rows are required")
    if frame.isna().any().any():
        bad = frame.columns[frame.isna().any()].tolist()
        raise ValueError(f"{manifest.experiment_id}: missing values in {bad}")
    numeric = frame.select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"{manifest.experiment_id}: all numeric inputs must be finite")
    times = frame["time_s"].to_numpy(dtype=float)
    if not np.all(np.diff(times) > 0):
        raise ValueError(f"{manifest.experiment_id}: time_s must be strictly increasing")
    _check_range(frame, "o2_reference_pct_wet", 0.0, 100.0)
    _check_range(frame, "pressure_reference_kpa", 1.0, 200.0)
    if "rh_ambient_pct" in frame:
        _check_range(frame, "rh_ambient_pct", 0.0, 100.0)
    _check_range(frame, "temp_ambient_c", -80.0, 80.0)
    if "temp_inlet_c" in frame:
        _check_range(frame, "temp_inlet_c", -80.0, 80.0)
    if "heater_power_w" in frame and (frame["heater_power_w"] < 0).any():
        raise ValueError(f"{manifest.experiment_id}: heater_power_w must be nonnegative")
    return frame


def resample_input_frame(frame: pd.DataFrame, dt_s: float) -> pd.DataFrame:
    """Resample environmental references linearly and actuator commands by zero-order hold."""
    if not np.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("resampling interval must be finite and positive")
    old_t = frame["time_s"].to_numpy(dtype=float)
    new_t = np.arange(old_t[0], old_t[-1] + dt_s * 0.5, dt_s)
    result: dict[str, np.ndarray] = {"time_s": new_t}
    held = {"heater_power_w", "gas_command_pct"}
    for column in frame.columns:
        if column == "time_s":
            continue
        values = frame[column].to_numpy()
        if column in held:
            indices = np.searchsorted(old_t, new_t, side="right") - 1
            indices = np.clip(indices, 0, len(old_t) - 1)
            result[column] = values[indices]
        elif np.issubdtype(values.dtype, np.number):
            result[column] = np.interp(new_t, old_t, values.astype(float))
    return pd.DataFrame(result)


def _check_range(frame: pd.DataFrame, column: str, lower: float, upper: float) -> None:
    if ((frame[column] < lower) | (frame[column] > upper)).any():
        raise ValueError(f"{column} must be within [{lower}, {upper}]")


def prepare_output_dir(path: str | Path, overwrite: bool) -> Path:
    output = Path(path)
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory is not empty: {output}; pass --overwrite")
    output.mkdir(parents=True, exist_ok=True)
    return output
