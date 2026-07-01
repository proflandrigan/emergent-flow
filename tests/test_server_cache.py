"""Tests for the on-disk DAG execution cache (Epic 7 Story 6).

Includes both unit tests for the ExecutionCache class itself and integration
tests that wire caching into the FUNCTIONAL execute path (service.py).
"""

from __future__ import annotations

import json
import threading

import pytest

from emergentflow import __version__
from emergentflow.ir import (
    Direction,
    Graph,
    Node,
    Paradigm,
    Param,
    Port,
    Position,
)
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.serialize import serialize_graph
from emergentflow.nodes import register as register_node
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.spec import ParamSpec, PortSpec
from emergentflow.server import cache as cache_mod
from emergentflow.server.cache import ExecutionCache
from emergentflow.server.service import (
    clear_cache,
    execute_graph,
    execute_graph_stream,
)

# Self-contained node definitions for testing cache-propagation.
# Registered with the default registry so get_node_definition can find them.


class _NonCacheableSource(NodeDefinition):
    type = "test.noncacheable_source"
    version = 1
    family = "test"
    label = "Non-cacheable Source"
    cacheable = False
    ports = [
        PortSpec(name="out", direction=Direction.OUT, data_type="Any"),
    ]
    params = []

    def codegen(self, node, ctx):
        return CodeFragment(body=f"{ctx.out_var('out')} = None")

    def execute(self, node, inputs):
        return {"out": None}


class _CacheableSource(NodeDefinition):
    """A deterministic, cacheable source node standing in for ``data.load_csv``.

    ``data.load_csv`` (and the other file-reading source nodes) are
    intentionally ``cacheable = False`` -- their ``execute()`` reads external
    file content the cache key can't see, so a cache hit would silently
    return stale data (Epic 7 Story 6 review). These cache-behavior tests
    need an actually-cacheable source node instead, so they exercise the
    caching contract itself rather than that unrelated staleness gap.
    """

    type = "test.cacheable_source"
    version = 1
    family = "test"
    label = "Cacheable Source"
    ports = [
        PortSpec(name="out", direction=Direction.OUT, data_type="Any"),
    ]
    params = [
        ParamSpec(name="value", type_token="str", default="x"),
    ]

    def codegen(self, node, ctx):
        return CodeFragment(body=f"{ctx.out_var('out')} = None")

    def execute(self, node, inputs):
        return {"out": None}


class _CacheablePassthrough(NodeDefinition):
    type = "test.cacheable_passthrough"
    version = 1
    family = "test"
    label = "Cacheable Pass-Through"
    ports = [
        PortSpec(name="in", direction=Direction.IN, data_type="Any"),
        PortSpec(name="out", direction=Direction.OUT, data_type="Any"),
    ]
    params = [
        ParamSpec(name="dummy", type_token="str", default="default"),
    ]

    def codegen(self, node, ctx):
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in')}")

    def execute(self, node, inputs):
        return {"out": inputs.get("in")}


register_node(_NonCacheableSource)
register_node(_CacheableSource)
register_node(_CacheablePassthrough)


def _load_graph(value: str | None = None) -> dict:
    """Minimal one-node cacheable-source graph -- shape mirrors a real source node."""
    node = Node(
        id="n-load",
        type="test.cacheable_source",
        label="Cacheable Source",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="value", type_token="str", value=value or "x")],
        ports=[
            Port(id="p-load-out", name="out", direction=Direction.OUT, data_type="Any"),
        ],
        position=Position(x=0.0, y=0.0),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="cache-test-load",
        nodes={node.id: node},
        edges={},
    )
    return json.loads(serialize_graph(graph))


