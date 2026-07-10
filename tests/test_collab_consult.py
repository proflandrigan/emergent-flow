"""
tests/test_collab_consult.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mode-B consult tests: unit tests for build_consult_messages / run_consult,
service-layer tests for consult_graph / consult_session, and HTTP smoke tests
for POST /consult and POST /sessions/{id}/consult.

Every test uses a hand-built fake LLMClient -- no ReplayClient fixtures, no
network calls (Task 07 owns the ReplayClient / replay-fixture tests).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.collab.consult import ConsultError, build_consult_messages, run_consult
from emergentflow.ir.serialize import deserialize_graph
from emergentflow.llm.protocol import LLMRequest, LLMResponse, Usage
from emergentflow.server.app import create_app
from emergentflow.server.service import consult_graph, consult_session

# ---------------------------------------------------------------------------
# Hand-built fake LLMClient (Task 07 owns ReplayClient fixture tests)
# ---------------------------------------------------------------------------


class FakeClient:
    """Hand-built fake ``LLMClient`` returning pre-canned responses.

    Never touches a real network.  ``response_data`` is returned directly as
    ``LLMResponse.data`` (``None`` tests the ``ConsultError`` path).
    """

    def __init__(self, response_data: dict[str, Any] | None = None) -> None:
        self.response_data = response_data
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            text=None,
            data=self.response_data,
            model="fake-model",
            usage=Usage(input_tokens=10, output_tokens=10),
            cost_usd=0.0,
            latency_ms=0.0,
            finish_reason="stop",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LOAD_CSV_NODE = {
    "id": "n1",
    "type": "data.load_csv",
    "label": "Load",
    "paradigm": "functional",
    "params": [{"name": "path", "type_token": "str", "value": "a.csv", "default": None}],
    "ports": [
        {
            "id": "p1",
            "name": "frame",
            "direction": "out",
            "data_type": "DataFrame",
            "cardinality": "one",
        }
    ],
    "position": {"x": 0.0, "y": 0.0},
    "group_id": None,
}


@pytest.fixture(autouse=True)
def _register_personas() -> None:
    """Register builtin personas so consult routes can resolve persona slugs."""
    from emergentflow.collab.persona_defs import register_builtin_personas

    register_builtin_personas()


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the process-wide default SessionStore per test."""
    monkeypatch.setattr(session_mod, "_default_store", None)


@pytest.fixture
def seeded_graph() -> dict:
    return {"nodes": {"n1": LOAD_CSV_NODE}, "edges": {}}


@pytest.fixture
def graph(seeded_graph: dict):
    return deserialize_graph(json.dumps(seeded_graph))


# ---------------------------------------------------------------------------
# build_consult_messages
# ---------------------------------------------------------------------------


class TestBuildConsultMessages:
    def test_returns_two_messages(self, graph: Any) -> None:
        messages = build_consult_messages(
            graph, persona_slug="data_modeller", node_ids=["n1"], ask="what path?"
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_user_message_mentions_target_node(self, graph: Any) -> None:
        messages = build_consult_messages(
            graph, persona_slug="data_modeller", node_ids=["n1"], ask="change it"
        )
        assert "n1" in messages[1]["content"]
        assert "data.load_csv" in messages[1]["content"]

    def test_unknown_node_id_raises_consult_error(self, graph: Any) -> None:
        with pytest.raises(ConsultError, match="not found"):
            build_consult_messages(
                graph, persona_slug="data_modeller", node_ids=["does-not-exist"], ask="fix"
            )

    def test_unknown_persona_raises(self, graph: Any) -> None:
        from emergentflow.collab.personas import UnknownPersonaError

        with pytest.raises(UnknownPersonaError):
            build_consult_messages(graph, persona_slug="nobody", node_ids=["n1"], ask="fix")


# ---------------------------------------------------------------------------
# run_consult
# ---------------------------------------------------------------------------


class TestRunConsult:
    def test_returns_mutation_with_set_params(self, graph: Any) -> None:
        fake = FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}})
        mutation = run_consult(
            graph,
            persona_slug="data_modeller",
            node_ids=["n1"],
            ask="change path",
            base_version=0,
            client=fake,
        )
        assert mutation.set_params == {"n1": {"path": "b.csv"}}
        assert mutation.base_version == 0
        assert mutation.author == "data_modeller"
        assert "Consult (data_modeller)" in mutation.description

    def test_none_data_raises_consult_error(self, graph: Any) -> None:
        fake = FakeClient(response_data=None)  # LLMResponse.data will be None
        with pytest.raises(ConsultError, match="set_params"):
            run_consult(
                graph,
                persona_slug="data_modeller",
                node_ids=["n1"],
                ask="change",
                base_version=0,
                client=fake,
            )


