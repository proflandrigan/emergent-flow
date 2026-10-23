"""Golden snapshots for ``ef.to_mermaid`` (issue #169).

Regenerate with ``uv run pytest tests/test_mermaid_golden.py --snapshot-update``.

Each case is also mirrored to a plain ``tests/golden/mermaid/<name>.mmd`` file so the UI vitest
(``ui/src/io/mermaidGoldens.test.ts``) can run the real Mermaid parser over the same output.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable

import pytest

from emergentflow.codegen.mermaid import to_mermaid
from emergentflow.ir import Direction, Edge, Graph, Node, Port, PortRef, load_graph

REPO_ROOT = pathlib.Path(__file__).parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "mermaid"


def _port(nid: str, name: str, direction: Direction) -> Port:
    suffix = "in" if direction is Direction.IN else "out"
    return Port(id=f"{nid}-{suffix}", name=name, direction=direction)


def _edge(src: str, tgt: str) -> Edge:
    return Edge(
        id=f"{src}->{tgt}",
        source=PortRef(node_id=src, port_id=f"{src}-out"),
        target=PortRef(node_id=tgt, port_id=f"{tgt}-in"),
    )


def _hostile_graph() -> Graph:
    nodes = [
        Node(id="grp", type="layout.group", label="Prep [stage #1]", ports=[]),
        Node(
            id="load",
            type="data.load_csv",
            label='Load "sales.csv" <raw> | v2',
            ports=[_port("load", "frame", Direction.OUT)],
            group_id="grp",
        ),
        Node(
            id="impute",
            type="clean.impute_missing",
            label="Impute {mean} & `fill`\nsecond line",
            ports=[
                _port("impute", "frame", Direction.IN),
                _port("impute", "frame", Direction.OUT),
            ],
            group_id="grp",
        ),
        Node(
            id="fit",
            type="ml.fit_estimator",
            label="Fit model; 100% → done",
            ports=[
                _port("fit", "data", Direction.IN),
                _port("fit", "model", Direction.OUT),
            ],
        ),
        Node(id="note", type="notes.markdown", label="Note: <b>not</b> html", ports=[]),
    ]
    edges = [_edge("load", "impute"), _edge("impute", "fit")]
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def _example(*parts: str) -> Callable[[], str]:
    return lambda: to_mermaid(load_graph(REPO_ROOT.joinpath("examples", *parts)))


CASES: dict[str, Callable[[], str]] = {
    "functional_pipeline": _example("functional_pipeline.json"),
    "declarative_module": _example("declarative_module.json"),
    "acceptance_demo": _example("acceptance_demo", "pipeline.json"),
    "hostile_labels": lambda: to_mermaid(_hostile_graph(), highlight=["fit"], include_notes=True),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_mermaid_golden(name: str, snapshot) -> None:
    assert CASES[name]() == snapshot


@pytest.mark.parametrize("name", sorted(CASES))
def test_mermaid_golden_file_in_sync(name: str, request: pytest.FixtureRequest) -> None:
    """Mirror each snapshot to tests/golden/mermaid/<name>.mmd for the UI's real-parser check."""
    rendered = CASES[name]()
    path = GOLDEN_DIR / f"{name}.mmd"
    if request.config.getoption("--snapshot-update"):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, (
        f"{path} is stale; regenerate with "
        "`uv run pytest tests/test_mermaid_golden.py --snapshot-update`"
    )
