"""
emergentflow.collab.agents
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Coding-agent CLI adapters for the in-app chat feature (see emergentflow/collab/chat.py for the
ChatTurn/ChatState models). Importing this package registers every adapter module below via
their @register_adapter decorator -- the same self-registration pattern emergentflow.nodes uses
for reference nodes.

Never imported by emergentflow/__init__.py or emergentflow/ir/graph.py (works-without-agents
invariant, ADR 0019) -- these CLIs are entirely optional, spawned only when a user starts an
in-app chat.
"""

from __future__ import annotations

from emergentflow.collab.agents import (  # noqa: F401
    claude_adapter,
    codex_adapter,
    gemini_adapter,
    opencode_adapter,
)
from emergentflow.collab.agents.base import (
    AdapterEvent,
    AgentAdapter,
    get_adapter,
    list_adapter_names,
    list_available_adapter_names,
    register_adapter,
)

__all__ = [
    "AdapterEvent",
    "AgentAdapter",
    "get_adapter",
    "list_adapter_names",
    "list_available_adapter_names",
    "register_adapter",
]
