#!/usr/bin/env python3
"""CI boundary check: ``ui/`` must never import the Python package (ADR 0013 Decision 4).

The monorepo (ADR 0013) replaced the physical repo wall with this check. The canvas under
``ui/`` talks to the local server only over HTTP; it must not ``import``/``require``/bundle
``emergentflow``. Only the four contract artifacts (the IR JSON Schema, the
``compile_to_code`` output string, the rules-as-data artifact, and the node catalog
artifact -- ADR 0015) cross the boundary -- and they cross as data, not as a code import.
Run standalone (``python
scripts/check_ui_boundary.py`` -> exit 1 on violation) or via ``tests/test_ui_boundary.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[1] / "ui"
PACKAGE = "emergentflow"
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue"}
SKIP_DIRS = {"node_modules", "dist", ".vite"}

# Capture the module specifier of an ES import / re-export / require / dynamic import.
# Matches: `import x from "spec"`, `import "spec"`, `export {x} from "spec"`,
# `require("spec")`, `import("spec")`. A plain path string (e.g. a Vite outDir) has no
# such keyword before it and is intentionally NOT matched.
_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\brequire\s*\(\s*|\bimport\s*\(\s*|\bimport\s+)['"]([^'"]+)['"]"""
)


def _iter_source_files(ui_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(ui_dir.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ui_dir).parts):
            continue
        files.append(path)
    return files


def _spec_targets_package(spec: str) -> bool:
    """True if the import specifier names the package itself, not just contains its name.

    Matches a bare/scoped module specifier (``emergentflow``, ``emergentflow/foo``) or a
    relative/absolute path with a ``emergentflow`` path segment (``../../emergentflow/ir``).
    A specifier that merely *contains* the substring ``emergentflow`` -- e.g. a same-repo
    asset import like ``./icons/emergentflow-logo.svg`` -- is intentionally NOT a violation:
    matching on substring rather than path segment would false-positive on any UI asset
    named after the project.
    """
    segments = [s for s in spec.split("/") if s not in ("", ".", "..")]
    return any(segment.lower() == PACKAGE for segment in segments)


def find_violations(ui_dir: Path) -> list[str]:
    """Return human-readable violation lines: every ui import that reaches into the package."""
    violations: list[str] = []
    for path in _iter_source_files(ui_dir):
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            for spec in _IMPORT_RE.findall(line):
                if _spec_targets_package(spec):
                    rel = path.relative_to(ui_dir.parent)
                    violations.append(f"{rel}:{lineno}: imports {spec!r} -> into {PACKAGE}/")
    return violations


def main() -> int:
    if not UI_DIR.is_dir():
        print("ui/ boundary check: no ui/ directory present; nothing to check.")
        return 0
    violations = find_violations(UI_DIR)
    if violations:
        print("ui/ -> emergentflow IMPORT-BAN VIOLATION (ADR 0013 Decision 4):")
        for violation in violations:
            print(f"  {violation}")
        print(
            "\nThe canvas must talk to the local server only over HTTP; it must not import "
            "the Python package. See docs/adr/0013-single-repo-bundled-ui-topology.md."
        )
        return 1
    print(f"ui/ boundary check: OK -- no '{PACKAGE}' imports found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
