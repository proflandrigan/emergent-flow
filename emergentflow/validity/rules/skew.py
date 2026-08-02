"""
emergentflow.validity.rules.skew
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Train/serve-skew validity rule (Epic 17, Story 5).

A model served via ``ml.load_model`` -> ``ml.predict`` must receive frames
transformed exactly as the training path transformed them. This rule diffs the
feature-transform chain feeding the scoring ``ml.predict``'s ``frame`` port
against the chain feeding the supervised training node's ``frame`` port, and
flags transforms present in one but absent in the other (or applied in a
different order). Pure, static, and deterministic over the graph IR.
"""

from __future__ import annotations

from collections import Counter

from emergentflow.ir import Graph, Node

from ..contract import ValidityFinding, ValidityRule
from ..registry import validity_rule
from ..traversal import all_edges, reaches, upstream

#: Feature-transform nodes whose ordered application matters for train/serve
#: parity. ``ml.pipeline`` is deliberately excluded: it FITS a model rather
#: than transforming a frame.
TRANSFORM_CHAIN_NODES: frozenset[str] = frozenset(
    {
        "ml.transform",
        "ml.fit_transform",
        "transform.scale_features",
        "transform.encode_categorical",
        "transform.discretize",
        "transform.generate_features",
    }
)

#: Supervised nodes that fit a model on a ``frame`` IN port -- the training path.
TRAINING_NODES: frozenset[str] = frozenset(
    {
        "ml.fit_estimator",
        "ml.train_classifier",
        "ml.train_regressor",
        "ml.train_random_forest",
        "ml.pipeline",
        "ml.cross_validate",
        "ml.grid_search",
    }
)


def _incoming_source(graph: Graph, node_id: str, port_name: str) -> str | None:
    """The node id feeding *node_id*'s IN port named *port_name*, or None.

    Resolves the target port by NAME (not id): edge targets carry the port's
    ``id``, which may differ from its ``name`` in real graphs. Returns the
    source node id of the first matching edge, or None when unconnected.
    """
    node = graph.nodes.get(node_id)
    if node is None:
        return None
    port_ids = {p.id for p in node.ports if p.name == port_name}
    for edge in all_edges(graph):
        if edge.target.node_id == node_id and edge.target.port_id in port_ids:
            return edge.source.node_id
    return None


def _fork_point(graph: Graph, a: str, b: str) -> str | None:
    """The deepest node that is an ancestor of (or equal to) both *a* and *b*.

    The two branches diverge at this node; transforms upstream of it are shared
    (and correct), so the skew diff only counts transforms between the fork and
    each consumer. Endpoint nodes themselves count as ancestors so a fork can be
    a root data source. "Deepest" is the candidate with the most ancestors of
    its own; ties break to the smaller node id. None when the two nodes share no
    ancestor (different data -- not comparable).
    """
    anc_a = upstream(graph, a) | {a}
    anc_b = upstream(graph, b) | {b}
    common = anc_a & anc_b
    if not common:
        return None
    depth = max(len(upstream(graph, c)) for c in common)
    deepest = [c for c in common if len(upstream(graph, c)) == depth]
    return min(deepest)


def _transforms_between(
    graph: Graph,
    fork: str,
    consumer: str,
) -> list[Node]:
    """Transform-chain nodes strictly between *fork* and *consumer*.

    Feature transforms downstream of the fork that reach *consumer* (the node
    consuming the frame, e.g. the fit or predict node). The fork itself is
    excluded so a transform that is the fork is treated as shared, not skew. In
    deterministic node-id order (used only for set comparison).
    """
    return sorted(
        (
            n
            for n in graph.nodes.values()
            if n.type in TRANSFORM_CHAIN_NODES
            and reaches(graph, fork, n.id)
            and reaches(graph, n.id, consumer)
        ),
        key=lambda n: n.id,
    )


def _chain_sequence(graph: Graph, fork: str, consumer: str) -> list[str]:
    """Transform types in application order along the path *fork* -> *consumer*.

    The application order is the topological order of the transform chain: a
    transform precedes every other chain transform it reaches. For the common
    linear chain this is exact; a diamond merge ties deterministically on
    (predecessor count, node id). Equal sequences mean the two paths apply the
    same transforms in the same order, so this is what the skew diff compares
    (an id-sorted type list cannot detect an order difference, and would
    false-positive on equivalent chains whose node ids happen to sort
    differently).
    """
    transforms = _transforms_between(graph, fork, consumer)
    if not transforms:
        return []
    return [
        node.type
        for node in sorted(
            transforms,
            key=lambda node: (
                sum(1 for other in transforms if reaches(graph, other.id, node.id)),
                node.id,
            ),
        )
    ]


