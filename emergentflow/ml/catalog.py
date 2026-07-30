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

from sklearn.cluster import (
    DBSCAN,
    AgglomerativeClustering,
    Birch,
    KMeans,
    MeanShift,
    MiniBatchKMeans,
    SpectralClustering,
)
from sklearn.covariance import EllipticEnvelope
from sklearn.decomposition import (
    NMF,
    PCA,
    FactorAnalysis,
    FastICA,
    TruncatedSVD,
)
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
    IsolationForest,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.feature_selection import (
    RFE,
    SelectFromModel,
    SelectKBest,
    VarianceThreshold,
    f_classif,
    f_regression,
    mutual_info_classif,
    mutual_info_regression,
)
from sklearn.linear_model import (
    ElasticNet,
    Lasso,
    LogisticRegression,
    Ridge,
    SGDClassifier,
    SGDRegressor,
)
from sklearn.manifold import TSNE, Isomap
from sklearn.mixture import BayesianGaussianMixture, GaussianMixture
from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor, LocalOutlierFactor
from sklearn.preprocessing import (
    Binarizer,
    KBinsDiscretizer,
    MaxAbsScaler,
    MinMaxScaler,
    Normalizer,
    OneHotEncoder,
    OrdinalEncoder,
    PolynomialFeatures,
    PowerTransformer,
    RobustScaler,
    StandardScaler,
    TargetEncoder,
)
from sklearn.svm import SVC, SVR, LinearSVC, OneClassSVM
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from emergentflow.ml.registry import EstimatorSpec, KwargSpec, register_estimator
from emergentflow.ml.summaries import (
    summarize_classifier,
    summarize_clustering,
    summarize_decomposition,
    summarize_outlier,
    summarize_preprocessing,
    summarize_regressor,
)

