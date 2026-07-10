"""Golden/snapshot tests for the solo-canvas HTTP surface and IR schema/version
(Epic 14 Story 11).

Proves the immutable-by-fiat solo-canvas HTTP routes (``/compile``, ``/validate``,
``/execute``) and the IR schema/version constants are byte-identical to how they
behaved before Epic 14's collaboration additions — the "the package and app work
identically with or without agents" invariant, made concrete for the server's
non-session routes specifically.

``compile_to_code`` output is already covered by golden tests in
``tests/test_codegen_golden.py`` and canvas ``toIR``/``fromIR`` by
``ui/src/store/ir.test.ts`` — both out of scope here.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from emergentflow.ir import (
    Direction,
    Graph,
    Node,
    Paradigm,
    Param,
    Port,
    Position,
)
from emergentflow.ir.graph import CURRENT_SCHEMA_VERSION
from emergentflow.ir.serialize import serialize_graph
from emergentflow.server import app
from emergentflow.server import cache as cache_mod

SAMPLE_CSV = (
    pathlib.Path(__file__).resolve().parents[1] / "examples" / "vertical_slice" / "sample.csv"
)


@pytest.fixture(autouse=True)
def _fresh_default_cache(tmp_path: pathlib.Path) -> Iterator[None]:
    """Isolate the on-disk execution cache per test so cached outputs from one
    test don't produce false cache hits in another."""
    from emergentflow.server.cache import ExecutionCache

    old = cache_mod._default_cache
    cache_mod._default_cache = ExecutionCache(root=tmp_path / ".ef-cache")
    yield
    cache_mod._default_cache = old


def _load_csv_graph(path: str | None = None) -> dict:
    """A minimal one-node functional graph that loads the bundled sample CSV."""
    node = Node(
        id="n-load",
        type="data.load_csv",
        label="Load CSV",
        paradigm=Paradigm.FUNCTIONAL,
        params=[Param(name="path", type_token="str", value=path or str(SAMPLE_CSV))],
        ports=[
            Port(
                id="p-load-frame",
                name="frame",
                direction=Direction.OUT,
                data_type="DataFrame",
            ),
        ],
        position=Position(x=0.0, y=0.0),
    )
    graph = Graph(
        paradigm=Paradigm.FUNCTIONAL,
        name="server-test",
        nodes={node.id: node},
        edges={},
    )
    return json.loads(serialize_graph(graph))


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A FastAPI test client over the module-level ``app`` (no real socket)."""
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Solo-canvas HTTP route goldens
# ---------------------------------------------------------------------------


def test_compile_response_golden(client: TestClient, snapshot) -> None:
    resp = client.post("/compile", json=_load_csv_graph())
    assert resp.status_code == 200
    assert resp.json() == snapshot


def test_validate_response_golden(client: TestClient, snapshot) -> None:
    resp = client.post("/validate", json=_load_csv_graph())
    assert resp.status_code == 200
    assert resp.json() == snapshot


def test_execute_response_golden(client: TestClient, snapshot) -> None:
    resp = client.post("/execute", json=_load_csv_graph())
    assert resp.status_code == 200
    assert resp.json() == snapshot


# ---------------------------------------------------------------------------
# IR schema/version invariants
# ---------------------------------------------------------------------------


def test_current_schema_version_is_pinned_at_one() -> None:
    # Epic 14's DoD requires the IR wire format stay untouched by the
    # collaboration layer: no new Graph/Node/Edge field, no migration step,
    # no schema_version bump (epics/epic-14-agent-collaboration.md, Definition
    # of Done). This pins that invariant permanently.
    assert CURRENT_SCHEMA_VERSION == 1


def test_ir_schema_json_unchanged_golden(snapshot) -> None:
    schema_path = (
        pathlib.Path(__file__).resolve().parents[1] / "ui" / "src" / "generated" / "ir.schema.json"
    )
    assert schema_path.read_text() == snapshot
