"""
Golden + equivalence tests for the Epic 8 Story 5 fit_transform estimator catalog.

Two things this file proves, per Story 5's own checklist and the Story 9 harness pattern:

1. Golden-code quality: for a representative estimator per family, the whole-graph
   ``compile_to_code`` output (LoadSample -> FitTransform) is syntactically valid Python and
   passes ``ruff check`` (mirrors ``tests/test_ml_supervised_catalog.py``'s idiom).
2. ADR-0002 equivalence at scale: for EVERY estimator registered with archetype="fit_transform"
   (the entire transformer allow-list, computed dynamically so this test grows automatically as
   the allow-list widens), ``execute()`` and running the code ``codegen()`` emits produce the
   same fitted-transformer metadata and the same transformed values.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml.errors import InvalidEstimatorParamsError
from emergentflow.ml.registry import get_estimator_spec, known_estimator_keys
from emergentflow.nodes.examples import FitTransform, LoadSample, Transform


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _fit_transform_archetype_keys() -> list[str]:
    return sorted(
        k for k in known_estimator_keys() if get_estimator_spec(k).archetype == "fit_transform"
    )


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


IRIS_FEATURES = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]


def _fit_transform_df() -> pd.DataFrame:
    """30 rows: 3 non-negative numeric features (x1/x2/x3), 1 low-cardinality categorical
    column (cat), 1 binary target column (y) -- sized/shaped to satisfy every curated
    fit_transform-archetype estimator's constraints (NMF needs non-negative input;
    OneHotEncoder/OrdinalEncoder need a categorical column; SelectKBest needs a target; TSNE
    needs perplexity < n_samples).
    """
    n = 30
    x1 = [float(i % 10) + 1.0 for i in range(n)]
    x2 = [float((i * 2) % 7) + 1.0 for i in range(n)]
    x3 = [float((i * 3) % 5) + 1.0 for i in range(n)]
    cat = [["a", "b", "c"][i % 3] for i in range(n)]
    y = [i % 2 for i in range(n)]
    return pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "cat": cat, "y": y})


_NUMERIC_FEATURES = ["x1", "x2", "x3"]

#: Per-key overrides for the estimators whose fit constraints differ from the generic
#: "just fit the three numeric columns" case: OneHotEncoder/OrdinalEncoder need a categorical
#: column instead; SelectKBest is a supervised feature selector and needs a target (plus a
#: smaller `k` to avoid a harmless-but-noisy "k > n_features" warning); TSNE's default
#: perplexity=30 (curated for realistic datasets) exceeds this test's 30 rows, so it is
#: overridden down for this synthetic sample only -- the catalog's curated default is untouched.
_KEY_OVERRIDES: dict[str, dict] = {
    "OneHotEncoder": {"features": ["cat"]},
    "OrdinalEncoder": {"features": ["cat"]},
    "SelectKBest": {"features": _NUMERIC_FEATURES, "target": "y", "params": {"k": 2}},
    "TSNE": {"features": _NUMERIC_FEATURES, "params": {"perplexity": 5}},
}


def _args_for(estimator_key: str) -> dict:
    overrides = _KEY_OVERRIDES.get(estimator_key, {})
    return {
        "features": overrides.get("features", _NUMERIC_FEATURES),
        "target": overrides.get("target"),
        "params": overrides.get("params", {}),
    }


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative estimator per family.
# ---------------------------------------------------------------------------

_REPRESENTATIVE_ESTIMATORS = [
    "StandardScaler",  # preprocessing (seed)
    "PCA",  # decomposition
    "Isomap",  # manifold
    "SelectKBest",  # feature selection (supervised)
]


def _build_fit_transform_graph(estimator_key: str) -> Graph:
    target = "target" if estimator_key == "SelectKBest" else None
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    fit = FitTransform().instantiate(
        estimator=estimator_key, target=target, features=IRIS_FEATURES, label="Fit Transform"
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    return Graph(nodes={load.id: load, fit.id: fit}, edges={edge.id: edge})


@pytest.mark.parametrize("estimator_key", _REPRESENTATIVE_ESTIMATORS)
def test_fit_transform_catalog_codegen_is_parseable(estimator_key: str) -> None:
    """Generated code for a representative fit_transform estimator parses (importable)."""
    code = compile_to_code(_build_fit_transform_graph(estimator_key))
    ast.parse(code)  # raises SyntaxError on failure


@pytest.mark.parametrize("estimator_key", _REPRESENTATIVE_ESTIMATORS)
def test_fit_transform_catalog_codegen_is_ruff_clean(estimator_key: str) -> None:
    """Generated code for a representative fit_transform estimator passes ``ruff check``."""
    code = compile_to_code(_build_fit_transform_graph(estimator_key))
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence matrix: every "fit_transform"-archetype estimator in the allow-list.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estimator_key", _fit_transform_archetype_keys())
def test_fit_transform_equivalence_matrix(estimator_key: str) -> None:
    """ADR 0002: execute == running the emitted code, for every fit_transform estimator."""
    args = _args_for(estimator_key)
    df = _fit_transform_df()

    fit_defn = FitTransform()
    fit_node = fit_defn.instantiate(
        estimator=estimator_key,
        target=args["target"],
        features=args["features"],
        params=args["params"],
    )
    executed = fit_defn.execute(fit_node, inputs={"frame": df.copy()})
    executed_transformer, executed_result = executed["transformer"], executed["result"]

    scope = _run_codegen(fit_defn, fit_node, {"frame": df.copy()})
    codegen_transformer, codegen_result = scope["transformer"], scope["result"]

    assert executed_transformer.estimator_type == codegen_transformer.estimator_type
    assert executed_transformer.feature_names == codegen_transformer.feature_names

    component_cols = [c for c in executed_result.columns if c.startswith("component_")]
    assert component_cols  # every fit_transform estimator adds at least one component column
    for col in component_cols:
        assert executed_result[col].tolist() == pytest.approx(codegen_result[col].tolist())


# ---------------------------------------------------------------------------
# 3. TSNE has no out-of-sample transform: ml.transform must reject it, not silently misbehave.
# ---------------------------------------------------------------------------


def test_transform_node_rejects_labels_only_style_transformer_on_new_data() -> None:
    """A transformer with no ``.transform()`` (e.g. TSNE) must raise via ``ml.transform``,
    not silently replay stale fit-time output when applied to a DIFFERENT frame."""
    df = _fit_transform_df()
    fit_defn = FitTransform()
    fit_node = fit_defn.instantiate(
        estimator="TSNE", features=_NUMERIC_FEATURES, params={"perplexity": 5}
    )
    fitted = fit_defn.execute(fit_node, inputs={"frame": df})
    transformer = fitted["transformer"]

    new_df = df.copy()
    tr_defn = Transform()
    tr_node = tr_defn.instantiate(op="transform")
    with pytest.raises(ValueError, match="does not support transform"):
        tr_defn.execute(tr_node, inputs={"transformer": transformer, "frame": new_df})


# ---------------------------------------------------------------------------
# 4. Tuple-typed curated defaults (e.g. MinMaxScaler.feature_range) must accept a JSON-native
#    list override, not just the curated tuple default itself.
# ---------------------------------------------------------------------------


def test_tuple_typed_param_accepts_list_override() -> None:
    """A caller-supplied override for a tuple-typed kwarg default arrives as a JSON-native list
    (there is no tuple type in JSON) -- ``ml.fit_transform`` must coerce it back to a tuple
    before constructing the estimator, not hand sklearn's strict param validation a list."""
    df = _fit_transform_df()
    fit_defn = FitTransform()
    fit_node = fit_defn.instantiate(
        estimator="MinMaxScaler",
        features=_NUMERIC_FEATURES,
        params={"feature_range": [0, 2]},
    )
    result = fit_defn.execute(fit_node, inputs={"frame": df})["result"]
    component_cols = [c for c in result.columns if c.startswith("component_")]
    for col in component_cols:
        assert result[col].min() == pytest.approx(0.0)
        assert result[col].max() == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 5. SelectKBest.score_func: the curated default (f_classif) must not silently degenerate to
