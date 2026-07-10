"""
tests/test_collab_knowledge.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 10 — knowledge base: store round-trips, signature computation
for graph fragments, apply_mutation + validation of retrieved fragments,
route-level smoke tests, and the works-without-agents import gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emergentflow import validate
from emergentflow.collab import knowledge as knowledge_mod
from emergentflow.collab.knowledge import (
    DuplicateSlugError,
    KnowledgeEntry,
    KnowledgeStore,
    UnknownKnowledgeEntryError,
    compute_signature,
)
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ir.mutation import GraphMutation, apply_mutation
from emergentflow.ir.node import Node
from emergentflow.ir.port import Port
from emergentflow.server.app import create_app

# ---------------------------------------------------------------------------
# Fixture: isolate the process-wide KnowledgeStore per test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_knowledge_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate the process-wide default KnowledgeStore per test, backed by a
    pytest tmp_path -- never the real repo's .emergentflow/ directory (the
    store is file-backed, unlike SessionStore, so resetting to None alone
    would still resolve to the real workspace path).
    """
    monkeypatch.setattr(
        knowledge_mod, "_default_store", KnowledgeStore(path=tmp_path / "knowledge.json")
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_csv_graph() -> Graph:
    """A single data.load_csv node with an OUT DataFrame port and no IN ports."""
    node = Node(
        id="n1",
        type="data.load_csv",
        ports=[Port(id="out", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    return Graph(nodes={"n1": node}, edges={})


def _describe_graph() -> Graph:
    """A lone stats.describe node: IN DataFrame + OUT DataFrame (unbound)."""
    node = Node(
        id="n1",
        type="stats.describe",
        ports=[
            Port(id="in", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="out", name="summary", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    return Graph(nodes={"n1": node}, edges={})


def _wired_load_csv_to_describe() -> Graph:
    """A fully wired load_csv -> describe fragment."""
    src = Node(
        id="src",
        type="data.load_csv",
        ports=[Port(id="result", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    dst = Node(
        id="dst",
        type="stats.describe",
        ports=[
            Port(id="input", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="result", name="summary", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    edge = Edge(
        id="e1",
        source=PortRef(node_id="src", port_id="result"),
        target=PortRef(node_id="dst", port_id="input"),
    )
    return Graph(nodes={"src": src, "dst": dst}, edges={"e1": edge})


# ---------------------------------------------------------------------------
# 1. Store round-trip
# ---------------------------------------------------------------------------


class TestStoreRoundTrip:
    """KnowledgeStore.save() then .get() and .list() round-trips."""

    def test_save_and_get_returns_same_entry(self, tmp_path: Path) -> None:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        entry = KnowledgeEntry(
            slug="test",
            description="A test entry",
            subgraph=_load_csv_graph(),
            created_by="human",
        )

        store.save(entry)
        retrieved = store.get("test")

        assert retrieved.slug == "test"
        assert retrieved.description == "A test entry"
        assert retrieved.created_by == "human"

    def test_list_returns_saved_entry(self, tmp_path: Path) -> None:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        entry = KnowledgeEntry(
            slug="list-me",
            description="Listing test",
            subgraph=_load_csv_graph(),
            created_by="human",
        )
        store.save(entry)

        entries = store.list()
        assert len(entries) == 1
        assert entries[0].slug == "list-me"

    def test_duplicate_slug_raises(self, tmp_path: Path) -> None:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        entry = KnowledgeEntry(
            slug="dup", description="First", subgraph=_load_csv_graph(), created_by="human"
        )
        store.save(entry)

        with pytest.raises(DuplicateSlugError):
            store.save(
                KnowledgeEntry(
                    slug="dup", description="Second", subgraph=_load_csv_graph(), created_by="human"
                )
            )

    def test_missing_slug_raises(self, tmp_path: Path) -> None:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")

        with pytest.raises(UnknownKnowledgeEntryError):
            store.get("does-not-exist")


# ---------------------------------------------------------------------------
# 2. Discovery via .list() filters
# ---------------------------------------------------------------------------


class TestListFilters:
    """KnowledgeStore.list() with in_type, out_type, and tag filters."""

    @pytest.fixture
    def populated_store(self, tmp_path: Path) -> KnowledgeStore:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        store.save(
            KnowledgeEntry(
                slug="stats-df",
                description="Describe on DataFrame",
                subgraph=_describe_graph(),
                tags=["stats"],
                created_by="human",
            )
        )
        store.save(
            KnowledgeEntry(
                slug="csv-loader",
                description="Load a CSV",
                subgraph=_load_csv_graph(),
                tags=["data"],
                created_by="human",
            )
        )
        return store

    def test_in_type_filter(self, populated_store: KnowledgeStore) -> None:
        entries = populated_store.list(in_type="DataFrame")
        assert [e.slug for e in entries] == ["stats-df"]

    def test_out_type_filter(self, populated_store: KnowledgeStore) -> None:
        entries = populated_store.list(out_type="DataFrame")
        assert sorted(e.slug for e in entries) == ["csv-loader", "stats-df"]

    def test_tag_filter(self, populated_store: KnowledgeStore) -> None:
        entries = populated_store.list(tag="data")
        assert [e.slug for e in entries] == ["csv-loader"]

    def test_combined_filters_and(self, populated_store: KnowledgeStore) -> None:
        entries = populated_store.list(in_type="DataFrame", tag="stats")
        assert [e.slug for e in entries] == ["stats-df"]

    def test_combined_filter_no_match_returns_empty(self, populated_store: KnowledgeStore) -> None:
        entries = populated_store.list(in_type="DataFrame", tag="data")
        assert entries == []


# ---------------------------------------------------------------------------
# 3. Signature computation
# ---------------------------------------------------------------------------


class TestSignatureComputation:
    """compute_signature for fragments with unbound inputs, fully wired
    fragments, and save()-time recomputation."""

    def test_unbound_input_fragment(self) -> None:
        fragment = _describe_graph()
        unbound, produced = compute_signature(fragment)
        assert unbound == ["DataFrame"]
        assert produced == ["DataFrame"]

    def test_fully_wired_fragment(self) -> None:
        fragment = _wired_load_csv_to_describe()
        unbound, produced = compute_signature(fragment)
        assert unbound == []
        assert produced == ["DataFrame"]

    def test_save_recomputes_signature(self, tmp_path: Path) -> None:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        entry = KnowledgeEntry(
            slug="recompute",
            description="Signature must be recomputed on save",
            subgraph=_describe_graph(),
            created_by="human",
            unbound_in_types=[],
            produced_out_types=[],
        )

        saved = store.save(entry)

        assert saved.unbound_in_types == ["DataFrame"]
        assert saved.produced_out_types == ["DataFrame"]


# ---------------------------------------------------------------------------
# 4. Retrieved fragment applies through apply_mutation and validates
# ---------------------------------------------------------------------------


class TestApplyMutationAndValidate:
    """A KnowledgeEntry fragment retrieved from the store applies as a
    GraphMutation and the result validates cleanly."""

    def test_retrieved_fragment_applies_and_validates(self, tmp_path: Path) -> None:
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        store.save(
            KnowledgeEntry(
                slug="valid-fragment",
                description="A valid subgraph fragment",
                subgraph=_load_csv_graph(),
                created_by="human",
            )
        )

        entry = store.get("valid-fragment")
        mutation = GraphMutation(
            base_version=0,
            add_nodes=list(entry.subgraph.nodes.values()),
            add_edges=list(entry.subgraph.edges.values()),
            author="human",
        )
        result = apply_mutation(Graph(), mutation)
        diagnostics = validate(result)

        assert diagnostics.diagnostics == []


# ---------------------------------------------------------------------------
# 5. Route-level smoke test
# ---------------------------------------------------------------------------


class TestKnowledgeRoutes:
    """HTTP route coverage for POST/GET /knowledge."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(create_app())

    def test_post_knowledge_returns_200_and_signature(self, client: TestClient) -> None:
        entry = KnowledgeEntry(
            slug="route-test",
            description="Created via HTTP",
            subgraph=_describe_graph(),
            created_by="human",
        )
        r = client.post("/knowledge", json=entry.model_dump(mode="json"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["slug"] == "route-test"
        assert body["unbound_in_types"] == ["DataFrame"]
        assert body["produced_out_types"] == ["DataFrame"]

    def test_get_knowledge_by_slug_returns_200(self, client: TestClient) -> None:
        entry = KnowledgeEntry(
            slug="get-me",
            description="Retrievable",
            subgraph=_load_csv_graph(),
            created_by="human",
        )
        client.post("/knowledge", json=entry.model_dump(mode="json"))

        r = client.get("/knowledge/get-me")
        assert r.status_code == 200, r.text
        assert r.json()["slug"] == "get-me"

    def test_get_knowledge_unknown_slug_returns_404(self, client: TestClient) -> None:
        r = client.get("/knowledge/does-not-exist")
        assert r.status_code == 404, r.text

    def test_get_knowledge_with_filters(self, client: TestClient) -> None:
        client.post(
            "/knowledge",
            json=KnowledgeEntry(
                slug="a",
                description="a",
                subgraph=_describe_graph(),
                tags=["stats"],
                created_by="human",
            ).model_dump(mode="json"),
        )
        client.post(
            "/knowledge",
            json=KnowledgeEntry(
                slug="b",
                description="b",
                subgraph=_load_csv_graph(),
                tags=["data"],
                created_by="human",
            ).model_dump(mode="json"),
        )

        r = client.get("/knowledge?in=DataFrame")
        assert r.status_code == 200, r.text
        slugs = [e["slug"] for e in r.json()["entries"]]
        assert slugs == ["a"]

        r = client.get("/knowledge?out=DataFrame")
        assert r.status_code == 200, r.text
        slugs = [e["slug"] for e in r.json()["entries"]]
        assert sorted(slugs) == ["a", "b"]

        r = client.get("/knowledge?tag=data")
        assert r.status_code == 200, r.text
        slugs = [e["slug"] for e in r.json()["entries"]]
        assert slugs == ["b"]

    def test_duplicate_slug_post_returns_422(self, client: TestClient) -> None:
        payload = KnowledgeEntry(
            slug="dup", description="First", subgraph=_load_csv_graph(), created_by="human"
        ).model_dump(mode="json")
        client.post("/knowledge", json=payload)

        r = client.post("/knowledge", json=payload)
        assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 6. Works-without-agents check
# ---------------------------------------------------------------------------


def test_knowledge_module_never_eagerly_imported() -> None:
    """A fresh ``import emergentflow`` must never pull in
    emergentflow.collab.knowledge -- it is only reachable by an explicit,
    opt-in ``import emergentflow.collab.knowledge`` (the works-without-agents
    invariant: no agent code path is on the base import graph).
    """
    script = (
        "import sys; import emergentflow;"
        "assert 'emergentflow.collab.knowledge' not in sys.modules, "
        "'emergentflow.collab.knowledge imported eagerly';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
