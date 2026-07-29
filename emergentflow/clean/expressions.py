"""
emergentflow.clean.expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Restricted-grammar expression pre-screen for ``ef.clean.derive_column`` (Epic 16, Story 6).

Evaluation of a derived-column expression is delegated to **``pandas.DataFrame.eval``** — this
module does not write its own evaluator. But ``df.eval`` accepts ``@name`` syntax to pull values
out of the *caller's* Python scope, and the epic (``epics/epic-16-...md``, "Notes / Risks")
requires this node to not become a second unsandboxed trust niche the way ``custom_code``
deliberately is. So every expression string is first validated by an ``ast`` allow-list, and only
then handed to pandas.

Two properties make this cheap and airtight:

1. ``@threshold`` is **not valid Python**, so ``ast.parse`` raises ``SyntaxError`` on it
   automatically — the ``@``-local escape hatch is closed for free.
2. Every bare ``ast.Name`` in the expression is checked against the frame's actual column names,
   so an expression cannot reference anything that is not a column.
"""

from __future__ import annotations

import ast

from .errors import CleanError, UnknownColumnError

__all__ = ["validate_expression"]

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Load,
    # arithmetic
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    # unary
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.Invert,
    # boolean / bitwise (pandas' eval uses & | ~ for element-wise logic)
    ast.And,
    ast.Or,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    # comparison
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def validate_expression(expr: str, *, available: list[str]) -> None:
    """Validate *expr* against the restricted grammar, raising on anything unsafe.

    Returns None on success. Raises CleanError for a syntactically invalid or
    disallowed expression, UnknownColumnError for a name that is not a column in
    *available*.
    """
    if not isinstance(expr, str) or not expr.strip():
        raise CleanError(f"expression must be a non-empty string; got {expr!r}.")

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CleanError(
            f"expression {expr!r} is not a valid expression: {exc.msg}. Note that pandas' "
            "'@name' syntax for referencing outside variables is deliberately not supported — "
            "an expression may only reference columns of the input frame."
        ) from exc

    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise CleanError(
                f"expression {expr!r} uses unsupported syntax "
                f"({type(node).__name__}); only column names, literals, arithmetic, "
                "comparison, and boolean/bitwise operators are allowed. Use a custom_code "
                "node if you need arbitrary Python."
            )

    seen: set[str] = set()
    unknown: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in available and node.id not in seen:
            unknown.append(node.id)
            seen.add(node.id)
    if unknown:
        raise UnknownColumnError(
            f"expression {expr!r} references unknown column(s) {unknown!r}; "
            f"expected one of {available!r}."
        )
