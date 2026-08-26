#!/usr/bin/env python3
"""Capture the instantiated Python environment without running study analyses."""
from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import io
import json
import locale
import os
import platform
import subprocess
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PACKAGES = [
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("pingouin", "pingouin"),
    ("statsmodels", "statsmodels"),
    ("matplotlib", "matplotlib"),
    ("seaborn", "seaborn"),
    ("scikit-learn", "sklearn"),
    ("pandas-flavor", "pandas_flavor"),
    ("joblib", "joblib"),
    ("threadpoolctl", "threadpoolctl"),
]


def run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prevent import probes from leaving bytecode in the verified source checkout.
    sys.dont_write_bytecode = True

    imports: Dict[str, Dict[str, Any]] = {}
    imports_ok = True
    imported_modules: Dict[str, Any] = {}
    for label, module_name in PACKAGES:
        try:
            module = importlib.import_module(module_name)
            imported_modules[label] = module
            imports[label] = {
                "status": "ok",
                "version": getattr(module, "__version__", "unknown"),
                "file": getattr(module, "__file__", None),
            }
        except Exception as exc:
            imports_ok = False
            imports[label] = {"status": "failed", "error": repr(exc)}

    expected_python = (3, 8, 16)
    python_exact = sys.version_info[:3] == expected_python
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)

    # Syntax-check in memory only. No study script is executed and no .pyc is written.
    analysis_scripts = sorted((repo / "data_analysis").glob("*.py"))
    compile_results: Dict[str, str] = {}
    for script in analysis_scripts:
        try:
            compile(script.read_bytes(), str(script), "exec", dont_inherit=True)
            compile_results[str(script.relative_to(repo))] = "ok"
        except Exception as exc:
            compile_results[str(script.relative_to(repo))] = repr(exc)

    # Import util.py only to verify definitions/import compatibility; its __main__ block is not run.
    util_import = {"status": "not_attempted"}
    util_path = repo / "data_analysis" / "util.py"
    try:
        spec = importlib.util.spec_from_file_location("eth_hai_upstream_util", util_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not create import spec for util.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        util_import = {"status": "ok", "path": str(util_path)}
    except Exception as exc:
        util_import = {"status": "failed", "error": repr(exc), "path": str(util_path)}

    numpy_config = ""
    scipy_config = ""
    if "numpy" in imported_modules:
        with io.StringIO() as buffer, contextlib.redirect_stdout(buffer):
            imported_modules["numpy"].show_config()
            numpy_config = buffer.getvalue()
    if "scipy" in imported_modules:
        with io.StringIO() as buffer, contextlib.redirect_stdout(buffer):
            imported_modules["scipy"].show_config()
            scipy_config = buffer.getvalue()
    (output_dir / "numpy_config.txt").write_text(numpy_config, encoding="utf-8")
    (output_dir / "scipy_config.txt").write_text(scipy_config, encoding="utf-8")

    threadpools: Any = None
    try:
        from threadpoolctl import threadpool_info

        threadpools = threadpool_info()
    except Exception as exc:
        threadpools = {"error": repr(exc)}

    pip_check = run([sys.executable, "-m", "pip", "check"], check=False)
    pip_version = run([sys.executable, "-m", "pip", "--version"], check=False)

    report = {
        "schema_version": "1.0",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": {
            "version": sys.version,
            "version_info": list(sys.version_info[:5]),
            "expected_exact_version": list(expected_python),
            "exact_version_match": python_exact,
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": getattr(sys, "base_prefix", None),
            "in_virtual_environment": in_venv,
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "build": list(platform.python_build()),
            "cache_tag": getattr(sys.implementation, "cache_tag", None),
        },
        "platform": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "libc": list(platform.libc_ver()),
            "uname": list(platform.uname()),
            "sysconfig_platform": sysconfig.get_platform(),
            "locale": locale.getdefaultlocale(),
            "preferred_encoding": locale.getpreferredencoding(False),
        },
        "packages": imports,
        "imports_ok": imports_ok,
        "analysis_script_compile_results": compile_results,
        "analysis_scripts_compiled_in_memory_only": True,
        "statistical_scripts_executed": False,
        "upstream_util_import": util_import,
        "threadpools": threadpools,
        "pip": {
            "version_output": pip_version.stdout.strip(),
            "check_returncode": pip_check.returncode,
            "check_stdout": pip_check.stdout.strip(),
            "check_stderr": pip_check.stderr.strip(),
        },
        "environment_variables": {
            key: os.environ.get(key)
            for key in [
                "LANG",
                "LC_ALL",
                "TZ",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "PYTHONHASHSEED",
                "PYTHONDONTWRITEBYTECODE",
            ]
        },
    }
    passed = bool(
        python_exact
        and in_venv
        and imports_ok
        and all(value == "ok" for value in compile_results.values())
        and util_import.get("status") == "ok"
        and pip_check.returncode == 0
    )
    report["passed"] = passed

    (output_dir / "environment_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
