#!/usr/bin/env python3
"""Generate claim-bounded figures for the paper CPU smoke benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence, cast

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import MultipleLocator, PercentFormatter  # noqa: E402


DEFAULT_ARTIFACT_DIR: Final = Path(
    "artifacts/test-results/2026-08-03/benchmark/authoritative-c"
)
DEFAULT_OUTPUT_DIR: Final = Path(
    "docs/experiments/figures/paper_cpu_smoke_v1_2026-08-03"
)
EXPECTED_EXPERIMENT_ID: Final = "paper_cpu_smoke_v1"
EXPECTED_COMPARISON_DESIGN: Final = "descriptive-unpaired-endogenous"
MODES: Final = ("baseline", "orchestra")
MODE_LABELS: Final = {
    "baseline": "Baseline contract reference",
    "orchestra": "ORCHESTRA mode (descriptive)",
}
MODE_COLORS: Final = {"baseline": "#59636E", "orchestra": "#0072B2"}
MODE_MARKERS: Final = {"baseline": "s", "orchestra": "o"}
METRICS: Final = ("S1_mean", "S2_mean", "S3_mean", "S4_mean", "Q_mean")
METRIC_LABELS: Final = {
    "S1_mean": "S1\nSignal fidelity",
    "S2_mean": "S2\nDirective compliance",
    "S3_mean": "S3\nAction coherence",
    "S4_mean": "S4\nTemporal stability",
    "Q_mean": "Q\nGeometric mean",
}
ACTIONS: Final = ("run", "sleep", "migrate", "throttle", "yield")
ACTION_LABELS: Final = {
    "run": "RUN",
    "sleep": "SLEEP",
    "migrate": "MIGRATE",
    "throttle": "THROTTLE",
    "yield": "YIELD",
}
ACTION_COLORS: Final = {
    "run": "#0072B2",
    "sleep": "#56B4E9",
    "migrate": "#009E73",
    "throttle": "#E69F00",
    "yield": "#CC79A7",
}
CLAIM_CAPTION: Final = (
    "Claim boundary: descriptive userspace observations; baseline is a contract "
    "reference.\nModes are unpaired/endogenous - no causal, kernel-scheduler, or "
    "general-performance inference."
)
FIGURE_DATE: Final = "2026-08-03"


@dataclass(frozen=True)
class Estimate:
    """One across-run estimate from processed summary.json."""

    n: int
    mean: float
    stdev: float
    ci95_lower: float
    ci95_upper: float


@dataclass(frozen=True)
class RunSummary:
    """Fields used from one validated invocation summary."""

    run_id: str
    mode: str
    repetition: int
    seed: int
    rows_after_warmup: int
    metrics: Mapping[str, float]
    action_fractions: Mapping[str, float]


@dataclass(frozen=True)
class PlotInputs:
    """Validated inputs and provenance required by the figures."""

    artifact_dir: Path
    experiment_id: str
    maturity_class: str
    comparison_design: str
    interpretation: str
    claim_boundary: str
    source_sha256: str
    binary_sha256: str
    estimates: Mapping[str, Mapping[str, Estimate]]
    runs: tuple[RunSummary, ...]
    input_hashes: Mapping[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_DIR,
        help=f"completed benchmark artifact (default: {DEFAULT_ARTIFACT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"figure destination (default: {DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(dict[str, object], value)


def require_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def require_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def require_int(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def require_float(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{context} must be finite")
    return result


def parse_csv_int(row: Mapping[str, str], name: str, run_id: str) -> int:
    try:
        return int(row[name])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{run_id}: invalid integer field {name!r}") from exc


def parse_csv_float(row: Mapping[str, str], name: str, run_id: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{run_id}: invalid numeric field {name!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{run_id}: {name!r} must be finite")
    return value


def load_run_summaries(path: Path) -> tuple[RunSummary, ...]:
    required = {
        "run_id",
        "mode",
        "repetition",
        "seed",
        "rows_after_warmup",
        *METRICS,
        *(f"{action}_action_fraction" for action in ACTIONS),
    }
    try:
        stream = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise ValueError(f"cannot read run summaries {path}: {exc}") from exc

    runs: list[RunSummary] = []
    with stream:
        reader = csv.DictReader(stream)
        header = set(reader.fieldnames or ())
        missing = sorted(required - header)
        if missing:
            raise ValueError(f"{path} is missing required columns: {missing}")
        for row_number, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"{path}:{row_number}: malformed field count")
            row = cast(Mapping[str, str], raw)
            run_id = row["run_id"]
            mode = row["mode"]
            if mode not in MODES:
                raise ValueError(f"{run_id}: unsupported mode {mode!r}")
            metrics = {name: parse_csv_float(row, name, run_id) for name in METRICS}
            actions = {
                action: parse_csv_float(row, f"{action}_action_fraction", run_id)
                for action in ACTIONS
            }
            for name, value in (*metrics.items(), *actions.items()):
                if value < 0.0 or value > 1.0:
                    raise ValueError(f"{run_id}: {name}={value} is outside [0, 1]")
            if not math.isclose(
                math.fsum(actions.values()), 1.0, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(f"{run_id}: action fractions do not sum to one")
            repetition = parse_csv_int(row, "repetition", run_id)
            seed = parse_csv_int(row, "seed", run_id)
            rows_after_warmup = parse_csv_int(row, "rows_after_warmup", run_id)
            if repetition < 1 or seed < 1 or rows_after_warmup < 1:
                raise ValueError(f"{run_id}: invalid run identity or observation count")
            runs.append(
                RunSummary(
                    run_id=run_id,
                    mode=mode,
                    repetition=repetition,
                    seed=seed,
                    rows_after_warmup=rows_after_warmup,
                    metrics=metrics,
                    action_fractions=actions,
                )
            )

    if not runs:
        raise ValueError(f"{path} contains no run summaries")
    if len({run.run_id for run in runs}) != len(runs):
        raise ValueError(f"{path} contains duplicate run_id values")
    return tuple(sorted(runs, key=lambda run: (run.repetition, MODES.index(run.mode))))


def load_estimates(summary: Mapping[str, object]) -> Mapping[str, Mapping[str, Estimate]]:
    modes = require_mapping(summary.get("modes"), "summary.modes")
    estimates: dict[str, Mapping[str, Estimate]] = {}
    for mode in MODES:
        mode_data = require_mapping(modes.get(mode), f"summary.modes.{mode}")
        metrics = require_mapping(mode_data.get("metrics"), f"summary.modes.{mode}.metrics")
        parsed: dict[str, Estimate] = {}
        for metric in METRICS:
            raw = require_mapping(metrics.get(metric), f"summary.{mode}.{metric}")
            estimate = Estimate(
                n=require_int(raw.get("n"), f"summary.{mode}.{metric}.n"),
                mean=require_float(raw.get("mean"), f"summary.{mode}.{metric}.mean"),
                stdev=require_float(raw.get("stdev"), f"summary.{mode}.{metric}.stdev"),
                ci95_lower=require_float(
                    raw.get("ci95_lower"), f"summary.{mode}.{metric}.ci95_lower"
                ),
                ci95_upper=require_float(
                    raw.get("ci95_upper"), f"summary.{mode}.{metric}.ci95_upper"
                ),
            )
            if not 0.0 <= estimate.mean <= 1.0:
                raise ValueError(f"summary.{mode}.{metric}.mean is outside [0, 1]")
            if not estimate.ci95_lower <= estimate.mean <= estimate.ci95_upper:
                raise ValueError(f"summary.{mode}.{metric} has an invalid confidence interval")
            parsed[metric] = estimate
        estimates[mode] = parsed
    return estimates


def validate_cross_file_consistency(
    runs: Sequence[RunSummary], estimates: Mapping[str, Mapping[str, Estimate]]
) -> None:
    repetition_sets: dict[str, set[int]] = {}
    for mode in MODES:
        mode_runs = [run for run in runs if run.mode == mode]
        if not mode_runs:
            raise ValueError(f"run summaries contain no {mode} invocations")
        repetition_sets[mode] = {run.repetition for run in mode_runs}
        for metric in METRICS:
            estimate = estimates[mode][metric]
            values = [run.metrics[metric] for run in mode_runs]
            if estimate.n != len(values):
                raise ValueError(
                    f"summary {mode}/{metric} n={estimate.n}, but run table has {len(values)}"
                )
            if not math.isclose(
                estimate.mean, statistics.fmean(values), rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError(f"summary mean disagrees with runs for {mode}/{metric}")
            expected_stdev = statistics.stdev(values) if len(values) > 1 else 0.0
            if not math.isclose(
                estimate.stdev, expected_stdev, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError(f"summary stdev disagrees with runs for {mode}/{metric}")
    if repetition_sets["baseline"] != repetition_sets["orchestra"]:
        raise ValueError("baseline and ORCHESTRA modes do not cover the same repetition labels")


def validate_hash(value: str, context: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{context} is not a lowercase SHA-256 digest")
    return value


def load_inputs(artifact_dir: Path) -> PlotInputs:
    summary_path = artifact_dir / "processed" / "summary.json"
    runs_path = artifact_dir / "processed" / "run_summaries.csv"
    result_path = artifact_dir / "benchmark_result.json"
    manifest_path = artifact_dir / "manifest.input.json"
    schema_path = artifact_dir / "metrics_schema.input.json"
    for path in (summary_path, runs_path, result_path, manifest_path, schema_path):
        if not path.is_file():
            raise ValueError(f"required benchmark input is missing: {path}")

    summary = load_json_object(summary_path)
    result = load_json_object(result_path)
    experiment_id = require_string(result.get("experiment_id"), "result.experiment_id")
    if experiment_id != EXPECTED_EXPERIMENT_ID:
        raise ValueError(f"unexpected experiment_id {experiment_id!r}")
    if result.get("status") != "complete":
        raise ValueError("benchmark_result status is not complete")
    expected_runs = require_int(result.get("expected_run_count"), "result.expected_run_count")
    validated_runs = require_int(
        result.get("validated_run_count"), "result.validated_run_count"
    )
    failed_runs = require_int(
        result.get("failed_or_excluded_run_count"), "result.failed_or_excluded_run_count"
    )
    if validated_runs != expected_runs or failed_runs != 0:
        raise ValueError("benchmark result is incomplete or contains excluded runs")

    comparison_design = require_string(
        result.get("comparison_design"), "result.comparison_design"
    )
    if comparison_design != EXPECTED_COMPARISON_DESIGN:
        raise ValueError(f"unsupported comparison design {comparison_design!r}")
    summary_design = require_string(summary.get("comparison_design"), "summary.comparison_design")
    if summary_design != comparison_design:
        raise ValueError("summary and benchmark result comparison designs disagree")

    source_start = validate_hash(
        require_string(result.get("source_sha256_start"), "result.source_sha256_start"),
        "result.source_sha256_start",
    )
    source_end = validate_hash(
        require_string(result.get("source_sha256_end"), "result.source_sha256_end"),
        "result.source_sha256_end",
    )
    binary_start = validate_hash(
        require_string(result.get("binary_sha256_start"), "result.binary_sha256_start"),
        "result.binary_sha256_start",
    )
    binary_end = validate_hash(
        require_string(result.get("binary_sha256_end"), "result.binary_sha256_end"),
        "result.binary_sha256_end",
    )
    if source_start != source_end or binary_start != binary_end:
        raise ValueError("source or binary changed during the benchmark")

    estimates = load_estimates(summary)
    runs = load_run_summaries(runs_path)
    if len(runs) != validated_runs:
        raise ValueError(
            f"run summary count {len(runs)} does not match validated count {validated_runs}"
        )
    validate_cross_file_consistency(runs, estimates)

    input_hashes = {
        "benchmark_result.json": sha256_file(result_path),
        "manifest.input.json": sha256_file(manifest_path),
        "metrics_schema.input.json": sha256_file(schema_path),
        "processed/summary.json": sha256_file(summary_path),
        "processed/run_summaries.csv": sha256_file(runs_path),
    }
    return PlotInputs(
        artifact_dir=artifact_dir.resolve(),
        experiment_id=experiment_id,
        maturity_class=require_string(result.get("maturity_class"), "result.maturity_class"),
        comparison_design=comparison_design,
        interpretation=require_string(summary.get("interpretation"), "summary.interpretation"),
        claim_boundary=require_string(result.get("claim_boundary"), "result.claim_boundary"),
        source_sha256=source_start,
        binary_sha256=binary_start,
        estimates=estimates,
        runs=runs,
        input_hashes=input_hashes,
    )


def configure_matplotlib() -> None:
    matplotlib.rcParams.update(
        {
            "axes.edgecolor": "#30343B",
            "axes.labelcolor": "#20242A",
            "axes.linewidth": 0.8,
            "axes.titleweight": "semibold",
            "figure.facecolor": "white",
            "font.family": "DejaVu Sans",
            "font.size": 10.0,
            "grid.alpha": 0.24,
            "grid.color": "#7F8790",
            "grid.linewidth": 0.7,
            "legend.frameon": False,
            "lines.linewidth": 1.8,
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "svg.hashsalt": "orchestra-paper-cpu-smoke-v1-2026-08-03",
            "xtick.color": "#30343B",
            "ytick.color": "#30343B",
        }
    )


def add_figure_header(fig: Figure, title: str, subtitle: str) -> None:
    fig.suptitle(title, x=0.075, y=0.965, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.075, 0.915, subtitle, ha="left", va="top", fontsize=9.5, color="#4C5560")
    fig.text(
        0.5,
        0.018,
        CLAIM_CAPTION,
        ha="center",
        va="bottom",
        fontsize=8.0,
        color="#4C5560",
        linespacing=1.35,
    )


def style_metric_axis(axis: Axes) -> None:
    axis.set_ylim(0.0, 1.08)
    axis.yaxis.set_major_locator(MultipleLocator(0.2))
    axis.grid(axis="y")
    axis.spines[["top", "right"]].set_visible(False)


def save_figure(fig: Figure, output_dir: Path, stem: str, title: str) -> tuple[Path, Path]:
    png_path = output_dir / f"{stem}.png"
    svg_path = output_dir / f"{stem}.svg"
    fig.savefig(
        png_path,
        dpi=200,
        metadata={
            "Software": "ORCHESTRA-OS plot_paper_cpu_smoke.py",
            "Title": title,
            "Description": CLAIM_CAPTION.replace("\n", " "),
        },
    )
    fig.savefig(
        svg_path,
        format="svg",
        metadata={
            "Title": title,
            "Description": CLAIM_CAPTION.replace("\n", " "),
            "Creator": "ORCHESTRA-OS plot_paper_cpu_smoke.py",
            "Date": FIGURE_DATE,
            "Format": "image/svg+xml",
        },
    )
    plt.close(fig)
    return png_path, svg_path


def plot_metric_means(inputs: PlotInputs, output_dir: Path) -> tuple[Path, Path]:
    title = "Coordination metrics across validated userspace runs"
    fig, axis = plt.subplots(figsize=(10.0, 6.1))
    add_figure_header(
        fig,
        title,
        "Run means with two-sided 95% t intervals (n=3 invocations per mode)",
    )
    x_positions = [float(index) for index in range(len(METRICS))]
    offsets = {"baseline": -0.13, "orchestra": 0.13}
    for mode in MODES:
        estimates = [inputs.estimates[mode][metric] for metric in METRICS]
        means = [estimate.mean for estimate in estimates]
        lower_errors = [estimate.mean - estimate.ci95_lower for estimate in estimates]
        upper_errors = [estimate.ci95_upper - estimate.mean for estimate in estimates]
        x_values = [position + offsets[mode] for position in x_positions]
        axis.errorbar(
            x_values,
            means,
            yerr=[lower_errors, upper_errors],
            color=MODE_COLORS[mode],
            marker=MODE_MARKERS[mode],
            markerfacecolor="white" if mode == "baseline" else MODE_COLORS[mode],
            markeredgewidth=1.5,
            markersize=7.5,
            capsize=5,
            elinewidth=1.6,
            linestyle="none",
            label=MODE_LABELS[mode],
            zorder=3,
        )
        for x_value, mean in zip(x_values, means, strict=True):
            axis.annotate(
                f"{mean:.3f}",
                (x_value, mean),
                xytext=(0, 9),
                textcoords="offset points",
                ha="center",
                fontsize=8.0,
                color=MODE_COLORS[mode],
            )

    style_metric_axis(axis)
    axis.set_ylabel("Mean score (0-1)")
    axis.set_xticks(x_positions, [METRIC_LABELS[metric] for metric in METRICS])
    axis.tick_params(axis="x", pad=8)
    axis.legend(loc="lower left", ncols=2, bbox_to_anchor=(0.0, 1.005))
    axis.text(
        0.995,
        0.025,
        "Error bars describe run-to-run uncertainty, not a mode-effect estimate.",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.0,
        color="#4C5560",
    )
    fig.subplots_adjust(left=0.09, right=0.97, top=0.80, bottom=0.20)
    return save_figure(fig, output_dir, "coordination_means_ci95", title)


def plot_run_variability(inputs: PlotInputs, output_dir: Path) -> tuple[Path, Path]:
    title = "Run-level coordination metric variability"
    fig, axes = plt.subplots(1, len(METRICS), figsize=(13.2, 5.3), sharey=True)
    add_figure_header(
        fig,
        title,
        "Each point is one validated invocation mean after the declared warm-up",
    )
    repetitions = sorted({run.repetition for run in inputs.runs})
    seeds_by_repetition: dict[int, int] = {}
    for repetition in repetitions:
        seeds = {run.seed for run in inputs.runs if run.repetition == repetition}
        if len(seeds) != 1:
            raise ValueError(f"repetition {repetition} does not have one declared seed")
        seeds_by_repetition[repetition] = seeds.pop()

    for axis, metric in zip(axes, METRICS, strict=True):
        for mode in MODES:
            mode_runs = sorted(
                (run for run in inputs.runs if run.mode == mode),
                key=lambda run: run.repetition,
            )
            axis.plot(
                [run.repetition for run in mode_runs],
                [run.metrics[metric] for run in mode_runs],
                color=MODE_COLORS[mode],
                marker=MODE_MARKERS[mode],
                markerfacecolor="white" if mode == "baseline" else MODE_COLORS[mode],
                markeredgewidth=1.3,
                markersize=6.5,
                linestyle="none",
                label=MODE_LABELS[mode],
            )
        style_metric_axis(axis)
        axis.set_title(METRIC_LABELS[metric], fontsize=10.0)
        axis.set_xticks(repetitions, [f"R{repetition}" for repetition in repetitions])
        axis.set_xlabel("Invocation")
    axes[0].set_ylabel("Per-run mean score (0-1)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.07, 0.875), ncols=2)
    seed_text = " · ".join(
        f"R{repetition}: seed {seeds_by_repetition[repetition]}"
        for repetition in repetitions
    )
    fig.text(0.5, 0.105, seed_text, ha="center", va="center", fontsize=8.0, color="#4C5560")
    fig.subplots_adjust(left=0.065, right=0.985, top=0.76, bottom=0.23, wspace=0.18)
    return save_figure(fig, output_dir, "coordination_per_run", title)


def plot_action_mix(inputs: PlotInputs, output_dir: Path) -> tuple[Path, Path]:
    title = "Action selection mix by validated invocation"
    fig, axis = plt.subplots(figsize=(11.5, 6.4))
    add_figure_header(
        fig,
        title,
        "Fractions are calculated within each run after the declared warm-up",
    )
    runs = list(inputs.runs)
    x_values: list[float] = []
    tick_labels: list[str] = []
    for run in runs:
        group_origin = float((run.repetition - 1) * 3)
        mode_offset = 0.0 if run.mode == "baseline" else 0.9
        x_values.append(group_origin + mode_offset)
        mode_label = "Reference" if run.mode == "baseline" else "ORCHESTRA"
        tick_labels.append(f"R{run.repetition}\n{mode_label}")

    bottoms = [0.0] * len(runs)
    for action in ACTIONS:
        values = [run.action_fractions[action] for run in runs]
        axis.bar(
            x_values,
            values,
            width=0.72,
            bottom=bottoms,
            color=ACTION_COLORS[action],
            edgecolor="white",
            linewidth=0.7,
            label=ACTION_LABELS[action],
        )
        for x_value, value, bottom in zip(x_values, values, bottoms, strict=True):
            if value >= 0.095:
                axis.text(
                    x_value,
                    bottom + value / 2.0,
                    f"{value:.0%}",
                    ha="center",
                    va="center",
                    fontsize=8.0,
                    color="white" if action == "run" else "#111820",
                    fontweight="semibold",
                )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values, strict=True)]

    axis.set_ylim(0.0, 1.0)
    axis.yaxis.set_major_locator(MultipleLocator(0.2))
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    axis.grid(axis="y")
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.set_ylabel("Fraction of recorded actions")
    axis.set_xticks(x_values, tick_labels)
    axis.tick_params(axis="x", pad=8)
    axis.legend(loc="lower left", bbox_to_anchor=(0.0, 1.005), ncols=5)
    for repetition in sorted({run.repetition for run in runs})[:-1]:
        axis.axvline(float(repetition * 3) - 1.05, color="#D4D8DD", linewidth=0.8)
    fig.subplots_adjust(left=0.09, right=0.975, top=0.80, bottom=0.21)
    return save_figure(fig, output_dir, "action_mix_per_run", title)


def write_readme(inputs: PlotInputs, output_dir: Path, figures: Sequence[Path]) -> Path:
    generator_path = Path(__file__).resolve()
    output_hashes = {path.name: sha256_file(path) for path in sorted(figures)}
    lines = [
        "# Paper CPU smoke v1 figures - 2026-08-03",
        "",
        "These figures were generated from the completed, validated artifact "
        f"`{inputs.artifact_dir}` using "
        "`tools/plotting/plot_paper_cpu_smoke.py`. The plotting script reads the "
        "processed tables and provenance only; it does not modify raw benchmark data.",
        "",
        "## Interpretation boundary",
        "",
        f"- Maturity class: **{inputs.maturity_class}**.",
        f"- Comparison design: `{inputs.comparison_design}`.",
        f"- Artifact claim boundary: {inputs.claim_boundary}",
        f"- Processed-summary interpretation: {inputs.interpretation}",
        "- The baseline is an instrumented, observed-state reactive **contract "
        "reference**, not a causal control group. Error bars and horizontal placement "
        "must not be interpreted as a treatment-effect estimate.",
        "- Each plotted run statistic uses one validated invocation after the "
        "declared warm-up. There are three invocations per mode.",
        "",
        "## Captions",
        "",
        "1. **Coordination means and 95% CI.** Across-run means for S1-S4 and the "
        "corrected coordination index `Q = (S1 × S2 × S3 × S4)^(1/4)`. Error bars "
        "are the processed two-sided 95% t intervals over three invocation means "
        "per mode. Baseline values characterize the contract reference; the figure "
        "does not estimate a mode effect.",
        "2. **Per-run coordination variability.** S1-S4 and Q invocation means for "
        "each repetition and declared seed. Points are independent invocation "
        "summaries; their horizontal placement identifies the run and does not "
        "encode a sequence, trend, pairing, or causal comparison.",
        "3. **Action mix by run and mode.** Post-warm-up fractions of canonical "
        "`RUN`, `SLEEP`, `MIGRATE`, `THROTTLE`, and `YIELD` actions for each "
        "validated invocation. The bars report observed policy behavior, not Linux "
        "kernel dispatch shares.",
        "",
        "## Source integrity",
        "",
        f"- Experiment ID: `{inputs.experiment_id}`",
        f"- Benchmark source SHA-256: `{inputs.source_sha256}`",
        f"- Benchmark binary SHA-256: `{inputs.binary_sha256}`",
        f"- Plot generator SHA-256: `{sha256_file(generator_path)}`",
    ]
    for name, digest in sorted(inputs.input_hashes.items()):
        lines.append(f"- `{name}` SHA-256: `{digest}`")
    lines.extend(["", "## Generated files", ""])
    for name, digest in sorted(output_hashes.items()):
        lines.append(f"- `{name}` SHA-256: `{digest}`")
    lines.extend(
        [
            "",
            f"Generated with Matplotlib `{matplotlib.__version__}` using a fixed SVG "
            "hash salt and fixed metadata date for deterministic output.",
            "Pinned visualization/report dependencies are listed in "
            "`tools/requirements-visualization.txt`.",
            "",
        ]
    )
    readme_path = output_dir / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    return readme_path


def main() -> int:
    args = parse_args()
    artifact_dir = cast(Path, args.artifact_dir).resolve()
    output_dir = cast(Path, args.output_dir).resolve()
    inputs = load_inputs(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()
    generated: list[Path] = []
    generated.extend(plot_metric_means(inputs, output_dir))
    generated.extend(plot_run_variability(inputs, output_dir))
    generated.extend(plot_action_mix(inputs, output_dir))
    readme = write_readme(inputs, output_dir, generated)
    print(f"validated artifact: {artifact_dir}")
    for path in (*generated, readme):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
