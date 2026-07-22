"""In-tree PEP 517 build backend: compile ui/ into emergentflow/_static/ before the wheel.

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
_AGENTS_SRC = _ROOT / "agents"
_AGENTS_DEST = _ROOT / "emergentflow" / "agents"


def _build_ui() -> None:
    """Best-effort: compile ui/ into emergentflow/_static/. Never raises out of the build."""
    if not (_UI_DIR / "package.json").is_file():
        return
    npm = shutil.which("npm")
    if npm is None:
        print("emergentflow build: npm not found; skipping ui/ build (server uses demo page).")
        return
    try:
        # `npm ci` (not a node_modules-exists check) so a stale node_modules from
        # an earlier build never skips reinstalling after package.json/package-lock.json
        # change -- it always installs exactly what the lockfile pins, removing any
        # existing node_modules first.
        subprocess.run([npm, "ci"], cwd=_UI_DIR, check=True)
        subprocess.run([npm, "run", "build"], cwd=_UI_DIR, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"emergentflow build: ui/ build skipped ({exc}); server uses the demo page.")


def _copy_agents() -> None:
    """Best-effort: copy repo-root agents/*.md into emergentflow/agents/ so the wheel ships the
    chat protocol doc + persona markdown as package data (chat_runner resolves it there).
    Never raises out of the build."""
    if not _AGENTS_SRC.is_dir():
        return
    try:
        _AGENTS_DEST.mkdir(parents=True, exist_ok=True)
        for md in _AGENTS_SRC.glob("*.md"):
            shutil.copy2(md, _AGENTS_DEST / md.name)
    except OSError as exc:
        print(f"emergentflow build: agents/ copy skipped ({exc}).")


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    """Copy agents docs + compile ui/ (both best-effort), then delegate to setuptools."""
    _copy_agents()
    _build_ui()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)
