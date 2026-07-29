"""
tests/test_epic16_acceptance_demos.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 16 Story 25's three acceptance demos — builds each demo's IR graph, writes it to
``examples/epic16_acceptance_demos/``, validates it, and proves ADR-0002 equivalence-adjacent
health (both ``execute()`` and the compiled module's ``main()`` run to completion). Mirrors
``tests/test_data_connectors_acceptance_demo.py`` in shape, but builds nodes via ``instantiate``
rather than hand-written ports.
"""

from __future__ import annotations

import ast
import pathlib

import pandas as pd
import pytest

import emergentflow as ef
import emergentflow.nodes  # noqa: F401
from emergentflow.clients import Clients
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.codegen.executor import execute
from emergentflow.data.http.protocol import HttpRequest, HttpResponse
from emergentflow.data.http.replay import ReplayHttpClient, write_http_fixture
from emergentflow.ir import Edge, Graph, Node, Paradigm, PortRef
from emergentflow.nodes import get as get_node_definition
from emergentflow.research.report import ReportMeta, build_report, section_from_value

REPO_ROOT = pathlib.Path(__file__).parent.parent
DEMO_DIR = REPO_ROOT / "examples" / "epic16_acceptance_demos"


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed demo graphs carry repo-relative data paths (see `_repo_relative`), so the
    loaders resolve them against the repo root -- the same contract
    `tests/test_data_connectors_acceptance_demo.py` gets by passing `cwd=REPO_ROOT` to its
    compiled subprocess."""
    monkeypatch.chdir(REPO_ROOT)


def _repo_relative(path: pathlib.Path) -> str:
    """Path as a repo-root-relative POSIX string.

    The demo graphs are committed to `examples/`, so an absolute path would bake this machine's
    home directory into a checked-in artifact and break the demo for every other checkout.
    """
    return path.relative_to(REPO_ROOT).as_posix()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make(node_type: str, node_id: str, **params) -> Node:
    """Instantiate a registered node definition with stable, readable node and port ids.

    `instantiate` mints a fresh UUID per port, which is right for a live canvas but wrong for a
    graph committed to `examples/`: every test run would rewrite all three pipeline JSONs with
    new ids, dirtying the working tree and putting pure churn in every future diff. Deriving each
    port id from `<node id>:<direction>:<port name>` makes the emitted JSON byte-stable across
    runs (`Port.id` is a plain `str` with no UUID constraint) and readable in the committed file.
    """
    node = get_node_definition(node_type)().instantiate(**params)
    node.id = node_id
    for port in node.ports:
        port.id = f"{node_id}:{port.direction.value}:{port.name}"
    return node


def _port_id(node: Node, name: str, direction: str) -> str:
    for port in node.ports:
        if port.name == name and port.direction.value == direction:
            return port.id
    raise KeyError(f"{node.type}: no {direction} port named {name!r}")


def _wire(edge_id: str, src: Node, src_port: str, dst: Node, dst_port: str) -> Edge:
    return Edge(
        id=edge_id,
        source=PortRef(node_id=src.id, port_id=_port_id(src, src_port, "out")),
        target=PortRef(node_id=dst.id, port_id=_port_id(dst, dst_port, "in")),
    )


def _write_pipeline(graph: Graph, filename: str) -> pathlib.Path:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_DIR / filename
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Demo 1 -- north star
# ---------------------------------------------------------------------------

NORTH_STAR_URL = "https://api.example.com/signups"
NORTH_STAR_BODY = (
    '{"rows":['
    '{"user_id":"u1","group":"control","signed_up":"2026-01-05","converted":1},'
    '{"user_id":"u2","group":"control","signed_up":"2026-01-06","converted":0},'
    '{"user_id":"u3","group":"control","signed_up":"2026-01-07","converted":0},'
    '{"user_id":"u4","group":"variant","signed_up":"2026-01-08","converted":1},'
    '{"user_id":"u5","group":"variant","signed_up":"2026-01-09","converted":1},'
    '{"user_id":"u6","group":"variant","signed_up":"2026-01-10","converted":0}'
    "]}"
)

NORTH_STAR_FIXTURES = DEMO_DIR / "http_fixtures"


def build_north_star_demo() -> Graph:
    """HTTP fetch -> parse dates -> derive cohort -> quality gate -> conversion lift -> report."""
    fetch = _make(
        "data.http_fetch",
        "n-fetch",
        label="Signups API",
        url=NORTH_STAR_URL,
        json_path="rows",
        pagination="none",
    )
    dates = _make(
        "clean.parse_dates",
        "n-dates",
        label="Parse signup dates",
        columns=["signed_up"],
        components=["month"],
    )
    derive = _make(
        "clean.derive_column",
        "n-derive",
        label="Derive cohort",
        columns=[{"name": "is_variant", "expr": "group == 'variant'"}],
    )
    gate = _make(
        "research.assert_data",
        "n-gate",
        label="Quality gate",
        expectations=[
            {"type": "non_null", "column": "user_id"},
            {"type": "allowed_values", "column": "group", "values": ["control", "variant"]},
        ],
    )
    prop = _make(
        "stats.test_proportions",
        "n-prop",
        label="Conversion lift",
        group_col="group",
        success_col="converted",
    )
    report = _make(
        "research.build_report",
        "n-report",
        label="Experiment report",
        title="Signup Experiment",
        author="Emergent Flow",
        generated_at="2026-07-29",
    )

    edges = [
        _wire("e-fetch-dates", fetch, "frame", dates, "frame"),
        _wire("e-dates-derive", dates, "frame", derive, "frame"),
        _wire("e-derive-gate", derive, "frame", gate, "frame"),
        _wire("e-gate-prop", gate, "frame", prop, "frame"),
        _wire("e-prop-report", prop, "result", report, "sections"),
    ]

    return Graph(
        name="epic16_north_star",
        paradigm=Paradigm.FUNCTIONAL,
        nodes={n.id: n for n in (fetch, dates, derive, gate, prop, report)},
        edges={e.id: e for e in edges},
    )


def _seed_north_star_fixture() -> ReplayHttpClient:
    NORTH_STAR_FIXTURES.mkdir(parents=True, exist_ok=True)
    write_http_fixture(
        NORTH_STAR_FIXTURES,
        HttpRequest(
            url=NORTH_STAR_URL,
            method="GET",
            headers=(),
            params=(),
            body=None,
            connection=None,
            timeout_s=None,
        ),
        HttpResponse(status=200, body=NORTH_STAR_BODY),
    )
    return ReplayHttpClient(NORTH_STAR_FIXTURES)


def test_north_star_demo_validates() -> None:
    graph = build_north_star_demo()
    _write_pipeline(graph, "north_star_pipeline.json")

    report = ef.validate(graph)
    errors = [d for d in report.diagnostics if d.severity == "error"]
    assert errors == []
    assert all(report.edge_compatibility.values())


def test_north_star_demo_executes_and_compiles() -> None:
    graph = build_north_star_demo()
    replay = _seed_north_star_fixture()
    clients = Clients(http=replay)

    results = execute(graph, clients=clients)
    assert set(results.keys()) == {
        "n-fetch",
        "n-dates",
        "n-derive",
        "n-gate",
        "n-prop",
        "n-report",
    }

    prop_result = results["n-prop"]["result"]
    assert not prop_result.empty
    assert "p_value" in prop_result.columns

    report_result = results["n-report"]["report"]
    assert report_result.html
    assert report_result.sections

    code = compile_to_code(graph)
    ast.parse(code)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"](clients=clients)
    assert main_results


def test_north_star_demo_traces_lineage_and_captures_reproducibility() -> None:
    graph = build_north_star_demo()

    lineage = ef.research.trace_lineage(graph, "n-report")
    assert [n.node_id for n in lineage.nodes] == [
        "n-fetch",
        "n-dates",
        "n-derive",
        "n-gate",
        "n-prop",
        "n-report",
    ]

    capture = ef.research.capture_run(graph)
    assert "n-fetch" in capture.content_hashes

    capture_again = ef.research.capture_run(graph)
    assert capture == capture_again


def test_north_star_report_embeds_lineage_and_reproducibility() -> None:
    """Story 25's "build_report (with lineage + reproducibility block)" clause.

    The `research.build_report` NODE exposes no `reproducibility` param, so a canvas-built graph
    cannot attach the block declaratively -- the composition is available at the `ef.research`
    API level, which is what this asserts. Wiring a `reproducibility` param onto the node would
    be a node contract change, out of scope for Story 25.
    """
    graph = build_north_star_demo()

    lineage = ef.research.trace_lineage(graph, "n-report")
    capture = ef.research.capture_run(graph)

    report = build_report(
        [section_from_value(lineage, title="Lineage")],
        ReportMeta(title="Signup Experiment", generated_at="2026-07-29"),
        reproducibility=capture,
    )

    assert [s.title for s in report.sections] == ["Lineage", "Reproducibility"]
    assert "Lineage" in report.html
    assert "Reproducibility" in report.html


# ---------------------------------------------------------------------------
# Demo 2 -- transform
# ---------------------------------------------------------------------------


def _write_transform_fixtures() -> str:
    """Two monthly CSVs so the committed graph's glob really matches multiple files."""
    data_dir = DEMO_DIR / "sales"
    data_dir.mkdir(parents=True, exist_ok=True)
    for i, month in enumerate(["jan", "feb"]):
        pd.DataFrame(
            {
                "region": ["  East ", "WEST  ", " east"],
                "channel": ["web", "web", "store"],
                "revenue": [10.0 + i, 20.0 + i, 30.0 + i],
                "units": [1 + i, 2 + i, 3 + i],
            }
        ).to_csv(data_dir / f"sales_{month}.csv", index=False)
    return _repo_relative(data_dir / "sales_*.csv")


