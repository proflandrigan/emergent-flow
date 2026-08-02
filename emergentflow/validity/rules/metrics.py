"""
emergentflow.validity.rules.metrics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Metric-appropriateness validity rules (Epic 17, Story 6).

Rules that detect experiment-invalid uses of evaluation metrics: ranking
metrics measured against a random (not temporal) holdout, a
classification/regression scoring string applied to the wrong task's estimator,
and EDA computed on the held-out test frame (peeking). All are static, pure
checks over the graph IR -- no data inspection, no training run.

Registered rules:
    ranking_metrics_on_random_split -- recommend.evaluate against a random split.
    task_mismatched_scoring         -- scoring string mismatches the estimator task.
    eda_peek_on_test                -- auto-EDA/profile computed on the test frame.
"""

from __future__ import annotations

from emergentflow.ir import Direction, Graph

from ..contract import ValidityFinding, ValidityRule
from ..registry import validity_rule
from ..traversal import all_edges, downstream, upstream
from .leakage import SPLIT_NODES
from .skew import _incoming_source

#: sklearn scoring strings that apply to classification problems.
CLASSIFICATION_SCORING: frozenset[str] = frozenset(
    {
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "f1",
        "f1_macro",
        "f1_micro",
        "f1_weighted",
        "precision_macro",
        "precision_micro",
        "recall_macro",
        "recall_micro",
        "roc_auc",
        "average_precision",
        "neg_log_loss",
        "top_k_accuracy",
    }
)

#: sklearn scoring strings that apply to regression problems.
REGRESSION_SCORING: frozenset[str] = frozenset(
    {
        "r2",
        "neg_mean_squared_error",
        "neg_root_mean_squared_error",
        "neg_mean_absolute_error",
        "neg_median_absolute_error",
        "neg_mean_squared_log_error",
        "explained_variance",
        "max_error",
        "neg_mean_poisson_deviance",
        "neg_mean_gamma_deviance",
    }
)

#: EDA/peek nodes whose frame input must never be the test branch.
EDA_PEEK_NODES: frozenset[str] = frozenset({"stats.auto_eda", "stats.eda_profile"})


def _test_branch_nodes(graph: Graph) -> set[str]:
    """Every node reachable from any split's ``test`` OUT port.

    The held-out branch of every split (ml.train_test_split test, or
    recommend.temporal_split test). Used to detect EDA peeking at the test data.
    """
    result: set[str] = set()
    for split in graph.nodes.values():
        if split.type not in SPLIT_NODES:
            continue
        test_port_ids = {
            p.id for p in split.ports if p.name == "test" and p.direction == Direction.OUT
        }
        if not test_port_ids:
            continue
        for edge in all_edges(graph):
            if edge.source.node_id == split.id and edge.source.port_id in test_port_ids:
                seed = edge.target.node_id
                result.add(seed)
                result |= downstream(graph, seed)
    return result


@validity_rule
class RankingMetricsOnRandomSplit(ValidityRule):
    """Ranking metrics measured against a random rather than temporal holdout."""

    id = "ranking_metrics_on_random_split"
    severity = "warning"
    confidence = "medium"
    title = "Ranking metrics measured against a random split"
    rationale = (
        "recommend.evaluate computes ranking metrics (precision@k, recall@k, "
        "NDCG@k, MAP@k) against its test_interactions input. When that input is "
        "held out by a random ml.train_test_split rather than a temporal "
        "recommend.temporal_split, the metric silently overstates quality on "
        "time-ordered interaction data. False-positive shape: the graph "
        "legitimately evaluates a non-temporal baseline, or the test "
        "interactions are random-held-out by design. Warning: the intended "
        "holdout depends on the experiment."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type == "recommend.evaluate" for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        findings: list[ValidityFinding] = []
        for evaluate in sorted(
            (n for n in graph.nodes.values() if n.type == "recommend.evaluate"),
            key=lambda n: n.id,
        ):
            test_feeder = _incoming_source(graph, evaluate.id, "test_interactions")
            if test_feeder is None:
                continue
            upstream_ids = upstream(graph, test_feeder) | {test_feeder}
            random_splits = sorted(
                n.id
                for n in graph.nodes.values()
                if n.type == "ml.train_test_split" and n.id in upstream_ids
            )
            temporal_splits = sorted(
                n.id
                for n in graph.nodes.values()
                if n.type == "recommend.temporal_split" and n.id in upstream_ids
            )
            if not random_splits or temporal_splits:
                continue
            for split_id in random_splits:
                findings.append(
                    ValidityFinding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=(
                            f"node {evaluate.id!r} (recommend.evaluate) measures "
                            f"ranking metrics against test data from random split "
                            f"{split_id!r} (ml.train_test_split); use "
                            "recommend.temporal_split for a temporal holdout."
                        ),
                        node_id=evaluate.id,
                        related_node_ids=[split_id],
                    )
                )
        return findings


