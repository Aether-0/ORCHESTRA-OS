from __future__ import annotations
import csv, json
from pathlib import Path
from typing import Mapping, Sequence
import numpy as np

def _default(v):
    if isinstance(v, np.integer): return int(v)
    if isinstance(v, np.floating): return float(v)
    if isinstance(v, np.bool_): return bool(v)
    if isinstance(v, Path): return str(v)
    raise TypeError(type(v).__name__)

def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=_default)+"\n", encoding="utf-8")

def write_tsv(path: Path, rows: Sequence[Mapping[str, object]], fields=()) -> None:
    if not fields: fields=list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as h:
        w=csv.DictWriter(h, fieldnames=list(fields), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for row in rows: w.writerow({k:"" if row.get(k) is None else row.get(k) for k in fields})
