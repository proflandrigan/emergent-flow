"""Equivalence harness — the ADR-0002 "A2" invariant (Epic 2, Story 6).

ADR 0002 commits the SDK to two pure functions over one IR — ``execute(graph)``
and ``compile_to_code(graph)`` — whose artifacts must be *equivalent*. This module
turns that promise into an enforced, corpus-driven gate:

  1. **execute side** — run ``execute(graph)`` in-process and canonicalize every
     per-port artifact to a JSON-native, comparable form.
  2. **code side** — compile the graph, run the emitted Python *as a real
     subprocess* (the genuine "what you see runs" path), and have it dump the
     same per-port artifacts to JSON via the SAME canonicalizer.
  3. assert the two sides match (float-tolerant, NaN-aware).

To run the compiled body and read its variables, the harness reuses the
compiler's internal ``_assemble`` seam (imports + un-indented body statements +
the OUT-port→variable map) and emits a module-scope script with a JSON-dump
footer — rather than the production ``main()`` module, which hides its locals
and ``del``s leaf bindings.

**Equivalence boundary.** Computed data artifacts (DataFrames, the ANOVA and
classifier result dataclasses) are compared *exactly*. Rendered-document
artifacts — OUT ports whose ``data_type`` is in :data:`_VOLATILE_DATA_TYPES`,
i.e. the ydata-profiling HTML report — embed wall-clock timestamps and measured
durations, so they are not byte-deterministic even across two runs of the
identical code path; for those the harness asserts *shape parity* (both sides a
non-empty string) instead of byte-equality. The deterministic computational
artifacts are what actually prove execute ≡ compile.

The productionized, sandboxed runtime is Epic 6; this executor/harness is the
pure, in-process reference that proves the invariant.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

import pytest

from emergentflow.codegen.compiler import _assemble, compile_to_code
from emergentflow.codegen.errors import CycleError, GraphValidationError
from emergentflow.codegen.executor import execute
from emergentflow.codegen.validation import validate
from emergentflow.ir import Direction, Edge, Graph, Node, Port, PortRef, load_graph
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.registry import register
from emergentflow.nodes.spec import PortSpec

REPO_ROOT = pathlib.Path(__file__).parent.parent

#: OUT-port data types whose artifact is a rendered document (not a deterministic
#: computed value). Compared by shape parity, not bytes — see the module docstring.
_VOLATILE_DATA_TYPES = frozenset({"HTML"})

# ---------------------------------------------------------------------------
# Canonicalizer — ONE source of truth, run on both sides.
#
# Defined as source text so the *identical* function executes in-process (the
# execute side) and inside the subprocess that runs the compiled module (the
# code side). Maps any artifact to a JSON-native, comparable structure:
#   * numpy scalars -> python scalars (via .item())
#   * DataFrame-like -> {"__df__": {column: [values]}} (deterministic)
#   * dataclass      -> {field: canon(value)} (recurses the DataFrame `summary`)
#   * pydantic model -> canon(model_dump())
#   * dict/list/tuple -> recurse
#   * scalars        -> as-is; anything else -> repr() (stable last resort)
# ---------------------------------------------------------------------------
_CANON_SRC = """
import dataclasses as _dc


