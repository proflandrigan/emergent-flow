"""
colonymind.codegen.formatting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This module runs the project's ``ruff format`` pass (ADR 0008) over the
whole-graph compiler's assembled module source before it is returned to the
caller; it is the final normalization step shared by every codegen
emission path (template-based functional pipelines today, the future
AST/libcst declarative path later) so neither has to hand-manage
whitespace.
"""

from __future__ import annotations

import subprocess
import sys

from colonymind.codegen.errors import CodegenError


def format_source(code: str) -> str:
    """Format Python source code using ruff format.

    Parameters
    ----------
    code : str
        The raw Python source code to be formatted.

    Returns
    -------
    str
        The formatted Python source code.

    Raises
    ------
    CodegenError
        If ruff format fails with a non-zero exit code.
    """
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CodegenError(f"ruff format failed:\n{result.stderr}")
    return result.stdout
