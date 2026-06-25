"""
tests/test_serialize.py
~~~~~~~~~~~~~~~~~~~~~~~~
Story 5 — graph serialization & deserialization.

Covers the public API in ``emergentflow.ir.serialize``:
  - lossless, string-stable round-tripping across a corpus of sample graphs;
  - file I/O via save_graph / load_graph (.ef.json convention);
  - validate-on-load (malformed JSON and structurally invalid graphs);
  - schema-version policy (reject newer; migrate older up to current — Story 9).

The sample-graph corpus reuses the builders in tests/test_examples.py — the single
source of truth for example IR graphs. On-disk graphs saved at prior schema versions
live under tests/fixtures/ and back the migration tests (TestMigrationFixtures).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from emergentflow.ir import (
    CURRENT_SCHEMA_VERSION,
    ArtifactRef,
    Direction,
    Graph,
    GraphDeserializationError,
    Node,
    Paradigm,
    Param,
    Port,
    SchemaVersionError,
    deserialize_graph,
    load_graph,
    save_graph,
    serialize_graph,
)
from tests.test_examples import build_declarative_module, build_functional_pipeline

# On-disk corpus of graphs saved at PRIOR schema versions (Story 9 migration fixtures).
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


def build_artifact_param_graph() -> Graph:
    """A minimal graph whose node carries an ArtifactRef-valued Param.

    Locks the discriminated-union round-trip in params.py: a serialized ArtifactRef must
    not decay into a plain mapping (and vice-versa) across serialize → deserialize.
    """
    node = Node(
        id="n-load",
        type="data.load_parquet",
        label="Load Parquet",
        params=[
            Param(
                name="source",
                type_token="ArtifactRef",
                value=ArtifactRef(uri="s3://bucket/data.parquet", media_type="application/parquet"),
            ),
            # A plain mapping shaped a bit like an ArtifactRef, to prove it stays a mapping.
            Param(name="options", type_token="dict", value={"uri": "not-an-artifact", "n": 3}),
        ],
        ports=[Port(id="p-out", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    return Graph(name="ArtifactRef Param Example", nodes={node.id: node})


# Named corpus used to parametrize the round-trip property tests.
CORPUS = {
    "functional_pipeline": build_functional_pipeline,
    "declarative_module": build_declarative_module,
    "artifact_param": build_artifact_param_graph,
}


@pytest.fixture(params=sorted(CORPUS), ids=sorted(CORPUS))
def sample_graph(request) -> Graph:
    return CORPUS[request.param]()


# ---------------------------------------------------------------------------
# Round-trip / property tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_model_equality_round_trip(self, sample_graph: Graph):
        """deserialize(serialize(g)) == g."""
        restored = deserialize_graph(serialize_graph(sample_graph))
        assert restored == sample_graph

    def test_string_stable_round_trip(self, sample_graph: Graph):
        """serialize(deserialize(serialize(g))) is byte-for-byte identical (idempotent)."""
        once = serialize_graph(sample_graph)
        twice = serialize_graph(deserialize_graph(once))
        assert once == twice

    def test_serialized_output_is_valid_json_with_version(self, sample_graph: Graph):
        obj = json.loads(serialize_graph(sample_graph))
        assert isinstance(obj, dict)
        assert obj["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_compact_and_indented_are_equivalent(self, sample_graph: Graph):
        compact = deserialize_graph(serialize_graph(sample_graph, indent=None))
        indented = deserialize_graph(serialize_graph(sample_graph, indent=2))
        assert compact == indented == sample_graph

    def test_artifact_ref_survives_round_trip(self):
        g = build_artifact_param_graph()
        restored = deserialize_graph(serialize_graph(g))
        source = restored.nodes["n-load"].params[0].value
        options = restored.nodes["n-load"].params[1].value
        assert isinstance(source, ArtifactRef)
        assert source.uri == "s3://bucket/data.parquet"
        # The look-alike mapping must NOT become an ArtifactRef.
        assert isinstance(options, dict)
        assert options == {"uri": "not-an-artifact", "n": 3}


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


class TestFileIO:
    def test_save_then_load_is_equal(self, tmp_path, sample_graph: Graph):
        path = tmp_path / "pipeline.ef.json"
        returned = save_graph(sample_graph, path)
        assert returned == path
        assert load_graph(path) == sample_graph

    def test_saved_file_ends_with_newline(self, tmp_path):
        path = save_graph(build_functional_pipeline(), tmp_path / "g.ef.json")
        assert path.read_text(encoding="utf-8").endswith("}\n")

    def test_load_missing_file_raises_clean_error(self, tmp_path):
        with pytest.raises(GraphDeserializationError):
            load_graph(tmp_path / "does-not-exist.ef.json")


# ---------------------------------------------------------------------------
# Validate-on-load
# ---------------------------------------------------------------------------


class TestValidateOnLoad:
    def test_malformed_json_raises(self):
        with pytest.raises(GraphDeserializationError, match="not valid JSON"):
            deserialize_graph("{not json")

    def test_non_object_json_raises(self):
        with pytest.raises(GraphDeserializationError, match="must be a JSON object"):
            deserialize_graph("[1, 2, 3]")

    def test_edge_to_missing_node_raises_and_names_id(self):
        """A structurally invalid graph (edge target node missing) is rejected on load."""
        node = Node(
            id="n-a",
            type="data.load_csv",
            ports=[Port(id="p-out", name="o", direction=Direction.OUT, data_type="DataFrame")],
        )
        # Build raw JSON with a dangling edge (can't construct via Graph(...) — it'd reject).
        payload = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "paradigm": "functional",
            "name": None,
            "nodes": {"n-a": json.loads(node.model_dump_json())},
            "edges": {
                "e-bad": {
                    "id": "e-bad",
                    "source": {"node_id": "n-a", "port_id": "p-out"},
                    "target": {"node_id": "n-missing", "port_id": "p-in"},
                }
            },
        }
        with pytest.raises(GraphDeserializationError, match="n-missing"):
            deserialize_graph(json.dumps(payload))

    def test_unknown_field_rejected(self):
        """IRModel forbids extra fields; that surfaces as a clean deserialization error."""
        payload = {"schema_version": CURRENT_SCHEMA_VERSION, "surprise": True}
        with pytest.raises(GraphDeserializationError):
            deserialize_graph(json.dumps(payload))


# ---------------------------------------------------------------------------
# Schema-version policy
# ---------------------------------------------------------------------------


class TestSchemaVersionPolicy:
    def test_current_version_loads(self):
        g = build_functional_pipeline()
        assert deserialize_graph(serialize_graph(g)) == g

    def test_newer_version_rejected(self):
        raw = json.loads(serialize_graph(build_functional_pipeline()))
        raw["schema_version"] = CURRENT_SCHEMA_VERSION + 1
        with pytest.raises(SchemaVersionError, match="newer version") as exc:
            deserialize_graph(json.dumps(raw))
        assert exc.value.found == CURRENT_SCHEMA_VERSION + 1
        assert exc.value.expected == CURRENT_SCHEMA_VERSION

    def test_older_version_is_migrated_on_load(self):
        """An older graph with a registered migration path is migrated up on load, not rejected.

        Uses the synthetic v0 shape: schema_version 0 with the legacy top-level "mode" key,
        which the v0->v1 example migration renames to "paradigm".
        """
        raw = json.loads(serialize_graph(build_functional_pipeline()))
        raw["schema_version"] = 0
        raw["mode"] = raw.pop("paradigm")
        restored = deserialize_graph(json.dumps(raw))
        assert restored.schema_version == CURRENT_SCHEMA_VERSION
        assert restored.paradigm == build_functional_pipeline().paradigm

    def test_non_integer_version_rejected(self):
        raw = json.loads(serialize_graph(build_functional_pipeline()))
        raw["schema_version"] = "1"
        with pytest.raises(GraphDeserializationError, match="schema_version must be an integer"):
            deserialize_graph(json.dumps(raw))

    def test_nested_subgraph_version_is_enforced(self):
        """A nested subgraph is itself a serialized graph; its schema_version is policed too.

        Regression guard: the version check must reach into composite-node subgraphs, not
        only the top-level graph, or a subgraph written by a newer build would load silently.
        """
        raw = json.loads(serialize_graph(build_declarative_module()))
        module_node = raw["nodes"]["n-module"]
        assert module_node["subgraph"] is not None, "fixture must have a nested subgraph"
        # Top-level stays current; only the nested subgraph claims a newer version.
        module_node["subgraph"]["schema_version"] = CURRENT_SCHEMA_VERSION + 1
        with pytest.raises(SchemaVersionError, match="newer version") as exc:
            deserialize_graph(json.dumps(raw))
        assert exc.value.found == CURRENT_SCHEMA_VERSION + 1

    def test_unmigratable_older_version_raises_schema_version_error(self, monkeypatch):
        """An older graph with NO registered migration path surfaces as SchemaVersionError.

        Exercises the MigrationError -> SchemaVersionError translation in deserialize_graph.
        With CURRENT == 1 the only older version (0) is always migratable, so we remove the
        v0->v1 step to make a v0 graph unmigratable through the real load path.
        """
        from emergentflow.ir import migrate as migrate_mod

        monkeypatch.setattr(migrate_mod, "_MIGRATIONS", {}, raising=True)
        raw = json.loads(serialize_graph(build_functional_pipeline()))
        raw["schema_version"] = 0
        with pytest.raises(SchemaVersionError, match="could not be migrated") as exc:
            deserialize_graph(json.dumps(raw))
        assert exc.value.found == 0
        assert exc.value.expected == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# On-disk migration fixtures
# ---------------------------------------------------------------------------


class TestMigrationFixtures:
    """Load graphs saved at prior schema versions from disk and assert they migrate (Story 9)."""

    def test_load_flat_v0_fixture_migrates(self):
        g = load_graph(FIXTURES_DIR / "graph_v0.json")
        assert g.schema_version == CURRENT_SCHEMA_VERSION
        assert g.paradigm == Paradigm.FUNCTIONAL
        assert len(g.nodes) == 3

    def test_load_nested_v0_subgraph_fixture_migrates(self):
        g = load_graph(FIXTURES_DIR / "graph_nested_v0_subgraph.json")
        assert g.schema_version == CURRENT_SCHEMA_VERSION
        subs = [n.subgraph for n in g.nodes.values() if n.subgraph is not None]
        assert subs, "fixture must contain at least one nested subgraph"
        assert all(s.schema_version == CURRENT_SCHEMA_VERSION for s in subs)

    def test_migrated_fixture_round_trips_at_current_version(self):
        g = load_graph(FIXTURES_DIR / "graph_v0.json")
        once = serialize_graph(g)
        assert json.loads(once)["schema_version"] == CURRENT_SCHEMA_VERSION
        # Re-serializing the deserialized graph is byte-identical (stable post-migration).
        twice = serialize_graph(deserialize_graph(once))
        assert once == twice
