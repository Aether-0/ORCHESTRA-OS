#!/usr/bin/env python3
"""Render retained ORCHESTRA-OS Markdown reports as readable PDFs."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import markdown
from weasyprint import HTML


PDF_SPECS: Final = (
    (
        "ORCHESTRA-OS_Benchmark_Result_2026-08-03.pdf",
        "ORCHESTRA-OS Benchmark Result",
        "Userspace-validated smoke evidence - 2026-08-03",
        ("docs/experiments/paper_cpu_smoke_v1_result_2026-08-03.md",),
    ),
    (
        "ORCHESTRA-OS_Release_Readiness_Plan.pdf",
        "ORCHESTRA-OS Release-Readiness Plan",
        "Evidence-gated WP1-WP10 roadmap",
        ("docs/operations/release-readiness-plan.md",),
    ),
    (
        "ORCHESTRA-OS_Test_Evidence_Archive_2026-08-03.pdf",
        "ORCHESTRA-OS Test Evidence Archive",
        "Retained local test artifacts and integrity record",
        ("artifacts/test-results/2026-08-03/README.md",),
    ),
    (
        "ORCHESTRA-OS_Testing_and_Release_Readiness_Report.pdf",
        "ORCHESTRA-OS Testing and Release-Readiness Report",
        "Benchmark evidence, improvement priorities, and release gates",
        (
            "docs/experiments/paper_cpu_smoke_v1_result_2026-08-03.md",
            "docs/operations/release-readiness-plan.md",
            "artifacts/test-results/2026-08-03/README.md",
        ),
    ),
)

CSS: Final = """
@page { size: A4; margin: 16mm 14mm 18mm; @bottom-center { content: "ORCHESTRA-OS | " counter(page); color: #596773; font-size: 8pt; } }
* { box-sizing: border-box; }
body { color: #263746; font-family: Arial, sans-serif; font-size: 9.3pt; line-height: 1.32; }
.cover { min-height: 245mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.eyebrow { color: #137C8B; font-size: 11pt; font-weight: bold; letter-spacing: 0.6pt; }
.cover h1 { color: #16324F; font-size: 29pt; line-height: 1.08; margin: 10pt 0; }
.subtitle { color: #596773; font-size: 14pt; margin-bottom: 20pt; }
.callout { background: #DCEFF1; border-left: 4pt solid #137C8B; padding: 10pt 12pt; font-size: 10pt; }
h1, h2, h3 { color: #16324F; page-break-after: avoid; }
h1 { font-size: 20pt; margin: 18pt 0 10pt; }
h2 { color: #137C8B; font-size: 14pt; margin: 15pt 0 7pt; }
h3 { font-size: 11pt; margin: 12pt 0 5pt; }
a { color: #137C8B; text-decoration: none; }
code { background: #EFF2F5; color: #16324F; font-family: monospace; font-size: 8.1pt; padding: 1pt 2pt; }
pre { background: #EFF2F5; border-left: 3pt solid #137C8B; padding: 7pt; white-space: pre-wrap; font-size: 7.5pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 7.3pt; table-layout: fixed; }
th { background: #16324F; color: white; font-weight: bold; }
th, td { border: 0.5pt solid #C9D0D6; padding: 4pt; vertical-align: top; overflow-wrap: anywhere; }
tr:nth-child(even) td { background: #F6F8FA; }
tr { break-inside: avoid; }
img { display: block; max-width: 100%; max-height: 220mm; margin: 9pt auto; }
blockquote { border-left: 3pt solid #D98E04; margin: 8pt 0; padding-left: 9pt; color: #46535F; }
.section-break { page-break-before: always; }
"""


@dataclass(frozen=True)
class PdfSpec:
    filename: str
    title: str
    subtitle: str
    sources: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("output/doc"))
    return parser.parse_args()


def sanitize_ascii_dashes(text: str) -> str:
    return text.translate(str.maketrans({
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": " - ", "\u2212": "-",
    }))


def rewrite_local_targets(text: str, source: Path) -> str:
    pattern = re.compile(r"(!?\[[^]]*\])\(([^)]+)\)")

    def replace(match: re.Match[str]) -> str:
        label, target = match.groups()
        if target.startswith(("#", "http://", "https://", "mailto:", "file:")):
            return match.group(0)
        split = target.split("#", 1)
        resolved = (source.parent / split[0]).resolve()
        if not resolved.exists():
            return match.group(0)
        anchor = f"#{split[1]}" if len(split) == 2 else ""
        return f"{label}({resolved.as_uri()}{anchor})"

    return pattern.sub(replace, text)


def markdown_fragment(source: Path) -> str:
    text = rewrite_local_targets(sanitize_ascii_dashes(source.read_text(encoding="utf-8")), source)
    return markdown.markdown(text, extensions=("tables", "fenced_code", "sane_lists", "toc"), output_format="html5")


def render_pdf(spec: PdfSpec, repository_root: Path, output_dir: Path) -> Path:
    fragments: list[str] = []
    for index, relative in enumerate(spec.sources):
        source = repository_root / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        page_class = " section-break" if index else ""
        fragments.append(f'<section class="report-section{page_class}">{markdown_fragment(source)}</section>')
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<section class="cover"><div class="eyebrow">ORCHESTRA-OS RESEARCH PROGRAM</div><h1>{spec.title}</h1><div class="subtitle">{spec.subtitle}</div><div class="callout"><strong>Evidence boundary:</strong> current results are userspace-validated only. This PDF does not establish a kernel scheduler, causal performance advantage, production security, or deployment readiness.</div></section>
{''.join(fragments)}</body></html>"""
    output = output_dir / spec.filename
    HTML(string=html, base_url=str(repository_root)).write_pdf(output)
    return output


def main() -> int:
    args = parse_args()
    root = args.repository_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for raw_spec in PDF_SPECS:
        print(render_pdf(PdfSpec(*raw_spec), root, output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
