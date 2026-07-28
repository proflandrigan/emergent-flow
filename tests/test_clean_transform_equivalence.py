"""
Parametrized ADR-0002 equivalence matrix for Epic 16 Story group B's nine ``clean.*`` nodes.

Each of ``Reshape``, ``DeriveColumn``, ``Concat``, ``Deduplicate``, ``Sort``, ``CleanText``,
``ParseDates``, ``SampleRows``, and ``FuzzyJoin`` already has one or two
``@pytest.mark.equivalence`` tests in its own per-node test file
(``tests/test_clean_text_dates_nodes.py``, ``tests/test_clean_combine_nodes.py``, and friends).
This module adds the **matrix**: one parametrized harness that sweeps many *parameter
combinations* per node, so the ADR-0002 invariant -- ``execute(ir)`` must equal running the
code ``compile_to_code``/``codegen`` emits for the same ``ir`` -- is gated across the whole new
surface rather than at one point per node.

The harness pattern (mirrored from the two files above):

    def _run_codegen(definition, node, scope):
        frag = definition.preview(node)
        exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
        return scope

``NodeDefinition.preview`` builds a standalone ``CodegenContext`` that binds every port name to
itself (IN and OUT alike, regardless of cardinality). So:

- a 1-in node emits ``frame = ef.clean.<op>(frame, ...)`` -- seed ``scope`` with ``{"frame": df}``;
- ``Concat``'s MANY port emits ``frame = ef.clean.concat(frames, ...)`` -- seed
  ``{"frames": [df1, df2]}``;
- ``FuzzyJoin`` emits ``frame = ef.clean.fuzzy_join(left, right, ...)`` -- seed
  ``{"left": ..., "right": ...}``.

The OUT port name is both the key of the ``execute`` return dict and the variable the emitted
code assigns to, so the two are compared by looking up the same name in both.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.nodes.examples import (
    CleanText,
    Concat,
    Deduplicate,
    DeriveColumn,
    FuzzyJoin,
    ParseDates,
    Reshape,
    SampleRows,
    Sort,
)

_HAS_RAPIDFUZZ = importlib.util.find_spec("rapidfuzz") is not None
_needs_fuzzy = pytest.mark.skipif(
    not _HAS_RAPIDFUZZ, reason="requires the optional [fuzzy] extra (rapidfuzz)"
)


# ---------------------------------------------------------------------------
# Fixtures -- module-level factory functions, so each case gets a fresh frame
# ---------------------------------------------------------------------------


def _long() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "metric": ["clicks", "views", "clicks", "views"],
            "amount": [3, 10, 5, 12],
        }
    )


def _long_dupes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-02"],
            "metric": ["clicks", "clicks", "views", "clicks"],
            "amount": [3, 4, 10, 5],
        }
    )


def _wide() -> pd.DataFrame:
    return pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "clicks": [3, 5], "views": [10, 12]})


def _money() -> pd.DataFrame:
    return pd.DataFrame({"revenue": [1500.0, 500.0, 50.0, 0.0], "cost": [500.0, 200.0, 20.0, 0.0]})


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": list(range(12)),
            "grp": ["a"] * 6 + ["b"] * 6,
            "value": [float(i) for i in range(12)],
        }
    )


def _dupe_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {"id": [1, 1, 2, 2, 3], "grp": ["a", "a", "b", "b", "c"], "n": [1, 2, 3, 4, 5]}
    )


def _na_rows() -> pd.DataFrame:
    return pd.DataFrame({"k": ["b", None, "a", "c"], "n": [1, 2, 3, 4]})


def _text() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["  Alice  ", "BOB", "carol dee"],
            "code": ["id-123", "id-4", "id-56"],
            "tags": ["a,b", "c", "d,e,f"],
        }
    )


def _dates() -> pd.DataFrame:
    return pd.DataFrame({"when": ["2024-01-15", "2024-06-30", "2023-12-01"], "n": [1, 2, 3]})


def _bad_dates() -> pd.DataFrame:
    return pd.DataFrame({"when": ["2024-01-15", "not-a-date", "2023-12-01"], "n": [1, 2, 3]})


def _fuzzy_left() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Apple Inc", "Microsft Corp", "Zzzz Ltd"], "lid": [1, 2, 3]})


def _fuzzy_right() -> pd.DataFrame:
    return pd.DataFrame({"company": ["Apple Inc.", "Microsoft Corp"], "rid": [10, 20]})


# ---------------------------------------------------------------------------
# The case record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    id: str
    node_cls: type
    params: dict[str, Any]
    inputs: dict[str, Callable[[], Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------

CASES: list[Case] = [
    # -- Reshape (4) ---------------------------------------------------
    Case(
        id="reshape-pivot",
        node_cls=Reshape,
        params={"mode": "pivot", "index": ["date"], "columns": ["metric"], "values": ["amount"]},
        inputs={"frame": _long},
    ),
    Case(
        id="reshape-pivot-aggfunc",
        node_cls=Reshape,
        params={
            "mode": "pivot",
            "index": ["date"],
            "columns": ["metric"],
            "values": ["amount"],
            "aggfunc": "sum",
        },
        inputs={"frame": _long_dupes},
    ),
    Case(
        id="reshape-melt",
        node_cls=Reshape,
        params={"mode": "melt", "id_vars": ["date"], "value_vars": ["clicks", "views"]},
        inputs={"frame": _wide},
    ),
    Case(
        id="reshape-melt-custom-names",
        node_cls=Reshape,
        params={
            "mode": "melt",
            "id_vars": ["date"],
            "value_vars": ["clicks", "views"],
            "var_name": "metric",
            "value_name": "amount",
        },
        inputs={"frame": _wide},
    ),
    # -- DeriveColumn (4) ------------------------------------------------
    Case(
        id="derive-arithmetic",
        node_cls=DeriveColumn,
        params={"columns": [{"name": "margin", "expr": "revenue - cost"}]},
        inputs={"frame": _money},
    ),
    Case(
        id="derive-ordered-chain",
        node_cls=DeriveColumn,
        params={
            "columns": [
                {"name": "margin", "expr": "revenue - cost"},
                {"name": "margin_pct", "expr": "margin / revenue"},
            ]
        },
        inputs={"frame": _money},
    ),
    Case(
        id="derive-case-when",
        node_cls=DeriveColumn,
        params={
            "columns": [
                {
                    "name": "tier",
                    "when": [
                        {"if": "revenue > 1000", "then": "high"},
                        {"if": "revenue > 100", "then": "mid"},
                        {"if": "revenue > 0", "then": "low"},
                    ],
                    "else": "zero",
                }
            ]
        },
        inputs={"frame": _money},
    ),
    Case(
        id="derive-case-when-no-else",
        node_cls=DeriveColumn,
        params={
            "columns": [
                {
                    "name": "tier",
                    "when": [
                        {"if": "revenue > 1000", "then": "high"},
                        {"if": "revenue > 100", "then": "mid"},
                        {"if": "revenue > 0", "then": "low"},
                    ],
                }
            ]
        },
        inputs={"frame": _money},
    ),
    # -- Concat (2) --------------------------------------------------------
    Case(
        id="concat-plain",
        node_cls=Concat,
        params={},
        inputs={"frames": lambda: [_wide(), _wide()]},
    ),
    Case(
        id="concat-source-and-keys",
        node_cls=Concat,
        params={"source_column": "src", "keys": ["l", "r"]},
        inputs={"frames": lambda: [_wide(), _wide()]},
    ),
    # -- Deduplicate (3) -----------------------------------------------------
    Case(
        id="dedup-all-columns",
        node_cls=Deduplicate,
        params={},
        inputs={"frame": _dupe_rows},
    ),
    Case(
        id="dedup-subset-keep-last",
        node_cls=Deduplicate,
        params={"subset": ["id"], "keep": "last"},
        inputs={"frame": _dupe_rows},
    ),
    Case(
        id="dedup-keep-none",
        node_cls=Deduplicate,
        params={"subset": ["id"], "keep": "none"},
        inputs={"frame": _dupe_rows},
    ),
    # -- Sort (3) -----------------------------------------------------------
    Case(
        id="sort-single-desc",
        node_cls=Sort,
        params={"by": ["n"], "ascending": [False]},
        inputs={"frame": _dupe_rows},
    ),
    Case(
        id="sort-multi-mixed",
        node_cls=Sort,
        params={"by": ["grp", "n"], "ascending": [True, False]},
        inputs={"frame": _dupe_rows},
    ),
    Case(
        id="sort-na-first",
        node_cls=Sort,
        params={"by": ["k"], "na_position": "first"},
        inputs={"frame": _na_rows},
    ),
    # -- CleanText (4) --------------------------------------------------------
    Case(
        id="clean-text-trim-lower",
        node_cls=CleanText,
        params={"columns": ["name"], "operations": [{"op": "trim"}, {"op": "lower"}]},
        inputs={"frame": _text},
    ),
    Case(
        id="clean-text-regex-replace",
        node_cls=CleanText,
        params={
            "columns": ["name"],
            "operations": [{"op": "replace", "pattern": r"\s+", "replacement": "_"}],
        },
        inputs={"frame": _text},
    ),
    Case(
        id="clean-text-extract",
        node_cls=CleanText,
        params={
            "columns": ["code"],
            "operations": [{"op": "extract", "pattern": r"id-(\d+)"}],
        },
        inputs={"frame": _text},
    ),
    Case(
        id="clean-text-split-suffix",
        node_cls=CleanText,
        params={
            "columns": ["tags"],
            "operations": [{"op": "split", "sep": ","}],
            "suffix": "_list",
        },
        inputs={"frame": _text},
    ),
    # -- ParseDates (4) ---------------------------------------------------
    Case(
        id="parse-dates-basic",
        node_cls=ParseDates,
        params={"columns": ["when"]},
        inputs={"frame": _dates},
    ),
    Case(
        id="parse-dates-components",
        node_cls=ParseDates,
        params={"columns": ["when"], "components": ["year", "month", "quarter"]},
        inputs={"frame": _dates},
    ),
    Case(
        id="parse-dates-explicit-format",
        node_cls=ParseDates,
        params={"columns": ["when"], "format": "%Y-%m-%d"},
        inputs={"frame": _dates},
    ),
    Case(
        id="parse-dates-coerce",
        node_cls=ParseDates,
        params={"columns": ["when"], "errors": "coerce"},
        inputs={"frame": _bad_dates},
    ),
    # -- SampleRows (4) -- every case sets an explicit seed ------------------
    Case(
        id="sample-random-n",
        node_cls=SampleRows,
        params={"mode": "random", "n": 4, "seed": 7},
        inputs={"frame": _rows},
    ),
    Case(
        id="sample-random-frac",
        node_cls=SampleRows,
        params={"mode": "random", "frac": 0.5, "seed": 7},
        inputs={"frame": _rows},
    ),
    Case(
        id="sample-stratified",
        node_cls=SampleRows,
        params={"mode": "stratified", "by": ["grp"], "n": 2, "seed": 7},
        inputs={"frame": _rows},
    ),
    Case(
        id="sample-top-n",
        node_cls=SampleRows,
        params={"mode": "top_n", "n": 3},
        inputs={"frame": _rows},
    ),
    # -- FuzzyJoin (3) ------------------------------------------------------
    Case(
        id="fuzzy-inner",
        node_cls=FuzzyJoin,
        params={"left_on": "name", "right_on": "company", "threshold": 80},
        inputs={"left": _fuzzy_left, "right": _fuzzy_right},
    ),
    Case(
        id="fuzzy-left",
        node_cls=FuzzyJoin,
        params={"left_on": "name", "right_on": "company", "threshold": 80, "how": "left"},
        inputs={"left": _fuzzy_left, "right": _fuzzy_right},
    ),
    Case(
        id="fuzzy-limit-2",
        node_cls=FuzzyJoin,
        params={"left_on": "name", "right_on": "company", "threshold": 80, "limit": 2},
        inputs={"left": _fuzzy_left, "right": _fuzzy_right},
    ),
]

_PARAMS = [
    pytest.param(c, marks=_needs_fuzzy) if c.node_cls is FuzzyJoin else pytest.param(c)
    for c in CASES
]
_IDS = [c.id for c in CASES]


# ---------------------------------------------------------------------------
# 1. The equivalence gate itself
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize("case", _PARAMS, ids=_IDS)
def test_clean_transform_equivalence(case: Case) -> None:
    """execute(node) must equal running the code that codegen(node) emits (ADR 0002)."""
    defn = case.node_cls()
    node = defn.instantiate(**case.params)

    executed = defn.execute(node, inputs={k: f() for k, f in case.inputs.items()})
    scope: dict[str, Any] = {k: f() for k, f in case.inputs.items()}
    exec(defn.preview(node).render(), scope)  # noqa: S102 -- test-only, our own emitted code

    assert executed, "execute returned no outputs"
    for port, value in executed.items():
        pd.testing.assert_frame_equal(value, scope[port])


# ---------------------------------------------------------------------------
# 2. Inspectable-contract sweep
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _PARAMS, ids=_IDS)
def test_clean_transform_output_is_inspectable(case: Case) -> None:
    defn = case.node_cls()
    node = defn.instantiate(**case.params)
    executed = defn.execute(node, inputs={k: f() for k, f in case.inputs.items()})
    for value in executed.values():
        assert is_inspectable(value)


# ---------------------------------------------------------------------------
# 3. Determinism sweep -- two independent executions must agree. This is what
# pins the captured seed on SampleRows and guards against any accidental
# reliance on a global RNG or on dict/group iteration order.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _PARAMS, ids=_IDS)
def test_clean_transform_is_deterministic(case: Case) -> None:
    defn = case.node_cls()
    node = defn.instantiate(**case.params)
    first = defn.execute(node, inputs={k: f() for k, f in case.inputs.items()})
    second = defn.execute(node, inputs={k: f() for k, f in case.inputs.items()})
    for port, value in first.items():
        pd.testing.assert_frame_equal(value, second[port])


# ---------------------------------------------------------------------------
# 4. Non-mutation sweep -- no node may mutate its input frames.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _PARAMS, ids=_IDS)
def test_clean_transform_does_not_mutate_inputs(case: Case) -> None:
    defn = case.node_cls()
    node = defn.instantiate(**case.params)
    inputs = {k: f() for k, f in case.inputs.items()}
    snapshots = {
        k: ([df.copy() for df in v] if isinstance(v, list) else v.copy()) for k, v in inputs.items()
    }
    defn.execute(node, inputs=inputs)
    for key, original in snapshots.items():
        current = inputs[key]
        if isinstance(original, list):
            for before, after in zip(original, current, strict=True):
                pd.testing.assert_frame_equal(before, after)
        else:
            pd.testing.assert_frame_equal(original, current)


# ---------------------------------------------------------------------------
# 5. Coverage guard -- the matrix must cover every node this story group added.
# ---------------------------------------------------------------------------

_STORY_GROUP_B_NODE_TYPES = {
    "clean.reshape",
    "clean.derive_column",
    "clean.concat",
    "clean.deduplicate",
    "clean.sort",
    "clean.clean_text",
    "clean.parse_dates",
    "clean.sample_rows",
    "clean.fuzzy_join",
}


def test_matrix_covers_every_story_group_b_node() -> None:
    """A new clean-family transform node must land in this matrix, not slip past the gate."""
    covered = {case.node_cls.type for case in CASES}
    assert covered == _STORY_GROUP_B_NODE_TYPES
