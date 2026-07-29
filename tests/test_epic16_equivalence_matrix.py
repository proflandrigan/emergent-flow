"""
Epic 16 Story 24 -- cross-family ADR-0002 equivalence matrix over every node the epic added,
keyed on each node's inspectable output (not one bespoke test per node -- each node's
hand-verified correctness test lives elsewhere; see tests/test_reference_nodes.py and the
per-story test files). Mirrors tests/test_recommend_equivalence_matrix.py (Epic 15 Story 13) in
structure: one parametrized sweep rather than 31 hand-written cases, plus a completeness guard so
a future Epic-16-family node can't silently escape coverage.
"""

from __future__ import annotations

import dataclasses
import math
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pytest

from emergentflow.data.http.protocol import HttpRequest, HttpResponse
from emergentflow.data.http.replay import ReplayHttpClient, write_http_fixture
from emergentflow.data.http.sheets import SHEETS_CSV_URL
from emergentflow.nodes import get as get_node_definition

pytestmark = pytest.mark.equivalence


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _frame() -> pd.DataFrame:
    """One deterministic frame wide enough to feed every DataFrame-consuming case."""
    return pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u2", "u2", "u3", "u3"],
            "group": ["a", "b", "a", "b", "a", "b"],
            "event": ["view", "cart", "view", "cart", "view", "buy"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "other": [2.0, 1.0, 5.0, 2.0, 9.0, 1.0],
            "success": [1, 0, 1, 1, 0, 1],
            "when": [
                "2026-01-01",
                "2026-01-15",
                "2026-02-01",
                "2026-02-10",
                "2026-03-01",
                "2026-03-05",
            ],
            "text": ["  Hello ", "WORLD  ", " a@b.com ", "x", "y", "z"],
            "p_value": [0.01, 0.04, 0.2, 0.5, 0.001, 0.3],
        }
    )


def _assert_artifacts_equal(executed: Any, generated: Any, path: str = "") -> None:
    """Recursively compare two inspectable artifacts, dispatching on type so DataFrame/Series
    fields nested inside dataclasses (CrosstabResult, CohortRetentionResult,
    DimensionReductionResult, Report) don't hit Python's ambiguous-truth-value error on `==`."""
    if isinstance(executed, pd.DataFrame):
        assert isinstance(generated, pd.DataFrame), (
            f"{path}: expected DataFrame, got {type(generated)}"
        )
        pd.testing.assert_frame_equal(executed, generated, check_exact=False, rtol=1e-9)
    elif isinstance(executed, pd.Series):
        assert isinstance(generated, pd.Series), f"{path}: expected Series, got {type(generated)}"
        pd.testing.assert_series_equal(executed, generated, check_exact=False, rtol=1e-9)
    elif dataclasses.is_dataclass(executed) and not isinstance(executed, type):
        assert type(executed) is type(generated), (
            f"{path}: dataclass type mismatch {type(executed)} != {type(generated)}"
        )
        for field in dataclasses.fields(executed):
            _assert_artifacts_equal(
                getattr(executed, field.name),
                getattr(generated, field.name),
                path=f"{path}.{field.name}",
            )
    elif isinstance(executed, dict):
        assert isinstance(generated, dict), f"{path}: expected dict, got {type(generated)}"
        assert set(executed.keys()) == set(generated.keys()), (
            f"{path}: key sets differ: {sorted(executed.keys())} != {sorted(generated.keys())}"
        )
        for key in executed:
            _assert_artifacts_equal(executed[key], generated[key], path=f"{path}[{key!r}]")
    elif isinstance(executed, (list, tuple)):
        assert isinstance(generated, (list, tuple)), (
            f"{path}: expected list/tuple, got {type(generated)}"
        )
        assert len(executed) == len(generated), (
            f"{path}: length mismatch {len(executed)} != {len(generated)}"
        )
        for i, (a_item, b_item) in enumerate(zip(executed, generated, strict=True)):
            _assert_artifacts_equal(a_item, b_item, path=f"{path}[{i}]")
    elif isinstance(executed, float) and isinstance(generated, float):
        if math.isnan(executed) and math.isnan(generated):
            pass
        else:
            assert math.isclose(executed, generated, rel_tol=1e-9, abs_tol=1e-12), (
                f"{path}: floats differ: {executed} != {generated}"
            )
    else:
        assert executed == generated, f"{path}: {executed!r} != {generated!r}"


@dataclass
class Case:
    node_type: str
    params: dict[str, Any]
    make_inputs: Callable[[], dict[str, Any]]


