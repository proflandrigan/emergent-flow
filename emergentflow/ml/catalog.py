"""
emergentflow.ml.catalog
~~~~~~~~~~~~~~~~~~~~~~~~
Seed estimator catalog for Emergent Flow (Epic 8, Story 2).

Importing this module registers a small, curated set of estimator allow-list entries
into the registry (``emergentflow.ml.registry``) as an import-time side effect,
mirroring how importing ``emergentflow.types.catalog`` registers type tokens.

This is a SEED set spanning the three fixed adapter archetypes (ADR 0016 subsection 3)
so the adapter (``ef.ml.fit_estimator`` / ``ef.ml.apply_estimator``) and its tests have
representative estimators to exercise. It is deliberately NOT the full curated
scikit-learn catalog -- that is generated and widened across Epic 8 Stories 4-6 (a
reviewed allow-list change per estimator family), not enumerated here.
"""

from __future__ import annotations

from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from emergentflow.ml.registry import EstimatorSpec, KwargSpec, register_estimator

register_estimator(
    EstimatorSpec(
        key="LogisticRegression",
        import_path="sklearn.linear_model.LogisticRegression",
        sklearn_class=LogisticRegression,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "max_iter": KwargSpec(default=1000, help="Maximum solver iterations."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
            "C": KwargSpec(default=1.0, help="Inverse of regularization strength."),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="StandardScaler",
        import_path="sklearn.preprocessing.StandardScaler",
        sklearn_class=StandardScaler,
        archetype="fit_transform",
        accepted_kwargs={
            "with_mean": KwargSpec(default=True, help="Center the data before scaling."),
            "with_std": KwargSpec(default=True, help="Scale the data to unit variance."),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="KMeans",
        import_path="sklearn.cluster.KMeans",
        sklearn_class=KMeans,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_clusters": KwargSpec(default=8, help="Number of clusters to form."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
            "n_init": KwargSpec(default=10, help="Number of centroid-seed runs."),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="GaussianMixture",
        import_path="sklearn.mixture.GaussianMixture",
        sklearn_class=GaussianMixture,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_components": KwargSpec(default=1, help="Number of mixture components."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
    )
)
