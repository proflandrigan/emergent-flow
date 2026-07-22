"""
emergentflow.nodes.examples.llm_prompt_from_file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``llm.prompt_from_file`` — reads a prompt template's text
from a file on disk (issue #92 Feature 2). 0 IN ports, 1 OUT port.

Mirrors ``data.load_csv``'s split: reading a file is not a pure function of
this node's declared params (the file's content can change without the
path param changing), so it stays ``cacheable = False``. It is local
filesystem I/O, not network I/O, so it needs no injected client
(``requires_client`` stays at its default ``False``). Both ``execute`` and
``codegen`` route through the same ``emergentflow.llm.prompt_from_file``
wrapper via the ``ef.llm.prompt_from_file`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.llm import prompt_from_file as llm_prompt_from_file

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LlmPromptFromFile(NodeDefinition):
    """Read a prompt template's text from a file on disk."""

    type = "llm.prompt_from_file"
    version = 1
    family = "llm"
    label = "Prompt From File"
    category = "LLM"
    description = "Read a prompt template's text from a file on disk."
    # execute() re-reads the file at `path` on every call; the file's content can
    # change without the `path` param changing, so this is not a pure function of
    # its declared params (see NodeDefinition.cacheable's docstring, and
    # data.load_csv's identical rationale).
    cacheable = False

    ports = [
        PortSpec(
            name="text",
            direction=Direction.OUT,
            data_type="str",
            help="The file's raw text content.",
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="Template path",
            help="Filesystem path to the prompt template file (e.g. prompts/summarize.md).",
            hints=ValidationHints(widget="file"),
        ),
    ]

    def _path(self, node: Node) -> str:
        values = {p.name: p.value for p in node.params}
        return cast(str, values.get("path"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path = self._path(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('text')} = ef.llm.prompt_from_file({path!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path = self._path(node)
        return {"text": llm_prompt_from_file(path)}
