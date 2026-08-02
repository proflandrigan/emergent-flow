"""
emergentflow.validity.rules.leakage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Leakage validity rules (Epic 17, Story 3).

Rules that detect the target-leakage family of experiment-invalid topologies: a
transform or aggregate that fits parameters on data which includes the rows the
split later holds out. All are static, pure checks over the graph IR -- no data
inspection, no training run.

Registered rules:
    fit_before_split              -- fitting transform upstream of a split.
    target_derived_feature        -- a derived feature computed from the target.
    global_aggregate_before_split -- group-by aggregate on the full frame before a split.
    global_imputation_before_split-- data-derived imputation on the full frame before a split.
"""

from __future__ import annotations

import ast
from typing import Any

from emergentflow.ir import Graph, Node

from ..contract import ValidityFinding, ValidityRule
from ..registry import validity_rule
from ..traversal import reaches

#: Node types that split data into train/test.
SPLIT_NODES: frozenset[str] = frozenset({"ml.train_test_split", "recommend.temporal_split"})

#: Node types that FIT parameters on the data passing through them. A fitting
#: transform upstream of a split sees the held-out rows. ``ml.transform`` is
#: deliberately excluded: it applies a fitted transformer, which is legitimate.
FITTING_TRANSFORMS: frozenset[str] = frozenset(
    {
        "ml.fit_transform",
        "ml.pipeline",
        "transform.scale_features",
        "transform.encode_categorical",
        "transform.discretize",
        "transform.generate_features",
    }
)

#: Supervised nodes that declare a ``target`` column name.
SUPERVISED_TARGET_NODES: frozenset[str] = frozenset(
    {
        "ml.fit_estimator",
        "ml.train_classifier",
        "ml.train_regressor",
        "ml.train_random_forest",
        "ml.pipeline",
    }
)

#: ``clean.impute_missing`` strategies that fit global statistics on the frame.
#: ``"constant"`` (and similar) do not depend on the data and are not leaks.
DATA_DERIVED_IMPUTE_STRATEGIES: frozenset[str] = frozenset({"mean", "median", "most_frequent"})


def _node_params(node: Node) -> dict[str, Any]:
    """Read a node's params as a name -> value map."""
    return {p.name: p.value for p in node.params}


def _split_ids(graph: Graph) -> list[str]:
    """Every split node id, ascending (deterministic order)."""
    return sorted(n.id for n in graph.nodes.values() if n.type in SPLIT_NODES)


