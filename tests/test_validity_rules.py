"""
Epic 17 — per-rule tripping + near-miss fixture tests.

The issue's DoD requires every registered validity rule to have a fixture graph
that trips it AND a near-miss graph that must NOT trip it. ``tests/test_validity_dogfood.py``
only guarantees zero findings on bundled examples (the near-miss side); this file
commits the tripping fixtures and one near-miss each, so a rule that stops firing
(or starts over-firing) fails here.

Each test builds a minimal ``Graph`` from IR models and asserts on the rule ids
returned by ``run_validity_checks`` (or by ``ef.validate`` for the end-to-end
hooks). Graphs are structurally valid (ports exist, edge endpoints are OUT/IN) so
``validate`` itself produces no structural noise on top.
"""

from __future__ import annotations

import emergentflow as ef
from emergentflow.ir import Direction, Edge, Graph, Node, Param, Port, PortRef
from emergentflow.validity import run_validity_checks

IN = Direction.IN
OUT = Direction.OUT
DF = "DataFrame"


def _node(node_id: str, node_type: str, ports=(), params=()) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        ports=[
            Port(id=port_id, name=name, direction=direction, data_type=data_type)
            for port_id, name, direction, data_type in ports
        ],
        params=[Param(name=name, type_token="str", value=value) for name, value in params],
    )


def _edge(edge_id: str, source: str, source_port: str, target: str, target_port: str) -> Edge:
    return Edge(
        id=edge_id,
        source=PortRef(node_id=source, port_id=source_port),
        target=PortRef(node_id=target, port_id=target_port),
    )


def _graph(nodes, edges=()) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in edges})


def _io(node_id: str, prefix: str = "p"):
    """A DataFrame in/out transform node's two ``frame`` ports."""
    return [
        (f"{prefix}-in", "frame", IN, DF),
        (f"{prefix}-out", "frame", OUT, DF),
    ]


def _split(node_id: str, node_type: str = "ml.train_test_split", prefix: str = "sp"):
    """A 1-in-2-out train/test split node."""
    return _node(
        node_id,
        node_type,
        [
            (f"{prefix}-in", "frame", IN, DF),
            (f"{prefix}-train", "train", OUT, DF),
            (f"{prefix}-test", "test", OUT, DF),
        ],
    )


def _rule_ids(graph: Graph) -> set[str]:
    return {f.rule_id for f in run_validity_checks(graph)}


# ---------------------------------------------------------------------------
# fit_before_split (Story 3)
# ---------------------------------------------------------------------------


def test_fit_before_split_trips_when_transform_feeds_split() -> None:
    scale = _node("scale", "transform.scale_features", _io("scale", "s"))
    split = _split("split")
    graph = _graph(
        [scale, split],
        [_edge("e1", "scale", "s-out", "split", "sp-in")],
    )
    assert "fit_before_split" in _rule_ids(graph)


def test_fit_before_split_silent_when_transform_on_train_branch() -> None:
    scale = _node("scale", "transform.scale_features", _io("scale", "s"))
    split = _split("split")
    graph = _graph(
        [scale, split],
        [_edge("e1", "split", "sp-train", "scale", "s-in")],
    )
    assert "fit_before_split" not in _rule_ids(graph)


def test_fit_before_split_silent_when_transform_never_reaches_split() -> None:
    scale = _node("scale", "transform.scale_features", _io("scale", "s"))
    split = _split("split")
    report = _node("report", "test.sink", [("p-in", "in0", IN, DF)])
    graph = _graph(
        [scale, split, report],
        [_edge("e1", "scale", "s-out", "report", "p-in")],
    )
    assert "fit_before_split" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# target_derived_feature (Story 3)
# ---------------------------------------------------------------------------


def _derive(node_id: str, expr: str) -> Node:
    return _node(
        node_id,
        "clean.derive_column",
        _io(node_id, node_id[0]),
        [("columns", [{"name": "derived", "expr": expr}])],
    )


