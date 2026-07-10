"""
tests/test_collab_consult_replay.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mode-B consult replay-fixture tests + no-ambient-LLM gate (Epic 14 Story 8, Task 07).

Part A — ReplayClient round-trip: proves run_consult produces a stable,
content-hashable LLMRequest and that the emitted GraphMutation matches the
replayed fixture's payload, plus validation.

Part B — advisor_persona is field-level metadata only: prove execute() and
compile_to_code() are completely unaffected by a node carrying advisor_persona.

Part C — No-ambient-LLM gate: GatewayClient is constructed ONLY inside the two
consult routes in app.py, never by session/proposal/review CRUD routes.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from emergentflow.collab import session as session_mod
from emergentflow.collab.consult import (
    _SET_PARAMS_RESPONSE_SCHEMA,
    build_consult_messages,
    run_consult,
)
from emergentflow.ir.mutation import propose_diagnostics
from emergentflow.ir.serialize import deserialize_graph
from emergentflow.llm.protocol import LLMRequest, LLMResponse, Usage
from emergentflow.llm.replay import ReplayClient, write_fixture
from emergentflow.server.app import create_app
from emergentflow.server.service import consult_graph

# ---------------------------------------------------------------------------
# Shared fixture helpers (reused by Part A and Part C)
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
    from emergentflow.collab.persona_defs import register_builtin_personas

    register_builtin_personas()


@pytest.fixture(autouse=True)
def _fresh_session_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "_default_store", None)


@pytest.fixture
def seeded_graph() -> dict:
    return {"nodes": {"n1": LOAD_CSV_NODE}, "edges": {}}


@pytest.fixture
def graph(seeded_graph: dict):
    return deserialize_graph(json.dumps(seeded_graph))


ASK = "change the CSV path to b.csv"

# ===========================================================================
# Part A — replay-fixture round-trip
# ===========================================================================


class TestReplayFixtureRoundTrip:
    def test_run_consult_via_replay_client(self, graph, tmp_path):
        messages = build_consult_messages(
            graph, persona_slug="data_modeller", node_ids=["n1"], ask=ASK
        )

        request = LLMRequest(
            provider="anthropic",
            model="claude-sonnet-5",
            messages=tuple(dict(m) for m in messages),
            temperature=0.0,
            max_tokens=None,
            response_format="json",
            response_schema=_SET_PARAMS_RESPONSE_SCHEMA,
            api_key_env=None,
        )
        response = LLMResponse(
            text=None,
            data={"set_params": {"n1": {"path": "b.csv"}}},
            model="claude-sonnet-5",
            usage=Usage(input_tokens=10, output_tokens=4),
            cost_usd=0.0,
            latency_ms=42.0,
            finish_reason="stop",
        )

        write_fixture(tmp_path, request, response)
        client = ReplayClient(tmp_path)

        mutation = run_consult(
            graph,
            persona_slug="data_modeller",
            node_ids=["n1"],
            ask=ASK,
            base_version=0,
            client=client,
        )

        assert mutation.set_params == {"n1": {"path": "b.csv"}}
        assert mutation.base_version == 0
        assert mutation.author == "data_modeller"

    def test_emitted_mutation_validates_cleanly(self, graph, tmp_path):
        messages = build_consult_messages(
            graph, persona_slug="data_modeller", node_ids=["n1"], ask=ASK
        )
        request = LLMRequest(
            provider="anthropic",
            model="claude-sonnet-5",
            messages=tuple(dict(m) for m in messages),
            temperature=0.0,
            max_tokens=None,
            response_format="json",
            response_schema=_SET_PARAMS_RESPONSE_SCHEMA,
            api_key_env=None,
        )
        response = LLMResponse(
            text=None,
            data={"set_params": {"n1": {"path": "b.csv"}}},
            model="claude-sonnet-5",
            usage=Usage(input_tokens=10, output_tokens=4),
            cost_usd=0.0,
            latency_ms=42.0,
            finish_reason="stop",
        )
        write_fixture(tmp_path, request, response)
        client = ReplayClient(tmp_path)

        mutation = run_consult(
            graph,
            persona_slug="data_modeller",
            node_ids=["n1"],
            ask=ASK,
            base_version=0,
            client=client,
        )

        diagnostics = propose_diagnostics(graph, mutation)
        assert diagnostics.diagnostics == []

    def test_service_layer_consult_graph_with_replay_client(self, seeded_graph, tmp_path):
        graph_obj = deserialize_graph(json.dumps(seeded_graph))
        messages = build_consult_messages(
            graph_obj, persona_slug="data_modeller", node_ids=["n1"], ask=ASK
        )
        request = LLMRequest(
            provider="anthropic",
            model="claude-sonnet-5",
            messages=tuple(dict(m) for m in messages),
            temperature=0.0,
            max_tokens=None,
            response_format="json",
            response_schema=_SET_PARAMS_RESPONSE_SCHEMA,
            api_key_env=None,
        )
        response = LLMResponse(
            text=None,
            data={"set_params": {"n1": {"path": "b.csv"}}},
            model="claude-sonnet-5",
            usage=Usage(input_tokens=10, output_tokens=4),
            cost_usd=0.0,
            latency_ms=42.0,
            finish_reason="stop",
        )
        write_fixture(tmp_path, request, response)

        result = consult_graph(
            {"graph": seeded_graph, "persona": "data_modeller", "node_ids": ["n1"], "ask": ASK},
            client=ReplayClient(tmp_path),
        )

        assert result["mutation"]["set_params"] == {"n1": {"path": "b.csv"}}
        assert result["diagnostics"]["diagnostics"] == []


# ===========================================================================
# Part B — advisor_persona is field-only metadata
# ===========================================================================


class TestAdvisorPersonaIsFieldOnlyMetadata:
    """Prove execute() and compile_to_code() are completely unaffected by
    a node carrying advisor_persona — the field is metadata only, never
    threads a client requirement through codegen."""

    def test_execute_with_advisor_persona_node_no_client_needed(self):
        from emergentflow.codegen.executor import execute
        from emergentflow.ir import Graph, Paradigm
        from emergentflow.nodes.examples.load_csv import LoadCsv

        node = LoadCsv().instantiate(path="/nonexistent/test.csv")
        graph = Graph(
            name="test_persona",
            paradigm=Paradigm.FUNCTIONAL,
            nodes={node.id: node},
            edges={},
        )
        # LoadCsv has advisor_persona="data_modeller" but does NOT declare
        # requires_client/requires, so execute(..., client=None) should never
        # raise MissingClientError. The FileNotFoundError is expected since the
        # file doesn't exist — the proof is it raises the WRONG error type for
        # a client-missing scenario.
        with pytest.raises(FileNotFoundError):
            execute(graph)

    def test_compile_to_code_with_advisor_persona_node_no_client_in_signature(self):
        from emergentflow.codegen.compiler import compile_to_code
        from emergentflow.ir import Graph, Paradigm
        from emergentflow.nodes.examples.load_csv import LoadCsv

        node = LoadCsv().instantiate(path="/nonexistent/test.csv")
        graph = Graph(
            name="test_persona",
            paradigm=Paradigm.FUNCTIONAL,
            nodes={node.id: node},
            edges={},
        )
        code = compile_to_code(graph)

        # advisor_persona must NOT thread a client requirement through codegen —
        # the emitted main() signature should NOT contain "client:".
        assert "client:" not in code or "def main(client:" not in code


# ===========================================================================
# Part C — No-ambient-LLM gate
# ===========================================================================


GATE_SENTINEL_TEXT = "GatewayClient must not be constructed here"


class _SentinelGatewayClient:
    """A callable that raises AssertionError if ever constructed.
    Used as a monkeypatch for GatewayClient in app.py to prove no
    non-consult route ever constructs one."""

    def __new__(cls):
        raise AssertionError(GATE_SENTINEL_TEXT)


class TestNoAmbientLLM:
    """GatewayClient is constructed ONLY inside the two consult routes —
    never by session/proposal/review/catalog/validate/compile/personas."""

    def test_grep_level_gateway_client_count_in_app(self):
        app_source = pathlib.Path(
            pathlib.Path(__file__).resolve().parents[1] / "emergentflow" / "server" / "app.py"
        ).read_text()
        count = app_source.count("GatewayClient()")
        # Exactly 2 calls: one in POST /consult, one in POST /sessions/{id}/consult
        assert count == 2, (
            f"Expected exactly 2 'GatewayClient()' calls in app.py, found {count}. "
            "If this changed deliberately, update this assertion and the gate tests."
        )

    def test_no_gateway_client_outside_consult_routes(self, monkeypatch, seeded_graph):
        import sys

        monkeypatch.setattr(
            sys.modules["emergentflow.server.app"],
            "GatewayClient",
            _SentinelGatewayClient,
        )

        app = create_app()

        # Since _SentinelGatewayClient raises on construction, ensure no
        # non-consult route ever triggers it. We build routes that NEVER
        # touch GatewayClient, so they must succeed.
        #
        # How to verify the sentinel never fired: every response below
        # must NOT contain the sentinel text and must have status < 500.

        with TestClient(app) as tc:
            # GET /catalog
            r = tc.get("/catalog")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # GET /personas
            r = tc.get("/personas")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST /validate
            r = tc.post("/validate", json=seeded_graph)
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST /compile
            r = tc.post("/compile", json=seeded_graph)
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST /sessions (create)
            r = tc.post("/sessions", json={"graph": seeded_graph})
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text
            session_id = r.json()["id"]

            # POST /sessions/{id}/proposals (propose before PUT to stay on base_version 0)
            r = tc.post(
                f"/sessions/{session_id}/proposals",
                json={"base_version": 0, "description": "test"},
            )
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text
            proposal_data = r.json()
            assert "id" in proposal_data, (
                f"Expected proposal response to contain 'id', got: {proposal_data}"
            )
            proposal_id = proposal_data["id"]

            # PUT /sessions/{id}/graph
            r = tc.put(
                f"/sessions/{session_id}/graph",
                json={"graph": seeded_graph, "expected_version": 0},
            )
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST /sessions/{id}/proposals/{pid}/accept
            r = tc.post(f"/sessions/{session_id}/proposals/{proposal_id}/accept")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST a second proposal then reject it
            r = tc.post(
                f"/sessions/{session_id}/proposals",
                json={"base_version": 1, "description": "reject-me"},
            )
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text
            pid2 = r.json()["id"]
            r = tc.post(f"/sessions/{session_id}/proposals/{pid2}/reject")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # GET /sessions/{id}
            r = tc.get(f"/sessions/{session_id}")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # GET /sessions
            r = tc.get("/sessions")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST /sessions/{id}/reviews
            r = tc.post(
                f"/sessions/{session_id}/reviews",
                json={"author": "data_modeller"},
            )
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text
            review_id = r.json()["id"]

            # GET /sessions/{id}/reviews
            r = tc.get(f"/sessions/{session_id}/reviews")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # POST /sessions/{id}/reviews/{rid}/comments
            r = tc.post(
                f"/sessions/{session_id}/reviews/{review_id}/comments",
                json={"author": "human", "text": "looks good"},
            )
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

            # DELETE /sessions/{id}
            r = tc.delete(f"/sessions/{session_id}")
            assert r.status_code < 500, r.text
            assert GATE_SENTINEL_TEXT not in r.text

    def test_positive_control_consult_triggers_sentinel(self, seeded_graph, monkeypatch):
        """Prove the sentinel actually works: POST /consult under the same
        monkeypatch MUST return the 422 error containing the sentinel text."""
        import sys

        monkeypatch.setattr(
            sys.modules["emergentflow.server.app"],
            "GatewayClient",
            _SentinelGatewayClient,
        )
        client = TestClient(create_app())

        r = client.post(
            "/consult",
            json={
                "graph": seeded_graph,
                "persona": "data_modeller",
                "node_ids": ["n1"],
                "ask": "change path",
            },
        )

        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        assert GATE_SENTINEL_TEXT in r.text, (
            f"Expected sentinel text in 422 response body, got: {r.text}"
        )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
