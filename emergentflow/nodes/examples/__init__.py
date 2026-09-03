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
from .assert_data import AssertData
from .auto_eda import AutoEda
from .blend_models import BlendModels
from .bootstrap_ci import BootstrapCi
from .build_report import BuildReport
from .calibrate_model import CalibrateModel
from .cast_types import CastTypes
from .chi_square import ChiSquare
from .clean_text import CleanText
from .cluster_detect import ClusterDetect
from .cluster_metrics import ClusterMetrics
from .cluster_stability import ClusterStability
from .cohort_retention import CohortRetention
from .compare_models import CompareModels
from .composite import Composite
from .concat import Concat
from .correct_pvalues import CorrectPvalues
from .correlation import Correlation
from .cross_validate import CrossValidate
from .crosstab import Crosstab
from .custom_code import CustomCode
from .data_dictionary import DataDictionary
from .deduplicate import Deduplicate
from .derive_column import DeriveColumn
from .describe import Describe
from .describe_relation import DescribeRelation
from .detect_outliers import DetectOutliers
from .diagnostic_frame import DiagnosticFrame
from .diagnostic_model import DiagnosticModel
from .discretize import Discretize
from .distribution_summary import DistributionSummary
from .drop_missing import DropMissing
from .eda_profile import EdaProfile
from .embed_text import EmbedText
from .encode_categorical import EncodeCategorical
from .encode_lists import EncodeLists
from .ensemble_model import EnsembleModel
from .eval_judge import EvalJudge
from .eval_label import EvalLabel
from .eval_run import EvalRun
from .eval_score import EvalScore
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
from .explode_lists import ExplodeLists
from .filter_rows import FilterRows
from .finalize_model import FinalizeModel
from .fit_bayesian_model import FitBayesianModel
from .fit_estimator import FitEstimator
from .fit_gam import FitGAM
from .fit_glm import FitGLM
from .fit_linear_regression import FitLinearRegression
from .fit_mixed_model import FitMixedModel
from .fit_survival import FitSurvival
from .fit_transform import FitTransform
from .forecast_arima import ForecastArima
from .forecast_ets import ForecastEts
from .funnel import Funnel
from .fuzzy_join import FuzzyJoin
from .generate_features import GenerateFeatures
from .grid_search import GridSearch
from .group_by_aggregate import GroupByAggregate
from .group_container import GroupContainer
from .http_fetch import HttpFetch
from .impute import ImputeMissing
from .kruskal import Kruskal
from .llm_call import LlmCall
from .llm_prompt import LlmPrompt
from .llm_prompt_from_file import LlmPromptFromFile
from .load_csv import LoadCsv
from .load_documents import LoadDocuments
from .load_excel import LoadExcel
from .load_google_sheet import LoadGoogleSheet
from .load_json import LoadJson
from .load_model import LoadModel
from .load_parquet import LoadParquet
from .load_sample import LoadSample
from .mann_whitney import MannWhitney
from .callout import CalloutNode
from .markdown_note import MarkdownNote
from .merge import Merge
from .missingness import Missingness
from .nn_linear import NnLinear
from .nn_module import NnModule
from .nn_relu import NnReLU
from .optimize_threshold import OptimizeThreshold
from .outlier_detect import OutlierDetect
from .outlier_summary import OutlierSummary
from .parse_dates import ParseDates
from .pipeline import Pipeline
from .power_analysis import PowerAnalysis
from .predict import Predict
from .prepare_interactions import PrepareInteractions
from .proportion_confint import ProportionConfint
from .proportions import TestProportions
from .query_builder import QueryBuilder
from .recommend_build_sequences import RecommendBuildSequences
from .recommend_by_embedding import RecommendByEmbedding
from .recommend_compare import RecommendCompare
from .recommend_encode_categorical_features import RecommendEncodeCategoricalFeatures
from .recommend_evaluate import RecommendEvaluate
from .recommend_fit import RecommendFit
from .recommend_fit_sequence import RecommendFitSequence
from .recommend_fit_two_tower import RecommendFitTwoTower
from .recommend_hybrid_switching import HybridSwitching
from .recommend_hybrid_weighted import HybridWeighted
from .recommend_load_model import RecommendLoadModel
from .recommend_recommend import Recommend
from .recommend_save_model import RecommendSaveModel
from .recommend_similar_items import SimilarItems
from .recommend_temporal_split import RecommendTemporalSplit
from .recommend_weight_interactions_by_recency import RecommendWeightInteractionsByRecency
from .redact_pii import RedactPii
from .reduce_dimensions import ReduceDimensions
from .report import GenerateHtmlSummary
from .reshape import Reshape
from .sample_rows import SampleRows
from .save_model import SaveModel
from .scale_features import ScaleFeatures
from .seasonal_decompose import SeasonalDecompose
from .select_columns import SelectColumns
from .select_features import SelectFeatures
from .semi_join import SemiJoin
from .sort import Sort
from .sql_query import SqlQuery
from .stack_models import StackModels
from .summarize import Summarize
from .survival_curve import SurvivalCurve
from .train import TrainClassifier
from .train_random_forest import TrainRandomForest
from .train_regressor import TrainRegressor
from .train_test_split import TrainTestSplit
from .transform import Transform
from .ts_difference import TsDifference
from .ts_ewma import TsEwma
from .ts_lag_features import TsLagFeatures
from .ts_rolling_aggregate import TsRollingAggregate
from .ts_time_weighted_aggregate import TsTimeWeightedAggregate
from .ttest import TTest
from .tune_model import TuneModel
from .viz_plot import VizPlot
from .viz_plot_acf import VizPlotAcf
from .viz_plot_coefficients import VizPlotCoefficients
from .viz_plot_confusion_matrix import VizPlotConfusionMatrix
from .viz_plot_correlation_heatmap import VizPlotCorrelationHeatmap
from .viz_plot_coverage_vs_accuracy import VizPlotCoverageVsAccuracy
from .viz_plot_metric_comparison import VizPlotMetricComparison
from .viz_plot_popularity_distribution import VizPlotPopularityDistribution
from .viz_plot_precision_recall_curve import VizPlotPrecisionRecallCurve
from .viz_plot_projection import VizPlotProjection
from .viz_plot_qq import VizPlotQQ
from .viz_plot_residuals import VizPlotResiduals
from .wilcoxon import Wilcoxon