def _chain_graph(value: str | None = None) -> dict:
    """Two-node cacheable-source -> passthrough chain -- same shape as test_server._chain_graph."""
    load = Node(
        id="n-load",
        type="test.cacheable_source",
        label="Cacheable Source",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="value", type_token="str", value=value or "x")],
        ports=[
            Port(id="p-load-out", name="out", direction=Direction.OUT, data_type="Any"),
        ],
        position=Position(x=0.0, y=0.0),
    )
    impute = Node(
        id="n-impute",
        type="test.cacheable_passthrough",
        label="Cacheable Pass-Through",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="dummy", type_token="str", value="mean")],
        ports=[
            Port(id="p-imp-in", name="in", direction=Direction.IN, data_type="Any"),
            Port(id="p-imp-out", name="out", direction=Direction.OUT, data_type="Any"),
        ],
        position=Position(x=1.0, y=0.0),
    )
    edge = Edge(
        id="e-load-impute",
        source=PortRef(node_id="n-load", port_id="p-load-out"),
        target=PortRef(node_id="n-impute", port_id="p-imp-in"),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="cache-test-chain",
        nodes={load.id: load, impute.id: impute},
        edges={edge.id: edge},
    )
    return json.loads(serialize_graph(graph))


def _noncacheable_chain_graph() -> dict:
    """Two-node chain: noncacheable (cacheable=False) -> cacheable passthrough.

    The upstream node is not cacheable, so its hash is always None, which
    propagates and prevents the downstream node from having a defined hash
    either -- both are never looked up in or written to the cache.
    """
    nc = Node(
        id="n-nc",
        type="test.noncacheable_source",
        label="Non-cacheable Source",
        paradigm=Paradigm.FUNCTIONAL,
        params=[],
        ports=[
            Port(id="p-nc-out", name="out", direction=Direction.OUT, data_type="Any"),
        ],
        position=Position(x=0.0, y=0.0),
    )
    pt = Node(
        id="n-pt",
        type="test.cacheable_passthrough",
        label="Cacheable Pass-Through",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="dummy", type_token="str", value="default")],
        ports=[
            Port(id="p-pt-in", name="in", direction=Direction.IN, data_type="Any"),
            Port(id="p-pt-out", name="out", direction=Direction.OUT, data_type="Any"),
        ],
        position=Position(x=1.0, y=0.0),
    )
    edge = Edge(
        id="e-nc-pt",
        source=PortRef(node_id="n-nc", port_id="p-nc-out"),
        target=PortRef(node_id="n-pt", port_id="p-pt-in"),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="cache-test-noncacheable",
        nodes={nc.id: nc, pt.id: pt},
        edges={edge.id: edge},
    )
    return json.loads(serialize_graph(graph))


def test_put_then_get_round_trips_outputs(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path)
    outputs = {"out1": 42, "out2": [1, 2, 3]}
    cache.put("deadbeef", outputs, node_id="n1", label="Node One")
    assert cache.get("deadbeef") == outputs


def test_get_unknown_hash_returns_none(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path)
    assert cache.get("nosuchhash") is None


def test_put_writes_meta_sidecar(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path)
    cache.put("h1", {"x": 1}, node_id="n1", label="Node One")
    meta = json.loads((tmp_path / "h1.meta.json").read_text())
    assert meta["node_id"] == "n1"
    assert meta["label"] == "Node One"
    assert meta["sdk_version"] == __version__
    assert isinstance(meta["timestamp"], float)


def test_put_is_idempotent_by_hash(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path)
    cache.put("h1", {"x": 1}, node_id="n1", label="A")
    cache.put("h1", {"x": 2}, node_id="n1", label="A")
    assert cache.get("h1") == {"x": 2}


def test_explicit_root_is_used(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path / "cache")
    cache.put("h1", {"x": 1}, node_id="n1", label="A")
    assert (tmp_path / "cache" / "h1.pkl").is_file()


def test_clear_removes_all_entries(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path)
    cache.put("h1", {"x": 1}, node_id="n1", label="A")
    cache.put("h2", {"x": 2}, node_id="n2", label="B")
    cache.clear()
    assert cache.get("h1") is None
    assert cache.get("h2") is None
    assert list(tmp_path.iterdir()) == []


def test_eviction_removes_oldest_entry_first(tmp_path) -> None:
    # Cap sized to hold roughly one entry: put one entry, measure its total
    # on-disk size (pkl + meta), then set max_mb just above that -- so a
    # second, same-sized entry pushes the total over the cap and the first
    # (oldest) one gets evicted.
    probe = ExecutionCache(root=tmp_path / "probe")
    probe.put("p", {"x": 1}, node_id="n", label="A")
    entry_bytes = sum(f.stat().st_size for f in (tmp_path / "probe").iterdir())
    max_mb = (entry_bytes * 1.5) / (1024 * 1024)

    cache = ExecutionCache(root=tmp_path / "cache", max_mb=max_mb)
    cache.put("h1", {"x": 1}, node_id="n1", label="A")
    cache.put("h2", {"x": 1}, node_id="n2", label="B")

    assert cache.get("h1") is None
    assert cache.get("h2") == {"x": 1}


