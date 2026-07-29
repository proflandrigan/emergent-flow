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