def build_transform_demo(glob_path: str) -> Graph:
    """Load monthly CSVs -> normalize -> melt -> aggregate / crosstab -> plot."""
    load = _make("data.load_csv", "n-load", label="Load monthly CSVs", path=glob_path)
    text = _make(
        "clean.clean_text",
        "n-text",
        label="Normalize region",
        columns=["region"],
        operations=[{"op": "trim"}, {"op": "lower"}],
    )
    melt = _make(
        "clean.reshape",
        "n-melt",
        label="Melt metrics",
        mode="melt",
        id_vars=["region", "channel"],
        value_vars=["revenue", "units"],
        var_name="metric",
        value_name="amount",
    )
    agg = _make(
        "stats.group_by_aggregate",
        "n-agg",
        label="Mean by region/metric",
        by=["region", "metric"],
        agg="mean",
        columns=["amount"],
    )
    tab = _make(
        "stats.crosstab",
        "n-tab",
        label="Region x metric",
        row_col="region",
        col_col="metric",
        margins=False,
    )
    plot = _make(
        "viz.plot",
        "n-plot",
        label="Region bar chart",
        chart="bar",
        encoding={"x": "region", "y": "amount"},
    )

    edges = [
        _wire("e-load-text", load, "frame", text, "frame"),
        _wire("e-text-melt", text, "frame", melt, "frame"),
        _wire("e-melt-agg", melt, "frame", agg, "frame"),
        _wire("e-melt-tab", melt, "frame", tab, "frame"),
        _wire("e-agg-plot", agg, "summary", plot, "frame"),
    ]

    return Graph(
        name="epic16_transform",
        paradigm=Paradigm.FUNCTIONAL,
        nodes={n.id: n for n in (load, text, melt, agg, tab, plot)},
        edges={e.id: e for e in edges},
    )


