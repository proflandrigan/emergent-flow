"""Tests for emergentflow.research.reproducibility (Epic 16, Story 18)."""

from __future__ import annotations

from emergentflow.api import is_inspectable
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.ir.params import Param
from emergentflow.ir.port import Port
from emergentflow.research.reproducibility import (
    capture_run,
    resolve_dependency_versions,
)


def _sample_graph() -> Graph:
    loader = Node(
        id="load",
        type="data.load_csv",
        params=[Param(name="path", type_token="str", value="x.csv")],
        ports=[Port(id="p1", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    sampler = Node(
        id="sample",
        type="clean.sample_rows",
        params=[
            Param(name="seed", type_token="int", value=7),
            Param(name="n", type_token="int", value=5),
        ],
        ports=[
            Port(id="p2", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p3", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    non_stochastic = Node(
        id="dedup",
        type="clean.deduplicate",
        params=[],
        ports=[
            Port(id="p4", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p5", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    return Graph(nodes={"load": loader, "sample": sampler, "dedup": non_stochastic}, edges={})


def test_capture_run_collects_seeds():
    capture = capture_run(_sample_graph())
    assert capture.seeds == {"sample": 7}


def test_capture_run_collects_float_seeds():
    node = Node(
        id="n1",
        type="clean.sample_rows",
        params=[Param(name="random_state", type_token="float", value=42.0)],
        ports=[
            Port(id="p1", name="frame", direction=Direction.IN, data_type="DataFrame"),
            Port(id="p2", name="frame", direction=Direction.OUT, data_type="DataFrame"),
        ],
    )
    capture = capture_run(Graph(nodes={"n1": node}, edges={}))
    assert capture.seeds == {"n1": 42.0}


def test_capture_run_collects_content_hashes_for_data_nodes_only():
    capture = capture_run(_sample_graph())
    assert "load" in capture.content_hashes
    assert "sample" not in capture.content_hashes
    assert "dedup" not in capture.content_hashes


def test_capture_run_same_graph_same_seeds_yields_identical_capture():
    """The story's explicit requirement: same graph + same seeds => identical capture block."""
    graph = _sample_graph()
    capture1 = capture_run(graph)
    capture2 = capture_run(graph)
    assert capture1 == capture2

    # A structurally-identical but freshly-built graph (new Node/Port objects, same content)
    # must also produce an identical capture -- proves the hash is content-keyed, not
    # object-identity-keyed.
    capture3 = capture_run(_sample_graph())
    assert capture1 == capture3


def test_capture_run_different_param_value_changes_content_hash():
    graph = _sample_graph()
    graph.nodes["load"].params[0].value = "different.csv"
    changed = capture_run(graph)
    original = capture_run(_sample_graph())
    assert changed.content_hashes["load"] != original.content_hashes["load"]


def test_capture_run_result_is_inspectable():
    assert is_inspectable(capture_run(_sample_graph())) is True


def test_capture_run_dependency_versions_default_empty():
    assert capture_run(_sample_graph()).dependency_versions == {}


def test_capture_run_threads_dependency_versions_verbatim():
    versions = {"pandas": "2.0.0"}
    capture = capture_run(_sample_graph(), dependency_versions=versions)
    assert capture.dependency_versions == versions


def test_resolve_dependency_versions_skips_missing_packages():
    versions = resolve_dependency_versions(["pandas", "this-package-does-not-exist-xyz"])
    assert "pandas" in versions
    assert "this-package-does-not-exist-xyz" not in versions


def test_fingerprint_source_detects_changed_bytes_at_same_path(tmp_path) -> None:
    from emergentflow.research.reproducibility import fingerprint_source

    path = tmp_path / "terms.csv"
    path.write_text("term,n\na,1\n")
    first = fingerprint_source(str(path))
    path.write_text("term,n\na,2\n")
    second = fingerprint_source(str(path))

    assert first.kind == "file"
    assert first.sha256 != second.sha256
    assert first.size == len("term,n\na,1\n")
    assert first.fingerprinted_at.endswith("+00:00")
    assert is_inspectable(first)


def test_fingerprint_source_missing_file_is_unverifiable_not_an_error(tmp_path) -> None:
    from emergentflow.research.reproducibility import fingerprint_source

    result = fingerprint_source(str(tmp_path / "nope.csv"))

    assert result.kind == "unverifiable"
    assert result.sha256 is None
    assert result.reason
    assert "unverifiable" in result.describe()


def test_fingerprint_source_remote_uses_store_metadata(monkeypatch) -> None:
    import pytest

    fsspec = pytest.importorskip("fsspec")
    from emergentflow import data as ef_data
    from emergentflow.research.reproducibility import fingerprint_source

    monkeypatch.setattr(ef_data, "REMOTE_URI_SCHEMES", ("memory://",))
    fs = fsspec.filesystem("memory")
    fs.pipe("/bucket/terms.parquet", b"abc")

    result = fingerprint_source("memory://bucket/terms.parquet", hash_remote=True)

    assert result.kind == "object"
    assert result.size == 3
    assert result.sha256 is not None
    assert "memory://bucket/terms.parquet" in result.describe()


def _loader_graph(path: str, node_type: str = "data.load_csv") -> Graph:
    loader = Node(
        id="load",
        type=node_type,
        params=[Param(name="path", type_token="str", value=path)],
        ports=[Port(id="p1", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    return Graph(name="g", nodes={"load": loader})


def test_fingerprint_data_sources_changed_bytes_same_path_same_config_hash(tmp_path) -> None:
    from emergentflow.research.reproducibility import fingerprint_data_sources

    path = tmp_path / "t.csv"
    path.write_text("a\n1\n")
    graph = _loader_graph(str(path))
    first = capture_run(graph, data_fingerprints=fingerprint_data_sources(graph))
    path.write_text("a\n2\n")
    second = capture_run(graph, data_fingerprints=fingerprint_data_sources(graph))

    assert first.content_hashes == second.content_hashes  # config hash is blind to bytes
    assert first.data_fingerprints["load"]["kind"] == "file"
    assert first.data_fingerprints["load"]["sha256"] != second.data_fingerprints["load"]["sha256"]


def test_fingerprint_data_sources_unverifiable_cases(tmp_path) -> None:
    from emergentflow.research.reproducibility import fingerprint_data_sources

    glob = fingerprint_data_sources(_loader_graph(str(tmp_path / "*.csv")))["load"]
    assert glob.kind == "unverifiable" and "glob" in (glob.reason or "")
    directory = fingerprint_data_sources(_loader_graph(str(tmp_path)))["load"]
    assert directory.kind == "unverifiable"
    http = fingerprint_data_sources(_loader_graph("https://x.test/a.csv", "data.http_fetch"))
    assert http["load"].kind == "unverifiable" and "http" in (http["load"].reason or "")
    sink = fingerprint_data_sources(_loader_graph(str(tmp_path / "o.csv"), "data.save_frame"))
    assert sink == {}


def test_fingerprint_data_sources_remote_does_not_hash_bytes(monkeypatch) -> None:
    from emergentflow.research import reproducibility as repro

    seen: dict = {}

    def fake(uri, *, connection=None, hash_remote=False):
        seen.update(uri=uri, hash_remote=hash_remote)
        return repro.SourceFingerprint(uri=uri, kind="object", etag="e1")

    monkeypatch.setattr(repro, "fingerprint_source", fake)
    out = repro.fingerprint_data_sources(_loader_graph("s3://b/k.parquet", "data.load_parquet"))
    assert out["load"].etag == "e1"
    assert seen == {"uri": "s3://b/k.parquet", "hash_remote": False}


def test_fingerprint_data_sources_never_raises(monkeypatch) -> None:
    from emergentflow.research import reproducibility as repro

    def boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(repro, "fingerprint_source", boom)
    out = repro.fingerprint_data_sources(_loader_graph("x.csv"))
    assert out["load"].kind == "unverifiable" and "nope" in (out["load"].reason or "")


def test_default_dependency_packages_resolve_non_empty() -> None:
    from emergentflow.research.reproducibility import default_dependency_packages

    names = default_dependency_packages()
    assert names[0] == "emergentflow"
    versions = resolve_dependency_versions(names)
    assert versions.get("emergentflow")
    assert "pandas" in versions
