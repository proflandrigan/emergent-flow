"""
tests/test_collab_agents_base.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The AgentAdapter contract and registry (emergentflow/collab/agents/base.py).
"""

from __future__ import annotations

import pytest

from emergentflow.collab.agents.base import (
    AdapterEvent,
    AgentAdapter,
    get_adapter,
    list_adapter_names,
    list_available_adapter_names,
    register_adapter,
)


class _FakeAdapter(AgentAdapter):
    name = "fake-test-adapter"
    cli_executable = "definitely-not-a-real-cli-xyz"

    def build_command(self, *, prompt: str, resume_id: str | None) -> list[str]:
        return [self.cli_executable, prompt]

    def parse_line(self, raw_line: str) -> AdapterEvent | None:
        return None


register_adapter(_FakeAdapter)


def test_adapter_event_is_frozen_dataclass() -> None:
    event = AdapterEvent(kind="text", text="hello")
    assert event.kind == "text"
    assert event.text == "hello"


def test_register_adapter_makes_it_discoverable() -> None:
    assert "fake-test-adapter" in list_adapter_names()
    instance = get_adapter("fake-test-adapter")
    assert isinstance(instance, _FakeAdapter)


def test_get_adapter_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("no-such-adapter")


def test_detect_false_for_nonexistent_executable() -> None:
    assert _FakeAdapter.detect() is False


def test_list_available_adapter_names_excludes_undetected() -> None:
    assert "fake-test-adapter" not in list_available_adapter_names()


def test_claude_adapter_registers_via_package_import() -> None:
    import emergentflow.collab.agents  # noqa: F401

    assert "claude" in list_adapter_names()