#    NaN scores for a continuous (regression) target -- score_func must be overridable.
# ---------------------------------------------------------------------------


def _regression_df() -> pd.DataFrame:
    """30 rows where y is a noisy linear function of x1/x2 -- a genuinely continuous target
    that f_classif (SelectKBest's curated default, an ANOVA F-test for CATEGORICAL targets)
    scores as all-NaN, since it treats each distinct float value of y as its own class."""
    n = 30
    x1 = [float(i) for i in range(n)]
    x2 = [float(n - i) for i in range(n)]
    x3 = [float(i % 4) for i in range(n)]
    y = [3.0 * a - 2.0 * b + 0.01 * i for i, (a, b) in enumerate(zip(x1, x2, strict=True))]
    return pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "y": y})


def test_select_k_best_score_func_override_avoids_nan_scores_for_continuous_target() -> None:
    """Overriding score_func to 'f_regression' for a continuous target yields real,
    non-NaN scores -- the curated default ('f_classif') would silently produce all-NaN."""
    df = _regression_df()
    fit_defn = FitTransform()
    node = fit_defn.instantiate(
        estimator="SelectKBest",
        target="y",
        features=["x1", "x2", "x3"],
        params={"k": 2, "score_func": "f_regression"},
    )
    fitted = fit_defn.execute(node, inputs={"frame": df})
    scores = fitted["transformer"].transformer.scores_
    assert not any(pd.isna(s) for s in scores)


def test_select_k_best_score_func_rejects_unknown_choice() -> None:
    """An unrecognized score_func string is rejected with a clear, curated-choices error
    instead of failing deep inside sklearn with a cryptic 'not callable' error."""
    df = _regression_df()
    fit_defn = FitTransform()
    node = fit_defn.instantiate(
        estimator="SelectKBest",
        target="y",
        features=["x1", "x2", "x3"],
        params={"score_func": "bogus"},
    )
    with pytest.raises(InvalidEstimatorParamsError, match="not a valid 'score_func'"):
        fit_defn.execute(node, inputs={"frame": df})
