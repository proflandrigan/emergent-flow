"""
emergentflow.script
~~~~~~~~~~~~~~~~~~~
Custom-code seam — arbitrary Python transforms as graph nodes (Epic 9, ADR 0017 seam).

Users write a short ``def transform(value):`` function that is compiled and
executed in a fresh namespace via ``compile()``/``exec()`` and called against
a runtime value. This is intentionally unsandboxed (same trust level as the
local emergentflow server); a separate, later node wrapper threads it into
the graph IR.

``run_code()`` is the thin public wrapper that ``ef.script`` nodes delegate to:
it compiles the user-supplied code, extracts ``transform``, calls it with the
incoming value, and returns the result — mirroring how ``ef.llm.call``
delegates to an injected client.
"""

from __future__ import annotations

import builtins
import io
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from emergentflow.api import public_op

__all__ = [
    "run_code",
    "run_transform_capture",
    "CaptureResult",
    "CustomCodeError",
    "TransformError",
]

_REQUIRED_FUNCTION_NAME = "transform"
_COMPILE_NAME = "<custom_code>"


class CustomCodeError(ValueError):
    """Raised when user-supplied custom code cannot be executed.

    Covers two cases: the code fails to parse/compile (``SyntaxError`` is
    rewrapped as ``CustomCodeError``), or the compiled code does not define a
    callable named ``transform``. Does **not** catch or rewrap runtime errors
    from the user's ``transform`` function itself — those propagate unmodified.
    """


@public_op(name="ef.script.run_code")
def run_code(code: str, value: Any) -> Any:
    """Run user-authored Python *code* against *value* and return its result.

    *code* must define a top-level function named ``transform`` taking exactly one
    positional argument. It is compiled and executed in a fresh, isolated namespace
    (no globals from this module or the caller leak in) and ``transform(value)`` is
    then called and its return value returned.

    This is intentionally unsandboxed — *code* runs with full interpreter privileges,
    the same trust level as the rest of the local emergentflow server. Never call this
    with code from an untrusted source.

    Raises
    ------
    CustomCodeError
        If *code* fails to parse/compile, or does not define a callable named
        ``transform``.
    """
    return _load_transform(code, {})(value)


def _load_transform(code: str, namespace: dict[str, Any]) -> Callable[[Any], Any]:
    """Compile *code*, exec it into *namespace*, and return its ``transform`` callable."""
    try:
        compiled = compile(code, _COMPILE_NAME, "exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise CustomCodeError(f"custom code failed to compile: {exc}") from exc

    exec(compiled, namespace)  # noqa: S102 -- intentional, documented unsandboxed exec seam

    transform = namespace.get(_REQUIRED_FUNCTION_NAME)
    if not callable(transform):
        raise CustomCodeError(
            f"custom code must define a callable named {_REQUIRED_FUNCTION_NAME!r}; "
            f"found {type(transform).__name__ if transform is not None else 'nothing'}."
        )
    return transform


@dataclass(frozen=True)
class TransformError:
    """A structured custom-code failure: what went wrong and where in the user's code."""

    type: str
    message: str
    traceback: str
    line: int | None


@dataclass(frozen=True)
class CaptureResult:
    """Outcome of ``run_transform_capture``: the value or an error, plus captured output."""

    value: Any
    stdout: str
    stderr: str
    error: TransformError | None


def _custom_code_line(exc: BaseException) -> int | None:
    """Line number of the innermost traceback frame that is the user's custom code."""
    if isinstance(exc, CustomCodeError) and isinstance(exc.__cause__, SyntaxError):
        return exc.__cause__.lineno
    line: int | None = None
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == _COMPILE_NAME:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def run_transform_capture(code: str, value: Any) -> CaptureResult:
    """Like ``run_code`` but never raises for user-code failures; captures output.

    Shares the ``run_code`` compile/exec/call seam, but is a plain function (not a
    ``@public_op``) because its result is a diagnostic envelope, not a node value.
    ``print`` inside *code* is routed to a per-call buffer by shadowing it in the
    exec namespace's builtins, rather than swapping ``sys.stdout`` -- that is
    process-global, so concurrent calls would interleave, and a call abandoned by a
    timeout would leave ``sys.stdout`` redirected. Output written straight to
    ``sys.stdout``/``sys.stderr`` bypasses capture; ``print(..., file=sys.stderr)``
    is captured as stderr. Any ``Exception`` from compile or ``transform`` becomes a
    ``TransformError`` carrying the type, message, traceback, and the line in *code*.
    """
    out, err = io.StringIO(), io.StringIO()

    def _print(*args: Any, file: Any = None, **kwargs: Any) -> None:
        target = err if file is sys.stderr else out if file is None else file
        builtins.print(*args, file=target, **kwargs)

    namespace: dict[str, Any] = {"__builtins__": {**vars(builtins), "print": _print}}
    try:
        result = _load_transform(code, namespace)(value)
    except Exception as exc:  # noqa: BLE001 - user code may raise anything; report it
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        error = TransformError(type(exc).__name__, str(exc), text, _custom_code_line(exc))
        return CaptureResult(None, out.getvalue(), err.getvalue(), error)
    return CaptureResult(result, out.getvalue(), err.getvalue(), None)
