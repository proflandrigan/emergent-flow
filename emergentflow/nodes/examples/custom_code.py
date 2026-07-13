"""
emergentflow.nodes.examples.custom_code
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``script.custom_code`` — a generic custom-code transform node.
1 required IN port, 1 OUT port, both typed "any" (the wildcard data type, see
``emergentflow/types/compatibility.py``) so it wires in anywhere: reshaping a
dataset row into LLM prompt variables, transforming a DataFrame in an ML/stats
flow, or anything else a graph needs a one-off Python transform for.

Both ``execute`` and ``codegen`` route through the same
``emergentflow.script.run_code`` wrapper via the ``ef.script.run_code`` alias
(ADR 0002): ``execute`` calls it directly against the exec'd user code; the
code emitted by ``codegen`` wraps the user's ``transform`` function inside a
per-node uniquely-named outer function (named from ``ctx.out_var``, which is
already collision-free across the graph) and calls it -- so the user's source
is never rewritten, only wrapped, and multiple custom-code nodes in one graph
never collide.

This node is intentionally unsandboxed (same trust level as the rest of the
local emergentflow server); see ``emergentflow.script.run_code`` for details.
``cacheable`` stays at its default ``True`` (custom code is assumed pure,
like every other node in the catalog) and ``requires_client`` stays at its
default ``False`` (no injected client needed).
"""

from __future__ import annotations

import ast
import textwrap
from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.script import run_code as script_run_code

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_REQUIRED_FUNCTION_NAME = "transform"


@register
class CustomCode(NodeDefinition):
    """Run user-authored Python code (a `transform(value)` function) against an input."""

    type = "script.custom_code"
    version = 1
    family = "script"
    label = "Custom Code"
    category = "Custom Code"
    description = "Run a user-authored Python transform() function against an input value."

    ports = [
        PortSpec(
            name="value",
            direction=Direction.IN,
            data_type="any",
            help="The value passed as transform()'s argument -- any upstream type.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="any",
            help="transform(value)'s return value.",
        ),
    ]
    params = [
        ParamSpec(
            name="code",
            type_token="str",
            default="",
            required=True,
            label="Code",
            help=(
                "A Python function named 'transform' taking one argument, e.g. "
                "'def transform(value):\\n    return value'. Any imports needed go "
                "inside the function body."
            ),
            hints=ValidationHints(widget="code"),
        ),
    ]

    def _code(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        return cast(str, values.get("code") or "")

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        code = self._code(node)
        fn_name = f"_run_{ctx.out_var('result')}"
        indented = textwrap.indent(code, "    ")
        return CodeFragment(
            imports=[],
            body=(
                f"def {fn_name}(value):\n"
                f"{indented}\n"
                f"    return {_REQUIRED_FUNCTION_NAME}(value)\n\n\n"
                f"{ctx.out_var('result')} = {fn_name}({ctx.in_var('value')})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        code = self._code(node)
        result = script_run_code(code, inputs["value"])
        return {"result": result}

    def validate_node(self, node: Node) -> list[str]:
        errors = super().validate_node(node)
        code = self._code(node)
        if not code:
            return errors
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            errors.append(f"param 'code' failed to parse: {exc}")
            return errors
        has_transform = any(
            isinstance(stmt, ast.FunctionDef)
            and stmt.name == _REQUIRED_FUNCTION_NAME
            and len(stmt.args.args) == 1
            for stmt in tree.body
        )
        if not has_transform:
            errors.append(
                f"param 'code' must define a top-level function "
                f"'{_REQUIRED_FUNCTION_NAME}(value)' taking exactly one argument."
            )
        return errors
