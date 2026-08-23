from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_simulation(frame: pd.DataFrame, output: Path, title: str) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    axes[0].plot(frame.time_s, frame.o2_reference_pct_wet, label="External reference", linestyle="--")
    axes[0].plot(frame.time_s, frame.o2_plenum_pct_wet, label="Plenum")
    if not (frame.o2_access_pct_wet == frame.o2_plenum_pct_wet).all():
        axes[0].plot(frame.time_s, frame.o2_access_pct_wet, label="Access state")
    axes[0].plot(frame.time_s, frame.o2_probe_pct_wet, label="Probe output")
    if "o2_probe_observed_pct" in frame:
        axes[0].scatter(frame.time_s, frame.o2_probe_observed_pct, label="Observed", s=8, alpha=0.7)
    axes[0].set_ylabel("O₂ (% wet basis)")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.25)

    axes[1].plot(frame.time_s, frame.temp_ambient_c, label="Ambient")
    axes[1].plot(frame.time_s, frame.temp_block_c, label="Block")
    if frame.temp_membrane_qs_c.notna().any():
        axes[1].plot(frame.time_s, frame.temp_membrane_qs_c, label="Membrane (quasi-steady)")
    power_axis = axes[1].twinx()
    power_axis.step(frame.time_s, frame.heater_applied_w, label="Heater", color="#c45a23", where="post")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Temperature (°C)")
    power_axis.set_ylabel("Power (W)")
    axes[1].grid(alpha=0.25)
    lines, labels = axes[1].get_legend_handles_labels()
    lines2, labels2 = power_axis.get_legend_handles_labels()
    axes[1].legend(lines + lines2, labels + labels2, loc="best")
    figure.suptitle(title)
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)


def plot_sweep(frame: pd.DataFrame, output: Path, x_name: str, y_name: str | None, metric: str) -> None:
    figure, axis = plt.subplots(figsize=(8, 5))
    if y_name is None:
        axis.plot(frame[x_name], frame[metric], marker="o")
        axis.set_ylabel(metric)
    else:
        pivot = frame.pivot(index=y_name, columns=x_name, values=metric)
        image = axis.imshow(
            pivot.to_numpy(), origin="lower", aspect="auto",
            extent=[pivot.columns.min(), pivot.columns.max(), pivot.index.min(), pivot.index.max()],
        )
        figure.colorbar(image, ax=axis, label=metric)
        axis.set_ylabel(y_name)
    axis.set_xlabel(x_name)
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)


def plot_prototype_summary(summary: pd.DataFrame, output: Path, settling_limit_s: float) -> None:
    figure, axis = plt.subplots(figsize=(9, 5))
    positions = range(len(summary))
    axis.bar(positions, summary["worst_studied_settling_time_2pct_s"], color="#b05f3c")
    axis.scatter(
        positions,
        summary["nominal_dry_no_access_settling_time_2pct_s"],
        color="#245f74",
        label="Nominal dry, no-access well-mixed estimate",
        zorder=3,
    )
    axis.axhline(settling_limit_s, color="#8b1e2d", linestyle="--", label=f"{settling_limit_s:g} s limit")
    axis.set_xticks(list(positions), summary["design"], rotation=18, ha="right")
    axis.set_ylabel("2% settling time (s)")
    axis.set_title("UNCALIBRATED well-mixed volume/area screening")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="best")
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)


def plot_prototype_frontier(frontier: pd.DataFrame, summary: pd.DataFrame, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.plot(
        frontier["free_area_mm2"],
        frontier["maximum_volume_cm3_at_limit"],
        marker="o",
        label="Well-mixed screening frontier",
    )
    axis.scatter(
        summary["free_area_nominal_mm2"],
        summary["volume_nominal_cm3"],
        color="#b05f3c",
        zorder=3,
    )
    for row in summary.itertuples(index=False):
        axis.annotate(row.design, (row.free_area_nominal_mm2, row.volume_nominal_cm3), xytext=(5, 4), textcoords="offset points", fontsize=8)
    axis.set_xlabel("Supported free membrane area (mm²)")
    axis.set_ylabel("Effective gas volume (cm³)")
    axis.set_title("Well-mixed volume/area frontier — screening only")
    axis.grid(alpha=0.25)
    axis.legend(loc="best")
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)


def plot_voxel_sensitivity(
    cases: pd.DataFrame, output: Path, settling_limit_s: float
) -> None:
    figure, axis = plt.subplots(figsize=(9, 5))
    for (scenario, weight), selected in cases.groupby(
        ["scenario", "front_port_weight"], sort=False
    ):
        axis.plot(
            selected["effective_diffusivity_m2_s"] * 1e5,
            selected["probe_settling_time_2pct_s"],
            marker="o",
            label=f"{scenario}; front weight={weight:g}",
        )
    axis.axhline(
        settling_limit_s,
        color="#8b1e2d",
        linestyle="--",
        label=f"{settling_limit_s:g} s limit",
    )
    axis.set_xlabel("Effective diffusivity (×10⁻⁵ m²/s)")
    axis.set_ylabel("Probe 2% settling time (s)")
    axis.set_title("UNCALIBRATED 3-D voxel geometry sensitivity")
    axis.grid(alpha=0.25)
    axis.legend(loc="best", fontsize=7)
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)