__all__ = [
    "Anova",
    "ApplyEstimator",
    "AssertData",
    "AutoEda",
    "BlendModels",
    "BootstrapCi",
    "BuildReport",
    "CalibrateModel",
    "CalloutNode",
    "CastTypes",
    "ChiSquare",
    "CleanText",
    "ClusterDetect",
    "ClusterMetrics",
    "ClusterStability",
    "CohortRetention",
    "CompareModels",
    "Composite",
    "Concat",
    "CorrectPvalues",
    "Correlation",
    "Crosstab",
    "CrossValidate",
    "CustomCode",
    "DataDictionary",
    "Deduplicate",
    "DeriveColumn",
    "Describe",
    "DescribeRelation",
    "DetectOutliers",
    "DiagnosticFrame",
    "DiagnosticModel",
    "Discretize",
    "DistributionSummary",
    "DropMissing",
    "EdaProfile",
    "EmbedText",
    "EncodeCategorical",
    "EncodeLists",
    "EnsembleModel",
    "EvalJudge",
    "EvalLabel",
    "EvalRun",
    "EvalScore",
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
    "ExplodeLists",
    "FilterRows",
    "FinalizeModel",
    "FitBayesianModel",
    "FitEstimator",
    "FitSurvival",
    "FitGAM",
    "FitGLM",
    "FitLinearRegression",
    "FitMixedModel",
    "FitTransform",
    "ForecastArima",
    "ForecastEts",
    "Funnel",
    "FuzzyJoin",
    "GenerateFeatures",
    "GenerateHtmlSummary",
    "GridSearch",
    "GroupByAggregate",
    "GroupContainer",
    "HttpFetch",
    "HybridSwitching",
    "HybridWeighted",
    "ImputeMissing",
    "Kruskal",
    "LlmCall",
    "LlmPrompt",
    "LlmPromptFromFile",
    "LoadCsv",
    "LoadDocuments",
    "LoadExcel",
    "LoadGoogleSheet",
    "LoadJson",
    "LoadModel",
    "LoadParquet",
    "LoadSample",
    "MannWhitney",
    "MarkdownNote",
    "Merge",
    "Missingness",
    "NnLinear",
    "NnModule",
    "NnReLU",
    "OptimizeThreshold",
    "OutlierDetect",
    "OutlierSummary",
    "ParseDates",
    "Pipeline",
    "PowerAnalysis",
    "ProportionConfint",
    "Predict",
    "PrepareInteractions",
    "QueryBuilder",
    "Recommend",
    "RecommendByEmbedding",
    "RecommendBuildSequences",
    "RecommendCompare",
    "RecommendEncodeCategoricalFeatures",
    "RecommendEvaluate",
    "RecommendFit",
    "RecommendFitSequence",
    "RecommendFitTwoTower",
    "RecommendLoadModel",
    "RecommendSaveModel",
    "RecommendTemporalSplit",
    "RecommendWeightInteractionsByRecency",
    "RedactPii",
    "ReduceDimensions",
    "Reshape",
    "SampleRows",
    "SaveModel",
    "ScaleFeatures",
    "SeasonalDecompose",
    "SelectColumns",
    "SelectFeatures",
    "SemiJoin",
    "SimilarItems",
    "Sort",
    "SurvivalCurve",
    "SqlQuery",
    "StackModels",
    "Summarize",
    "TestProportions",
    "TrainClassifier",
    "TrainRandomForest",
    "TrainRegressor",
    "TrainTestSplit",
    "Transform",
    "TsDifference",
    "TsEwma",
    "TsLagFeatures",
    "TsRollingAggregate",
    "TsTimeWeightedAggregate",
    "TTest",
    "TuneModel",
    "VizPlot",
    "VizPlotAcf",
    "VizPlotCoefficients",
    "VizPlotConfusionMatrix",
    "VizPlotCorrelationHeatmap",
    "VizPlotCoverageVsAccuracy",
    "VizPlotMetricComparison",
    "VizPlotPopularityDistribution",
    "VizPlotPrecisionRecallCurve",
    "VizPlotProjection",
    "VizPlotQQ",
    "VizPlotResiduals",
    "Wilcoxon",
]