CASES: list[Case] = [
    Case(
        "clean.clean_text",
        {"columns": ["text"], "operations": [{"op": "trim"}, {"op": "lower"}]},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.parse_dates",
        {"columns": ["when"], "components": ["year", "month"]},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.derive_column",
        {"columns": [{"name": "doubled", "expr": "value * 2"}]},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.deduplicate",
        {"subset": ["group"], "keep": "first"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.sort",
        {"by": ["value"], "ascending": [False]},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.reshape",
        {
            "mode": "melt",
            "id_vars": ["user_id"],
            "value_vars": ["value", "other"],
            "var_name": "k",
            "value_name": "v",
        },
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.sample_rows",
        {"mode": "random", "n": 3, "seed": 42},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.redact_pii",
        {"columns": ["text"], "categories": ["email"], "engine": "regex"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "clean.concat",
        {"ignore_index": True},
        lambda: {"frames": [_frame(), _frame()]},
    ),
    Case(
        "clean.merge",
        {"on": ["user_id"], "how": "inner"},
        lambda: {
            "left": _frame()[["user_id", "value"]],
            "right": pd.DataFrame({"user_id": ["u1", "u2", "u3"], "tier": ["x", "y", "z"]}),
        },
    ),
    Case(
        "clean.semi_join",
        {"on": ["user_id"], "mode": "keep"},
        lambda: {
            "frame": _frame(),
            "keys": pd.DataFrame({"user_id": ["u1", "u3"]}),
        },
    ),
    Case(
        "clean.fuzzy_join",
        {"left_on": "user_id", "right_on": "uid", "threshold": 80.0},
        lambda: {
            "left": pd.DataFrame({"user_id": ["alpha", "beta"], "v": [1, 2]}),
            "right": pd.DataFrame({"uid": ["alpah", "beta"], "w": [3, 4]}),
        },
    ),
    Case(
        "stats.chi_square",
        {"row_col": "group", "col_col": "event"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.crosstab",
        {"row_col": "group", "col_col": "event"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.kruskal",
        {"group_col": "group", "value_col": "value"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.mann_whitney",
        {"group_col": "group", "value_col": "value"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.wilcoxon",
        {"col_a": "value", "col_b": "other"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.correct_pvalues",
        {"p_col": "p_value", "method": "bonferroni"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.test_proportions",
        {"group_col": "group", "success_col": "success"},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.power_analysis",
        {"effect_size": 0.5, "power": 0.8, "alpha": 0.05},
        lambda: {},
    ),
    Case(
        "stats.cohort_retention",
        {"user_col": "user_id", "date_col": "when", "period": "M"},
        lambda: {"frame": _frame().assign(when=pd.to_datetime(_frame()["when"]))},
    ),
    Case(
        "stats.funnel",
        {"user_col": "user_id", "event_col": "event", "steps": ["view", "cart", "buy"]},
        lambda: {"frame": _frame()},
    ),
    Case(
        "stats.data_dictionary",
        {"top_n": 3},
        lambda: {"frame": _frame()},
    ),
    Case(
        "ml.reduce_dimensions",
        {"feature_cols": ["value", "other"], "method": "pca", "n_components": 2, "seed": 0},
        lambda: {"frame": _frame()},
    ),
    Case(
        "viz.plot_projection",
        {"x_col": "component_1", "y_col": "component_2", "color_col": "group"},
        lambda: {
            "frame": _frame().assign(
                component_1=[1.0, 2, 3, 4, 5, 6],
                component_2=[6.0, 5, 4, 3, 2, 1],
            )
        },
    ),
    Case(
        "research.assert_data",
        {"expectations": [{"type": "non_null", "column": "value"}]},
        lambda: {"frame": _frame()},
    ),
    Case(
        "research.build_report",
        {"title": "Matrix Report", "author": "ef", "generated_at": "2026-01-01"},
        lambda: {"sections": ["# Heading\n\nbody text"]},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c.node_type for c in CASES])
def test_codegen_matches_execute(case: Case) -> None:
    """ADR-0002: execute() and the emitted codegen fragment produce equivalent OUT ports."""
    defn = get_node_definition(case.node_type)()
    node = defn.instantiate(**case.params)

    executed = defn.execute(node, inputs=case.make_inputs())
    scope = _run_codegen(defn, node, dict(case.make_inputs()))

    assert len(executed) >= 1, f"{case.node_type}: execute() produced no OUT ports"
    for port, value in executed.items():
        assert port in scope, f"{case.node_type}: port {port!r} missing from codegen scope"
        _assert_artifacts_equal(value, scope[port], path=f"{case.node_type}.{port}")


# ---------------------------------------------------------------------------
# File/client cases -- standalone tests, not in CASES (they need tmp_path or repo fixtures)
# ---------------------------------------------------------------------------


def test_load_excel_equivalence(tmp_path: pathlib.Path) -> None:
    pytest.importorskip("openpyxl")
    xlsx = tmp_path / "book.xlsx"
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(xlsx, index=False)

    defn = get_node_definition("data.load_excel")()
    node = defn.instantiate(path=str(xlsx), sheet="0", header_row=0)

    executed = defn.execute(node, inputs={})
    scope = _run_codegen(defn, node, {})

    for port, value in executed.items():
        assert port in scope, f"data.load_excel: port {port!r} missing from codegen scope"
        _assert_artifacts_equal(value, scope[port], path=f"data.load_excel.{port}")


def test_load_documents_equivalence() -> None:
    docs_fixtures = pathlib.Path(__file__).parent / "fixtures" / "documents"

    defn = get_node_definition("data.load_documents")()
    node = defn.instantiate(path=str(docs_fixtures / "sample.md"), chunk_size=50, chunk_overlap=10)

    executed = defn.execute(node, inputs={})
    scope = _run_codegen(defn, node, {})

    for port, value in executed.items():
        assert port in scope, f"data.load_documents: port {port!r} missing from codegen scope"
        _assert_artifacts_equal(value, scope[port], path=f"data.load_documents.{port}")


def test_http_fetch_equivalence(tmp_path: pathlib.Path) -> None:
    url = "https://api.example.com/users"
    write_http_fixture(
        tmp_path,
        HttpRequest(
            url=url,
            method="GET",
            headers=(),
            params=(),
            body=None,
            connection=None,
            timeout_s=None,
        ),
        HttpResponse(status=200, body='{"data":[{"id":1,"name":"a"},{"id":2,"name":"b"}]}'),
    )
    replay = ReplayHttpClient(tmp_path)

    defn = get_node_definition("data.http_fetch")()
    node = defn.instantiate(url=url, json_path="data", pagination="none")

    executed = defn.execute(node, inputs={}, client=replay)
    scope = _run_codegen(defn, node, {"http": replay})

    for port, value in executed.items():
        assert port in scope, f"data.http_fetch: port {port!r} missing from codegen scope"
        _assert_artifacts_equal(value, scope[port], path=f"data.http_fetch.{port}")


def test_load_google_sheet_equivalence(tmp_path: pathlib.Path) -> None:
    request = HttpRequest(
        url=SHEETS_CSV_URL.format(spreadsheet_id="sheet-123"),
        method="GET",
        headers=(),
        params=(("sheet", "Sheet1"),),
        body=None,
        connection=None,
        timeout_s=None,
    )
    write_http_fixture(
        tmp_path,
        request,
        HttpResponse(status=200, body="a,b\n1,x\n2,y\n"),
    )
    replay = ReplayHttpClient(tmp_path)

    defn = get_node_definition("data.load_google_sheet")()
    node = defn.instantiate(spreadsheet_id="sheet-123", sheet="Sheet1", header_row=0)

    executed = defn.execute(node, inputs={}, client=replay)
    scope = _run_codegen(defn, node, {"http": replay})

    for port, value in executed.items():
        assert port in scope, f"data.load_google_sheet: port {port!r} missing from codegen scope"
        _assert_artifacts_equal(value, scope[port], path=f"data.load_google_sheet.{port}")


# ---------------------------------------------------------------------------
# Completeness guard
# ---------------------------------------------------------------------------

EPIC16_NODE_TYPES = frozenset(
    {
        "clean.clean_text",
        "clean.concat",
        "clean.deduplicate",
        "clean.derive_column",
        "clean.fuzzy_join",
        "clean.merge",
        "clean.parse_dates",
        "clean.redact_pii",
        "clean.reshape",
        "clean.sample_rows",
        "clean.semi_join",
        "clean.sort",
        "data.http_fetch",
        "data.load_documents",
        "data.load_excel",
        "data.load_google_sheet",
        "ml.reduce_dimensions",
        "research.assert_data",
        "research.build_report",
        "stats.chi_square",
        "stats.cohort_retention",
        "stats.correct_pvalues",
        "stats.crosstab",
        "stats.data_dictionary",
        "stats.funnel",
        "stats.kruskal",
        "stats.mann_whitney",
        "stats.power_analysis",
        "stats.test_proportions",
        "stats.wilcoxon",
        "viz.plot_projection",
    }
)

_FILE_CLIENT_NODE_TYPES = frozenset(
    {
        "data.load_excel",
        "data.load_documents",
        "data.http_fetch",
        "data.load_google_sheet",
    }
)


def test_every_epic16_node_is_covered() -> None:
    assert len(EPIC16_NODE_TYPES) == 31, (
        f"EPIC16_NODE_TYPES should have exactly 31 members, has {len(EPIC16_NODE_TYPES)}"
    )
    covered = {c.node_type for c in CASES} | _FILE_CLIENT_NODE_TYPES
    missing = EPIC16_NODE_TYPES - covered
    extra = covered - EPIC16_NODE_TYPES
    assert covered == EPIC16_NODE_TYPES, (
        f"Epic 16 nodes missing from the equivalence matrix: {sorted(missing)}; "
        f"unexpected extras: {sorted(extra)}"
    )


def test_every_epic16_node_is_registered() -> None:
    for node_type in EPIC16_NODE_TYPES:
        get_node_definition(node_type)()
