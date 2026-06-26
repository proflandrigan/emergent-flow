"""Corpus-wide codegen quality gate (Epic 2, Story 9).

Asserts that `compile_to_code` output for every shippable example graph is
`ruff`-clean and parseable (syntactically importable). Runtime execution and
the execute/compile equivalence are covered by tests/test_codegen_equivalence.py;
this gate guards lint + syntax across the whole corpus so a naming/formatting
regression in any composition is caught.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir import load_graph

REPO_ROOT = pathlib.Path(__file__).parent.parent

#: (id, repo-relative path) for every shippable corpus graph: linear chain,
#: fan-out, and the declarative subgraph.
CORPUS = [
    ("linear_chain", "examples/functional_pipeline.json"),
    ("fan_out", "examples/vertical_slice/pipeline.json"),
    ("declarative_subgraph", "examples/declarative_module.json"),
]


@pytest.mark.parametrize("rel_path", [p for _, p in CORPUS], ids=[i for i, _ in CORPUS])
def test_corpus_codegen_is_parseable(rel_path: str) -> None:
    """Generated code for each corpus graph parses (is syntactically importable)."""
    code = compile_to_code(load_graph(REPO_ROOT / rel_path))
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("rel_path", [p for _, p in CORPUS], ids=[i for i, _ in CORPUS])
def test_corpus_codegen_is_ruff_clean(rel_path: str) -> None:
    """Generated code for each corpus graph passes `ruff check`."""
    code = compile_to_code(load_graph(REPO_ROOT / rel_path))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
