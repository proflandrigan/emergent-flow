"""
emergentflow.causal.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Method allow-list catalog for the causal-inference family (issue #164 Gap 1).

Registers the curated effect-estimation and sensitivity methods as data so the node
surface stays thin (mirroring ``emergentflow.stats.catalog`` / ``emergentflow.ml.catalog``):
a node reads ``keys_for_archetype("estimate_effect")`` for its ``method`` dropdown instead
of hardcoding keys. Importing this module for its side effect registers the catalog.
"""

from __future__ import annotations

from emergentflow.causal.registry import EstimatorSpec, register_estimator

register_estimator(
    EstimatorSpec(
        key="ipw",
        archetype="estimate_effect",
        fn=float,
        description="Inverse-probability weighting (Hajek estimator).",
    )
)
register_estimator(
    EstimatorSpec(
        key="aipw",
        archetype="estimate_effect",
        fn=float,
        description="Doubly robust augmentation; consistent if the propensity OR outcome "
        "model is correct.",
    )
)
register_estimator(
    EstimatorSpec(
        key="matching",
        archetype="estimate_effect",
        fn=float,
        description="1:1 nearest-neighbour propensity matching on the ATT.",
    )
)
register_estimator(
    EstimatorSpec(
        key="regression_adjust",
        archetype="estimate_effect",
        fn=float,
        description="Regression adjustment: OLS of outcome on treatment + covariates.",
    )
)
register_estimator(
    EstimatorSpec(
        key="did",
        archetype="did",
        fn=float,
        description="Two-way fixed-effects difference-in-differences.",
    )
)
