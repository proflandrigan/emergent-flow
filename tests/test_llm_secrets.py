"""Tests for the API-key pre-flight check (Epic 9 Story 9).

Builds minimal `Graph`/`Node` fixtures directly (mirroring `tests/test_server.py`'s
`_load_csv_graph()` style) rather than round-tripping through JSON, since
`validate_api_keys_present` only needs a `Graph` object, not a served payload.
"""

from __future__ import annotations

import pytest

from emergentflow.ir import Direction, Graph, Node, Paradigm, Param, Port, Position
from emergentflow.llm.env import MissingAPIKeyError
from emergentflow.llm.secrets import validate_api_keys_present


def _llm_call_node(
    node_id: str = "n-llm",
    *,
    provider: str = "anthropic",
    api_key_env: str | None = None,
) -> Node:
    params = [Param(name="provider", type_token="str", value=provider)]
    if api_key_env is not None:
        params.append(Param(name="api_key_env", type_token="str", value=api_key_env))
    return Node(
        id=node_id,
        type="llm.call",
        label="LLM Call",
        paradigm=Paradigm.FUNCTIONAL,
        params=params,
        ports=[
            Port(
                id=f"p-{node_id}-response",
                name="response",
                direction=Direction.OUT,
                data_type="LLMResponse",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )


def _eval_run_node(node_id: str = "n-eval", *, variants: list[dict] | None = None) -> Node:
    return Node(
        id=node_id,
        type="eval.run",
        label="Eval Run",
        paradigm=Paradigm.FUNCTIONAL,
        params=[
            Param(name="system", type_token="str", value=""),
            Param(name="user", type_token="str", value=""),
            Param(name="variants", type_token="list[dict]", value=variants or []),
        ],
        ports=[
            Port(
                id=f"p-{node_id}-dataset",
                name="dataset",
                direction=Direction.IN,
                data_type="DataFrame",
            ),
            Port(
                id=f"p-{node_id}-results",
                name="results",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )


def _load_csv_node(node_id: str = "n-load") -> Node:
    return Node(
        id=node_id,
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="path", type_token="str", value="/no/such/file.csv")],
        ports=[
            Port(
                id=f"p-{node_id}-frame",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )


def _graph(*nodes: Node) -> Graph:
    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="secrets-test",
        nodes={n.id: n for n in nodes},
        edges={},
    )


def test_llm_call_with_default_env_var_set_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    graph = _graph(_llm_call_node(provider="anthropic"))
    validate_api_keys_present(graph)  # must not raise


def test_llm_call_with_env_var_unset_raises_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    graph = _graph(_llm_call_node(provider="anthropic"))
    with pytest.raises(MissingAPIKeyError) as exc_info:
        validate_api_keys_present(graph)
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_llm_call_with_explicit_api_key_env_checks_that_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MY_CUSTOM_KEY", "x")
    graph = _graph(_llm_call_node(provider="anthropic", api_key_env="MY_CUSTOM_KEY"))
    validate_api_keys_present(graph)  # must not raise -- proves MY_CUSTOM_KEY was checked


def test_eval_run_checks_every_variant_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    graph = _graph(
        _eval_run_node(variants=[{"provider": "anthropic"}, {"provider": "openai"}]),
    )
    with pytest.raises(MissingAPIKeyError) as exc_info:
        validate_api_keys_present(graph)
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_non_client_node_is_never_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    graph = _graph(_load_csv_node())
    validate_api_keys_present(graph)  # must not raise -- data.load_csv doesn't require_client


def test_node_ids_restricts_which_nodes_are_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("MY_CUSTOM_KEY", raising=False)
    set_node = _llm_call_node("n-llm-set", provider="anthropic")
    unset_node = _llm_call_node("n-llm-unset", provider="anthropic", api_key_env="MY_CUSTOM_KEY")
    graph = _graph(set_node, unset_node)

    validate_api_keys_present(graph, node_ids=["n-llm-set"])  # must not raise

    with pytest.raises(MissingAPIKeyError):
        validate_api_keys_present(graph)
