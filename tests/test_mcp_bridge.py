"""
tests/test_mcp_bridge.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Task 06b -- HTTP-backed stdio MCP bridge (``emergentflow.collab.mcp_bridge``).

The bridge fetches the tool catalog from ``GET /mcp/tools`` and forwards every
tool call to ``POST /mcp/invoke`` on a running server. These tests drive the
bridge against the FastAPI app in-process via an ASGI-backed ``httpx.AsyncClient``
(``app=create_app()``), so no live TCP server is needed.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from emergentflow.collab import session as session_mod
from emergentflow.server.app import create_app


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default SessionStore per test (mirror
    ``test_server_mcp_invoke.py``) so sessions created by one test never leak
    into another.
    """
    monkeypatch.setattr(session_mod, "_default_store", None)


def test_bridge_lists_and_registers_tools() -> None:
    """The bridge registers one tool per server tool, derived from /mcp/tools."""
    from emergentflow.collab.mcp_bridge import create_bridge_mcp_server

    async def _scenario() -> set[str]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()),
            base_url="http://testserver",
        ) as client:
            mcp = await create_bridge_mcp_server("http://testserver", _http_client=client)
            tools = await mcp.list_tools()
            return {t.name for t in tools}

    names = asyncio.run(_scenario())
    assert "add_node" in names


def test_bridge_add_node_forwards() -> None:
    """A tool call through the bridge reaches the server and mutates its store."""
    from emergentflow.collab.mcp_bridge import create_bridge_mcp_server

    async def _scenario() -> tuple[dict, str]:
        session = session_mod.get_default_store().create()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()),
            base_url="http://testserver",
        ) as client:
            mcp = await create_bridge_mcp_server("http://testserver", _http_client=client)
            result = await mcp.call_tool(
                "add_node",
                {
                    "session_id": session.id,
                    "node_type": "data.load_csv",
                    "params": {"path": "a.csv"},
                },
            )
            return result.structured_content, session.id

    content, session_id = asyncio.run(_scenario())
    assert "checkpoint_id" in content
    # The node now exists in the server's session store.
    stored = session_mod.get_default_store().get(session_id)
    assert content["node_id"] in stored.graph.nodes


def test_bridge_forwards_tool_error() -> None:
    """A server-side tool error surfaces as a ToolError through the bridge."""
    from fastmcp.exceptions import ToolError

    from emergentflow.collab.mcp_bridge import create_bridge_mcp_server

    async def _scenario() -> None:
        session = session_mod.get_default_store().create()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()),
            base_url="http://testserver",
        ) as client:
            mcp = await create_bridge_mcp_server("http://testserver", _http_client=client)
            await mcp.call_tool(
                "add_node",
                {"session_id": session.id, "node_type": "no.such.node"},
            )

    with pytest.raises(ToolError):
        asyncio.run(_scenario())


def test_bridge_forwards_explicit_none_for_required_param() -> None:
    """A ``None`` value for a REQUIRED param is forwarded, not dropped.

    Required params must reach the server verbatim (e.g. ``set_param``'s
    ``value``), otherwise an agent clearing a param to ``null`` would silently
    lose the argument. Only *optional* params that default to ``None`` are
    dropped to let the server apply its own defaults.
    """
    from emergentflow.collab.mcp_bridge import _make_wrapper

    received: dict[str, object] = {}

    async def invoke(tool_name: str, arguments: dict[str, object]) -> object:
        assert tool_name == "set_param"
        received["arguments"] = arguments
        return {}

    wrapper = _make_wrapper(
        "set_param",
        ["session_id", "node_id", "param_name", "value", "author", "reason"],
        {"session_id", "node_id", "param_name", "value"},
        invoke,
    )

    async def _scenario() -> None:
        await wrapper("s1", "n1", "encoding", None)

    asyncio.run(_scenario())
    args = received["arguments"]
    # Required ``value`` preserved as None; optional ``author``/``reason`` dropped
    # from their defaults so the server applies its own.
    assert args["value"] is None
    assert "author" not in args
    assert "reason" not in args


def test_bridge_drops_none_optional_param() -> None:
    """An optional param left at its ``None`` default is dropped, not sent."""
    from emergentflow.collab.mcp_bridge import _make_wrapper

    received: dict[str, object] = {}

    async def invoke(tool_name: str, arguments: dict[str, object]) -> object:
        received["arguments"] = arguments
        return {}

    wrapper = _make_wrapper(
        "add_note",
        ["session_id", "content", "anchor_id", "color"],
        {"session_id", "content"},
        invoke,
    )

    async def _scenario() -> None:
        await wrapper("s1", "hello")

    asyncio.run(_scenario())
    assert received["arguments"] == {"session_id": "s1", "content": "hello"}
