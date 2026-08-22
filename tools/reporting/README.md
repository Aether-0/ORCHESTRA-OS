# Release-readiness brief generation

Install the pinned reporting dependencies in an isolated environment and
generate the benchmark figures:

```bash
python3 -m pip install -r tools/requirements-visualization.txt
python3 tools/plotting/plot_paper_cpu_smoke.py
python3 tools/plotting/plot_release_readiness.py
```

Both plotting commands default to the retained authoritative benchmark under
`artifacts/test-results/2026-08-03/benchmark/authoritative-c`.

The maintained release-readiness document is Markdown:
`docs/operations/release-readiness-plan.md`. A converted brief with the four
archived figure assets is also retained at
`output/doc/ORCHESTRA-OS_Release_Readiness_Plan.md`.

Review the Markdown headings, tables, links, and figure paths after regenerating
the figures. The repository no longer uses a Word-document generation step.