def test_transform_demo_validates() -> None:
    glob_path = _write_transform_fixtures()
    graph = build_transform_demo(glob_path)
    _write_pipeline(graph, "transform_pipeline.json")

    report = ef.validate(graph)
    errors = [d for d in report.diagnostics if d.severity == "error"]
    assert errors == []
    assert all(report.edge_compatibility.values())


def test_transform_demo_executes_and_compiles() -> None:
    glob_path = _write_transform_fixtures()
    graph = build_transform_demo(glob_path)

    results = execute(graph)
    assert set(results.keys()) == {
        "n-load",
        "n-text",
        "n-melt",
        "n-agg",
        "n-tab",
        "n-plot",
    }

    summary = results["n-agg"]["summary"]
    assert list(summary.columns) == ["region", "metric", "amount"]
    assert len(summary) == 4
    assert all(region == region.strip().lower() for region in summary["region"])

    code = compile_to_code(graph)
    ast.parse(code)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"]()
    assert main_results


# ---------------------------------------------------------------------------
# Demo 3 -- research
# ---------------------------------------------------------------------------


def _write_research_fixture() -> str:
    """A tiny markdown corpus with a planted email address, so redact_pii has something to do."""
    docs_dir = DEMO_DIR / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / "handbook.md"
    path.write_text(
        "# Field Handbook\n\n"
        "Contact the research desk at research@example.com for access requests.\n\n"
        "## Sampling\n\n"
        "Every survey wave draws 400 respondents, stratified by region.\n",
        encoding="utf-8",
    )
    return _repo_relative(path)


