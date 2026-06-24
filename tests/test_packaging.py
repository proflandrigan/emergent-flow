"""Build-hook + packaging tests (Epic 4 Story 4d, ADR 0013).

Deterministic and Node-free: they assert the in-tree backend re-exports the PEP 517 hooks,
that the UI compile is best-effort (never raises without Node), and that pyproject declares
the bundled canvas as package data. A real wheel build is verified out-of-band with Node.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tomllib

_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

import build_backend  # noqa: E402


def _pyproject() -> dict:
    return tomllib.loads((_REPO / "pyproject.toml").read_text(encoding="utf-8"))


def test_build_backend_is_the_in_tree_shim() -> None:
    build_system = _pyproject()["build-system"]
    assert build_system["build-backend"] == "build_backend"
    assert "." in build_system["backend-path"]


def test_pyproject_bundles_static_as_package_data() -> None:
    package_data = _pyproject()["tool"]["setuptools"]["package-data"]["colonymind"]
    assert any("_static" in pattern for pattern in package_data)


def test_manifest_includes_build_backend_for_sdist() -> None:
    # build_backend.py lives at the repo root, outside any package setuptools
    # auto-includes in an sdist; without a MANIFEST.in entry, `uv build --sdist`
    # silently omits it and installing from that sdist fails with
    # "ModuleNotFoundError: No module named 'build_backend'" before the wheel
    # build even starts.
    manifest = (_REPO / "MANIFEST.in").read_text(encoding="utf-8")
    assert "build_backend.py" in manifest


def test_backend_reexports_pep517_hooks() -> None:
    for hook in ("build_wheel", "build_sdist", "build_editable", "get_requires_for_build_wheel"):
        assert callable(getattr(build_backend, hook))


def test_build_ui_skips_without_npm(monkeypatch) -> None:
    monkeypatch.setattr(build_backend.shutil, "which", lambda _name: None)
    build_backend._build_ui()  # must not raise


def test_build_ui_skips_without_ui_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_backend, "_UI_DIR", tmp_path / "nonexistent_ui")
    build_backend._build_ui()  # must not raise


def test_build_ui_swallows_npm_failure(tmp_path, monkeypatch) -> None:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "package.json").write_text("{}")
    (ui / "node_modules").mkdir()
    monkeypatch.setattr(build_backend, "_UI_DIR", ui)
    monkeypatch.setattr(build_backend.shutil, "which", lambda _name: "/usr/bin/npm")

    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "npm")

    monkeypatch.setattr(build_backend.subprocess, "run", boom)
    build_backend._build_ui()  # must not raise
