"""Tests for the colonymind.codegen package skeleton (Epic 2, Story 2, Task 1).

Covers the lazy ``cm.codegen`` namespace exposure and the typed error hierarchy.
"""

from __future__ import annotations

import subprocess
import sys

import colonymind as cm
from colonymind.codegen import CardinalityError, CodegenError, CycleError


def test_codegen_is_lazily_imported() -> None:
    # A fresh import of the package must NOT eagerly pull in colonymind.codegen;
    # it is only imported on first attribute access, like the functional families.
    # Run in a clean subprocess: importing the submodule binds `codegen` onto the
    # parent package's __dict__, so an in-process sys.modules reset can't observe
    # the lazy boundary reliably.
    script = (
        "import sys; import colonymind as cm;"
        "assert 'colonymind.codegen' not in sys.modules, 'codegen imported eagerly';"
        "ns = cm.codegen;"
        "assert 'colonymind.codegen' in sys.modules, 'codegen not imported on access';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_codegen_namespace_reexports_errors() -> None:
    assert cm.codegen.CodegenError is CodegenError
    assert cm.codegen.CycleError is CycleError
    assert cm.codegen.CardinalityError is CardinalityError


def test_error_hierarchy() -> None:
    assert issubclass(CycleError, CodegenError)
    assert issubclass(CardinalityError, CodegenError)
    assert issubclass(CodegenError, Exception)


def test_codegen_in_public_all() -> None:
    assert "codegen" in cm.__all__
