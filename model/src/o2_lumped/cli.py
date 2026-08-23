from __future__ import annotations

import argparse
import sys

from .config import load_config, load_manifest, write_json
from .fitting import fit_stage
from .io import load_experiment_frame, prepare_output_dir, resample_input_frame
from .metrics import analyze_steps
from .physics import simulate
from .plotting import (
    plot_prototype_frontier,
    plot_prototype_summary,
    plot_simulation,
    plot_sweep,
    plot_voxel_sensitivity,
)
from .prototype import (
    candidate_config,
    load_prototype_study,
    render_prototype_report,
    run_prototype_study,
)
from .sweeps import load_sweep_manifest, run_sweep
from .voxel_study import load_voxel_study, render_voxel_report, run_voxel_study


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="o2-lumped", description="Rev-A lumped O2 probe model")
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate_parser = subparsers.add_parser("simulate", help="simulate one experiment")
    _common_output_arguments(simulate_parser)
    simulate_parser.add_argument("--config", required=True)
    simulate_parser.add_argument("--experiment", required=True)

    fit_parser = subparsers.add_parser("fit", help="fit one staged calibration model")
    _common_output_arguments(fit_parser)
    fit_parser.add_argument("--config", required=True)
    fit_parser.add_argument("--stage", choices=["static", "thermal", "bare", "access", "window"], required=True)
    fit_parser.add_argument("--experiments", nargs="+", required=True)
    fit_parser.add_argument("--bootstrap", type=int, default=200)
    fit_parser.add_argument("--reportable", action="store_true", help="request at least 1000 bootstrap refits")
    fit_parser.add_argument("--seed", type=int, default=431)

    sweep_parser = subparsers.add_parser("sweep", help="run a one- or two-axis design sweep")
    _common_output_arguments(sweep_parser)
    sweep_parser.add_argument("--config", required=True)
    sweep_parser.add_argument("--sweep", required=True)

    prototype_parser = subparsers.add_parser(
        "prototype", help="evaluate prototype response geometry sensitivity"
    )
    _common_output_arguments(prototype_parser)
    prototype_parser.add_argument("--config", required=True)
    prototype_parser.add_argument("--study", required=True)

    voxel_parser = subparsers.add_parser(
        "voxel", help="evaluate CAD-derived 3-D candidate transport sensitivity"
    )
    _common_output_arguments(voxel_parser)
    voxel_parser.add_argument("--config", required=True)
    voxel_parser.add_argument("--study", required=True)
    return parser


def _common_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite", action="store_true")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "simulate":
            _simulate_command(args)
        elif args.command == "fit":
            _fit_command(args)
        elif args.command == "sweep":
            _sweep_command(args)
        elif args.command == "prototype":
            _prototype_command(args)
        elif args.command == "voxel":
            _voxel_command(args)
        else:
            raise AssertionError(args.command)
        return 0
    except Exception as exc:
        print(f"o2-lumped: error: {exc}", file=sys.stderr)
        return 2


def _simulate_command(args) -> None:
    output = prepare_output_dir(args.out, args.overwrite)
    config = load_config(args.config)
    manifest = load_manifest(args.experiment)
    inputs = load_experiment_frame(manifest)
    if manifest.role == "simulation":
        inputs = resample_input_frame(inputs, config.solver.max_step_s)
    result = simulate(config, manifest, inputs)
    frame = result.frame
    if "o2_probe_pct" in inputs:
        frame["o2_probe_observed_pct"] = inputs["o2_probe_pct"].to_numpy()
    if "cell_current_mA" in inputs:
        frame["cell_current_observed_mA"] = inputs["cell_current_mA"].to_numpy()
    metrics = analyze_steps(frame, manifest.step_windows)
    frame.to_csv(output / "timeseries.csv", index=False)
    summary = {
        **config.resolved_metadata(),
        "experiment_id": manifest.experiment_id,
        "diagnostics": result.diagnostics,
        "steps": metrics,
    }
    write_json(output / "summary.json", summary)
    title = f"{manifest.experiment_id}"
    if config.is_uncalibrated:
        title = "UNCALIBRATED — " + title
        (output / "UNCALIBRATED.txt").write_text(
            "This result uses assumed or sensitivity-only parameters and is not a calibrated prediction.\n"
        )
    plot_simulation(frame, output / "response.png", title)


