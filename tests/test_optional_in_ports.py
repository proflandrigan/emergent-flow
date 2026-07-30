"""Optional IN ports must work end to end (issue #111).

A node type may declare an IN port ``required=False``. A node *instance* can then
be in one of two states, which are semantically identical:

* the port is **declared but unwired** (no edge into it), or
* the port is **omitted** from the instance entirely.

Both must be accepted by `/validate`, `compile_to_code`, `ef.execute` *and* the
server's own node-by-node walk (`_execute_functional_stream`, behind `/execute`,
`/execute/stream` and `/sessions/{id}/execute`). Before the fix the first state
was rejected by the server (its dangling-input guard was spec-blind) and the
second was rejected by codegen (`CodegenContext.in_var` KeyError'd on a port the
instance never declared), so no configuration both ran and downloaded.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.context import CodegenContext, build_codegen_context
from emergentflow.codegen.executor import execute
from emergentflow.codegen.naming import build_name_map
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir import Direction, Edge, Graph, Node, Port, PortRef
from emergentflow.ir.serialize import serialize_graph
from emergentflow.nodes import registry as default_node_registry
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.examples.llm_prompt import LlmPrompt
from emergentflow.nodes.examples.recommend_fit import RecommendFit
from emergentflow.nodes.examples.recommend_fit_two_tower import RecommendFitTwoTower
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import PortSpec
from emergentflow.server import cache as cache_mod
from emergentflow.server.service import compile_graph, execute_graph, validate_graph


@pytest.fixture(autouse=True)
def _fresh_default_cache(tmp_path: pathlib.Path) -> Iterator[None]:
    """Isolate the on-disk execution cache and artifact store per test, so the
    declared-unwired and omitted variants of the same graph can't serve each
    other cache hits (they hash identically -- deliberately, since they mean the
    same thing)."""
    from emergentflow.server import artifacts as artifacts_mod
    from emergentflow.server.cache import ExecutionCache

    old_cache = cache_mod._default_cache
    cache_mod._default_cache = ExecutionCache(root=tmp_path / ".ef-cache")
    old_artifacts = artifacts_mod._default_artifacts
    artifacts_mod._default_artifacts = artifacts_mod.ArtifactStore(root=tmp_path / ".ef-artifacts")
    yield
    cache_mod._default_cache = old_cache
    artifacts_mod._default_artifacts = old_artifacts


# ---------------------------------------------------------------------------
# Fixture node types
# ---------------------------------------------------------------------------


@register
class _OptSource(NodeDefinition):
    """Test fixture: 0 in, 1 out. Always emits the constant 1."""

    type = "test.opt_source"
    family = "test"
    label = "OptSrc"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="int")]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = 1")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": 1}


@register
class _OptAdd(NodeDefinition):
    """Test fixture: 1 required IN, 1 *optional* IN, 1 out.

    Its ``codegen`` reaches for the optional port through `in_var_or_none`, the
    accessor that mirrors ``execute``'s ``inputs.get(...)``, so both behaviors
    survive the port being absent from the node instance.
    """

    type = "test.opt_add"
    family = "test"
    label = "OptAdd"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="bonus", direction=Direction.IN, data_type="int", required=False),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        bonus = ctx.in_var_or_none("bonus")
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in_')} + ({bonus} or 0)")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"] + (inputs.get("bonus") or 0)}


@register
class _OptTwoSlots(NodeDefinition):
    """Test fixture: 1 required IN plus *two* optional INs, and a result that
    depends on WHICH optional port was fed.

    The shape that exposes cache-key collisions (`recommend.fit_two_tower`'s
    ``item_features``/``user_features`` in miniature): an unfed optional port
    contributes no upstream hash, so position alone cannot say which port a hash
    belongs to.
    """

    type = "test.opt_two_slots"
    family = "test"
    label = "OptTwoSlots"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="slot_a", direction=Direction.IN, data_type="int", required=False),
        PortSpec(name="slot_b", direction=Direction.IN, data_type="int", required=False),
        PortSpec(name="out", direction=Direction.OUT, data_type="str"),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        slot_a = ctx.in_var_or_none("slot_a")
        slot_b = ctx.in_var_or_none("slot_b")
        return CodeFragment(
            body=f"{ctx.out_var('out')} = f'a={{{slot_a}}},b={{{slot_b}}}'",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": f"a={inputs.get('slot_a')},b={inputs.get('slot_b')}"}


def _source_node() -> Node:
    return Node(
        id="src",
        type=_OptSource.type,
        label=_OptSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="int")],
    )


def _add_node(*, declare_optional_port: bool) -> Node:
    """The consumer node in one of its two equivalent states.

    *declare_optional_port* True -> the ``bonus`` port exists on the instance but
    has no edge into it; False -> the instance omits ``bonus`` altogether.
    """
    ports = [Port(id="add-in", name="in_", direction=Direction.IN, data_type="int")]
    if declare_optional_port:
        ports.append(Port(id="add-bonus", name="bonus", direction=Direction.IN, data_type="int"))
    ports.append(Port(id="add-out", name="out", direction=Direction.OUT, data_type="int"))
    return Node(id="add", type=_OptAdd.type, label=_OptAdd.label, ports=ports)


def _graph(*, declare_optional_port: bool) -> Graph:
    src = _source_node()
    add = _add_node(declare_optional_port=declare_optional_port)
    edge = Edge(
        id="e-src-add",
        source=PortRef(node_id="src", port_id="src-out"),
        target=PortRef(node_id="add", port_id="add-in"),
    )
    return Graph(nodes={src.id: src, add.id: add}, edges={edge.id: edge})


def _graph_payload(*, declare_optional_port: bool) -> dict[str, Any]:
    return json.loads(serialize_graph(_graph(declare_optional_port=declare_optional_port)))


_BOTH_STATES = pytest.mark.parametrize(
    "declare_optional_port",
    [True, False],
    ids=["declared-unwired", "omitted"],
)


# ---------------------------------------------------------------------------
# CodegenContext: the accessor and the registry backfill
# ---------------------------------------------------------------------------


def test_in_var_or_none_falls_back_to_the_none_literal() -> None:
    """`in_var_or_none` returns the bound variable when the port is present and
    the ``"None"`` literal when it is absent -- unlike `in_var`, which raises."""
    ctx = CodegenContext(in_vars={"wired": "some_var"}, out_vars={})

    assert ctx.in_var_or_none("wired") == "some_var"
    assert ctx.in_var_or_none("absent") == "None"
    with pytest.raises(KeyError):
        ctx.in_var("absent")


@_BOTH_STATES
def test_build_codegen_context_backfills_absent_optional_port(declare_optional_port: bool) -> None:
    """With a registry, an optional IN port binds to ``"None"`` in *both* states,
    so codegen can't tell them apart."""
    graph = _graph(declare_optional_port=declare_optional_port)
    ctx = build_codegen_context(
        graph.nodes["add"],
        build_name_map(graph),
        build_wiring_map(graph),
        default_node_registry,
    )

    assert ctx.in_var("bonus") == "None"


