"""Non-invasive Matplotlib instrumentation for the direct descriptive reproduction.

When FIGURE_CAPTURE_DIR is set, replace pyplot.show() with a deterministic capture
that saves each open figure as PNG plus a compact JSON description of the plotted
artists. The upstream analysis scripts are not edited. Statistical computations and
console output are untouched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

_CAPTURE_DIR = os.environ.get("FIGURE_CAPTURE_DIR")
if _CAPTURE_DIR:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Wedge

    _capture_dir = Path(_CAPTURE_DIR)
    _capture_dir.mkdir(parents=True, exist_ok=True)
    _prefix = os.environ.get("FIGURE_CAPTURE_PREFIX", "figure")
    _counter = 0
    _original_show = plt.show

    def _finite(value: Any) -> Any:
        try:
            number = float(value)
        except Exception:
            return str(value)
        if number != number or number in (float("inf"), float("-inf")):
            return str(number)
        return number

    def _axis_record(ax: Any) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "title": ax.get_title(),
            "xlabel": ax.get_xlabel(),
            "ylabel": ax.get_ylabel(),
            "x_ticklabels": [tick.get_text() for tick in ax.get_xticklabels()],
            "y_ticklabels": [tick.get_text() for tick in ax.get_yticklabels()],
            "legend_labels": [],
            "rectangles": [],
            "wedges": [],
            "texts": [],
        }
        legend = ax.get_legend()
        if legend is not None:
            record["legend_labels"] = [text.get_text() for text in legend.get_texts()]
        for patch in ax.patches:
            if isinstance(patch, Wedge):
                record["wedges"].append(
                    {
                        "theta1": _finite(patch.theta1),
                        "theta2": _finite(patch.theta2),
                        "fraction": _finite((patch.theta2 - patch.theta1) / 360.0),
                        "center": [_finite(v) for v in patch.center],
                        "radius": _finite(patch.r),
                    }
                )
            elif isinstance(patch, Rectangle):
                record["rectangles"].append(
                    {
                        "x": _finite(patch.get_x()),
                        "y": _finite(patch.get_y()),
                        "width": _finite(patch.get_width()),
                        "height": _finite(patch.get_height()),
                        "visible": bool(patch.get_visible()),
                    }
                )
        for text in ax.texts:
            record["texts"].append(
                {
                    "text": text.get_text(),
                    "x": _finite(text.get_position()[0]),
                    "y": _finite(text.get_position()[1]),
                }
            )
        return record

    def _capturing_show(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        global _counter
        figure_numbers: List[int] = list(plt.get_fignums())
        for figure_number in figure_numbers:
            _counter += 1
            fig = plt.figure(figure_number)
            stem = f"{_prefix}_{_counter:02d}"
            png_path = _capture_dir / f"{stem}.png"
            json_path = _capture_dir / f"{stem}.json"
            fig.savefig(
                png_path,
                dpi=200,
                bbox_inches="tight",
                metadata={
                    "Title": "Direct descriptive reproduction figure",
                    "Software": "Matplotlib capture instrumentation",
                },
            )
            payload = {
                "schema_version": "1.0",
                "instrumentation": "pyplot.show capture; upstream script unchanged",
                "figure_number": int(figure_number),
                "size_inches": [_finite(v) for v in fig.get_size_inches()],
                "dpi": _finite(fig.dpi),
                "axes": [_axis_record(ax) for ax in fig.axes],
            }
            json_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        plt.close("all")

    plt.show = _capturing_show
