"""
tests/test_regression_no_ambient_llm.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14 Story 11 gate: prove that no session/proposal/review/gate/knowledge route ever
constructs a live LLM client — only /consult and /sessions/{id}/consult may, and only because
a user explicitly asked for a consult. The static AST check confirms GatewayClient()
construction is lexically confined to the two consult handlers; the runtime check drives the
real routes through TestClient with a spy on GatewayClient to prove it behaviorally.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import knowledge as knowledge_mod
from emergentflow.collab import session as session_mod
from emergentflow.collab.knowledge import KnowledgeEntry, KnowledgeStore
from emergentflow.ir.graph import Graph
from emergentflow.server.app import configure_session_auth, create_app

# ---------------------------------------------------------------------------
# Part A — static AST helpers
# ---------------------------------------------------------------------------


def _functions_constructing_gateway_client(source: str) -> set[str]:
    """Return the names of every function (at any nesting depth) whose body
    directly contains a ``GatewayClient(...)`` call site.
    """
    tree = ast.parse(source)
    found: set[str] = set()

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._stack: list[str] = []

        def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self._stack.append(node.name)
            self.generic_visit(node)
            self._stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_fn(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_fn(node)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "GatewayClient" and self._stack:
                found.add(self._stack[-1])
            self.generic_visit(node)

    _Visitor().visit(tree)
    return found


# ---------------------------------------------------------------------------
# Fixtures — session-store / knowledge-store isolation, personas
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _register_personas() -> None:
    from emergentflow.collab.persona_defs import register_builtin_personas

    register_builtin_personas()


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "_default_store", None)
    configure_session_auth(required=False)


@pytest.fixture(autouse=True)
def _fresh_knowledge_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        knowledge_mod, "_default_store", KnowledgeStore(path=tmp_path / "knowledge.json")
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Part A — Static checks
# ---------------------------------------------------------------------------


def test_gateway_client_only_constructed_in_consult_handlers() -> None:
    app_source = (
        Path(__file__).resolve().parents[1] / "emergentflow" / "server" / "app.py"
    ).read_text()
    constructing_functions = _functions_constructing_gateway_client(app_source)
    assert constructing_functions == {"_consult"}


@pytest.mark.parametrize(
    "relative_path",
    [
        "emergentflow/collab/session.py",
        "emergentflow/collab/review.py",
        "emergentflow/collab/gates.py",
        "emergentflow/collab/knowledge.py",
    ],
)
def test_collab_store_modules_never_construct_a_gateway_client(relative_path: str) -> None:
    source = (Path(__file__).resolve().parents[1] / relative_path).read_text()
    assert "GatewayClient(" not in source


# ---------------------------------------------------------------------------
# Part B — Runtime check via TestClient (spy on GatewayClient)
# ---------------------------------------------------------------------------


class _GatewayClientSpy:
    """Spy that records every construction but refuses to complete requests."""

    call_count = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).call_count += 1

    def complete(self, *args: object, **kwargs: object) -> None:  # type: ignore[explicit-any]
        msg = "this spy is not meant to actually complete a request"
        raise NotImplementedError(msg)


def _reset_spy() -> None:
    _GatewayClientSpy.call_count = 0


def test_no_ambient_llm_during_session_lifecycle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_spy()
    monkeypatch.setattr(
        sys.modules["emergentflow.server.app"],
        "GatewayClient",
        _GatewayClientSpy,
    )

    # 1. Create a session
    r = client.post("/sessions", json={})
    assert r.status_code == 200
    session_id = r.json()["id"]

    # 2. Submit a proposal
    r = client.post(
        f"/sessions/{session_id}/proposals",
        json={"base_version": 0},
    )
    assert r.status_code == 200
    proposal_id = r.json()["id"]

    # 3. Accept the proposal
    r = client.post(f"/sessions/{session_id}/proposals/{proposal_id}/accept")
    assert r.status_code == 200

    # 4. Post a review
    r = client.post(
        f"/sessions/{session_id}/reviews",
        json={"author": "human", "findings": []},
    )
    assert r.status_code == 200

    # 5. Open a gate
    r = client.post(
        f"/sessions/{session_id}/gates",
        json={"phase": "review", "kind": "phase", "description": "test gate"},
    )
    assert r.status_code == 200
    gate_id = r.json()["id"]

    # 6. Close the gate
    r = client.post(f"/sessions/{session_id}/gates/{gate_id}/close")
    assert r.status_code == 200

    # 7. Save a knowledge entry via HTTP
    r = client.post(
        "/knowledge",
        json=KnowledgeEntry(
            slug="ambient-test",
            description="Test entry",
            subgraph=Graph(nodes={}, edges={}),
            created_by="human",
        ).model_dump(mode="json"),
    )
    assert r.status_code == 200

    # --- Assert: GatewayClient was NEVER constructed ---
    assert _GatewayClientSpy.call_count == 0, (
        f"GatewayClient was constructed {_GatewayClientSpy.call_count} time(s) "
        f"during the session lifecycle — one of the routes constructed a live LLM client"
    )


def test_consult_route_constructs_gateway_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: prove the spy can detect GatewayClient construction."""
    _reset_spy()
    monkeypatch.setattr(
        sys.modules["emergentflow.server.app"],
        "GatewayClient",
        _GatewayClientSpy,
    )

    client.post(
        "/consult",
        json={
            "graph": {"nodes": {}, "edges": {}},
            "persona": "data_modeller",
            "node_ids": [],
            "ask": "hello",
        },
    )

    assert _GatewayClientSpy.call_count >= 1, (
        "POST /consult did not construct GatewayClient — the spy-based check is not load-bearing"
    )