def _canon(obj):
    # numpy (and similar 0-dim) scalars expose .item() and no __len__.
    if (
        hasattr(obj, "item")
        and not hasattr(obj, "__len__")
        and not isinstance(obj, (str, bytes))
    ):
        try:
            return _canon(obj.item())
        except Exception:
            pass
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    # DataFrame-like (duck-typed, matches pandas/polars): columns -> value lists.
    if hasattr(obj, "to_dict") and hasattr(obj, "shape") and hasattr(obj, "columns"):
        return {"__df__": {str(k): _canon(list(v)) for k, v in obj.to_dict(orient="list").items()}}
    # numpy ndarray / array-like (has tolist + shape but is not a DataFrame, handled
    # above): compare real values, not a repr() that is sensitive to print options.
    if hasattr(obj, "tolist") and hasattr(obj, "shape"):
        return _canon(obj.tolist())
    if _dc.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _canon(getattr(obj, f.name)) for f in _dc.fields(obj)}
    if hasattr(obj, "model_dump"):  # pydantic BaseModel
        return _canon(obj.model_dump())
    if isinstance(obj, dict):
        return {str(k): _canon(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    # Last resort: a repr -- but only when the class defines its own (stable, meaningful) one.
    # An object relying on the default object.__repr__ embeds a per-process memory address
    # (e.g. statsmodels' *ResultsWrapper carried in FittedStatsModel.results, an Any-typed live
    # model object the result-payload contract explicitly degrades to {"kind": "unsupported"}),
    # which differs between the in-process execute side and the compiled-code subprocess even for
    # a bit-identical fit. Degrade those to a stable, address-free sentinel mirroring that same
    # contract -- so opaque live-model internals are never compared, exactly as intended.
    if type(obj).__repr__ is object.__repr__:
        return {"__unsupported__": type(obj).__name__}
    return repr(obj)
"""

_canon_ns: dict[str, Any] = {}
exec(_CANON_SRC, _canon_ns)
_canon = _canon_ns["_canon"]

_SENTINEL_PATH_VAR = "_CM_ARTIFACTS_PATH"


def _volatile_ports(graph: Graph) -> set[tuple[str, str]]:
    """(node_id, out_port_name) pairs whose data_type is a rendered document."""
    out: set[tuple[str, str]] = set()
    for node in graph.nodes.values():
        for port in node.ports:
            if port.direction == Direction.OUT and port.data_type in _VOLATILE_DATA_TYPES:
                out.add((node.id, port.name))
    return out


def _execute_side(graph: Graph, *, cwd: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Run execute() in-process and canonicalize every per-port artifact.

    Runs under ``cwd`` so relative data paths in the graph resolve exactly as
    they do for the subprocess (code) side.
    """
    prev = pathlib.Path.cwd()
    os.chdir(cwd)
    try:
        raw = execute(graph)
    finally:
        os.chdir(prev)
    canon = {nid: {p: _canon(v) for p, v in outs.items()} for nid, outs in raw.items()}
    # Round-trip through JSON so this side normalizes identically to the code
    # side (key coercion, NaN handling), making the comparison apples-to-apples.
    return json.loads(json.dumps(canon))


def _code_side(graph: Graph, *, cwd: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Compile the graph, run the emitted module as a subprocess, return artifacts.

    Builds an *instrumented* variant of the compiled module from the compiler's
    ``_assemble`` seam: the same imports and body statements, but at module scope
    (no ``main()`` wrapper, no ``del`` of leaf vars) plus a footer that
    canonicalizes each OUT-port variable and writes the per-port artifact map to
    a temp JSON file. Running it as a real subprocess is the faithful
    "code runs outside the canvas" path.
    """
    assembled = _assemble(graph)
    fd, tmp_name = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    out_path = pathlib.Path(tmp_name)

    lines: list[str] = []
    lines.extend(assembled.imports)
    lines.append(_CANON_SRC)
    lines.append("import json as _json")
    lines.append("import pathlib as _pl")
    lines.extend(assembled.body_statements)  # module scope; no del, no main()
    lines.append(f"_OUT_PORTS = {assembled.out_ports!r}")
    lines.append("_g = globals()")
    lines.append("_artifacts = {}")
    lines.append("for _nid, _pname, _var in _OUT_PORTS:")
    lines.append("    _artifacts.setdefault(_nid, {})[_pname] = _canon(_g[_var])")
    lines.append(f"_pl.Path({str(out_path)!r}).write_text(_json.dumps(_artifacts))")
    script = "\n".join(lines)

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            # Bound the wait so a hung library call (e.g. ydata-profiling) surfaces
            # as a clear TimeoutExpired test failure rather than hanging CI forever.
            timeout=180,
        )
        assert proc.returncode == 0, (
            "compiled module failed to run:\n"
            f"STDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}\nSCRIPT:\n{script}"
        )
        return json.loads(out_path.read_text())
    finally:
        out_path.unlink(missing_ok=True)


def _assert_equiv(exec_v: Any, code_v: Any, path: str = "") -> None:
    """Deep, float-tolerant, NaN-aware equality between two canonical artifacts."""
    if isinstance(exec_v, dict):
        assert isinstance(code_v, dict), f"type mismatch at {path}: dict vs {type(code_v).__name__}"
        assert exec_v.keys() == code_v.keys(), (
            f"dict-key mismatch at {path}: {sorted(exec_v)} vs {sorted(code_v)}"
        )
        for key in exec_v:
            _assert_equiv(exec_v[key], code_v[key], f"{path}.{key}")
    elif isinstance(exec_v, list):
        assert isinstance(code_v, list), f"type mismatch at {path}: list vs {type(code_v).__name__}"
        assert len(exec_v) == len(code_v), f"list-length mismatch at {path}"
        for i, (a, b) in enumerate(zip(exec_v, code_v, strict=False)):
            _assert_equiv(a, b, f"{path}[{i}]")
    elif isinstance(exec_v, bool) or isinstance(code_v, bool):
        # bool is an int subclass; compare strictly so True is not equal to 1.
        assert type(exec_v) is type(code_v) and exec_v == code_v, (
            f"bool mismatch at {path}: {exec_v!r} != {code_v!r}"
        )
    elif isinstance(exec_v, (int, float)) or isinstance(code_v, (int, float)):
        # Both must be numeric; a number-vs-non-number pair is a clear mismatch
        # (not a TypeError out of math.isclose).
        assert isinstance(exec_v, (int, float)) and isinstance(code_v, (int, float)), (
            f"numeric/type mismatch at {path}: {exec_v!r} != {code_v!r}"
        )
        if math.isnan(exec_v) and math.isnan(code_v):
            return
        assert math.isclose(exec_v, code_v, rel_tol=1e-9, abs_tol=1e-12), (
            f"float mismatch at {path}: {exec_v!r} != {code_v!r}"
        )
    else:
        assert exec_v == code_v, f"mismatch at {path}: {exec_v!r} != {code_v!r}"


def assert_equivalent(graph: Graph, *, cwd: pathlib.Path = REPO_ROOT) -> None:
    """Assert ``execute(graph)`` artifacts equal artifacts from running compiled code.

    ``cwd`` is the working directory the compiled subprocess runs in, so that any
    relative data paths in the graph (e.g. a ``load_csv`` path) resolve.
    """
    exec_side = _execute_side(graph, cwd=cwd)
    code_side = _code_side(graph, cwd=cwd)

    assert exec_side.keys() == code_side.keys(), (
        f"node-id sets differ: {sorted(exec_side)} vs {sorted(code_side)}"
    )

    volatile = _volatile_ports(graph)
    for node_id in exec_side:
        e_ports, c_ports = exec_side[node_id], code_side[node_id]
        assert e_ports.keys() == c_ports.keys(), (
            f"port set differs for node {node_id!r}: {sorted(e_ports)} vs {sorted(c_ports)}"
        )
        for port_name in e_ports:
            e_val, c_val = e_ports[port_name], c_ports[port_name]
            if (node_id, port_name) in volatile:
                # Rendered document: assert shape parity, not byte-equality.
                assert isinstance(e_val, str) and isinstance(c_val, str), (
                    f"volatile port {node_id}.{port_name} expected str on both sides"
                )
                assert e_val and c_val, f"volatile port {node_id}.{port_name} empty on a side"
            else:
                _assert_equiv(e_val, c_val, f"{node_id}.{port_name}")


def assert_rejected_equivalently(
    graph: Graph, *, expected_error: type[Exception] = GraphValidationError
) -> None:
    """Assert ``execute`` and ``compile_to_code`` reject *graph* identically.

    The negative twin of `assert_equivalent`: both pure functions must raise the
    same error type with the same message (ADR 0002 equivalence extends to
    rejection — both route through the single shared validation gate, Story 6).
    """
    with pytest.raises(expected_error) as exec_exc:
        execute(graph)
    with pytest.raises(expected_error) as compile_exc:
        compile_to_code(graph)
    assert str(exec_exc.value) == str(compile_exc.value), (
        "execute and compile_to_code rejected the graph with different messages:\n"
        f"execute:        {exec_exc.value}\n"
        f"compile_to_code:{compile_exc.value}"
    )


# ---------------------------------------------------------------------------
# Trivial hermetic proof — pure-Python integer nodes, no data files.
# Unique type keys (test.equiv_*) avoid colliding with the fakes registered in
# tests/test_codegen_executor.py when both modules load in one pytest session.
# ---------------------------------------------------------------------------


@register
class _EquivSource(NodeDefinition):
    """Test fixture: 0 in, 1 out. Emits the constant 7."""

    type = "test.equiv_source"
    family = "test"
    label = "Equiv Src"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="int")]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = 7")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": 7}


@register
class _EquivDouble(NodeDefinition):
    """Test fixture: 1 in, 1 out. out = in_ * 2."""

    type = "test.equiv_double"
    family = "test"
    label = "Equiv Double"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="int"),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in_')} * 2")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"] * 2}


@register
class _EquivJoin2(NodeDefinition):
    """Test fixture: 2 in (a, b), 1 out. out = a + b — exercises fan-in wiring."""

    type = "test.equiv_join2"
    family = "test"
    label = "Equiv Join2"
    ports = [
        PortSpec(name="a", direction=Direction.IN, data_type="int"),
        PortSpec(name="b", direction=Direction.IN, data_type="int"),
        PortSpec(name="out", direction=Direction.OUT, data_type="int"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('a')} + {ctx.in_var('b')}")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["a"] + inputs["b"]}


@register
class _EquivDFSource(NodeDefinition):
    """Test fixture: 0 in, 1 out, declares a registered ``DataFrame`` OUT token."""

    type = "test.equiv_df_source"
    family = "test"
    label = "Equiv DF Src"
    ports = [PortSpec(name="out", direction=Direction.OUT, data_type="DataFrame")]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = None")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": None}


@register
class _EquivHTMLSink(NodeDefinition):
    """Test fixture: 1 in (registered ``HTML`` token), 1 out — type-incompatible IN."""

    type = "test.equiv_html_sink"
    family = "test"
    label = "Equiv HTML Sink"
    ports = [
        PortSpec(name="in_", direction=Direction.IN, data_type="HTML"),
        PortSpec(name="out", direction=Direction.OUT, data_type="HTML"),
    ]

    def codegen(self, node: Node, ctx: Any) -> CodeFragment:
        return CodeFragment(body=f"{ctx.out_var('out')} = {ctx.in_var('in_')}")

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"out": inputs["in_"]}


@pytest.mark.equivalence
def test_trivial_chain_equivalence() -> None:
    """A pure-Python source->double chain proves the harness end to end."""
    src = Node(
        id="src",
        type=_EquivSource.type,
        label=_EquivSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    dbl = Node(
        id="dbl",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="dbl-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="dbl-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    edge = Edge(
        source=PortRef(node_id="src", port_id="src-out"),
        target=PortRef(node_id="dbl", port_id="dbl-in"),
    )
    graph = Graph(nodes={src.id: src, dbl.id: dbl}, edges={edge.id: edge})

    assert_equivalent(graph)


@pytest.mark.equivalence
def test_empty_graph_equivalence() -> None:
    """The empty graph is trivially equivalent (no artifacts on either side)."""
    assert_equivalent(Graph())


# ---------------------------------------------------------------------------
# Corpus — the two graphs Story 6 names. Real reference nodes over real data.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_vertical_slice_equivalence() -> None:
    """The vertical slice (fan-out) is equivalent end to end over its sample CSV."""
    slice_dir = REPO_ROOT / "examples" / "vertical_slice"
    graph = load_graph(slice_dir / "pipeline.json")
    # cwd = the slice dir so the graph's relative "sample.csv" path resolves.
    assert_equivalent(graph, cwd=slice_dir)


@pytest.mark.equivalence
def test_functional_pipeline_equivalence() -> None:
    """The functional pipeline (linear chain) is equivalent over the sample CSV."""
    graph = load_graph(REPO_ROOT / "examples" / "functional_pipeline.json")
    # Its load_csv path is repo-root-relative, so run from the repo root.
    assert_equivalent(graph, cwd=REPO_ROOT)


@pytest.mark.equivalence
def test_acceptance_demo_equivalence() -> None:
    """The Story 7 acceptance demo (incl. the Model-bearing train->evaluate edge) is
    equivalent end to end. Uses the bundled sample dataset, so no cwd/file setup is needed."""
    graph = load_graph(REPO_ROOT / "examples" / "acceptance_demo" / "pipeline.json")
    assert_equivalent(graph)


def _diamond_graph() -> Graph:
    """A reconverging diamond: src -> {dbl_a, dbl_b} -> join.

    Exercises fan-out (src.out feeds two targets) AND fan-in (join has two IN
    ports fed by two distinct upstreams) — neither expressible with the
    single-input reference catalog, so built from the pure-Python int fakes.
    """
    src = Node(
        id="src",
        type=_EquivSource.type,
        label=_EquivSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    dbl_a = Node(
        id="dbl_a",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="dbl_a-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="dbl_a-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    dbl_b = Node(
        id="dbl_b",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="dbl_b-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="dbl_b-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    join = Node(
        id="join",
        type=_EquivJoin2.type,
        label=_EquivJoin2.label,
        ports=[
            Port(id="join-a", name="a", direction=Direction.IN, data_type="int"),
            Port(id="join-b", name="b", direction=Direction.IN, data_type="int"),
            Port(id="join-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    edges = [
        Edge(
            source=PortRef(node_id="src", port_id="src-out"),
            target=PortRef(node_id="dbl_a", port_id="dbl_a-in"),
        ),
        Edge(
            source=PortRef(node_id="src", port_id="src-out"),
            target=PortRef(node_id="dbl_b", port_id="dbl_b-in"),
        ),
        Edge(
            source=PortRef(node_id="dbl_a", port_id="dbl_a-out"),
            target=PortRef(node_id="join", port_id="join-a"),
        ),
        Edge(
            source=PortRef(node_id="dbl_b", port_id="dbl_b-out"),
            target=PortRef(node_id="join", port_id="join-b"),
        ),
    ]
    return Graph(
        nodes={n.id: n for n in (src, dbl_a, dbl_b, join)},
        edges={e.id: e for e in edges},
    )


@pytest.mark.equivalence
def test_diamond_equivalence() -> None:
    """The reconverging diamond is execute/compile equivalent (join out == 28)."""
    assert_equivalent(_diamond_graph())


def test_diamond_golden(snapshot) -> None:
    """The diamond compiles to stable golden code (fan-in/fan-out wiring)."""
    assert compile_to_code(_diamond_graph()) == snapshot


# ---------------------------------------------------------------------------
# Negative equivalence — both pure functions must reject identically.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
def test_type_incompatible_rejected_equivalently() -> None:
    """A DataFrame->HTML edge is rejected identically by execute and compile."""
    src = Node(
        id="df_src",
        type=_EquivDFSource.type,
        label=_EquivDFSource.label,
        ports=[Port(id="df_src-out", name="out", direction=Direction.OUT, data_type="DataFrame")],
    )
    sink = Node(
        id="html_sink",
        type=_EquivHTMLSink.type,
        label=_EquivHTMLSink.label,
        ports=[
            Port(id="html_sink-in", name="in_", direction=Direction.IN, data_type="HTML"),
            Port(id="html_sink-out", name="out", direction=Direction.OUT, data_type="HTML"),
        ],
    )
    edge = Edge(
        source=PortRef(node_id="df_src", port_id="df_src-out"),
        target=PortRef(node_id="html_sink", port_id="html_sink-in"),
    )
    graph = Graph(nodes={src.id: src, sink.id: sink}, edges={edge.id: edge})
    assert_rejected_equivalently(graph)


@pytest.mark.equivalence
def test_cardinality_violation_rejected_equivalently() -> None:
    """Two edges into one Cardinality.ONE IN port: rejected identically."""
    src_a = Node(
        id="src_a",
        type=_EquivSource.type,
        label=_EquivSource.label,
        ports=[Port(id="src_a-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    src_b = Node(
        id="src_b",
        type=_EquivSource.type,
        label=_EquivSource.label,
        ports=[Port(id="src_b-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    dbl = Node(
        id="dbl",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="dbl-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="dbl-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    edges = [
        Edge(
            source=PortRef(node_id="src_a", port_id="src_a-out"),
            target=PortRef(node_id="dbl", port_id="dbl-in"),
        ),
        Edge(
            source=PortRef(node_id="src_b", port_id="src_b-out"),
            target=PortRef(node_id="dbl", port_id="dbl-in"),
        ),
    ]
    graph = Graph(
        nodes={n.id: n for n in (src_a, src_b, dbl)},
        edges={e.id: e for e in edges},
    )
    assert_rejected_equivalently(graph)


@pytest.mark.equivalence
def test_cycle_rejected_equivalently() -> None:
    """A 2-node cycle is rejected identically (CycleError) by execute and compile.

    Cycle rejection is not a `GraphValidationError`: the gate runs `validate`,
    whose inference pass calls `topological_sort`, which raises `CycleError`
    (a `CodegenError`). Because BOTH pure functions route through the gate first,
    they raise the identical error — this test pins that equivalence so a future
    refactor of the inference pass can't silently break it.
    """
    a = Node(
        id="a",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="a-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="a-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    b = Node(
        id="b",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="b-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="b-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    edges = [
        Edge(
            source=PortRef(node_id="a", port_id="a-out"),
            target=PortRef(node_id="b", port_id="b-in"),
        ),
        Edge(
            source=PortRef(node_id="b", port_id="b-out"),
            target=PortRef(node_id="a", port_id="a-in"),
        ),
    ]
    graph = Graph(nodes={a.id: a, b.id: b}, edges={e.id: e for e in edges})
    assert_rejected_equivalently(graph, expected_error=CycleError)


@pytest.mark.equivalence
def test_warning_only_graph_runs_through_both(tmp_path: pathlib.Path) -> None:
    """Warn-don't-block, proven end to end: a graph whose only finding is a
    warning (unregistered `int` tokens) is NOT blocked — it validates with
    warnings, yet `compile_to_code` emits source and `execute` returns results,
    and the two stay equivalent.
    """
    src = Node(
        id="src",
        type=_EquivSource.type,
        label=_EquivSource.label,
        ports=[Port(id="src-out", name="out", direction=Direction.OUT, data_type="int")],
    )
    dbl = Node(
        id="dbl",
        type=_EquivDouble.type,
        label=_EquivDouble.label,
        ports=[
            Port(id="dbl-in", name="in_", direction=Direction.IN, data_type="int"),
            Port(id="dbl-out", name="out", direction=Direction.OUT, data_type="int"),
        ],
    )
    edge = Edge(
        source=PortRef(node_id="src", port_id="src-out"),
        target=PortRef(node_id="dbl", port_id="dbl-in"),
    )
    graph = Graph(nodes={src.id: src, dbl.id: dbl}, edges={edge.id: edge})

    # The graph is "warn-don't-block": warnings present, no errors.
    diagnostics = validate(graph)
    assert diagnostics.ok  # no error-severity diagnostics
    assert diagnostics.warnings  # but the unregistered `int` tokens warn

    # Neither pure function is blocked by the warnings.
    source = compile_to_code(graph)
    assert "def main()" in source
    assert execute(graph)["dbl"] == {"out": 14}

    # ...and they remain equivalent.
    assert_equivalent(graph, cwd=tmp_path)