def test_get_refreshes_recency_so_it_survives_eviction(tmp_path) -> None:
    probe = ExecutionCache(root=tmp_path / "probe")
    probe.put("p", {"x": 1}, node_id="n", label="A")
    entry_bytes = sum(f.stat().st_size for f in (tmp_path / "probe").iterdir())
    # Cap holds two entries but not three.
    max_mb = (entry_bytes * 2.5) / (1024 * 1024)

    cache = ExecutionCache(root=tmp_path / "cache", max_mb=max_mb)
    cache.put("h1", {"x": 1}, node_id="n1", label="A")
    cache.put("h2", {"x": 1}, node_id="n2", label="B")
    assert cache.get("h1") == {"x": 1}  # touch h1 -- now more recent than h2
    cache.put("h3", {"x": 1}, node_id="n3", label="C")  # pushes total over cap

    # h2 was the least-recently-used (never re-touched after its own put), so
    # it is evicted; h1 (touched) and h3 (just written) both survive.
    assert cache.get("h1") == {"x": 1}
    assert cache.get("h2") is None
    assert cache.get("h3") == {"x": 1}


def test_eviction_leaves_a_single_oversized_entry_in_place(tmp_path) -> None:
    cache = ExecutionCache(root=tmp_path, max_mb=0.0000001)
    cache.put("h1", {"x": "y" * 1000}, node_id="n1", label="A")
    # Cap is far smaller than one entry, but eviction never deletes the last one.
    assert cache.get("h1") == {"x": "y" * 1000}


def test_configure_cache_then_get_default_cache_uses_configured_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache_mod, "_default_cache", None)
    monkeypatch.setattr(cache_mod, "_configured_root", None)
    monkeypatch.setattr(cache_mod, "_configured_max_mb", cache_mod.DEFAULT_CACHE_MAX_MB)
    cache_mod.configure_cache(tmp_path / "configured", max_mb=10)
    cache = cache_mod.get_default_cache()
    assert cache.root == tmp_path / "configured"
    assert cache.root.is_dir()


def test_configure_cache_after_singleton_created_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache_mod, "_default_cache", None)
    monkeypatch.setattr(cache_mod, "_configured_root", None)
    cache_mod.get_default_cache()  # creates the singleton with defaults
    with pytest.raises(RuntimeError):
        cache_mod.configure_cache(tmp_path, max_mb=10)


def test_get_default_cache_is_thread_safe(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cache_mod, "_default_cache", None)
    monkeypatch.setattr(cache_mod, "_configured_root", None)
    thread_count = 16
    barrier = threading.Barrier(thread_count)
    caches: list[ExecutionCache] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        cache = cache_mod.get_default_cache()
        with lock:
            caches.append(cache)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(caches) == thread_count
    assert len({id(c) for c in caches}) == 1


# ---------------------------------------------------------------------------
# Integration: caching in the FUNCTIONAL execute path (service.py)
# ---------------------------------------------------------------------------


def test_cache_hit_on_identical_graph(monkeypatch, tmp_path) -> None:
    """Property 1: running the same graph twice yields 'cached' on the second run."""
    monkeypatch.setattr(cache_mod, "_default_cache", ExecutionCache(root=tmp_path / "cache"))
    graph = _load_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-load"]["status"] == "ok"
    second = execute_graph(graph)
    assert second["statuses"]["n-load"]["status"] == "cached"


def test_cache_miss_after_param_change(monkeypatch, tmp_path) -> None:
    """Property 2: changing a node's param invalidates its cache entry."""
    monkeypatch.setattr(cache_mod, "_default_cache", ExecutionCache(root=tmp_path / "cache"))
    graph = _chain_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-impute"]["status"] == "ok"
    # Change impute's strategy param.
    graph["nodes"]["n-impute"]["params"][0]["value"] = "median"
    second = execute_graph(graph)
    assert second["statuses"]["n-impute"]["status"] == "ok"
    assert second["statuses"]["n-load"]["status"] == "cached"


