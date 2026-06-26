"""ui/ -> emergentflow import-ban gate (ADR 0013 Decision 4).

Wraps scripts/check_ui_boundary.py so the invariant runs inside the existing pytest gate
(Task 07 also wires the standalone script into CI). Includes synthetic allow/deny cases so
the checker's own logic is covered, not just the current clean ui/ tree.
"""

from __future__ import annotations

import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))

from check_ui_boundary import find_violations  # noqa: E402


def test_real_ui_tree_has_no_boundary_violations() -> None:
    ui = _REPO / "ui"
    assert ui.is_dir(), "ui/ scaffold should exist (Story 4c)"
    assert find_violations(ui) == []


def test_detects_forbidden_package_import(tmp_path: pathlib.Path) -> None:
    ui = tmp_path / "ui"
    (ui / "src").mkdir(parents=True)
    (ui / "src" / "bad.ts").write_text('import cm from "emergentflow";\n')
    assert find_violations(ui)


def test_detects_relative_reach_in(tmp_path: pathlib.Path) -> None:
    ui = tmp_path / "ui"
    (ui / "src").mkdir(parents=True)
    (ui / "src" / "reach.ts").write_text('import { x } from "../../emergentflow/ir";\n')
    assert find_violations(ui)


def test_detects_require_form(tmp_path: pathlib.Path) -> None:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "legacy.cjs").write_text('const cm = require("emergentflow");\n')
    assert find_violations(ui)


def test_allows_outdir_path_string(tmp_path: pathlib.Path) -> None:
    # A build-output path string is NOT an import and must be allowed.
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "vite.config.ts").write_text(
        'export default { build: { outDir: "../emergentflow/_static" } };\n'
    )
    assert find_violations(ui) == []


def test_allows_asset_import_merely_named_after_the_package(tmp_path: pathlib.Path) -> None:
    # A same-repo asset whose filename happens to contain "emergentflow" (e.g. a logo
    # for a project literally named Emergent Flow) is NOT a package import and must
    # be allowed -- only a "emergentflow" *path segment* is a violation.
    ui = tmp_path / "ui"
    (ui / "src").mkdir(parents=True)
    (ui / "src" / "logo.ts").write_text('import logo from "./icons/emergentflow-logo.svg";\n')
    assert find_violations(ui) == []


def test_skips_node_modules(tmp_path: pathlib.Path) -> None:
    ui = tmp_path / "ui"
    (ui / "node_modules" / "pkg").mkdir(parents=True)
    (ui / "node_modules" / "pkg" / "index.js").write_text('import x from "emergentflow";\n')
    assert find_violations(ui) == []
