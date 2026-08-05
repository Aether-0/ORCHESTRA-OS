#!/usr/bin/env python3
"""Render the evidence-gated ORCHESTRA-OS path to a release decision.

This is a roadmap visualization, not a completion or schedule chart.  The
labels deliberately distinguish existing evidence from work-package exit
gates that have not yet been passed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


NAVY = "#16324F"
TEAL = "#137C8B"
LIGHT_TEAL = "#DCEFF1"
AMBER = "#D98E04"
LIGHT_AMBER = "#FFF1CF"
LIGHT_GRAY = "#EFF2F5"
DARK_GRAY = "#46535F"
RED = "#A53A3A"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the ORCHESTRA-OS release-readiness path."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/operations/figures"),
        help="Directory for PNG and SVG outputs.",
    )
    return parser.parse_args()


def add_stage(
    axis: plt.Axes,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    detail: str,
    status: str,
    facecolor: str,
    edgecolor: str,
) -> None:
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.025",
        linewidth=1.4,
        facecolor=facecolor,
        edgecolor=edgecolor,
    )
    axis.add_patch(box)
    axis.text(
        x + 0.04,
        y + height - 0.12,
        title,
        color=NAVY,
        fontsize=10.2,
        fontweight="bold",
        va="top",
    )
    axis.text(
        x + 0.04,
        y + height - 0.34,
        detail,
        color=DARK_GRAY,
        fontsize=8.1,
        linespacing=1.25,
        va="top",
    )
    axis.text(
        x + 0.04,
        y + 0.08,
        status,
        color=edgecolor,
        fontsize=7.7,
        fontweight="bold",
        va="bottom",
    )


def render(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / "release_readiness_path.png"
    svg_path = output_dir / "release_readiness_path.svg"

    stages = [
        (
            "Current evidence",
            "Paper simulation + selected\nuserspace WP2-WP6 mechanics\n+ one bounded smoke campaign",
            "USERSPACE-VALIDATED ONLY",
            LIGHT_TEAL,
            TEAL,
        ),
        (
            "Kernel foundation",
            "WP1 insertion point, class\nprecedence, boot, recovery,\nand fallback selftests",
            "EXIT GATE REQUIRED",
            LIGHT_AMBER,
            AMBER,
        ),
        (
            "Trusted local loop",
            "WP2-WP6 kernel signal bus,\npredictor, adaptive policy,\ncontrol, and tracepoints",
            "EXIT GATES REQUIRED",
            LIGHT_GRAY,
            DARK_GRAY,
        ),
        (
            "Controlled evidence",
            "WP7 identical workloads,\nrepeated runs, uncertainty,\ntails, fairness, and overhead",
            "EXIT GATE REQUIRED",
            LIGHT_GRAY,
            DARK_GRAY,
        ),
        (
            "Scale + resilience",
            "WP8 hierarchy and NUMA;\nWP9 attacks, faults, recovery,\nand long-duration reliability",
            "EXIT GATES REQUIRED",
            LIGHT_GRAY,
            DARK_GRAY,
        ),
        (
            "Release decision",
            "WP10 optimization, stable\nconfiguration, operations,\nrollback, and formal review",
            "NO-GO UNTIL ALL GATES PASS",
            "#F8E3E3",
            RED,
        ),
    ]

    matplotlib.rcParams["svg.hashsalt"] = "orchestra-os-release-readiness-v1"
    figure, axis = plt.subplots(figsize=(15.2, 5.4), constrained_layout=True)
    figure.patch.set_facecolor("white")
    axis.set_xlim(0, 15.2)
    axis.set_ylim(0, 5.4)
    axis.axis("off")

    axis.text(
        0.2,
        5.06,
        "ORCHESTRA-OS: evidence-gated path to a release decision",
        color=NAVY,
        fontsize=17,
        fontweight="bold",
        va="top",
    )
    axis.text(
        0.2,
        4.66,
        "Stages are dependency gates, not elapsed time or percent complete. A version label cannot replace evidence.",
        color=DARK_GRAY,
        fontsize=10,
        va="top",
    )

    width = 2.18
    height = 2.62
    gap = 0.29
    start_x = 0.2
    y = 1.18
    for index, (title, detail, status, fill, edge) in enumerate(stages):
        x = start_x + index * (width + gap)
        add_stage(
            axis,
            x=x,
            y=y,
            width=width,
            height=height,
            title=title,
            detail=detail,
            status=status,
            facecolor=fill,
            edgecolor=edge,
        )
        if index < len(stages) - 1:
            arrow = FancyArrowPatch(
                (x + width + 0.035, y + height / 2),
                (x + width + gap - 0.035, y + height / 2),
                arrowstyle="-|>",
                mutation_scale=13,
                linewidth=1.2,
                color=DARK_GRAY,
            )
            axis.add_patch(arrow)

    axis.text(
        0.2,
        0.66,
        "Release meaning: Deployment-ready only after correctness, safety, security, performance, reliability, reproducibility, observability, and operational gates pass.",
        color=NAVY,
        fontsize=9.4,
        fontweight="bold",
        va="top",
    )
    axis.text(
        0.2,
        0.31,
        "Current smoke results guide engineering priorities; they do not establish kernel scheduling benefit, causal performance, hard-real-time behavior, or production security.",
        color=DARK_GRAY,
        fontsize=8.8,
        va="top",
    )

    figure.savefig(
        png_path,
        dpi=220,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "ORCHESTRA-OS plot_release_readiness.py"},
    )
    figure.savefig(
        svg_path,
        bbox_inches="tight",
        facecolor="white",
        metadata={
            "Creator": "ORCHESTRA-OS plot_release_readiness.py",
            "Date": "2026-08-03",
        },
    )
    plt.close(figure)
    return png_path, svg_path


def main() -> int:
    args = parse_args()
    png_path, svg_path = render(args.output_dir)
    print(png_path)
    print(svg_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