def _supervised(node_id: str = "sup", target: str = "churn") -> Node:
    return _node(
        node_id,
        "ml.fit_estimator",
        [
            ("m-in", "frame", IN, DF),
            ("m-out", "model", OUT, "Model"),
        ],
        [("target", target)],
    )


def test_target_derived_feature_trips_when_expression_references_target() -> None:
    derive = _derive("derive", "churn * 2")
    sup = _supervised()
    graph = _graph([derive, sup], [_edge("e1", "derive", "d-out", "sup", "m-in")])
    assert "target_derived_feature" in _rule_ids(graph)


def test_target_derived_feature_silent_when_expression_omits_target() -> None:
    derive = _derive("derive", "age * 2")
    sup = _supervised()
    graph = _graph([derive, sup], [_edge("e1", "derive", "d-out", "sup", "m-in")])
    assert "target_derived_feature" not in _rule_ids(graph)


def test_target_derived_feature_silent_when_derive_never_reaches_supervised() -> None:
    derive = _derive("derive", "churn * 2")
    sup = _supervised()
    report = _node("report", "test.sink", [("p-in", "in0", IN, DF)])
    graph = _graph(
        [derive, sup, report],
        [_edge("e1", "derive", "d-out", "report", "p-in")],
    )
    assert "target_derived_feature" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# global_aggregate_before_split (Story 3)
# ---------------------------------------------------------------------------


def test_global_aggregate_before_split_trips_upstream_of_split() -> None:
    agg = _node("agg", "stats.group_by_aggregate", _io("agg", "a"))
    split = _split("split")
    graph = _graph([agg, split], [_edge("e1", "agg", "a-out", "split", "sp-in")])
    assert "global_aggregate_before_split" in _rule_ids(graph)


def test_global_aggregate_before_split_silent_after_split() -> None:
    agg = _node("agg", "stats.group_by_aggregate", _io("agg", "a"))
    split = _split("split")
    graph = _graph([agg, split], [_edge("e1", "split", "sp-train", "agg", "a-in")])
    assert "global_aggregate_before_split" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# global_imputation_before_split (Story 3)
# ---------------------------------------------------------------------------


def test_global_imputation_before_split_trips_for_data_derived_strategy() -> None:
    impute = _node(
        "impute",
        "clean.impute_missing",
        _io("impute", "i"),
        [("strategy", "mean")],
    )
    split = _split("split")
    graph = _graph([impute, split], [_edge("e1", "impute", "i-out", "split", "sp-in")])
    assert "global_imputation_before_split" in _rule_ids(graph)


def test_global_imputation_before_split_silent_for_constant_strategy() -> None:
    impute = _node(
        "impute",
        "clean.impute_missing",
        _io("impute", "i"),
        [("strategy", "constant")],
    )
    split = _split("split")
    graph = _graph([impute, split], [_edge("e1", "impute", "i-out", "split", "sp-in")])
    assert "global_imputation_before_split" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# window_crosses_split (Story 4)
# ---------------------------------------------------------------------------


def test_window_crosses_split_trips_upstream_of_split() -> None:
    window = _node("window", "timeseries.lag_features", _io("window", "w"))
    split = _split("split")
    graph = _graph([window, split], [_edge("e1", "window", "w-out", "split", "sp-in")])
    assert "window_crosses_split" in _rule_ids(graph)


def test_window_crosses_split_silent_when_window_feeds_reporting_branch() -> None:
    window = _node("window", "timeseries.ewma", _io("window", "w"))
    split = _split("split")
    report = _node("report", "test.sink", [("p-in", "in0", IN, DF)])
    graph = _graph(
        [window, split, report],
        [_edge("e1", "window", "w-out", "report", "p-in")],
    )
    assert "window_crosses_split" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# random_split_on_temporal_graph (Story 4)
# ---------------------------------------------------------------------------


def test_random_split_on_temporal_graph_trips_when_timeseries_present() -> None:
    split = _split("split")
    window = _node("window", "timeseries.ewma", _io("window", "w"))
    graph = _graph([split, window])
    assert "random_split_on_temporal_graph" in _rule_ids(graph)


