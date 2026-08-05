# Release-readiness brief build manifest

- Build date: 2026-08-03
- Claim class: Userspace-validated only for the named smoke mechanisms
- Benchmark input: `artifacts/test-results/2026-08-03/benchmark/authoritative-c`
- Output: `output/doc/ORCHESTRA-OS_Release_Readiness_Plan.docx`

## Input identity

- `processed/mode_summary.csv`: `ff44510b96698817a51cabc97a5eac7c7382dcb30c9d3cf247a3c98d5f25098e`
- `processed/run_summaries.csv`: `89dfcd5039b903a3051bc05dbf53fe70271a804c9b9784049e46b3990d459324`
- `processed/summary.json`: `a9b1cc25045fd4e5060626671861d0072eb7e0978ec3ab2a3239d105fa0b7188`
- [Release-readiness plan](release-readiness-plan.md): `625971bad98adf34b2bbadc0fd53eabeb6d03a51b1a69a5503f6e6de11ffcfc5`

## Generator identity

- `tools/plotting/plot_paper_cpu_smoke.py`: `192b386dd251af9c47b74502a0a7b1a17e85bfaf856ba1533fbfdd2015d76343`
- `tools/plotting/plot_release_readiness.py`: `d68912d7601236a6a0ea3ce7d1b242d2f4eae06d6c6791a672e56c63e5f5f321`
- `tools/reporting/build_release_readiness_docx.py`: `63a69f1956da000824ce87df9fca1369bbc5427f5c5b235d969269e7cda6ba74`
- `tools/requirements-visualization.txt`: `5744a297cc0240bf4f700425241b689623c1bf152eb70c66aeb86c3a66fe8141`

## Visual and document outputs

- `coordination_means_ci95.png`: `edc3003193d2925e09683898489581ed340f9cce070e36ee9d64ed3edcffa9d3`
- `coordination_per_run.png`: `57297f00c8167f4e3bb1776c1e7a58f45a99392cc06f5928e8f9d198c88a1a0f`
- `action_mix_per_run.png`: `b90a40d437e0ed52a881747d61405ee089f7ec22bbbc32b37c9999fcfe9a3072`
- `release_readiness_path.png`: `e245b186a509f1d435ed02f1adf3946d84eb2ca59176fec71563298c47f519a3`
- `ORCHESTRA-OS_Release_Readiness_Plan.docx`: `5761c5c2ade10f923a12aab6efb8b96691f59bae2d7568c1d7748563027081c1`

Two consecutive figure builds and two consecutive DOCX builds were
byte-identical. The DOCX archive passed ZIP integrity and reopen checks and
contains 220 paragraphs, 12 nonempty tables, and four embedded figures. The
embedded image bytes match the source PNG hashes.

No DOCX/PDF renderer was installed in the test environment, so page layout was
not visually rendered. Text, headings, table content, archive structure, local
links, and each source PNG were inspected; a pinned office-suite rendering and
page-by-page review remains required before external publication.
