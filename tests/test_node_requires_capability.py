"""Tests for ``NodeDefinition.requires`` / ``required_client_kinds`` (ADR 0018, Task 08)."""

from typing import Any

from emergentflow.clients import ClientKind
from emergentflow.nodes import get
from emergentflow.nodes.contract import CodeFragment, NodeDefinition


def test_pure_node_requires_nothing() -> None:
    assert get("data.load_csv").required_client_kinds() == frozenset()


def test_llm_node_requires_llm_via_legacy_boolean() -> None:
    assert get("llm.call").required_client_kinds() == frozenset({ClientKind.LLM})


def test_declared_requires_capability() -> None:
    class ThrowawayWarehouseNode(NodeDefinition):
        type = "test.throwaway_warehouse_node"
        family = "test"
        label = "Throwaway Warehouse Node"
        requires = frozenset({ClientKind.WAREHOUSE})

        def codegen(self, node: Any, ctx: Any) -> CodeFragment:
            return CodeFragment()

        def execute(self, node: Any, inputs: dict[str, Any]) -> dict[str, Any]:
            return {}

    assert ThrowawayWarehouseNode.required_client_kinds() == frozenset({ClientKind.WAREHOUSE})


def test_base_requires_is_empty_frozenset() -> None:
    assert NodeDefinition.requires == frozenset()
