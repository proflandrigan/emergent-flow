"""
emergentflow.codegen.formatting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This module runs the project's ruff normalization passes (ADR 0008) over the
whole-graph compiler's assembled module source before it is returned to the
caller; it is the final normalization step shared by every codegen
emission path (template-based functional pipelines today, the future
AST/libcst declarative path later) so neither has to hand-manage import
ordering or whitespace.
"""

from __future__ import annotations

import subprocess
import sys

from emergentflow.codegen.errors import CodegenError


def _run_ruff(args: list[str], code: str) -> subprocess.CompletedProcess[str]:
    """Run ``python -m ruff <args>`` feeding *code* on stdin, capturing output."""
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        input=code,
        capture_output=True,
        text=True,
    )


def format_source(code: str) -> str:
    """Normalize Python source code with ruff (organize imports, then format).

    The compiler collects and de-duplicates each node's import lines across the
    whole graph, but emits them in a paradigm-agnostic order. ``ruff format``
    normalizes whitespace, quotes and line length but never reorders imports, so
    a module that pulls in a mix of stdlib and third-party imports would emit
    isort-dirty (``I001``) output. We therefore run an import-organize pass
    (``--select I --fix``, which forces the rule regardless of config discovery
    and is fully auto-fixable) before the format pass, so the returned source is
    clean under the project's ``ruff check`` gate.

    Parameters
    ----------
    code : str
        The raw Python source code to be normalized.

    Returns
    -------
    str
        The import-organized, formatted Python source code.

    Raises
    ------
    CodegenError
        If either ruff pass fails with a non-zero exit code (e.g. the assembled
        source does not parse).
    """
    organized = _run_ruff(["check", "--select", "I", "--fix", "-"], code)
    if organized.returncode != 0:
        raise CodegenError(f"ruff import-organize failed:\n{organized.stderr}")

    formatted = _run_ruff(["format", "-"], organized.stdout)
    if formatted.returncode != 0:
        raise CodegenError(f"ruff format failed:\n{formatted.stderr}")
    return formatted.stdout