# ---------------------------------------------------------------------------
# consult_graph (service function)
# ---------------------------------------------------------------------------


class TestConsultGraph:
    def test_returns_mutation_and_diagnostics(self, seeded_graph: dict) -> None:
        fake = FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}})
        result = consult_graph(
            {
                "graph": seeded_graph,
                "persona": "data_modeller",
                "node_ids": ["n1"],
                "ask": "change path",
            },
            client=fake,
        )
        assert "mutation" in result
        assert "diagnostics" in result
        assert result["mutation"]["set_params"] == {"n1": {"path": "b.csv"}}

    def test_clean_diagnostics_for_well_formed_response(self, seeded_graph: dict) -> None:
        fake = FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}})
        result = consult_graph(
            {"graph": seeded_graph, "persona": "data_modeller", "node_ids": ["n1"], "ask": "x"},
            client=fake,
        )
        assert result["diagnostics"]["diagnostics"] == []


# ---------------------------------------------------------------------------
# consult_session (service function)
# ---------------------------------------------------------------------------


class TestConsultSession:
    def test_returns_proposal_dict(self, seeded_graph: dict) -> None:
        store = session_mod.get_default_store()
        session = store.create(deserialize_graph(json.dumps(seeded_graph)))

        fake = FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}})
        result = consult_session(
            session.id,
            {"persona": "data_modeller", "node_ids": ["n1"], "ask": "change path"},
            client=fake,
        )
        assert "id" in result
        assert "mutation" in result
        assert "diagnostics" in result
        assert result["status"] == "pending"
        assert result["mutation"]["set_params"] == {"n1": {"path": "b.csv"}}

    def test_proposal_stored_in_session(self, seeded_graph: dict) -> None:
        store = session_mod.get_default_store()
        session = store.create(deserialize_graph(json.dumps(seeded_graph)))

        fake = FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}})
        result = consult_session(
            session.id,
            {"persona": "data_modeller", "node_ids": ["n1"], "ask": "change path"},
            client=fake,
        )
        session = store.get(session.id)
        assert result["id"] in session.proposals

    def test_unknown_session_raises(self) -> None:
        fake = FakeClient()
        with pytest.raises(session_mod.UnknownSessionError):
            consult_session(
                "does-not-exist",
                {"persona": "data_modeller", "node_ids": ["n1"], "ask": "x"},
                client=fake,
            )


# ---------------------------------------------------------------------------
# HTTP smoke tests via TestClient
# ---------------------------------------------------------------------------


class TestConsultHTTP:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(create_app())

    def test_post_consult_returns_200(
        self, client: TestClient, seeded_graph: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        monkeypatch.setattr(
            sys.modules["emergentflow.server.app"],
            "GatewayClient",
            lambda: FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}}),
        )
        resp = client.post(
            "/consult",
            json={
                "graph": seeded_graph,
                "persona": "data_modeller",
                "node_ids": ["n1"],
                "ask": "what path?",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "mutation" in body
        assert "diagnostics" in body
        assert body["mutation"]["set_params"] == {"n1": {"path": "b.csv"}}

    def test_post_consult_bad_json_400(self, client: TestClient) -> None:
        resp = client.post(
            "/consult", content=b"not json", headers={"content-type": "application/json"}
        )
        assert resp.status_code == 400, resp.text

    def test_post_session_consult_returns_proposal(
        self, client: TestClient, seeded_graph: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        monkeypatch.setattr(
            sys.modules["emergentflow.server.app"],
            "GatewayClient",
            lambda: FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}}),
        )
        session_id = client.post("/sessions", json={"graph": seeded_graph}).json()["id"]

        resp = client.post(
            f"/sessions/{session_id}/consult",
            json={
                "persona": "data_modeller",
                "node_ids": ["n1"],
                "ask": "change path",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["mutation"]["set_params"] == {"n1": {"path": "b.csv"}}

    def test_post_session_consult_unknown_session_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        monkeypatch.setattr(
            sys.modules["emergentflow.server.app"],
            "GatewayClient",
            lambda: FakeClient(response_data={"set_params": {"n1": {"path": "b.csv"}}}),
        )
        resp = client.post(
            "/sessions/does-not-exist/consult",
            json={"persona": "data_modeller", "node_ids": ["n1"], "ask": "x"},
        )
        assert resp.status_code == 404, resp.text
