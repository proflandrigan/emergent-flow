"""Golden snapshot tests for functional-pipeline codegen (Epic 2, Story 9).

Snapshots the deterministic output of `compile_to_code` for the functional
corpus so regressions in naming, formatting, or import collection are caught.
Regenerate with `uv run pytest tests/test_codegen_golden.py --snapshot-update`.
"""

from __future__ import annotations

import pathlib

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir import load_graph

REPO_ROOT = pathlib.Path(__file__).parent.parent


def test_linear_chain_golden(snapshot) -> None:
    """Linear chain (functional_pipeline.json) compiles to stable golden code."""
    graph = load_graph(REPO_ROOT / "examples" / "functional_pipeline.json")
    assert compile_to_code(graph) == snapshot


def test_fan_out_golden(snapshot) -> None:
    """Fan-out (vertical slice) compiles to stable golden code."""
    graph = load_graph(REPO_ROOT / "examples" / "vertical_slice" / "pipeline.json")
    assert compile_to_code(graph) == snapshot