def test_random_split_on_temporal_graph_silent_without_temporal_signal() -> None:
    split = _split("split")
    graph = _graph([split])
    assert "random_split_on_temporal_graph" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# train_serve_skew (Story 5)
# ---------------------------------------------------------------------------


def _scoring_path(nodes, edges) -> Graph:
    return _graph(nodes, edges)


def test_train_serve_skew_trips_when_scoring_misses_a_transform() -> None:
    src = _node("src", "test.source", [("src-out", "out", OUT, DF)])
    scale = _node("scale", "transform.scale_features", _io("scale", "st"))
    fit = _node(
        "fit",
        "ml.fit_estimator",
        [("f-in", "frame", IN, DF), ("f-out", "model", OUT, "Model")],
    )
    lm = _node("lm", "ml.load_model", [("lm-out", "model", OUT, "Model")], [("path", "m.joblib")])
    pred = _node(
        "pred",
        "ml.predict",
        [
            ("p-model", "model", IN, "Model"),
            ("p-frame", "frame", IN, DF),
            ("p-out", "predictions", OUT, "Predictions"),
        ],
    )
    graph = _scoring_path(
        [src, scale, fit, lm, pred],
        [
            _edge("e1", "src", "src-out", "scale", "st-in"),
            _edge("e2", "scale", "st-out", "fit", "f-in"),
            _edge("e3", "src", "src-out", "pred", "p-frame"),
            _edge("e4", "lm", "lm-out", "pred", "p-model"),
        ],
    )
    assert "train_serve_skew" in _rule_ids(graph)


def test_train_serve_skew_silent_when_chains_are_equivalent() -> None:
    src = _node("src", "test.source", [("src-out", "out", OUT, DF)])
    train_scale = _node("train_scale", "transform.scale_features", _io("train_scale", "t"))
    serve_scale = _node("serve_scale", "transform.scale_features", _io("serve_scale", "s"))
    fit = _node(
        "fit",
        "ml.fit_estimator",
        [("f-in", "frame", IN, DF), ("f-out", "model", OUT, "Model")],
    )
    lm = _node("lm", "ml.load_model", [("lm-out", "model", OUT, "Model")], [("path", "m.joblib")])
    pred = _node(
        "pred",
        "ml.predict",
        [
            ("p-model", "model", IN, "Model"),
            ("p-frame", "frame", IN, DF),
            ("p-out", "predictions", OUT, "Predictions"),
        ],
    )
    graph = _scoring_path(
        [src, train_scale, serve_scale, fit, lm, pred],
        [
            _edge("e1", "src", "src-out", "train_scale", "t-in"),
            _edge("e2", "train_scale", "t-out", "fit", "f-in"),
            _edge("e3", "src", "src-out", "serve_scale", "s-in"),
            _edge("e4", "serve_scale", "s-out", "pred", "p-frame"),
            _edge("e5", "lm", "lm-out", "pred", "p-model"),
        ],
    )
    assert "train_serve_skew" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# ranking_metrics_on_random_split (Story 6)
# ---------------------------------------------------------------------------


def _recommend_evaluate() -> Node:
    return _node(
        "evaluate",
        "recommend.evaluate",
        [
            ("rv-rec", "recommender", IN, "Recommender"),
            ("rv-ti", "test_interactions", IN, "InteractionMatrix"),
            ("rv-out", "result", OUT, "EvalResult"),
        ],
    )


def test_ranking_metrics_on_random_split_trips_for_random_holdout() -> None:
    evaluate = _recommend_evaluate()
    split = _split("split", prefix="rs")
    graph = _graph(
        [split, evaluate],
        [_edge("e1", "split", "rs-test", "evaluate", "rv-ti")],
    )
    assert "ranking_metrics_on_random_split" in _rule_ids(graph)


def test_ranking_metrics_on_random_split_silent_for_temporal_holdout() -> None:
    evaluate = _recommend_evaluate()
    split = _split("split", node_type="recommend.temporal_split", prefix="ts")
    graph = _graph(
        [split, evaluate],
        [_edge("e1", "split", "ts-test", "evaluate", "rv-ti")],
    )
    assert "ranking_metrics_on_random_split" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# task_mismatched_scoring (Story 6)
