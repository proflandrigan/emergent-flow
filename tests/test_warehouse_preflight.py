"""Tests for the warehouse connection/credential pre-flight check (Epic 13 Story 3).

Builds minimal `Graph`/`Node` fixtures directly, mirroring `tests/test_llm_secrets.py`'s
construction style, since `validate_connections_present` only needs a `Graph` object, not a
served payload.
"""

from __future__ import annotations

import pytest

from emergentflow.data.warehouse.credentials import MissingConnectionCredentialError
from emergentflow.data.warehouse.preflight import (
    MissingConnectionProfileError,
    validate_connections_present,
)
from emergentflow.data.warehouse.profiles import ConnectionProfile, ProfileStore
from emergentflow.ir import Direction, Graph, Node, Paradigm, Param, Port, Position


def _connection_node(
    node_id: str = "n-query", *, connection: str | None = "warehouse_prod"
) -> Node:
    params = []
    if connection is not None:
        params.append(Param(name="connection", type_token="ConnectionRef", value=connection))
    return Node(
        id=node_id,
        type="warehouse.query",
        label="Warehouse Query",
        paradigm=Paradigm.FUNCTIONAL,
        params=params,
        ports=[
            Port(
                id=f"p-{node_id}-result",
                name="result",
                direction=Direction.OUT,
                data_type="QueryResult",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )


def _graph(*nodes: Node) -> Graph:
    return Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="preflight-test",
        nodes={n.id: n for n in nodes},
        edges={},
    )


def _profile_with_password_env() -> ConnectionProfile:
    return ConnectionProfile(
        name="warehouse_prod",
        dialect="postgres",
        auth_method="password_env",
        credential_refs={"password_env": "PGPASSWORD"},
    )


def test_missing_profile_raises() -> None:
    graph = _graph(_connection_node(connection="warehouse_prod"))
    store = ProfileStore()

    with pytest.raises(MissingConnectionProfileError) as exc_info:
        validate_connections_present(graph, store)

    assert "warehouse_prod" in str(exc_info.value)


def test_missing_credential_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PGPASSWORD", raising=False)
    graph = _graph(_connection_node(connection="warehouse_prod"))
    store = ProfileStore()
    store.add(_profile_with_password_env())

    with pytest.raises(MissingConnectionCredentialError) as exc_info:
        validate_connections_present(graph, store)

    assert "PGPASSWORD" in str(exc_info.value)


def test_all_present_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPASSWORD", "s3cr3t")
    graph = _graph(_connection_node(connection="warehouse_prod"))
    store = ProfileStore()
    store.add(_profile_with_password_env())

    validate_connections_present(graph, store)  # must not raise


def test_node_without_connection_is_skipped() -> None:
    graph = _graph(_connection_node("n-plain", connection=None))
    store = ProfileStore()

    validate_connections_present(graph, store)  # must not raise


def test_node_ids_subset_scopes_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPASSWORD", "s3cr3t")
    known_node = _connection_node("n-known", connection="warehouse_prod")
    unknown_node = _connection_node("n-unknown", connection="warehouse_staging")
    graph = _graph(known_node, unknown_node)
    store = ProfileStore()
    store.add(_profile_with_password_env())

    validate_connections_present(graph, store, node_ids=["n-known"])  # must not raise

    with pytest.raises(MissingConnectionProfileError):
        validate_connections_present(graph, store)
