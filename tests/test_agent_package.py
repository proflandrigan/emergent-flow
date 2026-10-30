"""Packaging checks for the ``agents/`` skill + Claude Code plugin."""

from __future__ import annotations

import json
import re
from pathlib import Path

import emergentflow

_ROOT = Path(__file__).resolve().parents[1]
_AGENTS = _ROOT / "agents"


def test_every_agent_doc_links_the_reply_contract() -> None:
    for path in sorted(_AGENTS.glob("*.md")):
        if path.name == "_reply-contract.md":
            continue
        text = path.read_text(encoding="utf-8")
        assert "(./_reply-contract.md)" in text, path.name


def test_relative_links_resolve_inside_agents_dir() -> None:
    base = _AGENTS.resolve()
    for path in sorted(_AGENTS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for m in re.findall(r"\]\((\.{1,2}/[^)#\s]+)", text):
            target = (_AGENTS / m).resolve()
            assert target.is_file(), f"{path.name}: {m}"
            assert target.is_relative_to(base), f"{path.name}: {m}"


def test_skill_front_matter() -> None:
    lines = (_AGENTS / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    block = lines[1:end]
    assert "name: emergent-flow" in block
    front = "\n".join(block)
    for phrase in ("build a pipeline", "analyse this CSV on the canvas", "review this flow"):
        assert phrase in front


def test_plugin_and_marketplace_manifests() -> None:
    plugin = json.loads((_AGENTS / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    mcp = json.loads((_AGENTS / ".mcp.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "emergent-flow"
    assert plugin["skills"] == ["./"]
    assert plugin["mcpServers"] == "./.mcp.json"
    assert market["plugins"][0]["source"] == "./agents"
    assert market["plugins"][0]["name"] == "emergent-flow"
    server = mcp["mcpServers"]["emergent-flow"]
    assert server["command"] == "emergentflow"
    assert server["args"][:2] == ["mcp", "--base-url"]
    assert plugin["version"] == emergentflow.__version__
    assert market["plugins"][0]["version"] == emergentflow.__version__


def test_mcp_config_has_no_token() -> None:
    text = (_AGENTS / ".mcp.json").read_text(encoding="utf-8").lower()
    assert "token" not in text
    assert "bearer" not in text
