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
from sklearn.discriminant_analysis import (
    LinearDiscriminantAnalysis,
    QuadraticDiscriminantAnalysis,
)
from sklearn.ensemble import (
    AdaBoostClassifier,
    AdaBoostRegressor,
    BaggingClassifier,
    BaggingRegressor,
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import (
    ElasticNet,
    Lasso,
    LogisticRegression,
    Ridge,
    SGDClassifier,
    SGDRegressor,
)
from sklearn.mixture import GaussianMixture
from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR, LinearSVC
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from emergentflow.ml.registry import EstimatorSpec, KwargSpec, register_estimator
from emergentflow.ml.summaries import (
    summarize_classifier,
    summarize_clustering,
    summarize_preprocessing,
    summarize_regressor,
)

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
        summary_builder=summarize_classifier,
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
        summary_builder=summarize_preprocessing,
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
        summary_builder=summarize_clustering,
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
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="Ridge",
        import_path="sklearn.linear_model.Ridge",
        sklearn_class=Ridge,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "alpha": KwargSpec(default=1.0, help="Regularization strength."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="Lasso",
        import_path="sklearn.linear_model.Lasso",
        sklearn_class=Lasso,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "alpha": KwargSpec(default=1.0, help="Regularization strength."),
            "max_iter": KwargSpec(default=1000, help="Maximum solver iterations."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="ElasticNet",
        import_path="sklearn.linear_model.ElasticNet",
        sklearn_class=ElasticNet,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "alpha": KwargSpec(default=1.0, help="Regularization strength."),
            "l1_ratio": KwargSpec(default=0.5, help="Mixing ratio between L1 and L2 penalty."),
            "max_iter": KwargSpec(default=1000, help="Maximum solver iterations."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="SGDClassifier",
        import_path="sklearn.linear_model.SGDClassifier",
        sklearn_class=SGDClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "loss": KwargSpec(default="hinge", help="Loss function to optimize."),
            "alpha": KwargSpec(default=0.0001, help="Regularization strength."),
            "max_iter": KwargSpec(default=1000, help="Maximum passes over the training data."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="SGDRegressor",
        import_path="sklearn.linear_model.SGDRegressor",
        sklearn_class=SGDRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "loss": KwargSpec(default="squared_error", help="Loss function to optimize."),
            "alpha": KwargSpec(default=0.0001, help="Regularization strength."),
            "max_iter": KwargSpec(default=1000, help="Maximum passes over the training data."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="DecisionTreeClassifier",
        import_path="sklearn.tree.DecisionTreeClassifier",
        sklearn_class=DecisionTreeClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "max_depth": KwargSpec(default=None, help="Maximum tree depth (None = unlimited)."),
            "min_samples_split": KwargSpec(default=2, help="Minimum samples to split a node."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="DecisionTreeRegressor",
        import_path="sklearn.tree.DecisionTreeRegressor",
        sklearn_class=DecisionTreeRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "max_depth": KwargSpec(default=None, help="Maximum tree depth (None = unlimited)."),
            "min_samples_split": KwargSpec(default=2, help="Minimum samples to split a node."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="RandomForestClassifier",
        import_path="sklearn.ensemble.RandomForestClassifier",
        sklearn_class=RandomForestClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of trees in the forest."),
            "max_depth": KwargSpec(default=None, help="Maximum tree depth (None = unlimited)."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="RandomForestRegressor",
        import_path="sklearn.ensemble.RandomForestRegressor",
        sklearn_class=RandomForestRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of trees in the forest."),
            "max_depth": KwargSpec(default=None, help="Maximum tree depth (None = unlimited)."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="ExtraTreesClassifier",
        import_path="sklearn.ensemble.ExtraTreesClassifier",
        sklearn_class=ExtraTreesClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of trees in the forest."),
            "max_depth": KwargSpec(default=None, help="Maximum tree depth (None = unlimited)."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="ExtraTreesRegressor",
        import_path="sklearn.ensemble.ExtraTreesRegressor",
        sklearn_class=ExtraTreesRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of trees in the forest."),
            "max_depth": KwargSpec(default=None, help="Maximum tree depth (None = unlimited)."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="GradientBoostingClassifier",
        import_path="sklearn.ensemble.GradientBoostingClassifier",
        sklearn_class=GradientBoostingClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of boosting stages."),
            "learning_rate": KwargSpec(default=0.1, help="Shrinks each tree's contribution."),
            "max_depth": KwargSpec(default=3, help="Maximum depth of each tree."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="GradientBoostingRegressor",
        import_path="sklearn.ensemble.GradientBoostingRegressor",
        sklearn_class=GradientBoostingRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of boosting stages."),
            "learning_rate": KwargSpec(default=0.1, help="Shrinks each tree's contribution."),
            "max_depth": KwargSpec(default=3, help="Maximum depth of each tree."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="HistGradientBoostingClassifier",
        import_path="sklearn.ensemble.HistGradientBoostingClassifier",
        sklearn_class=HistGradientBoostingClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "max_iter": KwargSpec(default=100, help="Maximum number of boosting iterations."),
            "learning_rate": KwargSpec(default=0.1, help="Shrinks each tree's contribution."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="HistGradientBoostingRegressor",
        import_path="sklearn.ensemble.HistGradientBoostingRegressor",
        sklearn_class=HistGradientBoostingRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "max_iter": KwargSpec(default=100, help="Maximum number of boosting iterations."),
            "learning_rate": KwargSpec(default=0.1, help="Shrinks each tree's contribution."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="AdaBoostClassifier",
        import_path="sklearn.ensemble.AdaBoostClassifier",
        sklearn_class=AdaBoostClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=50, help="Maximum number of estimators."),
            "learning_rate": KwargSpec(default=1.0, help="Shrinks each estimator's contribution."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="AdaBoostRegressor",
        import_path="sklearn.ensemble.AdaBoostRegressor",
        sklearn_class=AdaBoostRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "n_estimators": KwargSpec(default=50, help="Maximum number of estimators."),
            "learning_rate": KwargSpec(default=1.0, help="Shrinks each estimator's contribution."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="BaggingClassifier",
        import_path="sklearn.ensemble.BaggingClassifier",
        sklearn_class=BaggingClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "n_estimators": KwargSpec(
                default=10, help="Number of base estimators in the ensemble."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="BaggingRegressor",
        import_path="sklearn.ensemble.BaggingRegressor",
        sklearn_class=BaggingRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "n_estimators": KwargSpec(
                default=10, help="Number of base estimators in the ensemble."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="KNeighborsClassifier",
        import_path="sklearn.neighbors.KNeighborsClassifier",
        sklearn_class=KNeighborsClassifier,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "n_neighbors": KwargSpec(default=5, help="Number of neighbors to use."),
            "weights": KwargSpec(default="uniform", help="Weight function ('uniform'/'distance')."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="KNeighborsRegressor",
        import_path="sklearn.neighbors.KNeighborsRegressor",
        sklearn_class=KNeighborsRegressor,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "n_neighbors": KwargSpec(default=5, help="Number of neighbors to use."),
            "weights": KwargSpec(default="uniform", help="Weight function ('uniform'/'distance')."),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="GaussianNB",
        import_path="sklearn.naive_bayes.GaussianNB",
        sklearn_class=GaussianNB,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "var_smoothing": KwargSpec(
                default=1e-9,
                help="Portion of the largest variance added for calculation stability.",
            ),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="MultinomialNB",
        import_path="sklearn.naive_bayes.MultinomialNB",
        sklearn_class=MultinomialNB,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "alpha": KwargSpec(
                default=1.0, help="Additive (Laplace/Lidstone) smoothing parameter."
            ),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="LinearSVC",
        import_path="sklearn.svm.LinearSVC",
        sklearn_class=LinearSVC,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "C": KwargSpec(default=1.0, help="Regularization strength (inverse)."),
            "max_iter": KwargSpec(default=1000, help="Maximum solver iterations."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="SVC",
        import_path="sklearn.svm.SVC",
        sklearn_class=SVC,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "C": KwargSpec(default=1.0, help="Regularization strength (inverse)."),
            "kernel": KwargSpec(
                default="rbf", help="Kernel type ('linear'/'poly'/'rbf'/'sigmoid')."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="SVR",
        import_path="sklearn.svm.SVR",
        sklearn_class=SVR,
        archetype="fit",
        task="regression",
        accepted_kwargs={
            "C": KwargSpec(default=1.0, help="Regularization strength (inverse)."),
            "kernel": KwargSpec(
                default="rbf", help="Kernel type ('linear'/'poly'/'rbf'/'sigmoid')."
            ),
        },
        summary_builder=summarize_regressor,
    )
)

register_estimator(
    EstimatorSpec(
        key="LinearDiscriminantAnalysis",
        import_path="sklearn.discriminant_analysis.LinearDiscriminantAnalysis",
        sklearn_class=LinearDiscriminantAnalysis,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "solver": KwargSpec(default="svd", help="Solver ('svd'/'lsqr'/'eigen')."),
        },
        summary_builder=summarize_classifier,
    )
)

register_estimator(
    EstimatorSpec(
        key="QuadraticDiscriminantAnalysis",
        import_path="sklearn.discriminant_analysis.QuadraticDiscriminantAnalysis",
        sklearn_class=QuadraticDiscriminantAnalysis,
        archetype="fit",
        task="classification",
        accepted_kwargs={
            "reg_param": KwargSpec(default=0.0, help="Regularization of the covariance estimate."),
        },
        summary_builder=summarize_classifier,
    )
)