def test_build_codegen_context_without_registry_does_not_backfill() -> None:
    """The backfill is opt-in: passing no registry keeps the old instance-only
    behavior (this is what keeps `context.py` free of an import cycle)."""
    graph = _graph(declare_optional_port=False)
    ctx = build_codegen_context(graph.nodes["add"], build_name_map(graph), build_wiring_map(graph))

    assert "bonus" not in ctx.in_vars


def test_build_codegen_context_does_not_backfill_a_required_port() -> None:
    """Only *optional* ports are backfilled -- an absent required port stays a
    loud KeyError, matching ``execute``'s ``inputs[name]`` KeyError."""
    add = Node(
        id="add",
        type=_OptAdd.type,
        label=_OptAdd.label,
        ports=[Port(id="add-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    graph = Graph(nodes={add.id: add}, edges={})
    ctx = build_codegen_context(
        add, build_name_map(graph), build_wiring_map(graph), default_node_registry
    )

    assert "in_" not in ctx.in_vars


# ---------------------------------------------------------------------------
# The four consumers of the IR agree on both states
# ---------------------------------------------------------------------------


@_BOTH_STATES
def test_validate_reports_no_errors(declare_optional_port: bool) -> None:
    """An unfed optional IN port is not a diagnostic in either state. (The only
    diagnostic this fixture graph produces is a `type_unknown` *warning* for its
    unregistered ``int`` port type -- unrelated to optionality.)"""
    payload = validate_graph(_graph_payload(declare_optional_port=declare_optional_port))
    diagnostics = payload["diagnostics"]["diagnostics"]

    assert [d for d in diagnostics if d["severity"] == "error"] == []
    assert [d for d in diagnostics if d["code"] == "required_input_unconnected"] == []


@_BOTH_STATES
def test_compile_emits_the_none_literal_and_runs(declare_optional_port: bool) -> None:
    """`/compile` (and `compile_to_code` under it) must emit ``None`` for the
    unfed optional port rather than raising -- the "Download" path in the canvas."""
    graph = _graph(declare_optional_port=declare_optional_port)

    code = compile_to_code(graph)
    assert "None or 0" in code

    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    assert namespace["main"]()["optadd_out"] == 1

    served = compile_graph(_graph_payload(declare_optional_port=declare_optional_port))
    assert served["code"] == code


@_BOTH_STATES
def test_sdk_and_server_execute_agree(declare_optional_port: bool) -> None:
    """The regression assertion for root cause 1: `ef.execute` and the server's
    own walk (`/execute`, `/execute/stream`, `/sessions/{id}/execute`) must
    accept the same graph and produce the same value. They disagreed before --
    the server rejected every unwired IN port with `UnboundInputError`, and
    relaxing that guard alone would have hit `IndexError` on ``sources[0]``."""
    graph = _graph(declare_optional_port=declare_optional_port)

    sdk_results = execute(graph)
    assert sdk_results["add"] == {"out": 1}

    served = execute_graph(_graph_payload(declare_optional_port=declare_optional_port))
    assert served["statuses"]["add"] == {"status": "ok"}
    assert served["results"]["add"]["out"] == {"kind": "scalar", "value": 1}


def test_both_states_are_indistinguishable_end_to_end() -> None:
    """Round-trip: declaring the optional port and omitting it are the same graph
    as far as validate/compile/execute are concerned. No configuration may be
    accepted by one consumer and rejected by another."""
    declared = _graph_payload(declare_optional_port=True)
    omitted = _graph_payload(declare_optional_port=False)

    assert validate_graph(declared)["diagnostics"] == validate_graph(omitted)["diagnostics"]
    assert compile_graph(declared)["code"] == compile_graph(omitted)["code"]
    assert execute_graph(declared)["results"] == execute_graph(omitted)["results"]


def test_wired_optional_port_still_wins() -> None:
    """Sanity: the fix must not swallow a port that *is* wired."""
    src = _source_node()
    bonus_src = Node(
        id="bonus-src",
        type=_OptSource.type,
        label=_OptSource.label,
        ports=[Port(id="bonus-src-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    add = _add_node(declare_optional_port=True)
    edges = [
        Edge(
            id="e-src-add",
            source=PortRef(node_id="src", port_id="src-out"),
            target=PortRef(node_id="add", port_id="add-in"),
        ),
        Edge(
            id="e-bonus-add",
            source=PortRef(node_id="bonus-src", port_id="bonus-src-out"),
            target=PortRef(node_id="add", port_id="add-bonus"),
        ),
    ]
    graph = Graph(
        nodes={n.id: n for n in (src, bonus_src, add)},
        edges={e.id: e for e in edges},
    )

    assert execute(graph)["add"] == {"out": 2}
    served = execute_graph(json.loads(serialize_graph(graph)))
    assert served["results"]["add"]["out"] == {"kind": "scalar", "value": 2}
    assert "None or 0" not in compile_to_code(graph)


# ---------------------------------------------------------------------------
# Execution-cache keying
# ---------------------------------------------------------------------------


def _two_slot_graph(wired_slot: str) -> dict[str, Any]:
    """`src -> in_` plus the SAME second source wired into *wired_slot* only.

    The other optional slot is declared but left unwired, so the two graphs this
    builds differ ONLY in which optional port the second source feeds.
    """
    src = _source_node()
    feed = Node(
        id="feed",
        type=_OptSource.type,
        label=_OptSource.label,
        ports=[Port(id="feed-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    sink = Node(
        id="sink",
        type=_OptTwoSlots.type,
        label=_OptTwoSlots.label,
        ports=[
            Port(id="sink-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="sink-a", name="slot_a", direction=Direction.IN, data_type="int"),
            Port(id="sink-b", name="slot_b", direction=Direction.IN, data_type="int"),
            Port(id="sink-out", name="out", direction=Direction.OUT, data_type="str"),
        ],
    )
    edges = [
        Edge(
            id="e-src-sink",
            source=PortRef(node_id="src", port_id="src-out"),
            target=PortRef(node_id="sink", port_id="sink-in"),
        ),
        Edge(
            id="e-feed-sink",
            source=PortRef(node_id="feed", port_id="feed-out"),
            target=PortRef(node_id="sink", port_id=f"sink-{wired_slot}"),
        ),
    ]
    graph = Graph(
        nodes={n.id: n for n in (src, feed, sink)},
        edges={e.id: e for e in edges},
    )
    return json.loads(serialize_graph(graph))


def test_cache_key_distinguishes_which_optional_port_is_wired() -> None:
    """Two graphs that wire the same upstream into *different* optional ports
    must not share a cache key.

    An unwired optional port contributes no entry to ``upstream_hashes``, so
    before `_tagged_hash` these two folded to an identical payload and the second
    run was served the first run's result. This is the failure mode the
    relaxed dangling-input guard opened up: pre-fix, every IN port had to be
    wired, so position alone was unambiguous.
    """
    a_wired = execute_graph(_two_slot_graph("a"))
    b_wired = execute_graph(_two_slot_graph("b"))

    assert a_wired["results"]["sink"]["out"] == {"kind": "scalar", "value": "a=1,b=None"}
    assert b_wired["results"]["sink"]["out"] == {"kind": "scalar", "value": "a=None,b=1"}
    # Not a cache hit: the second graph is genuinely different work.
    assert b_wired["statuses"]["sink"]["status"] == "ok"


def test_cache_still_hits_for_an_identical_rerun() -> None:
    """Tagging the hashes must not defeat caching itself: an identical rerun is
    still served from the cache (status "cached", not "ok")."""
    payload = _two_slot_graph("a")

    first = execute_graph(payload)
    second = execute_graph(payload)

    assert first["statuses"]["sink"]["status"] == "ok"
    assert second["statuses"]["sink"]["status"] == "cached"
    assert first["results"]["sink"]["out"] == second["results"]["sink"]["out"]


def test_declared_unwired_and_omitted_share_one_cache_key() -> None:
    """The two spellings of an unfed optional port are the same graph, so they
    must land on the same cache entry -- otherwise deleting an unused port in
    the canvas would silently invalidate that node's cached result.

    Proven by the second run reporting "cached" despite never having been run in
    that spelling before."""
    first = execute_graph(_graph_payload(declare_optional_port=True))
    second = execute_graph(_graph_payload(declare_optional_port=False))

    assert first["statuses"]["add"]["status"] == "ok"
    assert second["statuses"]["add"]["status"] == "cached"
    assert first["results"] == second["results"]


# ---------------------------------------------------------------------------
# The real catalog nodes that carry optional IN ports
# ---------------------------------------------------------------------------


def test_recommend_fit_codegen_tolerates_an_absent_item_features_port() -> None:
    node = RecommendFit().instantiate(algorithm="popularity", params={})
    ctx = CodegenContext(in_vars={"interactions": "im"}, out_vars={"recommender": "rec"})

    fragment = RecommendFit().codegen(node, ctx)

    assert "item_features=None" in fragment.body


def test_recommend_fit_two_tower_codegen_tolerates_absent_feature_ports() -> None:
    node = RecommendFitTwoTower().instantiate(params={})
    ctx = CodegenContext(in_vars={"interactions": "im"}, out_vars={"recommender": "rec"})

    fragment = RecommendFitTwoTower().codegen(node, ctx)

    assert "item_features=None" in fragment.body
    assert "user_features=None" in fragment.body


def test_llm_prompt_codegen_tolerates_absent_template_ports() -> None:
    node = LlmPrompt().instantiate(system="You are {{persona}}.", user="{{q}}", variables={})
    ctx = CodegenContext(in_vars={"variables": "bindings"}, out_vars={"prompt": "prompt"})

    fragment = LlmPrompt().codegen(node, ctx)

    # Both templates fall back to their literal params when nothing is wired.
    assert "(None if None is not None else 'You are {{persona}}.')" in fragment.body
    assert "(None if None is not None else '{{q}}')" in fragment.body
