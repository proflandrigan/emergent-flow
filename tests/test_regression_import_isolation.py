"""
tests/test_regression_import_isolation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14 Story 11 — import-isolation + dependency gate: two of the five
permanent CI checks enforcing the epic's works-without-agents invariant
(the package and app work identically with or without agent/collaboration
code loaded).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tomllib

_PYPROJECT_PATH = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"

_EXPECTED_BASE_DEPENDENCIES = [
    "pydantic>=2.5,<3",
    "pandas>=2,<3",
    "statsmodels>=0.14,<1",
    "scikit-learn>=1.4",
    "scipy>=1.10",
    "pyarrow>=15",
    "plotly>=5,<7",
    "ydata-profiling>=4",
    "setuptools>=68,<81",
    "ruff>=0.6",
    "libcst>=1.1",
    "sqlglot>=25,<26",
    "duckdb>=1,<2",
]


# ---------------------------------------------------------------------------
# Import-isolation — runtime
# ---------------------------------------------------------------------------


def test_import_emergentflow_never_imports_collab_or_fastmcp() -> None:
    script = (
        "import sys; import emergentflow;"
        "bad = [m for m in sys.modules if m == 'fastmcp' or m.startswith('emergentflow.collab')];"
        "assert not bad, f'unexpected eager imports: {bad}';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_touching_every_lazy_export_never_imports_collab_or_fastmcp() -> None:
    script = (
        "import sys; import emergentflow as ef;"
        "[getattr(ef, name) for name in ef.__all__];"
        "bad = [m for m in sys.modules if m == 'fastmcp' or m.startswith('emergentflow.collab')];"
        "assert not bad, f'unexpected imports after touching every lazy export: {bad}';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


# ---------------------------------------------------------------------------
# Dependency gate — manifest-level
# ---------------------------------------------------------------------------


def test_base_dependencies_pinned() -> None:
    data = tomllib.loads(_PYPROJECT_PATH.read_text())
    assert data["project"]["dependencies"] == _EXPECTED_BASE_DEPENDENCIES


def test_fastmcp_is_not_a_base_dependency() -> None:
    data = tomllib.loads(_PYPROJECT_PATH.read_text())
    base_deps = " ".join(data["project"]["dependencies"]).lower()
    assert "fastmcp" not in base_deps


def test_mcp_extra_declares_fastmcp() -> None:
    data = tomllib.loads(_PYPROJECT_PATH.read_text())
    mcp_extra = data["project"]["optional-dependencies"]["mcp"]
    assert any(dep.lower().startswith("fastmcp") for dep in mcp_extra)