register_estimator(
    EstimatorSpec(
        key="LogisticRegression",
        description="Linear classifier that models class probabilities via the logistic function.",
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
        description="Standardizes features by removing the mean and scaling to unit variance.",
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
        key="MinMaxScaler",
        description="Scales features to a given range, typically [0, 1].",
        import_path="sklearn.preprocessing.MinMaxScaler",
        sklearn_class=MinMaxScaler,
        archetype="fit_transform",
        accepted_kwargs={
            "feature_range": KwargSpec(
                default=(0, 1), help="Desired range of transformed data (min, max)."
            ),
            "clip": KwargSpec(default=False, help="Clip transformed values to feature_range."),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="RobustScaler",
        description="Scales features using statistics robust to outliers (median and IQR).",
        import_path="sklearn.preprocessing.RobustScaler",
        sklearn_class=RobustScaler,
        archetype="fit_transform",
        accepted_kwargs={
            "with_centering": KwargSpec(default=True, help="Center the data before scaling."),
            "with_scaling": KwargSpec(default=True, help="Scale the data to the IQR."),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="Normalizer",
        description="Scales each sample (row) to unit norm.",
        import_path="sklearn.preprocessing.Normalizer",
        sklearn_class=Normalizer,
        archetype="fit_transform",
        accepted_kwargs={
            "norm": KwargSpec(default="l2", help="Norm to use ('l1'/'l2'/'max')."),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="OneHotEncoder",
        description="Encodes categorical features as one-hot binary columns.",
        import_path="sklearn.preprocessing.OneHotEncoder",
        sklearn_class=OneHotEncoder,
        archetype="fit_transform",
        accepted_kwargs={
            "handle_unknown": KwargSpec(
                default="error", help="How to handle unknown categories at transform time."
            ),
            "sparse_output": KwargSpec(
                default=False, help="Return a dense array instead of a sparse matrix."
            ),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="OrdinalEncoder",
        description="Encodes categorical features as ordinal integer codes.",
        import_path="sklearn.preprocessing.OrdinalEncoder",
        sklearn_class=OrdinalEncoder,
        archetype="fit_transform",
        accepted_kwargs={
            "handle_unknown": KwargSpec(
                default="error", help="How to handle unknown categories at transform time."
            ),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="PolynomialFeatures",
        description="Generates polynomial and interaction features from existing features.",
        import_path="sklearn.preprocessing.PolynomialFeatures",
        sklearn_class=PolynomialFeatures,
        archetype="fit_transform",
        accepted_kwargs={
            "degree": KwargSpec(default=2, help="The degree of the polynomial features."),
            "include_bias": KwargSpec(
                default=True, help="Include a bias (intercept) column of all ones."
            ),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="MaxAbsScaler",
        description="Scales each feature by its maximum absolute value, preserving sparsity.",
        import_path="sklearn.preprocessing.MaxAbsScaler",
        sklearn_class=MaxAbsScaler,
        archetype="fit_transform",
        accepted_kwargs={},
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="PowerTransformer",
        description=(
            "Applies a power transform (Yeo-Johnson or Box-Cox) to make data more Gaussian-like."
        ),
        import_path="sklearn.preprocessing.PowerTransformer",
        sklearn_class=PowerTransformer,
        archetype="fit_transform",
        accepted_kwargs={
            "method": KwargSpec(
                default="yeo-johnson", help="Power transform method ('yeo-johnson'/'box-cox')."
            ),
            "standardize": KwargSpec(
                default=True, help="Apply zero-mean, unit-variance normalization after transform."
            ),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="TargetEncoder",
        description=(
            "Encodes categorical features using the target mean, with built-in shrinkage "
            "to prevent overfitting."
        ),
        import_path="sklearn.preprocessing.TargetEncoder",
        sklearn_class=TargetEncoder,
        archetype="fit_transform",
        accepted_kwargs={
            "smooth": KwargSpec(
                default="auto", help="Smoothing factor ('auto' or a positive float)."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="KBinsDiscretizer",
        description=(
            "Bins continuous features into discrete intervals (uniform, quantile, or k-means)."
        ),
        import_path="sklearn.preprocessing.KBinsDiscretizer",
        sklearn_class=KBinsDiscretizer,
        archetype="fit_transform",
        accepted_kwargs={
            "n_bins": KwargSpec(default=5, help="Number of bins to produce."),
            "encode": KwargSpec(
                default="ordinal", help="Encoding method ('onehot'/'onehot-dense'/'ordinal')."
            ),
            "strategy": KwargSpec(
                default="quantile", help="Binning strategy ('uniform'/'quantile'/'kmeans')."
            ),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="Binarizer",
        description="Thresholds feature values to 0/1 based on a configurable cutoff.",
        import_path="sklearn.preprocessing.Binarizer",
        sklearn_class=Binarizer,
        archetype="fit_transform",
        accepted_kwargs={
            "threshold": KwargSpec(
                default=0.0, help="Values above this are set to 1; at or below to 0."
            ),
        },
        summary_builder=summarize_preprocessing,
    )
)

register_estimator(
    EstimatorSpec(
        key="KMeans",
        description="Partitions data into k clusters by minimizing within-cluster variance.",
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
        key="MiniBatchKMeans",
        description="A faster, mini-batch variant of KMeans clustering for large datasets.",
        import_path="sklearn.cluster.MiniBatchKMeans",
        sklearn_class=MiniBatchKMeans,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_clusters": KwargSpec(default=8, help="Number of clusters to form."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
            "batch_size": KwargSpec(default=1024, help="Size of the mini batches."),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="DBSCAN",
        description="Density-based clustering that groups closely packed points "
        "and flags outliers as noise.",
        import_path="sklearn.cluster.DBSCAN",
        sklearn_class=DBSCAN,
        archetype="cluster_detect",
        accepted_kwargs={
            "eps": KwargSpec(
                default=0.5,
                help="Maximum distance between two samples for one to be "
                "considered a neighbor of the other.",
            ),
            "min_samples": KwargSpec(
                default=5,
                help="Number of samples in a neighborhood for a point to be "
                "considered a core point.",
            ),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="AgglomerativeClustering",
        description="Builds nested clusters by successively merging or splitting groups.",
        import_path="sklearn.cluster.AgglomerativeClustering",
        sklearn_class=AgglomerativeClustering,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_clusters": KwargSpec(default=2, help="Number of clusters to find."),
            "linkage": KwargSpec(
                default="ward", help="Linkage criterion ('ward'/'complete'/'average'/'single')."
            ),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="SpectralClustering",
        description="Clusters data using the eigenvalues of a similarity matrix "
        "for dimensionality reduction before clustering.",
        import_path="sklearn.cluster.SpectralClustering",
        sklearn_class=SpectralClustering,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_clusters": KwargSpec(default=8, help="Number of clusters to find."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="MeanShift",
        description="Clustering by iteratively shifting points toward the mode of their "
        "neighborhood density.",
        import_path="sklearn.cluster.MeanShift",
        sklearn_class=MeanShift,
        archetype="cluster_detect",
        accepted_kwargs={
            "bandwidth": KwargSpec(default=None, help="Kernel bandwidth (None = auto-estimated)."),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="Birch",
        description="Incrementally builds a tree of cluster summaries for memory-efficient "
        "clustering of large datasets.",
        import_path="sklearn.cluster.Birch",
        sklearn_class=Birch,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_clusters": KwargSpec(
                default=3, help="Number of clusters after the final clustering step."
            ),
            "threshold": KwargSpec(
                default=0.5, help="Radius threshold for a new subcluster to be started."
            ),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="GaussianMixture",
        description="Fits a mixture of Gaussian distributions to model cluster membership "
        "probabilistically.",
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
        key="BayesianGaussianMixture",
        description="A Gaussian mixture model fit with variational Bayesian inference, which can "
        "prune unneeded components.",
        import_path="sklearn.mixture.BayesianGaussianMixture",
        sklearn_class=BayesianGaussianMixture,
        archetype="cluster_detect",
        accepted_kwargs={
            "n_components": KwargSpec(default=1, help="Maximum number of mixture components."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_clustering,
    )
)

register_estimator(
    EstimatorSpec(
        key="Ridge",
        description="Linear regression with L2 regularization to shrink coefficients and "
        "reduce overfitting.",
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
        description="Linear regression with L1 regularization that can shrink some "
        "coefficients to zero.",
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
        description="Linear regression combining L1 and L2 regularization penalties.",
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
        description="Linear classifier fit via stochastic gradient descent, supporting "
        "multiple loss functions.",
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
        description="Linear regressor fit via stochastic gradient descent.",
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
        description="Classifies data by learning simple decision rules inferred from "
        "feature splits.",
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
        description="Predicts continuous values by learning decision rules inferred from "
        "feature splits.",
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
        description="An ensemble of randomized decision trees combined by majority vote for "
        "classification.",
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
        description="An ensemble of randomized decision trees combined by averaging for "
        "regression.",
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
        description="An ensemble of extremely randomized trees for classification, "
        "trading some bias for reduced variance.",
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
        description="An ensemble of extremely randomized trees for regression, "
        "trading some bias for reduced variance.",
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
        description="Builds an additive ensemble of trees that sequentially correct "
        "prior errors for classification.",
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
        description="Builds an additive ensemble of trees that sequentially correct "
        "prior errors for regression.",
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
        description="A histogram-based gradient boosting classifier, fast on large datasets.",
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
        description="A histogram-based gradient boosting regressor, fast on large datasets.",
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
        description="An ensemble that combines weak classifiers, reweighting "
        "misclassified samples each round.",
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
        description="An ensemble that combines weak regressors, reweighting "
        "poorly predicted samples each round.",
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
        description="An ensemble that fits classifiers on random subsets of the data "
        "and aggregates their votes.",
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
        description="An ensemble that fits regressors on random subsets of the data "
        "and averages their predictions.",
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
        description="Classifies a sample by majority vote among its nearest neighbors.",
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
        description="Predicts a value by averaging its nearest neighbors' targets.",
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
        description="Naive Bayes classifier assuming features are normally distributed "
        "within each class.",
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
        description="Naive Bayes classifier suited to discrete count data such as "
        "word frequencies.",
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
        description="Linear support vector classifier that finds a maximum-margin "
        "separating hyperplane.",
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
        description="Support vector classifier that can use kernel functions to separate "
        "non-linearly-separable data.",
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
        description="Support vector regressor that fits within a margin of tolerance "
        "using kernel functions.",
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
        description="Classifies by finding a linear combination of features that best "
        "separates classes.",
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
        description="Classifies using a quadratic decision boundary fit per class, assuming "
        "Gaussian class-conditional densities.",
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

register_estimator(
    EstimatorSpec(
        key="PCA",
        description="Reduces dimensionality by projecting data onto directions of maximum "
        "variance.",
        import_path="sklearn.decomposition.PCA",
        sklearn_class=PCA,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(default=2, help="Number of components to keep."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="TruncatedSVD",
        description="Reduces dimensionality via truncated singular value decomposition, "
        "effective on sparse data.",
        import_path="sklearn.decomposition.TruncatedSVD",
        sklearn_class=TruncatedSVD,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(default=2, help="Desired dimensionality of output data."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="NMF",
        description="Factorizes data into non-negative components, useful for "
        "parts-based representations.",
        import_path="sklearn.decomposition.NMF",
        sklearn_class=NMF,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(default=2, help="Number of components."),
            "max_iter": KwargSpec(default=200, help="Maximum number of iterations."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="FastICA",
        description="Separates a multivariate signal into additive, statistically "
        "independent components.",
        import_path="sklearn.decomposition.FastICA",
        sklearn_class=FastICA,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(default=2, help="Number of components to use."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="FactorAnalysis",
        description="Models observed features as linear combinations of a smaller set of "
        "latent factors plus noise.",
        import_path="sklearn.decomposition.FactorAnalysis",
        sklearn_class=FactorAnalysis,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(
                default=2, help="Number of latent factors (dimensionality of the state space)."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="TSNE",
        description="Non-linear dimensionality reduction that embeds high-dimensional data "
        "for visualization, preserving local structure.",
        import_path="sklearn.manifold.TSNE",
        sklearn_class=TSNE,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(default=2, help="Dimension of the embedded space."),
            "perplexity": KwargSpec(
                default=30.0,
                help="Related to the number of nearest neighbors used in other manifold "
                "learning algorithms.",
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="Isomap",
        description="Non-linear dimensionality reduction that preserves geodesic distances "
        "along a manifold.",
        import_path="sklearn.manifold.Isomap",
        sklearn_class=Isomap,
        archetype="fit_transform",
        accepted_kwargs={
            "n_components": KwargSpec(default=2, help="Number of coordinates for the manifold."),
            "n_neighbors": KwargSpec(
                default=5, help="Number of neighbors to consider for each point."
            ),
        },
        summary_builder=summarize_decomposition,
    )
)

register_estimator(
    EstimatorSpec(
        key="SelectKBest",
        description="Selects the k highest-scoring features according to a statistical "
        "scoring function.",
        import_path="sklearn.feature_selection.SelectKBest",
        sklearn_class=SelectKBest,
        archetype="fit_transform",
        is_feature_selector=True,
        accepted_kwargs={
            "k": KwargSpec(default=10, help="Number of top features to select."),
            "score_func": KwargSpec(
                default="f_classif",
                help=(
                    "Scoring function: 'f_classif'/'mutual_info_classif' for a categorical "
                    "target, 'f_regression'/'mutual_info_regression' for a continuous one."
                ),
                choices={
                    "f_classif": f_classif,
                    "f_regression": f_regression,
                    "mutual_info_classif": mutual_info_classif,
                    "mutual_info_regression": mutual_info_regression,
                },
            ),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="VarianceThreshold",
        description="Removes features whose variance falls below a given threshold.",
        import_path="sklearn.feature_selection.VarianceThreshold",
        sklearn_class=VarianceThreshold,
        archetype="fit_transform",
        is_feature_selector=True,
        accepted_kwargs={
            "threshold": KwargSpec(
                default=0.0, help="Features with variance below this are removed."
            ),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="RFE",
        description="Recursively eliminates the lowest-ranked features using a fit-archetype "
        "estimator's coefficients or feature importances.",
        import_path="sklearn.feature_selection.RFE",
        sklearn_class=RFE,
        archetype="fit_transform",
        is_feature_selector=True,
        accepted_kwargs={
            "estimator": KwargSpec(
                default="LogisticRegression",
                estimator_ref=True,
                help="Fit-archetype estimator used to rank features via coef_/"
                "feature_importances_.",
            ),
            "n_features_to_select": KwargSpec(
                default=None,
                help="Number (int) or fraction (float) of features to select; unset selects half.",
            ),
            "step": KwargSpec(
                default=1,
                help="Number (int) or fraction (float) of features to remove at each iteration.",
            ),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="SelectFromModel",
        description="Selects features whose importance/coefficient from a fit-archetype "
        "estimator meets a threshold.",
        import_path="sklearn.feature_selection.SelectFromModel",
        sklearn_class=SelectFromModel,
        archetype="fit_transform",
        is_feature_selector=True,
        accepted_kwargs={
            "estimator": KwargSpec(
                default="RandomForestClassifier",
                estimator_ref=True,
                help="Fit-archetype estimator whose feature_importances_/coef_ scores features.",
            ),
            "threshold": KwargSpec(
                default=None,
                help="Importance threshold below which features are dropped; unset uses "
                "the estimator's default heuristic ('mean').",
            ),
            "max_features": KwargSpec(default=None, help="Maximum number of features to select."),
        },
    )
)

register_estimator(
    EstimatorSpec(
        key="IsolationForest",
        description="Detects anomalies by isolating observations via random recursive "
        "partitioning.",
        import_path="sklearn.ensemble.IsolationForest",
        sklearn_class=IsolationForest,
        archetype="outlier_detect",
        detects_outliers=True,
        accepted_kwargs={
            "n_estimators": KwargSpec(default=100, help="Number of base estimators."),
            "contamination": KwargSpec(
                default="auto", help="Expected proportion of outliers in the data."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_outlier,
    )
)

register_estimator(
    EstimatorSpec(
        key="LocalOutlierFactor",
        description="Detects anomalies by comparing a sample's local density to that of "
        "its neighbors.",
        import_path="sklearn.neighbors.LocalOutlierFactor",
        sklearn_class=LocalOutlierFactor,
        archetype="outlier_detect",
        detects_outliers=True,
        accepted_kwargs={
            "n_neighbors": KwargSpec(default=20, help="Number of neighbors to use."),
            "contamination": KwargSpec(
                default="auto", help="Expected proportion of outliers in the data."
            ),
            "novelty": KwargSpec(
                default=True,
                help="Must be True to support predicting on data after a separate fit().",
            ),
        },
        summary_builder=summarize_outlier,
    )
)

register_estimator(
    EstimatorSpec(
        key="OneClassSVM",
        description="Detects anomalies by learning a boundary that encloses the bulk of "
        "normal data.",
        import_path="sklearn.svm.OneClassSVM",
        sklearn_class=OneClassSVM,
        archetype="outlier_detect",
        detects_outliers=True,
        accepted_kwargs={
            "kernel": KwargSpec(
                default="rbf", help="Kernel type ('linear'/'poly'/'rbf'/'sigmoid')."
            ),
            "nu": KwargSpec(default=0.5, help="Upper bound on the fraction of training errors."),
        },
        summary_builder=summarize_outlier,
    )
)

register_estimator(
    EstimatorSpec(
        key="EllipticEnvelope",
        description="Detects anomalies by fitting a robust covariance ellipse to normal data.",
        import_path="sklearn.covariance.EllipticEnvelope",
        sklearn_class=EllipticEnvelope,
        archetype="outlier_detect",
        detects_outliers=True,
        accepted_kwargs={
            "contamination": KwargSpec(
                default=0.1, help="Expected proportion of outliers in the data."
            ),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        },
        summary_builder=summarize_outlier,
    )
)