@validity_rule
class TaskMismatchedScoring(ValidityRule):
    """A classification/regression scoring string applied to the wrong task."""

    id = "task_mismatched_scoring"
    severity = "warning"
    confidence = "medium"
    title = "Scoring metric mismatches the estimator's task"
    rationale = (
        "ml.cross_validate's scoring string must match the estimator's task: a "
        "classification metric (accuracy, precision, recall, f1, roc_auc, ...) on "
        "a regression estimator, or a regression metric (r2, mae, mse, ...) on a "
        "classifier, reports a meaningless number. The task is read from the "
        "estimator catalog (emergentflow.ml.registry). False-positive shape: an "
        "unknown estimator key or an unlisted custom scoring string skips the "
        "rule (it only fires on known catalog tasks vs. known scoring families)."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type == "ml.cross_validate" for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        findings: list[ValidityFinding] = []
        for node in sorted(
            (n for n in graph.nodes.values() if n.type == "ml.cross_validate"),
            key=lambda n: n.id,
        ):
            params = {p.name: p.value for p in node.params}
            estimator = params.get("estimator")
            scoring = params.get("scoring")
            if not isinstance(estimator, str) or not isinstance(scoring, str) or not scoring:
                continue
            try:
                from emergentflow.ml.registry import get_estimator_spec

                task = get_estimator_spec(estimator).task
            except Exception:
                continue  # unknown estimator or registry unavailable -- skip
            if task == "classification" and scoring in REGRESSION_SCORING:
                findings.append(
                    ValidityFinding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=(
                            f"node {node.id!r} (ml.cross_validate) uses regression "
                            f"scoring {scoring!r} on classification estimator "
                            f"{estimator!r}; the score is meaningless."
                        ),
                        node_id=node.id,
                    )
                )
            elif task == "regression" and scoring in CLASSIFICATION_SCORING:
                findings.append(
                    ValidityFinding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=(
                            f"node {node.id!r} (ml.cross_validate) uses "
                            f"classification scoring {scoring!r} on regression "
                            f"estimator {estimator!r}; the score is meaningless."
                        ),
                        node_id=node.id,
                    )
                )
        return findings


@validity_rule
class EdaPeekOnTest(ValidityRule):
    """EDA/profile computed on the held-out test frame."""

    id = "eda_peek_on_test"
    severity = "warning"
    confidence = "medium"
    title = "Exploratory analysis computed on the test frame"
    rationale = (
        "stats.auto_eda / stats.eda_profile summarise the distribution of their "
        "input frame. When that frame is the test branch of a split, the analyst "
        "sees the held-out distribution before evaluation -- a form of peeking "
        "that can bias model selection. False-positive shape: the EDA is "
        "explicitly for reporting after the experiment, or the frame is the "
        "train/full frame (rule stays silent). Warning: intent depends on when "
        "the analysis runs."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type in EDA_PEEK_NODES for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        findings: list[ValidityFinding] = []
        test_branch = _test_branch_nodes(graph)
        if not test_branch:
            return []
        for node in sorted(
            (n for n in graph.nodes.values() if n.type in EDA_PEEK_NODES),
            key=lambda n: n.id,
        ):
            if node.id not in test_branch:
                continue
            frame_feeder = _incoming_source(graph, node.id, "frame")
            findings.append(
                ValidityFinding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=(
                        f"node {node.id!r} ({node.type}) computes exploratory "
                        f"analysis on frame from node {frame_feeder!r}, which "
                        "is on the held-out test branch of a split; the analyst "
                        "is peeking at test data."
                    ),
                    node_id=node.id,
                    related_node_ids=[frame_feeder] if frame_feeder else [],
                )
            )
        return findings