def _referenced_columns(expr: str) -> set[str]:
    """Statically extract the column names *expr* references.

    Mirrors the AST walk in ``emergentflow.clean.expressions``: every bare
    ``ast.Name`` is a column reference. Returns an empty set when the expression
    is syntactically invalid (a malformed derive spec is a separate validation
    concern, not this rule's).
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _derive_expression_strings(node: Node) -> list[str]:
    """Every expression string in a ``clean.derive_column`` node's columns spec.

    Handles both spec shapes: ``{"expr": str}`` computed columns and
    ``{"when": [{"if": str, ...}, ...]}`` case-when columns.
    """
    specs = _node_params(node).get("columns") or []
    if not isinstance(specs, list):
        return []
    exprs: list[str] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        expr = spec.get("expr")
        if isinstance(expr, str):
            exprs.append(expr)
        when = spec.get("when")
        if isinstance(when, list):
            for branch in when:
                if isinstance(branch, dict) and isinstance(branch.get("if"), str):
                    exprs.append(branch["if"])
    return exprs


def _target_column(node: Node) -> str | None:
    """The ``target`` param value of a supervised node, or None when unset."""
    value = _node_params(node).get("target")
    if isinstance(value, str) and value:
        return value
    return None


@validity_rule
class FitBeforeSplit(ValidityRule):
    """A fitting transform upstream of a split fits on the held-out rows."""

    id = "fit_before_split"
    severity = "error"
    confidence = "high"
    title = "Transform fitted before the train/test split"
    rationale = (
        "A fitting transform (ml.fit_transform, ml.pipeline, transform.*) placed "
        "upstream of a train/test split fits its parameters on the full frame, "
        "including the rows the split later holds out. The fitted parameters "
        "therefore encode test information -- a target leak. False-positive "
        "shape: a fitting transform on a reporting/EDA branch that never feeds "
        "the split's frame input. Decidable without inference, so error."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type in SPLIT_NODES for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        splits = _split_ids(graph)
        if not splits:
            return []
        findings: list[ValidityFinding] = []
        for node in sorted(graph.nodes.values(), key=lambda n: n.id):
            if node.type not in FITTING_TRANSFORMS:
                continue
            for split_id in splits:
                if reaches(graph, node.id, split_id):
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {node.id!r} ({node.type}) fits a transform on "
                                f"data upstream of split node {split_id!r}; its "
                                "parameters see the held-out rows."
                            ),
                            node_id=node.id,
                            related_node_ids=[split_id],
                        )
                    )
        return findings


@validity_rule
class TargetDerivedFeature(ValidityRule):
    """A derived feature computed from the target column."""

    id = "target_derived_feature"
    severity = "error"
    confidence = "high"
    title = "Derived feature references the target column"
    rationale = (
        "clean.derive_column computes a feature from an expression that references "
        "the model's target column. The feature is a function of the answer, so a "
        "model trained on it leaks the target. False-positive shape: the derived "
        "column is computed for reporting and never feeds the supervised node, or "
        "the expression coincidentally shares a name with an unrelated column. "
        "Decidable without inference, so error."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type == "clean.derive_column" for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        supervised: list[tuple[str, Node, str]] = []
        for node in graph.nodes.values():
            if node.type not in SUPERVISED_TARGET_NODES:
                continue
            target = _target_column(node)
            if target is not None:
                supervised.append((target, node, node.id))
        # Stable order (node id ascending) so findings are golden-testable regardless
        # of dict insertion order -- same discipline as the sorted derive-node loop.
        supervised.sort(key=lambda entry: entry[2])
        if not supervised:
            return []
        findings: list[ValidityFinding] = []
        for node in sorted(graph.nodes.values(), key=lambda n: n.id):
            if node.type != "clean.derive_column":
                continue
            referenced: set[str] = set()
            for expr in _derive_expression_strings(node):
                referenced |= _referenced_columns(expr)
            if not referenced:
                continue
            for target, _, supervised_id in supervised:
                if target not in referenced:
                    continue
                if not reaches(graph, node.id, supervised_id):
                    continue
                findings.append(
                    ValidityFinding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=(
                            f"node {node.id!r} (clean.derive_column) derives a "
                            f"feature from target column {target!r}, which is the "
                            f"target of supervised node {supervised_id!r}; the "
                            "derived feature leaks the answer."
                        ),
                        node_id=node.id,
                        related_node_ids=[supervised_id],
                    )
                )
        return findings


@validity_rule
class GlobalAggregateBeforeSplit(ValidityRule):
    """A group-by aggregate computed on the full frame before a split."""

    id = "global_aggregate_before_split"
    severity = "warning"
    confidence = "medium"
    title = "Group-by aggregate computed before the train/test split"
    rationale = (
        "stats.group_by_aggregate computes aggregate statistics over the whole "
        "input frame. When it runs upstream of a train/test split and its output "
        "feeds the feature path, those statistics are computed on the held-out "
        "rows as well -- a leak. False-positive shape: the aggregate feeds a "
        "reporting/EDA branch, or is computed for a summary that never enters the "
        "model's features. Warning: whether it leaks depends on downstream wiring."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type in SPLIT_NODES for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        splits = _split_ids(graph)
        if not splits:
            return []
        findings: list[ValidityFinding] = []
        for node in sorted(graph.nodes.values(), key=lambda n: n.id):
            if node.type != "stats.group_by_aggregate":
                continue
            for split_id in splits:
                if reaches(graph, node.id, split_id):
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {node.id!r} (stats.group_by_aggregate) "
                                f"computes global statistics upstream of split "
                                f"node {split_id!r}; those statistics include the "
                                "held-out rows."
                            ),
                            node_id=node.id,
                            related_node_ids=[split_id],
                        )
                    )
        return findings


@validity_rule
class GlobalImputationBeforeSplit(ValidityRule):
    """A data-derived imputation computed on the full frame before a split."""

    id = "global_imputation_before_split"
    severity = "warning"
    confidence = "medium"
    title = "Data-derived imputation computed before the train/test split"
    rationale = (
        "clean.impute_missing with a data-derived strategy (mean/median/"
        "most_frequent) fits global statistics on the full frame. When it runs "
        "upstream of a train/test split, the imputation values are computed on "
        "the held-out rows as well -- a leak. False-positive shape: a constant "
        "strategy (which does not depend on the data) or imputation that only "
        "runs on the train branch. Warning: whether it leaks depends on wiring."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type in SPLIT_NODES for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        splits = _split_ids(graph)
        if not splits:
            return []
        findings: list[ValidityFinding] = []
        for node in sorted(graph.nodes.values(), key=lambda n: n.id):
            if node.type != "clean.impute_missing":
                continue
            strategy = _node_params(node).get("strategy")
            if strategy not in DATA_DERIVED_IMPUTE_STRATEGIES:
                continue
            for split_id in splits:
                if reaches(graph, node.id, split_id):
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {node.id!r} (clean.impute_missing) imputes "
                                f"with data-derived strategy {strategy!r} upstream "
                                f"of split node {split_id!r}; the imputation "
                                "statistics include the held-out rows."
                            ),
                            node_id=node.id,
                            related_node_ids=[split_id],
                        )
                    )
        return findings
