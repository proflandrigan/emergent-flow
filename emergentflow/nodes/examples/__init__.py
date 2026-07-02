"""
emergentflow.nodes.examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node definitions that conform to the Story 3 contract.

These are the real, library-backed Story 8 reference node families — no
longer the dependency-free toys from Story 3. Each node's ``execute`` and
``codegen`` both route through the same ``ef.*`` public-op wrapper
(``emergentflow.data``, ``emergentflow.clean``, ``emergentflow.stats``,
``emergentflow.ml``, ``emergentflow.reports`` — backed by pandas, scikit-learn,
statsmodels, and ydata-profiling respectively), which keeps ADR 0002's
"execute == compiled code" invariant true by construction and models the
Story 7 "thin wrapper" rule: exported code calls SDK functions rather than
re-implementing them inline.
"""

from .anova import Anova
from .apply_estimator import ApplyEstimator
from .cast_types import CastTypes
from .cluster_detect import ClusterDetect
from .correlation import Correlation
from .cross_validate import CrossValidate
from .describe import Describe
from .drop_missing import DropMissing
from .evaluate import Evaluate
from .filter_rows import FilterRows
from .fit_estimator import FitEstimator
from .fit_transform import FitTransform
from .grid_search import GridSearch
from .impute import ImputeMissing
from .load_csv import LoadCsv
from .load_json import LoadJson
from .load_parquet import LoadParquet
from .load_sample import LoadSample
from .nn_linear import NnLinear
from .nn_module import NnModule
from .nn_relu import NnReLU
from .pipeline import Pipeline
from .predict import Predict
from .report import GenerateHtmlSummary
from .select_columns import SelectColumns
from .train import TrainClassifier
from .train_random_forest import TrainRandomForest
from .train_regressor import TrainRegressor
from .train_test_split import TrainTestSplit
from .transform import Transform
from .ttest import TTest

__all__ = [
    "Anova",
    "ApplyEstimator",
    "CastTypes",
    "ClusterDetect",
    "Correlation",
    "CrossValidate",
    "Describe",
    "DropMissing",
    "Evaluate",
    "FilterRows",
    "FitEstimator",
    "FitTransform",
    "GenerateHtmlSummary",
    "GridSearch",
    "ImputeMissing",
    "LoadCsv",
    "LoadJson",
    "LoadParquet",
    "LoadSample",
    "NnLinear",
    "NnModule",
    "NnReLU",
    "Pipeline",
    "Predict",
    "SelectColumns",
    "TrainClassifier",
    "TrainRandomForest",
    "TrainRegressor",
    "TrainTestSplit",
    "Transform",
    "TTest",
]
