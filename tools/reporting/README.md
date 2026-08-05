# Release-readiness brief generation

Install the pinned reporting dependencies in an isolated environment, generate
the benchmark figures, then build the DOCX:

```bash
python3 -m pip install -r tools/requirements-visualization.txt
python3 tools/plotting/plot_paper_cpu_smoke.py
python3 tools/plotting/plot_release_readiness.py
python3 tools/reporting/build_release_readiness_docx.py \
  --repository-root .
```

Both generators default to the retained authoritative benchmark under
`artifacts/test-results/2026-08-03/benchmark/authoritative-c`.

The builder validates the processed metric columns, embeds the three benchmark
figures and the release-gate figure, reopens the DOCX, checks minimum table and
image counts, and normalizes archive timestamps for byte-stable output.

For release review, render the DOCX with a pinned office-suite version and
inspect every page for clipping, table overflow, font substitution, and page
breaks. Structural validation does not replace that visual review.