@validity_rule
class TrainServeSkew(ValidityRule):
    """The scoring transform chain differs from the training transform chain."""

    id = "train_serve_skew"
    severity = "warning"
    confidence = "medium"
    title = "Train/serve transform chain differs"
    rationale = (
        "A model served through ml.load_model -> ml.predict must receive data "
        "transformed exactly as the data it was trained on. This rule diffs the "
        "feature-transform chain feeding the scoring predict's frame against the "
        "chain feeding the supervised training node's frame (when both derive "
        "from a common source), and flags transforms present in one but not the "
        "other, or applied in a different order. False-positive shape: the "
        "scoring path deliberately serves an un-transformed baseline, or the two "
        "paths consume different data sources (no common fork -> rule stays "
        "silent). Warning: parity intent depends on the experiment."
    )

    @classmethod
    def applies_when(cls, graph: Graph) -> bool:
        return any(n.type == "ml.predict" for n in graph.nodes.values()) and any(
            n.type == "ml.load_model" for n in graph.nodes.values()
        )

    def check(self, graph: Graph) -> list[ValidityFinding]:
        findings: list[ValidityFinding] = []

        scoring: list[Node] = []
        for node in graph.nodes.values():
            if node.type != "ml.predict":
                continue
            model_feeder = _incoming_source(graph, node.id, "model")
            if model_feeder is None:
                continue
            feeder = graph.nodes.get(model_feeder)
            if feeder is not None and feeder.type == "ml.load_model":
                scoring.append(node)
        scoring.sort(key=lambda n: n.id)

        training = sorted(
            (n for n in graph.nodes.values() if n.type in TRAINING_NODES),
            key=lambda n: n.id,
        )

        for predict in scoring:
            predict_frame = _incoming_source(graph, predict.id, "frame") or predict.id
            for train in training:
                train_frame = _incoming_source(graph, train.id, "frame") or train.id
                fork = _fork_point(graph, predict_frame, train_frame)
                if fork is None:
                    continue  # different data sources -- not comparable
                predict_transforms = _transforms_between(graph, fork, predict.id)
                train_transforms = _transforms_between(graph, fork, train.id)
                predict_chain = _chain_sequence(graph, fork, predict.id)
                train_chain = _chain_sequence(graph, fork, train.id)

                if train_chain == predict_chain:
                    continue  # equivalent chain -- same transforms, same order

                train_counts = Counter(t.type for t in train_transforms)
                predict_counts = Counter(t.type for t in predict_transforms)

                if train_counts == predict_counts:
                    # Same transform types in the same counts, applied in a
                    # different order -- the documented third skew shape
                    # (rationale + docs page).
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {predict.id!r} (ml.predict) applies the same "
                                f"transforms as the training path into node {train.id!r} "
                                "but in a different order: scoring "
                                f"{predict_chain!r} vs training {train_chain!r}; the "
                                "served data is transformed differently from the data "
                                "the model was trained on."
                            ),
                            node_id=predict.id,
                            related_node_ids=[train.id],
                        )
                    )
                    continue

                # A transform type applied MORE times on one path than the other is a
                # count difference, not an order difference -- report it as a missing/
                # extra transform so the message is accurate.
                missing = [
                    t for t in train_transforms if train_counts[t.type] > predict_counts[t.type]
                ]
                extra = [
                    t for t in predict_transforms if predict_counts[t.type] > train_counts[t.type]
                ]

                for transform in missing:
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {transform.id!r} ({transform.type}) is applied "
                                f"on the training path into node {train.id!r} but "
                                f"NOT on the scoring path into node {predict.id!r} "
                                "(ml.predict); served data is missing this transform "
                                "the model was trained on."
                            ),
                            node_id=transform.id,
                            related_node_ids=[train.id, predict.id],
                        )
                    )
                for transform in extra:
                    findings.append(
                        ValidityFinding(
                            rule_id=self.id,
                            severity=self.severity,
                            message=(
                                f"node {transform.id!r} ({transform.type}) is applied "
                                f"on the scoring path into node {predict.id!r} "
                                "(ml.predict) but NOT on the training path into node "
                                f"{train.id!r}; the model never saw this transform."
                            ),
                            node_id=transform.id,
                            related_node_ids=[train.id, predict.id],
                        )
                    )
        return findings