# ---------------------------------------------------------------------------


def _cross_validate(node_id: str, estimator: str, scoring: str) -> Node:
    return _node(
        node_id,
        "ml.cross_validate",
        [
            ("cv-in", "frame", IN, DF),
            ("cv-out", "result", OUT, DF),
        ],
        [("estimator", estimator), ("scoring", scoring)],
    )


def test_task_mismatched_scoring_trips_for_cross_task_metric() -> None:
    cv = _cross_validate("cv", "RandomForestClassifier", "r2")
    assert "task_mismatched_scoring" in _rule_ids(_graph([cv]))


def test_task_mismatched_scoring_silent_for_matching_task_metric() -> None:
    cv = _cross_validate("cv", "RandomForestClassifier", "accuracy")
    assert "task_mismatched_scoring" not in _rule_ids(_graph([cv]))


# ---------------------------------------------------------------------------
# eda_peek_on_test (Story 6)
# ---------------------------------------------------------------------------


def _eda(node_id: str) -> Node:
    return _node(node_id, "stats.auto_eda", [(f"{node_id}-in", "frame", IN, DF)])


def test_eda_peek_on_test_trips_on_test_branch() -> None:
    split = _split("split")
    eda = _eda("eda")
    graph = _graph([split, eda], [_edge("e1", "split", "sp-test", "eda", "eda-in")])
    assert "eda_peek_on_test" in _rule_ids(graph)


def test_eda_peek_on_test_silent_on_train_branch() -> None:
    split = _split("split")
    eda = _eda("eda")
    graph = _graph([split, eda], [_edge("e1", "split", "sp-train", "eda", "eda-in")])
    assert "eda_peek_on_test" not in _rule_ids(graph)


# ---------------------------------------------------------------------------
# End-to-end hooks: ef.validate mapping + suppression
# ---------------------------------------------------------------------------


def _leaky_split_graph() -> Graph:
    """scale_features -> train_test_split, with the scale input wired so the
    graph is structurally clean and the only diagnostic is the validity finding."""
    src = _node("src", "test.source", [("src-out", "out", OUT, DF)])
    scale = _node("scale", "transform.scale_features", _io("scale", "s"))
    split = _split("split")
    return _graph(
        [src, scale, split],
        [
            _edge("e1", "src", "src-out", "scale", "s-in"),
            _edge("e2", "scale", "s-out", "split", "sp-in"),
        ],
    )


def test_validate_returns_rule_id_and_related_node_ids() -> None:
    graph = _leaky_split_graph()

    result = ef.validate(graph)
    validity = [d for d in result.diagnostics if d.rule_id is not None]
    assert len(validity) == 1
    finding = validity[0]
    assert finding.rule_id == "fit_before_split"
    assert finding.severity == "error"
    assert finding.node_id == "scale"
    assert finding.related_node_ids == ["split"]


def test_apply_suppressions_filters_validity_findings_only() -> None:
    graph = _leaky_split_graph()

    result = ef.validate(graph)
    filtered = ef.apply_suppressions(result, [["fit_before_split", "scale"]])
    assert not [d for d in filtered.diagnostics if d.rule_id is not None]
    assert not filtered.diagnostics

    # non-validity diagnostics (no rule_id) are never suppressed
    unfiltered = ef.apply_suppressions(result, [["fit_before_split", "other-node"]])
    assert len(unfiltered.diagnostics) == len(result.diagnostics)


# ---------------------------------------------------------------------------
# Regression tests for confirmed bug-hunt findings (PR #147 review)
# ---------------------------------------------------------------------------


def test_global_imputation_before_split_trips_for_default_strategy() -> None:
    """An impute node with no strategy param executes with the data-derived
    default (\"mean\"), so it must still trip -- not just an explicit mean."""
    impute = _node("impute", "clean.impute_missing", _io("impute", "i"))
    split = _split("split")
    graph = _graph([impute, split], [_edge("e1", "impute", "i-out", "split", "sp-in")])
    assert "global_imputation_before_split" in _rule_ids(graph)


