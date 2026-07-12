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
from .auto_eda import AutoEda
from .cast_types import CastTypes
from .cluster_detect import ClusterDetect
from .correlation import Correlation
from .cross_validate import CrossValidate
from .describe import Describe
from .describe_relation import DescribeRelation
from .diagnostic_frame import DiagnosticFrame
from .diagnostic_model import DiagnosticModel
from .discretize import Discretize
from .distribution_summary import DistributionSummary
from .drop_missing import DropMissing
from .eda_profile import EdaProfile
from .encode_categorical import EncodeCategorical
from .eval_label import EvalLabel
from .eval_run import EvalRun
from .evaluate import Evaluate
from .explain_error_table import ExplainErrorTable
from .explain_plot_calibration import ExplainPlotCalibration
from .explain_plot_predicted_vs_actual import ExplainPlotPredictedVsActual
from .explain_plot_residuals import ExplainPlotResiduals
from .explain_plot_roc_pr import ExplainPlotRocPr
from .explain_plot_shap_beeswarm import ExplainPlotShapBeeswarm
from .explain_plot_shap_importance import ExplainPlotShapImportance
from .explain_plot_shap_waterfall import ExplainPlotShapWaterfall
from .explain_shap_values import ExplainShapValues
from .filter_rows import FilterRows
from .fit_bayesian_model import FitBayesianModel
from .fit_estimator import FitEstimator
from .fit_gam import FitGAM
from .fit_glm import FitGLM
from .fit_linear_regression import FitLinearRegression
from .fit_mixed_model import FitMixedModel
from .fit_transform import FitTransform
from .generate_features import GenerateFeatures
from .grid_search import GridSearch
from .group_by_aggregate import GroupByAggregate
from .impute import ImputeMissing
from .llm_call import LlmCall
from .llm_prompt import LlmPrompt
from .load_csv import LoadCsv
from .load_json import LoadJson
from .load_parquet import LoadParquet
from .load_sample import LoadSample
from .markdown_note import MarkdownNote
from .missingness import Missingness
from .nn_linear import NnLinear
from .nn_module import NnModule
from .nn_relu import NnReLU
from .pipeline import Pipeline
from .predict import Predict
from .query_builder import QueryBuilder
from .report import GenerateHtmlSummary
from .scale_features import ScaleFeatures
from .select_columns import SelectColumns
from .sql_query import SqlQuery
from .summarize import Summarize
from .train import TrainClassifier
from .train_random_forest import TrainRandomForest
from .train_regressor import TrainRegressor
from .train_test_split import TrainTestSplit
from .transform import Transform
from .ttest import TTest
from .viz_plot import VizPlot
from .viz_plot_acf import VizPlotAcf
from .viz_plot_coefficients import VizPlotCoefficients
from .viz_plot_confusion_matrix import VizPlotConfusionMatrix
from .viz_plot_correlation_heatmap import VizPlotCorrelationHeatmap
from .viz_plot_qq import VizPlotQQ
from .viz_plot_residuals import VizPlotResiduals

__all__ = [
    "Anova",
    "ApplyEstimator",
    "AutoEda",
    "CastTypes",
    "ClusterDetect",
    "Correlation",
    "CrossValidate",
    "Describe",
    "DescribeRelation",
    "DiagnosticFrame",
    "DiagnosticModel",
    "Discretize",
    "DistributionSummary",
    "DropMissing",
    "EdaProfile",
    "EncodeCategorical",
    "EvalLabel",
    "EvalRun",
    "Evaluate",
    "ExplainErrorTable",
    "ExplainPlotCalibration",
    "ExplainPlotPredictedVsActual",
    "ExplainPlotResiduals",
    "ExplainPlotRocPr",
    "ExplainPlotShapBeeswarm",
    "ExplainPlotShapImportance",
    "ExplainPlotShapWaterfall",
    "ExplainShapValues",
    "FilterRows",
    "FitBayesianModel",
    "FitEstimator",
    "FitGAM",
    "FitGLM",
    "FitLinearRegression",
    "FitMixedModel",
    "FitTransform",
    "GenerateFeatures",
    "GenerateHtmlSummary",
    "GridSearch",
    "GroupByAggregate",
    "ImputeMissing",
    "LlmCall",
    "LlmPrompt",
    "LoadCsv",
    "LoadJson",
    "LoadParquet",
    "LoadSample",
    "MarkdownNote",
    "Missingness",
    "NnLinear",
    "NnModule",
    "NnReLU",
    "Pipeline",
    "Predict",
    "QueryBuilder",
    "ScaleFeatures",
    "SelectColumns",
    "SqlQuery",
    "Summarize",
    "TrainClassifier",
    "TrainRandomForest",
    "TrainRegressor",
    "TrainTestSplit",
    "Transform",
    "TTest",
    "VizPlot",
    "VizPlotAcf",
    "VizPlotCoefficients",
    "VizPlotConfusionMatrix",
    "VizPlotCorrelationHeatmap",
    "VizPlotQQ",
    "VizPlotResiduals",
]
