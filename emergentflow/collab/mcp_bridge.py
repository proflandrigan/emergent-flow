"""
emergentflow.collab.mcp_bridge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HTTP-backed stdio MCP bridge (Task 06b).

This module builds a FastMCP server whose tools are *thin forwarders*: it fetches
the tool catalog from ``GET /mcp/tools`` on a running ``emergentflow serve``
process and forwards every tool call to ``POST /mcp/invoke``. The agent sees the
exact same tool surface as the in-process server (``emergentflow.collab.mcp``)
without duplicating any tool logic or per-tool wrappers.

Only ``create_bridge_mcp_server`` performs network I/O; importing this module is
side-effect free. ``fastmcp`` and ``httpx`` are optional dependencies (the
``[mcp]`` extra) -- the CLI prints an install hint if either is missing.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError


def _collect_schema_types(p: dict) -> set[str]:
    """Collect the JSON-schema type tokens declared by property *p*, descending into
    ``anyOf``/``oneOf`` so an optional param's type is found even when wrapped in
    ``anyOf: [ {.., "type": X}, {"type": "null"} ]`` (FastMCP renders optional params this
    way)."""
    t = p.get("type")
    if isinstance(t, str):
        return {t}
    types: set[str] = set()
    for key in ("anyOf", "oneOf"):
        subs = p.get(key)
        if isinstance(subs, list):
            for sub in subs:
                if isinstance(sub, dict):
                    types |= _collect_schema_types(sub)
    return types


def _complex_schema_names(properties: dict) -> set[str]:
    """Return the set of param names whose JSON-schema type is ``object`` or ``array``.

    These are the arguments that a caller's MCP client is liable to deliver to the bridge
    as JSON strings; the bridge must parse them back to objects before forwarding.
    """
    names: set[str] = set()
    for name, p in properties.items():
        if not isinstance(p, dict):
            continue
        if {"object", "array"} & _collect_schema_types(p):
            names.add(name)
    return names


def _make_wrapper(
    tool_name: str,
    param_names: list[str],
    required: set[str],
    invoke: Any,
    complex_names: set[str] | None = None,
) -> Any:
    """Build an async wrapper whose signature mirrors a tool's ``inputSchema``.

    Required parameters get no default; optional parameters default to ``None``.
    The body forwards every argument to *invoke* EXCEPT ``None`` values on
    optional parameters (which the caller omitted and the server should apply
    its own default to); an explicitly-``None`` value for a REQUIRED parameter
    is preserved so callers can still pass a meaningful ``null``. ``exec`` is
    used to synthesize the signature because it cannot be expressed with a
    fixed ``def``; the generated function closes over *invoke* through its
    globals.
    """
    params: list[str] = []
    for name in param_names:
        if name in required:
            params.append(f"{name}: Any")
        else:
            params.append(f"{name}: Any = None")
    signature = ", ".join(params)
    source = (
        f"async def wrapper({signature}):\n"
        f"    args = {{k: v for k, v in locals().items() "
        f"if v is not None or k in _required}}\n"
        f"    for _name in _complex_names:\n"
        f"        if _name in args and isinstance(args[_name], str):\n"
        f"            args[_name] = json.loads(args[_name])\n"
        f"    return await _invoke({tool_name!r}, args)\n"
    )
    namespace: dict[str, Any] = {
        "_invoke": invoke,
        "_required": required,
        "_complex_names": complex_names or set(),
        "json": json,
        "Any": Any,
    }
    exec(source, namespace)
    return namespace["wrapper"]


async def create_bridge_mcp_server(
    base_url: str,
    token: str | None = None,
    *,
    _http_client: httpx.AsyncClient | None = None,
) -> FastMCP:
    """Build a stdio MCP server whose tools forward to an Emergent Flow server.

    Fetches the tool catalog from ``GET {base_url}/mcp/tools`` and registers one
    async wrapper per tool that forwards to ``POST {base_url}/mcp/invoke``. The
    optional ``_http_client`` is for tests (an ASGI-backed client); the CLI path
    creates its own ``httpx.AsyncClient``.

    Raises ``RuntimeError`` if the catalog request fails, so the CLI can print a
    helpful message when the server is unreachable.
    """
    client = _http_client or httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=600.0, write=10.0, pool=10.0)
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        tools_response = await client.get(f"{base_url}/mcp/tools", headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"failed to reach Emergent Flow server at {base_url}: {exc}") from exc
    if tools_response.status_code >= 400:
        raise RuntimeError(
            f"failed to fetch MCP tool catalog from {base_url}/mcp/tools: "
            f"HTTP {tools_response.status_code}: {tools_response.text}"
        )
    tools = tools_response.json().get("tools", [])

    async def _invoke(tool_name: str, arguments: dict[str, Any]) -> Any:
        """Forward a single tool call to the server's ``/mcp/invoke`` route."""
        response = await client.post(
            f"{base_url}/mcp/invoke",
            json={"tool_name": tool_name, "arguments": arguments},
            headers=headers,
        )
        if response.status_code >= 400:
            raise ToolError(f"HTTP {response.status_code}: {response.text}")
        return response.json()

    mcp = FastMCP("emergent-flow-bridge")
    for tool in tools:
        name = tool["name"]
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        wrapper = _make_wrapper(
            name,
            list(properties.keys()),
            required,
            _invoke,
            complex_names=_complex_schema_names(properties),
        )
        # fastmcp derives the tool name from the function's __name__ (there is no
        # name= kwarg on add_tool in this version), so stamp it before registering.
        wrapper.__name__ = name
        wrapper.__doc__ = tool.get("description")
        mcp.add_tool(wrapper)
    return mcp
