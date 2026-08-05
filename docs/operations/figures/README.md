# Release-readiness roadmap figure

`release_readiness_path.{png,svg}` visualizes the dependency gates from the
current userspace evidence to a future WP10 release decision. It is not a
schedule, percent-complete graphic, or maturity claim.

Generate both files from the repository root:

```bash
python3 tools/plotting/plot_release_readiness.py
```

The renderer uses a fixed SVG hash salt and fixed metadata for deterministic
output.

- Generator SHA-256: `d68912d7601236a6a0ea3ce7d1b242d2f4eae06d6c6791a672e56c63e5f5f321`
- PNG SHA-256: `e245b186a509f1d435ed02f1adf3946d84eb2ca59176fec71563298c47f519a3`
- SVG SHA-256: `30e1ee95167202f9fbd0eda569fecf4464590123ff17b87921a7fec4d0b77f4a`
