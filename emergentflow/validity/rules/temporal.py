"""
emergentflow.validity.rules.temporal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Temporal-leakage validity rules (Epic 17, Story 4).

Rules that detect experiment-invalid topologies involving time-ordered data:
a windowed feature transform computed across a split boundary, and a random
(shuffled) split on a graph whose rows are temporally ordered. All are static,
pure checks over the graph IR -- no data inspection, no training run.

Registered rules:
    window_crosses_split          -- a windowed feature transform spans a split boundary.
    random_split_on_temporal_graph -- a shuffled train/test split on a temporal graph.
"""

from __future__ import annotations

from emergentflow.ir import Graph

from ..contract import ValidityFinding, ValidityRule
from ..registry import validity_rule
from ..traversal import reaches
from .leakage import SPLIT_NODES

#: Node types that compute windowed/lagged features over an ordered frame. A
#: window computed on data that spans a split boundary sees future/test rows.
WINDOWED_TRANSFORMS: frozenset[str] = frozenset(
    {
        "timeseries.lag_features",
        "timeseries.rolling_aggregate",
        "timeseries.ewma",
        "timeseries.time_weighted_aggregate",
    }
)

#: Node types whose presence signals that the graph's rows are time-ordered.
#: A shuffled random split over such rows breaks temporal holdout.
TEMPORAL_SIGNAL_NODES: frozenset[str] = frozenset(
    {
        "timeseries.lag_features",
        "timeseries.rolling_aggregate",
        "timeseries.ewma",
        "timeseries.time_weighted_aggregate",
        "timeseries.difference",
        "timeseries.seasonal_decompose",
        "timeseries.forecast_arima",
        "timeseries.forecast_ets",
        "recommend.temporal_split",
    }
)


@validity_rule
class WindowCrossesSplit(ValidityRule):
    """A windowed feature transform computed across a split boundary."""

    id = "window_crosses_split"
    severity = "warning"
    confidence = "medium"
    title = "Windowed feature transform crosses the split boundary"
    rationale = (
        "A windowed feature transform (timeseries.lag_features, "
        "timeseries.rolling_aggregate, timeseries.ewma, "
        "timeseries.time_weighted_aggregate) placed upstream of a train/test "
        "split computes each row's window over neighbors that include the rows "
        "the split later holds out. Future/test values therefore leak into the "
        "features. False-positive shape: the window transform feeds a "
        "reporting/EDA branch and never enters the split's frame input, or the "
        "graph splits a non-temporal frame that merely passes through a "
        "window node. Warning: whether it leaks depends on wiring."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type in SPLIT_NODES for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        splits = sorted(n.id for n in graph.nodes.values() if n.type in SPLIT_NODES)
        if not splits:
            return []
        findings: list[ValidityFinding] = []
        for node in sorted(graph.nodes.values(), key=lambda n: n.id):
            if node.type not in WINDOWED_TRANSFORMS:
                continue
            for split_id in splits:
                if reaches(graph, node.id, split_id):
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {node.id!r} ({node.type}) computes a "
                                f"windowed feature across split node {split_id!r}; "
                                "window neighbors include the held-out rows."
                            ),
                            node_id=node.id,
                            related_node_ids=[split_id],
                        )
                    )
        return findings


@validity_rule
class RandomSplitOnTemporalGraph(ValidityRule):
    """A shuffled random split on a temporally ordered graph."""

    id = "random_split_on_temporal_graph"
    severity = "warning"
    confidence = "medium"
    title = "Random train/test split on a temporal graph"
    rationale = (
        "ml.train_test_split shuffles its rows before splitting (it has no "
        "shuffle param; sklearn's default is shuffle=True). When the graph's "
        "rows are time-ordered -- signalled by the presence of timeseries.* "
        "nodes or recommend.temporal_split -- a random split assigns future "
        "rows to train and past rows to test, so the model is trained on "
        'tomorrow to predict yesterday. Set strategy="temporal" on '
        "ml.train_test_split (or use recommend.temporal_split) for temporal "
        "holdout. False-positive shape: timeseries nodes present for EDA while "
        "the model branch splits an unrelated static frame. Warning: the "
        "intended holdout depends on the experiment."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type == "ml.train_test_split" for n in graph.nodes.values())

    def check(self, graph: Graph) -> list[ValidityFinding]:
        findings: list[ValidityFinding] = []
        has_temporal_signal = any(n.type in TEMPORAL_SIGNAL_NODES for n in graph.nodes.values())
        if not has_temporal_signal:
            return []
        for split in sorted(
            (n for n in graph.nodes.values() if n.type == "ml.train_test_split"),
            key=lambda n: n.id,
        ):
            findings.append(
                ValidityFinding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=(
                        f"node {split.id!r} (ml.train_test_split) shuffles rows in "
                        "a graph that contains temporally ordered data; future rows "
                        'can land in train. Set strategy="temporal" on the split '
                        "node (or use recommend.temporal_split) for temporal holdout."
                    ),
                    node_id=split.id,
                    related_node_ids=[],
                )
            )
        return findings