def build_research_demo(path: str, *, render_pdf: bool = False) -> Graph:
    """Load documents -> codebook -> redact PII -> report."""
    load = _make(
        "data.load_documents",
        "n-docs",
        label="Load documents",
        path=path,
        chunk_size=200,
        chunk_overlap=20,
    )
    dictionary = _make("stats.data_dictionary", "n-dict", label="Codebook", top_n=3)
    redact = _make(
        "clean.redact_pii",
        "n-redact",
        label="Redact PII",
        categories=["email", "phone"],
        engine="regex",
    )
    report = _make(
        "research.build_report",
        "n-report",
        label="Corpus report",
        title="Document Corpus Codebook",
        author="Emergent Flow",
        generated_at="2026-07-29",
        render_pdf=render_pdf,
    )

    edges = [
        # data.load_documents' OUT port is DocumentFrame and stats.data_dictionary's IN port is
        # DataFrame -- this edge is only compatible because of the DocumentFrame <: DataFrame
        # subtype edge declared in emergentflow/types/catalog.py (Epic 16, Story 22).
        _wire("e-docs-dict", load, "frame", dictionary, "frame"),
        _wire("e-dict-redact", dictionary, "dictionary", redact, "frame"),
        _wire("e-redact-report", redact, "frame", report, "sections"),
    ]

    return Graph(
        name="epic16_research",
        paradigm=Paradigm.FUNCTIONAL,
        nodes={n.id: n for n in (load, dictionary, redact, report)},
        edges={e.id: e for e in edges},
    )


def test_research_demo_validates() -> None:
    path = _write_research_fixture()
    graph = build_research_demo(path, render_pdf=False)
    _write_pipeline(graph, "research_pipeline.json")

    report = ef.validate(graph)
    errors = [d for d in report.diagnostics if d.severity == "error"]
    assert errors == []
    assert all(report.edge_compatibility.values())
    # Regression guard for the DocumentFrame <: DataFrame subtype edge (Epic 16, Story 22).
    assert report.edge_compatibility["e-docs-dict"] is True


def test_research_demo_executes_and_compiles() -> None:
    path = _write_research_fixture()
    graph = build_research_demo(path, render_pdf=False)

    results = execute(graph)
    assert set(results.keys()) == {"n-docs", "n-dict", "n-redact", "n-report"}

    dictionary = results["n-dict"]["dictionary"]
    assert "column" in dictionary.columns
    assert "top_values" in dictionary.columns
    assert "notes" in dictionary.columns

    report_result = results["n-report"]["report"]
    assert report_result.html
    assert report_result.pdf_bytes is None

    code = compile_to_code(graph)
    ast.parse(code)
    ns: dict = {}
    exec(code, ns)  # noqa: S102 -- test-only, on our own emitted code
    main_results = ns["main"]()
    assert main_results


def test_research_demo_pdf_lane() -> None:
    pytest.importorskip("weasyprint")

    path = _write_research_fixture()
    graph = build_research_demo(path, render_pdf=True)

    results = execute(graph)
    pdf_bytes = results["n-report"]["report"].pdf_bytes
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes


def test_committed_pipelines_are_byte_stable_across_runs() -> None:
    """Rebuilding a demo graph twice must serialize identically.

    The demo JSONs are committed to `examples/`, and every test run rewrites them. If node or
    port ids were nondeterministic (as raw `instantiate` makes them -- see `_make`), each
    `uv run pytest` would dirty the working tree and every future PR would carry pure id churn.
    """
    for build in (
        lambda: build_north_star_demo(),
        lambda: build_transform_demo(_write_transform_fixtures()),
        lambda: build_research_demo(_write_research_fixture()),
    ):
        first = build().model_dump_json(indent=2)
        second = build().model_dump_json(indent=2)
        assert first == second