def test_target_derived_feature_silent_when_features_param_excludes_derived() -> None:
    """The derived target-referencing column never reaches the model when the
    supervised node's features param explicitly excludes it -- no leak, no
    finding (and never an error that would block compile/execute)."""
    derive = _derive("derive", "churn * 2")
    sup = _node(
        "sup",
        "ml.fit_estimator",
        [("m-in", "frame", IN, DF), ("m-out", "model", OUT, "Model")],
        [("target", "churn"), ("features", ["age"])],
    )
    graph = _graph([derive, sup], [_edge("e1", "derive", "d-out", "sup", "m-in")])
    assert "target_derived_feature" not in _rule_ids(graph)


def test_target_derived_feature_trips_for_cross_validate_and_grid_search() -> None:
    """ml.cross_validate / ml.grid_search fit supervised estimators on a target;
    a target-referencing derived feature feeding them is the same leak as for
    fit_estimator."""
    derive = _derive("derive", "churn * 2")
    cv = _node(
        "cv",
        "ml.cross_validate",
        [("cv-in", "frame", IN, DF), ("cv-out", "result", OUT, DF)],
        [("estimator", "RandomForestClassifier"), ("target", "churn")],
    )
    graph = _graph([derive, cv], [_edge("e1", "derive", "d-out", "cv", "cv-in")])
    assert "target_derived_feature" in _rule_ids(graph)

    gs = _node(
        "gs",
        "ml.grid_search",
        [("gs-in", "frame", IN, DF), ("gs-out", "result", OUT, DF)],
        [("estimator", "RandomForestClassifier"), ("target", "churn")],
    )
    graph = _graph([derive, gs], [_edge("e1", "derive", "d-out", "gs", "gs-in")])
    assert "target_derived_feature" in _rule_ids(graph)


def test_target_derived_feature_is_warning_not_blocking() -> None:
    """target_derived_feature is a topological approximation, so it must warn,
    never error -- an error would hard-block compile/execute on a graph where
    the derived column is dropped before the model."""
    derive = _derive("derive", "churn * 2")
    sup = _supervised()
    graph = _graph([derive, sup], [_edge("e1", "derive", "d-out", "sup", "m-in")])
    findings = [f for f in run_validity_checks(graph) if f.rule_id == "target_derived_feature"]
    assert findings
    assert all(f.severity == "warning" for f in findings)


def _derive_named(node_id: str, name: str, expr: str) -> Node:
    return _node(
        node_id,
        "clean.derive_column",
        _io(node_id, node_id[0]),
        [("columns", [{"name": name, "expr": expr}])],
    )


def test_target_derived_feature_catches_two_hop_leak() -> None:
    """A two-hop leak (target -> intermediate -> feature) must be caught by
    column lineage even though no single derive expression names the target.

    ``churn`` -> ``two_churn`` (derive *2) -> ``feature`` (derive *3) -> model.
    The old topological approximation only checked whether a derive *expression*
    references the target directly, so it was silent here; column lineage walks
    the whole chain and sees ``churn`` in ``feature``'s provenance (Epic 18,
    Story 7).
    """
    derive1 = _derive_named("derive1", "two_churn", "churn * 2")
    derive2 = _derive_named("derive2", "feature", "two_churn * 3")
    sup = _supervised()
    graph = _graph(
        [derive1, derive2, sup],
        [
            _edge("e1", "derive1", "d-out", "derive2", "d-in"),
            _edge("e2", "derive2", "d-out", "sup", "m-in"),
        ],
    )
    assert "target_derived_feature" in _rule_ids(graph)


def test_target_derived_feature_silent_for_label_only_use() -> None:
    """A legitimate use of the target as the label only (not as a derived feature)
    must not be flagged -- e.g. the target column is never referenced by any
    derive feeding the model."""
    derive = _derive("derive", "age * 2")
    sup = _supervised()
    graph = _graph([derive, sup], [_edge("e1", "derive", "d-out", "sup", "m-in")])
    assert "target_derived_feature" not in _rule_ids(graph)