def _fit_command(args) -> None:
    output = prepare_output_dir(args.out, args.overwrite)
    config = load_config(args.config)
    manifests = [load_manifest(path) for path in args.experiments]
    bootstrap = max(args.bootstrap, 1200) if args.reportable else args.bootstrap
    if bootstrap < 0:
        raise ValueError("--bootstrap must be nonnegative")
    result = fit_stage(config, manifests, args.stage, bootstrap, args.seed)
    write_json(output / "fit_report.json", result.report)
    if result.report.get("identifiable"):
        write_json(output / "candidate_config.json", result.config.model_dump(mode="json"))
    else:
        (output / "FIT_NOT_IDENTIFIABLE.txt").write_text(
            "The fitted model was rank-deficient or hit parameter bounds; no candidate configuration was emitted.\n"
        )


def _sweep_command(args) -> None:
    output = prepare_output_dir(args.out, args.overwrite)
    config = load_config(args.config)
    sweep = load_sweep_manifest(args.sweep)
    frame = run_sweep(config, sweep)
    frame.to_csv(output / "sweep.csv", index=False)
    axes = [axis.parameter for axis in sweep.axes]
    plot_sweep(frame, output / "sweep.png", axes[0], axes[1] if len(axes) == 2 else None, sweep.metric)
    write_json(output / "summary.json", {
        **config.resolved_metadata(),
        "axes": [axis.model_dump(mode="json") for axis in sweep.axes],
        "metric": sweep.metric,
        "rows": len(frame),
    })
    if config.is_uncalibrated:
        (output / "UNCALIBRATED.txt").write_text(
            "This sweep uses assumed or sensitivity-only parameters and is not a calibrated prediction.\n"
        )


def _prototype_command(args) -> None:
    output = prepare_output_dir(args.out, args.overwrite)
    config = load_config(args.config)
    study = load_prototype_study(args.study)
    results = run_prototype_study(config, study)
    results.cases.to_csv(output / "prototype_cases.csv", index=False)
    results.summary.to_csv(output / "design_summary.csv", index=False)
    results.frontier.to_csv(output / "feasible_frontier.csv", index=False)
    results.thermal.to_csv(output / "thermal_sensitivity.csv", index=False)
    results.nonlinear_verification.to_csv(output / "nonlinear_verification.csv", index=False)
    results.axial_diffusion_sensitivity.to_csv(
        output / "axial_diffusion_sensitivity.csv", index=False
    )
    plot_prototype_summary(results.summary, output / "response_envelope.png", study.settling_limit_s)
    plot_prototype_frontier(results.frontier, results.summary, output / "geometry_frontier.png")
    write_json(
        output / "candidate_sensitivity_config.json",
        candidate_config(config, results.recommended).model_dump(mode="json"),
    )
    (output / "prototype_report.md").write_text(
        render_prototype_report(config, study, results)
    )
    (output / "UNCALIBRATED.txt").write_text(
        "Prototype geometry results are sensitivity cases, not calibrated compost predictions.\n"
    )


def _voxel_command(args) -> None:
    output = prepare_output_dir(args.out, args.overwrite)
    config = load_config(args.config)
    study = load_voxel_study(args.study)
    results = run_voxel_study(config, study)
    results.cases.to_csv(output / "voxel_cases.csv", index=False)
    results.summary.to_csv(output / "voxel_summary.csv", index=False)
    (output / "voxel_report.md").write_text(render_voxel_report(study, results))
    plot_voxel_sensitivity(
        results.cases,
        output / "voxel_sensitivity.png",
        study.settling_limit_s,
    )
    (output / "UNCALIBRATED.txt").write_text(
        "3-D voxel results are CAD-derived sensitivity cases, not calibrated compost predictions.\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
