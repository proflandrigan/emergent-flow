"""ArtifactStore revision tracking (issue #178) and its exposure on /execute."""

from __future__ import annotations

from emergentflow.server import artifacts as artifacts_mod
from emergentflow.server import service as service_mod
from emergentflow.server.artifacts import ArtifactStore
from emergentflow.server.service import execute_graph, execute_graph_stream
from tests.test_server_cache import _load_graph


def test_put_returns_revision_written_to_meta(tmp_path) -> None:
    store = ArtifactStore(root=tmp_path)
    revision = store.put("n1", {"out": 1}, label="L")
    meta = store.get_meta("n1")
    assert meta is not None
    assert meta["revision"] == revision
    assert meta["label"] == "L"


def test_revision_changes_on_every_put(tmp_path) -> None:
    store = ArtifactStore(root=tmp_path)
    revisions = [store.put("n1", {"out": 1}) for _ in range(50)]
    assert len(set(revisions)) == 50


def test_get_meta_miss_returns_none(tmp_path) -> None:
    assert ArtifactStore(root=tmp_path).get_meta("nope") is None


def test_get_with_revision_is_consistent_and_get_unchanged(tmp_path) -> None:
    store = ArtifactStore(root=tmp_path)
    store.put("n1", {"out": 1})
    second = store.put("n1", {"out": 2})
    assert store.get_with_revision("n1") == ({"out": 2}, second)
    assert store.get("n1") == {"out": 2}
    assert store.get_with_revision("missing") is None


def test_eviction_returns_none(tmp_path) -> None:
    store = ArtifactStore(root=tmp_path, max_mb=0.0001)
    store.put("old", {"blob": "x" * 5000})
    store.put("new", {"blob": "y" * 5000})
    assert store.get_with_revision("old") is None
    assert store.get_meta("old") is None
    assert store.get_with_revision("new") is not None


def test_put_leaves_no_tmp_files(tmp_path) -> None:
    store = ArtifactStore(root=tmp_path)
    store.put("n1", {"out": 1})
    assert sorted(p.suffix for p in tmp_path.iterdir()) == [".json", ".pkl"]


def test_execute_graph_reports_artifact_revisions(monkeypatch, tmp_path) -> None:
    store = ArtifactStore(root=tmp_path)
    monkeypatch.setattr(artifacts_mod, "_default_artifacts", store)
    monkeypatch.setattr(service_mod, "get_default_artifacts", lambda: store)
    first = execute_graph(_load_graph())
    revision = first["artifact_revisions"]["n-load"]
    assert store.get_meta("n-load")["revision"] == revision
    second = execute_graph(_load_graph())
    assert second["artifact_revisions"]["n-load"] != revision


def test_execute_stream_reports_revisions(monkeypatch, tmp_path) -> None:
    store = ArtifactStore(root=tmp_path)
    monkeypatch.setattr(service_mod, "get_default_artifacts", lambda: store)
    events = list(execute_graph_stream(_load_graph()))
    ok = next(e for e in events if e["type"] == "node_ok")
    assert ok["revision"] == store.get_meta("n-load")["revision"]
    assert events[-1]["artifact_revisions"] == {"n-load": ok["revision"]}