def test_fit_before_split_silent_for_generate_features() -> None:
    """PolynomialFeatures learns no data-derived parameters, so generating
    features before a split is not a target leak and must not trip the error
    rule."""
    gen = _node("gen", "transform.generate_features", _io("gen", "g"))
    split = _split("split")
    graph = _graph([gen, split], [_edge("e1", "gen", "g-out", "split", "sp-in")])
    assert "fit_before_split" not in _rule_ids(graph)


def test_train_serve_skew_reports_count_mismatch_not_order() -> None:
    """Applying a transform twice on train and once on serve is a count
    difference -- it must not be reported as \"same transforms, different
    order\"."""
    src = _node("src", "test.source", [("src-out", "out", OUT, DF)])
    sa = _node("sa", "transform.scale_features", _io("sa", "a"))
    sb = _node("sb", "transform.scale_features", _io("sb", "b"))
    sc = _node("sc", "transform.scale_features", _io("sc", "c"))
    fit = _node(
        "fit",
        "ml.fit_estimator",
        [("f-in", "frame", IN, DF), ("f-out", "model", OUT, "Model")],
    )
    lm = _node("lm", "ml.load_model", [("lm-out", "model", OUT, "Model")], [("path", "m.joblib")])
    pred = _node(
        "pred",
        "ml.predict",
        [
            ("p-model", "model", IN, "Model"),
            ("p-frame", "frame", IN, DF),
            ("p-out", "predictions", OUT, "Predictions"),
        ],
    )
    graph = _graph(
        [src, sa, sb, sc, fit, lm, pred],
        [
            _edge("e1", "src", "src-out", "sa", "a-in"),
            _edge("e2", "sa", "a-out", "sb", "b-in"),
            _edge("e3", "sb", "b-out", "fit", "f-in"),
            _edge("e4", "src", "src-out", "sc", "c-in"),
            _edge("e5", "sc", "c-out", "pred", "p-frame"),
            _edge("e6", "lm", "lm-out", "pred", "p-model"),
        ],
    )
    skew = [f for f in run_validity_checks(graph) if f.rule_id == "train_serve_skew"]
    assert skew, "skew must still be detected"
    assert all("different order" not in f.message for f in skew)


def test_train_serve_skew_emits_one_finding_per_count_delta() -> None:
    """A transform applied twice on train but once on serve is a single extra
    application (delta = 1), so the rule must report exactly one finding — not
    one per train node of that type (which would double-count the discrepancy)."""
    src = _node("src", "test.source", [("src-out", "out", OUT, DF)])
    sa = _node("sa", "transform.scale_features", _io("sa", "a"))
    sb = _node("sb", "transform.scale_features", _io("sb", "b"))
    sc = _node("sc", "transform.scale_features", _io("sc", "c"))
    fit = _node(
        "fit",
        "ml.fit_estimator",
        [("f-in", "frame", IN, DF), ("f-out", "model", OUT, "Model")],
    )
    lm = _node("lm", "ml.load_model", [("lm-out", "model", OUT, "Model")], [("path", "m.joblib")])
    pred = _node(
        "pred",
        "ml.predict",
        [
            ("p-model", "model", IN, "Model"),
            ("p-frame", "frame", IN, DF),
            ("p-out", "predictions", OUT, "Predictions"),
        ],
    )
    graph = _graph(
        [src, sa, sb, sc, fit, lm, pred],
        [
            _edge("e1", "src", "src-out", "sa", "a-in"),
            _edge("e2", "sa", "a-out", "sb", "b-in"),
            _edge("e3", "sb", "b-out", "fit", "f-in"),
            _edge("e4", "src", "src-out", "sc", "c-in"),
            _edge("e5", "sc", "c-out", "pred", "p-frame"),
            _edge("e6", "lm", "lm-out", "pred", "p-model"),
        ],
    )
    skew = [f for f in run_validity_checks(graph) if f.rule_id == "train_serve_skew"]
    assert len(skew) == 1, f"expected one finding for a single count delta, got {len(skew)}"