def test_cache_miss_after_version_change(monkeypatch, tmp_path) -> None:
    """Property 3: changing the SDK version invalidates every cache entry."""
    monkeypatch.setattr(cache_mod, "_default_cache", ExecutionCache(root=tmp_path / "cache"))
    graph = _load_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-load"]["status"] == "ok"
    # Monkeypatch the version that _node_hash reads (the name imported into service.py).
    import emergentflow.server.service as svc_mod

    monkeypatch.setattr(svc_mod, "__version__", "9.9.9-test")
    second = execute_graph(graph)
    assert second["statuses"]["n-load"]["status"] == "ok"


def test_unchanged_upstream_cached_after_downstream_param_change(monkeypatch, tmp_path) -> None:
    """Property 4: in a chain, an unchanged upstream node is cached when only the
    downstream node's param changes."""
    monkeypatch.setattr(cache_mod, "_default_cache", ExecutionCache(root=tmp_path / "cache"))
    graph = _chain_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-load"]["status"] == "ok"
    assert first["statuses"]["n-impute"]["status"] == "ok"
    # Change only the downstream (impute) strategy.
    graph["nodes"]["n-impute"]["params"][0]["value"] = "median"
    second = execute_graph(graph)
    # Upstream unchanged -> cached; downstream changed -> fresh.
    assert second["statuses"]["n-load"]["status"] == "cached"
    assert second["statuses"]["n-impute"]["status"] == "ok"


def test_noncacheable_ancestor_prevents_caching(monkeypatch, tmp_path) -> None:
    """Property 5: a non-cacheable upstream node prevents any downstream node
    from caching -- both nodes report "ok" on every run, never "cached"."""
    monkeypatch.setattr(cache_mod, "_default_cache", ExecutionCache(root=tmp_path / "cache"))
    graph = _noncacheable_chain_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-nc"]["status"] == "ok"
    assert first["statuses"]["n-pt"]["status"] == "ok"
    # Second run with identical params: still "ok" (never cached).
    second = execute_graph(graph)
    assert second["statuses"]["n-nc"]["status"] == "ok"
    assert second["statuses"]["n-pt"]["status"] == "ok"


def test_clear_cache_service_function_empties_the_default_cache(monkeypatch, tmp_path) -> None:
    """clear_cache({}) empties the default cache so the next execute is fresh."""
    cache = ExecutionCache(root=tmp_path / "cache")
    monkeypatch.setattr(cache_mod, "_default_cache", cache)
    graph = _load_graph()
    first = execute_graph(graph)
    assert first["statuses"]["n-load"]["status"] == "ok"
    second = execute_graph(graph)
    assert second["statuses"]["n-load"]["status"] == "cached"

    result = clear_cache({})
    assert result == {"status": "ok"}

    third = execute_graph(graph)
    assert third["statuses"]["n-load"]["status"] == "ok"


def test_execute_graph_stream_sse_includes_cached_flag(monkeypatch, tmp_path) -> None:
    """SSE stream: after the first run, the second run's node_ok events carry
    "cached": True for the unchanged upstream node, and every node_ok event
    has a "cached" key."""
    monkeypatch.setattr(cache_mod, "_default_cache", ExecutionCache(root=tmp_path / "cache"))
    graph = _chain_graph()
    # First run.
    first_events = list(execute_graph_stream(graph))
    first_ok = [e for e in first_events if e["type"] == "node_ok"]
    assert len(first_ok) == 2
    for ev in first_ok:
        assert "cached" in ev
        assert ev["cached"] is False
    # Second run.
    second_events = list(execute_graph_stream(graph))
    second_ok = [e for e in second_events if e["type"] == "node_ok"]
    assert len(second_ok) == 2
    for ev in second_ok:
        assert "cached" in ev
    # Upstream node (n-load) should be cached; downstream may or may not be.
    assert second_ok[0]["node_id"] == "n-load"
    assert second_ok[0]["cached"] is True
