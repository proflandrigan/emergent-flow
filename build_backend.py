"""In-tree PEP 517 build backend: compile ui/ into colonymind/_static/ before the wheel.

Wraps ``setuptools.build_meta`` so a real wheel build (``uv build`` / ``python -m build`` /
``pip wheel``) runs ``vite build`` and bundles the compiled canvas. The compile is
BEST-EFFORT: with no Node/npm (a pure-Python CI job, ``uv sync`` for the test gates, or the
release runner) it is skipped and the wheel ships without ``_static/`` -- the server then
falls back to its v0 demo page (ADR 0013). This mirrors ``torch`` being optional and lazily
used: the Python toolchain never depends on the Node toolchain. Only ``build_wheel`` is
hooked; the **editable** build path is the unmodified setuptools one, so ``uv sync`` /
``pip install -e`` never invoke Node.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from setuptools import build_meta as _orig
from setuptools.build_meta import (  # noqa: F401 - re-export PEP 517 hooks for the frontend
    build_editable,
    build_sdist,
    get_requires_for_build_editable,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
    prepare_metadata_for_build_editable,
    prepare_metadata_for_build_wheel,
)

_ROOT = Path(__file__).resolve().parent
_UI_DIR = _ROOT / "ui"


def _build_ui() -> None:
    """Best-effort: compile ui/ into colonymind/_static/. Never raises out of the build."""
    if not (_UI_DIR / "package.json").is_file():
        return
    npm = shutil.which("npm")
    if npm is None:
        print("colonymind build: npm not found; skipping ui/ build (server uses demo page).")
        return
    try:
        if not (_UI_DIR / "node_modules").is_dir():
            subprocess.run([npm, "install"], cwd=_UI_DIR, check=True)
        subprocess.run([npm, "run", "build"], cwd=_UI_DIR, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"colonymind build: ui/ build skipped ({exc}); server uses the demo page.")


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    """Compile ui/ (best-effort), then delegate to setuptools' wheel build."""
    _build_ui()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)
