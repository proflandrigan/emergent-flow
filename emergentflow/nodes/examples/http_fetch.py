"""
emergentflow.nodes.examples.http_fetch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.http_fetch`` — a *source* node (0 inputs, 1 output).

Both ``execute`` and ``codegen`` route through the same ``ef.data.http_fetch``
wrapper, so the two paths are equivalent by construction (ADR 0002). This node
sets ``requires = frozenset({ClientKind.HTTP})``: the injected ``HttpClient`` is
threaded in by the executor / the compiled module's ``main()``, never constructed
here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clients import ClientKind
from emergentflow.data import http_fetch
from emergentflow.data.http.protocol import HttpClient
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class HttpFetch(NodeDefinition):
    """Fetch JSON records from an HTTP/REST endpoint into a DataFrame."""

    type = "data.http_fetch"
    version = 1
    family = "data"
    label = "HTTP Fetch"
    category = "Ingest"
    description = "Fetch JSON records from an HTTP/REST endpoint into a tidy DataFrame."
    requires = frozenset({ClientKind.HTTP})
    advisor_persona = "data_modeller"
    cacheable = False  # the endpoint's content can change without any param changing

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The fetched records as a tidy pandas DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="url",
            type_token="str",
            required=True,
            label="URL",
            help="The URL to fetch.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="GET",
            label="Method",
            help="HTTP method for the request.",
            hints=ValidationHints(choices=["GET", "POST"], widget="select"),
        ),
        ParamSpec(
            name="headers",
            type_token="dict",
            default=None,
            label="Headers",
            help="Optional HTTP headers as a dict of key-value pairs.",
            hints=ValidationHints(widget="json"),
        ),
        ParamSpec(
            name="params",
            type_token="dict",
            default=None,
            label="Query params",
            help="Optional query-string parameters as a dict of key-value pairs.",
            hints=ValidationHints(widget="json"),
        ),
        ParamSpec(
            name="body",
            type_token="str",
            default=None,
            label="Body",
            help="Optional request body string (e.g. JSON or form-encoded).",
            hints=ValidationHints(widget="textarea"),
        ),
        ParamSpec(
            name="connection",
            type_token="str",
            default=None,
            label="Connection",
            help="A connection-profile name (never a credential). Resolved to live "
            "credentials by the HttpClient at fetch time.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="timeout_s",
            type_token="float",
            default=None,
            label="Timeout (s)",
            help="Request timeout in seconds.",
            hints=ValidationHints(widget="number"),
        ),
        ParamSpec(
            name="json_path",
            type_token="str",
            default=None,
            label="JSON path",
            help="Dot-separated path into the JSON response to select records "
            '(e.g. "data.items"). No wildcards or array indexing are supported.',
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="flatten",
            type_token="bool",
            default=True,
            label="Flatten",
            help="When True, normalize nested JSON objects into flat columns.",
            hints=ValidationHints(widget="checkbox"),
        ),
        ParamSpec(
            name="pagination",
            type_token="str",
            default="none",
            label="Pagination",
            help="Pagination strategy: none, cursor, offset, or page.",
            hints=ValidationHints(choices=["none", "cursor", "offset", "page"], widget="select"),
        ),
        ParamSpec(
            name="cursor_param",
            type_token="str",
            default="cursor",
            label="Cursor param",
            help="Query-parameter name for the cursor value when pagination is 'cursor'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="cursor_path",
            type_token="str",
            default=None,
            label="Cursor path",
            help="Dot-separated path to the next-cursor value in the response body, "
            "required when pagination is 'cursor'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="page_param",
            type_token="str",
            default="page",
            label="Page param",
            help="Query-parameter name for the page number when pagination is 'page'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="offset_param",
            type_token="str",
            default="offset",
            label="Offset param",
            help="Query-parameter name for the offset value when pagination is 'offset'.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="page_size",
            type_token="int",
            default=None,
            label="Page size",
            help="Number of records per page; required when pagination is 'offset' or 'page'.",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="max_pages",
            type_token="int",
            default=10,
            label="Max pages",
            help="Maximum number of pages to fetch before stopping.",
            hints=ValidationHints(min=1, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "url": values.get("url") or "",
            "method": values.get("method") or "GET",
            "headers": values.get("headers"),
            "params": values.get("params"),
            "body": values.get("body"),
            "connection": values.get("connection"),
            "timeout_s": values.get("timeout_s"),
            "json_path": values.get("json_path"),
            "flatten": values.get("flatten", True) if values.get("flatten") is not None else True,
            "pagination": values.get("pagination") or "none",
            "cursor_param": values.get("cursor_param") or "cursor",
            "cursor_path": values.get("cursor_path"),
            "page_param": values.get("page_param") or "page",
            "offset_param": values.get("offset_param") or "offset",
            "page_size": values.get("page_size"),
            "max_pages": values.get("max_pages") or 10,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        lines = [
            f"{ctx.out_var('frame')} = ef.data.http_fetch(",
            f"    url={args['url']!r},",
            "    client=http,",
            f"    method={args['method']!r},",
            f"    headers={args['headers']!r},",
            f"    params={args['params']!r},",
            f"    body={args['body']!r},",
            f"    connection={args['connection']!r},",
            f"    timeout_s={args['timeout_s']!r},",
            f"    json_path={args['json_path']!r},",
            f"    flatten={args['flatten']!r},",
            f"    pagination={args['pagination']!r},",
            f"    cursor_param={args['cursor_param']!r},",
            f"    cursor_path={args['cursor_path']!r},",
            f"    page_param={args['page_param']!r},",
            f"    offset_param={args['offset_param']!r},",
            f"    page_size={args['page_size']!r},",
            f"    max_pages={args['max_pages']!r},",
            ")",
        ]
        return CodeFragment(imports=["import emergentflow as ef"], body="\n".join(lines))

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: HttpClient | None = None
    ) -> dict[str, Any]:
        args = self._args(node)
        return {"frame": http_fetch(client=client, **args)}
