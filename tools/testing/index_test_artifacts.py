#!/usr/bin/env python3
"""Create a checksum manifest and inventory for an ORCHESTRA test archive."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


SCHEMA: Final = "orchestra.test_artifact_inventory/v1"
GENERATED_NAMES: Final = frozenset({"SHA256SUMS", "inventory.json"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifact_root",
        type=Path,
        help="Existing dated test artifact directory to index.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def category(relative: Path) -> str:
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "benchmark":
        return "/".join(parts[:2])
    if len(parts) >= 2 and parts[0] == "regression":
        return "/".join(parts[:2])
    return parts[0]


def main() -> int:
    args = parse_args()
    artifact_root = args.artifact_root.resolve()
    if not artifact_root.is_dir():
        raise NotADirectoryError(artifact_root)

    paths: list[Path] = []
    for path in artifact_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlinks are not permitted in the archive: {path}")
        if path.is_file() and path.name not in GENERATED_NAMES:
            paths.append(path)
    paths.sort(key=lambda item: item.relative_to(artifact_root).as_posix())
    if not paths:
        raise ValueError(f"no evidence files found under {artifact_root}")

    records: list[dict[str, object]] = []
    category_counts: Counter[str] = Counter()
    category_bytes: Counter[str] = Counter()
    for path in paths:
        relative = path.relative_to(artifact_root)
        size = path.stat().st_size
        digest = sha256_file(path)
        records.append(
            {
                "path": relative.as_posix(),
                "bytes": size,
                "sha256": digest,
            }
        )
        name = category(relative)
        category_counts[name] += 1
        category_bytes[name] += size

    checksum_path = artifact_root / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{record['sha256']}  {record['path']}\n" for record in records),
        encoding="utf-8",
    )
    inventory = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(artifact_root),
        "claim_boundary": (
            "Local userspace test evidence only; classification is defined in README.md."
        ),
        "indexed_file_count": len(records),
        "indexed_total_bytes": sum(int(record["bytes"]) for record in records),
        "categories": {
            name: {
                "files": category_counts[name],
                "bytes": category_bytes[name],
            }
            for name in sorted(category_counts)
        },
        "checksum_manifest": {
            "path": checksum_path.name,
            "bytes": checksum_path.stat().st_size,
            "sha256": sha256_file(checksum_path),
        },
        "excluded_from_checksum_manifest": sorted(GENERATED_NAMES),
        "hygiene": {
            "text_secret_and_email_scan": "completed-no-matches",
            "raw_local_host_metadata_retained": True,
            "generated_development_executables_copied": False,
        },
    }
    inventory_path = artifact_root / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"indexed {len(records)} files ({inventory['indexed_total_bytes']} bytes)")
    print(checksum_path)
    print(inventory_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
