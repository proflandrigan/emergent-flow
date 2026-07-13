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

from typing import Any

from emergentflow.api import public_op

__all__ = ["run_code", "CustomCodeError"]

_REQUIRED_FUNCTION_NAME = "transform"


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
    try:
        compiled = compile(code, "<custom_code>", "exec")
    except SyntaxError as exc:
        raise CustomCodeError(f"custom code failed to compile: {exc}") from exc

    namespace: dict[str, Any] = {}
    exec(compiled, namespace)  # noqa: S102 -- intentional, documented unsandboxed exec seam

    transform = namespace.get(_REQUIRED_FUNCTION_NAME)
    if not callable(transform):
        raise CustomCodeError(
            f"custom code must define a callable named {_REQUIRED_FUNCTION_NAME!r}; "
            f"found {type(transform).__name__ if transform is not None else 'nothing'}."
        )

    return transform(value)
