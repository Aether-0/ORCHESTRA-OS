#!/usr/bin/env python3
"""Verify a detached checkout against the connector-verified 27-object manifest.

This script performs source-identity checks only. It does not execute any statistical
analysis or inspect participant-level values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def run(cmd: List[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args], check=check)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_ls_tree(output: str) -> Dict[str, Dict[str, Any]]:
    observed: Dict[str, Dict[str, Any]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) not in (3, 4):
            raise ValueError(f"Unexpected git ls-tree row: {line!r}")
        mode, obj_type, obj_sha = parts[:3]
        size = None if len(parts) == 3 or parts[3] == "-" else int(parts[3])
        observed[path] = {"mode": mode, "type": obj_type, "sha": obj_sha, "size": size}
    return observed


def compare_entries(
    expected: Dict[str, Dict[str, Any]], observed: Dict[str, Dict[str, Any]]
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    mismatches: List[Dict[str, Any]] = []
    for path in sorted(set(expected) & set(observed)):
        exp = expected[path]
        obs = observed[path]
        comparable = ("mode", "type", "sha", "size")
        if any(exp.get(key) != obs.get(key) for key in comparable):
            mismatches.append(
                {
                    "path": path,
                    "expected": {key: exp.get(key) for key in comparable},
                    "observed": {key: obs.get(key) for key in comparable},
                }
            )
    return missing, extra, mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    manifest_path = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if git(repo, "rev-parse", "--git-dir", check=False).returncode != 0:
        raise SystemExit(f"ERROR: {repo} is not a Git checkout")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pinned_commit = manifest["commit_sha"]
    pinned_tree = manifest["root_tree_sha"]
    expected_entries = {entry["path"]: entry for entry in manifest["entries"]}

    actual_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    actual_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    symbolic = git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    detached_head = symbolic.returncode != 0
    status_text = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    working_tree_clean = not bool(status_text.strip())

    observed_output = git(repo, "ls-tree", "-r", "-t", "-l", "HEAD").stdout
    observed_entries = parse_ls_tree(observed_output)
    missing, extra, mismatches = compare_entries(expected_entries, observed_entries)

    blob_rows: List[Dict[str, Any]] = []
    working_tree_mismatches: List[Dict[str, Any]] = []
    for path, entry in sorted(expected_entries.items()):
        if entry["type"] != "blob":
            continue
        file_path = repo / path
        exists = file_path.is_file()
        observed_size = file_path.stat().st_size if exists else None
        observed_sha256 = file_sha256(file_path) if exists else None
        worktree_git_sha = (
            run(["git", "hash-object", "--no-filters", str(file_path)]).stdout.strip()
            if exists
            else None
        )
        mode_bits = stat.S_IMODE(file_path.stat().st_mode) if exists else None
        executable = bool(mode_bits & stat.S_IXUSR) if mode_bits is not None else None
        expected_executable = entry["mode"] == "100755"
        row = {
            "path": path,
            "expected_git_sha1": entry["sha"],
            "worktree_git_sha1": worktree_git_sha,
            "expected_size_bytes": entry["size"],
            "observed_size_bytes": observed_size,
            "sha256": observed_sha256,
            "expected_mode": entry["mode"],
            "owner_executable": executable,
            "restricted_redistribution": bool(entry.get("restricted_redistribution", False)),
        }
        blob_rows.append(row)
        if (
            not exists
            or observed_size != entry["size"]
            or worktree_git_sha != entry["sha"]
            or executable != expected_executable
        ):
            working_tree_mismatches.append(row)

    fsck = git(repo, "fsck", "--full", "--strict", "--no-reflogs", check=False)
    (output_dir / "git_fsck.txt").write_text(
        (fsck.stdout or "") + (fsck.stderr or ""), encoding="utf-8"
    )
    (output_dir / "source_commit_object.txt").write_text(
        git(repo, "cat-file", "-p", "HEAD").stdout, encoding="utf-8"
    )
    (output_dir / "source_commit_metadata.txt").write_text(
        git(repo, "show", "-s", "--format=fuller", "HEAD").stdout, encoding="utf-8"
    )
    (output_dir / "git_tree_observed.txt").write_text(observed_output, encoding="utf-8")
    (output_dir / "working_tree_status.txt").write_text(status_text, encoding="utf-8")

    sha_rows = [
        "sha256\tgit_sha1\tsize_bytes\tmode\trestricted_redistribution\tpath"
    ]
    for row in blob_rows:
        sha_rows.append(
            "{sha256}\t{expected_git_sha1}\t{observed_size_bytes}\t{expected_mode}\t{restricted_redistribution}\t{path}".format(
                **row
            )
        )
    (output_dir / "source_file_sha256.tsv").write_text(
        "\n".join(sha_rows) + "\n", encoding="utf-8"
    )

    passed = all(
        [
            actual_commit == pinned_commit,
            actual_tree == pinned_tree,
            detached_head,
            working_tree_clean,
            not missing,
            not extra,
            not mismatches,
            not working_tree_mismatches,
            fsck.returncode == 0,
            len(blob_rows) == manifest["blob_count"] == 27,
            sum(int(row["observed_size_bytes"]) for row in blob_rows)
            == manifest["total_blob_bytes"],
        ]
    )

    report = {
        "schema_version": "1.0",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": manifest["repository"],
        "repo_path": str(repo),
        "expected_commit": pinned_commit,
        "actual_commit": actual_commit,
        "expected_root_tree": pinned_tree,
        "actual_root_tree": actual_tree,
        "detached_head": detached_head,
        "symbolic_head": symbolic.stdout.strip() if not detached_head else None,
        "working_tree_clean": working_tree_clean,
        "expected_blob_count": manifest["blob_count"],
        "verified_blob_count": len(blob_rows),
        "expected_tree_count": manifest["tree_count"],
        "observed_entry_count": len(observed_entries),
        "expected_total_blob_bytes": manifest["total_blob_bytes"],
        "observed_total_blob_bytes": sum(int(row["observed_size_bytes"]) for row in blob_rows),
        "missing_entries": missing,
        "extra_entries": extra,
        "git_object_mismatches": mismatches,
        "working_tree_mismatches": working_tree_mismatches,
        "git_fsck_returncode": fsck.returncode,
        "git_version": run(["git", "--version"]).stdout.strip(),
        "platform": platform.platform(),
        "passed": passed,
        "statistical_scripts_executed": False,
    }
    (output_dir / "source_verification_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if not passed:
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
